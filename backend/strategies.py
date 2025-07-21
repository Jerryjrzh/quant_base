"""
交易策略库
所有函数接收一个包含OHLCV的DataFrame，并返回一个标记了信号日的布尔型或字符串型Series。
"""
import pandas as pd
import indicators # 导入我们自己的指标库

def apply_triple_cross(df):
    """应用“三重金叉”策略"""
    dif, dea = indicators.calculate_macd(df)
    k, d, j = indicators.calculate_kdj(df)
    rsi6 = indicators.calculate_rsi(df, 6)
    rsi12 = indicators.calculate_rsi(df, 12)
    
    macd_cross = (dif.shift(1) < dea.shift(1)) & (dif > dea) & (dea < 0.05)
    kdj_cross = (k.shift(1) < d.shift(1)) & (k > d) & (d < 50)
    rsi_cross = (rsi6.shift(1) < rsi12.shift(1)) & (rsi6 > rsi12)
    
    return macd_cross & kdj_cross & rsi_cross

def apply_pre_cross(df):
    """应用“临界金叉”策略"""
    dif, dea = indicators.calculate_macd(df)
    k, d, j = indicators.calculate_kdj(df)
    rsi6 = indicators.calculate_rsi(df, 6)
    
    cond1_kdj = (j > k) & (k > d) & (k > k.shift(1)) & (d < 50)
    macd_bar = dif - dea
    cond2_macd = (dif < dea) & (macd_bar > macd_bar.shift(1)) & (dea < 0.1)
    cond3_rsi = (rsi6 > rsi6.shift(1)) & (rsi6 < 60)
    
    return cond1_kdj & cond2_macd & cond3_rsi

def apply_macd_zero_axis_strategy(df, post_cross_days=3):
    """应用“MACD零轴启动策略”"""
    dif, dea = indicators.calculate_macd(df)
    macd_bar = dif - dea

    is_near_zero = (macd_bar > -0.01) & (macd_bar < 0.01)
    is_increasing = macd_bar > macd_bar.shift(1)
    primary_filter_passed = is_near_zero & is_increasing

    is_mid_cross = (dif.shift(1) < dea.shift(1)) & (dif > dea)
    cross_occured_recently = is_mid_cross.rolling(window=post_cross_days, min_periods=1).sum() > 0
    
    signal_pre = primary_filter_passed & (dif < dea)
    signal_mid = primary_filter_passed & is_mid_cross
    signal_post = primary_filter_passed & (dif > dea) & cross_occured_recently & (~is_mid_cross)

    results = pd.Series([''] * len(df), index=df.index)
    results[signal_pre] = 'PRE'
    results[signal_post] = 'POST'
    results[signal_mid] = 'MID' 
    
    return results
