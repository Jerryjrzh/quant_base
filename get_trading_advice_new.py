#!/usr/bin/env python3
"""
快速获取交易建议的工具 - 基于深度回测分析
使用方法: python get_trading_advice.py [股票代码]
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# 直接从 backtester 导入核心分析功能
from backtester import get_deep_analysis

# get_trading_advice.py

def format_advice(analysis: dict):
    """【已升级】格式化建议输出，以展示更详细的回测结果"""
    if 'error' in analysis:
        return f"❌ 分析失败: {analysis['error']}"

    output = []
    output.append(f"📊 {analysis['stock_code']} 深度交易分析")
    output.append("=" * 50)
    
    output.append(f"📅 分析时间: {analysis['analysis_time']}")
    output.append(f"💰 当前价格: ¥{analysis['current_price']:.2f}")
    output.append("")

    # --- 操作建议 (逻辑不变) ---
    advice = analysis['trading_advice']
    output.append("💡 操作建议:")
    output.append(f"   🎯 建议操作: {advice['action']}")
    output.append(f"   🔍 置信度: {advice['confidence']*100:.0f}%")
    if advice.get('optimal_add_price'):
        output.append(f"   📉 建议补仓价: ¥{advice['optimal_add_price']:.2f}")
    if advice.get('stop_loss_price'):
        output.append(f"   ⛔ 止损价参考: ¥{advice['stop_loss_price']:.2f}")
    if advice.get('reasons'):
        output.append("   📋 建议原因:")
        for reason in advice['reasons']:
            output.append(f"     • {reason}")
    output.append("")

    # --- 回测分析摘要 (核心修改) ---
    backtest = analysis['backtest_analysis']
    output.append("🔍 历史回测摘要 (基于MACD零轴策略):")
    if backtest.get('total_signals', 0) > 0:
        output.append(f"    signals: {backtest['total_signals']} 次")
        output.append(f"   胜率: {backtest['win_rate']}")
        output.append(f"   平均最大收益: {backtest['avg_max_profit']}")
        output.append(f"   平均最大回撤: {backtest['avg_max_drawdown']}")
        output.append(f"   盈利周期: {backtest['avg_days_to_peak']}")
    else:
        output.append("   (在历史数据中未发现有效的基准策略信号)")
    
    output.append("\n   --- 补仓系数优化 ---")
    if backtest.get('best_add_coefficient'):
        output.append(f"   🎯 最优补仓系数: {backtest['best_add_coefficient']} (评分: {backtest['best_add_score']:.2f})")
    else:
        output.append("   (未找到有效的补仓场景)")
    output.append("")

    return "\n".join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法: python get_trading_advice.py <股票代码>")
        print("示例: python get_trading_advice.py sh600006")
        return
    
    stock_code = sys.argv[1].lower()
    
    print("🤖 正在进行深度回测分析...")
    # 直接调用 backtester
    analysis_result = get_deep_analysis(stock_code)
    
    # 格式化并打印结果
    print(format_advice(analysis_result))

if __name__ == "__main__":
    main()