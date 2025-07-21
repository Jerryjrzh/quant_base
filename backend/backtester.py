import numpy as np
import pandas as pd

# --- 回测配置 ---
# 信号出现后，向后观察的最大天数
MAX_LOOKAHEAD_DAYS = 30
# 涨幅超过多少被认为是一次“成功的”交易
PROFIT_TARGET_FOR_SUCCESS = 0.05 

def get_optimal_entry_price(df, signal_idx, signal_state, lookback_days=5, lookahead_days=3):
    """
    根据信号状态确定最佳入场价格
    
    Args:
        df: 股票数据DataFrame
        signal_idx: 信号出现的索引
        signal_state: 信号状态 ('PRE', 'MID', 'POST' 或 True/False)
        lookback_days: 向前查找天数
        lookahead_days: 向后查找天数
    
    Returns:
        tuple: (最佳入场价格, 入场日期索引, 入场策略说明)
    """
    try:
        if signal_state == 'PRE':
            # PRE状态：预期即将突破，在信号后1-3天内寻找低点买入
            start_idx = signal_idx + 1
            end_idx = min(signal_idx + 1 + lookahead_days, len(df))
            window_data = df.iloc[start_idx:end_idx]
            
            if not window_data.empty:
                # 寻找最低价对应的日期
                min_idx = window_data['low'].idxmin()
                entry_price = df.loc[min_idx, 'low']
                return entry_price, min_idx, f"PRE状态-信号后{min_idx - signal_idx}天低点买入"
            else:
                # 如果没有未来数据，使用信号当天收盘价
                return df.loc[signal_idx, 'close'], signal_idx, "PRE状态-信号当天收盘价"
                
        elif signal_state == 'MID':
            # MID状态：正在突破中，立即买入或在当天低点买入
            entry_price = df.loc[signal_idx, 'low']  # 使用当天低点
            return entry_price, signal_idx, "MID状态-当天低点买入"
            
        elif signal_state == 'POST':
            # POST状态：已经突破，可能需要回调买入
            # 先检查信号前几天是否有更好的买点
            start_idx = max(0, signal_idx - lookback_days)
            end_idx = signal_idx + 1
            window_data = df.iloc[start_idx:end_idx]
            
            if not window_data.empty:
                # 寻找回调低点
                min_idx = window_data['low'].idxmin()
                entry_price = df.loc[min_idx, 'low']
                return entry_price, min_idx, f"POST状态-信号前{signal_idx - min_idx}天回调低点买入"
            else:
                return df.loc[signal_idx, 'close'], signal_idx, "POST状态-信号当天收盘价"
                
        else:
            # 布尔类型信号或其他情况，使用传统方法
            entry_price = df.loc[signal_idx, 'close']
            return entry_price, signal_idx, "传统方法-信号当天收盘价"
            
    except Exception as e:
        print(f"获取最佳入场价格时出错: {e}")
        # 出错时使用收盘价作为备选
        return df.loc[signal_idx, 'close'], signal_idx, "异常情况-使用收盘价"

