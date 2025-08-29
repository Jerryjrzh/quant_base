#!/usr/bin/env python3
"""
【V4.1 - 市场阶段自适应】技术形态识别器
根据Grok的深度分析建议（scorer_grok_review.md）进行优化：
1. 集成市场阶段识别，应用动态阈值
2. 移除冗余的"双重"质量检查
3. 调整评分逻辑，使其更适应不同市场环境
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from confluence_scorer import confluence_scorer

logger = logging.getLogger(__name__)

class PatternRecognizer:
    """
    【V4.1】技术形态识别器
    核心优化：根据市场阶段（积累/上升/分配/下跌）自适应调整识别逻辑
    """
    
    def __init__(self):
        self.min_consolidation_days = 10
        self.max_consolidation_days = 60
        self.consolidation_range_threshold = 0.15
        self.breakout_volume_multiplier = 1.2
    
    # ... (detect_consolidation_period, detect_ma_compression, detect_volume_breakout remain the same) ...
    def detect_consolidation_period(self, df: pd.DataFrame, end_index: int) -> Optional[Dict]:
        try:
            if end_index < self.min_consolidation_days: return None
            for lookback_days in range(self.min_consolidation_days, min(self.max_consolidation_days, end_index)):
                start_pos = end_index - lookback_days
                consolidation_data = df.iloc[start_pos:end_index]
                if len(consolidation_data) < self.min_consolidation_days: continue
                high_price = consolidation_data['high'].max()
                low_price = consolidation_data['low'].min()
                if high_price <= low_price: continue
                price_range = (high_price - low_price) / low_price
                if price_range <= self.consolidation_range_threshold:
                    in_range_count = ((consolidation_data['close'] >= low_price) & (consolidation_data['close'] <= high_price)).sum()
                    in_range_ratio = in_range_count / len(consolidation_data)
                    if in_range_ratio >= 0.8:
                        return {'start_date': consolidation_data.index[0], 'end_date': consolidation_data.index[-1], 'duration_days': lookback_days, 'high_price': high_price, 'low_price': low_price, 'price_range_pct': price_range, 'in_range_ratio': in_range_ratio}
            return None
        except Exception as e:
            logger.warning(f"检测整理期失败: {e}"); return None
    
    def detect_ma_compression(self, df: pd.DataFrame, index: int) -> Dict:
        try:
            if index < 30: return {'is_compressed': False, 'compression_ratio': 0}
            ma_columns = ['ma7', 'ma13', 'ma30']
            current_mas = [df.iloc[index].get(ma_col) for ma_col in ma_columns if pd.notna(df.iloc[index].get(ma_col))]
            if len(current_mas) < 3: return {'is_compressed': False, 'compression_ratio': 0}
            max_ma = max(current_mas); min_ma = min(current_mas)
            if min_ma <= 0: return {'is_compressed': False, 'compression_ratio': 0}
            compression_ratio = (max_ma - min_ma) / min_ma
            return {'is_compressed': compression_ratio <= 0.05, 'compression_ratio': compression_ratio, 'ma_values': current_mas}
        except Exception as e:
            logger.warning(f"检测均线收敛失败: {e}"); return {'is_compressed': False, 'compression_ratio': 0}
    
    def detect_volume_breakout(self, df: pd.DataFrame, index: int) -> Dict:
        try:
            if index < 5 or 'volume' not in df.columns: return {'is_volume_breakout': False, 'volume_ratio': 0}
            recent_volume = df.iloc[max(0, index-5):index]['volume'].mean()
            current_volume = df.iloc[index]['volume']
            if recent_volume <= 0: return {'is_volume_breakout': False, 'volume_ratio': 0}
            volume_ratio = current_volume / recent_volume
            return {'is_volume_breakout': volume_ratio >= self.breakout_volume_multiplier, 'volume_ratio': volume_ratio, 'current_volume': current_volume, 'avg_volume': recent_volume}
        except Exception as e:
            logger.warning(f"检测成交量突破失败: {e}"); return {'is_volume_breakout': False, 'volume_ratio': 0}

    def is_consolidation_breakout(self, df: pd.DataFrame, index: int, phase: str, score_threshold: int) -> Dict:
        """
        【V4.1】识别整理突破形态 (使用动态阈值)
        """
        try:
            consolidation_info = self.detect_consolidation_period(df, index)
            if not consolidation_info:
                return {'pattern_detected': False, 'reason': '未发现有效整理期'}

            ma_compression = self.detect_ma_compression(df, index)
            current_price = df.iloc[index]['close']
            is_price_breakout = current_price > consolidation_info['high_price']
            volume_info = self.detect_volume_breakout(df, index)
            confluence_result = confluence_scorer.calculate_confluence_score(df, index)
            
            pattern_score = 0; reasons = []
            
            # 评分逻辑
            pattern_score += 30 if consolidation_info['duration_days'] >= 15 else 15
            reasons.append(f"发现{consolidation_info['duration_days']}天整理期")
            if is_price_breakout: pattern_score += 25; reasons.append("价格突破整理区间上沿")
            if ma_compression['is_compressed']: pattern_score += 15; reasons.append("均线收敛")
            if volume_info['is_volume_breakout']:
                # 在上升期，成交量突破更重要
                volume_weight = 1.5 if phase == 'markup' else 1.0
                pattern_score += 10 * volume_weight
                reasons.append(f"成交量放大{volume_info['volume_ratio']:.1f}倍")

            # 融合评分贡献
            pattern_score += confluence_result['total_score'] * 0.2
            
            # --- [核心修改] 使用动态阈值，移除冗余的 is_high_quality 检查 ---
            is_pattern_detected = (pattern_score >= score_threshold and is_price_breakout)
            
            return {
                'pattern_detected': is_pattern_detected, 'pattern_type': 'consolidation_breakout',
                'pattern_score': pattern_score, 'confidence': min(pattern_score / 100, 1.0), 'reasons': reasons
            }
        except Exception as e:
            logger.error(f"识别整理突破形态失败: {e}"); return {'pattern_detected': False, 'reason': f'识别失败: {str(e)}'}
    
    def is_bottom_reversal(self, df: pd.DataFrame, index: int, score_threshold: int) -> Dict:
        """
        【V4.1】识别底部反转形态 (使用动态阈值)
        """
        try:
            confluence_result = confluence_scorer.calculate_confluence_score(df, index)
            price_position_score = confluence_result['breakdown'].get('price_position', 0)
            
            if price_position_score < confluence_scorer.weights['price_position'] * 0.5: # 价格位置评分必须达到权重的一半
                return {'pattern_detected': False, 'reason': '价格位置不够低'}

            macd_score = confluence_result['breakdown'].get('macd_state', 0)
            kdj_score = confluence_result['breakdown'].get('kdj_state', 0)
            
            # 简化K线分析
            is_bullish_candle = False
            if index >= 1: is_bullish_candle = df.iloc[index]['close'] > df.iloc[index-1]['close']
            
            pattern_score = price_position_score + macd_score + kdj_score
            reasons = [f"价格位置得分{price_position_score:.1f}", f"MACD得分{macd_score:.1f}", f"KDJ得分{kdj_score:.1f}"]
            if is_bullish_candle: pattern_score += 10; reasons.append("出现反弹K线")
            
            # --- [核心修改] 使用动态阈值，移除冗余的 is_high_quality 检查 ---
            is_pattern_detected = (pattern_score >= score_threshold)
            
            return {
                'pattern_detected': is_pattern_detected, 'pattern_type': 'bottom_reversal',
                'pattern_score': pattern_score, 'confidence': min(pattern_score / 100, 1.0), 'reasons': reasons
            }
        except Exception as e:
            logger.error(f"识别底部反转形态失败: {e}"); return {'pattern_detected': False, 'reason': f'识别失败: {str(e)}'}

    def recognize_pattern(self, df: pd.DataFrame, index: int) -> Dict:
        """
        【V4.1 - 核心升级】通用形态识别接口 (市场阶段自适应)
        """
        results = {}
        best_pattern = None
        best_confidence = 0
        
        # --- [新增逻辑] 1. 首先获取当前的市场阶段 ---
        phase_result = confluence_scorer.detect_market_phase(df, index)
        phase = phase_result.get('phase', 'accumulation')
        
        # --- [新增逻辑] 2. 根据阶段设置不同的识别策略和阈值 ---
        if phase in ['accumulation', 'decline']:
            # 在积累期或下跌期，优先寻找底部反转，且阈值可以更宽松
            pattern_priority = ['bottom_reversal', 'consolidation_breakout']
            thresholds = {'bottom_reversal': 55, 'consolidation_breakout': 65}
        elif phase == 'markup':
            # 在上升期，优先寻找整理突破（回调后的机会）
            pattern_priority = ['consolidation_breakout', 'bottom_reversal']
            thresholds = {'bottom_reversal': 65, 'consolidation_breakout': 60}
        else: # distribution
            return {'has_pattern': False, 'best_pattern': None, 'reason': f'高风险阶段: {phase}'}

        # --- [修改后逻辑] 3. 按优先级和动态阈值进行识别 ---
        for pattern_type in pattern_priority:
            score_threshold = thresholds.get(pattern_type, 70)
            
            if pattern_type == 'consolidation_breakout':
                result = self.is_consolidation_breakout(df, index, phase, score_threshold)
            elif pattern_type == 'bottom_reversal':
                result = self.is_bottom_reversal(df, index, score_threshold)
            else:
                continue
            
            results[pattern_type] = result
            
            if result.get('pattern_detected') and result.get('confidence', 0) > best_confidence:
                best_pattern = pattern_type
                best_confidence = result['confidence']
        
        return {
            'best_pattern': best_pattern,
            'best_confidence': best_confidence,
            'market_phase': phase,
            'all_results': results,
            'has_pattern': best_pattern is not None
        }

# 全局实例
pattern_recognizer = PatternRecognizer()