#!/usr/bin/env python3
"""
增强版交易建议工具 - 基于深度回测分析（包含卖出价系数）
使用方法: python get_trading_advice_enhanced.py [股票代码] [入场价格]
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from datetime import datetime
from portfolio_manager import create_portfolio_manager

def get_stock_advice_with_backtest(stock_code, entry_price=None):
    """获取基于深度回测的股票交易建议（包含卖出价系数）"""
    
    try:
        # 使用持仓管理器进行深度分析
        portfolio_manager = create_portfolio_manager()
        
        # 获取股票数据
        df = portfolio_manager.get_stock_data(stock_code)
        if df is None:
            return f"❌ 无法获取股票 {stock_code} 的数据"
        
        # 计算技术指标
        df = portfolio_manager.calculate_technical_indicators(df, stock_code)
        
        current_price = float(df.iloc[-1]['close'])
        purchase_price = entry_price if entry_price else current_price
        purchase_date = datetime.now().strftime('%Y-%m-%d')
        
        # 执行深度分析（包含回测）
        analysis = portfolio_manager.analyze_position_deep(stock_code, purchase_price, purchase_date)
        
        if 'error' in analysis:
            return f"❌ 分析失败: {analysis['error']}"
        
        return format_enhanced_advice(stock_code, analysis)
        
    except Exception as e:
        return f"❌ 处理股票 {stock_code} 失败: {e}"

def format_enhanced_advice(stock_code, analysis):
    """格式化增强的建议输出（包含卖出价系数）"""
    output = []
    output.append(f"📊 {stock_code} 深度交易分析（含卖出价系数）")
    output.append("=" * 60)
    
    # 基本信息
    output.append(f"📅 分析时间: {analysis['analysis_time']}")
    output.append(f"💰 当前价格: ¥{analysis['current_price']:.2f}")
    output.append(f"📊 盈亏状况: {analysis['profit_loss_pct']:.2f}%")
    output.append("")
    
    # 回测分析结果
    if 'backtest_analysis' in analysis and 'error' not in analysis['backtest_analysis']:
        backtest = analysis['backtest_analysis']
        
        output.append("🔍 深度回测分析结果:")
        if backtest.get('from_cache'):
            output.append("   📋 数据来源: 缓存（7天内有效）")
        else:
            output.append("   📋 数据来源: 实时计算")
        
        # 最优补仓系数
        if backtest.get('best_add_coefficient'):
            output.append(f"   🎯 最优补仓系数: {backtest['best_add_coefficient']}")
            output.append(f"   📊 补仓综合评分: {backtest['best_add_score']:.2f}")
        
        # 最优卖出系数
        if backtest.get('best_sell_coefficient'):
            output.append(f"   🎯 最优卖出系数: {backtest['best_sell_coefficient']}")
            output.append(f"   📊 卖出综合评分: {backtest['best_sell_score']:.2f}")
        
        # 补仓系数分析（显示前3个最佳）
        if 'add_coefficient_analysis' in backtest:
            output.append("\n   📈 补仓系数回测分析:")
            sorted_add_coeffs = sorted(backtest['add_coefficient_analysis'].items(), 
                                     key=lambda x: x[1].get('score', 0), reverse=True)
            
            for coeff, stats in sorted_add_coeffs[:3]:  # 只显示前3个最佳
                output.append(f"     系数 {coeff}: 成功率 {stats['success_rate']:.1f}%, 平均收益 {stats['avg_return']:.2f}%, 评分 {stats['score']:.2f}")
        
        # 卖出系数分析（显示前3个最佳）
        if 'sell_coefficient_analysis' in backtest:
            output.append("\n   📉 卖出系数回测分析:")
            sorted_sell_coeffs = sorted(backtest['sell_coefficient_analysis'].items(), 
                                      key=lambda x: x[1].get('score', 0), reverse=True)
            
            for coeff, stats in sorted_sell_coeffs[:3]:  # 只显示前3个最佳
                output.append(f"     系数 {coeff}: 成功率 {stats['success_rate']:.1f}%, 平均收益 {stats['avg_return']:.2f}%, 平均持有 {stats['avg_hold_days']:.1f}天, 评分 {stats['score']:.2f}")
        
        output.append("")
    
    # 预测分析
    if 'backtest_analysis' in analysis and 'prediction' in analysis['backtest_analysis']:
        pred = analysis['backtest_analysis']['prediction']
        
        if 'error' not in pred:
            output.append("🔮 预测分析:")
            
            if pred.get('support_level'):
                output.append(f"   🔻 技术支撑位: ¥{pred['support_level']:.2f}")
            if pred.get('resistance_level'):
                output.append(f"   🔺 技术阻力位: ¥{pred['resistance_level']:.2f}")
            if pred.get('optimal_add_price'):
                output.append(f"   💡 最优补仓价: ¥{pred['optimal_add_price']:.2f}")
            if pred.get('optimal_sell_price'):
                output.append(f"   💰 基于阻力位的卖出价: ¥{pred['optimal_sell_price']:.2f}")
            if pred.get('current_sell_price'):
                output.append(f"   🎯 当前建议卖出价: ¥{pred['current_sell_price']:.2f}")
            
            if pred.get('current_to_sell_return') and pred['current_to_sell_return'] > 0:
                output.append(f"   📈 当前价到卖出价收益: {pred['current_to_sell_return']:.2f}%")
            
            if pred.get('expected_return') and pred['expected_return'] > 0:
                output.append(f"   📊 完整交易周期收益: {pred['expected_return']:.2f}%")
            elif pred.get('expected_return'):
                output.append(f"   📉 预期风险: {abs(pred['expected_return']):.2f}%")
            
            if pred.get('expected_days_to_peak'):
                output.append(f"   ⏰ 预期到顶天数: {pred['expected_days_to_peak']}天")
            
            confidence_text = {
                'high': '高',
                'medium': '中',
                'low': '低'
            }.get(pred.get('confidence_level', 'low'), '低')
            output.append(f"   🎯 预测置信度: {confidence_text}")
            
            output.append("")
    
    # 操作建议
    if 'position_advice' in analysis:
        advice = analysis['position_advice']
        output.append("💡 操作建议:")
        output.append(f"   🎯 建议操作: {advice['action']}")
        output.append(f"   🔍 置信度: {advice['confidence']*100:.0f}%")
        
        if advice.get('add_position_price'):
            output.append(f"   📉 建议补仓价: ¥{advice['add_position_price']:.2f}")
        
        if advice.get('sell_position_price'):
            output.append(f"   📈 建议卖出价: ¥{advice['sell_position_price']:.2f}")
        
        if advice.get('stop_loss_price'):
            output.append(f"   ⛔ 止损价: ¥{advice['stop_loss_price']:.2f}")
        
        if advice.get('reasons'):
            output.append("   📋 建议原因:")
            for reason in advice['reasons']:
                output.append(f"     • {reason}")
        
        output.append("")
    
    # 风险评估
    if 'risk_assessment' in analysis:
        risk = analysis['risk_assessment']
        output.append("⚠️ 风险评估:")
        output.append(f"   📊 风险等级: {risk['risk_level']}")
        output.append(f"   📈 波动率: {risk['volatility']:.1f}%")
        output.append(f"   📉 最大回撤: {risk['max_drawdown']:.1f}%")
        output.append("")
    
    # 技术分析摘要
    if 'technical_analysis' in analysis:
        tech = analysis['technical_analysis']
        if 'trend_analysis' in tech:
            trend = tech['trend_analysis']
            output.append("📊 技术分析:")
            output.append(f"   📈 价格位置: {trend.get('price_position', '未知')}")
            output.append(f"   💪 趋势强度: {trend.get('trend_strength', 0)*100:.0f}%")
            
            if 'ma_signals' in trend and trend['ma_signals']:
                output.append("   📊 均线信号:")
                for signal in trend['ma_signals'][:3]:  # 只显示前3个
                    output.append(f"     • {signal}")
            output.append("")
    
    # 交易策略建议
    output.append("🎯 交易策略建议:")
    if 'backtest_analysis' in analysis and 'prediction' in analysis['backtest_analysis']:
        pred = analysis['backtest_analysis']['prediction']
        if pred.get('optimal_add_price') and pred.get('current_sell_price'):
            add_price = pred['optimal_add_price']
            sell_price = pred['current_sell_price']
            potential_return = (sell_price - add_price) / add_price * 100
            
            output.append(f"   📊 完整交易策略:")
            output.append(f"     • 补仓价位: ¥{add_price:.2f}")
            output.append(f"     • 卖出价位: ¥{sell_price:.2f}")
            output.append(f"     • 预期收益: {potential_return:.2f}%")
            
            if pred.get('expected_days_to_peak'):
                output.append(f"     • 预期周期: {pred['expected_days_to_peak']}天")
    
    return "\n".join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("增强版交易建议系统 v2.0")
        print("=" * 50)
        print("使用方法:")
        print("  python get_trading_advice_enhanced.py <股票代码> [入场价格]")
        print("")
        print("示例:")
        print("  python get_trading_advice_enhanced.py sh000001")
        print("  python get_trading_advice_enhanced.py sz000001 12.50")
        print("")
        print("新功能:")
        print("  • 基于深度回测分析")
        print("  • 提供补仓和卖出价系数")
        print("  • 预期收益和到顶天数")
        print("  • 完整交易策略建议")
        print("  • 智能缓存机制，快速响应")
        print("")
        print("支持的股票代码格式:")
        print("  • 上海: sh000001, sh600036")
        print("  • 深圳: sz000001, sz000002")
        return
    
    stock_code = sys.argv[1].lower()
    entry_price = float(sys.argv[2]) if len(sys.argv) > 2 else None
    
    print("🤖 正在进行深度回测分析（含卖出价系数）...")
    result = get_stock_advice_with_backtest(stock_code, entry_price)
    print(result)

if __name__ == "__main__":
    main()