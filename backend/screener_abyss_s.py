import os
import glob
import json
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime, timedelta
import logging
import warnings
import struct
import matplotlib.pyplot as plt
import mplfinance as mpf
from collections import Counter

warnings.filterwarnings('ignore')

# --- 全局配置 ---
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz']
# --- 核心修改：新增多时间周期策略，并设为默认 ---
STRATEGY_TO_RUN = 'MULTI_TIMEFRAME_PULLBACK' # <--- 运行“周线选股、日线择时”新策略
# STRATEGY_TO_RUN = 'STRONG_TREND_PULLBACK' # <--- 运行“强势趋势回调”筛选 (单周期)
# STRATEGY_TO_RUN = 'ABYSS_WATCHLIST'       # <--- 运行“关注池”筛选 (单周期)

# --- 路径定义 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
CONFIG_FILE = os.path.join(backend_dir, 'abyss_config.json')

# --- 初始化日志 ---
DATE = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, STRATEGY_TO_RUN)
os.makedirs(RESULT_DIR, exist_ok=True)
CHART_DIR = os.path.join(RESULT_DIR, 'charts')
os.makedirs(CHART_DIR, exist_ok=True)

LOG_FILE = os.path.join(RESULT_DIR, f'log_screener_{DATE}.txt')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE, 'a', 'utf-8'), logging.StreamHandler()])
logger = logging.getLogger('stock_screener_mtf')


# --- 工具函数 ---
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: config = json.load(f)
        logger.info(f"成功加载配置文件: {config.get('strategy_name')} v{config.get('version')}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}, 将使用默认值。")
        return json.loads('{"core_parameters":{}, "analysis_timeframe": "weekly"}')

CONFIG = load_config()
ANALYSIS_TIMEFRAME = CONFIG.get('analysis_timeframe', 'weekly') # 全局时间周期

def read_day_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            buffer = f.read(); count = len(buffer) // 32
            data = [struct.unpack('<IIIIIIII', buffer[i*32:(i+1)*32]) for i in range(count)]
        if not data: return None
        df = pd.DataFrame(data, columns=['date_int', 'open', 'high', 'low', 'close', 'amount', 'volume', '_'])
        df['date'] = pd.to_datetime(df['date_int'].astype(str), format='%Y%m%d')
        df.set_index('date', inplace=True)
        for col in ['open', 'high', 'low', 'close']: df[col] /= 100.0
        return df[['open', 'high', 'low', 'close', 'volume', 'amount']]
    except Exception: return None

def resample_to_weekly(df):
    if df is None or df.empty: return None
    agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum', 'amount': 'sum'}
    weekly_df = df.resample('W-FRI').agg(agg_dict)
    weekly_df.dropna(inplace=True)
    return weekly_df

# --- 基础策略类 ---
class StrategyBase:
    def __init__(self, config=None, timeframe='weekly'):
        self.config = config or CONFIG
        self.timeframe = timeframe
        if self.timeframe == 'weekly':
            self.time_config = self._convert_config_to_weekly(self.config)
        else:
            self.time_config = self._rename_days_to_periods(self.config)

    def _rename_days_to_periods(self, day_config):
        # 当使用日线时，仅重命名键以保持一致性
        renamed_cfg = json.loads(json.dumps(day_config)) # Deep copy
        core_params = renamed_cfg.get('core_parameters', {})
        for phase, params in core_params.items():
            if isinstance(params, dict):
                for key in list(params.keys()):
                    if 'days' in key:
                        new_key = key.replace('days', 'periods')
                        params[new_key] = params.pop(key)
        return renamed_cfg

    def _convert_config_to_weekly(self, day_config):
        weekly_cfg = {}
        DAYS_TO_WEEKS_FACTOR = 5
        core_params = day_config.get('core_parameters', {})
        for phase, params in core_params.items():
            if phase.startswith('_'): continue
            weekly_cfg[phase] = {}
            if isinstance(params, dict):
                for key, value in params.items():
                    if key.startswith('_'): continue
                    if 'days' in key:
                        new_key = key.replace('days', 'periods')
                        weekly_cfg[phase][new_key] = value // DAYS_TO_WEEKS_FACTOR
                    else: weekly_cfg[phase][key] = value
        weekly_cfg['technical_indicators'] = day_config.get('technical_indicators', {})
        return weekly_cfg

    def calculate_indicators(self, df):
        df = df.copy()
        ti_config = self.config.get('technical_indicators', {})
        ma_periods = ti_config.get('ma_periods', [7, 13, 30, 45, 60])
        for period in ma_periods:
            if len(df) >= period: df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        return df

