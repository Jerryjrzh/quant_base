#!/usr/bin/env python3
"""
多周期分析系统配置管理工具
提供命令行界面来管理系统配置
"""

import sys
import argparse
import json
from pathlib import Path

# 添加backend路径
sys.path.append('backend')

from multi_timeframe_config import MultiTimeframeConfig

def show_config_summary(config: MultiTimeframeConfig):
    """显示配置摘要"""
    print("\n" + "="*60)
    print("📊 多周期分析系统配置摘要")
    print("="*60)
    
    summary = config.get_config_summary()
    
    print(f"🔧 系统版本: {summary['system_version']}")
    print(f"📅 最后更新: {summary['last_updated']}")
    print(f"✅ 配置有效: {'是' if summary['config_valid'] else '否'}")
    
    print(f"\n📈 启用的时间周期 ({summary['enabled_timeframes']}/6):")
    for timeframe in summary['timeframe_list']:
        weight = config.get(f'timeframes.{timeframe}.weight')
        print(f"   • {timeframe}: 权重 {weight:.3f}")
    
    print(f"\n🎯 启用的策略 ({summary['enabled_strategies']}/4):")
    for strategy in summary['strategy_list']:
        weight = config.get(f'strategies.{strategy}.weight')
        print(f"   • {strategy}: 权重 {weight:.3f}")
    
    print(f"\n⚙️ 关键参数:")
    print(f"   • 置信度阈值: {summary['confidence_threshold']}")
    print(f"   • 最大仓位: {summary['max_position_size']:.1%}")
    print(f"   • 更新间隔: {summary['update_interval']}秒")
    
    # 检查配置错误
    errors = config.validate_config()
    if errors:
        print(f"\n❌ 配置错误:")
        for error in errors:
            print(f"   • {error}")

def show_timeframe_config(config: MultiTimeframeConfig):
    """显示时间周期配置"""
    print("\n" + "="*60)
    print("📈 时间周期配置")
    print("="*60)
    
    timeframes = config.config['timeframes']
    
    print(f"{'周期':<10} {'启用':<6} {'权重':<8} {'最小数据点':<10} {'颜色':<10}")
    print("-" * 50)
    
    for timeframe, tf_config in timeframes.items():
        enabled = "✅" if tf_config['enabled'] else "❌"
        weight = tf_config['weight']
        min_points = tf_config['min_data_points']
        color = tf_config['color']
        
        print(f"{timeframe:<10} {enabled:<6} {weight:<8.3f} {min_points:<10} {color:<10}")

def show_strategy_config(config: MultiTimeframeConfig):
    """显示策略配置"""
    print("\n" + "="*60)
    print("🎯 策略配置")
    print("="*60)
    
    strategies = config.config['strategies']
    
    for strategy, strategy_config in strategies.items():
        enabled = "✅" if strategy_config['enabled'] else "❌"
        weight = strategy_config['weight']
        
        print(f"\n{strategy} {enabled}")
        print(f"   权重: {weight:.3f}")
        print(f"   参数:")
        
        for param, value in strategy_config['parameters'].items():
            print(f"     • {param}: {value}")

def update_timeframe_weight(config: MultiTimeframeConfig, timeframe: str, weight: float):
    """更新时间周期权重"""
    if timeframe not in config.config['timeframes']:
        print(f"❌ 无效的时间周期: {timeframe}")
        return
    
    if not 0 <= weight <= 1:
        print(f"❌ 权重必须在0-1之间: {weight}")
        return
    
    config.update_timeframe_weight(timeframe, weight)
    print(f"✅ 已更新 {timeframe} 权重为 {weight:.3f}")

def update_strategy_weight(config: MultiTimeframeConfig, strategy: str, weight: float):
    """更新策略权重"""
    if strategy not in config.config['strategies']:
        print(f"❌ 无效的策略: {strategy}")
        return
    
    if not 0 <= weight <= 1:
        print(f"❌ 权重必须在0-1之间: {weight}")
        return
    
    config.update_strategy_weight(strategy, weight)
    print(f"✅ 已更新 {strategy} 权重为 {weight:.3f}")

def toggle_timeframe(config: MultiTimeframeConfig, timeframe: str, enable: bool):
    """切换时间周期启用状态"""
    if timeframe not in config.config['timeframes']:
        print(f"❌ 无效的时间周期: {timeframe}")
        return
    
    if enable:
        config.enable_timeframe(timeframe)
        print(f"✅ 已启用时间周期: {timeframe}")
    else:
        config.disable_timeframe(timeframe)
        print(f"❌ 已禁用时间周期: {timeframe}")

def toggle_strategy(config: MultiTimeframeConfig, strategy: str, enable: bool):
    """切换策略启用状态"""
    if strategy not in config.config['strategies']:
        print(f"❌ 无效的策略: {strategy}")
        return
    
    if enable:
        config.enable_strategy(strategy)
        print(f"✅ 已启用策略: {strategy}")
    else:
        config.disable_strategy(strategy)
        print(f"❌ 已禁用策略: {strategy}")

def set_config_value(config: MultiTimeframeConfig, key_path: str, value: str):
    """设置配置值"""
    try:
        # 尝试转换为数字
        if '.' in value:
            parsed_value = float(value)
        elif value.isdigit():
            parsed_value = int(value)
        elif value.lower() in ['true', 'false']:
            parsed_value = value.lower() == 'true'
        else:
            parsed_value = value
        
        config.set(key_path, parsed_value)
        print(f"✅ 已设置 {key_path} = {parsed_value}")
        
    except Exception as e:
        print(f"❌ 设置配置失败: {e}")

