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
from market_regime import MarketRegimeDetector
import talib # 确保导入talib

# === 新增并优化的策略逻辑 START ===
# 这是我们之前优化好的、可以正常工作的“反转做多”策略
def apply_reversed_short_optimized(df):
    """
    优化后的反转做空策略（用于做多选股）
    核心逻辑：寻找满足以下条件中至少两个的股票，表明下跌动能衰竭，可能反转。

    1. 修正的MACD底背离：价格在近期低位，但MACD指标已明显回升。
    2. 可靠的放量突破：价格上穿MA20，且成交量显著大于20日均量。
    3. 放宽的RSI超卖启动：RSI从35以下的超卖/低位区金叉回升。
    """
    if len(df) < 60:  # 需要足够数据来计算指标和判断背离
        return None

    try:
        # 统一计算所需指标（修正：MA20/MA60 分开命名，避免混淆）
        df['ma20'] = talib.MA(df['close'], timeperiod=20)
        df['ma60'] = talib.MA(df['close'], timeperiod=60)
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        macd, signal, _ = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        df['macd'] = macd
        df['rsi'] = talib.RSI(df['close'], timeperiod=14)

        signal_series = pd.Series(False, index=df.index)
        
        # 只检查最后一个交易日
        current_idx = -1
        current_data = df.iloc[current_idx]
        prev_data = df.iloc[current_idx - 1]

        conditions_met = 0
        
        # --- 条件1：修正的MACD底背离检查 ---
        # 修复：macd_at_trough 为负数时，乘以 1.3 会让阈值更负，需改为绝对差值判断
        lookback_period = 60
        recent_data = df.iloc[-lookback_period:]
        price_trough_date = recent_data['close'].idxmin()
        macd_at_trough = df.loc[price_trough_date]['macd']
        current_macd = current_data['macd']
        
        # 背离条件：价格创新低但 MACD 明显回升（用绝对差值，避免负数乘法陷阱）
        if (df.index[current_idx] - price_trough_date).days > 3:
            macd_recovery = current_macd - macd_at_trough  # 正值表示 MACD 已回升
            price_still_low = current_data['close'] < df.loc[price_trough_date]['close'] * 1.15
            # MACD 回升幅度需超过其自身绝对值的 30%（用绝对值避免符号问题）
            if macd_recovery > abs(macd_at_trough) * 0.3 and price_still_low:
                conditions_met += 1

        # --- 条件2：RSI超卖区启动 ---
        if prev_data['rsi'] < 35 and current_data['rsi'] > prev_data['rsi']:
            conditions_met += 1
            
        # --- 条件3：可靠的放量突破MA20（使用正确的 ma20，周期=20）---
        if (prev_data['close'] < prev_data['ma20'] and 
            current_data['close'] > current_data['ma20'] and 
            current_data['volume'] > current_data['volume_ma20'] * 1.5):
            conditions_met += 1
        
        # --- 条件4（新增）：价格在 MA60 上方，确认中期趋势向上 ---
        # 只有在中期趋势健康时才加分，避免在深度下跌中抄底
        if not pd.isna(current_data['ma60']) and current_data['close'] > current_data['ma60']:
            conditions_met += 0.5  # 半分，作为加权条件

        # 如果满足至少2个条件，则产生信号
        if conditions_met >= 2:
            signal_series.iloc[current_idx] = True
            
        return signal_series

    except Exception as e:
        return None
# === 新增并优化的策略逻辑 END ===
def evaluate_adaptive_entry_price(df, best_ma_period, polarity_confirmed, deep_touches, current_ma_val):
    """
    专为自适应均线深踩策略设计的入场价格评估
    核心目标：找出低位反弹空间大、风险可控的位置
    """
    current_price = df['close'].iloc[-1]
    recent_low = df['low'].iloc[-60:].min()
    rebound_potential = (current_price - recent_low) / recent_low if recent_low > 0 else 0
    
    ma20 = talib.MA(df['close'], 20).iloc[-1]
    ma60 = talib.MA(df['close'], 60).iloc[-1]
    
    if polarity_confirmed:
        # 极性转换确认 → 位置更可靠，可相对激进
        risk_level = "低"
        recommended = max(current_ma_val * 0.992, recent_low * 1.01)   # 略高于近期低点
        aggressive = current_ma_val * 1.008
        conservative = current_ma_val * 0.975
        expected_rebound = max(0.20, rebound_potential * 1.6)
    else:
        # 非极性确认 → 必须更保守，等更低价格
        risk_level = "中高"
        recommended = current_ma_val * 0.965
        aggressive = current_ma_val * 0.985
        conservative = max(recent_low * 1.005, current_ma_val * 0.94)
        expected_rebound = max(0.12, rebound_potential * 1.3)
    
    # 额外安全过滤：距离MA20过远则提高保守程度
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
    """
    通过重采样周线数据，甄别大级别处于主跌浪的左侧风险标的
    """
    try:
        df_copy = df.copy()
        if not isinstance(df_copy.index, pd.DatetimeIndex):
            df_copy.index = pd.to_datetime(df_copy.index)
            
        # 聚合生成真实的周线数据，杜绝未来函数
        weekly = df_copy.resample('W').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        if len(weekly) < 26:
            return True, "周线样本过少，放行"
            
        # 计算周线级别 5周、20周 核心移动平均线及MACD
        w_ma5 = talib.MA(weekly['close'], timeperiod=5)
        w_ma20 = talib.MA(weekly['close'], timeperiod=20)
        _, _, w_macdhist = talib.MACD(weekly['close'], 12, 26, 9)
        
        last_ma5 = w_ma5.iloc[-1]
        last_ma20 = w_ma20.iloc[-1]
        last_hist = w_macdhist.iloc[-1]
        
        # 🚨 左侧主跌浪熔断点：周线5周线下穿20周线（大趋势走坏）且周MACD绿柱连续放大
        if last_ma5 < last_ma20 and last_hist < 0 and last_hist < w_macdhist.iloc[-2]:
            return False, "周线级别处于MA死叉且主跌绿柱放大通道"
            
        # 🚨 左侧阴跌熔断点：价格处于20周线下方，且连续4周周MACD未能翻红
        if weekly['close'].iloc[-1] < last_ma20 and (w_macdhist.iloc[-4:] < 0).all():
            return False, "周线大趋势处于20周线下方的长期阴跌主跌浪"
            
        return True, "周线大级别大底形态合格"
    except Exception as e:
        return True, f"周线校验异常放行: {e}"

def apply_adaptive_ma_support_optimized_V17(df, config_dict=None):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V17 股性历史自共振对齐版)
    核心哲学：千股千面，用个股自己的历史对账单做裁判。
    1. 前置层：利用16个月全周期压测【止盈组25%分位卡尺】强行熔断 1384 只持仓到期死鱼。
    2. 打分层：利用向量化矩阵极速回溯个股历史真实触发点，计算其“历史笔均期望净利润”，作为最终排序唯一依据。
    """
    if len(df) < 250: 
        return None

    # 动态对接外层时光机配置参数
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

        # 1. 预计算全局基础技术指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 全时序动量条件布尔化
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

        # 🚀 向量化平铺未来矩阵，供个股内部小回测极速调用
        future_high_matrix = pd.DataFrame(index=df.index)
        future_low_matrix = pd.DataFrame(index=df.index)
        future_close_matrix = pd.DataFrame(index=df.index)
        for i in range(1, FORWARD_DAYS + 1):
            future_high_matrix[f'h_{i}'] = df['high'].shift(-i)
            future_low_matrix[f'l_{i}'] = df['low'].shift(-i)
            future_close_matrix[f'c_{i}'] = df['close'].shift(-i)

        # 3. 横向截面扫描候选专属长线均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            if ma_series.iloc[-1] < ma_series.iloc[-7] * 0.995: continue
            current_ma_val = ma_series.iloc[-1]
            if ma13_full.iloc[-1] < current_ma_val: continue

            # 🛠️ 提取当日环境核心特征属性
            ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]
            recent_12d_high = df['high'].iloc[-12:].max()
            drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high
            
            recent_120 = df.iloc[-120:]
            dist_close = (recent_120['close'] - ma_series.iloc[-120:]) / ma_series.iloc[-120:]
            dist_low = (recent_120['low'] - ma_series.iloc[-120:]) / ma_series.iloc[-120:]
            near_long_ma = (((dist_close >= -0.05) & (dist_close <= 0.035)) | ((dist_low >= -0.06) & (dist_low <= 0.02)))
            valid_deep_touches = (short_broken_full.iloc[-120:] & near_long_ma).sum()

            # =================================================================
            # 🛑 📐 门槛大闸：严格锁定全周期【止盈成功组25%分位技术防线】
            # 用真实数据矩阵硬性剔除 1384 笔持仓到期死鱼股
            # =================================================================
            if ma_slope < 0.0208: continue            # 均线仰角不够，蹦床无弹性，熔断！
            if drop_velocity > -0.0828: continue       # 砸盘速度过慢，未引发恐慌盘，熔断！
            if valid_deep_touches > 14: continue       # 蹭均线次数过多，属于散户菜市场，熔断！

            # 主升浪基因基本面过滤
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.12: continue  

            # 判定当日信号是否达标
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

            # =================================================================
            # 🔬 ⚡ 核心进化：个股自身历史对账单期望核算 (Self-Resonance)
            # =================================================================
            past_indices = np.where(full_strategy_mask.iloc[:-15].values)[0]
            
            if len(past_indices) == 0:
                # 历史上从来没触发出过该信号的股票（零信用白纸股），不给予前排机会，防止回测虚高
                ma_score = 0.0
            else:
                past_pnls = []
                win_count = 0
                
                # 原地复盘该个股过去3年内每一次踩针后的条件单执行结局
                for p_idx in past_indices:
                    p_ma_val = ma_series.iloc[p_idx]
                    
                    # 计算历史触发点的分流买入条件
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
                
                # 【期望打分逻辑重塑】：完全由历史自证的“笔均净利润”和“历史止盈胜率”交乘决定
                if past_pnls:
                    hist_win_rate = win_count / len(past_pnls)
                    hist_avg_pnl = np.mean(past_pnls)
                    # 基础分 100 + 历史胜率权重加成 + 历史笔均利润倍数放大
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

        # 调高精品出线线至 120 分，剔除历史期望为负的亏损基因股
        if best_ma is None or highest_score < 120:   
            return None

        # 4. 生成最终信号序列
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

        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)

        return signal_series

    except Exception:
        return None

def apply_adaptive_ma_support_optimized(df, config_dict=None):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V16 矩阵向量化自校准版)
    完美修复 Grok 指出的: 计算效率灾难、白纸股默认分过高漏洞、参数硬编码断层。
    核心逻辑：利用 Pandas 矩阵位移(Shift)消灭显式持仓循环，对零历史存证标的实施“零信用熔断”。
    """
    if len(df) < 250: 
        return None

    # 🛠️ 修复硬编码断层：动态对接外层时光机配置，若无则平稳降级至默认值
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

        # 1. 预计算全局基础技术指标序列
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)
        vol_ma20 = df['volume'].rolling(20).mean()

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 全时序动量条件布尔化
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

        # ⚡ 🚀【重大效率优化】：利用矩阵位移，提前将未来1到8天的最高/最低价平铺，彻底消灭下游逐日迭代循环
        # 创建单股未来特征矩阵
        future_high_matrix = pd.DataFrame(index=df.index)
        future_low_matrix = pd.DataFrame(index=df.index)
        future_close_matrix = pd.DataFrame(index=df.index)
        for i in range(1, FORWARD_DAYS + 1):
            future_high_matrix[f'h_{i}'] = df['high'].shift(-i)
            future_low_matrix[f'l_{i}'] = df['low'].shift(-i)
            future_close_matrix[f'c_{i}'] = df['close'].shift(-i)

        # 3. 遍历扫描候选专属均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            if ma_series.iloc[-1] < ma_series.iloc[-7] * 0.995: continue
            current_ma_val = ma_series.iloc[-1]
            if ma13_full.iloc[-1] < current_ma_val: continue

            # =================================================================
            # 🚨 新增：高位断头铡刀 / 瀑布杀 硬熔断 (彻底淘汰没到位的飞刀)
            # =================================================================
            # 计算近 5 天的最高点
            #recent_5d_high = df['high'].iloc[-5:].max()
            # 当前收盘价距离近 5 天最高点的回撤
            #short_term_dump = (df['close'].iloc[-1] - recent_5d_high) / recent_5d_high
            
            # 判定 1：如果 5 天内暴跌超过 10%，触发“危险位置”警报
            #if short_term_dump < -0.25:
                # 获取近 3 天的量能均值，与 20 日均量对比
                #vol_2d_avg = df['volume'].iloc[-2:].mean()
                #vol_20d_avg = vol_ma20.iloc[-1] if 'vol_ma20' in locals() else df['volume'].rolling(20).mean().iloc[-1]
                
                # 🔪 杀招 A：带量砸盘，绝对不接
                #if vol_2d_avg > vol_20d_avg * 2:
                #    continue # 熔断：放量瀑布杀，主力正在疯狂出逃，均线必破
                    
                # 🔪 杀招 B：光脚阴线，抛压未竭
                # 计算今天收盘价在全天振幅中的位置 (0表示收在最低，1表示收在最高)
                #today_candle_shape = (df['close'].iloc[-1] - df['low'].iloc[-1]) / (df['high'].iloc[-1] - df['low'].iloc[-1] + 1e-5)
                
                # 如果暴跌后，今天的收盘价依然处于全天振幅的下 25% (光脚或近乎光脚的阴线)
                #if today_candle_shape < 0.25: 
                #    continue # 熔断：抛压根本没有衰竭，连个下影线的抵抗都没有，形态极度没到位
            # =================================================================

            # 评估区间基本面健康检查（主升浪基因初筛）
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.08: continue  

            # 判定当前选股日是否触发信号
            distance = (df['close'] - ma_series) / ma_series
            is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)
            
            full_strategy_mask = (
                short_broken_full & 
                is_near_ma_full & 
                momentum_reversal_series & 
                (df['close'] > ma_series * 0.982) &
                (ma30_full > ma_series)
            )

            # 如果今天没触发信号，直接跳过
            if not full_strategy_mask.iloc[-1]: continue

            # =================================================================
            # 🔬 ⚡ V16 向量化个股行为历史自校准计算 ⚡
            # =================================================================
            # 提取历史前段的所有触发点索引（留足15天安全边界）
            past_indices = np.where(full_strategy_mask.iloc[:-15].values)[0]
            
            if len(past_indices) == 0:
                # 🛑【核心优化：填补默认分过高漏洞】
                # 历史上从来没有证明过自己股性契合该均线的“白纸股”，直接给予低分或者清零，严防逆袭
                ma_score = 0.0
            else:
                past_pnls = []
                win_count = 0
                
                # 滚动批量提取历史点的未来矩阵列（单股通常就十几个点，极速运行）
                for p_idx in past_indices:
                    p_ma_val = ma_series.iloc[p_idx]
                    
                    # 向量化平准摩擦频次
                    start_idx = max(0, p_idx - 30)
                    p_touches = (abs(df['close'].iloc[start_idx:p_idx] - ma_series.iloc[start_idx:p_idx]) / ma_series.iloc[start_idx:p_idx] <= 0.03).sum()
                    p_is_deep = ma30_full.iloc[p_idx] < p_ma_val * 0.985
                    
                    p_trigger_buy = p_ma_val * 0.96 if p_is_deep or p_touches > 14 else p_ma_val * 1.005
                    p_stop_loss = p_ma_val * 0.88 if p_is_deep or p_touches > 14 else p_ma_val * 0.925
                    
                    # 直接从预计算矩阵中提取该点往后的8天平铺向量，杜绝 iterrows 效率灾难
                    h_vec = future_high_matrix.iloc[p_idx].values
                    l_vec = future_low_matrix.iloc[p_idx].values
                    c_vec = future_close_matrix.iloc[p_idx].values
                    
                    p_status = "未成交"
                    p_entry_price = 0.0
                    p_pnl = 0.0
                    
                    # 极速向量迭代（仅 8 次无关联计算）
                    for d in range(FORWARD_DAYS):
                        cur_open = df['open'].iloc[p_idx + 1 + d]
                        cur_high = h_vec[d]
                        cur_low = l_vec[d]
                        cur_close = c_vec[d]
                        
                        if p_status == "未成交":
                            if cur_open <= p_stop_loss: continue
                            if cur_low <= p_trigger_buy:
                                if cur_close >= cur_low * 1.015:
                                    p_status = "持仓中"
                                    p_entry_price = min(p_trigger_buy, cur_low * 1.015)
                        elif p_status == "持仓中":
                            hold_d = d + 1
                            p_target = TARGET_PROFIT if hold_d <= 4 else DECAY_PROFIT
                            if cur_high >= p_entry_price * (1 + p_target):
                                p_pnl = p_target
                                p_status = "止盈成功"
                                break
                            if cur_low <= p_stop_loss * 0.97 or cur_close <= p_stop_loss:
                                p_pnl = (cur_close - p_entry_price) / p_entry_price
                                p_status = "止损出局"
                                break
                                
                    if p_status == "持仓中" and p_entry_price > 0:
                        p_pnl = (c_vec[-1] - p_entry_price) / p_entry_price
                        
                    if p_status != "未成交":
                        past_pnls.append(p_pnl)
                        if p_pnl > 0: win_count += 1
                
                # 计算自存证真实期望分
                if past_pnls:
                    hist_win_rate = win_count / len(past_pnls)
                    hist_avg_pnl = np.mean(past_pnls)
                    ma_score = 100.0 + (hist_win_rate * 80.0) + (hist_avg_pnl * 400.0) + (min(len(past_pnls), 5) * 4)
                else:
                    ma_score = 0.0

            if ma_score > highest_score:
                highest_score = ma_score
                best_ma = ma_period
                
                ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]
                recent_12d_high = df['high'].iloc[-12:].max()
                drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high
                historical_150d_low = df['low'].iloc[-150:].min()

                recent_120 = df.iloc[-120:]
                dist_close = (recent_120['close'] - ma_series.iloc[-120:]) / ma_series.iloc[-120:]
                dist_low = (recent_120['low'] - ma_series.iloc[-120:]) / ma_series.iloc[-120:]
                near_long_ma = (((dist_close >= -0.05) & (dist_close <= 0.035)) | ((dist_low >= -0.06) & (dist_low <= 0.02)))
                valid_deep_touches = (short_broken_full.iloc[-120:] & near_long_ma).sum()
                was_resistance = (df['close'].iloc[-250:-120] < ma_series.iloc[-250:-120]).mean() > 0.60

                best_details = {
                    'polarity_confirmed': was_resistance and crossover.any(), 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.985),
                    'ma_slope': float(ma_slope),
                    'drop_velocity': float(drop_velocity),
                    'historical_150d_low': float(historical_150d_low)
                }

        if best_ma is None or highest_score < 75:   
            return None

        # 4. 输出最终获胜生命线的信号序列
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
        recent_resistance = df['close'].iloc[-60:].max()
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)
        signal_series.weekly_floor_low = best_details.get('hisorical_150d_low', 2)
        signal_series.recent_resistance = round(recent_resistance, 2)

        return signal_series

    except Exception:
        return None
    
