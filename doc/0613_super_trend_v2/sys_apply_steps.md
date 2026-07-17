这套伪代码将你现有系统缺失的“市场结构感知”层完整补上，形成一个完整的**信号触发 → 结构过滤 → 等待入场 → 基于结构的出场和仓位管理**闭环。所有逻辑都可以在历史数据上离线回测验证。

---

## 一、Swing High/Low 检测（用于确定支撑/阻力）

**目标**：从T0前60天的日线数据中，找出重要拐点（至少被测试2次且未被有效突破）。

```python
# 输入: high_series, low_series (T0前60天的最高价和最低价序列)
# 参数: lookback=5 (左/右各看5天确认局部极值), min_tests=2 (至少被测试的次数)

def detect_swing_points(high, low, lookback=5, min_tests=2):
    swing_highs = []  # (日期, 价格, 测试次数)
    swing_lows = []

    # 1. 找局部极值点（使用滚动窗口）
    for i in range(lookback, len(high)-lookback):
        # 局部高点：比左右各 lookback 天的高点都高
        if high[i] == max(high[i-lookback:i+lookback+1]):
            # 测试：这个价格在之后是否被接近(±1%)且未有效突破(收盘站上)
            tests = count_tests(high, low, close, i, high[i], 'high')
            if tests >= min_tests:
                swing_highs.append((i, high[i], tests))

        # 局部低点同理
        if low[i] == min(low[i-lookback:i+lookback+1]):
            tests = count_tests(high, low, close, i, low[i], 'low')
            if tests >= min_tests:
                swing_lows.append((i, low[i], tests))

    return swing_highs, swing_lows

def count_tests(high, low, close, peak_idx, peak_price, type):
    """统计一个极值点被后续价格测试的次数（触及±1%视为测试）"""
    tests = 0
    for j in range(peak_idx+lookback, len(close)):
        if type == 'high':
            if high[j] >= peak_price * 0.99:  # 触及
                tests += 1
                # 如果收盘价突破该高点1%以上，则不再视为有效阻力
                if close[j] > peak_price * 1.01:
                    break
        else:  # low
            if low[j] <= peak_price * 1.01:
                tests += 1
                if close[j] < peak_price * 0.99:
                    break
    return tests
```

---

## 二、关键支撑/阻力位计算（结构过滤器核心）

```python
def get_key_levels(swing_highs, swing_lows, ma20, ma60, volume_profile_poc, current_price):
    """
    输出当前价格上方和下方的关键水平。
    支撑位：下方最近的 swing_low, ma20, ma60, volume POC
    阻力位：上方最近的 swing_high, 前高
    """
    supports = []
    resistances = []

    # 从 swing_lows 中取价格 < current_price 的，按距离排序
    supports += [price for (_, price, _) in swing_lows if price < current_price]
    # 加入均线支撑（如果当前价格在均线上方）
    if ma20 < current_price: supports.append(ma20)
    if ma60 < current_price: supports.append(ma60)
    if volume_profile_poc < current_price: supports.append(volume_profile_poc)

    # 同理阻力位
    resistances += [price for (_, price, _) in swing_highs if price > current_price]
    if ma20 > current_price: resistances.append(ma20)
    if ma60 > current_price: resistances.append(ma60)
    if volume_profile_poc > current_price: resistances.append(volume_profile_poc)

    # 按距离排序，取最近N个
    supports.sort(reverse=True)   # 从近到远
    resistances.sort()
    return supports, resistances
```

---

## 三、结构过滤器：决定信号是否有效

**逻辑**：如果当前价格处于明确的下降趋势（低点更低、高点更低），或者紧上方有极近的重阻力且无支撑空间，则过滤掉这个信号。

