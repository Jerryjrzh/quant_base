#!/usr/bin/env python3
"""
支撑位与阻力位 (Support/Resistance) 有效性回测验证工具
"""

import sys
import os
import pandas as pd
import traceback
import numpy as np

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backtester import get_deep_analysis
from data_handler import get_market_volatility_profile
def validate_support_resistance(sample_size=0):
    """
    使用历史时点切片，验证支撑位和阻力位的实际效用
    :param sample_size: 样本数，0表示使用全部完整数据
    """
    csv_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades.csv"
    
    try:
        df_csv = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"❌ 找不到文件: {csv_path}")
        return None

    print(f"✅ 成功加载 {len(df_csv)} 条历史交易记录")
    
    if sample_size > 0:
        df_csv = df_csv.sample(n=min(sample_size, len(df_csv)), random_state=42)
        print(f"🔍 抽取 {sample_size} 条样本进行评估...")
    else:
        print(f"🔍 使用全部 {len(df_csv)} 条完整数据进行深度评估...")
    
    results = []
    TOLERANCE = 0.03  # 3% 的容错度
    
    # 循环中的改动：
    for idx, row in df_csv.iterrows():
        stock = row['stock_code']
        entry_date = row['entry_date']
        
        # 获取该股票的专属容错带
        market_profile = get_market_volatility_profile(stock)
        dynamic_tolerance = market_profile['sr_tolerance']
        board_name = market_profile['board_type']
        
        print(f"[{idx+1:04d}/{len(df_csv)}] 分析 {stock} ({board_name}) @ {entry_date} ... ", end="")
        
        try:
            analysis = get_deep_analysis(stock_code=stock, analysis_date=entry_date)
            # ... 前面提取数据的代码不变 ...
            
            # --- 验证支撑位 (Support) ---
            supp_tested = False
            supp_held = False
            supp_broken = False
            supp_dist = None
            if support_level and current_price > 0:
                supp_dist = (current_price - support_level) / current_price
                # 测试条件：未来最低价跌到了支撑位上方容错带以内
                if future_min <= support_level * (1 + dynamic_tolerance):
                    supp_tested = True
                    # 破位条件：未来最低价跌穿了支撑位下方容错带
                    if future_min < support_level * (1 - dynamic_tolerance):
                        supp_broken = True
                    else:
                        supp_held = True
                        
            # --- 验证阻力位 (Resistance) 同理修改 ---
            res_tested = False
            res_held = False
            res_broken = False
            res_dist = None
            if resistance_level and current_price > 0:
                res_dist = (resistance_level - current_price) / current_price
                if future_max >= resistance_level * (1 - dynamic_tolerance):
                    res_tested = True
                    if future_max > resistance_level * (1 + dynamic_tolerance):
                        res_broken = True
                    else:
                        res_held = True

            results.append({
                'stock_code': stock,
                'board_type': board_name,          # 新增板块字段
                'dynamic_tol': dynamic_tolerance,  # 记录当时使用的容错率
                'entry_date': entry_date,
                'current_price': current_price,
                'future_min': future_min,
                'future_max': future_max,
                
                # 支撑位指标
                'support_level': support_level,
                'supp_dist_pct': round(supp_dist, 4) if supp_dist else None,
                'supp_tested': supp_tested,
                'supp_held': supp_held,
                'supp_broken': supp_broken,
                
                # 阻力位指标
                'resistance_level': resistance_level,
                'res_dist_pct': round(res_dist, 4) if res_dist else None,
                'res_tested': res_tested,
                'res_held': res_held,
                'res_broken': res_broken
            })
            
            print("✅ 完成")
            
        except Exception as e:
            print("❌ 异常")
            # traceback.print_exc()
            continue

    result_df = pd.DataFrame(results)
    
    # 统计支撑位表现
    total_supp_tested = result_df['supp_tested'].sum()
    supp_held_rate = (result_df['supp_held'].sum() / total_supp_tested * 100) if total_supp_tested > 0 else 0
    supp_broken_rate = (result_df['supp_broken'].sum() / total_supp_tested * 100) if total_supp_tested > 0 else 0
    avg_supp_dist = result_df['supp_dist_pct'].mean() * 100
    
    # 统计阻力位表现
    total_res_tested = result_df['res_tested'].sum()
    res_held_rate = (result_df['res_held'].sum() / total_res_tested * 100) if total_res_tested > 0 else 0
    res_broken_rate = (result_df['res_broken'].sum() / total_res_tested * 100) if total_res_tested > 0 else 0
    avg_res_dist = result_df['res_dist_pct'].mean() * 100
    
    print("\n" + "="*80)
    print("🎯 支撑/阻力位 (S/R Levels) 闭环验证报告")
    print("="*80)
    print(f"验证有效样本: {len(result_df)} 条")
    print(f"系统容错带  : ±{TOLERANCE*100}%")
    print("-" * 80)
    print("📉 支撑位 (Support) 表现:")
    print(f"  平均下方距离 : {avg_supp_dist:.2f}% (现价到支撑位的距离)")
    print(f"  实际被测试次 : {total_supp_tested} 次")
    if total_supp_tested > 0:
        print(f"  🟢 支撑有效率 : {supp_held_rate:.1f}% (撑住了没有大跌)")
        print(f"  🔴 破位失效占比: {supp_broken_rate:.1f}% (被强势击穿)")
        
    print("-" * 80)
    print("📈 阻力位 (Resistance) 表现:")
    print(f"  平均上方距离 : {avg_res_dist:.2f}% (现价到阻力位的距离)")
    print(f"  实际被测试次 : {total_res_tested} 次")
    if total_res_tested > 0:
        print(f"  🔴 阻力压制率 : {res_held_rate:.1f}% (碰到阻力就上不去了)")
        print(f"  🟢 强势突破率 : {res_broken_rate:.1f}% (突破阻力打开空间)")
    print("="*80)
    
    output_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/sr_validation_results.csv"
    result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"📊 详细分析矩阵已保存至: {output_path}")

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h']:
        print("使用方法:")
        print("  python validate_sr_levels.py <样本数>")
        print("  (提示: 传入 0 表示跑全量数据)")
        return
    
    try:
        sample_size = int(sys.argv[1])
        validate_support_resistance(sample_size)
    except ValueError:
        print("❌ 请输入正确的数字样本数")

if __name__ == "__main__":
    main()