def apply_adaptive_ma_support_optimized_V15(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V15 个股历史行为自校准对齐版 - 生产级修复)
    核心哲学：千股千面。废除跨个股的绝对指标打分，改为针对个股自身历史触发点的“原地小回测”。
    打分直接由该股过去对该均线的历史践踏胜率与期望收益决定，彻底解决高分死鱼与排序分散问题。
    """
    if len(df) < 250: 
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018
        FORWARD_DAYS = 8 # 严格对齐时光机的持仓未来看前窗口

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础技术指标序列
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)
        vol_ma20 = df['volume'].rolling(20).mean()

        try:
            # 💡 漏洞修复 1：严格对齐底层函数小写名称，杜绝 AttributeError 链式致盲信号
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 全时序动量条件生成 (全时序布尔化，用于快速历史定位)
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

        # 3. 遍历扫描候选专属均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            # 基础大趋势安全线
            if ma_series.iloc[-1] < ma_series.iloc[-7] * 0.995: continue
            current_ma_val = ma_series.iloc[-1]
            if ma13_full.iloc[-1] < current_ma_val: continue

            # 评估区间基本面健康检查（主升浪基因初筛）
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.08: continue  

            # 判定当前（选股日最后一天）是否触发该均线的深踩信号
            distance = (df['close'] - ma_series) / ma_series
            is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)
            
            full_strategy_mask = (
                short_broken_full & 
                is_near_ma_full & 
                momentum_reversal_series & 
                (df['close'] > ma_series * 0.982) &
                (ma30_full > ma_series)
            )

            # 🚨 如果今天没触发该均线信号，直接跳过其自回测，精简算力
            if not full_strategy_mask.iloc[-1]: continue

            # =================================================================
            # 🔬 ⚡ 核心逻辑：个股历史触发点“时光机自回测”验证 ⚡
            # =================================================================
            # 找出历史前段所有满足该策略买入条件的索引位置（留足最后15天未来窗口）
            past_signal_indices = np.where(full_strategy_mask.iloc[:-15].values)[0]
            
            past_pnls = []
            win_count = 0
            
            for p_idx in past_signal_indices:
                p_ma_val = ma_series.iloc[p_idx]
                
                # 💡 原地切片平准化估算当时的深踩摩擦频次（彻底防止 loc 带来的 datetime 索引错位）
                start_segment_idx = max(0, p_idx - 30)
                seg_close = df['close'].iloc[start_segment_idx:p_idx]
                seg_ma = ma_series.iloc[start_segment_idx:p_idx]
                p_touches = (abs(seg_close - seg_ma) / seg_ma <= 0.03).sum()
                
                p_is_deep = ma30_full.iloc[p_idx] < p_ma_val * 0.985
                
                if p_is_deep or p_touches > 14:
                    p_trigger_buy = p_ma_val * 0.96
                    p_stop_loss = p_ma_val * 0.88
                else:
                    p_trigger_buy = p_ma_val * 1.005
                    p_stop_loss = p_ma_val * 0.925
                    
                future_window = df.iloc[p_idx + 1 : p_idx + 1 + FORWARD_DAYS]
                if len(future_window) < FORWARD_DAYS: continue
                
                p_status = "未成交"
                p_entry_price = 0.0
                p_pnl = 0.0
                p_hold_days = 0
                
                for _, f_row in future_window.iterrows():
                    if p_status == "未成交":
                        if f_row['open'] <= p_stop_loss: continue
                        if f_row['low'] <= p_trigger_buy:
                            if f_row['close'] >= f_row['low'] * 1.015:
                                p_status = "持仓中"
                                p_entry_price = min(p_trigger_buy, f_row['low'] * 1.015)
                    elif p_status == "持仓中":
                        p_hold_days += 1
                        p_target = 0.098 if p_hold_days <= 4 else 0.075
                        if f_row['high'] >= p_entry_price * (1 + p_target):
                            p_pnl = p_target
                            p_status = "止盈成功"
                            break
                        if f_row['low'] <= p_stop_loss * 0.97 or f_row['close'] <= p_stop_loss:
                            p_pnl = (f_row['close'] - p_entry_price) / p_entry_price
                            p_status = "止损出局"
                            break
                            
                if p_status == "持仓中" and p_entry_price > 0:
                    p_pnl = (future_window['close'].iloc[-1] - p_entry_price) / p_entry_price
                    
                if p_status != "未成交":
                    past_pnls.append(p_pnl)
                    if p_pnl > 0: win_count += 1

            # =================================================================
            # ⚖️ 自适应期望打分矩阵 (数学期望模型)
            # =================================================================
            if len(past_pnls) > 0:
                hist_win_rate = win_count / len(past_pnls)
                hist_avg_pnl = np.mean(past_pnls)
                ma_score = 100.0 + (hist_win_rate * 80.0) + (hist_avg_pnl * 400.0) + (min(len(past_pnls), 5) * 4)
            else:
                ma_score = 75.0 

            if ma_score > highest_score:
                highest_score = ma_score
                best_ma = ma_period
                
                # 💡 漏洞修复 2：将形态特征移入获胜判定区动态计算，确保所有变量具备完美的生命周期定义
                ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]
                recent_12d_high = df['high'].iloc[-12:].max()
                drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high
                
                recent_120 = df.iloc[-120:]
                dist_close = (recent_120['close'] - ma_series.iloc[-120:]) / ma_series.iloc[-120:]
                dist_low = (recent_120['low'] - ma_series.iloc[-120:]) / ma_series.iloc[-120:]
                near_long_ma = (((dist_close >= -0.05) & (dist_close <= 0.035)) | ((dist_low >= -0.06) & (dist_low <= 0.02)))
                valid_deep_touches = (short_broken_full.iloc[-120:] & near_long_ma).sum()
                was_resistance = (df['close'].iloc[-250:-120] < ma_series.iloc[-250:-120]).mean() > 0.60

                best_details = {
                    'polarity_confirmed': was_resistance and crossover.any(), 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.985),
                    'ma_slope': float(ma_slope),
                    'drop_velocity': float(drop_velocity)
                }

        if best_ma is None or highest_score < 75:   
            return None

        # 4. 重新输出最佳专属生命线的全历史布尔信号
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

        # 元数据精准外抛绑定
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)

        return signal_series

    except Exception:
        return None
    
def apply_adaptive_ma_support_optimized_V14_e(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V14 门阀硬化过滤版)
    根据历史特征矩阵流水逆向倒推重构。
    彻底解决正常交易日“垃圾信号泛滥、全周期持仓到期过多”的痛点。
    """
    if len(df) < 250: 
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础技术指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)
        vol_ma20 = df['volume'].rolling(20).mean() 

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 横向扫描专属均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            if ma_series.iloc[-1] < ma_series.iloc[-7] * 0.995: continue
            current_ma_val = ma_series.iloc[-1]
            if ma13_full.iloc[-1] < current_ma_val: continue

            # ⚙️ 倒推特征数据提取
            ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]
            recent_12d_high = df['high'].iloc[-12:].max()
            drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high
            curr_vol_ratio = df['volume'].iloc[-1] / vol_ma20.iloc[-1] if vol_ma20.iloc[-1] > 0 else 1.0

            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]
            amplitude = (recent['high'].max() - recent['low'].min()) / recent['low'].min()

            # =================================================================
            # 🛑 🛡️ V14 门阀层：基于真实数据流水的【四维硬熔断门槛】
            # =================================================================
            # 门槛 1：均线斜率硬防线 —— 彻底剔除长期走平、踩上去不弹的死狗股
            if ma_slope < 0.025: continue 

            # 门槛 2：洗盘跌速硬防线 —— 彻底剔除慢吞吞阴跌、毫无反弹爆发力的磨洋工股
            if drop_velocity > -0.08: continue 

            # 门槛 3：量能纯净度硬防线 —— 坚决拦截放量破位砸盘、存在主力出逃嫌疑的风险股
            if curr_vol_ratio > 0.95: continue 

            # 门槛 4：波动基调硬防线 —— 拒绝过去半年死气沉沉、没有资金反复运作的低波动死水
            if amplitude < 0.50: continue 

            # 🧬 维度 A：真实主力波段爆发基因
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.12: continue  

            # 基础形态校验
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            polarity_confirmed = was_resistance and crossover.any()

            dist_close = (recent['close'] - recent_ma) / recent_ma
            dist_low = (recent['low'] - recent_ma) / recent_ma
            near_long_ma = (((dist_close >= -0.05) & (dist_close <= 0.035)) | ((dist_low >= -0.06) & (dist_low <= 0.02)))
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()
            
            if valid_deep_touches > 20: continue 

            # ==========================================
            # ⚖️ 非线性评分矩阵系统 (Scoring V14)
            # ==========================================
            score = 100.0  
            
            # 1. 活跃振幅极致增益
            if amplitude > 1.20:    score += 55.0   
            elif amplitude < 0.65:  score -= 40.0   

            # 2. 缩量急跌交叉高分奖赏
            if drop_velocity < -0.15 and curr_vol_ratio < 0.60:
                score += 55.0  # 逆向对账单中 `sh600172` 型超级黄金坑特征
            
            # 3. 妖股爆发比阶梯
            if burst_ratio >= 0.40:   score += 50.0
            elif burst_ratio >= 0.25: score += 25.0

            # 4. 均线斜率平准化加分
            normalized_slope = ma_slope * (ma_period / 60.0)
            if normalized_slope > 0.05: score += 40.0

            # 5. 触碰频次调和
            if 3 <= valid_deep_touches <= 9: score += 30.0

            if polarity_confirmed: score += 20.0
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            score -= crosses * 4

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed, 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.985),
                    'ma_slope': float(ma_slope),
                    'drop_velocity': float(drop_velocity)
                }

        # 🛑 【终极风控大闸】：将及格线由 45分 强行拉高至 100分！平庸股票绝不放行！
        if best_ma is None or highest_score < 100:   
            return None

        # 4. 全时序动量条件生成
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

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

        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)

        return signal_series

    except Exception:
        return None

def apply_adaptive_ma_support_optimized_V13(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V13 原始特征多维交乘对齐版)
    根据真实数据诊断流水矩阵进行逆向重构。
    核心逻辑：利用总振幅动态增益淘汰低波大盘股，利用量速纯净度剔除放量破位单边股。
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 基础技术指标计算
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)
        vol_ma20 = df['volume'].rolling(20).mean() 

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 横向截面扫描专属均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            if ma_series.iloc[-1] < ma_series.iloc[-7] * 0.995: continue
            current_ma_val = ma_series.iloc[-1]

            if ma13_full.iloc[-1] < current_ma_val: continue

            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # 🧬 维度 A：主力主升爆发特征
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.08: continue  

            # 🧬 维度 B：均线仰角斜率
            ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]

            # 🧬 维度 C：短线急跌洗盘系数
            recent_12d_high = df['high'].iloc[-12:].max()
            drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high

            # 🧬 维度 D：120日全景总振幅 (蹦床材质)
            amplitude = (recent['high'].max() - recent['low'].min()) / recent['low'].min()

            # 🧬 维度 E：洗盘当日量比
            curr_vol_ratio = df['volume'].iloc[-1] / vol_ma20.iloc[-1] if vol_ma20.iloc[-1] > 0 else 1.0

            # 形态过滤
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            polarity_confirmed = was_resistance and crossover.any()

            dist_close = (recent['close'] - recent_ma) / recent_ma
            dist_low = (recent['low'] - recent_ma) / recent_ma
            near_long_ma = (((dist_close >= -0.05) & (dist_close <= 0.035)) | ((dist_low >= -0.06) & (dist_low <= 0.02)))
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()
            
            if valid_deep_touches > 22: continue 

            # =================================================================
            # ⚖️ V13 逆向对账单推导评分矩阵 (Matrix Slicing Logic)
            # =================================================================
            score = 100.0  # 基础基准分
            
            # 1. 降维打击低振幅死鱼票 (总振幅核心判定)
            if amplitude > 1.20:
                score += 55.0   # 确认属于高弹性、高活跃度的活跃游资标的
            elif amplitude < 0.60:
                score -= 65.0   # 属于典型的大盘重型股或磨洋工死水股，强制从前排踢出

            # 2. 量速交叉匹配校验 (纯净洗盘 vs 放量破位)
            if drop_velocity < -0.12:
                # 属于急跌恐慌洗盘通道
                if curr_vol_ratio < 0.55:
                    score += 50.0  # 极品特征：缩量完美砸坑，散户恐慌割肉，主力不动如山
                elif curr_vol_ratio > 0.95:
                    score -= 60.0  # 危险特征：急跌伴随放量，属于结构性破位溃败，坚决不接飞刀
            else:
                # 慢阴跌滑落
                if curr_vol_ratio > 1.1:
                    score -= 40.0

            # 3. 均线周期斜率自适应归一化平准
            normalized_slope = ma_slope * (ma_period / 60.0)
            if normalized_slope > 0.04:
                score += 40.0
            elif normalized_slope < 0.002:
                score -= 45.0

            # 4. 触碰次数抛物线调和
            if 3 <= valid_deep_touches <= 9:
                score += 35.0
            elif valid_deep_touches >= 18:
                score -= 50.0

            # 5. 形态溢价
            if polarity_confirmed: score += 25.0

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed, 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.985),
                    'ma_slope': float(ma_slope),
                    'drop_velocity': float(drop_velocity)
                }

        if best_ma is None or highest_score < 80:   
            return None

        # 4. 全时序动量条件生成
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

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

        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)

        return signal_series

    except Exception:
        return None

