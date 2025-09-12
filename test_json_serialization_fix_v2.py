#!/usr/bin/env python3
"""
测试JSON序列化修复 - 验证前后端接口一致性
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import numpy as np
import pandas as pd
from datetime import datetime
from backend.app import safe_jsonify
from backend.unified_analysis_service import get_or_run_analysis

def test_safe_jsonify():
    """测试safe_jsonify函数处理各种数据类型"""
    print("🧪 测试 safe_jsonify 函数...")
    
    # 创建包含各种numpy类型的测试数据
    test_data = {
        'numpy_bool': np.bool_(True),
        'numpy_int': np.int64(42),
        'numpy_float': np.float64(3.14),
        'pandas_timestamp': pd.Timestamp('2025-08-28'),
        'datetime_obj': datetime.now(),
        'nested_dict': {
            'inner_bool': np.bool_(False),
            'inner_array': [np.int32(1), np.float32(2.5), np.bool_(True)]
        },
        'regular_data': {
            'string': 'test',
            'int': 123,
            'float': 4.56,
            'bool': True
        }
    }
    
    try:
        # 使用Flask的测试上下文
        from flask import Flask
        app = Flask(__name__)
        
        with app.app_context():
            response = safe_jsonify(test_data)
            print("✅ safe_jsonify 成功处理所有数据类型")
            return True
    except Exception as e:
        print(f"❌ safe_jsonify 测试失败: {e}")
        return False

def test_unified_analysis_interface():
    """测试统一分析接口的JSON序列化"""
    print("\n🧪 测试统一分析接口...")
    
    test_stock = 'sh600006'
    test_strategy = 'MACD零轴启动_v1.0'
    
    try:
        # 调用统一分析服务
        result = get_or_run_analysis(test_stock, test_strategy)
        
        if not result.get('success'):
            print(f"❌ 统一分析失败: {result.get('error')}")
            return False
        
        print(f"✅ 统一分析成功: {test_stock}")
        
        # 测试数据是否包含numpy类型
        data = result.get('data', {})
        
        def check_numpy_types(obj, path=""):
            """递归检查对象中是否包含numpy类型"""
            numpy_types_found = []
            
            if isinstance(obj, dict):
                for k, v in obj.items():
                    numpy_types_found.extend(check_numpy_types(v, f"{path}.{k}"))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    numpy_types_found.extend(check_numpy_types(v, f"{path}[{i}]"))
            elif isinstance(obj, (np.bool_, np.integer, np.floating)):
                numpy_types_found.append(f"{path}: {type(obj).__name__}")
            elif isinstance(obj, pd.Timestamp):
                numpy_types_found.append(f"{path}: pd.Timestamp")
            
            return numpy_types_found
        
        numpy_types = check_numpy_types(data)
        if numpy_types:
            print(f"⚠️  发现numpy类型数据: {numpy_types[:5]}...")  # 只显示前5个
        else:
            print("✅ 数据中未发现numpy类型")
        
        # 测试Flask JSON序列化
        from flask import Flask
        app = Flask(__name__)
        
        with app.app_context():
            try:
                response = safe_jsonify(result)
                print("✅ Flask JSON序列化成功")
                return True
            except Exception as e:
                print(f"❌ Flask JSON序列化失败: {e}")
                return False
                
    except Exception as e:
        print(f"❌ 统一分析接口测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_confluence_scorer_data():
    """测试V4.1 Confluence Scorer返回的数据类型"""
    print("\n🧪 测试 Confluence Scorer 数据类型...")
    
    try:
        from backend.data_handler import get_full_data_with_indicators
        from backend.backtester import get_deep_analysis
        
        test_stock = 'sh600006'
        
        # 获取深度分析结果
        result = get_deep_analysis(test_stock)
        
        if 'error' in result:
            print(f"❌ 深度分析失败: {result['error']}")
            return False
        
        print("✅ 深度分析成功")
        
        # 检查trading_advice中的数据类型
        trading_advice = result.get('trading_advice', {})
        
        def find_problematic_types(obj, path=""):
            """查找可能导致JSON序列化问题的类型"""
            problems = []
            
            if isinstance(obj, dict):
                for k, v in obj.items():
                    problems.extend(find_problematic_types(v, f"{path}.{k}"))
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    problems.extend(find_problematic_types(v, f"{path}[{i}]"))
            elif isinstance(obj, (np.bool_, np.integer, np.floating)):
                problems.append(f"{path}: {type(obj).__name__} = {obj}")
            elif isinstance(obj, pd.Timestamp):
                problems.append(f"{path}: pd.Timestamp = {obj}")
            elif hasattr(obj, 'item') and callable(obj.item):
                problems.append(f"{path}: numpy scalar = {obj}")
            
            return problems
        
        problems = find_problematic_types(trading_advice)
        if problems:
            print(f"⚠️  发现可能有问题的数据类型:")
            for problem in problems[:10]:  # 只显示前10个
                print(f"   {problem}")
        else:
            print("✅ 未发现有问题的数据类型")
        
        return True
        
    except Exception as e:
        print(f"❌ Confluence Scorer 数据类型测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🚀 开始JSON序列化修复验证测试\n")
    
    tests = [
        test_safe_jsonify,
        test_unified_analysis_interface,
        test_confluence_scorer_data
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！JSON序列化修复成功。")
    else:
        print("⚠️  部分测试失败，需要进一步检查。")
    
    return passed == total

if __name__ == "__main__":
    main()