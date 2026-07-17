import os
import glob
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import data_loader

from screenergf import apply_adaptive_ma_support_optimized

# ==========================================
# === 评估任务全局配置 ===
# ==========================================
STRATEGY_TO_TEST = 'ADAPTIVE_MA_SUPPORT' 
# 指定日期进行回测
EVAL_DATE = '2026-5-8'  
FORWARD_DAYS = 9        
# 初始目标 10%，4天后降为 7%
TARGET_PROFIT = 0.098    
DECAY_PROFIT = 0.07     

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
DATE_STR = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, f'WalkForward_{STRATEGY_TO_TEST}')
os.makedirs(RESULT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_time_sliced_data(df, eval_date_str, forward_days):
    if df is None or df.empty: return None, None
    if eval_date_str:
        eval_date = pd.to_datetime(eval_date_str)
        historical_df = df[df.index <= eval_date].copy()
        if historical_df.empty or len(historical_df) < 150: return None, None
        last_idx = df.index.get_loc(historical_df.index[-1])
        future_df = df.iloc[last_idx + 1 : last_idx + 1 + forward_days].copy()
    else:
        if len(df) < 150: return None, None
        historical_df = df.copy()
        future_df = df.iloc[0:0].copy() 
    return historical_df, future_df

def generate_strategy_signals(df, strategy_name):
    current_price = df['close'].iloc[-1]
    if strategy_name == 'ADAPTIVE_MA_SUPPORT':
        signal_series = apply_adaptive_ma_support_optimized(df)
        if signal_series is None or not signal_series.iloc[-1]: 
            return False, 0, 0, {}
        
        ma_val = getattr(signal_series, 'current_ma_val', current_price)
        deep_touches = getattr(signal_series, 'deep_touches', 0)
        is_deep_wash = getattr(signal_series, 'is_deep_wash', False)
        
        if is_deep_wash or deep_touches > 14:
            trigger_buy = ma_val * 0.96   
            stop_loss = ma_val * 0.88     
        else:
            trigger_buy = ma_val * 0.985  
            stop_loss = ma_val * 0.92     
            
        return (True, trigger_buy, stop_loss, {
            'best_ma': getattr(signal_series, 'best_ma_period', 0),
            'polarity': int(getattr(signal_series, 'polarity_confirmed', False)),
            'fit_score': getattr(signal_series, 'fit_score', 0.0),
            'deep_touches': deep_touches
        })
    return False, 0, 0, {}

def worker(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    if not (stock_code.startswith(('60', '688', '00', '300')) and len(stock_code) == 6): 
        return None

    try:
        df = data_loader.get_daily_data(file_path)
        if df is None: return None
        
        historical_df, future_df = get_time_sliced_data(df, EVAL_DATE, FORWARD_DAYS)
        if historical_df is None: return None
        
        has_signal, trigger_buy, stop_loss, features = generate_strategy_signals(historical_df, STRATEGY_TO_TEST)
        if not has_signal: return None

        if future_df.empty:
            return {
                'stock_code': stock_code_full, 'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'strategy': STRATEGY_TO_TEST, 'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                'trigger_buy': trigger_buy, 'stop_loss': stop_loss, **features
            }

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
                        if row['low'] <= extreme_stop:
                            trade_status, exit_price, mae_raw, holding_days = "止损出局", min(extreme_stop, row['close']), (row['low'] - entry_price) / entry_price, 1
                            break
                        elif row['close'] <= stop_loss:
                            trade_status, exit_price, mae_raw, holding_days = "止损出局", row['close'], (row['low'] - entry_price) / entry_price, 1
                            break
            
            elif trade_status == "持仓中":
                holding_days += 1
                curr_profit = (row['high'] - entry_price) / entry_price
                curr_drawdown = (row['low'] - entry_price) / entry_price
                
                if curr_profit > mfe_raw: mfe_raw = curr_profit
                if curr_drawdown < mae_raw: mae_raw = curr_drawdown
                
                # 🔻【改进1：时间衰减止盈】前4天要10%，第5天开始降至7%
                current_target_profit = TARGET_PROFIT if holding_days <= 4 else DECAY_PROFIT
                
                if row['high'] >= entry_price * (1 + current_target_profit):
                    trade_status = "止盈成功"
                    mfe_raw = max(mfe_raw, current_target_profit) 
                    exit_price = entry_price * (1 + current_target_profit)
                    break
                
                # 🔻【改进2：收盘防错杀止损】
                extreme_stop = stop_loss * 0.97
                if row['low'] <= extreme_stop: # 盘中暴跌彻底失控
                    trade_status, exit_price = "止损出局", min(extreme_stop, row['open'])
                    break
                elif row['close'] <= stop_loss: # 盘中刺穿不算，必须收盘价跌破止损线才认输
                    trade_status, exit_price = "止损出局", row['close']
                    break
                    
        if trade_status == "持仓中":
            exit_price, trade_status = future_df.iloc[-1]['close'], "持仓到期"

        result = {
            'stock_code': stock_code_full,
            'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
            'strategy': STRATEGY_TO_TEST,
            'trade_status': trade_status,
            'final_pnl': (exit_price - entry_price)/entry_price if entry_price > 0 else 0.0,
            'MFE': mfe_raw,
            'MAE': mae_raw,
            'holding_days': holding_days,
            'entry_slip': (entry_price - trigger_buy)/trigger_buy if entry_price > 0 else 0.0,
            'trigger_buy': trigger_buy,
            'stop_loss': stop_loss
        }
        result.update(features)
        return result
    except Exception:
        return None

def save_and_report_results(results):
    if not results: return
    df_res = pd.DataFrame(results)
    latest_csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    df_res.to_csv(latest_csv_path, index=False, float_format='%.4f')
    logger.info(f"💾 纯净无污染 T+1 测试数据已保存至: {latest_csv_path}")

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
    save_and_report_results([r for r in raw_results if r is not None])
