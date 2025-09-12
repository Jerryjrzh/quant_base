#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一股票跟踪器测试脚本
"""

import sys
import os

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from unified_stock_tracker import UnifiedStockTracker
from config_loader import ConfigLoader

def test_config_loader():
    """测试配置加载器"""
    print("🧪 测试配置加载器...")
    
    config_loader = ConfigLoader()
    
    # 测试配置验证
    if config_loader.validate_config():
        print("✅ 配置文件验证通过")
    else:
        print("❌ 配置文件验证失败")
        return False
    
    # 测试获取等级列表
    grades = config_loader.list_available_grades()
    print(f"📋 可用等级: {grades}")
    
    # 测试获取A级标准
    try:
        a_criteria = config_loader.get_grade_criteria('A')
        print(f"✅ A级标准加载成功: {a_criteria.get('name')}")
        print(f"   规则数量: {len(a_criteria.get('rules', []))}")
    except Exception as e:
        print(f"❌ A级标准加载失败: {e}")
        return False
    
    return True

def test_unified_tracker():
    """测试统一跟踪器"""
    print("\n🧪 测试统一股票跟踪器...")
    
    try:
        # 加载配置
        config_loader = ConfigLoader()
        a_criteria = config_loader.get_grade_criteria('A')
        
        # 创建跟踪器
        tracker = UnifiedStockTracker('A', a_criteria)
        print("✅ 统一跟踪器创建成功")
        
        # 测试加载筛选结果（只加载，不运行完整分析）
        print("🔍 测试加载筛选结果...")
        all_results = tracker.load_all_screening_results()
        print(f"✅ 加载了 {len(all_results)} 条筛选记录")
        
        if len(all_results) > 0:
            # 测试去重
            print("🔄 测试去重功能...")
            deduplicated = tracker.remove_duplicate_stocks(all_results)
            print(f"✅ 去重后剩余 {len(deduplicated)} 条记录")
            
            # 测试分级筛选
            print("🏆 测试A级筛选...")
            a_stocks = tracker.filter_stocks_by_grade(deduplicated)
            print(f"✅ 筛选出 {len(a_stocks)} 只A级股票")
            
            if len(a_stocks) > 0:
                # 显示前几只股票的信息
                print("📊 前5只A级股票:")
                for i, stock in enumerate(a_stocks[:5], 1):
                    stock_code = stock.get('stock_code', 'N/A')
                    reason = stock.get('a_grade_reason', 'N/A')
                    source = stock.get('source_type', 'N/A')
                    print(f"  {i}. {stock_code} - {reason} (来源: {source})")
        else:
            print("⚠️ 未找到筛选结果文件，跳过后续测试")
        
        return True
        
    except Exception as e:
        print(f"❌ 统一跟踪器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_criteria_checking():
    """测试分级标准检查逻辑"""
    print("\n🧪 测试分级标准检查逻辑...")
    
    try:
        config_loader = ConfigLoader()
        a_criteria = config_loader.get_grade_criteria('A')
        tracker = UnifiedStockTracker('A', a_criteria)
        
        # 测试样本数据
        test_stocks = [
            {
                'stock_code': 'TEST001',
                'comprehensive_score': 85,
                'confidence_score': 0.9,
                'risk_level': '低',
                'source_type': 'test'
            },
            {
                'stock_code': 'TEST002',
                'comprehensive_score': 75,
                'confidence_score': 0.7,
                'risk_level': '中',
                'source_type': 'test'
            },
            {
                'stock_code': 'TEST003',
                'comprehensive_score': 50,
                'confidence_score': 0.5,
                'risk_level': '高',
                'source_type': 'test'
            }
        ]
        
        print("📋 测试股票分级:")
        for stock in test_stocks:
            is_grade, reason = tracker._check_criteria(stock)
            status = "✅ A级" if is_grade else "❌ 非A级"
            print(f"  {stock['stock_code']}: {status} - {reason if reason else '不符合标准'}")
        
        return True
        
    except Exception as e:
        print(f"❌ 分级标准检查测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始统一股票跟踪器测试")
    print("=" * 60)
    
    success_count = 0
    total_tests = 3
    
    # 测试配置加载器
    if test_config_loader():
        success_count += 1
    
    # 测试统一跟踪器
    if test_unified_tracker():
        success_count += 1
    
    # 测试分级标准检查
    if test_criteria_checking():
        success_count += 1
    
    print("\n" + "=" * 60)
    print(f"📊 测试结果: {success_count}/{total_tests} 通过")
    
    if success_count == total_tests:
        print("🎉 所有测试通过！统一股票跟踪器可以正常使用")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查配置和代码")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)