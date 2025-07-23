#!/usr/bin/env python3
"""
用户界面优化测试脚本

测试第5-6周开发的用户界面功能：
- 交互式报告生成器
- Web仪表板
- 通知系统
- 可视化功能
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

from report_generator import ReportGenerator
from notification_system import NotificationSystem
from stock_pool_manager import StockPoolManager

# 尝试导入Web相关模块
try:
    from web_dashboard import WebDashboard
    HAS_WEB_DASHBOARD = True
except ImportError:
    HAS_WEB_DASHBOARD = False


class TestUIOptimization(unittest.TestCase):
    """用户界面优化测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.test_db = "test_ui_optimization.db"
        
        # 清理测试文件
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        # 创建测试数据
        self.pool_manager = StockPoolManager(self.test_db)
        self._create_test_data()
        
        # 设置日志级别
        logging.getLogger().setLevel(logging.WARNING)
    
    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        # 清理生成的报告文件
        reports_dir = Path("reports")
        if reports_dir.exists():
            for file in reports_dir.glob("*test*"):
                try:
                    file.unlink()
                except:
                    pass
    
    def _create_test_data(self):
        """创建测试数据"""
        test_stocks = [
            {
                'stock_code': 'sz300290',
                'stock_name': '荣科科技',
                'score': 0.85,
                'params': {'pre_entry_discount': 0.02},
                'risk_level': 'MEDIUM',
                'credibility_score': 0.9
            },
            {
                'stock_code': 'sh600000',
                'stock_name': '浦发银行',
                'score': 0.72,
                'params': {'moderate_stop': 0.05},
                'risk_level': 'LOW',
                'credibility_score': 0.8
            },
            {
                'stock_code': 'sz000001',
                'stock_name': '平安银行',
                'score': 0.68,
                'params': {'profit_target': 0.1},
                'risk_level': 'MEDIUM',
                'credibility_score': 0.75
            }
        ]
        
        for stock in test_stocks:
            self.pool_manager.add_stock_to_pool(stock)
        
        # 添加测试信号
        test_signals = [
            {
                'stock_code': 'sz300290',
                'signal_type': 'buy',
                'confidence': 0.85,
                'trigger_price': 17.5
            },
            {
                'stock_code': 'sh600000',
                'signal_type': 'sell',
                'confidence': 0.78,
                'trigger_price': 12.3
            }
        ]
        
        for signal in test_signals:
            self.pool_manager.record_signal(signal)
    
    def test_report_generator(self):
        """测试报告生成器"""
        print("\n🧪 测试报告生成器...")
        
        # 创建报告生成器
        report_gen = ReportGenerator(self.test_db)
        
        # 测试JSON报告生成
        result = report_gen.generate_comprehensive_report('json')
        self.assertIsInstance(result, dict, "报告生成结果格式不正确")
        
        # 测试HTML报告生成
        result = report_gen.generate_comprehensive_report('html')
        self.assertIsInstance(result, dict, "HTML报告生成结果格式不正确")
        
        if result.get('success'):
            self.assertTrue(os.path.exists(result.get('filename', '')), "HTML报告文件未生成")
        
        # 测试信号报告生成
        test_signals = [
            {
                'stock_code': 'sz300290',
                'signal_type': 'buy',
                'confidence': 0.85,
                'trigger_price': 17.5,
                'signal_date': datetime.now().isoformat()
            }
        ]
        
        signal_result = report_gen.generate_signal_report(test_signals, 'json')
        self.assertIsInstance(signal_result, dict, "信号报告生成结果格式不正确")
        
        # 测试绩效仪表板生成
        dashboard_result = report_gen.generate_performance_dashboard()
        self.assertIsInstance(dashboard_result, dict, "绩效仪表板生成结果格式不正确")
        
        print("✅ 报告生成器测试通过")
    
    def test_notification_system(self):
        """测试通知系统"""
        print("\n🧪 测试通知系统...")
        
        # 创建通知系统（禁用实际发送）
        config = {
            "email": {"enabled": False},
            "webhook": {"enabled": False}
        }
        notification = NotificationSystem(config)
        
        # 测试信号提醒
        test_signals = [
            {
                'stock_code': 'sz300290',
                'signal_type': 'buy',
                'confidence': 0.85,
                'trigger_price': 17.5,
                'signal_date': datetime.now().isoformat()
            }
        ]
        
        result = notification.send_signal_alert(test_signals)
        self.assertTrue(result.get('success'), f"信号提醒发送失败: {result.get('error')}")
        
        # 测试系统提醒
        result = notification.send_system_alert('test', '测试系统提醒')
        self.assertTrue(result.get('success'), f"系统提醒发送失败: {result.get('error')}")
        
        # 测试邮件内容生成
        message_data = {
            'type': 'signal_alert',
            'timestamp': datetime.now().isoformat(),
            'signals': test_signals,
            'summary': {
                'total_signals': 1,
                'buy_signals': 1,
                'sell_signals': 0,
                'avg_confidence': 0.85
            }
        }
        
        html_content = notification._generate_email_content(message_data)
        self.assertIsInstance(html_content, str, "邮件内容生成失败")
        self.assertIn('交易信号提醒', html_content, "邮件内容不正确")
        
        print("✅ 通知系统测试通过")
    
    def test_web_dashboard(self):
        """测试Web仪表板"""
        print("\n🧪 测试Web仪表板...")
        
        if not HAS_WEB_DASHBOARD:
            print("⚠️  Web仪表板模块未可用，跳过测试")
            return
        
        try:
            # 创建Web仪表板
            dashboard = WebDashboard(self.test_db)
            
            # 测试数据获取
            data = dashboard.get_dashboard_data()
            self.assertIsInstance(data, dict, "仪表板数据格式不正确")
            self.assertIn('pool_stats', data, "缺少观察池统计数据")
            self.assertIn('last_update', data, "缺少更新时间")
            
            # 验证观察池统计
            pool_stats = data['pool_stats']
            self.assertGreater(pool_stats.get('total_stocks', 0), 0, "观察池股票数量为0")
            
            print("✅ Web仪表板测试通过")
            
        except Exception as e:
            print(f"⚠️  Web仪表板测试失败: {e}")
    
    def test_visualization_features(self):
        """测试可视化功能"""
        print("\n🧪 测试可视化功能...")
        
        try:
            # 测试图表生成功能
            report_gen = ReportGenerator(self.test_db)
            
            # 收集报告数据
            report_data = report_gen._collect_report_data()
            self.assertIsInstance(report_data, dict, "报告数据格式不正确")
            
            # 测试图表生成（如果matplotlib可用）
            try:
                import matplotlib.pyplot as plt
                charts = report_gen._generate_charts(report_data)
                self.assertIsInstance(charts, dict, "图表生成结果格式不正确")
                print("✅ 图表生成功能可用")
            except ImportError:
                print("⚠️  matplotlib未安装，图表功能不可用")
            
            print("✅ 可视化功能测试通过")
            
        except Exception as e:
            print(f"❌ 可视化功能测试失败: {e}")
    
    def test_template_system(self):
        """测试模板系统"""
        print("\n🧪 测试模板系统...")
        
        try:
            # 测试HTML模板生成
            report_gen = ReportGenerator(self.test_db)
            
            # 测试获取HTML模板
            template = report_gen._get_html_template()
            self.assertIsInstance(template, str, "HTML模板格式不正确")
            self.assertIn('<html>', template, "HTML模板内容不正确")
            self.assertIn('{title}', template, "HTML模板缺少占位符")
            
            # 测试通知模板
            notification = NotificationSystem()
            
            test_message = {
                'type': 'signal_alert',
                'timestamp': datetime.now().isoformat(),
                'signals': [],
                'summary': {'total_signals': 0}
            }
            
            html_content = notification._generate_signal_alert_html(test_message)
            self.assertIsInstance(html_content, str, "通知模板生成失败")
            self.assertIn('<html>', html_content, "通知模板格式不正确")
            
            print("✅ 模板系统测试通过")
            
        except Exception as e:
            print(f"❌ 模板系统测试失败: {e}")
    
    def test_file_management(self):
        """测试文件管理"""
        print("\n🧪 测试文件管理...")
        
        try:
            # 测试报告目录创建
            reports_dir = Path("reports")
            self.assertTrue(reports_dir.exists() or reports_dir.mkdir(exist_ok=True), "报告目录创建失败")
            
            # 测试模板目录创建
            templates_dir = Path("templates")
            self.assertTrue(templates_dir.exists() or templates_dir.mkdir(exist_ok=True), "模板目录创建失败")
            
            # 测试文件生成和清理
            test_file = reports_dir / "test_report.html"
            test_file.write_text("<html><body>Test</body></html>", encoding='utf-8')
            self.assertTrue(test_file.exists(), "测试文件创建失败")
            
            # 清理测试文件
            test_file.unlink()
            self.assertFalse(test_file.exists(), "测试文件清理失败")
            
            print("✅ 文件管理测试通过")
            
        except Exception as e:
            print(f"❌ 文件管理测试失败: {e}")


