好的，我们按确认的路线图启动。下面是**阶段一的具体实施：构建可操作性过滤器**，这是整个升级的基础。我们将通过分析历史信号成败的归因、识别伪强势特征，训练一个“信号可操作性”二分类器，直接替代或融合当前的 `fine_score` 过滤。

---

## 阶段一：可操作性过滤器（信号成败归因 + 伪强势识别）

### 1.1 目标与产出

- **数据标注**：为 4423 笔信号创建标签 `operable`  
  - `operable=1`：在结构入场 + 动态出场下最终盈亏 > 0（或 MFE 高且能通过某种手法获利）  
  - `operable=0`：无论何种手法，实际可操作收益为负（如伪强势、高开低走等）  
- **分类器训练**：用选股时的 50+ 结构特征预测 `operable`，AUC > 0.7  
- **过滤效果**：在测试集上，被过滤器保留的信号（`operable=1`）在后续精细操作下，整体平均盈亏 ≥ +2%，交易笔数回升至 400+。

### 1.2 具体步骤

#### 步骤1：生成训练数据 `operable_label.csv`

从已有的全量回测结果中提取特征和收益信息：

```python
# scripts/build_operable_dataset.py

import pandas as pd
import numpy as np

# 加载 4423 笔信号的原始特征（含 V2 特征、结构特征）
features_df = pd.read_csv('data/result/super_trend/super_trend_training_data_v2.csv')

# 加载 V3.2 回测明细（包含每笔交易的实际收益）
trades_df = pd.read_csv('doc/0613_super_trend_v2/advanced_backtest_results.csv')
# 假设该文件有 signal_id, entry_style, pnl_pct, exit_reason 等字段

# 合并特征与交易结果
merged = features_df.merge(trades_df[['signal_id', 'pnl_pct', 'exit_reason']], 
                           on='signal_id', how='left')

# 定义 operable 标签
# 1. 实际交易且盈利 -> 1
# 2. 实际交易但亏损，但若用其他手法（如 chase）理论上可盈利？暂时简化为：最终盈亏>0
# 3. 未入场（过期/过滤）的信号，可通过模拟多种手法判断是否有正收益机会（后面补充）
merged['operable'] = np.where(merged['pnl_pct'] > 0, 1, 0)

# 保存数据集
merged.to_csv('data/operable_label.csv', index=False)
```

**注意**：对于过期/被过滤的信号，我们暂时不能直接标记为 0，因为它们可能只是因为手法不对而未被入场。更严谨的做法是：对每个信号，模拟四种手法（deep_pullback/shallow_pullback/chase/skip）选择最佳收益，若最佳收益 > 0 则标记为 1。这可以在阶段二的手法标注中统一完成，届时再回来更新标签。暂时先用已有回测结果标记。

#### 步骤2：特征工程与分类器训练

```python
# scripts/train_operable_classifier.py

import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import roc_auc_score

df = pd.read_csv('data/operable_label.csv')

# 定义特征列（原始 50 特征 + 结构特征如 trend_direction, support_count, resistance_distance等）
# 需要从 market_structure 预先计算并合并进来
feature_cols = [col for col in df.columns if col not in ['signal_id', 'pnl_pct', 'operable', 'exit_reason']]

# 按时序分割
df = df.sort_values('t0_date')
train_idx = df['t0_date'] < '2025-02-21'
val_idx = (df['t0_date'] >= '2025-02-21') & (df['t0_date'] < '2025-09-01')
test_idx = df['t0_date'] >= '2025-09-01'

X_train, y_train = df.loc[train_idx, feature_cols], df.loc[train_idx, 'operable']
X_val, y_val = df.loc[val_idx, feature_cols], df.loc[val_idx, 'operable']
X_test, y_test = df.loc[test_idx, feature_cols], df.loc[test_idx, 'operable']

# 训练
params = {
    'objective': 'binary',
    'metric': 'auc',
    'num_leaves': 63,
    'learning_rate': 0.05,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'reg_alpha': 0.1,
    'scale_pos_weight': len(y_train[y_train==0]) / len(y_train[y_train==1])
}
model = lgb.LGBMClassifier(**params)
model.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=[lgb.early_stopping(50)])

# 评估
print('Train AUC:', roc_auc_score(y_train, model.predict_proba(X_train)[:,1]))
print('Val AUC:', roc_auc_score(y_val, model.predict_proba(X_val)[:,1]))
print('Test AUC:', roc_auc_score(y_test, model.predict_proba(X_test)[:,1]))

# 保存模型
model.booster_.save_model('data/operable_classifier.txt')
```

#### 步骤3：集成到筛选链路

在精排 Top 20 后，对每个信号调用 `operable_score = model.predict_proba(features)[:,1]`，仅保留 `operable_score > threshold`（如 0.5）的信号进入执行端。

**验证**：使用过滤后的信号重新跑 V3.2 回测，观察平均盈亏、交易笔数、胜率是否达到目标（交易数 > 400，盈亏 > +2%）。

---

### 1.3 伪强势识别加强（规则过滤器并行）

在分类器训练的同时，可以先用规则快速过滤掉一些明显弱势的信号，减轻分类器负担。例如：

- **T+1 开盘后 3 天连阴且累计跌幅 > 5%**：大概率是见顶信号。  
- **T+0 之前 20 天相对强度排名持续下降且 < 0.3**：缺乏上升动力。  
- **支撑位数量为 0 且当前价低于所有均线**：无有效支撑，极易下跌。

这些规则可通过历史数据验证：统计满足规则信号的 `operable` 占比，若低于 10%，则直接标记为 `skip`。

---

### 1.4 下一阶段预告

阶段一完成后，我们将拥有一个更纯净的信号池（伪强势被剔除）。随后进入**阶段二**，利用纯净信号池训练操作手法分类器，实现因股施策。那时，我们将重新标注 `operable_label` 为“四种手法下最佳收益 > 0”，从而同时解决过滤和手法分配问题。

现在，请运行上述数据构建和训练脚本。如果 `advanced_backtest_results.csv` 中没有包含每笔信号的 `signal_id`，我们需要先从 `pure_mfe_analysis.csv` 和 V3.2 回测日志中关联出每笔信号的最终收益。需要我帮你写出这个关联代码吗？
