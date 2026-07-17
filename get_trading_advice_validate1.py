#!/usr/bin/env python3
"""
增强版交易建议工具 v2.4 - 历史时点回测验证
"""

import sys
import os
import pandas as pd
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backtester import get_deep_analysis

def validate_with_calendar_trades(sample_size=30):
    """优化版：基于真实限价单撮合逻辑的历史时点验证"""
    csv_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades.csv"
    
    try:
        df_csv = pd.read_csv(csv_path)
    except FileNotFoundError:
        print(f"❌ 找不到文件: {csv_path}")
        return None

    print(f"✅ 加载 {len(df_csv)} 条历史交易记录")
    
    if sample_size > 0:
        df_csv = df_csv.sample(n=min(sample_size, len(df_csv)), random_state=42)
    
    results = []
    entry_hits = 0  # 成功买入的次数
    target_hits = 0 # 成功止盈的次数
    
    print(f"\n🚀 开始 {len(df_csv)} 条历史时点严谨验证...\n")
    
    for idx, row in df_csv.iterrows():
        stock = row['stock_code']
        entry_date = row['entry_date']
        
        print(f"[{idx+1:04d}/{len(df_csv)}] {stock} @ {entry_date} ... ", end="")
        
        try:
            analysis = get_deep_analysis(stock_code=stock, analysis_date=entry_date)
            
            if 'error' in analysis:
                print("❌", analysis['error'][:50])
                continue
            
            advice = analysis.get('trading_advice', {})
            # 获取 V4 建议的三个核心价格
            predicted_entry = advice.get('entry_price')
            predicted_target = advice.get('target_price')
            predicted_stop = advice.get('stop_price')
            
            if not predicted_entry:
                predicted_entry = advice.get('current_price')
            
            future_min = row['future_min_low']
            future_max = row['future_max_high']
            
            # ==========================================
            # 优化 1: 真实的限价单买入撮合逻辑
            # 只要未来最低价触及或低于挂单价，就能成交
            # ==========================================
            entry_hit = (future_min <= predicted_entry <= future_max)
            
            # ==========================================
            # 优化 2 & 3: 动态 PNL 计算与止盈/止损评估
            # ==========================================
            recalculated_pnl = 0.0
            target_hit = False
            
            if entry_hit:
                entry_hits += 1
                # 粗略判定买入后的情况（因无逐日明细，基于最高/最低价做乐观/悲观推算）
                # 如果最高价摸到了目标价，视为成功止盈
                if predicted_target and future_max >= predicted_target:
                    target_hit = True
                    target_hits += 1
                    recalculated_pnl = (predicted_target - predicted_entry) / predicted_entry
                # 如果没触及目标价，但跌破了止损价，视为止损离场
                elif predicted_stop and future_min <= predicted_stop:
                    recalculated_pnl = (predicted_stop - predicted_entry) / predicted_entry
                # 既没止盈也没止损，按期末最高/最低的中间值粗略计算浮动盈亏
                else:
                    avg_future_price = (future_min + future_max) / 2
                    recalculated_pnl = (avg_future_price - predicted_entry) / predicted_entry
            else:
                # 没买进去，资金闲置，盈亏为0
                recalculated_pnl = 0.0

            results.append({
                'stock_code': stock,
                'entry_date': entry_date,
                'current_price': round(float(advice.get('current_price', 0)), 4),
                'pred_entry': round(float(predicted_entry), 4),
                'pred_target': round(float(predicted_target), 4) if predicted_target else None,
                'pred_stop': round(float(predicted_stop), 4) if predicted_stop else None,
                'future_min_low': future_min,
                'future_max_high': future_max,
                'entry_hit': entry_hit,
                'target_hit': target_hit,
                'recalculated_pnl': round(recalculated_pnl, 4),
                'original_csv_pnl': round(row.get('final_pnl', 0), 4),
                'action': advice.get('action', 'N/A')
            })
            
            # 输出状态：✅ 成功买入且止盈 | ⚠️ 买入了但没达到止盈 | 🛑 没买进去
            if entry_hit and target_hit:
                print("✅ (成交且止盈)")
            elif entry_hit:
                print(f"⚠️ (仅成交, PNL:{recalculated_pnl:.2%})")
            else:
                print("🛑 (未触发成交)")
            
        except Exception as e:
            print("❌ 抛出异常")
            traceback.print_exc()
            continue
    
    result_df = pd.DataFrame(results)
    
    # 统计数据
    valid_samples = len(result_df)
    entry_hit_rate = (entry_hits / valid_samples * 100) if valid_samples > 0 else 0
    
    # 只计算成功买入的交易的平均盈亏
    executed_trades = result_df[result_df['entry_hit'] == True]
    avg_recalc_pnl = executed_trades['recalculated_pnl'].mean() if not executed_trades.empty else 0
    
    print("\n" + "="*80)
    print("🎯 历史价格回测验证报告 (基于真实限价撮合)")
    print("="*80)
    print(f"验证总样本  : {valid_samples} 条")
    print(f"入场成交率  : {entry_hit_rate:.1f}% ({entry_hits}/{valid_samples})")
    
    if entry_hits > 0:
        target_hit_rate = (target_hits / entry_hits * 100)
        print(f"止盈触及率  : {target_hit_rate:.1f}% (基于已成交样本)")
        print(f"动态平均盈亏: {avg_recalc_pnl:.2%}")
    else:
        print("无成功买入的样本，无法计算胜率和盈亏。")
        
    print(f"原历史平均PNL: {result_df['original_csv_pnl'].mean():.2%}")
    
    output_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/price_validation_results_optimized.csv"
    result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"📊 详细结果已保存: {output_path}")
    
    return result_df

