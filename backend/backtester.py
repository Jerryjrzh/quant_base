#!/usr/bin/env python3
import numpy as np
import pandas as pd
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# 导入必要的模块 (原portfolio_manager中的依赖)
import data_loader
import indicators
from adjustment_processor import create_adjustment_config, create_adjustment_processor
# --- 新增：导入多指标融合评分系统 ---
from confluence_scorer import confluence_scorer
from pattern_recognizer import pattern_recognizer

# --- 回测配置 ---
# 信号出现后，向后观察的最大天数
MAX_LOOKAHEAD_DAYS = 30
# 涨幅超过多少被认为是一次“成功的”交易
PROFIT_TARGET_FOR_SUCCESS = 0.05 

def check_macd_zero_axis_filter(df, signal_idx, signal_state, lookback_days=5):
    """
    MACD零轴启动策略的过滤器：排除五日内价格上涨超过5%的情况
    
    Args:
        df: 股票数据DataFrame
        signal_idx: 信号出现的索引
        signal_state: 信号状态
        lookback_days: 回看天数
    
    Returns:
        tuple: (是否应该排除, 排除原因)
    """
    try:
        # 只对MACD零轴启动策略进行过滤
        if signal_state not in ['PRE', 'MID', 'POST']:
            return False, ""
        
        # 转换为位置索引进行计算
        signal_pos = df.index.get_loc(signal_idx) if signal_idx in df.index else 0
        
        # 获取信号前5天的数据
        start_pos = max(0, signal_pos - lookback_days)
        end_pos = signal_pos
        
        if start_pos >= end_pos:
            return False, ""
        
        # 计算5日内的最大涨幅
        lookback_data = df.iloc[start_pos:end_pos + 1]
        if len(lookback_data) < 2:
            return False, ""
        
        # 获取5日前的收盘价和信号当天的最高价
        base_price = lookback_data.iloc[0]['close']  # 5日前收盘价
        current_high = df.loc[signal_idx, 'high']    # 信号当天最高价
        
        # 计算涨幅
        price_increase = (current_high - base_price) / base_price
        
        # 如果5日内涨幅超过5%，则排除
        if price_increase > 0.25:
            return True, f"五日内涨幅{price_increase:.1%}超过25%，排除高低风险"
        
        return False, ""
        
    except Exception as e:
        print(f"MACD零轴过滤器检查失败: {e}")
        return False, ""

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
        tuple: (最佳入场价格, 入场日期索引, 入场策略说明, 是否被过滤)
    """
    try:
        # 首先检查MACD零轴启动的过滤条件
        #should_exclude, exclude_reason = check_macd_zero_axis_filter(df, signal_idx, signal_state, lookback_days)
        
        #if should_exclude:
        #    return None, signal_idx, exclude_reason, True
        
        if signal_state == 'PRE':
            # PRE状态：预期即将突破，在信号后1-3天内寻找低点买入
            signal_pos = df.index.get_loc(signal_idx) if signal_idx in df.index else 0
            start_pos = signal_pos + 1
            end_pos = min(signal_pos + 1 + lookahead_days, len(df))
            window_data = df.iloc[start_pos:end_pos]
            
            if not window_data.empty:
                # 寻找最低价对应的日期
                min_idx = window_data['low'].idxmin()
                entry_price = df.loc[min_idx, 'low']
                # 计算天数差异（使用位置索引）
                signal_pos = df.index.get_loc(signal_idx)
                min_pos = df.index.get_loc(min_idx)
                days_diff = min_pos - signal_pos
                return entry_price, min_idx, f"PRE状态-信号后{days_diff}天低点买入", False
            else:
                # 如果没有未来数据，使用信号当天收盘价
                return df.loc[signal_idx, 'close'], signal_idx, "PRE状态-信号当天收盘价", False
                
        elif signal_state == 'MID':
            # MID状态：正在突破中，立即买入或在当天低点买入
            entry_price = df.loc[signal_idx, 'low']  # 使用当天低点
            return entry_price, signal_idx, "MID状态-当天低点买入", False
            
        elif signal_state == 'POST':
            # POST状态：已经突破，可能需要回调买入
            # 先检查信号前几天是否有更好的买点
            signal_pos = df.index.get_loc(signal_idx) if signal_idx in df.index else 0
            start_pos = max(0, signal_pos - lookback_days)
            end_pos = signal_pos + 1
            window_data = df.iloc[start_pos:end_pos]
            
            if not window_data.empty:
                # 寻找回调低点
                min_idx = window_data['low'].idxmin()
                entry_price = df.loc[min_idx, 'low']
                # 计算天数差异（使用位置索引）
                signal_pos = df.index.get_loc(signal_idx)
                min_pos = df.index.get_loc(min_idx)
                days_diff = signal_pos - min_pos
                return entry_price, min_idx, f"POST状态-信号前{days_diff}天回调低点买入", False
            else:
                return df.loc[signal_idx, 'close'], signal_idx, "POST状态-信号当天收盘价", False
                
        else:
            # 布尔类型信号或其他情况，使用传统方法
            entry_price = df.loc[signal_idx, 'close']
            return entry_price, signal_idx, "传统方法-信号当天收盘价", False
            
    except Exception as e:
        print(f"获取最佳入场价格时出错: {e}")
        # 出错时使用收盘价作为备选
        return df.loc[signal_idx, 'close'], signal_idx, "异常情况-使用收盘价", False

def group_signals_by_cycle(df, signal_series):
    """将PRE/MID/POST信号按周期分组，每个周期只计算一次回测"""
    if signal_series.dtype == bool:
        # 为布尔信号创建简单的周期信息
        return [(idx, 'MID', {'start_idx': idx, 'pre_idx': None, 'mid_idx': idx, 'post_idx': None}) 
                for idx in df.index[signal_series]]
    
    signal_cycles = []
    current_cycle = None
    
    for idx, state in signal_series.items():
        if state == '':
            continue
            
        if state == 'PRE':
            # 开始新周期
            if current_cycle is None:
                current_cycle = {'start_idx': idx, 'pre_idx': idx, 'mid_idx': None, 'post_idx': None}
        elif state == 'MID' and current_cycle is not None:
            current_cycle['mid_idx'] = idx
        elif state == 'POST' and current_cycle is not None:
            current_cycle['post_idx'] = idx
            # 结束当前周期
            signal_cycles.append(current_cycle)
            current_cycle = None
        elif state == 'MID' and current_cycle is None:
            # 独立的MID信号
            signal_cycles.append({'start_idx': idx, 'pre_idx': None, 'mid_idx': idx, 'post_idx': None})
    
    # 处理未完成的周期
    if current_cycle is not None:
        signal_cycles.append(current_cycle)
    
    # 转换为回测用的格式：选择最佳入场点
    cycle_signals = []
    for cycle in signal_cycles:
        # 优先选择PRE，其次MID，最后POST
        if cycle['pre_idx'] is not None:
            cycle_signals.append((cycle['pre_idx'], 'PRE', cycle))
        elif cycle['mid_idx'] is not None:
            cycle_signals.append((cycle['mid_idx'], 'MID', cycle))
        elif cycle['post_idx'] is not None:
            cycle_signals.append((cycle['post_idx'], 'POST', cycle))
    
    return cycle_signals

def check_trend_confirmation(df, entry_idx, confirmation_days=5):
    """检查入场后的趋势确认"""
    try:
        # 转换为位置索引进行计算
        entry_pos = df.index.get_loc(entry_idx) if entry_idx in df.index else 0
        
        # 获取入场后的确认期数据
        confirm_start_pos = entry_pos + 1
        confirm_end_pos = min(confirm_start_pos + confirmation_days, len(df))
        
        if confirm_start_pos >= len(df):
            return False, "无后续数据"
        
        confirm_data = df.iloc[confirm_start_pos:confirm_end_pos]
        if confirm_data.empty:
            return False, "确认期数据不足"
        
        entry_price = df.iloc[entry_pos]['close']
        
        # 计算确认期内的价格趋势
        price_changes = []
        for i, row in confirm_data.iterrows():
            change = (row['close'] - entry_price) / entry_price
            price_changes.append(change)
        
        # 趋势确认条件：
        # 1. 确认期内至少有60%的交易日收盘价高于入场价
        # 2. 确认期结束时价格不能低于入场价超过2%
        positive_days = sum(1 for change in price_changes if change > 0)
        positive_ratio = positive_days / len(price_changes)
        
        final_change = price_changes[-1] if price_changes else -1
        
        trend_confirmed = positive_ratio >= 0.6 and final_change > -0.02
        
        reason = f"确认期{confirmation_days}天，上涨天数比例{positive_ratio:.1%}，期末涨幅{final_change:.1%}"
        
        return trend_confirmed, reason
        
    except Exception as e:
        return False, f"趋势确认检查失败: {e}"

def find_cycle_bottom_and_top(df, cycle_info):
    """找到一个信号周期内的价格底部和顶部"""
    try:
        start_idx = cycle_info['start_idx']
        
        # 转换为位置索引进行计算
        start_pos = df.index.get_loc(start_idx) if start_idx in df.index else 0
        
        # 确定周期结束点：如果有POST，用POST+5天；否则用开始点+15天
        if cycle_info['post_idx'] is not None:
            post_pos = df.index.get_loc(cycle_info['post_idx']) if cycle_info['post_idx'] in df.index else start_pos
            cycle_end_pos = min(post_pos + 5, len(df) - 1)
        else:
            cycle_end_pos = min(start_pos + 15, len(df) - 1)
        
        # 获取周期内的数据
        cycle_data = df.iloc[start_pos:cycle_end_pos + 1]
        
        if cycle_data.empty:
            return None, None, None, None
        
        # 找到最低点（底部）
        bottom_idx = cycle_data['low'].idxmin()
        bottom_price = df.loc[bottom_idx, 'low']
        
        # 从底部开始向后找最高点（顶部）
        bottom_pos = df.index.get_loc(bottom_idx)
        top_search_start_pos = max(bottom_pos, start_pos)
        top_search_end_pos = min(top_search_start_pos + MAX_LOOKAHEAD_DAYS, len(df) - 1)
        
        top_data = df.iloc[top_search_start_pos:top_search_end_pos + 1]
        if top_data.empty:
            return bottom_idx, bottom_price, None, None
        
        top_idx = top_data['high'].idxmax()
        top_price = df.loc[top_idx, 'high']
        
        return bottom_idx, bottom_price, top_idx, top_price
        
    except Exception as e:
        print(f"寻找周期底部和顶部失败: {e}")
        return None, None, None, None

def run_backtest(df, signal_series):
    """
    优化的回测函数：按周期分组，从底部到顶部计算收益，添加趋势确认
    """
    if signal_series is None:
        return {"total_signals": 0, "message": "无信号数据"}
    
    # 按周期分组信号
    cycle_signals = group_signals_by_cycle(df, signal_series)
    
    if not cycle_signals:
        return {"total_signals": 0, "message": "在历史数据中未发现有效信号周期"}

    trades = []
    valid_entry_indices = []
    
    for signal_idx, signal_state, cycle_info in cycle_signals:
        try:
            # 转换timestamp为位置索引以避免pandas版本兼容问题
            if signal_idx in df.index:
                signal_pos = df.index.get_loc(signal_idx)
            else:
                print(f"Signal index {signal_idx} not found in dataframe")
                continue
                
            # 根据信号状态获取最佳入场价格
            entry_result = get_optimal_entry_price(df, signal_idx, signal_state)
            entry_price, actual_entry_idx, entry_strategy, is_filtered = entry_result
            
            # 如果信号被过滤，跳过此信号
            if is_filtered:
                print(f"信号被过滤: {entry_strategy}")
                continue
            
            # 检查趋势确认
            trend_confirmed, trend_reason = check_trend_confirmation(df, actual_entry_idx)
            
            # 找到周期内的底部和顶部
            bottom_idx, bottom_price, top_idx, top_price = find_cycle_bottom_and_top(df, cycle_info)
            
            if bottom_idx is None or top_idx is None:
                print(f"无法确定周期{signal_idx}的底部或顶部")
                continue
            
            # 使用底部价格作为基准计算收益（更真实的收益计算）
            cycle_max_pnl = (top_price - bottom_price) / bottom_price
            
            # 计算实际入场价格的收益
            if top_price and entry_price:
                actual_max_pnl = (top_price - entry_price) / entry_price
            else:
                actual_max_pnl = 0
            
            # 计算最大回撤（从入场价到周期内最低价） - 使用位置索引
            try:
                entry_pos = df.index.get_loc(actual_entry_idx) if actual_entry_idx in df.index else 0
                top_pos = df.index.get_loc(top_idx) if top_idx in df.index else entry_pos
                if top_pos > entry_pos:
                    cycle_data = df.iloc[entry_pos:top_pos + 1]
                else:
                    cycle_data = df.iloc[entry_pos:entry_pos + 1]
            except:
                cycle_data = df.iloc[entry_pos:entry_pos + 1] if 'entry_pos' in locals() else pd.DataFrame()
            if not cycle_data.empty:
                trough_price = cycle_data['low'].min()
                max_drawdown = (trough_price - entry_price) / entry_price
            else:
                max_drawdown = 0
            
            # 计算时间指标 - 使用位置索引避免Timestamp算术运算
            if top_idx is not None and actual_entry_idx is not None:
                try:
                    top_pos = df.index.get_loc(top_idx) if top_idx in df.index else 0
                    entry_pos = df.index.get_loc(actual_entry_idx) if actual_entry_idx in df.index else 0
                    days_to_peak = top_pos - entry_pos if top_pos > entry_pos else 0
                except:
                    days_to_peak = 0
            else:
                days_to_peak = 0
            
            # 成功判定：考虑趋势确认和收益目标
            is_success = trend_confirmed and actual_max_pnl >= PROFIT_TARGET_FOR_SUCCESS
            
            # 安全转换Timestamp索引为位置索引
            try:
                signal_pos = df.index.get_loc(signal_idx) if signal_idx in df.index else 0
                entry_pos = df.index.get_loc(actual_entry_idx) if actual_entry_idx in df.index else 0
                bottom_pos = df.index.get_loc(bottom_idx) if bottom_idx in df.index else 0
                top_pos = df.index.get_loc(top_idx) if top_idx is not None and top_idx in df.index else None
            except:
                signal_pos = 0
                entry_pos = 0
                bottom_pos = 0
                top_pos = None
            
            trade_info = {
                "signal_idx": signal_pos,
                "signal_state": signal_state,
                "entry_idx": entry_pos,
                "entry_price": float(entry_price),
                "entry_strategy": entry_strategy,
                "bottom_idx": bottom_pos,
                "bottom_price": float(bottom_price),
                "top_idx": top_pos,
                "top_price": float(top_price) if top_price is not None else None,
                "cycle_max_pnl": float(cycle_max_pnl),
                "actual_max_pnl": float(actual_max_pnl),
                "max_drawdown": float(max_drawdown),
                "days_to_peak": int(days_to_peak),
                "trend_confirmed": trend_confirmed,
                "trend_reason": trend_reason,
                "is_success": bool(is_success),
                "cycle_info": cycle_info
            }
            
            trades.append(trade_info)
            valid_entry_indices.append(signal_pos)  # 使用已转换的位置索引
            
        except Exception as e:
            print(f"Error processing cycle signal at index {signal_idx}: {e}")
            continue

    if not trades:
        return {"total_signals": len(cycle_signals), "message": "信号周期过于靠近数据末尾，无法完成回测"}

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
    
    avg_max_profit = np.mean([t['actual_max_pnl'] for t in trades])
    avg_max_drawdown = np.mean([t['max_drawdown'] for t in trades])
    avg_days_to_peak = np.mean([t['days_to_peak'] for t in successful_trades]) if successful_trades else 0
    
    # 计算各状态的统计
    state_statistics = {}
    for state, state_trades in state_stats.items():
        state_successful = [t for t in state_trades if t['is_success']]
        state_win_rate = len(state_successful) / len(state_trades) if state_trades else 0
        state_avg_profit = np.mean([t['actual_max_pnl'] for t in state_trades]) if state_trades else 0
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

# --- 新增：从 portfolio_manager 迁移并整合的功能 ---

def _calculate_max_drawdown(prices: pd.Series) -> float:
    """计算最大回撤"""
    try:
        peak = prices.expanding(min_periods=1).max()
        drawdown = (prices - peak) / peak
        return float(drawdown.min())
    except Exception:
        return 0.0

def _assess_risk_profile(df: pd.DataFrame) -> Dict:
    """
    评估风险概况 (逻辑源自 enhanced_analyzer.py)
    """
    try:
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) # 年化波动率
        max_drawdown = _calculate_max_drawdown(df['close'])
        
        # 价格位置（当前价格在最近一年高低点中的位置）
        recent_year = df.tail(252)
        price_position_pct = 0
        if not recent_year.empty:
            min_price = recent_year['low'].min()
            max_price = recent_year['high'].max()
            current_price = df['close'].iloc[-1]
            if (max_price - min_price) > 0:
                price_position_pct = (current_price - min_price) / (max_price - min_price)

        # 综合风险评分 (0-1, 越高风险越大)
        volatility_risk = min(volatility / 0.8, 1.0)    # 波动率风险 (标准化)
        drawdown_risk = min(abs(max_drawdown) / 0.5, 1.0) # 回撤风险 (标准化)
        position_risk = price_position_pct * 0.5       # 价格位置风险
        
        overall_risk = (volatility_risk * 0.4 + drawdown_risk * 0.4 + position_risk * 0.2)
        
        risk_level = 'LOW' if overall_risk < 0.35 else 'MEDIUM' if overall_risk < 0.65 else 'HIGH'
        
        return {
            'volatility': float(volatility),
            'max_drawdown': float(max_drawdown),
            'price_position_pct': float(price_position_pct),
            'overall_risk_score': float(overall_risk),
            'risk_level': risk_level
        }
    except Exception as e:
        return {'error': f'风险评估失败: {str(e)}', 'risk_level': 'UNKNOWN'}

def _calculate_price_targets(df: pd.DataFrame, current_price: float) -> dict:
    """计算价格目标（支撑位和阻力位），这是一个辅助函数"""
    recent_data = df.tail(60)
    resistance_levels = []
    support_levels = []
    
    # 基于历史高低点
    highs = recent_data['high'].rolling(window=5).max()
    lows = recent_data['low'].rolling(window=5).min()
    
    for i in range(5, len(recent_data)-5):
        if highs.iloc[i] == recent_data['high'].iloc[i]:
            resistance_levels.append(float(recent_data['high'].iloc[i]))
        if lows.iloc[i] == recent_data['low'].iloc[i]:
            support_levels.append(float(recent_data['low'].iloc[i]))
    
    resistance_levels = sorted(list(set(resistance_levels)), reverse=True)
    support_levels = sorted(list(set(support_levels)))
    
    next_resistance = next((level for level in resistance_levels if level > current_price), None)
    next_support = next((level for level in reversed(support_levels) if level < current_price), None)
    
    return {'next_resistance': next_resistance, 'next_support': next_support}

def _optimize_coefficients_historically(df: pd.DataFrame) -> dict:
    """
    通过历史数据回测，优化补仓和卖出系数。
    【已增强】增加了卖出系数的优化逻辑。
    """
    add_coefficients = [0.96, 0.97, 0.98, 0.99, 1.00]
    sell_coefficients = [1.03, 1.05, 1.08, 1.10, 1.15, 1.20] # 卖出系数
    
    # --- 补仓系数回测 (逻辑不变) ---
    add_results = {}
    best_add_coefficient = None
    best_add_score = -999
    for add_coeff in add_coefficients:
        success_count, total_scenarios, total_return = 0, 0, 0
        for i in range(100, len(df) - 30):
            current_data = df.iloc[:i+1]
            future_data = df.iloc[i+1:i+31]
            if len(future_data) < 15: continue
            hist_price = float(current_data.iloc[-1]['close'])
            price_targets = _calculate_price_targets(current_data, hist_price)
            support_level = price_targets.get('next_support')
            if not support_level: continue
            add_price = support_level * add_coeff
            if float(future_data['low'].min()) <= add_price:
                total_scenarios += 1
                return_pct = (float(future_data['high'].max()) - add_price) / add_price * 100
                if return_pct > 0: success_count += 1
                total_return += return_pct
        if total_scenarios > 0:
            success_rate = success_count / total_scenarios * 100
            avg_return = total_return / total_scenarios
            score = success_rate * 0.6 + avg_return * 0.4
            add_results[add_coeff] = {'success_rate': success_rate, 'avg_return': avg_return, 'score': score}
            if score > best_add_score:
                best_add_score = score
                best_add_coefficient = add_coeff

    # --- 新增：卖出系数回测 ---
    sell_results = {}
    best_sell_coefficient = None
    best_sell_score = -999
    for sell_coeff in sell_coefficients:
        success_count, total_scenarios, total_return, total_hold_days = 0, 0, 0, 0
        for i in range(100, len(df) - 30):
            current_data = df.iloc[:i+1]
            future_data = df.iloc[i+1:i+31]
            if len(future_data) < 15: continue
            
            # 假设在当天买入
            entry_price = float(current_data.iloc[-1]['close'])
            # 基于当天价格计算卖出目标价
            sell_price = entry_price * sell_coeff
            
            # 检查未来是否能达到卖出价
            future_highs = future_data['high']
            if float(future_highs.max()) >= sell_price:
                total_scenarios += 1
                # 找到第一个达到卖出价的天数
                days_to_sell = (future_highs >= sell_price).idxmax()
                hold_days = (days_to_sell - current_data.index[-1]).days
                
                return_pct = (sell_price - entry_price) / entry_price * 100
                success_count += 1
                total_return += return_pct
                total_hold_days += hold_days
        
        if total_scenarios > 0:
            success_rate = success_count / total_scenarios * 100
            avg_return = total_return / total_scenarios
            avg_hold_days = total_hold_days / total_scenarios
            # 评分：收益率越高越好，持有天数越短越好
            score = (success_rate * 0.5 + avg_return * 0.5) / (1 + avg_hold_days * 0.05)
            sell_results[sell_coeff] = {'success_rate': success_rate, 'avg_return': avg_return, 'avg_hold_days': avg_hold_days, 'score': score}
            if score > best_sell_score:
                best_sell_score = score
                best_sell_coefficient = sell_coeff

    # --- 返回合并后的结果 ---
    return {
        'best_add_coefficient': best_add_coefficient,
        'best_add_score': best_add_score,
        'add_coefficient_analysis': add_results,
        'best_sell_coefficient': best_sell_coefficient, # 新增
        'best_sell_score': best_sell_score,           # 新增
        'sell_coefficient_analysis': sell_results,    # 新增
    }

# backend/backtester.py

# backend/backtester.py

def _generate_forward_advice(df: pd.DataFrame, backtest_results: dict) -> dict:
    """
    【增强版】基于多指标融合评分系统生成高质量交易建议
    集成价格位置、形态识别和技术指标一致性分析
    """
    current_price = float(df.iloc[-1]['close'])
    price_targets = _calculate_price_targets(df, current_price)
    support_level = price_targets.get('next_support')
    resistance_level = price_targets.get('next_resistance')
    
    # 获取最新数据索引
    latest_index = len(df) - 1
    
    # === 核心增强：多指标融合分析 ===
    
    # 1. 价格位置分析
    price_filter_passed, price_reason = confluence_scorer.filter_by_price_position(df, latest_index)
    
    # 2. 多指标融合评分
    confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
    
    # 3. 形态识别
    pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)
    
    # 4. 传统价格目标计算
    best_add_coefficient = backtest_results.get('best_add_coefficient')
    optimal_add_price = None
    if support_level and best_add_coefficient:
        optimal_add_price = support_level * best_add_coefficient
    
    best_sell_coefficient = backtest_results.get('best_sell_coefficient')
    optimal_sell_price = None
    if best_sell_coefficient:
        optimal_sell_price = current_price * best_sell_coefficient

    # === 增强版建议生成逻辑 ===
    action = 'HOLD'
    reasons = []
    confidence = confluence_result['confidence']  # 使用融合评分的置信度
    
    # 基于融合评分和形态识别生成建议
    if not price_filter_passed:
        action = 'AVOID'
        reasons.append(f"价格位置过高: {price_reason}")
        confidence = 0.3
    elif confluence_result['is_high_quality']:
        # 高质量信号
        if pattern_result['has_pattern']:
            action = 'BUY'
            reasons.append(f"发现{pattern_result['best_pattern']}形态，融合评分{confluence_result['total_score']:.1f}")
            reasons.append(f"多指标一致性良好，置信度{confluence_result['confidence']:.1%}")
            confidence = min(confluence_result['confidence'] + 0.1, 0.95)
        else:
            action = 'BUY'
            reasons.append(f"多指标融合评分{confluence_result['total_score']:.1f}，技术指标一致性好")
            confidence = confluence_result['confidence']
    elif confluence_result['total_score'] >= 50:
        # 中等质量信号
        action = 'WATCH'
        reasons.append(f"融合评分{confluence_result['total_score']:.1f}，建议观察等待更好时机")
        confidence = confluence_result['confidence'] * 0.8
    else:
        # 低质量信号
        action = 'AVOID'
        reasons.append(f"融合评分{confluence_result['total_score']:.1f}过低，技术指标不一致")
        confidence = 0.3
    
    # 添加具体的技术指标分析
    breakdown = confluence_result.get('breakdown', {})
    if breakdown.get('price_position', 0) >= 30:
        reasons.append("价格处于相对低位，安全边际较高")
    if breakdown.get('macd_state', 0) >= 20:
        reasons.append("MACD显示动能转强信号")
    if breakdown.get('kdj_state', 0) >= 15:
        reasons.append("KDJ指标显示超卖反弹")
    
    # 状态历史条件
    stateful_conditions = confluence_result.get('stateful_conditions', {})
    if stateful_conditions.get('macd_consolidation'):
        reasons.append("MACD经历充分整理，反转信号更可靠")
    if stateful_conditions.get('kdj_oversold_period'):
        reasons.append("KDJ经历超卖期，反弹概率增加")

    # 动态调整价格目标
    if confluence_result['is_high_quality']:
        # 高质量信号可以适当提高目标价
        if optimal_sell_price:
            optimal_sell_price *= 1.1
        if resistance_level:
            resistance_level *= 1.05
    
    # 映射键名以匹配前端和命令行工具的期望
    return {
        'action': action,
        'confidence': confidence,
        'analysis_logic': reasons,
        'current_price': current_price,
        'entry_price': optimal_add_price or (support_level or current_price * 0.98),
        'target_price': optimal_sell_price or resistance_level or current_price * 1.1,
        'stop_price': support_level * 0.95 if support_level else current_price * 0.92,
        'resistance_level': resistance_level,
        'support_level': support_level,
        # 新增：融合评分相关信息
        'confluence_score': confluence_result['total_score'],
        'quality_grade': 'A' if confluence_result['total_score'] >= 85 else 'B' if confluence_result['total_score'] >= 70 else 'C',
        'pattern_detected': pattern_result.get('has_pattern', False),
        'pattern_type': pattern_result.get('best_pattern', None),
        'price_position_safe': price_filter_passed
    }

def _generate_forward_advice_b1(df: pd.DataFrame, backtest_results: dict) -> dict:
    """
    【已优化】基于回测的最优系数，生成包含具体买卖价格的前瞻性交易建议。
    """
    current_price = float(df.iloc[-1]['close'])
    price_targets = _calculate_price_targets(df, current_price)
    support_level = price_targets.get('next_support')
    resistance_level = price_targets.get('next_resistance')
    
    # --- [核心修改开始] ---
    
    # 1. 计算建议的补仓/入场价
    best_add_coefficient = backtest_results.get('best_add_coefficient')
    optimal_add_price = None
    if support_level and best_add_coefficient:
        optimal_add_price = support_level * best_add_coefficient
    
    # 2. 【新增】计算基于最优回测系数的目标卖出价
    best_sell_coefficient = backtest_results.get('best_sell_coefficient')
    optimal_sell_price = None
    if best_sell_coefficient:
        optimal_sell_price = current_price * best_sell_coefficient
        
    # --- [核心修改结束] ---

    # 简化版建议生成逻辑
    action = 'HOLD'
    reasons = []
    confidence = 0.6
    latest = df.iloc[-1]
    if not pd.isna(latest.get('rsi6')) and latest['rsi6'] < 30:
        action = 'BUY'
        reasons.append(f"RSI(6)为{latest['rsi6']:.1f}，进入超卖区，存在反弹机会。")
        confidence = 0.75
    elif not pd.isna(latest.get('ma60')) and latest['close'] < latest['ma60']:
        action = 'AVOID'
        reasons.append(f"价格位于长期均线MA60下方，趋势偏弱。")
        confidence = 0.5
    else:
        reasons.append("当前技术指标处于中性区域，建议继续观察。")

    # 映射键名以匹配前端 app.js 的 updateAdvicePanel 函数
    return {
        'action': action,
        'confidence': confidence,
        'analysis_logic': reasons,
        'current_price': current_price,
        # 使用计算出的最优价格，如果不存在则提供一个合理的备用值
        'entry_price': optimal_add_price or (support_level or current_price * 0.98),
        'target_price': optimal_sell_price or resistance_level or current_price * 1.1,
        'stop_price': support_level * 0.95 if support_level else current_price * 0.92,
        'resistance_level': resistance_level,
        'support_level': support_level
    }

def _generate_forward_advice_b(df: pd.DataFrame, backtest_results: dict) -> dict:
    """
    【已修复】基于最新的数据和历史回测的最优系数，生成与前端兼容的交易建议。
    """
    current_price = float(df.iloc[-1]['close'])
    price_targets = _calculate_price_targets(df, current_price)
    support_level = price_targets.get('next_support')
    resistance_level = price_targets.get('next_resistance')
    
    best_add_coefficient = backtest_results.get('best_add_coefficient')
    optimal_add_price = None
    if support_level and best_add_coefficient:
        optimal_add_price = support_level * best_add_coefficient

    # 简化版建议生成
    action = 'HOLD'
    reasons = []
    confidence = 0.6

    latest = df.iloc[-1]
    if latest['rsi6'] < 30:
        action = 'BUY'
        reasons.append(f"RSI(6)为{latest['rsi6']:.1f}，进入超卖区，存在反弹机会。")
        confidence = 0.75
    elif latest['close'] < latest['ma60']:
        action = 'AVOID'
        reasons.append(f"价格位于长期均线MA60下方，趋势偏弱。")
        confidence = 0.5
    else:
        reasons.append("当前技术指标处于中性区域，建议继续观察。")

    # --- [FIX START] ---
    # 映射键名以匹配前端 app.js 的 updateAdvicePanel 函数
    return {
        'action': action,
        'confidence': confidence,
        'analysis_logic': reasons, # 前端期望 'analysis_logic'
        'current_price': current_price,
        'entry_price': optimal_add_price or (support_level or current_price * 0.98), # 映射到 entry_price
        'target_price': resistance_level or current_price * 1.1, # 映射到 target_price
        'stop_price': support_level * 0.95 if support_level else current_price * 0.92, # 映射到 stop_price
        'resistance_level': resistance_level,
        'support_level': support_level
    }
    # --- [FIX END] ---


def get_deep_analysis(stock_code: str, df: pd.DataFrame = None) -> dict:
    """
    【统一入口函数】
    对单只股票进行深度回测分析，并生成前瞻性交易建议。
    现在包含增强版交易建议功能。
    """
    try:
        # 1. 获取和准备数据
        if df is None:
            # 使用统一的数据处理模块
            from data_handler import get_full_data_with_indicators
            df = get_full_data_with_indicators(stock_code)
            if df is None:
                return {'error': '无法获取股票数据或数据不足'}

        # 2. 执行风险评估
        risk_assessment = _assess_risk_profile(df)

        # 3. 执行历史回测，优化系数
        backtest_results = _optimize_coefficients_historically(df)
        
        # 4. 基于最新数据和回测结果，生成前瞻性建议
        forward_advice = _generate_forward_advice(df, backtest_results)

        # 5. 组装最终结果
        analysis_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return {
            'stock_code': stock_code,
            'analysis_time': analysis_time,
            'current_price': float(df.iloc[-1]['close']),
            'backtest_analysis': backtest_results,
            'trading_advice': forward_advice,
            'risk_assessment': risk_assessment,
            'from_cache': False # 默认实时计算
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': f'深度分析失败: {str(e)}'}


