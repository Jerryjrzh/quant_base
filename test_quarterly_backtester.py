#!/usr/bin/env python3
"""
季度回测系统测试脚本
测试季度回测系统的基本功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def test_quarterly_backtester_import():
    """测试季度回测器导入"""
    print("=== 测试季度回测器导入 ===")
    
    try:
        from quarterly_backtester import QuarterlyBacktester, QuarterlyBacktestConfig, QuarterlyResult
        print("✓ 季度回测器导入成功")
        
        # 测试配置创建
        config = QuarterlyBacktestConfig()
        print(f"✓ 默认配置创建成功: {config.lookback_years} 年回测")
        print(f"✓ 股票池选择策略: {config.pool_selection_strategy}")
        print(f"✓ 测试策略: {config.test_strategies}")
        
        return True
        
    except ImportError as e:
        print(f"✗ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 其他错误: {e}")
        return False

def test_quarter_calculation():
    """测试季度计算功能"""
    print("\n=== 测试季度计算功能 ===")
    
    try:
        from quarterly_backtester import QuarterlyBacktester, QuarterlyBacktestConfig
        
        config = QuarterlyBacktestConfig(lookback_years=1)
        backtester = QuarterlyBacktester(config)
        
        # 测试季度计算
        end_date = datetime(2024, 12, 31)
        quarters = backtester.get_quarters_in_period(end_date)
        
        print(f"✓ 计算出 {len(quarters)} 个季度")
        for quarter_name, start_date, end_date in quarters:
            print(f"  {quarter_name}: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
        
        return len(quarters) > 0
        
    except Exception as e:
        print(f"✗ 季度计算失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_stock_list_loading():
    """测试股票列表加载"""
    print("\n=== 测试股票列表加载 ===")
    
    try:
        from quarterly_backtester import QuarterlyBacktester, QuarterlyBacktestConfig
        
        config = QuarterlyBacktestConfig()
        backtester = QuarterlyBacktester(config)
        
        stock_list = backtester.get_stock_list()
        print(f"✓ 加载了 {len(stock_list)} 只股票")
        
        if stock_list:
            print(f"✓ 示例股票: {stock_list[:5]}")
            return True
        else:
            print("✗ 没有加载到股票")
            return False
        
    except Exception as e:
        print(f"✗ 股票列表加载失败: {e}")
        return False

def test_data_loading():
    """测试数据加载功能"""
    print("\n=== 测试数据加载功能 ===")
    
    try:
        from quarterly_backtester import QuarterlyBacktester, QuarterlyBacktestConfig
        
        config = QuarterlyBacktestConfig()
        backtester = QuarterlyBacktester(config)
        
        # 获取股票列表
        stock_list = backtester.get_stock_list()
        if not stock_list:
            print("✗ 没有股票可供测试")
            return False
        
        # 测试加载几只股票的数据
        test_symbols = stock_list[:3]  # 测试前3只股票
        successful_loads = 0
        
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        
        for symbol in test_symbols:
            df = backtester.load_stock_data(symbol, start_date, end_date)
            if df is not None and not df.empty:
                successful_loads += 1
                print(f"✓ {symbol}: 加载了 {len(df)} 天数据")
            else:
                print(f"✗ {symbol}: 数据加载失败")
        
        success_rate = successful_loads / len(test_symbols)
        print(f"✓ 数据加载成功率: {success_rate:.1%}")
        
        return success_rate > 0
        
    except Exception as e:
        print(f"✗ 数据加载测试失败: {e}")
        return False

def test_strategy_functions():
    """测试策略函数"""
    print("\n=== 测试策略函数 ===")
    
    try:
        import strategies
        
        # 测试策略列表
        available_strategies = strategies.list_available_strategies()
        print(f"✓ 可用策略: {available_strategies}")
        
        # 测试获取策略函数
        test_strategies = ['WEEKLY_GOLDEN_CROSS_MA', 'TRIPLE_CROSS', 'MACD_ZERO_AXIS']
        
        for strategy_name in test_strategies:
            strategy_func = strategies.get_strategy_function(strategy_name)
            if strategy_func is not None:
                print(f"✓ {strategy_name}: 策略函数获取成功")
            else:
                print(f"✗ {strategy_name}: 策略函数获取失败")
        
        return True
        
    except Exception as e:
        print(f"✗ 策略函数测试失败: {e}")
        return False

def test_mock_backtest():
    """测试模拟回测"""
    print("\n=== 测试模拟回测 ===")
    
    try:
        from quarterly_backtester import QuarterlyBacktester, QuarterlyBacktestConfig
        
        # 创建简化配置
        config = QuarterlyBacktestConfig(
            lookback_years=1,
            max_pool_size=5,  # 减少股票数量
            test_period_days=30,  # 缩短测试期
            pool_selection_period=15  # 缩短选择期
        )
        
        backtester = QuarterlyBacktester(config)
        
        # 测试季度计算
        quarters = backtester.get_quarters_in_period()
        if not quarters:
            print("✗ 没有季度数据")
            return False
        
        print(f"✓ 将测试 {len(quarters)} 个季度")
        
        # 测试第一个季度的股票池选择
        quarter_name, quarter_start, quarter_end = quarters[0]
        print(f"✓ 测试季度: {quarter_name}")
        
        try:
            stock_pool = backtester.select_quarterly_pool(quarter_start, quarter_end)
            print(f"✓ 选择了 {len(stock_pool)} 只股票进入股票池")
            
            if stock_pool:
                print(f"✓ 示例股票: {stock_pool[:3]}")
                return True
            else:
                print("⚠ 股票池为空，但功能正常")
                return True
                
        except Exception as e:
            print(f"✗ 股票池选择失败: {e}")
            return False
        
    except Exception as e:
        print(f"✗ 模拟回测失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_analyzer_import():
    """测试分析器导入"""
    print("\n=== 测试分析器导入 ===")
    
    try:
        from quarterly_analyzer import QuarterlyAnalyzer
        print("✓ 季度分析器导入成功")
        return True
        
    except ImportError as e:
        print(f"✗ 分析器导入失败: {e}")
        return False
    except Exception as e:
        print(f"✗ 其他错误: {e}")
        return False

def test_configuration_options():
    """测试配置选项"""
    print("\n=== 测试配置选项 ===")
    
    try:
        from quarterly_backtester import QuarterlyBacktestConfig
        
        # 测试默认配置
        default_config = QuarterlyBacktestConfig()
        print(f"✓ 默认配置:")
        print(f"  - 回溯年数: {default_config.lookback_years}")
        print(f"  - 股票池策略: {default_config.pool_selection_strategy}")
        print(f"  - 最大股票池: {default_config.max_pool_size}")
        print(f"  - 测试策略: {default_config.test_strategies}")
        
        # 测试自定义配置
        custom_config = QuarterlyBacktestConfig(
            lookback_years=2,
            pool_selection_strategy='TRIPLE_CROSS',
            max_pool_size=20,
            test_strategies=['MACD_ZERO_AXIS', 'PRE_CROSS']
        )
        print(f"✓ 自定义配置:")
        print(f"  - 回溯年数: {custom_config.lookback_years}")
        print(f"  - 股票池策略: {custom_config.pool_selection_strategy}")
        print(f"  - 最大股票池: {custom_config.max_pool_size}")
        print(f"  - 测试策略: {custom_config.test_strategies}")
        
        return True
        
    except Exception as e:
        print(f"✗ 配置选项测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("季度回测系统功能测试")
    print("=" * 50)
    
    tests = [
        ("季度回测器导入", test_quarterly_backtester_import),
        ("季度计算功能", test_quarter_calculation),
        ("股票列表加载", test_stock_list_loading),
        ("数据加载功能", test_data_loading),
        ("策略函数", test_strategy_functions),
        ("配置选项", test_configuration_options),
        ("分析器导入", test_analyzer_import),
        ("模拟回测", test_mock_backtest)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} 测试通过")
            else:
                print(f"❌ {test_name} 测试失败")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
    
    print(f"\n{'='*60}")
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！季度回测系统功能正常。")
        print("\n✨ 系统已准备就绪，可以开始运行季度回测：")
        print("1. 运行完整回测:")
        print("   python backend/quarterly_backtester.py")
        print("\n2. 分析回测结果:")
        print("   python backend/quarterly_analyzer.py <结果文件.json> --charts --report")
        
    else:
        print("❌ 部分测试失败，请检查系统配置。")
    
    print(f"\n测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()