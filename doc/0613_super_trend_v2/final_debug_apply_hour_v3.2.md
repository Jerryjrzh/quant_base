我们从四个阶段推进P0计划，每一步都有明确的输入、输出和验证方式。

---

## 一、生成路径标签（聚类）

```python
# scripts/build_path_labels.py
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# 加载历史信号及未来22天的日线数据（假设已有路径数据）
# 从 pure_mfe_analysis.csv 或已有数据集获取

def compute_path_features(future_df):
    """
    future_df: 某信号T0后22天的日线数据，包含 close, high, low 列
    返回: max_dd, trend_smoothness
    """
    close = future_df['close'].values
    high = future_df['high'].values
    
    # 最大回撤（从峰值到谷底）
    peak = np.maximum.accumulate(high)
    dd = (peak - high) / peak
    max_dd = np.max(dd)
    
    # 趋势平滑度：对收盘价做线性回归的 R²
    x = np.arange(len(close))
    slope, intercept = np.polyfit(x, close, 1)
    y_pred = slope * x + intercept
    ss_res = np.sum((close - y_pred) ** 2)
    ss_tot = np.sum((close - np.mean(close)) ** 2)
    r2 = 1 - (ss_res / ss_tot)
    
    return max_dd, r2

# 遍历所有信号，构建特征矩阵
# ...

# KMeans 聚类
X = np.array([(dd, r2) for dd, r2 in path_features])
kmeans = KMeans(n_clusters=3, random_state=42, n_init=10)
labels = kmeans.fit_predict(X)

# 分析每个聚类的业务含义
for i in range(3):
    idx = labels == i
    print(f"Cluster {i}: avg max_dd={np.mean(X[idx,0]):.3f}, avg r2={np.mean(X[idx,1]):.3f}")
    # 根据回测盈亏进一步确认映射：Smooth, Pullback, Failure

# 保存标签
signals_df['path_label'] = labels
signals_df.to_csv('data/path_labels.csv', index=False)
```

**预期产出**：三个聚类的可视化图，以及人工确认其业务含义。通常回撤小、R²高的对应Smooth；回撤中等、R²中等的对应Pullback；回撤大或R²极低的对应Failure。

---

## 二、提取小时线特征

```python
# backend/hourly_features.py
import pandas as pd
import numpy as np
from typing import Dict, Any

def extract_hourly_features(stock_code, t0_date, data_loader):
    """
    提取T0日前20个交易日的60分钟K线特征。
    返回字典，键为特征名，值为标量。
    """
    # 加载数据
    df = data_loader.get_hourly(stock_code, end_date=t0_date, periods=-400)  # 约20天*4小时
    if df.empty or len(df) < 100:
        return None
    
    df['hourly_return'] = df['close'].pct_change()
    df['range'] = df['high'] - df['low']
    
    # 趋势结构特征
    df['ma20'] = df['close'].rolling(20).mean()
    df['ma60'] = df['close'].rolling(60).mean()
    ma20_slope = (df['ma20'].iloc[-1] - df['ma20'].iloc[-20]) / 20
    close_ma20_ratio = df['close'].iloc[-1] / df['ma20'].iloc[-1] - 1
    
    # 波动特征
    vol_5d = df['hourly_return'].rolling(20).std().iloc[-1]
    avg_amplitude = (df['range'] / df['open']).mean()
    gap_ratio = (abs(df['open'] - df['close'].shift(1)) / df['close'].shift(1) > 0.01).mean()
    
    # 量价关系
    up_vol = df.loc[df['close'] > df['open'], 'volume'].mean()
    down_vol = df.loc[df['close'] < df['open'], 'volume'].mean()
    vol_ratio = up_vol / (down_vol + 1e-6)
    vol_trend = df['volume'].rolling(20).mean().iloc[-1] / df['volume'].rolling(20).mean().iloc[-20]
    
    # 回调形态
    recent_high = df['high'].rolling(20).max().iloc[-20:]
    recent_low = df['low'].rolling(20).min().iloc[-20:]
    drawdown_depth = (recent_high.max() - recent_low.min()) / recent_high.max()
    pullback_recovery_speed = (df['close'].iloc[-1] - df['low'].iloc[-20:].min()) / (df['high'].iloc[-20:].max() - df['low'].iloc[-20:].min())
    
    # 路径特征：创新高频率、回踩均线次数
    rolling_high = df['high'].expanding().max()
    new_high_count = (df['high'] == rolling_high).sum()
    touch_ma20 = (df['low'] <= df['ma20']).sum()
    
    features = {
        'ma20_slope': ma20_slope,
        'close_ma20_ratio': close_ma20_ratio,
        'volatility': vol_5d,
        'avg_amplitude': avg_amplitude,
        'gap_freq': gap_ratio,
        'up_down_vol_ratio': vol_ratio,
        'volume_trend': vol_trend,
        'max_drawdown_recent': drawdown_depth,
        'rebound_ratio': pullback_recovery_speed,
        'new_high_freq': new_high_count / len(df),
        'ma20_touch_freq': touch_ma20 / len(df),
        # ... 可添加更多
    }
    return features
```

