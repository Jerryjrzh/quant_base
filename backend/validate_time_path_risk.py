#!/usr/bin/env python3
"""
量化风控引擎 v1.0 - 交易时间周期与路径轨迹 (T+N) 深度评估
"""

import sys
import os
import pandas as pd
import traceback
import multiprocessing
import concurrent.futures

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backtester import get_deep_analysis
from data_handler import get_market_volatility_profile, get_stock_data_simple

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

def track_trade_trajectory(stock_code: str, start_date: str, pred_entry: float, pred_target: float, pred_stop: float, lookahead_days: int = 7):
    """
    逐日回放K线，精确追踪 T+N 轨迹
    返回: (买入日T+N, 止盈日T+N, 止损日T+N, 绝对高点T+N)
    """
    try:
        df_full = get_stock_data_simple(stock_code)
        if df_full is None or df_full.empty:
            return None, None, None, None
            
        if not isinstance(df_full.index, pd.DatetimeIndex):
            df_full.index = pd.to_datetime(df_full.index)
            
        target_date = pd.to_datetime(start_date)
        future_data = df_full[df_full.index >= target_date].head(lookahead_days)
        
        if future_data.empty:
            return None, None, None, None
            
        entry_t = -1
        target_t = -1
        stop_t = -1
        peak_t = -1
        max_high = -9999
        
        # 逐日遍历 T+0 到 T+N
        for t, (date, row) in enumerate(future_data.iterrows()):
            high = float(row['high'])
            low = float(row['low'])
            
            # 记录绝对高点出现的日子
            if high > max_high:
                max_high = high
                peak_t = t
                
            # 1. 判断是否触发买入 (尚未买入时)
            if entry_t == -1 and low <= pred_entry:
                entry_t = t
                
            # 2. 如果已经买入，判断后续是否触发止盈或止损
            if entry_t != -1 and t >= entry_t: # 可以在买入当天(T+0)触发
                # 先判断止损 (风控第一)
                if stop_t == -1 and low <= pred_stop:
                    stop_t = t
                # 再判断止盈 (如果同一天既触及止损又触及止盈，保守视为先止损或洗盘失败)
                if target_t == -1 and high >= pred_target and stop_t == -1:
                    target_t = t
                    
        return entry_t, target_t, stop_t, peak_t
        
    except Exception as e:
        return None, None, None, None

def process_single_row(task_data):
    idx, row_dict = task_data
    stock = row_dict.get('stock_code')
    entry_date = row_dict.get('entry_date')
    
    if not stock or not entry_date:
        return {'status': 'error', 'msg': "缺失核心字段"}
        
    try:
        market_profile = get_market_volatility_profile(stock)
        board_name = market_profile['board_type']
        
        # 调取 V4.2 自适应系统的预测价
        analysis = get_deep_analysis(stock_code=stock, analysis_date=entry_date)
        if 'error' in analysis:
            return {'status': 'error'}
            
        advice = analysis.get('trading_advice', {})
        current_price = float(advice.get('current_price', 0))
        pred_entry = float(advice.get('entry_price', current_price))
        pred_target = float(advice.get('target_price', current_price * 1.1))
        pred_stop = float(advice.get('stop_price', current_price * 0.95))
        
        # ==========================================
        # 🚀 核心：时间路径追踪
        # ==========================================
        LOOKAHEAD = 7
        entry_t, target_t, stop_t, peak_t = track_trade_trajectory(
            stock, entry_date, pred_entry, pred_target, pred_stop, LOOKAHEAD
        )
        
        if entry_t is None:
            return {'status': 'error'}
            
        # 路径特征打标
        path_type = "未成交"
        if entry_t != -1:
            if target_t != -1:
                path_type = "成功止盈"
            elif stop_t != -1:
                path_type = "触发止损"
            else:
                path_type = "周期内持仓浮沉"
                
        # 极端风险标价：A杀陷阱 (高点出在极早期 T+0/1，随后触发止损)
        is_a_kill = (path_type == "触发止损" and peak_t <= 2)

        return {
            'status': 'success',
            'board_type': board_name,
            'entry_t': entry_t,
            'target_t': target_t,
            'stop_t': stop_t,
            'peak_t': peak_t,
            'path_type': path_type,
            'is_a_kill': is_a_kill
        }
    except Exception as e:
        return {'status': 'error'}

def evaluate_time_risk(sample_size=0):
    csv_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades.csv"
    try:
        df_csv = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"❌ 找不到文件: {csv_path}")
        return
        
    if sample_size > 0:
        df_csv = df_csv.sample(n=min(sample_size, len(df_csv)), random_state=42)
        
    tasks = [(idx, row.to_dict()) for idx, row in df_csv.iterrows()]
    results = []
    
    max_workers = max(1, multiprocessing.cpu_count() - 1)
    print(f"🚀 启动时间路径风控分析引擎 (核心数: {max_workers}) ...")
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single_row, task): task for task in tasks}
        iterator = concurrent.futures.as_completed(futures)
        if HAS_TQDM: iterator = tqdm(iterator, total=len(futures), desc="处理进度")
            
        for future in iterator:
            res = future.result()
            if res.get('status') == 'success':
                res.pop('status')
                results.append(res)

    df_res = pd.DataFrame(results)
    if df_res.empty: return
    
    # 过滤出成功买入的样本
    executed_df = df_res[df_res['entry_t'] != -1]
    
    print("\n" + "="*80)
    print("⏳ 交易时间与路径风控 (T+N) 深度分析报告")
    print("="*80)
    
    def analyze_board_time(group):
        total = len(group)
        wins = group[group['path_type'] == '成功止盈']
        losses = group[group['path_type'] == '触发止损']
        
        avg_entry_t = group['entry_t'].mean()
        avg_peak_t = group['peak_t'].mean()
        avg_win_t = wins['target_t'].mean() if not wins.empty else 0
        
        # A杀风险率：在所有交易中，高点极早出现然后迅速打损的比例
        a_kill_rate = group['is_a_kill'].sum() / total * 100
        
        return pd.Series({
            '买入样本': total,
            '平均买入日': f"T+{avg_entry_t:.1f}",
            '绝对高点平均日': f"T+{avg_peak_t:.1f}",
            '止盈平均耗时': f"T+{avg_win_t:.1f}" if avg_win_t > 0 else "-",
            '止损触发率(%)': round(len(losses)/total*100, 1),
            '极速A杀风险率(%)': round(a_kill_rate, 1)
        })

    print(executed_df.groupby('board_type').apply(analyze_board_time).to_string())
    print("="*80)
    
    # 保存结果
    out_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/time_path_risk_matrix.csv"
    df_res.to_csv(out_path, index=False)
    print(f"📊 路径矩阵已保存至: {out_path}")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sample_size = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    evaluate_time_risk(sample_size)
