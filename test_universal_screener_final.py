#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终测试通用筛选器
"""

import sys
import os

# 添加backend目录到路径
sys.path.append('backend')

def test_final():
    """最终测试"""
    print("🚀 通用筛选器最终测试")
    print("=" * 50)
    
    success = True
    
    try:
        # 1. 测试导入
        print("1️⃣ 测试导入...")
        import universal_screener
        from strategy_manager import StrategyManager
        from strategies.base_strategy import BaseStrategy
        print("✅ 所有模块导入成功")
        
        # 2. 测试策略管理器
        print("\n2️⃣ 测试策略管理器...")
        manager = StrategyManager()
        registered_strategies = list(manager.registered_strategies.keys())
        print(f"✅ 策略管理器初始化成功，注册了 {len(registered_strategies)} 个策略")
        for strategy_id in registered_strategies:
            print(f"  - {strategy_id}")
        
        # 3. 测试通用筛选器初始化
        print("\n3️⃣ 测试通用筛选器初始化...")
        screener = universal_screener.UniversalScreener()
        available_strategies = screener.get_available_strategies()
        print(f"✅ 筛选器初始化成功，发现 {len(available_strategies)} 个策略")
        
        # 4. 测试策略实例创建
        print("\n4️⃣ 测试策略实例创建...")
        enabled_strategies = screener.strategy_manager.get_enabled_strategies()
        print(f"启用的策略: {enabled_strategies}")
        
        for strategy_id in enabled_strategies[:2]:  # 只测试前两个策略
            try:
                strategy_instance = screener.strategy_manager.get_strategy_instance(strategy_id)
                if strategy_instance:
                    print(f"✅ 策略实例创建成功: {strategy_id}")
                else:
                    print(f"❌ 策略实例创建失败: {strategy_id}")
                    success = False
            except Exception as e:
                print(f"❌ 策略实例创建异常 {strategy_id}: {e}")
                success = False
        
        # 5. 测试配置加载
        print("\n5️⃣ 测试配置...")
        config = screener.config
        print(f"✅ 配置加载成功，包含 {len(config)} 个配置项")
        
        print("\n" + "=" * 50)
        if success:
            print("🎉 所有测试通过！通用筛选器修复成功！")
        else:
            print("❌ 部分测试失败")
        
        return success
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    test_final()