#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强势股MA13回调策略

专门针对强势股在MA13附近的回调机会
- 识别强势股特征
- 价格低于MA13时的回调机会
- 回调完会继续上涨
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional
from .base_strategy import BaseStrategy
import indicators


class StrongStockMA13PullbackStrategy(BaseStrategy):
    """强势股MA13回调策略类"""
    
    def get_strategy_name(self) -> str:
        return "强势股MA13回调策略"
    
    def get_strategy_version(self) -> str:
        return "1.0"
    
    def get_strategy_description(self) -> str:
        return "专门针对强势股在MA13附近的回调机会，基于人工分析逻辑的强势股专用策略"
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            "ma": {
                "short_period": 13,
                "long_period": 45,
                "tolerance": 0.05
            },
            "strong_stock": {
                "trend_days": 5,
                "strength_ratio": 1.15,
                "above_ma13_ratio": 0.7,
                "lookback_days": 20
            },
            "pullback": {
                "threshold": 0.05,
                "high_lookback": 10
            },
            "rsi": {
                "period": 14,
                "min_level": 35
            },
            "kdj": {
                "n_period": 27,
                "k_period": 3,
                "d_period": 3,
                "support_threshold": 30
            },
            "volume": {
                "ma_period": 10
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
            assert 0 < self.config["ma"]["tolerance"] < 0.2
            assert 0 < self.config["pullback"]["threshold"] < 0.2
            assert 0 < self.config["strong_stock"]["above_ma13_ratio"] <= 1
            assert self.config["rsi"]["min_level"] > 20
            
            return True
        except Exception as e:
            raise ValueError(f"配置验证失败: {e}")
    
    def get_required_data_length(self) -> int:
        """获取所需的最小数据长度"""
        return 100  # 需要足够数据计算MA45和强势股判断
    
    def apply_strategy(self, df: pd.DataFrame) -> Tuple[Optional[pd.Series], Optional[Dict[str, Any]]]:
        """
        应用强势股MA13回调策略
        
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
            
            # 先判断是否为强势股
            if not self._is_strong_stock(df):
                return None, None
            
            # 生成回调信号
            signals = self._generate_pullback_signals(df)
            
            # 检查最新信号
            if not signals.iloc[-1]:
                return None, None
            
            # 计算信号详情
            signal_details = self._calculate_signal_details(df, signals)
            
            return signals, signal_details
            
        except Exception as e:
            return None, None
    
    def _is_strong_stock(self, df: pd.DataFrame) -> bool:
        """判断是否为强势股"""
        try:
            lookback_days = self.config["strong_stock"]["lookback_days"]
            
            if len(df) < lookback_days + self.config["ma"]["long_period"]:
                return False
            
            # 1. 均线排列
            ma13 = df['close'].rolling(self.config["ma"]["short_period"]).mean()
            ma45 = df['close'].rolling(self.config["ma"]["long_period"]).mean()
            
            # MA13在MA45之上
            ma_bullish = ma13 > ma45
            
            # 2. 价格趋势
            # 近期收盘价在MA13之上的比例
            recent_data = df.tail(lookback_days)
            recent_ma13 = ma13.tail(lookback_days)
            
            above_ma13_ratio = (recent_data['close'] > recent_ma13).sum() / lookback_days
            
            # 3. 相对强度
            # 近期最高价相对于近期最低价的比例
            recent_strength = recent_data['high'].max() / recent_data['low'].min()
            
            # 综合判断
            is_strong = (
                ma_bullish.iloc[-1] and  # 当前MA排列正确
                above_ma13_ratio >= self.config["strong_stock"]["above_ma13_ratio"] and  # 足够时间在MA13之上
                recent_strength >= self.config["strong_stock"]["strength_ratio"]  # 足够的波动空间
            )
            
            return is_strong
            
        except Exception:
            return False
    
    def _generate_pullback_signals(self, df: pd.DataFrame) -> pd.Series:
        """生成回调信号"""
        # 1. 计算关键均线
        ma13 = df['close'].rolling(self.config["ma"]["short_period"]).mean()
        ma45 = df['close'].rolling(self.config["ma"]["long_period"]).mean()
        
        # 2. 强势股识别条件
        # MA13持续在MA45之上，且呈上升趋势
        strong_trend = (ma13 > ma45) & (ma13 > ma13.shift(self.config["strong_stock"]["trend_days"]))
        
        # 近期价格表现强势
        recent_strength = (
            df['close'].rolling(self.config["pullback"]["high_lookback"]).max() / 
            df['close'].rolling(30).min() > self.config["strong_stock"]["strength_ratio"]
        )
        
        # 3. 回调到MA13附近的机会
        tolerance = self.config["ma"]["tolerance"]
        near_ma13 = (
            (df['close'] >= ma13 * (1 - tolerance)) & 
            (df['close'] <= ma13 * (1 + tolerance))
        )
        
        # 从高点回调
        recent_high = df['high'].rolling(self.config["pullback"]["high_lookback"]).max()
        pullback_from_high = df['close'] < recent_high * (1 - self.config["pullback"]["threshold"])
        
        # 4. 技术指标确认 - 避免过度超卖
        rsi = indicators.calculate_rsi(df, period=self.config["rsi"]["period"])
        rsi_suitable = rsi > self.config["rsi"]["min_level"]  # 不要太超卖
        
        # 5. KDJ支撑确认
        k, d, j = indicators.calculate_kdj(df, 
                                         n=self.config["kdj"]["n_period"],
                                         k=self.config["kdj"]["k_period"],
                                         d=self.config["kdj"]["d_period"])
        kdj_support = k > self.config["kdj"]["support_threshold"]  # KDJ不在极度超卖区
        
        # 6. 成交量确认 - 回调时成交量应该萎缩
        volume_pullback = df['volume'] < df['volume'].rolling(self.config["volume"]["ma_period"]).mean()
        
        # 7. 综合强势股回调信号
        strong_pullback_signal = (
            strong_trend & 
            recent_strength &
            near_ma13 & 
            pullback_from_high & 
            rsi_suitable & 
            kdj_support & 
            volume_pullback
        )
        
        return strong_pullback_signal.fillna(False)
    
    def _calculate_signal_details(self, df: pd.DataFrame, signals: pd.Series) -> Dict[str, Any]:
        """计算信号详情"""
        # 计算MA13距离
        ma13 = df['close'].rolling(self.config["ma"]["short_period"]).mean().iloc[-1]
        current_price = df['close'].iloc[-1]
        ma13_distance = (current_price - ma13) / ma13 if ma13 > 0 else 0
        
        # 计算RSI和KDJ当前值
        rsi = indicators.calculate_rsi(df, period=self.config["rsi"]["period"]).iloc[-1]
        k, d, j = indicators.calculate_kdj(df, 
                                         n=self.config["kdj"]["n_period"],
                                         k=self.config["kdj"]["k_period"],
                                         d=self.config["kdj"]["d_period"])
        
        # 计算回调幅度
        recent_high = df['high'].rolling(self.config["pullback"]["high_lookback"]).max().iloc[-1]
        pullback_ratio = (recent_high - current_price) / recent_high if recent_high > 0 else 0
        
        # 成交量分析
        volume_ma = df['volume'].rolling(self.config["volume"]["ma_period"]).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / volume_ma if volume_ma > 0 else 0
        
        return {
            'strategy_type': 'strong_stock_ma13_pullback',
            'signal_strength': 4,  # 高强度
            'is_strong_stock': True,  # 只有强势股才会进入此策略
            'optimal_timeframe': 'hourly',  # 强势股建议使用小时线
            'ma13_distance': float(ma13_distance),
            'ma13_price': float(ma13),
            'pullback_ratio': float(pullback_ratio),
            'current_indicators': {
                'rsi': float(rsi) if not pd.isna(rsi) else 0,
                'kdj_k': float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else 0,
                'kdj_d': float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else 0,
                'volume_ratio': float(volume_ratio)
            },
            'analysis_date': df.index[-1].strftime('%Y-%m-%d'),
            'data_points_used': len(df),
            'risk_level': 'medium',
            'expected_holding_period': '1-2周',
            'entry_logic': 'MA13回调支撑位买入',
            'stop_loss_level': float(ma13 * 0.95),  # MA13下方5%止损
            'target_price': float(recent_high * 1.05)  # 突破前高5%止盈
        }