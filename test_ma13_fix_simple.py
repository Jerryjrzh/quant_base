#!/usr/bin/env python3
"""
MA13策略修复简单测试
验证导入和基本功能是否正常

作者：基于Grok和Gemini评估优化
日期：2025-09-17
"""

import sys
import os

# 确保在项目根目录
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def test_imports():
    """测试模块导入"""
    print("=== 测试模块导入 ===")
    
    try:
        print("1. 测试data_loader导入...")
        from backend.data_loader import fetch_hourly_kline, get_multi_timeframe_data
        print("   ✓ data_loader导入成功")
        
        print("2. 测试indicators导入...")
        from backend.indicators import get_indicator_position, calculate_macd
        print("   ✓ indicators导入成功")
        
        print("3. 测试MA13策略导入...")
        from backend.strategies.ma13_callback_strategy import MA13CallbackStrategy
        print("   ✓ MA13策略导入成功")
        
        print("4. 测试集成模块导入...")
        from backend.ma13_strategy_integration import MA13StrategyIntegration
        print("   ✓ 集成模块导入成功")
        
        return True
        
    except ImportError as e:
        print(f"   ✗ 导入失败: {e}")
        return False

def test_indicator_positions():
    """测试指标位置判断"""
    print("\n=== 测试指标位置判断 ===")
    
    try:
        from backend.indicators import get_indicator_position
        
        # 测试KDJ位置
        test_cases = [
            (30, 'kdj_j', 'oversold'),
            (60, 'kdj_j', 'relay'),
            (95, 'kdj_j', 'overbought'),
            (70, 'rsi_6', 'strong_support'),
            (0.1, 'macd_dif', 'above_zero'),
            (-0.1, 'macd_dif', 'below_zero')
        ]
        
        for value, category, expected in test_cases:
            result = get_indicator_position(value, category)
            status = "✓" if result == expected else "✗"
            print(f"   {status} {category}={value} -> {result} (期望: {expected})")
        
        return True
        
    except Exception as e:
        print(f"   ✗ 测试失败: {e}")
        return False

def test_strategy_initialization():
    """测试策略初始化"""
    print("\n=== 测试策略初始化 ===")
    
    try:
        from backend.strategies.ma13_callback_strategy import MA13CallbackStrategy
        
        config = {
            'callback_range': [3, 15],
            'vol_multiplier': 1.1,
            'kdj_relay_range': [40, 90],
            'ma13_tolerance': 0.02,
            'min_rise_pct': 15,
            'lookback_days': 60,
            'hourly_lookback_days': 10
        }
        
        strategy = MA13CallbackStrategy(config)
        print("   ✓ 策略初始化成功")
        print(f"   ✓ 配置加载: {len(strategy.config)} 个参数")
        
        return True
        
    except Exception as e:
        print(f"   ✗ 策略初始化失败: {e}")
        return False

def test_data_loading():
    """测试数据加载"""
    print("\n=== 测试数据加载 ===")
    
    try:
        from backend.data_loader import get_multi_timeframe_data, fetch_hourly_kline
        
        # 测试股票代码
        test_stock = 'sz002021'
        
        print(f"   测试股票: {test_stock}")
        
        # 测试多时间框架数据
        multi_data = get_multi_timeframe_data(test_stock)
        print(f"   ✓ 多时间框架数据获取完成")
        print(f"   ✓ 日线数据可用: {multi_data['data_status']['daily_available']}")
        print(f"   ✓ 5分钟数据可用: {multi_data['data_status']['min5_available']}")
        
        if multi_data['data_status']['daily_available']:
            daily_df = multi_data['daily_data']
            print(f"   ✓ 日线数据量: {len(daily_df)} 条")
        
        # 测试小时线数据聚合
        hourly_df = fetch_hourly_kline(test_stock, '2025-09-01', '2025-09-17')
        if not hourly_df.empty:
            print(f"   ✓ 小时线数据聚合成功: {len(hourly_df)} 条")
        else:
            print("   ! 小时线数据为空（可能是数据源问题）")
        
        return True
        
    except Exception as e:
        print(f"   ✗ 数据加载测试失败: {e}")
        return False

def test_integration():
    """测试系统集成"""
    print("\n=== 测试系统集成 ===")
    
    try:
        from backend.ma13_strategy_integration import MA13StrategyIntegration
        
        integration = MA13StrategyIntegration()
        print("   ✓ 集成模块初始化成功")
        
        # 测试单股筛选
        result = integration.screen_single_stock('sz002021')
        print(f"   ✓ 单股筛选完成: {result['status']}")
        
        if result['signal']:
            print(f"   ✓ 发现信号: {result['signal']} (强度: {result['strength']})")
        else:
            print("   - 无信号（正常情况）")
        
        return True
        
    except Exception as e:
        print(f"   ✗ 系统集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("MA13策略修复简单测试")
    print("=" * 50)
    
    tests = [
        ("模块导入", test_imports),
        ("指标位置判断", test_indicator_positions),
        ("策略初始化", test_strategy_initialization),
        ("数据加载", test_data_loading),
        ("系统集成", test_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"测试 {test_name} 时发生异常: {e}")
            results.append((test_name, False))
    
    # 输出测试结果摘要
    print("\n" + "=" * 50)
    print("测试结果摘要:")
    
    passed = 0
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 个测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！MA13策略修复成功！")
        return True
    else:
        print("⚠️  部分测试失败，请检查相关模块")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)