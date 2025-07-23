#!/usr/bin/env python3
"""
绩效跟踪器

这个模块实现了高级的绩效跟踪功能，包括：
- 信号跟踪与实际表现记录
- 多维度绩效分析
- 动态调整核心池的算法
- 风险调整收益计算
"""

import os
import sys
import json
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import statistics

# 添加backend目录到路径
sys.path.append(os.path.dirname(__file__))

from stock_pool_manager import StockPoolManager


class PerformanceTracker:
    """绩效跟踪器"""
    
    def __init__(self, db_path: str = "stock_pool.db", config: Optional[Dict] = None):
        """初始化绩效跟踪器"""
        self.db_path = db_path
        self.pool_manager = StockPoolManager(db_path)
        self.config = config or self._get_default_config()
        self.logger = logging.getLogger(__name__)
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "tracking_period_days": 30,
            "min_signals_for_analysis": 5,
            "performance_thresholds": {
                "excellent": 0.8,
                "good": 0.6,
                "average": 0.4,
                "poor": 0.2
            },
            "credibility_adjustments": {
                "excellent": 1.2,
                "good": 1.1,
                "average": 1.0,
                "poor": 0.8,
                "very_poor": 0.6
            },
            "risk_free_rate": 0.03,  # 无风险利率
            "benchmark_return": 0.08,  # 基准收益率
            "max_drawdown_threshold": 0.15,
            "min_sharpe_ratio": 0.5
        }
    
    def track_signal_performance(self, signal_id: int, actual_data: Dict[str, Any]) -> bool:
        """跟踪信号绩效"""
        try:
            # 更新信号结果
            result = self.pool_manager.update_signal_result(signal_id, actual_data)
            if not result:
                self.logger.error(f"更新信号 {signal_id} 结果失败")
                return False
            
            # 获取信号信息
            signal_info = self._get_signal_info(signal_id)
            if not signal_info:
                return False
            
            # 更新股票绩效统计
            self._update_stock_performance(signal_info['stock_code'], actual_data)
            
            # 记录绩效跟踪数据
            self._record_performance_data(signal_info, actual_data)
            
            self.logger.info(f"信号 {signal_id} 绩效跟踪完成")
            return True
            
        except Exception as e:
            self.logger.error(f"跟踪信号绩效失败: {e}")
            return False
    
    def analyze_stock_performance(self, stock_code: str, 
                                days: int = None) -> Dict[str, Any]:
        """分析股票绩效"""
        days = days or self.config.get('tracking_period_days', 30)
        
        try:
            # 获取基础绩效数据
            performance = self.pool_manager.get_stock_performance(stock_code, days)
            if not performance:
                return {}
            
            # 获取详细信号历史
            signal_history = self._get_signal_history(stock_code, days)
            
            # 计算高级绩效指标
            advanced_metrics = self._calculate_advanced_metrics(signal_history)
            
            # 风险分析
            risk_metrics = self._calculate_risk_metrics(signal_history)
            
            # 绩效评级
            performance_grade = self._calculate_performance_grade(advanced_metrics, risk_metrics)
            
            # 综合分析结果
            analysis_result = {
                'stock_code': stock_code,
                'analysis_period_days': days,
                'basic_performance': performance,
                'advanced_metrics': advanced_metrics,
                'risk_metrics': risk_metrics,
                'performance_grade': performance_grade,
                'recommendations': self._generate_recommendations(
                    stock_code, advanced_metrics, risk_metrics
                ),
                'analysis_time': datetime.now().isoformat()
            }
            
            return analysis_result
            
        except Exception as e:
            self.logger.error(f"分析股票绩效失败: {e}")
            return {}
    
    def batch_performance_analysis(self, stock_codes: Optional[List[str]] = None) -> Dict[str, Any]:
        """批量绩效分析"""
        try:
            if not stock_codes:
                # 获取所有活跃股票
                core_pool = self.pool_manager.get_core_pool(status='active')
                stock_codes = [stock['stock_code'] for stock in core_pool]
            
            analysis_results = {}
            summary_stats = {
                'total_analyzed': 0,
                'excellent_performers': 0,
                'good_performers': 0,
                'average_performers': 0,
                'poor_performers': 0,
                'avg_win_rate': 0,
                'avg_return': 0,
                'avg_sharpe_ratio': 0
            }
            
            win_rates = []
            returns = []
            sharpe_ratios = []
            
            for stock_code in stock_codes:
                analysis = self.analyze_stock_performance(stock_code)
                if analysis:
                    analysis_results[stock_code] = analysis
                    summary_stats['total_analyzed'] += 1
                    
                    # 统计绩效等级
                    grade = analysis['performance_grade']['overall_grade']
                    if grade == 'excellent':
                        summary_stats['excellent_performers'] += 1
                    elif grade == 'good':
                        summary_stats['good_performers'] += 1
                    elif grade == 'average':
                        summary_stats['average_performers'] += 1
                    else:
                        summary_stats['poor_performers'] += 1
                    
                    # 收集指标用于平均值计算
                    metrics = analysis['advanced_metrics']
                    if metrics.get('win_rate') is not None:
                        win_rates.append(metrics['win_rate'])
                    if metrics.get('avg_return') is not None:
                        returns.append(metrics['avg_return'])
                    if metrics.get('sharpe_ratio') is not None:
                        sharpe_ratios.append(metrics['sharpe_ratio'])
            
            # 计算平均指标
            if win_rates:
                summary_stats['avg_win_rate'] = statistics.mean(win_rates)
            if returns:
                summary_stats['avg_return'] = statistics.mean(returns)
            if sharpe_ratios:
                summary_stats['avg_sharpe_ratio'] = statistics.mean(sharpe_ratios)
            
            return {
                'analysis_results': analysis_results,
                'summary_statistics': summary_stats,
                'analysis_time': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"批量绩效分析失败: {e}")
            return {}
    
    def adjust_pool_based_on_performance(self) -> Dict[str, Any]:
        """基于绩效调整观察池"""
        try:
            # 执行批量绩效分析
            batch_analysis = self.batch_performance_analysis()
            if not batch_analysis:
                return {'success': False, 'error': '批量分析失败'}
            
            adjustments = {
                'promoted': [],
                'demoted': [],
                'removed': [],
                'credibility_updated': []
            }
            
            for stock_code, analysis in batch_analysis['analysis_results'].items():
                stock_adjustments = self._determine_stock_adjustments(stock_code, analysis)
                
                if stock_adjustments['action'] == 'promote':
                    adjustments['promoted'].append({
                        'stock_code': stock_code,
                        'reason': stock_adjustments['reason'],
                        'new_credibility': stock_adjustments['new_credibility']
                    })
                elif stock_adjustments['action'] == 'demote':
                    adjustments['demoted'].append({
                        'stock_code': stock_code,
                        'reason': stock_adjustments['reason'],
                        'new_credibility': stock_adjustments['new_credibility']
                    })
                elif stock_adjustments['action'] == 'remove':
                    adjustments['removed'].append({
                        'stock_code': stock_code,
                        'reason': stock_adjustments['reason']
                    })
                
                # 更新信任度
                if stock_adjustments['new_credibility'] is not None:
                    success = self.pool_manager.update_stock_credibility(
                        stock_code, stock_adjustments['new_credibility']
                    )
                    if success:
                        adjustments['credibility_updated'].append({
                            'stock_code': stock_code,
                            'new_credibility': stock_adjustments['new_credibility']
                        })
            
            # 生成调整报告
            adjustment_report = {
                'success': True,
                'adjustments': adjustments,
                'summary': {
                    'total_promoted': len(adjustments['promoted']),
                    'total_demoted': len(adjustments['demoted']),
                    'total_removed': len(adjustments['removed']),
                    'total_credibility_updated': len(adjustments['credibility_updated'])
                },
                'adjustment_time': datetime.now().isoformat()
            }
            
            # 保存调整报告
            self._save_adjustment_report(adjustment_report)
            
            self.logger.info(f"观察池调整完成: 提升{len(adjustments['promoted'])}只, "
                           f"降级{len(adjustments['demoted'])}只, 移除{len(adjustments['removed'])}只")
            
            return adjustment_report
            
        except Exception as e:
            self.logger.error(f"基于绩效调整观察池失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def generate_performance_report(self, report_type: str = 'comprehensive') -> Dict[str, Any]:
        """生成绩效报告"""
        try:
            if report_type == 'comprehensive':
                return self._generate_comprehensive_report()
            elif report_type == 'summary':
                return self._generate_summary_report()
            elif report_type == 'risk_analysis':
                return self._generate_risk_analysis_report()
            else:
                raise ValueError(f"不支持的报告类型: {report_type}")
                
        except Exception as e:
            self.logger.error(f"生成绩效报告失败: {e}")
            return {}
    
    def _get_signal_info(self, signal_id: int) -> Optional[Dict]:
        """获取信号信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT stock_code, signal_type, confidence, trigger_price, 
                           signal_date, status
                    FROM signal_history 
                    WHERE id = ?
                ''', (signal_id,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        'stock_code': row[0],
                        'signal_type': row[1],
                        'confidence': row[2],
                        'trigger_price': row[3],
                        'signal_date': row[4],
                        'status': row[5]
                    }
                return None
                
        except Exception as e:
            self.logger.error(f"获取信号信息失败: {e}")
            return None
    
    def _get_signal_history(self, stock_code: str, days: int) -> List[Dict]:
        """获取信号历史"""
        try:
            since_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, signal_type, confidence, trigger_price, target_price,
                           stop_loss, actual_entry_price, actual_exit_price, 
                           actual_return, holding_days, status, signal_date,
                           entry_date, exit_date
                    FROM signal_history 
                    WHERE stock_code = ? AND signal_date >= ?
                    ORDER BY signal_date DESC
                ''', (stock_code, since_date))
                
                columns = ['id', 'signal_type', 'confidence', 'trigger_price', 
                          'target_price', 'stop_loss', 'actual_entry_price', 
                          'actual_exit_price', 'actual_return', 'holding_days', 
                          'status', 'signal_date', 'entry_date', 'exit_date']
                
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
                
        except Exception as e:
            self.logger.error(f"获取信号历史失败: {e}")
            return []
    
    def _calculate_advanced_metrics(self, signal_history: List[Dict]) -> Dict[str, Any]:
        """计算高级绩效指标"""
        if not signal_history:
            return {}
        
        try:
            # 过滤已完成的信号
            completed_signals = [s for s in signal_history if s['status'] == 'closed' and s['actual_return'] is not None]
            
            if not completed_signals:
                return {'insufficient_data': True}
            
            returns = [s['actual_return'] for s in completed_signals]
            holding_days = [s['holding_days'] for s in completed_signals if s['holding_days'] is not None]
            
            # 基础指标
            total_signals = len(completed_signals)
            winning_signals = len([r for r in returns if r > 0])
            win_rate = winning_signals / total_signals if total_signals > 0 else 0
            
            avg_return = statistics.mean(returns) if returns else 0
            total_return = sum(returns)
            
            # 风险指标
            return_std = statistics.stdev(returns) if len(returns) > 1 else 0
            max_return = max(returns) if returns else 0
            min_return = min(returns) if returns else 0
            max_drawdown = abs(min_return) if min_return < 0 else 0
            
            # 夏普比率
            excess_return = avg_return - self.config['risk_free_rate'] / 252  # 日化
            sharpe_ratio = excess_return / return_std if return_std > 0 else 0
            
            # 盈亏比
            winning_returns = [r for r in returns if r > 0]
            losing_returns = [r for r in returns if r < 0]
            
            avg_win = statistics.mean(winning_returns) if winning_returns else 0
            avg_loss = abs(statistics.mean(losing_returns)) if losing_returns else 0
            profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf')
            
            # 时间指标
            avg_holding_days = statistics.mean(holding_days) if holding_days else 0
            
            return {
                'total_signals': total_signals,
                'winning_signals': winning_signals,
                'losing_signals': total_signals - winning_signals,
                'win_rate': win_rate,
                'avg_return': avg_return,
                'total_return': total_return,
                'return_std': return_std,
                'max_return': max_return,
                'min_return': min_return,
                'max_drawdown': max_drawdown,
                'sharpe_ratio': sharpe_ratio,
                'profit_factor': profit_factor,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'avg_holding_days': avg_holding_days
            }
            
        except Exception as e:
            self.logger.error(f"计算高级指标失败: {e}")
            return {}
    
    def _calculate_risk_metrics(self, signal_history: List[Dict]) -> Dict[str, Any]:
        """计算风险指标"""
        try:
            completed_signals = [s for s in signal_history if s['status'] == 'closed' and s['actual_return'] is not None]
            
            if not completed_signals:
                return {}
            
            returns = [s['actual_return'] for s in completed_signals]
            
            # VaR (Value at Risk) - 95%置信度
            sorted_returns = sorted(returns)
            var_95 = sorted_returns[int(len(sorted_returns) * 0.05)] if len(sorted_returns) > 20 else min(returns)
            
            # 最大连续亏损
            max_consecutive_losses = 0
            current_consecutive_losses = 0
            
            for ret in returns:
                if ret < 0:
                    current_consecutive_losses += 1
                    max_consecutive_losses = max(max_consecutive_losses, current_consecutive_losses)
                else:
                    current_consecutive_losses = 0
            
            # 波动率
            volatility = statistics.stdev(returns) if len(returns) > 1 else 0
            
            # 下行风险
            negative_returns = [r for r in returns if r < 0]
            downside_deviation = statistics.stdev(negative_returns) if len(negative_returns) > 1 else 0
            
            # Sortino比率
            avg_return = statistics.mean(returns)
            sortino_ratio = (avg_return - self.config['risk_free_rate'] / 252) / downside_deviation if downside_deviation > 0 else 0
            
            return {
                'var_95': var_95,
                'max_consecutive_losses': max_consecutive_losses,
                'volatility': volatility,
                'downside_deviation': downside_deviation,
                'sortino_ratio': sortino_ratio,
                'risk_level': self._assess_risk_level(volatility, var_95, max_consecutive_losses)
            }
            
        except Exception as e:
            self.logger.error(f"计算风险指标失败: {e}")
            return {}
    
    def _calculate_performance_grade(self, advanced_metrics: Dict, risk_metrics: Dict) -> Dict[str, Any]:
        """计算绩效评级"""
        try:
            if not advanced_metrics or advanced_metrics.get('insufficient_data'):
                return {'overall_grade': 'insufficient_data', 'score': 0}
            
            # 各项指标评分 (0-100)
            scores = {}
            
            # 胜率评分
            win_rate = advanced_metrics.get('win_rate', 0)
            scores['win_rate'] = min(100, win_rate * 125)  # 80%胜率 = 100分
            
            # 平均收益评分
            avg_return = advanced_metrics.get('avg_return', 0)
            scores['avg_return'] = min(100, max(0, (avg_return + 0.05) * 1000))  # 5%收益 = 100分
            
            # 夏普比率评分
            sharpe_ratio = advanced_metrics.get('sharpe_ratio', 0)
            scores['sharpe_ratio'] = min(100, max(0, sharpe_ratio * 50))  # 2.0夏普比率 = 100分
            
            # 盈亏比评分
            profit_factor = advanced_metrics.get('profit_factor', 0)
            if profit_factor == float('inf'):
                scores['profit_factor'] = 100
            else:
                scores['profit_factor'] = min(100, profit_factor * 33.33)  # 3.0盈亏比 = 100分
            
            # 风险评分 (风险越低分数越高)
            max_drawdown = advanced_metrics.get('max_drawdown', 0)
            scores['risk'] = max(0, 100 - max_drawdown * 500)  # 20%最大回撤 = 0分
            
            # 综合评分 (加权平均)
            weights = {
                'win_rate': 0.25,
                'avg_return': 0.25,
                'sharpe_ratio': 0.20,
                'profit_factor': 0.15,
                'risk': 0.15
            }
            
            overall_score = sum(scores[key] * weights[key] for key in weights)
            
            # 确定等级
            if overall_score >= 80:
                grade = 'excellent'
            elif overall_score >= 60:
                grade = 'good'
            elif overall_score >= 40:
                grade = 'average'
            else:
                grade = 'poor'
            
            return {
                'overall_grade': grade,
                'overall_score': overall_score,
                'component_scores': scores,
                'weights': weights
            }
            
        except Exception as e:
            self.logger.error(f"计算绩效评级失败: {e}")
            return {'overall_grade': 'error', 'score': 0}
    
    def _determine_stock_adjustments(self, stock_code: str, analysis: Dict) -> Dict[str, Any]:
        """确定股票调整方案"""
        try:
            performance_grade = analysis['performance_grade']['overall_grade']
            current_credibility = analysis['basic_performance'].get('credibility_score', 1.0)
            
            # 根据绩效等级确定调整
            adjustments = self.config.get('credibility_adjustments', {
                'excellent': 1.2,
                'good': 1.1,
                'average': 1.0,
                'poor': 0.8,
                'very_poor': 0.6
            })
            
            if performance_grade == 'excellent':
                new_credibility = min(1.0, current_credibility * adjustments['excellent'])
                return {
                    'action': 'promote',
                    'reason': f'优秀绩效 (评分: {analysis["performance_grade"]["overall_score"]:.1f})',
                    'new_credibility': new_credibility
                }
            elif performance_grade == 'good':
                new_credibility = min(1.0, current_credibility * adjustments['good'])
                return {
                    'action': 'promote' if new_credibility > current_credibility else 'maintain',
                    'reason': f'良好绩效 (评分: {analysis["performance_grade"]["overall_score"]:.1f})',
                    'new_credibility': new_credibility
                }
            elif performance_grade == 'average':
                new_credibility = current_credibility * adjustments['average']
                return {
                    'action': 'maintain',
                    'reason': f'平均绩效 (评分: {analysis["performance_grade"]["overall_score"]:.1f})',
                    'new_credibility': new_credibility
                }
            elif performance_grade == 'poor':
                new_credibility = current_credibility * adjustments['poor']
                if new_credibility < 0.3:  # 信任度过低，移除
                    return {
                        'action': 'remove',
                        'reason': f'绩效不佳，信任度过低 (评分: {analysis["performance_grade"]["overall_score"]:.1f})',
                        'new_credibility': None
                    }
                else:
                    return {
                        'action': 'demote',
                        'reason': f'绩效不佳 (评分: {analysis["performance_grade"]["overall_score"]:.1f})',
                        'new_credibility': new_credibility
                    }
            else:
                return {
                    'action': 'maintain',
                    'reason': '数据不足或评级错误',
                    'new_credibility': current_credibility
                }
                
        except Exception as e:
            self.logger.error(f"确定股票调整方案失败: {e}")
            return {
                'action': 'maintain',
                'reason': f'分析失败: {e}',
                'new_credibility': None
            }
    
    def _assess_risk_level(self, volatility: float, var_95: float, max_consecutive_losses: int) -> str:
        """评估风险等级"""
        risk_score = 0
        
        # 波动率评分
        if volatility > 0.05:
            risk_score += 3
        elif volatility > 0.03:
            risk_score += 2
        elif volatility > 0.02:
            risk_score += 1
        
        # VaR评分
        if var_95 < -0.08:
            risk_score += 3
        elif var_95 < -0.05:
            risk_score += 2
        elif var_95 < -0.03:
            risk_score += 1
        
        # 连续亏损评分
        if max_consecutive_losses >= 5:
            risk_score += 3
        elif max_consecutive_losses >= 3:
            risk_score += 2
        elif max_consecutive_losses >= 2:
            risk_score += 1
        
        # 确定风险等级
        if risk_score >= 7:
            return 'VERY_HIGH'
        elif risk_score >= 5:
            return 'HIGH'
        elif risk_score >= 3:
            return 'MEDIUM'
        elif risk_score >= 1:
            return 'LOW'
        else:
            return 'VERY_LOW'
    
    def _generate_recommendations(self, stock_code: str, advanced_metrics: Dict, 
                                risk_metrics: Dict) -> List[str]:
        """生成建议"""
        recommendations = []
        
        try:
            # 基于胜率的建议
            win_rate = advanced_metrics.get('win_rate', 0)
            if win_rate < 0.4:
                recommendations.append("胜率偏低，建议重新优化策略参数")
            elif win_rate > 0.7:
                recommendations.append("胜率优秀，可以考虑增加仓位")
            
            # 基于盈亏比的建议
            profit_factor = advanced_metrics.get('profit_factor', 0)
            if profit_factor < 1.5:
                recommendations.append("盈亏比偏低，建议优化止盈止损策略")
            elif profit_factor > 3.0:
                recommendations.append("盈亏比优秀，策略表现良好")
            
            # 基于风险的建议
            risk_level = risk_metrics.get('risk_level', 'MEDIUM')
            if risk_level in ['HIGH', 'VERY_HIGH']:
                recommendations.append("风险较高，建议降低仓位或加强风控")
            elif risk_level in ['LOW', 'VERY_LOW']:
                recommendations.append("风险可控，可以考虑适当增加仓位")
            
            # 基于最大回撤的建议
            max_drawdown = advanced_metrics.get('max_drawdown', 0)
            if max_drawdown > 0.15:
                recommendations.append("最大回撤过大，建议加强止损管理")
            
            # 基于持仓时间的建议
            avg_holding_days = advanced_metrics.get('avg_holding_days', 0)
            if avg_holding_days > 10:
                recommendations.append("平均持仓时间较长，可能需要优化出场时机")
            elif avg_holding_days < 2:
                recommendations.append("持仓时间较短，注意交易成本影响")
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"生成建议失败: {e}")
            return ["分析过程中出现错误，建议人工复核"]
    
    def _update_stock_performance(self, stock_code: str, actual_data: Dict) -> None:
        """更新股票绩效统计"""
        try:
            # 这里可以实现更复杂的绩效更新逻辑
            # 例如：更新胜率、平均收益等统计数据
            pass
            
        except Exception as e:
            self.logger.error(f"更新股票绩效统计失败: {e}")
    
    def _record_performance_data(self, signal_info: Dict, actual_data: Dict) -> None:
        """记录绩效跟踪数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT OR REPLACE INTO performance_tracking 
                    (stock_code, tracking_date, predicted_direction, actual_direction,
                     prediction_accuracy, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    signal_info['stock_code'],
                    datetime.now().date().isoformat(),
                    signal_info['signal_type'],
                    'up' if actual_data.get('actual_return', 0) > 0 else 'down',
                    1.0 if (signal_info['signal_type'] == 'buy' and actual_data.get('actual_return', 0) > 0) or 
                           (signal_info['signal_type'] == 'sell' and actual_data.get('actual_return', 0) < 0) else 0.0,
                    datetime.now().isoformat()
                ))
                
                conn.commit()
                
        except Exception as e:
            self.logger.error(f"记录绩效跟踪数据失败: {e}")
    
    def _generate_comprehensive_report(self) -> Dict[str, Any]:
        """生成综合绩效报告"""
        try:
            # 批量分析所有股票
            batch_analysis = self.batch_performance_analysis()
            
            # 系统整体统计
            pool_stats = self.pool_manager.get_pool_statistics()
            
            # 生成报告
            report = {
                'report_type': 'comprehensive',
                'report_date': datetime.now().isoformat(),
                'system_overview': pool_stats,
                'performance_analysis': batch_analysis,
                'top_performers': self._get_top_performers(batch_analysis),
                'risk_analysis': self._get_system_risk_analysis(batch_analysis),
                'recommendations': self._get_system_recommendations(batch_analysis)
            }
            
            # 保存报告
            self._save_performance_report(report)
            
            return report
            
        except Exception as e:
            self.logger.error(f"生成综合报告失败: {e}")
            return {}
    
    def _generate_summary_report(self) -> Dict[str, Any]:
        """生成摘要报告"""
        try:
            pool_stats = self.pool_manager.get_pool_statistics()
            
            return {
                'report_type': 'summary',
                'report_date': datetime.now().isoformat(),
                'key_metrics': {
                    'total_stocks': pool_stats.get('total_stocks', 0),
                    'active_stocks': pool_stats.get('active_stocks', 0),
                    'overall_win_rate': pool_stats.get('overall_win_rate', 0),
                    'total_signals': pool_stats.get('total_signals', 0),
                    'recent_signals': pool_stats.get('recent_signals', 0)
                }
            }
            
        except Exception as e:
            self.logger.error(f"生成摘要报告失败: {e}")
            return {}
    
    def _generate_risk_analysis_report(self) -> Dict[str, Any]:
        """生成风险分析报告"""
        try:
            batch_analysis = self.batch_performance_analysis()
            risk_analysis = self._get_system_risk_analysis(batch_analysis)
            
            return {
                'report_type': 'risk_analysis',
                'report_date': datetime.now().isoformat(),
                'risk_analysis': risk_analysis
            }
            
        except Exception as e:
            self.logger.error(f"生成风险分析报告失败: {e}")
            return {}
    
    def _get_top_performers(self, batch_analysis: Dict) -> List[Dict]:
        """获取表现最佳的股票"""
        try:
            if not batch_analysis.get('analysis_results'):
                return []
            
            performers = []
            for stock_code, analysis in batch_analysis['analysis_results'].items():
                if analysis['performance_grade']['overall_grade'] in ['excellent', 'good']:
                    performers.append({
                        'stock_code': stock_code,
                        'grade': analysis['performance_grade']['overall_grade'],
                        'score': analysis['performance_grade']['overall_score'],
                        'win_rate': analysis['advanced_metrics'].get('win_rate', 0),
                        'avg_return': analysis['advanced_metrics'].get('avg_return', 0)
                    })
            
            # 按评分排序
            performers.sort(key=lambda x: x['score'], reverse=True)
            return performers[:10]  # 返回前10名
            
        except Exception as e:
            self.logger.error(f"获取顶级表现者失败: {e}")
            return []
    
    def _get_system_risk_analysis(self, batch_analysis: Dict) -> Dict[str, Any]:
        """获取系统风险分析"""
        try:
            if not batch_analysis.get('analysis_results'):
                return {}
            
            risk_levels = {'VERY_LOW': 0, 'LOW': 0, 'MEDIUM': 0, 'HIGH': 0, 'VERY_HIGH': 0}
            total_analyzed = 0
            
            for analysis in batch_analysis['analysis_results'].values():
                risk_metrics = analysis.get('risk_metrics', {})
                risk_level = risk_metrics.get('risk_level', 'MEDIUM')
                if risk_level in risk_levels:
                    risk_levels[risk_level] += 1
                total_analyzed += 1
            
            return {
                'risk_distribution': risk_levels,
                'total_analyzed': total_analyzed,
                'high_risk_percentage': (risk_levels['HIGH'] + risk_levels['VERY_HIGH']) / total_analyzed * 100 if total_analyzed > 0 else 0
            }
            
        except Exception as e:
            self.logger.error(f"获取系统风险分析失败: {e}")
            return {}
    
    def _get_system_recommendations(self, batch_analysis: Dict) -> List[str]:
        """获取系统级建议"""
        recommendations = []
        
        try:
            summary = batch_analysis.get('summary_statistics', {})
            
            # 基于整体胜率的建议
            avg_win_rate = summary.get('avg_win_rate', 0)
            if avg_win_rate < 0.5:
                recommendations.append("系统整体胜率偏低，建议全面优化策略参数")
            elif avg_win_rate > 0.7:
                recommendations.append("系统整体胜率优秀，可以考虑扩大投资规模")
            
            # 基于绩效分布的建议
            excellent_count = summary.get('excellent_performers', 0)
            total_count = summary.get('total_analyzed', 1)
            
            if excellent_count / total_count < 0.1:
                recommendations.append("优秀表现股票比例较低，建议加强股票筛选标准")
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"获取系统建议失败: {e}")
            return ["系统分析出现错误，建议人工检查"]
    
    def _save_performance_report(self, report: Dict) -> None:
        """保存绩效报告"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'reports/performance_report_{report["report_type"]}_{timestamp}.json'
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"绩效报告已保存: {filename}")
            
        except Exception as e:
            self.logger.error(f"保存绩效报告失败: {e}")
    
    def _save_adjustment_report(self, report: Dict) -> None:
        """保存调整报告"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'reports/pool_adjustment_{timestamp}.json'
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"调整报告已保存: {filename}")
            
        except Exception as e:
            self.logger.error(f"保存调整报告失败: {e}")


