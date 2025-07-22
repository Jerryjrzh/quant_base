"""
技术指标计算库 - 支持可配置参数
所有函数接收一个包含标准OHLCV列的DataFrame，
并返回一个或多个包含完整指标序列的Pandas Series。
"""
import pandas as pd
import numpy as np
from typing import Tuple, Optional, Union
from dataclasses import dataclass

@dataclass
class IndicatorConfig:
    """指标配置基类"""
    pass

@dataclass
class MACDIndicatorConfig(IndicatorConfig):
    """MACD指标配置"""
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    price_type: str = 'close'  # 'close', 'hl2', 'hlc3', 'ohlc4'

@dataclass
class KDJIndicatorConfig(IndicatorConfig):
    """KDJ指标配置"""
    n_period: int = 27  # RSV计算周期
    k_period: int = 3   # K值平滑周期
    d_period: int = 3   # D值平滑周期
    smoothing_method: str = 'ema'  # 'ema', 'sma'

@dataclass
class RSIIndicatorConfig(IndicatorConfig):
    """RSI指标配置"""
    period: int = 14
    price_type: str = 'close'
    smoothing_method: str = 'wilder'  # 'wilder', 'ema', 'sma'

@dataclass
class VolumeIndicatorConfig(IndicatorConfig):
    """成交量指标配置"""
    ma_period: int = 30
    ma_type: str = 'sma'  # 'sma', 'ema'

def get_price_series(df: pd.DataFrame, price_type: str = 'close') -> pd.Series:
    """根据价格类型获取价格序列"""
    if price_type == 'close':
        return df['close']
    elif price_type == 'hl2':
        return (df['high'] + df['low']) / 2
    elif price_type == 'hlc3':
        return (df['high'] + df['low'] + df['close']) / 3
    elif price_type == 'ohlc4':
        return (df['open'] + df['high'] + df['low'] + df['close']) / 4
    else:
        return df['close']

def calculate_volume_ma(df: pd.DataFrame, config: Optional[VolumeIndicatorConfig] = None) -> pd.Series:
    """计算成交量移动平均线 - 支持配置"""
    if config is None:
        config = VolumeIndicatorConfig()
    
    if 'volume' not in df.columns:
        return pd.Series(index=df.index, dtype=float)
    
    if config.ma_type == 'ema':
        return df['volume'].ewm(span=config.ma_period, adjust=False).mean()
    else:  # sma
        return df['volume'].rolling(window=config.ma_period).mean()

def calculate_macd(df: pd.DataFrame, 
                  fast: Optional[int] = None, 
                  slow: Optional[int] = None, 
                  signal: Optional[int] = None,
                  config: Optional[MACDIndicatorConfig] = None) -> Tuple[pd.Series, pd.Series]:
    """计算MACD指标 - 支持配置和向后兼容"""
    
    # 向后兼容：如果传入了单独参数，使用它们
    if fast is not None or slow is not None or signal is not None:
        fast = fast or 12
        slow = slow or 26
        signal = signal or 9
        price_type = 'close'
    elif config is not None:
        fast = config.fast_period
        slow = config.slow_period
        signal = config.signal_period
        price_type = config.price_type
    else:
        # 使用默认配置
        config = MACDIndicatorConfig()
        fast = config.fast_period
        slow = config.slow_period
        signal = config.signal_period
        price_type = config.price_type
    
    # 获取价格序列
    price = get_price_series(df, price_type)
    
    # 计算MACD
    ema_fast = price.ewm(span=fast, adjust=False).mean()
    ema_slow = price.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()
    
    return dif, dea

