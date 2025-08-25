#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试单策略筛选功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_single_strategy_screening():
    """测试单策略筛选"""
    
    try:
        from universal_screener import UniversalScreener
        
        print("=== 测试单策略筛选功能 ===\n")
        
        # 创建筛选器实例
        screener = UniversalScreener()
        
        # 测试单个策略
        test_strategy = '强势股MA13回调策略_v1.0'
        print(f"测试策略: {test_strategy}")
        
        # 运行筛选
        print("开始筛选...")
        results = screener.run_screening([test_strategy])
        
        print(f"筛选结果数量: {len(results)}")
        
        if results:
            print("\n前5个结果:")
            for i, result in enumerate(results[:5]):
                print(f"  {i+1}. {result.stock_code} - {result.strategy_name} - {result.signal_type}")
        else:
            print("没有找到任何信号")
            
        # 验证结果中的策略名称
        unique_strategies = set(result.strategy_name for result in results)
        print(f"\n结果中包含的策略: {unique_strategies}")
        
        if len(unique_strategies) == 1 and test_strategy in unique_strategies:
            print("✅ 测试通过：只运行了指定的策略")
        else:
            print("❌ 测试失败：运行了多个策略或策略不匹配")
            
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_single_strategy_screening()