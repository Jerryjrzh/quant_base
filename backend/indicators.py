"""
技术指标计算库
所有函数接收一个包含标准OHLCV列的DataFrame，
并返回一个或多个包含完整指标序列的Pandas Series。
"""
import pandas as pd
import numpy as np

def calculate_volume_ma(df, period=30):
    """计算成交量移动平均线"""
    return df['volume'].rolling(window=period).mean()

def calculate_macd(df, fast=12, slow=26, signal=9):
    """计算MACD指标"""
    close = df['close']
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    return dif, dea

def calculate_kdj(df, n=27, k_period=3, d_period=3):
    """计算KDJ指标"""
    low_n = df['low'].rolling(window=n).min()
    high_n = df['high'].rolling(window=n).max()
    
    # 避免除以零
    high_minus_low = high_n - low_n
    rsv = pd.Series(
        np.where(high_minus_low != 0, ((df['close'] - low_n) / high_minus_low) * 100, 0), 
        index=df.index
    )
    
    k = rsv.ewm(com=(k_period-1)/2, adjust=False).mean()
    d = k.ewm(com=(d_period-1)/2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j

def calculate_rsi(df, periods):
    """采用Wilder's Smoothing (EMA) 计算RSI"""
    delta = df['close'].diff(1)
    
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.ewm(alpha=1/periods, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/periods, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(100)