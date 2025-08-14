#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试统一配置系统
验证前后端配置加载和同步
"""

import os
import sys
import json
import logging
from pathlib import Path

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

from config_manager import config_manager
from strategy_manager import strategy_manager

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_config_loading():
    """测试配置加载"""
    print("🔧 测试配置加载...")
    
    # 测试配置管理器
    print(f"配置文件路径: {config_manager.config_path}")
    print(f"配置版本: {config_manager.config.get('version', 'unknown')}")
    
    # 测试策略加载
    strategies = config_manager.get_strategies()
    print(f"加载策略数量: {len(strategies)}")
    
    for strategy_id, strategy in strategies.items():
        print(f"  - {strategy_id}: {strategy.get('name', 'unknown')} v{strategy.get('version', '1.0')}")
        print(f"    启用状态: {strategy.get('enabled', True)}")
        print(f"    风险等级: {strategy.get('risk_level', 'unknown')}")
        
        # 测试兼容性映射
        legacy_mapping = config_manager.get_legacy_mapping(strategy_id)
        if legacy_mapping:
            print(f"    兼容映射: {legacy_mapping}")
    
    print("✅ 配置加载测试完成\n")


def test_strategy_manager_integration():
    """测试策略管理器集成"""
    print("🔧 测试策略管理器集成...")
    
    # 测试策略管理器
    print(f"注册策略数量: {len(strategy_manager.registered_strategies)}")
    print(f"启用策略数量: {len(strategy_manager.get_enabled_strategies())}")
    
    # 测试策略实例创建
    enabled_strategies = strategy_manager.get_enabled_strategies()
    for strategy_id in enabled_strategies[:2]:  # 只测试前两个
        print(f"测试策略实例: {strategy_id}")
        instance = strategy_manager.get_strategy_instance(strategy_id)
        if instance:
            print(f"  ✅ 实例创建成功: {instance.name}")
        else:
            print(f"  ❌ 实例创建失败")
    
    print("✅ 策略管理器集成测试完成\n")


def test_legacy_mapping():
    """测试兼容性映射"""
    print("🔧 测试兼容性映射...")
    
    # 测试旧ID到新ID的映射
    test_mappings = [
        'ABYSS_BOTTOMING',
        'PRE_CROSS',
        'TRIPLE_CROSS',
        'MACD_ZERO_AXIS',
        'WEEKLY_GOLDEN_CROSS_MA'
    ]
    
    for old_id in test_mappings:
        new_id = config_manager.find_strategy_by_old_id(old_id)
        if new_id:
            print(f"  {old_id} -> {new_id}")
            
            # 测试反向映射
            strategy = config_manager.get_strategy(new_id)
            if strategy:
                legacy_mapping = strategy.get('legacy_mapping', {})
                api_id = legacy_mapping.get('api_id', legacy_mapping.get('old_id'))
                print(f"    API调用ID: {api_id}")
        else:
            print(f"  ❌ 未找到映射: {old_id}")
    
    print("✅ 兼容性映射测试完成\n")


def test_config_modification():
    """测试配置修改"""
    print("🔧 测试配置修改...")
    
    # 测试启用/禁用策略
    strategies = list(config_manager.get_strategies().keys())
    if strategies:
        test_strategy = strategies[0]
        print(f"测试策略: {test_strategy}")
        
        # 获取原始状态
        original_enabled = config_manager.get_strategy(test_strategy).get('enabled', True)
        print(f"原始状态: {'启用' if original_enabled else '禁用'}")
        
        # 切换状态
        if original_enabled:
            config_manager.disable_strategy(test_strategy)
            print("已禁用策略")
        else:
            config_manager.enable_strategy(test_strategy)
            print("已启用策略")
        
        # 验证状态
        new_enabled = config_manager.get_strategy(test_strategy).get('enabled', True)
        print(f"新状态: {'启用' if new_enabled else '禁用'}")
        
        # 恢复原始状态
        if original_enabled:
            config_manager.enable_strategy(test_strategy)
        else:
            config_manager.disable_strategy(test_strategy)
        print("已恢复原始状态")
    
    print("✅ 配置修改测试完成\n")


def test_frontend_settings():
    """测试前端设置"""
    print("🔧 测试前端设置...")
    
    frontend_settings = config_manager.get_frontend_settings()
    print("前端设置:")
    for key, value in frontend_settings.items():
        print(f"  {key}: {value}")
    
    global_settings = config_manager.get_global_settings()
    print("全局设置:")
    for key, value in global_settings.items():
        print(f"  {key}: {value}")
    
    print("✅ 前端设置测试完成\n")


def test_config_validation():
    """测试配置验证"""
    print("🔧 测试配置验证...")
    
    errors = config_manager.validate_config()
    if errors:
        print("配置验证错误:")
        for error in errors:
            print(f"  ❌ {error}")
    else:
        print("✅ 配置验证通过")
    
    print("✅ 配置验证测试完成\n")


def main():
    """主测试函数"""
    print("🚀 开始统一配置系统测试\n")
    
    try:
        test_config_loading()
        test_strategy_manager_integration()
        test_legacy_mapping()
        test_config_modification()
        test_frontend_settings()
        test_config_validation()
        
        print("🎉 所有测试完成！")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()