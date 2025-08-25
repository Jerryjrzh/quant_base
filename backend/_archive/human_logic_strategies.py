#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基于人工分析逻辑的策略实现
将实际交易经验转化为量化策略

策略特点:
1. 年度见底机会策略 - 一年2-5次精准机会
2. 强势股MA13回调策略 - 强势股专用策略  
3. 长周期横盘突破策略 - 筹码充足后突破
"""

import pandas as pd
import numpy as np
import indicators
from datetime import datetime, timedelta


def annual_bottom_opportunity_strategy(df, config=None):
    """
    年度见底机会策略
    
    核心逻辑:
    - 一年2-5次真正的见底机会
    - RSI见底 + MACD低位 + KDJ强势 + 成交量萎缩
    - 严格控制信号频率，确保精准度
    """
    if config is None:
        config = {
            'rsi_oversold': 30,
            'macd_convergence': 0.01,
            'volume_shrink_ratio': 0.7,
            'signal_spacing_days': 60,
            'kdj_oversold': 20
        }
    
    # 1. RSI见底确认
    rsi = indicators.calculate_rsi(df, period=14)
    rsi_bottom = (rsi < config['rsi_oversold']) & (rsi > rsi.shift(1))  # RSI超卖且开始反弹
    
    # 2. MACD低位且收敛
    dif, dea = indicators.calculate_macd(df)
    macd_low = (dif < 0) & (dea < 0)  # 双线负值
    macd_convergence = abs(dif - dea) < config['macd_convergence']  # 收敛状态
    
    # 3. 成交量萎缩 - 见底时成交量特别低
    volume_ma = df['volume'].rolling(20).mean()
    volume_shrink = df['volume'] < volume_ma * config['volume_shrink_ratio']
    
    # 4. KDJ强势背离潜力
    k, d, j = indicators.calculate_kdj(df)
    kdj_oversold = (k < config['kdj_oversold']) & (d < config['kdj_oversold'])
    kdj_turning = k > k.shift(1)  # K值开始上升
    
    # 5. 综合见底信号
    bottom_signal = rsi_bottom & macd_low & macd_convergence & volume_shrink & kdj_oversold & kdj_turning
    
    # 6. 年度频率控制 - 确保一年只有2-5次机会
    annual_signals = validate_annual_frequency(bottom_signal, config['signal_spacing_days'])
    
    return annual_signals


def strong_stock_ma13_pullback_strategy(df, config=None):
    """
    强势股MA13回调策略
    
    核心逻辑:
    - 识别强势股特征
    - 价格低于MA13时的回调机会
    - 回调完会继续上涨
    """
    if config is None:
        config = {
            'ma13_tolerance': 0.05,
            'rsi_min_level': 35,
            'strong_trend_days': 5,
            'pullback_threshold': 0.05
        }
    
    # 1. 计算关键均线
    ma13 = df['close'].rolling(13).mean()
    ma45 = df['close'].rolling(45).mean()
    
    # 2. 强势股识别
    # MA13持续在MA45之上，且呈上升趋势
    strong_trend = (ma13 > ma45) & (ma13 > ma13.shift(config['strong_trend_days']))
    
    # 近期价格表现强势
    recent_strength = df['close'].rolling(10).max() / df['close'].rolling(30).min() > 1.15
    
    # 3. 回调到MA13附近的机会
    near_ma13 = (
        (df['close'] >= ma13 * (1 - config['ma13_tolerance'])) & 
        (df['close'] <= ma13 * (1 + config['ma13_tolerance']))
    )
    
    # 从高点回调
    recent_high = df['high'].rolling(10).max()
    pullback_from_high = df['close'] < recent_high * (1 - config['pullback_threshold'])
    
    # 4. 技术指标确认 - 避免过度超卖
    rsi = indicators.calculate_rsi(df, period=14)
    rsi_suitable = rsi > config['rsi_min_level']  # 不要太超卖
    
    # 5. KDJ支撑确认
    k, d, j = indicators.calculate_kdj(df)
    kdj_support = k > 30  # KDJ不在极度超卖区
    
    # 6. 成交量确认 - 回调时成交量应该萎缩
    volume_pullback = df['volume'] < df['volume'].rolling(10).mean()
    
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
    
    return strong_pullback_signal


def long_term_consolidation_breakout_strategy(df, config=None):
    """
    长周期横盘突破策略
    
    核心逻辑:
    - 长期横盘整理，筹码充足
    - 突破后稳定强势上升
    """
    if config is None:
        config = {
            'consolidation_days': 60,
            'consolidation_range': 0.15,
            'breakout_threshold': 0.02,
            'volume_surge_ratio': 1.3
        }
    
    # 1. 长期横盘识别
    lookback_days = config['consolidation_days']
    high_60d = df['high'].rolling(lookback_days).max()
    low_60d = df['low'].rolling(lookback_days).min()
    
    # 横盘特征：价格波动范围小于15%
    price_range = (high_60d - low_60d) / ((high_60d + low_60d) / 2)
    is_consolidating = price_range < config['consolidation_range']
    
    # 2. 筹码充足判断
    # 成交量持续活跃且相对稳定
    volume_ma_30 = df['volume'].rolling(30).mean()
    volume_ma_60 = df['volume'].rolling(60).mean()
    adequate_volume = volume_ma_30 > volume_ma_60 * 0.8  # 近期成交量不能太萎缩
    
    # 成交量一致性
    volume_consistency = df['volume'].rolling(30).std() / volume_ma_30 < 0.6
    
    # 3. 突破确认
    breakout_price = high_60d * (1 + config['breakout_threshold'])
    breakout_signal = df['close'] > breakout_price
    
    # 4. 技术指标配合
    # RSI显示强势
    rsi = indicators.calculate_rsi(df, period=14)
    rsi_strength = rsi > 50
    
    # MACD金叉
    dif, dea = indicators.calculate_macd(df)
    macd_golden_cross = dif > dea
    
    # 5. 成交量放大确认
    volume_surge = df['volume'] > df['volume'].rolling(20).mean() * config['volume_surge_ratio']
    
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
    
    return breakout_confirmed


def validate_annual_frequency(signals, min_spacing_days=60):
    """
    验证信号频率，确保一年内不超过5次信号
    
    Args:
        signals: 原始信号序列
        min_spacing_days: 信号之间的最小间隔天数
    
    Returns:
        过滤后的信号序列
    """
    validated_signals = pd.Series(False, index=signals.index)
    last_signal_date = None
    signal_count_this_year = 0
    current_year = None
    
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
            
            # 验证条件：间隔足够 且 年度信号数不超过5次
            if days_since_last >= min_spacing_days and signal_count_this_year < 5:
                validated_signals[date] = True
                last_signal_date = date
                signal_count_this_year += 1
    
    return validated_signals


def is_strong_stock(df, lookback_days=20):
    """
    判断是否为强势股
    
    Args:
        df: 股票数据
        lookback_days: 回看天数
    
    Returns:
        True if 强势股, False otherwise
    """
    if len(df) < lookback_days + 45:
        return False
    
    # 1. 均线排列
    ma13 = df['close'].rolling(13).mean()
    ma45 = df['close'].rolling(45).mean()
    
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
        above_ma13_ratio >= 0.7 and  # 70%的时间在MA13之上
        recent_strength >= 1.15  # 近期有15%以上的波动空间
    )
    
    return is_strong


def get_optimal_timeframe(df):
    """
    智能选择分析时间周期
    
    Returns:
        'hourly' for 强势股, 'daily' for 一般股票
    """
    if is_strong_stock(df):
        return 'hourly'  # 强势股使用小时线精准分析
    else:
        return 'daily'   # 一般股票使用日线稳健分析


# 策略映射字典
HUMAN_LOGIC_STRATEGIES = {
    'ANNUAL_BOTTOM_OPPORTUNITY': annual_bottom_opportunity_strategy,
    'STRONG_STOCK_MA13_PULLBACK': strong_stock_ma13_pullback_strategy,
    'LONG_TERM_CONSOLIDATION_BREAKOUT': long_term_consolidation_breakout_strategy
}


def apply_human_logic_strategy(strategy_name, df, config=None):
    """
    应用基于人工分析逻辑的策略
    
    Args:
        strategy_name: 策略名称
        df: 股票数据
        config: 策略配置
    
    Returns:
        信号序列
    """
    if strategy_name not in HUMAN_LOGIC_STRATEGIES:
        raise ValueError(f"未知策略: {strategy_name}")
    
    strategy_func = HUMAN_LOGIC_STRATEGIES[strategy_name]
    return strategy_func(df, config)


if __name__ == "__main__":
    # 测试代码
    print("🎯 基于人工分析逻辑的策略模块")
    print("包含策略:")
    for name in HUMAN_LOGIC_STRATEGIES.keys():
        print(f"  - {name}")