#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复后的通用筛选器
"""

import sys
import os

# 添加backend目录到路径
sys.path.append('backend')

def test_imports():
    """测试导入"""
    print("🔍 测试导入...")
    
    try:
        import universal_screener
        print("✅ universal_screener 导入成功")
        
        from strategy_manager import StrategyManager
        print("✅ StrategyManager 导入成功")
        
        from strategies.base_strategy import BaseStrategy
        print("✅ BaseStrategy 导入成功")
        
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_strategy_manager():
    """测试策略管理器"""
    print("\n🔍 测试策略管理器...")
    
    try:
        from strategy_manager import StrategyManager
        manager = StrategyManager()
        
        strategies = manager.get_available_strategies()
        print(f"✅ 发现 {len(strategies)} 个策略")
        
        for strategy in strategies:
            print(f"  - {strategy['name']} v{strategy['version']}")
        
        return True
    except Exception as e:
        print(f"❌ 策略管理器测试失败: {e}")
        return False

def test_universal_screener_init():
    """测试通用筛选器初始化"""
    print("\n🔍 测试通用筛选器初始化...")
    
    try:
        import universal_screener
        screener = universal_screener.UniversalScreener()
        
        available_strategies = screener.get_available_strategies()
        print(f"✅ 筛选器初始化成功，发现 {len(available_strategies)} 个策略")
        
        return True
    except Exception as e:
        print(f"❌ 筛选器初始化失败: {e}")
        return False

def main():
    """主函数"""
    print("🚀 通用筛选器修复测试")
    print("=" * 50)
    
    success = True
    
    # 测试导入
    if not test_imports():
        success = False
    
    # 测试策略管理器
    if not test_strategy_manager():
        success = False
    
    # 测试筛选器初始化
    if not test_universal_screener_init():
        success = False
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 所有测试通过！修复成功！")
    else:
        print("❌ 部分测试失败，需要进一步修复")
    
    return success

if __name__ == '__main__':
    main()