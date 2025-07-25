"""
交易策略库 - 支持可配置参数
所有函数接收一个包含OHLCV的DataFrame，并返回一个标记了信号日的布尔型或字符串型Series。
"""
import pandas as pd
import indicators

# 默认配置类
class DefaultConfig:
    class MACD:
        fast_period = 12
        slow_period = 26
        signal_period = 9
        zero_axis_range = 0.1
        dea_threshold = 0.0  # DEA阈值
    
    class KDJ:
        n_period = 9  # 修正属性名
        k_period = 9
        d_period = 3
        j_period = 3
        oversold_threshold = 20
        overbought_threshold = 80
        d_low_threshold = 50  # 添加D值低位阈值
    
    class RSI:
        period = 14
        period_short = 6  # 添加短期RSI周期
        period_long = 14  # 添加长期RSI周期
        oversold_threshold = 30
        overbought_threshold = 70
        neutral_high = 60  # 添加中性区间上限
    
    class WeeklyGoldenCrossMA:
        ma13_tolerance = 0.02  # MA13附近的容忍度（±2%）
        volume_surge_threshold = 1.2  # 成交量放大阈值
        ma_trend_periods = [7, 13, 30, 45]  # 用于趋势判断的MA周期
        sell_threshold = 0.95  # 卖出阈值（MA13的95%）
    
    def __init__(self):
        self.macd = self.MACD()
        self.kdj = self.KDJ()
        self.rsi = self.RSI()
        self.weekly_golden_cross_ma = self.WeeklyGoldenCrossMA()
        self.post_cross_days = 3  # 添加缺失的属性

def get_strategy_config(strategy_name):
    """获取策略配置（临时实现）"""
    return DefaultConfig()

def apply_triple_cross(df, config=None):
    """应用"三重金叉"策略 - 支持可配置参数"""
    if config is None:
        config = get_strategy_config('TRIPLE_CROSS')
    
    # 使用配置参数计算指标
    dif, dea = indicators.calculate_macd(
        df, 
        fast=config.macd.fast_period,
        slow=config.macd.slow_period,
        signal=config.macd.signal_period
    )
    
    k, d, j = indicators.calculate_kdj(
        df,
        n=config.kdj.n_period,
        k_period=config.kdj.k_period,
        d_period=config.kdj.d_period
    )
    
    rsi_short = indicators.calculate_rsi(df, config.rsi.period_short)
    rsi_long = indicators.calculate_rsi(df, config.rsi.period_long)
    
    # 使用配置的阈值进行判断
    macd_cross = (
        (dif.shift(1) < dea.shift(1)) & 
        (dif > dea) & 
        (dea < config.macd.dea_threshold)
    )
    
    kdj_cross = (
        (k.shift(1) < d.shift(1)) & 
        (k > d) & 
        (d < config.kdj.d_low_threshold)
    )
    
    rsi_cross = (
        (rsi_short.shift(1) < rsi_long.shift(1)) & 
        (rsi_short > rsi_long)
    )
    
    return macd_cross & kdj_cross & rsi_cross

def apply_pre_cross(df, config=None):
    """应用"临界金叉"策略 - 支持可配置参数"""
    if config is None:
        config = get_strategy_config('PRE_CROSS')
    
    # 使用配置参数计算指标
    dif, dea = indicators.calculate_macd(
        df,
        fast=config.macd.fast_period,
        slow=config.macd.slow_period,
        signal=config.macd.signal_period
    )
    
    k, d, j = indicators.calculate_kdj(
        df,
        n=config.kdj.n_period,
        k_period=config.kdj.k_period,
        d_period=config.kdj.d_period
    )
    
    rsi_short = indicators.calculate_rsi(df, config.rsi.period_short)
    
    # 使用配置的阈值
    cond1_kdj = (
        (j > k) & 
        (k > d) & 
        (k > k.shift(1)) & 
        (d < config.kdj.d_low_threshold)
    )
    
    macd_bar = dif - dea
    cond2_macd = (
        (dif < dea) & 
        (macd_bar > macd_bar.shift(1)) & 
        (dea < config.macd.dea_threshold)
    )
    
    cond3_rsi = (
        (rsi_short > rsi_short.shift(1)) & 
        (rsi_short < config.rsi.neutral_high)
    )
    
    return cond1_kdj & cond2_macd & cond3_rsi

def apply_macd_zero_axis_strategy(df, config=None, post_cross_days=None):
    """应用"MACD零轴启动策略" - 支持可配置参数"""
    if config is None:
        config = get_strategy_config('MACD_ZERO_AXIS')
    
    # 向后兼容：如果传入了post_cross_days参数，使用它
    if post_cross_days is not None:
        config.post_cross_days = post_cross_days
    
    # 使用配置参数计算MACD
    dif, dea = indicators.calculate_macd(
        df,
        fast=config.macd.fast_period,
        slow=config.macd.slow_period,
        signal=config.macd.signal_period
    )
    
    macd_bar = dif - dea
    
    # 使用配置的零轴范围
    is_near_zero = (
        (macd_bar > -config.macd.zero_axis_range) & 
        (macd_bar < config.macd.zero_axis_range)
    )
    is_increasing = macd_bar > macd_bar.shift(1)
    primary_filter_passed = is_near_zero & is_increasing

    is_mid_cross = (dif.shift(1) < dea.shift(1)) & (dif > dea)
    cross_occured_recently = is_mid_cross.rolling(
        window=config.post_cross_days, 
        min_periods=1
    ).sum() > 0
    
    signal_pre = primary_filter_passed & (dif < dea)
    signal_mid = primary_filter_passed & is_mid_cross
    signal_post = primary_filter_passed & (dif > dea) & cross_occured_recently & (~is_mid_cross)

    results = pd.Series([''] * len(df), index=df.index)
    results[signal_pre] = 'PRE'
    results[signal_post] = 'POST'
    results[signal_mid] = 'MID' 
    
    return results

