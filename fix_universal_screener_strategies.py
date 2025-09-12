#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复通用筛选器策略名称问题
显示正确的策略名称并提供使用指南
"""

import sys
import os

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def get_available_strategies():
    """获取可用策略列表"""
    try:
        from strategy_manager import strategy_manager
        return strategy_manager.get_available_strategies()
    except Exception as e:
        print(f"❌ 获取策略列表失败: {e}")
        return []

def show_strategy_mapping():
    """显示策略名称映射"""
    print("📋 策略名称映射表:")
    print("-" * 60)
    
    # 常见的错误策略名称和正确名称的映射
    strategy_mapping = {
        'RSI_BOTTOM_FISHING': '深渊筑底策略_v2.0',
        'MACD_ZERO_AXIS_GOLDEN_CROSS': 'MACD零轴启动_v1.0',
        'TRIPLE_CROSS': '三重金叉_v1.0',
        'PRE_CROSS': '临界金叉_v1.0',
        'WEEKLY_GOLDEN_CROSS_MA': '周线金叉+日线MA_v1.0',
        'ABYSS_BOTTOMING': '深渊筑底策略_v2.0'
    }
    
    print("错误名称 → 正确名称")
    print("-" * 60)
    for wrong_name, correct_name in strategy_mapping.items():
        print(f"{wrong_name:<25} → {correct_name}")
    
    print()

def show_available_strategies():
    """显示当前可用的策略"""
    print("🔍 当前可用策略列表:")
    print("-" * 60)
    
    strategies = get_available_strategies()
    
    if strategies:
        for i, strategy_id in enumerate(strategies, 1):
            print(f"{i:2d}. {strategy_id}")
        
        print(f"\n✅ 总计 {len(strategies)} 个可用策略")
    else:
        print("❌ 未找到可用策略")
    
    print()

def show_usage_examples():
    """显示使用示例"""
    print("🚀 正确的使用方法:")
    print("-" * 60)
    
    strategies = get_available_strategies()
    
    if len(strategies) >= 2:
        strategy1 = strategies[0]
        strategy2 = strategies[1]
        
        print("1. 使用默认策略:")
        print("   python backend/universal_screener.py")
        print()
        
        print("2. 指定单个策略:")
        print(f"   python backend/universal_screener.py -s {strategy1}")
        print()
        
        print("3. 指定多个策略:")
        print(f"   python backend/universal_screener.py -s {strategy1} {strategy2}")
        print()
        
        print("4. 运行增强筛选:")
        print(f"   python backend/universal_screener.py --mode enhanced -s {strategy1}")
        print()
        
        print("5. 对比筛选模式:")
        print(f"   python backend/universal_screener.py --mode compare -s {strategy1}")
        print()
        
        print("6. 保存结果:")
        print(f"   python backend/universal_screener.py -s {strategy1} --output results.json")
        print()
    else:
        print("❌ 策略数量不足，无法生成示例")

def test_strategy_validity():
    """测试策略有效性"""
    print("🧪 测试策略有效性:")
    print("-" * 60)
    
    try:
        from strategy_manager import strategy_manager
        
        # 测试常用策略
        test_strategies = [
            '深渊筑底策略_v2.0',
            'MACD零轴启动_v1.0', 
            '三重金叉_v1.0',
            '临界金叉_v1.0',
            '周线金叉+日线MA_v1.0'
        ]
        
        valid_strategies = []
        invalid_strategies = []
        
        for strategy_id in test_strategies:
            strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
            if strategy_instance:
                valid_strategies.append(strategy_id)
                print(f"✅ {strategy_id}")
            else:
                invalid_strategies.append(strategy_id)
                print(f"❌ {strategy_id}")
        
        print(f"\n📊 测试结果:")
        print(f"   有效策略: {len(valid_strategies)}")
        print(f"   无效策略: {len(invalid_strategies)}")
        
        if valid_strategies:
            print(f"\n🎯 推荐使用的策略组合:")
            print(f"   python backend/universal_screener.py -s {' '.join(valid_strategies[:2])}")
        
        return valid_strategies
        
    except Exception as e:
        print(f"❌ 策略测试失败: {e}")
        return []

def create_fixed_demo_script():
    """创建修复后的演示脚本"""
    print("📝 创建修复后的演示脚本...")
    
    valid_strategies = test_strategy_validity()
    
    if len(valid_strategies) >= 2:
        demo_script = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复后的通用筛选器演示脚本
使用正确的策略名称
"""

import sys
import os

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def main():
    """主函数"""
    print("🚀 运行修复后的通用筛选器")
    
    try:
        from universal_screener import UniversalScreener
        
        # 使用验证过的有效策略
        valid_strategies = {valid_strategies[:2]}
        
        print(f"📋 使用策略: {{', '.join(valid_strategies)}}")
        
        # 创建筛选器
        screener = UniversalScreener()
        
        # 运行筛选
        results = screener.run_screening(valid_strategies, max_workers=2)
        
        print(f"✅ 筛选完成，发现 {{len(results)}} 个信号")
        
        if results:
            print("\\n📊 前5个结果:")
            for i, result in enumerate(results[:5], 1):
                print(f"   {{i}}. {{result.stock_code}} ({{result.stock_name}})")
                print(f"      信号: {{result.signal_type}}")
                print(f"      日期: {{result.date.strftime('%Y-%m-%d')}}")
                print(f"      价格: ¥{{result.current_price:.2f}}")
                print()
        
        return 0
        
    except Exception as e:
        print(f"❌ 运行失败: {{e}}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
'''
        
        with open('run_fixed_universal_screener.py', 'w', encoding='utf-8') as f:
            f.write(demo_script)
        
        print("✅ 创建修复脚本: run_fixed_universal_screener.py")
        print("   使用方法: python run_fixed_universal_screener.py")
    else:
        print("❌ 没有足够的有效策略，无法创建演示脚本")

def main():
    """主函数"""
    print("🔧 通用筛选器策略名称修复工具")
    print("=" * 60)
    
    # 1. 显示策略映射
    show_strategy_mapping()
    
    # 2. 显示可用策略
    show_available_strategies()
    
    # 3. 测试策略有效性
    valid_strategies = test_strategy_validity()
    
    # 4. 显示使用示例
    print()
    show_usage_examples()
    
    # 5. 创建修复脚本
    print()
    create_fixed_demo_script()
    
    print("\n" + "=" * 60)
    print("🎉 修复完成！")
    print("\n💡 关键要点:")
    print("   • 使用中文策略名称（如 '深渊筑底策略_v2.0'）")
    print("   • 避免使用英文别名（如 'RSI_BOTTOM_FISHING'）")
    print("   • 通过 strategy_manager.get_available_strategies() 获取最新列表")
    print("   • 使用 --help 参数查看完整选项")
    
    if valid_strategies:
        print(f"\n🚀 快速开始:")
        print(f"   python backend/universal_screener.py -s {valid_strategies[0]}")
    
    return 0

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)