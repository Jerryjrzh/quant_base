import os
import glob
import json
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging
# 假设这些模块存在于您的项目中
# import data_loader
# import backtester
# import indicators
# from win_rate_filter import WinRateFilter, AdvancedTripleCrossFilter

# --- 配置 ---
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz', 'bj']
# --- 已将新策略设为默认 ---
STRATEGY_TO_RUN = 'ABYSS_BOTTOMING'
#STRATEGY_TO_RUN = 'MACD_ZERO_AXIS'
#STRATEGY_TO_RUN = 'TRIPLE_CROSS'

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


# #############################################################################
# ##### 修正版：“深渊筑底” (Abyss Bottoming) 策略实现 #####
# #############################################################################

def apply_abyss_bottoming_strategy(df):
    """
    “深渊筑底”四部曲策略筛选函数 (修正版)
    判断当前股票是否处于“缩量挖坑”后的企稳拉升初期（最佳介入点）

    Args:
        df (pd.DataFrame): 包含'open', 'high', 'low', 'close', 'volume'的日线数据

    Returns:
        tuple: (pd.Series or None, dict or None)
               如果符合信号，返回 (信号Series, 信号详情字典)，否则返回 (None, None)
    """
    signal_series = pd.Series(index=df.index, dtype=object).fillna('')
    
    # --- 参数定义 ---
    LONG_TERM_DAYS = 250 * 2
    MIN_DROP_PERCENT = 0.60
    PRICE_LOW_PERCENTILE = 0.20 # 放宽到20%
    VOLUME_LOW_PERCENTILE = 0.15 # 放宽到15%

    HIBERNATION_DAYS = 60
    HIBERNATION_VOLATILITY_MAX = 0.35 # 放宽到35%

    WASHOUT_DAYS = 30
    WASHOUT_VOLUME_SHRINK_RATIO = 0.85 # 挖坑成交量小于横盘期的85%
    
    # 第三阶段（拉升）的判断参数
    MAX_RISE_FROM_BOTTOM = 0.15 # 从坑底最大反弹幅度不超过15%
    LIFTOFF_VOLUME_INCREASE_RATIO = 1.2 # 启动日成交量至少是坑内均量的1.2倍

    try:
        if len(df) < LONG_TERM_DAYS:
            return None, None

        # --- 第零阶段：深跌筑底 (The Great Premise) ---
        df_long_term = df.tail(LONG_TERM_DAYS)
        long_term_high = df_long_term['high'].max()
        long_term_low = df_long_term['low'].min()
        current_price = df['close'].iloc[-1]

        price_range = long_term_high - long_term_low
        if price_range == 0 or current_price > long_term_low + price_range * PRICE_LOW_PERCENTILE:
            return None, None
        if current_price > long_term_high * (1 - MIN_DROP_PERCENT):
            return None, None
        recent_avg_volume = df['volume'].tail(20).mean()
        volume_low_threshold = df_long_term['volume'].quantile(VOLUME_LOW_PERCENTILE)
        if recent_avg_volume > volume_low_threshold:
            return None, None

        # --- 第一阶段 & 第二阶段：寻找 横盘 + 挖坑 结构 ---
        df_washout = df.tail(WASHOUT_DAYS)
        df_hibernation = df.iloc[-(WASHOUT_DAYS + HIBERNATION_DAYS):-WASHOUT_DAYS]

        if df_hibernation.empty:
            return None, None

        hibernation_support = df_hibernation['low'].min()
        hibernation_resistance = df_hibernation['high'].max()
        
        volatility = (hibernation_resistance - hibernation_support) / hibernation_support
        if volatility > HIBERNATION_VOLATILITY_MAX or volatility <= 0:
            return None, None
        
        hibernation_avg_volume = df_hibernation['volume'].mean()
        if hibernation_avg_volume == 0:
            return None, None

        washout_low = df_washout['low'].min()
        if washout_low >= hibernation_support:
            return None, None

        pit_days_volume = df_washout[df_washout['low'] < hibernation_support]['volume']
        if pit_days_volume.empty:
            return None, None
        
        washout_avg_volume = pit_days_volume.mean()
        if washout_avg_volume == 0:
            return None, None
            
        if washout_avg_volume >= hibernation_avg_volume * WASHOUT_VOLUME_SHRINK_RATIO:
            return None, None

        # --- 第三阶段：确认拉升 (The Liftoff) - 核心逻辑修正 ---
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        # 条件1: 当天必须是阳线
        is_reversal_day = last_row['close'] > last_row['open'] and last_row['close'] > prev_row['close']
        
        # 条件2: 股价尚未远离坑底 (防止追高)
        is_near_bottom = last_row['close'] < washout_low * (1 + MAX_RISE_FROM_BOTTOM)
        
        # 条件3: 成交量必须温和放大 (确认资金入场)
        is_volume_recovering = last_row['volume'] > washout_avg_volume * LIFTOFF_VOLUME_INCREASE_RATIO

        # 最终判断：三个条件必须同时满足
        if is_reversal_day and is_near_bottom and is_volume_recovering:
            signal_series.iloc[-1] = 'BUY'
            
            # 准备详细信息以供输出
            details = {
                'signal_state': 'BUY-LIFTOFF',
                'hibernation_support': f"{hibernation_support:.2f}",
                'washout_low': f"{washout_low:.2f}",
                'rise_from_low': f"{(last_row['close'] / washout_low - 1):.2%}",
                'volume_ratio': f"{(last_row['volume'] / washout_avg_volume):.2f}x"
            }
            return signal_series, details
        
        return None, None

    except Exception:
        return None, None


