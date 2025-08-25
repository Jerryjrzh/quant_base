#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
年度见底机会策略

基于人工分析逻辑的年度见底机会捕捉策略
- 一年2-5次精准见底机会
- RSI见底 + MACD低位 + KDJ强势 + 成交量萎缩
- 严格控制信号频率，确保精准度
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional
from .base_strategy import BaseStrategy
import indicators


class AnnualBottomOpportunityStrategy(BaseStrategy):
    """年度见底机会策略类"""
    
    def get_strategy_name(self) -> str:
        return "年度见底机会策略"
    
    def get_strategy_version(self) -> str:
        return "1.0"
    
    def get_strategy_description(self) -> str:
        return "基于人工分析逻辑，一年2-5次精准见底机会捕捉，四重指标协同分析"
    
    def get_default_config(self) -> Dict[str, Any]:
        return {
            "rsi": {
                "period": 14,
                "oversold_threshold": 30
            },
            "macd": {
                "fast_period": 12,
                "slow_period": 26,
                "signal_period": 9,
                "convergence_threshold": 0.01
            },
            "kdj": {
                "n_period": 27,
                "k_period": 3,
                "d_period": 3,
                "oversold_threshold": 20
            },
            "volume": {
                "shrink_ratio": 0.7,
                "analysis_period": 20
            },
            "signal_spacing": {
                "min_days": 60,
                "max_annual_signals": 5
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
            assert 0 < self.config["rsi"]["oversold_threshold"] < 50
            assert 0 < self.config["volume"]["shrink_ratio"] < 1
            assert self.config["signal_spacing"]["min_days"] > 0
            assert 1 <= self.config["signal_spacing"]["max_annual_signals"] <= 10
            
            return True
        except Exception as e:
            raise ValueError(f"配置验证失败: {e}")
    
    def get_required_data_length(self) -> int:
        """获取所需的最小数据长度"""
        return 250  # 年度策略需要足够长的历史数据
    
    def apply_strategy(self, df: pd.DataFrame) -> Tuple[Optional[pd.Series], Optional[Dict[str, Any]]]:
        """
        应用年度见底机会策略
        
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
            
            # 生成见底信号
            signals = self._generate_bottom_signals(df)
            
            # 验证年度频率
            validated_signals = self._validate_annual_frequency(signals)
            
            # 检查最新信号
            if not validated_signals.iloc[-1]:
                return None, None
            
            # 计算信号详情
            signal_details = self._calculate_signal_details(df, validated_signals)
            
            return validated_signals, signal_details
            
        except Exception as e:
            return None, None
    
    def _generate_bottom_signals(self, df: pd.DataFrame) -> pd.Series:
        """生成见底信号"""
        # 1. RSI见底确认
        rsi = indicators.calculate_rsi(df, period=self.config["rsi"]["period"])
        rsi_bottom = (
            (rsi < self.config["rsi"]["oversold_threshold"]) & 
            (rsi > rsi.shift(1))  # RSI超卖且开始反弹
        )
        
        # 2. MACD低位且收敛
        dif, dea = indicators.calculate_macd(df, 
                                           fast=self.config["macd"]["fast_period"],
                                           slow=self.config["macd"]["slow_period"],
                                           signal=self.config["macd"]["signal_period"])
        
        macd_low = (dif < 0) & (dea < 0)  # 双线负值
        macd_convergence = abs(dif - dea) < self.config["macd"]["convergence_threshold"]  # 收敛状态
        
        # 3. 成交量萎缩 - 见底时成交量特别低
        volume_ma = df['volume'].rolling(self.config["volume"]["analysis_period"]).mean()
        volume_shrink = df['volume'] < volume_ma * self.config["volume"]["shrink_ratio"]
        
        # 4. KDJ强势背离潜力
        k, d, j = indicators.calculate_kdj(df, 
                                         n=self.config["kdj"]["n_period"],
                                         k=self.config["kdj"]["k_period"],
                                         d=self.config["kdj"]["d_period"])
        
        kdj_oversold = (k < self.config["kdj"]["oversold_threshold"]) & (d < self.config["kdj"]["oversold_threshold"])
        kdj_turning = k > k.shift(1)  # K值开始上升
        
        # 5. 综合见底信号
        bottom_signal = rsi_bottom & macd_low & macd_convergence & volume_shrink & kdj_oversold & kdj_turning
        
        return bottom_signal.fillna(False)
    
    def _validate_annual_frequency(self, signals: pd.Series) -> pd.Series:
        """验证信号频率，确保一年内不超过5次信号"""
        validated_signals = pd.Series(False, index=signals.index)
        last_signal_date = None
        signal_count_this_year = 0
        current_year = None
        
        min_spacing_days = self.config["signal_spacing"]["min_days"]
        max_annual_signals = self.config["signal_spacing"]["max_annual_signals"]
        
        for date, signal in signals.items():
            if signal:
                # 检查年份变化
                if current_year is None or date.year != current_year:
                    current_year = date.year
                    signal_count_this_year = 0
                
                # 检查信号间隔
                if last_signal_date is None:
                    days_since_last = float('inf')
                else:
                    days_since_last = (date - last_signal_date).days
                
                # 验证条件：间隔足够 且 年度信号数不超过限制
                if days_since_last >= min_spacing_days and signal_count_this_year < max_annual_signals:
                    validated_signals[date] = True
                    last_signal_date = date
                    signal_count_this_year += 1
        
        return validated_signals
    
    def _calculate_signal_details(self, df: pd.DataFrame, signals: pd.Series) -> Dict[str, Any]:
        """计算信号详情"""
        # 计算当前年度信号数量
        current_year = df.index[-1].year
        annual_signals = signals[signals.index.year == current_year]
        annual_signal_count = annual_signals.sum()
        
        # 计算技术指标当前值
        rsi = indicators.calculate_rsi(df, period=self.config["rsi"]["period"]).iloc[-1]
        dif, dea = indicators.calculate_macd(df, 
                                           fast=self.config["macd"]["fast_period"],
                                           slow=self.config["macd"]["slow_period"],
                                           signal=self.config["macd"]["signal_period"])
        k, d, j = indicators.calculate_kdj(df, 
                                         n=self.config["kdj"]["n_period"],
                                         k=self.config["kdj"]["k_period"],
                                         d=self.config["kdj"]["d_period"])
        
        # 成交量分析
        volume_ma = df['volume'].rolling(self.config["volume"]["analysis_period"]).mean().iloc[-1]
        current_volume = df['volume'].iloc[-1]
        volume_ratio = current_volume / volume_ma if volume_ma > 0 else 0
        
        return {
            'strategy_type': 'annual_bottom_opportunity',
            'signal_strength': 5,  # 最高强度
            'annual_signal_count': int(annual_signal_count),
            'max_annual_signals': self.config["signal_spacing"]["max_annual_signals"],
            'current_indicators': {
                'rsi': float(rsi) if not pd.isna(rsi) else 0,
                'macd_dif': float(dif.iloc[-1]) if not pd.isna(dif.iloc[-1]) else 0,
                'macd_dea': float(dea.iloc[-1]) if not pd.isna(dea.iloc[-1]) else 0,
                'kdj_k': float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else 0,
                'kdj_d': float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else 0,
                'volume_ratio': float(volume_ratio)
            },
            'analysis_date': df.index[-1].strftime('%Y-%m-%d'),
            'data_points_used': len(df),
            'optimal_timeframe': 'daily',  # 年度策略使用日线
            'risk_level': 'low',
            'expected_holding_period': '2-4周'
        }