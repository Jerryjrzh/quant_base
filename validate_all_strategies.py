#!/usr/bin/env python3
"""
验证所有策略和功能的完整性测试
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def create_test_data():
    """创建测试数据"""
    print("📊 创建测试数据...")
    
    # 生成模拟股价数据
    dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
    np.random.seed(42)
    
    # 模拟价格走势
    returns = np.random.normal(0.001, 0.02, len(dates))
    prices = 100 * np.cumprod(1 + returns)
    
    df = pd.DataFrame({
        'date': dates,
        'close': prices,
        'high': prices * (1 + np.random.uniform(0, 0.02, len(dates))),
        'low': prices * (1 - np.random.uniform(0, 0.02, len(dates))),
        'open': prices * (1 + np.random.uniform(-0.01, 0.01, len(dates))),
        'volume': np.random.randint(1000000, 10000000, len(dates))
    })
    df.set_index('date', inplace=True)
    
    print(f"✅ 创建了 {len(df)} 天的测试数据")
    return df

def test_indicators():
    """测试技术指标"""
    print("\n🔧 测试技术指标...")
    
    try:
        import indicators
        df = create_test_data()
        
        # 测试MACD
        macd_result = indicators.calculate_macd(df)
        assert len(macd_result) == 2, "MACD应该返回DIF和DEA"
        print("✅ MACD指标正常")
        
        # 测试KDJ
        kdj_result = indicators.calculate_kdj(df)
        assert len(kdj_result) == 3, "KDJ应该返回K、D、J"
        print("✅ KDJ指标正常")
        
        # 测试RSI
        rsi_result = indicators.calculate_rsi(df)
        assert isinstance(rsi_result, pd.Series), "RSI应该返回Series"
        print("✅ RSI指标正常")
        
        return True
        
    except Exception as e:
        print(f"❌ 技术指标测试失败: {e}")
        return False

def test_strategies():
    """测试交易策略"""
    print("\n📈 测试交易策略...")
    
    try:
        import strategies
        import indicators
        
        df = create_test_data()
        
        # 添加技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        kdj_values = indicators.calculate_kdj(df)
        df['k'], df['d'], df['j'] = kdj_values[0], kdj_values[1], kdj_values[2]
        
        df['rsi'] = indicators.calculate_rsi(df)
        
        # 测试MACD零轴启动策略
        macd_signals = strategies.apply_macd_zero_axis_strategy(df)
        assert isinstance(macd_signals, pd.Series), "策略应该返回Series"
        print("✅ MACD零轴启动策略正常")
        
        # 测试三重金叉策略
        triple_signals = strategies.apply_triple_cross(df)
        assert isinstance(triple_signals, pd.Series), "策略应该返回Series"
        print("✅ 三重金叉策略正常")
        
        # 测试PRE策略
        pre_signals = strategies.apply_pre_cross(df)
        assert isinstance(pre_signals, pd.Series), "策略应该返回Series"
        print("✅ PRE策略正常")
        
        return True
        
    except Exception as e:
        print(f"❌ 交易策略测试失败: {e}")
        return False

def test_backtester():
    """测试回测系统"""
    print("\n📊 测试回测系统...")
    
    try:
        import backtester
        import strategies
        import indicators
        
        df = create_test_data()
        
        # 添加技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        # 生成信号
        signals = strategies.apply_macd_zero_axis_strategy(df)
        
        # 执行回测
        backtest_result = backtester.run_backtest(df, signals)
        
        assert isinstance(backtest_result, dict), "回测应该返回字典"
        assert 'total_signals' in backtest_result, "回测结果应该包含信号总数"
        
        print("✅ 回测系统正常")
        print(f"   测试信号数: {backtest_result.get('total_signals', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 回测系统测试失败: {e}")
        return False

def test_trading_advisor():
    """测试交易顾问"""
    print("\n💡 测试交易顾问...")
    
    try:
        from trading_advisor import TradingAdvisor
        import strategies
        import indicators
        
        df = create_test_data()
        
        # 添加技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        # 生成信号
        signals = strategies.apply_macd_zero_axis_strategy(df)
        
        # 找到一个信号
        signal_indices = df.index[signals != ''].tolist()
        if signal_indices:
            signal_idx = df.index.get_loc(signal_indices[0])
            signal_state = signals.iloc[signal_idx]
            
            advisor = TradingAdvisor()
            
            # 测试入场建议
            entry_advice = advisor.get_entry_recommendations(df, signal_idx, signal_state)
            assert isinstance(entry_advice, dict), "入场建议应该返回字典"
            print("✅ 入场建议功能正常")
            
            # 测试出场建议
            entry_price = df.iloc[signal_idx]['close']
            exit_advice = advisor.get_exit_recommendations(df, signal_idx, entry_price)
            assert isinstance(exit_advice, dict), "出场建议应该返回字典"
            print("✅ 出场建议功能正常")
            
        return True
        
    except Exception as e:
        print(f"❌ 交易顾问测试失败: {e}")
        return False

def test_parametric_advisor():
    """测试参数化顾问"""
    print("\n🔧 测试参数化顾问...")
    
    try:
        from parametric_advisor import ParametricTradingAdvisor, TradingParameters
        import strategies
        import indicators
        
        df = create_test_data()
        
        # 添加技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        # 生成信号
        signals = strategies.apply_macd_zero_axis_strategy(df)
        
        # 创建参数化顾问
        params = TradingParameters()
        advisor = ParametricTradingAdvisor(params)
        
        # 测试回测
        backtest_result = advisor.backtest_parameters(df, signals)
        assert isinstance(backtest_result, dict), "参数化回测应该返回字典"
        print("✅ 参数化回测功能正常")
        
        # 找到信号测试建议
        signal_indices = df.index[signals != ''].tolist()
        if signal_indices:
            signal_idx = df.index.get_loc(signal_indices[0])
            signal_state = signals.iloc[signal_idx]
            
            # 测试参数化建议
            advice = advisor.get_parametric_entry_recommendations(df, signal_idx, signal_state)
            assert isinstance(advice, dict), "参数化建议应该返回字典"
            print("✅ 参数化建议功能正常")
        
        return True
        
    except Exception as e:
        print(f"❌ 参数化顾问测试失败: {e}")
        return False

def test_config_system():
    """测试配置系统"""
    print("\n⚙️ 测试配置系统...")
    
    try:
        from strategy_config import StrategyConfigManager
        
        config_manager = StrategyConfigManager()
        
        # 测试配置加载
        assert len(config_manager.market_environments) > 0, "应该有市场环境配置"
        assert len(config_manager.risk_profiles) > 0, "应该有风险配置"
        print("✅ 配置加载正常")
        
        # 测试市场环境检测
        df = create_test_data()
        detected_env = config_manager.detect_market_environment(df)
        assert detected_env in config_manager.market_environments, "检测的环境应该存在"
        print(f"✅ 市场环境检测正常: {detected_env}")
        
        # 测试自适应配置
        adaptive_config = config_manager.get_adaptive_config(df)
        assert isinstance(adaptive_config, dict), "自适应配置应该返回字典"
        assert 'parameters' in adaptive_config, "应该包含参数"
        print("✅ 自适应配置正常")
        
        return True
        
    except Exception as e:
        print(f"❌ 配置系统测试失败: {e}")
        return False

def test_enhanced_analyzer():
    """测试增强分析器"""
    print("\n🔍 测试增强分析器...")
    
    try:
        from enhanced_analyzer import EnhancedTradingAnalyzer
        
        # 注意：这里我们不能测试真实股票数据，因为可能不存在
        # 所以我们只测试类的创建
        analyzer = EnhancedTradingAnalyzer()
        assert analyzer is not None, "分析器应该能够创建"
        print("✅ 增强分析器创建正常")
        
        return True
        
    except Exception as e:
        print(f"❌ 增强分析器测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🧪 开始验证所有策略和功能")
    print("=" * 60)
    
    test_results = []
    
    # 执行所有测试
    tests = [
        ("技术指标", test_indicators),
        ("交易策略", test_strategies),
        ("回测系统", test_backtester),
        ("交易顾问", test_trading_advisor),
        ("参数化顾问", test_parametric_advisor),
        ("配置系统", test_config_system),
        ("增强分析器", test_enhanced_analyzer)
    ]
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}测试出现异常: {e}")
            test_results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📋 测试结果汇总")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:<12} {status}")
        if result:
            passed += 1
    
    print("-" * 60)
    print(f"总计: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！系统功能完整。")
        
        # 生成验证报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        report_file = f"validation_report_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"系统验证报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"测试通过率: {passed}/{total} ({passed/total*100:.1f}%)\n\n")
            f.write("测试详情:\n")
            for test_name, result in test_results:
                status = "通过" if result else "失败"
                f.write(f"  {test_name}: {status}\n")
            f.write("\n系统功能验证完成，可以正常使用。\n")
        
        print(f"📄 验证报告已保存到: {report_file}")
        
    else:
        print("⚠️ 部分测试失败，请检查相关功能。")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())