#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三重金叉策略
MA、MACD、KDJ三重金叉共振信号
"""

import pandas as pd
import sys
import os

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, backend_dir)

# 添加strategies目录到路径
strategies_dir = os.path.dirname(__file__)
sys.path.insert(0, strategies_dir)

import indicators
from base_strategy import BaseStrategy


class TripleCrossStrategy(BaseStrategy):
    """三重金叉策略"""
    
    def __init__(self, config=None):
        """初始化策略"""
        self._default_config = {
            'macd': {
                'fast_period': 12,
                'slow_period': 26,
                'signal_period': 9,
                'dea_threshold': 0.0
            },
            'kdj': {
                'n_period': 9,
                'k_period': 9,
                'd_period': 3,
                'd_low_threshold': 50
            },
            'rsi': {
                'period_short': 6,
                'period_long': 14
            }
        }
        
        super().__init__(config)
    
    def get_strategy_name(self) -> str:
        return "三重金叉"
    
    def get_strategy_version(self) -> str:
        return "1.0"
    
    def get_strategy_description(self) -> str:
        return "MA、MACD、KDJ三重金叉共振信号"
    
    def get_default_config(self):
        return self._default_config
    
    def validate_config(self) -> bool:
        try:
            if not hasattr(self, 'config') or not self.config:
                self.config = self._default_config
            else:
                self.config = self._merge_config(self._default_config, self.config)
            return True
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
    
    def _merge_config(self, default_config, user_config):
        merged = default_config.copy()
        if user_config:
            for key, value in user_config.items():
                if isinstance(value, dict) and key in merged:
                    merged[key].update(value)
                else:
                    merged[key] = value
        return merged
    
    def get_required_data_length(self):
        """获取所需的数据长度"""
        return max(
            self.config['macd']['slow_period'] + self.config['macd']['signal_period'],
            self.config['kdj']['n_period'] + self.config['kdj']['d_period'],
            self.config['rsi']['period_long']
        ) + 10  # 额外的缓冲
    
    def apply_strategy(self, df):
        """应用三重金叉策略"""
        try:
            # 计算MACD指标
            dif, dea = indicators.calculate_macd(
                df, 
                fast=self.config['macd']['fast_period'],
                slow=self.config['macd']['slow_period'],
                signal=self.config['macd']['signal_period']
            )
            
            # 计算KDJ指标
            k, d, j = indicators.calculate_kdj(
                df,
                n=self.config['kdj']['n_period'],
                k_period=self.config['kdj']['k_period'],
                d_period=self.config['kdj']['d_period']
            )
            
            # 计算RSI指标
            rsi_short = indicators.calculate_rsi(df, self.config['rsi']['period_short'])
            rsi_long = indicators.calculate_rsi(df, self.config['rsi']['period_long'])
            
            # MACD金叉条件
            macd_cross = (
                (dif.shift(1) < dea.shift(1)) & 
                (dif > dea) & 
                (dea < self.config['macd']['dea_threshold'])
            )
            
            # KDJ金叉条件
            kdj_cross = (
                (k.shift(1) < d.shift(1)) & 
                (k > d) & 
                (d < self.config['kdj']['d_low_threshold'])
            )
            
            # RSI金叉条件
            rsi_cross = (
                (rsi_short.shift(1) < rsi_long.shift(1)) & 
                (rsi_short > rsi_long)
            )
            
            # 三重金叉信号
            signals = macd_cross & kdj_cross & rsi_cross
            
            signal_details = {
                'strategy': self.name,
                'version': self.version,
                'signal_count': signals.sum() if hasattr(signals, 'sum') else 0
            }
            
            return signals, signal_details
            
        except Exception as e:
            logger.error(f"三重金叉策略执行失败: {e}")
            return pd.Series(False, index=df.index), None
    
    def get_signal_description(self, signal_value):
        """获取信号描述"""
        if signal_value:
            return "三重金叉信号：MACD、KDJ、RSI同时金叉，强势买入信号"
        return "无信号"
    
    def get_strategy_info(self):
        """获取策略信息"""
        return {
            'id': f"{self.name.replace(' ', '_').lower()}_v{self.version}",
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'required_data_length': self.get_required_data_length(),
            'config': self.config,
            'signal_types': ['强势买入'],
            'risk_level': 'medium',
            'suitable_market': ['牛市', '震荡市上升阶段'],
            'tags': ['三重金叉', '共振', '强势']
        }