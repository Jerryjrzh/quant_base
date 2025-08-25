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
from win_rate_filter import WinRateFilter, AdvancedTripleCrossFilter
import talib

# === 最终优化后的策略逻辑 START ===
# 这是经过重构的、逻辑更严谨、更有效的价值反转策略
def apply_value_reversal_final(df):
    """
    价值反转策略 (VALUE_REVERSAL) - 最终优化版
    核心逻辑：寻找“MACD底背离”这一核心形态，并由“RSI反弹”或“均线突破”来确认。

    - 信号A (核心): MACD底背离 - 价格在近期低位，但MACD指标形成更高低点。
    - 信号B (确认): RSI超卖反弹 - RSI从40以下的低位区回升。
    - 信号C (确认): 动量点火 - 价格放量突破20日均线。

    触发条件：(信号A 且 (信号B 或 信号C)) 或 (信号B 且 信号C)
    """
    if len(df) < 60:
        return None

    try:
        # 统一计算所需指标
        df['ma20'] = talib.MA(df['close'], timeperiod=20)
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        macd, signal, _ = talib.MACD(df['close'], fastperiod=12, slowperiod=26, signalperiod=9)
        df['macd'] = macd
        df['rsi'] = talib.RSI(df['close'], timeperiod=14)

        signal_series = pd.Series(False, index=df.index)
        
        # 只检查最后一个交易日的数据
        current_idx = -1
        if pd.isna(df.iloc[current_idx]).any() or pd.isna(df.iloc[current_idx-1]).any():
            return None # 如果数据不完整则跳过

        current_data = df.iloc[current_idx]
        prev_data = df.iloc[current_idx - 1]

        # --- 初始化信号 ---
        signal_A = False # MACD底背离
        signal_B = False # RSI反弹
        signal_C = False # 动量点火

        # --- 信号A: 准确的MACD底背离检测 ---
        lookback_period = 60
        recent_data = df.iloc[-lookback_period:]
        price_trough_date = recent_data['close'].idxmin()
        
        # 只有当最低点不是今天或昨天时，背离才有意义
        if (df.index[current_idx] - price_trough_date).days > 2:
            macd_at_trough = df.loc[price_trough_date]['macd']
            # 条件：当前价格仍接近前期低点，但MACD已显著抬高
            if current_data['close'] < df.loc[price_trough_date]['close'] * 1.15 and current_data['macd'] > macd_at_trough:
                # 进一步确认MACD是上升的
                if macd_at_trough < 0 and current_data['macd'] > macd_at_trough * 0.5: # 如果在水下，要求反弹更多
                     signal_A = True
                elif macd_at_trough >= 0:
                     signal_A = True

        # --- 信号B: RSI超卖区反弹 ---
        if prev_data['rsi'] < 40 and current_data['rsi'] > prev_data['rsi']:
            signal_B = True
            
        # --- 信号C: 放量突破MA20 ---
        if (prev_data['close'] < prev_data['ma20'] and 
            current_data['close'] > current_data['ma20'] and 
            current_data['volume'] > current_data['volume_ma20'] * 1.5):
            signal_C = True

        # --- 最终信号决策 ---
        # 规则1: 出现底背离，并且有任一动量信号确认
        if signal_A and (signal_B or signal_C):
            signal_series.iloc[current_idx] = True
        
        # 规则2: 没有明显背离，但是RSI和MA突破信号同时出现，形成强力反转
        if signal_B and signal_C:
            signal_series.iloc[current_idx] = True
            
        return signal_series

    except Exception as e:
        return None

# 将最终的策略函数注册到 strategies 模块（模拟）
strategies.apply_value_reversal_strategy = apply_value_reversal_final
# === 最终优化后的策略逻辑 END ===