# --- 新增：多时间周期策略 ---
class MultiTimeframeStrategy(StrategyBase):
    def __init__(self, config=None):
        # 此策略强制使用周线+日线，因此基类初始化为周线
        super().__init__(config, timeframe='weekly')
        logger.info("策略已初始化为【多时间周期】筛选模式 (周线定势, 日线择时)。")

    def analyze_weekly(self, df_weekly):
        """第一步：在周线图上寻找符合强势回调的结构"""
        try:
            if len(df_weekly) < 60: return False, {}
            df = self.calculate_indicators(df_weekly)
            latest = df.iloc[-1]
            required_mas = ['ma7', 'ma13', 'ma30', 'ma60']
            if latest[required_mas].isnull().any(): return False, {}

            is_strong_trend = (latest['ma7'] > latest['ma13'] > latest['ma30'] and latest['close'] > latest['ma60'])
            ma30_slope = (latest['ma30'] - df['ma30'].iloc[-5]) / 5 if len(df) >= 5 else 0
            is_trend_upward = ma30_slope > 0

            if not (is_strong_trend and is_trend_upward): return False, {}
            
            # 周线级别允许价格在MA13附近，不一定严格触及
            is_near_ma13 = abs(latest['close'] - latest['ma13']) / latest['ma13'] < 0.05 # 价格距离MA13在5%以内
            
            if not is_near_ma13: return False, {}

            details = {
                'weekly_support': latest['ma13'],
                'weekly_pressure': df['high'].iloc[-8:].max()
            }
            return True, details
        except Exception:
            return False, {}

    def confirm_daily(self, df_daily, weekly_details):
        """第二步：在日线图上寻找精准的看涨反转信号"""
        try:
            if len(df_daily) < 20: return False, {}
            weekly_support = weekly_details.get('weekly_support', 0)
            if weekly_support == 0: return False, {}
            
            # 只看最近5天的日K线
            recent_days = df_daily.tail(5)
            
            # 条件1: 最近几天有K线的最低价触及或接近周线支撑
            touched_support = (recent_days['low'] < weekly_support * 1.01).any()
            if not touched_support: return False, {}
            
            # 条件2: 最后一根日K线是企稳的阳线
            latest = recent_days.iloc[-1]
            prev = recent_days.iloc[-2]
            is_reversal_candle = latest['close'] > latest['open'] and latest['close'] > prev['close']
            
            if not is_reversal_candle: return False, {}

            details = {
                'daily_confirmation_candle': True,
                'weekly_support_tested': True
            }
            return True, details
        except Exception:
            return False, {}

# --- 其他单周期策略 (保持不变) ---
class StrongTrendPullbackStrategy(StrategyBase):
    pass # 省略实现
class AbyssWatchlistStrategy(StrategyBase):
    pass # 省略实现