def apply_weekly_golden_cross_ma_strategy(df, weekly_df=None, config=None):
    """
    应用"周线金叉+日线MA策略"
    
    策略逻辑：
    1. 通过周线指标判断金叉POST状态，深度筛选优化指标，确认大行情趋势，选择强势个股
    2. 使用MA 7 13 30 45 60 90 150 240指标，判断日线MA13作为价格底部指标，通过MA13附近确认入场盈利
    
    Args:
        df: 日线数据DataFrame
        weekly_df: 周线数据DataFrame
        config: 策略配置
    
    Returns:
        信号Series，包含'BUY'、'HOLD'、'SELL'信号
    """
    if config is None:
        config = get_strategy_config('WEEKLY_GOLDEN_CROSS_MA')
    
    # 如果没有周线数据，尝试从日线数据生成
    if weekly_df is None:
        weekly_df = convert_daily_to_weekly(df)
    
    # 第一步：周线金叉POST状态判断
    weekly_signals = apply_macd_zero_axis_strategy(weekly_df, config)
    weekly_post_signals = weekly_signals == 'POST'
    
    # 将周线信号映射到日线
    daily_weekly_signals = map_weekly_to_daily_signals(weekly_post_signals, df.index)
    
    # 第二步：计算日线MA指标
    ma_periods = [7, 13, 30, 45, 60, 90, 150, 240]
    mas = {}
    for period in ma_periods:
        mas[f'ma_{period}'] = df['close'].rolling(window=period).mean()
    
    # 第三步：MA13底部确认逻辑
    ma13 = mas['ma_13']
    close_price = df['close']
    
    # MA13附近的价格范围（±2%）
    ma13_tolerance = getattr(config.weekly_golden_cross_ma, 'ma13_tolerance', 0.02)
    near_ma13 = (
        (close_price >= ma13 * (1 - ma13_tolerance)) & 
        (close_price <= ma13 * (1 + ma13_tolerance))
    )
    
    # 第四步：多重MA排列确认趋势
    # 短期MA > 长期MA 表示上升趋势
    ma_trend_bullish = (
        (mas['ma_7'] > mas['ma_13']) &
        (mas['ma_13'] > mas['ma_30']) &
        (mas['ma_30'] > mas['ma_45'])
    )
    
    # 价格在MA13上方且MA排列良好
    price_above_ma13 = close_price > ma13
    
    # 第五步：成交量确认
    if 'volume' in df.columns:
        volume_ma = df['volume'].rolling(window=20).mean()
        volume_surge_threshold = getattr(config.weekly_golden_cross_ma, 'volume_surge_threshold', 1.2)
        volume_surge = df['volume'] > volume_ma * volume_surge_threshold
    else:
        volume_surge = pd.Series(True, index=df.index)  # 如果没有成交量数据，忽略此条件
    
    # 第六步：综合信号生成
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
    sell_threshold = getattr(config.weekly_golden_cross_ma, 'sell_threshold', 0.95)
    sell_signal = (
        (close_price < ma13 * sell_threshold) |  # 跌破MA13的阈值
        (~ma_trend_bullish)  # 或者趋势转弱
    )
    
    # 生成最终信号
    results = pd.Series([''] * len(df), index=df.index)
    results[buy_signal] = 'BUY'
    results[hold_signal] = 'HOLD'
    results[sell_signal] = 'SELL'
    
    return results

def convert_daily_to_weekly(daily_df):
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

def map_weekly_to_daily_signals(weekly_signals, daily_index):
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

def get_strategy_function(strategy_name: str):
    """根据策略名称获取策略函数"""
    strategy_map = {
        'TRIPLE_CROSS': apply_triple_cross,
        'PRE_CROSS': apply_pre_cross,
        'MACD_ZERO_AXIS': apply_macd_zero_axis_strategy,
        'WEEKLY_GOLDEN_CROSS_MA': apply_weekly_golden_cross_ma_strategy
    }
    return strategy_map.get(strategy_name)

def validate_strategy_config(strategy_name: str) -> tuple[bool, list]:
    """验证策略配置"""
    from strategy_config import config_manager
    return config_manager.validate_config(strategy_name)

def list_available_strategies() -> list:
    """列出可用的策略"""
    return ['TRIPLE_CROSS', 'PRE_CROSS', 'MACD_ZERO_AXIS', 'WEEKLY_GOLDEN_CROSS_MA']

def get_strategy_description(strategy_name: str) -> str:
    """获取策略描述"""
    descriptions = {
        'TRIPLE_CROSS': '三重金叉策略：MACD、KDJ、RSI同时金叉',
        'PRE_CROSS': '临界金叉策略：指标接近金叉的预警信号',
        'MACD_ZERO_AXIS': 'MACD零轴启动策略：MACD在零轴附近启动的信号',
        'WEEKLY_GOLDEN_CROSS_MA': '周线金叉+日线MA策略：周线POST状态+日线MA13底部确认'
    }
    return descriptions.get(strategy_name, '未知策略')

# 向后兼容的包装函数
def apply_triple_cross_legacy(df):
    """向后兼容的三重金叉策略"""
    return apply_triple_cross(df)

def apply_pre_cross_legacy(df):
    """向后兼容的临界金叉策略"""
    return apply_pre_cross(df)

def apply_macd_zero_axis_strategy_legacy(df, post_cross_days=3):
    """向后兼容的MACD零轴启动策略"""
    return apply_macd_zero_axis_strategy(df, post_cross_days=post_cross_days)