#!/usr/bin/env python3
"""
多周期分析系统完整功能演示
展示系统的所有核心功能和使用方法
"""

import sys
import time
from datetime import datetime

# 添加backend路径
sys.path.append('backend')

from multi_timeframe_config import MultiTimeframeConfig
from multi_timeframe_data_manager import MultiTimeframeDataManager
from multi_timeframe_signal_generator import MultiTimeframeSignalGenerator
from multi_timeframe_monitor import MultiTimeframeMonitor
from multi_timeframe_backtester import MultiTimeframeBacktester
from multi_timeframe_report_generator import MultiTimeframeReportGenerator
from multi_timeframe_visualizer import MultiTimeframeVisualizer

def demo_configuration_management():
    """演示配置管理功能"""
    print("\n" + "="*80)
    print("🔧 配置管理功能演示")
    print("="*80)
    
    # 初始化配置
    config = MultiTimeframeConfig()
    
    # 显示当前配置摘要
    print("📊 当前配置摘要:")
    summary = config.get_config_summary()
    print(f"   系统版本: {summary['system_version']}")
    print(f"   启用时间周期: {summary['enabled_timeframes']}/6")
    print(f"   启用策略: {summary['enabled_strategies']}/4")
    print(f"   配置有效: {'是' if summary['config_valid'] else '否'}")
    
    # 显示时间周期权重
    print("\n📈 时间周期权重:")
    weights = config.get_timeframe_weights()
    for timeframe, weight in weights.items():
        print(f"   {timeframe}: {weight:.3f}")
    
    # 显示策略权重
    print("\n🎯 策略权重:")
    strategy_weights = config.get_strategy_weights()
    for strategy, weight in strategy_weights.items():
        print(f"   {strategy}: {weight:.3f}")
    
    # 演示配置修改
    print("\n🔄 演示配置修改:")
    original_weight = config.get('timeframes.1day.weight')
    print(f"   原始日线权重: {original_weight}")
    
    # 临时修改权重
    config.update_timeframe_weight('1day', 0.4)
    new_weight = config.get('timeframes.1day.weight')
    print(f"   修改后日线权重: {new_weight}")
    
    # 恢复原始权重
    config.update_timeframe_weight('1day', original_weight)
    print(f"   恢复后日线权重: {config.get('timeframes.1day.weight')}")
    
    return config

def demo_data_management(config):
    """演示数据管理功能"""
    print("\n" + "="*80)
    print("📊 数据管理功能演示")
    print("="*80)
    
    # 初始化数据管理器
    data_manager = MultiTimeframeDataManager()
    
    # 测试股票
    test_stock = 'sz300290'
    print(f"📈 加载股票数据: {test_stock}")
    
    # 获取多周期数据
    sync_result = data_manager.get_synchronized_data(test_stock)
    
    if 'error' not in sync_result:
        timeframes = sync_result.get('timeframes', {})
        data_quality = sync_result.get('data_quality', {})
        
        print(f"✅ 成功加载 {len(timeframes)} 个时间周期的数据")
        
        # 显示各周期数据量
        for timeframe, data in timeframes.items():
            if data is not None and hasattr(data, 'empty') and not data.empty:
                quality_score = data_quality.get(timeframe, {}).get('quality_score', 0)
                print(f"   📈 {timeframe}: {len(data)} 条数据 (质量: {quality_score:.2f})")
            else:
                print(f"   ❌ {timeframe}: 无数据")
        
        # 显示数据质量统计
        print(f"\n📊 数据质量统计:")
        avg_quality = sum(q.get('quality_score', 0) for q in data_quality.values()) / len(data_quality)
        print(f"   平均质量评分: {avg_quality:.3f}")
        
        return data_manager, timeframes
    else:
        print(f"❌ 数据加载失败: {sync_result['error']}")
        return None, None

