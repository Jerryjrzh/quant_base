import os
import glob
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import data_loader

# ==========================================
# === 狙击手核心回测全局配置 ===
# ==========================================
STRATEGY_TO_TEST = 'MORSE_FACTOR_SNIPER' 
TARGET_PROFIT = 0.10  # 核心止盈目标：+10% 挂单
STOP_LOSS = -0.05     # 核心硬性止损：-5%

EVAL_DATE = '2026-05-6'  # 回测选股基准截面日
FORWARD_DAYS = 7        # 持仓/挂单观测窗口天数

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
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

# ==========================================
# 在 walk_forward_tester_s.py 的全局配置下方，新增板块参数生成器
# ==========================================
def get_board_params(stock_code):
    """🚨 Grok 特调：应对科创/创业板 20CM 降维打击"""
    if stock_code.startswith(('688', '689')):   # 科创板 20CM
        return {'target_profit': 0.15, 'stop_loss': -0.08}
    elif stock_code.startswith('300'):          # 创业板 20CM
        return {'target_profit': 0.12, 'stop_loss': -0.07}
    else:                                       # 主板 10CM
        return {'target_profit': 0.10, 'stop_loss': -0.05}

# ==========================================
# 完全覆盖你原来的 worker 函数
# ==========================================
def worker(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    if not (stock_code.startswith(('60', '688', '00', '300', '92')) and len(stock_code) == 6): 
        return None

    try:
        df_daily = data_loader.get_daily_data(file_path)
        if df_daily is None or df_daily.empty: return None
        df_15m = data_loader.get_min_data(stock_code, period='15m')
        historical_df, future_df = get_time_sliced_data(df_daily, EVAL_DATE, FORWARD_DAYS)
        if historical_df is None: return None
        
        m15_slice = None
        if df_15m is not None and not df_15m.empty:
            if 'datetime' in df_15m.columns: df_15m.index = pd.to_datetime(df_15m['datetime'])
            else: df_15m.index = pd.to_datetime(df_15m.index)
            cutoff = pd.to_datetime(f"{historical_df.index[-1].strftime('%Y-%m-%d')} 15:30:00")
            m15_slice = df_15m[df_15m.index <= cutoff].copy()

        if STRATEGY_TO_TEST == 'MORSE_FACTOR_SNIPER':
            from screenergf import apply_morse_sniper_strategy
            res = apply_morse_sniper_strategy(historical_df, df_15m=m15_slice)
        else:
            res = None

        if res is None or not res.get('signal'):
            return None

        # 🚨 获取板块自适应盈亏比
        board_params = get_board_params(stock_code)
        target_p = board_params['target_profit']
        stop_l = board_params['stop_loss']

        trigger_buy = res['trigger_price']
        strategy_score = res.get('score', 80)
        
        static_take_profit = trigger_buy * (1 + target_p)
        static_stop_loss = trigger_buy * (1 + stop_l)
        
        t0_close = historical_df['close'].iloc[-1]
        
        # --- 提取基因供后续日志记录 (已精简) ---
        morse_features = f"S:{strategy_score}"
        
        if future_df.empty:
            return {
                'stock_code': stock_code_full, 'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'entry_date': "", 'exit_date': "", 'future_min_low': 0.0, 'future_max_high': 0.0,
                'strategy': STRATEGY_TO_TEST, 'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                'trigger_buy': trigger_buy, 'stop_loss': static_stop_loss,
                'fit_score': strategy_score, 'ma_slope': 0.0,
                'morse_features': morse_features, 'future_7d_path': ""
            }

        future_min_low = future_df['low'].min()
        future_max_high = future_df['high'].max()
        
        trade_status = "未成交"
        entry_price, exit_price, mfe_raw, mae_raw, holding_days = 0.0, 0.0, 0.0, 0.0, 0
        entry_date, exit_date = "", ""
        pending_days = 0
        
        actual_take_profit = 0.0
        actual_stop_loss = 0.0
        
        for idx, row in future_df.iterrows():
            current_date_str = idx.strftime('%Y-%m-%d')
            
            if trade_status == "未成交":
                pending_days += 1
                if pending_days > 4: 
                    trade_status = "挂单超时撤销"
                    break
                
                open_price = row['open']
                low_price = row['low']
                
                # 🚨 Grok 终极防御 1：跳空低开核按钮过滤 (开盘直接跌破买点 3.5%，绝不接刀)
                if open_price <= trigger_buy * 0.965:
                    trade_status = "大幅低开放弃"
                    break
                    
                # 🚨 Grok 终极防御 2：开盘定生死 (高开回落可以接，低开闷杀不能接)
                # 如果开盘价连昨天收盘价的 -2% 都不到，说明势头完全坏了，撤单。
                if open_price <= t0_close * 0.98:
                    trade_status = "弱势低开撤单"
                    break

                # 正常撮合：摸到挂单价
                if low_price <= trigger_buy:
                    # 🚨 Grok 终极防御 3：必须有资金承接（不能收在最低点附近）
                    # 收盘价必须比最低价拉起 0.8%，否则说明接刀子接到半山腰了，假装没看见
                    if row['close'] >= low_price * 1.008:
                        trade_status = "持仓中"
                        entry_date = current_date_str
                        
                        # 🚨 修复滑点灾难：min() 取孰低，永远不当接盘侠
                        entry_price = min(trigger_buy, open_price * 0.995) 
                        
                        actual_take_profit = entry_price * (1 + target_p)
                        actual_stop_loss = entry_price * (1 + stop_l)
                        
                        # 日内刺穿防线
                        if low_price <= actual_stop_loss or row['close'] <= actual_stop_loss:
                            trade_status = "止损出局"
                            exit_price = row['close']
                            exit_date = current_date_str
                            mae_raw = (low_price - entry_price) / entry_price
                            break
                    else:
                        continue # 今天没接稳，不买，等明天
            
            elif trade_status == "持仓中":
                holding_days += 1
                curr_profit = (row['high'] - entry_price) / entry_price
                curr_drawdown = (row['low'] - entry_price) / entry_price
                
                if curr_profit > mfe_raw: mfe_raw = curr_profit
                if curr_drawdown < mae_raw: mae_raw = curr_drawdown
                
                if row['high'] >= actual_take_profit:
                    trade_status = "止盈成功"
                    exit_price = actual_take_profit
                    exit_date = current_date_str
                    break
                
                if row['low'] <= actual_stop_loss:
                    trade_status = "止损出局"
                    exit_price = actual_stop_loss
                    exit_date = current_date_str
                    break

        if trade_status == "持仓中":
            exit_price = future_df.iloc[-1]['close']
            trade_status = "持仓到期"
            exit_date = future_df.index[-1].strftime('%Y-%m-%d')

        path_list = []
        for idx, r in future_df.iterrows():
            high_pct = (r['high'] - t0_close) / t0_close * 100
            low_pct = (r['low'] - t0_close) / t0_close * 100
            path_list.append(f"H:{high_pct:+.1f}%/L:{low_pct:+.1f}%")
        future_7d_path = " -> ".join(path_list)

        return {
            'stock_code': stock_code_full,
            'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
            'entry_date': entry_date, 'exit_date': exit_date,
            'future_min_low': future_min_low, 'future_max_high': future_max_high,
            'strategy': STRATEGY_TO_TEST, 'trade_status': trade_status,
            'final_pnl': (exit_price - entry_price)/entry_price if entry_price > 0 else 0.0,
            'MFE': mfe_raw, 'MAE': mae_raw, 'holding_days': holding_days,
            'entry_slip': (entry_price - trigger_buy)/trigger_buy if entry_price > 0 else 0.0,
            'trigger_buy': trigger_buy, 'stop_loss': static_stop_loss,
            'fit_score': strategy_score, 'ma_slope': 0.0,
            'morse_features': morse_features, 'future_7d_path': future_7d_path
        }
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return None

def save_and_report_results(results):
    if not results: return
    df_res = pd.DataFrame(results)
    latest_csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    df_res.to_csv(latest_csv_path, index=False, float_format='%.4f')
    logger.info(f"💾 莫尔斯加权狙击选股测试数据已保存至: {latest_csv_path}")

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day")) 
            
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
        
    valid_results = [r for r in raw_results if r is not None]
    
    if valid_results:
        # 按照莫尔斯矩阵的打分高低进行系统优先级降序排列
        valid_results.sort(key=lambda x: (x.get('fit_score', 0), x.get('ma_slope', 0)), reverse=True)
        
        MAX_LIMIT = 500
        if len(valid_results) > MAX_LIMIT:
            logger.info(f"⚠️ 今日满足强共振个股共 {len(valid_results)} 只，执行机构级 Top {MAX_LIMIT} 容量截断！")
            valid_results[:] = valid_results[:MAX_LIMIT]
            
    save_and_report_results(valid_results)
