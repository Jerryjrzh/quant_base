"""
技术指标计算库 - 支持可配置参数和复权处理
所有函数接收一个包含标准OHLCV列的DataFrame，
并返回一个或多个包含完整指标序列的Pandas Series。
"""
import pandas as pd
import numpy as np
from typing import Tuple, Optional, Union
from dataclasses import dataclass

# 导入复权处理模块
try:
    from .adjustment_processor import AdjustmentProcessor, AdjustmentConfig, create_adjustment_config
except ImportError:
    from adjustment_processor import AdjustmentProcessor, AdjustmentConfig, create_adjustment_config

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
    adjustment_config: Optional[AdjustmentConfig] = None  # 复权配置

@dataclass
class KDJIndicatorConfig(IndicatorConfig):
    """KDJ指标配置"""
    n_period: int = 27  # RSV计算周期
    k_period: int = 3   # K值平滑周期
    d_period: int = 3   # D值平滑周期
    smoothing_method: str = 'ema'  # 'ema', 'sma'
    adjustment_config: Optional[AdjustmentConfig] = None  # 复权配置

@dataclass
class RSIIndicatorConfig(IndicatorConfig):
    """RSI指标配置"""
    period: int = 14
    price_type: str = 'close'
    smoothing_method: str = 'wilder'  # 'wilder', 'ema', 'sma'
    adjustment_config: Optional[AdjustmentConfig] = None  # 复权配置

@dataclass
class VolumeIndicatorConfig(IndicatorConfig):
    """成交量指标配置"""
    pass

