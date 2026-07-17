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

def generate_strategy_signals(df, strategy_name):
    """
    【数据通路打通】安全截获选股端抛出的周线大底低点及阻力压力位特征
    """
    current_price = df['close'].iloc[-1]
    if strategy_name == 'ADAPTIVE_MA_SUPPORT':
        signal_series = apply_adaptive_ma_support_optimized(df)
        if signal_series is None or not signal_series.iloc[-1]: 
            return False, 0, 0, {}
        
        ma_val = getattr(signal_series, 'current_ma_val', current_price)
        deep_touches = getattr(signal_series, 'deep_touches', 0)
        is_deep_wash = getattr(signal_series, 'is_deep_wash', False)
        
        # 经典原版高收益挂单网骨架
        if is_deep_wash or deep_touches > 14:
            trigger_buy = ma_val * 0.96   
            stop_loss = ma_val * 0.88     
        else:
            trigger_buy = ma_val * 0.99  
            stop_loss = ma_val * 0.92     
            
        return (True, trigger_buy, stop_loss, {
            'best_ma': getattr(signal_series, 'best_ma_period', 0),
            'polarity': int(getattr(signal_series, 'polarity_confirmed', False)),
            'fit_score': getattr(signal_series, 'fit_score', 0.0),
            'deep_touches': deep_touches,
            'burst_ratio': getattr(signal_series, 'burst_ratio', 0.0), 
            'is_deep_wash': is_deep_wash ,
            'ma_slope': getattr(signal_series, 'ma_slope', 0.0),
            'drop_velocity': getattr(signal_series, 'drop_velocity', 0.0),
            # 🚀 扩充解包通路，完美接收大级别特征
            'weekly_floor_low': getattr(signal_series, 'weekly_floor_low', df['low'].iloc[-150:].min()),
            'recent_resistance': getattr(signal_series, 'recent_resistance', df['close'].iloc[-60:].max())
        })
    return False, 0, 0, {}

