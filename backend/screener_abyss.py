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

warnings.filterwarnings('ignore')

# --- 全局配置 ---
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz'] # 默认不扫描北交所，可根据需要添加'bj'
STRATEGY_TO_RUN = 'ABYSS_BOTTOMING_OPTIMIZED'

# --- 路径定义 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
CONFIG_FILE = os.path.join(backend_dir, 'abyss_config.json')

# --- 初始化日志 ---
DATE = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, STRATEGY_TO_RUN)
os.makedirs(RESULT_DIR, exist_ok=True)
CHART_DIR = os.path.join(RESULT_DIR, 'charts') # 新增：图表保存目录
os.makedirs(CHART_DIR, exist_ok=True)

LOG_FILE = os.path.join(RESULT_DIR, f'log_screener_{DATE}.txt')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler(LOG_FILE, 'a', 'utf-8'), logging.StreamHandler()])
logger = logging.getLogger('abyss_screener_v2')


# --- 加载配置 ---
def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"成功加载配置文件: {config.get('strategy_name')} v{config.get('version')}")
            return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}, 将使用默认值。")
        return json.loads('{"core_parameters":{}}') # 返回一个安全的默认值

CONFIG = load_config()


def read_day_file(file_path):
    try:
        with open(file_path, 'rb') as f:
            data = [struct.unpack('<IIIIIIII', f.read(32)) for _ in range(os.path.getsize(file_path) // 32)]
        if not data: return None
        df = pd.DataFrame(data, columns=['date_int', 'open', 'high', 'low', 'close', 'amount', 'volume', '_'])
        df['date'] = pd.to_datetime(df['date_int'].astype(str), format='%Y%m%d')
        df.set_index('date', inplace=True)
        for col in ['open', 'high', 'low', 'close']: df[col] /= 100.0
        return df[['open', 'high', 'low', 'close', 'volume', 'amount']]
    except Exception as e:
        logger.error(f"读取文件失败 {os.path.basename(file_path)}: {e}")
        return None


class AbyssBottomingStrategyV2:
    """
    深渊筑底策略 V2 - 逻辑重构和验证优化版
    """
    def __init__(self, config=None):
        self.config = config or CONFIG
        core_params = self.config.get('core_parameters', {})
        self.p_decline = core_params.get('deep_decline_phase', {})
        self.p_volume = core_params.get('volume_analysis', {})
        self.p_hibernation = core_params.get('hibernation_phase', {})
        self.p_washout = core_params.get('washout_phase', {})
        self.p_liftoff = core_params.get('liftoff_phase', {})
    
    def calculate_indicators(self, df):
        ma_periods = self.config.get('technical_indicators', {}).get('ma_periods', [7, 13, 30, 45])
        for period in ma_periods: df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        return df

    def _analyze_volume_shrinkage(self, df):
        # 优化点：使用更合理的相对周期进行对比
        recent_days = self.p_volume.get('volume_analysis_days', 30)
        # 中期定义为近期之前的90天
        mid_term_df = df.iloc[-recent_days-90:-recent_days]
        recent_df = df.iloc[-recent_days:]
        
        if mid_term_df.empty or recent_df.empty: return False, {}
        
        mid_term_avg_vol = mid_term_df['volume'].mean()
        recent_avg_vol = recent_df['volume'].mean()
        
        if mid_term_avg_vol == 0: return False, {}
        
        shrink_ratio = recent_avg_vol / mid_term_avg_vol
        is_shrunk = shrink_ratio < self.p_volume.get('volume_shrink_threshold', 0.7)
        
        details = {'mid_term_avg': mid_term_avg_vol, 'recent_avg': recent_avg_vol, 'shrink_ratio': shrink_ratio}
        return is_shrunk, details

    def _check_stage0_decline(self, df):
        days = self.p_decline.get('long_term_days', 400)
        if len(df) < days: return False, {}
        
        long_term = df.tail(days)
        high = long_term['high'].max()
        low = long_term['low'].min()
        current = long_term['close'].iloc[-1]
        
        if (high - low) == 0: return False, {}
        
        price_pos = (current - low) / (high - low)
        drop_pct = (high - current) / high
        
        price_ok = price_pos < self.p_decline.get('price_low_percentile', 0.35)
        drop_ok = drop_pct > self.p_decline.get('min_drop_percent', 0.40)
        volume_ok, vol_details = self._analyze_volume_shrinkage(df)
        
        details = {'price_pos': price_pos, 'drop_pct': drop_pct, 'volume': vol_details}
        return price_ok and drop_ok and volume_ok, details

    def _check_stage1_hibernation(self, df):
        w_days = self.p_washout.get('washout_days', 15)
        h_days = self.p_hibernation.get('hibernation_days', 40)
        
        hib_df = df.iloc[-w_days-h_days:-w_days]
        if len(hib_df) < h_days: return False, {}
        
        support = hib_df['low'].min()
        resistance = hib_df['high'].max()
        avg_price = hib_df['close'].mean()
        
        # 优化点：使用均价作为波动率分母
        volatility = (resistance - support) / avg_price if avg_price > 0 else float('inf')
        volatility_ok = volatility < self.p_hibernation.get('hibernation_volatility_max', 0.4)
        
        details = {'support': support, 'resistance': resistance, 'avg_volume': hib_df['volume'].mean(), 'volatility': volatility}
        return volatility_ok, details

    def _check_stage2_washout(self, df, hibernation_info):
        w_days = self.p_washout.get('washout_days', 15)
        washout_df = df.tail(w_days)
        if len(washout_df) < w_days: return False, {}
        
        support = hibernation_info['support']
        pit_low = washout_df['low'].min()
        
        break_threshold = self.p_washout.get('washout_break_threshold', 0.95)
        broken_ok = pit_low < support * break_threshold
        
        pit_days_df = washout_df[washout_df['low'] < support]
        if len(pit_days_df) < self.p_washout.get('min_pit_days', 3): return False, {}
        
        pit_avg_vol = pit_days_df['volume'].mean()
        hib_avg_vol = hibernation_info['avg_volume']
        
        if hib_avg_vol == 0: return False, {}
        
        shrink_ratio = pit_avg_vol / hib_avg_vol
        shrink_ok = shrink_ratio < self.p_washout.get('washout_volume_shrink_ratio', 0.85)
        
        details = {'pit_low': pit_low, 'pit_avg_volume': pit_avg_vol, 'shrink_ratio': shrink_ratio}
        return broken_ok and shrink_ok, details

    def _check_stage3_liftoff(self, df, washout_info):
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        price_recovering = latest['close'] > latest['open'] and latest['close'] > prev['close']
        
        rise_from_bottom = (latest['close'] - washout_info['pit_low']) / washout_info['pit_low']
        near_bottom = rise_from_bottom < self.p_liftoff.get('max_rise_from_bottom', 0.18)
        
        # 优化点：成交量对比基准为“坑内均量”
        volume_increase_ratio = latest['volume'] / washout_info['pit_avg_volume'] if washout_info['pit_avg_volume'] > 0 else float('inf')
        volume_confirming = volume_increase_ratio > self.p_liftoff.get('liftoff_volume_increase_ratio', 1.15)
        
        # 所有核心条件必须满足
        all_ok = price_recovering and near_bottom and volume_confirming
        details = {'rise_from_bottom': rise_from_bottom, 'volume_increase_ratio': volume_increase_ratio, 'price_recovering': price_recovering, 'near_bottom': near_bottom, 'volume_confirming': volume_confirming}
        return all_ok, details

    def apply_strategy(self, df):
        """
        核心修正：严格执行四阶段筛选，只输出高质量信号
        """
        try:
            df = self.calculate_indicators(df)
            
            # --- 严格的顺序检查 ---
            stage0_ok, stage0_info = self._check_stage0_decline(df)
            if not stage0_ok: return None, None

            stage1_ok, stage1_info = self._check_stage1_hibernation(df)
            if not stage1_ok: return None, None

            stage2_ok, stage2_info = self._check_stage2_washout(df, stage1_info)
            if not stage2_ok: return None, None
            
            stage3_ok, stage3_info = self._check_stage3_liftoff(df, stage2_info)
            if not stage3_ok: return None, None

            # --- 如果所有阶段都通过，生成唯一的、高质量的买入信号 ---
            signal_series = pd.Series(index=df.index, dtype=object).fillna('')
            signal_series.iloc[-1] = 'ABYSS_BUY'
            
            signal_details = {
                'signal_state': 'FULL_PATTERN_CONFIRMED',
                'stage0_decline': stage0_info,
                'stage1_hibernation': stage1_info,
                'stage2_washout': stage2_info,
                'stage3_liftoff': stage3_info,
            }
            return signal_series, signal_details
            
        except Exception as e:
            logger.error(f"策略执行失败: {e}", exc_info=True)
            return None, None

def visualize_signal(df, stock_code, signal_date_str, details):
    """新增：为信号生成并保存K线图以供验证"""
    try:
        df_chart = df.copy()
        signal_date = pd.to_datetime(signal_date_str)
        start_date = signal_date - pd.Timedelta(days=200)
        df_chart = df_chart.loc[start_date:] # 只截取信号前的数据

        if df_chart.empty: return

        s0_info = details.get('stage0_decline', {})
        s1_info = details.get('stage1_hibernation', {})
        s2_info = details.get('stage2_washout', {})
        s3_info = details.get('stage3_liftoff', {})
        
        title = (f"{stock_code} on {signal_date_str} - ABYSS_BUY\n"
                 f"Drop: {s0_info.get('drop_pct', 0):.1%}, "
                 f"Rise from Pit: {s3_info.get('rise_from_bottom', 0):.1%}, "
                 f"Vol Ratio: {s3_info.get('volume_increase_ratio', 0):.1f}x")

        arrow_y = pd.Series(float('nan'), index=df_chart.index)
        arrow_y[signal_date_str] = df_chart.loc[signal_date_str]['low'] * 0.95
        
        apd = [
            mpf.make_addplot(df_chart[['ma30', 'ma45']], alpha=0.7),
            mpf.make_addplot(arrow_y, type='scatter', marker='^', color='lime', s=120)
        ]
        
        fig, axes = mpf.plot(df_chart, type='candle', style='yahoo', title=title,
                             volume=True, addplot=apd, figsize=(16, 8), returnfig=True)
        
        # 添加横盘和挖坑区域的标注
        if s1_info and s2_info:
            axes[0].axhline(y=s1_info.get('support'), color='orange', linestyle='--', alpha=0.7, label='Hibernation Support')
            axes[0].axhline(y=s2_info.get('pit_low'), color='red', linestyle=':', alpha=0.7, label='Washout Pit Low')
            axes[0].legend()

        save_path = os.path.join(CHART_DIR, f"{stock_code}_{signal_date_str}.png")
        fig.savefig(save_path)
        plt.close(fig)

    except Exception as e:
        logger.error(f"图表生成失败 for {stock_code}: {e}", exc_info=True)

def worker(args):
    file_path, market, strategy_instance = args
    stock_code = os.path.basename(file_path).split('.')[0]
    
    if not any(stock_code.replace(market, '').startswith(p) for p in CONFIG.get('market_filters', {}).get('valid_prefixes', {}).get(market, [])):
        return None
        
    try:
        df = read_day_file(file_path)
        if df is None: return None

        signal_series, details = strategy_instance.apply_strategy(df)
        
        if signal_series is not None and details is not None and signal_series.iloc[-1] == 'ABYSS_BUY':
            result = {
                'stock_code': stock_code,
                'signal_type': signal_series.iloc[-1],
                'date': df.index[-1].strftime('%Y-%m-%d'),
                'current_price': float(df['close'].iloc[-1]),
                'signal_details': json.loads(json.dumps(details, default=lambda x: float(x) if isinstance(x, (np.floating, np.integer)) else str(x)))
            }
            logger.info(f"发现高质量信号: {stock_code}")
            return result
        return None
    except Exception as e:
        logger.error(f"处理股票失败 {stock_code}: {e}", exc_info=True)
        return None

def main():
    start_time = datetime.now()
    logger.info("===== 开始执行深渊筑底策略筛选 (V2 优化版) =====")
    
    all_files = [(os.path.join(BASE_PATH, m, 'lday', f), m, AbyssBottomingStrategyV2(CONFIG)) for m in MARKETS for f in os.listdir(os.path.join(BASE_PATH, m, 'lday')) if f.endswith('.day')]
    if not all_files:
        logger.error("未找到任何日线文件。")
        return

    logger.info(f"共找到 {len(all_files)} 个日线文件，开始处理...")
    
    max_workers = CONFIG.get('performance_tuning', {}).get('max_workers', cpu_count())
    with Pool(processes=min(cpu_count(), max_workers)) as pool:
        results = pool.map(worker, all_files)
    
    passed_stocks = [r for r in results if r is not None]
    logger.info(f"筛选完成，发现 {len(passed_stocks)} 个高质量信号。")

    # 保存JSON结果
    output_file = os.path.join(RESULT_DIR, f'abyss_signals_v2_{DATE}.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(passed_stocks, f, ensure_ascii=False, indent=2)

    # 生成文本报告
    text_report_file = os.path.join(RESULT_DIR, f'abyss_report_v2_{DATE}.txt')
    with open(text_report_file, 'w', encoding='utf-8') as f:
        f.write(f"深渊筑底策略(V2)筛选报告 - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"处理文件数: {len(all_files)}, 发现信号数: {len(passed_stocks)}\n\n")
        for i, stock in enumerate(passed_stocks, 1):
            f.write(f"{i}. {stock['stock_code']} | Price: {stock['current_price']:.2f} | Date: {stock['date']}\n")

    print(f"\n📊 筛选完成！发现高质量信号: {len(passed_stocks)} 个")
    print(f"📄 结果已保存至: {RESULT_DIR}")

    # 新增：为所有信号生成验证图表
    if passed_stocks:
        print(f"📸 正在生成 {len(passed_stocks)} 个验证图表，请稍候...")
        charting_args = []
        for stock in passed_stocks:
            file_path = os.path.join(BASE_PATH, stock['stock_code'][:2], 'lday', f"{stock['stock_code']}.day")
            df = read_day_file(file_path)
            if df is not None:
                charting_args.append((df, stock['stock_code'], stock['date'], stock['signal_details']))
        
        # 可以用多进程加速图表生成，但对于IO密集型任务效果有限，简单起见用单进程循环
        for args in charting_args:
            visualize_signal(*args)
        print(f"✅ 所有图表已生成完毕，请查看目录: {CHART_DIR}")

    logger.info(f"总耗时: {(datetime.now() - start_time).total_seconds():.2f} 秒")
    print(f"🎉 完整流程结束！")

if __name__ == '__main__':
    main()