def calculate_kdj(df: pd.DataFrame, 
                 n: Optional[int] = None,
                 k_period: Optional[int] = None,
                 d_period: Optional[int] = None,
                 config: Optional[KDJIndicatorConfig] = None) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """计算KDJ指标 - 支持配置和向后兼容"""
    
    # 向后兼容：如果传入了单独参数，使用它们
    if n is not None or k_period is not None or d_period is not None:
        n = n or 27
        k_period = k_period or 3
        d_period = d_period or 3
        smoothing_method = 'ema'
    elif config is not None:
        n = config.n_period
        k_period = config.k_period
        d_period = config.d_period
        smoothing_method = config.smoothing_method
    else:
        # 使用默认配置
        config = KDJIndicatorConfig()
        n = config.n_period
        k_period = config.k_period
        d_period = config.d_period
        smoothing_method = config.smoothing_method
    
    # 计算RSV
    low_n = df['low'].rolling(window=n).min()
    high_n = df['high'].rolling(window=n).max()
    
    # 避免除以零
    high_minus_low = high_n - low_n
    rsv = pd.Series(
        np.where(high_minus_low != 0, ((df['close'] - low_n) / high_minus_low) * 100, 0), 
        index=df.index
    )
    
    # 计算K和D值
    if smoothing_method == 'sma':
        k = rsv.rolling(window=k_period).mean()
        d = k.rolling(window=d_period).mean()
    else:  # ema (默认)
        k = rsv.ewm(com=(k_period-1)/2, adjust=False).mean()
        d = k.ewm(com=(d_period-1)/2, adjust=False).mean()
    
    # 计算J值
    j = 3 * k - 2 * d
    
    return k, d, j

def calculate_rsi(df: pd.DataFrame, 
                 periods: Optional[int] = None,
                 config: Optional[RSIIndicatorConfig] = None) -> pd.Series:
    """计算RSI指标 - 支持配置和向后兼容"""
    
    # 向后兼容：如果传入了periods参数，使用它
    if periods is not None:
        period = periods
        price_type = 'close'
        smoothing_method = 'wilder'
    elif config is not None:
        period = config.period
        price_type = config.price_type
        smoothing_method = config.smoothing_method
    else:
        # 使用默认配置
        config = RSIIndicatorConfig()
        period = config.period
        price_type = config.price_type
        smoothing_method = config.smoothing_method
    
    # 获取价格序列
    price = get_price_series(df, price_type)
    
    # 计算价格变化
    delta = price.diff(1)
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 根据平滑方法计算平均收益和损失
    if smoothing_method == 'wilder':
        # Wilder's Smoothing (传统RSI计算方法)
        avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    elif smoothing_method == 'ema':
        # 指数移动平均
        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()
    else:  # sma
        # 简单移动平均
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
    
    # 计算RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi.fillna(100)

def calculate_bollinger_bands(df: pd.DataFrame, 
                            period: int = 20, 
                            std_dev: float = 2.0,
                            price_type: str = 'close') -> Tuple[pd.Series, pd.Series, pd.Series]:
    """计算布林带指标"""
    price = get_price_series(df, price_type)
    
    # 中轨（移动平均线）
    middle = price.rolling(window=period).mean()
    
    # 标准差
    std = price.rolling(window=period).std()
    
    # 上轨和下轨
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return upper, middle, lower

