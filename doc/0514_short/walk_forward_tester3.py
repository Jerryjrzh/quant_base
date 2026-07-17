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
EVAL_DATE = '2026-4-2'  
FORWARD_DAYS = 8        
TARGET_PROFIT = 0.098    
DECAY_PROFIT = 0.075     

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

def generate_strategy_signals_a(df, strategy_name):
    current_price = df['close'].iloc[-1]
    if strategy_name == 'ADAPTIVE_MA_SUPPORT':
        signal_series = apply_adaptive_ma_support_optimized(df)
        if signal_series is None or not signal_series.iloc[-1]: 
            return False, 0, 0, {}
        
        ma_val = getattr(signal_series, 'current_ma_val', current_price)
        deep_touches = getattr(signal_series, 'deep_touches', 0)
        is_deep_wash = getattr(signal_series, 'is_deep_wash', False)
        
        if is_deep_wash or deep_touches > 20:
            trigger_buy = ma_val * 0.96   
            stop_loss = ma_val * 0.88     
        else:
            trigger_buy = ma_val * 0.985  
            stop_loss = ma_val * 0.955     
            
        return (True, trigger_buy, stop_loss, {
            'best_ma': getattr(signal_series, 'best_ma_period', 0),
            'polarity': int(getattr(signal_series, 'polarity_confirmed', False)),
            'fit_score': getattr(signal_series, 'fit_score', 0.0),
            'deep_touches': deep_touches
        })
    return False, 0, 0, {}
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
            trigger_buy = ma_val * 0.99  
            stop_loss = ma_val * 0.92     
            
        # 🔻【修复点】：把新增的评分指标全部塞进 features 字典传给外层
        return (True, trigger_buy, stop_loss, {
            'best_ma': getattr(signal_series, 'best_ma_period', 0),
            'polarity': int(getattr(signal_series, 'polarity_confirmed', False)),
            'fit_score': getattr(signal_series, 'fit_score', 0.0),
            'deep_touches': deep_touches,
            'burst_ratio': getattr(signal_series, 'burst_ratio', 0.0), 
            'is_deep_wash': is_deep_wash ,
            'ma_slope': getattr(signal_series, 'ma_slope', 0.0),
            'drop_velocity': getattr(signal_series, 'drop_velocity', 0.0)
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

        # 🔻【修复点】：最新数据的 T+1 挂单也要输出完整的评分字段
        if future_df.empty:
            return {
                'stock_code': stock_code_full,
                'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'entry_date': "",
                'exit_date': "",
                'future_min_low': 0.0,
                'future_max_high': 0.0,
                'strategy': STRATEGY_TO_TEST,
                'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                'trigger_buy': trigger_buy, 'stop_loss': stop_loss,
                'fit_score': features.get('fit_score', 0.0),
                'best_ma': features.get('best_ma', 0),
                'deep_touches': features.get('deep_touches', 0),
                'polarity': features.get('polarity', 0),
                'burst_ratio': features.get('burst_ratio', 0.0),
                'ma_slope': getattr(signal_series, 'ma_slope', 0.0),
                'drop_velocity': getattr(signal_series, 'drop_velocity', 0.0),
                'is_deep_wash': int(features.get('is_deep_wash', False))
                
                
            }

        trade_status = "未成交"
        entry_price, exit_price, mfe_raw, mae_raw, holding_days = 0.0, 0.0, 0.0, 0.0, 0
        entry_date, exit_date = "", ""
        
        future_min_low = future_df['low'].min() if not future_df.empty else 0.0
        future_max_high = future_df['high'].max() if not future_df.empty else 0.0
        
        for idx, row in future_df.iterrows():
            current_date_str = idx.strftime('%Y-%m-%d')
            
            if trade_status == "未成交":
                if row['open'] <= stop_loss: continue
                    
                if row['low'] <= trigger_buy:
                    if row['close'] >= row['low'] * 1.015:  
                        trade_status = "持仓中"
                        entry_date = current_date_str
                        entry_price = min(trigger_buy, row['low'] * 1.015) 
                        
                        extreme_stop = stop_loss * 0.97
                        if row['low'] <= extreme_stop:
                            trade_status, exit_price, mae_raw, holding_days = "止损出局", min(extreme_stop, row['close']), (row['low'] - entry_price) / entry_price, 1
                            exit_date = current_date_str
                            break
                        elif row['close'] <= stop_loss:
                            trade_status, exit_price, mae_raw, holding_days = "止损出局", row['close'], (row['low'] - entry_price) / entry_price, 1
                            exit_date = current_date_str
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
                    exit_date = current_date_str
                    mfe_raw = max(mfe_raw, current_target_profit) 
                    exit_price = entry_price * (1 + current_target_profit)
                    break
                
                extreme_stop = stop_loss * 0.97
                if row['low'] <= extreme_stop: 
                    trade_status, exit_price, exit_date = "止损出局", min(extreme_stop, row['open']), current_date_str
                    break
                elif row['close'] <= stop_loss: 
                    trade_status, exit_price, exit_date = "止损出局", row['close'], current_date_str
                    break
                    
        if trade_status == "持仓中":
            exit_price = future_df.iloc[-1]['close']
            trade_status = "持仓到期"
            exit_date = future_df.index[-1].strftime('%Y-%m-%d')

        # 🔻【修复点】：从 features 获取变量，而不是不存在的 signal_series
        result = {
            'stock_code': stock_code_full,
            'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
            'entry_date': entry_date,
            'exit_date': exit_date,
            'future_min_low': future_min_low,
            'future_max_high': future_max_high,
            'strategy': STRATEGY_TO_TEST,
            'trade_status': trade_status,
            'final_pnl': (exit_price - entry_price)/entry_price if entry_price > 0 else 0.0,
            'MFE': mfe_raw,
            'MAE': mae_raw,
            'holding_days': holding_days,
            'entry_slip': (entry_price - trigger_buy)/trigger_buy if entry_price > 0 else 0.0,
            'trigger_buy': trigger_buy,
            'stop_loss': stop_loss,
            'fit_score': features.get('fit_score', 0.0),
            'best_ma': features.get('best_ma', 0),
            'deep_touches': features.get('deep_touches', 0),
            'polarity': features.get('polarity', 0),
            'burst_ratio': features.get('burst_ratio', 0.0),
            'is_deep_wash': int(features.get('is_deep_wash', False))
        }
        return result
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}") # 加个错误打印，防止未来再被吞掉
        return None
    
def worker_a(file_path):
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

        if future_df.empty:
            return {
                'stock_code': stock_code_full, 'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'strategy': STRATEGY_TO_TEST, 'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                'trigger_buy': trigger_buy, 'stop_loss': stop_loss, **features
            }

        # 🔻【核心修改】：增加日期与未成交波动记录
        trade_status = "未成交"
        entry_price, exit_price, mfe_raw, mae_raw, holding_days = 0.0, 0.0, 0.0, 0.0, 0
        entry_date, exit_date = "", ""
        
        future_min_low = future_df['low'].min() if not future_df.empty else 0.0
        future_max_high = future_df['high'].max() if not future_df.empty else 0.0
        
        for idx, row in future_df.iterrows():
            current_date_str = idx.strftime('%Y-%m-%d')
            
            if trade_status == "未成交":
                if row['open'] <= stop_loss: continue
                    
                if row['low'] <= trigger_buy:
                    if row['close'] >= row['low'] * 1:  
                        trade_status = "持仓中"
                        entry_date = current_date_str # 记录买入日
                        entry_price = min(trigger_buy, row['low'] * 1) 
                        
                        extreme_stop = stop_loss * 0.97
                        if row['low'] <= extreme_stop:
                            trade_status, exit_price, mae_raw, holding_days = "止损出局", min(extreme_stop, row['close']), (row['low'] - entry_price) / entry_price, 1
                            exit_date = current_date_str # 记录当天止损日
                            break
                        elif row['close'] <= stop_loss:
                            trade_status, exit_price, mae_raw, holding_days = "止损出局", row['close'], (row['low'] - entry_price) / entry_price, 1
                            exit_date = current_date_str
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
                    exit_date = current_date_str # 记录止盈日
                    mfe_raw = max(mfe_raw, current_target_profit) 
                    exit_price = entry_price * (1 + current_target_profit)
                    break
                
                extreme_stop = stop_loss * 0.97
                if row['low'] <= extreme_stop: 
                    trade_status, exit_price = "止损出局", min(extreme_stop, row['open'])
                    exit_date = current_date_str
                    break
                elif row['close'] <= stop_loss: 
                    trade_status, exit_price = "止损出局", row['close']
                    exit_date = current_date_str
                    break
                    
        if trade_status == "持仓中":
            exit_price = future_df.iloc[-1]['close']
            trade_status = "持仓到期"
            exit_date = future_df.index[-1].strftime('%Y-%m-%d') # 记录到期日

        # =================================================================
        # 严格同步：在 walk_forward_tester3.py 的 worker 函数尾部替换 result 字典
        # =================================================================
        result = {
            'stock_code': stock_code_full,
            'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
            'entry_date': entry_date,
            'exit_date': exit_date,
            'future_min_low': future_min_low,
            'future_max_high': future_max_high,
            'strategy': STRATEGY_TO_TEST,
            'trade_status': trade_status,
            'final_pnl': (exit_price - entry_price)/entry_price if entry_price > 0 else 0.0,
            'MFE': mfe_raw,
            'MAE': mae_raw,
            'holding_days': holding_days,
            'entry_slip': (entry_price - trigger_buy)/trigger_buy if entry_price > 0 else 0.0,
            'trigger_buy': trigger_buy,
            'stop_loss': stop_loss,
            
            # 🔻【核心新增：全维度评分系统指标特征，强行保留至 CSV】🔻
            'fit_score': features.get('fit_score', 0.0),          # 策略最终总分
            'best_ma': features.get('best_ma', 0),                # 专属生命线周期
            'deep_touches': features.get('deep_touches', 0),      # 日线深踩触碰次数
            'polarity': features.get('polarity', 0),              # 是否确立极性转换
            'burst_ratio': getattr(signal_series, 'burst_ratio', 0.0), # 过去45天的爆发基因系数
            'is_deep_wash': int(getattr(signal_series, 'is_deep_wash', False)) # 是否属于MA30假死叉深度洗盘
        }
        # 移除可能重复的 features.update，统一由上方明细控制
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
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day")) 
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
        
    # 1. 过滤掉未产生信号的空值
    valid_results = [r for r in raw_results if r is not None]
    
    # 🔻【终极风控：原地截面强行截断】🔻
    if valid_results:
        # 按照拟合分(fit_score)和极性确认(polarity)从高到低排序
        valid_results.sort(key=lambda x: (
            x.get('fit_score', 0), 
            x.get('polarity', 0)
        ), reverse=True)
        
        MAX_LIMIT = 500
        original_count = len(valid_results)
        
        if original_count > MAX_LIMIT:
            logger.info(f"⚠️ 当日共产生 {original_count} 个信号，触发资金防暴量截断！")
            # 💡 修复核心：使用 [:] 原地修改列表内容，强制覆盖内存指针，确保外层函数接收到的一定是Top 20
            valid_results[:] = valid_results[:MAX_LIMIT]
            logger.info(f"✂️ 已成功强规整，最终保留最强 Top {len(valid_results)} 只。")
        else:
            logger.info(f"✅ 当日共保留 {original_count} 个有效建仓信号。")
            
    # 2. 将被原地强行截断后的最强 20 只，传入保存引擎
    save_and_report_results(valid_results)
