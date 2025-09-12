#!/usr/bin/env python3
"""
测试V4.2高性能通用筛选器
"""
import sys
import os
sys.path.append('backend')

from universal_screener import UniversalScreener
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_v42_screener():
    """测试V4.2高性能筛选器"""
    print("🧪 测试V4.2高性能通用筛选器")
    print("=" * 60)
    
    try:
        # 创建筛选器实例
        screener = UniversalScreener()
        print(f"✅ 筛选器初始化成功，股票池数量: {len(screener.stock_pool)}")
        
        # 测试策略列表
        strategy_ids = ['PRE_CROSS', 'MACD_ZERO_AXIS']
        print(f"📊 测试策略: {', '.join(strategy_ids)}")
        
        # 运行筛选（使用较少的工作进程进行测试）
        print("\n🚀 开始运行V4.2高性能筛选...")
        results = screener.run_screening(strategy_ids, max_workers=4)
        
        print(f"\n✅ 筛选完成！")
        print(f"📈 发现高质量信号: {len(results)} 个")
        
        if results:
            print("\n🏆 前10名股票:")
            for i, result in enumerate(results[:10], 1):
                print(f"  {i:2d}. {result.stock_code} ({result.stock_name})")
                print(f"      评分: {result.confluence_score:.1f}分 ({result.quality_grade}级)")
                print(f"      置信度: {result.confidence:.1%}")
                print(f"      市场阶段: {result.market_phase}")
                print(f"      信号类型: {result.signal_type}")
                print(f"      当前价格: ¥{result.current_price:.2f}")
                print()
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_structure():
    """测试数据结构"""
    print("\n🔍 测试数据结构...")
    
    try:
        from universal_screener import HighQualityResult
        import pandas as pd
        from datetime import datetime
        
        # 创建测试结果
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
        
        print(f"✅ 数据结构测试成功")
        print(f"   股票代码: {test_result.stock_code}")
        print(f"   评分: {test_result.confluence_score}")
        print(f"   等级: {test_result.quality_grade}")
        
        # 测试转换为字典
        from dataclasses import asdict
        result_dict = asdict(test_result)
        print(f"✅ 字典转换成功，包含 {len(result_dict)} 个字段")
        
        return True
        
    except Exception as e:
        print(f"❌ 数据结构测试失败: {e}")
        return False

def main():
    """主函数"""
    print("🎯 V4.2高性能通用筛选器测试套件")
    print("=" * 60)
    
    all_tests_passed = True
    
    # 测试1: 数据结构
    if not test_data_structure():
        all_tests_passed = False
    
    # 测试2: 筛选器功能
    if not test_v42_screener():
        all_tests_passed = False
    
    print("\n" + "=" * 60)
    if all_tests_passed:
        print("🎉 所有测试通过！V4.2筛选器工作正常")
        print("\n📋 主要改进:")
        print("✅ 统一并行化工作流，提升性能")
        print("✅ 集成V4.1深度评分系统")
        print("✅ 按分数自动排序结果")
        print("✅ 保存深度扫描结果供前端使用")
        print("✅ 优化缓存更新机制")
    else:
        print("❌ 部分测试失败，请检查配置")
    
    print("\n🔧 使用方法:")
    print("1. 后端API: POST /api/run_deep_scan")
    print("2. 前端按钮: 点击'深度扫描'按钮")
    print("3. 结果查看: GET /api/deep_scan_results")

if __name__ == "__main__":
    main()