def main():
    """测试函数"""
    logging.basicConfig(level=logging.INFO)
    
    # 创建绩效跟踪器
    tracker = PerformanceTracker()
    
    print("🎯 绩效跟踪器测试")
    print("=" * 50)
    
    # 测试批量绩效分析
    print("📊 执行批量绩效分析...")
    batch_result = tracker.batch_performance_analysis(['sz300290', 'sh600000'])
    
    if batch_result:
        print("✅ 批量分析成功")
        summary = batch_result['summary_statistics']
        print(f"  - 分析股票数: {summary['total_analyzed']}")
        print(f"  - 优秀表现: {summary['excellent_performers']}")
        print(f"  - 良好表现: {summary['good_performers']}")
        print(f"  - 平均胜率: {summary['avg_win_rate']:.1%}")
    
    # 测试观察池调整
    print("\n🔧 执行观察池调整...")
    adjustment_result = tracker.adjust_pool_based_on_performance()
    
    if adjustment_result.get('success'):
        print("✅ 观察池调整成功")
        summary = adjustment_result['summary']
        print(f"  - 提升股票: {summary['total_promoted']}")
        print(f"  - 降级股票: {summary['total_demoted']}")
        print(f"  - 移除股票: {summary['total_removed']}")
    
    # 测试生成综合报告
    print("\n📋 生成综合绩效报告...")
    report = tracker.generate_performance_report('comprehensive')
    
    if report:
        print("✅ 综合报告生成成功")
        print(f"  - 报告类型: {report['report_type']}")
        print(f"  - 生成时间: {report['report_date']}")


if __name__ == "__main__":
    main()