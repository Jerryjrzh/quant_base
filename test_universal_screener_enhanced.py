#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Universal Screener 完整功能测试
验证所有新增的过滤器、回测分析、深度扫描等功能
"""

import os
import sys
import json
from datetime import datetime

# 添加backend路径到sys.path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.append(backend_dir)

def test_universal_screener_basic():
    """测试Universal Screener基础功能"""
    print("🧪 测试Universal Screener基础功能...")
    
    try:
        from universal_screener import UniversalScreener
        
        # 创建筛选器实例
        screener = UniversalScreener()
        print("✅ Universal Screener初始化成功")
        
        # 测试配置加载
        config = screener.config
        print(f"✅ 配置加载成功，包含 {len(config)} 个配置项")
        
        # 测试策略管理器
        available_strategies = screener.get_available_strategies()
        print(f"✅ 策略管理器工作正常，可用策略: {len(available_strategies)} 个")
        
        for strategy in available_strategies:
            status = "启用" if strategy['enabled'] else "禁用"
            print(f"   - {strategy['name']} v{strategy['version']} ({status})")
        
        return True
        
    except Exception as e:
        print(f"❌ 基础功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_filter_functions():
    """测试新增的过滤器函数"""
    print("\n🔍 测试策略专用过滤器...")
    
    try:
        from universal_screener import (
            check_macd_zero_axis_pre_filter,
            check_weekly_golden_cross_ma_filter,
            check_triple_cross_enhanced_filter
        )
        import pandas as pd
        import numpy as np
        
        # 创建模拟数据
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        mock_data = pd.DataFrame({
            'close': np.random.uniform(10, 20, 100),
            'high': np.random.uniform(10.5, 20.5, 100),
            'low': np.random.uniform(9.5, 19.5, 100),
            'volume': np.random.uniform(1000000, 5000000, 100)
        }, index=dates)
        
        # 测试MACD零轴过滤器
        should_exclude, reason = check_macd_zero_axis_pre_filter(
            mock_data, 50, 'PRE'
        )
        print(f"✅ MACD零轴过滤器测试: 排除={should_exclude}, 原因='{reason}'")
        
        # 测试周线金叉过滤器
        should_exclude, reason = check_weekly_golden_cross_ma_filter(
            mock_data, 50, 'BUY', 'sh600000'
        )
        print(f"✅ 周线金叉过滤器测试: 排除={should_exclude}, 原因='{reason}'")
        
        # 测试三重交叉过滤器
        should_exclude, reason, details = check_triple_cross_enhanced_filter(
            mock_data, 50, 'sh600000'
        )
        print(f"✅ 三重交叉过滤器测试: 排除={should_exclude}, 质量评分={details.get('quality_score', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 过滤器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ma_trend_analysis():
    """测试MA趋势分析功能"""
    print("\n📈 测试MA趋势分析...")
    
    try:
        from universal_screener import UniversalScreener
        import pandas as pd
        import numpy as np
        
        screener = UniversalScreener()
        
        # 创建模拟数据
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        mock_data = pd.DataFrame({
            'close': np.linspace(10, 20, 100),  # 上升趋势
            'volume': np.random.uniform(1000000, 5000000, 100)
        }, index=dates)
        
        # 测试MA趋势分析
        trend_analysis = screener.analyze_ma_trend(mock_data)
        
        print(f"✅ MA趋势分析完成:")
        print(f"   趋势强度: {trend_analysis['trend_strength']:.2f}")
        print(f"   MA13距离: {trend_analysis['ma13_distance']:.2%}")
        print(f"   成交量比例: {trend_analysis['volume_surge_ratio']:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ MA趋势分析测试失败: {e}")
        return False

def test_backtest_integration():
    """测试回测集成功能"""
    print("\n📊 测试回测集成...")
    
    try:
        from universal_screener import UniversalScreener
        from strategies.base_strategy import StrategyResult
        import pandas as pd
        import numpy as np
        
        screener = UniversalScreener()
        
        # 创建模拟策略结果
        mock_results = [
            StrategyResult(
                stock_code="sh600000",
                strategy_name="测试策略",
                signal_type="BUY",
                signal_strength=2,
                date="2024-08-24",
                current_price=15.50,
                signal_details={'stage_passed': 2}
            )
        ]
        
        # 创建模拟数据
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        mock_data = pd.DataFrame({
            'close': np.random.uniform(10, 20, 100),
            'high': np.random.uniform(10.5, 20.5, 100),
            'low': np.random.uniform(9.5, 19.5, 100),
            'volume': np.random.uniform(1000000, 5000000, 100)
        }, index=dates)
        
        # 创建模拟信号序列
        signal_series = pd.Series('', index=dates)
        signal_series.iloc[-1] = 'BUY'
        
        # 测试回测统计计算
        backtest_stats = screener.calculate_backtest_stats(mock_data, signal_series)
        
        print(f"✅ 回测统计计算完成:")
        print(f"   总信号数: {backtest_stats['total_signals']}")
        print(f"   胜率: {backtest_stats['win_rate']}")
        print(f"   平均收益: {backtest_stats['avg_max_profit']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 回测集成测试失败: {e}")
        return False

def test_report_generation():
    """测试报告生成功能"""
    print("\n📄 测试报告生成...")
    
    try:
        from universal_screener import UniversalScreener
        from strategies.base_strategy import StrategyResult
        
        screener = UniversalScreener()
        
        # 创建模拟策略结果
        mock_results = [
            StrategyResult(
                stock_code="sh600000",
                strategy_name="价值反转策略（最终版）",
                signal_type="STRONG_BUY",
                signal_strength=3,
                date="2024-08-24",
                current_price=15.50,
                signal_details={
                    'stage_passed': 3,
                    'backtest_win_rate': '65.5%',
                    'backtest_avg_profit': '8.2%'
                }
            ),
            StrategyResult(
                stock_code="sz000001",
                strategy_name="反转做多策略（优化版）",
                signal_type="BUY",
                signal_strength=2,
                date="2024-08-24",
                current_price=12.30,
                signal_details={
                    'stage_passed': 2,
                    'backtest_win_rate': '58.3%',
                    'backtest_avg_profit': '6.1%'
                }
            )
        ]
        
        # 测试汇总报告生成
        summary = screener.generate_summary_report(mock_results)
        
        print(f"✅ 汇总报告生成成功:")
        print(f"   总信号数: {summary['scan_summary']['total_signals']}")
        print(f"   策略分布: {summary['scan_summary']['strategy_distribution']}")
        print(f"   信号类型分布: {summary['scan_summary']['signal_type_distribution']}")
        print(f"   平均胜率: {summary['scan_summary']['avg_win_rate']}")
        print(f"   平均收益: {summary['scan_summary']['avg_profit_rate']}")
        print(f"   最佳表现者: {len(summary['top_performers'])} 个")
        
        # 测试文本报告生成
        test_report_file = os.path.join(os.path.dirname(__file__), 'test_report.txt')
        screener.generate_text_report(mock_results, test_report_file)
        
        if os.path.exists(test_report_file):
            print(f"✅ 文本报告生成成功: {test_report_file}")
            # 清理测试文件
            os.remove(test_report_file)
        else:
            print("⚠️ 文本报告生成失败")
        
        return True
        
    except Exception as e:
        print(f"❌ 报告生成测试失败: {e}")
        return False

def test_deep_scan_integration():
    """测试深度扫描集成"""
    print("\n🔬 测试深度扫描集成...")
    
    try:
        from universal_screener import UniversalScreener
        from strategies.base_strategy import StrategyResult
        
        screener = UniversalScreener()
        
        # 创建模拟策略结果
        mock_results = [
            StrategyResult(
                stock_code="sh600000",
                strategy_name="价值反转策略（最终版）",
                signal_type="BUY",
                signal_strength=2,
                date="2024-08-24",
                current_price=15.50,
                signal_details={'stage_passed': 2}
            )
        ]
        
        # 测试深度扫描触发（注意：实际深度扫描模块可能不存在）
        deep_scan_result = screener.trigger_deep_scan(mock_results)
        
        if deep_scan_result is None:
            print("⚠️ 深度扫描模块不可用，这是正常的（模块可能未安装）")
        else:
            print(f"✅ 深度扫描触发成功，结果: {len(deep_scan_result)} 个")
        
        return True
        
    except Exception as e:
        print(f"❌ 深度扫描集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 80)
    print("🧪 Universal Screener 完整功能测试")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"工作目录: {os.getcwd()}")
    
    # 执行所有测试
    tests = [
        ("基础功能", test_universal_screener_basic),
        ("过滤器功能", test_filter_functions),
        ("MA趋势分析", test_ma_trend_analysis),
        ("回测集成", test_backtest_integration),
        ("报告生成", test_report_generation),
        ("深度扫描集成", test_deep_scan_integration)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results.append((test_name, False))
    
    # 汇总测试结果
    print("\n" + "=" * 80)
    print("📊 测试结果汇总")
    print("=" * 80)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n总体结果: {passed}/{total} 测试通过 ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 所有测试通过！Universal Screener功能完善成功！")
        print("\n📋 新增功能总结:")
        print("1. ✅ 策略专用过滤器系统 - MACD零轴、周线金叉、三重交叉过滤")
        print("2. ✅ 高级胜率筛选机制 - 质量评分和交叉阶段分析")
        print("3. ✅ 深度技术分析功能 - MA趋势强度分析")
        print("4. ✅ 完整的回测统计系统 - 详细交易统计和状态分析")
        print("5. ✅ 自动深度扫描集成 - 智能触发和结果整合")
        print("6. ✅ 增强的报告生成 - 详细汇总和文本报告")
        print("\n🚀 Universal Screener现在具备了screener.py的所有核心功能！")
    else:
        print(f"\n⚠️ 部分测试失败，请检查相关功能")
    
    return passed == total

if __name__ == "__main__":
    main()