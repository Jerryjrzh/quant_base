#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用股票筛选器演示脚本
展示如何使用正确的策略名称运行筛选器
"""

import sys
import os

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def demo_available_strategies():
    """演示获取可用策略"""
    print("🔍 获取可用策略列表...")
    
    try:
        from strategy_manager import strategy_manager
        
        available_strategies = strategy_manager.get_available_strategies()
        print(f"✅ 发现 {len(available_strategies)} 个可用策略:")
        
        for i, strategy_id in enumerate(available_strategies, 1):
            print(f"   {i:2d}. {strategy_id}")
        
        return available_strategies
        
    except Exception as e:
        print(f"❌ 获取策略列表失败: {e}")
        return []

def demo_universal_screener_basic():
    """演示基本筛选功能"""
    print("\n🚀 演示基本筛选功能...")
    
    try:
        from universal_screener import UniversalScreener
        
        # 使用正确的策略名称
        valid_strategies = ['深渊筑底策略_v2.0', 'MACD零轴启动_v1.0']
        
        print(f"📋 使用策略: {', '.join(valid_strategies)}")
        
        # 创建筛选器
        screener = UniversalScreener()
        
        # 运行筛选（使用较少的工作进程以避免资源问题）
        results = screener.run_screening(valid_strategies, max_workers=2)
        
        print(f"✅ 筛选完成，发现 {len(results)} 个信号")
        
        if results:
            print("\n📊 筛选结果示例 (前5个):")
            for i, result in enumerate(results[:5], 1):
                print(f"   {i}. {result.stock_code} ({result.stock_name})")
                print(f"      信号: {result.signal_type}")
                print(f"      日期: {result.date.strftime('%Y-%m-%d')}")
                print(f"      价格: ¥{result.current_price:.2f}")
                print()
        
        return True
        
    except Exception as e:
        print(f"❌ 基本筛选演示失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def demo_enhanced_screener():
    """演示增强筛选功能"""
    print("\n🌟 演示增强筛选功能...")
    
    try:
        from universal_screener import UniversalScreener
        
        # 使用正确的策略名称
        valid_strategies = ['深渊筑底策略_v2.0', '三重金叉_v1.0']
        
        print(f"📋 使用策略: {', '.join(valid_strategies)}")
        
        # 创建筛选器
        screener = UniversalScreener()
        
        # 运行增强筛选
        results = screener.run_enhanced_screening(
            strategy_ids=valid_strategies,
            max_workers=2,
            min_quality_grade='B'
        )
        
        print(f"✅ 增强筛选完成，发现 {len(results)} 个高质量信号")
        
        if results:
            # 获取质量统计
            quality_summary = screener.enhanced_screener.get_quality_summary(results)
            print(f"\n📈 质量统计:")
            print(f"   质量分布: {quality_summary.get('quality_distribution', {})}")
            print(f"   平均融合评分: {quality_summary.get('avg_confluence_score', 0):.1f}")
            print(f"   高质量比例: {quality_summary.get('high_quality_ratio', 0):.1f}%")
            
            print(f"\n📊 增强筛选结果示例 (前3个):")
            for i, result in enumerate(results[:3], 1):
                print(f"   {i}. {result.stock_code} ({result.stock_name})")
                print(f"      信号: {result.signal_type}")
                print(f"      质量等级: {getattr(result, 'quality_grade', 'N/A')}")
                print(f"      融合评分: {getattr(result, 'confluence_score', 0):.1f}")
                print(f"      日期: {result.date.strftime('%Y-%m-%d')}")
                print(f"      价格: ¥{result.current_price:.2f}")
                print()
        
        return True
        
    except Exception as e:
        print(f"❌ 增强筛选演示失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def demo_command_line_usage():
    """演示命令行使用方法"""
    print("\n📖 命令行使用方法:")
    print("=" * 50)
    
    print("1. 查看帮助:")
    print("   python backend/universal_screener.py --help")
    print()
    
    print("2. 使用默认策略运行:")
    print("   python backend/universal_screener.py")
    print()
    
    print("3. 指定策略运行:")
    print("   python backend/universal_screener.py -s 深渊筑底策略_v2.0 MACD零轴启动_v1.0")
    print()
    
    print("4. 运行增强筛选:")
    print("   python backend/universal_screener.py --mode enhanced --min-grade B")
    print()
    
    print("5. 对比两种筛选模式:")
    print("   python backend/universal_screener.py --mode compare")
    print()
    
    print("6. 保存结果到文件:")
    print("   python backend/universal_screener.py --output results.json")
    print()
    
    print("7. 调整工作进程数:")
    print("   python backend/universal_screener.py --workers 4")

def main():
    """主演示函数"""
    print("🚀 通用股票筛选器演示")
    print("=" * 60)
    
    # 1. 获取可用策略
    available_strategies = demo_available_strategies()
    
    if not available_strategies:
        print("❌ 无法获取策略列表，演示终止")
        return 1
    
    # 2. 演示基本筛选（可选，因为可能耗时较长）
    print("\n" + "=" * 60)
    user_input = input("是否运行基本筛选演示？(y/N): ").strip().lower()
    if user_input == 'y':
        demo_universal_screener_basic()
    else:
        print("⏭️ 跳过基本筛选演示")
    
    # 3. 演示增强筛选（可选）
    print("\n" + "=" * 60)
    user_input = input("是否运行增强筛选演示？(y/N): ").strip().lower()
    if user_input == 'y':
        demo_enhanced_screener()
    else:
        print("⏭️ 跳过增强筛选演示")
    
    # 4. 显示命令行使用方法
    demo_command_line_usage()
    
    print("\n" + "=" * 60)
    print("🎉 演示完成！")
    print("\n💡 提示:")
    print("   • 使用正确的策略名称很重要")
    print("   • 可以通过 strategy_manager.get_available_strategies() 获取最新的策略列表")
    print("   • 增强筛选提供更高质量的信号，但计算时间更长")
    print("   • 可以通过命令行参数灵活控制筛选行为")
    
    return 0

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)