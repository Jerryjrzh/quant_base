import os
import glob
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging

from kline_patterns import KlinePatternDetector
import data_loader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# 配置
# ==========================================
VOLATILITY_THRESHOLD = 0.10   # 10% 振幅，兼顾黄金坑和爆发股
LOOKBACK_DAYS = 300
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'pattern_mining')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def process_stock_patterns(stock_code_full):
    detector = KlinePatternDetector()
    results = {'matched_patterns': [], 'anomaly_patterns': []}
    
    try:
        # 日线加载（修复调用方式）
        df_daily = data_loader.get_daily_data(stock_code_full)
        if df_daily is None or len(df_daily) < LOOKBACK_DAYS:
            return None
            
        df_daily = df_daily.iloc[-LOOKBACK_DAYS:].copy()
        
        # 计算振幅
        df_daily['prev_close'] = df_daily['close'].shift(1)
        df_daily['amplitude'] = (df_daily['high'] - df_daily['low']) / df_daily['prev_close']
        
        target_indices = np.where(df_daily['amplitude'] > VOLATILITY_THRESHOLD)[0]
        if len(target_indices) == 0:
            return None

        # 分钟线（带时间范围）
        end_date = df_daily.index[-1].strftime('%Y-%m-%d')
        start_60 = (pd.to_datetime(end_date) - pd.Timedelta(days=40)).strftime('%Y-%m-%d')
        start_15 = (pd.to_datetime(end_date) - pd.Timedelta(days=15)).strftime('%Y-%m-%d')
        
        df_60m = data_loader.get_min_data_in_range(stock_code_full, '60m', start_60, end_date)
        df_15m = data_loader.get_min_data_in_range(stock_code_full, '15m', start_15, end_date)

        for idx in target_indices:
            if idx < 8: 
                continue
                
            t_date = df_daily.index[idx]
            t_minus_2 = df_daily.index[idx-2]
            t_minus_1 = df_daily.index[idx-1]

            # 日线 T-2
            daily_slice = df_daily.iloc[:idx-1]
            daily_patterns = detector.detect_talib_patterns(daily_slice)
            deep_rev = detector.detect_deep_step_reversal(daily_slice)
            if deep_rev.get('reversal_signal'):
                daily_patterns['DEEP_STEP_REVERSAL'] = 1

            # 60分钟 T-2
            m60_slice = None
            if df_60m is not None and len(df_60m) > 15:
                cutoff = pd.to_datetime(f"{t_minus_2.strftime('%Y-%m-%d')} 15:00")
                m60_slice = df_60m[df_60m.index <= cutoff]
            m60_patterns = detector.detect_talib_patterns(m60_slice) if m60_slice is not None else {}

            # 15分钟 T-1
            m15_slice = None
            if df_15m is not None and len(df_15m) > 15:
                cutoff = pd.to_datetime(f"{t_minus_1.strftime('%Y-%m-%d')} 15:00")
                m15_slice = df_15m[df_15m.index <= cutoff]
            m15_patterns = detector.detect_talib_patterns(m15_slice) if m15_slice is not None else {}

            snapshot = {
                'stock_code': stock_code_full,
                'target_date': t_date.strftime('%Y-%m-%d'),
                'amplitude': f"{df_daily['amplitude'].iloc[idx]:.2%}",
                't2_daily': daily_patterns,
                't2_60m': m60_patterns,
                't1_15m': m15_patterns,
            }

            is_anomaly = (len(daily_patterns) <= 1 and len(m60_patterns) == 0 and len(m15_patterns) == 0)
            
            if is_anomaly:
                results['anomaly_patterns'].append(snapshot)
            else:
                results['matched_patterns'].append(snapshot)
                
        return results
        
    except Exception as e:
        logger.error(f"处理 {stock_code_full} 失败: {e}")
        return None


def main():
    logger.info("🚀 启动高波动前瞻形态挖掘引擎 (V2 稳定版)...")
    
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    
    # 测试建议先用少量股票
    # files = files[:200]

    stock_codes = [os.path.basename(f).split('.')[0] for f in files]
    
    with Pool(processes=min(cpu_count(), 12)) as pool:
        raw_results = pool.map(process_stock_patterns, stock_codes)
        
    all_matched = []
    all_anomalies = []
    for r in raw_results:
        if r:
            all_matched.extend(r['matched_patterns'])
            all_anomalies.extend(r['anomaly_patterns'])
    
    date_str = datetime.now().strftime("%Y%m%d")
    matched_df = pd.DataFrame(all_matched)
    anomaly_df = pd.DataFrame(all_anomalies)
    
    matched_df.to_csv(os.path.join(OUTPUT_DIR, f'matched_patterns_{date_str}.csv'), index=False, encoding='utf-8-sig')
    anomaly_df.to_csv(os.path.join(OUTPUT_DIR, f'anomaly_patterns_{date_str}.csv'), index=False, encoding='utf-8-sig')
    
    logger.info(f"挖掘完成！已知形态: {len(all_matched)} | 异常样本: {len(all_anomalies)}")
    logger.info(f"异常样本请重点人工复盘: {os.path.join(OUTPUT_DIR, f'anomaly_patterns_{date_str}.csv')}")

if __name__ == "__main__":
    main()
