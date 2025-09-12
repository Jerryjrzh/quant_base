#!/usr/bin/env python3
"""
增强版交易建议工具 - 基于深度回测分析
使用方法: python get_trading_advice_enhanced.py [股票代码] [可选:入场价格]
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# --- 核心修改：依赖从 portfolio_manager 切换到 backtester ---
from backtester import get_deep_analysis

def get_stock_advice_with_backtest(stock_code, entry_price=None):
    """
    【已重构】获取基于深度回测的股票交易建议。
    直接调用 backtester 作为核心分析引擎。
    """
    try:
        # 1. 直接调用 backtester 获取所有分析数据
        analysis = get_deep_analysis(stock_code)
        
        if 'error' in analysis:
            return f"❌ 分析失败: {analysis['error']}"
        
        # 2. 如果提供了入场价格，在脚本内部计算盈亏状况
        profit_loss_pct = 0.0
        if entry_price is not None:
            current_price = analysis.get('current_price', 0)
            if current_price > 0:
                profit_loss_pct = (current_price - entry_price) / entry_price * 100
        
        # 3. 将盈亏信息添加到分析结果中，传递给格式化函数
        analysis['profit_loss_pct'] = profit_loss_pct
        
        return format_enhanced_advice(stock_code, analysis)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 处理股票 {stock_code} 失败: {e}"

def format_enhanced_advice(stock_code, analysis):
    """
    格式化增强的建议输出。
    【已适配】现在使用 backtester.get_deep_analysis 的返回结构。
    """
    output = []
    output.append(f"📊 {stock_code} 深度交易分析")
    output.append("=" * 60)
    
    # 基本信息
    output.append(f"📅 分析时间: {analysis['analysis_time']}")
    output.append(f"💰 当前价格: ¥{analysis['current_price']:.2f}")
    if analysis.get('profit_loss_pct') is not None and analysis['profit_loss_pct'] != 0:
        output.append(f"📊 盈亏状况 (基于输入价格): {analysis['profit_loss_pct']:.2f}%")
    output.append("")
    
    # 回测分析结果
    if 'backtest_analysis' in analysis and analysis['backtest_analysis']:
        backtest = analysis['backtest_analysis']
        output.append("🔍 深度回测分析结果:")
        
        # 最优补仓系数
        if backtest.get('best_add_coefficient'):
            output.append(f"   🎯 最优补仓系数: {backtest['best_add_coefficient']} (评分: {backtest.get('best_add_score', 0):.2f})")
        
        # 最优卖出系数
        if backtest.get('best_sell_coefficient'):
            output.append(f"   🎯 最优卖出系数: {backtest['best_sell_coefficient']} (评分: {backtest.get('best_sell_score', 0):.2f})")
        
        # 补仓系数分析
        if 'add_coefficient_analysis' in backtest and backtest['add_coefficient_analysis']:
            output.append("\n   📈 补仓系数回测分析 (Top 3):")
            sorted_add = sorted(backtest['add_coefficient_analysis'].items(), key=lambda x: x[1].get('score', 0), reverse=True)
            for coeff, stats in sorted_add[:3]:
                output.append(f"     系数 {coeff}: 胜率 {stats['success_rate']:.1f}%, 均益 {stats['avg_return']:.2f}%, 评分 {stats['score']:.2f}")

        # 卖出系数分析
        if 'sell_coefficient_analysis' in backtest and backtest['sell_coefficient_analysis']:
            output.append("\n   📉 卖出系数回测分析 (Top 3):")
            sorted_sell = sorted(backtest['sell_coefficient_analysis'].items(), key=lambda x: x[1].get('score', 0), reverse=True)
            for coeff, stats in sorted_sell[:3]:
                output.append(f"     系数 {coeff}: 胜率 {stats['success_rate']:.1f}%, 均益 {stats['avg_return']:.2f}%, 均持 {stats['avg_hold_days']:.1f}天, 评分 {stats['score']:.2f}")

        output.append("")

    # 操作建议
    if 'trading_advice' in analysis and analysis['trading_advice']:
        advice = analysis['trading_advice']
        output.append("💡 操作建议:")
        output.append(f"   🎯 建议操作: {advice['action']}")
        output.append(f"   🔍 置信度: {advice['confidence']*100:.0f}%")
        
        if advice.get('optimal_add_price'):
            output.append(f"   📉 建议补仓价: ¥{advice['optimal_add_price']:.2f}")
        if advice.get('stop_loss_price'):
            output.append(f"   ⛔ 止损价: ¥{advice['stop_loss_price']:.2f}")
        
        if advice.get('reasons'):
            output.append("   📋 建议原因:")
            for reason in advice['reasons']:
                output.append(f"     • {reason}")
        output.append("")

    # 风险评估
    if 'risk_assessment' in analysis and analysis['risk_assessment']:
        risk = analysis['risk_assessment']
        output.append("⚠️ 风险评估:")
        output.append(f"   📊 风险等级: {risk.get('risk_level', '未知')}")
        output.append(f"   📈 年化波动率: {risk.get('volatility', 0)*100:.1f}%")
        output.append(f"   📉 最大回撤: {risk.get('max_drawdown', 0)*100:.1f}%")

    return "\n".join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("增强版交易建议系统 v2.1 (架构优化版)")
        print("=" * 50)
        print("使用方法: python get_trading_advice_enhanced.py <股票代码> [入场价格]")
        print("\n示例:")
        print("  python get_trading_advice_enhanced.py sh600036")
        print("  python get_trading_advice_enhanced.py sz000001 12.50")
        return
    
    stock_code = sys.argv[1].lower()
    entry_price = float(sys.argv[2]) if len(sys.argv) > 2 else None
    
    print("🤖 正在进行深度回测分析...")
    result = get_stock_advice_with_backtest(stock_code, entry_price)
    print(result)

if __name__ == "__main__":
    main()