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
# --- 核心修改：新增策略模式，并设为默认 ---
STRATEGY_TO_RUN = 'ABYSS_WATCHLIST' # <--- 运行“关注池”筛选
# STRATEGY_TO_RUN = 'ABYSS_FINAL_SIGNAL' # <--- 如需运行最终买点筛选，请取消本行注释，并注释掉上一行

# --- 路径定义 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
CONFIG_FILE = os.path.join(backend_dir, 'abyss_config.json')

# --- 初始化日志 ---
DATE = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, STRATEGY_TO_RUN) # 结果将保存在对应策略的文件夹下
os.makedirs(RESULT_DIR, exist_ok=True)
CHART_DIR = os.path.join(RESULT_DIR, 'charts_weekly')
os.makedirs(CHART_DIR, exist_ok=True)

LOG_FILE = os.path.join(RESULT_DIR, f'log_screener_{DATE}.txt')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE, 'a', 'utf-8'), logging.StreamHandler()])
logger = logging.getLogger('abyss_screener_watchlist')


# --- 工具函数 (保持不变) ---
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: config = json.load(f)
        logger.info(f"成功加载配置文件: {config.get('strategy_name')} v{config.get('version')}")
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}, 将使用默认值。")
        return json.loads('{"core_parameters":{}}')

CONFIG = load_config()

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

# --- 基础策略类 (用于代码复用) ---
class AbyssStrategyBase:
    def __init__(self, config=None):
        self.config = config or CONFIG
        self.config_weekly = self._convert_config_to_weekly(self.config)
        
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
        ti_config = self.config_weekly.get('technical_indicators', {})
        for period in ti_config.get('ma_periods', [7, 13, 30, 45]):
            if len(df) >= period: df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        rsi_period = ti_config.get('rsi_period', 14)
        if len(df) >= rsi_period:
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
            rs = gain / loss; df['rsi'] = 100 - (100 / (1 + rs))
        return df

    def _check_stage0_decline(self, df):
        p = self.config_weekly.get('deep_decline_phase', {})
        periods = p.get('long_term_periods', 80)
        if len(df) < periods: return False, {}
        long_term = df.tail(periods)
        high, low, current = long_term['high'].max(), long_term['low'].min(), long_term['close'].iloc[-1]
        if (high - low) == 0: return False, {}
        price_pos = (current - low) / (high - low); drop_pct = (high - current) / high
        price_ok = price_pos < p.get('price_low_percentile', 0.35)
        drop_ok = drop_pct > p.get('min_drop_percent', 0.35)
        details = {'price_pos': f"{price_pos:.2%}", 'drop_pct': f"{drop_pct:.2%}"}
        return price_ok and drop_ok, details

    def _check_stage1_hibernation(self, df):
        p_hib = self.config_weekly.get('hibernation_phase', {})
        p_wash = self.config_weekly.get('washout_phase', {})
        h_periods = p_hib.get('hibernation_periods', 16)
        w_periods = p_wash.get('washout_periods', 3)
        if len(df) < h_periods + w_periods: return False, {}
        # 修正：横盘阶段的识别应该包含最近的周期
        hib_df = df.iloc[-h_periods:]
        support, resistance, avg_price = hib_df['low'].min(), hib_df['high'].max(), hib_df['close'].mean()
        if avg_price == 0: return False, {}
        volatility = (resistance - support) / avg_price
        volatility_ok = volatility < p_hib.get('hibernation_volatility_max', 0.4)
        details = {'support': support, 'resistance': resistance, 'avg_volume': hib_df['volume'].mean(), 'volatility': f"{volatility:.2%}", 'hibernation_periods': h_periods}
        return volatility_ok, details

# --- 新增：关注池筛选策略 ---
class AbyssWatchlistStrategy(AbyssStrategyBase):
    def __init__(self, config=None):
        super().__init__(config)
        logger.info("策略已初始化为【关注池】筛选模式。")

    def apply_strategy(self, df):
        try:
            df = self.calculate_indicators(df)
            
            # 阶段0：必须通过深跌检查
            stage0_ok, stage0_info = self._check_stage0_decline(df)
            if not stage0_ok: return None, None
            
            # 阶段1：必须通过横盘检查
            stage1_ok, stage1_info = self._check_stage1_hibernation(df)
            if not stage1_ok: return None, None
            
            # 如果0和1都通过，则判定为关注池目标
            signal_series = pd.Series('', index=df.index, dtype=object)
            signal_series.iloc[-1] = 'IN_HIBERNATION'
            
            details = {
                'signal_state': 'WATCHLIST_CANDIDATE',
                'stage0_decline': stage0_info,
                'stage1_hibernation': stage1_info,
            }
            return signal_series, details
        except Exception as e:
            logger.error(f"关注池策略执行失败: {e}", exc_info=True)
            return None, None

