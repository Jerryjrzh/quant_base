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
STRATEGY_TO_RUN = 'ABYSS_BOTTOMING_OPTIMIZED'

# --- 路径定义 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
CONFIG_FILE = os.path.join(backend_dir, 'abyss_config.json')

# --- 初始化日志 ---
DATE = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, STRATEGY_TO_RUN)
os.makedirs(RESULT_DIR, exist_ok=True)
CHART_DIR = os.path.join(RESULT_DIR, 'charts_weekly')
os.makedirs(CHART_DIR, exist_ok=True)

LOG_FILE = os.path.join(RESULT_DIR, f'log_screener_{DATE}.txt')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE, 'a', 'utf-8'), logging.StreamHandler()])
logger = logging.getLogger('abyss_screener_debug')


# --- 工具函数 ---
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"成功加载配置文件: {config.get('strategy_name')} v{config.get('version')}")
            return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}, 将使用默认值。")
        return json.loads('{"core_parameters":{}}')

CONFIG = load_config()

def read_day_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            buffer = f.read()
            count = len(buffer) // 32
            data = [struct.unpack('<IIIIIIII', buffer[i*32:(i+1)*32]) for i in range(count)]
        if not data: return None
        df = pd.DataFrame(data, columns=['date_int', 'open', 'high', 'low', 'close', 'amount', 'volume', '_'])
        df['date'] = pd.to_datetime(df['date_int'].astype(str), format='%Y%m%d')
        df.set_index('date', inplace=True)
        for col in ['open', 'high', 'low', 'close']: df[col] /= 100.0
        return df[['open', 'high', 'low', 'close', 'volume', 'amount']]
    except Exception as e:
        logger.error(f"读取文件失败 {os.path.basename(file_path)}: {e}")
        return None

def resample_to_weekly(df):
    if df is None or df.empty: return None
    agg_dict = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum', 'amount': 'sum'}
    weekly_df = df.resample('W-FRI').agg(agg_dict)
    weekly_df.dropna(inplace=True)
    return weekly_df


