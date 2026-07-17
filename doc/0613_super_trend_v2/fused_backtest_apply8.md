## 实施计划：大盘感知的 operable_score 重训练

我们将分四步完成：数据准备、特征增强、模型重训练、集成回测验证。

---

### 第一步：获取大盘数据并计算市场环境指标

使用沪深300指数（000300）的日线数据。假设数据来源为已有的 `.day` 文件或 `data_handler` 接口。

```python
# scripts/build_market_regime_features.py

import pandas as pd
import numpy as np

# 加载沪深300日线数据
hs300 = load_index_data('000300')  # 返回 DataFrame，含 date, open, high, low, close, volume
hs300['ma60'] = hs300['close'].rolling(60).mean()
hs300['ma60_slope'] = hs300['ma60'].diff(5) / 5  # 5日斜率

# 定义市场环境判断函数
def get_market_regime(date, hs300_df):
    row = hs300_df[hs300_df['date'] == date]
    if row.empty:
        return 'unknown', 0.0, False
    close = row['close'].values[0]
    ma60 = row['ma60'].values[0]
    slope = row['ma60_slope'].values[0]
    above = close > ma60
    
    if not above and slope < 0:
        regime = 'weak'
    elif above and slope > 0:
        regime = 'strong'
    else:
        regime = 'neutral'
    return regime, slope, above
```

### 第二步：为信号数据集添加大盘特征

将原信号数据集 `super_trend_training_data_v2.csv` (或 operable 训练数据集) 与大盘特征合并：

```python
signals_df = pd.read_csv('data/result/super_trend/super_trend_training_data_v2.csv')
# 提取每条信号的 t0_date
signals_df['t0_date'] = pd.to_datetime(signals_df['t0_date'])
# 为每条信号获取大盘环境
regimes, slopes, aboves = [], [], []
for _, row in signals_df.iterrows():
    r, s, a = get_market_regime(row['t0_date'], hs300)
    regimes.append(r)
    slopes.append(s)
    aboves.append(a)
signals_df['market_regime'] = regimes
signals_df['hs300_ma60_slope'] = slopes
signals_df['hs300_above_ma60'] = aboves.astype(int)
signals_df.to_csv('data/operable_label_with_regime.csv', index=False)
```

### 第三步：重训练 operable 分类器

```python
# scripts/train_operable_with_regime.py

df = pd.read_csv('data/operable_label_with_regime.csv')
# 标签 operable 需要提前存在（根据历史回测盈亏标注）
# 特征列：原有50维 + 结构特征 + 大盘特征
feature_cols = [col for col in df.columns if col not in ['signal_id', 't0_date', 'operable', 'pnl', 'exit_reason']]
# 注意把 market_regime 进行 one-hot 编码
df = pd.get_dummies(df, columns=['market_regime'], prefix='regime')

# 按时序分割
train = df[df['t0_date'] < '2025-02-01']
val = df[(df['t0_date'] >= '2025-02-01') & (df['t0_date'] < '2025-09-01')]
test = df[df['t0_date'] >= '2025-09-01']

X_train, y_train = train[feature_cols], train['operable']
X_val, y_val = val[feature_cols], val['operable']
X_test, y_test = test[feature_cols], test['operable']

# 训练 LightGBM
model = lgb.LGBMClassifier(objective='binary', metric='auc', num_leaves=63, learning_rate=0.05,
                           subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1,
                           scale_pos_weight=len(y_train[y_train==0])/len(y_train[y_train==1]))
model.fit(X_train, y_train, eval_set=[(X_val, y_val)], callbacks=[lgb.early_stopping(50)])
model.booster_.save_model('data/operable_classifier_v2.txt')

# 评估 AUC
print('Train AUC:', roc_auc_score(y_train, model.predict_proba(X_train)[:,1]))
print('Val AUC:', roc_auc_score(y_val, model.predict_proba(X_val)[:,1]))
print('Test AUC:', roc_auc_score(y_test, model.predict_proba(X_test)[:,1]))
```

### 第四步：集成回测并对比

在 `batch_review4_final_backtest.py` 中替换 operable 模型为新版本，重新运行回测，并分别统计弱势月与强势月的表现。对比原系统与新系统的差异。

预期效果：

| 指标 | 原系统 (operable v1) | 新系统 (operable v2, 含大盘) |
|------|---------------------|---------------------------|
| 弱势月交易笔数 | 45 | 明显下降（预计 <25） |
| 弱势月 avg PnL | -1.64% | 改善至 -0.5% 以上 |
| 总交易笔数 | 394 | 可能略降 (360-380) |
| 总 avg PnL | +3.64% | 预期提升至 +4.0%+ |
| PF | 2.99 | 预期提升至 3.2+ |

---

### 第五步：模型解释与特征重要性分析

训练后输出特征重要性，确认大盘特征是否获得了较高的重要性。如果 `regime_weak` 或 `hs300_ma60_slope` 进入 Top 20，则说明模型确实在学习市场环境的影响，而不是仅靠硬编码规则。

---

### 验证验收标准

1. **新 operable 模型 AUC >= 旧模型 (0.74)**，在验证集上无退化。
2. **弱势月交易数减少 20% 以上**，且弱势月 avg PnL 提升 0.5% 以上。
3. **总 avg PnL 和 PF 不下降**，最好有小幅提升。
4. **大盘特征在特征重要性中排名靠前**，证明模型主动学习了市场环境影响。

完成以上步骤，即可确认弱势月份已被系统自动识别和规避，无需手动维护月度黑名单。

请批准执行，我将按此路线生成具体的脚本代码并开始运行。如果你希望我直接提供完整可执行的脚本，我也可以全部写好给你。
