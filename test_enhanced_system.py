#!/usr/bin/env python3
"""
增强版三阶段交易决策支持系统 - 综合测试脚本

测试内容：
- 数据库功能测试
- 工作流管理器测试
- 数据迁移测试
- 系统集成测试
"""

import os
import sys
import json
import sqlite3
import unittest
from datetime import datetime
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from stock_pool_manager import StockPoolManager
from enhanced_workflow_manager import EnhancedWorkflowManager


class TestEnhancedSystem(unittest.TestCase):
    """增强版系统测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.test_db = "test_enhanced.db"
        self.test_config = "test_enhanced_config.json"
        
        # 清理测试文件
        for file in [self.test_db, self.test_config]:
            if os.path.exists(file):
                os.remove(file)
        
        # 创建测试配置
        test_config = {
            "phase1": {"enabled": True, "frequency_days": 0, "min_score_threshold": 0.5},
            "phase2": {"enabled": True, "frequency_days": 0, "signal_confidence_threshold": 0.6},
            "phase3": {"enabled": True, "frequency_days": 0, "min_credibility": 0.3}
        }
        
        with open(self.test_config, 'w', encoding='utf-8') as f:
            json.dump(test_config, f, indent=2)
    
    def tearDown(self):
        """测试后清理"""
        for file in [self.test_db, self.test_config]:
            if os.path.exists(file):
                os.remove(file)
    
    def test_database_initialization(self):
        """测试数据库初始化"""
        print("\n🧪 测试数据库初始化...")
        
        manager = StockPoolManager(self.test_db)
        
        # 检查数据库文件是否创建
        self.assertTrue(os.path.exists(self.test_db))
        
        # 检查表结构
        with sqlite3.connect(self.test_db) as conn:
            cursor = conn.cursor()
            
            # 检查核心表
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            expected_tables = ['core_stock_pool', 'signal_history', 'performance_tracking']
            for table in expected_tables:
                self.assertIn(table, tables, f"表 {table} 未创建")
        
        print("✅ 数据库初始化测试通过")
    
    def test_stock_pool_operations(self):
        """测试股票池操作"""
        print("\n🧪 测试股票池操作...")
        
        manager = StockPoolManager(self.test_db)
        
        # 测试添加股票
        test_stock = {
            'stock_code': 'sz300290',
            'stock_name': '荣科科技',
            'score': 0.75,
            'params': {'pre_entry_discount': 0.02, 'moderate_stop': 0.05},
            'risk_level': 'MEDIUM',
            'win_rate': 0.65,
            'avg_return': 0.08
        }
        
        result = manager.add_stock_to_pool(test_stock)
        self.assertTrue(result, "添加股票失败")
        
        # 测试获取观察池
        pool = manager.get_core_pool()
        self.assertEqual(len(pool), 1, "观察池股票数量不正确")
        self.assertEqual(pool[0]['stock_code'], 'sz300290', "股票代码不匹配")
        
        # 测试更新信任度
        result = manager.update_stock_credibility('sz300290', 0.8)
        self.assertTrue(result, "更新信任度失败")
        
        # 验证更新结果
        pool = manager.get_core_pool()
        self.assertEqual(pool[0]['credibility_score'], 0.8, "信任度更新不正确")
        
        print("✅ 股票池操作测试通过")
    
    def test_signal_operations(self):
        """测试信号操作"""
        print("\n🧪 测试信号操作...")
        
        manager = StockPoolManager(self.test_db)
        
        # 先添加股票
        test_stock = {
            'stock_code': 'sz300290',
            'score': 0.75,
            'params': {}
        }
        manager.add_stock_to_pool(test_stock)
        
        # 测试记录信号
        signal_data = {
            'stock_code': 'sz300290',
            'signal_type': 'buy',
            'confidence': 0.8,
            'trigger_price': 17.5,
            'target_price': 19.0,
            'stop_loss': 16.0
        }
        
        result = manager.record_signal(signal_data)
        self.assertTrue(result, "记录信号失败")
        
        # 验证信号计数更新
        pool = manager.get_core_pool()
        self.assertEqual(pool[0]['signal_count'], 1, "信号计数不正确")
        
        print("✅ 信号操作测试通过")
    
    def test_performance_tracking(self):
        """测试绩效跟踪"""
        print("\n🧪 测试绩效跟踪...")
        
        manager = StockPoolManager(self.test_db)
        
        # 添加测试股票
        test_stock = {
            'stock_code': 'sz300290',
            'score': 0.75,
            'params': {}
        }
        manager.add_stock_to_pool(test_stock)
        
        # 获取绩效统计
        performance = manager.get_stock_performance('sz300290')
        self.assertIsInstance(performance, dict, "绩效数据格式不正确")
        self.assertEqual(performance['stock_code'], 'sz300290', "股票代码不匹配")
        
        # 测试观察池调整
        adjustments = manager.adjust_pool_based_on_performance()
        self.assertIsInstance(adjustments, dict, "调整结果格式不正确")
        
        print("✅ 绩效跟踪测试通过")
    
    def test_statistics_and_export(self):
        """测试统计和导出功能"""
        print("\n🧪 测试统计和导出功能...")
        
        manager = StockPoolManager(self.test_db)
        
        # 添加多只测试股票
        for i, code in enumerate(['sz300290', 'sh600000', 'sz000001']):
            test_stock = {
                'stock_code': code,
                'score': 0.6 + i * 0.1,
                'params': {}
            }
            manager.add_stock_to_pool(test_stock)
        
        # 测试统计信息
        stats = manager.get_pool_statistics()
        self.assertIsInstance(stats, dict, "统计信息格式不正确")
        self.assertEqual(stats['total_stocks'], 3, "总股票数不正确")
        self.assertEqual(stats['active_stocks'], 3, "活跃股票数不正确")
        
        # 测试导出功能
        export_file = "test_export.json"
        result = manager.export_to_json(export_file)
        self.assertTrue(result, "导出失败")
        self.assertTrue(os.path.exists(export_file), "导出文件未创建")
        
        # 验证导出内容
        with open(export_file, 'r', encoding='utf-8') as f:
            exported_data = json.load(f)
        
        self.assertEqual(len(exported_data), 3, "导出数据数量不正确")
        
        # 清理导出文件
        os.remove(export_file)
        
        print("✅ 统计和导出功能测试通过")
    
    def test_enhanced_workflow_manager(self):
        """测试增强版工作流管理器"""
        print("\n🧪 测试增强版工作流管理器...")
        
        manager = EnhancedWorkflowManager(self.test_config, self.test_db)
        
        # 测试状态获取
        status = manager.get_enhanced_status()
        self.assertIsInstance(status, dict, "状态信息格式不正确")
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
    
    def test_data_migration(self):
        """测试数据迁移功能"""
        print("\n🧪 测试数据迁移功能...")
        
        # 创建测试JSON文件
        test_json = "test_migration.json"
        test_data = [
            {
                'stock_code': 'sz300290',
                'score': 0.75,
                'params': {'pre_entry_discount': 0.02},
                'analysis_date': datetime.now().isoformat()
            },
            {
                'stock_code': 'sh600000',
                'score': 0.68,
                'params': {'moderate_stop': 0.05},
                'analysis_date': datetime.now().isoformat()
            }
        ]
        
        with open(test_json, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, indent=2)
        
        # 测试导入
        manager = StockPoolManager(self.test_db)
        result = manager.import_from_json(test_json)
        self.assertTrue(result, "数据迁移失败")
        
        # 验证导入结果
        pool = manager.get_core_pool()
        self.assertEqual(len(pool), 2, "导入股票数量不正确")
        
        # 清理测试文件
        os.remove(test_json)
        
        print("✅ 数据迁移功能测试通过")


def run_comprehensive_test():
    """运行综合测试"""
    print("🎯 增强版三阶段交易决策支持系统 - 综合测试")
    print("=" * 60)
    
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestEnhancedSystem)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    
    # 显示测试结果
    print("\n" + "=" * 60)
    print("📊 测试结果总结:")
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
    print(f"\n🎯 总体成功率: {success_rate:.1%}")
    
    if success_rate == 1.0:
        print("\n🎉 所有测试通过！增强版系统功能正常。")
        return True
    else:
        print("\n⚠️  部分测试失败，请检查系统配置。")
        return False


def test_integration_with_existing_system():
    """测试与现有系统的集成"""
    print("\n🔗 测试与现有系统的集成...")
    
    try:
        # 检查是否存在现有数据
        if os.path.exists('core_stock_pool.json'):
            print("📁 发现现有核心观察池数据")
            
            # 创建临时数据库进行测试
            temp_db = "temp_integration_test.db"
            manager = StockPoolManager(temp_db)
            
            # 测试导入现有数据
            result = manager.import_from_json('core_stock_pool.json')
            if result:
                print("✅ 现有数据导入成功")
                
                # 获取统计信息
                stats = manager.get_pool_statistics()
                print(f"📊 导入统计: {stats['total_stocks']} 只股票")
                
                # 测试导出兼容性
                manager.export_to_json("temp_export_test.json")
                print("✅ 数据导出兼容性测试通过")
                
                # 清理临时文件
                os.remove("temp_export_test.json")
            else:
                print("❌ 现有数据导入失败")
            
            # 清理临时数据库
            os.remove(temp_db)
        else:
            print("📁 未发现现有数据，跳过集成测试")
        
        print("✅ 系统集成测试完成")
        
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")


def main():
    """主函数"""
    print("🚀 启动增强版系统综合测试...")
    
    # 运行核心功能测试
    success = run_comprehensive_test()
    
    # 运行集成测试
    test_integration_with_existing_system()
    
    # 显示下一步建议
    print("\n📋 下一步建议:")
    if success:
        print("  1. 运行 python run_enhanced_workflow.py --migrate 迁移现有数据")
        print("  2. 运行 python run_enhanced_workflow.py --status 查看系统状态")
        print("  3. 运行 python run_enhanced_workflow.py 执行完整工作流")
    else:
        print("  1. 检查系统依赖和配置")
        print("  2. 重新运行测试确认问题")
        print("  3. 查看错误日志进行调试")
    
    return success


if __name__ == "__main__":
    main()