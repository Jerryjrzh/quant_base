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
from data_handler import get_full_data_with_indicators
import talib # 确保导入talib
from gbm_scorer import GBMScorer
from pricing_gbm import load_pricing_gbm, score_entry_strategy
from enhanced_analyzer import EnhancedTradingAnalyzer

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
                    'polarity_confirmed': was_resistance , 
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
#STRATEGY_TO_RUN = 'ADAPTIVE_MA_SUPPORT'  # <--- 启用自适应均线策略
STRATEGY_TO_RUN = 'MORSE_FACTOR_SNIPER'  # <--- 莫尔斯狙击手策略（含 GBM 过滤）

# --- 路径定义 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))

# --- 日志初始化改为惰性加载，防止多进程文件锁冲突 ---
DATE = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, STRATEGY_TO_RUN)
os.makedirs(RESULT_DIR, exist_ok=True)
LOG_FILE = os.path.join(RESULT_DIR, f'log_screener_{DATE}.txt')

# 创建一个全局变量但延迟初始化
_logger_initialized = False
_logger_instance = None

def get_logger():
    """惰性获取logger实例，只在需要时初始化文件处理器"""
    global _logger_initialized, _logger_instance
    
    if _logger_instance is None:
        _logger_instance = logging.getLogger('screener_logger')
        _logger_instance.setLevel(logging.WARNING)
    
    # 只有在主线程/进程且未初始化时才添加文件处理器
    if not _logger_initialized:
        # 检查是否已经有处理器（可能是其他代码添加的）
        if not _logger_instance.handlers:
            file_handler = logging.FileHandler(LOG_FILE, 'a', 'utf-8')
            file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
            _logger_instance.addHandler(file_handler)
        _logger_initialized = True
    
    return _logger_instance

# --- 全局复权处理器（多进程 worker 中通过模块级变量访问）---
_adj_processor = AdjustmentProcessor(AdjustmentConfig(adjustment_type=ADJUSTMENT_TYPE))

# --- GBM 模型全局初始化（与 walk_forward_tester_s.py 保持一致）---
_gbm_scorer = None
_gbm_enabled = True
_gbm_threshold = 0.62

def _init_gbm_scorer():
    """单例加载 GBM 信号打分模型，失败时降级"""
    global _gbm_scorer, _gbm_enabled
    if _gbm_scorer is None and _gbm_enabled:
        try:
            _gbm_scorer = GBMScorer()
            if not _gbm_scorer.load():
                _gbm_enabled = False
                _gbm_scorer = None
        except Exception:
            _gbm_enabled = False
            _gbm_scorer = None

def get_board_params(stock_code):
    """板块参数：科创/创业板 20CM、北交 30CM、主板 10CM"""
    if stock_code.startswith(('688', '689')):
        return {'target_profit': 0.15, 'stop_loss': -0.08, 'board_type': '20CM'}
    elif stock_code.startswith('30'):
        return {'target_profit': 0.12, 'stop_loss': -0.07, 'board_type': '20CM'}
    elif stock_code.startswith('92'):
        return {'target_profit': 0.18, 'stop_loss': -0.10, 'board_type': '30CM'}
    else:
        return {'target_profit': 0.10, 'stop_loss': -0.05, 'board_type': '10CM'}

def _worker_init():
    """多进程子进程初始化：预热 gbbq 缓存 + GBM 模型"""
    if ADJUSTMENT_TYPE != 'none':
        try:
            from gbbq_reader import read_gbbq
            read_gbbq()
        except Exception:
            pass
    _init_gbm_scorer()

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
        get_logger().error(f"回测计算失败: {e}")
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
        get_logger().error(f"周线金叉+日线MA过滤器检查失败 {stock_code}: {e}")
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
        get_logger().error(f"MA趋势分析失败: {e}")
        return {
            'trend_strength': 0,
            'ma13_distance': 0,
            'volume_surge_ratio': 1.0
        }

