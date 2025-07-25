"""
交易操作顾问模块
提供具体的买入卖出价格参考和操作建议
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

class TradingAdvisor:
    """交易操作顾问类"""
    
    def __init__(self):
        self.risk_levels = {
            'conservative': {'stop_loss': 0.03, 'take_profit': 0.08, 'position_size': 0.3},
            'moderate': {'stop_loss': 0.05, 'take_profit': 0.12, 'position_size': 0.5},
            'aggressive': {'stop_loss': 0.08, 'take_profit': 0.20, 'position_size': 0.7}
        }
    
    def get_entry_recommendations(self, df, signal_idx, signal_state, current_price=None):
        """
        获取入场建议
        
        Args:
            df: 股票数据
            signal_idx: 信号索引
            signal_state: 信号状态
            current_price: 当前价格（实时使用）
        
        Returns:
            dict: 入场建议
        """
        try:
            recommendations = {
                'signal_info': {
                    'date': df.index[signal_idx].strftime('%Y-%m-%d'),
                    'signal_state': signal_state,
                    'current_price': current_price or df.loc[df.index[signal_idx], 'close']
                },
                'entry_strategies': [],
                'risk_management': {},
                'timing_advice': {}
            }
            
            # 获取关键价格水平
            price_levels = self._calculate_price_levels(df, signal_idx)
            
            # 根据信号状态提供不同的入场策略
            if signal_state == 'PRE':
                recommendations['entry_strategies'] = self._get_pre_entry_strategies(df, signal_idx, price_levels)
                recommendations['timing_advice'] = {
                    'best_timing': '信号确认后1-3个交易日内',
                    'watch_for': '等待回调至支撑位附近',
                    'avoid_if': '连续大涨后不追高'
                }
            elif signal_state == 'MID':
                recommendations['entry_strategies'] = self._get_mid_entry_strategies(df, signal_idx, price_levels)
                recommendations['timing_advice'] = {
                    'best_timing': '当日或次日开盘',
                    'watch_for': '突破确认，成交量放大',
                    'avoid_if': '高开超过3%时谨慎'
                }
            elif signal_state == 'POST':
                recommendations['entry_strategies'] = self._get_post_entry_strategies(df, signal_idx, price_levels)
                recommendations['timing_advice'] = {
                    'best_timing': '等待回调确认支撑',
                    'watch_for': '回踩不破关键位',
                    'avoid_if': '已连续上涨超过10%'
                }
            
            # 风险管理建议
            recommendations['risk_management'] = self._get_risk_management_advice(df, signal_idx, price_levels)
            
            return recommendations
            
        except Exception as e:
            return {'error': f'获取入场建议失败: {e}'}
    
    def get_exit_recommendations(self, df, entry_idx, entry_price, current_idx=None, risk_level='moderate'):
        """
        获取出场建议
        
        Args:
            df: 股票数据
            entry_idx: 入场索引
            entry_price: 入场价格
            current_idx: 当前索引
            risk_level: 风险等级
        
        Returns:
            dict: 出场建议
        """
        try:
            current_idx = current_idx or len(df) - 1
            current_price = df.iloc[current_idx]['close']
            current_pnl = (current_price - entry_price) / entry_price
            
            recommendations = {
                'current_status': {
                    'entry_date': df.index[entry_idx].strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'current_price': current_price,
                    'current_pnl': f"{current_pnl:.2%}",
                    'holding_days': current_idx - entry_idx
                },
                'exit_strategies': [],
                'price_targets': {},
                'risk_alerts': []
            }
            
            # 获取价格目标
            price_targets = self._calculate_exit_targets(df, entry_idx, entry_price, risk_level)
            recommendations['price_targets'] = price_targets
            
            # 根据当前盈亏情况提供出场策略
            if current_pnl > 0.15:  # 盈利超过15%
                recommendations['exit_strategies'].extend(self._get_profit_taking_strategies(current_pnl, price_targets))
            elif current_pnl > 0.05:  # 盈利5-15%
                recommendations['exit_strategies'].extend(self._get_moderate_profit_strategies(current_pnl, price_targets))
            elif current_pnl > -0.03:  # 小幅盈亏
                recommendations['exit_strategies'].extend(self._get_neutral_strategies(current_pnl, price_targets))
            else:  # 亏损超过3%
                recommendations['exit_strategies'].extend(self._get_loss_cutting_strategies(current_pnl, price_targets))
            
            # 风险警报
            recommendations['risk_alerts'] = self._check_risk_alerts(df, entry_idx, current_idx, entry_price, current_price)
            
            return recommendations
            
        except Exception as e:
            return {'error': f'获取出场建议失败: {e}'}
    
    def _calculate_price_levels(self, df, signal_idx):
        """计算关键价格水平"""
        try:
            # 获取最近20天的数据用于计算支撑阻力
            signal_pos = df.index.get_loc(signal_idx) if signal_idx in df.index else 0
            lookback_days = min(20, signal_pos)
            recent_data = df.iloc[max(0, signal_pos - lookback_days):signal_pos + 1]
            
            current_price = df.iloc[signal_idx]['close']
            
            # 计算支撑和阻力位
            support_levels = []
            resistance_levels = []
            
            # 基于最近低点和高点
            recent_lows = recent_data['low'].nsmallest(3).values
            recent_highs = recent_data['high'].nlargest(3).values
            
            support_levels.extend(recent_lows)
            resistance_levels.extend(recent_highs)
            
            # 基于移动平均线
            if len(recent_data) >= 5:
                ma5 = recent_data['close'].rolling(5).mean().iloc[-1]
                ma10 = recent_data['close'].rolling(10).mean().iloc[-1] if len(recent_data) >= 10 else ma5
                ma20 = recent_data['close'].rolling(20).mean().iloc[-1] if len(recent_data) >= 20 else ma10
                
                support_levels.extend([ma5, ma10, ma20])
                resistance_levels.extend([ma5 * 1.05, ma10 * 1.08, ma20 * 1.10])
            
            return {
                'current_price': current_price,
                'support_levels': sorted(set([round(x, 2) for x in support_levels if x < current_price]))[-3:],
                'resistance_levels': sorted(set([round(x, 2) for x in resistance_levels if x > current_price]))[:3],
                'daily_range': {
                    'high': df.iloc[signal_idx]['high'],
                    'low': df.iloc[signal_idx]['low'],
                    'volume': df.iloc[signal_idx]['volume'] if 'volume' in df.columns else 0
                }
            }
            
        except Exception as e:
            print(f"计算价格水平失败: {e}")
            return {'current_price': df.iloc[signal_idx]['close'], 'support_levels': [], 'resistance_levels': []}
    
    def _get_pre_entry_strategies(self, df, signal_idx, price_levels):
        """PRE状态入场策略"""
        current_price = price_levels['current_price']
        support_levels = price_levels['support_levels']
        
        strategies = [
            {
                'strategy': '分批建仓',
                'entry_price_1': round(current_price * 0.98, 2),
                'entry_price_2': round(current_price * 0.95, 2),
                'position_allocation': '首次30%，回调后加仓40%',
                'rationale': 'PRE状态风险较低，可分批建仓降低成本'
            },
            {
                'strategy': '支撑位买入',
                'entry_price_1': support_levels[-1] if support_levels else round(current_price * 0.97, 2),
                'entry_price_2': support_levels[-2] if len(support_levels) > 1 else round(current_price * 0.94, 2),
                'position_allocation': '支撑位附近70%仓位',
                'rationale': '等待回调至技术支撑位，安全边际更高'
            }
        ]
        
        return strategies
    
    def _get_mid_entry_strategies(self, df, signal_idx, price_levels):
        """MID状态入场策略"""
        current_price = price_levels['current_price']
        daily_high = price_levels['daily_range']['high']
        daily_low = price_levels['daily_range']['low']
        
        strategies = [
            {
                'strategy': '突破确认买入',
                'entry_price_1': round(current_price * 1.01, 2),
                'entry_price_2': round(daily_high * 1.005, 2),
                'position_allocation': '确认突破后50%仓位',
                'rationale': 'MID状态突破概率高，确认后快速建仓'
            },
            {
                'strategy': '当日低点买入',
                'entry_price_1': round(daily_low * 1.002, 2),
                'entry_price_2': round((daily_low + current_price) / 2, 2),
                'position_allocation': '当日低点附近60%仓位',
                'rationale': '利用日内波动，在相对低点建仓'
            }
        ]
        
        return strategies
    
    def _get_post_entry_strategies(self, df, signal_idx, price_levels):
        """POST状态入场策略"""
        current_price = price_levels['current_price']
        support_levels = price_levels['support_levels']
        
        strategies = [
            {
                'strategy': '回调买入',
                'entry_price_1': round(current_price * 0.95, 2),
                'entry_price_2': round(current_price * 0.92, 2),
                'position_allocation': '等待5-8%回调后建仓',
                'rationale': 'POST状态已突破，等待健康回调后介入'
            },
            {
                'strategy': '强势追涨',
                'entry_price_1': round(current_price * 1.02, 2),
                'entry_price_2': round(current_price * 1.05, 2),
                'position_allocation': '强势不回调时小仓位追涨',
                'rationale': '如果持续强势不回调，小仓位参与'
            }
        ]
        
        return strategies
    
    def _get_risk_management_advice(self, df, signal_idx, price_levels):
        """风险管理建议"""
        current_price = price_levels['current_price']
        support_levels = price_levels['support_levels']
        
        # 计算止损位
        if support_levels:
            technical_stop = support_levels[-1] * 0.98
        else:
            technical_stop = current_price * 0.95
        
        return {
            'stop_loss_levels': {
                'conservative': round(current_price * 0.97, 2),
                'moderate': round(current_price * 0.95, 2),
                'aggressive': round(current_price * 0.92, 2),
                'technical': round(technical_stop, 2)
            },
            'position_sizing': {
                'conservative': '总资金的20-30%',
                'moderate': '总资金的30-50%',
                'aggressive': '总资金的50-70%'
            },
            'risk_reward_ratio': '建议风险收益比至少1:2',
            'max_holding_period': '建议最长持有30个交易日'
        }
    
    def _calculate_exit_targets(self, df, entry_idx, entry_price, risk_level):
        """计算出场目标价位"""
        risk_config = self.risk_levels[risk_level]
        
        return {
            'stop_loss': round(entry_price * (1 - risk_config['stop_loss']), 2),
            'take_profit_1': round(entry_price * (1 + risk_config['take_profit'] * 0.5), 2),
            'take_profit_2': round(entry_price * (1 + risk_config['take_profit']), 2),
            'take_profit_3': round(entry_price * (1 + risk_config['take_profit'] * 1.5), 2),
            'trailing_stop': '盈利后动态调整止损至成本价上方'
        }
    
    def _get_profit_taking_strategies(self, current_pnl, price_targets):
        """盈利15%以上的出场策略"""
        return [
            {
                'strategy': '分批获利了结',
                'action': f'当前盈利{current_pnl:.1%}，建议减仓50%',
                'target_price': price_targets['take_profit_2'],
                'rationale': '大幅盈利后分批获利，保留部分仓位'
            },
            {
                'strategy': '移动止损',
                'action': '将止损位调整至成本价上方8-10%',
                'target_price': '动态调整',
                'rationale': '保护利润，让利润奔跑'
            }
        ]
    
    def _get_moderate_profit_strategies(self, current_pnl, price_targets):
        """中等盈利的出场策略"""
        return [
            {
                'strategy': '部分获利',
                'action': f'当前盈利{current_pnl:.1%}，可考虑减仓30%',
                'target_price': price_targets['take_profit_1'],
                'rationale': '适度获利，保留主要仓位等待更大收益'
            },
            {
                'strategy': '提高止损',
                'action': '将止损位调整至成本价附近',
                'target_price': '成本价±2%',
                'rationale': '保护本金，避免盈利变亏损'
            }
        ]
    
    def _get_neutral_strategies(self, current_pnl, price_targets):
        """盈亏平衡附近的策略"""
        return [
            {
                'strategy': '耐心持有',
                'action': f'当前盈亏{current_pnl:.1%}，继续持有观察',
                'target_price': price_targets['take_profit_1'],
                'rationale': '信号仍然有效，给予更多时间发展'
            },
            {
                'strategy': '严格止损',
                'action': '严格执行预设止损位',
                'target_price': price_targets['stop_loss'],
                'rationale': '控制风险，避免小亏变大亏'
            }
        ]
    
    def _get_loss_cutting_strategies(self, current_pnl, price_targets):
        """亏损时的策略"""
        return [
            {
                'strategy': '及时止损',
                'action': f'当前亏损{current_pnl:.1%}，建议止损出场',
                'target_price': price_targets['stop_loss'],
                'rationale': '控制亏损，保护资金'
            },
            {
                'strategy': '分析原因',
                'action': '分析信号失效原因，总结经验',
                'target_price': '立即执行',
                'rationale': '从失败中学习，改进策略'
            }
        ]
    
    def _check_risk_alerts(self, df, entry_idx, current_idx, entry_price, current_price):
        """检查风险警报"""
        alerts = []
        
        # 持有时间过长
        holding_days = current_idx - entry_idx
        if holding_days > 30:
            alerts.append({
                'type': '时间风险',
                'message': f'已持有{holding_days}天，超过建议持有期',
                'severity': 'medium'
            })
        
        # 大幅亏损
        current_pnl = (current_price - entry_price) / entry_price
        if current_pnl < -0.08:
            alerts.append({
                'type': '亏损风险',
                'message': f'当前亏损{current_pnl:.1%}，建议考虑止损',
                'severity': 'high'
            })
        
        # 成交量异常（如果有成交量数据）
        if 'volume' in df.columns and current_idx > 0:
            recent_volume = df.iloc[current_idx]['volume']
            avg_volume = df.iloc[max(0, current_idx-10):current_idx]['volume'].mean()
            if recent_volume > avg_volume * 3:
                alerts.append({
                    'type': '成交量异常',
                    'message': '成交量异常放大，注意市场变化',
                    'severity': 'medium'
                })
        
        return alerts

    def generate_trading_report(self, df, signal_idx, signal_state, entry_price=None, current_price=None):
        """生成完整的交易报告"""
        try:
            # 获取入场建议
            entry_recommendations = self.get_entry_recommendations(df, signal_idx, signal_state, current_price)
            
            # 如果已经入场，获取出场建议
            exit_recommendations = None
            if entry_price:
                exit_recommendations = self.get_exit_recommendations(df, signal_idx, entry_price)
            
            report = {
                'report_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'stock_info': {
                    'signal_date': df.index[signal_idx].strftime('%Y-%m-%d'),
                    'signal_state': signal_state,
                    'current_price': current_price or df.iloc[signal_idx]['close']
                },
                'entry_analysis': entry_recommendations,
                'exit_analysis': exit_recommendations,
                'market_context': self._get_market_context(df, signal_idx),
                'action_summary': self._generate_action_summary(entry_recommendations, exit_recommendations)
            }
            
            return report
            
        except Exception as e:
            return {'error': f'生成交易报告失败: {e}'}
    
    def _get_market_context(self, df, signal_idx):
        """获取市场环境分析"""
        try:
            # 计算最近的市场趋势
            signal_pos = df.index.get_loc(signal_idx) if signal_idx in df.index else 0
            lookback = min(20, signal_pos)
            recent_data = df.iloc[max(0, signal_pos - lookback):signal_pos + 1]
            
            # 价格趋势
            price_trend = (recent_data['close'].iloc[-1] - recent_data['close'].iloc[0]) / recent_data['close'].iloc[0]
            
            # 波动率
            returns = recent_data['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)  # 年化波动率
            
            return {
                'price_trend': f"{price_trend:.1%} (最近{lookback}天)",
                'volatility': f"{volatility:.1%} (年化)",
                'trend_direction': '上升' if price_trend > 0.05 else '下降' if price_trend < -0.05 else '震荡',
                'market_state': '高波动' if volatility > 0.3 else '低波动' if volatility < 0.15 else '正常波动'
            }
            
        except Exception as e:
            return {'error': f'市场环境分析失败: {e}'}
    
    def _generate_action_summary(self, entry_rec, exit_rec):
        """生成操作摘要"""
        summary = []
        
        if entry_rec and 'entry_strategies' in entry_rec:
            if entry_rec['entry_strategies']:
                best_strategy = entry_rec['entry_strategies'][0]
                summary.append(f"建议入场策略: {best_strategy['strategy']}")
                summary.append(f"目标价位: {best_strategy['entry_price_1']}")
        
        if exit_rec and 'exit_strategies' in exit_rec:
            if exit_rec['exit_strategies']:
                best_exit = exit_rec['exit_strategies'][0]
                summary.append(f"当前建议: {best_exit['action']}")
        
        return summary