def calculate_williams_r(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算威廉指标(%R)"""
    high_n = df['high'].rolling(window=period).max()
    low_n = df['low'].rolling(window=period).min()
    
    # 避免除以零
    high_minus_low = high_n - low_n
    wr = pd.Series(
        np.where(high_minus_low != 0, ((high_n - df['close']) / high_minus_low) * -100, 0),
        index=df.index
    )
    
    return wr

def calculate_obv(df: pd.DataFrame) -> pd.Series:
    """计算能量潮指标(OBV)"""
    if 'volume' not in df.columns:
        return pd.Series(index=df.index, dtype=float)
    
    price_change = df['close'].diff()
    volume_direction = pd.Series(index=df.index, dtype=float)
    
    volume_direction[price_change > 0] = df['volume']
    volume_direction[price_change < 0] = -df['volume']
    volume_direction[price_change == 0] = 0
    
    obv = volume_direction.cumsum()
    return obv

def calculate_vwap(df: pd.DataFrame) -> pd.Series:
    """计算成交量加权平均价格(VWAP)"""
    if 'volume' not in df.columns:
        return df['close'].copy()
    
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    vwap = (typical_price * df['volume']).cumsum() / df['volume'].cumsum()
    
    return vwap

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算平均真实波幅(ATR)"""
    high_low = df['high'] - df['low']
    high_close_prev = np.abs(df['high'] - df['close'].shift(1))
    low_close_prev = np.abs(df['low'] - df['close'].shift(1))
    
    true_range = pd.concat([high_low, high_close_prev, low_close_prev], axis=1).max(axis=1)
    atr = true_range.ewm(span=period, adjust=False).mean()
    
    return atr

# 指标配置工厂函数
def create_macd_config(fast: int = 12, slow: int = 26, signal: int = 9, 
                      price_type: str = 'close') -> MACDIndicatorConfig:
    """创建MACD配置"""
    return MACDIndicatorConfig(fast, slow, signal, price_type)

def create_kdj_config(n: int = 27, k_period: int = 3, d_period: int = 3,
                     smoothing_method: str = 'ema') -> KDJIndicatorConfig:
    """创建KDJ配置"""
    return KDJIndicatorConfig(n, k_period, d_period, smoothing_method)

def create_rsi_config(period: int = 14, price_type: str = 'close',
                     smoothing_method: str = 'wilder') -> RSIIndicatorConfig:
    """创建RSI配置"""
    return RSIIndicatorConfig(period, price_type, smoothing_method)

def create_volume_config(ma_period: int = 30, ma_type: str = 'sma') -> VolumeIndicatorConfig:
    """创建成交量配置"""
    return VolumeIndicatorConfig(ma_period, ma_type)

# 批量计算函数
def calculate_all_indicators(df: pd.DataFrame, 
                           macd_config: Optional[MACDIndicatorConfig] = None,
                           kdj_config: Optional[KDJIndicatorConfig] = None,
                           rsi_config: Optional[RSIIndicatorConfig] = None) -> dict:
    """批量计算所有指标"""
    results = {}
    
    # MACD
    dif, dea = calculate_macd(df, config=macd_config)
    results['macd_dif'] = dif
    results['macd_dea'] = dea
    results['macd_histogram'] = dif - dea
    
    # KDJ
    k, d, j = calculate_kdj(df, config=kdj_config)
    results['kdj_k'] = k
    results['kdj_d'] = d
    results['kdj_j'] = j
    
    # RSI
    rsi = calculate_rsi(df, config=rsi_config)
    results['rsi'] = rsi
    
    # 布林带
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df)
    results['bb_upper'] = bb_upper
    results['bb_middle'] = bb_middle
    results['bb_lower'] = bb_lower
    
    # 威廉指标
    results['williams_r'] = calculate_williams_r(df)
    
    # 成交量指标
    if 'volume' in df.columns:
        results['obv'] = calculate_obv(df)
        results['vwap'] = calculate_vwap(df)
        results['volume_ma'] = calculate_volume_ma(df)
    
    # ATR
    results['atr'] = calculate_atr(df)
    
    return results

# 指标验证函数
def validate_indicator_data(df: pd.DataFrame) -> Tuple[bool, list]:
    """验证数据是否适合计算指标"""
    errors = []
    
    required_columns = ['open', 'high', 'low', 'close']
    for col in required_columns:
        if col not in df.columns:
            errors.append(f"缺少必需列: {col}")
    
    if len(df) < 50:
        errors.append("数据量不足，建议至少50个数据点")
    
    # 检查数据质量
    if not errors:
        if df['high'].min() < 0 or df['low'].min() < 0:
            errors.append("价格数据包含负值")
        
        if (df['high'] < df['low']).any():
            errors.append("存在最高价低于最低价的异常数据")
        
        if df[required_columns].isnull().any().any():
            errors.append("价格数据包含空值")
    
    return len(errors) == 0, errors