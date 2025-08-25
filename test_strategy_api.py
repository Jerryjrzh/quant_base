#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试策略API返回格式
"""

import json
import sys
import os

# 添加backend路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_api_response_format():
    """测试API响应格式"""
    
    # 测试成功响应格式
    success_response = {
        'success': True,
        'strategy_id': 'PRE_CROSS',
        'mapped_strategy_id': '临界金叉_v1.0',
        'total_count': 2,
        'data': [
            {
                'stock_code': '000001',
                'date': '2025-08-25',
                'signal_type': 'BUY',
                'signal_strength': 85,
                'current_price': 12.34,
                'strategy_name': '临界金叉_v1.0',
                'price': 12.34,
                'name': '平安银行',
                'sector': '银行',
                'industry': '银行业',
                'market': '深圳A股'
            },
            {
                'stock_code': '600000',
                'date': '2025-08-25',
                'signal_type': 'BUY',
                'signal_strength': 78,
                'current_price': 8.56,
                'strategy_name': '临界金叉_v1.0',
                'price': 8.56,
                'name': '浦发银行',
                'sector': '银行',
                'industry': '银行业',
                'market': '上海A股'
            }
        ],
        'stocks': []  # 向后兼容字段
    }
    
    # 测试空结果响应格式
    empty_response = {
        'success': True,
        'strategy_id': 'PRE_CROSS',
        'mapped_strategy_id': '临界金叉_v1.0',
        'total_count': 0,
        'data': [],
        'stocks': [],
        'message': '策略 PRE_CROSS 今日无信号'
    }
    
    # 测试错误响应格式
    error_response = {
        'success': False,
        'error': '获取策略股票列表失败: 测试错误',
        'data': [],
        'stocks': [],
        'total_count': 0
    }
    
    print("=== API响应格式测试 ===\n")
    
    print("1. 成功响应格式:")
    print(json.dumps(success_response, indent=2, ensure_ascii=False))
    
    print("\n2. 空结果响应格式:")
    print(json.dumps(empty_response, indent=2, ensure_ascii=False))
    
    print("\n3. 错误响应格式:")
    print(json.dumps(error_response, indent=2, ensure_ascii=False))
    
    # 验证前端期望的字段
    print("\n=== 前端兼容性验证 ===")
    
    for i, (name, response) in enumerate([
        ("成功响应", success_response),
        ("空结果响应", empty_response),
        ("错误响应", error_response)
    ], 1):
        print(f"\n{i}. {name}:")
        print(f"   success字段: {response.get('success')}")
        print(f"   data字段存在: {'data' in response}")
        print(f"   data类型: {type(response.get('data'))}")
        print(f"   data是数组: {isinstance(response.get('data'), list)}")
        print(f"   stocks数量: {len(response.get('data', []))}")
        
        # 检查前端逻辑
        if response.get('success') and response.get('data') is not None:
            print(f"   ✅ 符合新API格式 (success=True, data存在)")
        elif isinstance(response, list):
            print(f"   ✅ 符合旧API格式 (直接数组)")
        else:
            print(f"   ❌ 不符合任何预期格式，会触发'返回数据格式不正确'错误")

if __name__ == "__main__":
    test_api_response_format()