#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
临界金叉策略
识别即将形成金叉的股票，提前布局
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


class PreCrossStrategy(BaseStrategy):
    """临界金叉策略"""
    
    def __init__(self, config=None):
        """初始化策略"""
        # 先设置默认配置，再调用父类初始化
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
                'neutral_high': 60
            }
        }
        
        super().__init__(config)
    
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "临界金叉"
    
    def get_strategy_version(self) -> str:
        """获取策略版本"""
        return "1.0"
    
    def get_strategy_description(self) -> str:
        """获取策略描述"""
        return "识别即将形成金叉的股票，提前布局"
    
    def get_default_config(self):
        """获取默认配置"""
        return self._default_config
    
    def validate_config(self) -> bool:
        """验证配置参数"""
        try:
            # 合并默认配置和用户配置
            if not hasattr(self, 'config') or not self.config:
                self.config = self._default_config
            else:
                self.config = self._merge_config(self._default_config, self.config)
            return True
        except Exception as e:
            logger.error(f"配置验证失败: {e}")
            return False
    
    def _merge_config(self, default_config, user_config):
        """合并配置"""
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
            self.config['rsi']['period_short']
        ) + 10  # 额外的缓冲
    
    def apply_strategy(self, df):
        """应用临界金叉策略"""
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
            
            # 条件1：KDJ即将金叉
            cond1_kdj = (
                (j > k) & 
                (k > d) & 
                (k > k.shift(1)) & 
                (d < self.config['kdj']['d_low_threshold'])
            )
            
            # 条件2：MACD柱状图上升但未金叉
            macd_bar = dif - dea
            cond2_macd = (
                (dif < dea) & 
                (macd_bar > macd_bar.shift(1)) & 
                (dea < self.config['macd']['dea_threshold'])
            )
            
            # 条件3：RSI上升且在中性区间
            cond3_rsi = (
                (rsi_short > rsi_short.shift(1)) & 
                (rsi_short < self.config['rsi']['neutral_high'])
            )
            
            # 综合信号
            signals = cond1_kdj & cond2_macd & cond3_rsi
            
            # 返回信号和详情
            signal_details = {
                'strategy': self.name,
                'version': self.version,
                'signal_count': signals.sum() if hasattr(signals, 'sum') else 0
            }
            
            return signals, signal_details
            
        except Exception as e:
            logger.error(f"临界金叉策略执行失败: {e}")
            return pd.Series(False, index=df.index), None
    
    def get_signal_description(self, signal_value):
        """获取信号描述"""
        if signal_value:
            return "临界金叉信号：指标即将形成金叉，建议关注"
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
            'signal_types': ['买入预警'],
            'risk_level': 'low',
            'suitable_market': ['牛市', '震荡市'],
            'tags': ['金叉', '趋势', '技术分析']
        }