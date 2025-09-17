"""
MA13强势回调趋势系统 - 完整实现5步筛选流程
专为捕捉强势股回调后的精准入场时机设计

策略核心：
1. 日线定大势（步骤1-3）：底部稳定 + 放量突破 + 回调MA13
2. 小时线定买点（步骤4-5）：超跌反弹模型 + 中继确认模型

作者：基于Grok和Gemini评估优化
日期：2025-09-17
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import sys
import os

# 添加backend路径以便导入模块
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)

try:
    from backend.data_loader import fetch_hourly_kline, get_multi_timeframe_data
    from backend.indicators import (
        calculate_ma, calculate_macd, calculate_kdj, calculate_rsi,
        get_indicator_position, check_macd_golden_cross, check_volume_amplification,
        get_ma13_support_level
    )
except ImportError as e:
    print(f"导入模块失败: {e}")
    # 尝试相对导入
    try:
        from ..data_loader import fetch_hourly_kline, get_multi_timeframe_data
        from ..indicators import (
            calculate_ma, calculate_macd, calculate_kdj, calculate_rsi,
            get_indicator_position, check_macd_golden_cross, check_volume_amplification,
            get_ma13_support_level
        )
    except ImportError:
        raise ImportError("无法导入必要的模块，请检查项目结构")

class MA13CallbackStrategy:
    """MA13强势回调趋势策略"""
    
    def __init__(self, config: Dict):
        """
        初始化策略
        
        Args:
            config: 策略配置字典
        """
        self.config = config
        self.default_config = {
            'callback_range': [3, 15],      # 回调幅度范围 3%-15%
            'vol_multiplier': 1.1,          # 成交量放大倍数
            'kdj_relay_range': [40, 90],     # KDJ中继区间
            'ma13_tolerance': 0.02,          # MA13支撑容忍度 2%
            'min_rise_pct': 15,              # 最小涨幅要求 15%
            'lookback_days': 60,             # 回看天数
            'hourly_lookback_days': 10       # 小时线回看天数
        }
        
        # 合并配置
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
    
    def apply_strategy(self, stock_code: str, daily_df: pd.DataFrame) -> Dict:
        """
        应用完整的5步MA13策略
        
        Args:
            stock_code: 股票代码
            daily_df: 日线数据DataFrame
        
        Returns:
            Dict: 策略结果 {'signal': str, 'strength': float, 'model': str, 'details': dict}
        """
        try:
            # === 步骤1-3: 日线趋势检查 ===
            daily_result = self._check_daily_trend(stock_code, daily_df)
            if not daily_result['passed']:
                return {
                    'signal': None,
                    'strength': 0.0,
                    'model': 'daily_filter',
                    'details': daily_result
                }
            
            # === 步骤4-5: 小时线确认 ===
            # 只在日线通过后才加载小时线数据，提高效率
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=self.config['hourly_lookback_days'])).strftime('%Y-%m-%d')
            
            hourly_df = fetch_hourly_kline(stock_code, start_date, end_date)
            
            if hourly_df.empty or len(hourly_df) < 20:
                return {
                    'signal': None,
                    'strength': 0.0,
                    'model': 'hourly_data_insufficient',
                    'details': {'hourly_bars': len(hourly_df) if not hourly_df.empty else 0}
                }
            
            # 计算小时线指标
            hourly_indicators = self._calculate_hourly_indicators(hourly_df)
            
            # 应用双模型检查
            model_result = self._apply_hourly_models(hourly_df, hourly_indicators)
            
            # 合并结果
            result = {
                'signal': model_result['signal'],
                'strength': model_result['strength'],
                'model': model_result['model'],
                'details': {
                    'daily': daily_result,
                    'hourly': model_result['details'],
                    'stock_code': stock_code,
                    'timestamp': datetime.now().isoformat()
                }
            }
            
            return result
            
        except Exception as e:
            return {
                'signal': None,
                'strength': 0.0,
                'model': 'error',
                'details': {'error': str(e)}
            }
    
    def _check_daily_trend(self, stock_code: str, df: pd.DataFrame) -> Dict:
        """
        检查日线趋势（步骤1-3）
        
        Args:
            stock_code: 股票代码
            df: 日线数据
        
        Returns:
            Dict: 日线检查结果
        """
        if len(df) < 60:
            return {'passed': False, 'reason': 'insufficient_data', 'bars': len(df)}
        
        # 确保数据按日期排序
        df = df.sort_index()
        
        # 计算必要指标
        ma13 = calculate_ma(df, 13)
        ma60 = calculate_ma(df, 60)
        vol_ma20 = df['volume'].rolling(20).mean()
        
        # 获取最近数据
        current_price = df['close'].iloc[-1]
        current_ma13 = ma13.iloc[-1]
        current_ma60 = ma60.iloc[-1]
        
        # === 步骤1: 底部稳定检查 ===
        # 检查60日内的价格波动范围
        recent_60_high = df['high'].tail(60).max()
        recent_60_low = df['low'].tail(60).min()
        price_range_pct = (recent_60_high - recent_60_low) / recent_60_low * 100
        
        # 检查MA60斜率（简化：比较最近5日MA60均值）
        ma60_slope_positive = ma60.tail(5).mean() > ma60.tail(10).head(5).mean()
        
        bottom_stable = price_range_pct < 50 and ma60_slope_positive  # 波动<50%且MA60向上
        
        # === 步骤2: 放量突破检查 ===
        # 检查最近20日内是否有显著涨幅和放量
        recent_20_low = df['low'].tail(20).min()
        rise_from_low_pct = (current_price - recent_20_low) / recent_20_low * 100
        
        # 检查是否有放量（最近5日内有成交量>1.2倍均量）
        recent_vol_amplified = any(
            df['volume'].tail(5) > vol_ma20.tail(5) * 1.2
        )
        
        breakout_confirmed = rise_from_low_pct >= self.config['min_rise_pct'] and recent_vol_amplified
        
        # === 步骤3: MA13回调检查 ===
        # 检查当前是否在MA13附近（支撑位）
        ma13_support = get_ma13_support_level(df['close'], 13, self.config['ma13_tolerance'])
        
        # 检查回调幅度
        recent_high = df['high'].tail(10).max()
        callback_pct = (recent_high - current_price) / recent_high * 100
        callback_in_range = (self.config['callback_range'][0] <= callback_pct <= 
                           self.config['callback_range'][1])
        
        # 综合判断
        daily_passed = bottom_stable and breakout_confirmed and ma13_support['supported'] and callback_in_range
        
        return {
            'passed': daily_passed,
            'bottom_stable': bottom_stable,
            'breakout_confirmed': breakout_confirmed,
            'ma13_supported': ma13_support['supported'],
            'callback_in_range': callback_in_range,
            'details': {
                'price_range_pct': price_range_pct,
                'rise_from_low_pct': rise_from_low_pct,
                'callback_pct': callback_pct,
                'ma13_distance': ma13_support['distance'],
                'current_price': current_price,
                'ma13_value': current_ma13
            }
        }
    
    def _calculate_hourly_indicators(self, hourly_df: pd.DataFrame) -> Dict:
        """
        计算小时线指标
        
        Args:
            hourly_df: 小时线数据
        
        Returns:
            Dict: 指标结果
        """
        # MACD(8,21,6) - 适合小时线的参数
        dif, dea = calculate_macd(hourly_df, fast=8, slow=21, signal=6)
        
        # KDJ(27,3,3) - 适合小时线的参数
        k, d, j = calculate_kdj(hourly_df, n=27, k_period=3, d_period=3)
        
        # RSI(6) - 短周期RSI更敏感
        rsi = calculate_rsi(hourly_df, periods=6)
        
        # 成交量均线
        vol_ma20 = hourly_df['volume'].rolling(20).mean()
        
        return {
            'macd_dif': dif,
            'macd_dea': dea,
            'kdj_k': k,
            'kdj_d': d,
            'kdj_j': j,
            'rsi': rsi,
            'vol_ma20': vol_ma20
        }
    
    def _apply_hourly_models(self, hourly_df: pd.DataFrame, indicators: Dict) -> Dict:
        """
        应用小时线双模型（步骤4-5）
        
        Args:
            hourly_df: 小时线数据
            indicators: 计算好的指标
        
        Returns:
            Dict: 模型结果
        """
        # 获取最新指标值
        latest_kdj_j = indicators['kdj_j'].iloc[-1]
        latest_rsi = indicators['rsi'].iloc[-1]
        latest_dif = indicators['macd_dif'].iloc[-1]
        latest_dea = indicators['macd_dea'].iloc[-1]
        latest_volume = hourly_df['volume'].iloc[-1]
        latest_vol_ma20 = indicators['vol_ma20'].iloc[-1]
        
        # 检查成交量放大
        vol_amplified = check_volume_amplification(
            hourly_df['volume'], 
            ma_period=20, 
            multiplier=self.config['vol_multiplier']
        )
        
        # 检查MACD金叉
        macd_golden = check_macd_golden_cross(
            indicators['macd_dif'], 
            indicators['macd_dea'], 
            lookback=3
        )
        
        # === 模型1: 超跌反弹模型 ===
        kdj_oversold = get_indicator_position(latest_kdj_j, 'kdj_j') == 'oversold'
        
        super_fall_conditions = [
            kdj_oversold,                    # KDJ J < 40 超卖
            macd_golden,                     # MACD金叉
            vol_amplified                    # 成交量放大
        ]
        
        if all(super_fall_conditions):
            return {
                'signal': 'buy_super_fall',
                'strength': 0.7,
                'model': 'Super Fall Rebound',
                'details': {
                    'kdj_j': latest_kdj_j,
                    'kdj_position': 'oversold',
                    'macd_golden': macd_golden,
                    'vol_amplified': vol_amplified,
                    'conditions_met': super_fall_conditions
                }
            }
        
        # === 模型2: 中继确认模型 ===
        macd_above_zero = get_indicator_position(latest_dif, 'macd_dif') == 'above_zero'
        kdj_relay = get_indicator_position(latest_kdj_j, 'kdj_j') == 'relay'
        rsi_strong = get_indicator_position(latest_rsi, 'rsi_6') == 'strong_support'
        macd_bullish = latest_dif > latest_dea  # 拒绝死叉或保持金叉
        
        relay_conditions = [
            macd_above_zero,                 # MACD DIF在零轴上方
            macd_bullish,                    # DIF > DEA（拒绝死叉）
            kdj_relay,                       # KDJ在中继区间40-90
            rsi_strong,                      # RSI > 60强势支撑
            vol_amplified                    # 成交量放大
        ]
        
        if all(relay_conditions):
            return {
                'signal': 'buy_relay',
                'strength': 0.9,
                'model': 'Relay Confirmation',
                'details': {
                    'kdj_j': latest_kdj_j,
                    'kdj_position': 'relay',
                    'rsi': latest_rsi,
                    'rsi_position': 'strong_support',
                    'macd_dif': latest_dif,
                    'macd_position': 'above_zero',
                    'macd_bullish': macd_bullish,
                    'vol_amplified': vol_amplified,
                    'conditions_met': relay_conditions
                }
            }
        
        # 无信号
        return {
            'signal': None,
            'strength': 0.0,
            'model': 'No Signal',
            'details': {
                'super_fall_score': sum(super_fall_conditions),
                'relay_score': sum(relay_conditions),
                'kdj_j': latest_kdj_j,
                'kdj_position': get_indicator_position(latest_kdj_j, 'kdj_j'),
                'rsi': latest_rsi,
                'macd_dif': latest_dif,
                'vol_amplified': vol_amplified
            }
        }
    
    def get_risk_management_params(self, entry_price: float, ma13_value: float) -> Dict:
        """
        获取风险管理参数
        
        Args:
            entry_price: 入场价格
            ma13_value: MA13数值
        
        Returns:
            Dict: 风险管理参数
        """
        # 止损位：MA13下方3-5%
        stop_loss_pct = 0.03  # 3%
        stop_loss_price = ma13_value * (1 - stop_loss_pct)
        
        # 持仓窗口：5-8天
        hold_days_min = 5
        hold_days_max = 8
        
        # 仓位建议
        position_size = {
            'super_fall': 0.3,  # 超跌反弹：较保守仓位
            'relay': 0.7        # 中继确认：较积极仓位
        }
        
        return {
            'stop_loss_price': stop_loss_price,
            'stop_loss_pct': stop_loss_pct,
            'hold_days_range': [hold_days_min, hold_days_max],
            'position_size': position_size,
            'risk_reward_ratio': 2.0  # 风险收益比 1:2
        }

def test_ma13_strategy():
    """测试MA13策略"""
    # 测试配置
    config = {
        'callback_range': [3, 15],
        'vol_multiplier': 1.1,
        'kdj_relay_range': [40, 90],
        'ma13_tolerance': 0.02,
        'min_rise_pct': 15,
        'lookback_days': 60,
        'hourly_lookback_days': 10
    }
    
    strategy = MA13CallbackStrategy(config)
    
    # 测试股票代码（可以替换为实际股票）
    test_stocks = ['002021', '600618', '300739']
    
    for stock_code in test_stocks:
        print(f"\n=== 测试股票: {stock_code} ===")
        
        try:
            # 获取日线数据
            multi_data = get_multi_timeframe_data(stock_code)
            
            if not multi_data['data_status']['daily_available']:
                print(f"无法获取 {stock_code} 的日线数据")
                continue
            
            daily_df = multi_data['daily_data']
            
            # 应用策略
            result = strategy.apply_strategy(stock_code, daily_df)
            
            print(f"信号: {result['signal']}")
            print(f"强度: {result['strength']}")
            print(f"模型: {result['model']}")
            
            if result['signal']:
                print("详细信息:")
                print(f"  日线检查: {result['details']['daily']['passed']}")
                if 'hourly' in result['details']:
                    print(f"  小时线模型: {result['details']['hourly']['model']}")
            
        except Exception as e:
            print(f"测试 {stock_code} 时出错: {e}")

if __name__ == "__main__":
    test_ma13_strategy()