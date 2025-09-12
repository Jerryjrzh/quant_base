#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用股票筛选器测试脚本
"""

import sys
import os

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_universal_screener_import():
    """测试通用筛选器导入"""
    print("🧪 测试通用筛选器导入...")
    
    try:
        from universal_screener import UniversalScreener, StrategyResult
        print("✅ 通用筛选器导入成功")
        return True
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 导入异常: {e}")
        return False

def test_strategy_manager():
    """测试策略管理器"""
    print("\n🧪 测试策略管理器...")
    
    try:
        from strategy_manager import strategy_manager
        
        # 获取可用策略
        available_strategies = strategy_manager.get_available_strategies()
        print(f"✅ 可用策略数量: {len(available_strategies)}")
        
        if available_strategies:
            print("📋 可用策略列表:")
            for strategy_id in available_strategies[:5]:  # 显示前5个
                print(f"   • {strategy_id}")
            if len(available_strategies) > 5:
                print(f"   ... 还有 {len(available_strategies) - 5} 个策略")
        
        return True
        
    except ImportError as e:
        print(f"❌ 策略管理器导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 策略管理器测试失败: {e}")
        return False

def test_stock_pool_manager():
    """测试股票池管理器"""
    print("\n🧪 测试股票池管理器...")
    
    try:
        from stock_pool_manager import StockPoolManager
        
        pool_manager = StockPoolManager()
        stocks = pool_manager.get_all_stocks()
        
        print(f"✅ 股票池加载成功，股票数量: {len(stocks)}")
        
        if stocks:
            print("📋 股票池示例:")
            for stock in stocks[:3]:  # 显示前3只股票
                stock_code = stock.get('stock_code', 'N/A')
                stock_name = stock.get('stock_name', 'N/A')
                print(f"   • {stock_code}: {stock_name}")
        
        return True
        
    except ImportError as e:
        print(f"❌ 股票池管理器导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 股票池管理器测试失败: {e}")
        return False

def test_universal_screener_basic():
    """测试通用筛选器基本功能"""
    print("\n🧪 测试通用筛选器基本功能...")
    
    try:
        from universal_screener import UniversalScreener
        
        # 创建筛选器实例
        screener = UniversalScreener()
        print("✅ 筛选器实例创建成功")
        
        # 检查股票池
        if hasattr(screener, 'stock_pool') and screener.stock_pool:
            print(f"✅ 股票池已加载: {len(screener.stock_pool)} 只股票")
        else:
            print("⚠️ 股票池为空或未加载")
        
        # 检查增强筛选器
        if hasattr(screener, 'enhanced_screener'):
            print("✅ 增强筛选器已初始化")
        else:
            print("⚠️ 增强筛选器未初始化")
        
        return True
        
    except Exception as e:
        print(f"❌ 通用筛选器基本功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dependencies():
    """测试依赖项"""
    print("\n🧪 测试依赖项...")
    
    dependencies = [
        ('data_handler', 'get_full_data_with_indicators'),
        ('strategy_manager', 'strategy_manager'),
        ('stock_pool_manager', 'StockPoolManager'),
    ]
    
    success_count = 0
    
    for module_name, item_name in dependencies:
        try:
            module = __import__(module_name)
            if hasattr(module, item_name):
                print(f"   ✅ {module_name}.{item_name}")
                success_count += 1
            else:
                print(f"   ❌ {module_name}.{item_name} 不存在")
        except ImportError:
            print(f"   ❌ {module_name} 导入失败")
        except Exception as e:
            print(f"   ❌ {module_name} 测试异常: {e}")
    
    # 测试可选依赖项
    optional_dependencies = [
        ('unified_analysis_service', 'get_or_run_analysis'),
        ('confluence_scorer', 'confluence_scorer'),
        ('pattern_recognizer', 'pattern_recognizer'),
        ('enhanced_screener', 'EnhancedScreener'),
        ('strategy_screening_cache', 'strategy_screening_cache'),
    ]
    
    print("\n   可选依赖项:")
    for module_name, item_name in optional_dependencies:
        try:
            module = __import__(module_name)
            if hasattr(module, item_name):
                print(f"   ✅ {module_name}.{item_name} (可选)")
            else:
                print(f"   ⚠️ {module_name}.{item_name} 不存在 (可选)")
        except ImportError:
            print(f"   ⚠️ {module_name} 导入失败 (可选)")
        except Exception as e:
            print(f"   ⚠️ {module_name} 测试异常: {e} (可选)")
    
    print(f"\n   核心依赖项: {success_count}/{len(dependencies)} 通过")
    return success_count >= len(dependencies) // 2  # 至少一半的依赖项可用

def main():
    """主测试函数"""
    print("🚀 开始通用股票筛选器测试")
    print("=" * 60)
    
    tests = [
        test_universal_screener_import,
        test_dependencies,
        test_strategy_manager,
        test_stock_pool_manager,
        test_universal_screener_basic,
    ]
    
    success_count = 0
    
    for test_func in tests:
        try:
            if test_func():
                success_count += 1
        except Exception as e:
            print(f"❌ 测试 {test_func.__name__} 异常: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 测试结果: {success_count}/{len(tests)} 通过")
    
    if success_count == len(tests):
        print("🎉 所有测试通过！通用筛选器可以正常使用")
        print("\n🚀 使用方法:")
        print("   python backend/universal_screener.py --help")
        print("   python backend/universal_screener.py --mode enhanced --min-grade B")
        return 0
    elif success_count >= len(tests) // 2:
        print("⚠️ 部分测试通过，筛选器可能可以使用，但建议检查失败的依赖项")
        print("\n🚀 尝试运行:")
        print("   python backend/universal_screener.py --help")
        return 0
    else:
        print("❌ 大部分测试失败，请检查依赖项和配置")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)