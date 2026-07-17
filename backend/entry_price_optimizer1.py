import pandas as pd
import numpy as np

def optimize_entry_prices(csv_path="full_calendar_trades.csv"):
    print("🚀 启动 [自适应折扣定价] 闭环分析模型...\n")
    df = pd.read_csv(csv_path)
    
    # 1. 解析 Morse 核心形态组合 (简化版提取)
    # 假设我们重点关注日线的 T1 形态作为大类划分
    df['Main_Morph'] = df['morse_features'].apply(
        lambda x: 'T1_B(长下影)' if 'T1_B:1' in x else 
                  'T1_L(缩量)' if 'T1_L:1' in x else 
                  'T1_U(上影突破)' if 'T1_U:1' in x else 
                  'T1_D(大阴)' if 'T1_D:1' in x else 'Other'
    )

    # 2. 预设不同的挂单折扣率 (从 0% 即市价，一直到 -8% 深度低吸)
    discounts = np.arange(0.0, -0.085, -0.005) # [0.0, -0.005, -0.01 ... -0.08]
    
    results = []
    
    # 3. 按形态分组进行寻优
    for morph, group in df.groupby('Main_Morph'):
        if len(group) < 50: continue # 过滤小样本
        
        best_discount = 0.0
        max_ev = -999.0
        best_metrics = {}
        
        for disc in discounts:
            # 核心判断：是否成交？
            # 只要该笔交易的实际最大回撤(MAE) <= 我们的挂单折扣，就能成交
            # 例如：实际 MAE 是 -0.05，我们挂单 -0.03，则成功买入。
            filled_mask = group['MAE'] <= disc
            fill_rate = filled_mask.mean()
            
            if fill_rate < 0.05: # 成交率低于5%没有实战意义
                continue
                
            # 核心计算：成交后的真实收益
            # 既然买得更便宜了，实际收益率 = 原收益率 + 节约的成本 (|disc|)
            # 这里做线性近似，严谨计算需还原具体价格，但近似误差在千分位
            adjusted_pnl = group.loc[filled_mask, 'final_pnl'] + abs(disc)
            avg_pnl = adjusted_pnl.mean()
            win_rate = (adjusted_pnl > 0).mean()
            
            # 计算期望值 Expected Value (闭环核心指标)
            ev = fill_rate * avg_pnl
            
            if ev > max_ev:
                max_ev = ev
                best_discount = disc
                best_metrics = {
                    '形态': morph,
                    '样本数': len(group),
                    '最优挂单位置': f"{best_discount*100:.1f}%",
                    '预计成交率': f"{fill_rate*100:.1f}%",
                    '成交后胜率': f"{win_rate*100:.1f}%",
                    '成交后均收益': f"{avg_pnl*100:.2f}%",
                    '综合期望EV': round(ev, 4)
                }
                
        if best_metrics:
            results.append(best_metrics)
            
    # 4. 打印闭环参数表
    res_df = pd.DataFrame(results).sort_values('综合期望EV', ascending=False)
    print("📊 各形态最优入场定价表 (用于反向写入 screenergf.py)：")
    print(res_df.to_markdown(index=False))

if __name__ == "__main__":
    optimize_entry_prices()
