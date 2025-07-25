#!/usr/bin/env python3
"""
多周期信号生成器
实现多时间框架协同的信号生成和融合算法
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
import strategies
import indicators

class MultiTimeframeSignalGenerator:
    """多周期信号生成器"""
    
    def __init__(self, data_manager: MultiTimeframeDataManager = None):
        """初始化多周期信号生成器"""
        self.data_manager = data_manager or MultiTimeframeDataManager()
        
        # 信号融合权重
        self.signal_weights = {
            '1week': 0.40,   # 长期趋势权重最高
            '1day': 0.25,    # 主趋势权重
            '4hour': 0.20,   # 中期趋势权重
            '1hour': 0.10,   # 短期趋势权重
            '30min': 0.03,   # 入场时机权重
            '15min': 0.015,  # 精确入场权重
            '5min': 0.005    # 微调权重
        }
        
        # 信号强度阈值
        self.signal_thresholds = {
            'strong_buy': 0.7,
            'buy': 0.4,
            'weak_buy': 0.2,
            'neutral': 0.0,
            'weak_sell': -0.2,
            'sell': -0.4,
            'strong_sell': -0.7
        }
        
        # 策略配置
        self.strategies = {
            'trend_following': self._trend_following_strategy,
            'reversal_catching': self._reversal_catching_strategy,
            'breakout': self._breakout_strategy,
            'momentum': self._momentum_strategy
        }
        
        self.logger = logging.getLogger(__name__)
    
    def generate_composite_signals(self, stock_code: str, strategy_types: List[str] = None) -> Dict:
        """生成复合周期信号"""
        try:
            if strategy_types is None:
                strategy_types = list(self.strategies.keys())
            
            self.logger.info(f"为{stock_code}生成多周期复合信号")
            
            # 获取多周期指标数据
            indicators_data = self.data_manager.calculate_multi_timeframe_indicators(stock_code)
            if 'error' in indicators_data:
                return indicators_data
            
            # 生成信号结果
            signal_result = {
                'stock_code': stock_code,
                'generation_time': datetime.now().isoformat(),
                'timeframe_signals': {},
                'strategy_signals': {},
                'composite_signal': {},
                'confidence_analysis': {},
                'risk_assessment': {}
            }
            
            # 1. 为每个时间周期生成信号
            for timeframe, tf_data in indicators_data['timeframes'].items():
                tf_signals = self._generate_timeframe_signals(tf_data, timeframe)
                signal_result['timeframe_signals'][timeframe] = tf_signals
            
            # 2. 为每个策略类型生成信号
            for strategy_type in strategy_types:
                if strategy_type in self.strategies:
                    strategy_signals = self.strategies[strategy_type](
                        indicators_data, signal_result['timeframe_signals']
                    )
                    signal_result['strategy_signals'][strategy_type] = strategy_signals
            
            # 3. 融合生成复合信号
            composite_signal = self._fuse_signals(
                signal_result['timeframe_signals'],
                signal_result['strategy_signals']
            )
            signal_result['composite_signal'] = composite_signal
            
            # 4. 置信度分析
            confidence_analysis = self._analyze_signal_confidence(
                signal_result['timeframe_signals'],
                indicators_data.get('cross_timeframe_analysis', {})
            )
            signal_result['confidence_analysis'] = confidence_analysis
            
            # 5. 风险评估
            risk_assessment = self._assess_signal_risk(
                signal_result['composite_signal'],
                indicators_data
            )
            signal_result['risk_assessment'] = risk_assessment
            
            return signal_result
            
        except Exception as e:
            self.logger.error(f"生成{stock_code}复合信号失败: {e}")
            return {'error': str(e)}
    
    def _generate_timeframe_signals(self, tf_data: Dict, timeframe: str) -> Dict:
        """为单个时间周期生成信号"""
        try:
            tf_signals = {
                'timeframe': timeframe,
                'trend_signal': 0.0,
                'momentum_signal': 0.0,
                'reversal_signal': 0.0,
                'breakout_signal': 0.0,
                'composite_score': 0.0,
                'signal_strength': 'neutral',
                'supporting_indicators': []
            }
            
            indicators_dict = tf_data.get('indicators', {})
            signals_dict = tf_data.get('signals', {})
            trend_analysis = tf_data.get('trend_analysis', {})
            
            # 1. 趋势信号
            trend_signal = self._calculate_trend_signal(indicators_dict, trend_analysis)
            tf_signals['trend_signal'] = trend_signal
            
            # 2. 动量信号
            momentum_signal = self._calculate_momentum_signal(indicators_dict, signals_dict)
            tf_signals['momentum_signal'] = momentum_signal
            
            # 3. 反转信号
            reversal_signal = self._calculate_reversal_signal(indicators_dict, signals_dict)
            tf_signals['reversal_signal'] = reversal_signal
            
            # 4. 突破信号
            breakout_signal = self._calculate_breakout_signal(indicators_dict, trend_analysis)
            tf_signals['breakout_signal'] = breakout_signal
            
            # 5. 复合评分
            composite_score = (
                trend_signal * 0.4 +
                momentum_signal * 0.3 +
                reversal_signal * 0.2 +
                breakout_signal * 0.1
            )
            tf_signals['composite_score'] = composite_score
            
            # 6. 信号强度分类
            tf_signals['signal_strength'] = self._classify_signal_strength(composite_score)
            
            # 7. 支持指标
            tf_signals['supporting_indicators'] = self._identify_supporting_indicators(
                indicators_dict, signals_dict, composite_score
            )
            
            return tf_signals
            
        except Exception as e:
            self.logger.error(f"生成{timeframe}信号失败: {e}")
            return {'error': str(e)}
    
    def _calculate_trend_signal(self, indicators_dict: Dict, trend_analysis: Dict) -> float:
        """计算趋势信号"""
        try:
            trend_signal = 0.0
            
            # 基于价格趋势
            price_trend = trend_analysis.get('price_trend', 'sideways')
            if price_trend == 'uptrend':
                trend_signal += 0.3
            elif price_trend == 'downtrend':
                trend_signal -= 0.3
            
            # 基于移动平均线
            ma_data = indicators_dict.get('ma', {})
            ma_5 = ma_data.get('ma_5', [])
            ma_10 = ma_data.get('ma_10', [])
            ma_20 = ma_data.get('ma_20', [])
            
            if len(ma_5) >= 1 and len(ma_10) >= 1 and len(ma_20) >= 1:
                current_price = ma_5[-1] if ma_5 else 0
                
                # 均线排列
                if current_price > ma_5[-1] > ma_10[-1] > ma_20[-1]:
                    trend_signal += 0.4  # 多头排列
                elif current_price < ma_5[-1] < ma_10[-1] < ma_20[-1]:
                    trend_signal -= 0.4  # 空头排列
                
                # 均线斜率
                if len(ma_20) >= 5:
                    ma20_slope = (ma_20[-1] - ma_20[-5]) / ma_20[-5]
                    trend_signal += ma20_slope * 2  # 放大斜率影响
            
            # 基于MACD趋势
            macd_data = indicators_dict.get('macd', {})
            macd_dif = macd_data.get('dif', [])
            macd_dea = macd_data.get('dea', [])
            
            if len(macd_dif) >= 2 and len(macd_dea) >= 2:
                if macd_dif[-1] > macd_dea[-1] and macd_dif[-1] > macd_dif[-2]:
                    trend_signal += 0.2
                elif macd_dif[-1] < macd_dea[-1] and macd_dif[-1] < macd_dif[-2]:
                    trend_signal -= 0.2
            
            return np.clip(trend_signal, -1.0, 1.0)
            
        except Exception as e:
            self.logger.error(f"计算趋势信号失败: {e}")
            return 0.0
    
    def _calculate_momentum_signal(self, indicators_dict: Dict, signals_dict: Dict) -> float:
        """计算动量信号"""
        try:
            momentum_signal = 0.0
            
            # 基于RSI
            rsi_data = indicators_dict.get('rsi', {})
            rsi_14 = rsi_data.get('rsi_14', [])
            
            if len(rsi_14) >= 2:
                current_rsi = rsi_14[-1]
                prev_rsi = rsi_14[-2]
                
                # RSI动量
                rsi_momentum = (current_rsi - prev_rsi) / 100
                momentum_signal += rsi_momentum * 2
                
                # RSI位置
                if current_rsi < 30:
                    momentum_signal += 0.3  # 超卖反弹
                elif current_rsi > 70:
                    momentum_signal -= 0.3  # 超买回调
            
            # 基于KDJ动量
            kdj_data = indicators_dict.get('kdj', {})
            kdj_k = kdj_data.get('k', [])
            kdj_d = kdj_data.get('d', [])
            
            if len(kdj_k) >= 2 and len(kdj_d) >= 2:
                k_momentum = (kdj_k[-1] - kdj_k[-2]) / 100
                d_momentum = (kdj_d[-1] - kdj_d[-2]) / 100
                
                momentum_signal += (k_momentum + d_momentum) * 0.5
            
            # 基于MACD柱状图
            macd_data = indicators_dict.get('macd', {})
            macd_histogram = macd_data.get('histogram', [])
            
            if len(macd_histogram) >= 2:
                histogram_change = macd_histogram[-1] - macd_histogram[-2]
                momentum_signal += histogram_change * 10  # 放大柱状图变化影响
            
            return np.clip(momentum_signal, -1.0, 1.0)
            
        except Exception as e:
            self.logger.error(f"计算动量信号失败: {e}")
            return 0.0
    
    def _calculate_reversal_signal(self, indicators_dict: Dict, signals_dict: Dict) -> float:
        """计算反转信号"""
        try:
            reversal_signal = 0.0
            
            # 基于RSI反转
            rsi_data = indicators_dict.get('rsi', {})
            rsi_14 = rsi_data.get('rsi_14', [])
            
            if len(rsi_14) >= 3:
                current_rsi = rsi_14[-1]
                
                # RSI背离检测（简化版）
                if current_rsi < 30 and rsi_14[-2] < rsi_14[-3]:
                    reversal_signal += 0.4  # 超卖反转
                elif current_rsi > 70 and rsi_14[-2] > rsi_14[-3]:
                    reversal_signal -= 0.4  # 超买反转
            
            # 基于KDJ反转
            kdj_signals = signals_dict.get('kdj_signals', [])
            if 'oversold_golden_cross' in kdj_signals:
                reversal_signal += 0.3
            elif 'overbought_death_cross' in kdj_signals:
                reversal_signal -= 0.3
            
            # 基于布林带反转
            bb_data = indicators_dict.get('bollinger', {})
            bb_upper = bb_data.get('upper', [])
            bb_lower = bb_data.get('lower', [])
            
            if len(bb_upper) >= 1 and len(bb_lower) >= 1:
                # 这里需要价格数据，暂时简化处理
                # 实际应用中需要传入价格数据进行比较
                pass
            
            return np.clip(reversal_signal, -1.0, 1.0)
            
        except Exception as e:
            self.logger.error(f"计算反转信号失败: {e}")
            return 0.0
    
    def _calculate_breakout_signal(self, indicators_dict: Dict, trend_analysis: Dict) -> float:
        """计算突破信号"""
        try:
            breakout_signal = 0.0
            
            # 基于成交量突破
            volume_trend = trend_analysis.get('volume_trend', 'stable')
            if volume_trend == 'increasing':
                breakout_signal += 0.3
            elif volume_trend == 'decreasing':
                breakout_signal -= 0.1
            
            # 基于波动率突破
            volatility = trend_analysis.get('volatility', 0)
            if volatility > 0.3:  # 高波动率
                breakout_signal += 0.2
            elif volatility < 0.1:  # 低波动率
                breakout_signal -= 0.1
            
            # 基于移动平均线突破
            ma_signals = indicators_dict.get('ma', {})
            # 这里可以添加更复杂的突破逻辑
            
            return np.clip(breakout_signal, -1.0, 1.0)
            
        except Exception as e:
            self.logger.error(f"计算突破信号失败: {e}")
            return 0.0
    
    def _classify_signal_strength(self, composite_score: float) -> str:
        """分类信号强度"""
        if composite_score >= self.signal_thresholds['strong_buy']:
            return 'strong_buy'
        elif composite_score >= self.signal_thresholds['buy']:
            return 'buy'
        elif composite_score >= self.signal_thresholds['weak_buy']:
            return 'weak_buy'
        elif composite_score <= self.signal_thresholds['strong_sell']:
            return 'strong_sell'
        elif composite_score <= self.signal_thresholds['sell']:
            return 'sell'
        elif composite_score <= self.signal_thresholds['weak_sell']:
            return 'weak_sell'
        else:
            return 'neutral'
    
    def _identify_supporting_indicators(self, indicators_dict: Dict, signals_dict: Dict, composite_score: float) -> List[str]:
        """识别支持指标"""
        supporting = []
        
        try:
            # MACD支持
            macd_signals = signals_dict.get('macd_signals', [])
            if composite_score > 0 and 'golden_cross' in macd_signals:
                supporting.append('MACD金叉')
            elif composite_score < 0 and 'death_cross' in macd_signals:
                supporting.append('MACD死叉')
            
            # KDJ支持
            kdj_signals = signals_dict.get('kdj_signals', [])
            if composite_score > 0 and 'oversold_golden_cross' in kdj_signals:
                supporting.append('KDJ超卖金叉')
            elif composite_score < 0 and 'overbought_death_cross' in kdj_signals:
                supporting.append('KDJ超买死叉')
            
            # RSI支持
            rsi_signals = signals_dict.get('rsi_signals', [])
            if composite_score > 0 and 'oversold' in rsi_signals:
                supporting.append('RSI超卖')
            elif composite_score < 0 and 'overbought' in rsi_signals:
                supporting.append('RSI超买')
            
            # 移动平均线支持
            ma_signals = signals_dict.get('ma_signals', [])
            if composite_score > 0 and 'ma5_cross_ma20_up' in ma_signals:
                supporting.append('均线金叉')
            elif composite_score < 0 and 'ma5_cross_ma20_down' in ma_signals:
                supporting.append('均线死叉')
            
        except Exception as e:
            self.logger.error(f"识别支持指标失败: {e}")
        
        return supporting
    
    def _trend_following_strategy(self, indicators_data: Dict, timeframe_signals: Dict) -> Dict:
        """趋势跟踪策略"""
        try:
            strategy_result = {
                'strategy_type': 'trend_following',
                'signal_score': 0.0,
                'confidence': 0.0,
                'entry_conditions': [],
                'risk_factors': []
            }
            
            # 长周期趋势确认
            long_term_trend = 0.0
            for timeframe in ['1day', '4hour']:
                if timeframe in timeframe_signals:
                    tf_signal = timeframe_signals[timeframe]
                    trend_signal = tf_signal.get('trend_signal', 0)
                    weight = self.signal_weights.get(timeframe, 0.1)
                    long_term_trend += trend_signal * weight
            
            # 中短期入场时机
            entry_timing = 0.0
            for timeframe in ['1hour', '30min', '15min']:
                if timeframe in timeframe_signals:
                    tf_signal = timeframe_signals[timeframe]
                    momentum_signal = tf_signal.get('momentum_signal', 0)
                    weight = self.signal_weights.get(timeframe, 0.1)
                    entry_timing += momentum_signal * weight
            
            # 综合评分
            strategy_result['signal_score'] = (long_term_trend * 0.7 + entry_timing * 0.3)
            
            # 置信度计算
            trend_consistency = self._calculate_trend_consistency(timeframe_signals)
            strategy_result['confidence'] = trend_consistency
            
            # 入场条件
            if strategy_result['signal_score'] > 0.3:
                strategy_result['entry_conditions'] = [
                    '长周期趋势向上',
                    '中短周期动量配合',
                    '多周期信号一致'
                ]
            elif strategy_result['signal_score'] < -0.3:
                strategy_result['entry_conditions'] = [
                    '长周期趋势向下',
                    '中短周期动量配合',
                    '多周期信号一致'
                ]
            
            return strategy_result
            
        except Exception as e:
            self.logger.error(f"趋势跟踪策略失败: {e}")
            return {'error': str(e)}
    
    def _reversal_catching_strategy(self, indicators_data: Dict, timeframe_signals: Dict) -> Dict:
        """反转捕捉策略"""
        try:
            strategy_result = {
                'strategy_type': 'reversal_catching',
                'signal_score': 0.0,
                'confidence': 0.0,
                'entry_conditions': [],
                'risk_factors': []
            }
            
            # 反转信号强度
            reversal_strength = 0.0
            for timeframe, tf_signal in timeframe_signals.items():
                reversal_signal = tf_signal.get('reversal_signal', 0)
                weight = self.signal_weights.get(timeframe, 0.1)
                reversal_strength += abs(reversal_signal) * weight
            
            # 超买超卖程度
            oversold_score = 0.0
            overbought_score = 0.0
            
            for timeframe, tf_signal in timeframe_signals.items():
                supporting_indicators = tf_signal.get('supporting_indicators', [])
                if 'RSI超卖' in supporting_indicators or 'KDJ超卖金叉' in supporting_indicators:
                    oversold_score += self.signal_weights.get(timeframe, 0.1)
                elif 'RSI超买' in supporting_indicators or 'KDJ超买死叉' in supporting_indicators:
                    overbought_score += self.signal_weights.get(timeframe, 0.1)
            
            # 综合评分
            if oversold_score > overbought_score:
                strategy_result['signal_score'] = oversold_score * reversal_strength
            else:
                strategy_result['signal_score'] = -overbought_score * reversal_strength
            
            # 置信度
            strategy_result['confidence'] = min(reversal_strength, 1.0)
            
            return strategy_result
            
        except Exception as e:
            self.logger.error(f"反转捕捉策略失败: {e}")
            return {'error': str(e)}
    
    def _breakout_strategy(self, indicators_data: Dict, timeframe_signals: Dict) -> Dict:
        """突破策略"""
        try:
            strategy_result = {
                'strategy_type': 'breakout',
                'signal_score': 0.0,
                'confidence': 0.0,
                'entry_conditions': [],
                'risk_factors': []
            }
            
            # 突破信号强度
            breakout_strength = 0.0
            for timeframe, tf_signal in timeframe_signals.items():
                breakout_signal = tf_signal.get('breakout_signal', 0)
                weight = self.signal_weights.get(timeframe, 0.1)
                breakout_strength += breakout_signal * weight
            
            strategy_result['signal_score'] = breakout_strength
            strategy_result['confidence'] = abs(breakout_strength)
            
            return strategy_result
            
        except Exception as e:
            self.logger.error(f"突破策略失败: {e}")
            return {'error': str(e)}
    
    def _momentum_strategy(self, indicators_data: Dict, timeframe_signals: Dict) -> Dict:
        """动量策略"""
        try:
            strategy_result = {
                'strategy_type': 'momentum',
                'signal_score': 0.0,
                'confidence': 0.0,
                'entry_conditions': [],
                'risk_factors': []
            }
            
            # 动量信号强度
            momentum_strength = 0.0
            for timeframe, tf_signal in timeframe_signals.items():
                momentum_signal = tf_signal.get('momentum_signal', 0)
                weight = self.signal_weights.get(timeframe, 0.1)
                momentum_strength += momentum_signal * weight
            
            strategy_result['signal_score'] = momentum_strength
            strategy_result['confidence'] = abs(momentum_strength)
            
            return strategy_result
            
        except Exception as e:
            self.logger.error(f"动量策略失败: {e}")
            return {'error': str(e)}
    
    def _fuse_signals(self, timeframe_signals: Dict, strategy_signals: Dict) -> Dict:
        """融合信号"""
        try:
            composite_signal = {
                'final_score': 0.0,
                'signal_strength': 'neutral',
                'confidence_level': 0.0,
                'primary_timeframes': [],
                'primary_strategies': [],
                'consensus_analysis': {}
            }
            
            # 1. 时间周期信号融合
            timeframe_score = 0.0
            timeframe_weights_sum = 0.0
            
            for timeframe, tf_signal in timeframe_signals.items():
                if 'error' not in tf_signal:
                    score = tf_signal.get('composite_score', 0)
                    weight = self.signal_weights.get(timeframe, 0.1)
                    timeframe_score += score * weight
                    timeframe_weights_sum += weight
            
            if timeframe_weights_sum > 0:
                timeframe_score /= timeframe_weights_sum
            
            # 2. 策略信号融合
            strategy_score = 0.0
            strategy_count = 0
            
            for strategy_type, strategy_signal in strategy_signals.items():
                if 'error' not in strategy_signal:
                    score = strategy_signal.get('signal_score', 0)
                    strategy_score += score
                    strategy_count += 1
            
            if strategy_count > 0:
                strategy_score /= strategy_count
            
            # 3. 最终评分
            composite_signal['final_score'] = (timeframe_score * 0.6 + strategy_score * 0.4)
            
            # 4. 信号强度分类
            composite_signal['signal_strength'] = self._classify_signal_strength(
                composite_signal['final_score']
            )
            
            # 5. 置信度计算
            confidence_factors = []
            
            # 时间周期一致性
            trend_consistency = self._calculate_trend_consistency(timeframe_signals)
            confidence_factors.append(trend_consistency)
            
            # 策略一致性
            strategy_consistency = self._calculate_strategy_consistency(strategy_signals)
            confidence_factors.append(strategy_consistency)
            
            composite_signal['confidence_level'] = np.mean(confidence_factors) if confidence_factors else 0.0
            
            # 6. 主要支持周期和策略
            composite_signal['primary_timeframes'] = self._identify_primary_timeframes(timeframe_signals)
            composite_signal['primary_strategies'] = self._identify_primary_strategies(strategy_signals)
            
            # 7. 共识分析
            composite_signal['consensus_analysis'] = self._analyze_signal_consensus(
                timeframe_signals, strategy_signals
            )
            
            return composite_signal
            
        except Exception as e:
            self.logger.error(f"信号融合失败: {e}")
            return {'error': str(e)}
    
    def _calculate_trend_consistency(self, timeframe_signals: Dict) -> float:
        """计算趋势一致性"""
        try:
            trend_signals = []
            for tf_signal in timeframe_signals.values():
                if 'error' not in tf_signal:
                    trend_signal = tf_signal.get('trend_signal', 0)
                    trend_signals.append(trend_signal)
            
            if len(trend_signals) < 2:
                return 0.0
            
            # 计算信号方向一致性
            positive_count = sum(1 for s in trend_signals if s > 0.1)
            negative_count = sum(1 for s in trend_signals if s < -0.1)
            neutral_count = len(trend_signals) - positive_count - negative_count
            
            max_consensus = max(positive_count, negative_count, neutral_count)
            consistency = max_consensus / len(trend_signals)
            
            return consistency
            
        except Exception as e:
            self.logger.error(f"计算趋势一致性失败: {e}")
            return 0.0
    
    def _calculate_strategy_consistency(self, strategy_signals: Dict) -> float:
        """计算策略一致性"""
        try:
            strategy_scores = []
            for strategy_signal in strategy_signals.values():
                if 'error' not in strategy_signal:
                    score = strategy_signal.get('signal_score', 0)
                    strategy_scores.append(score)
            
            if len(strategy_scores) < 2:
                return 0.0
            
            # 计算策略信号的标准差，标准差越小一致性越高
            std_dev = np.std(strategy_scores)
            consistency = max(0.0, 1.0 - std_dev)
            
            return consistency
            
        except Exception as e:
            self.logger.error(f"计算策略一致性失败: {e}")
            return 0.0
    
    def _identify_primary_timeframes(self, timeframe_signals: Dict) -> List[str]:
        """识别主要支持时间周期"""
        try:
            timeframe_scores = []
            for timeframe, tf_signal in timeframe_signals.items():
                if 'error' not in tf_signal:
                    score = abs(tf_signal.get('composite_score', 0))
                    timeframe_scores.append((timeframe, score))
            
            # 按评分排序
            timeframe_scores.sort(key=lambda x: x[1], reverse=True)
            
            # 返回前3个主要时间周期
            return [tf[0] for tf in timeframe_scores[:3]]
            
        except Exception as e:
            self.logger.error(f"识别主要时间周期失败: {e}")
            return []
    
    def _identify_primary_strategies(self, strategy_signals: Dict) -> List[str]:
        """识别主要支持策略"""
        try:
            strategy_scores = []
            for strategy_type, strategy_signal in strategy_signals.items():
                if 'error' not in strategy_signal:
                    score = abs(strategy_signal.get('signal_score', 0))
                    strategy_scores.append((strategy_type, score))
            
            # 按评分排序
            strategy_scores.sort(key=lambda x: x[1], reverse=True)
            
            # 返回前2个主要策略
            return [st[0] for st in strategy_scores[:2]]
            
        except Exception as e:
            self.logger.error(f"识别主要策略失败: {e}")
            return []
    
    def _analyze_signal_consensus(self, timeframe_signals: Dict, strategy_signals: Dict) -> Dict:
        """分析信号共识"""
        try:
            consensus_analysis = {
                'timeframe_consensus': 0.0,
                'strategy_consensus': 0.0,
                'overall_consensus': 0.0,
                'conflicting_signals': [],
                'supporting_signals': []
            }
            
            # 时间周期共识
            tf_scores = [tf_signal.get('composite_score', 0) 
                        for tf_signal in timeframe_signals.values() 
                        if 'error' not in tf_signal]
            
            if tf_scores:
                positive_tf = sum(1 for score in tf_scores if score > 0.1)
                negative_tf = sum(1 for score in tf_scores if score < -0.1)
                total_tf = len(tf_scores)
                
                consensus_analysis['timeframe_consensus'] = max(positive_tf, negative_tf) / total_tf
            
            # 策略共识
            strategy_scores = [strategy_signal.get('signal_score', 0) 
                             for strategy_signal in strategy_signals.values() 
                             if 'error' not in strategy_signal]
            
            if strategy_scores:
                positive_st = sum(1 for score in strategy_scores if score > 0.1)
                negative_st = sum(1 for score in strategy_scores if score < -0.1)
                total_st = len(strategy_scores)
                
                consensus_analysis['strategy_consensus'] = max(positive_st, negative_st) / total_st
            
            # 整体共识
            consensus_analysis['overall_consensus'] = (
                consensus_analysis['timeframe_consensus'] * 0.6 +
                consensus_analysis['strategy_consensus'] * 0.4
            )
            
            return consensus_analysis
            
        except Exception as e:
            self.logger.error(f"分析信号共识失败: {e}")
            return {}
    
    def _analyze_signal_confidence(self, timeframe_signals: Dict, cross_timeframe_analysis: Dict) -> Dict:
        """分析信号置信度"""
        try:
            confidence_analysis = {
                'overall_confidence': 0.0,
                'confidence_factors': {},
                'risk_factors': [],
                'confidence_breakdown': {}
            }
            
            confidence_factors = []
            
            # 1. 趋势一致性置信度
            trend_consistency = self._calculate_trend_consistency(timeframe_signals)
            confidence_factors.append(('trend_consistency', trend_consistency, 0.3))
            
            # 2. 信号强度置信度
            signal_strengths = []
            for tf_signal in timeframe_signals.values():
                if 'error' not in tf_signal:
                    strength = abs(tf_signal.get('composite_score', 0))
                    signal_strengths.append(strength)
            
            avg_strength = np.mean(signal_strengths) if signal_strengths else 0.0
            confidence_factors.append(('signal_strength', avg_strength, 0.25))
            
            # 3. 跨周期分析置信度
            cross_confidence = 0.0
            if cross_timeframe_analysis:
                alignment_strength = cross_timeframe_analysis.get('trend_alignment', {}).get('alignment_strength', 0)
                convergence_strength = cross_timeframe_analysis.get('signal_convergence', {}).get('convergence_strength', 0)
                cross_confidence = (alignment_strength + convergence_strength) / 2
            
            confidence_factors.append(('cross_timeframe', cross_confidence, 0.25))
            
            # 4. 支持指标数量置信度
            total_supporting = 0
            for tf_signal in timeframe_signals.values():
                if 'error' not in tf_signal:
                    supporting = len(tf_signal.get('supporting_indicators', []))
                    total_supporting += supporting
            
            supporting_confidence = min(total_supporting / 10, 1.0)  # 最多10个支持指标
            confidence_factors.append(('supporting_indicators', supporting_confidence, 0.2))
            
            # 计算加权置信度
            weighted_confidence = 0.0
            for factor_name, factor_value, weight in confidence_factors:
                weighted_confidence += factor_value * weight
                confidence_analysis['confidence_factors'][factor_name] = {
                    'value': factor_value,
                    'weight': weight,
                    'contribution': factor_value * weight
                }
            
            confidence_analysis['overall_confidence'] = weighted_confidence
            
            # 风险因素识别
            if trend_consistency < 0.5:
                confidence_analysis['risk_factors'].append('趋势不一致')
            
            if avg_strength < 0.3:
                confidence_analysis['risk_factors'].append('信号强度偏弱')
            
            if cross_confidence < 0.4:
                confidence_analysis['risk_factors'].append('跨周期分析不支持')
            
            return confidence_analysis
            
        except Exception as e:
            self.logger.error(f"分析信号置信度失败: {e}")
            return {'error': str(e)}
    
    def _assess_signal_risk(self, composite_signal: Dict, indicators_data: Dict) -> Dict:
        """评估信号风险"""
        try:
            risk_assessment = {
                'overall_risk_level': 'medium',
                'risk_score': 0.5,
                'risk_factors': [],
                'risk_mitigation': [],
                'position_sizing_suggestion': 0.5
            }
            
            risk_factors = []
            risk_score = 0.0
            
            # 1. 信号强度风险
            final_score = abs(composite_signal.get('final_score', 0))
            if final_score < 0.3:
                risk_factors.append('信号强度偏弱')
                risk_score += 0.2
            
            # 2. 置信度风险
            confidence_level = composite_signal.get('confidence_level', 0)
            if confidence_level < 0.5:
                risk_factors.append('置信度不足')
                risk_score += 0.3
            
            # 3. 市场波动风险
            cross_analysis = indicators_data.get('cross_timeframe_analysis', {})
            if cross_analysis:
                # 这里可以添加更多基于跨周期分析的风险评估
                pass
            
            # 4. 流动性风险（基于成交量分析）
            # 这里需要更多的成交量数据分析
            
            risk_assessment['risk_score'] = min(risk_score, 1.0)
            risk_assessment['risk_factors'] = risk_factors
            
            # 风险等级分类
            if risk_score < 0.3:
                risk_assessment['overall_risk_level'] = 'low'
                risk_assessment['position_sizing_suggestion'] = 0.8
            elif risk_score < 0.7:
                risk_assessment['overall_risk_level'] = 'medium'
                risk_assessment['position_sizing_suggestion'] = 0.5
            else:
                risk_assessment['overall_risk_level'] = 'high'
                risk_assessment['position_sizing_suggestion'] = 0.2
            
            # 风险缓解建议
            if '信号强度偏弱' in risk_factors:
                risk_assessment['risk_mitigation'].append('等待更强信号确认')
            
            if '置信度不足' in risk_factors:
                risk_assessment['risk_mitigation'].append('降低仓位规模')
            
            return risk_assessment
            
        except Exception as e:
            self.logger.error(f"评估信号风险失败: {e}")
            return {'error': str(e)}

def main():
    """测试函数"""
    print("🎯 多周期信号生成器测试")
    print("=" * 50)
    
    # 创建信号生成器
    signal_generator = MultiTimeframeSignalGenerator()
    
    # 测试股票
    test_stocks = ['sz300290', 'sz002691']
    
    for stock_code in test_stocks:
        print(f"\n📊 测试股票: {stock_code}")
        
        # 生成复合信号
        signal_result = signal_generator.generate_composite_signals(stock_code)
        
        if 'error' in signal_result:
            print(f"  ❌ 信号生成失败: {signal_result['error']}")
            continue
        
        # 显示结果
        composite_signal = signal_result.get('composite_signal', {})
        final_score = composite_signal.get('final_score', 0)
        signal_strength = composite_signal.get('signal_strength', 'neutral')
        confidence_level = composite_signal.get('confidence_level', 0)
        
        print(f"  ✅ 复合信号生成成功")
        print(f"    最终评分: {final_score:.3f}")
        print(f"    信号强度: {signal_strength}")
        print(f"    置信度: {confidence_level:.3f}")
        
        # 显示主要支持
        primary_timeframes = composite_signal.get('primary_timeframes', [])
        primary_strategies = composite_signal.get('primary_strategies', [])
        
        if primary_timeframes:
            print(f"    主要时间周期: {', '.join(primary_timeframes)}")
        
        if primary_strategies:
            print(f"    主要策略: {', '.join(primary_strategies)}")
        
        # 显示风险评估
        risk_assessment = signal_result.get('risk_assessment', {})
        risk_level = risk_assessment.get('overall_risk_level', 'unknown')
        position_suggestion = risk_assessment.get('position_sizing_suggestion', 0)
        
        print(f"    风险等级: {risk_level}")
        print(f"    建议仓位: {position_suggestion:.1%}")
        
        break  # 只测试第一个有效股票

if __name__ == "__main__":
    main()