def apply_morse_sniper_strategy(df_daily, df_15m=None, stock_code=None, end_date=None):
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
        score = 95  # 拿到入场券的基础分
            
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
        # 🚨 v4.5 一票否决: T1_L + T1_B 组合 (实测 PF=2.63, 全分组最差)
        # 长下影+下影线 = 诱多形态, 在打分前直接剔除, 不参与后续判定
        # ========================================================
        if T1_L and T1_B:
            return None

        # ========================================================
        # 4. 交叉加权打分 (v4.4 原版, v4.5 不再反转 — 回滚死锁修复)
        # ========================================================
        if T1_U: score -= 20
        if T1_T and T1_H: score -= 25
        if T1_B: score -= 15
        if T1_D: score -= 10

        if T1_L:
            # T1_L + T1_B 已在上方被一票否决, 此分支实际不会命中
            if T1_B: score -= 50
            elif T1_X and M15_U: score += 5
            elif T1_d_small or T1_D: score -= 30
            else: score -= 15

        if T1_D and M15_U and M15_H: score += 10

        # ========================================================
        # 5. 判定输出与【基于乖离率的三维深蹲定价】
        # ========================================================
        if score >= 85:
            # ========================================================
            # 6. V4.4 动态定价 (场景化 ATR 定价，替代静态折扣)
            # ========================================================
            v44_ok = False
            v44_meta = {}
            if stock_code:
                try:
                    df_full = get_full_data_with_indicators(stock_code, end_date=end_date)
                    if df_full is not None and len(df_full) >= 100:
                        advice = backtester._generate_forward_advice_v4(df_full, stock_code)
                        if advice and advice.get('action') == 'AVOID':
                            return None
                        if advice and advice.get('action') not in ('ERROR', 'AVOID'):
                            v44_entry = advice.get('entry_price')
                            v44_target = advice.get('target_price')
                            v44_stop = advice.get('stop_price')
                            if v44_entry and v44_target and v44_stop and v44_entry > 0:
                                trigger_buy = v44_entry
                                target_p = (v44_target - v44_entry) / v44_entry
                                stop_l = (v44_stop - v44_entry) / v44_entry
                                v44_ok = True
                                v44_meta = {
                                    'v44_entry': v44_entry,
                                    'v44_target': v44_target,
                                    'v44_stop': v44_stop,
                                    'v44_target_p': target_p,
                                    'v44_stop_l': stop_l,
                                    'v44_trend': advice.get('feature_trend', ''),
                                    'v44_bias_tier': advice.get('feature_bias_tier', ''),
                                    'v44_grade': advice.get('quality_grade', ''),
                                    'v44_action': advice.get('action', ''),
                                    'entry_pos': advice.get('entry_pos', 0.5),
                                }
                except Exception:
                    pass

            if not v44_ok:
                if bias_13 > 0.05 and not T1_B:
                    trigger_buy = close_t * 0.935
                elif T1_D:
                    trigger_buy = close_t * 0.915
                elif T1_B:
                    trigger_buy = close_t * 0.98
                elif M15_U:
                    trigger_buy = close_t * 0.990
                else:
                    trigger_buy = close_t * 0.955

                recent_7d = df_daily.tail(7)
                range_high = float(recent_7d['high'].max())
                range_low = float(recent_7d['low'].min())
                price_range = range_high - range_low
                entry_pos_fb = (trigger_buy - range_low) / price_range if price_range > 0 else 0.5
                if entry_pos_fb > 0.5:
                    return None
                v44_meta['entry_pos'] = round(entry_pos_fb, 4)

            # --- V4.9 爆发前信号标记 ---
            ep_val = v44_meta.get('entry_pos', 0.5)
            trend_val = v44_meta.get('v44_trend', '')
            pending_explosion = (
                ep_val <= 0.3 and
                trend_val in ('accumulation', 'markup') and
                abs(bias_13) < 0.05
            )
            if pending_explosion:
                v44_meta['pending_explosion'] = True
                v44_meta['explosion_reason'] = (
                    f"entry_pos={ep_val:.2f}≤0.3 + {trend_val} + bias={bias_13:+.2%} "
                    f"→ 洗盘蓄力特征, 建议耐心持有15天等待爆发"
                )

            return {
                'signal': True,
                'score': score,
                'position': stock_position,
                'trigger_price': trigger_buy,
                'ma_slope': slope_13,
                'bias_20': bias_13,
                **v44_meta
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

def _process_morse_sniper_strategy(df, result_base, stock_code_full):
    """
    处理 MORSE_FACTOR_SNIPER 策略
    完整复刻 walk_forward_tester_s.py 的筛选管线：
    apply_morse_sniper_strategy → GBM 过滤 → v5 评分 → 定价 → 特征提取
    """
    try:
        stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')

        # --- 1. 加载 15 分钟线 ---
        df_15m = data_loader.get_min_data(stock_code, period='15m')
        m15_slice = None
        if df_15m is not None and not df_15m.empty:
            if 'datetime' in df_15m.columns:
                df_15m.index = pd.to_datetime(df_15m['datetime'])
            elif not isinstance(df_15m.index, pd.DatetimeIndex):
                df_15m.index = pd.to_datetime(df_15m.index)
            cutoff = pd.to_datetime(f"{df.index[-1].strftime('%Y-%m-%d')} 15:30:00")
            m15_slice = df_15m[df_15m.index <= cutoff].copy()

        # --- 2. 调用基础策略 ---
        end_date = df.index[-1].strftime('%Y-%m-%d')
        res = apply_morse_sniper_strategy(df, df_15m=m15_slice,
                                          stock_code=stock_code_full, end_date=end_date)
        if res is None or not res.get('signal'):
            return None

        # --- 3. GBM 概率过滤 ---
        _init_gbm_scorer()
        if _gbm_enabled and _gbm_scorer is not None:
            try:
                ma_slope = res.get('ma_slope', 0)
                board_params = get_board_params(stock_code)
                board_type = board_params.get('board_type', '10CM')

                # Scheme C 基础过滤
                if ma_slope > -0.02 or board_type != '20CM':
                    return None

                # GBM 打分
                signal_df = pd.DataFrame([{
                    'ma_slope': ma_slope,
                    'bias_20': res.get('bias_20', 0),
                    'score': res.get('score', 95),
                    'market_env': res.get('v44_trend', ''),
                    'v44_trend': res.get('v44_trend', ''),
                    'v44_bias_tier': res.get('v44_bias_tier', ''),
                }])
                gbm_proba = _gbm_scorer.score(signal_df)[0]

                if gbm_proba < _gbm_threshold:
                    return None

                res['gbm_proba'] = gbm_proba
            except Exception:
                pass
        else:
            pass

        strategy_score = res.get('score', 65)
        gbm_proba_val = res.get('gbm_proba', 0.0)

        # --- 4. V4.4 定价 ---
        v44_ok = 'v44_entry' in res
        v44_meta = {}
        if v44_ok:
            trigger_buy = res['v44_entry']
            static_take_profit = res['v44_target']
            static_stop_loss = res['v44_stop']
            v44_meta = {
                'v44_trend': res.get('v44_trend', ''),
                'v44_bias_tier': res.get('v44_bias_tier', ''),
                'v44_grade': res.get('v44_grade', ''),
                'v44_action': res.get('v44_action', ''),
                'v44_entry': trigger_buy,
                'v44_target': static_take_profit,
                'v44_stop': static_stop_loss,
            }
        else:
            board_params = get_board_params(stock_code)
            trigger_buy = res['trigger_price']
            static_take_profit = trigger_buy * (1 + board_params['target_profit'])
            static_stop_loss = trigger_buy * (1 + board_params['stop_loss'])
            v44_meta = {
                'v44_entry': trigger_buy,
                'v44_target': static_take_profit,
                'v44_stop': static_stop_loss,
            }

        # --- 5. 全景环境与特征提取 ---
        t0_close = df['close'].iloc[-1]
        vol_ma20_d = df['volume'].rolling(20).mean().iloc[-1]
        row_t1 = df.iloc[-1]

        d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
        d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
        d_lower_shadow = (min(row_t1['close'], row_t1['open']) - row_t1['low']) / (row_t1['open'] + 1e-9)

        T1_U = 1 if d_pct > 0.062 else 0
        T1_D = 1 if d_pct < -0.062 else 0
        T1_L = 1 if d_vol < 0.8 else 0
        T1_B = 1 if d_lower_shadow > 0.026 else 0

        M15_U, M15_L, M15_H = 0, 0, 0
        if m15_slice is not None and len(m15_slice) > 20:
            vol_ma20_m15 = m15_slice['volume'].rolling(20).mean().iloc[-1]
            row_m15 = m15_slice.iloc[-1]
            m_pct = (row_m15['close'] - row_m15['open']) / (row_m15['open'] + 1e-9)
            m_vol = row_m15['volume'] / (vol_ma20_m15 + 1e-9)
            M15_U = 1 if m_pct > 0.0062 else 0
            M15_L = 1 if m_vol < 0.5 else 0
            M15_H = 1 if m_vol > 2.5 else 0

        ma20 = df['close'].rolling(20).mean().iloc[-1]
        bias_20 = (t0_close - ma20) / ma20 if ma20 > 0 else 0
        ma_slope = res.get('ma_slope', 0)

        # --- 6. 大盘环境判断 ---
        market_env = "震荡"
        index_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000001.day")
        if os.path.exists(index_path):
            try:
                df_index = data_loader.get_daily_data(index_path)
                t0_date_str = df.index[-1].strftime('%Y-%m-%d')
                if t0_date_str in df_index.index:
                    idx_loc = df_index.index.get_loc(t0_date_str)
                    if idx_loc > 0:
                        idx_pct = (df_index['close'].iloc[idx_loc] - df_index['close'].iloc[idx_loc-1]) / df_index['close'].iloc[idx_loc-1]
                        if idx_pct > 0.01: market_env = "顺风大涨"
                        elif idx_pct < -0.015: market_env = "股灾暴跌"
                        elif idx_pct < -0.005: market_env = "弱势阴跌"
            except Exception:
                pass

        # --- 7. v5 评分重构 ---
        screenergf_score = strategy_score
        new_score = 70
        if T1_D == 1:
            if gbm_proba_val >= 0.80:
                new_score = 120
            elif gbm_proba_val >= 0.75:
                new_score = 110
            else:
                new_score = 95
        elif gbm_proba_val >= 0.70:
            new_score = 95
        if gbm_proba_val == 0.0:
            new_score = screenergf_score
        strategy_score = new_score

        if   new_score == 120:                v5_tier_label = 'S'
        elif new_score == 110:                v5_tier_label = 'A'
        elif new_score == 95 and T1_D == 1:   v5_tier_label = 'B_T1D'
        elif new_score == 95:                 v5_tier_label = 'B_GBM'
        else:                                 v5_tier_label = 'C'

        # --- 8. 莫尔斯特征字符串 ---
        morse_features = (
            f"S:{strategy_score}|OS:{screenergf_score}|MKT:{market_env}|"
            f"B20:{bias_20:.3f}|T1_U:{T1_U}|T1_D:{T1_D}|T1_L:{T1_L}|T1_B:{T1_B}|"
            f"M15_U:{M15_U}|M15_L:{M15_L}|M15_H:{M15_H}|GBM:{gbm_proba_val:.3f}"
        )

        # --- 9. V4.9 TP/SL ---
        board_params = get_board_params(stock_code)
        board_type = board_params.get('board_type', '10CM')
        v44_trend = res.get('v44_trend', '')
        v44_bias = res.get('v44_bias_tier', '')

        v46_tp = 0.10
        if board_type == '20CM':
            v46_sl = -0.12
            if v44_trend == 'markup' and v44_bias == '空头偏离(-15%~-5%)':
                v46_sl = -0.07
        else:
            v46_sl = -0.10

        static_take_profit = round(trigger_buy * (1 + v46_tp), 2)
        static_stop_loss = round(trigger_buy * (1 + v46_sl), 2)

        # --- 10. 组装输出 ---
        result_base.update({
            'signal_state': 'BUY_CANDIDATE',
            'filter_status': 'passed_morse_sniper',
            'priority_score': strategy_score,
            # v5 评分体系
            'v5_score': strategy_score,
            'v5_tier': v5_tier_label,
            'screenergf_score': screenergf_score,
            # GBM & 因子
            'gbm_proba': round(gbm_proba_val, 4),
            'ma_slope': round(ma_slope, 4),
            'bias_20': round(bias_20, 4),
            'pricing_proba': 0.5,
            # T1/M15 因子标记
            'T1_D': T1_D, 'T1_U': T1_U, 'T1_L': T1_L, 'T1_B': T1_B, 'M15_U': M15_U,
            # 大盘环境
            'market_env': market_env,
            # 莫尔斯特征
            'morse_features': morse_features,
            # 定价
            'trigger_buy_price': round(trigger_buy, 2),
            'stop_loss_price': round(static_stop_loss, 2),
            'target_price': round(static_take_profit, 2),
            'close_t0': round(t0_close, 2),
            # V4.4 元数据
            **v44_meta
        })
        return result_base

    except Exception as e:
        get_logger().error(f"处理MORSE_FACTOR_SNIPER策略失败 {stock_code_full}: {e}")
        return None

def worker(args):
    """多进程工作函数 - 优化版本，提高执行效率"""
    file_path, market = args
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code_no_prefix = stock_code_full.replace(market, '')

    # 快速过滤无效股票代码
    #valid_prefixes = ('60', '92',  '00', '300', '688')
    valid_prefixes = ('30', '68', '92')
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
        elif STRATEGY_TO_RUN == 'MORSE_FACTOR_SNIPER':
            return _process_morse_sniper_strategy(df, result_base, stock_code_full)
            
        return None
        
    except Exception as e:
        get_logger().error(f"处理 {stock_code_full} 时发生未知错误: {e}")
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
                get_logger().info(f"{stock_code_full} 被过滤: {exclude_reason}")
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
                get_logger().info(f"{stock_code_full} 被过滤: {exclude_reason}")
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
                get_logger().info(f"{stock_code_full} 被过滤: {exclude_reason}")
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
        get_logger().error(f"处理周线金叉+日线MA策略失败 {stock_code_full}: {e}")
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
        get_logger().error(f"处理REVERSED_SHORT_OPTIMIZED策略失败 {stock_code_full}: {e}")
        return None



def _process_adaptive_ma_support_strategy(df, result_base, stock_code_full):
    """处理 Phase 1 自适应均线右侧深踩策略"""
    try:
        # 新增：股指多周期状态判断
        df_zz1000 = data_loader.get_daily_data("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000852.day")  # 中证1000
        regime = MarketRegimeDetector().evaluate_regime(df_zz1000, df.index[-1].strftime('%Y-%m-%d'))
        
        if regime['risk_score'] > 75:   # 高风险环境直接过滤
            get_logger().info(f"{stock_code_full} 被股指雷达过滤: {regime['state']}")
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
        get_logger().error(f"处理ADAPTIVE_MA_SUPPORT策略失败 {stock_code_full}: {e}")
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
        get_logger().error(f"快速回测计算失败: {e}")
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
            [s for s in passed_stocks if s.get('total_signals', 0) > 0 or s.get('v5_score', 0) > 0 or s.get('priority_score', 0) > 0],
            key=lambda x: (
                float(x.get('v5_score', x.get('priority_score', 0))),  # 优先按 v5/综合评分
                float(x.get('gbm_proba', 0)),                           # 其次按 GBM 概率
                float(x.get('avg_max_profit', '0%').replace('%', ''))   # 再按收益
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


def run_price_evaluation_batch(passed_stocks, gbm_threshold=0.5, max_workers=8):
    """对初筛通过股票统一跑一轮价格评估 (两阶段: pricing_gbm 快筛 + 完整价格评估)。

    Phase 1: 用 pricing_gbm 计算浅入场概率 (0~1); 低于阈值直接跳过, 节省算力。
    Phase 2: 对通过 Phase 1 的股票跑 EnhancedTradingAnalyzer 拿到
             basic_analysis + trading_advice, 再执行 perform_price_evaluation
             得到入场/止盈/止损建议。

    结果写入每只 stock dict:
      - 'gbm_shallow_proba': float, pricing_gbm 浅入场概率
      - 'price_evaluation': dict 或 {'error': ...}
    并保存汇总到 RESULT_DIR/price_evaluation_summary.json。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from trading_advisor import TradingAdvisor

    if not passed_stocks:
        return {'evaluated': 0, 'passed_gbm': 0, 'passed_full': 0}

    print(f"\n💰 启动价格评估阶段...")
    print(f"📊 待评估股票: {len(passed_stocks)}")

    # 1) 加载 pricing_gbm (一次性, 线程安全用于 predict)
    try:
        pricing_model, pricing_meta = load_pricing_gbm()
    except Exception as e:
        print(f"❌ 加载 pricing_gbm 失败, 跳过价格评估: {e}")
        return {'evaluated': 0, 'error': str(e)}

    # 2) 准备 (stock, file_path, market) 元组
    items = []
    for stock in passed_stocks:
        code_full = stock.get('stock_code')
        if not code_full:
            continue
        market = code_full[:2].lower()
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{code_full}.day')
        if not os.path.exists(file_path):
            continue
        items.append((stock, file_path, market))

    if not items:
        print("⚠️ 没有可用的日线文件可评估")
        return {'evaluated': 0}

    # 3) 创建全局共享组件 (EnhancedTradingAnalyzer 内部无状态, 线程安全)
    analyzer = EnhancedTradingAnalyzer()
    advisor = TradingAdvisor()

    # 4) 价格评估工作函数
    def _do_price_eval(stock, file_path, market):
        code_full = stock['stock_code']
        code_no_prefix = code_full.replace(market, '')

        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 150:
            return {'gbm_shallow_proba': None, 'price_evaluation': {'error': '数据不足'}}

        if ADJUSTMENT_TYPE != 'none':
            try:
                df = _adj_processor.process_data(df, code_no_prefix)
            except Exception as e:
                return {'gbm_shallow_proba': None, 'price_evaluation': {'error': f'复权失败: {e}'}}

        # Phase 1: pricing_gbm 快筛
        # pricing_gbm.build_features 依赖 T1_* 列; 选股阶段的 df 仅有 OHLCV,
        # 故补 NaN 让模型以缺失值路径打分 (不抛 KeyError)。
        # 同时补 one-hot 前缀列 (market_env / v44_trend / v44_bias_tier),
        # 否则 pd.get_dummies 生成不出对应 dummy, predict_proba 报缺列。
        t1_cols = ['T1_Open', 'T1_High', 'T1_Low', 'T1_Close']
        oh_cols = ['market_env', 'v44_trend', 'v44_bias_tier']
        added_cols = []
        for c in t1_cols:
            if c not in df.columns:
                df[c] = np.nan
                added_cols.append(c)
        if 'close_t0' not in df.columns:
            df['close_t0'] = df['close']
            added_cols.append('close_t0')
        for c in oh_cols:
            if c not in df.columns:
                df[c] = 'unknown'
                added_cols.append(c)
        try:
            proba_arr = score_entry_strategy(df, pricing_model, pricing_meta)
            proba = float(proba_arr[-1]) if len(proba_arr) > 0 else 0.0
        except Exception as e:
            proba = 0.0
            gbm_err = f'pricing_gbm 打分失败: {e}'
            return {'gbm_shallow_proba': None, 'price_evaluation': {'error': gbm_err}}
        finally:
            if added_cols:
                df.drop(columns=added_cols, errors='ignore', inplace=True)

        if proba < gbm_threshold:
            return {'gbm_shallow_proba': proba, 'price_evaluation': None}

        # Phase 2: 完整分析 + 价格评估
        # EnhancedTradingAnalyzer 按 stock_code 直接拼盘文件名 (大小写敏感),
        # 磁盘上是小写 (sz300750.day); 统一小写传入。
        code_for_analyzer = code_full.lower()
        try:
            analysis = analyzer.analyze_stock_comprehensive(code_for_analyzer, use_optimized_params=True)
        except Exception as e:
            return {'gbm_shallow_proba': proba, 'price_evaluation': {'error': f'综合分析失败: {e}'}}

        if 'error' in analysis:
            return {'gbm_shallow_proba': proba, 'price_evaluation': {'error': analysis['error']}}

        try:
            _, price_eval = perform_price_evaluation(code_for_analyzer, analysis)
        except Exception as e:
            price_eval = {'error': f'perform_price_evaluation: {e}'}

        # 增强: 附加 entry_strategies 的自适应建议 (便于主流程打印)
        if 'error' not in price_eval:
            price_eval['gbm_shallow_proba'] = proba
            advice = analysis.get('trading_advice', {}).get('advice', {})
            if advice:
                price_eval['entry_strategies'] = advice.get('entry_strategies', [])
                price_eval['risk_management'] = advice.get('risk_management', {})

        return {'gbm_shallow_proba': proba, 'price_evaluation': price_eval}

    # 5) 并发执行
    evaluated = 0
    passed_gbm = 0
    passed_full = 0
    failed = 0
    proba_sum = 0.0
    proba_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_do_price_eval, s, f, m): s for s, f, m in items}
        for fut in as_completed(futures):
            stock = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                stock['price_evaluation'] = {'error': f'线程异常: {e}'}
                failed += 1
                continue

            if res.get('gbm_shallow_proba') is not None:
                proba_sum += res['gbm_shallow_proba']
                proba_count += 1

            stock['gbm_shallow_proba'] = res.get('gbm_shallow_proba')
            pe = res.get('price_evaluation')
            if pe is None:
                # Phase 1 淘汰, 不写入 price_evaluation (保持 None 语义)
                continue
            stock['price_evaluation'] = pe
            evaluated += 1
            if 'error' in pe:
                failed += 1
            else:
                passed_full += 1
            if res.get('gbm_shallow_proba') is not None and res['gbm_shallow_proba'] >= gbm_threshold:
                passed_gbm += 1

    avg_proba = (proba_sum / proba_count) if proba_count else 0.0

    # 6) 保存汇总
    summary = {
        'scan_date': DATE,
        'strategy': STRATEGY_TO_RUN,
        'total_input': len(passed_stocks),
        'evaluated_count': evaluated,
        'passed_gbm_count': passed_gbm,
        'passed_full_count': passed_full,
        'failed_count': failed,
        'gbm_threshold': gbm_threshold,
        'avg_gbm_proba': round(avg_proba, 4),
    }
    try:
        summary_file = os.path.join(RESULT_DIR, 'price_evaluation_summary.json')
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(convert_numpy_types(summary), f, ensure_ascii=False, indent=2)
    except Exception as e:
        get_logger().warning(f"保存 price_evaluation_summary 失败: {e}")

    print(f"✅ 价格评估完成:")
    print(f"  📊 已评估: {evaluated}/{len(passed_stocks)}")
    print(f"  🟢 通过 GBM 快筛 (≥{gbm_threshold}): {passed_gbm}")
    print(f"  💰 通过完整评估: {passed_full}")
    print(f"  ❌ 失败: {failed}")
    print(f"  📈 平均 GBM 浅入场概率: {avg_proba:.3f}")

    get_logger().info(
        f"Price eval done: evaluated={evaluated}, passed_gbm={passed_gbm}, "
        f"passed_full={passed_full}, failed={failed}, avg_proba={avg_proba:.3f}"
    )
    return summary


def perform_price_evaluation(stock_code, analysis_result):
    """轻量级本地价格评估 (避免从 run_enhanced_screening 循环导入)。

    提取 trading_advice 中的 entry_strategies / risk_management, 生成
    结构化的 price_evaluation dict 并保存到 A_GRADE_EVALUATIONS 目录。
    """
    try:
        basic = analysis_result.get('basic_analysis', {})
        current_price = basic.get('current_price', 0)
        trading = analysis_result.get('trading_advice', {})
        advice = trading.get('advice', {}) if isinstance(trading, dict) else {}

        price_evaluation = {
            'evaluation_time': datetime.now().isoformat(),
            'stock_code': stock_code,
            'current_price': current_price,
            'grade': analysis_result.get('overall_score', {}).get('grade', 'N/A'),
            'evaluation_details': {},
        }

        if isinstance(advice, dict) and 'entry_strategies' in advice and advice['entry_strategies']:
            strategy = advice['entry_strategies'][0]
            entry_p1 = strategy.get('entry_price_1', current_price) or current_price
            entry_p2 = strategy.get('entry_price_2', current_price) or current_price
            price_evaluation['evaluation_details'] = {
                'entry_strategy': strategy.get('strategy', 'N/A'),
                'target_price_1': entry_p1,
                'target_price_2': entry_p2,
                'position_allocation': strategy.get('position_allocation', 'N/A'),
                'discount_1': ((current_price - entry_p1) / current_price) if current_price > 0 else 0,
                'discount_2': ((current_price - entry_p2) / current_price) if current_price > 0 else 0,
            }

        if isinstance(advice, dict) and 'risk_management' in advice:
            risk_mgmt = advice['risk_management']
            if 'stop_loss_levels' in risk_mgmt:
                stops = risk_mgmt['stop_loss_levels']
                price_evaluation['evaluation_details']['stop_loss'] = {
                    'conservative': stops.get('conservative', 0),
                    'moderate': stops.get('moderate', 0),
                    'aggressive': stops.get('aggressive', 0),
                    'technical': stops.get('technical', 0),
                }
            if 'take_profit_levels' in risk_mgmt:
                profits = risk_mgmt['take_profit_levels']
                price_evaluation['evaluation_details']['take_profit'] = {
                    'conservative': profits.get('conservative', 0),
                    'moderate': profits.get('moderate', 0),
                    'aggressive': profits.get('aggressive', 0),
                }

        # 保存记录
        try:
            eval_dir = os.path.join('data', 'result', 'A_GRADE_EVALUATIONS')
            os.makedirs(eval_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M")
            stock_file = os.path.join(eval_dir, f"{stock_code}_evaluation_{ts}.json")
            with open(stock_file, 'w', encoding='utf-8') as f:
                json.dump(price_evaluation, f, ensure_ascii=False, indent=2)
        except Exception as e:
            get_logger().warning(f"保存 A_GRADE_EVALUATIONS 失败: {e}")

        return stock_code, price_evaluation
    except Exception as e:
        return stock_code, {'error': f'价格评估失败: {e}'}


def main():
    """主执行函数 - 增强版本，集成深度扫描，多线程操作"""
    start_time = datetime.now()
    get_logger().info(f"===== 开始执行批量筛选, 策略: {STRATEGY_TO_RUN} =====")
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
                elif 'v5_score' in stock:
                    tier = stock.get('v5_tier', 'C')
                    gbm = stock.get('gbm_proba', 0)
                    mkt = stock.get('market_env', '')
                    trigger = stock.get('trigger_buy_price', 0)
                    stop = stock.get('stop_loss_price', 0)
                    target = stock.get('target_price', 0)
                    v44_trend = stock.get('v44_trend', '')
                    v44_grade = stock.get('v44_grade', '')
                    morse_info = (f"\n    └─ v5: {stock['v5_score']}分 [{tier}] | GBM: {gbm:.3f} | 环境: {mkt}\n"
                                  f"    └─ 趋势: {v44_trend} | 等级: {v44_grade}\n"
                                  f"    └─ 🛒 买点: ¥{trigger} | 🎯 目标: ¥{target} | 🛑 止损: ¥{stop}\n")
                    f.write(f"{i:2d}. {stock['stock_code']} - 现价: ¥{stock.get('close_t0', 'N/A')}" + morse_info)
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

    # 新增: 主筛选后统一跑价格评估 (pricing_gbm 快筛 + 完整评估)
    price_eval_summary = {}
    if len(passed_stocks) > 0:
        print(f"\n" + "="*60)
        print(f"💰 启动价格评估阶段 (主筛选后统一跑)")
        print(f"="*60)
        try:
            price_eval_summary = run_price_evaluation_batch(passed_stocks) or {}

            # 统计通过价格评估的股票, 合并进 summary_report
            price_eval_pass = [
                s['stock_code'] for s in passed_stocks
                if isinstance(s.get('price_evaluation'), dict) and 'error' not in s['price_evaluation']
            ]
            gbm_passed = [
                s['stock_code'] for s in passed_stocks
                if (s.get('gbm_shallow_proba') or 0) >= 0.5
            ]
            summary_report['price_evaluation_summary'] = {
                'total_input': price_eval_summary.get('total_input', len(passed_stocks)),
                'evaluated_count': price_eval_summary.get('evaluated_count', 0),
                'passed_gbm_count': len(gbm_passed),
                'passed_full_count': len(price_eval_pass),
                'failed_count': price_eval_summary.get('failed_count', 0),
                'avg_gbm_proba': price_eval_summary.get('avg_gbm_proba', 0),
                'price_evaluated_stocks': price_eval_pass,
                'gbm_passed_stocks': gbm_passed,
            }
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(convert_numpy_types(summary_report), f, ensure_ascii=False, indent=4)

            # 文本报告追加价格评估章节
            with open(text_report_file, 'a', encoding='utf-8') as f:
                f.write(f"\n=== 价格评估结果 ===\n")
                f.write(f"待评估: {price_eval_summary.get('total_input', 0)}\n")
                f.write(f"已评估: {price_eval_summary.get('evaluated_count', 0)}\n")
                f.write(f"通过 GBM 快筛 (≥0.5): {len(gbm_passed)}\n")
                f.write(f"通过完整评估: {len(price_eval_pass)}\n")
                f.write(f"平均 GBM 浅入场概率: {price_eval_summary.get('avg_gbm_proba', 0):.3f}\n\n")

                for s in passed_stocks:
                    pe = s.get('price_evaluation')
                    if not isinstance(pe, dict) or 'error' in pe:
                        continue
                    details = pe.get('evaluation_details', {})
                    entry1 = details.get('target_price_1', 0)
                    entry2 = details.get('target_price_2', 0)
                    stops = details.get('stop_loss', {})
                    profits = details.get('take_profit', {})
                    proba = s.get('gbm_shallow_proba', 0) or 0
                    f.write(f"💰 {s['stock_code']} 现价: ¥{pe.get('current_price', 0):.2f} "
                            f"(GBM={proba:.2f}, 等级: {pe.get('grade', 'N/A')})\n")
                    f.write(f"   ├─ 入场策略: {details.get('entry_strategy', 'N/A')} | "
                            f"仓位: {details.get('position_allocation', 'N/A')}\n")
                    f.write(f"   ├─ 挂单价位 1: ¥{entry1:.2f} (折 {details.get('discount_1', 0)*100:+.1f}%) | "
                            f"价位 2: ¥{entry2:.2f} (折 {details.get('discount_2', 0)*100:+.1f}%)\n")
                    if stops:
                        f.write(f"   ├─ 止损 (保守/适中/激进/技术): "
                                f"¥{stops.get('conservative',0):.2f} / ¥{stops.get('moderate',0):.2f} / "
                                f"¥{stops.get('aggressive',0):.2f} / ¥{stops.get('technical',0):.2f}\n")
                    if profits:
                        f.write(f"   └─ 止盈 (保守/适中/激进): "
                                f"¥{profits.get('conservative',0):.2f} / ¥{profits.get('moderate',0):.2f} / "
                                f"¥{profits.get('aggressive',0):.2f}\n")
                    f.write("-" * 50 + "\n")
        except Exception as e:
            get_logger().error(f"价格评估阶段异常: {e}")
            print(f"❌ 价格评估阶段异常: {e}")

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
    
    get_logger().info(f"===== 完整扫描完成！初步筛选: {len(passed_stocks)} 个信号，总耗时: {total_time:.2f} 秒 =====")

if __name__ == '__main__':
    main()
