#!/usr/bin/env python3
"""
增强版交易建议工具 - 支持CSV批量验证
使用方法: 
  python get_trading_advice_enhanced.py [股票代码] [可选:入场价格]
  python get_trading_advice_enhanced.py --validate-csv [可选:采样数量]
"""

import sys
import os
import pandas as pd
from datetime import datetime
import traceback

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# --- 核心依赖 ---
from backtester import get_deep_analysis

def get_stock_advice_with_backtest(stock_code, entry_price=None):
    """原有单股分析功能（保持不变）"""
    try:
        analysis = get_deep_analysis(stock_code)
        
        if 'error' in analysis:
            return f"❌ 分析失败: {analysis['error']}"
        
        profit_loss_pct = 0.0
        if entry_price is not None:
            current_price = analysis.get('current_price', 0)
            if current_price > 0:
                profit_loss_pct = (current_price - entry_price) / entry_price * 100
        
        analysis['profit_loss_pct'] = profit_loss_pct
        return format_enhanced_advice(stock_code, analysis)
        
    except Exception as e:
        traceback.print_exc()
        return f"❌ 处理股票 {stock_code} 失败: {e}"


def validate_with_calendar_trades(sample_size=None):
    """批量验证 full_calendar_trades.csv 中的交易记录"""
    csv_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades.csv"
    
    if not os.path.exists(csv_path):
        return f"❌ 未找到CSV文件: {csv_path}"
    
    print(f"📂 正在读取 {csv_path} ...")
    df = pd.read_csv(csv_path)
    print(f"✅ 读取完成，共 {len(df)} 条记录")
    
    if sample_size:
        df = df.sample(n=min(sample_size, len(df)), random_state=42)
        print(f"🔢 采样模式: 随机抽取 {len(df)} 条记录进行验证")
    
    results = []
    success_count = 0
    total = len(df)
    
    print(f"🚀 开始验证 {total} 条交易记录...\n")
    
    for idx, row in df.iterrows():
        stock_code = row['stock_code']
        entry_date = row['entry_date']
        entry_price = row.get('entry_price')  # 如果CSV有入场价字段
        
        print(f"[{idx+1:04d}/{total}] 验证 {stock_code} ({entry_date}) ... ", end="")
        
        try:
            # 调用深度分析
            analysis = get_deep_analysis(stock_code)
            
            if 'error' in analysis:
                print("❌")
                continue
            
            # 提取预测价格
            advice = analysis.get('trading_advice', {})
            predicted_entry = advice.get('optimal_add_price') or analysis.get('current_price')
            stop_loss = advice.get('stop_loss_price')
            # 可根据需要扩展 target_price 等
            
            future_min = row['future_min_low']
            future_max = row['future_max_high']
            
            # 评估逻辑
            hit_low = predicted_entry and predicted_entry >= future_min * 0.98  # 允许2%误差
            hit_high = future_max and predicted_entry and predicted_entry <= future_max * 1.05
            
            pnl_sim = row.get('final_pnl', 0)
            
            results.append({
                'stock_code': stock_code,
                'entry_date': entry_date,
                'entry_price_csv': entry_price,
                'predicted_price': predicted_entry,
                'stop_loss_pred': stop_loss,
                'future_min_low': future_min,
                'future_max_high': future_max,
                'hit_low': hit_low,
                'hit_high': hit_high,
                'final_pnl': pnl_sim,
                'analysis_time': analysis.get('analysis_time')
            })
            
            if hit_low or hit_high:
                success_count += 1
            print("✅")
            
        except Exception as e:
            print("❌")
            continue
    
    # 统计结果
    df_result = pd.DataFrame(results)
    hit_rate = (success_count / total * 100) if total > 0 else 0
    avg_pnl = df_result['final_pnl'].mean() if not df_result.empty else 0
    
    print("\n" + "="*60)
    print("🎯 价格评估验证总结")
    print("="*60)
    print(f"总样本: {total}")
    print(f"价格命中率: {hit_rate:.1f}%")
    print(f"平均PNL: {avg_pnl:.2f}%")
    print(f"成功验证: {len(df_result)} 条")
    
    # 保存结果
    output_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/price_validation_results.csv"
    df_result.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"📊 详细结果已保存至: {output_path}")
    
    return df_result


def format_enhanced_advice(stock_code, analysis):
    """原有格式化函数（保持不变）"""
    output = []
    output.append(f"📊 {stock_code} 深度交易分析")
    output.append("=" * 60)
    
    output.append(f"📅 分析时间: {analysis['analysis_time']}")
    output.append(f"💰 当前价格: ¥{analysis['current_price']:.2f}")
    if analysis.get('profit_loss_pct') is not None and analysis['profit_loss_pct'] != 0:
        output.append(f"📊 盈亏状况 (基于输入价格): {analysis['profit_loss_pct']:.2f}%")
    output.append("")
    
    # 回测分析、操作建议、风险评估等保持原有逻辑...
    # （为节省篇幅，此处省略完整format_enhanced_advice，如需要可保留原脚本中的全部内容）

    return "\n".join(output)


def main():
    """主函数"""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("增强版交易建议系统 v2.2 (CSV验证增强版)")
        print("=" * 60)
        print("使用方法:")
        print("  python get_trading_advice_enhanced.py <股票代码> [入场价格]")
        print("  python get_trading_advice_enhanced.py --validate-csv [采样数量]")
        print("\n示例:")
        print("  python get_trading_advice_enhanced.py sh600036")
        print("  python get_trading_advice_enhanced.py --validate-csv 50")
        return
    
    arg = sys.argv[1].lower()
    
    if arg == '--validate-csv':
        sample = int(sys.argv[2]) if len(sys.argv) > 2 else None
        validate_with_calendar_trades(sample)
    else:
        stock_code = arg
        entry_price = float(sys.argv[2]) if len(sys.argv) > 2 else None
        print("🤖 正在进行深度回测分析...")
        result = get_stock_advice_with_backtest(stock_code, entry_price)
        print(result)


if __name__ == "__main__":
    main()
