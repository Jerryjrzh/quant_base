#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
价值反转策略（最终优化版）
基于MACD底背离的精准反转策略
迁移自 screener1f.py - 经过验证的最终版本
"""

import pandas as pd
import numpy as np
import talib
from typing import Dict, Any, Tuple, Optional
import logging

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class ValueReversalFinalStrategy(BaseStrategy):
    """价值反转策略（最终优化版）"""
    
    def get_strategy_name(self) -> str:
        return "价值反转策略（最终版）"
    
    def get_strategy_version(self) -> str:
        return "1.0"
    
    def get_strategy_description(self) -> str:
        return """
        价值反转策略（最终优化版）- 基于MACD底背离的精准反转策略
        
        核心逻辑：寻找"MACD底背离"这一核心形态，并由"RSI反弹"或"均线突破"来确认。
        
        - 信号A (核心): MACD底背离 - 价格在近期低位，但MACD指标形成更高低点
        - 信号B (确认): RSI超卖反弹 - RSI从40以下的低位区回升  
        - 信号C (确认): 动量点火 - 价格放量突破20日均线
        
        触发条件：(信号A 且 (信号B 或 信号C)) 或 (信号B 且 信号C)
        
        特点：
        1. 精准的MACD底背离检测
        2. 严格的背离确认机制
        3. 双重确认逻辑，避免假背离
        4. 适用于精准抄底场景
        """
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            "macd": {
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9
            },
            "rsi": {
                "period": 14,
                "oversold_threshold": 40  # RSI超卖阈值
            },
            "ma": {
                "period": 20  # 均线周期
            },
            "volume": {
                "ma_period": 20,
                "surge_threshold": 1.5  # 成交量放大阈值
            },
            "divergence": {
                "lookback_period": 60,  # 背离检测回看周期
                "min_days_from_trough": 2,  # 最低点距今最少天数
                "price_tolerance": 1.15,  # 价格容忍度
                "macd_recovery_ratio": 0.5  # MACD恢复比例（水下时）
            }
        }
    
    def validate_config(self) -> bool:
        """验证配置参数"""
        try:
            required_keys = ['macd', 'rsi', 'ma', 'volume', 'divergence']
            for key in required_keys:
                if key not in self.config:
                    logger.error(f"配置缺少必要参数: {key}")
                    return False
            
            # 验证数值范围
            if self.config['rsi']['oversold_threshold'] <= 0 or self.config['rsi']['oversold_threshold'] >= 100:
                logger.error("RSI超卖阈值必须在0-100之间")
                return False
            
            if self.config['volume']['surge_threshold'] <= 1.0:
                logger.error("成交量放大阈值必须大于1.0")
                return False
            
            return True
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
    
    def get_required_data_length(self) -> int:
        """获取所需的最小数据长度"""
        return max(
            self.config['divergence']['lookback_period'],
            self.config['ma']['period'],
            self.config['volume']['ma_period'],
            self.config['rsi']['period']
        ) + 10  # 额外缓冲
    
    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        try:
            # 移动平均线
            df[f'ma{self.config["ma"]["period"]}'] = talib.MA(
                df['close'], 
                timeperiod=self.config['ma']['period']
            )
            
            # 成交量移动平均
            df[f'volume_ma{self.config["volume"]["ma_period"]}'] = df['volume'].rolling(
                window=self.config['volume']['ma_period']
            ).mean()
            
            # MACD指标
            macd, signal, hist = talib.MACD(
                df['close'],
                fastperiod=self.config['macd']['fast_period'],
                slowperiod=self.config['macd']['slow_period'],
                signalperiod=self.config['macd']['signal_period']
            )
            df['macd'] = macd
            df['macd_signal'] = signal
            df['macd_hist'] = hist
            
            # RSI指标
            df['rsi'] = talib.RSI(
                df['close'], 
                timeperiod=self.config['rsi']['period']
            )
            
            return df
            
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
            return df
    
    def detect_macd_divergence(self, df: pd.DataFrame, current_idx: int) -> bool:
        """检测MACD底背离"""
        try:
            lookback_period = self.config['divergence']['lookback_period']
            min_days_from_trough = self.config['divergence']['min_days_from_trough']
            price_tolerance = self.config['divergence']['price_tolerance']
            macd_recovery_ratio = self.config['divergence']['macd_recovery_ratio']
            
            # 获取回看期间的数据
            start_idx = max(0, current_idx - lookback_period + 1)
            recent_data = df.iloc[start_idx:current_idx + 1]
            
            if len(recent_data) < min_days_from_trough + 1:
                return False
            
            # 找到价格最低点
            price_trough_idx = recent_data['close'].idxmin()
            price_trough_pos = df.index.get_loc(price_trough_idx)
            
            # 确保最低点不是今天或昨天
            days_from_trough = current_idx - price_trough_pos
            if days_from_trough <= min_days_from_trough:
                return False
            
            # 获取关键数据
            current_data = df.iloc[current_idx]
            trough_data = df.loc[price_trough_idx]
            
            # 检查价格条件：当前价格仍接近前期低点
            if current_data['close'] >= trough_data['close'] * price_tolerance:
                return False
            
            # 检查MACD背离条件
            current_macd = current_data['macd']
            trough_macd = trough_data['macd']
            
            if pd.isna(current_macd) or pd.isna(trough_macd):
                return False
            
            # MACD必须高于最低点时的MACD
            if current_macd <= trough_macd:
                return False
            
            # 如果MACD在水下，要求更大的反弹幅度
            if trough_macd < 0:
                required_recovery = trough_macd * macd_recovery_ratio
                if current_macd <= required_recovery:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"MACD背离检测失败: {e}")
            return False
    
    def check_rsi_reversal(self, df: pd.DataFrame, current_idx: int) -> bool:
        """检查RSI超卖区反弹"""
        try:
            if current_idx < 1:
                return False
            
            oversold_threshold = self.config['rsi']['oversold_threshold']
            
            current_rsi = df.iloc[current_idx]['rsi']
            prev_rsi = df.iloc[current_idx - 1]['rsi']
            
            if pd.isna(current_rsi) or pd.isna(prev_rsi):
                return False
            
            # RSI从超卖区反弹
            return prev_rsi < oversold_threshold and current_rsi > prev_rsi
            
        except Exception as e:
            logger.error(f"RSI反弹检测失败: {e}")
            return False
    
    def check_volume_breakout(self, df: pd.DataFrame, current_idx: int) -> bool:
        """检查放量突破MA20"""
        try:
            if current_idx < 1:
                return False
            
            ma_period = self.config['ma']['period']
            surge_threshold = self.config['volume']['surge_threshold']
            volume_ma_period = self.config['volume']['ma_period']
            
            current_data = df.iloc[current_idx]
            prev_data = df.iloc[current_idx - 1]
            
            ma_col = f'ma{ma_period}'
            volume_ma_col = f'volume_ma{volume_ma_period}'
            
            if ma_col not in df.columns or volume_ma_col not in df.columns:
                return False
            
            # 检查价格突破：昨日在均线下方，今日在均线上方
            price_breakout = (
                prev_data['close'] < prev_data[ma_col] and
                current_data['close'] > current_data[ma_col]
            )
            
            # 检查成交量放大
            volume_surge = current_data['volume'] > current_data[volume_ma_col] * surge_threshold
            
            return price_breakout and volume_surge
            
        except Exception as e:
            logger.error(f"放量突破检测失败: {e}")
            return False
    
    def apply_strategy(self, df: pd.DataFrame) -> Tuple[Optional[pd.Series], Optional[Dict[str, Any]]]:
        """应用策略"""
        try:
            # 数据预处理
            df = self.preprocess_data(df)
            
            # 计算技术指标
            df = self.calculate_technical_indicators(df)
            
            # 检查数据完整性
            if len(df) < self.get_required_data_length():
                return None, None
            
            # 初始化信号序列
            signals = pd.Series('', index=df.index)
            
            # 只检查最后一个交易日
            current_idx = len(df) - 1
            
            # 检查数据完整性
            if (pd.isna(df.iloc[current_idx]).any() or 
                pd.isna(df.iloc[current_idx - 1]).any()):
                return None, None
            
            # 检测三个信号
            signal_A = self.detect_macd_divergence(df, current_idx)  # MACD底背离
            signal_B = self.check_rsi_reversal(df, current_idx)      # RSI反弹
            signal_C = self.check_volume_breakout(df, current_idx)   # 放量突破
            
            # 信号决策逻辑
            signal_triggered = False
            signal_strength = 0
            trigger_reasons = []
            
            # 规则1: 出现底背离，并且有任一动量信号确认
            if signal_A and (signal_B or signal_C):
                signal_triggered = True
                signal_strength = 3 if (signal_B and signal_C) else 2
                trigger_reasons.append("MACD底背离确认")
                if signal_B:
                    trigger_reasons.append("RSI反弹确认")
                if signal_C:
                    trigger_reasons.append("放量突破确认")
            
            # 规则2: 没有明显背离，但RSI和MA突破信号同时出现，形成强力反转
            elif signal_B and signal_C:
                signal_triggered = True
                signal_strength = 2
                trigger_reasons.extend(["RSI反弹", "放量突破"])
            
            if signal_triggered:
                if signal_strength >= 3:
                    signals.iloc[current_idx] = 'STRONG_BUY'
                elif signal_strength >= 2:
                    signals.iloc[current_idx] = 'BUY'
                else:
                    signals.iloc[current_idx] = 'POTENTIAL_BUY'
                
                # 构建信号详情
                signal_details = {
                    'signal_strength': signal_strength,
                    'stage_passed': signal_strength,
                    'trigger_reasons': trigger_reasons,
                    'signals': {
                        'macd_divergence': signal_A,
                        'rsi_reversal': signal_B,
                        'volume_breakout': signal_C
                    },
                    'technical_data': {
                        'current_price': float(df.iloc[current_idx]['close']),
                        'current_rsi': float(df.iloc[current_idx]['rsi']),
                        'current_macd': float(df.iloc[current_idx]['macd']),
                        'volume_ratio': float(df.iloc[current_idx]['volume'] / df.iloc[current_idx][f'volume_ma{self.config["volume"]["ma_period"]}'])
                    }
                }
                
                # 转换numpy类型
                signal_details = self.convert_numpy_types(signal_details)
                
                return signals, signal_details
            
            return None, None
            
        except Exception as e:
            logger.error(f"策略应用失败: {e}")
            return None, None