def apply_adaptive_ma_support_optimized_V12(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V12 动态解耦弹性矩阵版)
    解决硬熔断过密导致个股输出为0的死锁问题。
    将严格的风控逻辑从“硬熔断”释放到“非线性得分体系”中，用 Top 20 截面排序做最终防线。
    """
    if len(df) < 250: # 恢复基础样本窗口至 250
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础技术指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)
        vol_ma20 = df['volume'].rolling(20).mean() 

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 横向扫描候选专属均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            # 基座过滤：均线长线方向不能呈现严重的单边加速下坠
            if ma_series.iloc[-1] < ma_series.iloc[-7] * 0.995: continue
            current_ma_val = ma_series.iloc[-1]

            # 排列过滤：短期均线不能跌破长期专属生命线
            if ma13_full.iloc[-1] < current_ma_val: continue

            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # 🧬 维度 A：真实主力控盘主升爆发基因 (Burst Ratio)
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.08: continue  # 【松绑】：由 0.12 放宽至 0.08，给长线大底品种出线机会

            # 🧬 维度 B：均线仰角斜率 (MA Slope)
            ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]

            # 🧬 维度 C：短线急跌宣泄系数 (Drop Velocity)
            recent_12d_high = df['high'].iloc[-12:].max()
            drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high

            # 极性转换校验
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > recent['volume'].rolling(20).mean() * 1.5)
            has_breakthrough = breakthrough.any()
            
            has_valid_retest = False
            post_breakthrough = recent[crossover.cumsum() > 0]
            if not post_breakthrough.empty and len(post_breakthrough) > 8:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (post_breakthrough['low'] <= post_ma * 1.018) & (post_breakthrough['close'] >= post_ma * 0.98)
                has_valid_retest = valid_retest.sum() >= 1

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 深踩触碰结构计算
            dist_close = (recent['close'] - recent_ma) / recent_ma
            dist_low = (recent['low'] - recent_ma) / recent_ma
            near_long_ma = (
                ((dist_close >= -0.05) & (dist_close <= 0.035)) | 
                ((dist_low >= -0.06) & (dist_low <= 0.02))
            )
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()
            
            if valid_deep_touches > 25: continue # 恢复硬风控门槛为 25

            # ==========================================
            # ⚖️ 非线性多维矩阵评分系统 (Scoring V12 - 解耦版)
            # ==========================================
            score = 0
            
            # 1. 触碰频次最优抛物线打分
            if 3 <= valid_deep_touches <= 9:   score += 50
            elif 10 <= valid_deep_touches <= 14: score += 20
            elif valid_deep_touches >= 20:       score -= 50

            # 2. 妖股爆发爆发比分级加分
            if burst_ratio >= 0.40:   score += 65
            elif burst_ratio >= 0.25: score += 35
            elif burst_ratio < 0.12:  score -= 25

            # 3. 专属生命线斜率弹性加分 (【核心解耦】：移除硬熔断，转为阶梯打分)
            if ma_slope > 0.04:     score += 45
            elif ma_slope > 0.015:  score += 20
            elif ma_slope < -0.005: score -= 45  # 负斜率（下倾趋势）扣分

            # 4. 恐慌盘急跌洗盘宣泄度打分 (【核心解耦】：转为阶梯打分，不破坏地量)
            if drop_velocity < -0.14:   score += 45  # 12天跌超14%
            elif drop_velocity < -0.07: score += 20
            elif drop_velocity > -0.02: score -= 40  # 阴跌无弹性扣分

            # 5. 筹码锁定地量检验
            curr_vol_ratio = df['volume'].iloc[-1] / vol_ma20.iloc[-1]
            if curr_vol_ratio < 0.55:  score += 25  
            elif curr_vol_ratio > 1.25: score -= 25 

            # 6. 均线缠绕无效穿刺惩罚
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            score -= crosses * 4

            # 7. 微观结构多维波动与极性补偿
            if polarity_confirmed: score += 35
            recent_amplitude = (recent['high'].max() - recent['low'].min()) / recent['low'].min()
            if recent_amplitude > 0.22: score += 15 

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed, 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.985),
                    'ma_slope': float(ma_slope),
                    'drop_velocity': float(drop_velocity)
                }

        # 【恢复出线权】：调降基础出线门槛至 45 分，只要通得过基础回踩即发放出线权
        if best_ma is None or highest_score < 45:   
            return None

        # 4. 全时序动量条件生成
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

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

        # 4. 传出元数据绑定
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)

        return signal_series

    except Exception:
        return None
    
def apply_adaptive_ma_support_optimized_V12(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V12 机构全息矩阵版)
    解决 Top 20 强截断后收益退化问题。
    核心逻辑：利用专属均线仰角斜率(弹性) + 回调急跌洗盘系数(速度) + 地量阈值(筹码锁定)进行非线性重构。
    """
    if len(df) < 300: # 提升基础样本窗口以保证长期均线稳定性
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础技术指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)
        vol_ma20 = df['volume'].rolling(20).mean() 

        try:
            k, d, j = indicators.calculate_kDJ(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 横向截面扫描候选专属均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            # 基座过滤：专属生命线自身7日内不能单边掉头向下
            if ma_series.iloc[-1] < ma_series.iloc[-7]: continue
            current_ma_val = ma_series.iloc[-1]

            # 排列过滤：短期均线不能跌破长期均线
            if ma13_full.iloc[-1] < current_ma_val: continue

            recent = df.iloc[-130:].copy()
            historical = df.iloc[-250:-130].copy()
            recent_ma = ma_series.iloc[-130:]
            hist_ma = ma_series.iloc[-250:-130]

            # 🧬 维度 A：主力控盘主升爆发基因 (Burst Ratio)
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.12: continue  # 剔除无庄控盘的单边死狗股

            # 🧬 维度 B：均线仰角斜率 (MA Slope - 蹦床的弹力基准)
            # 计算过去20个交易日均线自身的斜率
            ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]

            # 🧬 维度 C：短线急跌宣泄系数 (Drop Velocity - 衡量洗盘是否干脆)
            # 回溯12天内最高价到当前的跌幅
            recent_12d_high = df['high'].iloc[-12:].max()
            drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high

            # 极性转换校验（历史压力转支撑）
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > recent['volume'].rolling(20).mean() * 1.6)
            has_breakthrough = breakthrough.any()
            
            has_valid_retest = False
            post_breakthrough = recent[crossover.cumsum() > 0]
            if not post_breakthrough.empty and len(post_breakthrough) > 8:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (post_breakthrough['low'] <= post_ma * 1.018) & (post_breakthrough['close'] >= post_ma * 0.98)
                has_valid_retest = valid_retest.sum() >= 1

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 深踩触碰收盘与最低价的矩阵计算
            dist_close = (recent['close'] - recent_ma) / recent_ma
            dist_low = (recent['low'] - recent_ma) / recent_ma
            near_long_ma = (
                ((dist_close >= -0.05) & (dist_close <= 0.035)) | 
                ((dist_low >= -0.06) & (dist_low <= 0.02))
            )
            deep_step_pattern = short_broken_full.iloc[-130:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()
            
            if valid_deep_touches > 22: continue # 熔断：拒绝在均线附近反复摩擦的死鱼票

            # ==========================================
            # ⚖️ 非线性多维矩阵评分系统 (Scoring V12)
            # ==========================================
            score = 0
            
            # 1. 触碰频次最优抛物线打分
            if 4 <= valid_deep_touches <= 10:
                score += 65   # 真龙洗盘通常点到即止（黄金区间）
            elif 11 <= valid_deep_touches <= 15:
                score += 25   # 常规震荡
            elif valid_deep_touches >= 19:
                score -= 60   # 强力惩罚粘连废股

            # 2. 妖股爆发爆发比分级加分
            if burst_ratio >= 0.45:   score += 80  # 极品股性，具备连板基因
            elif burst_ratio >= 0.25: score += 45  # 标准中线主升浪
            elif burst_ratio < 0.15:  score -= 30  # 股性较沉闷

            # 3. 专属生命线斜率弹性加分 (均线不下倾)
            if ma_slope > 0.05:     score += 50  # 强多头陡峭均线，提供极强蹦床反弹力
            elif ma_slope > 0.02:   score += 20
            elif ma_slope < 0.005:  score -= 55  # 均线基本走平，缺乏承接动能，重罚

            # 4. 恐慌盘急跌洗盘宣泄度打分
            if drop_velocity < -0.16:   score += 50  # V型急跌，浮筹极速出局，反弹极速
            elif drop_velocity < -0.08: score += 20  # 正常回踩
            elif drop_velocity > -0.03: score -= 45  # 阴跌赖在均线不走，毫无爆发弹性

            # 5. 筹码锁定地量检验
            curr_vol_ratio = df['volume'].iloc[-1] / vol_ma20.iloc[-1]
            if curr_vol_ratio < 0.48:  score += 25  # 极度缩量洗盘，主力锁筹明显
            elif curr_vol_ratio > 1.3: score -= 30  # 破位放量，存在主力弃庄嫌疑

            # 6. 均线缠绕无效穿刺惩罚
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            score -= crosses * 4

            # 7. 微观结构多维波动补偿
            recent_amplitude = (recent['high'].max() - recent['low'].min()) / recent['low'].min()
            if recent_amplitude > 0.25: score += 20 # 高弹性高振幅标的加分

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed, 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.985),
                    'ma_slope': float(ma_slope),
                    'drop_velocity': float(drop_velocity)
                }

        # 调高精品门槛线至 75 分
        if best_ma is None or highest_score < 75:   
            return None

        # 3. 全时序动量条件生成
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

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

        # 4. 传出元数据绑定
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)

        return signal_series

    except Exception:
        return None
    
def apply_adaptive_ma_support_optimized_V11(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V11 动能斜率矩阵版)
    引入【均线仰角斜率】与【短线急跌系数】降维打击高分死鱼票
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)
        vol_ma20 = df['volume'].rolling(20).mean() 

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 遍历候选均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            if ma_series.iloc[-1] < ma_series.iloc[-7]:
                continue
            current_ma_val = ma_series.iloc[-1]

            if ma13_full.iloc[-1] < current_ma_val:
                continue

            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # 🧬 基因 A：真实爆发力 (近 45 天)
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            if burst_ratio < 0.06:
                continue

            # 🧬 基因 B：均线仰角斜率 (MA Slope - 衡量蹦床弹性)
            # 计算 20 天前该均线的位置与现在的涨幅差异
            ma_slope = (current_ma_val - ma_series.iloc[-20]) / ma_series.iloc[-20]

            # 🧬 基因 C：回调急跌系数 (Drop Velocity - 衡量洗盘凶悍度)
            # 计算最近 12 天的最高点到今天的跌幅
            recent_12d_high = df['high'].iloc[-12:].max()
            drop_velocity = (df['close'].iloc[-1] - recent_12d_high) / recent_12d_high

            # 极性转换校验
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > recent['volume'].rolling(20).mean() * 1.6)
            has_breakthrough = breakthrough.any()
            has_valid_retest = False
            post_breakthrough = recent[crossover.cumsum() > 0]
            if not post_breakthrough.empty and len(post_breakthrough) > 8:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (post_breakthrough['low'] <= post_ma * 1.018) & (post_breakthrough['close'] >= post_ma * 0.98)
                has_valid_retest = valid_retest.sum() >= 1

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 深踩结构计算
            dist_close = (recent['close'] - recent_ma) / recent_ma
            dist_low = (recent['low'] - recent_ma) / recent_ma
            near_long_ma = (
                ((dist_close >= -0.05) & (dist_close <= 0.035)) | 
                ((dist_low >= -0.06) & (dist_low <= 0.02))
            )
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()
            
            if valid_deep_touches > 25:
                continue

            # ==========================================
            # ⚖️ 非线性评分系统 (V11 全息降维打击版)
            # ==========================================
            score = 0
            
            # 【维度 1：触碰次数打分】
            if 3 <= valid_deep_touches <= 9: score += 50
            elif 10 <= valid_deep_touches <= 14: score += 20
            elif valid_deep_touches >= 20: score -= 60
            else: score += valid_deep_touches * 2

            # 【维度 2：妖股基因阶梯】
            if burst_ratio >= 0.40: score += 60
            elif burst_ratio >= 0.25: score += 35
            elif burst_ratio >= 0.15: score += 15
            elif burst_ratio < 0.08: score -= 40

            # 🌟【新增维度 3：均线仰角斜率 (蹦床弹性)】🌟
            if ma_slope > 0.06:
                score += 45   # 均线陡峭向上，极强支撑弹簧
            elif ma_slope > 0.03:
                score += 20
            elif ma_slope < 0.01:
                score -= 50   # 均线走平或向下，必定破位阴跌，重罚！

            # 🌟【新增维度 4：回调急跌系数 (V型反转基因)】🌟
            if drop_velocity < -0.15:
                score += 45   # 12天内暴跌超15%，恐慌盘宣泄极易V反
            elif drop_velocity < -0.08:
                score += 20   # 正常强势洗盘
            elif drop_velocity > -0.04:
                score -= 50   # 阴跌或横盘慢跌蹭到均线，毫无弹力 (L型死鱼)

            # 【维度 5：极性与缩量】
            if polarity_confirmed: score += 30
            curr_vol_ratio = df['volume'].iloc[-1] / vol_ma20.iloc[-1]
            if curr_vol_ratio < 0.5: score += 20
            elif curr_vol_ratio > 1.2: score -= 30 
                
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            score -= crosses * 4
            # =================================================================
            # ⚖️ 非线性评分系统 V12 (前台执行力与未成交微观归因补丁)
            # =================================================================
            # 在之前计算完 score 之后，针对未成交/成交边界进行前台模拟优化
            
            # 【核心注入：前台微观挂单宽容度矩阵】
            # 我们根据当前个股的盘中极限波幅，以及它距离均线支撑的吸附力进行打分
            
            # 1. 拦截左侧单边暴跌飞刀 (如果在回测中频繁触发防飞刀，说明个股处于断崖期，扣除前台期望分)
            if 'df_index' in locals() and curr_vol_ratio > 1.5 and dist_close.iloc[-1] < -0.03:
                score -= 40  # 量能异常且属于冰点破位，前台不予优先挂单
                
            # 2. 增强“弹性波动基因”打分
            # 区间振幅代表股票被错杀砸到均线后的“深V反弹活性”
            recent_amplitude = (recent['high'].max() - recent['low'].min()) / recent['low'].min()
            if recent_amplitude > 0.25:
                score += 35  # 超高弹性股，一旦触发成交，反弹动能极大，优先靠前排序
            elif recent_amplitude > 0.15:
                score += 15

            # 3. 专属生命线共振加分
            # 统计发现，MA120(半年线)和MA240(年报牛熊线)回踩产生的V反概率远大于短线均线
            if ma_period in [120, 240]:
                score += 20  # 机构大长线支撑共振加分

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed, 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.98),
                    'ma_slope': float(ma_slope),            # 向外抛出新特征
                    'drop_velocity': float(drop_velocity)   # 向外抛出新特征
                }

        # 及格线提高，淘汰弱势股
        if best_ma is None or highest_score < 70:   
            return None

        # 4. 全时序动量条件生成
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

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

        # 抛出全部基因变量供下游回测记录
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)
        signal_series.ma_slope = best_details.get('ma_slope', 0.0)
        signal_series.drop_velocity = best_details.get('drop_velocity', 0.0)

        return signal_series

    except Exception as e:
        return None
    
