#!/usr/bin/env python3
"""
技术形态识别器
基于screener_test_gmini_review.md的建议实施
实现从"信号猎取"到"形态识别"的转变
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from confluence_scorer import confluence_scorer

logger = logging.getLogger(__name__)

class PatternRecognizer:
    """
    技术形态识别器
    专门识别"整理突破"和"底部反转"等经典形态
    """
    
    def __init__(self):
        self.min_consolidation_days = 10  # 最小整理天数
        self.max_consolidation_days = 60  # 最大整理天数
        self.consolidation_range_threshold = 0.15  # 整理区间阈值（15%）
        self.breakout_volume_multiplier = 1.2  # 突破成交量倍数
    
    def detect_consolidation_period(self, df: pd.DataFrame, end_index: int) -> Optional[Dict]:
        """
        检测整理期
        识别价格在一定区间内横盘整理的时期
        """
        try:
            if end_index < self.min_consolidation_days:
                return None
            
            # 向前查找整理期
            for lookback_days in range(self.min_consolidation_days, 
                                     min(self.max_consolidation_days, end_index)):
                start_pos = end_index - lookback_days
                consolidation_data = df.iloc[start_pos:end_index]
                
                if len(consolidation_data) < self.min_consolidation_days:
                    continue
                
                # 计算整理区间
                high_price = consolidation_data['high'].max()
                low_price = consolidation_data['low'].min()
                
                if high_price <= low_price:
                    continue
                
                # 检查价格波动是否在合理范围内
                price_range = (high_price - low_price) / low_price
                if price_range <= self.consolidation_range_threshold:
                    # 检查是否大部分时间在此区间内
                    in_range_count = 0
                    for _, row in consolidation_data.iterrows():
                        if low_price <= row['close'] <= high_price:
                            in_range_count += 1
                    
                    in_range_ratio = in_range_count / len(consolidation_data)
                    if in_range_ratio >= 0.8:  # 80%的时间在区间内
                        return {
                            'start_date': consolidation_data.index[0],
                            'end_date': consolidation_data.index[-1],
                            'duration_days': lookback_days,
                            'high_price': high_price,
                            'low_price': low_price,
                            'price_range_pct': price_range,
                            'in_range_ratio': in_range_ratio
                        }
            
            return None
            
        except Exception as e:
            logger.warning(f"检测整理期失败: {e}")
            return None
    
    def detect_ma_compression(self, df: pd.DataFrame, index: int) -> Dict:
        """
        检测均线收敛
        识别短中期均线聚集的情况
        """
        try:
            if index < 30:
                return {'is_compressed': False, 'compression_ratio': 0}
            
            # 获取多条均线
            ma_columns = ['ma7', 'ma13', 'ma30']
            current_mas = []
            
            for ma_col in ma_columns:
                if ma_col in df.columns:
                    ma_value = df.iloc[index].get(ma_col)
                    if pd.notna(ma_value):
                        current_mas.append(ma_value)
            
            if len(current_mas) < 3:
                return {'is_compressed': False, 'compression_ratio': 0}
            
            # 计算均线间的最大差异
            max_ma = max(current_mas)
            min_ma = min(current_mas)
            
            if min_ma <= 0:
                return {'is_compressed': False, 'compression_ratio': 0}
            
            compression_ratio = (max_ma - min_ma) / min_ma
            is_compressed = compression_ratio <= 0.05  # 5%以内认为收敛
            
            return {
                'is_compressed': is_compressed,
                'compression_ratio': compression_ratio,
                'ma_values': current_mas
            }
            
        except Exception as e:
            logger.warning(f"检测均线收敛失败: {e}")
            return {'is_compressed': False, 'compression_ratio': 0}
    
    def detect_volume_breakout(self, df: pd.DataFrame, index: int, 
                             consolidation_info: Dict) -> Dict:
        """
        检测成交量突破
        确认突破的有效性
        """
        try:
            if index < 5:
                return {'is_volume_breakout': False, 'volume_ratio': 0}
            
            # 计算近期平均成交量
            recent_volume = df.iloc[max(0, index-5):index]['volume'].mean()
            current_volume = df.iloc[index]['volume']
            
            if recent_volume <= 0:
                return {'is_volume_breakout': False, 'volume_ratio': 0}
            
            volume_ratio = current_volume / recent_volume
            is_volume_breakout = volume_ratio >= self.breakout_volume_multiplier
            
            return {
                'is_volume_breakout': is_volume_breakout,
                'volume_ratio': volume_ratio,
                'current_volume': current_volume,
                'avg_volume': recent_volume
            }
            
        except Exception as e:
            logger.warning(f"检测成交量突破失败: {e}")
            return {'is_volume_breakout': False, 'volume_ratio': 0}
    
    def is_consolidation_breakout(self, df: pd.DataFrame, index: int) -> Dict:
        """
        识别整理突破形态
        这是核心的形态识别函数
        """
        try:
            # 1. 价格位置快速过滤
            price_filter_result, price_reason = confluence_scorer.filter_by_price_position(df, index)
            if not price_filter_result:
                return {
                    'pattern_detected': False,
                    'pattern_type': 'consolidation_breakout',
                    'reason': price_reason,
                    'confidence': 0
                }
            
            # 2. 检测整理期
            consolidation_info = self.detect_consolidation_period(df, index)
            if not consolidation_info:
                return {
                    'pattern_detected': False,
                    'pattern_type': 'consolidation_breakout',
                    'reason': '未发现有效整理期',
                    'confidence': 0
                }
            
            # 3. 检测均线收敛
            ma_compression = self.detect_ma_compression(df, index)
            
            # 4. 检测价格突破
            current_price = df.iloc[index]['close']
            breakout_threshold = consolidation_info['high_price']
            is_price_breakout = current_price > breakout_threshold
            
            # 5. 检测成交量确认
            volume_info = self.detect_volume_breakout(df, index, consolidation_info)
            
            # 6. 计算多指标融合评分
            confluence_result = confluence_scorer.calculate_confluence_score(df, index)
            
            # 7. 综合判断
            pattern_score = 0
            reasons = []
            
            # 整理期评分（30分）
            if consolidation_info['duration_days'] >= 15:
                pattern_score += 30
                reasons.append(f"发现{consolidation_info['duration_days']}天整理期")
            else:
                pattern_score += 15
                reasons.append(f"发现{consolidation_info['duration_days']}天短期整理")
            
            # 价格突破评分（25分）
            if is_price_breakout:
                pattern_score += 25
                reasons.append("价格突破整理区间上沿")
            
            # 均线收敛评分（15分）
            if ma_compression['is_compressed']:
                pattern_score += 15
                reasons.append("均线收敛，趋势不明")
            
            # 成交量确认评分（10分）
            if volume_info['is_volume_breakout']:
                pattern_score += 10
                reasons.append(f"成交量放大{volume_info['volume_ratio']:.1f}倍")
            
            # 多指标融合评分（20分）
            pattern_score += confluence_result['total_score'] * 0.2
            
            # 最终判断
            is_pattern_detected = (pattern_score >= 70 and 
                                 confluence_result['is_high_quality'] and
                                 is_price_breakout)
            
            return {
                'pattern_detected': is_pattern_detected,
                'pattern_type': 'consolidation_breakout',
                'pattern_score': pattern_score,
                'confidence': min(pattern_score / 100, 1.0),
                'reasons': reasons,
                'consolidation_info': consolidation_info,
                'ma_compression': ma_compression,
                'volume_info': volume_info,
                'confluence_result': confluence_result,
                'price_breakout': is_price_breakout
            }
            
        except Exception as e:
            logger.error(f"识别整理突破形态失败: {e}")
            return {
                'pattern_detected': False,
                'pattern_type': 'consolidation_breakout',
                'reason': f'识别失败: {str(e)}',
                'confidence': 0
            }
    
    def is_bottom_reversal(self, df: pd.DataFrame, index: int) -> Dict:
        """
        识别底部反转形态
        """
        try:
            # 1. 价格位置过滤
            price_filter_result, price_reason = confluence_scorer.filter_by_price_position(df, index)
            if not price_filter_result:
                return {
                    'pattern_detected': False,
                    'pattern_type': 'bottom_reversal',
                    'reason': price_reason,
                    'confidence': 0
                }
            
            # 2. 检查是否在相对低位
            confluence_result = confluence_scorer.calculate_confluence_score(df, index)
            price_position_score = confluence_result['breakdown'].get('price_position', 0)
            
            if price_position_score < 20:  # 价格位置评分太低
                return {
                    'pattern_detected': False,
                    'pattern_type': 'bottom_reversal',
                    'reason': '价格位置不够低',
                    'confidence': 0
                }
            
            # 3. 检查技术指标反转信号
            macd_score = confluence_result['breakdown'].get('macd_state', 0)
            kdj_score = confluence_result['breakdown'].get('kdj_state', 0)
            
            # 4. 检查K线形态（简化版）
            if index >= 2:
                current_candle = df.iloc[index]
                prev_candle = df.iloc[index-1]
                
                # 检查是否有反弹K线
                is_bullish_candle = current_candle['close'] > current_candle['open']
                has_momentum = current_candle['close'] > prev_candle['close']
            else:
                is_bullish_candle = False
                has_momentum = False
            
            # 5. 综合评分
            pattern_score = 0
            reasons = []
            
            # 价格位置（40分）
            pattern_score += price_position_score
            if price_position_score >= 30:
                reasons.append("价格处于相对低位")
            
            # MACD反转（30分）
            pattern_score += macd_score
            if macd_score >= 15:
                reasons.append("MACD显示反转信号")
            
            # KDJ反转（20分）
            pattern_score += kdj_score
            if kdj_score >= 10:
                reasons.append("KDJ显示反转信号")
            
            # K线形态（10分）
            if is_bullish_candle and has_momentum:
                pattern_score += 10
                reasons.append("出现反弹K线")
            
            # 最终判断
            is_pattern_detected = (pattern_score >= 60 and 
                                 confluence_result['is_high_quality'])
            
            return {
                'pattern_detected': is_pattern_detected,
                'pattern_type': 'bottom_reversal',
                'pattern_score': pattern_score,
                'confidence': min(pattern_score / 100, 1.0),
                'reasons': reasons,
                'confluence_result': confluence_result,
                'candle_analysis': {
                    'is_bullish_candle': is_bullish_candle,
                    'has_momentum': has_momentum
                }
            }
            
        except Exception as e:
            logger.error(f"识别底部反转形态失败: {e}")
            return {
                'pattern_detected': False,
                'pattern_type': 'bottom_reversal',
                'reason': f'识别失败: {str(e)}',
                'confidence': 0
            }
    
    def recognize_pattern(self, df: pd.DataFrame, index: int, 
                         pattern_types: List[str] = None) -> Dict:
        """
        通用形态识别接口
        """
        if pattern_types is None:
            pattern_types = ['consolidation_breakout', 'bottom_reversal']
        
        results = {}
        best_pattern = None
        best_confidence = 0
        
        for pattern_type in pattern_types:
            if pattern_type == 'consolidation_breakout':
                result = self.is_consolidation_breakout(df, index)
            elif pattern_type == 'bottom_reversal':
                result = self.is_bottom_reversal(df, index)
            else:
                continue
            
            results[pattern_type] = result
            
            if result['pattern_detected'] and result['confidence'] > best_confidence:
                best_pattern = pattern_type
                best_confidence = result['confidence']
        
        return {
            'best_pattern': best_pattern,
            'best_confidence': best_confidence,
            'all_results': results,
            'has_pattern': best_pattern is not None
        }

# 全局实例
pattern_recognizer = PatternRecognizer()