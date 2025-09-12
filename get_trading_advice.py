#!/usr/bin/env python3
"""
【已优化】增强版交易建议工具 - 现在使用统一分析服务以支持缓存
"""

import sys
import os
import json
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# --- 核心修改：依赖从 backtester 切换到 unified_analysis_service ---
from unified_analysis_service import get_or_run_analysis
from config_manager import config_manager

def get_stock_advice_from_service(stock_code, strategy_id='abyss_bottoming_v2.0'):
    """
    【已重构】通过统一服务获取股票交易建议，自动利用缓存。
    """
    try:
        # 1. 直接调用统一分析服务
        # 注意：命令行工具需要指定一个默认策略ID
        result = get_or_run_analysis(stock_code, strategy_id)
        
        if not result.get('success'):
            return f"❌ 分析失败: {result.get('error', '未知错误')}"
        
        # 2. 从返回的统一结构中提取所需信息
        analysis_data = result['data']['analysis']
        analysis_data['current_price'] = result['data']['analysis'].get('current_price', 0)
        analysis_data['analysis_time'] = result['data'].get('analysis_time', 'N/A')
        
        # 检查是否从缓存加载
        from_cache = result['data'].get('from_cache', False)
        
        return format_enhanced_advice(stock_code, analysis_data, from_cache)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 处理股票 {stock_code} 失败: {e}"

def format_enhanced_advice(stock_code, analysis, from_cache=False):
    """
    格式化增强的建议输出。
    """
    output = []
    cache_status = "⚡️ (来自缓存)" if from_cache else "💻 (实时计算)"
    output.append(f"📊 {stock_code} 深度交易分析 {cache_status}")
    output.append("=" * 60)
    
    output.append(f"📅 分析时间: {analysis['analysis_time']}")
    output.append(f"💰 当前价格: ¥{analysis['current_price']:.2f}")
    output.append("")

    # 操作建议 (合并基础版和增强版)
    advice = analysis.get('trading_advice', {})
    enhanced_advice = analysis.get('enhanced_trading_advice', {})
    
    # 优先使用增强版建议
    action = enhanced_advice.get('enhanced_action', advice.get('action', 'N/A'))
    confidence = enhanced_advice.get('confidence_score', advice.get('confidence', 0))
    
    output.append("💡 操作建议:")
    output.append(f"   🎯 建议操作: {action}")
    output.append(f"   🔍 置信度: {confidence*100:.0f}%")
    
    # ... (其他格式化逻辑保持不变或根据新结构微调) ...

    return "\n".join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        # ... (帮助信息不变) ...
        return
    
    stock_code = sys.argv[1].lower()
    
    print("🤖 正在通过统一服务获取分析...")
    result = get_stock_advice_from_service(stock_code)
    print(result)

if __name__ == "__main__":
    main()
