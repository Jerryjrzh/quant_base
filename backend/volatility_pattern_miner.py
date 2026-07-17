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
        # 日线加载
        df_daily = data_loader.get_daily_data(file_path)
        if df_daily is None or len(df_daily) < 30: # 基础数据过少直接略过
            return None
            
        # 安全切片上限控制
        slice_len = min(len(df_daily), LOOKBACK_DAYS)
        df_daily = df_daily.iloc[-slice_len:].copy()
        
        # 计算振幅
        df_daily['prev_close'] = df_daily['close'].shift(1)
        df_daily['amplitude'] = (df_daily['high'] - df_daily['low']) / df_daily['prev_close']
        
        target_indices = np.where(df_daily['amplitude'] > VOLATILITY_THRESHOLD)[0]
        if len(target_indices) == 0:
            return None
            
        clean_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
        df_60m = data_loader.get_min_data(clean_code, period='60m')
        df_15m = data_loader.get_min_data(clean_code, period='15m')
        
        # 🛡️ 强力防御 1：确保分钟线索引均被强转回标准的 DatetimeIndex 
        for df_min in [df_60m, df_15m]:
            if df_min is not None and not df_min.empty:
                if 'datetime' in df_min.columns:
                    df_min.index = pd.to_datetime(df_min['datetime'])
                else:
                    df_min.index = pd.to_datetime(df_min.index)

        # 遍历异动节点，提取前序形态
        for idx in target_indices:
            # 🛡️ 强力防御 2：安全边界防护，防止回溯 T-2 时发生日线越界
            if idx < 5 or idx >= len(df_daily): 
                continue 
            
            t_date = df_daily.index[idx]
            t_minus_1_date = df_daily.index[idx - 1]
            t_minus_2_date = df_daily.index[idx - 2]
            
            # --- A. 提取 T-2 的日线形态 ---
            daily_t2_slice = df_daily.iloc[:idx-1].copy()
            if len(daily_t2_slice) < 20: # 日线样本太少算不出指标
                continue
                
            daily_patterns = detector.detect_talib_patterns(daily_t2_slice)
            deep_wash_daily = detector.detect_deep_step_reversal(daily_t2_slice)
            if deep_wash_daily.get('reversal_signal'):
                daily_patterns['DEEP_STEP_REVERSAL'] = 1
                
            # --- B. 提取 T-2 的 60分钟线形态 ---
            m60_patterns = {}
            if df_60m is not None and not df_60m.empty:
                t2_cutoff = pd.to_datetime(f"{t_minus_2_date.strftime('%Y-%m-%d')} 15:30:00")
                m60_t2_slice = df_60m.loc[df_60m.index <= t2_cutoff].copy()
                # 🛡️ 强力防御 3：防止分钟线切片过短导致 TA-Lib 内部 iloc 越界崩溃（核心修护）
                if len(m60_t2_slice) >= 30: 
                    m60_patterns = detector.detect_talib_patterns(m60_t2_slice)
                
            # --- C. 提取 T-1 的 15分钟线形态 ---
            m15_patterns = {}
            if df_15m is not None and not df_15m.empty:
                t1_cutoff = pd.to_datetime(f"{t_minus_1_date.strftime('%Y-%m-%d')} 15:30:00")
                m15_t1_slice = df_15m.loc[df_15m.index <= t1_cutoff].copy()
                # 🛡️ 强力防御 4：防止 15 分钟线样本过短导致越界崩溃
                if len(m15_t1_slice) >= 30:
                    m15_patterns = detector.detect_talib_patterns(m15_t1_slice)

            # 过滤出线规则：只有在至少提取到了一个有效基础形态时才打包输出，否则放入异常池
            snapshot = {
                'stock_code': stock_code_full,
                'target_date': t_date.strftime('%Y-%m-%d'),
                'target_amplitude': f"{df_daily['amplitude'].iloc[idx]:.2%}",
                't2_daily_patterns': list(daily_patterns.keys()),
                't2_60m_patterns': list(m60_patterns.keys()),
                't1_15m_patterns': list(m15_patterns.keys()),
            }
            
            is_anomaly = (len(daily_patterns) == 0 and len(m60_patterns) == 0 and len(m15_patterns) == 0)
            if is_anomaly:
                results['anomaly_patterns'].append(snapshot)
            else:
                results['matched_patterns'].append(snapshot)
                
        return results
    except Exception as e:
        logger.error(f"❌ 处理 {stock_code_full} 严重失败: {e}")
        return None

