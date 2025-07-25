#!/usr/bin/env python3
"""
多周期报告生成器
生成专业的多周期分析报告
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.dirname(__file__))

from multi_timeframe_data_manager import MultiTimeframeDataManager
from multi_timeframe_signal_generator import MultiTimeframeSignalGenerator
from multi_timeframe_monitor import MultiTimeframeMonitor

class MultiTimeframeReportGenerator:
    """多周期报告生成器"""
    
    def __init__(self, 
                 data_manager: MultiTimeframeDataManager = None,
                 signal_generator: MultiTimeframeSignalGenerator = None,
                 monitor: MultiTimeframeMonitor = None):
        """初始化多周期报告生成器"""
        
        self.data_manager = data_manager or MultiTimeframeDataManager()
        self.signal_generator = signal_generator or MultiTimeframeSignalGenerator(self.data_manager)
        self.monitor = monitor
        
        # 报告配置
        self.report_config = {
            'include_charts': True,
            'include_detailed_analysis': True,
            'include_risk_assessment': True,
            'include_recommendations': True,
            'max_stocks_per_report': 50,
            'analysis_depth': 'comprehensive'  # basic, standard, comprehensive
        }
        
        self.logger = logging.getLogger(__name__)
        
        # 创建报告目录
        self.reports_dir = Path("reports/multi_timeframe")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_daily_multi_timeframe_report(self, stock_list: List[str] = None) -> Dict:
        """生成每日多周期分析报告"""
        try:
            if stock_list is None:
                # 从核心股票池获取
                stock_list = self._get_default_stock_list()
            
            # 限制股票数量
            if len(stock_list) > self.report_config['max_stocks_per_report']:
                stock_list = stock_list[:self.report_config['max_stocks_per_report']]
            
            self.logger.info(f"生成每日多周期报告: {len(stock_list)} 只股票")
            
            report = {
                'report_type': 'daily_multi_timeframe',
                'generation_time': datetime.now().isoformat(),
                'report_date': datetime.now().strftime('%Y-%m-%d'),
                'stock_count': len(stock_list),
                'summary': {},
                'market_overview': {},
                'stock_analysis': {},
                'signal_alerts': [],
                'risk_warnings': [],
                'recommendations': {},
                'technical_summary': {}
            }
            
            # 1. 市场概览
            market_overview = self._generate_market_overview(stock_list)
            report['market_overview'] = market_overview
            
            # 2. 个股分析
            stock_analysis_results = {}
            signal_alerts = []
            risk_warnings = []
            
            for stock_code in stock_list:
                try:
                    stock_analysis = self._analyze_stock_multi_timeframe(stock_code)
                    
                    if 'error' not in stock_analysis:
                        stock_analysis_results[stock_code] = stock_analysis
                        
                        # 收集信号预警
                        stock_alerts = stock_analysis.get('alerts', [])
                        signal_alerts.extend(stock_alerts)
                        
                        # 收集风险警告
                        stock_risks = stock_analysis.get('risk_warnings', [])
                        risk_warnings.extend(stock_risks)
                        
                        self.logger.debug(f"  {stock_code} 分析完成")
                    else:
                        self.logger.warning(f"  {stock_code} 分析失败: {stock_analysis['error']}")
                        
                except Exception as e:
                    self.logger.error(f"分析 {stock_code} 失败: {e}")
                    continue
            
            report['stock_analysis'] = stock_analysis_results
            report['signal_alerts'] = signal_alerts
            report['risk_warnings'] = risk_warnings
            
            # 3. 生成摘要
            summary = self._generate_report_summary(stock_analysis_results, market_overview)
            report['summary'] = summary
            
            # 4. 生成建议
            recommendations = self._generate_recommendations(stock_analysis_results)
            report['recommendations'] = recommendations
            
            # 5. 技术摘要
            technical_summary = self._generate_technical_summary(stock_analysis_results)
            report['technical_summary'] = technical_summary
            
            # 保存报告
            self._save_report(report, 'daily')
            
            return report
            
        except Exception as e:
            self.logger.error(f"生成每日多周期报告失败: {e}")
            return {'error': str(e)}
    
    def generate_strategy_performance_report(self, backtest_results: Dict) -> Dict:
        """生成策略绩效报告"""
        try:
            self.logger.info("生成策略绩效报告")
            
            report = {
                'report_type': 'strategy_performance',
                'generation_time': datetime.now().isoformat(),
                'backtest_summary': {},
                'performance_analysis': {},
                'strategy_comparison': {},
                'risk_analysis': {},
                'optimization_suggestions': [],
                'detailed_results': {}
            }
            
            # 1. 回测摘要
            backtest_summary = self._extract_backtest_summary(backtest_results)
            report['backtest_summary'] = backtest_summary
            
            # 2. 性能分析
            performance_analysis = self._analyze_strategy_performance(backtest_results)
            report['performance_analysis'] = performance_analysis
            
            # 3. 策略对比
            strategy_comparison = self._compare_strategies(backtest_results)
            report['strategy_comparison'] = strategy_comparison
            
            # 4. 风险分析
            risk_analysis = self._analyze_strategy_risks(backtest_results)
            report['risk_analysis'] = risk_analysis
            
            # 5. 优化建议
            optimization_suggestions = self._generate_optimization_suggestions(backtest_results)
            report['optimization_suggestions'] = optimization_suggestions
            
            # 6. 详细结果
            report['detailed_results'] = backtest_results
            
            # 保存报告
            self._save_report(report, 'strategy_performance')
            
            return report
            
        except Exception as e:
            self.logger.error(f"生成策略绩效报告失败: {e}")
            return {'error': str(e)}
    
    def generate_monitoring_summary_report(self) -> Dict:
        """生成监控摘要报告"""
        try:
            if not self.monitor:
                return {'error': 'monitor_not_available'}
            
            self.logger.info("生成监控摘要报告")
            
            # 获取监控状态
            monitoring_status = self.monitor.get_monitoring_status()
            
            report = {
                'report_type': 'monitoring_summary',
                'generation_time': datetime.now().isoformat(),
                'monitoring_status': monitoring_status,
                'alert_summary': {},
                'performance_summary': {},
                'stock_rankings': {},
                'system_health': {}
            }
            
            # 1. 预警摘要
            alert_summary = self._generate_alert_summary()
            report['alert_summary'] = alert_summary
            
            # 2. 性能摘要
            performance_summary = self._generate_monitoring_performance_summary()
            report['performance_summary'] = performance_summary
            
            # 3. 股票排名
            stock_rankings = self._generate_stock_rankings()
            report['stock_rankings'] = stock_rankings
            
            # 4. 系统健康状态
            system_health = self._assess_system_health()
            report['system_health'] = system_health
            
            # 保存报告
            self._save_report(report, 'monitoring_summary')
            
            return report
            
        except Exception as e:
            self.logger.error(f"生成监控摘要报告失败: {e}")
            return {'error': str(e)}
    
    def _get_default_stock_list(self) -> List[str]:
        """获取默认股票列表"""
        try:
            # 尝试从核心股票池文件读取
            core_pool_file = Path("core_stock_pool.json")
            if core_pool_file.exists():
                with open(core_pool_file, 'r', encoding='utf-8') as f:
                    pool_data = json.load(f)
                    return list(pool_data.get('stocks', {}).keys())
            
            # 默认测试股票
            return ['sz300290', 'sz002691', 'sh600690', 'sz000725']
            
        except Exception as e:
            self.logger.error(f"获取默认股票列表失败: {e}")
            return ['sz300290', 'sz002691']
    
    def _generate_market_overview(self, stock_list: List[str]) -> Dict:
        """生成市场概览"""
        try:
            market_overview = {
                'total_stocks_analyzed': len(stock_list),
                'market_sentiment': 'neutral',
                'dominant_trends': {},
                'sector_analysis': {},
                'risk_level_distribution': {},
                'signal_strength_distribution': {}
            }
            
            # 分析市场情绪和趋势
            sentiment_scores = []
            trend_directions = []
            risk_levels = []
            signal_strengths = []
            
            for stock_code in stock_list[:10]:  # 限制分析数量以提高速度
                try:
                    # 获取信号
                    signals = self.signal_generator.generate_composite_signals(stock_code)
                    
                    if 'error' not in signals:
                        composite_signal = signals.get('composite_signal', {})
                        final_score = composite_signal.get('final_score', 0)
                        signal_strength = composite_signal.get('signal_strength', 'neutral')
                        
                        sentiment_scores.append(final_score)
                        signal_strengths.append(signal_strength)
                        
                        # 风险评估
                        risk_assessment = signals.get('risk_assessment', {})
                        risk_level = risk_assessment.get('overall_risk_level', 'medium')
                        risk_levels.append(risk_level)
                        
                        # 趋势方向
                        if final_score > 0.1:
                            trend_directions.append('bullish')
                        elif final_score < -0.1:
                            trend_directions.append('bearish')
                        else:
                            trend_directions.append('neutral')
                
                except Exception as e:
                    self.logger.error(f"分析 {stock_code} 市场概览失败: {e}")
                    continue
            
            # 计算市场情绪
            if sentiment_scores:
                avg_sentiment = np.mean(sentiment_scores)
                if avg_sentiment > 0.2:
                    market_overview['market_sentiment'] = 'bullish'
                elif avg_sentiment < -0.2:
                    market_overview['market_sentiment'] = 'bearish'
                else:
                    market_overview['market_sentiment'] = 'neutral'
            
            # 主导趋势
            if trend_directions:
                from collections import Counter
                trend_counts = Counter(trend_directions)
                market_overview['dominant_trends'] = dict(trend_counts)
            
            # 风险等级分布
            if risk_levels:
                from collections import Counter
                risk_counts = Counter(risk_levels)
                market_overview['risk_level_distribution'] = dict(risk_counts)
            
            # 信号强度分布
            if signal_strengths:
                from collections import Counter
                strength_counts = Counter(signal_strengths)
                market_overview['signal_strength_distribution'] = dict(strength_counts)
            
            return market_overview
            
        except Exception as e:
            self.logger.error(f"生成市场概览失败: {e}")
            return {'error': str(e)}
    
    def _analyze_stock_multi_timeframe(self, stock_code: str) -> Dict:
        """分析单只股票的多周期情况"""
        try:
            stock_analysis = {
                'stock_code': stock_code,
                'analysis_time': datetime.now().isoformat(),
                'signals': {},
                'timeframe_analysis': {},
                'risk_assessment': {},
                'recommendations': [],
                'alerts': [],
                'risk_warnings': [],
                'confidence_score': 0.0
            }
            
            # 1. 生成多周期信号
            signals = self.signal_generator.generate_composite_signals(stock_code)
            
            if 'error' in signals:
                return {'error': signals['error']}
            
            stock_analysis['signals'] = signals
            
            # 2. 时间周期分析
            timeframe_signals = signals.get('timeframe_signals', {})
            timeframe_analysis = self._analyze_timeframe_consistency(timeframe_signals)
            stock_analysis['timeframe_analysis'] = timeframe_analysis
            
            # 3. 风险评估
            risk_assessment = signals.get('risk_assessment', {})
            stock_analysis['risk_assessment'] = risk_assessment
            
            # 4. 生成建议
            recommendations = self._generate_stock_recommendations(signals, timeframe_analysis)
            stock_analysis['recommendations'] = recommendations
            
            # 5. 生成预警
            alerts = self._generate_stock_alerts(signals, timeframe_analysis)
            stock_analysis['alerts'] = alerts
            
            # 6. 风险警告
            risk_warnings = self._generate_risk_warnings(risk_assessment, signals)
            stock_analysis['risk_warnings'] = risk_warnings
            
            # 7. 置信度评分
            confidence_analysis = signals.get('confidence_analysis', {})
            confidence_score = confidence_analysis.get('overall_confidence', 0.0)
            stock_analysis['confidence_score'] = confidence_score
            
            return stock_analysis
            
        except Exception as e:
            self.logger.error(f"分析 {stock_code} 多周期失败: {e}")
            return {'error': str(e)}
    
    def _analyze_timeframe_consistency(self, timeframe_signals: Dict) -> Dict:
        """分析时间周期一致性"""
        try:
            consistency_analysis = {
                'signal_alignment': 0.0,
                'trend_consistency': 0.0,
                'momentum_alignment': 0.0,
                'conflicting_timeframes': [],
                'supporting_timeframes': [],
                'overall_consistency': 0.0
            }
            
            if not timeframe_signals:
                return consistency_analysis
            
            # 收集各周期信号
            trend_signals = []
            momentum_signals = []
            composite_scores = []
            
            for timeframe, tf_signal in timeframe_signals.items():
                if 'error' not in tf_signal:
                    trend_signals.append(tf_signal.get('trend_signal', 0))
                    momentum_signals.append(tf_signal.get('momentum_signal', 0))
                    composite_scores.append(tf_signal.get('composite_score', 0))
            
            # 计算一致性
            if trend_signals:
                # 趋势一致性：同向信号比例
                positive_trends = sum(1 for s in trend_signals if s > 0.1)
                negative_trends = sum(1 for s in trend_signals if s < -0.1)
                total_trends = len(trend_signals)
                
                consistency_analysis['trend_consistency'] = max(positive_trends, negative_trends) / total_trends
            
            if momentum_signals:
                # 动量一致性
                positive_momentum = sum(1 for s in momentum_signals if s > 0.1)
                negative_momentum = sum(1 for s in momentum_signals if s < -0.1)
                total_momentum = len(momentum_signals)
                
                consistency_analysis['momentum_alignment'] = max(positive_momentum, negative_momentum) / total_momentum
            
            if composite_scores:
                # 信号对齐度
                positive_signals = sum(1 for s in composite_scores if s > 0.1)
                negative_signals = sum(1 for s in composite_scores if s < -0.1)
                total_signals = len(composite_scores)
                
                consistency_analysis['signal_alignment'] = max(positive_signals, negative_signals) / total_signals
            
            # 整体一致性
            consistency_factors = [
                consistency_analysis['signal_alignment'],
                consistency_analysis['trend_consistency'],
                consistency_analysis['momentum_alignment']
            ]
            consistency_analysis['overall_consistency'] = np.mean([f for f in consistency_factors if f > 0])
            
            # 识别冲突和支持的时间周期
            for timeframe, tf_signal in timeframe_signals.items():
                if 'error' not in tf_signal:
                    composite_score = tf_signal.get('composite_score', 0)
                    avg_score = np.mean(composite_scores) if composite_scores else 0
                    
                    # 如果信号方向与平均方向相反，视为冲突
                    if (composite_score > 0.1 and avg_score < -0.1) or (composite_score < -0.1 and avg_score > 0.1):
                        consistency_analysis['conflicting_timeframes'].append(timeframe)
                    elif abs(composite_score) > 0.1 and np.sign(composite_score) == np.sign(avg_score):
                        consistency_analysis['supporting_timeframes'].append(timeframe)
            
            return consistency_analysis
            
        except Exception as e:
            self.logger.error(f"分析时间周期一致性失败: {e}")
            return {}
    
    def _generate_stock_recommendations(self, signals: Dict, timeframe_analysis: Dict) -> List[str]:
        """生成股票建议"""
        try:
            recommendations = []
            
            composite_signal = signals.get('composite_signal', {})
            final_score = composite_signal.get('final_score', 0)
            confidence_level = composite_signal.get('confidence_level', 0)
            signal_strength = composite_signal.get('signal_strength', 'neutral')
            
            overall_consistency = timeframe_analysis.get('overall_consistency', 0)
            
            # 基于信号强度和一致性生成建议
            if signal_strength in ['strong_buy', 'buy'] and confidence_level > 0.6 and overall_consistency > 0.6:
                recommendations.append(f"建议买入 - 多周期信号一致向好 (置信度: {confidence_level:.2f})")
            elif signal_strength in ['strong_sell', 'sell'] and confidence_level > 0.6 and overall_consistency > 0.6:
                recommendations.append(f"建议卖出 - 多周期信号一致向坏 (置信度: {confidence_level:.2f})")
            elif signal_strength == 'neutral' or overall_consistency < 0.4:
                recommendations.append("建议观望 - 信号不明确或周期间存在分歧")
            
            # 基于风险评估的建议
            risk_assessment = signals.get('risk_assessment', {})
            risk_level = risk_assessment.get('overall_risk_level', 'medium')
            
            if risk_level == 'high':
                recommendations.append("注意风险控制 - 当前风险等级较高")
            elif risk_level == 'low' and abs(final_score) > 0.3:
                recommendations.append("风险可控 - 可适当增加仓位")
            
            # 基于策略信号的建议
            strategy_signals = signals.get('strategy_signals', {})
            for strategy_type, strategy_signal in strategy_signals.items():
                if 'error' not in strategy_signal:
                    strategy_score = strategy_signal.get('signal_score', 0)
                    strategy_confidence = strategy_signal.get('confidence', 0)
                    
                    if abs(strategy_score) > 0.5 and strategy_confidence > 0.7:
                        if strategy_type == 'trend_following':
                            recommendations.append(f"趋势跟踪策略信号强烈 - 考虑趋势交易")
                        elif strategy_type == 'reversal_catching':
                            recommendations.append(f"反转捕捉策略信号强烈 - 关注反转机会")
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"生成股票建议失败: {e}")
            return []
    
    def _generate_stock_alerts(self, signals: Dict, timeframe_analysis: Dict) -> List[Dict]:
        """生成股票预警"""
        try:
            alerts = []
            
            composite_signal = signals.get('composite_signal', {})
            final_score = composite_signal.get('final_score', 0)
            confidence_level = composite_signal.get('confidence_level', 0)
            
            # 强信号预警
            if abs(final_score) > 0.7 and confidence_level > 0.8:
                alerts.append({
                    'type': 'strong_signal',
                    'level': 'high',
                    'message': f"检测到强烈信号 (强度: {final_score:.3f}, 置信度: {confidence_level:.3f})",
                    'action_required': True
                })
            
            # 信号收敛预警
            overall_consistency = timeframe_analysis.get('overall_consistency', 0)
            if overall_consistency > 0.8 and abs(final_score) > 0.4:
                alerts.append({
                    'type': 'signal_convergence',
                    'level': 'medium',
                    'message': f"多周期信号高度收敛 (一致性: {overall_consistency:.3f})",
                    'action_required': False
                })
            
            # 信号分歧预警
            conflicting_timeframes = timeframe_analysis.get('conflicting_timeframes', [])
            if len(conflicting_timeframes) >= 2:
                alerts.append({
                    'type': 'signal_divergence',
                    'level': 'medium',
                    'message': f"检测到周期间信号分歧: {', '.join(conflicting_timeframes)}",
                    'action_required': False
                })
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"生成股票预警失败: {e}")
            return []
    
    def _generate_risk_warnings(self, risk_assessment: Dict, signals: Dict) -> List[Dict]:
        """生成风险警告"""
        try:
            warnings = []
            
            risk_level = risk_assessment.get('overall_risk_level', 'medium')
            
            if risk_level == 'high':
                warnings.append({
                    'type': 'high_risk',
                    'level': 'high',
                    'message': "当前风险等级为高风险，建议谨慎操作",
                    'recommendation': "减少仓位或暂停交易"
                })
            
            # 检查波动率风险
            volatility_risk = risk_assessment.get('volatility_risk', 'medium')
            if volatility_risk == 'high':
                warnings.append({
                    'type': 'high_volatility',
                    'level': 'medium',
                    'message': "检测到高波动率，价格波动可能较大",
                    'recommendation': "适当调整止损位"
                })
            
            # 检查流动性风险
            liquidity_risk = risk_assessment.get('liquidity_risk', 'low')
            if liquidity_risk == 'high':
                warnings.append({
                    'type': 'liquidity_risk',
                    'level': 'medium',
                    'message': "流动性风险较高，可能影响交易执行",
                    'recommendation': "分批建仓或减仓"
                })
            
            return warnings
            
        except Exception as e:
            self.logger.error(f"生成风险警告失败: {e}")
            return []
    
    def _generate_report_summary(self, stock_analysis_results: Dict, market_overview: Dict) -> Dict:
        """生成报告摘要"""
        try:
            summary = {
                'total_stocks_analyzed': len(stock_analysis_results),
                'successful_analysis': len([r for r in stock_analysis_results.values() if 'error' not in r]),
                'market_sentiment': market_overview.get('market_sentiment', 'neutral'),
                'high_confidence_signals': 0,
                'strong_buy_signals': 0,
                'strong_sell_signals': 0,
                'high_risk_stocks': 0,
                'top_recommendations': []
            }
            
            # 统计信号分布
            for stock_code, analysis in stock_analysis_results.items():
                if 'error' not in analysis:
                    signals = analysis.get('signals', {})
                    composite_signal = signals.get('composite_signal', {})
                    
                    confidence_level = composite_signal.get('confidence_level', 0)
                    signal_strength = composite_signal.get('signal_strength', 'neutral')
                    
                    if confidence_level > 0.7:
                        summary['high_confidence_signals'] += 1
                    
                    if signal_strength == 'strong_buy':
                        summary['strong_buy_signals'] += 1
                    elif signal_strength == 'strong_sell':
                        summary['strong_sell_signals'] += 1
                    
                    # 风险统计
                    risk_assessment = analysis.get('risk_assessment', {})
                    if risk_assessment.get('overall_risk_level') == 'high':
                        summary['high_risk_stocks'] += 1
            
            # 生成顶级建议
            top_recommendations = self._extract_top_recommendations(stock_analysis_results)
            summary['top_recommendations'] = top_recommendations
            
            return summary
            
        except Exception as e:
            self.logger.error(f"生成报告摘要失败: {e}")
            return {}
    
    def _generate_recommendations(self, stock_analysis_results: Dict) -> Dict:
        """生成整体建议"""
        try:
            recommendations = {
                'buy_list': [],
                'sell_list': [],
                'watch_list': [],
                'avoid_list': [],
                'portfolio_suggestions': [],
                'risk_management_advice': []
            }
            
            for stock_code, analysis in stock_analysis_results.items():
                if 'error' not in analysis:
                    signals = analysis.get('signals', {})
                    composite_signal = signals.get('composite_signal', {})
                    
                    signal_strength = composite_signal.get('signal_strength', 'neutral')
                    confidence_level = composite_signal.get('confidence_level', 0)
                    risk_level = analysis.get('risk_assessment', {}).get('overall_risk_level', 'medium')
                    
                    # 分类建议
                    if signal_strength in ['strong_buy', 'buy'] and confidence_level > 0.6 and risk_level != 'high':
                        recommendations['buy_list'].append({
                            'stock_code': stock_code,
                            'signal_strength': signal_strength,
                            'confidence': confidence_level,
                            'risk_level': risk_level
                        })
                    elif signal_strength in ['strong_sell', 'sell'] and confidence_level > 0.6:
                        recommendations['sell_list'].append({
                            'stock_code': stock_code,
                            'signal_strength': signal_strength,
                            'confidence': confidence_level,
                            'risk_level': risk_level
                        })
                    elif signal_strength == 'neutral' and confidence_level > 0.5:
                        recommendations['watch_list'].append({
                            'stock_code': stock_code,
                            'reason': '信号中性，继续观察'
                        })
                    elif risk_level == 'high':
                        recommendations['avoid_list'].append({
                            'stock_code': stock_code,
                            'reason': '风险等级过高'
                        })
            
            # 组合建议
            if len(recommendations['buy_list']) > 0:
                recommendations['portfolio_suggestions'].append(
                    f"建议关注买入列表中的 {len(recommendations['buy_list'])} 只股票"
                )
            
            if len(recommendations['avoid_list']) > 0:
                recommendations['risk_management_advice'].append(
                    f"避免投资 {len(recommendations['avoid_list'])} 只高风险股票"
                )
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"生成整体建议失败: {e}")
            return {}
    
    def _generate_technical_summary(self, stock_analysis_results: Dict) -> Dict:
        """生成技术摘要"""
        try:
            technical_summary = {
                'signal_distribution': {},
                'timeframe_analysis': {},
                'strategy_performance': {},
                'risk_distribution': {},
                'confidence_analysis': {}
            }
            
            # 收集统计数据
            signal_strengths = []
            confidence_levels = []
            risk_levels = []
            
            for analysis in stock_analysis_results.values():
                if 'error' not in analysis:
                    signals = analysis.get('signals', {})
                    composite_signal = signals.get('composite_signal', {})
                    
                    signal_strengths.append(composite_signal.get('signal_strength', 'neutral'))
                    confidence_levels.append(composite_signal.get('confidence_level', 0))
                    
                    risk_assessment = analysis.get('risk_assessment', {})
                    risk_levels.append(risk_assessment.get('overall_risk_level', 'medium'))
            
            # 信号分布
            if signal_strengths:
                from collections import Counter
                signal_counts = Counter(signal_strengths)
                technical_summary['signal_distribution'] = dict(signal_counts)
            
            # 置信度分析
            if confidence_levels:
                technical_summary['confidence_analysis'] = {
                    'average_confidence': np.mean(confidence_levels),
                    'high_confidence_ratio': len([c for c in confidence_levels if c > 0.7]) / len(confidence_levels),
                    'low_confidence_ratio': len([c for c in confidence_levels if c < 0.4]) / len(confidence_levels)
                }
            
            # 风险分布
            if risk_levels:
                from collections import Counter
                risk_counts = Counter(risk_levels)
                technical_summary['risk_distribution'] = dict(risk_counts)
            
            return technical_summary
            
        except Exception as e:
            self.logger.error(f"生成技术摘要失败: {e}")
            return {}
    
    def _extract_top_recommendations(self, stock_analysis_results: Dict, top_n: int = 5) -> List[Dict]:
        """提取顶级建议"""
        try:
            recommendations = []
            
            for stock_code, analysis in stock_analysis_results.items():
                if 'error' not in analysis:
                    signals = analysis.get('signals', {})
                    composite_signal = signals.get('composite_signal', {})
                    
                    final_score = composite_signal.get('final_score', 0)
                    confidence_level = composite_signal.get('confidence_level', 0)
                    signal_strength = composite_signal.get('signal_strength', 'neutral')
                    
                    # 计算综合评分
                    combined_score = abs(final_score) * confidence_level
                    
                    recommendations.append({
                        'stock_code': stock_code,
                        'signal_strength': signal_strength,
                        'final_score': final_score,
                        'confidence_level': confidence_level,
                        'combined_score': combined_score
                    })
            
            # 按综合评分排序
            recommendations.sort(key=lambda x: x['combined_score'], reverse=True)
            
            return recommendations[:top_n]
            
        except Exception as e:
            self.logger.error(f"提取顶级建议失败: {e}")
            return []
    
    def _save_report(self, report: Dict, report_type: str):
        """保存报告"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{report_type}_report_{timestamp}.json"
            filepath = self.reports_dir / filename
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            self.logger.info(f"报告已保存: {filepath}")
            
        except Exception as e:
            self.logger.error(f"保存报告失败: {e}")
    
    # 以下是策略绩效报告相关方法的简化实现
    def _extract_backtest_summary(self, backtest_results: Dict) -> Dict:
        """提取回测摘要"""
        return backtest_results.get('overall_performance', {})
    
    def _analyze_strategy_performance(self, backtest_results: Dict) -> Dict:
        """分析策略性能"""
        return {'analysis': 'strategy_performance_analysis_placeholder'}
    
    def _compare_strategies(self, backtest_results: Dict) -> Dict:
        """对比策略"""
        return {'comparison': 'strategy_comparison_placeholder'}
    
    def _analyze_strategy_risks(self, backtest_results: Dict) -> Dict:
        """分析策略风险"""
        return {'risk_analysis': 'strategy_risk_analysis_placeholder'}
    
    def _generate_optimization_suggestions(self, backtest_results: Dict) -> List[str]:
        """生成优化建议"""
        return ['optimization_suggestions_placeholder']
    
    # 以下是监控报告相关方法的简化实现
    def _generate_alert_summary(self) -> Dict:
        """生成预警摘要"""
        return {'alert_summary': 'placeholder'}
    
    def _generate_monitoring_performance_summary(self) -> Dict:
        """生成监控性能摘要"""
        return {'performance_summary': 'placeholder'}
    
    def _generate_stock_rankings(self) -> Dict:
        """生成股票排名"""
        return {'stock_rankings': 'placeholder'}
    
    def _assess_system_health(self) -> Dict:
        """评估系统健康状态"""
        return {'system_health': 'healthy'}

