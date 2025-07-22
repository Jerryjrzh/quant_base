"""
参数化交易顾问模块
支持个股参数优化和回测验证
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import itertools

@dataclass
class TradingParameters:
    """交易参数配置"""
    # 入场参数
    pre_entry_discount: float = 0.02  # PRE状态入场折扣
    pre_entry_discount_2: float = 0.05  # PRE状态第二入场点折扣
    mid_entry_premium: float = 0.01   # MID状态入场溢价
    post_entry_discount: float = 0.05  # POST状态等待回调折扣
    
    # 止损参数
    conservative_stop: float = 0.03   # 保守止损比例
    moderate_stop: float = 0.05       # 适中止损比例
    aggressive_stop: float = 0.08     # 激进止损比例
    
    # 止盈参数
    conservative_profit: float = 0.08  # 保守止盈比例
    moderate_profit: float = 0.12      # 适中止盈比例
    aggressive_profit: float = 0.20    # 激进止盈比例
    
    # 仓位参数
    conservative_position: float = 0.3  # 保守仓位比例
    moderate_position: float = 0.5      # 适中仓位比例
    aggressive_position: float = 0.7    # 激进仓位比例
    
    # 技术指标参数
    support_lookback: int = 20         # 支撑位回看天数
    resistance_lookback: int = 20      # 阻力位回看天数
    ma_periods: List[int] = None       # 移动平均线周期
    
    # 风险控制参数
    max_holding_days: int = 30         # 最大持有天数
    trend_confirm_days: int = 5        # 趋势确认天数
    volume_threshold: float = 2.0      # 成交量异常阈值
    
    def __post_init__(self):
        if self.ma_periods is None:
            self.ma_periods = [5, 10, 20]

class ParametricTradingAdvisor:
    """参数化交易顾问"""
    
    def __init__(self, parameters: TradingParameters = None):
        self.parameters = parameters or TradingParameters()
        self.optimization_history = []
    
    def get_parametric_entry_recommendations(self, df, signal_idx, signal_state, current_price=None):
        """基于参数的入场建议"""
        try:
            current_price = current_price or df.iloc[signal_idx]['close']
            
            recommendations = {
                'signal_info': {
                    'date': df.index[signal_idx].strftime('%Y-%m-%d'),
                    'signal_state': signal_state,
                    'current_price': current_price,
                    'parameters_used': asdict(self.parameters)
                },
                'entry_strategies': [],
                'risk_management': {},
                'timing_advice': {}
            }
            
            # 计算技术价格水平
            price_levels = self._calculate_parametric_price_levels(df, signal_idx)
            
            # 根据信号状态和参数生成策略
            if signal_state == 'PRE':
                recommendations['entry_strategies'] = self._get_parametric_pre_strategies(
                    current_price, price_levels
                )
            elif signal_state == 'MID':
                recommendations['entry_strategies'] = self._get_parametric_mid_strategies(
                    current_price, price_levels
                )
            elif signal_state == 'POST':
                recommendations['entry_strategies'] = self._get_parametric_post_strategies(
                    current_price, price_levels
                )
            
            # 参数化风险管理
            recommendations['risk_management'] = self._get_parametric_risk_management(
                current_price, price_levels
            )
            
            return recommendations
            
        except Exception as e:
            return {'error': f'获取参数化入场建议失败: {e}'}
    
    def _calculate_parametric_price_levels(self, df, signal_idx):
        """基于参数计算价格水平"""
        try:
            # 使用参数化的回看期
            lookback_days = min(self.parameters.support_lookback, signal_idx)
            recent_data = df.iloc[max(0, signal_idx - lookback_days):signal_idx + 1]
            
            current_price = df.iloc[signal_idx]['close']
            
            # 计算支撑和阻力位
            support_levels = []
            resistance_levels = []
            
            # 基于最近低点和高点
            recent_lows = recent_data['low'].nsmallest(3).values
            recent_highs = recent_data['high'].nlargest(3).values
            
            support_levels.extend(recent_lows)
            resistance_levels.extend(recent_highs)
            
            # 基于参数化的移动平均线
            for period in self.parameters.ma_periods:
                if len(recent_data) >= period:
                    ma = recent_data['close'].rolling(period).mean().iloc[-1]
                    if ma < current_price:
                        support_levels.append(ma)
                    else:
                        resistance_levels.append(ma)
            
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
            print(f"计算参数化价格水平失败: {e}")
            return {'current_price': df.iloc[signal_idx]['close'], 'support_levels': [], 'resistance_levels': []}
    
    def _get_parametric_pre_strategies(self, current_price, price_levels):
        """PRE状态参数化策略"""
        strategies = [
            {
                'strategy': '参数化分批建仓',
                'entry_price_1': round(current_price * (1 - self.parameters.pre_entry_discount), 2),
                'entry_price_2': round(current_price * (1 - self.parameters.pre_entry_discount_2), 2),
                'position_allocation': f'首次{int(self.parameters.conservative_position*100)}%，回调后加仓{int(self.parameters.moderate_position*100-self.parameters.conservative_position*100)}%',
                'rationale': f'基于{self.parameters.pre_entry_discount:.1%}和{self.parameters.pre_entry_discount_2:.1%}折扣参数'
            }
        ]
        
        # 如果有支撑位，添加支撑位策略
        if price_levels['support_levels']:
            strategies.append({
                'strategy': '参数化支撑位买入',
                'entry_price_1': price_levels['support_levels'][-1],
                'entry_price_2': price_levels['support_levels'][-2] if len(price_levels['support_levels']) > 1 else round(current_price * 0.94, 2),
                'position_allocation': f'支撑位附近{int(self.parameters.moderate_position*100)}%仓位',
                'rationale': f'基于{self.parameters.support_lookback}天支撑位计算'
            })
        
        return strategies
    
    def _get_parametric_mid_strategies(self, current_price, price_levels):
        """MID状态参数化策略"""
        return [
            {
                'strategy': '参数化突破确认',
                'entry_price_1': round(current_price * (1 + self.parameters.mid_entry_premium), 2),
                'entry_price_2': round(price_levels['daily_range']['high'] * 1.005, 2),
                'position_allocation': f'确认突破后{int(self.parameters.moderate_position*100)}%仓位',
                'rationale': f'基于{self.parameters.mid_entry_premium:.1%}溢价参数'
            },
            {
                'strategy': '参数化当日低点',
                'entry_price_1': round(price_levels['daily_range']['low'] * 1.002, 2),
                'entry_price_2': round((price_levels['daily_range']['low'] + current_price) / 2, 2),
                'position_allocation': f'当日低点附近{int(self.parameters.aggressive_position*100)}%仓位',
                'rationale': '利用日内波动的参数化策略'
            }
        ]
    
    def _get_parametric_post_strategies(self, current_price, price_levels):
        """POST状态参数化策略"""
        return [
            {
                'strategy': '参数化回调买入',
                'entry_price_1': round(current_price * (1 - self.parameters.post_entry_discount), 2),
                'entry_price_2': round(current_price * (1 - self.parameters.post_entry_discount * 1.5), 2),
                'position_allocation': f'等待{self.parameters.post_entry_discount:.0%}回调后建仓',
                'rationale': f'基于{self.parameters.post_entry_discount:.1%}回调参数'
            }
        ]
    
    def _get_parametric_risk_management(self, current_price, price_levels):
        """参数化风险管理"""
        # 计算技术止损位
        technical_stop = current_price * 0.95
        if price_levels['support_levels']:
            technical_stop = price_levels['support_levels'][-1] * 0.98
        
        return {
            'stop_loss_levels': {
                'conservative': round(current_price * (1 - self.parameters.conservative_stop), 2),
                'moderate': round(current_price * (1 - self.parameters.moderate_stop), 2),
                'aggressive': round(current_price * (1 - self.parameters.aggressive_stop), 2),
                'technical': round(technical_stop, 2)
            },
            'take_profit_levels': {
                'conservative': round(current_price * (1 + self.parameters.conservative_profit), 2),
                'moderate': round(current_price * (1 + self.parameters.moderate_profit), 2),
                'aggressive': round(current_price * (1 + self.parameters.aggressive_profit), 2)
            },
            'position_sizing': {
                'conservative': f'{self.parameters.conservative_position:.0%}',
                'moderate': f'{self.parameters.moderate_position:.0%}',
                'aggressive': f'{self.parameters.aggressive_position:.0%}'
            },
            'max_holding_period': f'{self.parameters.max_holding_days}个交易日'
        }
    
    def backtest_parameters(self, df, signals, risk_level='moderate'):
        """回测参数效果"""
        try:
            if signals is None or not signals.any():
                return {'error': '无有效信号进行回测'}
            
            # 获取风险等级对应的参数
            risk_params = {
                'conservative': {
                    'stop_loss': self.parameters.conservative_stop,
                    'take_profit': self.parameters.conservative_profit,
                    'position_size': self.parameters.conservative_position
                },
                'moderate': {
                    'stop_loss': self.parameters.moderate_stop,
                    'take_profit': self.parameters.moderate_profit,
                    'position_size': self.parameters.moderate_position
                },
                'aggressive': {
                    'stop_loss': self.parameters.aggressive_stop,
                    'take_profit': self.parameters.aggressive_profit,
                    'position_size': self.parameters.aggressive_position
                }
            }
            
            params = risk_params[risk_level]
            
            # 执行回测
            trades = []
            signal_indices = df.index[signals != ''].tolist()
            
            for signal_date in signal_indices:
                signal_idx = df.index.get_loc(signal_date)
                signal_state = signals.loc[signal_date]
                
                if signal_idx >= len(df) - 10:  # 确保有足够的后续数据
                    continue
                
                # 计算入场价格
                entry_price = self._calculate_parametric_entry_price(df, signal_idx, signal_state)
                
                # 计算出场价格和时间
                exit_result = self._calculate_parametric_exit(df, signal_idx, entry_price, params)
                
                if exit_result:
                    trade = {
                        'signal_date': signal_date.strftime('%Y-%m-%d'),
                        'signal_state': signal_state,
                        'entry_price': entry_price,
                        'exit_price': exit_result['exit_price'],
                        'exit_date': exit_result['exit_date'],
                        'holding_days': exit_result['holding_days'],
                        'pnl_pct': exit_result['pnl_pct'],
                        'exit_reason': exit_result['exit_reason']
                    }
                    trades.append(trade)
            
            # 计算回测统计
            if not trades:
                return {'error': '无有效交易进行统计'}
            
            stats = self._calculate_backtest_stats(trades)
            stats['parameters_used'] = asdict(self.parameters)
            stats['risk_level'] = risk_level
            
            return stats
            
        except Exception as e:
            return {'error': f'回测失败: {e}'}
    
    def _calculate_parametric_entry_price(self, df, signal_idx, signal_state):
        """计算参数化入场价格"""
        current_price = df.iloc[signal_idx]['close']
        
        if signal_state == 'PRE':
            return current_price * (1 - self.parameters.pre_entry_discount)
        elif signal_state == 'MID':
            return current_price * (1 + self.parameters.mid_entry_premium)
        elif signal_state == 'POST':
            return current_price * (1 - self.parameters.post_entry_discount)
        else:
            return current_price
    
    def _calculate_parametric_exit(self, df, signal_idx, entry_price, params):
        """计算参数化出场"""
        try:
            stop_loss = entry_price * (1 - params['stop_loss'])
            take_profit = entry_price * (1 + params['take_profit'])
            max_days = self.parameters.max_holding_days
            
            # 从入场后一天开始检查
            for i in range(1, min(max_days + 1, len(df) - signal_idx)):
                current_idx = signal_idx + i
                current_price = df.iloc[current_idx]['close']
                current_low = df.iloc[current_idx]['low']
                current_high = df.iloc[current_idx]['high']
                
                # 检查止损
                if current_low <= stop_loss:
                    return {
                        'exit_price': stop_loss,
                        'exit_date': df.index[current_idx].strftime('%Y-%m-%d'),
                        'holding_days': i,
                        'pnl_pct': (stop_loss - entry_price) / entry_price,
                        'exit_reason': '止损'
                    }
                
                # 检查止盈
                if current_high >= take_profit:
                    return {
                        'exit_price': take_profit,
                        'exit_date': df.index[current_idx].strftime('%Y-%m-%d'),
                        'holding_days': i,
                        'pnl_pct': (take_profit - entry_price) / entry_price,
                        'exit_reason': '止盈'
                    }
            
            # 超过最大持有期，按收盘价出场
            final_idx = min(signal_idx + max_days, len(df) - 1)
            final_price = df.iloc[final_idx]['close']
            
            return {
                'exit_price': final_price,
                'exit_date': df.index[final_idx].strftime('%Y-%m-%d'),
                'holding_days': final_idx - signal_idx,
                'pnl_pct': (final_price - entry_price) / entry_price,
                'exit_reason': '超时出场'
            }
            
        except Exception as e:
            print(f"计算出场失败: {e}")
            return None
    
    def _calculate_backtest_stats(self, trades):
        """计算回测统计"""
        if not trades:
            return {}
        
        pnls = [trade['pnl_pct'] for trade in trades]
        winning_trades = [t for t in trades if t['pnl_pct'] > 0]
        losing_trades = [t for t in trades if t['pnl_pct'] < 0]
        
        stats = {
            'total_trades': len(trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(trades) if trades else 0,
            'avg_pnl': np.mean(pnls),
            'avg_win': np.mean([t['pnl_pct'] for t in winning_trades]) if winning_trades else 0,
            'avg_loss': np.mean([t['pnl_pct'] for t in losing_trades]) if losing_trades else 0,
            'max_win': max(pnls) if pnls else 0,
            'max_loss': min(pnls) if pnls else 0,
            'avg_holding_days': np.mean([t['holding_days'] for t in trades]),
            'profit_factor': abs(sum([t['pnl_pct'] for t in winning_trades]) / sum([t['pnl_pct'] for t in losing_trades])) if losing_trades else float('inf'),
            'trades_detail': trades
        }
        
        return stats
    
    def optimize_parameters_for_stock(self, df, signals, optimization_target='win_rate'):
        """为单只股票优化参数"""
        print(f"🔧 开始参数优化，目标: {optimization_target}")
        
        # 定义参数搜索空间
        param_ranges = {
            'pre_entry_discount': [0.01, 0.02, 0.03, 0.05],
            'moderate_stop': [0.03, 0.05, 0.08],
            'moderate_profit': [0.08, 0.12, 0.15, 0.20],
            'max_holding_days': [15, 20, 30, 45]
        }
        
        best_params = None
        best_score = -float('inf') if optimization_target in ['win_rate', 'avg_pnl', 'profit_factor'] else float('inf')
        optimization_results = []
        
        # 生成参数组合
        param_combinations = list(itertools.product(*param_ranges.values()))
        total_combinations = len(param_combinations)
        
        print(f"📊 总共需要测试 {total_combinations} 种参数组合")
        
        for i, combination in enumerate(param_combinations):
            if i % 10 == 0:
                print(f"进度: {i}/{total_combinations} ({i/total_combinations*100:.1f}%)")
            
            # 创建测试参数
            test_params = TradingParameters()
            test_params.pre_entry_discount = combination[0]
            test_params.moderate_stop = combination[1]
            test_params.moderate_profit = combination[2]
            test_params.max_holding_days = combination[3]
            
            # 创建测试顾问
            test_advisor = ParametricTradingAdvisor(test_params)
            
            # 执行回测
            backtest_result = test_advisor.backtest_parameters(df, signals, 'moderate')
            
            if 'error' not in backtest_result and backtest_result['total_trades'] >= 3:
                score = backtest_result.get(optimization_target, 0)
                
                result = {
                    'parameters': asdict(test_params),
                    'score': score,
                    'stats': backtest_result
                }
                optimization_results.append(result)
                
                # 更新最佳参数
                if optimization_target in ['win_rate', 'avg_pnl', 'profit_factor']:
                    if score > best_score:
                        best_score = score
                        best_params = test_params
                else:  # 对于需要最小化的目标
                    if score < best_score:
                        best_score = score
                        best_params = test_params
        
        # 保存优化历史
        self.optimization_history.append({
            'timestamp': datetime.now().isoformat(),
            'optimization_target': optimization_target,
            'best_score': best_score,
            'best_parameters': asdict(best_params) if best_params else None,
            'total_combinations_tested': len(optimization_results)
        })
        
        print(f"✅ 参数优化完成！")
        print(f"最佳{optimization_target}: {best_score:.4f}")
        
        return {
            'best_parameters': best_params,
            'best_score': best_score,
            'optimization_results': sorted(optimization_results, key=lambda x: x['score'], reverse=True)[:10],  # 返回前10个结果
            'optimization_target': optimization_target
        }
    
    def save_optimized_parameters(self, stock_code, optimization_result, file_path=None):
        """保存优化后的参数"""
        if file_path is None:
            file_path = f"optimized_parameters_{stock_code}.json"
        
        save_data = {
            'stock_code': stock_code,
            'optimization_date': datetime.now().isoformat(),
            'best_parameters': asdict(optimization_result['best_parameters']),
            'best_score': optimization_result['best_score'],
            'optimization_target': optimization_result['optimization_target'],
            'top_results': optimization_result['optimization_results'][:5]
        }
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(save_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 优化参数已保存到: {file_path}")
    
    def load_optimized_parameters(self, stock_code, file_path=None):
        """加载优化后的参数"""
        if file_path is None:
            file_path = f"optimized_parameters_{stock_code}.json"
        
        if not os.path.exists(file_path):
            print(f"⚠️ 参数文件不存在: {file_path}")
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 重建参数对象
            params_dict = data['best_parameters']
            optimized_params = TradingParameters(**params_dict)
            
            print(f"📂 已加载 {stock_code} 的优化参数")
            return optimized_params
            
        except Exception as e:
            print(f"❌ 加载参数失败: {e}")
            return None