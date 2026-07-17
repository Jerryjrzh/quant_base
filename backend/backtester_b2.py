#!/usr/bin/env python3
"""
【V4.1 - 深度分析中心】
此模块现在是统一的深度分析和交易建议生成中心。
完全集成 V4.0 Confluence Scorer 的所有智能分析功能。
"""
import numpy as np
import pandas as pd
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

# 导入必要的模块 (原portfolio_manager中的依赖)
import data_loader
import indicators
from adjustment_processor import create_adjustment_config, create_adjustment_processor
# --- 核心依赖：导入V4.0评分系统和形态识别器 ---
from confluence_scorer import confluence_scorer
from pattern_recognizer import pattern_recognizer
from data_handler import get_full_data_with_indicators

logger = logging.getLogger(__name__)

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

def _calculate_price_targets(df: pd.DataFrame, current_price: float, atr: float = None, trend_phase: str = 'unknown', board_limit: float = 0.10) -> dict:
    """
    【V4.3 终极融合版】结构化支撑/阻力 + 强趋势敏感过滤
    """
    try:
        # 1. 扩大视野：看 120 天的数据找真正的结构性大底/大顶
        lookback = min(150, len(df))
        recent_data = df.tail(lookback)
        
        support_levels = []
        resistance_levels = []
        
        # 2. 寻找波段极值 (Pivot Points) - 更加严格的 V 型反转点
        # 要求比前后 3 天都低/高 才算有效结构
        for i in range(5, len(recent_data) - 5):
            window_low = recent_data['low'].iloc[i-5:i+6]
            if recent_data['low'].iloc[i] == window_low.min():
                support_levels.append(recent_data['low'].iloc[i])
            
            window_high = recent_data['high'].iloc[i-5:i+6]
            if recent_data['high'].iloc[i] == window_high.max():
                resistance_levels.append(recent_data['high'].iloc[i])
        
        # 3. 引入长线均线作为宏观心理支撑/阻力
        latest = df.iloc[-1]
        for ma in ['ma60', 'ma120', 'ma250']:
            if ma in latest and pd.notna(latest[ma]) and latest[ma] > 0:
                if latest[ma] < current_price * 1.05:
                    support_levels.append(latest[ma])
                else:
                    resistance_levels.append(latest[ma])
                    
        # 去重并排序
        support_levels = sorted(list(set(support_levels)))
        resistance_levels = sorted(list(set(resistance_levels)),reverse=True)
        
        # 4. 🚀 修复点 1：彻底消灭 ATR 的绝对值兜底硬编码
        if not atr or atr <= 0:
            # 如果真没取到ATR，用板块涨跌幅的 20% 作为动态兜底 (10CM是2%, 30CM是6%)
            atr = current_price * board_limit * 0.20 
            
        # 3. 🚀 Grok 优化：使用显式字典进行趋势敏感缓冲
        # 下跌期要求支撑位必须极远(1.4倍ATR)才算有效；吸筹期要求极低(0.6倍)即可
        buffer_mult = {'decline': 1.4, 'distribution': 1.2, 'accumulation': 0.6, 'markup': 0.8}.get(trend_phase, 1.0)
        buffer_dist = atr * buffer_mult
        
        valid_supports = [s for s in support_levels if s <= current_price - buffer_dist]
        next_support = valid_supports[-1] if valid_supports else None
        
        valid_resistances = [r for r in resistance_levels if r >= current_price + (buffer_dist * 0.7)]
        next_resistance = valid_resistances[0] if valid_resistances else None
        
        return {
            'next_support': next_support,
            'next_resistance': next_resistance,
            'buffer_dist': buffer_dist
        }
    except Exception:
        import traceback; traceback.print_exc()
        return {'next_support': None, 'next_resistance': None}
    
def _calculate_price_targets_v1(df: pd.DataFrame, current_price: float, atr: float = None, trend_risk_score: float = 1.0, board_limit: float = 0.10) -> dict:
    """
    【V4.2 重构】计算动态结构性支撑与阻力位 (融入 ATR 波动率过滤)
    """
    try:
        # 1. 扩大视野：看 120 天的数据找真正的结构性大底/大顶
        lookback = min(120, len(df))
        recent_data = df.tail(lookback)
        
        support_levels = []
        resistance_levels = []
        
        # 2. 寻找波段极值 (Pivot Points) - 更加严格的 V 型反转点
        # 要求比前后 3 天都低/高 才算有效结构
        for i in range(5, len(recent_data) - 5):
            window_low = recent_data['low'].iloc[i-5:i+6]
            if recent_data['low'].iloc[i] == window_low.min():
                support_levels.append(recent_data['low'].iloc[i])
            
            window_high = recent_data['high'].iloc[i-5:i+6]
            if recent_data['high'].iloc[i] == window_high.max():
                resistance_levels.append(recent_data['high'].iloc[i])
        
        # 3. 引入长线均线作为宏观心理支撑/阻力
        latest = df.iloc[-1]
        for ma in ['ma60', 'ma120', 'ma250']:
            if ma in latest and pd.notna(latest[ma]) and latest[ma] > 0:
                if latest[ma] < current_price * 1.05:
                    support_levels.append(latest[ma])
                else:
                    resistance_levels.append(latest[ma])
                    
        # 去重并排序
        support_levels = sorted(list(set(support_levels)))
        resistance_levels = sorted(list(set(resistance_levels)),reverse=True)
        
        # 4. 🚀 修复点 1：彻底消灭 ATR 的绝对值兜底硬编码
        if not atr or atr <= 0:
            # 如果真没取到ATR，用板块涨跌幅的 20% 作为动态兜底 (10CM是2%, 30CM是6%)
            atr = current_price * board_limit * 0.20 
            
        # 5. 🚀 修复点 2：引入趋势敏感过滤 (Trend-Sensitive Filtering)
        # 趋势风险分(trend_risk_score): 吸筹期最安全(0.5)，主升浪次之(0.8)，派发期(1.5)，下跌期极危险(1.8)
        # 我们用基础 0.5 * 风险分。
        # 意味着：吸筹期只需 0.25 倍 ATR 就是有效支撑；下跌期需要 0.9 倍 ATR 才是有效支撑！
        dynamic_buffer_mult = 0.5 * trend_risk_score
        buffer_dist = atr * dynamic_buffer_mult
        
        valid_supports = [s for s in support_levels if s <= current_price - buffer_dist]
        next_support = valid_supports[-1] if valid_supports else None
        
        valid_resistances = [r for r in resistance_levels if r >= current_price + buffer_dist]
        next_resistance = valid_resistances[0] if valid_resistances else None
        
        return {
            'next_support': next_support,
            'next_resistance': next_resistance,
            'buffer_dist': buffer_dist # 暴露出去方便调试
        }
        
    except Exception as e:
        import traceback; traceback.print_exc()
        return {'next_support': None, 'next_resistance': None}
    
    
def _calculate_price_targets_v0(df: pd.DataFrame, current_price: float) -> dict:
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

