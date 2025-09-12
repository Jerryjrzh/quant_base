#!/usr/bin/env python3
"""
【最终优化版】增强版交易建议工具 - 使用统一分析服务并恢复完整输出
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from unified_analysis_service import get_or_run_analysis

def get_stock_advice_from_service(stock_code, entry_price=None, strategy_id='abyss_bottoming_v2.0'):
    """
    通过统一服务获取股票交易建议，自动利用缓存。
    """
    try:
        result = get_or_run_analysis(stock_code, strategy_id)
        
        if not result.get('success'):
            return f"❌ 分析失败: {result.get('error', '未知错误')}"
        
        data = result['data']
        
        profit_loss_pct = None
        if entry_price is not None:
            current_price = data['analysis'].get('current_price', 0)
            if current_price > 0:
                profit_loss_pct = (current_price - entry_price) / entry_price * 100
        
        return format_enhanced_advice(data, profit_loss_pct)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 处理股票 {stock_code} 失败: {e}"

def format_enhanced_advice(data, profit_loss_pct):
    """
    【已重构】格式化增强的建议输出，恢复所有缺失的详细信息。
    """
    stock_code = data['stock_code']
    analysis = data['analysis']
    from_cache = data.get('from_cache', False)
    
    output = []
    cache_status = "⚡️ (来自缓存)" if from_cache else "💻 (实时计算)"
    output.append(f"📊 {stock_code} 深度交易分析 {cache_status}")
    output.append("=" * 60)
    
    output.append(f"📅 分析时间: {data.get('analysis_time', 'N/A')}")
    output.append(f"💰 当前价格: ¥{analysis.get('current_price', 0):.2f}")
    if profit_loss_pct is not None:
        output.append(f"📊 盈亏状况 (基于输入价格): {profit_loss_pct:.2f}%")
    output.append("")
    
    # 深度回测分析结果
    backtest = analysis.get('backtest_analysis', {})
    if backtest:
        output.append("🔍 深度回测分析结果:")
        if backtest.get('best_add_coefficient'):
            output.append(f"   🎯 最优补仓系数: {backtest['best_add_coefficient']} (评分: {backtest.get('best_add_score', 0):.2f})")
        if backtest.get('best_sell_coefficient'):
            output.append(f"   🎯 最优卖出系数: {backtest['best_sell_coefficient']} (评分: {backtest.get('best_sell_score', 0):.2f})")
        
        add_analysis = backtest.get('add_coefficient_analysis', {})
        if add_analysis:
            output.append("\n   📈 补仓系数回测分析 (Top 3):")
            sorted_add = sorted(add_analysis.items(), key=lambda x: x[1].get('score', 0), reverse=True)
            for coeff, stats in sorted_add[:3]:
                output.append(f"     系数 {coeff}: 胜率 {stats.get('success_rate', 0):.1f}%, 均益 {stats.get('avg_return', 0):.2f}%, 评分 {stats.get('score', 0):.2f}")

        sell_analysis = backtest.get('sell_coefficient_analysis', {})
        if sell_analysis:
            output.append("\n   📉 卖出系数回测分析 (Top 3):")
            sorted_sell = sorted(sell_analysis.items(), key=lambda x: x[1].get('score', 0), reverse=True)
            for coeff, stats in sorted_sell[:3]:
                output.append(f"     系数 {coeff}: 胜率 {stats.get('success_rate', 0):.1f}%, 均益 {stats.get('avg_return', 0):.2f}%, 均持 {stats.get('avg_hold_days', 0):.1f}天, 评分 {stats.get('score', 0):.2f}")
        output.append("")

    # 操作建议
    advice = analysis.get('trading_advice', {})
    if advice:
        output.append("💡 操作建议:")
        output.append(f"   🎯 建议操作: {advice.get('action', 'N/A')}")
        output.append(f"   🔍 置信度: {advice.get('confidence', 0)*100:.0f}%")
        
        if advice.get('entry_price'):
            output.append(f"   📥 建议入场/补仓价: ¥{advice['entry_price']:.2f}")
        if advice.get('target_price'):
            output.append(f"   📤 建议目标卖出价: ¥{advice['target_price']:.2f}")
        if advice.get('stop_price'):
            output.append(f"   ⛔ 止损价: ¥{advice['stop_price']:.2f}")
        
        if advice.get('analysis_logic'):
            output.append("   📋 建议原因:")
            for reason in advice['analysis_logic']:
                output.append(f"     • {reason}")
        output.append("")

    # 风险评估
    risk = analysis.get('risk_assessment', {})
    if risk and 'error' not in risk:
        output.append("⚠️ 风险评估:")
        output.append(f"   📊 风险等级: {risk.get('risk_level', '未知')}")
        output.append(f"   📈 年化波动率: {risk.get('volatility', 0)*100:.1f}%")
        output.append(f"   📉 最大回撤: {risk.get('max_drawdown', 0)*100:.1f}%")

    return "\n".join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("增强版交易建议系统 v3.0 (统一服务版)")
        print("=" * 50)
        print("使用方法: python get_trading_advice_enhanced.py <股票代码> [你的入场价格]")
        print("\n示例:")
        print("  python get_trading_advice_enhanced.py sh600036")
        print("  python get_trading_advice_enhanced.py sz000001 12.50")
        return
    
    stock_code = sys.argv[1].lower()
    entry_price = float(sys.argv[2]) if len(sys.argv) > 2 else None
    
    print("🤖 正在通过统一服务获取分析...")
    result = get_stock_advice_from_service(stock_code, entry_price)
    print(result)

if __name__ == "__main__":
    main()
