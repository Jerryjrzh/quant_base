#!/usr/bin/env python3
"""
季度回测系统快速开始脚本
简化的回测流程，适合初次使用和快速验证
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from datetime import datetime
import json

def quick_test():
    """快速测试系统功能"""
    print("🔧 快速测试系统功能...")
    
    try:
        from quarterly_backtester import QuarterlyBacktester, QuarterlyBacktestConfig
        
        # 创建测试配置
        config = QuarterlyBacktestConfig(
            lookback_years=1,
            max_pool_size=10,  # 减少股票数量以加快测试
            test_period_days=30,
            pool_selection_period=15
        )
        
        backtester = QuarterlyBacktester(config)
        
        # 测试基本功能
        quarters = backtester.get_quarters_in_period()
        stock_list = backtester.get_stock_list()
        
        print(f"✅ 系统正常，发现 {len(quarters)} 个季度，{len(stock_list)} 只股票")
        return True
        
    except Exception as e:
        print(f"❌ 系统测试失败: {e}")
        return False

def run_quick_backtest():
    """运行快速回测"""
    print("\n🚀 开始快速回测...")
    
    try:
        from quarterly_backtester import QuarterlyBacktester, QuarterlyBacktestConfig
        
        # 创建快速回测配置
        config = QuarterlyBacktestConfig(
            lookback_years=1,
            pool_selection_strategy='WEEKLY_GOLDEN_CROSS_MA',
            max_pool_size=20,  # 限制股票数量
            min_pool_size=5,
            test_strategies=['WEEKLY_GOLDEN_CROSS_MA', 'TRIPLE_CROSS'],  # 只测试2个策略
            test_period_days=45,
            pool_selection_period=20
        )
        
        print(f"📋 配置信息:")
        print(f"  - 回溯期间: {config.lookback_years} 年")
        print(f"  - 股票池策略: {config.pool_selection_strategy}")
        print(f"  - 最大股票池: {config.max_pool_size}")
        print(f"  - 测试策略: {config.test_strategies}")
        
        # 创建回测器
        backtester = QuarterlyBacktester(config)
        
        # 运行回测
        print("\n⏳ 正在运行回测，请稍候...")
        results = backtester.run_full_backtest()
        
        if results:
            print(f"✅ 回测完成！共完成 {len(results)} 个季度")
            
            # 保存结果
            filename = backtester.save_results()
            print(f"📁 结果已保存到: {filename}")
            
            return filename
        else:
            print("❌ 回测失败，没有生成结果")
            return None
            
    except Exception as e:
        print(f"❌ 回测失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def analyze_results(results_file):
    """分析回测结果"""
    print(f"\n📊 分析回测结果: {results_file}")
    
    try:
        # 加载结果
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        # 显示摘要
        summary = results['summary']
        print(f"\n=== 📈 回测摘要 ===")
        print(f"总季度数: {summary['total_quarters']}")
        print(f"最佳整体策略: {summary['best_overall_strategy']}")
        print(f"平均季度收益率: {summary['avg_quarterly_return']:.2%}")
        print(f"平均胜率: {summary['avg_win_rate']:.1%}")
        print(f"总交易次数: {summary['total_trades']}")
        
        # 显示策略表现
        print(f"\n=== 🎯 策略表现 ===")
        for strategy_name, perf in results['strategy_performance'].items():
            print(f"{strategy_name}:")
            print(f"  平均收益率: {perf['avg_return']:.2%}")
            print(f"  平均胜率: {perf['avg_win_rate']:.1%}")
            print(f"  使用季度数: {perf['quarters_used']}")
            print(f"  总交易次数: {perf['total_trades']}")
        
        # 显示季度分析
        print(f"\n=== 📅 季度分析 ===")
        for quarter_info in results['quarterly_analysis']:
            print(f"{quarter_info['quarter']}:")
            print(f"  股票池大小: {quarter_info['pool_size']}")
            print(f"  最佳策略: {quarter_info['best_strategy']}")
            print(f"  收益率: {quarter_info['best_return']:.2%}")
            print(f"  胜率: {quarter_info['win_rate']:.1%}")
        
        # 显示优化建议
        print(f"\n=== 💡 优化建议 ===")
        for i, suggestion in enumerate(results['optimization_suggestions'], 1):
            priority_icon = "🔴" if suggestion['priority'] == 'high' else "🟡"
            print(f"{i}. {priority_icon} {suggestion['suggestion']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 结果分析失败: {e}")
        return False

def generate_simple_charts(results_file):
    """生成简单图表"""
    print(f"\n📈 生成分析图表...")
    
    try:
        from quarterly_analyzer import QuarterlyAnalyzer
        
        analyzer = QuarterlyAnalyzer(results_file)
        
        # 生成图表
        print("正在生成策略对比图...")
        analyzer.plot_strategy_comparison('charts/strategy_comparison.png')
        
        print("正在生成季度趋势图...")
        analyzer.plot_quarterly_trends('charts/quarterly_trends.png')
        
        print("✅ 图表已保存到 charts/ 目录")
        return True
        
    except ImportError:
        print("⚠️ 缺少可视化依赖，跳过图表生成")
        print("如需生成图表，请安装: pip install matplotlib")
        return False
    except Exception as e:
        print(f"❌ 图表生成失败: {e}")
        return False

def main():
    """主函数"""
    print("🎯 季度回测系统 - 快速开始")
    print("=" * 50)
    
    # 步骤1: 系统测试
    if not quick_test():
        print("\n❌ 系统测试失败，请检查环境配置")
        return
    
    # 步骤2: 运行回测
    results_file = run_quick_backtest()
    if not results_file:
        print("\n❌ 回测失败，程序退出")
        return
    
    # 步骤3: 分析结果
    if not analyze_results(results_file):
        print("\n❌ 结果分析失败")
        return
    
    # 步骤4: 生成图表（可选）
    generate_simple_charts(results_file)
    
    # 完成提示
    print(f"\n🎉 快速回测完成！")
    print(f"\n📁 生成的文件:")
    print(f"  - 回测结果: {results_file}")
    print(f"  - 图表目录: charts/")
    
    print(f"\n🔄 下一步建议:")
    print(f"1. 查看详细结果文件: {results_file}")
    print(f"2. 根据优化建议调整策略参数")
    print(f"3. 运行完整回测: python backend/quarterly_backtester.py")
    print(f"4. 生成完整分析: python backend/quarterly_analyzer.py {results_file} --charts --report")
    
    print(f"\n✨ 快速开始完成！")

if __name__ == "__main__":
    main()