# 为了让脚本可以独立运行，我们将其他策略函数创建为虚拟函数
# 在您的实际使用中，请确保 strategies 模块和其中的函数是真实存在的
class StrategyHolder: pass
strategies = StrategyHolder()
def dummy_strategy(df):
    return pd.Series([False] * len(df), index=df.index)

strategies.apply_abyss_bottoming_strategy = apply_abyss_bottoming_strategy
strategies.apply_pre_cross = dummy_strategy
strategies.apply_triple_cross = dummy_strategy
strategies.apply_macd_zero_axis_strategy = dummy_strategy
strategies.apply_weekly_golden_cross_ma_strategy = dummy_strategy

# 同样，为其他依赖创建虚拟对象
class DummyModule:
    def __getattr__(self, name):
        def _dummy_func(*args, **kwargs): return None
        return _dummy_func
class DummyFilter: pass
data_loader = DummyModule()
backtester = DummyModule()
indicators = DummyModule()
WinRateFilter = DummyFilter
AdvancedTripleCrossFilter = DummyFilter


# #############################################################################
# #####               原有脚本主要逻辑（已适配新策略）               #####
# #############################################################################

def worker(args):
    """多进程工作函数"""
    file_path, market = args
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code_no_prefix = stock_code_full.replace(market, '')

    valid_prefixes = ('600', '601', '603', '000', '001', '002', '003', '300', '688')
    if not stock_code_no_prefix.startswith(valid_prefixes):
        return None

    try:
        # 假设 data_loader.get_daily_data 是您项目中真实存在的函数
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 250 * 2: # 策略需要至少2年数据
            return None

        current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        latest_date = df.index[-1].strftime('%Y-%m-%d')
        
        result_base = {
            'stock_code': stock_code_full,
            'strategy': STRATEGY_TO_RUN,
            'date': latest_date,
            'scan_timestamp': current_timestamp
        }
        
        # 根据策略分发
        if STRATEGY_TO_RUN == 'ABYSS_BOTTOMING':
            return _process_abyss_bottoming_strategy(df, result_base)
        # ... (其他策略的处理函数)
        
        return None
        
    except Exception as e:
        # logger.error(f"处理 {stock_code_full} 时发生未知错误: {e}")
        return None

def _process_abyss_bottoming_strategy(df, result_base):
    """处理“深渊筑底”策略"""
    try:
        signal_series, details = strategies.apply_abyss_bottoming_strategy(df)
        
        # 检查最新一天是否有'BUY'信号
        if signal_series is not None and details is not None and signal_series.iloc[-1] == 'BUY':
            # 将策略返回的详细信息合并到结果中
            result_base.update(details)
            # 对于这种信号稀少的策略，回测意义不大，直接报告发现
            result_base.update({
                'total_signals': 1,
                'win_rate': 'N/A',
                'avg_max_profit': 'N/A',
            })
            return result_base
        return None
    except Exception as e:
        logger.error(f"处理深渊筑底策略失败 {result_base.get('stock_code', '')}: {e}")
        return None

def generate_summary_report(passed_stocks):
    """生成汇总报告"""
    if not passed_stocks:
        return {
            'scan_summary': {'total_signals': 0, 'strategy': STRATEGY_TO_RUN},
            'stocks_found': []
        }
    
    summary = {
        'scan_summary': {
            'total_signals': len(passed_stocks),
            'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'strategy': STRATEGY_TO_RUN,
        },
        'stocks_found': passed_stocks # 直接列出所有找到的股票及其详情
    }
    return summary


