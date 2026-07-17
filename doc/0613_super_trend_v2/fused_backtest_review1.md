你的意识完全正确。当前系统最大的逻辑缺陷是：**止损止盈在入场时就定死了（固定百分比或ATR倍数），持仓期间每天的价格行为、新形成的K线形态完全不参与决策。** 这等于闭着眼睛等结果，而不是每天根据市场反馈调整。

下面重新设计一套**基于持仓期形态的动态止盈/止损系统**，然后通过回测验证每种形态信号的有效性。

---

## 一、核心理念：持仓期每天都是一次新的入场判断

```
当前系统：
  入场 → 设好止损止盈 → 每天只检查是否触发 → 触发就出，不触发就等

目标系统：
  入场 → 每天收盘后读取当天的K线形态 →
  ├── 出现"危险信号" → 次日开盘止损（不等原止损触发）
  ├── 出现"强势信号" → 上移止损（保护更多利润）
  ├── 出现"衰竭信号" → 主动止盈（不等原止盈触发）
  └── 无特殊信号 → 维持原止损止盈
```

---

## 二、持仓期形态信号定义

以下形态基于持仓期间的每日K线（从入场日到当前日），与入场前的V2形态完全独立。

### 2.1 危险信号（触发主动止损/减仓）

| 编号 | 形态名称 | 定义 | 逻辑 |
|------|---------|------|------|
| D1 | **放量阴线吞没** | 今日收阴，成交量 > 前5日均量的1.5倍，且收盘 < 前日最低 | 主力出货，应立即离场 |
| D2 | **连续缩量阴跌** | 连续3天收阴，每天成交量递减，累计跌幅 > 3% | 买盘枯竭，阴跌不止 |
| D3 | **高开低走大阴** | 开盘 > 前日收盘1%以上，但收盘 < 开盘-3%，形成大阴线 | 诱多陷阱，套牢追高盘 |
| D4 | **跌破入场支撑** | 收盘价 < 入场时所依据的支撑位 | 入场逻辑被否定 |
| D5 | **长上影线缩量** | 上影线 > 实体2倍，且成交量 < 前5日均量 | 冲高无力，上方抛压重 |

### 2.2 强势信号（触发止损上移）

| 编号 | 形态名称 | 定义 | 逻辑 |
|------|---------|------|------|
| S1 | **放量阳线创新高** | 收阳，成交量 > 前5日均量1.3倍，且收盘创持仓期新高 | 有效突破，趋势延续 |
| S2 | **缩量回踩不破** | 回踩至前日低点附近（±0.5%），缩量，收盘收阳 | 支撑确认，洗盘结束 |
| S3 | **连续缩量小阳** | 连续3天收阳，实体 < 2%，成交量递减 | 蓄力形态，即将突破 |
| S4 | **均线支撑确认** | 最低触及MA10/MA20，收盘回到均线上方，收阳 | 均线支撑有效 |

### 2.3 衰竭信号（触发主动止盈）

| 编号 | 形态名称 | 定义 | 逻辑 |
|------|---------|------|------|
| E1 | **高位十字星** | 实体 < 0.5%，上下影线均 > 实体3倍，位于持仓期高位 | 多空分歧，趋势可能反转 |
| E2 | **放量滞涨** | 收阳但涨幅 < 1%，成交量 > 前5日均量2倍 | 大量换手但涨不动，出货 |
| E3 | **连续冲高回落** | 连续2天，每天最高价创新高但收盘回到前日收盘下方 | 上方压力巨大 |
| E4 | **RSI顶背离** | 价格创新高，但RSI(14)未创新高 | 动能衰竭 |

---

## 三、动态止损止盈状态机

