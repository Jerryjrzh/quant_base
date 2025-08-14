#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深渊筑底策略
基于经过测试验证的深渊筑底理论实现
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional
import logging
import sys
import os

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, backend_dir)

# 添加strategies目录到路径
strategies_dir = os.path.dirname(__file__)
sys.path.insert(0, strategies_dir)

from base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class AbyssBottomingStrategy(BaseStrategy):
    """深渊筑底策略"""
    
    def get_strategy_name(self) -> str:
        return "深渊筑底策略"
    
    def get_strategy_version(self) -> str:
        return "2.0"
    
    def get_strategy_description(self) -> str:
        return "识别从深度下跌中恢复的股票，基于位置优于一切的理念，捕捉深跌筑底后的拉升机会"
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            # 深跌筑底参数
            'long_term_days': 400,
            'min_drop_percent': 0.40,
            'price_low_percentile': 0.35,
            
            # 成交量分析参数
            'volume_shrink_threshold': 0.70,
            'volume_consistency_threshold': 0.30,
            'volume_analysis_days': 30,
            
            # 横盘蓄势参数
            'hibernation_days': 40,
            'hibernation_volatility_max': 0.40,
            
            # 缩量挖坑参数
            'washout_days': 15,
            'washout_volume_shrink_ratio': 0.85,
            
            # 确认拉升参数
            'max_rise_from_bottom': 0.18,
            'liftoff_volume_increase_ratio': 1.15,
        }
    
    def validate_config(self) -> bool:
        """验证配置参数"""
        default_config = self.get_default_config()
        
        # 合并默认配置
        for key, value in default_config.items():
            if key not in self.config:
                self.config[key] = value
        
        # 验证关键参数
        required_params = [
            'long_term_days', 'min_drop_percent', 'price_low_percentile',
            'volume_shrink_threshold', 'volume_consistency_threshold'
        ]
        
        for param in required_params:
            if param not in self.config:
                raise ValueError(f"缺少必需参数: {param}")
        
        return True
    
    def get_required_data_length(self) -> int:
        return self.config.get('long_term_days', 400)
    
    def analyze_volume_shrinkage(self, df: pd.DataFrame) -> Tuple[bool, Dict[str, Any]]:
        """
        分析成交量萎缩情况 - 核心优化逻辑
        """
        try:
            if len(df) < 250:
                return False, {"error": "数据不足"}
            
            volumes = df['volume'].values
            
            # 1. 计算历史平均成交量（使用前半段数据作为基准）
            historical_volumes = volumes[:len(volumes)//2]
            historical_avg = np.mean(historical_volumes)
            
            # 2. 计算最近成交量
            recent_days = self.config['volume_analysis_days']
            recent_volumes = volumes[-recent_days:]
            recent_avg = np.mean(recent_volumes)
            
            # 3. 计算萎缩比例
            shrink_ratio = recent_avg / historical_avg if historical_avg > 0 else 1.0
            is_volume_shrunk = shrink_ratio <= self.config['volume_shrink_threshold']
            
            # 4. 检查地量的持续性
            threshold_volume = historical_avg * self.config['volume_shrink_threshold']
            low_volume_days = sum(1 for v in recent_volumes if v <= threshold_volume)
            consistency_ratio = low_volume_days / len(recent_volumes)
            is_consistent = consistency_ratio >= self.config['volume_consistency_threshold']
            
            # 5. 额外检查：最近成交量应该明显低于长期中位数
            long_term_median = np.percentile(volumes, 50)
            recent_vs_median = recent_avg / long_term_median if long_term_median > 0 else 1.0
            
            details = {
                'historical_avg': historical_avg,
                'recent_avg': recent_avg,
                'shrink_ratio': shrink_ratio,
                'consistency_ratio': consistency_ratio,
                'long_term_median': long_term_median,
                'recent_vs_median': recent_vs_median,
                'is_volume_shrunk': is_volume_shrunk,
                'is_consistent': is_consistent,
                'threshold_volume': threshold_volume
            }
            
            # 综合判断：成交量萎缩 且 有持续性
            volume_ok = is_volume_shrunk and is_consistent
            
            return volume_ok, details
            
        except Exception as e:
            logger.error(f"成交量分析失败: {e}")
            return False, {"error": str(e)}
    
    def check_deep_decline_phase(self, df: pd.DataFrame) -> Tuple[bool, Dict[str, Any]]:
        """
        第零阶段：深跌筑底检查
        """
        try:
            long_term_days = self.config['long_term_days']
            if len(df) < long_term_days:
                return False, {"error": "数据长度不足"}
            
            # 获取长期数据
            long_term_data = df.tail(long_term_days)
            long_term_high = long_term_data['high'].max()
            long_term_low = long_term_data['low'].min()
            current_price = df['close'].iloc[-1]
            
            # 1. 检查价格位置
            price_range = long_term_high - long_term_low
            if price_range == 0:
                return False, {"error": "价格无波动"}
            
            price_position = (current_price - long_term_low) / price_range
            price_position_ok = price_position <= self.config['price_low_percentile']
            
            # 2. 检查下跌幅度
            drop_percent = (long_term_high - current_price) / long_term_high
            drop_percent_ok = drop_percent >= self.config['min_drop_percent']
            
            # 3. 使用优化的成交量分析
            volume_ok, volume_details = self.analyze_volume_shrinkage(df)
            
            # 综合判断
            conditions = {
                'price_position_ok': price_position_ok,
                'drop_percent_ok': drop_percent_ok,
                'volume_ok': volume_ok
            }
            
            all_ok = all(conditions.values())
            
            details = {
                'drop_percent': drop_percent,
                'price_position': price_position,
                'long_term_high': long_term_high,
                'long_term_low': long_term_low,
                'current_price': current_price,
                'conditions': conditions,
                'volume_analysis': volume_details
            }
            
            return all_ok, details
            
        except Exception as e:
            logger.error(f"深跌筑底检查失败: {e}")
            return False, {"error": str(e)}
    
    def check_hibernation_phase(self, df: pd.DataFrame) -> Tuple[bool, Dict[str, Any]]:
        """第一阶段：横盘蓄势检查"""
        try:
            washout_days = self.config['washout_days']
            hibernation_days = self.config['hibernation_days']
            
            # 获取横盘期数据
            start_idx = -(washout_days + hibernation_days)
            end_idx = -washout_days if washout_days > 0 else len(df)
            hibernation_data = df.iloc[start_idx:end_idx]
            
            if hibernation_data.empty:
                return False, {"error": "横盘期数据为空"}
            
            # 计算横盘区间
            support_level = hibernation_data['low'].min()
            resistance_level = hibernation_data['high'].max()
            
            # 检查波动率
            volatility = (resistance_level - support_level) / support_level if support_level > 0 else float('inf')
            volatility_ok = volatility <= self.config['hibernation_volatility_max']
            
            # 检查均线收敛
            ma_convergence_ok = True
            if 'ma20' in hibernation_data.columns and 'ma30' in hibernation_data.columns:
                ma_values = hibernation_data[['ma20', 'ma30']].iloc[-1]
                ma_range = (ma_values.max() - ma_values.min()) / ma_values.mean()
                ma_convergence_ok = ma_range <= 0.05
            
            # 检查成交量稳定性
            avg_volume = hibernation_data['volume'].mean()
            volume_stability = hibernation_data['volume'].std() / avg_volume if avg_volume > 0 else float('inf')
            
            details = {
                'support_level': support_level,
                'resistance_level': resistance_level,
                'volatility': volatility,
                'volatility_ok': volatility_ok,
                'ma_convergence_ok': ma_convergence_ok,
                'avg_volume': avg_volume,
                'volume_stability': volume_stability
            }
            
            return volatility_ok and ma_convergence_ok, details
            
        except Exception as e:
            logger.error(f"横盘蓄势检查失败: {e}")
            return False, {"error": str(e)}
    
    def check_washout_phase(self, df: pd.DataFrame, hibernation_info: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """第二阶段：缩量挖坑检查"""
        try:
            washout_days = self.config['washout_days']
            washout_data = df.tail(washout_days)
            
            if washout_data.empty:
                return False, {"error": "挖坑期数据为空"}
            
            support_level = hibernation_info['support_level']
            hibernation_avg_volume = hibernation_info['avg_volume']
            
            # 检查是否跌破支撑
            washout_low = washout_data['low'].min()
            support_broken = washout_low < support_level * 0.95
            
            # 检查挖坑期的缩量特征
            pit_days = washout_data[washout_data['low'] < support_level]
            if pit_days.empty:
                return False, {"error": "无有效挖坑数据"}
            
            pit_avg_volume = pit_days['volume'].mean()
            volume_shrink_ratio = pit_avg_volume / hibernation_avg_volume if hibernation_avg_volume > 0 else float('inf')
            volume_shrink_ok = volume_shrink_ratio <= self.config['washout_volume_shrink_ratio']
            
            conditions = {
                'support_broken': support_broken,
                'volume_shrink_ok': volume_shrink_ok
            }
            
            all_ok = all(conditions.values())
            
            details = {
                'washout_low': washout_low,
                'support_break': (support_level - washout_low) / support_level if support_level > 0 else 0,
                'volume_shrink_ratio': volume_shrink_ratio,
                'pit_days_count': len(pit_days),
                'conditions': conditions
            }
            
            return all_ok, details
            
        except Exception as e:
            logger.error(f"缩量挖坑检查失败: {e}")
            return False, {"error": str(e)}
    
    def check_liftoff_confirmation(self, df: pd.DataFrame, washout_info: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """第三阶段：确认拉升检查"""
        try:
            washout_low = washout_info['washout_low']
            recent_data = df.tail(3)  # 最近3天
            
            if recent_data.empty:
                return False, {"error": "确认期数据不足"}
            
            latest = recent_data.iloc[-1]
            prev = recent_data.iloc[-2] if len(recent_data) > 1 else latest
            
            # 条件1：价格企稳回升
            is_price_recovering = (
                latest['close'] > latest['open'] and  # 当日阳线
                latest['close'] > prev['close'] and   # 价格上涨
                latest['low'] >= washout_low * 0.98   # 未创新低
            )
            
            # 条件2：尚未远离坑底
            rise_from_bottom = (latest['close'] - washout_low) / washout_low if washout_low > 0 else 0
            is_near_bottom = rise_from_bottom <= self.config['max_rise_from_bottom']
            
            # 条件3：成交量温和放大
            recent_volumes = df['volume'].tail(10).mean()
            volume_increase = latest['volume'] / recent_volumes if recent_volumes > 0 else 0
            is_volume_confirming = volume_increase >= self.config['liftoff_volume_increase_ratio']
            
            # 条件4：技术指标配合
            rsi_ok = 25 <= latest.get('rsi', 50) <= 60 if 'rsi' in latest else True
            macd_improving = latest.get('macd', 0) > prev.get('macd', 0) if 'macd' in latest else True
            
            conditions = {
                'price_recovering': is_price_recovering,
                'near_bottom': is_near_bottom,
                'volume_confirming': is_volume_confirming,
                'rsi_ok': rsi_ok,
                'macd_improving': macd_improving
            }
            
            conditions_met = sum(conditions.values())
            all_ok = conditions_met >= 3  # 至少满足3个条件
            
            details = {
                'rise_from_bottom': rise_from_bottom,
                'volume_increase': volume_increase,
                'conditions_met': conditions_met,
                'total_conditions': len(conditions),
                'conditions': conditions
            }
            
            return all_ok, details
            
        except Exception as e:
            logger.error(f"拉升确认检查失败: {e}")
            return False, {"error": str(e)}
    
    def apply_strategy(self, df: pd.DataFrame) -> Tuple[Optional[pd.Series], Optional[Dict[str, Any]]]:
        """
        应用深渊筑底策略
        """
        try:
            if len(df) < self.get_required_data_length():
                return None, None
            
            # 预处理数据和计算技术指标
            df = self.preprocess_data(df)
            df = self.calculate_technical_indicators(df)
            
            # 第零阶段：深跌筑底检查（必须通过）
            deep_decline_ok, deep_decline_info = self.check_deep_decline_phase(df)
            if not deep_decline_ok:
                return None, None
            
            # 第一阶段：横盘蓄势检查
            hibernation_ok, hibernation_info = self.check_hibernation_phase(df)
            if not hibernation_ok:
                # 如果横盘检查未通过，但深跌检查通过，仍可以作为潜在信号
                signal_series = pd.Series(index=df.index, dtype=object).fillna('')
                signal_series.iloc[-1] = 'POTENTIAL_BUY'
                
                signal_details = {
                    'signal_state': 'DEEP_DECLINE_ONLY',
                    'stage_passed': 1,
                    'deep_decline': deep_decline_info,
                    'hibernation': hibernation_info,
                    'strategy_version': self.version
                }
                
                return signal_series, self.convert_numpy_types(signal_details)
            
            # 第二阶段：缩量挖坑检查
            washout_ok, washout_info = self.check_washout_phase(df, hibernation_info)
            if not washout_ok:
                # 前两阶段通过，作为较强信号
                signal_series = pd.Series(index=df.index, dtype=object).fillna('')
                signal_series.iloc[-1] = 'BUY'
                
                signal_details = {
                    'signal_state': 'HIBERNATION_CONFIRMED',
                    'stage_passed': 2,
                    'deep_decline': deep_decline_info,
                    'hibernation': hibernation_info,
                    'washout': washout_info,
                    'strategy_version': self.version
                }
                
                return signal_series, self.convert_numpy_types(signal_details)
            
            # 第三阶段：确认拉升检查
            liftoff_ok, liftoff_info = self.check_liftoff_confirmation(df, washout_info)
            
            # 生成最终信号
            signal_series = pd.Series(index=df.index, dtype=object).fillna('')
            
            if liftoff_ok:
                signal_series.iloc[-1] = 'STRONG_BUY'
                signal_state = 'FULL_ABYSS_CONFIRMED'
                stage_passed = 4
            else:
                signal_series.iloc[-1] = 'BUY'
                signal_state = 'WASHOUT_CONFIRMED'
                stage_passed = 3
            
            # 整合所有阶段信息
            signal_details = {
                'signal_state': signal_state,
                'stage_passed': stage_passed,
                'deep_decline': deep_decline_info,
                'hibernation': hibernation_info,
                'washout': washout_info,
                'liftoff': liftoff_info,
                'strategy_version': self.version
            }
            
            return signal_series, self.convert_numpy_types(signal_details)
            
        except Exception as e:
            logger.error(f"深渊筑底策略执行失败: {e}")
            return None, None