def run_backtest(df, signal_series):
    """
    细化的回测函数，根据signal_state优化入场点
    """
    if signal_series is None:
        return {"total_signals": 0, "message": "无信号数据"}
        
    if signal_series.dtype == bool:
        entry_indices = df.index[signal_series]
        signal_states = ['MID'] * len(entry_indices)  # 布尔信号默认为MID状态
    else:
        entry_indices = df.index[signal_series != '']
        signal_states = [signal_series.loc[idx] for idx in entry_indices]

    if entry_indices.empty:
        return {"total_signals": 0, "message": "在历史数据中未发现信号点"}

    trades = []
    valid_entry_indices = []
    
    for i, signal_idx in enumerate(entry_indices):
        try:
            signal_state = signal_states[i]
            
            # 根据信号状态获取最佳入场价格
            entry_price, actual_entry_idx, entry_strategy = get_optimal_entry_price(
                df, signal_idx, signal_state
            )
            
            # 定义未来30天的观察窗口（从实际入场日开始）
            window_start_idx = actual_entry_idx + 1
            window_end_idx = min(window_start_idx + MAX_LOOKAHEAD_DAYS, len(df))
            
            if window_start_idx >= len(df):
                continue
                
            future_data = df.iloc[window_start_idx:window_end_idx]
            
            if future_data.empty:
                continue

            # 找到窗口内的最高价及其位置
            peak_price = future_data['high'].max()
            peak_idx = future_data['high'].idxmax()
            
            # 同时记录最低价，用于分析最大回撤
            trough_price = future_data['low'].min()
            trough_idx = future_data['low'].idxmin()
            
            # 计算收益指标
            max_pnl = (peak_price - entry_price) / entry_price
            max_drawdown = (trough_price - entry_price) / entry_price
            days_to_peak = peak_idx - actual_entry_idx
            days_to_trough = trough_idx - actual_entry_idx
            
            is_success = max_pnl >= PROFIT_TARGET_FOR_SUCCESS
            
            trade_info = {
                "signal_idx": int(signal_idx),
                "signal_state": signal_state,
                "entry_idx": int(actual_entry_idx),
                "entry_price": float(entry_price),
                "entry_strategy": entry_strategy,
                "peak_price": float(peak_price),
                "trough_price": float(trough_price),
                "max_pnl": float(max_pnl),
                "max_drawdown": float(max_drawdown),
                "days_to_peak": int(days_to_peak),
                "days_to_trough": int(days_to_trough),
                "is_success": bool(is_success)
            }
            
            trades.append(trade_info)
            valid_entry_indices.append(int(signal_idx))
            
        except Exception as e:
            print(f"Error processing entry at index {signal_idx}: {e}")
            continue

    if not trades:
        return {"total_signals": len(entry_indices), "message": "信号点过于靠近数据末尾，无法完成回测"}

    # 按信号状态分组统计
    state_stats = {}
    for trade in trades:
        state = trade['signal_state']
        if state not in state_stats:
            state_stats[state] = []
        state_stats[state].append(trade)
    
    # 计算整体统计指标
    total_signals = len(trades)
    successful_trades = [t for t in trades if t['is_success']]
    win_rate = len(successful_trades) / total_signals if total_signals > 0 else 0
    
    avg_max_profit = np.mean([t['max_pnl'] for t in trades])
    avg_max_drawdown = np.mean([t['max_drawdown'] for t in trades])
    avg_days_to_peak = np.mean([t['days_to_peak'] for t in successful_trades]) if successful_trades else 0
    
    # 计算各状态的统计
    state_statistics = {}
    for state, state_trades in state_stats.items():
        state_successful = [t for t in state_trades if t['is_success']]
        state_win_rate = len(state_successful) / len(state_trades) if state_trades else 0
        state_avg_profit = np.mean([t['max_pnl'] for t in state_trades]) if state_trades else 0
        state_avg_drawdown = np.mean([t['max_drawdown'] for t in state_trades]) if state_trades else 0
        state_avg_days = np.mean([t['days_to_peak'] for t in state_successful]) if state_successful else 0
        
        state_statistics[state] = {
            "count": len(state_trades),
            "win_rate": f"{state_win_rate:.1%}",
            "avg_max_profit": f"{state_avg_profit:.1%}",
            "avg_max_drawdown": f"{state_avg_drawdown:.1%}",
            "avg_days_to_peak": f"{state_avg_days:.1f} 天"
        }

    return {
        "total_signals": total_signals,
        "win_rate": f"{win_rate:.1%}",
        "avg_max_profit": f"{avg_max_profit:.1%}",
        "avg_max_drawdown": f"{avg_max_drawdown:.1%}",
        "avg_days_to_peak": f"{avg_days_to_peak:.1f} 天",
        "state_statistics": state_statistics,
        "trades": trades,
        "entry_indices": valid_entry_indices
    }
