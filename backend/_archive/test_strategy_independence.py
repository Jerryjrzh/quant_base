#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试人工分析逻辑策略类的独立性和功能

验证策略是否能够正确地从universal_screener.py独立出来
"""

import sys
import os

# Fix import path to run from archive
_PROJ_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _PROJ_ROOT not in sys.path:
    sys.path.insert(0, _PROJ_ROOT)

def test_strategy_imports():
    """测试策略类的导入"""
    print("🧪 测试策略类导入...")
    
    try:
        from strategies.annual_bottom_opportunity_strategy import AnnualBottomOpportunityStrategy
        print("✅ AnnualBottomOpportunityStrategy 导入成功")
    except Exception as e:
        print(f"❌ AnnualBottomOpportunityStrategy 导入失败: {e}")
        return False
    
    try:
        from strategies.strong_stock_ma13_pullback_strategy import StrongStockMA13PullbackStrategy
        print("✅ StrongStockMA13PullbackStrategy 导入成功")
    except Exception as e:
        print(f"❌ StrongStockMA13PullbackStrategy 导入失败: {e}")
        return False
    
    try:
        from strategies.long_term_consolidation_breakout_strategy import LongTermConsolidationBreakoutStrategy
        print("✅ LongTermConsolidationBreakoutStrategy 导入成功")
    except Exception as e:
        print(f"❌ LongTermConsolidationBreakoutStrategy 导入失败: {e}")
        return False
    
    return True

def test_strategy_manager():
    """测试策略管理器是否能够识别新策略"""
    print("\n🧪 测试策略管理器...")
    
    try:
        from strategy_manager import StrategyManager
        
        manager = StrategyManager()
        strategies = manager.get_available_strategies()
        
        # 查找人工分析逻辑策略
        human_logic_strategies = []
        for strategy in strategies:
            if any(keyword in strategy['name'] for keyword in ['年度见底', 'MA13回调', '横盘突破']):
                human_logic_strategies.append(strategy)
        
        print(f"✅ 发现 {len(human_logic_strategies)} 个人工分析逻辑策略:")
        for strategy in human_logic_strategies:
            print(f"   - {strategy['name']} (ID: {strategy['id']})")
        
        return len(human_logic_strategies) >= 3
        
    except Exception as e:
        print(f"❌ 策略管理器测试失败: {e}")
        return False

def test_strategy_instantiation():
    """测试策略实例化"""
    print("\n🧪 测试策略实例化...")
    
    try:
        from strategies.annual_bottom_opportunity_strategy import AnnualBottomOpportunityStrategy
        from strategies.strong_stock_ma13_pullback_strategy import StrongStockMA13PullbackStrategy
        from strategies.long_term_consolidation_breakout_strategy import LongTermConsolidationBreakoutStrategy
        
        # 测试年度见底机会策略
        strategy1 = AnnualBottomOpportunityStrategy()
        print(f"✅ {strategy1.name} v{strategy1.version} 实例化成功")
        print(f"   描述: {strategy1.description}")
        print(f"   所需数据长度: {strategy1.get_required_data_length()}")
        
        # 测试强势股MA13回调策略
        strategy2 = StrongStockMA13PullbackStrategy()
        print(f"✅ {strategy2.name} v{strategy2.version} 实例化成功")
        print(f"   描述: {strategy2.description}")
        print(f"   所需数据长度: {strategy2.get_required_data_length()}")
        
        # 测试长周期横盘突破策略
        strategy3 = LongTermConsolidationBreakoutStrategy()
        print(f"✅ {strategy3.name} v{strategy3.version} 实例化成功")
        print(f"   描述: {strategy3.description}")
        print(f"   所需数据长度: {strategy3.get_required_data_length()}")
        
        return True
        
    except Exception as e:
        print(f"❌ 策略实例化失败: {e}")
        return False

def test_universal_screener_independence():
    """测试universal_screener.py的独立性"""
    print("\n🧪 测试universal_screener.py独立性...")
    
    try:
        from universal_screener import UniversalScreener
        
        screener = UniversalScreener()
        print("✅ UniversalScreener 创建成功")
        
        # 检查是否还有对人工分析逻辑策略的直接引用
        import inspect
        source = inspect.getsource(UniversalScreener)
        
        forbidden_imports = [
            'human_logic_strategies',
            'annual_bottom_opportunity_strategy',
            'strong_stock_ma13_pullback_strategy', 
            'long_term_consolidation_breakout_strategy'
        ]
        
        for forbidden in forbidden_imports:
            if forbidden in source:
                print(f"⚠️ 发现残留引用: {forbidden}")
                return False
        
        print("✅ 未发现对人工分析逻辑策略的直接引用")
        return True
        
    except Exception as e:
        print(f"❌ UniversalScreener 测试失败: {e}")
        return False

def test_strategy_through_manager():
    """测试通过策略管理器使用策略"""
    print("\n🧪 测试通过策略管理器使用策略...")
    
    try:
        from strategy_manager import StrategyManager
        
        manager = StrategyManager()
        
        # 尝试获取策略实例
        test_strategies = [
            "年度见底机会策略_v1.0",
            "强势股MA13回调策略_v1.0", 
            "长周期横盘突破策略_v1.0"
        ]
        
        success_count = 0
        for strategy_id in test_strategies:
            strategy = manager.get_strategy_instance(strategy_id)
            if strategy is not None:
                print(f"✅ 成功获取策略实例: {strategy.name}")
                success_count += 1
            else:
                print(f"❌ 无法获取策略实例: {strategy_id}")
        
        return success_count == len(test_strategies)
        
    except Exception as e:
        print(f"❌ 策略管理器使用测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🎯 人工分析逻辑策略独立性测试")
    print("=" * 50)
    
    test_results = []
    
    # 执行所有测试
    test_results.append(("策略类导入", test_strategy_imports()))
    test_results.append(("策略管理器识别", test_strategy_manager()))
    test_results.append(("策略实例化", test_strategy_instantiation()))
    test_results.append(("UniversalScreener独立性", test_universal_screener_independence()))
    test_results.append(("通过管理器使用策略", test_strategy_through_manager()))
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("📊 测试结果汇总:")
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 总体结果: {passed}/{total} 测试通过")
    
    if passed == total:
        print("🎉 所有测试通过！策略独立性重构成功！")
        print("\n📋 重构总结:")
        print("   ✅ 三个人工分析逻辑策略已成功独立为策略类")
        print("   ✅ 策略类继承BaseStrategy并实现标准接口")
        print("   ✅ 策略管理器能够正确识别和管理新策略")
        print("   ✅ UniversalScreener不再直接依赖人工分析逻辑策略")
        print("   ✅ 所有策略通过统一的策略管理器进行调用")
        return True
    else:
        print("⚠️ 部分测试失败，需要进一步检查和修复")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)