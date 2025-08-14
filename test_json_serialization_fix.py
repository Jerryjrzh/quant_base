#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试JSON序列化修复
"""

import sys
import os
import json
import numpy as np
import pandas as pd

# 添加backend目录到路径
sys.path.append('backend')

def test_numpy_encoder():
    """测试自定义JSON编码器"""
    print("🔍 测试自定义JSON编码器")
    print("=" * 50)
    
    try:
        from universal_screener import NumpyEncoder
        
        # 测试数据包含各种numpy类型
        test_data = {
            'int64_value': np.int64(123),
            'float64_value': np.float64(123.456),
            'array_value': np.array([1, 2, 3]),
            'timestamp_value': pd.Timestamp.now(),
            'series_value': pd.Series([1, 2, 3]),
            'normal_value': 'test_string',
            'nested_dict': {
                'nested_int64': np.int64(456),
                'nested_float64': np.float64(789.123)
            }
        }
        
        # 尝试序列化
        json_str = json.dumps(test_data, cls=NumpyEncoder, indent=2)
        print("✅ JSON序列化成功")
        
        # 尝试反序列化
        parsed_data = json.loads(json_str)
        print("✅ JSON反序列化成功")
        
        print(f"📄 序列化结果预览:")
        print(json_str[:200] + "..." if len(json_str) > 200 else json_str)
        
        return True
        
    except Exception as e:
        print(f"❌ JSON编码器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_strategy_result_serialization():
    """测试策略结果序列化"""
    print("\n🔍 测试策略结果序列化")
    print("=" * 50)
    
    try:
        from strategies.base_strategy import StrategyResult
        
        # 创建包含numpy数据的策略结果
        signal_details = {
            'stage_passed': np.int64(3),
            'confidence': np.float64(0.85),
            'indicators': {
                'ma5': np.float64(12.34),
                'ma20': np.float64(11.89),
                'volume': np.int64(1000000)
            },
            'price_array': np.array([10.1, 10.2, 10.3]),
            'timestamp': pd.Timestamp.now()
        }
        
        result = StrategyResult(
            stock_code='sh600000',
            strategy_name='测试策略',
            signal_type='BUY',
            signal_strength=3,
            date='2025-08-14',
            current_price=10.25,
            signal_details=signal_details
        )
        
        # 转换为字典
        result_dict = result.to_dict()
        print("✅ 策略结果转换为字典成功")
        
        # 尝试JSON序列化
        json_str = json.dumps(result_dict, indent=2)
        print("✅ 策略结果JSON序列化成功")
        
        # 验证数据类型
        parsed = json.loads(json_str)
        print(f"📊 序列化后的数据类型:")
        for key, value in parsed.items():
            print(f"  - {key}: {type(value).__name__}")
        
        return True
        
    except Exception as e:
        print(f"❌ 策略结果序列化测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("🚀 JSON序列化修复测试")
    print("=" * 50)
    
    success = True
    
    # 测试自定义编码器
    if not test_numpy_encoder():
        success = False
    
    # 测试策略结果序列化
    if not test_strategy_result_serialization():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 所有JSON序列化测试通过！")
    else:
        print("❌ 部分测试失败")
    
    return success

if __name__ == '__main__':
    main()