def validate_and_fix_config(config: MultiTimeframeConfig):
    """验证并修复配置"""
    print("\n" + "="*60)
    print("🔍 配置验证")
    print("="*60)
    
    errors = config.validate_config()
    
    if not errors:
        print("✅ 配置验证通过，无需修复")
        return
    
    print("❌ 发现配置错误:")
    for error in errors:
        print(f"   • {error}")
    
    print("\n🔧 尝试自动修复...")
    
    # 修复时间周期权重
    enabled_timeframes = config.get_enabled_timeframes()
    if enabled_timeframes:
        total_weight = sum(config.get(f'timeframes.{tf}.weight', 0) for tf in enabled_timeframes)
        if abs(total_weight - 1.0) > 0.01:
            # 重新分配权重
            equal_weight = 1.0 / len(enabled_timeframes)
            for tf in enabled_timeframes:
                config.update_timeframe_weight(tf, equal_weight)
            print(f"   ✅ 已重新分配时间周期权重 (每个 {equal_weight:.3f})")
    
    # 修复策略权重
    enabled_strategies = config.get_enabled_strategies()
    if enabled_strategies:
        total_weight = sum(config.get(f'strategies.{s}.weight', 0) for s in enabled_strategies)
        if abs(total_weight - 1.0) > 0.01:
            # 重新分配权重
            equal_weight = 1.0 / len(enabled_strategies)
            for strategy in enabled_strategies:
                config.update_strategy_weight(strategy, equal_weight)
            print(f"   ✅ 已重新分配策略权重 (每个 {equal_weight:.3f})")
    
    print("\n🔍 重新验证...")
    errors = config.validate_config()
    if not errors:
        print("✅ 配置修复成功")
    else:
        print("❌ 仍有配置错误需要手动修复")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='多周期分析系统配置管理工具')
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 显示配置摘要
    subparsers.add_parser('summary', help='显示配置摘要')
    
    # 显示时间周期配置
    subparsers.add_parser('timeframes', help='显示时间周期配置')
    
    # 显示策略配置
    subparsers.add_parser('strategies', help='显示策略配置')
    
    # 更新时间周期权重
    tf_weight_parser = subparsers.add_parser('set-tf-weight', help='更新时间周期权重')
    tf_weight_parser.add_argument('timeframe', help='时间周期 (5min, 15min, 30min, 1hour, 4hour, 1day)')
    tf_weight_parser.add_argument('weight', type=float, help='权重值 (0-1)')
    
    # 更新策略权重
    strategy_weight_parser = subparsers.add_parser('set-strategy-weight', help='更新策略权重')
    strategy_weight_parser.add_argument('strategy', help='策略名称')
    strategy_weight_parser.add_argument('weight', type=float, help='权重值 (0-1)')
    
    # 启用/禁用时间周期
    tf_toggle_parser = subparsers.add_parser('toggle-tf', help='启用/禁用时间周期')
    tf_toggle_parser.add_argument('timeframe', help='时间周期')
    tf_toggle_parser.add_argument('action', choices=['enable', 'disable'], help='操作')
    
    # 启用/禁用策略
    strategy_toggle_parser = subparsers.add_parser('toggle-strategy', help='启用/禁用策略')
    strategy_toggle_parser.add_argument('strategy', help='策略名称')
    strategy_toggle_parser.add_argument('action', choices=['enable', 'disable'], help='操作')
    
    # 设置配置值
    set_parser = subparsers.add_parser('set', help='设置配置值')
    set_parser.add_argument('key', help='配置键路径 (如: signal_processing.confidence_threshold)')
    set_parser.add_argument('value', help='配置值')
    
    # 验证配置
    subparsers.add_parser('validate', help='验证并修复配置')
    
    # 重置配置
    subparsers.add_parser('reset', help='重置为默认配置')
    
    # 导出配置
    export_parser = subparsers.add_parser('export', help='导出配置')
    export_parser.add_argument('path', help='导出路径')
    
    # 导入配置
    import_parser = subparsers.add_parser('import', help='导入配置')
    import_parser.add_argument('path', help='导入路径')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 初始化配置
    config = MultiTimeframeConfig()
    
    # 执行命令
    if args.command == 'summary':
        show_config_summary(config)
    
    elif args.command == 'timeframes':
        show_timeframe_config(config)
    
    elif args.command == 'strategies':
        show_strategy_config(config)
    
    elif args.command == 'set-tf-weight':
        update_timeframe_weight(config, args.timeframe, args.weight)
    
    elif args.command == 'set-strategy-weight':
        update_strategy_weight(config, args.strategy, args.weight)
    
    elif args.command == 'toggle-tf':
        toggle_timeframe(config, args.timeframe, args.action == 'enable')
    
    elif args.command == 'toggle-strategy':
        toggle_strategy(config, args.strategy, args.action == 'enable')
    
    elif args.command == 'set':
        set_config_value(config, args.key, args.value)
    
    elif args.command == 'validate':
        validate_and_fix_config(config)
    
    elif args.command == 'reset':
        confirm = input("⚠️ 确定要重置为默认配置吗？这将丢失所有自定义设置 (y/N): ")
        if confirm.lower() == 'y':
            config.reset_to_defaults()
            print("✅ 配置已重置为默认值")
        else:
            print("❌ 操作已取消")
    
    elif args.command == 'export':
        config.export_config(args.path)
    
    elif args.command == 'import':
        config.import_config(args.path)

if __name__ == "__main__":
    main()