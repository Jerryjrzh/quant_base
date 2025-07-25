#!/usr/bin/env python3
"""
多周期分析系统运行脚本
整合所有多周期分析组件，提供完整的分析流程
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

# 添加backend目录到路径
sys.path.append('backend')

from multi_timeframe_data_manager import MultiTimeframeDataManager
from multi_timeframe_signal_generator import MultiTimeframeSignalGenerator
from multi_timeframe_monitor import MultiTimeframeMonitor
from multi_timeframe_backtester import MultiTimeframeBacktester
from multi_timeframe_report_generator import MultiTimeframeReportGenerator
from multi_timeframe_visualizer import MultiTimeframeVisualizer
from multi_timeframe_config import MultiTimeframeConfig

class MultiTimeframeAnalysisSystem:
    """多周期分析系统"""
    
    def __init__(self):
        """初始化多周期分析系统"""
        print("🚀 初始化多周期分析系统...")
        
        # 初始化各个组件
        self.config = MultiTimeframeConfig()
        self.data_manager = MultiTimeframeDataManager()
        self.signal_generator = MultiTimeframeSignalGenerator(self.data_manager)
        self.monitor = MultiTimeframeMonitor(self.data_manager)
        self.backtester = MultiTimeframeBacktester(self.data_manager)
        self.report_generator = MultiTimeframeReportGenerator()
        self.visualizer = MultiTimeframeVisualizer()
        
        print("✅ 多周期分析系统初始化完成")
    
    def run_comprehensive_analysis(self, stock_list: list = None):
        """运行综合分析"""
        print("\n📊 开始综合多周期分析")
        print("=" * 60)
        
        if stock_list is None:
            stock_list = self._get_default_stock_list()
        
        print(f"📈 分析股票列表: {stock_list}")
        
        # 1. 数据质量检查
        print("\n🔍 步骤1: 数据质量检查")
        data_quality_report = self._check_data_quality(stock_list)
        self._display_data_quality(data_quality_report)
        
        # 2. 多周期信号分析
        print("\n📡 步骤2: 多周期信号分析")
        signal_analysis_results = self._analyze_signals(stock_list)
        self._display_signal_analysis(signal_analysis_results)
        
        # 3. 生成每日报告
        print("\n📄 步骤3: 生成分析报告")
        daily_report = self.report_generator.generate_daily_multi_timeframe_report(stock_list)
        self._display_report_summary(daily_report)
        
        # 4. 风险评估
        print("\n⚠️  步骤4: 风险评估")
        risk_assessment = self._assess_overall_risk(signal_analysis_results)
        self._display_risk_assessment(risk_assessment)
        
        # 5. 投资建议
        print("\n💡 步骤5: 投资建议")
        investment_advice = self._generate_investment_advice(daily_report)
        self._display_investment_advice(investment_advice)
        
        # 6. 生成可视化图表
        print("\n📊 步骤6: 生成可视化图表")
        chart_paths = self._generate_visualization_charts(stock_list, signal_analysis_results)
        self._display_chart_info(chart_paths)
        
        print("\n✅ 综合多周期分析完成")
        
        return {
            'data_quality': data_quality_report,
            'signal_analysis': signal_analysis_results,
            'daily_report': daily_report,
            'risk_assessment': risk_assessment,
            'investment_advice': investment_advice
        }
    
    def run_backtest_analysis(self, stock_list: list = None, days: int = 90):
        """运行回测分析"""
        print("\n🧪 开始多周期回测分析")
        print("=" * 60)
        
        if stock_list is None:
            stock_list = self._get_default_stock_list()
        
        # 设置回测时间范围
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        print(f"📅 回测期间: {start_date} 至 {end_date}")
        print(f"📈 回测股票: {stock_list}")
        
        # 运行回测
        backtest_results = self.backtester.run_multi_timeframe_backtest(
            stock_list=stock_list,
            start_date=start_date,
            end_date=end_date
        )
        
        if 'error' in backtest_results:
            print(f"❌ 回测失败: {backtest_results['error']}")
            return backtest_results
        
        # 显示回测结果
        self._display_backtest_results(backtest_results)
        
        # 生成策略绩效报告
        print("\n📊 生成策略绩效报告")
        performance_report = self.report_generator.generate_strategy_performance_report(backtest_results)
        
        print("✅ 多周期回测分析完成")
        
        return {
            'backtest_results': backtest_results,
            'performance_report': performance_report
        }
    
    def start_monitoring(self, stock_list: list = None, duration_minutes: int = 60):
        """启动实时监控"""
        print("\n📡 启动多周期实时监控")
        print("=" * 60)
        
        if stock_list is None:
            stock_list = self._get_default_stock_list()
        
        # 添加股票到监控列表
        for stock_code in stock_list:
            success = self.monitor.add_stock_to_monitor(stock_code)
            print(f"{'✅' if success else '❌'} 添加 {stock_code} 到监控列表")
        
        # 启动监控
        if self.monitor.start_monitoring():
            print(f"🚀 监控已启动，将运行 {duration_minutes} 分钟")
            
            try:
                import time
                time.sleep(duration_minutes * 60)
            except KeyboardInterrupt:
                print("\n⏹️  用户中断监控")
            
            # 停止监控
            self.monitor.stop_monitoring()
            
            # 生成监控报告
            monitoring_report = self.report_generator.generate_monitoring_summary_report()
            self._display_monitoring_summary(monitoring_report)
            
            return monitoring_report
        else:
            print("❌ 监控启动失败")
            return {'error': 'monitoring_start_failed'}
    
    def _get_default_stock_list(self) -> list:
        """获取默认股票列表"""
        try:
            # 尝试从核心股票池读取
            core_pool_file = Path("core_stock_pool.json")
            if core_pool_file.exists():
                with open(core_pool_file, 'r', encoding='utf-8') as f:
                    pool_data = json.load(f)
                    stocks = list(pool_data.get('stocks', {}).keys())
                    return stocks[:10]  # 限制数量
            
            # 默认测试股票
            return ['sz300290', 'sz002691', 'sh600690', 'sz000725']
            
        except Exception as e:
            print(f"⚠️  获取股票列表失败: {e}")
            return ['sz300290', 'sz002691']
    
    def _check_data_quality(self, stock_list: list) -> dict:
        """检查数据质量"""
        quality_report = {
            'total_stocks': len(stock_list),
            'available_stocks': 0,
            'quality_scores': {},
            'issues': []
        }
        
        for stock_code in stock_list:
            try:
                sync_data = self.data_manager.get_synchronized_data(stock_code)
                
                if 'error' not in sync_data:
                    quality_report['available_stocks'] += 1
                    
                    # 计算平均质量评分
                    data_quality = sync_data.get('data_quality', {})
                    quality_scores = [q.get('quality_score', 0) for q in data_quality.values()]
                    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
                    
                    quality_report['quality_scores'][stock_code] = avg_quality
                    
                    if avg_quality < 0.8:
                        quality_report['issues'].append(f"{stock_code}: 数据质量较低 ({avg_quality:.2f})")
                else:
                    quality_report['issues'].append(f"{stock_code}: 数据获取失败")
                    
            except Exception as e:
                quality_report['issues'].append(f"{stock_code}: 检查失败 - {e}")
        
        return quality_report
    
    def _analyze_signals(self, stock_list: list) -> dict:
        """分析信号"""
        signal_results = {
            'total_analyzed': 0,
            'successful_analysis': 0,
            'signal_summary': {},
            'strong_signals': [],
            'weak_signals': []
        }
        
        for stock_code in stock_list:
            try:
                signals = self.signal_generator.generate_composite_signals(stock_code)
                
                if 'error' not in signals:
                    signal_results['successful_analysis'] += 1
                    
                    composite_signal = signals.get('composite_signal', {})
                    final_score = composite_signal.get('final_score', 0)
                    signal_strength = composite_signal.get('signal_strength', 'neutral')
                    confidence_level = composite_signal.get('confidence_level', 0)
                    
                    signal_results['signal_summary'][stock_code] = {
                        'final_score': final_score,
                        'signal_strength': signal_strength,
                        'confidence_level': confidence_level
                    }
                    
                    # 分类强弱信号
                    if abs(final_score) > 0.5 and confidence_level > 0.7:
                        signal_results['strong_signals'].append({
                            'stock_code': stock_code,
                            'final_score': final_score,
                            'signal_strength': signal_strength,
                            'confidence_level': confidence_level
                        })
                    elif abs(final_score) < 0.2 or confidence_level < 0.4:
                        signal_results['weak_signals'].append({
                            'stock_code': stock_code,
                            'final_score': final_score,
                            'signal_strength': signal_strength,
                            'confidence_level': confidence_level
                        })
                
                signal_results['total_analyzed'] += 1
                
            except Exception as e:
                print(f"⚠️  {stock_code} 信号分析失败: {e}")
        
        return signal_results
    
    def _assess_overall_risk(self, signal_analysis_results: dict) -> dict:
        """评估整体风险"""
        risk_assessment = {
            'overall_risk_level': 'medium',
            'high_risk_stocks': [],
            'risk_factors': [],
            'risk_score': 0.5
        }
        
        signal_summary = signal_analysis_results.get('signal_summary', {})
        high_risk_count = 0
        total_confidence = 0
        confidence_count = 0
        
        for stock_code, signal_info in signal_summary.items():
            confidence = signal_info.get('confidence_level', 0)
            total_confidence += confidence
            confidence_count += 1
            
            # 简化的风险评估
            if confidence < 0.3:
                high_risk_count += 1
                risk_assessment['high_risk_stocks'].append(stock_code)
        
        # 计算整体风险
        if confidence_count > 0:
            avg_confidence = total_confidence / confidence_count
            risk_ratio = high_risk_count / len(signal_summary) if signal_summary else 0
            
            if avg_confidence < 0.4 or risk_ratio > 0.3:
                risk_assessment['overall_risk_level'] = 'high'
                risk_assessment['risk_score'] = 0.8
            elif avg_confidence > 0.7 and risk_ratio < 0.1:
                risk_assessment['overall_risk_level'] = 'low'
                risk_assessment['risk_score'] = 0.2
        
        # 风险因素
        if high_risk_count > 0:
            risk_assessment['risk_factors'].append(f"{high_risk_count} 只股票信号置信度较低")
        
        strong_signals = signal_analysis_results.get('strong_signals', [])
        if len(strong_signals) == 0:
            risk_assessment['risk_factors'].append("缺乏强烈的交易信号")
        
        return risk_assessment
    
    def _generate_investment_advice(self, daily_report: dict) -> dict:
        """生成投资建议"""
        if 'error' in daily_report:
            return {'error': 'report_generation_failed'}
        
        recommendations = daily_report.get('recommendations', {})
        summary = daily_report.get('summary', {})
        
        advice = {
            'market_outlook': 'neutral',
            'recommended_actions': [],
            'position_suggestions': [],
            'risk_management': []
        }
        
        # 市场展望
        market_sentiment = summary.get('market_sentiment', 'neutral')
        if market_sentiment == 'bullish':
            advice['market_outlook'] = 'positive'
            advice['recommended_actions'].append("市场情绪偏多，可适当增加仓位")
        elif market_sentiment == 'bearish':
            advice['market_outlook'] = 'negative'
            advice['recommended_actions'].append("市场情绪偏空，建议降低仓位")
        
        # 具体建议
        buy_list = recommendations.get('buy_list', [])
        sell_list = recommendations.get('sell_list', [])
        
        if buy_list:
            advice['position_suggestions'].append(f"考虑买入: {', '.join([item['stock_code'] for item in buy_list[:3]])}")
        
        if sell_list:
            advice['position_suggestions'].append(f"考虑卖出: {', '.join([item['stock_code'] for item in sell_list[:3]])}")
        
        # 风险管理
        high_risk_stocks = summary.get('high_risk_stocks', 0)
        if high_risk_stocks > 0:
            advice['risk_management'].append(f"注意 {high_risk_stocks} 只高风险股票")
        
        high_confidence_signals = summary.get('high_confidence_signals', 0)
        if high_confidence_signals > 0:
            advice['risk_management'].append(f"重点关注 {high_confidence_signals} 个高置信度信号")
        
        return advice
    
    def _display_data_quality(self, quality_report: dict):
        """显示数据质量报告"""
        print(f"  📊 总股票数: {quality_report['total_stocks']}")
        print(f"  ✅ 可用股票数: {quality_report['available_stocks']}")
        
        if quality_report['quality_scores']:
            avg_quality = sum(quality_report['quality_scores'].values()) / len(quality_report['quality_scores'])
            print(f"  📈 平均质量评分: {avg_quality:.2f}")
        
        if quality_report['issues']:
            print(f"  ⚠️  发现 {len(quality_report['issues'])} 个问题:")
            for issue in quality_report['issues'][:3]:  # 只显示前3个
                print(f"    - {issue}")
    
    def _display_signal_analysis(self, signal_results: dict):
        """显示信号分析结果"""
        print(f"  📊 分析股票数: {signal_results['total_analyzed']}")
        print(f"  ✅ 成功分析数: {signal_results['successful_analysis']}")
        print(f"  💪 强信号数: {len(signal_results['strong_signals'])}")
        print(f"  😐 弱信号数: {len(signal_results['weak_signals'])}")
        
        # 显示强信号
        if signal_results['strong_signals']:
            print(f"  🔥 强信号股票:")
            for signal in signal_results['strong_signals'][:3]:
                print(f"    {signal['stock_code']}: {signal['signal_strength']} (置信度: {signal['confidence_level']:.2f})")
    
    def _display_report_summary(self, daily_report: dict):
        """显示报告摘要"""
        if 'error' in daily_report:
            print(f"  ❌ 报告生成失败: {daily_report['error']}")
            return
        
        summary = daily_report.get('summary', {})
        print(f"  📊 市场情绪: {summary.get('market_sentiment', 'unknown')}")
        print(f"  📈 强买入信号: {summary.get('strong_buy_signals', 0)}")
        print(f"  📉 强卖出信号: {summary.get('strong_sell_signals', 0)}")
        print(f"  🎯 高置信度信号: {summary.get('high_confidence_signals', 0)}")
    
    def _display_risk_assessment(self, risk_assessment: dict):
        """显示风险评估"""
        print(f"  📊 整体风险等级: {risk_assessment['overall_risk_level']}")
        print(f"  📈 风险评分: {risk_assessment['risk_score']:.2f}")
        print(f"  ⚠️  高风险股票数: {len(risk_assessment['high_risk_stocks'])}")
        
        if risk_assessment['risk_factors']:
            print(f"  🚨 主要风险因素:")
            for factor in risk_assessment['risk_factors']:
                print(f"    - {factor}")
    
    def _display_investment_advice(self, advice: dict):
        """显示投资建议"""
        if 'error' in advice:
            print(f"  ❌ 建议生成失败: {advice['error']}")
            return
        
        print(f"  🔮 市场展望: {advice['market_outlook']}")
        
        if advice['recommended_actions']:
            print(f"  💡 推荐行动:")
            for action in advice['recommended_actions']:
                print(f"    - {action}")
        
        if advice['position_suggestions']:
            print(f"  📍 仓位建议:")
            for suggestion in advice['position_suggestions']:
                print(f"    - {suggestion}")
        
        if advice['risk_management']:
            print(f"  🛡️  风险管理:")
            for risk_tip in advice['risk_management']:
                print(f"    - {risk_tip}")
    
    def _display_backtest_results(self, backtest_results: dict):
        """显示回测结果"""
        overall_perf = backtest_results.get('overall_performance', {})
        
        print(f"  📊 测试股票数: {overall_perf.get('tested_stocks', 0)}")
        print(f"  📈 平均收益率: {overall_perf.get('avg_return', 0):.2%}")
        print(f"  📊 平均夏普比率: {overall_perf.get('avg_sharpe_ratio', 0):.3f}")
        print(f"  📉 平均最大回撤: {overall_perf.get('avg_max_drawdown', 0):.2%}")
        print(f"  🎯 平均胜率: {overall_perf.get('avg_win_rate', 0):.2%}")
        
        if overall_perf.get('best_stock'):
            print(f"  🏆 最佳股票: {overall_perf['best_stock']}")
    
    def _display_monitoring_summary(self, monitoring_report: dict):
        """显示监控摘要"""
        if 'error' in monitoring_report:
            print(f"  ❌ 监控报告生成失败: {monitoring_report['error']}")
            return
        
        monitoring_status = monitoring_report.get('monitoring_status', {})
        print(f"  📊 监控股票数: {monitoring_status.get('monitored_stocks_count', 0)}")
        
        stats = monitoring_status.get('stats', {})
        print(f"  🔄 总更新次数: {stats.get('total_updates', 0)}")
        print(f"  🚨 总预警次数: {stats.get('total_alerts', 0)}")
    
    def _generate_visualization_charts(self, stock_list: list, signal_analysis_results: dict) -> dict:
        """生成可视化图表"""
        chart_paths = {
            'dashboard_charts': [],
            'timeframe_charts': [],
            'errors': []
        }
        
        try:
            # 为每个有强信号的股票生成仪表板
            strong_signals = signal_analysis_results.get('strong_signals', [])
            signal_summary = signal_analysis_results.get('signal_summary', {})
            
            # 选择要生成图表的股票（强信号股票优先）
            chart_stocks = []
            for signal in strong_signals[:3]:  # 最多3个强信号股票
                chart_stocks.append(signal['stock_code'])
            
            # 如果强信号股票不足，补充其他股票
            for stock_code in stock_list:
                if stock_code not in chart_stocks and len(chart_stocks) < 5:
                    chart_stocks.append(stock_code)
            
            # 为每个股票生成图表
            for stock_code in chart_stocks:
                try:
                    # 获取该股票的分析结果
                    if stock_code in signal_summary:
                        # 重新生成完整的信号分析结果用于可视化
                        signals = self.signal_generator.generate_composite_signals(stock_code)
                        
                        if 'error' not in signals:
                            # 生成仪表板
                            dashboard_path = self.visualizer.create_multi_timeframe_dashboard(
                                stock_code, signals
                            )
                            if dashboard_path:
                                chart_paths['dashboard_charts'].append({
                                    'stock_code': stock_code,
                                    'path': dashboard_path,
                                    'type': 'dashboard'
                                })
                            
                            # 生成多周期对比图
                            sync_data = self.data_manager.get_synchronized_data(stock_code)
                            if 'error' not in sync_data:
                                timeframe_data = sync_data.get('timeframes', {})
                                timeframe_path = self.visualizer.create_timeframe_comparison_chart(
                                    stock_code, timeframe_data
                                )
                                if timeframe_path:
                                    chart_paths['timeframe_charts'].append({
                                        'stock_code': stock_code,
                                        'path': timeframe_path,
                                        'type': 'timeframe_comparison'
                                    })
                        else:
                            chart_paths['errors'].append(f"{stock_code}: 信号生成失败")
                    else:
                        chart_paths['errors'].append(f"{stock_code}: 无信号数据")
                        
                except Exception as e:
                    chart_paths['errors'].append(f"{stock_code}: 图表生成失败 - {str(e)}")
            
        except Exception as e:
            chart_paths['errors'].append(f"可视化系统错误: {str(e)}")
        
        return chart_paths
    
    def _display_chart_info(self, chart_paths: dict):
        """显示图表信息"""
        dashboard_charts = chart_paths.get('dashboard_charts', [])
        timeframe_charts = chart_paths.get('timeframe_charts', [])
        errors = chart_paths.get('errors', [])
        
        print(f"  📊 生成仪表板图表: {len(dashboard_charts)} 个")
        for chart in dashboard_charts:
            print(f"    ✅ {chart['stock_code']}: {chart['path']}")
        
        print(f"  📈 生成对比图表: {len(timeframe_charts)} 个")
        for chart in timeframe_charts:
            print(f"    ✅ {chart['stock_code']}: {chart['path']}")
        
        if errors:
            print(f"  ⚠️  图表生成错误: {len(errors)} 个")
            for error in errors[:3]:  # 只显示前3个错误
                print(f"    ❌ {error}")
        
        total_charts = len(dashboard_charts) + len(timeframe_charts)
        if total_charts > 0:
            print(f"  🎨 图表已保存到 charts/multi_timeframe/ 目录")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='多周期分析系统')
    parser.add_argument('--mode', choices=['analysis', 'backtest', 'monitor'], 
                       default='analysis', help='运行模式')
    parser.add_argument('--stocks', nargs='+', help='股票代码列表')
    parser.add_argument('--days', type=int, default=90, help='回测天数')
    parser.add_argument('--duration', type=int, default=60, help='监控时长(分钟)')
    
    args = parser.parse_args()
    
    # 创建分析系统
    system = MultiTimeframeAnalysisSystem()
    
    try:
        if args.mode == 'analysis':
            # 综合分析模式
            results = system.run_comprehensive_analysis(args.stocks)
            
        elif args.mode == 'backtest':
            # 回测分析模式
            results = system.run_backtest_analysis(args.stocks, args.days)
            
        elif args.mode == 'monitor':
            # 实时监控模式
            results = system.start_monitoring(args.stocks, args.duration)
        
        print(f"\n🎉 {args.mode} 模式运行完成!")
        
    except KeyboardInterrupt:
        print("\n⏹️  用户中断程序")
    except Exception as e:
        print(f"\n❌ 程序运行出错: {e}")

if __name__ == "__main__":
    main()