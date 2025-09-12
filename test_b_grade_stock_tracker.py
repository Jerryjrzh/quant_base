#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
B级股票跟踪器测试脚本
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from b_grade_stock_tracker import BGradeStockTracker

def test_b_grade_tracker():
    """测试B级股票跟踪器"""
    print("🧪 开始测试B级股票跟踪器...")
    
    try:
        # 创建跟踪器实例
        tracker = BGradeStockTracker()
        
        # 运行完整分析
        result = tracker.run_full_analysis()
        
        print("\n✅ 测试完成!")
        print(f"📊 分析结果摘要:")
        print(f"  - 总加载记录: {result['total_loaded']}")
        print(f"  - 去重后记录: {result['after_deduplication']}")
        print(f"  - B级股票数量: {result['b_grade_count']}")
        print(f"  - 报告文件: {result['report_file']}")
        if result['excel_file']:
            print(f"  - Excel文件: {result['excel_file']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_b_grade_criteria():
    """测试B级筛选标准"""
    print("\n🔍 测试B级筛选标准...")
    
    tracker = BGradeStockTracker()
    
    # 测试样本数据
    test_stocks = [
        {
            'stock_code': 'sh600000',
            'confidence_score': 0.75,
            'risk_level': '中',
            'source_type': 'rsi_bottom'
        },
        {
            'stock_code': 'sz000001',
            'signal_strength': 2,
            'source_type': 'universal_screening'
        },
        {
            'stock_code': 'sh600036',
            'comprehensive_score': 70,
            'source_type': 'general_screening'
        },
        {
            'stock_code': 'sz000002',
            'confidence_score': 0.90,  # 太高，应该是A级
            'risk_level': '低',
            'source_type': 'rsi_bottom'
        },
        {
            'stock_code': 'sh600519',
            'confidence_score': 0.50,  # 太低，不应该入选
            'risk_level': '高',
            'source_type': 'rsi_bottom'
        }
    ]
    
    # 筛选B级股票
    b_grade_stocks = tracker.filter_b_grade_stocks(test_stocks)
    
    print(f"📊 测试结果:")
    print(f"  - 输入股票: {len(test_stocks)}只")
    print(f"  - B级股票: {len(b_grade_stocks)}只")
    
    for stock in b_grade_stocks:
        print(f"  - {stock['stock_code']}: {stock.get('b_grade_reason', 'N/A')}")
    
    # 预期结果：前3只应该被选中，后2只不应该被选中
    expected_b_grade = 3
    if len(b_grade_stocks) == expected_b_grade:
        print("✅ B级筛选标准测试通过")
        return True
    else:
        print(f"❌ B级筛选标准测试失败，期望{expected_b_grade}只，实际{len(b_grade_stocks)}只")
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("B级股票跟踪器测试")
    print("=" * 60)
    
    # 测试筛选标准
    criteria_test = test_b_grade_criteria()
    
    # 测试完整流程
    full_test = test_b_grade_tracker()
    
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    print(f"筛选标准测试: {'✅ 通过' if criteria_test else '❌ 失败'}")
    print(f"完整流程测试: {'✅ 通过' if full_test else '❌ 失败'}")
    
    if criteria_test and full_test:
        print("🎉 所有测试通过!")
        return True
    else:
        print("⚠️ 部分测试失败，请检查代码")
        return False

if __name__ == "__main__":
    main()