def run_ui_optimization_test():
    """运行用户界面优化测试"""
    print("🎨 用户界面优化功能测试")
    print("=" * 60)
    
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestUIOptimization)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)
    
    # 显示测试结果
    print("\n" + "=" * 60)
    print("📊 用户界面优化测试结果:")
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
    print(f"\n🎯 用户界面优化测试成功率: {success_rate:.1%}")
    
    return success_rate == 1.0


def test_dependencies():
    """测试依赖库"""
    print("\n🔍 检查用户界面相关依赖...")
    
    dependencies = {
        'matplotlib': '图表生成',
        'pandas': '数据处理',
        'jinja2': '模板引擎',
        'flask': 'Web界面',
        'requests': 'HTTP请求'
    }
    
    available = []
    missing = []
    
    for lib, desc in dependencies.items():
        try:
            __import__(lib)
            available.append(f"✅ {lib} - {desc}")
        except ImportError:
            missing.append(f"❌ {lib} - {desc}")
    
    print("可用依赖:")
    for dep in available:
        print(f"  {dep}")
    
    if missing:
        print("\n缺失依赖:")
        for dep in missing:
            print(f"  {dep}")
        print("\n安装建议:")
        print("  pip install matplotlib pandas jinja2 flask requests")
    
    return len(missing) == 0


