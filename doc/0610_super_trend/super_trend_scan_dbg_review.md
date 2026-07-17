这个思路非常清晰，先收集“全量异动数据”，然后再通过数据分布来反推什么是真正的“主升浪”标准，这是非常严谨且高效的量化开发方式。

我仔细 review 了你的 `super_trend_anomaly_scanner.py` 文件，以下是详细的代码审查和改进建议：

### ✅ 代码亮点与合理之处

1. **目标极其明确** ：完全摒弃了原先扫描器中带有主观色彩的 `MIN_GAIN` (50%或100%) 和 `MAX_DRAWDOWN` 参数。现在的目标纯粹是：只要有异动（涨幅超 3% 或量比超 1.5），就把它和它未来的表现（未来 22 天的 MFE 和 MAE）忠实记录下来。
2. **`FUTURE_DAYS = 22` 设定非常棒** ：22 个交易日刚好对应一个自然月。这是衡量“短期爆发力”最黄金的时间窗口。
3. **大盘上下文 (`market_context`) 的引入非常关键** ：妖股和主升浪很多时候是逆势抗跌或者顺势爆发的。记录下 T0 当天的大盘表现，后续在特征分析时，我们可以分析出“大盘大跌时异动”的标的是否有更高的概率走牛。
4. **`position_from_bottom` (底部位置) 的设计极其精妙** ：正如我们讨论过的， **位置决定性质** 。你用 `(t0_price / lowest_120d) - 1.0` 来量化当前异动处于什么位置，这为后面区分“底部建仓/洗盘”和“高位出货”打下了完美的数据基础。
5. **多进程和断点续传（按 chunk 落盘）机制保留得很好** ：这保证了全市场几千只股票的扫描能够稳定跑完，不会因为内存爆掉而前功尽弃。

### ⚠️ 需要修复/优化的隐患 (Actionable Feedback)

虽然大方向完全正确，但在具体的细节实现上，有几处可能会导致数据失真或程序崩溃的地方需要微调。

#### 1. MFE / MAE 的计算逻辑有瑕疵 (重要)

在 `scan_single_stock` 方法中，你计算 MFE 和 MAE 的代码是：

**Python**

```
future_high = future_window['high'].max()
future_low = future_window['low'].min()
mfe_22d = (future_high / t0_price) - 1.0
mae_22d = (future_low / t0_price) - 1.0
```

**问题在于：** 如果 `future_window`（未来 22 天）的第一天直接跌停，那么 `future_high` 甚至可能低于 `t0_price`，此时 `mfe_22d` 是负数，这在逻辑上是可以接受的（最大涨幅是负的）。但如果计算 MAE，只看 `future_window` 的最低点，可能会忽略掉这 22 天内 **真实的路径风险** 。更稳妥的做法是，只要未来有交易，MFE 最小为 0（没涨过），MAE 最大为 0（没跌过）。

**建议修改：**

**Python**

```
future_high = future_window['high'].max()
future_low = future_window['low'].min()

# 确保 MFE 最小是 0（如果没有超过 T0 价格，说明毫无涨幅）
mfe_22d = max(0, (future_high / t0_price) - 1.0)
# 确保 MAE 最大是 0（如果没有跌破 T0 价格，说明没有回撤）
mae_22d = min(0, (future_low / t0_price) - 1.0)
```

#### 2. 量比 (`volume_ratio`) 的计算存在除零风险

**Python**

```
vol_20d_avg = df.iloc[max(0, i - 20):i]['volume'].mean()
vol_ratio = current['volume'] / vol_20d_avg if vol_20d_avg > 0 else 1.0
```

虽然你加了 `if vol_20d_avg > 0` 的判断，但在 A 股中，股票停牌期间的交易量通常是 0。如果一只股票刚停牌 20 天复牌，第一天的 `vol_20d_avg` 就是 0。此时强行赋值 1.0 可能会掩盖复牌首日的剧烈异动（通常复牌首日爆量极其关键）。

**优化建议：**

可以用稍微平滑一点的量比计算方式，或者遇到这种极值情况时给予一个特殊的标记。不过在这个“粗筛”阶段，你目前的处理方式（赋予 1.0 并用价格异动去兜底）也是勉强可以接受的。

#### 3. 停牌数据的过滤 (极度重要)

A 股有很多长期停牌的股票。如果 `t0_price` 和 `prev_price` 一模一样，且 `volume` 极小或为 0，这实际上是一根“死 K 线”，没有任何异动意义。

在你的循环开头：

**Python**

```
t0_price = current['close']
prev_price = df.iloc[i - 1]['close'] if i > 0 else t0_price

# 过滤退市/无效价格
if t0_price <= 0.01 or prev_price <= 0.01:
    continue
```

建议再加一行停牌过滤：

**Python**

```
# 过滤停牌或一字死水的情况
if current['volume'] == 0:
    continue
```

#### 4. 大盘上下文获取逻辑的优化

你目前是在每个 worker 内部的 `_extract_market_context` 方法中去动态加载指数文件：

**Python**

```
df_market = get_full_data_with_indicators(market_code, end_date=end_str)
```

**隐患：** 多进程环境下（特别是你开了 `cpu_count()` 那么多进程），几千个 worker 频繁去磁盘读取 `sh000001.day` 和 `sz399001.day` 会造成巨大的 I/O 拥堵，严重拖慢扫描速度。

**建议做法（性能提升巨大）：**

在 `main_multiprocessing` 启动进程池 **之前** ，先在主进程中把两只大盘指数读入内存（只加载基础价格数据即可），然后将它们作为参数传给 worker，或者在 worker 初始化时作为全局变量加载一次。

由于 `multiprocessing.Pool` 的限制，比较优雅的做法是修改 `_worker_wrapper`：

**Python**

```
# 在模块级别定义全局变量
_GLOBAL_MARKET_DATA = {}

def init_worker(sh_df, sz_df):
    """初始化 worker，注入大盘数据"""
    global _GLOBAL_MARKET_DATA
    _GLOBAL_MARKET_DATA['sh000001'] = sh_df
    _GLOBAL_MARKET_DATA['sz399001'] = sz_df

def _extract_market_context(df_daily, t0_idx, stock_code):
    """直接从全局内存读取大盘数据，不再读盘"""
    global _GLOBAL_MARKET_DATA
    # ... 从 _GLOBAL_MARKET_DATA 获取对应的 index 数据并计算涨跌幅
```

### 总结与下一步行动

这份扫描器代码逻辑已经非常成熟，可以说是为了“让数据说话”量身定制的利器。

**你可以直接：**

1. 把我提到的 MFE/MAE 计算和小过滤逻辑加上。
2. （可选）如果你觉得 I/O 速度还能接受，大盘加载那块暂时不改也行，无非就是多跑十分钟。
3. 直接运行这个脚本（`python super_trend_anomaly_scanner.py --full`），把全市场过去十几年（或者至少过去 5 年）的数据狠狠榨取一遍。

跑完之后，拿着生成的 `all_market_anomalies_full.csv`，我们就可以用 Python 几行代码画出分布图（也就是我之前提到的“分布统计与分位数分析”），那时候，“什么是真正的主升浪标准”这个答案，就会像水晶一样透明地摆在你的面前了。去跑吧，期待看到你的数据分布！