def apply_adaptive_ma_support_optimized_e(df):
    """
    V8.0 多周期阶梯共振重构版：
    第一阶梯：宽开口提取满足均线贴合与右侧主升爆发特征的标的。
    第二阶梯：利用周线大级别主跌浪硬熔断 + 日线密集深踩惩罚，强力排除到期阴跌和左侧破位个股。
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120]
        tolerance_upper = 0.022
        tolerance_lower = -0.019

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算核心全局指标
        macd, _, macdhist = talib.MACD(df['close'], 8, 21, 6)
        ma13 = talib.MA(df['close'], 13)
        ma30 = talib.MA(df['close'], 30)
        volume_ma20 = df['volume'].rolling(20).mean()

        try:
            _, _, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except:
            j = pd.Series(50, index=df.index)

        # --------------------------------------------------
        # 【第一阶梯：形态高包容初选池】
        # --------------------------------------------------
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            # 大基座趋势：专属均线不能呈现明显的单边加速下坠
            if ma_series.iloc[-1] < ma_series.iloc[-25] * 0.98: continue

            recent = df.iloc[-140:]
            recent_ma = ma_series.iloc[-140:]

            # 核心爆发基因回溯（没有波段爆发，说明没有控盘资金，判定为纯左侧阴跌）
            high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (high_45 - ma_series.iloc[-1]) / ma_series.iloc[-1]

            if burst_ratio < 0.10:  # 严格排除低于10%无动能死狗个股
                continue

            # 计算深踩结构与高频触碰特征
            near_ma = abs(recent['close'] - recent_ma) / recent_ma <= 0.026
            short_broken = (recent['close'] < ma13.iloc[-140:]) & (recent['close'] < ma30.iloc[-140:])
            valid_deep_touches = (short_broken & near_ma).sum()

            # 量能衰减状态评估
            vol_on_touch = recent['volume'][near_ma].mean() if valid_deep_touches > 0 else 0
            vol_ratio = vol_on_touch / volume_ma20.iloc[-140:].mean() if vol_on_touch > 0 else 2.0

            # 极性转换特征
            polarity_score = 35 if (recent['close'].shift(1) < recent_ma.shift(1)).any() and (recent['close'] > recent_ma).any() else 0

            # ⚙️ 逻辑纠正：健康的深踩回踩次数在 3 ~ 12 次之间最坚固
            # 超过 15 次密集粘连说明跌破并赖着不走，从加分项转为严重的“死鱼惩罚项”
            if 3 <= valid_deep_touches <= 12:
                touch_score = valid_deep_touches * 8
            elif valid_deep_touches > 15:
                touch_score = (12 * 8) - (valid_deep_touches - 15) * 12  # 重罚长期趴在底部的废股
            else:
                touch_score = valid_deep_touches * 4

            score = touch_score + polarity_score

            # 爆发力阶梯加分
            if burst_ratio >= 0.18: score += 55
            elif burst_ratio >= 0.13: score += 30

            # 缩量回调加分
            if vol_ratio < 1.3: score += 25
            elif vol_ratio > 2.0: score -= 35

            # MA30深度洗盘状态追踪
            is_deep_wash = ma30.iloc[-1] < ma_series.iloc[-1] * 0.98
            if is_deep_wash:
                score -= 30

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'burst_ratio': round(burst_ratio, 3),
                    'vol_ratio': round(vol_ratio, 2),
                    'deep_touches': int(valid_deep_touches),
                    'is_deep_wash': is_deep_wash
                }

        # 初选出线门槛
        if best_ma is None or highest_score < 65:
            return None

        # --------------------------------------------------
        # 【第二阶梯：多周期大级别共振硬熔断防线】
        # --------------------------------------------------
        # 1. 拦截日线多头崩溃票：如果最近5天创出新低，且MA13/MA30呈现倾斜向下的单边空头加速发散
        if df['close'].iloc[-1] == df['close'].iloc[-5:].min() and ma13.iloc[-1] < ma30.iloc[-1] and ma30.iloc[-1] < ma30.iloc[-5]:
            return None

        # 2. 拦截周线级别大熊市主跌浪（多周期共振）
        is_weekly_safe, weekly_reason = check_weekly_trend_safe(df)
        if not is_weekly_safe:
            return None

        # 3. 严格的盘口超卖见底确认
        j_low = j.iloc[-12:].min() < 22  # 12天内必须狠砸出过深坑
        j_turn = (j > j.shift(1)).iloc[-6:].any()  # 动量拐头
        macd_ok = macdhist.iloc[-1] > macdhist.iloc[-3]  # MACD空头衰竭
        
        if not (j_low and j_turn and macd_ok):
            return None

        # --------------------------------------------------
        # 4. 买点信号输出与元数据绑定
        # --------------------------------------------------
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        signal_series = pd.Series(False, index=df.index)
        if is_near.iloc[-1] and df['close'].iloc[-1] > best_ma_series.iloc[-1] * 0.978:
            signal_series.iloc[-1] = True

        # 动态传递状态变量
        signal_series.best_ma_period = int(best_ma)
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)

        return signal_series

    except Exception as e:
        logger.error(f"V8阶梯多周期共振策略异常: {e}", exc_info=True)
        return None

def apply_adaptive_ma_support_optimized_d(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略（V4.5 阶梯式过滤版）
    不搞一票否决，通过时序和排列特征动态切换“常规档/深踩档”条件单
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 遍历候选均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            # 【阶梯一：大基座趋势过滤（不拦截假死叉）】
            # 只要均线整体方向不是单边向下（近20天内跌幅不超过均线自身价值的1.5%）即可进入池子
            if ma_series.iloc[-1] < ma_series.iloc[-20] * 0.985:
                continue

            current_ma_val = ma_series.iloc[-1]

            # 截取评估区间
            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # 极性转换校验（历史压力位特征）
            was_resistance = (historical['close'] < hist_ma).mean() > 0.58
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            has_breakthrough = crossover.any()

            # 深踩结构与触碰次数
            near_long_ma = (abs(recent['close'] - recent_ma) / recent_ma) <= 0.03
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()

            # 过滤在底部长线处横盘太久的死鱼
            if valid_deep_touches > 25:
                continue

            # --------------------------------------------------
            # 【阶梯二：精细化分层打分引擎（不淘汰，只动态区分）】
            # --------------------------------------------------
            score = valid_deep_touches * 5
            if was_resistance and has_breakthrough:
                score += 50
                
            # 特征分流：判定是否属于“MA30假死叉型”深度洗盘
            is_deep_wash = ma30_full.iloc[-1] < current_ma_val
            
            if is_deep_wash:
                # 深度洗盘票降级初始分（防止泥沙俱下），但通过后面的动能和爆发重新赢回分数
                score -= 15  
            else:
                score += 25  # 均线系统依然维持完美多头，属于标准常规回踩，大加分

            # 检查过去30天内个股是否具备“右侧爆发基因”（最高价脱离均线幅度）
            recent_high_30 = df['high'].iloc[-30:].max()
            burst_ratio = (recent_high_30 - current_ma_val) / current_ma_val
            if burst_ratio >= 0.12:
                score += 30  # 近期爆发极强，属于典型游资/庄股黄金坑，强力加分
            elif burst_ratio < 0.05:
                score -= 40  # 近期一潭死水，属于纯左侧阴跌或弃庄票，重罚分

            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            score -= crosses * 3  # 无效穿刺惩罚

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': was_resistance and has_breakthrough,
                    'deep_touches': int(valid_deep_touches),
                    'is_deep_wash': is_deep_wash # 将这个状态机标记传出去
                }

        # 动态门槛调降：只要有爆发基因支撑，40分即可出线，防止优质黄金坑流失
        if best_ma is None or highest_score < 38:   
            return None

        # 3. 动量反转全时序生成
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 28) | (j.shift(1) < 15)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        # 最终信号网格
        signal_series = (
            short_broken_full & 
            is_near_ma_full & 
            momentum_reversal_series & 
            (df['close'] > best_ma_series * 0.982)
        )

        if not signal_series.iloc[-1]:
            return None

        # 4. 动态元数据绑定：将阶梯策略结果直接挂载在 Series 上，供外层执行卡调度
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False) # 传给外层

        return signal_series

    except Exception as e:
        logger.error(f"阶梯式自适应策略异常: {e}", exc_info=True)
        return None

def apply_adaptive_ma_support_optimized_c(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略（左侧硬熔断防踩踏版）
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 遍历候选均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            # --- 🛡️ 熔断层 1：长期趋势定性 ---
            if ma_series.iloc[-1] < ma_series.iloc[-20]:
                continue

            current_ma_val = ma_series.iloc[-1]

            # --- 🛡️ 熔断层 2：均线多头排列硬熔断 (拦截阴跌左侧票的核心) ---
            # 如果中期的 MA30 已经跌到了长期专属均线下方，属于绝对的左侧单边阴跌趋势，直接熔断
            if ma30_full.iloc[-1] < current_ma_val:
                continue

            # --- 🛡️ 熔断层 3：近期爆发力回溯硬熔断 (拦截无量盘整死鱼票) ---
            # 过去 30 个交易日内，最高价必须明显脱离过均线（涨幅 > 8%），确认曾是右侧强势股
            recent_high_30 = df['high'].iloc[-30:].max()
            if (recent_high_30 - current_ma_val) / current_ma_val < 0.08:
                continue

            # 3. 截取评估区间
            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # 极性转换校验
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > recent['volume'].rolling(20).mean() * 1.6)
            has_breakthrough = breakthrough.any()

            has_valid_retest = False
            post_breakthrough = recent[crossover.cumsum() > 0]
            if not post_breakthrough.empty and len(post_breakthrough) > 8:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (post_breakthrough['low'] <= post_ma * 1.018) & (post_breakthrough['close'] >= post_ma * 0.98)
                has_valid_retest = valid_retest.sum() >= 1

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 深踩结构计算
            near_long_ma = (abs(recent['close'] - recent_ma) / recent_ma) <= 0.028
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()

            # 熔断：长期趴在均线附近的废股
            if valid_deep_touches > 20:
                continue

            # 评分机制
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            score = valid_deep_touches * 4  
            if polarity_confirmed: score += 65
            score -= crosses * 4 # 提高穿刺惩罚权重

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {'polarity_confirmed': polarity_confirmed, 'deep_touches': int(valid_deep_touches)}

        if best_ma is None or highest_score < 45:   
            return None

        # 4. 全时序动量条件生成 (回测安全版)
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        signal_series = (
            short_broken_full & 
            is_near_ma_full & 
            momentum_reversal_series & 
            (df['close'] > best_ma_series * 0.982) &
            (ma30_full > best_ma_series) # 信号点同样增加多头防线检查
        )

        if not signal_series.iloc[-1]:
            return None

        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.vol_ratio = 0.8  # 预置占位

        return signal_series

    except Exception as e:
        logger.error(f"增强版策略异常: {e}", exc_info=True)
        return None
# =====================================================================
# === Phase 1 自适应均线右侧深踩选股策略 (Grok 强化版) ===
#版本收益一般
# =====================================================================
def apply_adaptive_ma_support_optimized_b(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略（全向量化回测兼容版）
    结合了 Grok 的极性转换逻辑 + 修复了历史回测信号失真 + 引入了"死鱼"剔除机制
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局指标 (Vectorized for backtesting)
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 动量反转的全历史布尔序列 (解决回测失效的核心)
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        # 允许 J 值在最近6天内发生过拐头
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent
        #动量极值反转
        macd_bottom = macdhist.iloc[-120:]
        macd_improving = (macd_bottom > macd_bottom.shift(1)) & (macd_bottom < 0)
        momentum_reversal = bool(
            (macd_improving.any() or j_turning.any()) and j_turning.iloc[-6:].any()
        )
        # 短线破位序列 (全历史)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)

        # 2. 遍历寻找专属生命线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            # 长期趋势必须向上
            if ma_series.iloc[-1] < ma_series.iloc[-20]:
                continue

            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # 【极性转换评估】
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            
            # 放量突破
            vol_ma20 = recent['volume'].rolling(20).mean()
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > vol_ma20 * 1.6)
            has_breakthrough = breakthrough.any()

            has_valid_retest = False
            post_breakthrough = recent[crossover.cumsum() > 0]
            if not post_breakthrough.empty and len(post_breakthrough) > 8:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (
                    (post_breakthrough['low'] <= post_ma * 1.018) & 
                    (post_breakthrough['close'] >= post_ma * 0.98)
                )
                has_valid_retest = valid_retest.sum() >= 1

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 【深踩结构与平底锅熔断】
            near_long_ma = (abs(recent['close'] - recent_ma) / recent_ma) <= 0.028
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()

            # 熔断：如果在长线附近趴了太久（>22天），说明股性已死，直接跳过
            if valid_deep_touches > 22:
                continue
            
            # 【穿刺与量能评估】
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            vol_on_retest = recent['volume'][deep_step_pattern].mean() if valid_deep_touches > 0 else 0
            vol_ratio = vol_on_retest / vol_ma20.mean() if vol_on_retest > 0 else 999

            # 【打分系统重构】
            # 适度奖励深踩（证明支撑有效），但重赏极性转换
            score = valid_deep_touches * 4  
            if polarity_confirmed:
                score += 65
            elif has_valid_retest:
                score += 25
            
            score -= crosses * 3 # 严惩反复无效穿刺
            
            # 评价最后几天的动能
            if momentum_reversal_series.iloc[-5:].any():
                score += 20
                
            # 缩量回踩加分
            if 0.3 < vol_ratio < 1.5:
                score += 15

            # 保存最佳 MA
            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed,
                    'valid_deep_touches': int(valid_deep_touches),
                    'crosses': int(crosses),
                    'vol_ratio': round(vol_ratio, 2)
                }

        # 提高门槛：动态门槛，必须有一定的确信度才通过
        if best_ma is None or highest_score < 60:   
            return None
        # 新增：要求有明显动量反转 + 极性或高深踩次数
        if not momentum_reversal_series.iloc[-5].any() or (not polarity_confirmed and valid_deep_touches < 3):
            if highest_score < 65:   # 极性未确认时要求更高分数
                return None
        # 在循环内或最终判断前
        ma30 = talib.MA(df['close'], timeperiod=30)
        if ma30.iloc[-1] < ma30.iloc[-10]:   # 中期均线必须向上
            return None  # 或大幅扣分
        # =======================================================
        # 3. 生成全历史的信号序列 (完美支持 backtester 算胜率)
        # =======================================================
        best_ma = int(best_ma)
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        # 历史买点信号：跌破短线 + 靠近专属长线 + 动量反转 + 收盘不深跌
        signal_series = (
            short_broken_full & 
            is_near_ma_full & 
            momentum_reversal_series & 
            (df['close'] > best_ma_series * 0.982)
        )

        # 如果最后一天没有触发，直接返回 None (过滤掉历史牛股但今天没买点的标的)
        if not signal_series.iloc[-1]:
            return None

        # 绑定元数据（供主控提取）
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('valid_deep_touches', 0)
        signal_series.vol_ratio = best_details.get('vol_ratio', 0)
                # ==================== 入场价格评估 ====================
        price_eval = evaluate_adaptive_entry_price(
            df, best_ma, polarity_confirmed, 
            best_details.get('valid_deep_touches', 0), 
            best_ma_series.iloc[-1]
        )
        
        signal_series.recommended_entry = price_eval['recommended_entry']
        signal_series.aggressive_entry = price_eval['aggressive_entry']
        signal_series.conservative_entry = price_eval['conservative_entry']
        signal_series.expected_rebound = price_eval['expected_rebound']
        signal_series.price_risk_level = price_eval['risk_level']
        return signal_series

    except Exception as e:
        logger.error(f"自适应均线深踩策略异常: {e}", exc_info=True)
        return None
    
def apply_adaptive_ma_support_optimized_a(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略（左侧硬熔断防踩踏版）
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 遍历候选均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            # --- 🛡️ 熔断层 1：长期趋势定性 ---
            #过滤有效
            if ma_series.iloc[-1] < ma_series.iloc[-7]:
                continue

            current_ma_val = ma_series.iloc[-1]

            # --- 🛡️ 熔断层 2：均线多头排列硬熔断 (拦截阴跌左侧票的核心) ---
            # 如果中期的 MA30 已经跌到了长期专属均线下方，属于绝对的左侧单边阴跌趋势，直接熔断
            #没有起作用
            if ma13_full.iloc[-1] < current_ma_val:
                continue

            # --- 🛡️ 熔断层 3：近期爆发力回溯硬熔断 (拦截无量盘整死鱼票) ---
            # 过去 13 个交易日内，最高价必须明显脱离过均线（涨幅 > 8%），确认曾是右侧强势股
            #可以过滤部分
            recent_high_13 = df['high'].iloc[-13:].max()
            if (recent_high_13 - current_ma_val) / current_ma_val < 0.08:
                continue

            # 3. 截取评估区间
            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # 极性转换校验
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > recent['volume'].rolling(20).mean() * 1.6)
            has_breakthrough = breakthrough.any()

            has_valid_retest = False
            post_breakthrough = recent[crossover.cumsum() > 0]
            if not post_breakthrough.empty and len(post_breakthrough) > 8:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (post_breakthrough['low'] <= post_ma * 1.018) & (post_breakthrough['close'] >= post_ma * 0.98)
                has_valid_retest = valid_retest.sum() >= 1

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 深踩结构计算
            # 分别计算收盘价和最低价距离专属均线的乖离率
            dist_close = (recent['close'] - recent_ma) / recent_ma
            dist_low = (recent['low'] - recent_ma) / recent_ma
            # 重新定义“靠近长线均线 (near_long_ma)”的条件：
            # 条件A (实体震荡)：收盘价在均线下方 5% 到上方 3.5% 之间 (容忍主力凶狠的砸盘破位)
            # 条件B (长下影线)：最低价曾经砸穿或靠近均线 (距离 -6% 到 +2%)，无论收盘价拉多高，都算有效触碰
            near_long_ma = (
                ((dist_close >= -0.05) & (dist_close <= 0.035)) | 
                ((dist_low >= -0.06) & (dist_low <= 0.02))
            )
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()
            # 熔断：长期趴在均线附近的废股
            # 25 明显改善
            if valid_deep_touches > 25:
                continue

            # 评分机制
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            score = valid_deep_touches * 4  
            if polarity_confirmed: score += 65
            score -= crosses * 4 # 提高穿刺惩罚权重

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {'polarity_confirmed': polarity_confirmed, 'deep_touches': int(valid_deep_touches)}

        if best_ma is None or highest_score < 45:   
            return None

        # 4. 全时序动量条件生成 (回测安全版)
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        signal_series = (
            short_broken_full & 
            is_near_ma_full & 
            momentum_reversal_series & 
            (df['close'] > best_ma_series * 0.982) &
            (ma30_full > best_ma_series) # 信号点同样增加多头防线检查
        )

        if not signal_series.iloc[-1]:
            return None

        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.vol_ratio = 0.8  # 预置占位

        return signal_series

    except Exception as e:
        logger.error(f"增强版策略异常: {e}", exc_info=True)
        return None

def apply_adaptive_ma_support_optimized_x_V10(df):
    """
    V10.0 最终极简版：真实深踩 + 强爆发 + 健康中期趋势
    """
    if len(df) < 300:
        return None

    try:
        ma_candidates = [60, 90, 120]
        tolerance_upper = 0.022
        tolerance_lower = -0.019

        macd, _, macdhist = talib.MACD(df['close'], 8, 21, 6)
        ma13 = talib.MA(df['close'], 13)
        ma30 = talib.MA(df['close'], 30)
        ma60 = talib.MA(df['close'], 60)
        vol_ma20 = df['volume'].rolling(20).mean()

        try:
            _, _, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except:
            j = pd.Series(50, index=df.index)

        best_ma = None
        highest_score = -999
        best_details = {}

        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            if ma_series.iloc[-1] < ma_series.iloc[-25] * 0.965: continue

            recent = df.iloc[-140:]
            recent_ma = ma_series.iloc[-140:]

            # 1. 真实深踩（必须有触碰）
            near_ma = (abs(recent['close'] - recent_ma) / recent_ma <= 0.027) | \
                      (abs(recent['low'] - recent_ma) / recent_ma <= 0.032)
            short_broken = (recent['close'] < ma13.iloc[-140:]) & (recent['close'] < ma30.iloc[-140:])
            deep_touches = (short_broken & near_ma).sum()
            if deep_touches < 4: continue   # 必须有真实回踩

            # 2. 强爆发基因
            high_40 = df['high'].iloc[-45:].max()
            burst_ratio = (high_40 - ma_series.iloc[-1]) / ma_series.iloc[-1]
            if burst_ratio < 0.14: continue

            # 3. 缩量回踩
            vol_ratio = recent['volume'][near_ma].mean() / vol_ma20.iloc[-140:].mean() if deep_touches > 0 else 3.0
            if vol_ratio > 1.75: continue

            # 4. 中期趋势不能太差
            if ma30.iloc[-1] < ma_series.iloc[-1] * 0.97: continue

            # 5. 动量
            j_turn = ((j > j.shift(1)) & (j < 28)).iloc[-7:].any()
            macd_ok = macdhist.iloc[-1] > macdhist.iloc[-3]
            if not (j_turn and macd_ok): continue

            score = int(burst_ratio * 80) + deep_touches * 6 + (40 if vol_ratio < 1.4 else 0)

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'burst_ratio': round(burst_ratio, 3),
                    'deep_touches': int(deep_touches),
                    'vol_ratio': round(vol_ratio, 2)
                }

        if best_ma is None or highest_score < 110:
            return None

        # 最终信号
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        signal_series = pd.Series(False, index=df.index)
        if is_near.iloc[-1] and df['close'].iloc[-1] > best_ma_series.iloc[-1] * 0.978:
            signal_series.iloc[-1] = True

        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0)
        signal_series.deep_touches = best_details.get('deep_touches', 0)

        return signal_series

    except Exception as e:
        logger.error(f"V10策略异常: {e}", exc_info=True)
        return None
        
def apply_adaptive_ma_support_optimized_x_V9(df):
    """
    V9.0 极简铁三角版：只保留最强信号，目标是高质量而非数量
    """
    if len(df) < 300:
        return None

    try:
        ma_candidates = [60, 90, 120]   # 只用中期MA
        tolerance_upper = 0.022
        tolerance_lower = -0.019

        # 全局指标
        macd, _, macdhist = talib.MACD(df['close'], 8, 21, 6)
        ma13 = talib.MA(df['close'], 13)
        ma30 = talib.MA(df['close'], 30)
        vol_ma20 = df['volume'].rolling(20).mean()

        try:
            _, _, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except:
            j = pd.Series(50, index=df.index)

        best_ma = None
        highest_score = -999
        best_details = {}

        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): continue

            if ma_series.iloc[-1] < ma_series.iloc[-25] * 0.96: continue

            recent = df.iloc[-130:]
            recent_ma = ma_series.iloc[-130:]

            # 铁三角条件1：强爆发基因（必须）
            high_40 = df['high'].iloc[-40:].max()
            burst_ratio = (high_40 - ma_series.iloc[-1]) / ma_series.iloc[-1]
            if burst_ratio < 0.13: continue   # 核心门槛

            # 铁三角条件2：有效深踩
            near_ma = abs(recent['close'] - recent_ma) / recent_ma <= 0.026
            short_broken = (recent['close'] < ma13.iloc[-130:]) & (recent['close'] < ma30.iloc[-130:])
            deep_touches = (short_broken & near_ma).sum()
            if deep_touches < 4 or deep_touches > 18: continue

            # 铁三角条件3：缩量 + 动量
            vol_ratio = recent['volume'][near_ma].mean() / vol_ma20.iloc[-130:].mean() if deep_touches > 0 else 3
            if vol_ratio > 1.8: continue   # 放量下跌不要

            # 动量严格
            j_turn = ((j > j.shift(1)) & (j < 28)).iloc[-8:].any()
            macd_ok = macdhist.iloc[-1] > macdhist.iloc[-2]
            if not (j_turn and macd_ok): continue

            # 简单评分（仅用于排序）
            score = int(burst_ratio * 100) + deep_touches * 5 + (30 if vol_ratio < 1.35 else 0)

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'burst_ratio': round(burst_ratio, 3),
                    'deep_touches': deep_touches,
                    'vol_ratio': round(vol_ratio, 2)
                }

        if best_ma is None or highest_score < 95:
            return None

        # 生成信号
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        signal_series = pd.Series(False, index=df.index)
        if is_near.iloc[-1] and df['close'].iloc[-1] > best_ma_series.iloc[-1] * 0.978:
            signal_series.iloc[-1] = True

        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0)

        return signal_series

    except Exception as e:
        logger.error(f"V9策略异常: {e}", exc_info=True)
        return None
        
def apply_adaptive_ma_support_optimized_x_V8(df):
    """
    V8.0 极简高效版：聚焦高质量机构/游资黄金坑
    核心原则：强爆发 + 动量反转 + 缩量 + 中期趋势健康
    """
    if len(df) < 300:
        return None

    try:
        ma_candidates = [60, 90, 120]   # 只保留中期MA
        tolerance_upper = 0.022
        tolerance_lower = -0.019

        best_ma = None
        highest_score = -999
        best_details = {}

        macd, _, macdhist = talib.MACD(df['close'], 8, 21, 6)
        ma13 = talib.MA(df['close'], 13)
        ma30 = talib.MA(df['close'], 30)
        vol_ma20 = df['volume'].rolling(20).mean()

        try:
            _, _, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except:
            j = pd.Series(50, index=df.index)

        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]): 
                continue

            # 基础趋势
            if ma_series.iloc[-1] < ma_series.iloc[-25] * 0.965:
                continue

            recent = df.iloc[-140:]
            recent_ma = ma_series.iloc[-140:]

            # 1. 强爆发基因（最重要）
            high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (high_45 - ma_series.iloc[-1]) / ma_series.iloc[-1]
            if burst_ratio < 0.11: 
                continue   # 无明显主升浪直接淘汰

            # 2. 深踩结构
            near_ma = abs(recent['close'] - recent_ma) / recent_ma <= 0.026
            short_broken = (recent['close'] < ma13.iloc[-140:]) & (recent['close'] < ma30.iloc[-140:])
            deep_touches = (short_broken & near_ma).sum()

            # 3. 量能（缩量优先）
            vol_on_touch = recent['volume'][near_ma].mean() if deep_touches > 0 else 0
            vol_ratio = vol_on_touch / vol_ma20.iloc[-140:].mean() if vol_on_touch > 0 else 2.5

            # 4. 极性简单确认
            polarity_ok = ((recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)).any()

            # 评分
            score = deep_touches * 8
            score += 45 if burst_ratio >= 0.18 else 25 if burst_ratio >= 0.13 else 0
            score += 30 if vol_ratio < 1.4 else -25 if vol_ratio > 2.0 else 0
            score += 35 if polarity_ok else 0

            # MA30死叉重罚
            if ma30.iloc[-1] < ma_series.iloc[-1] * 0.975:
                score -= 40

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'burst_ratio': round(burst_ratio, 3),
                    'vol_ratio': round(vol_ratio, 2),
                    'deep_touches': int(deep_touches),
                    'polarity_ok': polarity_ok
                }

        if best_ma is None or highest_score < 78:   # 高门槛
            return None

        # 严格动量反转
        j_extreme = (j < 22) | (j.shift(1) < 9)
        j_turning = (j > j.shift(1)) & j_extreme
        momentum_ok = j_turning.iloc[-7:].any() and macdhist.iloc[-1] > macdhist.iloc[-3]

        if not momentum_ok:
            return None

        # 生成信号
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        signal_series = pd.Series(False, index=df.index)
        if (is_near.iloc[-1] and 
            df['close'].iloc[-1] > best_ma_series.iloc[-1] * 0.978 and 
            momentum_ok):
            signal_series.iloc[-1] = True

        # 元数据
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0)

        return signal_series

    except Exception as e:
        logger.error(f"V8策略异常: {e}", exc_info=True)
        return None
    
def apply_adaptive_ma_support_optimized_v0(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略 (V9 非线性基因打分优化版)
    针对 Top20 资金截断痛点，大幅提高“高爆发、精简触碰”极品龙头的得分权重
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局基础指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)
        vol_ma20 = df['volume'].rolling(20).mean() # 用于缩量检验

        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 2. 遍历候选均线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            # --- 🛡️ 熔断层 1：长期趋势定性 ---
            if ma_series.iloc[-1] < ma_series.iloc[-7]:
                continue

            current_ma_val = ma_series.iloc[-1]

            # --- 🛡️ 熔断层 2：均线多头排列硬熔断 ---
            if ma13_full.iloc[-1] < current_ma_val:
                continue

            # 3. 截取评估区间
            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # --- 🧬 基因提取 1：真实爆发力 (Burst Ratio) ---
            # 扩展到 45 天，捕捉真正的主升浪基因
            recent_high_45 = df['high'].iloc[-45:].max()
            burst_ratio = (recent_high_45 - current_ma_val) / current_ma_val
            
            # 如果近45天连 6% 的波澜都没有，绝对是死狗，直接熔断
            if burst_ratio < 0.06:
                continue

            # 极性转换校验
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > recent['volume'].rolling(20).mean() * 1.6)
            has_breakthrough = breakthrough.any()

            has_valid_retest = False
            post_breakthrough = recent[crossover.cumsum() > 0]
            if not post_breakthrough.empty and len(post_breakthrough) > 8:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (post_breakthrough['low'] <= post_ma * 1.018) & (post_breakthrough['close'] >= post_ma * 0.98)
                has_valid_retest = valid_retest.sum() >= 1

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 深踩结构计算
            dist_close = (recent['close'] - recent_ma) / recent_ma
            dist_low = (recent['low'] - recent_ma) / recent_ma
            near_long_ma = (
                ((dist_close >= -0.05) & (dist_close <= 0.035)) | 
                ((dist_low >= -0.06) & (dist_low <= 0.02))
            )
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()
            
            # 绝对熔断：长期趴在底部的彻底废股
            if valid_deep_touches > 25:
                continue

            # ==========================================
            # ⚖️ 非线性评分重构系统 V10 (基于实战数据微调)
            # ==========================================
            score = 0
            
            # 【维度 A：触碰次数的黄金分割】(修复边界漏洞，重奖 4~9 次极品坑)
            if 3 <= valid_deep_touches <= 9:
                score += 65   # 绝佳买点：干脆利落的主力洗盘
            elif 10 <= valid_deep_touches <= 14:
                score += 25   # 常规震荡：稍显拖沓，给中等分
            elif 15 <= valid_deep_touches <= 19:
                score += 0    # 边缘危险：不加分
            elif valid_deep_touches >= 20:
                score -= 60   # 死鱼熔断：彻底堵死 19-20 的漏洞，重罚粘连票
            else:
                score += valid_deep_touches * 2 # 1-2次的轻微试探

            # 【维度 B：妖股基因阶梯】(根据实战爆发比拉开绝对分差)
            if burst_ratio >= 0.40:
                score += 75   # 妖股特权：曾有 >40% 的暴涨，主力极度活跃
            elif burst_ratio >= 0.25:
                score += 45   # 强主升浪：>25% 
            elif burst_ratio >= 0.15:
                score += 20   # 普通强势
            elif burst_ratio < 0.08:
                score -= 40   # 缺乏股性，重罚

            # 【维度 C：极性与形态确认】
            if polarity_confirmed: 
                score += 40
            
            # 【维度 D：缩量洗盘确认】
            curr_vol_ratio = df['volume'].iloc[-1] / vol_ma20.iloc[-1]
            if curr_vol_ratio < 0.5:
                score += 20   # 极致缩量，地量见地价
            elif curr_vol_ratio > 1.2:
                score -= 20   # 底部放量，可能是主力出逃，扣分
                
            # 【维度 E：穿刺破位惩罚】
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            score -= crosses * 4 # 提高均线缠绕的扣分权重

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed, 
                    'deep_touches': int(valid_deep_touches),
                    'burst_ratio': float(burst_ratio),  # 修复Bug：正确记录爆发比
                    'is_deep_wash': bool(ma30_full.iloc[-1] < current_ma_val * 0.98) # 修复Bug：正确记录洗盘深度
                }

        # 调高及格线：由于满分提高了，垃圾股的门槛也提高到 50 分
        if best_ma is None or highest_score < 50:   
            return None

        # 4. 全时序动量条件生成 (回测安全版)
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

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

        # 🔻 完美向外抛出所有基因变量
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('deep_touches', 0)
        signal_series.burst_ratio = best_details.get('burst_ratio', 0.0)
        signal_series.is_deep_wash = best_details.get('is_deep_wash', False)

        return signal_series

    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"增强版策略异常: {e}", exc_info=True)
        return None

def filter_by_morse_leaderboard(stock_code, eval_date, current_morse_chain, leaderboard_df):
    """
    【莫尔斯动态筛选大闸】
    依据历史大数定律，对个股的跨时空基因链进行实战通关拦截
    """
    # 1. 检查当前长链是否在历史高频爆发密码本中
    if current_morse_chain not in leaderboard_df['system_共振_code'].values:
        return False, 0.0, "未被已知黄金莫尔斯密码本收录，放弃"
        
    # 2. 提取该电码在历史上的统治力数据
    morse_row = leaderboard_df[leaderboard_df['system_共振_code'] == current_morse_chain].iloc[0]
    hist_count = morse_row['触发总次数']
    expected_pnl = morse_row['max_rebound_3d']
    
    # 3. 🎯 实战准入硬性门槛判定
    # 如果该形态属于历史上触发过（比如触发 >= 1次，随着你lookback加长可调高），且平均反弹期望大于 3%
    if hist_count >= 1 and expected_pnl >= 0.03:
        # 算出一个基于时空期望的全新优先级评分
        morse_priority_score = expected_pnl * 1000  # 比如期望 4.69% 换算为 46.9 溢价分
        return True, morse_priority_score, f"通过！历史触发 {hist_count} 次 | 期望收益: +{expected_pnl*100:.2f}%"
        
    return False, 0.0, f"被拦截：历史期望收益 (+{expected_pnl*100:.2f}%) 未达标"

# --- 配置 ---
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz', 'bj']
# --- 复权配置：'forward'=前复权, 'backward'=后复权, 'none'=不复权 ---
ADJUSTMENT_TYPE = 'forward'
# --- 您可以在这里切换要运行的策略 ---
#STRATEGY_TO_RUN = 'MACD_ZERO_AXIS' 
#STRATEGY_TO_RUN = 'TRIPLE_CROSS' 
#STRATEGY_TO_RUN = 'PRE_CROSS'
#STRATEGY_TO_RUN = 'WEEKLY_GOLDEN_CROSS_MA'
#STRATEGY_TO_RUN = 'REVERSED_SHORT' # <--- 新增的策略选项
STRATEGY_TO_RUN = 'ADAPTIVE_MA_SUPPORT'  # <--- 启用自适应均线策略

# --- 路径定义 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))

# --- 初始化日志 ---
DATE = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, STRATEGY_TO_RUN)
os.makedirs(RESULT_DIR, exist_ok=True)
LOG_FILE = os.path.join(RESULT_DIR, f'log_screener_{DATE}.txt')

file_handler = logging.FileHandler(LOG_FILE, 'a', 'utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger = logging.getLogger('screener_logger')
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()
logger.addHandler(file_handler)

# --- 全局复权处理器（多进程 worker 中通过模块级变量访问）---
_adj_processor = AdjustmentProcessor(AdjustmentConfig(adjustment_type=ADJUSTMENT_TYPE))
logger.info(f"复权模式: {ADJUSTMENT_TYPE}")


def _worker_init():
    """多进程子进程初始化：预热 gbbq 缓存，每个子进程只解密一次"""
    if ADJUSTMENT_TYPE != 'none':
        try:
            from gbbq_reader import read_gbbq
            read_gbbq()
        except Exception:
            pass

def calculate_backtest_stats(df, signal_series):
    """计算细化的回测统计信息"""
    try:
        # 计算技术指标（回测需要）
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        kdj_values = indicators.calculate_kdj(df)
        df['k'], df['d'], df['j'] = kdj_values[0], kdj_values[1], kdj_values[2]
        
        # 执行细化回测
        backtest_results = backtester.run_backtest(df, signal_series)
        
        if isinstance(backtest_results, dict) and backtest_results.get('total_signals', 0) > 0:
            stats = {
                'total_signals': backtest_results.get('total_signals', 0),
                'win_rate': backtest_results.get('win_rate', '0.0%'),
                'avg_max_profit': backtest_results.get('avg_max_profit', '0.0%'),
                'avg_max_drawdown': backtest_results.get('avg_max_drawdown', '0.0%'),
                'avg_days_to_peak': backtest_results.get('avg_days_to_peak', '0.0 天')
            }
            
            # 添加各状态统计信息
            if 'state_statistics' in backtest_results:
                stats['state_statistics'] = backtest_results['state_statistics']
            
            # 添加详细交易信息（用于进一步分析）
            if 'trades' in backtest_results:
                # 计算一些额外的统计指标
                trades = backtest_results['trades']
                if trades:
                    # 最佳表现交易
                    best_trade = max(trades, key=lambda x: x['actual_max_pnl'])
                    worst_trade = min(trades, key=lambda x: x['actual_max_pnl'])
                    
                    stats.update({
                        'best_trade_profit': f"{best_trade['actual_max_pnl']:.1%}",
                        'worst_trade_profit': f"{worst_trade['actual_max_pnl']:.1%}",
                        'avg_entry_strategy': get_most_common_entry_strategy(trades)
                    })
            
            return stats
        else:
            return {
                'total_signals': 0,
                'win_rate': '0.0%',
                'avg_max_profit': '0.0%',
                'avg_max_drawdown': '0.0%',
                'avg_days_to_peak': '0.0 天'
            }
    except Exception as e:
        logger.error(f"回测计算失败: {e}")
        return {
            'total_signals': 0,
            'win_rate': '0.0%',
            'avg_max_profit': '0.0%',
            'avg_max_drawdown': '0.0%',
            'avg_days_to_peak': '0.0 天'
        }

def get_most_common_entry_strategy(trades):
    """获取最常用的入场策略"""
    try:
        from collections import Counter
        strategies = [trade.get('entry_strategy', '未知') for trade in trades]
        most_common = Counter(strategies).most_common(1)
        return most_common[0][0] if most_common else '未知'
    except:
        return '未知'

def check_macd_zero_axis_pre_filter(df, signal_idx, signal_state, lookback_days=5):
    """
    MACD零轴启动策略的预筛选过滤器：排除五日内价格上涨超过5%的情况
    
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
        
        # 获取信号前5天的数据
        start_idx = max(0, signal_idx - lookback_days)
        end_idx = signal_idx
        
        if start_idx >= end_idx:
            return False, ""
        
        # 计算5日内的最大涨幅
        lookback_data = df.iloc[start_idx:end_idx + 1]
        if len(lookback_data) < 2:
            return False, ""
        
        # 获取5日前的收盘价和信号当天的最高价
        base_price = lookback_data.iloc[0]['close']  # 5日前收盘价
        current_high = df.iloc[signal_idx]['high']    # 信号当天最高价
        
        # 计算涨幅
        price_increase = (current_high - base_price) / base_price
        
        # 如果5日内涨幅超过5%，则排除
        if price_increase > 0.25 or price_increase < 0.05:
            return True, f"五日内涨幅{price_increase:.1%}超过25%或者低于5%，排除不活跃风险"
            #return True, f"五日内涨幅{price_increase:.1%}超过25%，排除追高风险"
        
        return False, ""
        
    except Exception as e:
        print(f"MACD零轴预筛选过滤器检查失败: {e}")
        return False, ""

