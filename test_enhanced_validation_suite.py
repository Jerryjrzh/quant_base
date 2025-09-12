#!/usr/bin/env python3
"""
测试增强版验证套件功能
演示新增的调试、回测和性能分析功能
"""

import sys
import os
from datetime import datetime, timedelta

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

from validation_suite import ValidationSuite

def test_basic_validation():
    """测试基础验证功能"""
    print("🧪 测试基础验证功能")
    print("=" * 50)
    
    try:
        # 创建验证套件实例
        suite = ValidationSuite(
            strategy_id='MACD零轴启动_v1.0',
            debug_mode=True
        )
        
        # 测试单只股票验证
        result = suite.run_validation_for_stock('sh600000', enable_backtest=True)
        
        print(f"✅ 基础验证测试完成")
        print(f"   股票代码: {result['stock_code']}")
        print(f"   处理时间: {result['processing_time']:.3f}s")
        print(f"   是否有错误: {'是' if result.get('error') else '否'}")
        
        return True
        
    except Exception as e:
        print(f"❌ 基础验证测试失败: {e}")
        return False

def test_batch_validation():
    """测试批量验证功能"""
    print("\n🧪 测试批量验证功能")
    print("=" * 50)
    
    try:
        suite = ValidationSuite(
            strategy_id='MACD零轴启动_v1.0',
            debug_mode=True
        )
        
        # 测试批量处理
        test_stocks = ['sh600000', 'sh600036', 'sh600519']
        results = suite.run_suite(
            stock_codes=test_stocks,
            enable_backtest=True,
            export_results=False  # 测试时不导出文件
        )
        
        print(f"✅ 批量验证测试完成")
        print(f"   成功处理: {len(results['successful_results'])} 只")
        print(f"   处理失败: {len(results['failed_results'])} 只")
        print(f"   总处理时间: {results['performance_stats']['total_time']:.2f}s")
        
        return True
        
    except Exception as e:
        print(f"❌ 批量验证测试失败: {e}")
        return False

def test_historical_backtest():
    """测试历史回测功能"""
    print("\n🧪 测试历史回测功能")
    print("=" * 50)
    
    try:
        suite = ValidationSuite(
            strategy_id='MACD零轴启动_v1.0',
            debug_mode=True
        )
        
        # 设置回测参数
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)  # 回测最近30天
        
        results = suite.run_historical_backtest(
            stock_codes=['sh600000'],
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            step_days=7
        )
        
        print(f"✅ 历史回测测试完成")
        print(f"   回测结果数: {len(results['backtest_results'])}")
        print(f"   测试日期数: {results['analysis']['unique_dates']}")
        print(f"   Layer0通过率: {results['analysis']['success_rate_by_layer'].get('layer0', 0):.1%}")
        
        return True
        
    except Exception as e:
        print(f"❌ 历史回测测试失败: {e}")
        return False

def test_performance_analysis():
    """测试性能分析功能"""
    print("\n🧪 测试性能分析功能")
    print("=" * 50)
    
    try:
        suite = ValidationSuite(
            strategy_id='MACD零轴启动_v1.0',
            debug_mode=True
        )
        
        # 运行一些验证以生成性能数据
        test_stocks = ['sh600000', 'sh600036']
        suite.run_suite(stock_codes=test_stocks, enable_backtest=False)
        
        # 生成性能报告
        report = suite.generate_performance_report()
        
        if 'error' not in report:
            print(f"✅ 性能分析测试完成")
            print(f"   分析股票数: {report['overview']['total_stocks']}")
            print(f"   平均处理时间: {report['overview']['avg_processing_time']:.3f}s")
            print(f"   瓶颈数量: {len(report['bottlenecks'])}")
            print(f"   建议数量: {len(report['recommendations'])}")
            return True
        else:
            print(f"❌ 性能分析失败: {report['error']}")
            return False
        
    except Exception as e:
        print(f"❌ 性能分析测试失败: {e}")
        return False

def test_debug_features():
    """测试调试功能"""
    print("\n🧪 测试调试功能")
    print("=" * 50)
    
    try:
        suite = ValidationSuite(
            strategy_id='MACD零轴启动_v1.0',
            debug_mode=True
        )
        
        # 运行验证以生成调试数据
        result = suite.run_validation_for_stock('sh600000')
        
        print(f"✅ 调试功能测试完成")
        print(f"   调试日志条数: {len(suite.detailed_logs)}")
        print(f"   调试结果记录: {len(suite.debug_results)}")
        print(f"   技术分析数据: {'有' if result.get('technical_analysis') else '无'}")
        
        # 检查调试结果结构
        if suite.debug_results:
            debug_result = suite.debug_results[0]
            layers_count = len(debug_result.get('layers', {}))
            print(f"   分层结果数: {layers_count}")
        
        return True
        
    except Exception as e:
        print(f"❌ 调试功能测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 增强版验证套件功能测试")
    print("=" * 60)
    
    test_results = []
    
    # 执行各项测试
    test_results.append(test_basic_validation())
    test_results.append(test_batch_validation())
    test_results.append(test_historical_backtest())
    test_results.append(test_performance_analysis())
    test_results.append(test_debug_features())
    
    # 总结
    print("\n" + "=" * 60)
    print("📋 测试总结:")
    passed_tests = sum(test_results)
    total_tests = len(test_results)
    
    print(f"   通过测试: {passed_tests}/{total_tests}")
    
    if passed_tests == total_tests:
        print("🎉 所有增强功能测试通过！")
        print("\n💡 使用示例:")
        print("   # 基础验证")
        print("   python backend/validation_suite.py -s MACD零轴启动_v1.0 -c sh600000 --debug")
        print("   # 批量验证并导出结果")
        print("   python backend/validation_suite.py -s MACD零轴启动_v1.0 --limit 10 --export --performance-report --debug")
        print("   # 历史回测")
        print("   python backend/validation_suite.py -s MACD零轴启动_v1.0 -c sh600000 --historical-backtest --start-date 2025-08-01 --end-date 2025-08-26")
    else:
        print("⚠️ 部分测试失败，需要进一步调试")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    main()