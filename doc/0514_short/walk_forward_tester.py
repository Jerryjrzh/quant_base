import os
import glob
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import data_loader

from screenergf import apply_adaptive_ma_support_optimized, apply_reversed_short_optimized
from strategies import apply_triple_cross, apply_macd_zero_axis_strategy

# ==========================================
# === 评估任务全局配置 ===
# ==========================================
STRATEGY_TO_TEST = 'ADAPTIVE_MA_SUPPORT' 
# 指定日期 (如 '2026-05-06')，None 表示从当前最新数据前推
EVAL_DATE = '2026-5-19'  
FORWARD_DAYS = 8        
TARGET_PROFIT = 0.10    

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
DATE_STR = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, f'WalkForward_{STRATEGY_TO_TEST}')
os.makedirs(RESULT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_time_sliced_data(df, eval_date_str, forward_days):
    if eval_date_str:
        eval_date = pd.to_datetime(eval_date_str)
        historical_df = df[df.index <= eval_date].copy()
        if historical_df.empty or len(historical_df) < 150: return None, None
        last_idx = df.index.get_loc(historical_df.index[-1])
        future_df = df.iloc[last_idx + 1 : last_idx + 1 + forward_days].copy()
    else:
        if len(df) < 150 + forward_days: return None, None
        historical_df = df.iloc[:-forward_days].copy()
        future_df = df.iloc[-forward_days:].copy()
    return historical_df, future_df

def generate_strategy_signals(df, strategy_name):
    current_price = df['close'].iloc[-1]
    if strategy_name == 'ADAPTIVE_MA_SUPPORT':
        signal_series = apply_adaptive_ma_support_optimized(df)
        if signal_series is None or not signal_series.iloc[-1]: return False, 0, 0, {}
        ma_val = getattr(signal_series, 'current_ma_val', current_price)
        deep_touches = getattr(signal_series, 'deep_touches', 0)
        if deep_touches > 15:
            trigger_buy = ma_val * 0.96   # 激进接针：均线下方 4%
            stop_loss = ma_val * 0.88     # 宽幅止损：给足 12% 的极限诱空空间
        else:
            trigger_buy = ma_val * 0.985  # 常规接针：均线下方 1.5%
            stop_loss = ma_val * 0.92     # 常规止损：8% 防守空间

        return (True, trigger_buy, stop_loss, {
            'best_ma': getattr(signal_series, 'best_ma_period', 0),
            'polarity': int(getattr(signal_series, 'polarity_confirmed', False)),
            'fit_score': getattr(signal_series, 'fit_score', 0.0),
            'deep_touches': getattr(signal_series, 'deep_touches', 0)
        })
    return False, 0, 0, {}

def worker(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    if not (stock_code.startswith(('60', '688', '00', '300', '92')) and len(stock_code) == 6): return None

    try:
        df = data_loader.get_daily_data(file_path)
        if df is None: return None
        historical_df, future_df = get_time_sliced_data(df, EVAL_DATE, FORWARD_DAYS)
        if historical_df is None or future_df is None or future_df.empty: return None
        
        has_signal, trigger_buy, stop_loss, features = generate_strategy_signals(historical_df, STRATEGY_TO_TEST)
        if not has_signal: return None

        trade_status, entry_price, exit_price, mfe_raw, mae_raw, holding_days = "未成交", 0.0, 0.0, 0.0, 0.0, 0
        
        for idx, row in future_df.iterrows():
            if trade_status == "未成交":
                if row['close'] >= row['low'] * 1.015:  # 有 1.5% 的资金抄底抵抗
                        trade_status = "持仓中"
                        # 模拟在反弹的过程中成交，而不是买在绝对最低点
                        entry_price = min(trigger_buy, row['low'] * 1.015) 
                        
                        # 如果极端情况：买入后立马砸穿了宽幅止损线
                        if row['low'] <= stop_loss:
                            trade_status = "止损出局"
                            mae_raw = (row['low'] - entry_price) / entry_price
                            exit_price = row['low']
                            holding_days = 1
                            break
            elif trade_status == "持仓中":
                holding_days += 1
                curr_profit, curr_drawdown = (row['high'] - entry_price) / entry_price, (row['low'] - entry_price) / entry_price
                if curr_profit > mfe_raw: mfe_raw = curr_profit
                if curr_drawdown < mae_raw: mae_raw = curr_drawdown
                
                if row['low'] <= stop_loss:
                    trade_status, exit_price = "止损出局", min(stop_loss, row['open'])
                    break
                if row['high'] >= entry_price * (1 + TARGET_PROFIT):
                    trade_status, mfe_raw, exit_price = "止盈成功", max(mfe_raw, TARGET_PROFIT), entry_price * (1 + TARGET_PROFIT)
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
    
    # 【修复重点】保存一个固定名称的文件到 backend 根目录，供分析器读取
    latest_csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    df_res.to_csv(latest_csv_path, index=False, float_format='%.4f')
    
    # 同时也保留带时间戳的工程归档
    df_res.to_csv(os.path.join(RESULT_DIR, f'time_machine_{DATE_STR}.csv'), index=False, float_format='%.4f')
    logger.info(f"💾 测试数据已保存至: {latest_csv_path} (供分析器使用)")

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
    save_and_report_results([r for r in raw_results if r is not None])
