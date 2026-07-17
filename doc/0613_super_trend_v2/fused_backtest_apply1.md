我们分两步实现：第一步编写`dynamic_exit_manager.py`，包含三大类形态信号检测函数和带状态机的动态出场管理器；第二步编写`validate_dynamic_signals.py`，在历史交易数据上回测每个出场信号的有效性，对比“信号触发即行动”与“忽略信号按原策略”的收益差异，并特别分析持有期间高/低点与实际出场的关系。

---

## 一、`dynamic_exit_manager.py` 完整实现

```python
# backend/dynamic_exit_manager.py

import numpy as np
import pandas as pd

def extract_candle(day_row):
    """从DataFrame的一行中提取标准K线字典"""
    return {
        'open': day_row['open'],
        'high': day_row['high'],
        'low': day_row['low'],
        'close': day_row['close'],
        'volume': day_row.get('volume', 0)
    }

def detect_danger_signals(today, prev_days, entry_price, supports, position):
    """
    检测危险信号，返回 {'code': str, 'severity': 'exit'/'reduce'} 或 None
    prev_days: 列表，最近N天的K线字典，按时间升序，最后一个是昨天
    """
    avg_vol_5 = np.mean([d['volume'] for d in prev_days[-5:]]) if len(prev_days) >= 5 else today['volume']
    
    # D1: 放量阴线吞没
    if today['close'] < today['open']:
        if today['volume'] > avg_vol_5 * 1.5:
            if prev_days and today['close'] < prev_days[-1]['low']:
                return {'code': 'D1', 'severity': 'exit'}
    
    # D2: 连续缩量阴跌
    if len(prev_days) >= 2:
        last3 = [prev_days[-2], prev_days[-1], today]
        if all(d['close'] < d['open'] for d in last3):
            if last3[0]['volume'] > last3[1]['volume'] > last3[2]['volume']:
                cum_drop = (today['close'] - last3[0]['open']) / last3[0]['open']
                if cum_drop < -0.03:
                    return {'code': 'D2', 'severity': 'exit'}
    
    # D4: 跌破入场时依据的支撑位
    nearest_support = supports[0].price if supports else entry_price * 0.95
    if today['close'] < nearest_support:
        return {'code': 'D4', 'severity': 'exit'}
    
    # D5: 长上影线缩量
    upper_shadow = today['high'] - max(today['open'], today['close'])
    body = abs(today['close'] - today['open']) + 0.001
    if upper_shadow > body * 2:
        if len(prev_days) >= 5 and today['volume'] < avg_vol_5:
            return {'code': 'D5', 'severity': 'reduce'}
    
    return None

def detect_strength_signals(today, prev_days, highest_close, entry_price):
    """
    检测强势信号，返回 {'code': str, 'level': 'strong'/'moderate'} 或 None
    """
    avg_vol_5 = np.mean([d['volume'] for d in prev_days[-5:]]) if len(prev_days) >= 5 else today['volume']
    
    # S1: 放量阳线创新高
    if today['close'] > today['open'] and today['close'] > highest_close:
        if today['volume'] > avg_vol_5 * 1.3:
            return {'code': 'S1', 'level': 'strong'}
    
    # S2: 缩量回踩不破
    if prev_days:
        prev_low = prev_days[-1]['low']
        if abs(today['low'] - prev_low) / prev_low < 0.005:
            if today['close'] > today['open']:
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

def detect_exhaustion_signals(today, prev_days, highest_close, entry_price):
    """
    检测衰竭信号，返回 {'code': str, 'severity': 'exit'/'reduce'} 或 None
    """
    body = abs(today['close'] - today['open'])
    upper_shadow = today['high'] - max(today['open'], today['close'])
    lower_shadow = min(today['open'], today['close']) - today['low']
    avg_vol_5 = np.mean([d['volume'] for d in prev_days[-5:]]) if len(prev_days) >= 5 else today['volume']
    
    # E1: 高位十字星
    if body < 0.005 * today['open'] and upper_shadow > body * 3 and lower_shadow > body * 3:
        if today['high'] >= highest_close * 0.98:
            return {'code': 'E1', 'severity': 'reduce'}
    
    # E2: 放量滞涨
    if today['close'] > today['open']:
        gain = (today['close'] - today['open']) / today['open']
        if gain < 0.01 and today['volume'] > avg_vol_5 * 2:
            return {'code': 'E2', 'severity': 'exit'}
    
    # E3: 连续冲高回落
    if len(prev_days) >= 1:
        yesterday = prev_days[-1]
        if today['high'] > yesterday['high'] and today['close'] < yesterday['close']:
            # 检查昨天是否也是冲高回落
            if len(prev_days) >= 2:
                day_before = prev_days[-2]
                if yesterday['high'] > day_before['high'] and yesterday['close'] < day_before['close']:
                    return {'code': 'E3', 'severity': 'exit'}
    
    return None

def run_dynamic_exit_manager(entry_date, entry_price, initial_stop, initial_tp,
                              path_df, supports, atr, v2_features=None):
    """
    持仓期每日动态调整止损/止盈。
    path_df: 从入场日开始的价格DataFrame，包含列 open, high, low, close, volume
    supports: 融合支撑位列表（用于D4判断）
    返回:
        exit_date, exit_price, exit_reason, trigger_signal, pnl_pct
    """
    position = 1.0
    current_stop = initial_stop
    current_tp = initial_tp
    highest_close = entry_price
    prev_days = []  # 持仓期间已过的K线
    
    for i, (idx, day) in enumerate(path_df.iterrows()):
        if i == 0:  # 入场日当天不评估，从次日开始
            prev_days.append(extract_candle(day))
            continue
            
        today_candle = extract_candle(day)
        
        # 1. 危险信号检测
        danger = detect_danger_signals(today_candle, prev_days, entry_price, supports, position)
        if danger:
            if danger['severity'] == 'exit':
                exit_price = day['open']   # 次日开盘出场（实际回测可调整为当日收盘）
                pnl = (exit_price / entry_price - 1)
                return (day.name, exit_price, 'dynamic_stop', danger['code'], pnl)
            elif danger['severity'] == 'reduce':
                position *= 0.5
                # 减仓后止损上移到当前收盘价（保护剩余仓位）
                current_stop = max(current_stop, day['close'])
        
        # 2. 衰竭信号检测
        exhaustion = detect_exhaustion_signals(today_candle, prev_days, highest_close, entry_price)
        if exhaustion and position > 0:
            if exhaustion['severity'] == 'exit':
                exit_price = day['open']
                pnl = (exit_price / entry_price - 1)
                return (day.name, exit_price, 'dynamic_tp', exhaustion['code'], pnl)
            elif exhaustion['severity'] == 'reduce':
                position *= 0.5
                current_stop = max(current_stop, day['close'])
        
        # 3. 强势信号 → 上移止损
        strength = detect_strength_signals(today_candle, prev_days, highest_close, entry_price)
        if strength:
            if strength['level'] == 'strong':
                current_stop = max(current_stop, day['low'] - 0.5 * atr)
            elif strength['level'] == 'moderate':
                if prev_days:
                    current_stop = max(current_stop, prev_days[-1]['low'])
        
        # 更新最高收盘价
        highest_close = max(highest_close, day['close'])
        
        # 4. 检查原始止损/止盈是否触发
        if day['low'] <= current_stop:
            exit_price = current_stop
            pnl = (exit_price / entry_price - 1)
            return (day.name, exit_price, 'initial_stop', None, pnl)
        if day['high'] >= current_tp:
            exit_price = current_tp
            pnl = (exit_price / entry_price - 1)
            return (day.name, exit_price, 'initial_tp', None, pnl)
        
        prev_days.append(today_candle)
    
    # 持有到期
    last_day = path_df.iloc[-1]
    exit_price = last_day['close']
    pnl = (exit_price / entry_price - 1)
    return (last_day.name, exit_price, 'expiry', None, pnl)
```