class TechnicalIndicators:
    """技术指标计算类 - 为MA13策略提供简化接口"""
    
    def __init__(self):
        pass
    
    def calculate_ma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """计算移动平均线"""
        return calculate_ma(df, period)
    
    def calculate_macd(self, df: pd.DataFrame, fast=12, slow=26, signal=9) -> Tuple[pd.Series, pd.Series]:
        """计算MACD指标"""
        config = MACDIndicatorConfig(fast_period=fast, slow_period=slow, signal_period=signal)
        return calculate_macd(df, config)
    
    def calculate_kdj(self, df: pd.DataFrame, n=27, k=3, d=3) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """计算KDJ指标"""
        config = KDJIndicatorConfig(n_period=n, k_period=k, d_period=d)
        return calculate_kdj(df, config)
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算RSI指标"""
        config = RSIIndicatorConfig(period=period)
        return calculate_rsi(df, config)
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

def calculate_ma(df: pd.DataFrame, period: int, price_type: str = 'close', ma_type: str = 'sma') -> pd.Series:
    """计算移动平均线
    
    Args:
        df: 包含OHLCV数据的DataFrame
        period: 移动平均周期
        price_type: 价格类型 ('close', 'hl2', 'hlc3', 'ohlc4')
        ma_type: 移动平均类型 ('sma', 'ema')
    
    Returns:
        移动平均线序列
    """
    price = get_price_series(df, price_type)
    
    if ma_type == 'ema':
        return price.ewm(span=period, adjust=False).mean()
    else:  # sma (默认)
        return price.rolling(window=period).mean()

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
                  config: Optional[MACDIndicatorConfig] = None,
                  stock_code: Optional[str] = None) -> Tuple[pd.Series, pd.Series]:
    """计算MACD指标 - 支持配置、复权处理和向后兼容"""
    
    # 向后兼容：如果传入了单独参数，使用它们
    if fast is not None or slow is not None or signal is not None:
        fast = fast or 12
        slow = slow or 26
        signal = signal or 9
        price_type = 'close'
        adjustment_config = None
    elif config is not None:
        fast = config.fast_period
        slow = config.slow_period
        signal = config.signal_period
        price_type = config.price_type
        adjustment_config = config.adjustment_config
    else:
        # 使用默认配置
        config = MACDIndicatorConfig()
        fast = config.fast_period
        slow = config.slow_period
        signal = config.signal_period
        price_type = config.price_type
        adjustment_config = config.adjustment_config
    
    # 应用复权处理
    working_df = df.copy()
    if adjustment_config is not None:
        processor = AdjustmentProcessor(adjustment_config)
        working_df = processor.process_data(working_df, stock_code)
    
    # 获取价格序列
    price = get_price_series(working_df, price_type)
    
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
                 config: Optional[KDJIndicatorConfig] = None,
                 stock_code: Optional[str] = None) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """计算KDJ指标 - 支持配置、复权处理和向后兼容"""
    
    # 向后兼容：如果传入了单独参数，使用它们
    if n is not None or k_period is not None or d_period is not None:
        n = n or 27
        k_period = k_period or 3
        d_period = d_period or 3
        smoothing_method = 'ema'
        adjustment_config = None
    elif config is not None:
        n = config.n_period
        k_period = config.k_period
        d_period = config.d_period
        smoothing_method = config.smoothing_method
        adjustment_config = config.adjustment_config
    else:
        # 使用默认配置
        config = KDJIndicatorConfig()
        n = config.n_period
        k_period = config.k_period
        d_period = config.d_period
        smoothing_method = config.smoothing_method
        adjustment_config = config.adjustment_config
    
    # 应用复权处理
    working_df = df.copy()
    if adjustment_config is not None:
        processor = AdjustmentProcessor(adjustment_config)
        working_df = processor.process_data(working_df, stock_code)
        
        # 记录复权信息（用于调试）
        if stock_code:
            adj_info = processor.get_adjustment_info(df, working_df)
            #print(f"📊 KDJ复权处理 {stock_code}: {adj_info['adjustment_type']}, "
             #     f"调整次数: {adj_info['adjustments_applied']}, "
              #    f"价格比例: {adj_info['price_change_ratio']:.4f}")
    
    # 计算RSV
    low_n = working_df['low'].rolling(window=n).min()
    high_n = working_df['high'].rolling(window=n).max()
    
    # 避免除以零
    high_minus_low = high_n - low_n
    rsv = pd.Series(
        np.where(high_minus_low != 0, ((working_df['close'] - low_n) / high_minus_low) * 100, 0), 
        index=working_df.index
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
                 config: Optional[RSIIndicatorConfig] = None,
                 stock_code: Optional[str] = None) -> pd.Series:
    """计算RSI指标 - 支持配置、复权处理和向后兼容"""
    
    # 向后兼容：如果传入了periods参数，使用它
    if periods is not None:
        period = periods
        price_type = 'close'
        smoothing_method = 'wilder'
        adjustment_config = None
    elif config is not None:
        period = config.period
        price_type = config.price_type
        smoothing_method = config.smoothing_method
        adjustment_config = config.adjustment_config
    else:
        # 使用默认配置
        config = RSIIndicatorConfig()
        period = config.period
        price_type = config.price_type
        smoothing_method = config.smoothing_method
        adjustment_config = config.adjustment_config
    
    # 应用复权处理
    working_df = df.copy()
    if adjustment_config is not None:
        processor = AdjustmentProcessor(adjustment_config)
        working_df = processor.process_data(working_df, stock_code)
    
    # 获取价格序列
    price = get_price_series(working_df, price_type)
    
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
                      price_type: str = 'close',
                      adjustment_type: str = 'forward') -> MACDIndicatorConfig:
    """创建MACD配置"""
    adjustment_config = create_adjustment_config(adjustment_type) if adjustment_type != 'none' else None
    return MACDIndicatorConfig(fast, slow, signal, price_type, adjustment_config)

def create_kdj_config(n: int = 27, k_period: int = 3, d_period: int = 3,
                     smoothing_method: str = 'ema',
                     adjustment_type: str = 'forward') -> KDJIndicatorConfig:
    """创建KDJ配置"""
    adjustment_config = create_adjustment_config(adjustment_type) if adjustment_type != 'none' else None
    return KDJIndicatorConfig(n, k_period, d_period, smoothing_method, adjustment_config)

def create_rsi_config(period: int = 14, price_type: str = 'close',
                     smoothing_method: str = 'wilder',
                     adjustment_type: str = 'forward') -> RSIIndicatorConfig:
    """创建RSI配置"""
    adjustment_config = create_adjustment_config(adjustment_type) if adjustment_type != 'none' else None
    return RSIIndicatorConfig(period, price_type, smoothing_method, adjustment_config)

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

# MA13短线策略专用：指标位置判断逻辑
def get_indicator_position(indicator_value: float, category: str) -> str:
    """
    将指标的绝对数值分类为相对位置，解决僵化阈值问题
    专为MA13强势回调趋势系统设计
    
    Args:
        indicator_value: 指标数值
        category: 指标类别 ('kdj_j', 'rsi_6', 'macd_dif')
    
    Returns:
        str: 位置分类 ('oversold', 'relay', 'overbought', 'strong_support', 'above_zero', 'below_zero', 'neutral')
    """
    if category == 'kdj_j':
        # KDJ的J值位置判断
        if indicator_value < 40:
            return 'oversold'  # 超卖区域，适合超跌反弹模型
        elif 40 <= indicator_value <= 90:
            return 'relay'     # 中继区域，适合中继确认模型
        else:
            return 'overbought'  # 超买区域，但强势股可能钝化
    
    elif category == 'rsi_6':
        # RSI6的位置判断（6周期RSI更敏感）
        if indicator_value > 60:
            return 'strong_support'  # 强势支撑位
        elif indicator_value < 30:
            return 'oversold'
        else:
            return 'neutral'
    
    elif category == 'macd_dif':
        # MACD DIF线的零轴位置判断
        if indicator_value > 0:
            return 'above_zero'  # 零轴上方，多头趋势
        else:
            return 'below_zero'  # 零轴下方，空头趋势
    
    return 'neutral'

def check_macd_golden_cross(dif: pd.Series, dea: pd.Series, lookback: int = 3) -> bool:
    """
    检查MACD是否出现金叉信号
    
    Args:
        dif: MACD DIF线
        dea: MACD DEA线  
        lookback: 回看周期数
    
    Returns:
        bool: 是否出现金叉
    """
    if len(dif) < lookback + 1 or len(dea) < lookback + 1:
        return False
    
    # 检查最近是否有金叉：DIF从下方穿越DEA
    for i in range(1, lookback + 1):
        if (dif.iloc[-i-1] <= dea.iloc[-i-1] and 
            dif.iloc[-i] > dea.iloc[-i]):
            return True
    
    return False

def check_volume_amplification(volume: pd.Series, ma_period: int = 20, multiplier: float = 1.1) -> bool:
    """
    检查成交量是否放大
    
    Args:
        volume: 成交量序列
        ma_period: 均量周期
        multiplier: 放大倍数
    
    Returns:
        bool: 成交量是否放大
    """
    if len(volume) < ma_period + 1:
        return False
    
    vol_ma = volume.rolling(window=ma_period).mean()
    current_vol = volume.iloc[-1]
    avg_vol = vol_ma.iloc[-1]
    
    return current_vol > avg_vol * multiplier

def get_ma13_support_level(close: pd.Series, ma_period: int = 13, tolerance: float = 0.02) -> dict:
    """
    获取MA13支撑位信息
    
    Args:
        close: 收盘价序列
        ma_period: MA周期
        tolerance: 支撑容忍度（2%）
    
    Returns:
        dict: 支撑位信息
    """
    if len(close) < ma_period + 1:
        return {'supported': False, 'distance': None, 'ma13_value': None}
    
    ma13 = close.rolling(window=ma_period).mean()
    current_price = close.iloc[-1]
    current_ma13 = ma13.iloc[-1]
    
    # 计算距离MA13的百分比
    distance_pct = (current_price - current_ma13) / current_ma13
    
    # 判断是否在支撑位上方
    supported = distance_pct >= -tolerance
    
    return {
        'supported': supported,
        'distance': distance_pct,
        'ma13_value': current_ma13,
        'current_price': current_price
    }

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