def check_weekly_golden_cross_ma_filter(df, signal_idx, signal_state, stock_code):
    """
    周线金叉+日线MA策略的过滤器
    
    Args:
        df: 股票数据DataFrame
        signal_idx: 信号出现的索引
        signal_state: 信号状态 ('BUY', 'HOLD', 'SELL')
        stock_code: 股票代码
    
    Returns:
        tuple: (是否应该排除, 排除原因)
    """
    try:
        # 只对BUY信号进行严格过滤
        if signal_state != 'BUY':
            return False, ""
        
        # 1. 检查数据长度是否足够
        if len(df) < 240:  # 需要足够的数据计算MA240
            return True, "数据长度不足，无法计算长期MA"
        
        # 2. 检查价格是否过度上涨（防止追高）
        current_price = df.iloc[signal_idx]['close']
        ma13 = df['close'].rolling(window=13).mean().iloc[signal_idx]
        
        if pd.isna(ma13):
            return True, "MA13计算失败"
        
        # 价格距离MA13超过5%则排除
        price_distance = (current_price - ma13) / ma13
        if price_distance > 0.05:
            return True, f"价格距离MA13过远({price_distance:.1%})，排除追高风险"
        
        # 3. 检查成交量是否异常
        if 'volume' in df.columns:
            current_volume = df.iloc[signal_idx]['volume']
            avg_volume = df['volume'].rolling(window=20).mean().iloc[signal_idx]
            
            if not pd.isna(avg_volume) and avg_volume > 0:
                volume_ratio = current_volume / avg_volume
                # 成交量过度放大（超过5倍）可能是异常
                if volume_ratio > 5.0:
                    return True, f"成交量异常放大({volume_ratio:.1f}倍)，可能存在风险"
        
        # 4. 检查短期涨幅（5日内涨幅超过15%排除）
        if signal_idx >= 5:
            price_5_days_ago = df.iloc[signal_idx - 5]['close']
            short_term_gain = (current_price - price_5_days_ago) / price_5_days_ago
            if short_term_gain > 0.15:
                return True, f"短期涨幅过大({short_term_gain:.1%})，排除追高风险"
        
        return False, ""
        
    except Exception as e:
        logger.error(f"周线金叉+日线MA过滤器检查失败 {stock_code}: {e}")
        return True, f"过滤器执行失败: {e}"

