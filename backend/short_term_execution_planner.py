"""
短线交易执行计划生成器

基于MA13短线策略生成具体的实战执行计划
包含支撑位、目标位、时间窗口和风险控制
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
import sys
import os

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

logger = logging.getLogger(__name__)

class ShortTermExecutionPlanner:
    """短线交易执行计划生成器"""
    
    def __init__(self):
        self.name = "短线实战执行计划器"
        self.version = "1.0"
        
        # 执行参数
        self.params = {
            # 支撑位参数
            'support_buffer_pct': 0.02,  # 支撑位缓冲区
            'ma13_support_weight': 0.8,  # MA13支撑权重
            'ma30_support_weight': 0.6,  # MA30支撑权重
            
            # 目标位参数
            'target_1_buffer': 1.02,  # 第一目标位缓冲
            'target_2_multiplier': 0.5,  # 第二目标位倍数
            'target_3_multiplier': 1.20,  # 第三目标位倍数
            
            # 时间窗口参数
            'min_hold_days': 3,  # 最小持仓天数
            'max_hold_days': 10,  # 最大持仓天数
            'golden_window_days': 8,  # 黄金窗口期
            
            # 仓位管理参数
            'initial_position': 0.3,  # 初始仓位
            'add_position': 0.4,  # 加仓比例
            'max_position': 0.7,  # 最大仓位
            
            # 止盈止损参数
            'stop_loss_pct': 0.05,  # 止损幅度
            'take_profit_1_pct': 0.10,  # 第一止盈
            'take_profit_2_pct': 0.20,  # 第二止盈
            'trailing_stop_pct': 0.08,  # 移动止损
        }

    def generate_execution_plan(self, df: pd.DataFrame, strategy_result: Dict, 
                              stock_code: str = None) -> Dict:
        """
        生成完整的执行计划
        
        Args:
            df: 股票数据
            strategy_result: MA13策略分析结果
            stock_code: 股票代码
            
        Returns:
            执行计划字典
        """
        try:
            if not strategy_result.get('success', False):
                return self._create_plan_result(False, "策略分析未通过", {})
            
            latest = df.iloc[-1]
            current_price = latest['close']
            current_date = latest['date']
            
            # 计算支撑位分析
            support_analysis = self._calculate_support_levels(df, strategy_result)
            
            # 计算目标位分析
            target_analysis = self._calculate_target_levels(df, strategy_result)
            
            # 生成时间窗口分析
            time_window = self._calculate_time_window(df, current_date)
            
            # 生成仓位管理计划
            position_plan = self._generate_position_plan(strategy_result)
            
            # 生成风险控制计划
            risk_control = self._generate_risk_control_plan(current_price, support_analysis, target_analysis)
            
            # 生成操作指引
            operation_guide = self._generate_operation_guide(
                current_price, support_analysis, target_analysis, 
                strategy_result, time_window
            )
            
            # 生成执行总结表
            execution_summary = self._generate_execution_summary(
                current_price, support_analysis, target_analysis, 
                time_window, position_plan, risk_control
            )
            
            plan = {
                'stock_code': stock_code,
                'current_price': current_price,
                'analysis_date': current_date,
                'plan_generated_at': datetime.now().isoformat(),
                
                'support_analysis': support_analysis,
                'target_analysis': target_analysis,
                'time_window': time_window,
                'position_plan': position_plan,
                'risk_control': risk_control,
                'operation_guide': operation_guide,
                'execution_summary': execution_summary,
                
                'strategy_confidence': strategy_result.get('recommendation', {}).get('confidence', 0),
                'expected_return': self._calculate_expected_return(current_price, target_analysis),
                'risk_reward_ratio': risk_control.get('risk_reward_ratio', 0)
            }
            
            return self._create_plan_result(True, "执行计划生成成功", plan)
            
        except Exception as e:
            logger.error(f"生成执行计划出错: {str(e)}")
            return self._create_plan_result(False, f"生成执行计划出错: {str(e)}", {})

    def _calculate_support_levels(self, df: pd.DataFrame, strategy_result: Dict) -> Dict:
        """计算支撑位分析"""
        try:
            latest = df.iloc[-1]
            recent_data = df.tail(20)
            key_levels = strategy_result.get('key_levels', {})
            
            # 第一支撑区 (核心防守带)
            ma13 = latest.get('ma13', 0)
            recent_low = recent_data['low'].min()
            
            support_1_upper = max(recent_low, ma13 * (1 + self.params['support_buffer_pct']))
            support_1_lower = ma13
            
            # 第二支撑区 (最终止损线)
            ma30 = latest.get('ma30', 0)
            box_upper = df.tail(120)['high'].quantile(0.8)  # 箱体上轨
            
            support_2_upper = ma30 if ma30 > 0 else support_1_lower * 0.95
            support_2_lower = min(ma30 * 0.95, box_upper) if ma30 > 0 else support_1_lower * 0.90
            
            # 支撑位强度评估
            current_price = latest['close']
            
            support_strength = self._evaluate_support_strength(
                current_price, support_1_lower, support_2_lower, recent_data
            )
            
            return {
                'core_support_zone': {
                    'upper': round(support_1_upper, 2),
                    'lower': round(support_1_lower, 2),
                    'description': f"核心防守带: {support_1_upper:.2f}元 - {support_1_lower:.2f}元",
                    'tactical_meaning': "最重要的持仓安全区，回踩不破可加仓"
                },
                'final_support_zone': {
                    'upper': round(support_2_upper, 2),
                    'lower': round(support_2_lower, 2),
                    'description': f"最终止损线: {support_2_upper:.2f}元 - {support_2_lower:.2f}元",
                    'tactical_meaning': "趋势最后防线，有效跌破需严格止损"
                },
                'current_position': self._get_support_position(current_price, support_1_lower, support_2_lower),
                'support_strength': support_strength,
                'ma13_value': round(ma13, 2),
                'ma30_value': round(ma30, 2)
            }
            
        except Exception as e:
            logger.error(f"计算支撑位出错: {str(e)}")
            return {}

    def _calculate_target_levels(self, df: pd.DataFrame, strategy_result: Dict) -> Dict:
        """计算目标位分析"""
        try:
            latest = df.iloc[-1]
            recent_data = df.tail(20)
            current_price = latest['close']
            
            # 第一目标位 (突破确认)
            recent_high = recent_data['high'].max()
            target_1 = recent_high * self.params['target_1_buffer']
            
            # 第二目标位 (量化测算)
            box_low = df.tail(120)['low'].min()
            box_height = recent_high - box_low
            target_2 = recent_high + box_height * self.params['target_2_multiplier']
            
            # 第三目标位 (潜在挑战位)
            target_3 = recent_high * self.params['target_3_multiplier']
            
            # 计算各目标位的涨幅
            gain_to_target_1 = (target_1 - current_price) / current_price
            gain_to_target_2 = (target_2 - current_price) / current_price
            gain_to_target_3 = (target_3 - current_price) / current_price
            
            # 目标位可达性评估
            target_probability = self._evaluate_target_probability(
                current_price, target_1, target_2, target_3, recent_data
            )
            
            return {
                'target_1': {
                    'price': round(target_1, 2),
                    'gain_pct': round(gain_to_target_1 * 100, 1),
                    'description': f"第一目标位: {target_1:.2f}元 (+{gain_to_target_1:.1%})",
                    'basis': f"前高突破确认位 ({recent_high:.2f}元)",
                    'operation': "观察突破力度，确认趋势延续",
                    'probability': target_probability['target_1']
                },
                'target_2': {
                    'price': round(target_2, 2),
                    'gain_pct': round(gain_to_target_2 * 100, 1),
                    'description': f"第二目标位: {target_2:.2f}元 (+{gain_to_target_2:.1%})",
                    'basis': f"等幅测算 (箱体高度{box_height:.2f}元)",
                    'operation': "核心利润目标区，建议分批止盈",
                    'probability': target_probability['target_2']
                },
                'target_3': {
                    'price': round(target_3, 2),
                    'gain_pct': round(gain_to_target_3 * 100, 1),
                    'description': f"第三目标位: {target_3:.2f}元 (+{gain_to_target_3:.1%})",
                    'basis': "乐观情绪推动的潜在高点",
                    'operation': "使用移动止盈法捕捉额外利润",
                    'probability': target_probability['target_3']
                },
                'recent_high': round(recent_high, 2),
                'box_height': round(box_height, 2),
                'expected_main_target': round(target_2, 2)
            }
            
        except Exception as e:
            logger.error(f"计算目标位出错: {str(e)}")
            return {}

    def _calculate_time_window(self, df: pd.DataFrame, current_date: str) -> Dict:
        """计算操作时间窗口"""
        try:
            # 解析当前日期
            if isinstance(current_date, str):
                current_dt = datetime.strptime(current_date, '%Y-%m-%d')
            else:
                current_dt = current_date
            
            # 计算时间窗口
            min_exit_date = current_dt + timedelta(days=self.params['min_hold_days'])
            max_exit_date = current_dt + timedelta(days=self.params['max_hold_days'])
            golden_window_end = current_dt + timedelta(days=self.params['golden_window_days'])
            
            # 计算交易日(排除周末)
            trading_days_count = 0
            check_date = current_dt + timedelta(days=1)
            while check_date <= max_exit_date:
                if check_date.weekday() < 5:  # 周一到周五
                    trading_days_count += 1
                check_date += timedelta(days=1)
            
            return {
                'start_date': current_dt.strftime('%Y-%m-%d'),
                'min_hold_until': min_exit_date.strftime('%Y-%m-%d'),
                'max_hold_until': max_exit_date.strftime('%Y-%m-%d'),
                'golden_window_end': golden_window_end.strftime('%Y-%m-%d'),
                'expected_trading_days': trading_days_count,
                'window_description': f"预期持仓周期: {self.params['min_hold_days']}-{self.params['max_hold_days']}个交易日",
                'golden_period': f"黄金窗口期: 未来{self.params['golden_window_days']}个交易日",
                'time_risk_warning': f"超过{self.params['max_hold_days']}个交易日仍未达到目标需警惕趋势衰竭"
            }
            
        except Exception as e:
            logger.error(f"计算时间窗口出错: {str(e)}")
            return {}

    def _generate_position_plan(self, strategy_result: Dict) -> Dict:
        """生成仓位管理计划"""
        try:
            signals = strategy_result.get('signals', {})
            recommendation = strategy_result.get('recommendation', {})
            
            # 根据信号类型确定仓位策略
            initial_position = self.params['initial_position']
            add_position = self.params['add_position']
            
            if signals.get('continuation_model', False):
                # 中继确认信号 - 更激进
                initial_position = 0.4
                add_position = 0.3
            elif signals.get('oversold_model', False):
                # 超跌反弹信号 - 相对保守
                initial_position = 0.2
                add_position = 0.5
            
            return {
                'initial_entry': {
                    'position_pct': initial_position * 100,
                    'description': f"初始建仓: {initial_position:.0%}仓位",
                    'trigger': "当前价位或支撑区回踩确认"
                },
                'add_position': {
                    'position_pct': add_position * 100,
                    'description': f"加仓比例: {add_position:.0%}仓位",
                    'trigger': "突破第一目标位或中继信号确认"
                },
                'max_position': {
                    'position_pct': self.params['max_position'] * 100,
                    'description': f"最大仓位: {self.params['max_position']:.0%}",
                    'warning': "严格控制总仓位，避免过度集中"
                },
                'position_stages': [
                    f"第一阶段: {initial_position:.0%}仓位试探",
                    f"第二阶段: 确认后加仓至{initial_position + add_position:.0%}",
                    f"第三阶段: 强势突破可满仓{self.params['max_position']:.0%}"
                ],
                'risk_control': "单票仓位不超过总资金20%，严格执行分批建仓"
            }
            
        except Exception as e:
            logger.error(f"生成仓位计划出错: {str(e)}")
            return {}

    def _generate_risk_control_plan(self, current_price: float, 
                                  support_analysis: Dict, target_analysis: Dict) -> Dict:
        """生成风险控制计划"""
        try:
            # 计算止损位
            ma13_value = support_analysis.get('ma13_value', current_price * 0.95)
            stop_loss_price = ma13_value * (1 - self.params['stop_loss_pct'])
            
            # 计算止盈位
            target_1_price = target_analysis.get('target_1', {}).get('price', current_price * 1.1)
            target_2_price = target_analysis.get('target_2', {}).get('price', current_price * 1.2)
            
            # 计算风险收益比
            risk_amount = current_price - stop_loss_price
            reward_amount = target_2_price - current_price
            risk_reward_ratio = reward_amount / risk_amount if risk_amount > 0 else 0
            
            # 移动止损计算
            trailing_stop_price = current_price * (1 - self.params['trailing_stop_pct'])
            
            return {
                'stop_loss': {
                    'price': round(stop_loss_price, 2),
                    'pct_from_current': round((stop_loss_price - current_price) / current_price * 100, 1),
                    'trigger': f"收盘价有效跌破{stop_loss_price:.2f}元",
                    'description': f"无条件止损线: {stop_loss_price:.2f}元"
                },
                'take_profit_1': {
                    'price': round(target_1_price, 2),
                    'pct_from_current': round((target_1_price - current_price) / current_price * 100, 1),
                    'action': "减仓50%，锁定部分利润",
                    'description': f"第一止盈: {target_1_price:.2f}元"
                },
                'take_profit_2': {
                    'price': round(target_2_price, 2),
                    'pct_from_current': round((target_2_price - current_price) / current_price * 100, 1),
                    'action': "减仓至30%，保留核心仓位",
                    'description': f"第二止盈: {target_2_price:.2f}元"
                },
                'trailing_stop': {
                    'initial_price': round(trailing_stop_price, 2),
                    'rule': "价格每上涨5%，止损位上移3%",
                    'description': "动态移动止损，保护浮盈"
                },
                'risk_reward_ratio': round(risk_reward_ratio, 2),
                'max_loss_pct': round(risk_amount / current_price * 100, 1),
                'expected_gain_pct': round(reward_amount / current_price * 100, 1),
                'risk_assessment': self._assess_risk_level(risk_reward_ratio, risk_amount / current_price)
            }
            
        except Exception as e:
            logger.error(f"生成风险控制计划出错: {str(e)}")
            return {}

    def _generate_operation_guide(self, current_price: float, support_analysis: Dict,
                                target_analysis: Dict, strategy_result: Dict, 
                                time_window: Dict) -> Dict:
        """生成操作指引"""
        try:
            signals = strategy_result.get('signals', {})
            recommendation = strategy_result.get('recommendation', {})
            
            # 当前市场状态判断
            market_status = self._assess_market_status(current_price, support_analysis, signals)
            
            # 生成具体操作建议
            operations = []
            
            if recommendation.get('action') == 'buy_heavy':
                operations.append({
                    'timing': '立即执行',
                    'action': '重仓建仓',
                    'position': '40-70%仓位',
                    'reason': '多重信号确认，趋势强劲'
                })
            elif recommendation.get('action') == 'buy_light':
                operations.append({
                    'timing': '谨慎建仓',
                    'action': '轻仓试探',
                    'position': '20-30%仓位',
                    'reason': '信号初现，等待确认'
                })
            else:
                operations.append({
                    'timing': '观望等待',
                    'action': '暂不操作',
                    'position': '空仓',
                    'reason': '信号不明确，等待更好时机'
                })
            
            # 关键监控点
            monitoring_points = [
                f"密切关注MA13支撑({support_analysis.get('ma13_value', 0):.2f}元)",
                f"观察成交量是否持续放大",
                f"监控第一目标位({target_analysis.get('target_1', {}).get('price', 0):.2f}元)突破情况",
                f"注意{time_window.get('golden_window_end', '')}前的表现"
            ]
            
            # 应急预案
            contingency_plans = [
                {
                    'scenario': '快速拉升至目标位',
                    'action': '分批止盈，不要贪心'
                },
                {
                    'scenario': '回调至支撑区',
                    'action': '观察支撑强度，考虑加仓'
                },
                {
                    'scenario': '跌破止损位',
                    'action': '无条件离场，保住本金'
                },
                {
                    'scenario': '横盘整理超时',
                    'action': '减仓观望，避免资金沉淀'
                }
            ]
            
            return {
                'market_status': market_status,
                'immediate_operations': operations,
                'monitoring_points': monitoring_points,
                'contingency_plans': contingency_plans,
                'daily_checklist': [
                    '检查MA13支撑是否有效',
                    '观察成交量变化',
                    '监控技术指标信号',
                    '评估市场情绪变化',
                    '复盘当日K线形态'
                ],
                'success_factors': [
                    '严格执行止损纪律',
                    '分批建仓和止盈',
                    '控制单票仓位',
                    '保持理性心态',
                    '及时调整策略'
                ]
            }
            
        except Exception as e:
            logger.error(f"生成操作指引出错: {str(e)}")
            return {}

    def _generate_execution_summary(self, current_price: float, support_analysis: Dict,
                                  target_analysis: Dict, time_window: Dict,
                                  position_plan: Dict, risk_control: Dict) -> Dict:
        """生成执行总结表"""
        try:
            summary_table = [
                {
                    'item': '核心支撑',
                    'key_level': f"{support_analysis.get('core_support_zone', {}).get('lower', 0):.2f}元",
                    'tactical_response': support_analysis.get('core_support_zone', {}).get('tactical_meaning', '')
                },
                {
                    'item': '最终止损',
                    'key_level': f"{risk_control.get('stop_loss', {}).get('price', 0):.2f}元",
                    'tactical_response': '无条件离场，保住本金'
                },
                {
                    'item': '第一目标',
                    'key_level': f"{target_analysis.get('target_1', {}).get('price', 0):.2f}元",
                    'tactical_response': '观察突破力度，确认趋势延续'
                },
                {
                    'item': '核心目标',
                    'key_level': f"{target_analysis.get('target_2', {}).get('price', 0):.2f}元",
                    'tactical_response': '主要利润兑现区，建议分批止盈'
                },
                {
                    'item': '时间窗口',
                    'key_level': time_window.get('window_description', ''),
                    'tactical_response': '交易的黄金周期，密切跟踪'
                }
            ]
            
            # 关键数据汇总
            key_metrics = {
                'current_price': round(current_price, 2),
                'support_distance': round((current_price - support_analysis.get('core_support_zone', {}).get('lower', current_price)) / current_price * 100, 1),
                'target_distance': round((target_analysis.get('target_2', {}).get('price', current_price) - current_price) / current_price * 100, 1),
                'risk_reward_ratio': risk_control.get('risk_reward_ratio', 0),
                'max_position': position_plan.get('max_position', {}).get('position_pct', 0),
                'expected_days': time_window.get('expected_trading_days', 0)
            }
            
            return {
                'summary_table': summary_table,
                'key_metrics': key_metrics,
                'execution_priority': [
                    '1. 确认支撑位有效性',
                    '2. 控制建仓节奏',
                    '3. 设置止损止盈',
                    '4. 监控时间窗口',
                    '5. 执行分批操作'
                ],
                'risk_warnings': [
                    f"单票最大亏损不超过{risk_control.get('max_loss_pct', 5):.1f}%",
                    f"持仓时间不超过{time_window.get('expected_trading_days', 10)}个交易日",
                    "严格执行止损纪律，避免情绪化操作",
                    "市场环境变化时及时调整策略"
                ]
            }
            
        except Exception as e:
            logger.error(f"生成执行总结出错: {str(e)}")
            return {}

    def _evaluate_support_strength(self, current_price: float, support_1: float, 
                                 support_2: float, recent_data: pd.DataFrame) -> Dict:
        """评估支撑位强度"""
        try:
            # 计算支撑位距离
            distance_to_support_1 = (current_price - support_1) / current_price
            distance_to_support_2 = (current_price - support_2) / current_price
            
            # 历史测试次数
            test_count_1 = len(recent_data[recent_data['low'] <= support_1 * 1.02])
            test_count_2 = len(recent_data[recent_data['low'] <= support_2 * 1.02])
            
            # 支撑强度评分
            strength_score = 0
            if distance_to_support_1 > 0.02:  # 距离支撑位2%以上
                strength_score += 30
            if test_count_1 <= 2:  # 测试次数少
                strength_score += 40
            if distance_to_support_2 > 0.05:  # 距离最终支撑5%以上
                strength_score += 30
            
            strength_level = 'strong' if strength_score >= 80 else 'medium' if strength_score >= 50 else 'weak'
            
            return {
                'strength_score': strength_score,
                'strength_level': strength_level,
                'distance_to_support_1_pct': round(distance_to_support_1 * 100, 1),
                'distance_to_support_2_pct': round(distance_to_support_2 * 100, 1),
                'test_count_1': test_count_1,
                'test_count_2': test_count_2
            }
            
        except Exception:
            return {'strength_score': 50, 'strength_level': 'medium'}

    def _evaluate_target_probability(self, current_price: float, target_1: float,
                                   target_2: float, target_3: float, 
                                   recent_data: pd.DataFrame) -> Dict:
        """评估目标位达到概率"""
        try:
            # 基于历史波动率和趋势强度评估
            volatility = recent_data['close'].pct_change().std() * np.sqrt(252)  # 年化波动率
            
            # 计算各目标位的涨幅要求
            gain_1 = (target_1 - current_price) / current_price
            gain_2 = (target_2 - current_price) / current_price
            gain_3 = (target_3 - current_price) / current_price
            
            # 基于波动率和涨幅计算概率
            prob_1 = min(90, max(30, 80 - gain_1 * 200))  # 第一目标概率较高
            prob_2 = min(70, max(20, 60 - gain_2 * 150))  # 第二目标概率中等
            prob_3 = min(40, max(10, 30 - gain_3 * 100))  # 第三目标概率较低
            
            return {
                'target_1': round(prob_1, 0),
                'target_2': round(prob_2, 0),
                'target_3': round(prob_3, 0)
            }
            
        except Exception:
            return {'target_1': 60, 'target_2': 40, 'target_3': 20}

    def _get_support_position(self, current_price: float, support_1: float, support_2: float) -> str:
        """获取当前价格相对支撑位的位置"""
        try:
            if current_price >= support_1 * 1.02:
                return "安全区域"
            elif current_price >= support_1:
                return "接近核心支撑"
            elif current_price >= support_2:
                return "核心支撑区间"
            else:
                return "跌破核心支撑"
        except Exception:
            return "位置不明"

    def _assess_market_status(self, current_price: float, support_analysis: Dict, signals: Dict) -> Dict:
        """评估当前市场状态"""
        try:
            status = "观望"
            confidence = 50
            
            if signals.get('continuation_model', False):
                status = "中继上涨"
                confidence = 75
            elif signals.get('oversold_model', False):
                status = "超跌反弹"
                confidence = 65
            
            # 根据支撑位位置调整
            position = support_analysis.get('current_position', '')
            if position == "安全区域":
                confidence += 10
            elif position == "跌破核心支撑":
                confidence -= 20
                status = "风险警告"
            
            return {
                'status': status,
                'confidence': min(95, max(5, confidence)),
                'description': f"当前状态: {status}，信心度: {confidence}%"
            }
            
        except Exception:
            return {'status': '不明', 'confidence': 50}

    def _assess_risk_level(self, risk_reward_ratio: float, max_loss_pct: float) -> str:
        """评估风险等级"""
        try:
            if risk_reward_ratio >= 2.0 and max_loss_pct <= 0.05:
                return "低风险"
            elif risk_reward_ratio >= 1.5 and max_loss_pct <= 0.08:
                return "中等风险"
            else:
                return "高风险"
        except Exception:
            return "风险不明"

    def _calculate_expected_return(self, current_price: float, target_analysis: Dict) -> float:
        """计算期望收益率"""
        try:
            target_2_price = target_analysis.get('target_2', {}).get('price', current_price)
            return (target_2_price - current_price) / current_price
        except Exception:
            return 0.0

    def _create_plan_result(self, success: bool, message: str, data: Dict) -> Dict:
        """创建统一的计划结果格式"""
        result = {
            'success': success,
            'message': message,
            'planner': self.name,
            'version': self.version,
            'timestamp': datetime.now().isoformat()
        }
        
        if data:
            result.update(data)
        
        return result