```python
def structure_filter(current_price, supports, resistances, trend_direction):
    """
    trend_direction: 'UP' / 'DOWN' / 'RANGE'
    """
    # 下降趋势中不做多
    if trend_direction == 'DOWN':
        return False

    # 如果最近阻力位在2%以内，且最近支撑位在5%以外，盈亏比差，过滤
    nearest_resistance = resistances[0] if resistances else None
    nearest_support = supports[0] if supports else None

    if nearest_resistance and nearest_support:
        if (nearest_resistance / current_price - 1) < 0.02 and \
           (current_price / nearest_support - 1) > 0.05:
            return False  # 上方空间不足

    return True
```

---

## 四、入场逻辑：回调到支撑位买入

**核心理念**：信号触发后，等待价格回调到关键支撑位，出现企稳K线时入场。

```python
# 状态机: WAITING -> ENTERED -> MANAGING -> CLOSED
state = 'WAITING'
entry_price = None
stop_loss = None
take_profit_levels = []  # 分批止盈目标
position_size = 0

def check_entry_on_day(day_data, supports, current_state):
    """
    每天检查是否触发入场条件。
    day_data: {'open', 'high', 'low', 'close', 'ma20', 'volume'}
    """
    if current_state != 'WAITING':
        return None

    # 检查是否回踩到支撑位（触及最近支撑位的±1%范围）
    nearest_support = supports[0]  # 最近的支撑
    if day_data['low'] <= nearest_support * 1.01:  # 触及支撑区
        # 企稳确认：当日收阳线且收盘价在支撑上方，或出现长下影线
        bullish_engulf = (day_data['close'] > day_data['open'] and 
                         day_data['close'] > nearest_support)
        long_lower_shadow = (min(day_data['open'], day_data['close']) - day_data['low']) > \
                            (day_data['high'] - max(day_data['open'], day_data['close'])) * 2
        
        if bullish_engulf or long_lower_shadow:
            # 入场：以次日开盘价买入（避免未来数据）
            return 'ENTRY_SIGNAL', day_data['date']  # 实际回测在次日开盘执行
    return None
```

**突破确认入场（备选）**：

```python
def check_breakout_entry(day_data, resistances, current_state):
    """如果价格向上突破最近阻力，且回踩确认，则入场"""
    nearest_resistance = resistances[0]
    # 今日最高价突破阻力位
    if day_data['high'] > nearest_resistance:
        # 等待回踩：次日低点回到阻力位附近（±1%），且收盘在阻力位上方
        # 回测中需要看下一日数据，此处略
        return 'BREAKOUT_ENTRY_SIGNAL'
    return None
```

---

## 五、止损逻辑：基于结构而非固定百分比

```python
def set_initial_stop(entry_price, supports, atr_20):
    """
    止损设在入场时依据的那个支撑位下方一定距离。
    如果入场依据是MA20，止损就在MA20 - 1.5*ATR。
    如果是swing_low，止损就在swing_low - 0.5*ATR。
    """
    # 找到入场时最靠近的那个支撑位（即触发入场的支撑）
    triggered_support = supports[0]  # 简化，实际需记录具体是哪个支撑

    # 止损缓冲：0.5~1.5倍ATR，防止被噪声触发
    stop_buffer = 1.0 * atr_20
    stop_price = min(triggered_support - stop_buffer, entry_price * 0.95)  # 硬性最大亏损5%保护
    return stop_price
```

**动态移动止损**：持仓期间，如果价格形成了新的 swing_low（更高的低点），可以将止损提升到该低点下方。

```python
def update_trailing_stop(current_low, swing_lows, atr, current_stop):
    """在上升趋势中，将止损上移到最近的swing_low下方"""
    new_swing_lows = [price for (_, price, _) in swing_lows if price > current_stop]
    if new_swing_lows:
        new_stop = max(new_swing_lows) - 0.5 * atr
        return max(current_stop, new_stop)  # 只上移不下移
    return current_stop
```

---

## 六、止盈逻辑：分批在阻力位了结