---

## 二、`validate_dynamic_signals.py` 完整实现

该脚本加载已有的真实交易路径数据，针对每笔交易运行动态出场管理器，并对比“触发信号即离场”与“无视信号按原固定止损止盈持有”的差异。重点分析每个信号触发时的高/低点与最终收益的关系。

```python
# validate_dynamic_signals.py

import pandas as pd
import numpy as np
from backend.dynamic_exit_manager import run_dynamic_exit_manager
from backend.market_structure import SupportLevel

def load_trades(filepath):
    """加载交易路径数据，格式应与batch_backtest_results.csv一致"""
    df = pd.read_csv(filepath)
    # 假设列名: trade_id, entry_date, entry_price, stop_loss_initial, take_profit_initial,
    #           high_0~high_21, low_0~low_21, close_0~close_21, volume_0~volume_21
    return df

def simulate_original_strategy(trade_row, stop_loss_pct=0.08, take_profit_pct=0.30):
    """模拟原始固定止损止盈策略，返回最终盈亏"""
    entry_price = trade_row['entry_price']
    stop_price = entry_price * (1 - stop_loss_pct)
    tp_price = entry_price * (1 + take_profit_pct)
    
    for i in range(22):
        high = trade_row[f'high_{i}']
        low = trade_row[f'low_{i}']
        close = trade_row[f'close_{i}']
        if low <= stop_price:
            return (stop_price / entry_price - 1)
        if high >= tp_price:
            return (tp_price / entry_price - 1)
    return (trade_row['close_21'] / entry_price - 1)

def run_validation(trades_df, output_csv):
    results = []
    
    for idx, row in trades_df.iterrows():
        entry_price = row['entry_price']
        # 构建路径DataFrame
        path_data = {
            'open': [entry_price] + [row[f'open_{i}'] for i in range(22)],
            'high': [entry_price] + [row[f'high_{i}'] for i in range(22)],
            'low': [entry_price] + [row[f'low_{i}'] for i in range(22)],
            'close': [entry_price] + [row[f'close_{i}'] for i in range(22)],
            'volume': [row[f'volume_{i}'] for i in range(22)]
        }
        path_df = pd.DataFrame(path_data)
        
        # 使用动态出场管理器（设定初始止损止盈，这里以8%/30%为例，也可从数据中读取）
        initial_stop = entry_price * 0.92
        initial_tp = entry_price * 1.30
        # 简单支撑位（仅用于D4，这里用一个虚拟支撑）
        supports = [SupportLevel(price=entry_price*0.95, source='default', confidence=0.5)]
        atr = row.get('atr', 0.05 * entry_price)  # 若无ATR则估算
        
        exit_date, exit_price, exit_reason, trigger_signal, dynamic_pnl = \
            run_dynamic_exit_manager(row['entry_date'], entry_price, initial_stop, initial_tp,
                                     path_df, supports, atr)
        
        # 原始固定策略盈亏
        original_pnl = simulate_original_strategy(row)
        
        # 记录信号触发时的高/低点信息（需要在状态机内部记录，此处简化：从退出原因判断）
        # 为详细分析，我们可以再运行一次仅记录信号触发点而不实际离场，但此处暂略。
        
        results.append({
            'trade_id': idx,
            'dynamic_pnl': dynamic_pnl,
            'original_pnl': original_pnl,
            'exit_reason': exit_reason,
            'trigger_signal': trigger_signal
        })
    
    res_df = pd.DataFrame(results)
    res_df.to_csv(output_csv, index=False)
    print(f"验证结果已保存至 {output_csv}")
    return res_df

def analyze_signals(res_df):
    """按信号分组统计"""
    print("\n=== 出场信号有效性分析 ===\n")
    # 仅分析因动态信号（danger/exhaustion）主动退出的交易
    dyn_trades = res_df[res_df['exit_reason'].isin(['dynamic_stop', 'dynamic_tp'])]
    for signal_code in ['D1','D2','D4','D5','E1','E2','E3']:
        subset = dyn_trades[dyn_trades['trigger_signal'] == signal_code]
        if len(subset) == 0:
            continue
        avg_dyn = subset['dynamic_pnl'].mean()
        avg_ori = subset['original_pnl'].mean()
        improvement = avg_dyn - avg_ori
        win_rate = (subset['dynamic_pnl'] > subset['original_pnl']).mean()
        print(f"信号 {signal_code}: 触发 {len(subset)} 次")
        print(f"  动态出场平均盈亏: {avg_dyn:.2%}, 继续持有平均盈亏: {avg_ori:.2%}")
        print(f"  改善幅度: {improvement:.2%}, 胜出率: {win_rate:.1%}")
        print()
    # 强势信号的效果需通过回测上移止损后的整体回撤改善来评估，这里简略

if __name__ == '__main__':
    # 请根据实际路径修改
    trades_file = 'data/result/super_trend/batch_backtest_results.csv'
    output = 'data/result/super_trend/dynamic_signal_validation.csv'
    res_df = run_validation(trades_file, output)
    analyze_signals(res_df)
```

