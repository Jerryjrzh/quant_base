#!/usr/bin/env python3
"""
测试MA13 v2.0策略注册

验证新的MA13增强策略是否被正确注册到策略管理器中
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.strategy_manager import strategy_manager
from backend.config_manager import config_manager

def test_strategy_registration():
    """测试策略注册"""
    print("=" * 60)
    print("测试MA13 v2.0策略注册")
    print("=" * 60)
    
    # 1. 检查已注册的策略
    print("\n1. 已注册的策略:")
    registered_strategies = strategy_manager.registered_strategies
    for strategy_id, strategy_class in registered_strategies.items():
        print(f"  - {strategy_id}: {strategy_class.__name__}")
    
    # 2. 检查配置文件中的策略
    print("\n2. 配置文件中的策略:")
    config_strategies = config_manager.get_strategies()
    for config_id, config_data in config_strategies.items():
        name = config_data.get('name', '')
        version = config_data.get('version', '')
        enabled = config_data.get('enabled', False)
        print(f"  - {config_id}: {name} v{version} ({'启用' if enabled else '禁用'})")
    
    # 3. 检查MA13 v2.0策略是否存在
    print("\n3. 检查MA13 v2.0策略:")
    target_strategy_id = "MA13强势回调_v2.0"
    
    if target_strategy_id in registered_strategies:
        print(f"  ✓ 策略已注册: {target_strategy_id}")
        
        # 尝试创建实例
        try:
            strategy_class = registered_strategies[target_strategy_id]
            instance = strategy_class()
            print(f"    - 策略名称: {instance.name}")
            print(f"    - 策略版本: {instance.version}")
            print(f"    - 策略描述: {instance.description}")
        except Exception as e:
            print(f"  ✗ 创建策略实例失败: {e}")
    else:
        print(f"  ✗ 策略未注册: {target_strategy_id}")
        
        # 检查是否有类似的策略
        similar_strategies = [sid for sid in registered_strategies.keys() if 'MA13' in sid]
        if similar_strategies:
            print(f"    发现类似策略: {similar_strategies}")
    
    # 4. 检查配置文件中的MA13 v2.0
    if target_strategy_id in config_strategies:
        print(f"  ✓ 配置文件中存在: {target_strategy_id}")
        config = config_strategies[target_strategy_id]
        print(f"    - 启用状态: {config.get('enabled', False)}")
        print(f"    - 优先级: {config.get('priority', 'N/A')}")
    else:
        print(f"  ✗ 配置文件中不存在: {target_strategy_id}")
    
    # 5. 测试策略管理器的获取方法
    print("\n4. 测试策略获取:")
    try:
        available_strategies = strategy_manager.get_available_strategies()
        print(f"  可用策略数量: {len(available_strategies)}")
        
        ma13_strategies = [s for s in available_strategies if 'MA13' in s.get('name', '')]
        if ma13_strategies:
            print("  MA13相关策略:")
            for strategy in ma13_strategies:
                print(f"    - {strategy.get('id')}: {strategy.get('name')} v{strategy.get('version')}")
        else:
            print("  未找到MA13相关策略")
            
    except Exception as e:
        print(f"  ✗ 获取可用策略失败: {e}")
    
    # 6. 测试策略实例获取
    print("\n5. 测试策略实例获取:")
    try:
        instance = strategy_manager.get_strategy_instance(target_strategy_id)
        if instance:
            print(f"  ✓ 成功获取策略实例: {target_strategy_id}")
            print(f"    - 类型: {type(instance).__name__}")
            print(f"    - 名称: {instance.name}")
        else:
            print(f"  ✗ 无法获取策略实例: {target_strategy_id}")
    except Exception as e:
        print(f"  ✗ 获取策略实例时出错: {e}")

def test_strategy_functionality():
    """测试策略功能"""
    print("\n" + "=" * 60)
    print("测试MA13 v2.0策略功能")
    print("=" * 60)
    
    target_strategy_id = "MA13强势回调_v2.0"
    
    try:
        # 获取策略实例
        instance = strategy_manager.get_strategy_instance(target_strategy_id)
        if not instance:
            print("  ✗ 无法获取策略实例，跳过功能测试")
            return
        
        print(f"  ✓ 策略实例获取成功")
        
        # 测试配置
        print(f"\n1. 测试默认配置:")
        default_config = instance.get_default_config()
        print(f"  - 配置项数量: {len(default_config)}")
        print(f"  - 包含增强筛选: {'enhanced_screening' in default_config}")
        
        # 测试数据长度要求
        print(f"\n2. 测试数据要求:")
        required_length = instance.get_required_data_length()
        print(f"  - 最小数据长度: {required_length}")
        
        # 测试配置验证
        print(f"\n3. 测试配置验证:")
        is_valid = instance.validate_config()
        print(f"  - 配置验证结果: {'通过' if is_valid else '失败'}")
        
        print(f"\n  ✓ 策略功能测试完成")
        
    except Exception as e:
        print(f"  ✗ 策略功能测试失败: {e}")

def main():
    """主函数"""
    print("MA13 v2.0策略注册测试")
    print(f"测试时间: {os.popen('date').read().strip()}")
    
    try:
        # 测试策略注册
        test_strategy_registration()
        
        # 测试策略功能
        test_strategy_functionality()
        
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n测试过程中出现异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()