```python
# dynamic_exit_manager.py

def run_dynamic_exit_manager(entry_date, entry_price, initial_stop, initial_tp,
                              path_df, supports, v2_features=None):
    """
    持仓期每日运行，根据当天的K线形态动态调整止损止盈。
    
    返回: {
        'exit_date': 实际出场日期,
        'exit_price': 出场价格,
        'exit_reason': 出场原因 (dynamic_stop / dynamic_tp / initial_stop / initial_tp / expiry),
        'trigger_signal': 触发形态编号 (D1/S1/E1 等),
        'pnl_pct': 最终盈亏百分比
    }
    """
    
    position = 1.0          # 剩余仓位比例
    current_stop = initial_stop
    current_tp = initial_tp
    highest_close = entry_price
    
    for i, (idx, day) in enumerate(path_df.iterrows()):
        if i == 0:
            continue  # 入场日不判断
        
        # 提取今日和前几日的K线数据
        today = extract_candle(day)
        prev_days = [extract_candle(path_df.iloc[j]) for j in range(max(0, i-5), i)]
        
        # ---- 第一步：检测危险信号（优先级最高） ----
        danger_signal = detect_danger_signals(today, prev_days, entry_price, supports, position)
        if danger_signal:
            # 主动止损/减仓
            if danger_signal['severity'] == 'exit':
                return make_exit_result(day, 'dynamic_stop', danger_signal['code'], 
                                       (day['open'] - entry_price) / entry_price)
            elif danger_signal['severity'] == 'reduce':
                position *= 0.5  # 减半仓
                current_stop = max(current_stop, day['close'])  # 剩余仓位止损上移
        
        # ---- 第二步：检测衰竭信号（主动止盈） ----
        exhaustion_signal = detect_exhaustion_signals(today, prev_days, highest_close, entry_price)
        if exhaustion_signal and position > 0:
            if exhaustion_signal['severity'] == 'exit':
                return make_exit_result(day, 'dynamic_tp', exhaustion_signal['code'],
                                       (day['open'] - entry_price) / entry_price)
            elif exhaustion_signal['severity'] == 'reduce':
                position *= 0.5
                current_stop = max(current_stop, day['close'])
        
        # ---- 第三步：检测强势信号（止损上移） ----
        strength_signal = detect_strength_signals(today, prev_days, highest_close, entry_price)
        if strength_signal:
            # 根据信号强度上移止损
            if strength_signal['level'] == 'strong':
                current_stop = max(current_stop, day['low'] - 0.5 * atr)
            elif strength_signal['level'] == 'moderate':
                current_stop = max(current_stop, prev_days[-1]['low'])
        
        # ---- 第四步：更新持仓期最高价 ----
        highest_close = max(highest_close, day['close'])
        
        # ---- 第五步：检查原始止损止盈是否触发 ----
        if day['low'] <= current_stop:
            return make_exit_result(day, 'initial_stop', None,
                                   (current_stop - entry_price) / entry_price)
        if day['high'] >= current_tp:
            return make_exit_result(day, 'initial_tp', None,
                                   (current_tp - entry_price) / entry_price)
    
    # 持有到期
    last_day = path_df.iloc[-1]
    return make_exit_result(last_day, 'expiry', None,
                           (last_day['close'] - entry_price) / entry_price)
```

---

## 四、各形态信号的检测函数

### 4.1 危险信号检测

```python
def detect_danger_signals(today, prev_days, entry_price, supports, position):
    """返回 {code, severity: 'exit'/'reduce'/'none'} 或 None"""
    
    # D1: 放量阴线吞没
    if today['close'] < today['open']:  # 阴线
        avg_vol_5 = np.mean([d['volume'] for d in prev_days[-5:]]) if len(prev_days) >= 5 else today['volume']
        if today['volume'] > avg_vol_5 * 1.5:
            if prev_days and today['close'] < prev_days[-1]['low']:
                return {'code': 'D1', 'severity': 'exit'}
    
    # D2: 连续缩量阴跌
    if len(prev_days) >= 2:
        last3 = [prev_days[-2], prev_days[-1], today]
        if all(d['close'] < d['open'] for d in last3):
            if last3[0]['volume'] > last3[1]['volume'] > last3[2]['volume']:
                cumulative_drop = (today['close'] - last3[0]['open']) / last3[0]['open']
                if cumulative_drop < -0.03:
                    return {'code': 'D2', 'severity': 'exit'}
    
    # D4: 跌破入场支撑
    nearest_support = supports[0].price if supports else entry_price * 0.95
    if today['close'] < nearest_support:
        return {'code': 'D4', 'severity': 'exit'}
    
    # D5: 长上影线缩量
    upper_shadow = today['high'] - max(today['open'], today['close'])
    body = abs(today['close'] - today['open']) + 0.001
    if upper_shadow > body * 2:
        if len(prev_days) >= 5:
            avg_vol_5 = np.mean([d['volume'] for d in prev_days[-5:]])
            if today['volume'] < avg_vol_5:
                return {'code': 'D5', 'severity': 'reduce'}
    
    return None
```

