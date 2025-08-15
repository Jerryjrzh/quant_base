#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略注册修复
"""

import sys
import os
sys.path.append('backend')

from strategy_manager import strategy_manager

def test_strategy_registration():
    """测试策略注册"""
    print("=== 策略注册测试 ===")
    
    # 获取已注册的策略
    registered = strategy_manager.registered_strategies
    print(f"已注册策略数量: {len(registered)}")
    
    for strategy_id in registered.keys():
        print(f"  - {strategy_id}")
    
    print("\n=== 配置文件中的策略 ===")
    config_strategies = strategy_manager.strategy_configs
    print(f"配置中策略数量: {len(config_strategies)}")
    
    for strategy_id in config_strategies.keys():
        print(f"  - {strategy_id}")
    
    print("\n=== 启用的策略 ===")
    enabled = strategy_manager.get_enabled_strategies()
    print(f"启用策略数量: {len(enabled)}")
    
    for strategy_id in enabled:
        print(f"  - {strategy_id}")
    
    print("\n=== 策略实例测试 ===")
    for strategy_id in enabled[:3]:  # 测试前3个
        instance = strategy_manager.get_strategy_instance(strategy_id)
        if instance:
            print(f"✅ {strategy_id}: 实例创建成功")
        else:
            print(f"❌ {strategy_id}: 实例创建失败")

if __name__ == "__main__":
    test_strategy_registration()