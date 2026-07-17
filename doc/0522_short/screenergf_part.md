import os
import glob
import json
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging
import data_loader
import strategies
import backtester
import indicators
from adjustment_processor import AdjustmentProcessor, AdjustmentConfig
from win_rate_filter import WinRateFilter, AdvancedTripleCrossFilter
import talib # 确保导入talib

# === 新增并优化的策略逻辑 START ===
def apply_reversed_short_optimized(df):
    """
    优化后的反转做空策略（用于做多选股）
    核心逻辑：寻找满足以下条件中至少两个的股票，表明下跌动能衰竭，可能反转。
    """
    if len(df) < 60:
        return None
    try:
        df['ma20'] = talib.MA(df['close'], timeperiod=20)
        df['ma60'] = talib.MA(df['close'], timeperiod=60)
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        macd, signal, _ = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        df['macd'] = macd
        df['rsi'] = talib.RSI(df['close'], timeperiod=14)

        signal_series = pd.Series(False, index=df.index)
        current_idx = -1
        current_data = df.iloc[current_idx]
        prev_data = df.iloc[current_idx - 1]
        conditions_met = 0
        
        lookback_period = 60
        recent_data = df.iloc[-lookback_period:]
        price_trough_date = recent_data['close'].idxmin()
        macd_at_trough = df.loc[price_trough_date]['macd']
        current_macd = current_data['macd']
        
        if (df.index[current_idx] - price_trough_date).days > 3:
            macd_recovery = current_macd - macd_at_trough
            price_still_low = current_data['close'] < df.loc[price_trough_date]['close'] * 1.15
            if macd_recovery > abs(macd_at_trough) * 0.3 and price_still_low:
                conditions_met += 1

        if prev_data['rsi'] < 35 and current_data['rsi'] > prev_data['rsi']:
            conditions_met += 1
            
        if (prev_data['close'] < prev_data['ma20'] and 
            current_data['close'] > current_data['ma20'] and 
            current_data['volume'] > current_data['volume_ma20'] * 1.5):
            conditions_met += 1
        
        if not pd.isna(current_data['ma60']) and current_data['close'] > current_data['ma60']:
            conditions_met += 0.5

        if conditions_met >= 2:
            signal_series.iloc[current_idx] = True
        return signal_series
    except Exception as e:
        return None

def evaluate_adaptive_entry_price(df, best_ma_period, polarity_confirmed, deep_touches, current_ma_val):
    """专为自适应均线深踩策略设计的入场价格评估"""
    current_price = df['close'].iloc[-1]
    recent_low = df['low'].iloc[-60:].min()
    rebound_potential = (current_price - recent_low) / recent_low if recent_low > 0 else 0
    
    ma20 = talib.MA(df['close'], 20).iloc[-1]
    ma60 = talib.MA(df['close'], 60).iloc[-1]
    
    if polarity_confirmed:
        risk_level = "低"
        recommended = max(current_ma_val * 0.992, recent_low * 1.01)
        aggressive = current_ma_val * 1.008
        conservative = current_ma_val * 0.975
        expected_rebound = max(0.20, rebound_potential * 1.6)
    else:
        risk_level = "中高"
        recommended = current_ma_val * 0.965
        aggressive = current_ma_val * 0.985
        conservative = max(recent_low * 1.005, current_ma_val * 0.94)
        expected_rebound = max(0.12, rebound_potential * 1.3)
    
    if not pd.isna(ma20) and current_price / ma20 > 1.07:
        risk_level = "高"
        recommended *= 0.98
        conservative *= 0.97
    
    return {
        'recommended_entry': round(recommended, 2),
        'aggressive_entry': round(aggressive, 2),
        'conservative_entry': round(conservative, 2),
        'expected_rebound': round(expected_rebound, 4),
        'risk_level': risk_level,
        'rebound_potential': round(rebound_potential, 4),
        'current_ma_val': round(current_ma_val, 2)
    }

