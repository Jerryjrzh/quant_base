import pandas as pd
import numpy as np

def categorize_board(stock_code):
    """根据股票代码划分市场板块，对应不同的波动率特征"""
    code_str = str(stock_code).lower()
    # 提取数字部分
    num_part = ''.join([c for c in code_str if c.isdigit()])
    
    if num_part.startswith('300'):
        return '2_创业板(20%)'
    elif num_part.startswith('688'):
        return '2_科创板(20%)'
    elif code_str.startswith('bj') or num_part.startswith('920'):
        return '3_北交所(30%)'
    else:
        return '1_主板(10%)'

def optimize_entry_prices_3d(csv_path="full_calendar_trades.csv"):
    print("🚀 启动 [板块定制化 x 自适应折扣定价] 闭环分析模型...\n")
    df = pd.read_csv(csv_path)
    
    # 1. 解析板块和形态
    df['Board'] = df['stock_code'].apply(categorize_board)
    df['Main_Morph'] = df['morse_features'].apply(
        lambda x: 'T1_B(长下影)' if 'T1_B:1' in x else 
                  'T1_L(缩量)' if 'T1_L:1' in x else 
                  'T1_U(上影突破)' if 'T1_U:1' in x else 'Other'
    )

    # 由于北交所波动巨大，我们把寻优网格加深到 -12%
    discounts = np.arange(0.0, -0.125, -0.005) 
    
    results = []
    
    # 2. 按【板块】和【形态】进行双重分组寻优
    for (board, morph), group in df.groupby(['Board', 'Main_Morph']):
        if len(group) < 30 or morph == 'Other': continue # 过滤小样本
        
        best_discount = 0.0
        max_ev = -999.0
        best_metrics = {}
        
        for disc in discounts:
            filled_mask = group['MAE'] <= disc
            fill_rate = filled_mask.mean()
            
            if fill_rate < 0.05: continue
                
            adjusted_pnl = group.loc[filled_mask, 'final_pnl'] + abs(disc)
            avg_pnl = adjusted_pnl.mean()
            ev = fill_rate * avg_pnl
            
            if ev > max_ev:
                max_ev = ev
                best_discount = disc
                best_metrics = {
                    '板块': board,
                    '形态': morph,
                    '样本数': len(group),
                    '最优挂单位置': f"{best_discount*100:.1f}%",
                    '成交率': f"{fill_rate*100:.1f}%",
                    '成交后均收益': f"{avg_pnl*100:.2f}%",
                    '综合期望EV': round(ev, 4)
                }
                
        if best_metrics:
            results.append(best_metrics)
            
    res_df = pd.DataFrame(results).sort_values(['板块', '综合期望EV'], ascending=[True, False])
    print("📊 各板块 x 形态 最优入场定价表：")
    print(res_df.to_markdown(index=False))

if __name__ == "__main__":
    optimize_entry_prices_3d()