def analyze_ma_trend(df):
    """
    分析MA趋势强度和相关指标
    
    Args:
        df: 股票数据DataFrame
    
    Returns:
        dict: 包含趋势分析结果的字典
    """
    try:
        # 计算各种MA
        ma_periods = [7, 13, 30, 45]
        mas = {}
        for period in ma_periods:
            mas[f'ma_{period}'] = df['close'].rolling(window=period).mean()
        
        current_price = df['close'].iloc[-1]
        ma13_current = mas['ma_13'].iloc[-1]
        
        # 1. 计算趋势强度（MA排列程度）
        trend_strength = 0
        if not pd.isna(ma13_current):
            # 检查MA排列：7>13>30>45
            if (mas['ma_7'].iloc[-1] > mas['ma_13'].iloc[-1] and
                mas['ma_13'].iloc[-1] > mas['ma_30'].iloc[-1] and
                mas['ma_30'].iloc[-1] > mas['ma_45'].iloc[-1]):
                trend_strength = 1.0
            elif (mas['ma_7'].iloc[-1] > mas['ma_13'].iloc[-1] and
                  mas['ma_13'].iloc[-1] > mas['ma_30'].iloc[-1]):
                trend_strength = 0.7
            elif mas['ma_7'].iloc[-1] > mas['ma_13'].iloc[-1]:
                trend_strength = 0.4
            else:
                trend_strength = 0.0
        
        # 2. 计算价格距离MA13的百分比
        ma13_distance = 0
        if not pd.isna(ma13_current) and ma13_current > 0:
            ma13_distance = (current_price - ma13_current) / ma13_current
        
        # 3. 计算成交量放大比例
        volume_surge_ratio = 1.0
        if 'volume' in df.columns and len(df) >= 20:
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]
            if not pd.isna(avg_volume) and avg_volume > 0:
                volume_surge_ratio = current_volume / avg_volume
        
        return {
            'trend_strength': trend_strength,
            'ma13_distance': ma13_distance,
            'volume_surge_ratio': volume_surge_ratio
        }
        
    except Exception as e:
        logger.error(f"MA趋势分析失败: {e}")
        return {
            'trend_strength': 0,
            'ma13_distance': 0,
            'volume_surge_ratio': 1.0
        }

def apply_morse_sniper_strategy(df_daily, df_15m=None):
    if df_daily is None or len(df_daily) < 60:
        return None
        
    try:
        # ========================================================
        # 1. 大前提：基于 RAW 数据逆向工程的 MA13 黄金起爆位
        # ========================================================
        close_t = df_daily['close'].iloc[-1]
        ma13 = df_daily['close'].rolling(13).mean().iloc[-1]
        ma13_prev5 = df_daily['close'].rolling(13).mean().iloc[-5]
        
        bias_13 = (close_t - ma13) / ma13
        slope_13 = (ma13 - ma13_prev5) / ma13_prev5
        
        # 🚨 填入纯净版跑出的绝对阈值
        BIAS_MIN = -0.048
        BIAS_MAX = 0.080
        SLOPE_MIN = -0.030

        if bias_13 < BIAS_MIN or bias_13 > BIAS_MAX:
            return None  # 剔除贴地死鱼和极度追高
            
        if slope_13 < SLOPE_MIN:
            return None  # 剔除处于加速下降通道的标的
            
        stock_position = 'MA13起爆区间'
        score = 60  # 拿到入场券的基础分
            
        # ========================================================
        # 2. 提取日线因子 (使用大样本校准的真实阈值)
        # ========================================================
        vol_ma20_d = df_daily['volume'].rolling(20).mean().iloc[-1]
        row_t1 = df_daily.iloc[-1]
        
        d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
        d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
        d_lower_shadow = (min(row_t1['close'], row_t1['open']) - row_t1['low']) / (row_t1['open'] + 1e-9)
        
        T1_U = 1 if d_pct > 0.062 else 0
        T1_D = 1 if d_pct < -0.062 else 0
        T1_d_small = 1 if -0.062 <= d_pct < -0.01 else 0
        T1_X = 1 if abs(d_pct) <= 0.01 else 0
        
        T1_L = 1 if d_vol < 0.8 else 0
        T1_H = 1 if d_vol > 1.9 else 0
        T1_B = 1 if d_lower_shadow > 0.026 else 0
        T1_T = 1 if (row_t1['high'] - max(row_t1['close'], row_t1['open'])) / (row_t1['open'] + 1e-9) > 0.03 else 0

        # ========================================================
        # 3. 提取微观 15 分钟因子 & 🚨 Grok 微观崩盘防御
        # ========================================================
        M15_U, M15_H, M15_L = 0, 0, 0
        if df_15m is not None and len(df_15m) > 20:
            vol_ma20_m15 = df_15m['volume'].rolling(20).mean().iloc[-1]
            last_15m = df_15m.iloc[-1]
            
            # 🚨 Grok 级防御：微观结构崩坏直接一票否决！
            if last_15m['close'] < last_15m['open'] * 0.985:
                return None

            m_pct = (last_15m['close'] - last_15m['open']) / (last_15m['open'] + 1e-9)
            m_vol = last_15m['volume'] / (vol_ma20_m15 + 1e-9)
            
            M15_U = 1 if m_pct > 0.0062 else 0 
            M15_H = 1 if m_vol > 2.5 else 0    
            M15_L = 1 if m_vol < 0.5 else 0     
            
            if M15_U: score += 15 

        # ========================================================
        # 4. 交叉加权打分
        # ========================================================
        if T1_U: score -= 20  
        if T1_T and T1_H: score -= 25 
        if T1_B: score += 15  
        if T1_D: score += 10  
        
        if T1_L:
            if T1_B: score += 20 
            elif T1_X and M15_U: score += 15
            elif T1_d_small or T1_D: score -= 30
            else: score -= 5
                
        if T1_D and M15_U and M15_H: score += 25

        # ========================================================
        # 5. 判定输出与【基于乖离率的三维深蹲定价】
        # ========================================================
        if score >= 85:
            # 🚨 定价逻辑重构：按乖离率和基因分层
            
            # 第一层：乖离率极高 (>5%) 且没有长下影线护体
            # 这种票属于高位接力，极其容易补跌。必须强行压低接客价，宁可踏空，绝不追高！
            if bias_13 > 0.05 and not T1_B:
                trigger_buy = close_t * 0.935  # 强压 -3.5% 防守
                
            # 第二层：遭遇大阴线核打击 (T1_D)
            # 昨天大阴线，今天惯性低开是常识。绝不能在平盘附近接刀。
            elif T1_D:
                trigger_buy = close_t * 0.915  # 强压 -3.5% 接带血筹码
                
            # 第三层：黄金洗盘坑 (有下影线 T1_B 或 尾盘抢筹 M15_U)
            # 这种票主力控盘极强，稍微一砸就会被捞起。买点必须抬高，防止踏空！
            elif T1_B:
                trigger_buy = close_t * 0.98  # 微微深蹲 -1.5% 即可
            elif M15_U:
                trigger_buy = close_t * 0.990  # 尾盘抢筹次日易高开，只让步 -1.0%
                
            # 第四层：普通常规标的
            else:
                trigger_buy = close_t * 0.955  # 常规防守 -2.5%
                
            return {
                'signal': True,
                'score': score,
                'position': stock_position,
                'trigger_price': trigger_buy
            }
        return None
        
    except Exception as e:
        return None
    
def apply_morse_sniper_strategy_V2(df_daily, df_15m=None):
    if df_daily is None or len(df_daily) < 60:
        return None
        
    try:
        # 1. 大前提：必须是多头主升
        close_t = df_daily['close'].iloc[-1]
        ma20 = df_daily['close'].rolling(20).mean().iloc[-1]
        ma60 = df_daily['close'].rolling(60).mean().iloc[-1]
        
        if close_t > ma20 and ma20 > ma60:
            stock_position = '多头主升'
            score = 60  # 基础分
        else:
            return None 
            
        # 2. 提取日线因子
        vol_ma20_d = df_daily['volume'].rolling(20).mean().iloc[-1]
        row_t1 = df_daily.iloc[-1]
        
        d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
        d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
        d_lower_shadow = (min(row_t1['close'], row_t1['open']) - row_t1['low']) / (row_t1['open'] + 1e-9)
        
        T1_U = 1 if d_pct > 0.062 else 0
        T1_D = 1 if d_pct < -0.062 else 0
        T1_d_small = 1 if -0.062 <= d_pct < -0.01 else 0
        T1_X = 1 if abs(d_pct) <= 0.01 else 0
        
        T1_L = 1 if d_vol < 0.8 else 0
        T1_H = 1 if d_vol > 1.9 else 0
        T1_B = 1 if d_lower_shadow > 0.026 else 0
        T1_T = 1 if (row_t1['high'] - max(row_t1['close'], row_t1['open'])) / (row_t1['open'] + 1e-9) > 0.03 else 0

        # 3. 提取微观 15 分钟因子 & Grok 防御
        M15_U, M15_H, M15_L = 0, 0, 0
        if df_15m is not None and len(df_15m) > 20:
            vol_ma20_m15 = df_15m['volume'].rolling(20).mean().iloc[-1]
            last_15m = df_15m.iloc[-1]
            
            # 🚨 Grok防御：如果最后一根 15 分钟是明显杀跌（弱于 -1.5%），直接一票否决防核按钮！
            if last_15m['close'] < last_15m['open'] * 0.985:
                return None

            m_pct = (last_15m['close'] - last_15m['open']) / (last_15m['open'] + 1e-9)
            m_vol = last_15m['volume'] / (vol_ma20_m15 + 1e-9)
            
            M15_U = 1 if m_pct > 0.0062 else 0 
            M15_H = 1 if m_vol > 2.5 else 0    
            M15_L = 1 if m_vol < 0.5 else 0     
            
            if M15_U: score += 15 

        # 4. 交叉加权打分
        if T1_U: score -= 20  
        if T1_T and T1_H: score -= 25 
        if T1_B: score += 15  
        if T1_D: score += 10  
        
        if T1_L:
            if T1_B: score += 20 
            elif T1_X and M15_U: score += 15
            elif T1_d_small or T1_D: score -= 30
            else: score -= 5
                
        if T1_D and M15_U and M15_H: score += 25

        # 5. 判定输出与【深蹲买点定价】
        # 🚨 Grok 级风控：及格线强行拉高到 100 分！砍掉 80% 的无效交易！
        if score >= 75:
            if T1_B:
                trigger_buy = close_t * 0.980 
            elif T1_D:
                trigger_buy = close_t * 0.965
            elif M15_U and not T1_L:
                trigger_buy = close_t * 0.990
            else:
                trigger_buy = close_t * 0.975
                
            return {
                'signal': True,
                'score': score,
                'position': stock_position,
                'trigger_price': trigger_buy
            }
        return None
        
    except Exception as e:
        return None

def apply_morse_sniper_strategy_V1(df_daily, df_15m=None):
    if df_daily is None or len(df_daily) < 60:
        return None
        
    try:
        # ---------------------------------------------------------
        # 1. 大前提：必须是多头主升 (趋势决定生死)
        # ---------------------------------------------------------
        close_t = df_daily['close'].iloc[-1]
        ma20 = df_daily['close'].rolling(20).mean().iloc[-1]
        ma60 = df_daily['close'].rolling(60).mean().iloc[-1]
        
        if close_t > ma20 and ma20 > ma60:
            stock_position = '多头主升'
            score = 60  # 基础分
        else:
            return None # 剔除所有深坑和震荡
            
        # ---------------------------------------------------------
        # 2. 提取日线因子 (使用大样本校准的真实阈值)
        # ---------------------------------------------------------
        vol_ma20_d = df_daily['volume'].rolling(20).mean().iloc[-1]
        row_t1 = df_daily.iloc[-1]
        
        d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
        d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
        d_lower_shadow = (min(row_t1['close'], row_t1['open']) - row_t1['low']) / (row_t1['open'] + 1e-9)
        
        # 实体识别
        T1_U = 1 if d_pct > 0.062 else 0
        T1_D = 1 if d_pct < -0.062 else 0
        T1_d_small = 1 if -0.062 <= d_pct < -0.01 else 0 # 小阴线/中阴线
        T1_X = 1 if abs(d_pct) <= 0.01 else 0            # 十字星/极小实体
        
        # 量能与影线
        T1_L = 1 if d_vol < 0.8 else 0                   # 极致缩量
        T1_H = 1 if d_vol > 1.9 else 0                   # 显著放量
        T1_B = 1 if d_lower_shadow > 0.026 else 0        # 强力下影线
        T1_T = 1 if (row_t1['high'] - max(row_t1['close'], row_t1['open'])) / (row_t1['open'] + 1e-9) > 0.03 else 0 # 长上影

        # ---------------------------------------------------------
        # 3. 提取微观 15 分钟因子 & 🚨 引入 Grok 微观崩盘防御
        # ---------------------------------------------------------
        M15_U, M15_H, M15_L = 0, 0, 0
        if df_15m is not None and len(df_15m) > 20:
            vol_ma20_m15 = df_15m['volume'].rolling(20).mean().iloc[-1]
            last_15m = df_15m.iloc[-1]
            
            # 🚨 Grok 级防御：微观结构崩坏直接一票否决！
            # 如果最后一根 15 分钟 K 线是一根跌幅超过 1.5% 的大阴线，说明有抢跑资金砸盘，次日极易核按钮。
            if last_15m['close'] < last_15m['open'] * 0.985:
                return None  # 直接过滤，不参与打分！

            m_pct = (last_15m['close'] - last_15m['open']) / (last_15m['open'] + 1e-9)
            m_vol = last_15m['volume'] / (vol_ma20_m15 + 1e-9)
            
            M15_U = 1 if m_pct > 0.0062 else 0 
            M15_H = 1 if m_vol > 2.5 else 0    
            M15_L = 1 if m_vol < 0.5 else 0     
            
            if M15_U: score += 15 
            if M15_L: score += 5
        # ---------------------------------------------------------
        # 🧬 4. 核心大脑：多维交叉加权打分机制 (彻底告别一刀切)
        # ---------------------------------------------------------
        
        # [单维惩罚区]
        if T1_U: score -= 20  # 昨天已经大涨(>6.2%)，今天追高接盘风险极大，重扣！
        if T1_T and T1_H: score -= 25 # 昨天放量长上影线（主力诱多出货典型），一票否决！
        
        # [单维奖励区]
        if T1_B: score += 15  # 长下影线是洗盘真神，单维直接奖励
        if T1_D: score += 10  # 主升浪里的大阴线，通常是暴力洗血筹，轻奖
        
        if M15_U: score += 15 # 尾盘显著抢筹，必须奖励
        
        # [🌟 交叉因子区：解决 T1_L 的双面刃问题]
        if T1_L:
            if T1_B:
                # 黄金坑：缩量 + 长下影。说明空头砸不动了，抛压枯竭。极品！
                score += 20 
            elif T1_X and M15_U:
                # 变盘点：全天缩量十字星 + 尾盘突然抢筹。变盘向上确立！
                score += 15
            elif T1_d_small or T1_D:
                # 毒药：缩量阴跌，无资金承接的阴跌中继。
                score -= 30
            else:
                # 其他不明状态的缩量，轻微惩罚其流动性缺失
                score -= 5
                
        # [🌟 交叉因子区：解决大阴线的买点确认问题]
        if T1_D and M15_U and M15_H:
            # 如果昨天是大阴线，但尾盘爆发出了巨量大阳线抢筹，说明错杀被纠正
            score += 25

        # ---------------------------------------------------------
        # 🎯 5. 判定输出与【基于形态的精准买点定价】
        # ---------------------------------------------------------
        # 及格线提高到 80 分！
        if score >= 80:
            
            # 价格评估机制必须跟着形态走！不能一刀切。
            
            if T1_B:
                # 既然是下影线洗盘，说明主力喜欢盘中深蹲。我们挂在昨收价下方接针。
                # 挂昨收的 -2.0%
                trigger_buy = close_t * 0.980 
                
            elif T1_D:
                # 大阴线次日极易惯性低开，绝对不能高买！
                # 必须挂昨收价的 -3.5% 接血筹
                trigger_buy = close_t * 0.965
                
            elif M15_U and not T1_L:
                # 尾盘抢筹且不是缩量死票，次日可能平开或高开。
                # 稍微让步一点，挂昨收的 -1.0%
                trigger_buy = close_t * 0.990
                
            else:
                # 默认强行下压 -2.5% 防守
                trigger_buy = close_t * 0.975
                
            return {
                'signal': True,
                'score': score,
                'position': stock_position,
                'trigger_price': trigger_buy
            }
            
        return None
        
    except Exception as e:
        return None
    