def visualize_signal(df, stock_code, signal_date_str, details, timeframe='weekly'):
    try:
        df_chart = df.copy()
        signal_date = pd.to_datetime(signal_date_str)
        
        # 根据时间周期调整图表视窗
        if timeframe == 'weekly':
            start_date = signal_date - pd.Timedelta(weeks=104)
        else: # daily
            start_date = signal_date - pd.Timedelta(days=120)
            
        df_chart = df_chart.loc[start_date:]
        if df_chart.empty: return

        signal_state = details.get('signal_state', 'UNKNOWN')
        title = f"{timeframe.upper()} CHART: {signal_state} for {stock_code} on {signal_date_str}"
        
        addplots = [mpf.make_addplot(df_chart[['ma7', 'ma13', 'ma30', 'ma60']], alpha=0.7)]
        arrow_y = pd.Series(float('nan'), index=df_chart.index)
        
        # 修正：处理日期可能不是索引一部分的情况
        signal_idx = df_chart.index.get_indexer([signal_date], method='nearest')[0]
        signal_display_date = df_chart.index[signal_idx]
        
        arrow_y[signal_display_date] = df_chart.loc[signal_display_date]['low'] * 0.95
        addplots.append(mpf.make_addplot(arrow_y, type='scatter', marker='^', color='lime', markersize=150))
        
        fig, _ = mpf.plot(df_chart, type='candle', style='yahoo', title=title, volume=True, addplot=addplots, figsize=(16, 8), returnfig=True)
        
        save_path = os.path.join(CHART_DIR, f"{stock_code}_{signal_date_str}_{timeframe}.png")
        fig.savefig(save_path); plt.close(fig)
    except Exception as e: logger.error(f"图表生成失败 for {stock_code} ({timeframe}): {e}", exc_info=True)


def worker(args):
    file_path, market, strategy_instance = args
    stock_code = os.path.basename(file_path).split('.')[0]
    valid_prefixes = CONFIG.get('market_filters', {}).get('valid_prefixes', {}).get(market, [])
    if not any(stock_code.replace(market, '').startswith(p) for p in valid_prefixes): return None
        
    try:
        df_daily = read_day_file(file_path)
        if df_daily is None or len(df_daily) < 250: return None

        # --- 核心修改：根据策略类型决定分析流程 ---
        if isinstance(strategy_instance, MultiTimeframeStrategy):
            df_weekly = resample_to_weekly(df_daily)
            if df_weekly is None or df_weekly.empty: return None

            is_weekly_ok, weekly_details = strategy_instance.analyze_weekly(df_weekly)
            if is_weekly_ok:
                is_daily_confirmed, daily_details = strategy_instance.confirm_daily(df_daily, weekly_details)
                if is_daily_confirmed:
                    details = {**weekly_details, **daily_details, 'signal_state': 'MULTI_TIMEFRAME_BUY'}
                    result = {'stock_code': stock_code, 'signal_type': 'MTF_BUY', 'date': df_daily.index[-1].strftime('%Y-%m-%d'),
                              'current_price': float(df_daily['close'].iloc[-1]),
                              'signal_details': json.loads(json.dumps(details, default=str))}
                    logger.info(f"发现多周期共振信号: {stock_code}")
                    return result
        else: # 单周期策略
            df_to_analyze = resample_to_weekly(df_daily) if strategy_instance.timeframe == 'weekly' else df_daily
            if df_to_analyze is None or df_to_analyze.empty: return None
            signal_series, details = strategy_instance.apply_strategy(df_to_analyze)
            if signal_series is not None and details is not None:
                result = {'stock_code': stock_code, 'signal_type': signal_series.iloc[-1], 'date': df_to_analyze.index[-1].strftime('%Y-%m-%d'),
                          'current_price': float(df_to_analyze['close'].iloc[-1]), 'signal_details': json.loads(json.dumps(details, default=str))}
                logger.info(f"发现 {strategy_instance.timeframe} 信号 [{result['signal_type']}]: {stock_code}")
                return result
        return None
    except Exception as e:
        logger.error(f"处理股票失败 {stock_code}: {e}", exc_info=True)
        return None

