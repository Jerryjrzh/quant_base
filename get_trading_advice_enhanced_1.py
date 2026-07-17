#!/usr/bin/env python3
"""
增强版交易建议工具 v4.2 - 包含千人千面特征与时间风控体系
使用方法: python get_trading_advice_enhanced.py [股票代码] [可选:入场价格]
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backtester import get_deep_analysis

def get_stock_advice_with_backtest(stock_code, entry_price=None):
    """
    获取基于深度回测与自适应网格的股票交易建议。
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
    完美适配 V4.2 自适应多维特征与网格评估价。
    """
    output = []
    output.append(f"📊 {stock_code} 深度量化交易分析 (v4.2 引擎)")
    output.append("=" * 65)
    
    # ================= 基本信息 =================
    output.append(f"📅 分析时间: {analysis.get('analysis_time', 'N/A')}")
    output.append(f"💰 当前价格: ¥{analysis.get('current_price', 0):.2f}")
    if analysis.get('profit_loss_pct') is not None and analysis['profit_loss_pct'] != 0:
        output.append(f"📈 浮动盈亏 (基于输入价): {analysis['profit_loss_pct']:+.2f}%")
    output.append("")
    
    # ================= V4.2 核心操作建议 =================
    if 'trading_advice' in analysis and analysis['trading_advice']:
        advice = analysis['trading_advice']
        
        # 1. 提取 Alpha 多维位置特征标签
        output.append("🏷️ 位置与特征画像:")
        if 'feature_trend' in advice:
            output.append(f"   📈 趋势阶段: {advice.get('feature_trend', 'unknown').upper()}")
        if 'feature_pattern' in advice:
            output.append(f"   🧩 形态识别: {advice.get('feature_pattern', 'None')}")
        if 'feature_bias_tier' in advice:
            bias_val = advice.get('feature_bias_val', 0) * 100
            output.append(f"   📏 乖离率位置: {advice.get('feature_bias_tier', 'N/A')} ({bias_val:+.2f}%)")
        output.append("")

        # 2. 核心操作指令
        output.append("💡 核心操作建议:")
        grade = advice.get('quality_grade', 'N/A')
        output.append(f"   🎯 建议操作: {advice.get('action', 'N/A')} (评级: {grade})")
        output.append(f"   🔍 综合置信度: {advice.get('confidence', 0)*100:.0f}%")
        
        # 3. 动态网格评估价（强制输出，无论是否 AVOID）
        output.append("\n   📐 动态网格评估价 (推算基准，供博弈参考):")
        if advice.get('entry_price'):
            output.append(f"     📥 挂单伏击价: ¥{advice['entry_price']:.2f}")
        if advice.get('target_price'):
            output.append(f"     🎯 预期止盈价: ¥{advice['target_price']:.2f}")
        if advice.get('stop_price'):
            output.append(f"     ⛔ 极限止损价: ¥{advice['stop_price']:.2f}")
            
        if advice.get('support_level'):
            output.append(f"     🛡️ 技术支撑底: ¥{advice['support_level']:.2f}")
        if advice.get('resistance_level'):
            output.append(f"     🧱 技术阻力顶: ¥{advice['resistance_level']:.2f}")

        # 4. 时间与路径风控 (T+N)
        if 'time_stop_days' in advice:
            output.append("\n   ⏳ 时间与路径风控军规:")
            output.append(f"     ⏱️ 时间止损: 持仓 {advice['time_stop_days']} 个交易日未触及目标即强制清仓")
            output.append(f"     🛡️ 利润保护: 盈利触及 {advice.get('trailing_stop_trigger', 0)*100:.1f}% 后开启防回撤保护")

        # 5. 决策逻辑链条
        if advice.get('analysis_logic'):
            output.append("\n   📋 AI 决策逻辑链:")
            for reason in advice['analysis_logic']:
                output.append(f"     • {reason}")
        output.append("")

    # ================= 传统风险评估 (兼容保留) =================
    if 'risk_assessment' in analysis and analysis['risk_assessment']:
        risk = analysis['risk_assessment']
        output.append("⚠️ 宏观风险评估:")
        output.append(f"   📊 风险等级: {risk.get('risk_level', '未知')}")
        output.append(f"   📈 年化波动率: {risk.get('volatility', 0)*100:.1f}%")
        output.append(f"   📉 最大回撤: {risk.get('max_drawdown', 0)*100:.1f}%")

    return "\n".join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("增强版交易建议系统 v4.2 (自适应网格与时间风控版)")
        print("=" * 60)
        print("使用方法: python get_trading_advice_enhanced.py <股票代码> [已持仓成本价]")
        print("\n示例:")
        print("  python get_trading_advice_enhanced.py sh600036")
        print("  python get_trading_advice_enhanced.py sz000001 12.50")
        return
    
    stock_code = sys.argv[1].lower()
    entry_price = float(sys.argv[2]) if len(sys.argv) > 2 else None
    
    print(f"🤖 正在调用 V4.2 引擎对 {stock_code} 进行深度特征提取与网格计算...")
    result = get_stock_advice_with_backtest(stock_code, entry_price)
    print(result)

if __name__ == "__main__":
    main()