def demo_signal_generation(data_manager):
    """演示信号生成功能"""
    print("\n" + "="*80)
    print("🎯 信号生成功能演示")
    print("="*80)
    
    if not data_manager:
        print("❌ 数据管理器不可用，跳过信号生成演示")
        return None
    
    # 初始化信号生成器
    signal_generator = MultiTimeframeSignalGenerator(data_manager)
    
    # 测试股票
    test_stock = 'sz300290'
    print(f"🔄 生成多周期信号: {test_stock}")
    
    # 生成复合信号
    signals = signal_generator.generate_composite_signals(test_stock)
    
    if 'error' not in signals:
        print("✅ 信号生成成功")
        
        # 显示综合信号
        composite = signals.get('composite_signal', {})
        print(f"\n🎯 综合信号:")
        print(f"   信号强度: {composite.get('signal_strength', 'unknown')}")
        print(f"   最终评分: {composite.get('final_score', 0):.3f}")
        print(f"   置信度: {composite.get('confidence_level', 0):.3f}")
        
        # 显示各时间周期信号
        timeframe_signals = signals.get('timeframe_signals', {})
        print(f"\n📈 各时间周期信号:")
        for tf, signal_data in timeframe_signals.items():
            strength = signal_data.get('signal_strength', 'neutral')
            score = signal_data.get('final_score', 0)
            print(f"   {tf}: {strength} (评分: {score:.3f})")
        
        # 显示策略信号
        strategy_signals = signals.get('strategy_signals', {})
        print(f"\n🎲 策略信号:")
        for strategy, signal_data in strategy_signals.items():
            score = signal_data.get('final_score', 0)
            print(f"   {strategy}: {score:.3f}")
        
        # 显示风险评估
        risk_assessment = signals.get('risk_assessment', {})
        print(f"\n⚠️  风险评估:")
        print(f"   风险等级: {risk_assessment.get('overall_risk_level', 'unknown')}")
        print(f"   风险评分: {risk_assessment.get('risk_score', 0):.3f}")
        
        return signal_generator, signals
    else:
        print(f"❌ 信号生成失败: {signals['error']}")
        return None, None

def demo_monitoring_system(data_manager):
    """演示监控系统功能"""
    print("\n" + "="*80)
    print("👁️ 监控系统功能演示")
    print("="*80)
    
    if not data_manager:
        print("❌ 数据管理器不可用，跳过监控演示")
        return None
    
    # 初始化监控系统
    monitor = MultiTimeframeMonitor(data_manager)
    
    # 测试股票列表
    test_stocks = ['sz300290', 'sz002691']
    print(f"🔍 添加监控股票: {test_stocks}")
    
    # 添加股票到监控
    for stock in test_stocks:
        success = monitor.add_stock_to_monitor(stock)
        print(f"   {'✅' if success else '❌'} {stock}")
    
    # 执行一次监控更新
    print("\n🔄 执行监控更新...")
    monitor._update_all_signals()
    
    # 获取监控状态
    status = monitor.get_monitoring_status()
    print(f"\n📊 监控状态:")
    print(f"   监控股票数: {status['monitored_stocks_count']}")
    print(f"   监控活跃: {status['monitoring_active']}")
    
    stats = status.get('stats', {})
    print(f"   总更新次数: {stats.get('total_updates', 0)}")
    print(f"   总预警次数: {stats.get('total_alerts', 0)}")
    
    # 获取最新信号
    print(f"\n📡 最新信号:")
    for stock in test_stocks:
        history = monitor.get_stock_signal_history(stock, limit=1)
        if history:
            signal = history[-1]
            strength = signal.get('signal_strength', 'neutral')
            confidence = signal.get('confidence_level', 0)
            timestamp = signal.get('timestamp', 'unknown')
            print(f"   {stock}: {strength} (置信度: {confidence:.3f}) [{timestamp}]")
        else:
            print(f"   {stock}: 暂无信号")
    
    return monitor