# --- 配置 ---
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz', 'bj']
# --- 您可以在这里切换要运行的策略 ---
#STRATEGY_TO_RUN = 'MACD_ZERO_AXIS' 
#STRATEGY_TO_RUN = 'TRIPLE_CROSS' 
#STRATEGY_TO_RUN = 'PRE_CROSS'
#STRATEGY_TO_RUN = 'WEEKLY_GOLDEN_CROSS_MA'
STRATEGY_TO_RUN = 'VALUE_REVERSAL' # <--- 运行我们最终优化的策略

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
    """
    try:
        if signal_state not in ['PRE', 'MID', 'POST']:
            return False, ""
        
        start_idx = max(0, signal_idx - lookback_days)
        end_idx = signal_idx
        
        if start_idx >= end_idx:
            return False, ""
        
        lookback_data = df.iloc[start_idx:end_idx + 1]
        if len(lookback_data) < 2:
            return False, ""
        
        base_price = lookback_data.iloc[0]['close']
        current_high = df.iloc[signal_idx]['high']
        price_increase = (current_high - base_price) / base_price
        
        if price_increase > 0.25 or price_increase < 0.05:
            return True, f"五日内涨幅{price_increase:.1%}超过25%或者低于5%，排除不活跃风险"
        
        return False, ""
        
    except Exception as e:
        print(f"MACD零轴预筛选过滤器检查失败: {e}")
        return False, ""

def check_weekly_golden_cross_ma_filter(df, signal_idx, signal_state, stock_code):
    """
    周线金叉+日线MA策略的过滤器
    """
    try:
        if signal_state != 'BUY':
            return False, ""
        
        if len(df) < 240:
            return True, "数据长度不足，无法计算长期MA"
        
        current_price = df.iloc[signal_idx]['close']
        ma13 = df['close'].rolling(window=13).mean().iloc[signal_idx]
        
        if pd.isna(ma13):
            return True, "MA13计算失败"
        
        price_distance = (current_price - ma13) / ma13
        if price_distance > 0.05:
            return True, f"价格距离MA13过远({price_distance:.1%})，排除追高风险"
        
        if 'volume' in df.columns:
            current_volume = df.iloc[signal_idx]['volume']
            avg_volume = df['volume'].rolling(window=20).mean().iloc[signal_idx]
            
            if not pd.isna(avg_volume) and avg_volume > 0:
                volume_ratio = current_volume / avg_volume
                if volume_ratio > 5.0:
                    return True, f"成交量异常放大({volume_ratio:.1f}倍)，可能存在风险"
        
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
    """
    try:
        ma_periods = [7, 13, 30, 45]
        mas = {}
        for period in ma_periods:
            mas[f'ma_{period}'] = df['close'].rolling(window=period).mean()
        
        current_price = df['close'].iloc[-1]
        ma13_current = mas['ma_13'].iloc[-1]
        
        trend_strength = 0
        if not pd.isna(ma13_current):
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
        
        ma13_distance = 0
        if not pd.isna(ma13_current) and ma13_current > 0:
            ma13_distance = (current_price - ma13_current) / ma13_current
        
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
    TRIPLE_CROSS策略的增强过滤器
    """
    try:
        advanced_filter = AdvancedTripleCrossFilter()
        should_exclude, exclude_reason, quality_score, cross_stage = advanced_filter.enhanced_triple_cross_filter(df, signal_idx)
        
        if should_exclude:
            return True, exclude_reason, {}
        
        signal_series = strategies.apply_triple_cross(df)
        if signal_series is not None:
            win_rate_filter = WinRateFilter(min_win_rate=0.4, min_signals=3, min_avg_profit=0.08)
            should_exclude_wr, exclude_reason_wr, backtest_stats = win_rate_filter.should_exclude_stock(df, signal_series, stock_code)
            
            if should_exclude_wr:
                return True, f"胜率筛选: {exclude_reason_wr}", {'backtest_stats': backtest_stats}
        
        return False, "通过增强筛选", {'backtest_stats': backtest_stats if 'backtest_stats' in locals() else {}}
        
    except Exception as e:
        return True, f"增强过滤器执行失败: {e}", {}

def worker(args):
    """多进程工作函数"""
    file_path, market = args
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code_no_prefix = stock_code_full.replace(market, '')

    valid_prefixes = ('600', '601', '603', '000', '001', '002', '003', '300', '688')
    if not stock_code_no_prefix.startswith(valid_prefixes):
        return None

    try:
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 150:
            return None

        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        latest_date = df.index[-1].strftime('%Y-%m-%d')
        
        result_base = {
            'stock_code': stock_code_full,
            'strategy': STRATEGY_TO_RUN,
            'date': latest_date,
            'scan_timestamp': current_timestamp
        }
        
        if STRATEGY_TO_RUN == 'PRE_CROSS':
            return _process_pre_cross_strategy(df, result_base)
        elif STRATEGY_TO_RUN == 'TRIPLE_CROSS':
            return _process_triple_cross_strategy(df, result_base, stock_code_full)
        elif STRATEGY_TO_RUN == 'MACD_ZERO_AXIS':
            return _process_macd_zero_axis_strategy(df, result_base, stock_code_full)
        elif STRATEGY_TO_RUN == 'WEEKLY_GOLDEN_CROSS_MA':
            return _process_weekly_golden_cross_ma_strategy(df, result_base, stock_code_full)
        elif STRATEGY_TO_RUN == 'VALUE_REVERSAL':
            return _process_value_reversal_strategy(df, result_base)
            
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
    except Exception:
        return None

def _process_triple_cross_strategy(df, result_base, stock_code_full):
    """处理TRIPLE_CROSS策略"""
    try:
        signal_series = strategies.apply_triple_cross(df)
        if signal_series is not None and signal_series.iloc[-1]:
            should_exclude, exclude_reason, filter_details = check_triple_cross_enhanced_filter(df, len(df) - 1, stock_code_full)
            
            if should_exclude:
                logger.info(f"{stock_code_full} 被过滤: {exclude_reason}")
                return None
            
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            result_base.update({
                'filter_status': 'passed',
                **backtest_stats
            })
            return result_base
        return None
    except Exception:
        return None

def _process_macd_zero_axis_strategy(df, result_base, stock_code_full):
    """处理MACD_ZERO_AXIS策略"""
    try:
        signal_series = strategies.apply_macd_zero_axis_strategy(df)
        signal_state = signal_series.iloc[-1]
        if signal_state in ['PRE', 'MID', 'POST']:
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
    except Exception:
        return None

def _process_weekly_golden_cross_ma_strategy(df, result_base, stock_code_full):
    """处理WEEKLY_GOLDEN_CROSS_MA策略"""
    try:
        signal_series = strategies.apply_weekly_golden_cross_ma_strategy(df)
        signal_state = signal_series.iloc[-1]
        
        if signal_state in ['BUY', 'HOLD', 'SELL']:
            should_exclude, exclude_reason = check_weekly_golden_cross_ma_filter(df, len(df) - 1, signal_state, stock_code_full)
            
            if should_exclude:
                logger.info(f"{stock_code_full} 被过滤: {exclude_reason}")
                return None
            
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
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

def _process_value_reversal_strategy(df, result_base):
    """处理VALUE_REVERSAL策略"""
    try:
        signal_series = strategies.apply_value_reversal_strategy(df)
        if signal_series is not None and signal_series.iloc[-1]:
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            result_base.update({
                'filter_status': 'passed',
                **backtest_stats
            })
            return result_base
        return None
    except Exception as e:
        logger.error(f"处理价值反转策略失败 {result_base.get('stock_code', '')}: {e}")
        return None

def calculate_backtest_stats_fast(df, signal_series):
    """快速计算回测统计信息"""
    try:
        if 'dif' not in df.columns or 'dea' not in df.columns:
            macd_values = indicators.calculate_macd(df)
            df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        if 'k' not in df.columns or 'd' not in df.columns:
            kdj_values = indicators.calculate_kdj(df)
            df['k'], df['d'], df['j'] = kdj_values[0], kdj_values[1], kdj_values[2]
        
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
            return {'total_signals': 0, 'win_rate': '0.0%', 'avg_max_profit': '0.0%', 'avg_max_drawdown': '0.0%', 'avg_days_to_peak': '0.0 天'}
    except Exception as e:
        logger.error(f"快速回测计算失败: {e}")
        return {'total_signals': 0, 'win_rate': '0.0%', 'avg_max_profit': '0.0%', 'avg_max_drawdown': '0.0%', 'avg_days_to_peak': '0.0 天'}

def generate_summary_report(passed_stocks):
    """生成详细的汇总报告"""
    if not passed_stocks:
        return {
            'scan_summary': {'total_signals': 0, 'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'strategy': STRATEGY_TO_RUN, 'total_historical_signals': 0, 'avg_win_rate': '0.0%', 'avg_profit_rate': '0.0%', 'avg_days_to_peak': '0.0 天'},
            'signal_breakdown': {},
            'top_performers': []
        }
    
    total_signals = len(passed_stocks)
    
    signal_states = {}
    if STRATEGY_TO_RUN == 'MACD_ZERO_AXIS':
        for stock in passed_stocks:
            state = stock.get('signal_state', 'UNKNOWN')
            if state not in signal_states:
                signal_states[state] = []
            signal_states[state].append(stock)
    
    total_historical_signals = sum(stock.get('total_signals', 0) for stock in passed_stocks if stock.get('total_signals', 0) > 0)
    
    win_rates = [float(s.get('win_rate', '0.0%').replace('%', '')) for s in passed_stocks if s.get('total_signals', 0) > 0]
    profit_rates = [float(s.get('avg_max_profit', '0.0%').replace('%', '')) for s in passed_stocks if s.get('total_signals', 0) > 0]
    days_to_peak = [float(s.get('avg_days_to_peak', '0.0 天').replace(' 天', '')) for s in passed_stocks if s.get('total_signals', 0) > 0]
    
    avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
    avg_profit_rate = sum(profit_rates) / len(profit_rates) if profit_rates else 0
    avg_days_to_peak = sum(days_to_peak) / len(days_to_peak) if days_to_peak else 0
    
    summary = {
        'scan_summary': {
            'total_signals': total_signals, 'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'strategy': STRATEGY_TO_RUN, 'total_historical_signals': total_historical_signals, 'avg_win_rate': f"{avg_win_rate:.1f}%", 'avg_profit_rate': f"{avg_profit_rate:.1f}%", 'avg_days_to_peak': f"{avg_days_to_peak:.1f} 天"
        },
        'signal_breakdown': signal_states,
        'top_performers': sorted([s for s in passed_stocks if s.get('total_signals', 0) > 0], key=lambda x: float(x.get('avg_max_profit', '0%').replace('%', '')), reverse=True)[:10]
    }
    
    return summary

def trigger_deep_scan_multithreaded(passed_stocks):
    """触发多线程深度扫描"""
    if not passed_stocks:
        print("⚠️ 没有通过筛选的股票，跳过深度扫描")
        return None
    
    print(f"\n🔍 触发多线程深度扫描...")
    print(f"📊 筛选出 {len(passed_stocks)} 只股票进行深度分析")
    
    stock_codes = [stock['stock_code'] for stock in passed_stocks]
    
    try:
        from run_enhanced_screening import deep_scan_stocks
        max_workers = min(cpu_count() * 2, len(stock_codes), 32)
        print(f"🧵 使用 {max_workers} 个线程进行深度扫描")
        deep_scan_results = deep_scan_stocks(stock_codes, use_optimized_params=True, max_workers=max_workers)
        print(f"✅ 多线程深度扫描完成")
        return deep_scan_results
        
    except Exception as e:
        print(f"❌ 多线程深度扫描失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """主执行函数"""
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
    
    with Pool(processes=cpu_count()) as pool:
        results = pool.map(worker, all_files)
    
    passed_stocks = [r for r in results if r is not None]
    processing_time = (datetime.now() - start_time).total_seconds()
    
    print(f"📈 初步筛选完成，通过筛选: {len(passed_stocks)} 只股票")
    
    output_file = os.path.join(RESULT_DIR, 'signals_summary.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(passed_stocks, f, ensure_ascii=False, indent=4)
    
    summary_report = generate_summary_report(passed_stocks)
    summary_report['scan_summary']['processing_time'] = f"{processing_time:.2f} 秒"
    summary_report['scan_summary']['files_processed'] = len(all_files)
    
    summary_file = os.path.join(RESULT_DIR, 'scan_summary_report.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_report, f, ensure_ascii=False, indent=4)
    
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
            f.write("=== 前10名表现最佳股票 ===\n")
            for i, stock in enumerate(summary_report['top_performers'], 1):
                f.write(f"{i:2d}. {stock['stock_code']} - 胜率: {stock.get('win_rate', 'N/A')}, "
                       f"收益: {stock.get('avg_max_profit', 'N/A')}, "
                       f"天数: {stock.get('avg_days_to_peak', 'N/A')}\n")
    
    print(f"\n📊 初步筛选完成！")
    print(f"🎯 发现信号: {len(passed_stocks)} 个")
    print(f"⏱️ 处理耗时: {processing_time:.2f} 秒")
    print(f"📈 平均胜率: {summary_report['scan_summary']['avg_win_rate']}")
    print(f"💰 平均收益: {summary_report['scan_summary']['avg_profit_rate']}")
    print(f"📄 结果已保存至:")
    print(f"  - 信号列表: {output_file}")
    print(f"  - 汇总报告: {summary_file}")
    print(f"  - 文本报告: {text_report_file}")
    
    if len(passed_stocks) > 0:
        print(f"\n" + "="*60)
        print(f"🔍 启动深度扫描阶段 (多线程)")
        print(f"="*60)
        
        deep_scan_results = trigger_deep_scan_multithreaded(passed_stocks)
        
        if deep_scan_results:
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
            
            summary_report['deep_scan_summary'] = {
                'total_analyzed': len(valid_deep_results), 'a_grade_count': len(a_grade_stocks), 'price_evaluated_count': len(price_evaluated_stocks), 'buy_recommendations': len(buy_recommendations), 'a_grade_stocks': a_grade_stocks, 'buy_recommendation_stocks': buy_recommendations
            }
            
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary_report, f, ensure_ascii=False, indent=4)
            
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
                        f.write(f"{stock_code}: {score:.1f}分, ¥{price:.2f}, {action} (信心度: {confidence:.1%}){price_eval_mark}\n")
                
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