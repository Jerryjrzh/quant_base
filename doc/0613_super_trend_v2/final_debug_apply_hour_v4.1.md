完全同意ChatGPT的判断。回顾整个过程，我们一直在调整“怎么卖”，但v4.0的数据已经明确告诉我们：**80%的信号都会经历>15%的深回撤。** 这不是出场策略能解决的问题——再怎么优化止盈止损，也无法把一辆过山车变成平稳的高铁。唯一的办法是，在上车前就知道哪辆车更平稳。

以下是基于这个新认知的具体任务和实现逻辑。

---

## 一、任务规划

| 序号 | 任务 | 目标 | 优先级 |
|------|------|------|--------|
| **Task 1** | 构建路径质量标签 | 用 `future_MFE / future_DD` 替代原有MFE作为训练标签 | P0 |
| **Task 2** | 小时线路径预测器 | 利用T0前的60分钟K线特征，预测该信号未来是“平稳型”还是“过山车型” | P0 |
| **Task 3** | 路径质量分层回测 | 验证仅保留高Path Quality信号后，系统整体盈亏的提升幅度 | P0 |

---

## 二、Task 1 伪代码：构建路径质量标签

**目标**：对4423笔信号，重新计算一个更合理的标签，同时衡量“涨得多不多”和“过程顺不顺”。

```python
# 对每笔信号的未来22天日线数据
future_df = get_future_22d_daily(signal_id)

# 计算未来最大回撤（从峰值到谷底）
peak = future_df['high'].cummax()
drawdown = (peak - future_df['high']) / peak
max_dd = drawdown.max()

# 计算未来最高涨幅
mfe = (future_df['high'].max() / future_df['open'].iloc[0]) - 1

# 计算路径质量
path_quality = (1 + mfe) / (1 + max_dd) - 1  
# 例：MFE=25%, DD=5% → path_quality ≈ 19%
# 例：MFE=25%, DD=25% → path_quality ≈ 0%

# 保存为新的标签列
signals_df['path_quality'] = path_quality
```

**产出**：一个0到1之间的连续值，越高代表“涨得多且回撤小”。

---

## 三、Task 2 伪代码：小时线路径预测器

**目标**：仅用T0之前的信息，预测该信号未来会走哪条路。不是预测涨跌，而是预测路径的颠簸程度。

```python
def extract_hourly_features_for_path(stock_code, t0_date):
    """
    提取T0日前20天的60分钟K线特征，专门用于预测路径颠簸程度。
    """
    df = get_hourly_data(stock_code, end_date=t0_date, periods=-400)
    
    features = {}
    
    # 1. 微观波动率：最近80小时的收益率标准差
    features['hourly_volatility'] = df['close'].pct_change().tail(80).std()
    
    # 2. 趋势稳定性：最近20小时的线性拟合R²
    x = np.arange(20)
    y = df['close'].tail(20).values
    _, _, r_value, _, _ = linregress(x, y)
    features['trend_stability'] = r_value ** 2
    
    # 3. 盘中回调深度：最近5天内，每小时的最大跌幅均值
    df['hourly_return'] = df['close'].pct_change()
    features['avg_intraday_dd'] = df['hourly_return'].rolling(4).min().tail(80).mean()
    
    # 4. 量价配合度：上涨小时量 / 下跌小时量
    up_vol = df[df['close'] > df['open']]['volume'].sum()
    down_vol = df[df['close'] < df['open']]['volume'].sum()
    features['vol_ratio'] = up_vol / (down_vol + 1)
    
    # 5. 结构紧凑度：最近高点与低点的比值
    recent_high = df['high'].tail(80).max()
    recent_low = df['low'].tail(80).min()
    features['price_compactness'] = (recent_high / recent_low - 1)
    
    return features

# 对全量信号提取特征
all_features = [extract_hourly_features_for_path(row.stock, row.t0) for row in signals]

# 训练一个回归模型，预测 path_quality（连续值）
model = LightGBMRegressor(objective='regression', metric='rmse')
model.fit(X_train, y_train['path_quality'])
```

**产出**：一个回归模型，输入T0前的60分钟特征，输出预测的 `predicted_path_quality`。

---

## 三、Task 3 伪代码：路径质量分层回测

**目标**：验证保留高Path Quality信号后，系统表现如何。

```python
# 为测试集信号生成预测
test_signals['predicted_path_quality'] = model.predict(X_test)

# 按预测质量分为三组
test_signals['quality_tier'] = pd.qcut(test_signals['predicted_path_quality'], 
                                        q=[0, 0.3, 0.7, 1.0], 
                                        labels=['Low', 'Mid', 'High'])

# 对每组，应用当前最优日线系统（Review4 Final）进行回测
for tier in ['Low', 'Mid', 'High']:
    tier_signals = test_signals[test_signals['quality_tier'] == tier]
    results = run_backtest(tier_signals, config='review4_final')
    print(f"Tier {tier}: avg PnL={results.avg_pnl}, PF={results.profit_factor}")

# 最终决策：只保留 High + Mid 组
final_signals = test_signals[test_signals['quality_tier'].isin(['High', 'Mid'])]
final_results = run_backtest(final_signals, config='review4_final')
```

**验收标准**：
- High组的平均盈亏 > 全量信号均值的 1.5 倍。
- Low组的平均盈亏 < 0（或显著低于全量均值），证明过滤有效。
- 最终策略（仅High+Mid）的整体盈亏 > 6%，盈利因子 > 3.0。
