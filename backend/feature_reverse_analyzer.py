import os
import glob
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import data_loader
import talib

from screenergf import apply_adaptive_ma_support_optimized

# ==========================================
# === 1. 诊断任务全局配置 ===
# ==========================================
STRATEGY_TO_TEST = 'ADAPTIVE_MA_SUPPORT' 
# 建议选择一个信号密集爆发、方便归纳特征的历史切片日（如大震荡日）
EVAL_DATE = '2026-04-01'  
FORWARD_DAYS = 9        
TARGET_PROFIT = 0.098    
DECAY_PROFIT = 0.075     

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'Diagnostic'))
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_time_sliced_data(df, eval_date_str, forward_days):
    if df is None or df.empty: return None, None
    eval_date = pd.to_datetime(eval_date_str)
    historical_df = df[df.index <= eval_date].copy()
    if historical_df.empty or len(historical_df) < 150: return None, None
    last_idx = df.index.get_loc(historical_df.index[-1])
    future_df = df.iloc[last_idx + 1 : last_idx + 1 + forward_days].copy()
    return historical_df, future_df

def worker(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    if not (stock_code.startswith(('60', '688', '00', '300')) and len(stock_code) == 6): 
        return None

    try:
        df = data_loader.get_daily_data(file_path)
        if df is None: return None
        
        historical_df, future_df = get_time_sliced_data(df, EVAL_DATE, FORWARD_DAYS)
        if historical_df is None or future_df.empty: return None
        
        # 激活策略获取底层的 Series
        signal_series = apply_adaptive_ma_support_optimized(historical_df)
        if signal_series is None or not signal_series.iloc[-1]: return None

        # 2. 提取最原始的技术属性特征（不含任何人工加权打分）
        ma_val = getattr(signal_series, 'current_ma_val', historical_df['close'].iloc[-1])
        deep_touches = getattr(signal_series, 'deep_touches', 0)
        is_deep_wash = getattr(signal_series, 'is_deep_wash', False)
        burst_ratio = getattr(signal_series, 'burst_ratio', 0.0)
        ma_slope = getattr(signal_series, 'ma_slope', 0.0)
        drop_velocity = getattr(signal_series, 'drop_velocity', 0.0)
        
        # 重新获取当天的交易量比，用于多维印证
        vol_ma20 = historical_df['volume'].rolling(20).mean().iloc[-1]
        raw_vol_ratio = historical_df['volume'].iloc[-1] / vol_ma20 if vol_ma20 > 0 else 1.0
        
        recent_120 = historical_df.iloc[-120:]
        raw_amplitude = (recent_120['high'].max() - recent_120['low'].min()) / recent_120['low'].min()

        # 3. 动态计算前台条件单执行路径
        if is_deep_wash or deep_touches > 14:
            trigger_buy = ma_val * 0.96   
            stop_loss = ma_val * 0.88     
        else:
            trigger_buy = ma_val * 1.005  
            stop_loss = ma_val * 0.925    

        trade_status = "未成交"
        entry_price, exit_price, mfe_raw, mae_raw, holding_days = 0.0, 0.0, 0.0, 0.0, 0
        
        for idx, row in future_df.iterrows():
            if trade_status == "未成交":
                if row['open'] <= stop_loss: continue
                if row['low'] <= trigger_buy:
                    if row['close'] >= row['low'] * 1.015:  
                        trade_status = "持仓中"
                        entry_price = min(trigger_buy, row['low'] * 1.015) 
                        
                        extreme_stop = stop_loss * 0.97
                        if row['low'] <= extreme_stop or row['close'] <= stop_loss:
                            trade_status, exit_price, holding_days = "止损出局", row['close'], 1
                            break
            elif trade_status == "持仓中":
                holding_days += 1
                curr_profit = (row['high'] - entry_price) / entry_price
                curr_drawdown = (row['low'] - entry_price) / entry_price
                
                if curr_profit > mfe_raw: mfe_raw = curr_profit
                if curr_drawdown < mae_raw: mae_raw = curr_drawdown
                
                current_target_profit = TARGET_PROFIT if holding_days <= 4 else DECAY_PROFIT
                if row['high'] >= entry_price * (1 + current_target_profit):
                    trade_status = "止盈成功"
                    exit_price = entry_price * (1 + current_target_profit)
                    break
                
                if row['low'] <= stop_loss * 0.97 or row['close'] <= stop_loss: 
                    trade_status = "止损出局"
                    exit_price = row['close']
                    break
                    
        if trade_status == "持仓中":
            exit_price, trade_status = future_df.iloc[-1]['close'], "持仓到期"

        # 4. 汇总无污染数据行
        return {
            'stock_code': stock_code_full,
            'trade_status': trade_status,
            'final_pnl': (exit_price - entry_price)/entry_price if entry_price > 0 else 0.0,
            'holding_days': holding_days,
            'MFE': mfe_raw,
            'MAE': mae_raw,
            
            # --- 原始核心技术参数指标 (无人工权重分配) ---
            'raw_score_v12': getattr(signal_series, 'fit_score', 0.0), # 作为老打分参考
            'best_ma': int(getattr(signal_series, 'best_ma_period', 0)),
            'deep_touches': int(deep_touches),
            'burst_ratio': round(burst_ratio, 4),
            'ma_slope': round(ma_slope, 4),
            'drop_velocity': round(drop_velocity, 4),
            'vol_ratio': round(raw_vol_ratio, 4),
            'amplitude': round(raw_amplitude, 4)
        }
    except Exception:
        return None

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    
    logger.info(f"📊 启动特征流水线，正在扫描全市场提取原始数据特征...")
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
        
    valid_results = [r for r in raw_results if r is not None]
    
    if valid_results:
        df_diagnostic = pd.DataFrame(valid_results)
        diagnostic_csv = os.path.join(OUTPUT_DIR, 'raw_feature_outcome_matrix.csv')
        df_diagnostic.to_csv(diagnostic_csv, index=False, float_format='%.4f')
        logger.info(f"💾 特征矩阵导出成功！共 {len(df_diagnostic)} 只有效候选券。文件路径: {diagnostic_csv}")