```python
def set_take_profit_levels(entry_price, resistances):
    """
    第一目标：最近的前期摆动高点（或阻力位）—— 减仓50%
    第二目标：下一个阻力位 —— 减仓剩余仓位（或使用追踪止盈）
    """
    # 取最近的两个阻力位
    tp1 = resistances[0] if resistances else entry_price * 1.15  # 默认15%
    tp2 = resistances[1] if len(resistances) > 1 else entry_price * 1.25
    return [tp1, tp2]

def check_partial_profit(day_high, current_position, tp_levels, current_state):
    """达到第一目标止盈一半，剩余仓位止损上移到成本价"""
    if current_position > 0 and tp_levels:
        if day_high >= tp_levels[0]:
            # 执行半仓止盈
            sell_half()
            # 剩余仓位的止损移到成本价
            current_stop = max(current_stop, entry_price)
            # 剩余仓位跟踪第二个目标或追踪止损
```

---

## 七、仓位管理：基于风险的动态仓位

```python
def calculate_position_size(capital, entry_price, stop_price, max_risk_per_trade=0.005):
    """
    每笔交易允许亏损总资金的 max_risk_per_trade (0.5%)
    仓位大小 = (资本 * 风险比例) / (每股风险金额)
    """
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share == 0: return 0
    position_size = (capital * max_risk_per_trade) / risk_per_share
    # 考虑A股100股整数限制
    return int(position_size / 100) * 100
```

---

## 八、持仓管理状态机（完整流程）

```python
state = 'WAITING'      # 等待入场
entry_date = None
entry_price = None
current_stop = None
tp_levels = []
position = 0
remaining_position = 0
trailing_activated = False

for each day in signal_day to signal_day + 22:
    if state == 'WAITING':
        # 检查是否到期（5天无回调则放弃）
        if day_index > signal_day + 5:
            state = 'EXPIRED'
            break
        # 检查入场条件（回调买入或突破买入）
        entry_signal = check_entry_on_day(day_data, supports)
        if entry_signal:
            # 次日开盘执行
            state = 'ENTERED'
            entry_date = day_index + 1
            entry_price = next_day_open
            # 计算止损、止盈、仓位
            current_stop = set_initial_stop(entry_price, supports, atr)
            tp_levels = set_take_profit_levels(entry_price, resistances)
            position = calculate_position_size(capital, entry_price, current_stop, 0.005)
            remaining_position = position

    elif state == 'ENTERED' or state == 'MANAGING':
        # 每日检查止损/止盈
        # 止损检查：最低价触及止损价
        if day_low <= current_stop:
            exit_price = current_stop  # 或实际触发价
            record_trade(exit_price, 'stop_loss')
            state = 'CLOSED'
            break
        # 第一部分止盈检查
        if tp_levels and day_high >= tp_levels[0]:
            # 止盈一半
            sell_qty = remaining_position // 2
            record_trade(tp_levels[0], 'take_profit_1', qty=sell_qty)
            remaining_position -= sell_qty
            # 剩余仓位止损提到成本价
            current_stop = max(current_stop, entry_price)
            tp_levels.pop(0)  # 移除第一个目标，跟踪第二个目标
        # 第二部分止盈/追踪
        if remaining_position > 0 and day_high >= tp_levels[0]:
            # 全部止盈
            record_trade(tp_levels[0], 'take_profit_2', qty=remaining_position)
            remaining_position = 0
            state = 'CLOSED'
            break
        # 动态移动止损（上移）
        current_stop = update_trailing_stop(...)

    # 持有到期
    if day_index == signal_day + 22:
        exit_price = day_close
        record_trade(exit_price, 'expiry')
        state = 'CLOSED'
```

---

## 九、离线验证方案和数据回测用例

### 验证案例（取自你们的真实失败交易）

**股票X（代号 sz002958）**：
- T0日期：假设为2025-03-10
- T+1开盘价：100元
- 关键支撑位（由T0前60天数据计算）：
  - Swing Low: 95元（被测试3次）
  - MA20: 97元
  - MA60: 92元