def generate_kline_morse_code(df_slice) -> str:
    """
    【K线莫尔斯电码发生器】将传入的 DataFrame 序列转化为一串金融基因码
    """
    if df_slice is None or len(df_slice) < 2:
        return "UNKNOWN"
        
    # 计算量能基准（20日均量）
    vol_ma20 = df_slice['volume'].rolling(20, min_periods=1).mean()
    
    morse_codes = []
    
    # 遍历切片中的每一根 K 线（比如 T-2, T-1）
    for i in range(len(df_slice)):
        row = df_slice.iloc[i]
        v_ma = vol_ma20.iloc[i]
        
        close, open_p, high, low = row['close'], row['open'], row['high'], row['low']
        pct = (close - open_p) / (open_p + 1e-9)
        amplitude = (high - low) / (open_p + 1e-9)
        
        # 1. 测序：实体姿态 (Body)
        if pct > 0.035:    body = 'U'
        elif pct > 0.005:  body = 'u'
        elif pct < -0.035: body = 'D'
        elif pct < -0.005: body = 'd'
        else:              body = 'X'
        
        # 2. 测序：影线抵抗 (Shadow)
        upper_shadow = high - max(close, open_p)
        lower_shadow = min(close, open_p) - low
        body_size = abs(close - open_p)
        
        if lower_shadow > body_size * 1.2 and lower_shadow > upper_shadow:
            shadow = 'B'  # 下影线抵抗
        elif upper_shadow > body_size * 1.2 and upper_shadow > lower_shadow:
            shadow = 'T'  # 上影线抛压
        elif upper_shadow < body_size * 0.1 and lower_shadow < body_size * 0.1:
            shadow = 'N'  # 光头光脚
        else:
            shadow = 'S'  # 震荡有影线
            
        # 3. 测序：量能异动 (Volume)
        vol_ratio = row['volume'] / (v_ma + 1e-9)
        if vol_ratio > 1.8:   volume = 'H'
        elif vol_ratio < 0.6: volume = 'L'
        else:                 volume = 'A'
        
        # 组装单根K线电码
        morse_codes.append(f"{body}{shadow}{volume}")
        
    return "-".join(morse_codes)

def main():
    logger.info("🚀 启动高波动前瞻形态挖掘引擎 (V2 最终稳定版)...")
    
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    
    if not files:
        logger.error("❌ 未找到任何本地 .day 数据文件，请检查 vipdoc 路径！")
        return

    # 为了稳定性，多进程核心数进行安全调配限制
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
    
    matched_path = os.path.join(OUTPUT_DIR, f'matched_patterns_{date_str}.csv')
    anomaly_path = os.path.join(OUTPUT_DIR, f'anomaly_patterns_{date_str}.csv')
    
    if not matched_df.empty:
        matched_df.to_csv(matched_path, index=False, encoding='utf-8-sig')
        logger.info(f"💾 已知特征异动池成功导出至: {matched_path}")
    if not anomaly_df.empty:
        anomaly_df.to_csv(anomaly_path, index=False, encoding='utf-8-sig')
        logger.info(f"🚨 未知/异常形态隐秘金矿池已导出至: {anomaly_path}")
        # 看看在未识别的暴涨票中，哪种15分钟电码出现的频率最高
        top_codes = anomaly_df['t1_15m_sequence'].value_counts().head(10)
        print(top_codes)
    logger.info(f"🎉 跨时空全要素挖掘任务圆满结束。总计捕获匹配个股: {len(all_matched)} 例，异常个股: {len(all_anomalies)} 例,频率最高: {top_codes}")


if __name__ == '__main__':
    main()