# --- 原有最终信号策略 (V5) ---
class AbyssFinalSignalStrategy(AbyssStrategyBase):
    def __init__(self, config=None):
        super().__init__(config)
        logger.info("策略已初始化为【最终信号】筛选模式。")
    
    # ... (省略内部函数 _check_stage2_washout, _check_liftoff_flexible, 因为它们与上一版相同) ...
    def _check_stage2_washout(self, df, hibernation_info):
        p_wash = self.config_weekly.get('washout_phase', {})
        w_periods = p_wash.get('washout_periods', 3)
        if len(df) < w_periods: return False, {}
        washout_df = df.tail(w_periods)
        support, pit_low = hibernation_info['support'], washout_df['low'].min()
        broken_ok = pit_low < support * p_wash.get('washout_break_threshold', 0.98)
        details = {'pit_low': pit_low}
        return broken_ok, details
    
    def _check_liftoff_flexible(self, df, baseline_volume, baseline_price):
        p_lift = self.config_weekly.get('liftoff_phase', {})
        if len(df) < 2: return False, {}
        latest, prev = df.iloc[-1], df.iloc[-2]
        conditions = {'price_recovering': latest['close'] > latest['open'] and latest['close'] > prev['close']}
        if baseline_price > 0:
            rise_from_baseline = (latest['close'] - baseline_price) / baseline_price
            conditions['near_baseline'] = rise_from_baseline < p_lift.get('max_rise_from_bottom', 0.18)
        else: conditions['near_baseline'] = False
        if baseline_volume > 0:
            volume_increase_ratio = latest['volume'] / baseline_volume
            conditions['volume_confirming'] = volume_increase_ratio > p_lift.get('liftoff_volume_increase_ratio', 1.6)
        else: conditions['volume_confirming'] = False
        rsi_range = p_lift.get('rsi_range', [25, 60])
        conditions['rsi_ok'] = 'rsi' in df.columns and rsi_range[0] <= latest['rsi'] <= rsi_range[1]
        conditions_met = sum(conditions.values())
        min_req = p_lift.get('min_conditions_met', 3)
        details = {**conditions, 'conditions_met': conditions_met, 'min_req': min_req}
        return conditions_met >= min_req, details

    def apply_strategy(self, df):
        try:
            df = self.calculate_indicators(df)
            stage0_ok, stage0_info = self._check_stage0_decline(df)
            if not stage0_ok: return None, None
            stage1_ok, stage1_info = self._check_stage1_hibernation(df)
            if not stage1_ok: return None, None
            stage2_ok, stage2_info = self._check_stage2_washout(df, stage1_info)
            if stage2_ok:
                liftoff_ok, liftoff_info = self._check_liftoff_flexible(df, stage1_info['avg_volume'], stage2_info['pit_low'])
                if liftoff_ok:
                    signal_series = pd.Series('', index=df.index, dtype=object); signal_series.iloc[-1] = 'ABYSS_BUY_WEEKLY'
                    details = {'final_path': 'A_Washout', 'stage0': stage0_info, 'stage1': stage1_info, 'stage2': stage2_info, 'liftoff': liftoff_info}
                    return signal_series, details
            liftoff_ok_B, liftoff_info_B = self._check_liftoff_flexible(df, stage1_info['avg_volume'], stage1_info['support'])
            if liftoff_ok_B:
                signal_series = pd.Series('', index=df.index, dtype=object); signal_series.iloc[-1] = 'ABYSS_BUY_WEEKLY'
                details = {'final_path': 'B_Platform', 'stage0': stage0_info, 'stage1': stage1_info, 'liftoff': liftoff_info_B}
                return signal_series, details
            return None, None
        except Exception as e:
            logger.error(f"最终信号策略执行失败: {e}", exc_info=True)
            return None, None

