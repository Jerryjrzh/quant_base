import os
import glob
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging

import data_loader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

VOLATILITY_THRESHOLD = 0.10
LOOKBACK_DAYS = 1000
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'morse_analytics')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def extract_raw_metrics(df_slice, prefix=""):
    """提取最后一根K线的绝对原始数据和真实比率"""
    if df_slice is None or len(df_slice) < 20:
        # 如果数据缺失，返回空字典
        cols = ['O', 'H', 'L', 'C', 'V', 'V_MA20', '实体涨幅%', '上影线%', '下影线%', '量比']
        return {f"{prefix}_{c}": np.nan for c in cols}
        
    vol_ma20 = df_slice['volume'].rolling(20, min_periods=1).mean().iloc[-1]
    row = df_slice.iloc[-1]
    
    o, h, l, c, v = row['open'], row['high'], row['low'], row['close'], row['volume']
    
    # 防御 0 除错误
    base_p = o + 1e-9 
    vol_base = vol_ma20 + 1e-9
    
    # 计算真实比例 (保留4位小数，即百分之XX.XX)
    body_pct = round((c - o) / base_p * 100, 4)
    up_shadow_pct = round((h - max(c, o)) / base_p * 100, 4)
    dn_shadow_pct = round((min(c, o) - l) / base_p * 100, 4)
    vol_ratio = round(v / vol_base, 4)
    
    return {
        f"{prefix}_O": round(o, 2),
        f"{prefix}_H": round(h, 2),
        f"{prefix}_L": round(l, 2),
        f"{prefix}_C": round(c, 2),
        f"{prefix}_V": int(v),
        f"{prefix}_V_MA20": int(vol_ma20),
        f"{prefix}_实体涨幅%": body_pct,
        f"{prefix}_上影线%": up_shadow_pct,
        f"{prefix}_下影线%": dn_shadow_pct,
        f"{prefix}_量比": vol_ratio
    }

def process_raw_data_dump(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    clean_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    # 快速过滤无效股票代码
    valid_prefixes = ('60', '92',  '00' '300', '688')
    if not clean_code.startswith(valid_prefixes):
        return None
    
    try:
        df_daily = data_loader.get_daily_data(file_path)
        if df_daily is None or len(df_daily) < 40: return None
        
        slice_len = min(len(df_daily), LOOKBACK_DAYS)
        df_daily = df_daily.iloc[-slice_len:].copy()
        df_daily['prev_close'] = df_daily['close'].shift(1)
        df_daily['amplitude'] = (df_daily['high'] - df_daily['low']) / df_daily['prev_close']
        
        target_indices = np.where(df_daily['amplitude'] > VOLATILITY_THRESHOLD)[0]
        if len(target_indices) == 0: return None
        
        df_60m = data_loader.get_min_data(clean_code, period='60m')
        df_15m = data_loader.get_min_data(clean_code, period='15m')
        
        records = []
        for idx in target_indices:
            if idx < 20 or idx >= len(df_daily) - 1: continue
            
            t_date = df_daily.index[idx]
            t_minus_1 = df_daily.index[idx - 1]
            t_minus_2 = df_daily.index[idx - 2]
            
            # --- 切片 ---
            d_slice_t2 = df_daily.iloc[:idx-1].copy()
            d_slice_t1 = df_daily.iloc[:idx].copy()
            
            m60_slice = None
            if df_60m is not None:
                if 'datetime' in df_60m.columns: df_60m.index = pd.to_datetime(df_60m['datetime'])
                else: df_60m.index = pd.to_datetime(df_60m.index)
                m60_slice = df_60m[df_60m.index <= pd.to_datetime(f"{t_minus_1.strftime('%Y-%m-%d')} 15:30:00")].copy()
                
            m15_slice = None
            if df_15m is not None:
                if 'datetime' in df_15m.columns: df_15m.index = pd.to_datetime(df_15m['datetime'])
                else: df_15m.index = pd.to_datetime(df_15m.index)
                m15_slice = df_15m[df_15m.index <= pd.to_datetime(f"{t_minus_1.strftime('%Y-%m-%d')} 15:30:00")].copy()
            
            # --- 提取原始数值 ---
            metrics = {
                '股票代码': stock_code_full,
                '异动日期(T日)': t_date.strftime('%Y-%m-%d')
            }
            
            metrics.update(extract_raw_metrics(d_slice_t2, prefix="日线T-2"))
            metrics.update(extract_raw_metrics(d_slice_t1, prefix="日线T-1"))
            metrics.update(extract_raw_metrics(m60_slice, prefix="尾盘60m"))
            metrics.update(extract_raw_metrics(m15_slice, prefix="尾盘15m"))
            
            # 计算爆发收益
            future_slice = df_daily.iloc[idx + 1: min(idx + 4, len(df_daily))]
            max_rebound = 0.0
            if not future_slice.empty:
                max_rebound = (future_slice['high'].max() - df_daily['close'].iloc[idx]) / df_daily['close'].iloc[idx]
            metrics['未来3日最高反弹%'] = round(max_rebound * 100, 2)
            
            records.append(metrics)
        return records
    except Exception:
        return None

def main():
    logger.info("🚀 启动 [多周期原始量价数据全息提取器]...")
    
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day"))
    
    with Pool(processes=min(cpu_count(), 12)) as pool:
        raw_results = pool.map(process_raw_data_dump, files)
        
    flat_records = []
    for r in raw_results:
        if r: flat_records.extend(r)
        
    df_raw = pd.DataFrame(flat_records)
    
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    report_path = os.path.join(OUTPUT_DIR, f'RAW_PRICE_VOL_METRICS_{date_str}.csv')
    df_raw.to_csv(report_path, index=False, encoding='utf-8-sig')
    
    logger.info(f"🎉 原始数据提取完成！共计 {len(df_raw)} 条异动切片。")
    logger.info(f"💾 数据已导出至: {report_path}")
    logger.info(f"💡 建议操作：使用 Excel 打开，按【尾盘15m_实体涨幅%】降序排列，查看前 10% 的极值是多少，直接将其设为你的 U 阈值！")

if __name__ == '__main__':
    main()
