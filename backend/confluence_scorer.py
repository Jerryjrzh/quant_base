#!/usr/bin/env python3
"""
【V4.0 - 智能自适应融合评分系统】
基于Grok和Gemini的深度分析建议，实现以下核心优化：
1. 市场阶段识别与自适应权重调整
2. 趋势导向的KDJ/RSI评分（替代固定阈值）
3. 历史形态对齐检测与个股特征学习
4. 多时间框架融合分析
"""

import pandas as pd
import numpy as np
import yaml
import os
from typing import Dict, Optional, Tuple, List
from scipy.signal import find_peaks
from scipy.stats import pearsonr
import logging

logger = logging.getLogger(__name__)

class ConfluenceScorer:
    """
    【V4.0 - 智能自适应融合评分器】
    核心创新：
    1. 市场阶段自动识别（积累期/上升期/分配期/下跌期）
    2. 趋势导向评分：KDJ/RSI基于斜率而非固定阈值
    3. 历史形态对齐：检测价格底部与指标底部的同步性
    4. 个股特征学习：基于历史数据优化评分参数
    """
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            config_path = os.path.join(base_dir, 'config', 'confluence_scorer_config.yaml')
        
        self.config_path = config_path
        self._load_config()
        
        # V4.0 新增：市场阶段枚举
        self.MARKET_PHASES = {
            'ACCUMULATION': 'accumulation',    # 积累期
            'MARKUP': 'markup',               # 上升期  
            'DISTRIBUTION': 'distribution',    # 分配期
            'DECLINE': 'decline'              # 下跌期
        }

    # ... ( _load_config and _use_default_config remain the same) ...
    def _load_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.weights = config.get('weights', {})
            self.thresholds = config.get('thresholds', {})
            self.scoring = config.get('scoring', {})
            self.stateful_checks = config.get('stateful_checks', {})
            self.bonus_scores = config.get('bonus_scores', {})
            self.phase_weights = config.get('phase_weights', {})  # 修复：确保phase_weights总是被设置
            logger.info(f"✅ V4.0融合评分器配置加载成功: {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"⚠️ 配置文件不存在，使用V4.0默认配置: {self.config_path}")
            self._use_default_config()
        except Exception as e:
            logger.error(f"⚠️ 加载配置文件失败，使用V4.0默认配置: {e}")
            self._use_default_config()
    
    def _use_default_config(self):
        """使用V4.0默认配置"""
        # 基础权重（将根据市场阶段动态调整）
        self.weights = {'price_position': 40, 'macd_state': 30, 'kdj_state': 20, 'rsi_state': 10}
        
        # V4.0 新增：阶段特定权重
        self.phase_weights = {
            'accumulation': {'price_position': 45, 'macd_state': 25, 'kdj_state': 20, 'rsi_state': 10},
            'markup': {'price_position': 20, 'macd_state': 40, 'kdj_state': 25, 'rsi_state': 15},
            'distribution': {'price_position': 30, 'macd_state': 35, 'kdj_state': 20, 'rsi_state': 15},
            'decline': {'price_position': 50, 'macd_state': 20, 'kdj_state': 20, 'rsi_state': 10}
        }
        
        self.thresholds = {
            'price_position_tiers': { 'tier1': 0.4, 'tier2': 0.6, 'tier3': 0.8 },
            'price_position_scores': { 'tier1': 40, 'tier2': 30, 'tier3': 15 },
            'price_ratio_filter': 0.85, 'macd_zero_threshold': 0.1, 'kdj_low_threshold': 50,
            'kdj_oversold': 20, 'rsi_bullish_low': 50, 'rsi_bullish_high': 75, 'rsi_oversold': 30,
            # V4.0 新增：趋势检测参数
            'trend_slope_days': 5, 'min_slope_threshold': 0.1, 'alignment_tolerance_days': 3
        }
        
        self.scoring = {'min_confluence_score': 70, 'max_possible_score': 130} # 增加历史对齐奖励
        self.stateful_checks = {'lookback_days': 10, 'macd_consolidation_ratio': 0.6, 'kdj_oversold_min_days': 2}
        
        # V4.0 增强奖励分系统
        self.bonus_scores = {
            'macd_consolidation': 5, 'kdj_oversold_period': 5, 'long_term_trend': 5,
            'kdj_trend_bonus': 3, 'rsi_trend_bonus': 2, 'historical_alignment': 10  # 新增
        }

    def detect_market_phase(self, df: pd.DataFrame, index: int) -> Dict[str, any]:
        """
        【V4.1 增强】市场阶段识别
        集成波动率分析和成交量确认，提供更准确的阶段判断
        """
        try:
            current = df.iloc[index]
            current_price = current['close']
            
            # 获取均线数据
            ma50 = current.get('ma50', current_price)
            ma200 = current.get('ma200', current_price) 
            ma90 = current.get('ma90', current_price)
            ma150 = current.get('ma150', current_price)
            
            # 计算ATR（平均真实波动率）用于波动率调整
            atr_window = min(14, index)
            if atr_window >= 5:
                recent_data = df.iloc[max(0, index-atr_window):index+1]
                high_low = recent_data['high'] - recent_data['low']
                high_close = abs(recent_data['high'] - recent_data['close'].shift(1))
                low_close = abs(recent_data['low'] - recent_data['close'].shift(1))
                true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = true_range.mean()
            else:
                atr = current_price * 0.02  # 默认2%波动率
            
            # 计算52周价格位置
            window_size = min(240, len(df))
            if window_size < 30:
                return {'phase': self.MARKET_PHASES['ACCUMULATION'], 'confidence': 0.5, 'atr': atr}
                
            end_pos = index + 1
            start_pos = max(0, end_pos - window_size)
            window_data = df.iloc[start_pos:end_pos]
            
            price_high = window_data['high'].max()
            price_low = window_data['low'].min()
            price_position = (current_price - price_low) / (price_high - price_low) if price_high > price_low else 0.5
            
            # 获取技术指标
            rsi = current.get('rsi6', 50)
            macd = current.get('macd', 0)
            diff = current.get('diff', 0)
            dea = current.get('dea', 0)
            
            # 成交量分析（如果有数据）
            volume_trend = 1.0  # 默认中性
            if 'volume' in current and index >= 10:
                recent_volume = df.iloc[index-9:index+1]['volume'].mean()
                long_volume = df.iloc[max(0, index-29):index-9]['volume'].mean()
                if long_volume > 0:
                    volume_trend = recent_volume / long_volume
            
            # 增强的阶段判断逻辑
            confidence = 0.0
            phase_scores = {
                'accumulation': 0,
                'markup': 0, 
                'distribution': 0,
                'decline': 0
            }
            
            # 积累期特征
            if price_position < 0.4:
                phase_scores['accumulation'] += 30
            if current_price < ma200 and ma90 < ma150:
                phase_scores['accumulation'] += 25
            if rsi < 50 and volume_trend < 0.8:  # 低RSI + 成交量萎缩
                phase_scores['accumulation'] += 20
            
            # 上升期特征
            if current_price > ma50 and ma50 > ma200:
                phase_scores['markup'] += 30
            if diff > dea and macd > 0:
                phase_scores['markup'] += 25
            if price_position > 0.3 and volume_trend > 1.2:  # 突破 + 放量
                phase_scores['markup'] += 20
            
            # 分配期特征
            if price_position > 0.7:
                phase_scores['distribution'] += 25
            if rsi > 70:
                phase_scores['distribution'] += 20
            if diff < dea and price_position > 0.8:  # 高位背离
                phase_scores['distribution'] += 30
            
            # 下跌期特征
            if current_price < ma50 and ma50 < ma200:
                phase_scores['decline'] += 30
            if diff < dea and macd < 0:
                phase_scores['decline'] += 25
            if price_position > 0.4 and price_position < 0.7 and rsi < 40:
                phase_scores['decline'] += 20
            
            # 确定最终阶段
            best_phase = max(phase_scores.items(), key=lambda x: x[1])
            confidence = min(best_phase[1] / 75.0, 1.0)  # 最高75分，转换为置信度
            
            return {
                'phase': best_phase[0],
                'confidence': confidence,
                'atr': atr,
                'price_position': price_position,
                'volume_trend': volume_trend,
                'phase_scores': phase_scores
            }
                
        except Exception as e:
            logger.warning(f"市场阶段识别失败: {e}")
            return {
                'phase': self.MARKET_PHASES['ACCUMULATION'], 
                'confidence': 0.5, 
                'atr': current_price * 0.02,
                'error': str(e)
            }

    def filter_by_price_position(self, df: pd.DataFrame, index: int) -> Tuple[bool, str]:
        """
        【V3.2 - 已增强】价格位置过滤器
        集成了MA长周期趋势判断和52周高点位置判断
        """
        try:
            # --- [新增逻辑 - MA长周期趋势判断] ---
            current_ma90 = df.iloc[index].get('ma90')
            current_ma150 = df.iloc[index].get('ma150')

            # 确保均线数据有效
            if pd.notna(current_ma90) and pd.notna(current_ma150):
                if current_ma90 >= current_ma150:
                    return False, f"长周期趋势偏高 (MA90 {current_ma90:.2f} >= MA150 {current_ma150:.2f})"
            else:
                # 如果缺少长周期均线数据，可以发出警告但暂时通过
                logger.warning(f"{df.iloc[index].name} 缺少MA90或MA150数据，跳过趋势过滤")

            # --- [现有逻辑 - 52周高点位置判断] ---
            window_size = min(240, len(df))
            if window_size < 30: return True, "数据不足，跳过过滤"
            
            end_pos = index + 1; start_pos = max(0, end_pos - window_size)
            window_data = df.iloc[start_pos:end_pos]
            current_price = df.iloc[index]['close']; rolling_high = window_data['high'].max()
            
            if rolling_high <= 0: return True, "价格数据异常"
            
            price_ratio = current_price / rolling_high
            price_filter_threshold = self.thresholds.get('price_ratio_filter', 0.8)
            
            if price_ratio > price_filter_threshold:
                return False, f"价格位于52周高点的{price_ratio:.1%}，过高（阈值{price_filter_threshold:.1%}）"
            
            return True, f"长周期趋势向好且价格位于52周高点的{price_ratio:.1%}"
            
        except Exception as e:
            logger.warning(f"价格位置过滤失败: {e}"); return True, "过滤器异常，允许通过"

    def calculate_dynamic_thresholds(self, df: pd.DataFrame, index: int, atr: float) -> Dict[str, float]:
        """
        【V4.1 新增】动态阈值计算
        基于ATR和市场阶段调整技术指标阈值
        """
        try:
            base_thresholds = self.thresholds.copy()
            
            # ATR标准化因子（相对于价格的波动率）
            current_price = df.iloc[index]['close']
            atr_ratio = atr / current_price if current_price > 0 else 0.02
            
            # 动态调整RSI阈值
            volatility_factor = min(max(atr_ratio / 0.02, 0.5), 2.0)  # 限制在0.5-2.0倍
            
            dynamic_thresholds = {
                'rsi_oversold': max(20, base_thresholds.get('rsi_oversold', 30) - atr_ratio * 100),
                'rsi_bullish_low': max(40, base_thresholds.get('rsi_bullish_low', 50) - atr_ratio * 50),
                'rsi_bullish_high': min(85, base_thresholds.get('rsi_bullish_high', 75) + atr_ratio * 50),
                'kdj_oversold': max(15, base_thresholds.get('kdj_oversold', 20) - atr_ratio * 100),
                'kdj_low_threshold': max(40, base_thresholds.get('kdj_low_threshold', 50) - atr_ratio * 50),
                'min_slope_threshold': base_thresholds.get('min_slope_threshold', 0.1) * volatility_factor
            }
            
            return dynamic_thresholds
            
        except Exception as e:
            logger.warning(f"动态阈值计算失败: {e}")
            return self.thresholds.copy()

    def detect_historical_alignment(self, df: pd.DataFrame, index: int) -> Dict[str, any]:
        """
        【V4.0 新增】历史形态对齐检测
        分析价格底部与技术指标底部的历史同步性
        """
        try:
            # 设置分析窗口（60-120天）
            lookback_window = min(120, index)
            if lookback_window < 30:
                return {'alignment_score': 0, 'sync_quality': 'insufficient_data'}
            
            start_pos = max(0, index - lookback_window)
            window_data = df.iloc[start_pos:index+1]
            
            # 寻找价格底部（使用反向峰值检测）
            price_series = window_data['close'].values
            price_bottoms, _ = find_peaks(-price_series, distance=5, prominence=0.02)
            
            # 寻找KDJ底部
            k_series = window_data.get('k', pd.Series([50]*len(window_data))).values
            kdj_bottoms, _ = find_peaks(-k_series, distance=3, prominence=2)
            
            # 寻找RSI底部  
            rsi_series = window_data.get('rsi6', pd.Series([50]*len(window_data))).values
            rsi_bottoms, _ = find_peaks(-rsi_series, distance=3, prominence=3)
            
            alignment_score = 0
            tolerance = self.thresholds.get('alignment_tolerance_days', 3)
            
            # 检查最近的底部对齐情况
            if len(price_bottoms) > 0:
                latest_price_bottom = price_bottoms[-1]
                
                # KDJ对齐检查
                kdj_aligned = any(abs(kb - latest_price_bottom) <= tolerance for kb in kdj_bottoms)
                if kdj_aligned:
                    alignment_score += 5
                
                # RSI对齐检查  
                rsi_aligned = any(abs(rb - latest_price_bottom) <= tolerance for rb in rsi_bottoms)
                if rsi_aligned:
                    alignment_score += 5
                
                # 三重对齐奖励
                if kdj_aligned and rsi_aligned:
                    alignment_score += 5  # 额外奖励
            
            sync_quality = 'excellent' if alignment_score >= 10 else 'good' if alignment_score >= 5 else 'poor'
            
            return {
                'alignment_score': alignment_score,
                'sync_quality': sync_quality,
                'price_bottoms_count': len(price_bottoms),
                'kdj_bottoms_count': len(kdj_bottoms),
                'rsi_bottoms_count': len(rsi_bottoms)
            }
            
        except Exception as e:
            logger.warning(f"历史对齐检测失败: {e}")
            return {'alignment_score': 0, 'sync_quality': 'error'}

    def backtest_alignments(self, df: pd.DataFrame, index: int) -> Dict[str, any]:
        """
        【V4.1 新增】历史对齐回测验证
        模拟基于对齐信号的历史入场，计算胜率和收益统计
        """
        try:
            # 设置回测窗口（至少需要60天数据）
            min_history = 60
            if index < min_history:
                return {'win_rate': 0.5, 'avg_return': 0, 'signal_count': 0, 'confidence_multiplier': 1.0}
            
            # 回测参数
            lookback_window = min(120, index - 20)  # 保留最后20天作为未来验证
            entry_signals = []
            
            # 扫描历史对齐信号
            for i in range(min_history, index - 20):
                alignment_result = self.detect_historical_alignment(df, i)
                
                # 如果对齐评分足够高，记录为入场信号
                if alignment_result['alignment_score'] >= 5:
                    entry_price = df.iloc[i]['close']
                    
                    # 计算未来5天和10天的收益
                    future_5d = df.iloc[min(i+5, len(df)-1)]['close']
                    future_10d = df.iloc[min(i+10, len(df)-1)]['close']
                    
                    return_5d = (future_5d - entry_price) / entry_price
                    return_10d = (future_10d - entry_price) / entry_price
                    
                    entry_signals.append({
                        'entry_index': i,
                        'entry_price': entry_price,
                        'alignment_score': alignment_result['alignment_score'],
                        'return_5d': return_5d,
                        'return_10d': return_10d,
                        'win_5d': return_5d > 0,
                        'win_10d': return_10d > 0
                    })
            
            if not entry_signals:
                return {'win_rate': 0.5, 'avg_return': 0, 'signal_count': 0, 'confidence_multiplier': 1.0}
            
            # 计算统计指标
            win_rate_5d = sum(s['win_5d'] for s in entry_signals) / len(entry_signals)
            win_rate_10d = sum(s['win_10d'] for s in entry_signals) / len(entry_signals)
            avg_return_5d = np.mean([s['return_5d'] for s in entry_signals])
            avg_return_10d = np.mean([s['return_10d'] for s in entry_signals])
            
            # 综合胜率（5天权重0.6，10天权重0.4）
            combined_win_rate = win_rate_5d * 0.6 + win_rate_10d * 0.4
            combined_avg_return = avg_return_5d * 0.6 + avg_return_10d * 0.4
            
            # 计算置信度乘数（基于历史表现）
            if combined_win_rate >= 0.7 and combined_avg_return > 0.02:
                confidence_multiplier = 1.3  # 历史表现优秀
            elif combined_win_rate >= 0.6 and combined_avg_return > 0:
                confidence_multiplier = 1.1  # 历史表现良好
            elif combined_win_rate < 0.4 or combined_avg_return < -0.02:
                confidence_multiplier = 0.8  # 历史表现较差
            else:
                confidence_multiplier = 1.0  # 历史表现一般
            
            return {
                'win_rate': combined_win_rate,
                'win_rate_5d': win_rate_5d,
                'win_rate_10d': win_rate_10d,
                'avg_return': combined_avg_return,
                'avg_return_5d': avg_return_5d,
                'avg_return_10d': avg_return_10d,
                'signal_count': len(entry_signals),
                'confidence_multiplier': confidence_multiplier,
                'recent_signals': entry_signals[-5:] if len(entry_signals) >= 5 else entry_signals
            }
            
        except Exception as e:
            logger.warning(f"历史对齐回测失败: {e}")
            return {'win_rate': 0.5, 'avg_return': 0, 'signal_count': 0, 'confidence_multiplier': 1.0}

    def calculate_confluence_score(self, df: pd.DataFrame, index: int) -> Dict:
        """
        【V4.1 - 增强自适应】计算综合融合评分
        核心升级：
        1. 增强市场阶段识别（集成波动率和成交量）
        2. 动态阈值调整（基于ATR）
        3. 历史回测验证（胜率置信度调整）
        4. 多维度评分透明度提升
        """
        try:
            # V4.1 增强：市场阶段识别（返回详细信息）
            phase_result = self.detect_market_phase(df, index)
            market_phase = phase_result['phase']
            phase_confidence = phase_result['confidence']
            atr = phase_result['atr']
            
            # V4.1 新增：动态阈值计算
            dynamic_thresholds = self.calculate_dynamic_thresholds(df, index, atr)
            original_thresholds = self.thresholds.copy()
            self.thresholds.update(dynamic_thresholds)  # 临时使用动态阈值
            
            # 根据市场阶段调整权重
            phase_weights = self.phase_weights.get(market_phase, self.weights)
            original_weights = self.weights.copy()
            self.weights = phase_weights  # 临时切换权重
            
            # 计算各项评分（使用阶段特定权重和动态阈值）
            price_score = self.calculate_price_position_score(df, index)
            macd_score = self.calculate_macd_state_score(df, index)
            kdj_score = self.calculate_kdj_state_score(df, index)
            rsi_score = self.calculate_rsi_state_score(df, index)
            
            # 恢复原始配置
            self.weights = original_weights
            self.thresholds = original_thresholds
            
            # 历史状态检查
            stateful_conditions = self.check_stateful_conditions(df, index)
            
            # 历史形态对齐检测
            alignment_result = self.detect_historical_alignment(df, index)
            
            # V4.1 新增：历史回测验证
            backtest_result = self.backtest_alignments(df, index)
            
            base_score = price_score + macd_score + kdj_score + rsi_score
            
            # 奖励分计算
            bonus_score = 0
            if stateful_conditions['macd_consolidation']: 
                bonus_score += self.bonus_scores.get('macd_consolidation', 5)
            if stateful_conditions['kdj_oversold_period']: 
                bonus_score += self.bonus_scores.get('kdj_oversold_period', 5)

            # 长周期趋势奖励
            current_ma90 = df.iloc[index].get('ma90')
            current_ma150 = df.iloc[index].get('ma150')
            if pd.notna(current_ma90) and pd.notna(current_ma150) and current_ma90 < current_ma150:
                bonus_score += self.bonus_scores.get('long_term_trend', 5)
            
            # 历史对齐奖励（基于回测结果调整）
            alignment_bonus = alignment_result['alignment_score']
            if backtest_result['confidence_multiplier'] != 1.0:
                alignment_bonus *= backtest_result['confidence_multiplier']
            bonus_score += alignment_bonus
            
            total_score = base_score + bonus_score
            
            # V4.1 增强：置信度计算（集成阶段置信度和回测置信度）
            max_possible_score = self.scoring.get('max_possible_score', 130)
            base_confidence = min(total_score / max_possible_score, 1.0)
            
            # 综合置信度：基础置信度 × 阶段置信度 × 回测置信度
            combined_confidence = base_confidence * phase_confidence * min(backtest_result['confidence_multiplier'], 1.2)
            combined_confidence = min(combined_confidence, 1.0)
            
            min_score_threshold = self.scoring.get('min_confluence_score', 70)
            
            return {
                'total_score': total_score, 
                'confidence': combined_confidence,
                'base_confidence': base_confidence,
                'market_phase': market_phase,
                'phase_confidence': phase_confidence,
                'breakdown': {
                    'price_position': price_score, 
                    'macd_state': macd_score, 
                    'kdj_state': kdj_score, 
                    'rsi_state': rsi_score, 
                    'bonus_score': bonus_score,
                    'alignment_bonus': alignment_bonus
                },
                'stateful_conditions': stateful_conditions, 
                'alignment_analysis': alignment_result,
                'backtest_analysis': backtest_result,  # V4.1 新增
                'phase_analysis': phase_result,        # V4.1 新增
                'dynamic_thresholds': dynamic_thresholds,  # V4.1 新增
                'phase_weights_used': phase_weights,
                'is_high_quality': total_score >= min_score_threshold and combined_confidence >= 0.6
            }
        except Exception as e:
            logger.error(f"计算融合评分失败: {e}")
            return {
                'total_score': 0, 'confidence': 0, 'market_phase': 'unknown',
                'breakdown': {}, 'stateful_conditions': {}, 'alignment_analysis': {},
                'backtest_analysis': {}, 'phase_analysis': {},
                'is_high_quality': False, 'error': str(e)
            }

    # ... (The rest of the functions: calculate_price_position_score, calculate_macd_state_score, etc. remain unchanged from V3.1) ...
    def calculate_price_position_score(self, df: pd.DataFrame, index: int) -> float:
        """【V3】计算价格位置评分 (分层模式)"""
        try:
            window_size = min(90, len(df)); end_pos = index + 1; start_pos = max(0, end_pos - window_size)
            if window_size < 30: return 0
            
            window_data = df.iloc[start_pos:end_pos]
            current_price = df.iloc[index]['close']
            min_price = window_data['low'].min(); max_price = window_data['high'].max()
            if max_price <= min_price: return 0
            
            price_position = (current_price - min_price) / (max_price - min_price)
            
            tiers = self.thresholds.get('price_position_tiers', {'tier1': 0.4, 'tier2': 0.6, 'tier3': 0.8})
            scores = self.thresholds.get('price_position_scores', {'tier1': 40, 'tier2': 30, 'tier3': 15})

            if price_position <= tiers['tier1']: return scores['tier1']
            if price_position <= tiers['tier2']: return scores['tier2']
            if price_position <= tiers['tier3']: return scores['tier3']
            return 0
        except Exception as e:
            logger.warning(f"计算价格位置评分失败: {e}"); return 0
    
    def calculate_macd_state_score(self, df: pd.DataFrame, index: int) -> float:
        """
        【V2 - 已恢复】计算MACD状态评分
        此版本逻辑能更好地奖励持续的健康状态。
        """
        try:
            if index < 1:
                return 0
            
            current = df.iloc[index]
            prev = df.iloc[index-1]
            
            score = 0
            
            # 条件1: 处于金叉状态 (最重要)
            if current.get('diff', 0) > current.get('dea', 0):
                score += self.weights['macd_state'] * 0.5  # 基础分
                
                # 条件2: MACD柱状线为正 (加分)
                if current.get('macd', 0) > 0:
                    score += self.weights['macd_state'] * 0.3
                    
                # 条件3: 柱状线刚刚翻红 (额外奖励)
                if prev.get('macd', 0) <= 0:
                    score += self.weights['macd_state'] * 0.2
            
            # 条件4: 靠近零轴 (额外奖励)
            if abs(current.get('macd', 0)) <= self.thresholds.get('macd_zero_threshold', 0.1):
                score += self.weights['macd_state'] * 0.1
            
            return min(score, self.weights['macd_state'])
            
        except Exception as e:
            logger.warning(f"计算MACD状态评分失败: {e}")
            return 0

    def calculate_kdj_state_score(self, df: pd.DataFrame, index: int) -> float:
        """
        【V4.0 - 趋势导向】计算KDJ状态评分
        核心改进：基于斜率趋势而非固定阈值判断
        """
        try:
            if index < 1: 
                return 0
                
            current_k = df.iloc[index].get('k', 50)
            current_d = df.iloc[index].get('d', 50)
            prev_k = df.iloc[index-1].get('k', 50)
            
            score = 0
            
            # V4.0 新增：KDJ趋势斜率分析
            trend_days = self.thresholds.get('trend_slope_days', 5)
            if index >= trend_days:
                # 计算K线斜率（过去5天）
                k_values = df.iloc[index-trend_days+1:index+1]['k'].values
                if len(k_values) == trend_days:
                    k_slope = np.polyfit(range(trend_days), k_values, 1)[0]
                    min_slope = self.thresholds.get('min_slope_threshold', 0.1)
                    
                    # 趋势奖励：正斜率获得奖励
                    if k_slope > min_slope:
                        score += self.weights['kdj_state'] * 0.4
                        # 额外趋势奖励
                        score += self.bonus_scores.get('kdj_trend_bonus', 3)
                    elif k_slope > 0:  # 轻微上升也给予基础分
                        score += self.weights['kdj_state'] * 0.2
            
            # 传统逻辑保留（作为补充）
            if current_k > current_d:
                score += self.weights['kdj_state'] * 0.3
                
            # 低位反弹奖励（使用动态阈值）
            kdj_low_threshold = self.thresholds.get('kdj_low_threshold', 50)
            if current_k < kdj_low_threshold and current_k > prev_k:
                score += self.weights['kdj_state'] * 0.2
                
            # 脱离超卖奖励（使用动态阈值）
            kdj_oversold = self.thresholds.get('kdj_oversold', 20)
            if current_k > kdj_oversold and prev_k <= kdj_oversold:
                score += self.weights['kdj_state'] * 0.3
            
            return min(score, self.weights['kdj_state'] + self.bonus_scores.get('kdj_trend_bonus', 3))
            
        except Exception as e:
            logger.warning(f"计算KDJ状态评分失败: {e}")
            return 0
    
    def calculate_rsi_state_score(self, df: pd.DataFrame, index: int) -> float:
        """
        【V4.0 - 趋势导向】计算RSI状态评分
        核心改进：基于RSI斜率和动量而非固定区间判断
        """
        try:
            if index < 1: 
                return 0
                
            current_rsi = df.iloc[index].get('rsi6', 50)
            prev_rsi = df.iloc[index-1].get('rsi6', 50)
            
            score = 0
            
            # V4.0 新增：RSI趋势斜率分析
            trend_days = self.thresholds.get('trend_slope_days', 5)
            if index >= trend_days:
                # 计算RSI斜率（过去5天）
                rsi_values = df.iloc[index-trend_days+1:index+1]['rsi6'].fillna(50).values
                if len(rsi_values) == trend_days:
                    rsi_slope = np.polyfit(range(trend_days), rsi_values, 1)[0]
                    min_slope = self.thresholds.get('min_slope_threshold', 0.1)
                    
                    # 趋势奖励：正斜率获得奖励
                    if rsi_slope > min_slope:
                        score += self.weights['rsi_state'] * 0.5
                        # 额外趋势奖励
                        score += self.bonus_scores.get('rsi_trend_bonus', 2)
                    elif rsi_slope > 0:  # 轻微上升
                        score += self.weights['rsi_state'] * 0.3
            
            # 动态区间评分（替代固定50-75区间）
            rsi_bullish_low = self.thresholds.get('rsi_bullish_low', 50)
            rsi_bullish_high = self.thresholds.get('rsi_bullish_high', 75)
            
            # 健康区间奖励（但更注重趋势）
            if rsi_bullish_low <= current_rsi <= rsi_bullish_high:
                score += self.weights['rsi_state'] * 0.4
                # 区间内上升额外奖励
                if current_rsi > prev_rsi:
                    score += self.weights['rsi_state'] * 0.2
            
            # 超卖反弹奖励（使用动态阈值）
            rsi_oversold = self.thresholds.get('rsi_oversold', 30)
            if prev_rsi <= rsi_oversold and current_rsi > rsi_oversold:
                score += self.weights['rsi_state'] * 0.4
            
            # V4.0 新增：RSI动量检测
            if index >= 2:
                rsi_2days_ago = df.iloc[index-2].get('rsi6', 50)
                # 连续上升奖励
                if current_rsi > prev_rsi > rsi_2days_ago:
                    score += self.weights['rsi_state'] * 0.1
            
            return min(score, self.weights['rsi_state'] + self.bonus_scores.get('rsi_trend_bonus', 2))
            
        except Exception as e:
            logger.warning(f"计算RSI状态评分失败: {e}")
            return 0

    def check_stateful_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        try:
            lookback_days = min(self.stateful_checks.get('lookback_days', 10), index)
            if lookback_days < 5: return {'macd_consolidation': False, 'kdj_oversold_period': False}
            start_pos = index - lookback_days
            window_data = df.iloc[start_pos:index]
            macd_values = window_data.get('macd', pd.Series())
            consolidation_ratio = self.stateful_checks.get('macd_consolidation_ratio', 0.6)
            macd_consolidation = (macd_values <= 0).sum() >= lookback_days * consolidation_ratio
            k_values = window_data.get('k', pd.Series())
            min_oversold_days = self.stateful_checks.get('kdj_oversold_min_days', 2)
            kdj_oversold_period = (k_values <= 30).sum() >= min_oversold_days
            return {'macd_consolidation': macd_consolidation, 'kdj_oversold_period': kdj_oversold_period}
        except Exception as e:
            logger.warning(f"检查状态历史条件失败: {e}"); return {'macd_consolidation': False, 'kdj_oversold_period': False}

# 全局实例
confluence_scorer = ConfluenceScorer()