# --- 策略类 V4 (带分步调试) ---
class AbyssBottomingStrategyV4:
    def __init__(self, config=None):
        self.config = config or CONFIG
        self.config_weekly = self._convert_config_to_weekly(self.config)
        logger.info("策略已初始化为周线分析模式 (V4 - 分步调试)。")
    
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
                        if phase == 'hibernation_phase' and key == 'hibernation_days': value = 80
                        if phase == 'washout_phase' and key == 'washout_days': value = 15
                        weekly_cfg[phase][new_key] = value // DAYS_TO_WEEKS_FACTOR
                    else:
                        weekly_cfg[phase][key] = value
        weekly_cfg['technical_indicators'] = day_config.get('technical_indicators', {})
        return weekly_cfg

    def calculate_indicators(self, df):
        df = df.copy()
        ma_periods = self.config_weekly.get('technical_indicators', {}).get('ma_periods', [7, 13, 30, 45])
        for period in ma_periods:
            if len(df) >= period: df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        return df

    def _check_stage0_decline(self, df):
        p_decline = self.config_weekly.get('deep_decline_phase', {})
        periods = p_decline.get('long_term_periods', 80)
        min_drop = p_decline.get('min_drop_percent', 0.35)
        if len(df) < periods: return False, {}
        long_term = df.tail(periods)
        high, low, current = long_term['high'].max(), long_term['low'].min(), long_term['close'].iloc[-1]
        if (high - low) == 0: return False, {}
        price_pos = (current - low) / (high - low)
        drop_pct = (high - current) / high
        price_ok = price_pos < p_decline.get('price_low_percentile', 0.35)
        drop_ok = drop_pct > min_drop
        details = {'price_pos': price_pos, 'drop_pct': drop_pct}
        return price_ok and drop_ok, details

    def _check_stage1_hibernation(self, df):
        p_hib = self.config_weekly.get('hibernation_phase', {})
        p_wash = self.config_weekly.get('washout_phase', {})
        h_periods = p_hib.get('hibernation_periods', 16)
        w_periods = p_wash.get('washout_periods', 3)
        if len(df) < h_periods + w_periods: return False, {}
        hib_df = df.iloc[-h_periods-w_periods:-w_periods]
        support, resistance, avg_price = hib_df['low'].min(), hib_df['high'].max(), hib_df['close'].mean()
        if avg_price == 0: return False, {}
        volatility = (resistance - support) / avg_price
        volatility_ok = volatility < p_hib.get('hibernation_volatility_max', 0.4)
        details = {'support': support, 'resistance': resistance, 'avg_volume': hib_df['volume'].mean(), 'volatility': volatility}
        return volatility_ok, details
    
    def _check_stage2_washout(self, df, hibernation_info):
        p_wash = self.config_weekly.get('washout_phase', {})
        w_periods = p_wash.get('washout_periods', 3)
        if len(df) < w_periods: return False, {}
        washout_df = df.tail(w_periods)
        support, pit_low = hibernation_info['support'], washout_df['low'].min()
        broken_ok = pit_low < support * p_wash.get('washout_break_threshold', 0.98)
        details = {'pit_low': pit_low}
        return broken_ok, details
    
    def _check_liftoff(self, df, baseline_volume, baseline_price):
        p_lift = self.config_weekly.get('liftoff_phase', {})
        if len(df) < 2: return False, {}
        latest, prev = df.iloc[-1], df.iloc[-2]
        price_recovering = latest['close'] > latest['open'] and latest['close'] > prev['close']
        if baseline_price == 0: return False, {}
        rise_from_baseline = (latest['close'] - baseline_price) / baseline_price
        near_baseline = rise_from_baseline < p_lift.get('max_rise_from_bottom', 0.18)
        if baseline_volume == 0: return False, {}
        volume_increase_ratio = latest['volume'] / baseline_volume
        volume_confirming = volume_increase_ratio > p_lift.get('liftoff_volume_increase_ratio', 2.0)
        all_ok = price_recovering and near_baseline and volume_confirming
        details = {'rise_from_baseline': rise_from_baseline, 'volume_increase_ratio': volume_increase_ratio, 'baseline_volume': baseline_volume}
        return all_ok, details

    def apply_strategy(self, df):
        """
        核心修正：函数现在返回股票通过的最高阶段编号
        - 0: 仅通过深跌
        - 1: 通过深跌+横盘
        - 2: 通过深跌+横盘+启动(任一路径)
        - -1: 任何阶段都未通过
        """
        try:
            df = self.calculate_indicators(df)
            details = {}

            stage0_ok, stage0_info = self._check_stage0_decline(df)
            details['stage0_decline'] = stage0_info
            if not stage0_ok:
                return -1, details # 未通过初始阶段

            stage1_ok, stage1_info = self._check_stage1_hibernation(df)
            details['stage1_hibernation'] = stage1_info
            if not stage1_ok:
                return 0, details # 通过第0阶段

            # 路径A: 经典挖坑模式
            stage2_ok, stage2_info = self._check_stage2_washout(df, stage1_info)
            details['stage2_washout'] = stage2_info
            if stage2_ok:
                liftoff_ok, liftoff_info = self._check_liftoff(df, stage1_info['avg_volume'], stage2_info['pit_low'])
                details['liftoff_path_A'] = liftoff_info
                if liftoff_ok:
                    details['final_path'] = 'A_Washout'
                    return 2, details # 最终信号

            # 路径B: 平台启动模式
            liftoff_ok_B, liftoff_info_B = self._check_liftoff(df, stage1_info['avg_volume'], stage1_info['support'])
            details['liftoff_path_B'] = liftoff_info_B
            if liftoff_ok_B:
                details['final_path'] = 'B_Platform'
                return 2, details # 最终信号
            
            return 1, details # 通过第1阶段，但未触发启动

        except Exception as e:
            logger.error(f"策略执行失败: {e}", exc_info=True)
            return -1, {}

def visualize_signal(df_weekly, stock_code, signal_date_str, details):
    # (此函数保持不变)
    try:
        df_chart = df_weekly.copy()
        signal_date = pd.to_datetime(signal_date_str)
        start_date = signal_date - pd.Timedelta(weeks=104)
        df_chart = df_chart.loc[start_date:]
        if df_chart.empty: return

        path_type = details.get('final_path', 'Unknown')
        liftoff_details = details.get('liftoff_path_A') if path_type == 'A_Washout' else details.get('liftoff_path_B', {})

        title = (f"WEEKLY {path_type}: {stock_code} on {signal_date_str}\n"
                 f"Rise: {liftoff_details.get('rise_from_baseline', 0):.1%}, Vol Ratio: {liftoff_details.get('volume_increase_ratio', 0):.1f}x")

        addplots = [mpf.make_addplot(df_chart[['ma30', 'ma45']], alpha=0.7)]
        arrow_y = pd.Series(float('nan'), index=df_chart.index)
        signal_week_index = df_chart.index[df_chart.index.isin([signal_date])]
        if not signal_week_index.empty:
            arrow_y[signal_week_index[0]] = df_chart.loc[signal_week_index[0]]['low'] * 0.95
            addplots.append(mpf.make_addplot(arrow_y, type='scatter', marker='^', color='lime', markersize=120))
        
        fig, axes = mpf.plot(df_chart, type='candle', style='yahoo', title=title,
                             volume=True, addplot=addplots, figsize=(16, 8), returnfig=True)
        
        s1_info = details.get('stage1_hibernation', {})
        s2_info = details.get('stage2_washout', {})
        if s1_info: axes[0].axhline(y=s1_info.get('support'), color='orange', linestyle='--', alpha=0.7, label='Hibernation Support')
        if s2_info and s2_info.get('pit_low'): axes[0].axhline(y=s2_info.get('pit_low'), color='red', linestyle=':', alpha=0.7, label='Washout Pit Low')
        if s1_info or s2_info: axes[0].legend()

        save_path = os.path.join(CHART_DIR, f"{stock_code}_{signal_date_str}_weekly.png")
        fig.savefig(save_path); plt.close(fig)
    except Exception as e:
        logger.error(f"周线图表生成失败 for {stock_code}: {e}", exc_info=True)


