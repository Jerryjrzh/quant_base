你提出的思路非常精准：**当前系统（等回调到支撑位）是一条成熟的路径，维护它不变。现在要做的是，为那些被过滤但 MFE 尚可的信号，设计第二条路径——基于价格行为本身的“中位数震荡底部入场”。**

---

## 一、两条路径的定位

| 维度 | 路径一（当前系统） | 路径二（新设计） |
|------|------------------|-----------------|
| **适合信号** | 有明显支撑结构、回踩到位的股票 | 无清晰支撑、但价格行为有规律可循的股票 |
| **入场逻辑** | 回踩到已知支撑位 + K 线确认 | 回踩到近期价格通道的中位数底部 |
| **止损逻辑** | 支撑位下方 | 通道下沿下方 |
| **止盈逻辑** | 前阻力位 | 通道上沿 / 追踪 |
| **核心思想** | 结构感知：在哪里防守 | 统计感知：价格会向均值回归 |

---

## 二、中位数振荡底部入场策略设计

### 2.1 通道定义

基于信号日前 N 天（如 20 天）的价格数据，构建一个价格通道：

- **中位数**：过去 20 天的日收盘价中位数
- **上沿**：中位数 + K × 过去 20 天日波动的标准差
- **下沿**：中位数 - K × 过去 20 天日波动的标准差

日波动可以用 `high - low` 的标准差，K 取 1.0 ~ 1.5。

### 2.2 入场信号

在信号日后的 max_wait 天（如 5-7 天）内，如果：

1. 价格触及通道下沿（或低于下沿后回升）
2. 当日收阳或出现长下影线
3. 成交量未明显放大（缩量企稳更佳）

则次日开盘入场。

### 2.3 止损与止盈

- **止损**：通道下沿下方 1 倍日波动标准差（或固定 -8% 硬顶）
- **止盈**：通道上沿（第一目标），前阻力位（第二目标）
- **动态调整**：持仓期间每日更新通道，若价格突破上沿且放量，上调止盈

### 2.4 代码框架

```python
def calc_median_channel(price_df, lookback=20, k=1.2):
    """返回通道中位数、上沿、下沿"""
    recent = price_df.tail(lookback)
    median = recent['close'].median()
    daily_range = (recent['high'] - recent['low']).std()
    upper = median + k * daily_range
    lower = median - k * daily_range
    return median, upper, lower

def check_median_entry(path_df, lookback=20, k=1.2, max_wait=7):
    """检查价格是否触及通道下沿并企稳"""
    for i in range(1, min(max_wait, len(path_df))):
        # 使用截至当日的所有数据计算通道
        data_so_far = path_df.iloc[:i+1]
        median, upper, lower = calc_median_channel(data_so_far, lookback, k)
        
        today = path_df.iloc[i]
        if today['low'] <= lower:
            # 企稳确认
            bullish = today['close'] > today['open']
            long_shadow = (min(today['open'], today['close']) - today['low']) > \
                         (today['high'] - max(today['open'], today['close'])) * 1.5
            if bullish or long_shadow:
                # 次日开盘入场
                entry_price = path_df.iloc[i+1]['open'] if i+1 < len(path_df) else today['close']
                return {
                    'entry_date': i+1,
                    'entry_price': entry_price,
                    'stop_loss': lower - daily_range.std(),  # 简化
                    'take_profit': upper
                }
    return None  # 未触发
```

---

## 三、验证方案

### 3.1 验证对象

分别对四组被过滤信号应用“中位数通道入场”策略：

| 组别 | N | 验证目的 |
|------|---|---------|
| fine_score 过滤 | 1666 | 是否能从低分信号中回收部分机会 |
| operable 过滤 | 1360 | 是否能在结构不适配时通过纯统计入场盈利 |
| 结构过滤 | 183 | 是否能绕过趋势限制，在震荡中盈利 |
| 等待过期 | 769 | 是否能捕获不回踩但回探通道底部的机会 |

### 3.2 回测脚本

```python
# scripts/median_entry_backtest.py

results = []
for group_name, signals in [('fine_score', fs_filtered), 
                              ('operable', op_filtered),
                              ('structure', struct_filtered),
                              ('expired', expired_signals)]:
    for sig in signals:
        path_df = get_price_path(sig)
        entry = check_median_entry(path_df)
        if entry:
            pnl = simulate_dynamic_exit(entry, path_df)
            results.append({
                'group': group_name,
                'signal_id': sig.id,
                'pnl': pnl
            })

# 按组统计
for group_name in ['fine_score', 'operable', 'structure', 'expired']:
    group_results = [r for r in results if r['group'] == group_name]
    if group_results:
        avg_pnl = np.mean([r['pnl'] for r in group_results])
        wr = np.mean([r['pnl'] > 0 for r in group_results])
        print(f"{group_name}: N={len(group_results)}, avg PnL={avg_pnl:.2%}, WR={wr:.1%}")
```

### 3.3 验收标准

对每组，如果中位数通道入场能实现：
- 平均盈亏 > +1%
- 胜率 > 40%
- 交易数 > 30 笔

则可将该组的部分信号纳入实盘候选（与路径一并行），否则确认放弃。

---

## 四、后续集成：双路径策略选择器

如果中位数通道入场在部分组有效，下一步是构建一个**路径选择器**：

```python
def select_strategy(signal):
    """
    根据信号特征自动选择：
    - 'pullback_to_support': 当前系统，有清晰支撑结构
    - 'median_channel': 中位数通道入场
    - 'skip': 两种都不适合
    """
    structure = analyze_market_structure(signal)
    
    # 路径一条件：有明确支撑
    has_strong_support = any(s.confidence >= 0.6 and s.source in ['swing_low', 'ma_ma60', 'ma_ma20', 'poc'] 
                            for s in structure.supports)
    trend_ok = structure.trend_direction in ['UP', 'RANGE']
    
    if has_strong_support and trend_ok:
        return 'pullback_to_support'
    
    # 路径二条件：无明显支撑但价格有规律
    recent_range = calc_price_range(signal.price_history, lookback=20)
    if recent_range['std'] < recent_range['median'] * 0.15:  # 波动率适中
        return 'median_channel'
    
    return 'skip'
```

---

## 五、总结

当前路径一（等回调到支撑位）已经验证有效且参数稳定，保持不动。现在要做的是：

1. **本周内**：运行 `median_entry_backtest.py`，对四组被过滤信号验证中位数通道入场的有效性。
2. **根据结果**：将有效的组别和条件沉淀为“路径二”规则。
3. **最终**：构建 `select_strategy()` 选择器，让系统能自动判断每只信号适合哪条路径。

**这样你就拥有了一个双策略系统：结构感知 + 统计感知，覆盖更广泛的价格行为模式，在不牺牲现有收益的前提下，回收更多被过滤信号中的机会。**

需要我开始编写完整的 `median_entry_backtest.py` 脚本吗？