def visualize_signal(df_weekly, stock_code, signal_date_str, details):
    try:
        df_chart = df_weekly.copy(); signal_date = pd.to_datetime(signal_date_str)
        start_date = signal_date - pd.Timedelta(weeks=104); df_chart = df_chart.loc[start_date:]
        if df_chart.empty: return

        signal_state = details.get('signal_state', 'FINAL_SIGNAL')
        
        if signal_state == 'WATCHLIST_CANDIDATE':
            s1_info = details.get('stage1_hibernation', {})
            title = (f"WATCHLIST: {stock_code} on {signal_date_str}\n"
                     f"Volatility: {s1_info.get('volatility', 'N/A')}, Support: {s1_info.get('support', 0):.2f}")
        else:
            path_type = details.get('final_path', 'Unknown')
            liftoff_details = details.get('liftoff', {})
            title = (f"FINAL SIGNAL {path_type}: {stock_code} on {signal_date_str}\n"
                     f"Conditions Met: {liftoff_details.get('conditions_met', 0)}/{liftoff_details.get('min_req', 0)}")

        addplots = [mpf.make_addplot(df_chart[['ma30', 'ma45']], alpha=0.7)]
        
        # 最终信号用箭头，观察池用星号
        marker, color, size = ('^', 'lime', 120) if signal_state != 'WATCHLIST_CANDIDATE' else ('*', 'yellow', 150)
        
        arrow_y = pd.Series(float('nan'), index=df_chart.index)
        signal_week_index = df_chart.index[df_chart.index.isin([signal_date])]
        if not signal_week_index.empty:
            arrow_y[signal_week_index[0]] = df_chart.loc[signal_week_index[0]]['low'] * 0.95
            addplots.append(mpf.make_addplot(arrow_y, type='scatter', marker=marker, color=color, markersize=size))
        
        fig, axes = mpf.plot(df_chart, type='candle', style='yahoo', title=title, volume=True, addplot=addplots, figsize=(16, 8), returnfig=True)
        
        s1_info = details.get('stage1_hibernation') or details.get('stage1')
        s2_info = details.get('stage2')
        if s1_info:
            axes[0].axhline(y=s1_info.get('support'), color='orange', linestyle='--', alpha=0.7, label='Support')
            axes[0].axhline(y=s1_info.get('resistance'), color='cyan', linestyle='--', alpha=0.5, label='Resistance')
        if s2_info and s2_info.get('pit_low'): axes[0].axhline(y=s2_info.get('pit_low'), color='red', linestyle=':', alpha=0.7, label='Washout Pit Low')
        if s1_info or (s2_info and s2_info.get('pit_low')): axes[0].legend()

        save_path = os.path.join(CHART_DIR, f"{stock_code}_{signal_date_str}_weekly.png")
        fig.savefig(save_path); plt.close(fig)
    except Exception as e: logger.error(f"周线图表生成失败 for {stock_code}: {e}", exc_info=True)


def worker(args):
    file_path, market, strategy_instance = args
    stock_code = os.path.basename(file_path).split('.')[0]
    valid_prefixes = CONFIG.get('market_filters', {}).get('valid_prefixes', {}).get(market, [])
    if not any(stock_code.replace(market, '').startswith(p) for p in valid_prefixes): return None
        
    try:
        df_daily = read_day_file(file_path)
        if df_daily is None: return None
        df_weekly = resample_to_weekly(df_daily)
        if df_weekly is None or len(df_weekly) < 80: return None

        signal_series, details = strategy_instance.apply_strategy(df_weekly)
        
        if signal_series is not None and details is not None:
            result = {'stock_code': stock_code, 'signal_type': signal_series.iloc[-1], 'date': df_weekly.index[-1].strftime('%Y-%m-%d'),
                      'current_price': float(df_weekly['close'].iloc[-1]),
                      'signal_details': json.loads(json.dumps(details, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x)))}
            logger.info(f"发现信号 [{result['signal_type']}]: {stock_code}")
            return result
        return None
    except Exception as e:
        logger.error(f"处理股票失败 {stock_code}: {e}", exc_info=True)
        return None

def main():
    start_time = datetime.now()
    
    # --- 核心修改：根据STRATEGY_TO_RUN选择策略实例 ---
    if STRATEGY_TO_RUN == 'ABYSS_WATCHLIST':
        strategy_instance = AbyssWatchlistStrategy(CONFIG)
    elif STRATEGY_TO_RUN == 'ABYSS_FINAL_SIGNAL':
        strategy_instance = AbyssFinalSignalStrategy(CONFIG)
    else:
        logger.error(f"未知的策略名称: {STRATEGY_TO_RUN}")
        return
        
    logger.info(f"===== 开始执行策略筛选: {STRATEGY_TO_RUN} =====")
    
    all_files = []
    for m in MARKETS:
        market_path = os.path.join(BASE_PATH, m, 'lday')
        if os.path.exists(market_path):
            all_files.extend([(os.path.join(market_path, f), m, strategy_instance) for f in os.listdir(market_path) if f.endswith('.day')])

    if not all_files: logger.error("未找到任何日线文件。"); return
    logger.info(f"共找到 {len(all_files)} 个日线文件，将转换为周线进行处理...")
    
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
                df_weekly = resample_to_weekly(df_daily)
                if df_weekly is not None:
                    df_with_indicators = strategy_instance.calculate_indicators(df_weekly)
                    visualize_signal(df_with_indicators, stock['stock_code'], stock['date'], stock['signal_details'])
        print(f"✅ 所有图表已生成完毕，请查看目录: {CHART_DIR}")

    logger.info(f"总耗时: {(datetime.now() - start_time).total_seconds():.2f} 秒")
    print(f"🎉 完整流程结束！")

if __name__ == '__main__':
    main()