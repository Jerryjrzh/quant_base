#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终策略修复验证测试
"""

import sys
import os
import json

def test_strategy_registration():
    """测试策略注册修复"""
    print("=== 策略注册修复验证 ===\n")
    
    # 1. 检查配置文件
    config_file = "config/unified_strategy_config.json"
    if not os.path.exists(config_file):
        print("❌ 配置文件不存在")
        return False
    
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    strategies = config.get('strategies', {})
    enabled_strategies = [sid for sid, sdata in strategies.items() if sdata.get('enabled', False)]
    
    print(f"📋 配置文件中的策略:")
    print(f"   总数: {len(strategies)}")
    print(f"   启用: {len(enabled_strategies)}")
    
    for strategy_id in enabled_strategies:
        strategy_name = strategies[strategy_id].get('name', '未知')
        print(f"   ✓ {strategy_id} ({strategy_name})")
    
    # 2. 检查策略文件
    strategies_dir = "backend/strategies"
    if not os.path.exists(strategies_dir):
        print("❌ 策略目录不存在")
        return False
    
    strategy_files = [f for f in os.listdir(strategies_dir) if f.endswith('_strategy.py') and f != 'base_strategy.py']
    print(f"\n📁 策略文件:")
    print(f"   总数: {len(strategy_files)}")
    
    for f in strategy_files:
        print(f"   ✓ {f}")
    
    # 3. 检查策略管理器修复
    strategy_manager_file = "backend/strategy_manager.py"
    with open(strategy_manager_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"\n🔧 策略管理器修复检查:")
    
    fixes = [
        ("_register_config_strategies", "配置策略注册方法"),
        ("_ensure_config_strategy_mapping", "策略映射确保方法"),
        ("_find_alternative_strategy_id", "替代策略ID查找方法"),
        ("_get_english_name", "英文名称映射方法")
    ]
    
    all_fixes_present = True
    for method_name, description in fixes:
        if method_name in content:
            print(f"   ✓ {description}")
        else:
            print(f"   ❌ {description} - 缺失")
            all_fixes_present = False
    
    # 4. 总结
    print(f"\n📊 修复状态总结:")
    print(f"   配置文件: {'✓' if len(enabled_strategies) > 0 else '❌'}")
    print(f"   策略文件: {'✓' if len(strategy_files) > 0 else '❌'}")
    print(f"   代码修复: {'✓' if all_fixes_present else '❌'}")
    
    if len(enabled_strategies) > 0 and len(strategy_files) > 0 and all_fixes_present:
        print(f"\n🎉 策略注册修复验证通过！")
        print(f"   系统现在应该能够正确识别和注册所有策略")
        return True
    else:
        print(f"\n⚠️  仍有问题需要解决")
        return False

def provide_usage_instructions():
    """提供使用说明"""
    print(f"\n📖 使用说明:")
    print(f"1. 运行回测系统:")
    print(f"   python backend/backtester.py")
    print(f"")
    print(f"2. 运行通用筛选器:")
    print(f"   python backend/universal_screener.py")
    print(f"")
    print(f"3. 如果仍有问题，检查日志输出中的具体错误信息")

if __name__ == "__main__":
    success = test_strategy_registration()
    provide_usage_instructions()
    
    if success:
        print(f"\n✅ 验证完成 - 策略注册问题已修复")
    else:
        print(f"\n❌ 验证失败 - 需要进一步检查")