- 阻力位：Swing High 115元

**原始策略**：T+1以100元买入，止损 -8%（92元），最终第22天收盘92元，亏损 -8%。

**新策略模拟**：
- 信号触发后，状态WAITING。
- T+2 最低价触及97.5元（回踩MA20），当日收阳线，确认企稳。
- T+3 以开盘价98元买入（假设开盘于98）。
- 止损设在MA20下方1.5倍ATR（ATR=3，止损=97-4.5=92.5，取92.5）。
- 第一止盈115元（前高），第二止盈125元。
- 仓位：可承受总资金0.5%亏损，每股风险5.5元，假设资本100万，买900股。
- 后续走势：第7天最高到116元，触发第一止盈115元，卖出450股，盈利17.3%；剩余仓位止损提至成本价98。第15天最高125元触发第二止盈，全出，盈利27.5%。

**对比**：原策略亏8%，新策略加权盈利22%（综合两个止盈）。

### 离线批量回测用例设计

1. **提取历史交易路径数据**：从 `pure_mfe_analysis.csv` 中取出每一笔信号的T0日期、T+1至T+22每天的OHLC、MA20/MA60、ATR20，以及提前计算好的摆动高低点列表（可离线计算并存表）。

2. **回测引擎**：
   - 逐笔循环，应用上述状态机。
   - 输出每笔交易的入场日期、入场价、止损价、止盈价、实际出场价、持仓天数、盈亏、出场原因。
   - 统计指标：平均收益、胜率、盈亏比、最大连续亏损、收益曲线。

3. **对比基准**：
   - 基准1：原策略（T+1开盘买入，-8%止损，+30%止盈，持有22天）。
   - 基准2：原策略但无止损/止盈（纯持有22天收盘）。

4. **验收标准**：
   - 新策略的平均收益需 > 原策略 + 2%
   - 新策略的胜率需 > 原策略 + 5个百分点
   - 新策略的最大回撤（账户净值回撤）不得高于原策略的80%
   - 结构过滤器应滤除至少20%的原始信号，而这些被滤除信号的平均收益应为负（证明过滤器有效）

### 伪代码：离线验证主循环

```python
for each trade in dataset:
    signal_date = trade['t0_date']
    # 获取T0前60天数据计算摆动点、MA、VOL POC
    pre_data = get_pre_60_days(signal_date, stock_code)
    swings_high, swings_low = detect_swing_points(pre_data['high'], pre_data['low'])
    ma20 = pre_data['close'].rolling(20).mean().iloc[-1]
    atr = compute_atr(pre_data)
    supports, resistances = get_key_levels(swings_high, swings_low, ma20, ma60, poc, current_price)

    # 结构过滤器
    if not structure_filter(pre_data['close'].iloc[-1], supports, resistances, trend):
        filtered_out += 1
        continue

    # 运行状态机，模拟入场和出场
    result = run_state_machine(trade, supports, resistances, atr)
    add_to_results(result)

# 输出统计
print("过滤掉的信号数:", filtered_out)
print("新策略平均收益:", np.mean(results['pnl']))
print("胜率:", np.mean(results['pnl'] > 0))
```

---

## 十、实施路线图

1. **第1步**：实现 `detect_swing_points` 和 `get_key_levels`，在历史数据上生成每个信号日的支撑阻力列表，验证其合理性（人工抽查10个案例）。
2. **第2步**：实现入场逻辑，回测“回调到支撑位买入”相较于T+1无脑买入的改善，确认胜率提升。
3. **第3步**：实现基于结构的止损和分批止盈，完整回测，对比基准。
4. **第4步**：加入仓位管理模块，观察对收益曲线平滑度的影响。

这套体系一旦确立，你的动能策略将不再是“跳上正在冲刺的马车”，而是“等马儿在驿站歇脚时从容上马”，从底层逻辑上解决冲高回落导致的亏损问题。需要我把任何一步转为具体的Python实现吗？
