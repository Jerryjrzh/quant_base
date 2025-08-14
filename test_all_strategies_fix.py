#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试所有策略修复
验证策略注册和执行是否正常
"""

import os
import sys
import logging
import pandas as pd
from datetime import datetime

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

from config_manager import config_manager
from strategy_manager import strategy_manager
import data_loader

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_strategy_registration():
    """测试策略注册"""
    print("🔧 测试策略注册...")
    
    print(f"配置中的策略数量: {len(config_manager.get_strategies())}")
    print(f"注册的策略类数量: {len(strategy_manager.registered_strategies)}")
    
    print("\n配置中的策略:")
    for strategy_id, strategy in config_manager.get_strategies().items():
        print(f"  - {strategy_id}: {strategy.get('name', 'unknown')}")
    
    print("\n注册的策略类:")
    for strategy_id in strategy_manager.registered_strategies.keys():
        print(f"  - {strategy_id}")
    
    print("\n可用策略:")
    available = strategy_manager.get_available_strategies()
    for strategy in available:
        print(f"  - {strategy['id']}: {strategy['name']} v{strategy['version']} (启用: {strategy['enabled']})")
    
    print("✅ 策略注册测试完成\n")


def test_strategy_mapping():
    """测试策略映射"""
    print("🔧 测试策略映射...")
    
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
            
            # 测试策略实例创建
            instance = strategy_manager.get_strategy_instance(new_id)
            if instance:
                print(f"    ✅ 实例创建成功: {instance.name}")
            else:
                print(f"    ❌ 实例创建失败")
        else:
            print(f"  ❌ 未找到映射: {old_id}")
    
    print("✅ 策略映射测试完成\n")


def test_strategy_execution():
    """测试策略执行"""
    print("🔧 测试策略执行...")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    test_data = pd.DataFrame({
        'open': 10.0 + (pd.Series(range(100)) * 0.1),
        'high': 10.5 + (pd.Series(range(100)) * 0.1),
        'low': 9.5 + (pd.Series(range(100)) * 0.1),
        'close': 10.0 + (pd.Series(range(100)) * 0.1),
        'volume': 1000000
    }, index=dates)
    
    # 测试每个策略
    test_strategies = [
        ('PRE_CROSS', '临界金叉_v1.0'),
        ('TRIPLE_CROSS', '三重金叉_v1.0'),
        ('MACD_ZERO_AXIS', 'MACD零轴启动_v1.0'),
        ('WEEKLY_GOLDEN_CROSS_MA', '周线金叉+日线MA_v1.0')
    ]
    
    for old_id, new_id in test_strategies:
        print(f"测试策略: {old_id} -> {new_id}")
        
        try:
            instance = strategy_manager.get_strategy_instance(new_id)
            if instance:
                result = instance.apply_strategy(test_data)
                if result is not None:
                    # 处理返回的tuple (signals, details)
                    if isinstance(result, tuple) and len(result) == 2:
                        signals, details = result
                    else:
                        signals = result
                        details = None
                    
                    if signals is not None:
                        signal_count = (signals != '').sum() if hasattr(signals, 'sum') else sum(signals)
                        print(f"  ✅ 执行成功，信号数量: {signal_count}")
                    else:
                        print(f"  ❌ 执行失败，信号为None")
                else:
                    print(f"  ❌ 执行失败，返回None")
            else:
                print(f"  ❌ 策略实例未找到")
        except Exception as e:
            print(f"  ❌ 执行异常: {e}")
            import traceback
            traceback.print_exc()
    
    print("✅ 策略执行测试完成\n")


def test_real_data_execution():
    """使用真实数据测试策略执行"""
    print("🔧 使用真实数据测试策略执行...")
    
    # 尝试加载一个真实的股票数据文件
    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    test_files = [
        os.path.join(base_path, 'sh', 'lday', 'sh600000.day'),
        os.path.join(base_path, 'sz', 'lday', 'sz000001.day'),
        os.path.join(base_path, 'sh', 'lday', 'sh688001.day')
    ]
    
    test_file = None
    for file_path in test_files:
        if os.path.exists(file_path):
            test_file = file_path
            break
    
    if not test_file:
        print("  ⚠️ 未找到真实数据文件，跳过真实数据测试")
        return
    
    print(f"  使用数据文件: {test_file}")
    
    try:
        # 加载真实数据
        df = data_loader.get_daily_data(test_file)
        if df is None or len(df) < 100:
            print("  ⚠️ 数据加载失败或数据不足")
            return
        
        print(f"  数据长度: {len(df)} 天")
        
        # 测试深渊筑底策略（已注册的策略）
        abyss_instance = strategy_manager.get_strategy_instance('深渊筑底策略_v2.0')
        if abyss_instance:
            result = abyss_instance.apply_strategy(df)
            if result is not None:
                if isinstance(result, tuple) and len(result) == 2:
                    signals, details = result
                else:
                    signals = result
                    details = None
                
                if signals is not None:
                    signal_count = sum(signals)
                    print(f"  ✅ 深渊筑底策略执行成功，信号数量: {signal_count}")
                else:
                    print(f"  ❌ 深渊筑底策略执行失败，信号为None")
            else:
                print(f"  ❌ 深渊筑底策略执行失败，返回None")
        
        # 测试其他策略
        for strategy_id in ['临界金叉_v1.0', '三重金叉_v1.0']:
            if strategy_id in strategy_manager.registered_strategies:
                instance = strategy_manager.get_strategy_instance(strategy_id)
                if instance:
                    result = instance.apply_strategy(df)
                    if result is not None:
                        if isinstance(result, tuple) and len(result) == 2:
                            signals, details = result
                        else:
                            signals = result
                            details = None
                        
                        if signals is not None:
                            signal_count = (signals != '').sum() if hasattr(signals, 'sum') else sum(signals)
                            print(f"  ✅ {strategy_id} 执行成功，信号数量: {signal_count}")
                        else:
                            print(f"  ❌ {strategy_id} 执行失败，信号为None")
                    else:
                        print(f"  ❌ {strategy_id} 执行失败，返回None")
            else:
                print(f"  ⚠️ {strategy_id} 未注册")
        
    except Exception as e:
        print(f"  ❌ 真实数据测试失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("✅ 真实数据测试完成\n")


def main():
    """主测试函数"""
    print("🚀 开始策略修复测试\n")
    
    try:
        test_strategy_registration()
        test_strategy_mapping()
        test_strategy_execution()
        test_real_data_execution()
        
        print("🎉 所有测试完成！")
        
        # 输出最终状态
        print("\n=== 最终状态 ===")
        print(f"配置策略数量: {len(config_manager.get_strategies())}")
        print(f"注册策略数量: {len(strategy_manager.registered_strategies)}")
        print(f"可用策略数量: {len(strategy_manager.get_available_strategies())}")
        
        enabled_strategies = config_manager.get_enabled_strategies()
        print(f"启用策略数量: {len(enabled_strategies)}")
        
        print("\n启用的策略:")
        for strategy_id in enabled_strategies:
            strategy = config_manager.get_strategy(strategy_id)
            if strategy:
                print(f"  - {strategy_id}: {strategy.get('name', 'unknown')}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()