def main():
    """测试函数"""
    print("📄 多周期报告生成器测试")
    print("=" * 50)
    
    # 创建报告生成器
    report_generator = MultiTimeframeReportGenerator()
    
    # 测试股票列表
    test_stocks = ['sz300290', 'sz002691']
    
    print(f"📊 生成每日多周期报告")
    
    # 生成每日报告
    daily_report = report_generator.generate_daily_multi_timeframe_report(test_stocks)
    
    if 'error' in daily_report:
        print(f"❌ 报告生成失败: {daily_report['error']}")
        return
    
    # 显示报告摘要
    summary = daily_report.get('summary', {})
    print(f"\n📈 报告摘要:")
    print(f"  分析股票数: {summary.get('total_stocks_analyzed', 0)}")
    print(f"  成功分析数: {summary.get('successful_analysis', 0)}")
    print(f"  市场情绪: {summary.get('market_sentiment', 'unknown')}")
    print(f"  高置信度信号: {summary.get('high_confidence_signals', 0)}")
    print(f"  强买入信号: {summary.get('strong_buy_signals', 0)}")
    print(f"  强卖出信号: {summary.get('strong_sell_signals', 0)}")
    
    # 显示建议摘要
    recommendations = daily_report.get('recommendations', {})
    buy_list = recommendations.get('buy_list', [])
    sell_list = recommendations.get('sell_list', [])
    
    if buy_list:
        print(f"\n💰 买入建议:")
        for item in buy_list[:3]:  # 显示前3个
            print(f"  {item['stock_code']}: {item['signal_strength']} (置信度: {item['confidence']:.2f})")
    
    if sell_list:
        print(f"\n📉 卖出建议:")
        for item in sell_list[:3]:  # 显示前3个
            print(f"  {item['stock_code']}: {item['signal_strength']} (置信度: {item['confidence']:.2f})")
    
    print(f"\n✅ 多周期报告生成器测试完成")

if __name__ == "__main__":
    main()