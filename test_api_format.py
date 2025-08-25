#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试API返回格式
"""

import json

def test_api_format():
    """测试API返回的数据格式"""
    
    # 模拟策略结果
    class MockResult:
        def __init__(self):
            self.stock_code = "000001"
            self.date = "2025-08-25"
            self.signal_type = "BUY"
            self.signal_strength = 85
            self.current_price = 12.34
            self.strategy_name = "临界金叉_v1.0"
    
    # 模拟API处理逻辑
    results = [MockResult()]
    stocks = []
    stock_codes = []
    
    for result in results:
        # 确保所有字段都有有效值
        stock_data = {
            'stock_code': str(result.stock_code) if result.stock_code else '',
            'date': str(result.date) if result.date else '',
            'signal_type': str(result.signal_type) if result.signal_type else '',
            'signal_strength': int(result.signal_strength) if result.signal_strength is not None else 0,
            'current_price': float(result.current_price) if result.current_price is not None else 0.0,
            'strategy_name': str(result.strategy_name) if result.strategy_name else '',
            'price': float(result.current_price) if result.current_price is not None else 0.0
        }
        stocks.append(stock_data)
        if result.stock_code:
            stock_codes.append(result.stock_code)
    
    # 模拟API返回格式
    api_response = {
        'success': True,
        'strategy_id': 'PRE_CROSS',
        'mapped_strategy_id': '临界金叉_v1.0',
        'total_count': len(stocks),
        'data': stocks,
        'stocks': stocks
    }
    
    print("API返回格式测试:")
    print(json.dumps(api_response, indent=2, ensure_ascii=False))
    
    # 验证前端期望的字段
    print("\n前端验证:")
    print(f"success: {api_response.get('success')}")
    print(f"data存在: {'data' in api_response}")
    print(f"data类型: {type(api_response.get('data'))}")
    print(f"stocks数量: {len(api_response.get('data', []))}")
    
    if api_response.get('data'):
        first_stock = api_response['data'][0]
        print(f"第一只股票字段: {list(first_stock.keys())}")

if __name__ == "__main__":
    test_api_format()