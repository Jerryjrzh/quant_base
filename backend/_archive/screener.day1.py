import os
import glob
import json
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging
# 假设这些模块在您的项目中存在
# import data_loader
# import strategies
# import backtester
# import indicators
# from win_rate_filter import WinRateFilter, AdvancedTripleCrossFilter
import talib 

# === 模拟模块 (为了让脚本可以独立运行) ===
# 在您的真实环境中，请删除或注释掉这部分，并确保您的模块可被导入
class DummyModule:
    def __getattr__(self, name):
        if name == 'get_daily_data':
            def get_mock_data(file_path):
                dates = pd.to_datetime(pd.date_range(end=datetime.now(), periods=500, freq='D'))
                prices = pd.Series(10 + np.random.randn(500).cumsum() + np.sin(np.linspace(0, 20, 500))*2, index=dates)
                df = pd.DataFrame({'open': prices, 'high': prices*1.02, 'low': prices*0.98, 'close': prices, 'volume': np.random.randint(1e6, 5e7, 500)}, index=dates)
                return df
            return get_mock_data
        if name == 'run_backtest':
            return lambda df, signals: {'total_signals': signals.sum(), 'win_rate': '50.0%', 'avg_max_profit': '5.0%'}
        def _dummy(*args, **kwargs): return (pd.Series(), pd.Series(), pd.Series())
        return _dummy
data_loader = DummyModule()
strategies = DummyModule()
backtester = DummyModule()
indicators = DummyModule()
class WinRateFilter: pass
class AdvancedTripleCrossFilter: pass
# === 模拟模块结束 ===


# === 新增 DAILY_MA_PULLBACK 策略 (V2 - 强化版) START ===
def resample_to_weekly(df):
    """将日线数据聚合为周线数据"""
    if df is None or df.empty: return None
    agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    weekly_df = df.resample('W-FRI').agg(agg_dict)
    weekly_df.dropna(inplace=True)
    return weekly_df

def apply_daily_ma_pullback_strategy(df):
    """
    周线确认强势 V2 (更严格)，日线寻找MA13回踩买点策略
    """
    if len(df) < 250: return None

    try:
        # 1. 数据准备和指标计算
        df_weekly = resample_to_weekly(df)
        if df_weekly is None or len(df_weekly) < 120: # 需要更长数据计算周线MA60和量比
            return None

        # 计算周线级别指标
        for p in [13, 30, 60]: df_weekly[f'ma{p}'] = talib.MA(df_weekly['close'], timeperiod=p)
        for p in [20, 60]: df_weekly[f'vol_ma{p}'] = talib.MA(df_weekly['volume'], timeperiod=p)
        # 计算日线级别指标
        df[f'ma13'] = talib.MA(df['close'], timeperiod=13)

        if df_weekly.iloc[-5:].isnull().values.any() or df.iloc[-1].isnull().values.any():
            return None 

        # 2. 【V2版】长周期（周线）确认强势趋势 (新增严格过滤)
        latest_w = df_weekly.iloc[-1]
        
        # 条件a: 周线均线多头排列 (基础)
        ma_alignment_ok = latest_w['ma13'] > latest_w['ma30'] > latest_w['ma60']
        
        # 【新增】条件b: 均线斜率持续为正 (要求趋势持续性)
        ma30_slope_ok = latest_w['ma30'] > df_weekly['ma30'].iloc[-4] # 检查MA30在过去4周是上升的

        # 【新增】条件c: 均线之间有足够发散度 (过滤粘合状态)
        ma_separation_ok = (latest_w['ma13'] / latest_w['ma60'] - 1) > 0.03 # 要求MA13至少高于MA60 3%

        # 【新增】条件d: 成交量趋势健康 (近期放量)
        volume_trend_ok = latest_w['vol_ma20'] > latest_w['vol_ma60']

        # 最终强势判断：必须同时满足所有严格条件
        is_strong_trend_weekly = ma_alignment_ok and ma30_slope_ok and ma_separation_ok and volume_trend_ok
        
        if not is_strong_trend_weekly:
            return None

        # 3. 短周期（日线）确认回踩买点
        latest_d = df.iloc[-1]
        
        is_pullback = latest_d['low'] <= latest_d['ma13'] * 1.01
        is_bounce = latest_d['close'] > latest_d['ma13']
        
        if is_pullback and is_bounce:
            signal_series = pd.Series(False, index=df.index)
            signal_series.iloc[-1] = True
            return signal_series

        return None
    except Exception as e:
        return None

