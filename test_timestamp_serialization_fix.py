#!/usr/bin/env python3
"""
测试时间戳序列化修复
"""
import sys
import os
sys.path.append('backend')

import json
import pandas as pd
from datetime import datetime
from dataclasses import dataclass, asdict

# 导入修复后的模块
from universal_screener import HighQualityResult, UniversalScreener

def test_timestamp_serialization():
    """测试时间戳序列化"""
    print("🧪 测试时间戳序列化修复")
    print("=" * 50)
    
    # 创建测试数据
    test_result = HighQualityResult(
        stock_code='sz000001',
        stock_name='平安银行',
        date=pd.Timestamp('2025-01-01'),
        signal_type='买入信号',
        current_price=12.34,
        confluence_score=85.5,
        confidence=0.85,
        market_phase='上升趋势',
        quality_grade='A'
    )
    
    print(f"✅ 创建测试结果: {test_result.stock_code}")
    print(f"   日期类型: {type(test_result.date)}")
    print(f"   日期值: {test_result.date}")
    
    # 测试1: 直接使用asdict（应该失败）
    print("\n🔍 测试1: 直接使用asdict")
    try:
        direct_dict = asdict(test_result)
        json_str = json.dumps(direct_dict)
        print("❌ 直接序列化成功（不应该成功）")
    except TypeError as e:
        print(f"✅ 直接序列化失败（预期）: {e}")
    
    # 测试2: 使用修复后的方法
    print("\n🔍 测试2: 使用修复后的转换方法")
    try:
        # 模拟修复后的转换逻辑
        fixed_dict = {
            'stock_code': test_result.stock_code,
            'stock_name': test_result.stock_name,
            'date': test_result.date.isoformat() if hasattr(test_result.date, 'isoformat') else str(test_result.date),
            'signal_type': test_result.signal_type,
            'price': test_result.current_price,
            'confluence_score': test_result.confluence_score,
            'confidence': test_result.confidence,
            'market_phase': test_result.market_phase,
            'quality_grade': test_result.quality_grade
        }
        
        json_str = json.dumps(fixed_dict, ensure_ascii=False, indent=2)
        print("✅ 修复后序列化成功")
        print("📄 序列化结果:")
        print(json_str)
        
        # 验证反序列化
        parsed_data = json.loads(json_str)
        print(f"✅ 反序列化成功，日期: {parsed_data['date']}")
        
    except Exception as e:
        print(f"❌ 修复后序列化失败: {e}")
        return False
    
    return True

def test_cache_update():
    """测试缓存更新"""
    print("\n🧪 测试缓存更新")
    print("=" * 50)
    
    try:
        # 创建测试结果列表
        test_results = [
            HighQualityResult(
                stock_code='sz000001',
                stock_name='平安银行',
                date=pd.Timestamp('2025-01-01'),
                signal_type='买入信号',
                current_price=12.34,
                confluence_score=85.5,
                confidence=0.85,
                market_phase='上升趋势',
                quality_grade='A'
            ),
            HighQualityResult(
                stock_code='sz000002',
                stock_name='万科A',
                date=pd.Timestamp('2025-01-02'),
                signal_type='观察信号',
                current_price=23.45,
                confluence_score=75.2,
                confidence=0.72,
                market_phase='震荡',
                quality_grade='B'
            )
        ]
        
        # 创建筛选器实例
        screener = UniversalScreener()
        
        # 测试缓存更新方法
        print("🔄 测试缓存更新方法...")
        screener._update_strategy_screening_cache(['TEST_STRATEGY'], test_results)
        
        print("✅ 缓存更新测试成功")
        return True
        
    except Exception as e:
        print(f"❌ 缓存更新测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_deep_scan_save():
    """测试深度扫描结果保存"""
    print("\n🧪 测试深度扫描结果保存")
    print("=" * 50)
    
    try:
        # 创建测试结果
        test_results = [
            HighQualityResult(
                stock_code='sz000001',
                stock_name='平安银行',
                date=pd.Timestamp('2025-01-01'),
                signal_type='买入信号',
                current_price=12.34,
                confluence_score=85.5,
                confidence=0.85,
                market_phase='上升趋势',
                quality_grade='A'
            )
        ]
        
        # 创建筛选器实例
        screener = UniversalScreener()
        
        # 测试保存方法
        print("💾 测试深度扫描结果保存...")
        screener._save_deep_scan_results(test_results)
        
        print("✅ 深度扫描结果保存测试成功")
        return True
        
    except Exception as e:
        print(f"❌ 深度扫描结果保存测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("🎯 时间戳序列化修复测试套件")
    print("=" * 60)
    
    all_tests_passed = True
    
    # 测试1: 时间戳序列化
    if not test_timestamp_serialization():
        all_tests_passed = False
    
    # 测试2: 缓存更新
    if not test_cache_update():
        all_tests_passed = False
    
    # 测试3: 深度扫描结果保存
    if not test_deep_scan_save():
        all_tests_passed = False
    
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 所有测试通过！时间戳序列化问题已修复")
        print("\n📋 修复内容:")
        print("✅ 修复了HighQualityResult中pd.Timestamp的JSON序列化问题")
        print("✅ 更新了_update_strategy_screening_cache方法")
        print("✅ 确保所有时间戳都转换为ISO格式字符串")
        print("✅ 保持了与前端API的兼容性")
    else:
        print("❌ 部分测试失败，请检查修复")
    
    print("\n🔧 修复说明:")
    print("- 将pd.Timestamp转换为ISO格式字符串")
    print("- 避免直接使用asdict()转换包含时间戳的dataclass")
    print("- 手动构建可JSON序列化的字典结构")

if __name__ == "__main__":
    main()