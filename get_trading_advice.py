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

def format_advice(analysis: dict):
    """格式化建议输出"""
    if 'error' in analysis:
        return f"❌ 分析失败: {analysis['error']}"

    output = []
    output.append(f"📊 {analysis['stock_code']} 深度交易分析")
    output.append("=" * 50)
    
    output.append(f"📅 分析时间: {analysis['analysis_time']}")
    output.append(f"💰 当前价格: ¥{analysis['current_price']:.2f}")
    output.append("")

    # 操作建议
    advice = analysis['trading_advice']
    output.append("💡 操作建议:")
    output.append(f"   🎯 建议操作: {advice['action']}")
    output.append(f"   🔍 置信度: {advice['confidence']*100:.0f}%")
    
    if advice.get('optimal_add_price'):
        output.append(f"   📉 建议补仓价 (基于历史最优系数): ¥{advice['optimal_add_price']:.2f}")
    else:
        output.append(f"   📉 建议补仓价: 暂无明确信号")
        
    if advice.get('stop_loss_price'):
        output.append(f"   ⛔ 止损价参考: ¥{advice['stop_loss_price']:.2f}")
    
    if advice.get('reasons'):
        output.append("   📋 建议原因:")
        for reason in advice['reasons']:
            output.append(f"     • {reason}")
    output.append("")

    # 回测分析摘要
    backtest = analysis['backtest_analysis']
    output.append("🔍 历史回测摘要:")
    if backtest.get('best_add_coefficient'):
        output.append(f"   🎯 历史最优补仓系数: {backtest['best_add_coefficient']} (综合评分: {backtest['best_add_score']:.2f})")
        output.append("   (注: 系数代表在支撑位价格上的乘数)")
    else:
        output.append("   🎯 历史最优补仓系数: 未找到有效策略")
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