strategies.apply_daily_ma_pullback_strategy = apply_daily_ma_pullback_strategy
# === 新增 DAILY_MA_PULLBACK 策略 (V2 - 强化版) END ===


# --- 配置 ---
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz', 'bj']
STRATEGY_TO_RUN = 'DAILY_MA_PULLBACK'
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
if logger.hasHandlers(): logger.handlers.clear()
logger.addHandler(file_handler)

# --- 原有脚本函数 (保持不变, 此处仅保留必要部分以供调用) ---
def calculate_backtest_stats_fast(df, signal_series):
    try:
        backtest_results = backtester.run_backtest(df, signal_series)
        if isinstance(backtest_results, dict) and backtest_results.get('total_signals', 0) > 0:
            return {
                'total_signals': backtest_results.get('total_signals', 0),
                'win_rate': backtest_results.get('win_rate', '0.0%'),
                'avg_max_profit': backtest_results.get('avg_max_profit', '0.0%'),
            }
        return {'total_signals': 0, 'win_rate': '0.0%', 'avg_max_profit': '0.0%'}
    except Exception as e:
        logger.error(f"快速回测计算失败: {e}")
        return {'total_signals': 0, 'win_rate': '0.0%', 'avg_max_profit': '0.0%'}

def _process_daily_ma_pullback_strategy(df, result_base):
    """处理DAILY_MA_PULLBACK策略"""
    try:
        signal_series = strategies.apply_daily_ma_pullback_strategy(df)
        if signal_series is not None and signal_series.iloc[-1]:
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            result_base.update({'filter_status': 'passed', **backtest_stats})
            return result_base
        return None
    except Exception as e:
        logger.error(f"处理 DAILY_MA_PULLBACK 策略失败 {result_base.get('stock_code', '')}: {e}")
        return None

def worker(args):
    """多进程工作函数"""
    file_path, market = args
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code_no_prefix = stock_code_full.replace(market, '')
    valid_prefixes = ('600', '601', '603', '000', '001', '002', '003', '300', '688')
    if not stock_code_no_prefix.startswith(valid_prefixes): return None
    try:
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 150: return None
        result_base = {
            'stock_code': stock_code_full, 'strategy': STRATEGY_TO_RUN,
            'date': df.index[-1].strftime('%Y-%m-%d'),
            'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        if STRATEGY_TO_RUN == 'DAILY_MA_PULLBACK':
            return _process_daily_ma_pullback_strategy(df, result_base)
        # (此处省略其他策略的处理逻辑)
        return None
    except Exception as e:
        logger.error(f"处理 {stock_code_full} 时发生未知错误: {e}")
        return None

def main():
    """主执行函数"""
    start_time = datetime.now()
    logger.info(f"===== 开始执行批量筛选, 策略: {STRATEGY_TO_RUN} (V2 强势增强版) =====")
    print(f"🚀 开始执行批量筛选, 策略: {STRATEGY_TO_RUN} (V2 强势增强版)")
    
    all_files = []
    for market in MARKETS:
        path = os.path.join(BASE_PATH, market, 'lday', '*.day')
        files = glob.glob(path)
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

    print(f"\n📊 初步筛选完成！")
    print(f"🎯 发现信号: {len(passed_stocks)} 个")
    print(f"⏱️ 处理耗时: {processing_time:.2f} 秒")
    print(f"📄 结果已保存至: {output_file}")
    
    total_time = (datetime.now() - start_time).total_seconds()
    print(f"\n🎉 完整扫描流程结束！总耗时: {total_time:.2f} 秒")
    logger.info(f"===== 完整扫描完成！初步筛选: {len(passed_stocks)} 个信号，总耗时: {total_time:.2f} 秒 =====")

if __name__ == '__main__':
    main()