def _calculate_priority_score(df, backtest_stats, features=None):
    """
    【期望打分模型全面进化】融合周线安全边际与压力位反弹预期空间
    打分模型不干扰撮合，专门负责拦截截面的智能动态优化与排序
    """
    try:
        score = 0.0
        current_price = df['close'].iloc[-1]
        feat = features if features else {}

        # 1. 历史回测胜率基准（权重 35%）
        win_rate_str = backtest_stats.get('win_rate', '0.0%').replace('%', '')
        win_rate = float(win_rate_str) / 100.0
        score += win_rate * 35

        # 2. 历史回测平均最大收益（权重 25%）
        profit_str = backtest_stats.get('avg_max_profit', '0.0%').replace('%', '')
        avg_profit = float(profit_str) / 100.0
        score += min(avg_profit / 0.4, 1.0) * 25

        # 3. 📐 压力位反弹预期潜在空间空间增益（权重 20%）
        recent_resistance = feat.get('recent_resistance', current_price * 1.15)
        # 精算当前价格距离上方筹码阻力位的潜在垂直反弹斜率
        expected_upside = (recent_resistance - current_price) / (current_price + 1e-9)
        if expected_upside > 0:
            # 反弹潜在预期空间越大，得分越高（若空间有 15% 以上则拿满 20 分期望分）
            score += min(expected_upside / 0.15, 1.0) * 20

        # 4. 🛡️ 周线级别绝对历史大底安全垫（权重 20%）
        weekly_floor_low = feat.get('weekly_floor_low', current_price * 0.90)
        # 精算当前收盘价距离周线极限物理地板的悬空溢价距离
        distance_to_floor = (current_price - weekly_floor_low) / (current_price + 1e-9)
        
        if distance_to_floor <= 0.03:
            score += 20  # 极为贴近周线历史铁底，安全垫牢固，加满 20 分！
        elif distance_to_floor <= 0.06:
            score += 12  # 相对安全
        elif distance_to_floor > 0.12:
            score -= 15  # 悬空过高，属于空中楼阁，惩罚扣分防止追高

        # 动态将精算出的压力位反弹期望百分比更新回状态卡，方便复盘分析
        backtest_stats['expected_upside_pnl'] = f"{expected_upside:.1%}"
        backtest_stats['weekly_floor_low_val'] = weekly_floor_low
        backtest_stats['recent_resistance_val'] = recent_resistance

        return round(score, 1)
    except Exception:
        return 0.0

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

        # 快速计算单股的基础特征
        backtest_stats = calculate_backtest_stats_fast(historical_df, pd.Series(True, index=historical_df.index)) # 占位
        
        # 注入周线、压力特征进入优先级打分卡
        priority_score = _calculate_priority_score(historical_df, backtest_stats, features)

        if future_df.empty:
            return {
                'stock_code': stock_code_full,
                'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'entry_date': "", 'exit_date': "",
                'future_min_low': 0.0, 'future_max_high': 0.0,
                'strategy': STRATEGY_TO_TEST,
                'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                'trigger_buy': trigger_buy, 'stop_loss': stop_loss,
                'priority_score': priority_score,
                'fit_score': features.get('fit_score', 0.0),
                'best_ma': features.get('best_ma', 0),
                'deep_touches': features.get('deep_touches', 0),
                'polarity': features.get('polarity', 0),
                'burst_ratio': features.get('burst_ratio', 0.0),
                'ma_slope': features.get('ma_slope', 0.0),
                'drop_velocity': features.get('drop_velocity', 0.0),
                'is_deep_wash': int(features.get('is_deep_wash', False)),
                'weekly_floor_low': features.get('weekly_floor_low', 0.0),
                'recent_resistance': features.get('recent_resistance', 0.0),
                'expected_upside_pnl': backtest_stats.get('expected_upside_pnl', '0.0%')
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
                        if row['low'] <= extreme_stop or row['close'] <= stop_loss:
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
                if row['low'] <= extreme_stop or row['close'] <= stop_loss: 
                    trade_status, exit_price, exit_date = "止损出局", row['close'], current_date_str
                    break
                    
        if trade_status == "持仓中":
            exit_price = future_df.iloc[-1]['close']
            trade_status = "持仓到期"
            exit_date = future_df.index[-1].strftime('%Y-%m-%d')

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
            # 🚀 特征抛出
            'priority_score': priority_score,
            'fit_score': features.get('fit_score', 0.0),
            'best_ma': features.get('best_ma', 0),
            'deep_touches': features.get('deep_touches', 0),
            'polarity': features.get('polarity', 0),
            'burst_ratio': features.get('burst_ratio', 0.0),
            'ma_slope': features.get('ma_slope', 0.0),
            'drop_velocity': features.get('drop_velocity', 0.0),
            'is_deep_wash': int(features.get('is_deep_wash', False)),
            'weekly_floor_low': features.get('weekly_floor_low', 0.0),
            'recent_resistance': features.get('recent_resistance', 0.0),
            'expected_upside_pnl': backtest_stats.get('expected_upside_pnl', '0.0%')
        }
        return result
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return None

def calculate_backtest_stats_fast(df, signal_series):
    """快速计算回测统计信息占位（可无缝扩展）"""
    return {
        'total_signals': 1,
        'win_rate': '62.5%',
        'avg_max_profit': '14.2%',
        'avg_max_drawdown': '-4.5%',
        'avg_days_to_peak': '3.2 天'
    }

def save_and_report_results(results):
    if not results: return
    df_res = pd.DataFrame(results)
    latest_csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    df_res.to_csv(latest_csv_path, index=False, float_format='%.4f')
    logger.info(f"💾 纯净无污染时空特征级 T+1 测试数据已保存至: {latest_csv_path}")

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day")) 
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
        
    valid_results = [r for r in raw_results if r is not None]
    
    if valid_results:
        # 🌟【拦截大闸】改用全新进化的 priority_score (期望潜在利润空间) 进行截面智能优选
        valid_results.sort(key=lambda x: x.get('priority_score', 0.0), reverse=True)
        
        MAX_LIMIT = 15 # 自动拦截并有限建仓期望最高的精品 Top 15
        original_count = len(valid_results)
        if original_count > MAX_LIMIT:
            logger.info(f"⚠️ 当日产生 {original_count} 个信号，触发 Top {MAX_LIMIT} 阻力期望拦截优化！")
            valid_results[:] = valid_results[:MAX_LIMIT]
        else:
            logger.info(f"✅ 当日共保留 {original_count} 个有效建仓信号。")
            
    save_and_report_results(valid_results)