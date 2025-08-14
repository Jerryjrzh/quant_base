#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
周线金叉+日线MA策略
周线级别金叉配合日线MA确认
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


class WeeklyGoldenCrossMaStrategy(BaseStrategy):
    """周线金叉+日线MA策略"""
    
    def __init__(self, config=None):
        """初始化策略"""
        self._default_config = {
            'macd': {
                'fast_period': 12,
                'slow_period': 26,
                'signal_period': 9
            },
            'ma_periods': [7, 13, 30, 45, 60, 90, 150, 240],
            'ma13_tolerance': 0.02,  # MA13附近的容忍度（±2%）
            'volume_surge_threshold': 1.2,  # 成交量放大阈值
            'sell_threshold': 0.95,  # 卖出阈值（MA13的95%）
            'post_cross_days': 3
        }
        
        super().__init__(config)
    
    def get_strategy_name(self) -> str:
        return "周线金叉+日线MA"
    
    def get_strategy_version(self) -> str:
        return "1.0"
    
    def get_strategy_description(self) -> str:
        return "周线级别金叉配合日线MA确认"
    
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
        return max(self.config['ma_periods']) + 50  # 需要足够的数据计算长期MA
    
    def convert_daily_to_weekly(self, daily_df):
        """将日线数据转换为周线数据"""
        if daily_df.empty:
            return daily_df.copy()
        
        # 确保索引是日期时间格式
        if not isinstance(daily_df.index, pd.DatetimeIndex):
            daily_df = daily_df.copy()
            daily_df.index = pd.to_datetime(daily_df.index)
        
        # 按周重采样
        weekly_df = daily_df.resample('W').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum' if 'volume' in daily_df.columns else 'last'
        }).dropna()
        
        return weekly_df
    
    def map_weekly_to_daily_signals(self, weekly_signals, daily_index):
        """将周线信号映射到日线"""
        if not isinstance(daily_index, pd.DatetimeIndex):
            daily_index = pd.to_datetime(daily_index)
        
        # 创建日线信号序列
        daily_signals = pd.Series(False, index=daily_index)
        
        # 将每个周线信号映射到对应的日线区间
        for week_date, signal in weekly_signals.items():
            if signal:
                # 找到这一周对应的日线数据
                week_start = week_date - pd.Timedelta(days=6)  # 周的开始
                week_end = week_date  # 周的结束
                
                # 在这个时间范围内的所有日线都标记为True
                mask = (daily_index >= week_start) & (daily_index <= week_end)
                daily_signals[mask] = True
        
        return daily_signals
    
    def apply_macd_zero_axis_to_weekly(self, weekly_df):
        """对周线数据应用MACD零轴启动策略"""
        try:
            # 计算周线MACD
            dif, dea = indicators.calculate_macd(
                weekly_df,
                fast=self.config['macd']['fast_period'],
                slow=self.config['macd']['slow_period'],
                signal=self.config['macd']['signal_period']
            )
            
            macd_bar = dif - dea
            
            # 零轴附近判断
            is_near_zero = (macd_bar > -0.1) & (macd_bar < 0.1)
            is_increasing = macd_bar > macd_bar.shift(1)
            primary_filter_passed = is_near_zero & is_increasing
            
            # 金叉判断
            is_mid_cross = (dif.shift(1) < dea.shift(1)) & (dif > dea)
            cross_occured_recently = is_mid_cross.rolling(
                window=self.config['post_cross_days'], 
                min_periods=1
            ).sum() > 0
            
            # POST信号
            signal_post = primary_filter_passed & (dif > dea) & cross_occured_recently & (~is_mid_cross)
            
            return signal_post
            
        except Exception as e:
            self.logger.error(f"周线MACD零轴启动策略执行失败: {e}")
            return pd.Series(False, index=weekly_df.index)
    
    def apply_strategy(self, df):
        """应用周线金叉+日线MA策略"""
        try:
            # 第一步：生成周线数据
            weekly_df = self.convert_daily_to_weekly(df)
            
            # 第二步：周线金叉POST状态判断
            weekly_post_signals = self.apply_macd_zero_axis_to_weekly(weekly_df)
            
            # 将周线信号映射到日线
            daily_weekly_signals = self.map_weekly_to_daily_signals(weekly_post_signals, df.index)
            
            # 第三步：计算日线MA指标
            mas = {}
            for period in self.config['ma_periods']:
                mas[f'ma_{period}'] = df['close'].rolling(window=period).mean()
            
            # 第四步：MA13底部确认逻辑
            ma13 = mas['ma_13']
            close_price = df['close']
            
            # MA13附近的价格范围（±2%）
            near_ma13 = (
                (close_price >= ma13 * (1 - self.config['ma13_tolerance'])) & 
                (close_price <= ma13 * (1 + self.config['ma13_tolerance']))
            )
            
            # 第五步：多重MA排列确认趋势
            ma_trend_bullish = (
                (mas['ma_7'] > mas['ma_13']) &
                (mas['ma_13'] > mas['ma_30']) &
                (mas['ma_30'] > mas['ma_45'])
            )
            
            # 价格在MA13上方
            price_above_ma13 = close_price > ma13
            
            # 第六步：成交量确认
            if 'volume' in df.columns:
                volume_ma = df['volume'].rolling(window=20).mean()
                volume_surge = df['volume'] > volume_ma * self.config['volume_surge_threshold']
            else:
                volume_surge = pd.Series(True, index=df.index)
            
            # 第七步：综合信号生成
            # BUY信号：周线POST + 价格接近MA13 + 趋势向上 + 成交量放大
            buy_signal = (
                daily_weekly_signals &
                near_ma13 &
                ma_trend_bullish &
                volume_surge
            )
            
            # HOLD信号：周线POST + 价格在MA13上方 + 趋势向上
            hold_signal = (
                daily_weekly_signals &
                price_above_ma13 &
                ma_trend_bullish &
                (~buy_signal)  # 排除已经是BUY的信号
            )
            
            # SELL信号：价格跌破MA13且趋势转弱
            sell_signal = (
                (close_price < ma13 * self.config['sell_threshold']) |
                (~ma_trend_bullish)
            )
            
            # 生成最终信号
            results = pd.Series([''] * len(df), index=df.index)
            results[buy_signal] = 'BUY'
            results[hold_signal] = 'HOLD'
            results[sell_signal] = 'SELL'
            
            signal_details = {
                'strategy': self.name,
                'version': self.version,
                'signal_count': (results != '').sum()
            }
            
            return results, signal_details
            
        except Exception as e:
            logger.error(f"周线金叉+日线MA策略执行失败: {e}")
            return pd.Series('', index=df.index), None
    
    def get_signal_description(self, signal_value):
        """获取信号描述"""
        descriptions = {
            'BUY': '买入信号：周线金叉确认，价格接近MA13支撑',
            'HOLD': '持有信号：周线金叉持续，价格在MA13上方运行',
            'SELL': '卖出信号：价格跌破MA13支撑或趋势转弱',
            '': '无信号'
        }
        return descriptions.get(signal_value, '未知信号')
    
    def get_strategy_info(self):
        """获取策略信息"""
        return {
            'id': f"{self.name.replace(' ', '_').replace('+', '_').lower()}_v{self.version}",
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'required_data_length': self.get_required_data_length(),
            'config': self.config,
            'signal_types': ['BUY', 'HOLD', 'SELL'],
            'risk_level': 'low',
            'suitable_market': ['牛市', '震荡市'],
            'tags': ['周线', '金叉', '多周期']
        }