def check_weekly_trend_safe(df):
    """通过重采样周线数据，甄别大级别处于主跌浪的左侧风险标的"""
    try:
        df_copy = df.copy()
        if not isinstance(df_copy.index, pd.DatetimeIndex):
            df_copy.index = pd.to_datetime(df_copy.index)
        weekly = df_copy.resample('W').agg({
            'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
        }).dropna()
        
        if len(weekly) < 26: return True, "周线样本过少，放行"
        w_ma5 = talib.MA(weekly['close'], timeperiod=5)
        w_ma20 = talib.MA(weekly['close'], timeperiod=20)
        _, _, w_macdhist = talib.MACD(weekly['close'], 12, 26, 9)
        
        if w_ma5.iloc[-1] < w_ma20.iloc[-1] and w_macdhist.iloc[-1] < 0 and w_macdhist.iloc[-1] < w_macdhist.iloc[-2]:
            return False, "周线级别处于MA死叉且主跌绿柱放大通道"
        if weekly['close'].iloc[-1] < w_ma20.iloc[-1] and (w_macdhist.iloc[-4:] < 0).all():
            return False, "周线大趋势处于20周线下方的长期阴跌主跌浪"
        return True, "周线大级别大底形态合格"
    except Exception as e:
        return True, f"周线校验异常放行: {e}"