**关键点**：所有特征仅使用T0及之前的数据，无未来信息。

---

## 三、训练路径分类器

```python
# scripts/train_path_classifier.py
import pandas as pd
import lightgbm as lgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# 加载标签和特征
labels_df = pd.read_csv('data/path_labels.csv')
features_list = []
for idx, row in labels_df.iterrows():
    feat = extract_hourly_features(row['stock_code'], row['t0_date'], data_loader)
    if feat:
        feat['signal_id'] = idx
        features_list.append(feat)
feat_df = pd.DataFrame(features_list)

# 合并
data = labels_df.merge(feat_df, on='signal_id', how='inner')
X = data.drop(columns=['path_label', 'signal_id'])
y = data['path_label']

# 时序划分（按t0_date）
data = data.sort_values('t0_date')
train = data[data['t0_date'] < '2025-02-01']
val = data[(data['t0_date'] >= '2025-02-01') & (data['t0_date'] < '2025-09-01')]
test = data[data['t0_date'] >= '2025-09-01']

model = lgb.LGBMClassifier(objective='multiclass', num_class=3,
                           num_leaves=31, learning_rate=0.05,
                           n_estimators=200, subsample=0.8, colsample_bytree=0.8)
model.fit(X_train, y_train, eval_set=[(X_val, y_val)],
          callbacks=[lgb.early_stopping(50)])

# 评估
y_pred = model.predict(X_test)
print(classification_report(y_test, y_pred, target_names=['Smooth','Pullback','Failure']))
```

**验收标准**：在测试集上的Accuracy > 0.6（三分类，基线约0.33），且对Failure类的召回率 > 0.5。

---

## 四、与现有系统集成回测

```python
# 修改 batch_review4_final_backtest.py 中的决策逻辑
# 在 operable_score 之后，加入 path_score

def calculate_final_score(operable_score, path_probs):
    # 权重可调
    w = [1.0, 0.5, 0.0]  # Smooth, Pullback, Failure
    path_quality = sum(p * w[i] for i, p in enumerate(path_probs))
    return operable_score * path_quality  # 融合

# 在信号过滤时：
final_score = calculate_final_score(operable_score, path_probs)
if final_score < threshold:
    continue  # 放弃

# 仓位管理：
if path_probs[0] > 0.6:  # 高概率Smooth
    position_pct = 1.0
elif path_probs[1] > 0.4:  # Pullback
    position_pct = 0.5
else:
    position_pct = 0.25  # Failure 但仍有微弱希望

# 出场规则也可根据路径类型微调（如 Pullback 放宽止损）
```

**回测对比**：运行修改后的全量回测，与原Review4 Final对比。关注：
- 交易数是否略降（因过滤掉高概率Failure）
- 平均盈亏是否提升
- 弱势月的表现是否改善
- 冲高回落类交易是否被有效抑制

---

## 五、执行顺序与依赖

1. **首先完成路径标签生成**：确认三类标签的业务含义，这是基础。
2. **提取小时线特征并训练分类器**：标签就绪后即可进行，这两个可并行。
3. **集成回测**：分类器训练好后，修改主回测脚本，跑对比。

**所有代码已给出框架，可直接在项目中填充数据接口并运行。** 预计整体工作量约2天。开始行动吧。