def apply_morse_sniper_strategy_V0(df_daily, df_15m=None, df_60m=None):
    """
    【全新大杀器】基于大数据真实分布阈值的 Bit位 独立加权狙击策略
    触发价格没有调整到位
    """
    if df_daily is None or len(df_daily) < 60:
        return None
        
    try:
        # 1. 确认大前提：趋势位置 (位置决定性质)
        close_t = df_daily['close'].iloc[-1]
        ma20 = df_daily['close'].rolling(20).mean().iloc[-1]
        ma60 = df_daily['close'].rolling(60).mean().iloc[-1]
        
        # 我们的统计证明，多头主升浪的胜率最高，深坑容错率极低
        if close_t > ma20 and ma20 > ma60:
            stock_position = '多头主升'
            score = 30  # 基础分
        elif close_t < ma20 * 0.93:
            stock_position = '超跌深坑'
            score = 10
        else:
            return None # 震荡市不参与，过滤垃圾时间
            
        # 2. 提取 T-1 日线关键因子
        vol_ma20_d = df_daily['volume'].rolling(20).mean().iloc[-1]
        row_t1 = df_daily.iloc[-1]
        
        # 使用真实大数据校准的日线阈值
        d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
        d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
        d_lower_shadow = (min(row_t1['close'], row_t1['open']) - row_t1['low']) / (row_t1['open'] + 1e-9)
        
        T1_U = 1 if d_pct > 0.062 else 0    # 日线大阳线(>6.2%)
        T1_D = 1 if d_pct < -0.062 else 0   # 日线大阴洗盘(<-6.2%)
        T1_L = 1 if d_vol < 0.8 else 0      # 日线极致缩量(<0.8x)
        T1_B = 1 if d_lower_shadow > 0.026 else 0 # 强力下影线(>2.6%)

        # 加权打分 (权重来源于我们统计的 净暴击分 排行榜)
        if T1_U: 
            score += 15
            #trigger_price = row_t1['open'] + (row_t1['close'] - row_t1['open']) * 0.382
        if T1_D and stock_position == '多头主升': score += 20 # 主升浪中的大阴线是绝佳暴力洗盘
        if T1_L: score += 10
        if T1_B: score += 15
        
        # 3. 提取 M15 微观基因 (最强狙击点)
        if df_15m is not None and len(df_15m) > 20:
            vol_ma20_m15 = df_15m['volume'].rolling(20).mean().iloc[-1]
            row_m15 = df_15m.iloc[-1]
            
            # 使用真实大数据校准的15分钟阈值
            m_pct = (row_m15['close'] - row_m15['open']) / (row_m15['open'] + 1e-9)
            m_vol = row_m15['volume'] / (vol_ma20_m15 + 1e-9)
            
            M15_U = 1 if m_pct > 0.0062 else 0  # 15分钟尾盘大阳线抢筹 (>0.62%)
            M15_L = 1 if m_vol < 0.5 else 0     # 15分钟极致缩量死寂
            
            if M15_U: 
                #trigger_price = close_t * 0.985
                score += 25 # 榜单一哥，权重拉满
            if M15_L: score += 10
        if T1_U == 1:
            trigger_price = row_t1['open'] + (row_t1['close'] - row_t1['open']) * 0.382
        elif M15_U == 1: # 如果只有尾盘抢筹，挂昨收价下浮 1.5%
            trigger_price = close_t * 0.985
        else:
            trigger_price = close_t * 0.97 # 常规等跌 3% 接    
        # 4. 判定输出
        # 满分大概在 100 左右，我们设定及格线为 65 分 (意味着必须有多个强力因子共振)
        if score >= 65:
            return {
                'signal': True,
                'score': score,
                'position': stock_position,
                'trigger_price': trigger_price
            }
        return None
        
    except Exception as e:
        return None
    
def check_triple_cross_enhanced_filter(df, signal_idx, stock_code):
    """
    TRIPLE_CROSS策略的增强过滤器：结合胜率筛选和交叉阶段分析
    
    Args:
        df: 股票数据DataFrame
        signal_idx: 信号出现的索引
        stock_code: 股票代码
    
    Returns:
        tuple: (是否应该排除, 排除原因, 详细信息)
    """
    try:
        # 1. 使用增强版过滤器
        advanced_filter = AdvancedTripleCrossFilter()
        should_exclude, exclude_reason, quality_score, cross_stage = advanced_filter.enhanced_triple_cross_filter(df, signal_idx)
        
        if should_exclude:
            return True, exclude_reason, {
                'quality_score': quality_score,
                'cross_stage': cross_stage,
                'filter_type': 'advanced_quality'
            }
        
        # 2. 胜率过滤器检查
        signal_series = strategies.apply_triple_cross(df)
        if signal_series is not None:
            win_rate_filter = WinRateFilter(min_win_rate=0.4, min_signals=3, min_avg_profit=0.08)
            should_exclude_wr, exclude_reason_wr, backtest_stats = win_rate_filter.should_exclude_stock(df, signal_series, stock_code)
            
            if should_exclude_wr:
                return True, f"胜率筛选: {exclude_reason_wr}", {
                    'quality_score': quality_score,
                    'cross_stage': cross_stage,
                    'filter_type': 'win_rate',
                    'backtest_stats': backtest_stats
                }
        
        # 3. 通过所有筛选
        return False, "通过增强筛选", {
            'quality_score': quality_score,
            'cross_stage': cross_stage,
            'filter_type': 'passed',
            'backtest_stats': backtest_stats if 'backtest_stats' in locals() else {}
        }
        
    except Exception as e:
        return True, f"增强过滤器执行失败: {e}", {
            'quality_score': 0,
            'cross_stage': 'UNKNOWN',
            'filter_type': 'error'
        }

def worker(args):
    """多进程工作函数 - 优化版本，提高执行效率"""
    file_path, market = args
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code_no_prefix = stock_code_full.replace(market, '')

    # 快速过滤无效股票代码
    valid_prefixes = ('60', '92',  '00' '300', '688')
    if not stock_code_no_prefix.startswith(valid_prefixes):
        return None

    try:
        # 快速加载数据
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 150:
            return None

        # 复权处理
        if ADJUSTMENT_TYPE != 'none':
            df = _adj_processor.process_data(df, stock_code_no_prefix)

        # 预计算常用数据
        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        latest_date = df.index[-1].strftime('%Y-%m-%d')
        
        result_base = {
            'stock_code': stock_code_full,
            'strategy': STRATEGY_TO_RUN,
            'date': latest_date,
            'scan_timestamp': current_timestamp
        }
        
        # 根据策略执行相应逻辑
        if STRATEGY_TO_RUN == 'PRE_CROSS':
            return _process_pre_cross_strategy(df, result_base)
        elif STRATEGY_TO_RUN == 'TRIPLE_CROSS':
            return _process_triple_cross_strategy(df, result_base, stock_code_full)
        elif STRATEGY_TO_RUN == 'MACD_ZERO_AXIS':
            return _process_macd_zero_axis_strategy(df, result_base, stock_code_full)
        elif STRATEGY_TO_RUN == 'WEEKLY_GOLDEN_CROSS_MA':
            return _process_weekly_golden_cross_ma_strategy(df, result_base, stock_code_full)
        # --- 集成新策略的处理分支 ---
        elif STRATEGY_TO_RUN == 'REVERSED_SHORT':
            return _process_reversed_short_strategy_optimized(df, result_base, stock_code_full)
        # --- 新增: 处理自适应均线策略 ---
        elif STRATEGY_TO_RUN == 'ADAPTIVE_MA_SUPPORT':
            return _process_adaptive_ma_support_strategy(df, result_base, stock_code_full)
            
        return None
        
    except Exception as e:
        logger.error(f"处理 {stock_code_full} 时发生未知错误: {e}")
        return None

def _process_pre_cross_strategy(df, result_base):
    """处理PRE_CROSS策略"""
    try:
        signal_series = strategies.apply_pre_cross(df)
        if signal_series is not None and signal_series.iloc[-1]:
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            result_base.update(backtest_stats)
            return result_base
        return None
    except Exception as e:
        return None

def _process_triple_cross_strategy(df, result_base, stock_code_full):
    """处理TRIPLE_CROSS策略"""
    try:
        signal_series = strategies.apply_triple_cross(df)
        if signal_series is not None and signal_series.iloc[-1]:
            # 快速过滤检查
            should_exclude, exclude_reason, filter_details = check_triple_cross_enhanced_filter(df, len(df) - 1, stock_code_full)
            
            if should_exclude:
                logger.info(f"{stock_code_full} 被过滤: {exclude_reason}")
                return None
            
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            result_base.update({
                'quality_score': filter_details.get('quality_score', 0),
                'cross_stage': filter_details.get('cross_stage', 'UNKNOWN'),
                'filter_status': 'passed',
                **backtest_stats
            })
            return result_base
        return None
    except Exception as e:
        return None

def _process_macd_zero_axis_strategy(df, result_base, stock_code_full):
    """处理MACD_ZERO_AXIS策略"""
    try:
        signal_series = strategies.apply_macd_zero_axis_strategy(df)
        signal_state = signal_series.iloc[-1]
        if signal_state in ['PRE', 'MID', 'POST']:
            # 快速过滤检查
            should_exclude, exclude_reason = check_macd_zero_axis_pre_filter(df, len(df) - 1, signal_state)
            
            if should_exclude:
                logger.info(f"{stock_code_full} 被过滤: {exclude_reason}")
                return None
            
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            result_base.update({
                'signal_state': signal_state,
                'filter_status': 'passed',
                **backtest_stats
            })
            return result_base
        return None
    except Exception as e:
        return None

def _process_weekly_golden_cross_ma_strategy(df, result_base, stock_code_full):
    """处理WEEKLY_GOLDEN_CROSS_MA策略"""
    try:
        signal_series = strategies.apply_weekly_golden_cross_ma_strategy(df)
        signal_state = signal_series.iloc[-1]
        
        if signal_state in ['BUY', 'HOLD', 'SELL']:
            # 周线金叉+日线MA策略的过滤检查
            should_exclude, exclude_reason = check_weekly_golden_cross_ma_filter(df, len(df) - 1, signal_state, stock_code_full)
            
            if should_exclude:
                logger.info(f"{stock_code_full} 被过滤: {exclude_reason}")
                return None
            
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            
            # 计算额外的MA相关指标
            ma_analysis = analyze_ma_trend(df)
            
            result_base.update({
                'signal_state': signal_state,
                'filter_status': 'passed',
                'ma_trend_strength': ma_analysis.get('trend_strength', 0),
                'ma13_distance': ma_analysis.get('ma13_distance', 0),
                'volume_surge_ratio': ma_analysis.get('volume_surge_ratio', 1.0),
                **backtest_stats
            })
            return result_base
        return None
    except Exception as e:
        logger.error(f"处理周线金叉+日线MA策略失败 {stock_code_full}: {e}")
        return None

# --- 新增的策略处理函数 ---
def _calculate_priority_score(df, backtest_stats):
    """
    计算综合优先级评分（0-100），用于筛选结果排序，解决"看不出优先级"的问题。
    评分维度：历史胜率 + 平均收益 + 近期量能 + 趋势强度
    """
    try:
        score = 0.0

        # 1. 历史胜率（权重 35%）
        win_rate_str = backtest_stats.get('win_rate', '0.0%').replace('%', '')
        win_rate = float(win_rate_str) / 100.0
        score += win_rate * 35

        # 2. 平均最大收益（权重 30%，上限 50% 收益对应满分）
        profit_str = backtest_stats.get('avg_max_profit', '0.0%').replace('%', '')
        avg_profit = float(profit_str) / 100.0
        score += min(avg_profit / 0.5, 1.0) * 30

        # 3. 近期量能（权重 20%）：最近5日均量 vs 20日均量
        if len(df) >= 20:
            vol_5 = df['volume'].iloc[-5:].mean()
            vol_20 = df['volume'].iloc[-20:].mean()
            if vol_20 > 0:
                vol_ratio = min(vol_5 / vol_20, 3.0)  # 上限3倍
                score += (vol_ratio / 3.0) * 20

        # 4. 趋势强度（权重 15%）：MA5 > MA10 > MA20 排列
        if len(df) >= 20:
            ma5 = df['close'].iloc[-5:].mean()
            ma10 = df['close'].iloc[-10:].mean()
            ma20 = df['close'].iloc[-20:].mean()
            if ma5 > ma10 > ma20:
                score += 15
            elif ma5 > ma10:
                score += 8

        return round(score, 1)
    except Exception:
        return 0.0


def _process_reversed_short_strategy_optimized(df, result_base, stock_code_full):
    """处理优化后的REVERSED_SHORT策略"""
    try:
        signal_series = apply_reversed_short_optimized(df)
        
        if signal_series is not None and signal_series.iloc[-1]:
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            # 计算优先级评分，方便前端直接排序，无需人工逐一判断
            priority_score = _calculate_priority_score(df, backtest_stats)
            result_base.update({
                'signal_state': 'BUY_CANDIDATE',
                'filter_status': 'passed_optimized',
                'priority_score': priority_score,
                **backtest_stats
            })
            return result_base
        return None
    except Exception as e:
        logger.error(f"处理REVERSED_SHORT_OPTIMIZED策略失败 {stock_code_full}: {e}")
        return None

def _process_adaptive_ma_support_strategy_b(df, result_base, stock_code_full):
    """处理 Phase 1 自适应均线右侧深踩策略 (阶梯挂单控制与分流版)"""
    try:
        signal_series = apply_adaptive_ma_support_optimized(df)
        
        if signal_series is not None and signal_series.iloc[-1]:
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            priority_score = _calculate_priority_score(df, backtest_stats)
            
            # 安全提取绑定在 Series 上的多周期元数据
            best_ma = getattr(signal_series, 'best_ma_period', 0)
            fit_score = getattr(signal_series, 'fit_score', 0.0)
            current_ma_val = getattr(signal_series, 'current_ma_val', 0.0)
            polarity_confirmed = getattr(signal_series, 'polarity_confirmed', False)
            deep_touches = getattr(signal_series, 'deep_touches', 0)
            is_deep_wash = getattr(signal_series, 'is_deep_wash', False)
            
            current_price = df['close'].iloc[-1]
            
            # ⚙️ 【执行层：根据第二阶梯洗盘深度，动态下修接针档位】
            if is_deep_wash or deep_touches > 14:
                # 均线缠绕或深度砸坑：采取极限接针防御，防范低于3%收益的到期阴跌
                trigger_buy_price = current_ma_val * 0.96   # 挂条件单于均线下方 4% 的极端防守位
                hard_stop_loss = current_ma_val * 0.88      # 拉宽极限止损给 12% 的诱空空间
            else:
                # 稳健的多头上升轨道回踩
                trigger_buy_price = current_ma_val * 0.985  # 均线下方 1.5% 常规介入
                hard_stop_loss = current_ma_val * 0.92      # 标准 8% 保护线
            
            result_base.update({
                'signal_state': 'BUY_CANDIDATE',
                'filter_status': 'passed_adaptive_ma',
                'priority_score': priority_score,
                'best_ma_period': int(best_ma),
                'fit_score': fit_score,
                'polarity_confirmed': polarity_confirmed,
                'deep_touches': deep_touches,
                'is_deep_wash': int(is_deep_wash),
                'current_price': current_price,
                'trigger_buy_price': round(trigger_buy_price, 2),
                'hard_stop_loss': round(hard_stop_loss, 2),
                **backtest_stats
            })
            return result_base
        return None
    except Exception as e:
        logger.error(f"处理ADAPTIVE_MA_SUPPORT策略失败 {stock_code_full}: {e}")
        return None

def _process_adaptive_ma_support_strategy(df, result_base, stock_code_full):
    """处理 Phase 1 自适应均线右侧深踩策略"""
    try:
        # 新增：股指多周期状态判断
        df_zz1000 = data_loader.get_daily_data("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000852.day")  # 中证1000
        regime = MarketRegimeDetector().evaluate_regime(df_zz1000, df.index[-1].strftime('%Y-%m-%d'))
        
        if regime['risk_score'] > 75:   # 高风险环境直接过滤
            logger.info(f"{stock_code_full} 被股指雷达过滤: {regime['state']}")
            return None

        signal_series = apply_adaptive_ma_support_optimized(df)
        momentum_reversal = getattr(signal_series, 'momentum_reversal', False)
        # 判断最后一天是否触发信号
        if signal_series is not None and signal_series.iloc[-1]:
            # 获取快速回测数据，用于评分排序
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            priority_score = _calculate_priority_score(df, backtest_stats)
            
            # 安全提取绑定在 Series 上的元数据
            best_ma = getattr(signal_series, 'best_ma_period', 0)
            fit_score = getattr(signal_series, 'fit_score', 0.0)
            current_ma_val = getattr(signal_series, 'current_ma_val', 0.0)
            polarity_confirmed = getattr(signal_series, 'polarity_confirmed', False)
            deep_touches = getattr(signal_series, 'deep_touches', 0)
            
            current_price = df['close'].iloc[-1]
            
            # 组装"明日交易执行卡"核心参数
            result_base.update({
                'signal_state': 'BUY_CANDIDATE',
                'filter_status': 'passed_adaptive_ma',
                'priority_score': priority_score,
                # --- 交易执行卡/条件单专属数据 ---
                'best_ma_period': best_ma,
                'fit_score': fit_score,
                'polarity_confirmed': polarity_confirmed,
                'deep_touches': deep_touches,
                'current_price': current_price,
                'trigger_buy_price': round(current_ma_val * 0.98, 2), # 专属均线上方0.5%设买点
                'hard_stop_loss': round(current_ma_val * 0.95, 2),     # 跌破专属均线4%无条件离场
                **backtest_stats
            })
            # 把regime信息也加入执行卡
            result_base.update({
                'market_state': regime['state'],
                'risk_score': regime['risk_score'],
                'discount': regime['discount'],
                'max_positions': regime['max_positions']
            })
            return result_base
        return None
    except Exception as e:
        logger.error(f"处理ADAPTIVE_MA_SUPPORT策略失败 {stock_code_full}: {e}")
        return None

