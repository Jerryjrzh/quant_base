#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试API单策略功能
"""

import json

def simulate_api_call():
    """模拟API调用过程"""
    
    print("=== 模拟API调用测试 ===\n")
    
    # 模拟前端请求
    strategy_id = "STRONG_STOCK_MA13_PULLBACK"
    print(f"1. 前端请求策略: {strategy_id}")
    
    # 模拟后端映射
    strategy_mapping = {
        'PRE_CROSS': '临界金叉_v1.0',
        'TRIPLE_CROSS': '三重金叉_v1.0', 
        'MACD_ZERO_AXIS': 'MACD零轴启动_v1.0',
        'WEEKLY_GOLDEN_CROSS_MA': '周线金叉+日线MA_v1.0',
        'ABYSS_BOTTOMING': '深渊筑底策略_v2.0',
        'VALUE_REVERSAL': '价值反转策略（最终版）_v1.0',
        'REVERSED_SHORT': '反转做多策略（优化版）_v1.0',
        'ANNUAL_BOTTOM_OPPORTUNITY': '年度见底机会策略_v1.0',
        'ANNUAL_BOTTOM': '年度见底机会策略_v1.0',
        'STRONG_STOCK_MA13_PULLBACK': '强势股MA13回调策略_v1.0',
        'STRONG_PULLBACK': '强势股MA13回调策略_v1.0',
        'LONG_TERM_CONSOLIDATION_BREAKOUT': '长周期横盘突破策略_v1.0',
        'BREAKOUT': '长周期横盘突破策略_v1.0'
    }
    
    mapped_strategy_id = strategy_mapping.get(strategy_id, strategy_id)
    print(f"2. 后端映射结果: {strategy_id} -> {mapped_strategy_id}")
    
    # 模拟筛选器调用
    print(f"3. 调用筛选器: screener.run_screening(['{mapped_strategy_id}'])")
    
    # 模拟预期结果
    expected_strategies = [mapped_strategy_id]
    print(f"4. 预期只运行策略: {expected_strategies}")
    
    # 模拟API响应格式
    mock_results = [
        {
            'stock_code': '000001',
            'date': '2025-08-25',
            'signal_type': 'BUY',
            'signal_strength': 85,
            'current_price': 12.34,
            'strategy_name': mapped_strategy_id,
            'price': 12.34,
            'name': '平安银行',
            'sector': '银行',
            'industry': '银行业',
            'market': '深圳A股'
        }
    ]
    
    api_response = {
        'success': True,
        'strategy_id': strategy_id,
        'mapped_strategy_id': mapped_strategy_id,
        'total_count': len(mock_results),
        'data': mock_results,
        'stocks': mock_results
    }
    
    print(f"5. API响应格式:")
    print(json.dumps(api_response, indent=2, ensure_ascii=False))
    
    # 验证前端兼容性
    print(f"\n6. 前端兼容性验证:")
    print(f"   success: {api_response.get('success')}")
    print(f"   data存在: {'data' in api_response}")
    print(f"   data是数组: {isinstance(api_response.get('data'), list)}")
    print(f"   结果数量: {len(api_response.get('data', []))}")
    
    if api_response.get('success') and isinstance(api_response.get('data'), list):
        print("   ✅ 符合前端期望格式")
    else:
        print("   ❌ 不符合前端期望格式")

if __name__ == "__main__":
    simulate_api_call()