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
    
    def __init__(self):
        self.macd = self.MACD()
        self.kdj = self.KDJ()
        self.rsi = self.RSI()
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

def get_strategy_function(strategy_name: str):
    """根据策略名称获取策略函数"""
    strategy_map = {
        'TRIPLE_CROSS': apply_triple_cross,
        'PRE_CROSS': apply_pre_cross,
        'MACD_ZERO_AXIS': apply_macd_zero_axis_strategy
    }
    return strategy_map.get(strategy_name)

def validate_strategy_config(strategy_name: str) -> tuple[bool, list]:
    """验证策略配置"""
    from strategy_config import config_manager
    return config_manager.validate_config(strategy_name)

def list_available_strategies() -> list:
    """列出可用的策略"""
    return ['TRIPLE_CROSS', 'PRE_CROSS', 'MACD_ZERO_AXIS']

def get_strategy_description(strategy_name: str) -> str:
    """获取策略描述"""
    descriptions = {
        'TRIPLE_CROSS': '三重金叉策略：MACD、KDJ、RSI同时金叉',
        'PRE_CROSS': '临界金叉策略：指标接近金叉的预警信号',
        'MACD_ZERO_AXIS': 'MACD零轴启动策略：MACD在零轴附近启动的信号'
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