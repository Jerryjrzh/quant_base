#!/usr/bin/env python3
"""
测试修复后的持仓扫描功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from portfolio_manager import PortfolioManager

def test_portfolio_scan():
    """测试持仓扫描功能"""
    try:
        # 创建持仓管理器
        portfolio_manager = PortfolioManager()
        
        # 测试单个持仓分析
        print("🔍 测试单个持仓分析...")
        analysis = portfolio_manager.analyze_position_deep(
            stock_code='sz300741',
            purchase_price=50.0,
            purchase_date='2024-01-01'
        )
        
        print(f"分析结果: {analysis}")
        
        # 检查必要的字段
        if 'error' in analysis:
            print(f"❌ 分析失败: {analysis['error']}")
            return False
            
        required_fields = ['risk_assessment', 'position_advice']
        for field in required_fields:
            if field not in analysis:
                print(f"❌ 缺少必要字段: {field}")
                return False
            else:
                print(f"✅ 字段 {field} 存在: {analysis[field]}")
        
        # 检查风险评估结构
        if 'risk_level' not in analysis['risk_assessment']:
            print("❌ 风险评估缺少 risk_level 字段")
            return False
        
        print(f"✅ 风险等级: {analysis['risk_assessment']['risk_level']}")
        print(f"✅ 交易建议: {analysis['position_advice'].get('action', 'N/A')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 开始测试持仓扫描修复...")
    success = test_portfolio_scan()
    
    if success:
        print("✅ 测试通过！持仓扫描功能已修复")
    else:
        print("❌ 测试失败，需要进一步调试")