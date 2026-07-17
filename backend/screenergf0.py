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

# =====================================================================
# === Phase 1 自适应均线右侧深踩选股策略 (Grok 强化版) ===
# =====================================================================
def apply_adaptive_ma_support_optimized(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略（强化版）
    严格按照「压力→支撑极性转换 + 短线破位恐慌 + 长线黄金坑」逻辑实现
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        # 更严格的容忍度（符合深踩特征）
        tolerance_upper = 0.025   # 2.5%
        tolerance_lower = -0.018  # 允许轻微刺穿

        best_ma = None
        highest_score = -999
        best_details = {}

        # 预计算指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        
        # 兼容你的 KDJ 计算模块
        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            # 1. 大基座：长期趋势必须向上
            if ma_series.iloc[-1] < ma_series.iloc[-20]:
                continue

            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # ==================== 核心强化逻辑 ====================

            # 【修复点1】压力支撑极性转换（时序验证）
            was_resistance = (historical['close'] < hist_ma).mean() > 0.62
            
            # 突破确认：最近120天内出现过放量上穿
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > recent['volume'].rolling(20).mean() * 1.8)
            has_breakthrough = breakthrough.any()

            # 突破后回踩确认（极性转换核心）
            post_breakthrough = recent[crossover.cumsum() > 0]  # 突破之后的数据
            if not post_breakthrough.empty and len(post_breakthrough) > 5:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (
                    (post_breakthrough['low'] <= post_ma * 1.015) & 
                    (post_breakthrough['close'] >= post_ma * 0.982)
                )
                has_valid_retest = valid_retest.sum() >= 1
            else:
                has_valid_retest = False

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 【修复点2】短线破位 + 长线支撑（深踩恐慌结构）
            ma13 = talib.MA(df['close'], timeperiod=13)
            ma30 = talib.MA(df['close'], timeperiod=30)
            
            short_broken = (recent['close'] < ma13.iloc[-120:]) & (recent['close'] < ma30.iloc[-120:])
            near_long_ma = (abs(recent['close'] - recent_ma) / recent_ma) <= 0.025
            deep_step_pattern = short_broken & near_long_ma

            valid_deep_touches = deep_step_pattern.sum()

            # 【修复点3】动量极值反转
            macd_bottom = macdhist.iloc[-120:]
            macd_improving = (macd_bottom > macd_bottom.shift(1)) & (macd_bottom < 0)
            
            j_series = j.iloc[-120:]
            j_extreme = (j_series < 20) | (j_series.shift(1) < 10)  # 极值区
            j_turning = (j_series > j_series.shift(1)) & j_extreme
            
            momentum_reversal = (macd_improving.any() | j_turning.any()) and j_turning.iloc[-5:].any()

            # 【修复点4】无效穿刺惩罚 + 其他维度打分
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            volume_on_retest = recent['volume'][deep_step_pattern].mean() if valid_deep_touches > 0 else 0
            vol_ratio = volume_on_retest / recent['volume'].rolling(20).mean().mean() if volume_on_retest > 0 else 0

            # 综合评分（大幅提升极性转换权重）
            score = 0
            score += valid_deep_touches * 8
            if polarity_confirmed:
                score += 55          # 重罚权重
            if has_valid_retest:
                score += 25
            score -= crosses * 3
            if momentum_reversal:
                score += 20
            if 0.5 < vol_ratio < 1.8:   # 缩量回踩更佳
                score += 12

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed,
                    'valid_deep_touches': int(valid_deep_touches),
                    'momentum_reversal': bool(momentum_reversal),
                    'crosses': int(crosses)
                }

        # 门槛提高
        if best_ma is None or highest_score < 35:   
            return None

        # ==================== 生成最终信号序列 ====================
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series

        is_near_ma = (distance >= tolerance_lower) & (distance <= tolerance_upper)
        
        # 最终信号条件（更严谨）
        # 这里优化了 pd.Series 的生成方式，避免索引报错
        momentum_mask = pd.Series(momentum_reversal, index=df.index)
        
        signal_series = (
            is_near_ma & 
            (df['close'] > best_ma_series * 0.982) & 
            momentum_mask
        )

        # 绑定元数据（供主控脚本提取生成执行卡）
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('valid_deep_touches', 0)

        return signal_series

    except Exception as e:
        logger.error(f"自适应均线深踩策略异常: {e}", exc_info=True)
        return None


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
    valid_prefixes = ('600', '601', '603', '000', '001', '002', '003', '300', '688')
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

def _process_adaptive_ma_support_strategy(df, result_base, stock_code_full):
    """处理 Phase 1 自适应均线右侧深踩策略"""
    try:
        signal_series = apply_adaptive_ma_support_optimized(df)
        
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
                'trigger_buy_price': round(current_ma_val * 1.005, 2), # 专属均线上方0.5%设买点
                'hard_stop_loss': round(current_ma_val * 0.96, 2),     # 跌破专属均线4%无条件离场
                **backtest_stats
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
                        confidence = result['recommendation']['confidence']
                        f.write(f"{stock_code}: {score:.1f}分, ¥{price:.2f}, 信心度: {confidence:.1%}\n")
    else:
        print(f"\n⚠️ 未发现符合条件的股票，跳过深度扫描")
    
    total_time = (datetime.now() - start_time).total_seconds()
    print(f"\n🎉 完整扫描流程结束！总耗时: {total_time:.2f} 秒")
    
    logger.info(f"===== 完整扫描完成！初步筛选: {len(passed_stocks)} 个信号，总耗时: {total_time:.2f} 秒 =====")

if __name__ == '__main__':
    main()
