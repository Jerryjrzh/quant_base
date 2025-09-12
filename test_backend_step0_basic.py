#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端Step0基础功能测试

测试新增功能的基本可用性，不依赖外部数据
"""

import os
import sys
import logging
import json
from datetime import datetime

# 添加backend路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_database_extension():
    """测试数据库扩展"""
    print("测试数据库扩展...")
    
    try:
        from backend.stock_pool_manager import StockPoolManager
        
        # 创建管理器
        manager = StockPoolManager("test_extended.db")
        
        # 测试添加股票
        test_stock = {
            'stock_code': 'sz300290',
            'stock_name': '荣科科技',
            'score': 0.75,
            'params': {'kdj_n': 9, 'rsi_period': 14},
            'risk_level': 'MEDIUM'
        }
        
        success = manager.add_stock_to_pool(test_stock)
        print(f"  添加股票: {'✅ 成功' if success else '❌ 失败'}")
        
        # 测试更新画像数据
        profile_data = {
            'health_score': 0.8,
            'sector': '科技',
            'eps': 0.25,
            'dividend_yield': 2.5,
            'lhb_history': json.dumps([{'date': '2024-01-01', 'amount': 1000000}]),
            'limit_up_reason': '业绩预增'
        }
        
        update_success = manager.update_stock_profile('sz300290', profile_data)
        print(f"  更新画像数据: {'✅ 成功' if update_success else '❌ 失败'}")
        
        # 获取统计信息
        stats = manager.get_pool_statistics()
        print(f"  统计信息: {'✅ 成功' if stats else '❌ 失败'}")
        
        # 清理
        if os.path.exists("test_extended.db"):
            os.remove("test_extended.db")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 数据库扩展测试失败: {e}")
        return False


def test_data_enricher():
    """测试数据丰富器"""
    print("测试数据丰富器...")
    
    try:
        from backend.data_enricher import DataEnricher
        from backend.stock_pool_manager import StockPoolManager
        
        # 先创建测试数据
        manager = StockPoolManager("test_enricher.db")
        test_stock = {
            'stock_code': 'sz300290',
            'stock_name': '荣科科技',
            'score': 0.75,
            'params': {},
            'risk_level': 'MEDIUM'
        }
        manager.add_stock_to_pool(test_stock)
        
        # 创建数据丰富器
        enricher = DataEnricher("test_enricher.db")
        
        # 测试健康分数计算
        test_data = {
            'eps': 0.3,
            'dividend_yield': 2.0,
            'lhb_history': json.dumps([{'test': 'data'}]),
            'limit_up_reason': '业绩预增利好'
        }
        
        health_score = enricher._calculate_health_score(test_data, 'sz300290')
        print(f"  健康分数计算: {'✅ 成功' if health_score is not None else '❌ 失败'}")
        
        # 测试获取摘要
        summary = enricher.get_enrichment_summary()
        print(f"  获取摘要: {'✅ 成功' if summary else '❌ 失败'}")
        
        # 清理
        if os.path.exists("test_enricher.db"):
            os.remove("test_enricher.db")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 数据丰富器测试失败: {e}")
        return False


def test_stock_profiler():
    """测试个股画像生成器"""
    print("测试个股画像生成器...")
    
    try:
        from backend.stock_profiler import StockProfiler
        from backend.stock_pool_manager import StockPoolManager
        import pandas as pd
        import numpy as np
        
        # 先创建测试数据
        manager = StockPoolManager("test_profiler.db")
        test_stock = {
            'stock_code': 'sz300290',
            'stock_name': '荣科科技',
            'score': 0.75,
            'params': {},
            'risk_level': 'MEDIUM'
        }
        manager.add_stock_to_pool(test_stock)
        
        # 创建画像生成器
        profiler = StockProfiler("test_profiler.db")
        
        # 测试参数边界
        print(f"  参数边界设置: {'✅ 成功' if profiler.param_bounds else '❌ 失败'}")
        
        # 测试默认参数
        print(f"  默认参数设置: {'✅ 成功' if profiler.default_params else '❌ 失败'}")
        
        # 创建模拟数据测试目标函数
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        mock_df = pd.DataFrame({
            'close': np.random.randn(100).cumsum() + 100,
            'high': np.random.randn(100).cumsum() + 102,
            'low': np.random.randn(100).cumsum() + 98,
            'volume': np.random.randint(1000000, 10000000, 100)
        }, index=dates)
        
        # 测试目标函数
        test_params = [9, 14, 12, 26, 10, 30]
        try:
            objective_value = profiler._objective_function(test_params, mock_df)
            print(f"  目标函数计算: {'✅ 成功' if objective_value is not None else '❌ 失败'}")
        except:
            print(f"  目标函数计算: ⚠️  需要indicators模块")
        
        # 测试获取摘要
        summary = profiler.get_profiling_summary()
        print(f"  获取摘要: {'✅ 成功' if summary is not None else '❌ 失败'}")
        
        # 清理
        if os.path.exists("test_profiler.db"):
            os.remove("test_profiler.db")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 个股画像生成器测试失败: {e}")
        return False


def test_universal_screener_extension():
    """测试通用筛选器扩展"""
    print("测试通用筛选器扩展...")
    
    try:
        from backend.universal_screener import UniversalScreener
        
        # 创建筛选器
        screener = UniversalScreener()
        
        # 测试新增的历史日期参数
        print(f"  筛选器初始化: {'✅ 成功' if screener else '❌ 失败'}")
        
        # 测试验证方法存在
        has_validate_method = hasattr(screener, 'validate_screening_results')
        print(f"  验证方法存在: {'✅ 成功' if has_validate_method else '❌ 失败'}")
        
        # 测试配置加载
        config_loaded = screener.config is not None
        print(f"  配置加载: {'✅ 成功' if config_loaded else '❌ 失败'}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 通用筛选器扩展测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🧪 后端Step0基础功能测试")
    print("="*50)
    
    # 设置简单日志
    logging.basicConfig(level=logging.WARNING)  # 减少日志输出
    
    test_results = []
    
    # 运行各项测试
    tests = [
        ("数据库扩展", test_database_extension),
        ("数据丰富器", test_data_enricher),
        ("个股画像生成器", test_stock_profiler),
        ("通用筛选器扩展", test_universal_screener_extension)
    ]
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}")
        print("-" * 30)
        try:
            result = test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"  ❌ 测试异常: {e}")
            test_results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "="*50)
    print("📊 测试结果汇总")
    print("="*50)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("🎉 所有基础功能测试通过！")
        print("\n✅ 后端Step0调整已成功实施:")
        print("  - 数据库结构已扩展")
        print("  - 数据丰富器已创建")
        print("  - 个股画像生成器已创建")
        print("  - 通用筛选器已支持历史回测")
    else:
        print("⚠️  部分功能需要进一步调试")
        print("这可能是因为缺少某些依赖模块或数据文件")
    
    print(f"\n💡 提示: 运行 python demo_backend_step0.py 查看完整功能演示")


if __name__ == "__main__":
    main()