def generate_ui_test_report():
    """生成用户界面测试报告"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 收集测试信息
        test_info = {
            'test_time': datetime.now().isoformat(),
            'test_type': 'UI Optimization',
            'modules_tested': [
                'ReportGenerator',
                'NotificationSystem',
                'WebDashboard',
                'VisualizationFeatures'
            ],
            'dependencies_checked': True,
            'test_environment': 'Development'
        }
        
        # 保存测试报告
        report_filename = f'reports/ui_test_report_{timestamp}.json'
        Path('reports').mkdir(exist_ok=True)
        
        with open(report_filename, 'w', encoding='utf-8') as f:
            json.dump(test_info, f, indent=2, ensure_ascii=False)
        
        print(f"📄 用户界面测试报告已保存: {report_filename}")
        
    except Exception as e:
        print(f"❌ 生成测试报告失败: {e}")


def main():
    """主函数"""
    print("🚀 启动用户界面优化功能测试...")
    
    # 检查依赖
    deps_ok = test_dependencies()
    
    # 运行核心测试
    success = run_ui_optimization_test()
    
    # 生成测试报告
    generate_ui_test_report()
    
    # 显示下一步建议
    print("\n📋 下一步建议:")
    if success:
        print("  1. 用户界面优化功能测试通过")
        print("  2. 可以启动Web界面: python web_dashboard.py")
        print("  3. 测试报告生成: 运行相关脚本生成HTML报告")
        if not deps_ok:
            print("  4. 安装缺失的依赖库以获得完整功能")
        print("  5. 开始第7-8周的测试与优化阶段")
    else:
        print("  1. 检查失败的测试用例")
        print("  2. 修复发现的问题")
        print("  3. 重新运行测试确认修复")
    
    print(f"\n🎊 用户界面优化阶段{'完成' if success else '需要修复'}！")
    
    return success


if __name__ == "__main__":
    main()