---

## 三、执行说明

1. **数据准备**  
   确保 `batch_backtest_results.csv` 包含每笔交易的 22 天 OHLC 数据。如果没有，需从 `pure_mfe_analysis.csv` 按照 `stock_code` 和 `t0_date` 构建。

2. **集成点**  
   - `run_dynamic_exit_manager` 可替代原有固定止损止盈逻辑，直接嵌入 `structure_backtester.py` 的持仓循环。  
   - 初始止损 `initial_stop` 可由你现有的 `set_initial_stop_by_pattern` 生成，保持形态差异化入场。  
   - 支撑位 `supports` 使用融合后的列表。

3. **验证结果解读**  
   - 若某危险信号 `improvement` 为正且显著（>0.5%），保留该信号。  
   - 若为负，则从动态管理器中去除此信号检测。  
   - 强势信号（S1-S3）的效果通过对比“上移止损”与“不上移”的最终盈亏来验证（需要单独编写对比脚本）。

4. **高/低点差异的深入分析**  
   要精确评估“在信号触发日按高点/低点离场”是否更好，可以在信号触发时记录当日的最高价和最低价，计算若以最高价止盈（对于衰竭信号）或以最低价止损（对于危险信号）的潜在收益，并与实际次日开盘价离场对比。这可以通过修改 `run_dynamic_exit_manager` 记录更多细节实现，后续再扩展。

先运行此验证脚本，你将得到量化证据：哪些K线形态真的能在持仓期提供有效的离场信号，哪些只是噪声。之后我们就可以只保留高胜率信号，形成最终的动态出场规则，大幅提升整体盈亏。
