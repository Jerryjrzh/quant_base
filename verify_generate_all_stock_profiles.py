#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 generate_all_stock_profiles.py 脚本的功能

这个脚本验证：
1. 依赖模块导入
2. 数据库连接
3. 基本功能测试
4. 导出功能测试
"""

import sys
import os
import json
from datetime import datetime

def test_imports():
    """测试模块导入"""
    print("🔍 测试模块导入...")
    try:
        sys.path.append('backend')
        from stock_profiler import StockProfiler
        from stock_pool_manager import StockPoolManager
        from generate_all_stock_profiles import ProfileGenerationManager
        print("✅ 所有依赖模块导入成功")
        return True
    except Exception as e:
        print(f"❌ 模块导入失败: {e}")
        return False

def test_database_connection():
    """测试数据库连接"""
    print("\n🔍 测试数据库连接...")
    try:
        sys.path.append('backend')
        from stock_pool_manager import StockPoolManager
        
        pool_manager = StockPoolManager('stock_pool.db')
        all_stocks = pool_manager.get_all_stocks()
        core_stocks = pool_manager.get_core_pool()
        
        print(f"✅ 数据库连接成功")
        print(f"   总股票数: {len(all_stocks)}")
        print(f"   核心池股票数: {len(core_stocks)}")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return False

def test_profile_manager():
    """测试画像管理器"""
    print("\n🔍 测试画像管理器...")
    try:
        from generate_all_stock_profiles import ProfileGenerationManager
        
        manager = ProfileGenerationManager()
        summary = manager.get_generation_summary()
        
        print("✅ 画像管理器初始化成功")
        print(f"   画像覆盖率: {summary.get('profile_coverage', 0):.1f}%")
        print(f"   已有画像股票: {summary.get('profiled_stocks', 0)}")
        print(f"   平均验证分数: {summary.get('avg_validation_score', 0):.3f}")
        return True, manager
    except Exception as e:
        print(f"❌ 画像管理器测试失败: {e}")
        return False, None

def test_export_function(manager):
    """测试导出功能"""
    print("\n🔍 测试导出功能...")
    try:
        test_filename = f"test_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filename = manager.export_profiles_to_json(test_filename)
        
        # 验证文件是否创建
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"✅ 导出功能正常")
            print(f"   导出文件: {filename}")
            print(f"   导出股票数量: {len(data)}")
            
            # 清理测试文件
            os.remove(filename)
            return True
        else:
            print("❌ 导出文件未创建")
            return False
    except Exception as e:
        print(f"❌ 导出功能测试失败: {e}")
        return False

def test_batch_processing():
    """测试批处理逻辑"""
    print("\n🔍 测试批处理逻辑...")
    try:
        from generate_all_stock_profiles import ProfileGenerationManager
        
        manager = ProfileGenerationManager()
        
        # 模拟批处理（不实际执行优化）
        all_stocks = manager.pool_manager.get_all_stocks()
        
        # 检查已有画像和待生成画像的分类逻辑
        stocks_with_profiles = []
        stocks_without_profiles = []
        
        for stock in all_stocks:
            if stock.get('optimized_params'):
                stocks_with_profiles.append(stock)
            else:
                stocks_without_profiles.append(stock)
        
        print("✅ 批处理逻辑正常")
        print(f"   已有画像: {len(stocks_with_profiles)}")
        print(f"   待生成画像: {len(stocks_without_profiles)}")
        return True
    except Exception as e:
        print(f"❌ 批处理逻辑测试失败: {e}")
        return False

def main():
    """主验证函数"""
    print("🚀 开始验证 generate_all_stock_profiles.py")
    print("=" * 60)
    
    tests_passed = 0
    total_tests = 5
    
    # 测试1: 模块导入
    if test_imports():
        tests_passed += 1
    
    # 测试2: 数据库连接
    if test_database_connection():
        tests_passed += 1
    
    # 测试3: 画像管理器
    success, manager = test_profile_manager()
    if success:
        tests_passed += 1
        
        # 测试4: 导出功能
        if test_export_function(manager):
            tests_passed += 1
    else:
        print("\n⏭️  跳过导出功能测试（画像管理器初始化失败）")
    
    # 测试5: 批处理逻辑
    if test_batch_processing():
        tests_passed += 1
    
    # 总结
    print("\n" + "=" * 60)
    print(f"📊 验证结果: {tests_passed}/{total_tests} 项测试通过")
    
    if tests_passed == total_tests:
        print("🎉 所有测试通过！generate_all_stock_profiles.py 脚本功能正常")
        return True
    else:
        print("⚠️  部分测试失败，请检查相关功能")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)