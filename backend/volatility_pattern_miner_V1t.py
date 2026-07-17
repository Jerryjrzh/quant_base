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
VOLATILITY_THRESHOLD = 0.10
LOOKBACK_DAYS = 300
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'pattern_mining')
os.makedirs(OUTPUT_DIR, exist_ok=True)


def process_stock_patterns(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    detector = KlinePatternDetector()
    results = {'matched_patterns': [], 'anomaly_patterns': []}
    
    try:
        # 日线（使用正确的调用方式）
        df_daily = data_loader.get_daily_data(file_path)
        if df_daily is None or len(df_daily) < LOOKBACK_DAYS:
            return None
            
        df_daily = df_daily.iloc[-LOOKBACK_DAYS:].copy()
        
        # 计算振幅
        df_daily['prev_close'] = df_daily['close'].shift(1)
        df_daily['amplitude'] = (df_daily['high'] - df_daily['low']) / df_daily['prev_close']
        
        target_indices = np.where(df_daily['amplitude'] > VOLATILITY_THRESHOLD)[0]
        if len(target_indices) == 0:
            return None

        # 时间范围
        end_date = df_daily.index[-1].strftime('%Y-%m-%d')
        start_60 = (pd.to_datetime(end_date) - pd.Timedelta(days=40)).strftime('%Y-%m-%d')
        start_15 = (pd.to_datetime(end_date) - pd.Timedelta(days=15)).strftime('%Y-%m-%d')
        
        # 关键修复：统一使用 stock_code_full（带 sh/sz 前缀）
        clean_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
        df_60m = data_loader.get_min_data_in_range(clean_code, '60m', start_60, end_date)
        df_15m = data_loader.get_min_data_in_range(clean_code, '15m', start_15, end_date)

        if df_60m is None or df_15m is None or df_60m.empty or df_15m.empty:
            return None
        
        # ---------------------------------------------------------
        # 🔑 核心修复：强制规整重采样后的分钟线索引，砸碎 NumPy 数组错位炸弹
        # ---------------------------------------------------------
        for df_min in [df_60m, df_15m]:
            if 'datetime' in df_min.columns:
                df_min.index = pd.to_datetime(df_min['datetime'])
            elif not isinstance(df_min.index, pd.DatetimeIndex):
                df_min.index = pd.to_datetime(df_min.index)

        for idx in target_indices:
            if idx < 8: 
                continue
                
            t_date = df_daily.index[idx]
            t_minus_2_date = df_daily.index[idx-2]
            t_minus_1_date = df_daily.index[idx-1]

            # 日线 T-2
            daily_slice = df_daily.iloc[:idx-1]
            daily_patterns = detector.detect_talib_patterns(daily_slice)
            deep_rev = detector.detect_deep_step_reversal(daily_slice)
            if deep_rev.get('reversal_signal'):
                daily_patterns['DEEP_STEP_REVERSAL'] = 1

            # --- B. 🔑 核心修复：基于标准 DatetimeIndex 实施切片 ---
            t2_cutoff = pd.to_datetime(f"{t_minus_2_date.strftime('%Y-%m-%d')} 15:30:00")
            m60_t2_slice = df_60m.loc[df_60m.index <= t2_cutoff].copy()
            
            if len(m60_t2_slice) > 20:
                m60_patterns = detector.detect_talib_patterns(m60_t2_slice)
            else:
                m60_patterns = {}
                
            # --- C. 🔑 核心修复：基于标准 DatetimeIndex 实施切片 ---
            t1_cutoff = pd.to_datetime(f"{t_minus_1_date.strftime('%Y-%m-%d')} 15:30:00")
            m15_t1_slice = df_15m.loc[df_15m.index <= t1_cutoff].copy()
            
            if len(m15_t1_slice) > 20:
                m15_patterns = detector.detect_talib_patterns(m15_t1_slice)
            else:
                m15_patterns = {}

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
    logger.info("🚀 启动高波动前瞻形态挖掘引擎 (V2 最终稳定版)...")
    
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    
    # 测试时限制数量（建议先跑300只验证）
    # files = files[:300]

    #stock_codes = [os.path.basename(f).split('.')[0] for f in files]
    
    with Pool(processes=min(cpu_count(), 12)) as pool:
        raw_results = pool.map(process_stock_patterns, files)
        
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
    
    logger.info(f"✅ 挖掘完成！已知形态样本: {len(all_matched)} | 异常样本: {len(all_anomalies)}")
    if len(all_anomalies) > 0:
        logger.info(f"🔍 异常样本路径（重点人工复盘）: {os.path.join(OUTPUT_DIR, f'anomaly_patterns_{date_str}.csv')}")

if __name__ == "__main__":
    main()
