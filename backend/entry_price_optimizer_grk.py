import pandas as pd
import numpy as np

def categorize_board(stock_code):
    code_str = str(stock_code).lower()
    num_part = ''.join([c for c in code_str if c.isdigit()])
    if num_part.startswith('300'):
        return '创业板(20%)'
    elif num_part.startswith('688'):
        return '科创板(20%)'
    elif code_str.startswith('bj') or num_part.startswith('920'):
        return '北交所(30%)'
    else:
        return '主板(10%)'

def simulate_trade_path(path_str, entry_discount, tp, sl):
    """真正路径依赖模拟器 - Gemini 改进版"""
    if pd.isna(path_str) or not isinstance(path_str, str):
        return -999
    
    days = path_str.split(' -> ')
    if not days:
        return 0.0
    
    buy_price_ratio = 1.0 + entry_discount   # 相对于原始 trigger_buy 的折扣
    
    for day in days:
        if '/L:' not in day:
            continue
        h_str, l_str = day.split('/L:')
        day_high = float(h_str.replace('H:', '').replace('%', '')) / 100.0
        day_low = float(l_str.replace('%', '')) / 100.0
        
        real_high_pnl = (1.0 + day_high) / buy_price_ratio - 1.0
        real_low_pnl = (1.0 + day_low) / buy_price_ratio - 1.0
        
        # 优先判断止损（悲观防守）
        if real_low_pnl <= sl:
            return sl
        if real_high_pnl >= tp:
            return tp
    
    # 持仓到期，按最后一天近似收盘价结算
    last_day = days[-1]
    h_str, l_str = last_day.split('/L:')
    last_high = float(h_str.replace('H:', '').replace('%', '')) / 100.0
    last_low = float(l_str.replace('%', '')) / 100.0
    last_close = (last_high + last_low) / 2.0
    final_pnl = (1.0 + last_close) / buy_price_ratio - 1.0
    return final_pnl


def optimize_entry_exit_v2(csv_path="full_calendar_trades.csv"):
    print("🚀 启动【路径依赖真实模拟】三维参数优化...\n")
    df = pd.read_csv(csv_path)
    df['Board'] = df['stock_code'].apply(categorize_board)
    
    df['Main_Morph'] = df['morse_features'].apply(
        lambda x: 'T1_B_strong' if 'T1_B:1' in str(x) else 
                  'T1_L_strong' if 'T1_L:1' in str(x) else 
                  'T1_U' if 'T1_U:1' in str(x) else 'Other'
    )

    entry_discounts = np.arange(0.0, -0.13, -0.005)
    tp_levels = [0.10, 0.12, 0.15, 0.18, 0.22]
    sl_levels = [-0.055, -0.065, -0.075, -0.085, -0.095, -0.11]

    results = []

    for (board, morph), group in df.groupby(['Board', 'Main_Morph']):
        if len(group) < 30 or morph == 'Other':
            continue

        best_ev = -999
        best_params = None

        for disc in entry_discounts:
            for tp in tp_levels:
                for sl in sl_levels:
                    pnls = []
                    for _, row in group.iterrows():
                        pnl = simulate_trade_path(row['future_7d_path'], disc, tp, sl)
                        if pnl > -900:  # 有效模拟
                            pnls.append(pnl)
                    
                    if not pnls:
                        continue
                        
                    fill_rate = len(pnls) / len(group)
                    avg_pnl = np.mean(pnls)
                    ev = fill_rate * avg_pnl
                    
                    if ev > best_ev:
                        best_ev = ev
                        best_params = {
                            '板块': board,
                            '形态': morph,
                            '样本数': len(group),
                            '入场折扣': f"{disc*100:+.1f}%",
                            '止盈目标': f"{tp*100:.0f}%",
                            '止损位置': f"{sl*100:.1f}%",
                            '成交率': f"{fill_rate*100:.1f}%",
                            '成交后均PNL': f"{avg_pnl*100:+.2f}%",
                            'EV': round(ev, 4)
                        }
        
        if best_params:
            results.append(best_params)

    res_df = pd.DataFrame(results).sort_values('EV', ascending=False)
    print(res_df.to_markdown(index=False))
    return res_df


if __name__ == "__main__":
    optimize_entry_exit_v2()