def _optimize_coefficients_historically(df: pd.DataFrame, stock_code: str = "") -> dict:
    """
    通过历史数据回测，优化补仓和卖出系数。
    【已增强】增加了卖出系数的优化逻辑。
    """
    add_coefficients = [0.96, 0.97, 0.98, 0.99, 1.00]
    sell_coefficients = [1.03, 1.05, 1.08, 1.10, 1.15, 1.20] # 卖出系数
    # ==========================================
    # 1. 提取板块涨跌幅限制 (在循环外部只执行一次，极省性能)
    # ==========================================
    board_limit = 0.10
    if stock_code:
        try:
            from data_handler import get_market_volatility_profile
            market_profile = get_market_volatility_profile(stock_code)
            board_limit = market_profile.get('limit', 0.10)
        except Exception:
            pass
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
            # ==========================================
            # 2. 极速计算历史当天的截面 ATR 与 趋势分
            # ==========================================
            # 快速 ATR：如果有算好的列直接取，没有则用最近 14天的高低点均值
            if 'atr' in current_data.columns:
                hist_atr = float(current_data['atr'].iloc[-1])
            else:
                hist_atr = (current_data['high'].tail(14) - current_data['low'].tail(14)).mean()
                if pd.isna(hist_atr) or hist_atr <= 0:
                    hist_atr = hist_price * 0.03
                    
            # 快速趋势分：依托 MA60 牛熊分界线极速判定 (省略繁重的 confluence_scorer)
            hist_trend_score = 1.0
            if 'ma60' in current_data.columns:
                ma60 = current_data['ma60'].iloc[-1]
                if pd.notna(ma60) and ma60 > 0:
                    # 跌破 MA60 视为高风险(1.8)，在之上视为主升/强势区(0.8)
                    hist_trend_score = 1.8 if hist_price < ma60 else 0.8
            
            # ==========================================
            # 3. 完美装填 V4.2 引擎所需的全部参数
            # ==========================================
            price_targets = _calculate_price_targets(
                df=current_data, 
                current_price=hist_price,
                atr=hist_atr,
                trend_risk_score=hist_trend_score,
                board_limit=board_limit
            )
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
def _generate_forward_advice_v4(df: pd.DataFrame, stock_code: str) -> dict:
    """
    【V4.3 终极核心函数】基于 V4.0 Confluence Scorer 生成高质量、可解释的交易建议
    融入自适应数学网格、动态支撑/阻力过滤、多维特征标签与时间风控体系。
    """
    try:
        latest_index = len(df) - 1
        current_price = float(df.iloc[latest_index]['close'])
        
        # 1. 调用 V4.0 评分系统获取最全面的分析结果
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
        
        # 2. 调用形态识别器
        pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)

        # 3. 初始化建议
        action = 'HOLD'
        reasons = []
        confidence = confluence_result['confidence']
        quality_grade = 'D'

        # ==========================================
        # 第一阶段：基础特征提取与评分逻辑
        # ==========================================
        # 提取趋势与市场环境
        market_phase = confluence_result.get('market_phase', 'unknown')
        trend_phase = market_phase  # 统一变量名
        
        # 获取 ATR 及板块信息
        atr = confluence_result.get('phase_analysis', {}).get('atr', current_price * 0.03)
        atr_pct = atr / current_price
        
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code)
        board_limit = market_profile.get('limit', 0.10)
        board_type = market_profile.get('board_type', '10CM')
        
        is_high_vol = atr_pct > (board_limit * 0.35)

        reasons.append(f"宏观判断：当前处于 {market_phase.upper()} 阶段。")
        if market_phase in ['distribution', 'decline']:
            action = 'AVOID'
            reasons.append("风险提示：市场处于高风险或下跌阶段，建议规避。")
            confidence *= 0.7

        total_score = confluence_result.get('total_score', 0)
        if total_score >= 85:
            quality_grade = 'A'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (A级)，技术面高度共振。")
        elif total_score >= 70:
            quality_grade = 'B'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (B级)，技术面较为一致。")
        elif total_score >= 55:
            quality_grade = 'C'
            action = 'WATCH' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (C级)，建议保持观察。")
        else:
            quality_grade = 'D'
            action = 'AVOID'
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (D级)，技术指标不一致，建议规避。")

        pattern_name = pattern_result.get('best_pattern', 'None') if pattern_result.get('has_pattern') else 'None'
        if pattern_result.get('has_pattern'):
            reasons.append(f"形态分析：识别到 {pattern_name} 形态 (置信度: {pattern_result['best_confidence']:.1%})。")
            confidence = (confidence + pattern_result['best_confidence']) / 2

        alignment = confluence_result.get('alignment_analysis', {})
        if alignment.get('alignment_score', 0) > 5:
            reasons.append(f"历史对齐：价格与指标底部同步性良好 (得分: {alignment['alignment_score']})。")
        
        backtest_val = confluence_result.get('backtest_analysis', {})
        if backtest_val.get('signal_count', 0) > 0:
            reasons.append(f"历史回测：基于对齐信号的历史胜率为 {backtest_val['win_rate']:.1%} (共{backtest_val['signal_count']}次)。")

        # ==========================================
        # 第二阶段：多维特征标签构造 (供深度回测透视使用)
        # ==========================================
        # 乖离率特征 (Bias - 距离MA60的偏离程度)
        latest_ma60 = df.iloc[latest_index].get('ma60')
        if pd.isna(latest_ma60) or latest_ma60 == 0:
            bias_pct = 0.0
        else:
            bias_pct = (current_price - latest_ma60) / latest_ma60
            
        if bias_pct > 0.15:
            bias_tier = "高位极度乖离(>15%)"
        elif bias_pct > 0.05:
            bias_tier = "多头偏离(5%~15%)"
        elif bias_pct < -0.15:
            bias_tier = "深渊超跌(<-15%)"
        elif bias_pct < -0.05:
            bias_tier = "空头偏离(-15%~-5%)"
        else:
            bias_tier = "均值回归(±5%)"

        # ==========================================
        # 第三阶段：自适应网格定价与支撑阻力过滤
        # ==========================================
        # 提前计算趋势风险分，用于支撑位过滤
        trend_risk_score = {'decline': 1.85, 'distribution': 0.85, 'accumulation': 0.55, 'markup': 0.9}.get(trend_phase, 1.0)
        
        # 动态计算有效支撑位和阻力位 (调用最新的 V4.3 函数)
        price_targets = _calculate_price_targets(
            df=df, 
            current_price=current_price, 
            atr=atr, 
            trend_phase=trend_phase, 
            board_limit=board_limit
        )
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 乖离惩罚：给超跌折扣，超买加深防守。控制在物理极限内。
        #raw_bias_penalty = bias_pct * 2.5 
        #bias_penalty = max(-0.8, min(1.5, raw_bias_penalty))
        if bias_pct > 0.15:
            bias_penalty = max(-0.35, bias_pct * -1.6)
        else:
            bias_penalty = max(-0.7, bias_pct * -2.0)

        # 波动率温和惩罚
        vol_penalty = 0.20 if is_high_vol else 0.0

        # ----------- 动态入场价 (Entry) -----------
        # 核心方程：挂单深度 = 趋势风险 + 乖离惩罚 + 波动惩罚
        raw_pullback_mult = trend_risk_score + bias_penalty + vol_penalty
        pullback_multiplier = max(0.25, min(raw_pullback_mult, 2.2))

        MAX_DRAWDOWN_CAP = board_limit * 1.3 
        MAX_PROFIT_CAP = board_limit * 1.3

        max_allowed_drawdown = current_price * MAX_DRAWDOWN_CAP
        pullback = min(atr * pullback_multiplier, max_allowed_drawdown)
        dynamic_entry = current_price - pullback
        
        supp_distance = (current_price - support_level) / current_price if support_level else 1
        
        # 智能支撑位交互方程
        if support_level and supp_distance < market_profile['limit']:
            if trend_risk_score > 1.0:
                dynamic_entry = min(dynamic_entry, support_level * 0.97)
                reasons.append(f"入场建议：[自适应] 行情偏弱，任由价格击穿支撑位({support_level:.2f})吸筹，限价 ¥{dynamic_entry:.2f}。")
            else:
                dynamic_entry = max(dynamic_entry, support_level + (atr * 0.1))
                reasons.append(f"入场建议：[自适应] 行情强势，依托技术支撑位({support_level:.2f})上方拦截，限价 ¥{dynamic_entry:.2f}。")
        else:
            reasons.append(f"入场建议：[自适应] 依据趋势分({trend_risk_score:.1f})与乖离，自动计算回撤系数 {pullback_multiplier:.1f}x ATR。")

        if pullback_multiplier >= 2.8:
            action = 'AVOID'
            reasons.append("⚠️风险警示：系统测算趋势破位且乖离过大，风险收益比极差，强烈建议规避。")

        #entry_price = round(max(min(dynamic_entry, current_price * 0.99), current_price * (1 - board_limit)), 2)
                # distribution 高位乖离时略微放宽下限保护
        min_price_floor = current_price * 0.78 if (trend_phase == 'distribution' and bias_pct > 0.12) else current_price * 0.75
        entry_price = round(max(min(dynamic_entry, current_price * 0.99), min_price_floor), 2)

        volatility_ratio = atr / current_price # 动态日内波动率评估
        is_high_vol = volatility_ratio > 0.06  
        # ----------- 动态止损价 (Stop) -----------
        stop_mult = 1.2 + (volatility_ratio * 10)  
        max_stop_distance = entry_price * (board_limit * 0.8) 
        
        stop_price = round(entry_price - min(atr * stop_mult, max_stop_distance), 2)  
        if support_level and support_level < entry_price:
            stop_price = max(stop_price, round(support_level * 0.98, 2)) 

        # ----------- 动态止盈价 (Target) -----------
        base_target_mult = 2 - (trend_risk_score - 0.5) * 1.4 - (bias_penalty * 0.3)
        target_multiplier = max(1.2, base_target_mult * (0.7 if is_high_vol else 1.0))
        #base_target_mult = 3.2 - (trend_risk_score - 0.5) * 1.8 - (bias_penalty * 0.6)
        #target_multiplier = max(1.2, base_target_mult * (0.6 if is_high_vol else 1.0))
        
        target_add = min(atr * target_multiplier, entry_price * MAX_PROFIT_CAP)
        target_price = round(entry_price + target_add, 2)
        
        reasons.append(f"止盈建议：[动态弹性] 算法预期弹性系数为 {target_multiplier:.1f}x ATR，最高锁定天花板为 {MAX_PROFIT_CAP*100:.0f}%。")

        if resistance_level and entry_price < resistance_level:
             # Grok 逃顶逻辑融合
             if trend_phase == 'accumulation' and not is_high_vol and bias_pct < 0.08:
                 target_price = max(target_price, round(resistance_level * 1.015, 2))
                 reasons.append(f"风控动作：底部蓄力坚实且未超买，预期突破上行阻力({resistance_level:.2f})。")
             else:
                 target_price = min(target_price, round(resistance_level * 0.975, 2))
                 reasons.append(f"风控动作：历史大数据显示该位置阻力突破胜率极低，严格压低目标至强阻力({resistance_level:.2f})下方逃顶。")

        # ==========================================
        # 第四阶段：引入时间风控 (Time-in-Market Risk)
        # ==========================================
        if board_type == '10CM':
             reasons.append("⏳ 风控军规：[10CM A杀高危区] 历史数据显示该板块 T+1/T+2 极易诱多A杀。若 T+2 冲高未能触及止盈，必须手动下调目标价，利润回撤至 3% 时无条件强制平仓，严禁格局！")
        else:
             reasons.append("⏳ 风控军规：历史大数据表明，当前交易模型的绝对高点均在 T+2 左右出现。严格执行【T+3 时间止损法】：若持仓 3 天仍未触及止盈，无论盈亏，强制清仓释放资金！")
             
        return {
            'action': action,
            'confidence': float(confidence),
            'quality_grade': quality_grade,
            'analysis_logic': reasons,
            'current_price': current_price,
            'entry_price': entry_price,      
            'target_price': target_price,    
            'stop_price': stop_price,        
            'resistance_level': resistance_level,
            'support_level': support_level,
            'feature_trend': trend_phase,
            'feature_pattern': pattern_name,
            'feature_bias_val': round(bias_pct, 4),
            'feature_bias_tier': bias_tier,
            'full_confluence_result': confluence_result,
            'time_stop_days': 3, 
            'trailing_stop_trigger': 0.05, 
        }
    except Exception as e:
        logger.error(f"V4.3交易建议生成失败: {e}")
        import traceback; traceback.print_exc()
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}
    