def calculate_backtest_stats_fast(df, signal_series):
    """快速计算回测统计信息 - 优化版本"""
    try:
        # 只计算必要的技术指标
        if 'dif' not in df.columns or 'dea' not in df.columns:
            macd_values = indicators.calculate_macd(df)
            df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        if 'k' not in df.columns or 'd' not in df.columns:
            kdj_values = indicators.calculate_kdj(df)
            df['k'], df['d'], df['j'] = kdj_values[0], kdj_values[1], kdj_values[2]
        
        # 执行快速回测
        backtest_results = backtester.run_backtest(df, signal_series)
        
        if isinstance(backtest_results, dict) and backtest_results.get('total_signals', 0) > 0:
            return {
                'total_signals': backtest_results.get('total_signals', 0),
                'win_rate': backtest_results.get('win_rate', '0.0%'),
                'avg_max_profit': backtest_results.get('avg_max_profit', '0.0%'),
                'avg_max_drawdown': backtest_results.get('avg_max_drawdown', '0.0%'),
                'avg_days_to_peak': backtest_results.get('avg_days_to_peak', '0.0 天')
            }
        else:
            return {
                'total_signals': 0,
                'win_rate': '0.0%',
                'avg_max_profit': '0.0%',
                'avg_max_drawdown': '0.0%',
                'avg_days_to_peak': '0.0 天'
            }
    except Exception as e:
        logger.error(f"快速回测计算失败: {e}")
        return {
            'total_signals': 0,
            'win_rate': '0.0%',
            'avg_max_profit': '0.0%',
            'avg_max_drawdown': '0.0%',
            'avg_days_to_peak': '0.0 天'
        }

def generate_summary_report(passed_stocks):
    """生成详细的汇总报告"""
    if not passed_stocks:
        return {
            'scan_summary': {
                'total_signals': 0,
                'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'strategy': STRATEGY_TO_RUN,
                'total_historical_signals': 0,
                'avg_win_rate': '0.0%',
                'avg_profit_rate': '0.0%',
                'avg_days_to_peak': '0.0 天'
            },
            'signal_breakdown': {},
            'top_performers': []
        }
    
    # 计算整体统计
    total_signals = len(passed_stocks)
    
    # 按信号状态分组（仅适用于MACD_ZERO_AXIS策略）
    signal_states = {}
    if STRATEGY_TO_RUN == 'MACD_ZERO_AXIS':
        for stock in passed_stocks:
            state = stock.get('signal_state', 'UNKNOWN')
            if state not in signal_states:
                signal_states[state] = []
            signal_states[state].append(stock)
    
    # 计算平均回测指标
    total_historical_signals = sum(stock.get('total_signals', 0) for stock in passed_stocks if stock.get('total_signals', 0) > 0)
    
    # 解析胜率和收益率（去掉百分号）
    win_rates = []
    profit_rates = []
    days_to_peak = []
    
    for stock in passed_stocks:
        if stock.get('total_signals', 0) > 0:
            # 解析胜率
            win_rate_str = stock.get('win_rate', '0.0%').replace('%', '')
            try:
                win_rates.append(float(win_rate_str))
            except:
                pass
            
            # 解析收益率
            profit_str = stock.get('avg_max_profit', '0.0%').replace('%', '')
            try:
                profit_rates.append(float(profit_str))
            except:
                pass
            
            # 解析达峰天数
            days_str = stock.get('avg_days_to_peak', '0.0 天').replace(' 天', '')
            try:
                days_to_peak.append(float(days_str))
            except:
                pass
    
    # 计算平均值
    avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
    avg_profit_rate = sum(profit_rates) / len(profit_rates) if profit_rates else 0
    avg_days_to_peak = sum(days_to_peak) / len(days_to_peak) if days_to_peak else 0
    
    summary = {
        'scan_summary': {
            'total_signals': total_signals,
            'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'strategy': STRATEGY_TO_RUN,
            'total_historical_signals': total_historical_signals,
            'avg_win_rate': f"{avg_win_rate:.1f}%",
            'avg_profit_rate': f"{avg_profit_rate:.1f}%",
            'avg_days_to_peak': f"{avg_days_to_peak:.1f} 天"
        },
        'signal_breakdown': signal_states if signal_states else {},
        'top_performers': sorted(
            [s for s in passed_stocks if s.get('total_signals', 0) > 0],
            key=lambda x: (
                float(x.get('priority_score', 0)),           # 优先按综合评分
                float(x.get('avg_max_profit', '0%').replace('%', ''))  # 其次按收益
            ),
            reverse=True
        )[:10] if passed_stocks else []  # 前10名表现最好的
    }
    
    return summary

def trigger_deep_scan(passed_stocks):
    """触发深度扫描"""
    if not passed_stocks:
        print("⚠️ 没有通过筛选的股票，跳过深度扫描")
        return
    
    print(f"\n🔍 触发深度扫描...")
    print(f"📊 筛选出 {len(passed_stocks)} 只股票进行深度分析")
    
    # 提取股票代码
    stock_codes = [stock['stock_code'] for stock in passed_stocks]
    
    try:
        # 导入深度扫描模块
        from run_enhanced_screening import analyze_multiple_stocks
        
        # 执行深度扫描
        deep_scan_results = analyze_multiple_stocks(stock_codes, use_optimized_params=True, max_workers=32)
        
        print(f"✅ 深度扫描完成")
        return deep_scan_results
        
    except Exception as e:
        print(f"❌ 深度扫描失败: {e}")
        return None

def trigger_deep_scan_multithreaded(passed_stocks):
    """触发多线程深度扫描"""
    if not passed_stocks:
        print("⚠️ 没有通过筛选的股票，跳过深度扫描")
        return None
    
    print(f"\n🔍 触发多线程深度扫描...")
    print(f"📊 筛选出 {len(passed_stocks)} 只股票进行深度分析")
    
    # 提取股票代码
    stock_codes = [stock['stock_code'] for stock in passed_stocks]
    
    try:
        # 导入深度扫描模块
        from run_enhanced_screening import deep_scan_stocks
        
        # 根据股票数量动态调整线程数
        max_workers = min(cpu_count() * 2, len(stock_codes), 32)  # 最多16个线程
        print(f"🧵 使用 {max_workers} 个线程进行深度扫描")
        
        # 执行多线程深度扫描
        deep_scan_results = deep_scan_stocks(stock_codes, use_optimized_params=True, max_workers=max_workers)
        
        print(f"✅ 多线程深度扫描完成")
        return deep_scan_results
        
    except Exception as e:
        print(f"❌ 多线程深度扫描失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """主执行函数 - 增强版本，集成深度扫描，多线程操作"""
    start_time = datetime.now()
    logger.info(f"===== 开始执行批量筛选, 策略: {STRATEGY_TO_RUN} =====")
    print(f"🚀 开始执行批量筛选, 策略: {STRATEGY_TO_RUN}")
    print(f"⏰ 扫描时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_files = []
    for market in MARKETS:
        path = os.path.join(BASE_PATH, market, 'lday', '*.day')
        files = glob.glob(path)
        if not files:
            print(f"⚠️ 警告: 在路径 {path} 未找到任何文件。")
        all_files.extend([(f, market) for f in files])
    
    if not all_files:
        print("❌ 错误: 未能在任何市场目录下找到日线文件，请检查BASE_PATH配置。")
        return

    print(f"📊 共找到 {len(all_files)} 个日线文件，开始多进程处理...")
    
    # 使用多进程进行初步筛选
    with Pool(processes=cpu_count(), initializer=_worker_init) as pool:
        results = pool.map(worker, all_files)
    
    passed_stocks = [r for r in results if r is not None]
    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()
    
    print(f"📈 初步筛选完成，通过筛选: {len(passed_stocks)} 只股票")
    
    # 转换 numpy 类型为 Python 原生类型
    def convert_numpy_types(obj):
        if isinstance(obj, dict):
            return {k: convert_numpy_types(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_numpy_types(item) for item in obj]
        elif hasattr(obj, 'item'):  # numpy scalar types
            return obj.item()
        elif isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
            return int(obj)
        elif isinstance(obj, (np.float64, np.float32, np.float16)):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        else:
            return obj
    
    # 保存详细信号列表
    output_file = os.path.join(RESULT_DIR, 'signals_summary.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(convert_numpy_types(passed_stocks), f, ensure_ascii=False, indent=4)
    
    # 生成并保存汇总报告
    summary_report = generate_summary_report(passed_stocks)
    summary_report['scan_summary']['processing_time'] = f"{processing_time:.2f} 秒"
    summary_report['scan_summary']['files_processed'] = len(all_files)
    
    summary_file = os.path.join(RESULT_DIR, 'scan_summary_report.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(convert_numpy_types(summary_report), f, ensure_ascii=False, indent=4)
    
    # 生成文本格式的汇总报告
    text_report_file = os.path.join(RESULT_DIR, f'scan_report_{DATE}.txt')
    with open(text_report_file, 'w', encoding='utf-8') as f:
        f.write(f"=== {STRATEGY_TO_RUN} 策略筛选报告 ===\n")
        f.write(f"扫描时间: {summary_report['scan_summary']['scan_timestamp']}\n")
        f.write(f"处理文件数: {summary_report['scan_summary']['files_processed']}\n")
        f.write(f"处理耗时: {summary_report['scan_summary']['processing_time']}\n")
        f.write(f"发现信号数: {summary_report['scan_summary']['total_signals']}\n")
        f.write(f"历史信号总数: {summary_report['scan_summary'].get('total_historical_signals', 0)}\n")
        f.write(f"平均胜率: {summary_report['scan_summary']['avg_win_rate']}\n")
        f.write(f"平均收益率: {summary_report['scan_summary']['avg_profit_rate']}\n")
        f.write(f"平均达峰天数: {summary_report['scan_summary']['avg_days_to_peak']}\n\n")
        
        if summary_report['signal_breakdown']:
            f.write("=== 信号状态分布 ===\n")
            for state, stocks in summary_report['signal_breakdown'].items():
                f.write(f"{state}: {len(stocks)} 个\n")
            f.write("\n")
        
        if summary_report['top_performers']:
            f.write("=== 前10名表现最佳股票 (推荐优先交易) ===\n")
            for i, stock in enumerate(summary_report['top_performers'], 1):
                base_info = (f"{i:2d}. {stock['stock_code']} - 胜率: {stock.get('win_rate', 'N/A')}, "
                             f"收益: {stock.get('avg_max_profit', 'N/A')}, "
                             f"天数: {stock.get('avg_days_to_peak', 'N/A')}")
                
                # 如果是自适应均线策略，输出额外的条件单执行卡数据
                if 'best_ma_period' in stock:
                    polarity_mark = "⚡极性转换确认" if stock.get('polarity_confirmed') else ""
                    extra_info = (f"\n    └─ 专属MA: {stock['best_ma_period']} (拟合分: {stock['fit_score']}) {polarity_mark}\n"
                                  f"    └─ 💡 条件单买点: ¥{stock.get('trigger_buy_price', 0)} | 🛑 破位止损: ¥{stock.get('hard_stop_loss', 0)}\n")
                    f.write(base_info + extra_info)
                else:
                    f.write(base_info + "\n")
    
    print(f"\n📊 初步筛选完成！")
    print(f"🎯 发现信号: {len(passed_stocks)} 个")
    print(f"⏱️ 处理耗时: {processing_time:.2f} 秒")
    print(f"📈 平均胜率: {summary_report['scan_summary']['avg_win_rate']}")
    print(f"💰 平均收益: {summary_report['scan_summary']['avg_profit_rate']}")
    print(f"📄 结果已保存至:")
    print(f"  - 信号列表: {output_file}")
    print(f"  - 汇总报告: {summary_file}")
    print(f"  - 文本报告: {text_report_file}")
    
    # 自动触发深度扫描（多线程）
    if len(passed_stocks) > 0:
        print(f"\n" + "="*60)
        print(f"🔍 启动深度扫描阶段 (多线程)")
        print(f"="*60)
        
        deep_scan_results = trigger_deep_scan_multithreaded(passed_stocks)
        
        if deep_scan_results:
            # 统计深度扫描结果
            valid_deep_results = {k: v for k, v in deep_scan_results.items() if 'error' not in v}
            a_grade_stocks = [k for k, v in valid_deep_results.items() if v.get('overall_score', {}).get('grade') == 'A']
            price_evaluated_stocks = [k for k, v in valid_deep_results.items() if 'price_evaluation' in v]
            buy_recommendations = [k for k, v in valid_deep_results.items() if v.get('recommendation', {}).get('action') == 'BUY']
            
            print(f"\n🎉 深度扫描结果:")
            print(f"📊 深度分析成功: {len(valid_deep_results)}/{len(passed_stocks)}")
            print(f"🏆 A级股票发现: {len(a_grade_stocks)}")
            print(f"💰 价格评估完成: {len(price_evaluated_stocks)}")
            print(f"🟢 买入推荐: {len(buy_recommendations)}")
            
            if a_grade_stocks:
                print(f"\n🌟 A级股票列表:")
                for stock_code in a_grade_stocks:
                    result = valid_deep_results[stock_code]
                    if result is None:  # 增加防护！
                        continue
                    score = result['overall_score']['total_score']
                    price = result['basic_analysis']['current_price']
                    action = result['recommendation']['action']
                    confidence = result['recommendation']['confidence']
                    price_eval_mark = " 💰" if 'price_evaluation' in result else ""
                    print(f"  🏆 {stock_code}: {score:.1f}分, ¥{price:.2f}, {action} ({confidence:.1%}){price_eval_mark}")
            
            # 保存深度扫描汇总到筛选报告
            summary_report['deep_scan_summary'] = {
                'total_analyzed': len(valid_deep_results),
                'a_grade_count': len(a_grade_stocks),
                'price_evaluated_count': len(price_evaluated_stocks),
                'buy_recommendations': len(buy_recommendations),
                'a_grade_stocks': a_grade_stocks,
                'buy_recommendation_stocks': buy_recommendations
            }
            
            # 更新汇总报告文件
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(convert_numpy_types(summary_report), f, ensure_ascii=False, indent=4)
            
            # 更新文本报告
            with open(text_report_file, 'a', encoding='utf-8') as f:
                f.write(f"\n=== 深度扫描结果 (多线程) ===\n")
                f.write(f"深度分析成功: {len(valid_deep_results)}/{len(passed_stocks)}\n")
                f.write(f"A级股票发现: {len(a_grade_stocks)}\n")
                f.write(f"价格评估完成: {len(price_evaluated_stocks)}\n")
                f.write(f"买入推荐: {len(buy_recommendations)}\n\n")
                
                if a_grade_stocks:
                    f.write("=== A级股票详情 ===\n")
                    for stock_code in a_grade_stocks:
                        result = valid_deep_results[stock_code]
                        score = result['overall_score']['total_score']
                        price = result['basic_analysis']['current_price']
                        action = result['recommendation']['action']
                        confidence = result['recommendation']['confidence']
                        price_eval_mark = " [已评估]" if 'price_evaluation' in result else ""
                        f.write(f"{stock_code}: {score:.1f}分, ¥{price:.2f}, {action} "
                               f"(信心度: {confidence:.1%}){price_eval_mark}\n")
                
                if buy_recommendations:
                    f.write(f"\n=== 买入推荐股票 ===\n")
                    for stock_code in buy_recommendations:
                        result = valid_deep_results[stock_code]
                        score = result['overall_score']['total_score']
                        price = result['basic_analysis']['current_price']
                        # 👇 核心新增：参照 validate_sr_levels_morse 提取自适应价格
                        advice = result.get('trading_advice', {})
                        confidence = result['recommendation']['confidence']
                        # 提取自适应算法生成的买卖预测价
                        pred_entry = float(advice.get('entry_price', current_price))
                        pred_target = float(advice.get('target_price', current_price * 1.1))
                        pred_stop = float(advice.get('stop_price', current_price * 0.95))
                        # 提取形态标签用于日志输出
                        feat_pattern = advice.get('feature_pattern', 'T1_L')
                        board_info = advice.get('market_board', '未知板块')
                        
                        # 计算挂单折扣和止损幅度
                        discount_pct = (pred_entry - current_price) / current_price * 100
                        sl_pct = (pred_stop - pred_entry) / pred_entry * 100
                        
                        price_eval_mark = " [已通过价格自适应评估]" if 'trading_advice' in result else ""

                        # 格式化输出到选股日志
                        f.write(f"📌 {stock_code}: {score:.1f}分 (信心: {confidence:.1%}) {price_eval_mark}\n")
                        f.write(f"   ├─ 形态标签: {board_info} | {feat_pattern}\n")
                        f.write(f"   ├─ 基准现价: ¥{current_price:.2f}\n")
                        f.write(f"   ├─ 🛒 黄金挂单: ¥{pred_entry:.2f} (折价 {discount_pct:+.1f}%)\n")
                        f.write(f"   ├─ 🎯 止盈目标: ¥{pred_target:.2f}\n")
                        f.write(f"   └─ ⛔ 动态止损: ¥{pred_stop:.2f} (破位 {sl_pct:+.1f}%)\n")
                        f.write("-" * 50 + "\n")
    else:
        print(f"\n⚠️ 未发现符合条件的股票，跳过深度扫描")
    
    total_time = (datetime.now() - start_time).total_seconds()
    print(f"\n🎉 完整扫描流程结束！总耗时: {total_time:.2f} 秒")
    
    logger.info(f"===== 完整扫描完成！初步筛选: {len(passed_stocks)} 个信号，总耗时: {total_time:.2f} 秒 =====")

if __name__ == '__main__':
    main()