def apply_adaptive_ma_support_optimized(df, config_dict=None):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V17 评分特征打增益完全体)
    向外无缝绑定外抛：weekly_floor_low (周线级别历史大底低点) 与 recent_resistance (筹码压力位)
    """
    if len(df) < 250: 
        return None

    cfg = config_dict if config_dict else {}
    FORWARD_DAYS = cfg.get('forward_days', 8)
    TARGET_PROFIT = cfg.get('target_profit', 0.098)
    DECAY_PROFIT = cfg.get('decay_profit', 0.075)

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

        future_high_matrix = pd.DataFrame(index=df.index)
        future_low_matrix = pd.DataFrame(index=df.index)
        future_close_matrix = pd.DataFrame(index=df.index)
        for i in range(1, FORWARD_DAYS + 1):
            future_high_matrix[f'h_{i}'] = df['high'].shift(-i)
            future_low_matrix[f'l_{i}'] = df['low'].shift(-i)
            future_close_matrix[f'c_{i}'] = df['close'].shift(-i)

        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            if ma_series.iloc[-1] < ma_series.iloc[-7] * 0.995: continue
            current_ma_val = ma_series.iloc[-1]
            if ma13_full.iloc[-1] < current_ma_val: continue

            ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]
            recent_12d_high = df['high'].iloc[-12:].max()
            drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high
            
            recent_120 = df.iloc[-120:]
            dist_close = (recent_120['close'] - ma_series.iloc[-120:]) / ma_series.iloc[-120:]
            dist_low = (recent_120['low'] - ma_series.iloc[-120:]) / ma_series.iloc[-120:]
            near_long_ma = (((dist_close >= -0.05) & (dist_close <= 0.035)) | ((dist_low >= -0.06) & (dist_low <= 0.02)))
            valid_deep_touches = (short_broken_full.iloc[-120:] & near_long_ma).sum()

            if ma_slope < 0.0208: continue            
            if drop_velocity > -0.0828: continue       
            if valid_deep_touches > 14: continue       

            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.12: continue  

            distance = (df['close'] - ma_series) / ma_series
            is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)
            
            full_strategy_mask = (
                short_broken_full & 
                is_near_ma_full & 
                momentum_reversal_series & 
                (df['close'] > ma_series * 0.982) &
                (ma30_full > ma_series)
            )

            if not full_strategy_mask.iloc[-1]: continue

            past_indices = np.where(full_strategy_mask.iloc[:-15].values)[0]
            if len(past_indices) == 0:
                ma_score = 0.0
            else:
                past_pnls = []
                win_count = 0
                for p_idx in past_indices:
                    p_ma_val = ma_series.iloc[p_idx]
                    start_idx = max(0, p_idx - 30)
                    p_touches = (abs(df['close'].iloc[start_idx:p_idx] - ma_series.iloc[start_idx:p_idx]) / ma_series.iloc[start_idx:p_idx] <= 0.03).sum()
                    p_is_deep = ma30_full.iloc[p_idx] < p_ma_val * 0.985
                    
                    p_trigger_buy = p_ma_val * 0.96 if p_is_deep or p_touches > 14 else p_ma_val * 1.005
                    p_stop_loss = p_ma_val * 0.88 if p_is_deep or p_touches > 14 else p_ma_val * 0.925
                    
                    h_vec = future_high_matrix.iloc[p_idx].values
                    l_vec = future_low_matrix.iloc[p_idx].values
                    c_vec = future_close_matrix.iloc[p_idx].values
                    
                    p_status = "未成交"
                    p_entry_price = 0.0
                    p_pnl = 0.0
                    
                    for d in range(FORWARD_DAYS):
                        cur_open = df['open'].iloc[p_idx + 1 + d]
                        if p_status == "未成交":
                            if cur_open <= p_stop_loss: continue
                            if l_vec[d] <= p_trigger_buy:
                                if c_vec[d] >= l_vec[d] * 1.015:
                                    p_status = "持仓中"
                                    p_entry_price = min(p_trigger_buy, l_vec[d] * 1.015)
                        elif p_status == "持仓中":
                            hold_d = d + 1
                            p_target = TARGET_PROFIT if hold_d <= 4 else DECAY_PROFIT
                            if h_vec[d] >= p_entry_price * (1 + p_target):
                                p_pnl = p_target
                                p_status = "止盈成功"
                                break
                            if l_vec[d] <= p_stop_loss * 0.97 or c_vec[d] <= p_stop_loss:
                                p_pnl = (c_vec[d] - p_entry_price) / p_entry_price
                                p_status = "止损出局"
                                break
                                
                    if p_status == "持仓中" and p_entry_price > 0:
                        p_pnl = (c_vec[-1] - p_entry_price) / p_entry_price
                    if p_status != "未成交":
                        past_pnls.append(p_pnl)
                        if p_pnl > 0: win_count += 1
                
                if past_pnls:
                    hist_win_rate = win_count / len(past_pnls)
                    hist_avg_pnl = np.mean(past_pnls)
                    ma_score = 100.0 + (hist_win_rate * 100.0) + (hist_avg_pnl * 500.0)
                else:
                    ma_score = 0.0

            if ma_score > highest_score:
                highest_score = ma_score
                best_ma = ma_period
                was_resistance = (df['close'].iloc[-250:-120] < ma_series.iloc[-250:-120]).mean() > 0.60
                best_details = {
                    'polarity_confirmed': was_resistance, 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.985),
                    'ma_slope': float(ma_slope),
                    'drop_velocity': float(drop_velocity)
                }

        if best_ma is None or highest_score < 120:   
            return None

        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        signal_series = (
            short_broken_full & 
            is_near_ma_full & 
            momentum_reversal_series & 
            (df['close'] > best_ma_series * 0.982) &
            (ma30_full > best_ma_series) 
        )

        if not signal_series.iloc[-1]:
            return None

        # =================================================================
        # 🚀 仅在选股最终出线点，静态抽取周线级大底与强阻力位，彻底拒绝回测卡顿
        # =================================================================
        weekly_floor_low = df['low'].iloc[-150:].min()          # 30周极限物理低点防线
        recent_resistance = df['close'].iloc[-60:].max()        # 3个月近期核心阻力压力位

        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)
        
        # 🔑 特征挂载
        signal_series.weekly_floor_low = round(weekly_floor_low, 2)
        signal_series.recent_resistance = round(recent_resistance, 2)

        return signal_series
    except Exception:
        return None

