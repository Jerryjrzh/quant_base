#!/usr/bin/env python3
"""
量化特征透视引擎 - 针对板块、趋势、形态、乖离率的深度分析
"""
import pandas as pd

def run_feature_analysis():
    csv_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/morse_price_validation_matrix_v2.csv"
    
    try:
        df = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"❌ 找不到特征回测矩阵: {csv_path}")
        return

    print(f"✅ 成功加载特征回测矩阵，总样本: {len(df)}")
    
    # 定义透视分析函数
    def analyze_group(group):
        total = len(group)
        if total < 10:  # 过滤掉偶然样本，避免统计失真
            return None
            
        entry_hit_count = group['entry_hit'].sum()
        target_hit_count = group['target_hit'].sum()
        
        entry_rate = (entry_hit_count / total) * 100
        target_rate = (target_hit_count / entry_hit_count * 100) if entry_hit_count > 0 else 0
        
        avg_entry_bias = group['entry_bias_pct'].mean() * 100
        avg_target_bias = group['target_bias_pct'].mean() * 100
        
        return pd.Series({
            '样本数': total,
            '买入成交率(%)': round(entry_rate, 1),
            '买入平均偏离(%)': round(avg_entry_bias, 2),
            '止盈触及率(%)': round(target_rate, 1),
            '止盈平均偏离(%)': round(avg_target_bias, 2)
        })

    # ==========================================
    # 维度一：板块 + 乖离率 (揭示超跌抄底与主升追高的不同表现)
    # ==========================================
    print("\n" + "="*80)
    print("📊 维度一：【板块 + MA60乖离率】交叉透视")
    print("="*80)
    bias_summary = df.groupby(['board_type', 'bias_tier']).apply(analyze_group).dropna()
    print(bias_summary.to_string())

    # ==========================================
    # 维度二：板块 + 趋势阶段 (揭示吸筹期与派发期的参数差异)
    # ==========================================
    print("\n" + "="*80)
    print("📊 维度二：【板块 + 趋势阶段】交叉透视")
    print("="*80)
    trend_summary = df.groupby(['board_type', 'trend_phase']).apply(analyze_group).dropna()
    print(trend_summary.to_string())
    
    # ==========================================
    # 维度三：高胜率绝杀组合提取 (挖掘黄金坑)
    # ==========================================
    print("\n" + "="*80)
    print("🏆 发现高胜率阿尔法 (Alpha) 特征组合")
    print("="*80)
    # 寻找 买入率 > 40% 且 止盈率 > 30% 的极致组合
    alpha_combos = df.groupby(['board_type', 'trend_phase', 'bias_tier']).apply(analyze_group).dropna()
    best_combos = alpha_combos[(alpha_combos['买入成交率(%)'] > 40) & (alpha_combos['止盈触及率(%)'] > 30)]
    
    if not best_combos.empty:
        print("💡 以下组合属于系统最优博弈区，可在此类情况下放大仓位或提高目标价：")
        print(best_combos.sort_values(by='止盈触及率(%)', ascending=False).to_string())
    else:
        print("当前参数下，暂未发现同时满足极高买入率和极高止盈率的绝对黄金组合，需参考上述透视表继续微调 parameters。")

if __name__ == "__main__":
    run_feature_analysis()