def demo_backtesting_system(data_manager):
    """演示回测系统功能"""
    print("\n" + "="*80)
    print("📈 回测系统功能演示")
    print("="*80)
    
    if not data_manager:
        print("❌ 数据管理器不可用，跳过回测演示")
        return None
    
    # 初始化回测系统
    backtester = MultiTimeframeBacktester(data_manager)
    
    # 测试股票
    test_stocks = ['sz300290']
    print(f"🔄 执行回测: {test_stocks}")
    
    # 设置回测参数
    from datetime import datetime, timedelta
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)  # 30天回测
    
    print(f"   时间范围: {start_date.strftime('%Y-%m-%d')} 到 {end_date.strftime('%Y-%m-%d')}")
    
    # 运行回测
    backtest_results = backtester.run_multi_timeframe_backtest(
        test_stocks, start_date, end_date
    )
    
    if 'error' not in backtest_results:
        print("✅ 回测完成")
        
        # 显示整体性能
        overall_perf = backtest_results.get('overall_performance', {})
        print(f"\n📊 整体回测结果:")
        print(f"   测试股票数: {overall_perf.get('tested_stocks', 0)}")
        print(f"   平均收益率: {overall_perf.get('avg_return', 0):.2%}")
        print(f"   平均胜率: {overall_perf.get('avg_win_rate', 0):.2%}")
        print(f"   平均最大回撤: {overall_perf.get('avg_max_drawdown', 0):.2%}")
        print(f"   平均夏普比率: {overall_perf.get('avg_sharpe_ratio', 0):.3f}")
        
        # 显示个股结果
        results = backtest_results.get('results', {})
        for stock, result in results.items():
            print(f"\n📈 {stock} 详细结果:")
            performance = result.get('performance_metrics', {})
            
            print(f"   总收益率: {performance.get('total_return', 0):.2%}")
            print(f"   胜率: {performance.get('win_rate', 0):.2%}")
            print(f"   最大回撤: {performance.get('max_drawdown', 0):.2%}")
            print(f"   夏普比率: {performance.get('sharpe_ratio', 0):.3f}")
            
            trades = result.get('trades', [])
            print(f"   交易次数: {len(trades)}")
        
        return backtester, backtest_results
    else:
        print(f"❌ 回测失败: {backtest_results['error']}")
        return None, None

def demo_report_generation():
    """演示报告生成功能"""
    print("\n" + "="*80)
    print("📋 报告生成功能演示")
    print("="*80)
    
    # 初始化报告生成器
    report_generator = MultiTimeframeReportGenerator()
    
    # 测试股票
    test_stocks = ['sz300290', 'sz002691']
    print(f"📝 生成每日多周期报告: {test_stocks}")
    
    # 生成每日报告
    daily_report = report_generator.generate_daily_multi_timeframe_report(test_stocks)
    
    if 'error' not in daily_report:
        print("✅ 报告生成成功")
        
        # 显示报告摘要
        market_overview = daily_report.get('market_overview', {})
        print(f"\n🌍 市场概览:")
        print(f"   分析股票数: {market_overview.get('total_stocks', 0)}")
        print(f"   活跃信号数: {market_overview.get('active_signals', 0)}")
        print(f"   平均置信度: {market_overview.get('avg_confidence', 0):.3f}")
        
        # 显示投资建议
        recommendations = daily_report.get('recommendations', {})
        buy_list = recommendations.get('buy_list', [])
        sell_list = recommendations.get('sell_list', [])
        watch_list = recommendations.get('watch_list', [])
        
        print(f"\n💡 投资建议:")
        print(f"   买入推荐: {len(buy_list)} 只")
        print(f"   卖出建议: {len(sell_list)} 只")
        print(f"   观察名单: {len(watch_list)} 只")
        
        if buy_list:
            print(f"   🟢 买入推荐: {[item['stock_code'] for item in buy_list]}")
        if sell_list:
            print(f"   🔴 卖出建议: {[item['stock_code'] for item in sell_list]}")
        
        # 显示风险警告
        risk_warnings = daily_report.get('risk_warnings', [])
        if risk_warnings:
            print(f"\n⚠️  风险警告:")
            for warning in risk_warnings[:3]:  # 只显示前3个
                print(f"   - {warning}")
        
        return report_generator, daily_report
    else:
        print(f"❌ 报告生成失败: {daily_report['error']}")
        return None, None

