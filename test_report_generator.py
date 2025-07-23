#!/usr/bin/env python3
"""
报告生成器专项测试脚本

专门测试报告生成器的：
- 模板系统
- 可视化功能
- HTML报告生成
- 图表生成
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from report_generator import ReportGenerator
from stock_pool_manager import StockPoolManager


def test_report_generator_visualization():
    """测试报告生成器的可视化功能"""
    print("🧪 测试报告生成器可视化功能...")
    
    # 创建测试数据库
    test_db = "test_report_generator.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    
    try:
        # 创建测试数据
        pool_manager = StockPoolManager(test_db)
        test_stocks = [
            {
                'stock_code': 'sz300290',
                'stock_name': '荣科科技',
                'score': 0.75,
                'params': {'pre_entry_discount': 0.02},
                'risk_level': 'MEDIUM',
                'credibility_score': 0.8,
                'grade': 'A'
            },
            {
                'stock_code': 'sh600000',
                'stock_name': '浦发银行',
                'score': 0.68,
                'params': {'moderate_stop': 0.05},
                'risk_level': 'LOW',
                'credibility_score': 0.9,
                'grade': 'B'
            },
            {
                'stock_code': 'sz000001',
                'stock_name': '平安银行',
                'score': 0.82,
                'params': {'aggressive_entry': 0.03},
                'risk_level': 'HIGH',
                'credibility_score': 0.7,
                'grade': 'A'
            }
        ]
        
        for stock in test_stocks:
            pool_manager.add_stock_to_pool(stock)
        
        # 添加一些测试信号
        signals = [
            {
                'stock_code': 'sz300290',
                'signal_type': 'buy',
                'confidence': 0.85,
                'trigger_price': 17.5
            },
            {
                'stock_code': 'sh600000',
                'signal_type': 'sell',
                'confidence': 0.72,
                'trigger_price': 12.3
            }
        ]
        
        for signal in signals:
            pool_manager.record_signal(signal)
        
        # 创建报告生成器
        report_generator = ReportGenerator(test_db)
        
        print("📊 测试综合报告生成...")
        
        # 测试HTML报告生成
        html_result = report_generator.generate_comprehensive_report("html")
        print(f"HTML报告结果: {html_result}")
        
        if html_result.get('success'):
            print(f"✅ HTML报告生成成功: {html_result['filename']}")
            
            # 检查文件是否存在
            if os.path.exists(html_result['filename']):
                print(f"✅ 报告文件已创建，大小: {html_result['size']} 字节")
                
                # 读取并检查HTML内容
                with open(html_result['filename'], 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                # 检查关键元素
                checks = [
                    ('<!DOCTYPE html>', 'HTML文档类型'),
                    ('<title>', 'HTML标题'),
                    ('交易决策支持系统', '系统标题'),
                    ('data:image/png;base64,', '图表数据'),
                    ('stats-grid', 'CSS样式'),
                    ('chart-container', '图表容器')
                ]
                
                for check, desc in checks:
                    if check in content:
                        print(f"✅ {desc} 检查通过")
                    else:
                        print(f"❌ {desc} 检查失败")
            else:
                print(f"❌ 报告文件未创建: {html_result['filename']}")
        else:
            print(f"❌ HTML报告生成失败: {html_result.get('error')}")
        
        # 测试JSON报告生成
        print("\n📋 测试JSON报告生成...")
        json_result = report_generator.generate_comprehensive_report("json")
        print(f"JSON报告结果: {json_result}")
        
        # 测试信号报告生成
        print("\n🎯 测试信号报告生成...")
        signal_result = report_generator.generate_signal_report(signals, "html")
        print(f"信号报告结果: {signal_result}")
        
        # 测试绩效仪表板
        print("\n📈 测试绩效仪表板生成...")
        dashboard_result = report_generator.generate_performance_dashboard()
        print(f"仪表板结果: {dashboard_result}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # 清理测试文件
        if os.path.exists(test_db):
            os.remove(test_db)


def test_template_system():
    """测试模板系统"""
    print("\n🧪 测试模板系统...")
    
    try:
        # 检查模板目录
        templates_dir = Path("templates")
        if not templates_dir.exists():
            templates_dir.mkdir(exist_ok=True)
            print("✅ 模板目录已创建")
        
        # 创建测试模板
        test_template = """
<!DOCTYPE html>
<html>
<head>
    <title>{{title}}</title>
</head>
<body>
    <h1>{{header}}</h1>
    <p>生成时间: {{timestamp}}</p>
    <div>数据: {{data}}</div>