def _generate_forward_advice_v4_b5(df: pd.DataFrame, stock_code: str) -> dict:
    """
    【V4.1 核心函数】基于 V4.0 Confluence Scorer 生成高质量、可解释的交易建议（已修复参数传递）
    """
    try:
        latest_index = len(df) - 1
        current_price = float(df.iloc[latest_index]['close'])
        
        # 1. 调用 V4.0 评分系统获取最全面的分析结果
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
        
        # 2. 调用形态识别器
        pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)

        # 3. 初始化建议
        action = 'HOLD'
        reasons = []
        confidence = confluence_result['confidence']
        quality_grade = 'D'

        # 4. 构建层次化的决策逻辑
        market_phase = confluence_result.get('market_phase', 'unknown')
        reasons.append(f"宏观判断：当前处于 {market_phase.upper()} 阶段。")
        if market_phase in ['distribution', 'decline']:
            action = 'AVOID'
            reasons.append("风险提示：市场处于高风险或下跌阶段，建议规避。")
            confidence *= 0.7

        total_score = confluence_result.get('total_score', 0)
        if total_score >= 85:
            quality_grade = 'A'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (A级)，技术面高度共振。")
        elif total_score >= 70:
            quality_grade = 'B'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (B级)，技术面较为一致。")
        elif total_score >= 55:
            quality_grade = 'C'
            action = 'WATCH' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (C级)，建议保持观察。")
        else:
            quality_grade = 'D'
            action = 'AVOID'
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (D级)，技术指标不一致，建议规避。")

        if pattern_result.get('has_pattern'):
            reasons.append(f"形态分析：识别到 {pattern_result['best_pattern']} 形态 (置信度: {pattern_result['best_confidence']:.1%})。")
            confidence = (confidence + pattern_result['best_confidence']) / 2

        alignment = confluence_result.get('alignment_analysis', {})
        if alignment.get('alignment_score', 0) > 5:
            reasons.append(f"历史对齐：价格与指标底部同步性良好 (得分: {alignment['alignment_score']})。")
        
        backtest_val = confluence_result.get('backtest_analysis', {})
        if backtest_val.get('signal_count', 0) > 0:
            reasons.append(f"历史回测：基于对齐信号的历史胜率为 {backtest_val['win_rate']:.1%} (共{backtest_val['signal_count']}次)。")

        # 5. 计算支撑位和阻力位
        price_targets = _calculate_price_targets(df, current_price)
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 🚀 引入市场波动画像 (完美接入传入的 stock_code)
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code)
        board_type = market_profile['board_type']
        atr_adj = market_profile['atr_entry_mult']
        # ==========================================
        # 🏷️ 核心新增：提取“位置决定性质”的多维特征标签
        # ==========================================
        # 1. 趋势特征 (Trend)
        trend_phase = confluence_result.get('market_phase', 'unknown')
        
        # 2. 形态特征 (Pattern)
        pattern_name = pattern_result.get('best_pattern', 'None') if pattern_result.get('has_pattern') else 'None'
        
        # 3. 乖离率特征 (Bias - 距离MA60的偏离程度)
        latest_ma60 = df.iloc[latest_index].get('ma60')
        if pd.isna(latest_ma60) or latest_ma60 == 0:
            bias_pct = 0.0
        else:
            bias_pct = (current_price - latest_ma60) / latest_ma60
            
        # 乖离率离散化（方便后续分组统计）
        if bias_pct > 0.15:
            bias_tier = "高位极度乖离(>15%)"
        elif bias_pct > 0.05:
            bias_tier = "多头偏离(5%~15%)"
        elif bias_pct < -0.15:
            bias_tier = "深渊超跌(<-15%)"
        elif bias_pct < -0.05:
            bias_tier = "空头偏离(-15%~-5%)"
        else:
            bias_tier = "均值回归(±5%)"
        # 6. 获取基础 ATR 和 计算高波因子
        atr = confluence_result.get('phase_analysis', {}).get('atr', current_price * 0.03)
        volatility_ratio = atr / current_price # 动态日内波动率评估
        is_high_vol = volatility_ratio > 0.06  
        
        # ==========================================
        # 🚀 进化：引入【最大偏离封顶(Cap)】的自适应网格
        # ==========================================
        
        # ----------- 动态入场价 (Entry) -----------
        if board_type == '10CM':
            if bias_pct < -0.15 and trend_phase == 'accumulation':
                pullback = atr * 0.5
                reasons.append("入场建议：[10CM 黄金坑] 深渊超跌，小幅回撤极速上车。")
            elif is_high_vol and trend_phase in ['distribution', 'decline']:
                # 限制最大回撤深度，防止挂单深到离谱（不超过现价的8%）
                pullback = min(atr * 2.0, current_price * 0.08)
                reasons.append("入场建议：[10CM 高波防守] 波动极大，启用封顶防守深度挂单。")
            else:
                pullback = atr * (0.8 if action == 'BUY' else 1.2)
                reasons.append("入场建议：[10CM 常规] 基于均值回归逻辑寻找稳定买点。")
                
        elif board_type == '30CM':
            if trend_phase == 'accumulation' or bias_tier == '均值回归(±5%)':
                pullback = atr * 0.3 
                reasons.append("入场建议：[30CM 底部洗盘] 支撑极强，缩小挂单深度防止踏空。")
            elif trend_phase in ['distribution', 'markup']:
                action = 'AVOID'
                pullback = atr * 3.0
                reasons.append("⚠️风险警示：[30CM 高位崩塌区] 胜率极低，强烈建议规避。")
            else:
                # 修复30CM踏空：最大回撤深度硬性封顶于 12%
                pullback = min(atr * 1.5, current_price * 0.12)
                reasons.append("入场建议：[30CM 冰点区] 限制最大防守深度，防止脱离实际行情。")
                
        else: # 20CM
            if trend_phase == 'decline':
                pullback = atr * 0.5
                reasons.append("入场建议：[20CM 超跌反弹] 缩小接针深度。")
            elif is_high_vol and bias_pct > 0.05:
                pullback = min(atr * 1.5, current_price * 0.10)
                reasons.append("入场建议：[20CM 高波震荡] 乖离过高，限价深调。")
            else:
                pullback = atr * 0.8
                reasons.append("入场建议：[20CM 稳健区] 依托 ATR 构建常规安全垫。")
       # ----------- 绝对空间封顶 (Cap) 配置 -----------
        MAX_PROFIT_CAP = {'10CM': 0.24, '20CM': 0.28, '30CM': 0.45}.get(board_type, 0.25)
        MAX_DRAWDOWN_CAP = {'10CM': 0.18, '20CM': 0.18, '30CM': 0.22}.get(board_type, 0.18)
        
        # 1. 基础深度护栏
        max_allowed_drawdown = current_price * MAX_DRAWDOWN_CAP
        pullback = min(pullback, max_allowed_drawdown)
        
        # 2. 计算初步买点
        dynamic_entry = current_price - pullback
        supp_distance = (current_price - support_level) / current_price if support_level else 1
        
        # 3. 支撑位防穿透与抢跑重构
        if support_level and supp_distance < market_profile['limit']:
            # 防穿透：无论 ATR 算出多深的跌幅，最多只允许跌穿支撑位 2%
            support_floor = support_level * 0.98
            dynamic_entry = max(dynamic_entry, support_floor)
            
            # 抢跑：如果初步买点已经掉进了支撑位附近的“引力区”，则在支撑位上方 0.1 ATR 处抢跑拦截
            if dynamic_entry < support_level + (atr * 0.3):
                dynamic_entry = max(dynamic_entry, support_level + (atr * 0.1))

        # 4. 跌停板托底与现价防呆
        entry_price = round(max(min(dynamic_entry, current_price * 0.99), current_price * 0.7), 2) 

        # ----------- 动态止损价 (Stop) -----------
        stop_multiplier = {'10CM': 1.2, '20CM': 1.5, '30CM': 2.0}.get(board_type, 1.5) if is_high_vol else {'10CM': 1.5, '20CM': 1.8, '30CM': 2.5}.get(board_type, 1.5)
        
        # 绝对止损护栏：单笔最大止损不得超过 15%
        max_stop_loss_distance = entry_price * 0.15
        stop_price = round(entry_price - min(atr * stop_multiplier, max_stop_loss_distance), 2)  
        
        if support_level and support_level < entry_price:
            tech_stop = round(support_level * (1 - market_profile['sr_tolerance']), 2)
            stop_price = max(stop_price, tech_stop) 

        # ----------- 动态止盈价 (Target) -----------
        if board_type == '10CM':
            if is_high_vol:
                target_add = atr * 1.5 
                reasons.append("止盈建议：[10CM 高波快打] ATR臃肿，强行降速，微利即走。")
            elif bias_pct < -0.15 or bias_pct > 0.05:
                target_add = atr * 4.0 
                reasons.append("止盈建议：[10CM 稳态主升] 目标放大至波段高点。")
            else:
                target_add = atr * 2.5
                
        elif board_type == '30CM':
            if trend_phase == 'accumulation':
                target_add = atr * 3.5 
                reasons.append("止盈建议：[30CM 底部起爆] 配合高胜率底仓锁定波段。")
            else:
                target_add = atr * 1.2 
                reasons.append("止盈建议：[30CM 快进快出] 弱势区微利即走。")
                
        else: # 20CM
            if is_high_vol:
                target_add = atr * 2.0
                reasons.append("止盈建议：[20CM 高波短打] 剧烈震荡目标收敛。")
            elif bias_pct > 0.15 and trend_phase in ['distribution', 'markup']:
                target_add = atr * 3.5 
                reasons.append("止盈建议：[20CM 龙头首阴] 高位反抽强劲。")
            else:
                target_add = atr * 2.5

        # 应用绝对天花板：防止高波股出现不可能达到的预期
        final_target_add = min(target_add, entry_price * MAX_PROFIT_CAP)
        target_price = round(entry_price + final_target_add, 2)
        
        if resistance_level and entry_price < resistance_level:
             if "稳态主升" in reasons[-1] or "底部起爆" in reasons[-1]:
                 pass
             else:
                 target_price = min(target_price, round(resistance_level * 0.98, 2))
        # ----------- 引入时间风控 (Time-in-Market Risk) -----------
        if board_type == '10CM':
             reasons.append("⏳ 风控军规：[10CM A杀高危区] 历史数据显示该板块 T+1/T+2 极易诱多A杀。若 T+2 冲高未能触及止盈，必须手动下调目标价，利润回撤至 3% 时无条件强制平仓，严禁格局！")
        else:
             reasons.append("⏳ 风控军规：历史大数据表明，当前交易模型的绝对高点均在 T+2 左右出现。严格执行【T+3 时间止损法】：若持仓 3 天仍未触及止盈，无论盈亏，强制清仓释放资金！")

        return {
            'action': action,
            'confidence': float(confidence),
            'quality_grade': quality_grade,
            'analysis_logic': reasons,
            'current_price': current_price,
            'entry_price': entry_price,      
            'target_price': target_price,    
            'stop_price': stop_price,        
            'resistance_level': resistance_level,
            'support_level': support_level,
            'feature_trend': trend_phase,
            'feature_pattern': pattern_name,
            'feature_bias_val': round(bias_pct, 4),
            'feature_bias_tier': bias_tier,
            'full_confluence_result': confluence_result ,
            'time_stop_days': 3, # 强制时间止损：3个交易日
            'trailing_stop_trigger': 0.05, # 利润回撤触发线：涨幅超5%后开启保护
        }
    except Exception as e:
        logger.error(f"V4.1交易建议生成失败: {e}")
        import traceback; traceback.print_exc()
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}
    