def demo_visualization_system(signals, timeframes):
    """演示可视化系统功能"""
    print("\n" + "="*80)
    print("🎨 可视化系统功能演示")
    print("="*80)
    
    # 初始化可视化器
    visualizer = MultiTimeframeVisualizer()
    
    # 测试股票
    test_stock = 'sz300290'
    print(f"🖼️ 生成可视化图表: {test_stock}")
    
    chart_paths = []
    
    # 生成分析仪表板
    if signals:
        print("📊 生成分析仪表板...")
        dashboard_path = visualizer.create_multi_timeframe_dashboard(test_stock, signals)
        if dashboard_path:
            chart_paths.append(('仪表板', dashboard_path))
            print(f"   ✅ 仪表板已保存: {dashboard_path}")
        else:
            print("   ❌ 仪表板生成失败")
    
    # 生成多周期对比图
    if timeframes:
        print("📈 生成数据对比图...")
        comparison_path = visualizer.create_timeframe_comparison_chart(test_stock, timeframes)
        if comparison_path:
            chart_paths.append(('对比图', comparison_path))
            print(f"   ✅ 对比图已保存: {comparison_path}")
        else:
            print("   ❌ 对比图生成失败")
    
    # 生成性能摘要图
    print("📋 生成性能摘要图...")
    performance_data = {
        'accuracy_by_timeframe': {
            '5min': 0.65, '15min': 0.68, '30min': 0.72,
            '1hour': 0.75, '4hour': 0.78, '1day': 0.82
        },
        'signal_distribution': {'buy': 35, 'neutral': 45, 'sell': 20},
        'confidence_distribution': [0.6, 0.7, 0.8, 0.75, 0.65, 0.9, 0.55],
        'performance_metrics': {
            'Total Return': 0.15, 'Win Rate': 0.72,
            'Sharpe Ratio': 1.25, 'Max Drawdown': -0.08
        }
    }
    
    summary_path = visualizer.create_performance_summary_chart(performance_data)
    if summary_path:
        chart_paths.append(('性能摘要', summary_path))
        print(f"   ✅ 性能摘要已保存: {summary_path}")
    else:
        print("   ❌ 性能摘要生成失败")
    
    # 显示生成的图表
    if chart_paths:
        print(f"\n🎨 成功生成 {len(chart_paths)} 个图表:")
        for chart_type, path in chart_paths:
            print(f"   📊 {chart_type}: {path}")
        print(f"\n💡 提示: 图表文件保存在 charts/multi_timeframe/ 目录下")
    
    return visualizer, chart_paths

def main():
    """主演示函数"""
    print("🚀 多周期分析系统完整功能演示")
    print("="*80)
    print("本演示将展示多周期分析系统的所有核心功能")
    print("包括配置管理、数据处理、信号生成、监控、回测、报告和可视化")
    
    start_time = time.time()
    
    try:
        # 1. 配置管理演示
        config = demo_configuration_management()
        
        # 2. 数据管理演示
        data_manager, timeframes = demo_data_management(config)
        
        # 3. 信号生成演示
        signal_generator, signals = demo_signal_generation(data_manager)
        
        # 4. 监控系统演示
        monitor = demo_monitoring_system(data_manager)
        
        # 5. 回测系统演示
        backtester, backtest_results = demo_backtesting_system(data_manager)
        
        # 6. 报告生成演示
        report_generator, daily_report = demo_report_generation()
        
        # 7. 可视化系统演示
        visualizer, chart_paths = demo_visualization_system(signals, timeframes)
        
        # 演示总结
        end_time = time.time()
        duration = end_time - start_time
        
        print("\n" + "="*80)
        print("🎉 多周期分析系统功能演示完成")
        print("="*80)
        print(f"⏱️ 总耗时: {duration:.2f} 秒")
        
        # 功能完成度统计
        completed_demos = []
        if config: completed_demos.append("配置管理")
        if data_manager: completed_demos.append("数据管理")
        if signal_generator: completed_demos.append("信号生成")
        if monitor: completed_demos.append("监控系统")
        if backtester: completed_demos.append("回测系统")
        if report_generator: completed_demos.append("报告生成")
        if visualizer: completed_demos.append("可视化系统")
        
        print(f"✅ 演示完成模块 ({len(completed_demos)}/7): {', '.join(completed_demos)}")
        
        if len(completed_demos) == 7:
            print("🎯 所有核心功能演示成功！多周期分析系统运行完美")
        else:
            print(f"⚠️ {7 - len(completed_demos)} 个模块演示未完成")
        
        # 使用建议
        print(f"\n💡 使用建议:")
        print(f"   1. 使用配置工具调整系统参数: python multi_timeframe_config_tool.py")
        print(f"   2. 运行综合分析: python run_multi_timeframe_analysis.py --mode analysis")
        print(f"   3. 执行回测验证: python run_multi_timeframe_analysis.py --mode backtest")
        print(f"   4. 启动实时监控: python run_multi_timeframe_analysis.py --mode monitor")
        print(f"   5. 查看生成的图表文件: charts/multi_timeframe/")
        
    except KeyboardInterrupt:
        print("\n⏹️  用户中断演示")
    except Exception as e:
        print(f"\n❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()