def worker(args):
    file_path, market, strategy_instance = args
    stock_code = os.path.basename(file_path).split('.')[0]
    valid_prefixes = CONFIG.get('market_filters', {}).get('valid_prefixes', {}).get(market, [])
    if not any(stock_code.replace(market, '').startswith(p) for p in valid_prefixes): return None
        
    try:
        df_daily = read_day_file(file_path)
        if df_daily is None: return None
        df_weekly = resample_to_weekly(df_daily)
        if df_weekly is None or len(df_weekly) < 80: return None # 至少需要80周数据

        # --- 核心改动：接收最高通过阶段和详情 ---
        highest_stage, details = strategy_instance.apply_strategy(df_weekly)
        
        # 总是返回结果用于统计
        result = {
            'stock_code': stock_code,
            'highest_stage': highest_stage,
            'date': df_weekly.index[-1].strftime('%Y-%m-%d'),
            'current_price': float(df_weekly['close'].iloc[-1]),
            'details': json.loads(json.dumps(details, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x)))
        }
        return result
    except Exception as e:
        logger.error(f"处理股票失败 {stock_code}: {e}", exc_info=True)
        return None

def main():
    start_time = datetime.now()
    logger.info("===== 开始执行深渊筑底策略筛选 (V4 分步调试版) =====")
    
    strategy_instance = AbyssBottomingStrategyV4(CONFIG)
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
    
    # --- 新增：分步统计逻辑 ---
    all_results = [r for r in results if r is not None]
    stage_counts = Counter(r['highest_stage'] for r in all_results)
    
    # 最终通过的信号
    passed_stocks = [r for r in all_results if r['highest_stage'] == 2]
    
    # --- 新增：打印漏斗分析报告 ---
    total_processed = len(all_results)
    passed_s0 = stage_counts.get(0, 0) + stage_counts.get(1, 0) + stage_counts.get(2, 0)
    passed_s1 = stage_counts.get(1, 0) + stage_counts.get(2, 0)
    passed_s2 = stage_counts.get(2, 0)

    print("\n" + "="*80)
    print(" " * 28 + "筛选漏斗分析报告")
    print("="*80)
    print(f"总计处理股票数: {total_processed}")
    print("-" * 80)
    
    s0_pct = (passed_s0 / total_processed * 100) if total_processed > 0 else 0
    print(f"通过 [阶段 0: 深跌筑底] 的股票数: {passed_s0} ({s0_pct:.2f}%)")
    
    s1_pct_of_s0 = (passed_s1 / passed_s0 * 100) if passed_s0 > 0 else 0
    print(f"通过 [阶段 1: 横盘蓄势] 的股票数: {passed_s1} (占上一阶段的 {s1_pct_of_s0:.2f}%)")
    
    s2_pct_of_s1 = (passed_s2 / passed_s1 * 100) if passed_s1 > 0 else 0
    print(f"通过 [阶段 2: 确认拉升] 的股票数: {passed_s2} (占上一阶段的 {s2_pct_of_s1:.2f}%)")
    print("="*80)
    
    logger.info(f"漏斗分析 - S0: {passed_s0}, S1: {passed_s1}, S2(最终信号): {passed_s2}")

    # --- 保存和可视化最终信号 ---
    if passed_stocks:
        output_file = os.path.join(RESULT_DIR, f'abyss_signals_weekly_v4_{DATE}.json')
        with open(output_file, 'w', encoding='utf-8') as f: json.dump(passed_stocks, f, ensure_ascii=False, indent=2)
        print(f"\n📊 发现 {len(passed_stocks)} 个高质量周线信号！")
        print(f"📄 结果已保存至: {output_file}")

        print(f"📸 正在生成 {len(passed_stocks)} 个周线验证图表...")
        for stock in passed_stocks:
            file_path = os.path.join(BASE_PATH, stock['stock_code'][:2], 'lday', f"{stock['stock_code']}.day")
            df_daily = read_day_file(file_path)
            if df_daily is not None:
                df_weekly = resample_to_weekly(df_daily)
                if df_weekly is not None:
                    df_with_indicators = strategy_instance.calculate_indicators(df_weekly)
                    visualize_signal(df_with_indicators, stock['stock_code'], stock['date'], stock['details'])
        print(f"✅ 所有图表已生成完毕，请查看目录: {CHART_DIR}")
    else:
        print("\n" + "未发现最终通过所有阶段的信号。请根据上方的漏斗分析报告调整config.json中的参数。")


    logger.info(f"总耗时: {(datetime.now() - start_time).total_seconds():.2f} 秒")
    print(f"\n🎉 完整流程结束！")

if __name__ == '__main__':
    main()