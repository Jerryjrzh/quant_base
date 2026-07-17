import os
import glob
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging
import json

# 假设你的形态识别器和数据加载器在同级目录
from kline_patterns import KlinePatternDetector
import data_loader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# === 挖掘任务全局配置 ===
# ==========================================
VOLATILITY_THRESHOLD = 0.15  # 目标单日波动率 > 15% (振幅或涨跌幅)
LOOKBACK_DAYS = 250          # 扫描过去多少个交易日（约1年）

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'pattern_mining')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def process_stock_patterns(stock_code_full):
    """
    核心挖掘逻辑：寻找 T 日大波动，解剖 T-2 和 T-1 的微观形态
    """
    detector = KlinePatternDetector()
    results = {
        'matched_patterns': [],  # 成功识别到标准形态的样本
        'anomaly_patterns': []   # 未识别出任何标准形态的异常样本（重点研究对象）
    }
    
    try:
        # 1. 加载全周期数据 (请确保你的 data_loader 支持获取分钟级数据)
        # 如果你的本地只有 .day 数据，可以通过 akshare/tushare 缓存分钟线，或解析 tdx 的 .fzline
        df_daily = data_loader.get_daily_data(stock_code_full)
        if df_daily is None or len(df_daily) < LOOKBACK_DAYS:
            return None
            
        df_daily = df_daily.iloc[-LOOKBACK_DAYS:]
        
        # 2. 寻找 T 日异动节点 (波动率 > 15%)
        # 波动率计算：(当日最高 - 当日最低) / 昨日收盘价
        df_daily['prev_close'] = df_daily['close'].shift(1)
        df_daily['amplitude'] = (df_daily['high'] - df_daily['low']) / df_daily['prev_close']
        
        # 找出所有符合大波动条件的 T 日索引
        target_indices = np.where(df_daily['amplitude'] > VOLATILITY_THRESHOLD)[0]
        
        if len(target_indices) == 0:
            return None
            
        # 提取股票代码纯数字部分用于分钟线加载
        clean_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
        
        # 为了效率，只在发现目标后加载分钟线数据
        # 假设你有类似 data_loader.get_min_data(code, period='60m'/'15m') 的函数
        df_60m = data_loader.get_min_data(clean_code, period='60m')
        df_15m = data_loader.get_min_data(clean_code, period='15m')
        
        if df_60m is None or df_15m is None:
            return None # 缺乏微观数据则跳过

        # 3. 遍历异动节点，提取前序形态
        for idx in target_indices:
            if idx < 5: continue # 确保前面有足够的K线计算形态
            
            t_date = df_daily.index[idx]
            t_minus_1_date = df_daily.index[idx - 1]
            t_minus_2_date = df_daily.index[idx - 2]
            
            # --- A. 提取 T-2 的日线形态 ---
            daily_t2_slice = df_daily.iloc[:idx-1].copy() # 截断到 T-2
            daily_patterns = detector.detect_talib_patterns(daily_t2_slice)
            deep_wash_daily = detector.detect_deep_step_reversal(daily_t2_slice)
            if deep_wash_daily.get('reversal_signal'):
                daily_patterns['DEEP_STEP_REVERSAL'] = 1
                
            # --- B. 提取 T-2 的 60分钟线形态 ---
            # 截取直到 T-2 收盘的所有 60 分钟数据
            m60_t2_slice = df_60m[df_60m.index <= pd.to_datetime(f"{t_minus_2_date.strftime('%Y-%m-%d')} 15:00:00")].copy()
            if len(m60_t2_slice) > 20:
                m60_patterns = detector.detect_talib_patterns(m60_t2_slice)
            else:
                m60_patterns = {}
                
            # --- C. 提取 T-1 的 15分钟线形态 ---
            # 截取直到 T-1 收盘的所有 15 分钟数据
            m15_t1_slice = df_15m[df_15m.index <= pd.to_datetime(f"{t_minus_1_date.strftime('%Y-%m-%d')} 15:00:00")].copy()
            if len(m15_t1_slice) > 20:
                m15_patterns = detector.detect_talib_patterns(m15_t1_slice)
            else:
                m15_patterns = {}

            # 4. 组装数据快照
            snapshot = {
                'stock_code': stock_code_full,
                'target_date': t_date.strftime('%Y-%m-%d'),
                'target_amplitude': f"{df_daily['amplitude'].iloc[idx]:.2%}",
                't2_daily_patterns': daily_patterns,
                't2_60m_patterns': m60_patterns,
                't1_15m_patterns': m15_patterns,
            }
            
            # 5. 异常分类逻辑 (核心分离机制)
            # 如果日线、小时线、15分钟线 【全部没有】 识别出现有的标准形态
            # 说明这极有可能是庄家一种极其隐蔽的、未被 TA-Lib 收录的新洗盘手法！
            is_anomaly = (len(daily_patterns) == 0 and len(m60_patterns) == 0 and len(m15_patterns) == 0)
            
            if is_anomaly:
                results['anomaly_patterns'].append(snapshot)
            else:
                results['matched_patterns'].append(snapshot)
                
        return results
    except Exception as e:
        logger.error(f"处理 {stock_code_full} 失败: {e}")
        return None

def main():
    logger.info("🚀 启动异动前瞻特征挖掘引擎...")
    
    # 假设获取全市场标的
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    
    # 为了测试，可以先截取前 500 只股票
    # files = files[:500] 

    stock_codes = [os.path.basename(f).split('.')[0] for f in files]
    
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(process_stock_patterns, stock_codes)
        
    all_matched = []
    all_anomalies = []
    
    for r in raw_results:
        if r is not None:
            all_matched.extend(r['matched_patterns'])
            all_anomalies.extend(r['anomaly_patterns'])
            
    # 导出统计结果
    matched_df = pd.DataFrame(all_matched)
    anomaly_df = pd.DataFrame(all_anomalies)
    
    matched_path = os.path.join(OUTPUT_DIR, f'matched_patterns_{datetime.now().strftime("%Y%m%d")}.csv')
    anomaly_path = os.path.join(OUTPUT_DIR, f'anomaly_patterns_{datetime.now().strftime("%Y%m%d")}.csv')
    
    if not matched_df.empty:
        matched_df.to_csv(matched_path, index=False, encoding='utf-8-sig')
    if not anomaly_df.empty:
        anomaly_df.to_csv(anomaly_path, index=False, encoding='utf-8-sig')
        
    logger.info(f"✅ 挖掘完毕！")
    logger.info(f"📊 匹配到已知形态的异动样本数: {len(all_matched)}")
    logger.info(f"🚨 捕获到异常/未知形态的隐秘样本数: {len(all_anomalies)}")
    logger.info(f"💾 异常样本请重点研究：{anomaly_path}")

if __name__ == "__main__":
    main()
