#!/usr/bin/env python3
"""
多周期实时监控系统
实现多时间框架信号的实时监控和智能预警
"""

import os
import sys
import json
import pandas as pd
import numpy as np
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
import logging
from pathlib import Path
from collections import defaultdict, deque

# 添加backend目录到路径
sys.path.append(os.path.dirname(__file__))

from multi_timeframe_data_manager import MultiTimeframeDataManager
from multi_timeframe_signal_generator import MultiTimeframeSignalGenerator
from notification_system import NotificationSystem

class MultiTimeframeMonitor:
    """多周期实时监控器"""
    
    def __init__(self, 
                 data_manager: MultiTimeframeDataManager = None,
                 signal_generator: MultiTimeframeSignalGenerator = None,
                 notification_system: NotificationSystem = None):
        """初始化多周期监控器"""
        
        self.data_manager = data_manager or MultiTimeframeDataManager()
        self.signal_generator = signal_generator or MultiTimeframeSignalGenerator(self.data_manager)
        self.notification_system = notification_system or NotificationSystem()
        
        # 监控配置
        self.monitoring_config = {
            'update_interval': 60,  # 更新间隔（秒）
            'max_stocks': 100,      # 最大监控股票数
            'alert_cooldown': 300,  # 预警冷却时间（秒）
            'history_length': 1000, # 历史记录长度
            'auto_cleanup': True    # 自动清理过期数据
        }
        
        # 监控状态
        self.monitored_stocks = set()
        self.monitoring_active = False
        self.monitor_thread = None
        
        # 数据存储
        self.signal_history = defaultdict(lambda: deque(maxlen=self.monitoring_config['history_length']))
        self.alert_history = defaultdict(lambda: deque(maxlen=100))
        self.last_alerts = {}  # 用于冷却时间控制
        
        # 预警条件
        self.alert_conditions = {
            'signal_convergence': {
                'enabled': True,
                'threshold': 0.7,
                'description': '多周期信号收敛'
            },
            'trend_change': {
                'enabled': True,
                'threshold': 0.6,
                'description': '趋势转换'
            },
            'breakout': {
                'enabled': True,
                'threshold': 0.5,
                'description': '关键位突破'
            },
            'risk_level_change': {
                'enabled': True,
                'threshold': 0.3,
                'description': '风险等级变化'
            }
        }
        
        # 统计信息
        self.monitoring_stats = {
            'start_time': None,
            'total_updates': 0,
            'total_alerts': 0,
            'successful_signals': 0,
            'failed_signals': 0,
            'avg_update_time': 0.0
        }
        
        self.logger = logging.getLogger(__name__)
        
        # 创建监控报告目录
        self.reports_dir = Path("reports/monitoring")
        self.reports_dir.mkdir(parents=True, exist_ok=True)
    
    def add_stock_to_monitor(self, stock_code: str, alert_conditions: Dict = None) -> bool:
        """添加股票到监控列表"""
        try:
            if len(self.monitored_stocks) >= self.monitoring_config['max_stocks']:
                self.logger.warning(f"监控股票数量已达上限 {self.monitoring_config['max_stocks']}")
                return False
            
            self.monitored_stocks.add(stock_code)
            
            # 设置个股特定的预警条件
            if alert_conditions:
                # 这里可以为特定股票设置特殊的预警条件
                pass
            
            self.logger.info(f"添加 {stock_code} 到监控列表")
            return True
            
        except Exception as e:
            self.logger.error(f"添加监控股票失败: {e}")
            return False
    
    def remove_stock_from_monitor(self, stock_code: str) -> bool:
        """从监控列表移除股票"""
        try:
            if stock_code in self.monitored_stocks:
                self.monitored_stocks.remove(stock_code)
                
                # 清理历史数据
                if stock_code in self.signal_history:
                    del self.signal_history[stock_code]
                if stock_code in self.alert_history:
                    del self.alert_history[stock_code]
                if stock_code in self.last_alerts:
                    del self.last_alerts[stock_code]
                
                self.logger.info(f"从监控列表移除 {stock_code}")
                return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"移除监控股票失败: {e}")
            return False
    
    def start_monitoring(self) -> bool:
        """开始监控"""
        try:
            if self.monitoring_active:
                self.logger.warning("监控已在运行中")
                return False
            
            if not self.monitored_stocks:
                self.logger.warning("没有股票需要监控")
                return False
            
            self.monitoring_active = True
            self.monitoring_stats['start_time'] = datetime.now()
            
            # 启动监控线程
            self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
            self.monitor_thread.start()
            
            self.logger.info(f"开始监控 {len(self.monitored_stocks)} 只股票")
            return True
            
        except Exception as e:
            self.logger.error(f"启动监控失败: {e}")
            self.monitoring_active = False
            return False
    
    def stop_monitoring(self) -> bool:
        """停止监控"""
        try:
            if not self.monitoring_active:
                return True
            
            self.monitoring_active = False
            
            # 等待监控线程结束
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=10)
            
            # 生成监控报告
            self._generate_monitoring_report()
            
            self.logger.info("监控已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"停止监控失败: {e}")
            return False
    
    def _monitoring_loop(self):
        """监控主循环"""
        self.logger.info("监控循环开始")
        
        while self.monitoring_active:
            try:
                loop_start_time = time.time()
                
                # 更新所有监控股票的信号
                self._update_all_signals()
                
                # 检查预警条件
                self._check_alert_conditions()
                
                # 更新统计信息
                loop_duration = time.time() - loop_start_time
                self.monitoring_stats['total_updates'] += 1
                self.monitoring_stats['avg_update_time'] = (
                    (self.monitoring_stats['avg_update_time'] * (self.monitoring_stats['total_updates'] - 1) + loop_duration) /
                    self.monitoring_stats['total_updates']
                )
                
                # 自动清理过期数据
                if self.monitoring_config['auto_cleanup']:
                    self._cleanup_expired_data()
                
                # 等待下次更新
                time.sleep(self.monitoring_config['update_interval'])
                
            except Exception as e:
                self.logger.error(f"监控循环错误: {e}")
                time.sleep(5)  # 错误后短暂等待
    
    def _update_all_signals(self):
        """更新所有监控股票的信号"""
        for stock_code in list(self.monitored_stocks):  # 使用list避免迭代时修改
            try:
                self._update_stock_signal(stock_code)
            except Exception as e:
                self.logger.error(f"更新 {stock_code} 信号失败: {e}")
    
    def _update_stock_signal(self, stock_code: str):
        """更新单个股票的信号"""
        try:
            # 生成最新信号
            signal_result = self.signal_generator.generate_composite_signals(stock_code)
            
            if 'error' in signal_result:
                self.logger.warning(f"{stock_code} 信号生成失败: {signal_result['error']}")
                return
            
            # 添加时间戳
            signal_result['timestamp'] = datetime.now().isoformat()
            
            # 存储到历史记录
            self.signal_history[stock_code].append(signal_result)
            
            # 检查信号变化
            self._analyze_signal_changes(stock_code, signal_result)
            
        except Exception as e:
            self.logger.error(f"更新 {stock_code} 信号失败: {e}")
    
    def _analyze_signal_changes(self, stock_code: str, current_signal: Dict):
        """分析信号变化"""
        try:
            history = self.signal_history[stock_code]
            if len(history) < 2:
                return
            
            previous_signal = history[-2]
            
            # 比较信号强度变化
            current_strength = current_signal.get('composite_signal', {}).get('signal_strength', 'neutral')
            previous_strength = previous_signal.get('composite_signal', {}).get('signal_strength', 'neutral')
            
            if current_strength != previous_strength:
                self.logger.info(f"{stock_code} 信号强度变化: {previous_strength} -> {current_strength}")
            
            # 比较置信度变化
            current_confidence = current_signal.get('composite_signal', {}).get('confidence_level', 0)
            previous_confidence = previous_signal.get('composite_signal', {}).get('confidence_level', 0)
            
            confidence_change = abs(current_confidence - previous_confidence)
            if confidence_change > 0.2:
                self.logger.info(f"{stock_code} 置信度显著变化: {previous_confidence:.3f} -> {current_confidence:.3f}")
            
            # 比较风险等级变化
            current_risk = current_signal.get('risk_assessment', {}).get('overall_risk_level', 'medium')
            previous_risk = previous_signal.get('risk_assessment', {}).get('overall_risk_level', 'medium')
            
            if current_risk != previous_risk:
                self.logger.info(f"{stock_code} 风险等级变化: {previous_risk} -> {current_risk}")
            
        except Exception as e:
            self.logger.error(f"分析 {stock_code} 信号变化失败: {e}")
    
    def _check_alert_conditions(self):
        """检查预警条件"""
        for stock_code in self.monitored_stocks:
            try:
                self._check_stock_alerts(stock_code)
            except Exception as e:
                self.logger.error(f"检查 {stock_code} 预警失败: {e}")
    
    def _check_stock_alerts(self, stock_code: str):
        """检查单个股票的预警条件"""
        try:
            history = self.signal_history[stock_code]
            if len(history) == 0:
                return
            
            current_signal = history[-1]
            
            # 检查冷却时间
            if self._is_in_cooldown(stock_code):
                return
            
            alerts_triggered = []
            
            # 1. 检查信号收敛预警
            if self.alert_conditions['signal_convergence']['enabled']:
                convergence_alert = self._check_signal_convergence(stock_code, current_signal)
                if convergence_alert:
                    alerts_triggered.append(convergence_alert)
            
            # 2. 检查趋势变化预警
            if self.alert_conditions['trend_change']['enabled']:
                trend_alert = self._check_trend_change(stock_code, current_signal)
                if trend_alert:
                    alerts_triggered.append(trend_alert)
            
            # 3. 检查突破预警
            if self.alert_conditions['breakout']['enabled']:
                breakout_alert = self._check_breakout(stock_code, current_signal)
                if breakout_alert:
                    alerts_triggered.append(breakout_alert)
            
            # 4. 检查风险等级变化预警
            if self.alert_conditions['risk_level_change']['enabled']:
                risk_alert = self._check_risk_level_change(stock_code, current_signal)
                if risk_alert:
                    alerts_triggered.append(risk_alert)
            
            # 发送预警
            for alert in alerts_triggered:
                self._send_alert(stock_code, alert)
            
        except Exception as e:
            self.logger.error(f"检查 {stock_code} 预警条件失败: {e}")
    
    def _check_signal_convergence(self, stock_code: str, current_signal: Dict) -> Optional[Dict]:
        """检查信号收敛预警"""
        try:
            composite_signal = current_signal.get('composite_signal', {})
            confidence_level = composite_signal.get('confidence_level', 0)
            final_score = abs(composite_signal.get('final_score', 0))
            
            threshold = self.alert_conditions['signal_convergence']['threshold']
            
            if confidence_level >= threshold and final_score >= 0.5:
                return {
                    'type': 'signal_convergence',
                    'message': f'多周期信号收敛 (置信度: {confidence_level:.3f}, 强度: {final_score:.3f})',
                    'severity': 'high' if confidence_level >= 0.8 else 'medium',
                    'data': {
                        'confidence_level': confidence_level,
                        'final_score': final_score,
                        'signal_strength': composite_signal.get('signal_strength', 'neutral')
                    }
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"检查 {stock_code} 信号收敛失败: {e}")
            return None
    
    def _check_trend_change(self, stock_code: str, current_signal: Dict) -> Optional[Dict]:
        """检查趋势变化预警"""
        try:
            history = self.signal_history[stock_code]
            if len(history) < 3:
                return None
            
            # 获取最近3个信号的趋势强度
            recent_signals = list(history)[-3:]
            trend_scores = []
            
            for signal in recent_signals:
                composite = signal.get('composite_signal', {})
                score = composite.get('final_score', 0)
                trend_scores.append(score)
            
            # 检查趋势反转
            if len(trend_scores) >= 3:
                # 从负转正或从正转负
                if (trend_scores[0] < -0.2 and trend_scores[1] < 0 and trend_scores[2] > 0.2) or \
                   (trend_scores[0] > 0.2 and trend_scores[1] > 0 and trend_scores[2] < -0.2):
                    
                    return {
                        'type': 'trend_change',
                        'message': f'趋势发生反转 ({trend_scores[0]:.3f} -> {trend_scores[2]:.3f})',
                        'severity': 'high',
                        'data': {
                            'trend_scores': trend_scores,
                            'change_magnitude': abs(trend_scores[2] - trend_scores[0])
                        }
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"检查 {stock_code} 趋势变化失败: {e}")
            return None
    
    def _check_breakout(self, stock_code: str, current_signal: Dict) -> Optional[Dict]:
        """检查突破预警"""
        try:
            # 检查突破信号
            strategy_signals = current_signal.get('strategy_signals', {})
            breakout_strategy = strategy_signals.get('breakout', {})
            
            if 'error' not in breakout_strategy:
                breakout_score = breakout_strategy.get('signal_score', 0)
                confidence = breakout_strategy.get('confidence', 0)
                
                threshold = self.alert_conditions['breakout']['threshold']
                
                if abs(breakout_score) >= threshold and confidence >= 0.5:
                    return {
                        'type': 'breakout',
                        'message': f'检测到突破信号 (强度: {breakout_score:.3f}, 置信度: {confidence:.3f})',
                        'severity': 'medium',
                        'data': {
                            'breakout_score': breakout_score,
                            'confidence': confidence,
                            'direction': 'upward' if breakout_score > 0 else 'downward'
                        }
                    }
            
            return None
            
        except Exception as e:
            self.logger.error(f"检查 {stock_code} 突破失败: {e}")
            return None
    
    def _check_risk_level_change(self, stock_code: str, current_signal: Dict) -> Optional[Dict]:
        """检查风险等级变化预警"""
        try:
            history = self.signal_history[stock_code]
            if len(history) < 2:
                return None
            
            current_risk = current_signal.get('risk_assessment', {}).get('overall_risk_level', 'medium')
            previous_risk = history[-2].get('risk_assessment', {}).get('overall_risk_level', 'medium')
            
            # 定义风险等级数值
            risk_levels = {'low': 1, 'medium': 2, 'high': 3}
            
            current_level = risk_levels.get(current_risk, 2)
            previous_level = risk_levels.get(previous_risk, 2)
            
            # 风险等级显著变化
            if abs(current_level - previous_level) >= 1:
                return {
                    'type': 'risk_level_change',
                    'message': f'风险等级变化: {previous_risk} -> {current_risk}',
                    'severity': 'high' if current_risk == 'high' else 'medium',
                    'data': {
                        'previous_risk': previous_risk,
                        'current_risk': current_risk,
                        'risk_change': current_level - previous_level
                    }
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"检查 {stock_code} 风险等级变化失败: {e}")
            return None
    
    def _is_in_cooldown(self, stock_code: str) -> bool:
        """检查是否在冷却时间内"""
        if stock_code not in self.last_alerts:
            return False
        
        last_alert_time = self.last_alerts[stock_code]
        cooldown_period = self.monitoring_config['alert_cooldown']
        
        return (datetime.now() - last_alert_time).total_seconds() < cooldown_period
    
    def _send_alert(self, stock_code: str, alert: Dict):
        """发送预警"""
        try:
            # 记录预警时间
            self.last_alerts[stock_code] = datetime.now()
            
            # 添加到预警历史
            alert_record = {
                'timestamp': datetime.now().isoformat(),
                'stock_code': stock_code,
                'alert': alert
            }
            self.alert_history[stock_code].append(alert_record)
            
            # 更新统计
            self.monitoring_stats['total_alerts'] += 1
            
            # 构建通知消息
            message = f"【{stock_code}】{alert['message']}"
            
            # 发送通知
            if self.notification_system:
                self.notification_system.send_notification(
                    title=f"多周期监控预警 - {alert['type']}",
                    message=message,
                    level=alert.get('severity', 'medium'),
                    data=alert.get('data', {})
                )
            
            self.logger.info(f"发送预警: {message}")
            
        except Exception as e:
            self.logger.error(f"发送预警失败: {e}")
    
    def _cleanup_expired_data(self):
        """清理过期数据"""
        try:
            # 这里可以添加清理逻辑，比如删除过期的历史记录
            pass
        except Exception as e:
            self.logger.error(f"清理过期数据失败: {e}")
    
    def get_monitoring_status(self) -> Dict:
        """获取监控状态"""
        return {
            'monitoring_active': self.monitoring_active,
            'monitored_stocks_count': len(self.monitored_stocks),
            'monitored_stocks': list(self.monitored_stocks),
            'stats': self.monitoring_stats.copy(),
            'alert_conditions': self.alert_conditions.copy(),
            'config': self.monitoring_config.copy()
        }
    
    def get_stock_signal_history(self, stock_code: str, limit: int = 10) -> List[Dict]:
        """获取股票信号历史"""
        if stock_code not in self.signal_history:
            return []
        
        history = list(self.signal_history[stock_code])
        return history[-limit:] if limit > 0 else history
    
    def get_stock_alert_history(self, stock_code: str, limit: int = 10) -> List[Dict]:
        """获取股票预警历史"""
        if stock_code not in self.alert_history:
            return []
        
        history = list(self.alert_history[stock_code])
        return history[-limit:] if limit > 0 else history
    
    def _generate_monitoring_report(self):
        """生成监控报告"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            report = {
                'report_type': 'monitoring_summary',
                'generation_time': datetime.now().isoformat(),
                'monitoring_period': {
                    'start_time': self.monitoring_stats['start_time'].isoformat() if self.monitoring_stats['start_time'] else None,
                    'end_time': datetime.now().isoformat(),
                    'duration_hours': (datetime.now() - self.monitoring_stats['start_time']).total_seconds() / 3600 if self.monitoring_stats['start_time'] else 0
                },
                'statistics': self.monitoring_stats.copy(),
                'monitored_stocks': list(self.monitored_stocks),
                'alert_summary': self._generate_alert_summary(),
                'performance_analysis': self._analyze_monitoring_performance()
            }
            
            # 保存报告
            report_file = self.reports_dir / f"monitoring_report_{timestamp}.json"
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            
            self.logger.info(f"监控报告已保存: {report_file}")
            
        except Exception as e:
            self.logger.error(f"生成监控报告失败: {e}")
    
    def _generate_alert_summary(self) -> Dict:
        """生成预警摘要"""
        try:
            alert_summary = {
                'total_alerts': 0,
                'alert_by_type': defaultdict(int),
                'alert_by_severity': defaultdict(int),
                'alert_by_stock': defaultdict(int),
                'most_active_stocks': []
            }
            
            for stock_code, alerts in self.alert_history.items():
                for alert_record in alerts:
                    alert = alert_record['alert']
                    alert_summary['total_alerts'] += 1
                    alert_summary['alert_by_type'][alert['type']] += 1
                    alert_summary['alert_by_severity'][alert.get('severity', 'medium')] += 1
                    alert_summary['alert_by_stock'][stock_code] += 1
            
            # 最活跃的股票
            stock_alerts = list(alert_summary['alert_by_stock'].items())
            stock_alerts.sort(key=lambda x: x[1], reverse=True)
            alert_summary['most_active_stocks'] = stock_alerts[:10]
            
            return dict(alert_summary)
            
        except Exception as e:
            self.logger.error(f"生成预警摘要失败: {e}")
            return {}
    
    def _analyze_monitoring_performance(self) -> Dict:
        """分析监控性能"""
        try:
            performance = {
                'avg_update_time': self.monitoring_stats['avg_update_time'],
                'update_frequency': self.monitoring_config['update_interval'],
                'system_efficiency': 0.0,
                'alert_accuracy': 0.0,
                'recommendations': []
            }
            
            # 系统效率评估
            if self.monitoring_stats['avg_update_time'] > 0:
                performance['system_efficiency'] = min(1.0, 30 / self.monitoring_stats['avg_update_time'])
            
            # 建议
            if self.monitoring_stats['avg_update_time'] > 60:
                performance['recommendations'].append('考虑增加更新间隔或减少监控股票数量')
            
            if self.monitoring_stats['total_alerts'] > self.monitoring_stats['total_updates'] * 0.1:
                performance['recommendations'].append('预警频率较高，考虑调整预警阈值')
            
            return performance
            
        except Exception as e:
            self.logger.error(f"分析监控性能失败: {e}")
            return {}

def main():
    """测试函数"""
    print("📡 多周期实时监控系统测试")
    print("=" * 50)
    
    # 创建监控器
    monitor = MultiTimeframeMonitor()
    
    # 添加测试股票
    test_stocks = ['sz300290', 'sz002691']
    
    for stock_code in test_stocks:
        success = monitor.add_stock_to_monitor(stock_code)
        print(f"添加 {stock_code} 到监控: {'✅' if success else '❌'}")
    
    # 获取监控状态
    status = monitor.get_monitoring_status()
    print(f"\n📊 监控状态:")
    print(f"  监控股票数: {status['monitored_stocks_count']}")
    print(f"  监控活跃: {status['monitoring_active']}")
    
    # 手动更新一次信号（测试用）
    print(f"\n🔄 手动更新信号测试:")
    for stock_code in test_stocks:
        try:
            monitor._update_stock_signal(stock_code)
            history = monitor.get_stock_signal_history(stock_code, 1)
            if history:
                signal = history[0]
                composite = signal.get('composite_signal', {})
                print(f"  {stock_code}: {composite.get('signal_strength', 'unknown')} "
                      f"(置信度: {composite.get('confidence_level', 0):.3f})")
            else:
                print(f"  {stock_code}: 无信号数据")
        except Exception as e:
            print(f"  {stock_code}: 更新失败 - {e}")
    
    print(f"\n✅ 多周期监控系统测试完成")

if __name__ == "__main__":
    main()