</body>
</html>
        """
        
        template_file = templates_dir / "test_template.html"
        with open(template_file, 'w', encoding='utf-8') as f:
            f.write(test_template)
        
        print("✅ 测试模板已创建")
        
        # 测试模板渲染
        try:
            from jinja2 import Environment, FileSystemLoader
            
            env = Environment(loader=FileSystemLoader(str(templates_dir)))
            template = env.get_template("test_template.html")
            
            rendered = template.render(
                title="测试报告",
                header="这是测试标题",
                timestamp=datetime.now().isoformat(),
                data="测试数据内容"
            )
            
            print("✅ 模板渲染成功")
            
            # 保存渲染结果
            output_file = "test_template_output.html"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(rendered)
            
            print(f"✅ 渲染结果已保存: {output_file}")
            
            # 清理
            os.remove(output_file)
            os.remove(template_file)
            
            return True
            
        except ImportError:
            print("⚠️  Jinja2未安装，跳过模板渲染测试")
            return True
            
    except Exception as e:
        print(f"❌ 模板系统测试失败: {e}")
        return False


def test_chart_generation():
    """测试图表生成功能"""
    print("\n🧪 测试图表生成功能...")
    
    try:
        # 检查matplotlib是否可用
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from matplotlib.figure import Figure
            print("✅ Matplotlib库可用")
        except ImportError:
            print("❌ Matplotlib库未安装，无法生成图表")
            return False
        
        # 创建测试数据
        test_db = "test_chart_generation.db"
        if os.path.exists(test_db):
            os.remove(test_db)
        
        pool_manager = StockPoolManager(test_db)
        
        # 添加测试数据
        test_data = {
            'grade_distribution': {'A': 5, 'B': 3, 'C': 2},
            'performance_data': [0.02, 0.03, -0.01, 0.04, 0.02],
            'signal_stats': {'buy': 8, 'sell': 5}
        }
        
        # 创建报告生成器并测试图表生成
        report_generator = ReportGenerator(test_db)
        
        # 测试评级分布图
        grade_chart = report_generator._create_grade_distribution_chart(
            {'grade_distribution': test_data['grade_distribution']}
        )
        
        if grade_chart and grade_chart.startswith('data:image/png;base64,'):
            print("✅ 评级分布图生成成功")
        else:
            print("❌ 评级分布图生成失败")
        
        # 测试绩效趋势图
        performance_chart = report_generator._create_performance_trend_chart({})
        
        if performance_chart and performance_chart.startswith('data:image/png;base64,'):
            print("✅ 绩效趋势图生成成功")
        else:
            print("❌ 绩效趋势图生成失败")
        
        # 清理
        if os.path.exists(test_db):
            os.remove(test_db)
        
        return True
        
    except Exception as e:
        print(f"❌ 图表生成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_dependencies():
    """检查依赖库"""
    print("🔍 检查依赖库...")
    
    dependencies = [
        ('matplotlib', '图表生成'),
        ('pandas', '数据处理'),
        ('jinja2', '模板系统')
    ]
    
    missing_deps = []
    
    for dep, desc in dependencies:
        try:
            __import__(dep)
            print(f"✅ {dep} - {desc}")
        except ImportError:
            print(f"❌ {dep} - {desc} (未安装)")
            missing_deps.append(dep)
    
    if missing_deps:
        print(f"\n⚠️  缺少依赖库: {', '.join(missing_deps)}")
        print("请运行以下命令安装:")
        print(f"pip install {' '.join(missing_deps)}")
        return False
    
    return True


def main():
    """主函数"""
    print("🚀 报告生成器专项测试")
    print("=" * 50)
    
    # 设置日志级别
    logging.getLogger().setLevel(logging.WARNING)
    
    # 检查依赖
    deps_ok = check_dependencies()
    
    # 运行测试
    tests = [
        ("模板系统", test_template_system),
        ("图表生成", test_chart_generation),
        ("报告生成器可视化", test_report_generator_visualization)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results[test_name] = False
    
    # 显示测试结果
    print("\n" + "=" * 50)
    print("📊 测试结果总结:")
    
    success_count = sum(1 for result in results.values() if result)
    total_count = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name}: {status}")
    
    print(f"\n🎯 总体成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
    
    # 问题诊断
    if success_count < total_count:
        print("\n🔧 问题诊断:")
        
        if not deps_ok:
            print("  1. 安装缺失的依赖库")
        
        failed_tests = [name for name, result in results.items() if not result]
        if failed_tests:
            print(f"  2. 检查失败的测试: {', '.join(failed_tests)}")
        
        print("  3. 查看详细错误信息")
        print("  4. 检查文件权限和目录结构")
    
    return success_count == total_count


if __name__ == "__main__":
    main()