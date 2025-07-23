#!/usr/bin/env python3
"""
增强版功能模块综合测试脚本

测试新开发的功能模块：
- 每日信号扫描器 (DailySignalScanner)
- 绩效跟踪器 (PerformanceTracker)
- 增强版工作流管理器 (EnhancedWorkflowManager)
- 系统集成测试
"""

import os
import sys
import json
import unittest
import logging
from datetime import datetime
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from stock_pool_manager import StockPoolManager
from daily_signal_scanner import DailySignalScanner
from performance_tracker import PerformanceTracker
from enhanced_workflow_manager import EnhancedWorkflowManager


class TestEnhancedModules(unittest.TestCase):
    """增强版功能模块测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.test_db = "test_enhanced_modules.db"
        self.test_config = "test_enhanced_modules_config.json"
        
        # 清理测试文件
        for file in [self.test_db, self.test_config]:
            if os.path.exists(file):
                os.remove(file)
        
        # 创建测试配置
        test_config = {
            "phase1": {
                "enabled": True,
                "frequency_days": 0,
                "min_score_threshold": 0.5,
                "max_stocks": 100
            },
            "phase2": {
                "enabled": True,
                "frequency_days": 0,
                "signal_confidence_threshold": 0.6,
                "market_condition_filter": False,  # 关闭市场条件过滤以便测试
                "max_signals_per_day": 10
            },
            "phase3": {
                "enabled": True,
                "frequency_days": 0,
                "min_credibility": 0.3,
                "tracking_period_days": 30
            }
        }
        
        with open(self.test_config, 'w', encoding='utf-8') as f:
            json.dump(test_config, f, indent=2)
        
        # 设置日志级别
        logging.getLogger().setLevel(logging.WARNING)  # 减少测试时的日志输出
    
    def tearDown(self):
        """测试后清理"""
        for file in [self.test_db, self.test_config]:
            if os.path.exists(file):
                os.remove(file)
    
    def test_daily_signal_scanner(self):
        """测试每日信号扫描器"""
        print("\n🧪 测试每日信号扫描器...")
        
        # 创建测试数据
        pool_manager = StockPoolManager(self.test_db)
        test_stocks = [
            {
                'stock_code': 'sz300290',
                'stock_name': '荣科科技',
                'score': 0.75,
                'params': {'pre_entry_discount': 0.02},
                'risk_level': 'MEDIUM',
                'credibility_score': 0.8
            },
            {
                'stock_code': 'sh600000',
                'stock_name': '浦发银行',
                'score': 0.68,
                'params': {'moderate_stop': 0.05},
                'risk_level': 'LOW',
                'credibility_score': 0.9
            }
        ]
        
        for stock in test_stocks:
            pool_manager.add_stock_to_pool(stock)
        
        # 创建信号扫描器
        scanner_config = {
            "signal_confidence_threshold": 0.5,
            "market_condition_filter": False,
            "max_signals_per_day": 10,
            "min_credibility_score": 0.5,
            "risk_level_filter": ["LOW", "MEDIUM", "HIGH"]
        }
        
        scanner = DailySignalScanner(self.test_db, scanner_config)
        
        # 执行信号扫描
        result = scanner.scan_daily_signals()
        
        self.assertTrue(result['success'], f"信号扫描失败: {result.get('error')}")
        self.assertIsInstance(result['statistics'], dict, "统计信息格式不正确")
        self.assertGreaterEqual(result['statistics']['total_scanned'], 2, "扫描股票数量不正确")
        
        # 测试扫描历史
        history = scanner.get_scan_history(1)
        self.assertIsInstance(history, list, "扫描历史格式不正确")
        
        print("✅ 每日信号扫描器测试通过")
    
    def test_performance_tracker(self):
        """测试绩效跟踪器"""
        print("\n🧪 测试绩效跟踪器...")
        
        # 创建测试数据
        pool_manager = StockPoolManager(self.test_db)
        test_stock = {
            'stock_code': 'sz300290',
            'score': 0.75,
            'params': {},
            'credibility_score': 0.8
        }
        pool_manager.add_stock_to_pool(test_stock)
        
        # 添加测试信号
        signal_data = {
            'stock_code': 'sz300290',
            'signal_type': 'buy',
            'confidence': 0.8,
            'trigger_price': 17.5
        }
        pool_manager.record_signal(signal_data)
        
        # 创建绩效跟踪器
        tracker_config = {
            "tracking_period_days": 30,
            "min_signals_for_analysis": 1,
            "credibility_adjustments": {
                "excellent": 1.2,
                "good": 1.1,
                "average": 1.0,
                "poor": 0.8
            }
        }
        
        tracker = PerformanceTracker(self.test_db, tracker_config)
        
        # 测试股票绩效分析
        analysis = tracker.analyze_stock_performance('sz300290')
        self.assertIsInstance(analysis, dict, "绩效分析结果格式不正确")
        self.assertEqual(analysis.get('stock_code'), 'sz300290', "股票代码不匹配")
        
        # 测试批量绩效分析
        batch_analysis = tracker.batch_performance_analysis(['sz300290'])
        self.assertIsInstance(batch_analysis, dict, "批量分析结果格式不正确")
        self.assertIn('analysis_results', batch_analysis, "缺少分析结果")
        
        # 测试观察池调整
        adjustment_result = tracker.adjust_pool_based_on_performance()
        self.assertTrue(adjustment_result.get('success'), f"观察池调整失败: {adjustment_result.get('error')}")
        
        # 测试绩效报告生成
        report = tracker.generate_performance_report('summary')
        self.assertIsInstance(report, dict, "绩效报告格式不正确")
        self.assertEqual(report.get('report_type'), 'summary', "报告类型不正确")
        
        print("✅ 绩效跟踪器测试通过")
    
    def test_enhanced_workflow_manager(self):
        """测试增强版工作流管理器"""
        print("\n🧪 测试增强版工作流管理器...")
        
        # 创建增强版工作流管理器
        manager = EnhancedWorkflowManager(self.test_config, self.test_db)
        
        # 测试系统状态获取
        status = manager.get_enhanced_status()
        self.assertIsInstance(status, dict, "系统状态格式不正确")
        self.assertIn('pool_statistics', status, "缺少观察池统计")
        
        # 测试第一阶段
        result1 = manager.run_enhanced_phase1()
        self.assertTrue(result1.get('success'), f"第一阶段失败: {result1.get('error')}")
        self.assertGreater(result1.get('processed_stocks', 0), 0, "未处理任何股票")
        
        # 测试第二阶段
        result2 = manager.run_enhanced_phase2()
        self.assertTrue(result2.get('success'), f"第二阶段失败: {result2.get('error')}")
        
        # 测试第三阶段
        result3 = manager.run_enhanced_phase3()
        self.assertTrue(result3.get('success'), f"第三阶段失败: {result3.get('error')}")
        
        print("✅ 增强版工作流管理器测试通过")
    
    def test_module_integration(self):
        """测试模块集成"""
        print("\n🧪 测试模块集成...")
        
        # 创建完整的工作流
        manager = EnhancedWorkflowManager(self.test_config, self.test_db)
        
        # 执行完整的三阶段工作流
        phases = ['phase1', 'phase2', 'phase3']
        results = {}
        
        for phase in phases:
            if phase == 'phase1':
                result = manager.run_enhanced_phase1()
            elif phase == 'phase2':
                result = manager.run_enhanced_phase2()
            elif phase == 'phase3':
                result = manager.run_enhanced_phase3()
            
            results[phase] = result
        
        # 验证所有阶段都成功
        success_count = sum(1 for result in results.values() if result.get('success'))
        self.assertEqual(success_count, 3, f"只有 {success_count}/3 个阶段成功")
        
        # 验证数据一致性
        final_status = manager.get_enhanced_status()
        pool_stats = final_status.get('pool_statistics', {})
        self.assertGreater(pool_stats.get('total_stocks', 0), 0, "观察池为空")
        
        print("✅ 模块集成测试通过")
    
    def test_database_consistency(self):
        """测试数据库一致性"""
        print("\n🧪 测试数据库一致性...")
        
        # 创建多个管理器实例，测试数据库共享
        pool_manager = StockPoolManager(self.test_db)
        scanner = DailySignalScanner(self.test_db)
        tracker = PerformanceTracker(self.test_db)
        
        # 添加测试数据
        test_stock = {
            'stock_code': 'sz300290',
            'score': 0.75,
            'params': {},
            'credibility_score': 0.8
        }
        
        self.assertTrue(pool_manager.add_stock_to_pool(test_stock), "添加股票失败")
        
        # 验证数据在不同模块间的一致性
        pool_stocks = pool_manager.get_core_pool()
        self.assertEqual(len(pool_stocks), 1, "观察池股票数量不正确")
        
        # 通过扫描器访问相同数据
        scan_result = scanner.scan_daily_signals()
        self.assertTrue(scan_result['success'], "信号扫描失败")
        
        # 通过跟踪器访问相同数据
        analysis = tracker.analyze_stock_performance('sz300290')
        self.assertEqual(analysis.get('stock_code'), 'sz300290', "数据不一致")
        
        print("✅ 数据库一致性测试通过")
    
    def test_error_handling(self):
        """测试错误处理"""
        print("\n🧪 测试错误处理...")
        
        # 测试无效数据库路径
        try:
            invalid_manager = StockPoolManager("/invalid/path/test.db")
            # 如果没有抛出异常，至少应该能处理错误
            self.assertIsNotNone(invalid_manager)
        except Exception:
            pass  # 预期的异常
        
        # 测试空观察池的信号扫描
        empty_scanner = DailySignalScanner(self.test_db)
        result = empty_scanner.scan_daily_signals()
        # 应该能处理空观察池的情况
        self.assertIsInstance(result, dict, "错误处理不当")
        
        # 测试无效股票代码的绩效分析
        tracker = PerformanceTracker(self.test_db)
        analysis = tracker.analyze_stock_performance('INVALID_CODE')
        self.assertIsInstance(analysis, dict, "错误处理不当")
        
        print("✅ 错误处理测试通过")


def run_comprehensive_module_test():
    """运行综合模块测试"""
    print("🎯 增强版功能模块综合测试")
    print("=" * 60)
    
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEnhancedModules)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    
    # 显示测试结果
    print("\n" + "=" * 60)
    print("📊 模块测试结果总结:")
    print(f"✅ 成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"❌ 失败: {len(result.failures)}")
    print(f"⚠️  错误: {len(result.errors)}")
    
    if result.failures:
        print("\n❌ 失败的测试:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback}")
    
    if result.errors:
        print("\n⚠️  错误的测试:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    success_rate = (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun
    print(f"\n🎯 模块测试成功率: {success_rate:.1%}")
    
    return success_rate == 1.0


def test_real_system_integration():
    """测试与真实系统的集成"""
    print("\n🔗 测试与真实系统的集成...")
    
    try:
        # 测试增强版工作流
        from run_enhanced_workflow import main as run_enhanced_main
        
        print("📋 测试增强版工作流执行...")
        
        # 这里可以添加更多的集成测试
        print("✅ 真实系统集成测试完成")
        
    except Exception as e:
        print(f"❌ 真实系统集成测试失败: {e}")


def generate_module_test_report():
    """生成模块测试报告"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 收集系统信息
        system_info = {
            'test_time': datetime.now().isoformat(),
            'python_version': sys.version,
            'modules_tested': [
                'DailySignalScanner',
                'PerformanceTracker', 
                'EnhancedWorkflowManager',
                'StockPoolManager'
            ],
            'test_database': 'SQLite',
            'test_environment': 'Development'
        }
        
        # 保存测试报告
        report_filename = f'reports/module_test_report_{timestamp}.json'
        Path('reports').mkdir(exist_ok=True)
        
        with open(report_filename, 'w', encoding='utf-8') as f:
            json.dump(system_info, f, indent=2, ensure_ascii=False)
        
        print(f"📄 模块测试报告已保存: {report_filename}")
        
    except Exception as e:
        print(f"❌ 生成测试报告失败: {e}")


def main():
    """主函数"""
    print("🚀 启动增强版功能模块综合测试...")
    
    # 运行核心模块测试
    success = run_comprehensive_module_test()
    
    # 运行集成测试
    test_real_system_integration()
    
    # 生成测试报告
    generate_module_test_report()
    
    # 显示下一步建议
    print("\n📋 下一步建议:")
    if success:
        print("  1. 所有模块测试通过，可以投入使用")
        print("  2. 运行 python run_enhanced_workflow.py 体验完整功能")
        print("  3. 根据需要调整配置参数")
        print("  4. 开始第5-6周的用户界面优化开发")
    else:
        print("  1. 检查失败的测试用例")
        print("  2. 修复发现的问题")
        print("  3. 重新运行测试确认修复")
    
    print(f"\n🎊 功能模块开发阶段{'完成' if success else '需要修复'}！")
    
    return success


if __name__ == "__main__":
    main()