def validate_with_calendar_trades_0(sample_size=30):
    """历史时点价格验证"""
    csv_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades.csv"
    df_csv = pd.read_csv(csv_path)
    print(f"✅ 加载 {len(df_csv)} 条历史交易记录")
    
    if sample_size > 0:
        df_csv = df_csv.sample(n=min(sample_size, len(df_csv)), random_state=42)
    
    results = []
    hits = 0
    
    print(f"\n🚀 开始 {len(df_csv)} 条历史时点验证...\n")
    
    for idx, row in df_csv.iterrows():
        stock = row['stock_code']
        entry_date = row['entry_date']
        
        print(f"[{idx+1:04d}/{len(df_csv)}] {stock} @ {entry_date} ... ", end="")
        
        try:
            analysis = get_deep_analysis(stock_code=stock, analysis_date=entry_date)
            
            if 'error' in analysis:
                print("❌", analysis['error'][:50])
                continue
            
            advice = analysis.get('trading_advice', {})
            predicted_price = (advice.get('entry_price') or 
                             advice.get('current_price'))
            
            future_min = row['future_min_low']
            future_max = row['future_max_high']
            
            hit = (predicted_price >= future_min * 0.93 and 
                   predicted_price <= future_max * 1.10)
            
            if hit:
                hits += 1
            
            results.append({
                'stock_code': stock,
                'entry_date': entry_date,
                'predicted_price': round(float(predicted_price), 4),
                'future_min_low': future_min,
                'future_max_high': future_max,
                'price_hit': hit,
                'final_pnl': row.get('final_pnl', 0),
                'data_points': analysis.get('data_points', 0)
            })
            
            print("✅" if hit else "⚠️")
            
        except Exception as e:
            print("❌")
            continue
    
    result_df = pd.DataFrame(results)
    hit_rate = (hits / len(result_df) * 100) if len(result_df) > 0 else 0
    
    print("\n" + "="*80)
    print("🎯 历史价格验证报告")
    print("="*80)
    print(f"验证样本: {len(result_df)} 条")
    print(f"价格命中率: {hit_rate:.1f}%")
    print(f"平均实际PNL: {result_df['final_pnl'].mean():.2f}%")
    
    output_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/price_validation_results.csv"
    result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"📊 详细结果已保存: {output_path}")
    
    return result_df


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h']:
        print("使用方法:")
        print("  python get_trading_advice_enhanced.py <stock_code>")
        print("  python get_trading_advice_enhanced.py --validate-csv [样本数]")
        return
    
    if sys.argv[1] == '--validate-csv':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        validate_with_calendar_trades(n)
    else:
        stock = sys.argv[1].lower()
        analysis = get_deep_analysis(stock)
        print(analysis.get('trading_advice', {}))


if __name__ == "__main__":
    main()