def _generate_forward_advice_v4_b4(df: pd.DataFrame, stock_code: str) -> dict:
    """
    【V4.1 核心函数】基于 V4.0 Confluence Scorer 生成高质量、可解释的交易建议（已修复参数传递）
    """
    try:
        latest_index = len(df) - 1
        current_price = float(df.iloc[latest_index]['close'])
        
        # 1. 调用 V4.0 评分系统获取最全面的分析结果
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
        
        # 2. 调用形态识别器
        pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)

        # 3. 初始化建议
        action = 'HOLD'
        reasons = []
        confidence = confluence_result['confidence']
        quality_grade = 'D'

        # 4. 构建层次化的决策逻辑
        market_phase = confluence_result.get('market_phase', 'unknown')
        reasons.append(f"宏观判断：当前处于 {market_phase.upper()} 阶段。")
        if market_phase in ['distribution', 'decline']:
            action = 'AVOID'
            reasons.append("风险提示：市场处于高风险或下跌阶段，建议规避。")
            confidence *= 0.7

        total_score = confluence_result.get('total_score', 0)
        if total_score >= 85:
            quality_grade = 'A'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (A级)，技术面高度共振。")
        elif total_score >= 70:
            quality_grade = 'B'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (B级)，技术面较为一致。")
        elif total_score >= 55:
            quality_grade = 'C'
            action = 'WATCH' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (C级)，建议保持观察。")
        else:
            quality_grade = 'D'
            action = 'AVOID'
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (D级)，技术指标不一致，建议规避。")

        if pattern_result.get('has_pattern'):
            reasons.append(f"形态分析：识别到 {pattern_result['best_pattern']} 形态 (置信度: {pattern_result['best_confidence']:.1%})。")
            confidence = (confidence + pattern_result['best_confidence']) / 2

        alignment = confluence_result.get('alignment_analysis', {})
        if alignment.get('alignment_score', 0) > 5:
            reasons.append(f"历史对齐：价格与指标底部同步性良好 (得分: {alignment['alignment_score']})。")
        
        backtest_val = confluence_result.get('backtest_analysis', {})
        if backtest_val.get('signal_count', 0) > 0:
            reasons.append(f"历史回测：基于对齐信号的历史胜率为 {backtest_val['win_rate']:.1%} (共{backtest_val['signal_count']}次)。")

        # 5. 计算支撑位和阻力位
        price_targets = _calculate_price_targets(df, current_price)
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 🚀 引入市场波动画像 (完美接入传入的 stock_code)
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code)
        board_type = market_profile['board_type']
        atr_adj = market_profile['atr_entry_mult']
        # ==========================================
        # 🏷️ 核心新增：提取“位置决定性质”的多维特征标签
        # ==========================================
        # 1. 趋势特征 (Trend)
        trend_phase = confluence_result.get('market_phase', 'unknown')
        
        # 2. 形态特征 (Pattern)
        pattern_name = pattern_result.get('best_pattern', 'None') if pattern_result.get('has_pattern') else 'None'
        
        # 3. 乖离率特征 (Bias - 距离MA60的偏离程度)
        latest_ma60 = df.iloc[latest_index].get('ma60')
        if pd.isna(latest_ma60) or latest_ma60 == 0:
            bias_pct = 0.0
        else:
            bias_pct = (current_price - latest_ma60) / latest_ma60
            
        # 乖离率离散化（方便后续分组统计）
        if bias_pct > 0.15:
            bias_tier = "高位极度乖离(>15%)"
        elif bias_pct > 0.05:
            bias_tier = "多头偏离(5%~15%)"
        elif bias_pct < -0.15:
            bias_tier = "深渊超跌(<-15%)"
        elif bias_pct < -0.05:
            bias_tier = "空头偏离(-15%~-5%)"
        else:
            bias_tier = "均值回归(±5%)"
        # 6. 获取基础 ATR
        atr = confluence_result.get('phase_analysis', {}).get('atr', current_price * 0.03)
        supp_distance = (current_price - support_level) / current_price if support_level else 1

        # ==========================================
        # 🚀 终极进化：基于多维特征 (板块+趋势+乖离) 的精准自适应挂单系统
        # ==========================================
        
        # ----------- 动态入场价 (Entry) -----------
        if board_type == '10CM':
            if bias_pct < -0.15 and trend_phase == 'accumulation':
                # [黄金坑] 买点极准，坚决不上浮也不深潜，保持现状
                pullback_multiplier = 0.5
                reasons.append("入场建议：[10CM 黄金坑] 深渊超跌且处于吸筹区，按现价小幅回撤极速上车。")
            elif trend_phase == 'decline':
                # [下跌期修复] 之前偏离 -3.07% 导致严重踏空，将买点拉高
                pullback_multiplier = 0.4 if action == 'BUY' else 0.8
                reasons.append("入场建议：[10CM 弱势抵抗] 下跌趋势中不宜过度深挂，防止踏空有效反弹。")
            else:
                # 常规趋势，适度防守
                pullback_multiplier = 0.8 if action == 'BUY' else 1.2
                reasons.append("入场建议：[10CM 常规] 基于均值回归逻辑，在现价下方寻找稳定买点。")
                
        elif board_type == '30CM':
            if bias_pct > 0.15:
                # [高位狂飙] 之前偏离 -2.77% 踏空，拉高买点
                pullback_multiplier = 0.2
                reasons.append("入场建议：[30CM 极度狂热] 强势动能股，极浅回撤挂单，拥抱高波动。")
            else:
                # [低位死水] 维持深挂防守
                pullback_multiplier = 1.8
                reasons.append("入场建议：[30CM 冰点区] 动能匮乏，必须在极深处限价伏击。")
                
        else: # 20CM
            if trend_phase == 'decline':
                # [下跌期修复] 之前偏离 -5.57% 严重踏空
                pullback_multiplier = 0.5
                reasons.append("入场建议：[20CM 超跌反弹] 缩小接针深度，捕捉日内急跌反抽。")
            elif bias_pct > 0.15:
                # 高位回撤
                pullback_multiplier = 1.0
                reasons.append("入场建议：[20CM 高位震荡] 乖离过高，耐心等待一倍 ATR 的健康回调。")
            else:
                pullback_multiplier = 0.8
                reasons.append("入场建议：[20CM 稳健区] 依托 ATR 构建常规安全垫。")

        # 结合支撑位与动态计算的买点
        dynamic_entry = current_price - (atr * pullback_multiplier)
        # 无论哪个板块，如果有很近的技术支撑位，优先尊重支撑位托底
        if support_level and supp_distance < market_profile['limit']:
             dynamic_entry = min(dynamic_entry, support_level + (atr * 0.1))

        entry_price = round(min(dynamic_entry, current_price * 0.99), 2)

        # ----------- 动态止损价 (Stop) -----------
        stop_multiplier_map = {'10CM': 1.5, '20CM': 1.8, '30CM': 2.5} # 结合位置适当放宽止损
        stop_price = round(entry_price - atr * stop_multiplier_map.get(board_type, 1.5), 2)  
        if support_level and support_level < entry_price:
            tech_stop = round(support_level * (1 - market_profile['sr_tolerance']), 2)
            stop_price = max(stop_price, tech_stop) 

        # ----------- 动态止盈价 (Target) -----------
        
        if board_type == '10CM':
            # 全面纠错：10CM 此前止盈触及率极高但溢出过大（+7.92%）
            if bias_pct < -0.15 or bias_pct > 0.05:
                target_multiplier = 4.5 # 黄金坑或主升浪，让利润狂奔
                reasons.append(f"止盈建议：[10CM 极值动能] 统计胜率极高区域，无视小阻力，目标极度放大至 {round(entry_price + atr * target_multiplier, 2)}。")
            else:
                target_multiplier = 3.5 # 恢复到较高水平
                reasons.append("止盈建议：[10CM 稳健波段] 顺势而为，目标定于合理波段高点。")
                
        elif board_type == '30CM':
            if bias_pct > 0.15 or trend_phase == 'markup':
                target_multiplier = 6.0 # 之前高位卖飞 +9.23%，直接暴力上调
                reasons.append(f"止盈建议：[30CM 龙妖模式] 绝对主升浪特征，拥抱泡沫，看高一线至 {round(entry_price + atr * target_multiplier, 2)}。")
            else:
                target_multiplier = 1.5 # 之前低位止盈极其惨烈(-10.53%)，断崖式下调
                reasons.append("止盈建议：[30CM 冰点模式] 弱势无主升，微利即走，坚决执行日内超短套利。")
                
        else: # 20CM
            if bias_pct > 0.15 and trend_phase in ['distribution', 'markup']:
                target_multiplier = 4.5 # 派发期龙头首阴，反弹极强，之前卖飞 +6.5%
                reasons.append(f"止盈建议：[20CM 龙头首阴] 高位宽幅震荡反抽强劲，上调利润预期至 {round(entry_price + atr * target_multiplier, 2)}。")
            elif bias_pct < -0.15 and trend_phase == 'accumulation':
                target_multiplier = 3.0 # 此处之前偏离 +0.73%，完美卡位，维持不动
                reasons.append("止盈建议：[20CM 底部吸筹] 完美卡位历史数据测算极值。")
            else:
                target_multiplier = 3.5 
                reasons.append("止盈建议：[20CM 常规波段] 锁定正常 ATR 震荡空间。")

        target_price = round(entry_price + atr * target_multiplier, 2)
        
        # 阻力位压制逻辑（最后防线）
        if resistance_level and entry_price < resistance_level:
             # 如果模型认定此时是"让利润狂奔"的极值动能区，则忽略阻力位
             if "极值动能" in reasons[-1] or "龙妖模式" in reasons[-1]:
                 pass
             else:
                 # 否则，尊重阻力位，但允许略微突破 (0.99 改为 1.01，吃掉一部分溢出利润)
                 target_price = min(target_price, round(resistance_level * 1.01, 2))

        return {
            'action': action,
            'confidence': float(confidence),
            'quality_grade': quality_grade,
            'analysis_logic': reasons,
            'current_price': current_price,
            'entry_price': entry_price,      
            'target_price': target_price,    
            'stop_price': stop_price,        
            'resistance_level': resistance_level,
            'support_level': support_level,
            'feature_trend': trend_phase,
            'feature_pattern': pattern_name,
            'feature_bias_val': round(bias_pct, 4),
            'feature_bias_tier': bias_tier,
            'full_confluence_result': confluence_result 
        }
    except Exception as e:
        logger.error(f"V4.1交易建议生成失败: {e}")
        import traceback; traceback.print_exc()
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}
    
