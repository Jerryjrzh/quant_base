#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略修复
"""

import sys
import os
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)

# 添加backend路径
sys.path.insert(0, 'backend')

def test_strategy_loading():
    """测试策略加载"""
    try:
        # 导入策略管理器
        from strategy_manager import StrategyManager
        
        print("=== 创建策略管理器 ===")
        manager = StrategyManager()
        
        print(f"已注册策略数量: {len(manager.registered_strategies)}")
        for strategy_id in manager.registered_strategies.keys():
            print(f"  - {strategy_id}")
        
        print("\n=== 测试启用的策略 ===")
        enabled_strategies = manager.get_enabled_strategies()
        print(f"启用策略数量: {len(enabled_strategies)}")
        
        for strategy_id in enabled_strategies:
            print(f"\n测试策略: {strategy_id}")
            instance = manager.get_strategy_instance(strategy_id)
            if instance:
                print(f"  ✅ 实例创建成功")
                print(f"  名称: {instance.name}")
                print(f"  版本: {instance.version}")
            else:
                print(f"  ❌ 实例创建失败")
        
        return True
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_strategy_loading()
    if success:
        print("\n✅ 策略加载测试通过")
    else:
        print("\n❌ 策略加载测试失败")