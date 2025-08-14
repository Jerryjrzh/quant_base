#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MACD零轴启动策略
MACD在零轴附近启动的强势信号
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


class MacdZeroAxisStrategy(BaseStrategy):
    """MACD零轴启动策略"""
    
    def __init__(self, config=None):
        """初始化策略"""
        self._default_config = {
            'macd': {
                'fast_period': 12,
                'slow_period': 26,
                'signal_period': 9,
                'zero_axis_range': 0.1
            },
            'post_cross_days': 3
        }
        
        super().__init__(config)
    
    def get_strategy_name(self) -> str:
        return "MACD零轴启动"
    
    def get_strategy_version(self) -> str:
        return "1.0"
    
    def get_strategy_description(self) -> str:
        return "MACD在零轴附近启动的强势信号"
    
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
        return self.config['macd']['slow_period'] + self.config['macd']['signal_period'] + 20
    
    def apply_strategy(self, df):
        """应用MACD零轴启动策略"""
        try:
            # 计算MACD指标
            dif, dea = indicators.calculate_macd(
                df,
                fast=self.config['macd']['fast_period'],
                slow=self.config['macd']['slow_period'],
                signal=self.config['macd']['signal_period']
            )
            
            macd_bar = dif - dea
            
            # 零轴附近判断
            is_near_zero = (
                (macd_bar > -self.config['macd']['zero_axis_range']) & 
                (macd_bar < self.config['macd']['zero_axis_range'])
            )
            
            # MACD柱状图上升
            is_increasing = macd_bar > macd_bar.shift(1)
            
            # 基础过滤条件
            primary_filter_passed = is_near_zero & is_increasing
            
            # 金叉判断
            is_mid_cross = (dif.shift(1) < dea.shift(1)) & (dif > dea)
            
            # 最近几天内发生过金叉
            cross_occured_recently = is_mid_cross.rolling(
                window=self.config['post_cross_days'], 
                min_periods=1
            ).sum() > 0
            
            # 三个阶段的信号
            signal_pre = primary_filter_passed & (dif < dea)  # 金叉前
            signal_mid = primary_filter_passed & is_mid_cross  # 金叉时
            signal_post = primary_filter_passed & (dif > dea) & cross_occured_recently & (~is_mid_cross)  # 金叉后
            
            # 生成信号序列
            results = pd.Series([''] * len(df), index=df.index)
            results[signal_pre] = 'PRE'
            results[signal_post] = 'POST'
            results[signal_mid] = 'MID'
            
            signal_details = {
                'strategy': self.name,
                'version': self.version,
                'signal_count': (results != '').sum()
            }
            
            return results, signal_details
            
        except Exception as e:
            logger.error(f"MACD零轴启动策略执行失败: {e}")
            return pd.Series('', index=df.index), None
    
    def get_signal_description(self, signal_value):
        """获取信号描述"""
        descriptions = {
            'PRE': '零轴启动预警：MACD即将在零轴附近金叉',
            'MID': '零轴启动确认：MACD在零轴附近金叉',
            'POST': '零轴启动跟进：MACD金叉后在零轴附近运行',
            '': '无信号'
        }
        return descriptions.get(signal_value, '未知信号')
    
    def get_strategy_info(self):
        """获取策略信息"""
        return {
            'id': f"{self.name.replace(' ', '_').lower()}_v{self.version}",
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'required_data_length': self.get_required_data_length(),
            'config': self.config,
            'signal_types': ['PRE', 'MID', 'POST'],
            'risk_level': 'medium',
            'suitable_market': ['牛市', '震荡市'],
            'tags': ['MACD', '零轴', '启动']
        }