def _generate_forward_advice_v4_b3(df: pd.DataFrame, stock_code: str) -> dict:
    """
    【V4.1 核心函数】基于 V4.0 Confluence Scorer 生成高质量、可解释的交易建议（已修复参数传递）
    """
    try:
        latest_index = len(df) - 1
        current_price = float(df.iloc[latest_index]['close'])
        
        # 1. 调用 V4.0 评分系统获取最全面的分析结果
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
        
        # 2. 调用形态识别器
        pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)

        # 3. 初始化建议
        action = 'HOLD'
        reasons = []
        confidence = confluence_result['confidence']
        quality_grade = 'D'

        # 4. 构建层次化的决策逻辑
        market_phase = confluence_result.get('market_phase', 'unknown')
        reasons.append(f"宏观判断：当前处于 {market_phase.upper()} 阶段。")
        if market_phase in ['distribution', 'decline']:
            action = 'AVOID'
            reasons.append("风险提示：市场处于高风险或下跌阶段，建议规避。")
            confidence *= 0.7

        total_score = confluence_result.get('total_score', 0)
        if total_score >= 85:
            quality_grade = 'A'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (A级)，技术面高度共振。")
        elif total_score >= 70:
            quality_grade = 'B'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (B级)，技术面较为一致。")
        elif total_score >= 55:
            quality_grade = 'C'
            action = 'WATCH' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (C级)，建议保持观察。")
        else:
            quality_grade = 'D'
            action = 'AVOID'
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (D级)，技术指标不一致，建议规避。")

        if pattern_result.get('has_pattern'):
            reasons.append(f"形态分析：识别到 {pattern_result['best_pattern']} 形态 (置信度: {pattern_result['best_confidence']:.1%})。")
            confidence = (confidence + pattern_result['best_confidence']) / 2

        alignment = confluence_result.get('alignment_analysis', {})
        if alignment.get('alignment_score', 0) > 5:
            reasons.append(f"历史对齐：价格与指标底部同步性良好 (得分: {alignment['alignment_score']})。")
        
        backtest_val = confluence_result.get('backtest_analysis', {})
        if backtest_val.get('signal_count', 0) > 0:
            reasons.append(f"历史回测：基于对齐信号的历史胜率为 {backtest_val['win_rate']:.1%} (共{backtest_val['signal_count']}次)。")

        # 5. 计算支撑位和阻力位
        price_targets = _calculate_price_targets(df, current_price)
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 🚀 引入市场波动画像 (完美接入传入的 stock_code)
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code)
        board_type = market_profile['board_type']
        atr_adj = market_profile['atr_entry_mult']
        
        # 6. 获取ATR波动率
        atr = confluence_result.get('phase_analysis', {}).get('atr', current_price * 0.03)
        
        # 获取市场特征画像
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code)
        board_type = market_profile['board_type']

        # ==========================================
        # 🚀 基于全量8万条回测数据的降维打击：板块个性化参数校准
        # ==========================================
        
        supp_distance = (current_price - support_level) / current_price if support_level else 1
        
        # ----------- 动态入场价 (Entry) -----------
        # 诊断报告：10CM买入太容易(偏离+5.77%)需要加深防守；30CM买点极准(偏离+0.33%)保持不动
        
        if board_type == '10CM':
            # 10CM重构：极度防守。强行剥离当前价格虚高，基于ATR加深回调预期。
            pullback_multiplier = 1.4 if action == 'BUY' else 1.6 # 大幅增加回撤倍数1.2 -> 1.4 1.8 -> 1.6
            dynamic_entry = current_price - (atr * pullback_multiplier)
            
            # 即便有支撑位，也不抢跑，甚至要在支撑位下方要折扣（因为10CM假跌破太多）
            if support_level and supp_distance < 0.05:
                dynamic_entry = min(dynamic_entry, support_level * 0.99)
            reasons.append(f"入场建议：[10CM弱势重构] 防御为主，在现价下方深潜 {abs(current_price - dynamic_entry):.2f} 元挂单，宁可错过绝不追高。")
            
        elif board_type == '30CM':
            # 30CM重构：保持当前的神级命中率参数
            if support_level and supp_distance < market_profile['limit']:
                dynamic_entry = support_level + (atr * 0.2)
                reasons.append(f"入场建议：[30CM高波市] 支撑极强，依托技术支撑 {support_level:.2f} 附近限价伏击。")
            else:
                dynamic_entry = current_price - (atr * 1.5)
                reasons.append("入场建议：[30CM高波市] 等待日内大波幅回调再介入。")
                
        else: # 20CM
            # 20CM重构：适度防守，抵消 3.75% 的买入安全垫虚高
            pullback_multiplier = 0.8 if action == 'BUY' else 1.5
            dynamic_entry = current_price - (atr * pullback_multiplier)
            
            if support_level and supp_distance < market_profile['limit']:
                 # 不再在支撑位上方抢跑，直接贴紧支撑位
                 dynamic_entry = min(dynamic_entry, support_level)
            reasons.append(f"入场建议：[20CM震荡市] 贴紧支撑位或按近期波动率在下方 {abs(current_price - dynamic_entry):.2f} 元处耐心等候。")

        # 确保入场价不高于现价下方一点，防止下错单
        entry_price = round(min(dynamic_entry, current_price * 0.99), 2)

        # ----------- 动态止损价 (Stop) -----------
        # 既然10CM和20CM都买得深了，止损的ATR倍数可以稍微收窄，盈亏比就上来了 30cm 2.0 -> 1.9
        stop_multiplier_map = {'10CM': 1.2, '20CM': 1.5, '30CM': 1.9}
        stop_multiplier = stop_multiplier_map.get(board_type, 1.5)
        stop_price = round(entry_price - atr * stop_multiplier, 2)  
        
        # 托底止损（给技术派留个颜面）
        if support_level and support_level < entry_price:
            tech_stop = round(support_level * (1 - market_profile['sr_tolerance']), 2)
            stop_price = max(stop_price, tech_stop) 

        # ----------- 动态止盈价 (Target) -----------
        # 诊断报告：10CM/20CM 止盈目标严重挂高（偏离极值 -12.85% / -8.45%），导致触及率低下
        
        if board_type == '10CM':
            # 10CM重构：放弃格局，降维打击。基础目标从 4xATR 直降为 2xATR。
            target_price = round(entry_price + atr * 2.5, 2)
            if resistance_level and entry_price < resistance_level:
                # 碰到阻力位，直接提前 1.5% 跑路，绝对不赌突破
                target_price = min(target_price, round(resistance_level * 0.985, 2))
                reasons.append(f"止盈建议：[10CM弱势重构] 放弃幻想，在阻力位 {resistance_level:.2f} 下方提前减仓锁利 ({target_price:.2f})。")
            else:
                reasons.append(f"止盈建议：[10CM弱势重构] 执行短波段快进快出，目标价位 {target_price:.2f}。")
                
        elif board_type == '20CM':
            # 20CM重构：目标收敛。基础目标从 4xATR 降为 3xATR。
            target_price = round(entry_price + atr * 3.0, 2)
            if resistance_level and entry_price < resistance_level:
                target_price = min(target_price, round(resistance_level * 0.99, 2))
                reasons.append(f"止盈建议：[20CM震荡市] 目标收敛，在阻力位 {resistance_level:.2f} 附近落袋为安 ({target_price:.2f})。")
            else:
                reasons.append(f"止盈建议：[20CM震荡市] 按收敛的波动率预期，目标设为 {target_price:.2f}。")
                
        else: # 30CM
            # 30CM重构：保持原有高压迫感逻辑，目标依然锚定 4xATR
            target_price = round(entry_price + atr * 4.0, 2)
            if resistance_level and entry_price < resistance_level:
                # 30CM 阻力极其有效，一定要在阻力前下车
                target_price = min(target_price, round(resistance_level - atr * 0.5, 2))
                reasons.append(f"止盈建议：[30CM高波市] 阻力压制强劲，于 {target_price:.2f} 提前止盈。")
            else:
                reasons.append(f"止盈建议：[30CM高波市] 维持高波动预期目标 {target_price:.2f}。")

        # ==========================================
        # 🏷️ 核心新增：提取“位置决定性质”的多维特征标签
        # ==========================================
        # 1. 趋势特征 (Trend)
        trend_phase = confluence_result.get('market_phase', 'unknown')
        
        # 2. 形态特征 (Pattern)
        pattern_name = pattern_result.get('best_pattern', 'None') if pattern_result.get('has_pattern') else 'None'
        
        # 3. 乖离率特征 (Bias - 距离MA60的偏离程度)
        latest_ma60 = df.iloc[latest_index].get('ma60')
        if pd.isna(latest_ma60) or latest_ma60 == 0:
            bias_pct = 0.0
        else:
            bias_pct = (current_price - latest_ma60) / latest_ma60
            
        # 乖离率离散化（方便后续分组统计）
        if bias_pct > 0.15:
            bias_tier = "高位极度乖离(>15%)"
        elif bias_pct > 0.05:
            bias_tier = "多头偏离(5%~15%)"
        elif bias_pct < -0.15:
            bias_tier = "深渊超跌(<-15%)"
        elif bias_pct < -0.05:
            bias_tier = "空头偏离(-15%~-5%)"
        else:
            bias_tier = "均值回归(±5%)"

        return {
            'action': action,
            'confidence': float(confidence),
            'quality_grade': quality_grade,
            'analysis_logic': reasons,
            'current_price': current_price,
            'entry_price': entry_price,      
            'target_price': target_price,    
            'stop_price': stop_price,        
            'resistance_level': resistance_level,
            'support_level': support_level,
            # 👇 新增输出的特征矩阵
            'feature_trend': trend_phase,
            'feature_pattern': pattern_name,
            'feature_bias_val': round(bias_pct, 4),
            'feature_bias_tier': bias_tier,
            'full_confluence_result': confluence_result 
        }
    except Exception as e:
        logger.error(f"V4.1交易建议生成失败: {e}")
        import traceback; traceback.print_exc()
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}
    
