#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试策略注册问题
"""

import sys
import os
import json

# 检查配置文件
config_file = "config/unified_strategy_config.json"
if os.path.exists(config_file):
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    print("=== 配置文件中的策略 ===")
    strategies = config.get('strategies', {})
    for strategy_id, strategy_config in strategies.items():
        enabled = strategy_config.get('enabled', False)
        name = strategy_config.get('name', '未知')
        print(f"  {strategy_id}: {name} ({'启用' if enabled else '禁用'})")
    
    print(f"\n总计: {len(strategies)} 个策略")
    enabled_count = sum(1 for s in strategies.values() if s.get('enabled', False))
    print(f"启用: {enabled_count} 个策略")
else:
    print("配置文件不存在")

# 检查策略文件
strategies_dir = "backend/strategies"
if os.path.exists(strategies_dir):
    print(f"\n=== 策略文件目录 ===")
    strategy_files = [f for f in os.listdir(strategies_dir) if f.endswith('_strategy.py')]
    for f in strategy_files:
        print(f"  - {f}")
    print(f"总计: {len(strategy_files)} 个策略文件")
else:
    print("策略目录不存在")

print("\n=== 问题分析 ===")
print("错误信息显示策略未注册，可能的原因：")
print("1. 策略ID不匹配（配置文件使用中文ID，代码生成英文ID）")
print("2. 策略类未正确继承BaseStrategy")
print("3. 策略文件导入失败")
print("4. 配置文件路径问题")

print("\n=== 建议解决方案 ===")
print("1. 统一策略ID格式")
print("2. 添加策略别名支持")
print("3. 改进错误处理和日志")