def main():
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
    # 注意：Windows下多进程调试可能不便，可以先用 map 代替 pool.map 进行单进程测试
    # results = list(map(worker, all_files))
    with Pool(processes=cpu_count()) as pool:
        results = pool.map(worker, all_files)
    
    passed_stocks = [r for r in results if r is not None]
    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()
    
    print(f"📈 初步筛选完成，通过筛选: {len(passed_stocks)} 只股票")
    
    # 保存详细信号列表
    output_file = os.path.join(RESULT_DIR, 'signals_summary.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(passed_stocks, f, ensure_ascii=False, indent=4)
    
    # 生成并保存汇总报告
    summary_report = generate_summary_report(passed_stocks)
    summary_report['scan_summary']['processing_time'] = f"{processing_time:.2f} 秒"
    summary_report['scan_summary']['files_processed'] = len(all_files)
    
    summary_file = os.path.join(RESULT_DIR, 'scan_summary_report.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_report, f, ensure_ascii=False, indent=4)
    
    # 生成文本格式的汇总报告
    text_report_file = os.path.join(RESULT_DIR, f'scan_report_{DATE}.txt')
    with open(text_report_file, 'w', encoding='utf-8') as f:
        f.write(f"=== {STRATEGY_TO_RUN} 策略筛选报告 ===\n")
        f.write(f"扫描时间: {summary_report['scan_summary']['scan_timestamp']}\n")
        f.write(f"处理文件数: {summary_report['scan_summary']['files_processed']}\n")
        f.write(f"处理耗时: {summary_report['scan_summary']['processing_time']}\n")
        f.write(f"发现信号数: {summary_report['scan_summary']['total_signals']}\n\n")
        
        if passed_stocks:
            f.write("=== 发现信号的股票列表 ===\n")
            for i, stock in enumerate(passed_stocks, 1):
                details_str = ", ".join([f"{k}: {v}" for k, v in stock.items() if k not in ['stock_code', 'strategy', 'date', 'scan_timestamp']])
                f.write(f"{i:2d}. {stock['stock_code']} - {details_str}\n")

    print(f"\n📊 初步筛选完成！")
    print(f"🎯 发现信号: {len(passed_stocks)} 个")
    print(f"⏱️ 处理耗时: {processing_time:.2f} 秒")
    print(f"📄 结果已保存至:")
    print(f"  - 详细列表 (JSON): {output_file}")
    print(f"  - 汇总报告 (JSON): {summary_file}")
    print(f"  - 文本报告 (TXT): {text_report_file}")
    
    total_time = (datetime.now() - start_time).total_seconds()
    print(f"\n🎉 完整扫描流程结束！总耗时: {total_time:.2f} 秒")
    logger.info(f"===== 完整扫描完成！初步筛选: {len(passed_stocks)} 个信号，总耗时: {total_time:.2f} 秒 =====")

if __name__ == '__main__':
    # 为了让脚本可以独立运行，您需要提供真实的 data_loader 模块
    # 以下是一个虚拟的 data_loader 用于演示，它会创建一个随机的DataFrame
    # 请务必替换为您自己的真实数据加载函数
    class MockDataLoader:
        def get_daily_data(self, file_path):
            # 创建一个符合策略测试条件的模拟DataFrame
            dates = pd.to_datetime(pd.date_range(end=datetime.now(), periods=250 * 3, freq='D'))
            n = len(dates)
            
            # 模拟一个深跌过程
            high_price = 100
            low_price = 10
            prices = np.linspace(high_price, low_price, n)
            
            # 增加一些噪声
            noise = np.random.normal(0, 2, n).cumsum()
            prices += noise
            prices = np.maximum(prices, 1) # 价格不为负
            
            # 创建横盘期
            hibernation_start = n - 90
            hibernation_end = n - 30
            prices[hibernation_start:hibernation_end] = np.random.uniform(low_price, low_price * 1.15, 60)
            
            # 创建挖坑
            pit_end = n-1
            prices[hibernation_end:pit_end] = np.random.uniform(low_price * 0.9, low_price, 29)
            
            # 创建最后一日的拉升
            prices[-1] = prices[-2] * 1.03 # 最后一天上涨3%

            # 模拟成交量
            volumes = np.random.randint(500000, 2000000, n)
            # 地量结构
            volumes[int(n/2):] = np.random.randint(100000, 500000, len(volumes) - int(n/2))
            # 挖坑缩量
            volumes[hibernation_end:pit_end] = np.random.randint(50000, 100000, 29)
            # 拉升放量
            volumes[-1] = volumes[-5] * 1.5


            df = pd.DataFrame({
                'open': prices * 0.99,
                'high': prices * 1.02,
                'low': prices * 0.98,
                'close': prices,
                'volume': volumes
            }, index=dates)
            
            # 为了让模拟数据符合“深跌”条件
            df.loc[df.index[0], 'high'] = high_price * 1.5 
            df.loc[df.index[n-100], 'low'] = low_price * 0.9
            return df
            
    data_loader = MockDataLoader()
    
    main()