def _generate_forward_advice_v4_b2(df: pd.DataFrame, stock_code: str) -> dict:
    """
    【V4.1 核心函数】基于 V4.0 Confluence Scorer 生成高质量、可解释的交易建议（已修复参数传递）
    """
    try:
        latest_index = len(df) - 1
        current_price = float(df.iloc[latest_index]['close'])
        
        # 1. 调用 V4.0 评分系统获取最全面的分析结果
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
        
        # 2. 调用形态识别器
        pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)

        # 3. 初始化建议
        action = 'HOLD'
        reasons = []
        confidence = confluence_result['confidence']
        quality_grade = 'D'

        # 4. 构建层次化的决策逻辑
        market_phase = confluence_result.get('market_phase', 'unknown')
        reasons.append(f"宏观判断：当前处于 {market_phase.upper()} 阶段。")
        if market_phase in ['distribution', 'decline']:
            action = 'AVOID'
            reasons.append("风险提示：市场处于高风险或下跌阶段，建议规避。")
            confidence *= 0.7

        total_score = confluence_result.get('total_score', 0)
        if total_score >= 85:
            quality_grade = 'A'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (A级)，技术面高度共振。")
        elif total_score >= 70:
            quality_grade = 'B'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (B级)，技术面较为一致。")
        elif total_score >= 55:
            quality_grade = 'C'
            action = 'WATCH' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (C级)，建议保持观察。")
        else:
            quality_grade = 'D'
            action = 'AVOID'
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (D级)，技术指标不一致，建议规避。")

        if pattern_result.get('has_pattern'):
            reasons.append(f"形态分析：识别到 {pattern_result['best_pattern']} 形态 (置信度: {pattern_result['best_confidence']:.1%})。")
            confidence = (confidence + pattern_result['best_confidence']) / 2

        alignment = confluence_result.get('alignment_analysis', {})
        if alignment.get('alignment_score', 0) > 5:
            reasons.append(f"历史对齐：价格与指标底部同步性良好 (得分: {alignment['alignment_score']})。")
        
        backtest_val = confluence_result.get('backtest_analysis', {})
        if backtest_val.get('signal_count', 0) > 0:
            reasons.append(f"历史回测：基于对齐信号的历史胜率为 {backtest_val['win_rate']:.1%} (共{backtest_val['signal_count']}次)。")

        # 5. 计算支撑位和阻力位
        price_targets = _calculate_price_targets(df, current_price)
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 🚀 引入市场波动画像 (完美接入传入的 stock_code)
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code)
        board_type = market_profile['board_type']
        atr_adj = market_profile['atr_entry_mult']
        
        # 6. 获取ATR波动率
        atr = confluence_result.get('phase_analysis', {}).get('atr', current_price * 0.03)

        # ==========================================
        # 🚀 终极版：基于全量回测数据的自适应交易策略
        # ==========================================
        supp_distance = (current_price - support_level) / current_price if support_level else 1
        
        # ----------- 动态入场价 (Entry) -----------
        if board_type == '10CM':
            # 10CM特征：支撑极易跌破(62.8%)，尽量少在支撑位接飞刀，多用波动率回调
            if support_level and supp_distance < 0.08: # 距离极近才参考
                dynamic_entry = support_level - (atr * 0.5) # 甚至要在支撑位下方去接（防止假跌破洗盘）
                reasons.append("入场建议：[10CM趋势市] 支撑易破，建议在支撑位下方极限位埋伏，或等确认企稳。")
            else:
                dynamic_entry = current_price - (atr * (0.5 if action == 'BUY' else 1.0))
                reasons.append(f"入场建议：[10CM趋势市] 基于波动率，建议现价下方约 {abs(current_price - dynamic_entry):.2f} 元挂单。")
                
        elif board_type == '30CM':
            # 30CM特征：支撑极其有效(73.5%)，深跌就是机会，果断在支撑位上方抢跑
            if support_level and supp_distance < market_profile['limit']:
                dynamic_entry = support_level + (atr * 0.2)
                reasons.append(f"入场建议：[30CM边界市] 支撑极强，果断在支撑位 {support_level:.2f} 上方抢跑买入。")
            else:
                dynamic_entry = current_price - (atr * 1.5) # 没有支撑就挂深一点
                reasons.append("入场建议：[30CM高波市] 暂无支撑，挂深单等待日内大波幅回调。")
                
        else: # 20CM
            # 20CM特征：标准震荡，支撑有59%的防守力
            if support_level and supp_distance < market_profile['limit']:
                dynamic_entry = support_level + (atr * 0.1)
                reasons.append(f"入场建议：[20CM震荡市] 依托技术支撑 {support_level:.2f} 附近限价买入。")
            else:
                dynamic_entry = current_price - (atr * (0.6 if action == 'BUY' else 1.2))
                reasons.append("入场建议：[20CM震荡市] 基于 ATR 在现价下方寻找买点。")

        # 确保入场价不高于现价
        entry_price = round(min(dynamic_entry, current_price * 0.995), 2)

        # ----------- 动态止损价 (Stop) -----------
        stop_multiplier = 1.5 * atr_adj
        stop_price = round(entry_price - atr * stop_multiplier, 2)  
        
        # 10CM不迷信技术止损，20CM/30CM严格执行技术止损
        if board_type in ['20CM', '30CM'] and support_level and support_level < entry_price:
            tech_stop = round(support_level * (1 - market_profile['sr_tolerance']), 2)
            stop_price = max(stop_price, tech_stop) # 托底止损

        # ----------- 动态止盈价 (Target) -----------
        # 默认基础目标
        target_price = round(current_price + atr * 4, 2)
        
        if resistance_level and current_price < resistance_level:
            if board_type == '10CM':
                # 10CM 突破率 62.2%，拥抱突破，目标设在阻力位上方
                breakout_target = round(resistance_level + atr * 1.5, 2)
                target_price = max(target_price, breakout_target)
                reasons.append(f"止盈建议：[10CM突破市] 历史突破率高达62%，目标价设于阻力位上方 ({target_price:.2f}) 扩大盈利。")
                
            elif board_type == '30CM':
                # 30CM 压制率 70.2%，绝不格局，阻力位下方提前抢跑下车
                front_run_target = round(resistance_level - atr * 0.5, 2)
                target_price = min(target_price, front_run_target)
                reasons.append(f"止盈建议：[30CM边界市] 阻力压制力极强，切勿贪高，在 {target_price:.2f} 提前止盈。")
                
            else: # 20CM
                # 20CM 压制率 59.0%，比较纠结，在阻力位精准卖出
                target_price = round(resistance_level * 0.99, 2)
                reasons.append(f"止盈建议：[20CM震荡市] 尊重阻力位压制，在 {target_price:.2f} 附近离场。")

        return {
            'action': action,
            'confidence': float(confidence),
            'quality_grade': quality_grade,
            'analysis_logic': reasons,
            'current_price': current_price,
            'entry_price': entry_price,      
            'target_price': target_price,    
            'stop_price': stop_price,        
            'resistance_level': resistance_level,
            'support_level': support_level,
            'full_confluence_result': confluence_result 
        }
    except Exception as e:
        logger.error(f"V4.1交易建议生成失败: {e}")
        import traceback; traceback.print_exc()
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}
        