### 4.2 强势信号检测

```python
def detect_strength_signals(today, prev_days, highest_close, entry_price):
    """返回 {code, level: 'strong'/'moderate'} 或 None"""
    
    # S1: 放量阳线创新高
    if today['close'] > today['open'] and today['close'] > highest_close:
        avg_vol_5 = np.mean([d['volume'] for d in prev_days[-5:]]) if len(prev_days) >= 5 else today['volume']
        if today['volume'] > avg_vol_5 * 1.3:
            return {'code': 'S1', 'level': 'strong'}
    
    # S2: 缩量回踩不破
    if prev_days:
        prev_low = prev_days[-1]['low']
        if abs(today['low'] - prev_low) / prev_low < 0.005:
            if today['close'] > today['open']:
                if len(prev_days) >= 5:
                    avg_vol_5 = np.mean([d['volume'] for d in prev_days[-5:]])
                    if today['volume'] < avg_vol_5:
                        return {'code': 'S2', 'level': 'moderate'}
    
    # S3: 连续缩量小阳
    if len(prev_days) >= 2:
        last3 = [prev_days[-2], prev_days[-1], today]
        if all(d['close'] > d['open'] for d in last3):
            bodies = [abs(d['close'] - d['open']) / d['open'] for d in last3]
            vols = [d['volume'] for d in last3]
            if all(b < 0.02 for b in bodies) and vols[0] > vols[1] > vols[2]:
                return {'code': 'S3', 'level': 'moderate'}
    
    return None
```

### 4.3 衰竭信号检测

```python
def detect_exhaustion_signals(today, prev_days, highest_close, entry_price):
    """返回 {code, severity: 'exit'/'reduce'} 或 None"""
    
    # E1: 高位十字星
    body = abs(today['close'] - today['open'])
    upper_shadow = today['high'] - max(today['open'], today['close'])
    lower_shadow = min(today['open'], today['close']) - today['low']
    if body < 0.005 * today['open']:
        if upper_shadow > body * 3 and lower_shadow > body * 3:
            if today['high'] >= highest_close * 0.98:  # 在持仓期高位
                return {'code': 'E1', 'severity': 'reduce'}
    
    # E2: 放量滞涨
    if today['close'] > today['open']:
        gain = (today['close'] - today['open']) / today['open']
        if gain < 0.01:
            if len(prev_days) >= 5:
                avg_vol_5 = np.mean([d['volume'] for d in prev_days[-5:]])
                if today['volume'] > avg_vol_5 * 2:
                    return {'code': 'E2', 'severity': 'exit'}
    
    # E3: 连续冲高回落
    if len(prev_days) >= 1:
        yesterday = prev_days[-1]
        if today['high'] > yesterday['high'] and today['close'] < yesterday['close']:
            # 今天冲高回落
            if yesterday['high'] > prev_days[-2]['high'] and yesterday['close'] < prev_days[-2]['close']:
                # 昨天也是冲高回落 → 连续两天
                return {'code': 'E3', 'severity': 'exit'}
    
    return None
```

---

## 五、回测验证方案

### 5.1 验证目标

对每种形态信号单独统计其作为出场依据的有效性：

