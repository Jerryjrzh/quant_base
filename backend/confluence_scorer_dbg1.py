#!/usr/bin/env python3
"""
【V2 - 已优化】多指标融合评分系统
基于screener_tester_gemini.md和screener_tester_grok.md的分析实施
实现"价格不高"和"指标一致性"的量化评分
根据 test_fix_4.md 和 test_fix_5.md 优化建议进行改进
"""

import pandas as pd
import numpy as np
import yaml
import os
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class ConfluenceScorer:
    """
    【V2 - 已优化】多指标融合评分器
    根据技术分析文档中识别的共性特征，对股票信号进行质量评分
    根据 test_fix_4.md 和 test_fix_5.md 优化建议进行改进，支持配置文件
    
    V2 优化重点：
    - MACD评分更侧重于奖励持续的健康状态
    - RSI评分奖励处于看涨区间的状态，而不是严格要求每日递增
    """
    
    def __init__(self, config_path: str = None):
        """
        初始化融合评分器
        
        Args:
            config_path: 配置文件路径，默认为 config/confluence_scorer_config.yaml
        """
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            config_path = os.path.join(base_dir, 'config', 'confluence_scorer_config.yaml')
        
        self.config_path = config_path
        self._load_config()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.weights = config.get('weights', {})
            self.thresholds = config.get('thresholds', {})
            self.scoring = config.get('scoring', {})
            self.stateful_checks = config.get('stateful_checks', {})
            self.bonus_scores = config.get('bonus_scores', {})
            
            logger.info(f"✅ 融合评分器配置加载成功: {self.config_path}")
            
        except FileNotFoundError:
            logger.warning(f"⚠️ 配置文件不存在，使用默认配置: {self.config_path}")
            self._use_default_config()
        except Exception as e:
            logger.error(f"⚠️ 加载配置文件失败，使用默认配置: {e}")
            self._use_default_config()
    
    def _use_default_config(self):
        """使用默认配置"""
        self.weights = {
            'price_position': 40,      # 价格位置权重（高）
            'macd_state': 30,          # MACD状态权重（高）
            'kdj_state': 20,           # KDJ状态权重（中）
            'rsi_state': 10            # RSI状态权重（低）
        }
        
        self.thresholds = {
            'price_position_low': 0.4,     # 价格在90日区间底部40%
            'price_position_high': 0.7,    # 价格在90日区间顶部30%
            'price_ratio_filter': 0.8,     # 52周高点过滤阈值
            'macd_zero_threshold': 0.1,    # MACD零轴附近阈值
            'kdj_low_threshold': 50,       # KDJ低位阈值
            'kdj_oversold': 20,            # KDJ超卖阈值
            'rsi_bullish_low': 50,         # RSI看涨区间下限
            'rsi_bullish_high': 75,        # RSI看涨区间上限
            'rsi_oversold': 30             # RSI超卖阈值
        }
        
        self.scoring = {
            'min_confluence_score': 70,
            'max_possible_score': 110
        }
        
        self.stateful_checks = {
            'lookback_days': 10,
            'macd_consolidation_ratio': 0.6,
            'kdj_oversold_min_days': 2
        }
        
        self.bonus_scores = {
            'macd_consolidation': 5,
            'kdj_oversold_period': 5
        }
    
    def calculate_price_position_score(self, df: pd.DataFrame, index: int) -> float:
        """
        计算价格位置评分
        基于"价格不高"原则，价格越低位评分越高
        """
        try:
            # 计算90日价格区间
            window_size = min(90, len(df))
            if window_size < 30:
                return 0
            
            end_pos = index + 1
            start_pos = max(0, end_pos - window_size)
            window_data = df.iloc[start_pos:end_pos]
            
            current_price = df.iloc[index]['close']
            min_price = window_data['low'].min()
            max_price = window_data['high'].max()
            
            if max_price <= min_price:
                return 0
            
            # 计算价格在区间中的位置（0-1）
            price_position = (current_price - min_price) / (max_price - min_price)
            
            # 评分逻辑：底部40%得满分，顶部30%得0分
            if price_position <= self.thresholds['price_position_low']:
                score = self.weights['price_position']
            elif price_position >= self.thresholds['price_position_high']:
                score = 0
            else:
                # 线性递减
                score = self.weights['price_position'] * (
                    1 - (price_position - self.thresholds['price_position_low']) / 
                    (self.thresholds['price_position_high'] - self.thresholds['price_position_low'])
                )
            
            return score
            
        except Exception as e:
            logger.warning(f"计算价格位置评分失败: {e}")
            return 0
    
    def calculate_macd_state_score(self, df: pd.DataFrame, index: int) -> float:
        """
        【V2 - 已优化】计算MACD状态评分
        更侧重于奖励持续的健康状态，而不仅仅是单日的事件。
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
        【已优化】计算KDJ状态评分
        基于"KDJ低位金叉"和"向上趋势"特征
        """
        try:
            if index < 1:
                return 0

            current_k = df.iloc[index].get('k', 50)
            current_d = df.iloc[index].get('d', 50)
            prev_k = df.iloc[index-1].get('k', 50)  # 获取前一天K值
            
            score = 0
            
            # 检查趋势方向 (新增) - 必须是向上趋势才给分
            is_trending_up = current_k > prev_k
            if not is_trending_up:
                return 0  # 如果KDJ向下，直接给0分，这是一票否决
            
            # 检查K线上穿D线（金叉）
            if current_k > current_d:
                score += self.weights['kdj_state'] * 0.5
            
            # 检查是否在低位（50以下）
            if current_k < self.thresholds['kdj_low_threshold']:
                score += self.weights['kdj_state'] * 0.3
            
            # 检查是否从超卖区域反弹
            if current_k > self.thresholds['kdj_oversold']:
                score += self.weights['kdj_state'] * 0.2
            
            return min(score, self.weights['kdj_state'])
            
        except Exception as e:
            logger.warning(f"计算KDJ状态评分失败: {e}")
            return 0
    
    def calculate_rsi_state_score(self, df: pd.DataFrame, index: int) -> float:
        """
        【V2 - 已优化】计算RSI状态评分
        奖励处于健康看涨区间的状态，而不是严格要求每日递增。
        """
        try:
            if index < 1:
                return 0
            
            current_rsi = df.iloc[index].get('rsi6', 50)
            prev_rsi = df.iloc[index-1].get('rsi6', 50)
            
            score = 0
            
            # 条件1: RSI处于看涨区间 (50-75)
            rsi_bullish_low = self.thresholds.get('rsi_bullish_low', 50)
            rsi_bullish_high = self.thresholds.get('rsi_bullish_high', 75)
            
            if rsi_bullish_low <= current_rsi <= rsi_bullish_high:
                score += self.weights['rsi_state'] * 0.7  # 主要分数
                
                # 条件2: RSI趋势向上 (额外奖励)
                if current_rsi > prev_rsi:
                    score += self.weights['rsi_state'] * 0.3
            
            # 条件3: 从超卖区反弹 (特殊奖励)
            rsi_oversold = self.thresholds.get('rsi_oversold', 30)
            if prev_rsi <= rsi_oversold and current_rsi > rsi_oversold:
                score += self.weights['rsi_state'] * 0.5
            
            return min(score, self.weights['rsi_state'])
            
        except Exception as e:
            logger.warning(f"计算RSI状态评分失败: {e}")
            return 0
    
    def check_stateful_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        """
        检查状态历史条件
        确保信号来自真正的反转而非噪音
        """
        try:
            lookback_days = min(self.stateful_checks.get('lookback_days', 10), index)
            if lookback_days < 5:
                return {'macd_consolidation': False, 'kdj_oversold_period': False}
            
            start_pos = index - lookback_days
            window_data = df.iloc[start_pos:index]
            
            # 检查MACD是否有足够的负值期（表明之前的整理）
            macd_values = window_data.get('macd', pd.Series())
            consolidation_ratio = self.stateful_checks.get('macd_consolidation_ratio', 0.6)
            macd_consolidation = (macd_values <= 0).sum() >= lookback_days * consolidation_ratio
            
            # 检查KDJ是否有超卖期
            k_values = window_data.get('k', pd.Series())
            min_oversold_days = self.stateful_checks.get('kdj_oversold_min_days', 2)
            kdj_oversold_period = (k_values <= 30).sum() >= min_oversold_days
            
            return {
                'macd_consolidation': macd_consolidation,
                'kdj_oversold_period': kdj_oversold_period
            }
            
        except Exception as e:
            logger.warning(f"检查状态历史条件失败: {e}")
            return {'macd_consolidation': False, 'kdj_oversold_period': False}
    
    def calculate_confluence_score(self, df: pd.DataFrame, index: int) -> Dict:
        """
        计算综合融合评分
        返回详细的评分结果
        """
        try:
            # 基础指标评分
            price_score = self.calculate_price_position_score(df, index)
            macd_score = self.calculate_macd_state_score(df, index)
            kdj_score = self.calculate_kdj_state_score(df, index)
            rsi_score = self.calculate_rsi_state_score(df, index)
            
            # 状态历史检查
            stateful_conditions = self.check_stateful_conditions(df, index)
            
            # 计算基础总分
            base_score = price_score + macd_score + kdj_score + rsi_score
            
            # 状态历史加分
            bonus_score = 0
            if stateful_conditions['macd_consolidation']:
                bonus_score += self.bonus_scores.get('macd_consolidation', 5)
            if stateful_conditions['kdj_oversold_period']:
                bonus_score += self.bonus_scores.get('kdj_oversold_period', 5)
            
            total_score = base_score + bonus_score
            
            # 计算置信度（0-1）
            max_possible_score = self.scoring.get('max_possible_score', 110)
            confidence = min(total_score / max_possible_score, 1.0)
            
            # 高质量信号阈值（可配置）
            min_score_threshold = self.scoring.get('min_confluence_score', 70)
            
            return {
                'total_score': total_score,
                'confidence': confidence,
                'breakdown': {
                    'price_position': price_score,
                    'macd_state': macd_score,
                    'kdj_state': kdj_score,
                    'rsi_state': rsi_score,
                    'bonus_score': bonus_score
                },
                'stateful_conditions': stateful_conditions,
                'is_high_quality': total_score >= min_score_threshold
            }
            
        except Exception as e:
            logger.error(f"计算融合评分失败: {e}")
            return {
                'total_score': 0,
                'confidence': 0,
                'breakdown': {},
                'stateful_conditions': {},
                'is_high_quality': False,
                'error': str(e)
            }
    
    def filter_by_price_position(self, df: pd.DataFrame, index: int) -> Tuple[bool, str]:
        """
        价格位置过滤器
        快速过滤掉价格过高的股票
        """
        try:
            window_size = min(252, len(df))  # 使用52周数据
            if window_size < 30:
                return True, "数据不足，跳过过滤"
            
            end_pos = index + 1
            start_pos = max(0, end_pos - window_size)
            window_data = df.iloc[start_pos:end_pos]
            
            current_price = df.iloc[index]['close']
            rolling_high = window_data['high'].max()
            
            if rolling_high <= 0:
                return True, "价格数据异常"
            
            price_ratio = current_price / rolling_high
            
            # 如果价格在52周高点的阈值以上，过滤掉（可配置）
            price_filter_threshold = self.thresholds.get('price_ratio_filter', 0.8)
            if price_ratio > price_filter_threshold:
                return False, f"价格位于52周高点的{price_ratio:.1%}，过高（阈值{price_filter_threshold:.1%}）"
            
            return True, f"价格位于52周高点的{price_ratio:.1%}，合适"
            
        except Exception as e:
            logger.warning(f"价格位置过滤失败: {e}")
            return True, "过滤器异常，允许通过"

# 全局实例
confluence_scorer = ConfluenceScorer()