def _generate_forward_advice_v4_b1(df: pd.DataFrame, stock_code: str) -> dict:
    """
    【V4.1 核心函数】基于 V4.0 Confluence Scorer 生成高质量、可解释的交易建议（已修复参数传递）
    """
    try:
        latest_index = len(df) - 1
        current_price = float(df.iloc[latest_index]['close'])
        
        # 1. 调用 V4.0 评分系统获取最全面的分析结果
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
        
        # 2. 调用形态识别器
        pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)

        # 3. 初始化建议
        action = 'HOLD'
        reasons = []
        confidence = confluence_result['confidence']
        quality_grade = 'D'

        # 4. 构建层次化的决策逻辑
        market_phase = confluence_result.get('market_phase', 'unknown')
        reasons.append(f"宏观判断：当前处于 {market_phase.upper()} 阶段。")
        if market_phase in ['distribution', 'decline']:
            action = 'AVOID'
            reasons.append("风险提示：市场处于高风险或下跌阶段，建议规避。")
            confidence *= 0.7

        total_score = confluence_result.get('total_score', 0)
        if total_score >= 85:
            quality_grade = 'A'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (A级)，技术面高度共振。")
        elif total_score >= 70:
            quality_grade = 'B'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (B级)，技术面较为一致。")
        elif total_score >= 55:
            quality_grade = 'C'
            action = 'WATCH' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (C级)，建议保持观察。")
        else:
            quality_grade = 'D'
            action = 'AVOID'
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (D级)，技术指标不一致，建议规避。")

        if pattern_result.get('has_pattern'):
            reasons.append(f"形态分析：识别到 {pattern_result['best_pattern']} 形态 (置信度: {pattern_result['best_confidence']:.1%})。")
            confidence = (confidence + pattern_result['best_confidence']) / 2

        alignment = confluence_result.get('alignment_analysis', {})
        if alignment.get('alignment_score', 0) > 5:
            reasons.append(f"历史对齐：价格与指标底部同步性良好 (得分: {alignment['alignment_score']})。")
        
        backtest_val = confluence_result.get('backtest_analysis', {})
        if backtest_val.get('signal_count', 0) > 0:
            reasons.append(f"历史回测：基于对齐信号的历史胜率为 {backtest_val['win_rate']:.1%} (共{backtest_val['signal_count']}次)。")

        # 5. 计算支撑位和阻力位
        price_targets = _calculate_price_targets(df, current_price)
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 🚀 引入市场波动画像 (完美接入传入的 stock_code)
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code)
        board_type = market_profile['board_type']
        atr_adj = market_profile['atr_entry_mult']
        
        # 6. 获取ATR波动率
        atr = confluence_result.get('phase_analysis', {}).get('atr', current_price * 0.03)

        # ==========================================
        # 结合板块特性的动态入场价与止损计算
        # ==========================================
        pullback_multiplier = (0.4 if action == 'BUY' else 0.8) * atr_adj
        base_entry = current_price - (atr * pullback_multiplier)

        supp_distance = (current_price - support_level) / current_price if support_level else 1
        
        if support_level and (supp_distance < market_profile['limit']): 
            dynamic_entry = support_level + (atr * 0.1 * atr_adj)
            dynamic_entry = min(dynamic_entry, current_price * 0.995)
            dynamic_entry = max(dynamic_entry, support_level)
            reasons.append(f"入场建议：[{board_type}特性] 靠近支撑位 {support_level:.2f} 附近限价挂单。")
        else:
            dynamic_entry = base_entry
            reasons.append(f"入场建议：[{board_type}特性] 基于近期波动率，建议在现价下方回调约 {atr*pullback_multiplier:.2f} 元处挂单。")

        entry_price = round(dynamic_entry, 2)

        # 动态止损
        stop_multiplier = 1.5 * atr_adj
        stop_price = round(entry_price - atr * stop_multiplier, 2)  
        
        if support_level and support_level < entry_price:
            tech_stop = round(support_level * (1 - market_profile['sr_tolerance']/2), 2)
            stop_price = max(stop_price, tech_stop)

        # ==========================================
        # 🎯 优化：拥抱高突破率的攻击性止盈逻辑
        # ==========================================
        # 默认基础目标：4倍ATR（如果市场波动大，这就已经很高了）
        target_price = round(current_price + atr * 4, 2)
        
        if resistance_level and current_price < resistance_level:
            # 既然历史数据显示高达 71.4% 的概率会强势突破阻力位
            # 我们不再在阻力位下方卖出，而是将阻力位视为“加速器”
            # 目标价取 【基础ATR目标】 和 【阻力位突破后再加1倍ATR】 的最大值
            breakout_target = round(resistance_level + atr, 2)
            
            if target_price < breakout_target:
                target_price = breakout_target
                reasons.append(f"止盈建议：[{board_type}特性] 鉴于系统选股的高突破率，目标价设于阻力位上方突破区域 ({target_price:.2f})。")
            else:
                reasons.append(f"止盈建议：[{board_type}特性] 保持大波段目标 ({target_price:.2f})，无视近期小阻力。")

        return {
            'action': action,
            'confidence': float(confidence),
            'quality_grade': quality_grade,
            'analysis_logic': reasons,
            'current_price': current_price,
            'entry_price': entry_price,      
            'target_price': target_price,    
            'stop_price': stop_price,        
            'resistance_level': resistance_level,
            'support_level': support_level,
            'full_confluence_result': confluence_result 
        }
    except Exception as e:
        logger.error(f"V4.1交易建议生成失败: {e}")
        import traceback; traceback.print_exc()
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}
    

