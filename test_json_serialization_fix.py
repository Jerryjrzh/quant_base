#!/usr/bin/env python3
"""
测试JSON序列化修复
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from backend.unified_analysis_service import get_or_run_analysis

def test_json_serialization():
    """测试JSON序列化问题修复"""
    print("=" * 50)
    print("【JSON序列化修复测试】")
    print("=" * 50)
    
    test_stock = "000001"  # 平安银行
    
    try:
        print(f"测试股票: {test_stock}")
        result = get_or_run_analysis(test_stock, "macd_zero_axis_strategy")
        
        if result.get('success'):
            print("✅ 分析成功，JSON序列化问题已修复")
            data = result.get('data', {})
            print(f"   股票名称: {data.get('stock_name')}")
            print(f"   缓存状态: {'命中' if data.get('from_cache') else '实时计算'}")
            
            # 检查分析结构
            analysis = data.get('analysis', {})
            if 'deep_analysis' in analysis:
                print("   ✅ 深度分析数据正常")
            if 'historical_backtest' in analysis:
                print("   ✅ 历史回测数据正常")
            if 'chart_data' in data:
                print("   ✅ 图表数据正常")
                
        else:
            print(f"❌ 分析失败: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_json_serialization()