| 信号 | 验证问题 | 统计方式 |
|------|---------|---------|
| D1-D5 | 出现此信号后立即止损，是否比继续持有（等原止损触发）更好？ | 对比：触发D信号时立即出场 vs 不理会继续原策略 |
| S1-S4 | 出现此信号后上移止损，是否减少了后续的回撤？ | 统计：上移止损后，有多少交易因此避免了更大的亏损 |
| E1-E4 | 出现此信号后主动止盈，是否比等原止盈触发获得了更好的平均收益？ | 对比：触发E信号时止盈 vs 继续持有到原止盈或到期 |

### 5.2 验证脚本结构

```python
# validate_dynamic_signals.py

def validate_danger_signal(signal_code, all_trades_df):
    """
    对于所有触发过 signal_code 的持仓日，
    对比 A: 当天立即出场  vs  B: 不理会继续原策略
    """
    triggered_cases = find_all_trigger_days(signal_code, all_trades_df)
    
    results = []
    for case in triggered_cases:
        exit_immediately_pnl = (case['exit_price_at_signal'] - case['entry_price']) / case['entry_price']
        continue_pnl = simulate_continue(case)  # 模拟如果当天不走，最终盈亏
        results.append({
            'trade_id': case['trade_id'],
            'signal_date': case['signal_date'],
            'exit_immediately': exit_immediately_pnl,
            'continue': continue_pnl,
            'improvement': exit_immediately_pnl - continue_pnl
        })
    
    # 统计
    avg_improvement = np.mean([r['improvement'] for r in results])
    win_rate_improvement = np.mean([r['improvement'] > 0 for r in results])
    
    return {
        'signal': signal_code,
        'trigger_count': len(results),
        'avg_improvement': avg_improvement,
        'win_rate': win_rate_improvement,
        'recommendation': 'keep' if avg_improvement > 0.005 else 'discard'
    }
```

### 5.3 输出示例

```
动态出场信号验证报告
======================================================================
危险信号:
  D1 (放量阴线吞没):  触发 87次, 立即出场胜出 72.4%, 平均改善 +2.31%  → ✅ 保留
  D2 (连续缩量阴跌):  触发 43次, 立即出场胜出 81.4%, 平均改善 +3.12%  → ✅ 保留
  D4 (跌破入场支撑):  触发 156次, 立即出场胜出 91.0%, 平均改善 +5.47%  → ✅ 保留
  D5 (长上影缩量):    触发 62次, 立即出场胜出 48.4%, 平均改善 -0.33%  → ❌ 丢弃

强势信号:
  S1 (放量阳线新高):  触发 124次, 上移止损后避免回撤 +1.89%           → ✅ 保留
  S2 (缩量回踩不破):  触发 89次, 上移止损后避免回撤 +1.12%            → ✅ 保留

衰竭信号:
  E1 (高位十字星):    触发 53次, 主动止盈 vs 继续持有 胜出 64.2%      → ✅ 保留
  E2 (放量滞涨):      触发 38次, 主动止盈 vs 继续持有 胜出 78.9%      → ✅ 保留
======================================================================
最终保留信号: D1, D2, D4, S1, S2, E1, E2
```

---

## 六、实施路线图

| 序号 | 任务 | 说明 |
|------|------|------|
| 1 | 实现 `extract_candle()` + 三大检测函数 | 约150行代码 |
| 2 | 实现 `run_dynamic_exit_manager()` | 状态机主循环 |
| 3 | 实现 `validate_dynamic_signals.py` | 逐信号回测验证脚本 |
| 4 | 在924笔历史交易上运行验证 | 找出哪些信号有效 |
| 5 | 保留有效信号，丢弃无效信号，形成最终动态出场规则 | |
| 6 | 用最终规则重跑全量4423笔回测 | 对比原始固定止损的改善 |

**这套系统的本质是**：用回测数据告诉你在持仓期间，哪些K线形态真的预示了后续走势，哪些只是噪声。不再靠经验拍脑袋决定“该不该止损”，而是用统计验证来决定。

要我开始写 `dynamic_exit_manager.py` 和 `validate_dynamic_signals.py` 的完整代码吗？