def _generate_forward_advice_v4_b(df: pd.DataFrame) -> dict:
    """
    【V4.1 核心函数】基于 V4.0 Confluence Scorer 生成高质量、可解释的交易建议
    """
    try:
        latest_index = len(df) - 1
        current_price = float(df.iloc[latest_index]['close'])
        
        # 1. 调用 V4.0 评分系统获取最全面的分析结果
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
        
        # 2. 调用形态识别器
        pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)

        # 3. 初始化建议
        action = 'HOLD'
        reasons = []
        confidence = confluence_result['confidence']
        quality_grade = 'D'

        # 4. 构建层次化的决策逻辑
        
        # 第一层：基于市场阶段的宏观判断
        market_phase = confluence_result.get('market_phase', 'unknown')
        reasons.append(f"宏观判断：当前处于 {market_phase.upper()} 阶段。")
        if market_phase in ['distribution', 'decline']:
            action = 'AVOID'
            reasons.append("风险提示：市场处于高风险或下跌阶段，建议规避。")
            confidence *= 0.7 # 降低置信度

        # 第二层：基于融合评分的核心决策
        total_score = confluence_result.get('total_score', 0)
        if total_score >= 85:
            quality_grade = 'A'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (A级)，技术面高度共振。")
        elif total_score >= 70:
            quality_grade = 'B'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (B级)，技术面较为一致。")
        elif total_score >= 55:
            quality_grade = 'C'
            action = 'WATCH' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (C级)，建议保持观察。")
        else:
            quality_grade = 'D'
            action = 'AVOID'
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (D级)，技术指标不一致，建议规避。")

        # 第三层：基于具体分析的细化理由
        
        # 形态分析
        if pattern_result.get('has_pattern'):
            reasons.append(f"形态分析：识别到 {pattern_result['best_pattern']} 形态 (置信度: {pattern_result['best_confidence']:.1%})。")
            confidence = (confidence + pattern_result['best_confidence']) / 2 # 结合形态置信度

        # 历史对齐分析
        alignment = confluence_result.get('alignment_analysis', {})
        if alignment.get('alignment_score', 0) > 5:
            reasons.append(f"历史对齐：价格与指标底部同步性良好 (得分: {alignment['alignment_score']})。")
        
        # 回测验证
        backtest_val = confluence_result.get('backtest_analysis', {})
        if backtest_val.get('signal_count', 0) > 0:
            reasons.append(f"历史回测：基于对齐信号的历史胜率为 {backtest_val['win_rate']:.1%} (共{backtest_val['signal_count']}次)。")

        # 5. 计算支撑位和阻力位
        price_targets = _calculate_price_targets(df, current_price)
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 获取市场波动画像
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code) # 注意确保函数有传入 stock_code
        board_type = market_profile['board_type']
        atr_adj = market_profile['atr_entry_mult']
        
        # 6. 获取ATR波动率 (默认为股价的3%)
        atr = confluence_result.get('phase_analysis', {}).get('atr', current_price * 0.03)

        # ==========================================
        # 🚀 核心优化：结合板块特性的动态入场价
        # ==========================================
        # 基础回撤系数结合板块波动率放大
        pullback_multiplier = (0.4 if action == 'BUY' else 0.8) * atr_adj
        base_entry = current_price - (atr * pullback_multiplier)

        # 支撑位判定也要加入板块容忍度
        supp_distance = (current_price - support_level) / current_price if support_level else 1
        
        if support_level and (supp_distance < market_profile['limit']): 
            # 策略 A：基于支撑位抢跑。波动越大的市场，抢跑的垫子(0.1*atr_adj)要稍微厚一点
            dynamic_entry = support_level + (atr * 0.1 * atr_adj)
            dynamic_entry = min(dynamic_entry, current_price * 0.995)
            dynamic_entry = max(dynamic_entry, support_level)
            reasons.append(f"入场建议：[{board_type}特性] 靠近支撑位 {support_level:.2f} 附近限价挂单。")
        else:
            # 策略 B：无有效支撑，基于波动率回调
            dynamic_entry = base_entry
            reasons.append(f"入场建议：[{board_type}特性] 基于近期波动率，建议在现价下方回调约 {atr*pullback_multiplier:.2f} 元处挂单。")

        entry_price = round(dynamic_entry, 2)

        # 动态计算止损 (根据板块放大止损容忍度，防止被日常洗盘洗掉)
        stop_multiplier = 1.5 * atr_adj
        stop_price = round(entry_price - atr * stop_multiplier, 2)  
        
        if support_level and support_level < entry_price:
            # 技术止损位同样赋予板块特性的缓冲
            tech_stop = round(support_level * (1 - market_profile['sr_tolerance']/2), 2)
            stop_price = max(stop_price, tech_stop)

        target_price = round(current_price * (1 + atr / current_price * 4), 2)
        if resistance_level and current_price < resistance_level < target_price:
            target_price = round(resistance_level * 0.99, 2)

        return {
            'action': action,
            'confidence': float(confidence),
            'quality_grade': quality_grade,
            'analysis_logic': reasons,
            'current_price': current_price,
            'entry_price': entry_price,      # ⬅️ 完美接入动态挂单价
            'target_price': target_price,    # ⬅️ 优化后的抢跑止盈价
            'stop_price': stop_price,        # ⬅️ 基于买入价的严谨止损位
            'resistance_level': resistance_level,
            'support_level': support_level,
            'full_confluence_result': confluence_result
        }
    except Exception as e:
        logger.error(f"V4.1交易建议生成失败: {e}")
        import traceback; traceback.print_exc();
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}

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


def get_deep_analysis_V0(stock_code: str, df: pd.DataFrame = None) -> dict:
    """
    【V4.1 统一入口】
    对单只股票进行深度分析，并生成V4.1版前瞻性交易建议。
    """
    try:
        if df is None:
            from data_handler import get_full_data_with_indicators
            df = get_full_data_with_indicators(stock_code)
            if df is None:
                return {'error': '无法获取股票数据或数据不足'}

        # 核心改变：直接调用 V4.1 的建议生成函数
        forward_advice = _generate_forward_advice_v4(df)

        return {
            'stock_code': stock_code,
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'current_price': float(df.iloc[-1]['close']),
            'trading_advice': forward_advice, # 这是唯一的建议来源
            'from_cache': False
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': f'深度分析失败: {str(e)}'}

def get_deep_analysis(stock_code: str, analysis_date: str = None, df: pd.DataFrame = None) -> dict:
    """
    【V4.1 统一入口 - 已支持历史日期】
    analysis_date: 指定历史分析日期 (YYYY-MM-DD)，None 为最新数据
    """
    try:
        if df is None:
            # 调用增强后的 data_handler，支持 end_date
            df = get_full_data_with_indicators(
                stock_code, 
                adjustment_type='forward', 
                end_date=analysis_date
            )
            if df is None or len(df) < 100:
                return {'error': f'无法获取 {stock_code} 在 {analysis_date or "最新"} 的足够数据'}

        # 确保数据按时间排序
        df = df.sort_index()
        
        # 调用 V4.1 前瞻建议生成
        forward_advice = _generate_forward_advice_v4(df, stock_code)

        return {
            'stock_code': stock_code,
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'analysis_date': analysis_date or str(df.index[-1].date()),
            'current_price': float(df.iloc[-1]['close']),
            'trading_advice': forward_advice,
            'data_points': len(df),
            'from_cache': False
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'error': f'深度分析失败: {str(e)}'}
