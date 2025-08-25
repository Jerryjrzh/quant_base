#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
反转做多策略（优化版）
寻找下跌动能衰竭的反转信号
迁移自 screenergf.py - 经过验证的优化版本
"""

import pandas as pd
import numpy as np
import talib
from typing import Dict, Any, Tuple, Optional
import logging

from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class ReversedShortOptimizedStrategy(BaseStrategy):
    """反转做多策略（优化版）"""
    
    def get_strategy_name(self) -> str:
        return "反转做多策略（优化版）"
    
    def get_strategy_version(self) -> str:
        return "1.0"
    
    def get_strategy_description(self) -> str:
        return """
        反转做多策略（优化版）- 寻找下跌动能衰竭的反转信号
        
        核心逻辑：寻找满足以下条件中至少两个的股票，表明下跌动能衰竭，可能反转。
        
        1. 修正的MACD底背离：价格在近期低位，但MACD指标已明显回升
        2. 可靠的放量突破：价格上穿MA20，且成交量显著大于20日均量
        3. 放宽的RSI超卖启动：RSI从35以下的超卖/低位区回升
        
        特点：
        1. 宽松的触发条件 - 满足2个条件即可触发
        2. MACD改进算法 - 要求最低点发生在3天前，MACD反弹30%以上
        3. 放量突破确认 - 成交量必须是20日均量的1.5倍以上
        4. 适度的RSI阈值 - 从35以下反弹，适用于趋势反转捕捉
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
                "oversold_threshold": 35  # 更宽松的RSI阈值
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
                "min_days_from_trough": 3,  # 最低点距今最少天数（更宽松）
                "price_tolerance": 1.15,  # 价格容忍度
                "macd_recovery_ratio": 1.3  # MACD恢复比例（要求30%以上反弹）
            },
            "signal": {
                "min_conditions": 2  # 至少满足2个条件
            }
        }
    
    def validate_config(self) -> bool:
        """验证配置参数"""
        try:
            required_keys = ['macd', 'rsi', 'ma', 'volume', 'divergence', 'signal']
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
            
            if self.config['signal']['min_conditions'] < 1 or self.config['signal']['min_conditions'] > 3:
                logger.error("最少条件数必须在1-3之间")
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
    
    def check_macd_divergence(self, df: pd.DataFrame, current_idx: int) -> bool:
        """检查修正的MACD底背离"""
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
            
            # 确保最低点发生在指定天数前或更早
            days_from_trough = current_idx - price_trough_pos
            if days_from_trough <= min_days_from_trough:
                return False
            
            # 获取关键数据
            current_data = df.iloc[current_idx]
            trough_data = df.loc[price_trough_idx]
            
            # 检查价格条件：当前价格仍接近前期低点
            if current_data['close'] >= trough_data['close'] * price_tolerance:
                return False
            
            # 检查MACD背离条件：当前MACD高于最低点时的MACD 30%以上
            current_macd = current_data['macd']
            trough_macd = trough_data['macd']
            
            if pd.isna(current_macd) or pd.isna(trough_macd):
                return False
            
            # MACD必须反弹超过指定比例
            return current_macd > trough_macd * macd_recovery_ratio
            
        except Exception as e:
            logger.error(f"MACD背离检测失败: {e}")
            return False
    
    def check_rsi_reversal(self, df: pd.DataFrame, current_idx: int) -> bool:
        """检查RSI超卖区启动"""
        try:
            if current_idx < 1:
                return False
            
            oversold_threshold = self.config['rsi']['oversold_threshold']
            
            current_rsi = df.iloc[current_idx]['rsi']
            prev_rsi = df.iloc[current_idx - 1]['rsi']
            
            if pd.isna(current_rsi) or pd.isna(prev_rsi):
                return False
            
            # RSI从35以下的超卖区回升
            return prev_rsi < oversold_threshold and current_rsi > prev_rsi
            
        except Exception as e:
            logger.error(f"RSI反弹检测失败: {e}")
            return False
    
    def check_volume_breakout(self, df: pd.DataFrame, current_idx: int) -> bool:
        """检查可靠的放量突破MA20"""
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
            
            # 检查成交量显著放大
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
            
            # 检测三个条件
            condition_1 = self.check_macd_divergence(df, current_idx)   # 修正的MACD底背离
            condition_2 = self.check_rsi_reversal(df, current_idx)      # RSI超卖区启动
            condition_3 = self.check_volume_breakout(df, current_idx)   # 可靠的放量突破
            
            # 统计满足的条件数
            conditions_met = sum([condition_1, condition_2, condition_3])
            min_conditions = self.config['signal']['min_conditions']
            
            if conditions_met >= min_conditions:
                # 根据满足条件数确定信号强度
                if conditions_met >= 3:
                    signal_type = 'STRONG_BUY'
                    signal_strength = 3
                elif conditions_met >= 2:
                    signal_type = 'BUY'
                    signal_strength = 2
                else:
                    signal_type = 'POTENTIAL_BUY'
                    signal_strength = 1
                
                signals.iloc[current_idx] = signal_type
                
                # 构建触发原因
                trigger_reasons = []
                if condition_1:
                    trigger_reasons.append("MACD底背离")
                if condition_2:
                    trigger_reasons.append("RSI超卖启动")
                if condition_3:
                    trigger_reasons.append("放量突破MA20")
                
                # 构建信号详情
                signal_details = {
                    'signal_strength': signal_strength,
                    'stage_passed': signal_strength,
                    'conditions_met': conditions_met,
                    'min_conditions_required': min_conditions,
                    'trigger_reasons': trigger_reasons,
                    'conditions': {
                        'macd_divergence': condition_1,
                        'rsi_reversal': condition_2,
                        'volume_breakout': condition_3
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