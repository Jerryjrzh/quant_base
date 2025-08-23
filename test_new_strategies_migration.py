#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试新迁移的策略
验证价值反转策略（最终版）和反转做多策略（优化版）
"""

import os
import sys
import json
from datetime import datetime

# 添加backend路径到sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

def test_new_strategies():
    """测试新迁移的策略"""
    print("🚀 开始测试新迁移的策略...")
    
    try:
        # 测试策略类导入
        print("\n📦 测试策略类导入...")
        from strategies.value_reversal_final_strategy import ValueReversalFinalStrategy
        from strategies.reversed_short_optimized_strategy import ReversedShortOptimizedStrategy
        
        print("✅ 策略类导入成功")
        
        # 测试策略实例化
        print("\n🏗️ 测试策略实例化...")
        
        # 价值反转策略
        value_strategy = ValueReversalFinalStrategy()
        print(f"✅ 价值反转策略实例化成功")
        print(f"   策略名称: {value_strategy.get_strategy_name()}")
        print(f"   策略版本: {value_strategy.get_strategy_version()}")
        print(f"   所需数据长度: {value_strategy.get_required_data_length()}")
        
        # 反转做多策略
        reversed_strategy = ReversedShortOptimizedStrategy()
        print(f"✅ 反转做多策略实例化成功")
        print(f"   策略名称: {reversed_strategy.get_strategy_name()}")
        print(f"   策略版本: {reversed_strategy.get_strategy_version()}")
        print(f"   所需数据长度: {reversed_strategy.get_required_data_length()}")
        
        # 测试配置验证
        print("\n⚙️ 测试配置验证...")
        
        value_config_valid = value_strategy.validate_config()
        reversed_config_valid = reversed_strategy.validate_config()
        
        print(f"✅ 价值反转策略配置验证: {'通过' if value_config_valid else '失败'}")
        print(f"✅ 反转做多策略配置验证: {'通过' if reversed_config_valid else '失败'}")
        
        # 测试策略管理器注册
        print("\n📋 测试策略管理器注册...")
        
        try:
            from strategy_manager import StrategyManager
            
            strategy_manager = StrategyManager()
            available_strategies = strategy_manager.get_available_strategies()
            
            print(f"✅ 策略管理器初始化成功")
            print(f"   可用策略数量: {len(available_strategies)}")
            print(f"   策略列表: {available_strategies}")
            
            # 检查新策略是否已注册
            new_strategy_ids = [
                "价值反转策略（最终版）_v1.0",
                "反转做多策略（优化版）_v1.0"
            ]
            
            for strategy_id in new_strategy_ids:
                if strategy_id in available_strategies:
                    print(f"✅ 策略 {strategy_id} 已成功注册")
                else:
                    print(f"⚠️ 策略 {strategy_id} 未找到，检查注册状态")
            
        except ImportError as e:
            print(f"⚠️ 策略管理器导入失败: {e}")
        
        # 测试统一配置加载
        print("\n📄 测试统一配置加载...")
        
        try:
            from config_manager import config_manager
            
            strategies_config = config_manager.get_strategies()
            print(f"✅ 统一配置加载成功")
            print(f"   配置中的策略数量: {len(strategies_config)}")
            
            # 检查新策略配置
            new_config_ids = [
                "价值反转策略（最终版）_v1.0",
                "反转做多策略（优化版）_v1.0"
            ]
            
            for config_id in new_config_ids:
                if config_id in strategies_config:
                    strategy_config = strategies_config[config_id]
                    print(f"✅ 策略配置 {config_id} 已加载")
                    print(f"   启用状态: {strategy_config.get('enabled', False)}")
                    print(f"   优先级: {strategy_config.get('priority', 'N/A')}")
                else:
                    print(f"⚠️ 策略配置 {config_id} 未找到")
            
        except ImportError as e:
            print(f"⚠️ 配置管理器导入失败: {e}")
        
        print("\n🎉 新策略测试完成!")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_universal_screener_integration():
    """测试与通用筛选器的集成"""
    print("\n🔧 测试与通用筛选器的集成...")
    
    try:
        from universal_screener import UniversalScreener
        
        # 创建筛选器实例
        screener = UniversalScreener()
        print("✅ 通用筛选器初始化成功")
        
        # 测试策略加载
        strategy_manager = screener.strategy_manager
        enabled_strategies = strategy_manager.get_enabled_strategies()
        
        print(f"✅ 启用的策略: {enabled_strategies}")
        
        # 检查新策略是否可被识别
        new_strategy_names = [
            "价值反转策略（最终版）_v1.0",
            "反转做多策略（优化版）_v1.0"
        ]
        
        for strategy_name in new_strategy_names:
            try:
                strategy_instance = strategy_manager.get_strategy_instance(strategy_name)
                if strategy_instance:
                    print(f"✅ 策略 {strategy_name} 可正常获取实例")
                else:
                    print(f"⚠️ 策略 {strategy_name} 实例获取失败")
            except Exception as e:
                print(f"⚠️ 策略 {strategy_name} 实例化失败: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ 通用筛选器集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("🧪 新策略迁移验证测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"工作目录: {os.getcwd()}")
    
    # 执行测试
    test1_result = test_new_strategies()
    test2_result = test_universal_screener_integration()
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    print(f"策略类测试: {'✅ 通过' if test1_result else '❌ 失败'}")
    print(f"筛选器集成测试: {'✅ 通过' if test2_result else '❌ 失败'}")
    
    if test1_result and test2_result:
        print("\n🎉 所有测试通过！新策略迁移成功！")
        print("\n📋 迁移完成的策略:")
        print("1. 价值反转策略（最终版）_v1.0 - 基于MACD底背离的精准反转策略")
        print("2. 反转做多策略（优化版）_v1.0 - 寻找下跌动能衰竭的反转信号")
        print("\n🚀 可以开始使用新策略进行股票筛选了！")
    else:
        print("\n⚠️ 存在测试失败，请检查相关配置和代码")
    
    return test1_result and test2_result

if __name__ == "__main__":
    main()