#!/usr/bin/env python3
"""
多周期分析系统测试脚本
验证所有核心组件的功能
"""

import sys
import os
from datetime import datetime

# 添加backend目录到路径
sys.path.append('backend')

def test_data_manager():
    """测试数据管理器"""
    print("🔍 测试多周期数据管理器...")
    
    try:
        from backend.multi_timeframe_data_manager import MultiTimeframeDataManager
        
        manager = MultiTimeframeDataManager()
        
        # 测试获取多周期数据
        result = manager.get_synchronized_data('sz300290')
        
        if 'error' not in result:
            timeframes = result.get('timeframes', {})
            print(f"  ✅ 成功获取 {len(timeframes)} 个时间周期的数据")
            
            # 测试指标计算
            indicators_result = manager.calculate_multi_timeframe_indicators('sz300290')
            if 'error' not in indicators_result:
                indicators_timeframes = indicators_result.get('timeframes', {})
                print(f"  ✅ 成功计算 {len(indicators_timeframes)} 个时间周期的指标")
                return True
            else:
                print(f"  ❌ 指标计算失败: {indicators_result['error']}")
                return False
        else:
            print(f"  ❌ 数据获取失败: {result['error']}")
            return False
            
    except Exception as e:
        print(f"  ❌ 数据管理器测试失败: {e}")
        return False

def test_signal_generator():
    """测试信号生成器"""
    print("🔍 测试多周期信号生成器...")
    
    try:
        from backend.multi_timeframe_data_manager import MultiTimeframeDataManager
        from backend.multi_timeframe_signal_generator import MultiTimeframeSignalGenerator
        
        data_manager = MultiTimeframeDataManager()
        signal_generator = MultiTimeframeSignalGenerator(data_manager)
        
        # 测试信号生成
        signals = signal_generator.generate_composite_signals('sz300290')
        
        if 'error' not in signals:
            composite_signal = signals.get('composite_signal', {})
            final_score = composite_signal.get('final_score', 0)
            signal_strength = composite_signal.get('signal_strength', 'unknown')
            confidence_level = composite_signal.get('confidence_level', 0)
            
            print(f"  ✅ 信号生成成功")
            print(f"    信号强度: {signal_strength}")
            print(f"    最终评分: {final_score:.3f}")
            print(f"    置信度: {confidence_level:.3f}")
            
            # 检查策略信号
            strategy_signals = signals.get('strategy_signals', {})
            print(f"    策略数量: {len(strategy_signals)}")
            
            return True
        else:
            print(f"  ❌ 信号生成失败: {signals['error']}")
            return False
            
    except Exception as e:
        print(f"  ❌ 信号生成器测试失败: {e}")
        return False

def test_report_generator():
    """测试报告生成器"""
    print("🔍 测试多周期报告生成器...")
    
    try:
        from backend.multi_timeframe_report_generator import MultiTimeframeReportGenerator
        
        report_generator = MultiTimeframeReportGenerator()
        
        # 测试每日报告生成
        daily_report = report_generator.generate_daily_multi_timeframe_report(['sz300290'])
        
        if 'error' not in daily_report:
            summary = daily_report.get('summary', {})
            stock_analysis = daily_report.get('stock_analysis', {})
            recommendations = daily_report.get('recommendations', {})
            
            print(f"  ✅ 每日报告生成成功")
            print(f"    分析股票数: {summary.get('total_stocks_analyzed', 0)}")
            print(f"    成功分析数: {summary.get('successful_analysis', 0)}")
            print(f"    市场情绪: {summary.get('market_sentiment', 'unknown')}")
            print(f"    买入建议数: {len(recommendations.get('buy_list', []))}")
            print(f"    卖出建议数: {len(recommendations.get('sell_list', []))}")
            
            return True
        else:
            print(f"  ❌ 报告生成失败: {daily_report['error']}")
            return False
            
    except Exception as e:
        print(f"  ❌ 报告生成器测试失败: {e}")
        return False

def test_monitor():
    """测试监控系统"""
    print("🔍 测试多周期监控系统...")
    
    try:
        from backend.multi_timeframe_monitor import MultiTimeframeMonitor
        
        monitor = MultiTimeframeMonitor()
        
        # 测试添加监控股票
        success = monitor.add_stock_to_monitor('sz300290')
        if success:
            print(f"  ✅ 成功添加监控股票")
            
            # 测试获取监控状态
            status = monitor.get_monitoring_status()
            print(f"    监控股票数: {status.get('monitored_stocks_count', 0)}")
            print(f"    监控活跃: {status.get('monitoring_active', False)}")
            
            # 测试手动更新信号
            monitor._update_stock_signal('sz300290')
            
            # 获取信号历史
            history = monitor.get_stock_signal_history('sz300290', 1)
            if history:
                print(f"    信号历史记录: {len(history)} 条")
            
            return True
        else:
            print(f"  ❌ 添加监控股票失败")
            return False
            
    except Exception as e:
        print(f"  ❌ 监控系统测试失败: {e}")
        return False

def test_integration():
    """测试系统集成"""
    print("🔍 测试系统集成...")
    
    try:
        from run_multi_timeframe_analysis import MultiTimeframeAnalysisSystem
        
        system = MultiTimeframeAnalysisSystem()
        
        # 测试数据质量检查
        quality_report = system._check_data_quality(['sz300290'])
        print(f"  ✅ 数据质量检查完成")
        print(f"    可用股票数: {quality_report.get('available_stocks', 0)}")
        
        # 测试信号分析
        signal_results = system._analyze_signals(['sz300290'])
        print(f"  ✅ 信号分析完成")
        print(f"    成功分析数: {signal_results.get('successful_analysis', 0)}")
        print(f"    强信号数: {len(signal_results.get('strong_signals', []))}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 系统集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🧪 多周期分析系统全面测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    test_results = []
    
    # 执行各项测试
    tests = [
        ("数据管理器", test_data_manager),
        ("信号生成器", test_signal_generator),
        ("报告生成器", test_report_generator),
        ("监控系统", test_monitor),
        ("系统集成", test_integration)
    ]
    
    for test_name, test_func in tests:
        print(f"📋 测试项目: {test_name}")
        try:
            result = test_func()
            test_results.append((test_name, result))
            if result:
                print(f"✅ {test_name} 测试通过\n")
            else:
                print(f"❌ {test_name} 测试失败\n")
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}\n")
            test_results.append((test_name, False))
    
    # 测试结果汇总
    print("📊 测试结果汇总")
    print("=" * 60)
    
    passed_tests = sum(1 for _, result in test_results if result)
    total_tests = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n📈 测试统计:")
    print(f"  总测试数: {total_tests}")
    print(f"  通过数: {passed_tests}")
    print(f"  失败数: {total_tests - passed_tests}")
    print(f"  通过率: {passed_tests/total_tests*100:.1f}%")
    
    if passed_tests == total_tests:
        print(f"\n🎉 所有测试通过！多周期分析系统运行正常")
        return True
    else:
        print(f"\n⚠️  部分测试失败，请检查相关组件")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)