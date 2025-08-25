#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
长周期横盘突破策略

识别长期横盘整理后的突破机会
- 长期横盘整理，筹码充足
- 突破后稳定强势上升
- 适合中长期持有
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional
from .base_strategy import BaseStrategy
import indicators


class LongTermConsolidationBreakoutStrategy(BaseStrategy):
    """长周期横盘突破策略类"""
    
    def get_strategy_name(self) -> str:
        return "长周期横盘突破策略"
    
    def get_strategy_version(self) -> str:
        return "1.0"
    
    def get_strategy_description(self) -> str:
        return "识别长期横盘整理后的突破机会，筹码充足后的稳定强势上升"
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            "consolidation": {
                "days": 60,
                "range_threshold": 0.15,
                "breakout_threshold": 0.02
            },
            "volume": {
                "surge_ratio": 1.3,
                "ma_short": 30,
                "ma_long": 60,
                "min_ratio": 0.8,
                "consistency_threshold": 0.6,
                "analysis_period": 20
            },
            "rsi": {
                "period": 14,
                "strength_threshold": 50
            },
            "macd": {
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9
            }
        }
    
    def validate_config(self) -> bool:
        """验证配置参数"""
        try:
            # 合并默认配置
            default_config = self.get_default_config()
            for key, value in default_config.items():
                if key not in self.config:
                    self.config[key] = value
                elif isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if sub_key not in self.config[key]:
                            self.config[key][sub_key] = sub_value
            
            # 验证关键参数
            assert 30 <= self.config["consolidation"]["days"] <= 120
            assert 0.05 <= self.config["consolidation"]["range_threshold"] <= 0.3
            assert 0 < self.config["volume"]["surge_ratio"] < 5
            assert 0 < self.config["volume"]["min_ratio"] <= 1
            
            return True
        except Exception as e:
            raise ValueError(f"配置验证失败: {e}")
    
    def get_required_data_length(self) -> int:
        """获取所需的最小数据长度"""
        return 150  # 需要足够数据进行长期横盘分析
    
    def apply_strategy(self, df: pd.DataFrame) -> Tuple[Optional[pd.Series], Optional[Dict[str, Any]]]:
        """
        应用长周期横盘突破策略
        
        Args:
            df: 股票数据DataFrame
            
        Returns:
            tuple: (信号Series, 信号详情字典)
        """
        try:
            if len(df) < self.get_required_data_length():
                return None, None
            
            # 数据预处理
            df = self.preprocess_data(df)
            
            # 计算技术指标
            df = self.calculate_technical_indicators(df)
            
            # 生成突破信号
            signals = self._generate_breakout_signals(df)
            
            # 检查最新信号
            if not signals.iloc[-1]:
                return None, None
            
            # 计算信号详情
            signal_details = self._calculate_signal_details(df, signals)
            
            return signals, signal_details
            
        except Exception as e:
            return None, None
    
    def _generate_breakout_signals(self, df: pd.DataFrame) -> pd.Series:
        """生成突破信号"""
        # 1. 长期横盘识别
        lookback_days = self.config["consolidation"]["days"]
        high_60d = df['high'].rolling(lookback_days).max()
        low_60d = df['low'].rolling(lookback_days).min()
        
        # 横盘特征：价格波动范围小于阈值
        price_range = (high_60d - low_60d) / ((high_60d + low_60d) / 2)
        is_consolidating = price_range < self.config["consolidation"]["range_threshold"]
        
        # 2. 筹码充足判断
        # 成交量持续活跃且相对稳定
        volume_ma_30 = df['volume'].rolling(self.config["volume"]["ma_short"]).mean()
        volume_ma_60 = df['volume'].rolling(self.config["volume"]["ma_long"]).mean()
        adequate_volume = volume_ma_30 > volume_ma_60 * self.config["volume"]["min_ratio"]  # 近期成交量不能太萎缩
        
        # 成交量一致性
        volume_consistency = (
            df['volume'].rolling(self.config["volume"]["ma_short"]).std() / volume_ma_30 < 
            self.config["volume"]["consistency_threshold"]
        )
        
        # 3. 突破确认
        breakout_price = high_60d * (1 + self.config["consolidation"]["breakout_threshold"])
        breakout_signal = df['close'] > breakout_price
        
        # 4. 技术指标配合
        # RSI显示强势
        rsi = indicators.calculate_rsi(df, period=self.config["rsi"]["period"])
        rsi_strength = rsi > self.config["rsi"]["strength_threshold"]
        
        # MACD金叉
        dif, dea = indicators.calculate_macd(df, 
                                           fast=self.config["macd"]["fast_period"],
                                           slow=self.config["macd"]["slow_period"],
                                           signal=self.config["macd"]["signal_period"])
        macd_golden_cross = dif > dea
        
        # 5. 成交量放大确认
        volume_surge = (
            df['volume'] > 
            df['volume'].rolling(self.config["volume"]["analysis_period"]).mean() * 
            self.config["volume"]["surge_ratio"]
        )
        
        # 6. 综合突破信号
        breakout_confirmed = (
            is_consolidating & 
            adequate_volume & 
            volume_consistency & 
            breakout_signal & 
            rsi_strength & 
            macd_golden_cross & 
            volume_surge
        )
        
        return breakout_confirmed.fillna(False)
    
    def _calculate_signal_details(self, df: pd.DataFrame, signals: pd.Series) -> Dict[str, Any]:
        """计算信号详情"""
        # 计算横盘时间和范围
        lookback_days = self.config["consolidation"]["days"]
        high_60d = df['high'].rolling(lookback_days).max().iloc[-1]
        low_60d = df['low'].rolling(lookback_days).min().iloc[-1]
        consolidation_range = (high_60d - low_60d) / ((high_60d + low_60d) / 2)
        
        # 计算当前技术指标
        current_price = df['close'].iloc[-1]
        rsi = indicators.calculate_rsi(df, period=self.config["rsi"]["period"]).iloc[-1]
        
        # MACD指标
        dif, dea = indicators.calculate_macd(df, 
                                           fast=self.config["macd"]["fast_period"],
                                           slow=self.config["macd"]["slow_period"],
                                           signal=self.config["macd"]["signal_period"])
        
        # 成交量分析
        volume_ma = df['volume'].rolling(self.config["volume"]["analysis_period"]).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        volume_surge_ratio = current_volume / volume_ma if volume_ma > 0 else 0
        
        # 计算筹码充足度指标
        volume_ma_30 = df['volume'].rolling(self.config["volume"]["ma_short"]).mean().iloc[-1]
        volume_ma_60 = df['volume'].rolling(self.config["volume"]["ma_long"]).mean().iloc[-1]
        volume_adequacy = volume_ma_30 / volume_ma_60 if volume_ma_60 > 0 else 0
        
        # 计算成交量稳定性
        volume_std = df['volume'].rolling(self.config["volume"]["ma_short"]).std().iloc[-1]
        volume_stability = 1 - (volume_std / volume_ma_30) if volume_ma_30 > 0 else 0
        
        return {
            'strategy_type': 'long_term_consolidation_breakout',
            'signal_strength': 4,  # 高强度信号
            'optimal_timeframe': 'daily',  # 长周期策略使用日线
            'consolidation_days': lookback_days,
            'consolidation_range': float(consolidation_range),
            'breakout_level': float(high_60d),
            'current_indicators': {
                'rsi': float(rsi) if not pd.isna(rsi) else 0,
                'macd_dif': float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else 0,
                'macd_dea': float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else 0,
                'volume_surge_ratio': float(volume_surge_ratio),
                'volume_adequacy': float(volume_adequacy),
                'volume_stability': float(max(0, volume_stability))
            },
            'consolidation_analysis': {
                'high_level': float(high_60d),
                'low_level': float(low_60d),
                'range_percentage': float(consolidation_range * 100),
                'breakout_threshold': float(high_60d * (1 + self.config["consolidation"]["breakout_threshold"]))
            },
            'analysis_date': df.index[-1].strftime('%Y-%m-%d'),
            'data_points_used': len(df),
            'risk_level': 'medium',
            'expected_holding_period': '4-8周',
            'entry_logic': '放量突破长期横盘上轨',
            'stop_loss_level': float(low_60d * 0.98),  # 横盘下轨下方2%止损
            'target_price': float(high_60d * (1 + consolidation_range * 1.5))  # 横盘区间1.5倍作为目标
        }