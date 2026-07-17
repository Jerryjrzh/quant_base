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
# 指定日期 (如 '2026-05-13')，None 表示使用最新一天收盘数据进行 T+1 实盘复盘预演
EVAL_DATE = '2026-5-11'
FORWARD_DAYS = 8        
TARGET_PROFIT = 0.10    

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
DATE_STR = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, f'WalkForward_{STRATEGY_TO_TEST}')
os.makedirs(RESULT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# === 修复核心：严格剔除T日污染的时序切片机 ===
# ==========================================
def get_time_sliced_data(df, eval_date_str, forward_days):
    """
    严格按照时序切分：
    - 历史评估集（historical_df）：截止到 T 日（选股日）
    - 未来验证集（future_df）：从 T+1 日（下一个交易日）开始，绝不包含 T 日！
    """
    if df is None or df.empty:
        return None, None
        
    if eval_date_str:
        eval_date = pd.to_datetime(eval_date_str)
        historical_df = df[df.index <= eval_date].copy()
        if historical_df.empty or len(historical_df) < 150: 
            return None, None
            
        last_date = historical_df.index[-1]
        # 找到 T 日在全量数据中的位置
        last_idx = df.index.get_loc(last_date)
        
        # 🔻【关键修复】future_df 必须从 last_idx + 1 (即 T+1 日) 开始截取！
        future_df = df.iloc[last_idx + 1 : last_idx + 1 + forward_days].copy()
    else:
        # 如果未指定日期，默认以最新一天为 T 日（选股日）
        if len(df) < 150: 
            return None, None
            
        # 🔻【关键修复】最新一天的 T 日策略，其未来验证天数 forward_days 应该在现实中还未发生
        # 历史数据截止到最后一行（T日）
        historical_df = df.copy()
        # 未来数据在当前不可见，留空（等待 T+1 日实盘数据出来再复盘）
        future_df = df.iloc[0:0].copy() 
        
    return historical_df, future_df

def generate_strategy_signals(df, strategy_name):
    current_price = df['close'].iloc[-1]
    if strategy_name == 'ADAPTIVE_MA_SUPPORT':
        signal_series = apply_adaptive_ma_support_optimized(df)
        if signal_series is None or not signal_series.iloc[-1]: 
            return False, 0, 0, {}
        
        is_deep_wash = getattr(signal_series, 'is_deep_wash', False)
        burst_ratio = getattr(signal_series, 'burst_ratio', 0)

        if is_deep_wash or burst_ratio < 0.10:
            trigger_buy = ma_val * 0.96   
            stop_loss = ma_val * 0.88
            strategy_desc = "深踩型(MA30死叉/放宽防守)"
        else:
            trigger_buy = ma_val * 0.985  
            stop_loss = ma_val * 0.92     
            strategy_desc = "常规型(趋势稳健/常规防守)"
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
    if not (stock_code.startswith(('60', '688', '00', '300', '92')) and len(stock_code) == 6): 
        return None

    try:
        df = data_loader.get_daily_data(file_path)
        if df is None: return None
        
        historical_df, future_df = get_time_sliced_data(df, EVAL_DATE, FORWARD_DAYS)
        if historical_df is None: return None
        
        has_signal, trigger_buy, stop_loss, features = generate_strategy_signals(historical_df, STRATEGY_TO_TEST)
        if not has_signal: return None

        # 如果未来验证集为空（说明是在用最新数据做 T+1 挂单预演），标记为未成交状态传出，作为明天的挂单依据
        if future_df.empty:
            return {
                'stock_code': stock_code_full,
                'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'strategy': STRATEGY_TO_TEST,
                'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                'trigger_buy': trigger_buy, 'stop_loss': stop_loss, **features
            }

        trade_status = "未成交"
        entry_price, exit_price, mfe_raw, mae_raw, holding_days = 0.0, 0.0, 0.0, 0.0, 0
        
        # 严格在 T+1 日及以后的序列里滚动
        for idx, row in future_df.iterrows():
            if trade_status == "未成交":
                # 规则 1：如果开盘价就跌破了止损价，直接熔断单子，防止吃断头铡
                if row['open'] <= stop_loss:
                    continue
                    
                # 规则 2：防飞刀条件单触发检测
                if row['low'] <= trigger_buy:
                    # 必须有下影线抵抗才买
                    if row['close'] >= row['low'] * 1.015:  
                        trade_status = "持仓中"
                        entry_date = idx
                        # 正常回落反弹买入成本
                        entry_price = min(trigger_buy, row['low'] * 1.015) 
                        
                        # 检查当天买入后，是否又向下砸穿了止损线
                        if row['low'] <= stop_loss:
                            trade_status = "止损出局"
                            # 真实世界中，当天跌破止损，你只能在止损线或者更差的低点割肉
                            exit_price = min(stop_loss, row['close']) 
                            mae_raw = (row['low'] - entry_price) / entry_price
                            holding_days = 1
                            break
            
            elif trade_status == "持仓中":
                holding_days += 1
                curr_profit = (row['high'] - entry_price) / entry_price
                curr_drawdown = (row['low'] - entry_price) / entry_price
                
                if curr_profit > mfe_raw: mfe_raw = curr_profit
                if curr_drawdown < mae_raw: mae_raw = curr_drawdown
                
                # 检查持仓期内是否触及止损
                if row['low'] <= stop_loss:
                    trade_status = "止损出局"
                    # 如果当天开盘就低开在止损线下，以开盘价割肉；否则以标准的极限止损价割肉
                    exit_price = min(stop_loss, row['open'])
                    break
                
                # 检查是否触及 10% 目标止盈
                if row['high'] >= entry_price * (1 + TARGET_PROFIT):
                    trade_status = "止盈成功"
                    mfe_raw = max(mfe_raw, TARGET_PROFIT) 
                    exit_price = entry_price * (1 + TARGET_PROFIT)
                    break
                    
        if trade_status == "持仓中":
            exit_price = future_df.iloc[-1]['close']
            trade_status = "持仓到期"

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
    df_res.to_csv(os.path.join(RESULT_DIR, f'time_machine_{DATE_STR}.csv'), index=False, float_format='%.4f')
    logger.info(f"💾 纯净无污染 T+1 测试数据已保存至: {latest_csv_path}")

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
    save_and_report_results([r for r in raw_results if r is not None])