def main():
    start_time = datetime.now()
    
    # --- 根据STRATEGY_TO_RUN选择策略实例 ---
    if STRATEGY_TO_RUN == 'MULTI_TIMEFRAME_PULLBACK':
        strategy_instance = MultiTimeframeStrategy(CONFIG)
    elif STRATEGY_TO_RUN == 'STRONG_TREND_PULLBACK':
        strategy_instance = StrongTrendPullbackStrategy(CONFIG, timeframe=ANALYSIS_TIMEFRAME)
    elif STRATEGY_TO_RUN == 'ABYSS_WATCHLIST':
        strategy_instance = AbyssWatchlistStrategy(CONFIG, timeframe=ANALYSIS_TIMEFRAME)
    else:
        logger.error(f"未知的策略名称: {STRATEGY_TO_RUN}"); return
        
    logger.info(f"===== 开始执行策略筛选: {STRATEGY_TO_RUN} (全局周期: {ANALYSIS_TIMEFRAME}) =====")
    
    all_files = []
    for m in MARKETS:
        market_path = os.path.join(BASE_PATH, m, 'lday')
        if os.path.exists(market_path):
            all_files.extend([(os.path.join(market_path, f), m, strategy_instance) for f in os.listdir(market_path) if f.endswith('.day')])

    if not all_files: logger.error("未找到任何日线文件。"); return
    logger.info(f"共找到 {len(all_files)} 个日线文件进行处理...")
    
    max_workers = CONFIG.get('performance_tuning', {}).get('max_workers', cpu_count())
    with Pool(processes=min(cpu_count(), max_workers)) as pool:
        results = pool.map(worker, all_files)
    
    passed_stocks = [r for r in results if r is not None]
    logger.info(f"筛选完成，发现 {len(passed_stocks)} 个相关信号。")

    output_file = os.path.join(RESULT_DIR, f'signals_{DATE}.json')
    with open(output_file, 'w', encoding='utf-8') as f: json.dump(passed_stocks, f, ensure_ascii=False, indent=2)
    
    print(f"\n📊 筛选完成！发现 {len(passed_stocks)} 个信号。")
    print(f"📄 结果已保存至: {RESULT_DIR}")

    if passed_stocks:
        print(f"📸 正在生成 {len(passed_stocks)} 个验证图表...")
        for stock in passed_stocks:
            file_path = os.path.join(BASE_PATH, stock['stock_code'][:2], 'lday', f"{stock['stock_code']}.day")
            df_daily = read_day_file(file_path)
            if df_daily is not None:
                # 为多周期策略生成两张图
                if STRATEGY_TO_RUN == 'MULTI_TIMEFRAME_PULLBACK':
                    df_weekly = resample_to_weekly(df_daily)
                    df_weekly_indicators = strategy_instance.calculate_indicators(df_weekly)
                    visualize_signal(df_weekly_indicators, stock['stock_code'], stock['date'], stock['signal_details'], timeframe='weekly')
                    df_daily_indicators = strategy_instance.calculate_indicators(df_daily) # 复用指标计算
                    visualize_signal(df_daily_indicators, stock['stock_code'], stock['date'], stock['signal_details'], timeframe='daily')
                else: # 单周期策略
                    df_to_plot = resample_to_weekly(df_daily) if ANALYSIS_TIMEFRAME == 'weekly' else df_daily
                    df_with_indicators = strategy_instance.calculate_indicators(df_to_plot)
                    visualize_signal(df_with_indicators, stock['stock_code'], stock['date'], stock['signal_details'], timeframe=ANALYSIS_TIMEFRAME)
        print(f"✅ 所有图表已生成完毕，请查看目录: {CHART_DIR}")

    logger.info(f"总耗时: {(datetime.now() - start_time).total_seconds():.2f} 秒")
    print(f"🎉 完整流程结束！")

if __name__ == '__main__':
    # 为了让脚本能独立运行，需要模拟一些策略类
    class AbyssFinalSignalStrategy(StrategyBase): pass
    class AbyssWatchlistStrategy(StrategyBase): pass
    main()