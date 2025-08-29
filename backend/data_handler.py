#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一数据处理模块
功能：
1. 统一的股票数据加载入口
2. 统一的技术指标计算
3. 消除各模块间的数据处理代码重复
"""

import os
import pandas as pd
import struct
import logging
from typing import Optional
import data_loader
import indicators
from typing import List
from adjustment_processor import create_adjustment_config, create_adjustment_processor

from config import BASE_PATH, ENABLE_HK_STOCKS, ALL_MARKETS

# 配置日志
logger = logging.getLogger(__name__)

def _get_market_from_stock_code(stock_code: str) -> str:
    """
    根据股票代码确定市场
    
    Args:
        stock_code: 股票代码
        
    Returns:
        市场代码 ('sh', 'sz', 'bj', 'ds')
    """
    # 港股代码以数字+#开头，如 31#00700, 43#09988
    if '#' in stock_code:
        return 'ds'
    
    # A股代码
    prefix = stock_code[:2]
    if prefix in ['sh', 'sz', 'bj']:
        return prefix
    
    # 默认返回前两位作为市场代码
    return prefix

def _get_hk_price_divisor(stock_code: str) -> float:
    """
    根据港股代码确定价格除数
    
    Args:
        stock_code: 港股代码，如 31#00700
        
    Returns:
        价格除数
    """
    if not '#' in stock_code:
        return 100.0  # 非港股默认除数
    
    # 港股不同交易所可能有不同的价格除数
    prefix = stock_code.split('#')[0]
    
    # 根据前缀确定除数
    if prefix == '31':  # 港股主板
        return 1000.0
    elif prefix == '43':  # 港股创业板
        return 1000.0
    elif prefix == '48':  # 港股其他
        return 1000.0
    else:
        return 1000.0  # 默认港股除数

def get_full_data_with_indicators(stock_code: str, adjustment_type: str = 'forward', **indicator_params) -> Optional[pd.DataFrame]:
    """
    【统一数据入口】
    获取单只股票的完整历史数据，并计算好所有通用技术指标。
    
    Args:
        stock_code: 股票代码，如 'sh600006' 或 '31#01772'
        adjustment_type: 复权类型，'forward'(前复权), 'backward'(后复权), 'none'(不复权)
    
    Returns:
        包含所有技术指标的DataFrame，失败时返回None
    """
    try:
        # 检查是否为港股且港股功能是否启用
        if is_hk_stock(stock_code) and not ENABLE_HK_STOCKS:
            #logger.warning(f"港股功能未启用，跳过 {stock_code}")
            return None
        
        # 1. 加载数据 - 修复港股市场识别
        market = _get_market_from_stock_code(stock_code)
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
        if not os.path.exists(file_path):
            return None
        
        df = data_loader.get_daily_data(file_path, stock_code)
        if df is None or len(df) < 100:
            return None
        
        # 2. 复权处理
        if adjustment_type != 'none':
            adj_config = create_adjustment_config(adjustment_type)
            adj_processor = create_adjustment_processor(adj_config)
            df = adj_processor.process_data(df, stock_code)

        # 3. 计算所有通用技术指标
        df = calculate_all_indicators(df, stock_code, adjustment_type, **indicator_params)

        return df
    except Exception as e:
        logger.error(f"获取股票数据失败 {stock_code}: {e}")
        return None

def read_day_file(file_path: str, stock_code: str = None) -> Optional[pd.DataFrame]:
    """
    读取通达信.day文件，支持A股和港股
    
    Args:
        file_path: .day文件路径
        stock_code: 股票代码，用于确定价格除数
    
    Returns:
        DataFrame或None
    """
    try:
        # 根据市场确定价格除数
        if stock_code and '#' in stock_code:
            price_divisor = _get_hk_price_divisor(stock_code)
        else:
            price_divisor = 100.0  # A股默认除以100
        
        with open(file_path, 'rb') as f:
            data = []
            while True:
                chunk = f.read(32)  # 每条记录32字节
                if len(chunk) < 32:
                    break
                
                # 解析数据结构
                date, open_price, high, low, close, amount, volume, _ = struct.unpack('<IIIIIIII', chunk)
                
                # 转换日期格式
                year = date // 10000
                month = (date % 10000) // 100
                day = date % 100
                
                # 验证日期有效性
                if year < 1990 or year > 2030 or month < 1 or month > 12 or day < 1 or day > 31:
                    continue
                
                # 根据市场类型处理价格
                data.append({
                    'date': f"{year:04d}-{month:02d}-{day:02d}",
                    'open': open_price / price_divisor,
                    'high': high / price_divisor,
                    'low': low / price_divisor,
                    'close': close / price_divisor,
                    'volume': volume,
                    'amount': amount
                })
        
        if not data:
            return None
            
        # 转换为DataFrame
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True)
        
        # 数据质量检查
        df = df[df['close'] > 0]  # 过滤无效价格
        df = df.dropna()  # 删除空值
        
        return df
        
    except Exception as e:
        logger.error(f"读取文件失败 {file_path}: {e}")
        return None

def calculate_all_indicators(df: pd.DataFrame, stock_code: str, adjustment_type: str = 'forward', **indicator_params) -> pd.DataFrame:
    """
    计算所有通用技术指标
    
    Args:
        df: 股票数据DataFrame
        stock_code: 股票代码
        adjustment_type: 复权类型
    
    Returns:
        包含所有指标的DataFrame
    """
    try:
        # 基础均线指标 - 计算完整的MA系列 (7, 13, 30, 45, 60, 90, 150, 240)
        ma_periods = [7, 13, 30, 45, 60, 90, 150, 240]
        for period in ma_periods:
            df[f'ma{period}'] = indicators.calculate_ma(df, period)
        
        # 保持向后兼容性
        df['ma5'] = indicators.calculate_ma(df, 5)
        df['ma21'] = indicators.calculate_ma(df, 21)
        
        # 添加优化的均线
        ma_short = indicator_params.get('ma_short', 5)
        ma_long = indicator_params.get('ma_long', 21)
        if ma_short not in [5, 7, 13, 30, 45, 60, 90, 150, 240]:
            df[f'ma{ma_short}'] = indicators.calculate_ma(df, ma_short)
        if ma_long not in [5, 21, 7, 13, 30, 45, 60, 90, 150, 240]:
            df[f'ma{ma_long}'] = indicators.calculate_ma(df, ma_long)
        
        # 创建复权配置
        adjustment_config = create_adjustment_config(adjustment_type) if adjustment_type != 'none' else None
        
        # MACD指标 - 使用优化参数
        macd_fast = indicator_params.get('macd_fast', 12)
        macd_slow = indicator_params.get('macd_slow', 26)
        macd_config = indicators.MACDIndicatorConfig(
            fast_period=macd_fast,
            slow_period=macd_slow,
            adjustment_config=adjustment_config
        )
        df['dif'], df['dea'] = indicators.calculate_macd(df, config=macd_config, stock_code=stock_code)
        df['macd'] = df['dif'] - df['dea']
        
        # KDJ指标 - 使用优化参数
        kdj_n = indicator_params.get('kdj_n', 9)
        kdj_config = indicators.KDJIndicatorConfig(
            n_period=kdj_n,
            adjustment_config=adjustment_config
        )
        df['k'], df['d'], df['j'] = indicators.calculate_kdj(df, config=kdj_config, stock_code=stock_code, n=kdj_n)
        
        # RSI指标 - 使用优化参数
        rsi_period = indicator_params.get('rsi_period', 14)
        df['rsi6'] = indicators.calculate_rsi(df, 6)
        df['rsi12'] = indicators.calculate_rsi(df, 12)
        df['rsi24'] = indicators.calculate_rsi(df, 24)
        if rsi_period not in [6, 12, 24]:
            df[f'rsi{rsi_period}'] = indicators.calculate_rsi(df, rsi_period)
        
        # 布林带
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = indicators.calculate_bollinger_bands(df)
        
        return df
    except Exception as e:
        logger.error(f"计算技术指标失败 {stock_code}: {e}")
        return df

def get_stock_data_simple(stock_code: str) -> Optional[pd.DataFrame]:
    """
    简化版数据获取，只获取基础数据不计算指标
    
    Args:
        stock_code: 股票代码
    
    Returns:
        基础数据DataFrame或None
    """
    try:
        # 检查是否为港股且港股功能是否启用
        if is_hk_stock(stock_code) and not ENABLE_HK_STOCKS:
            #logger.warning(f"港股功能未启用，跳过 {stock_code}")
            return None
            
        market = _get_market_from_stock_code(stock_code)
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
        return read_day_file(file_path, stock_code)
    except Exception as e:
        logger.error(f"获取股票基础数据失败 {stock_code}: {e}")
        return None
    
def get_all_stock_codes_from_filesystem(include_hk: bool = None) -> List[str]:
    """
    从本地数据目录扫描所有股票代码
    
    Args:
        include_hk: 是否包含港股，None时使用全局配置
    
    Returns:
        股票代码列表
    """
    all_codes = []
    
    # 确定是否包含港股
    if include_hk is None:
        include_hk = ENABLE_HK_STOCKS
    
    # 基础市场
    market_folders = {
        'sh': 'lday',
        'sz': 'lday',
        'bj': 'lday',  # 北交所
    }
    
    # 如果启用港股，添加港股市场
    if include_hk:
        market_folders['ds'] = 'lday'  # 港股
    
    for market, folder in market_folders.items():
        market_path = os.path.join(BASE_PATH, market, folder)
        if not os.path.isdir(market_path):
            continue
        
        for filename in os.listdir(market_path):
            if filename.endswith('.day'):
                stock_code = filename.split('.')[0]
                all_codes.append(stock_code)
                
    return all_codes

def get_hk_stock_codes() -> List[str]:
    """
    获取所有港股代码
    
    Returns:
        港股代码列表，如果港股功能未启用则返回空列表
    """
    if not ENABLE_HK_STOCKS:
        logger.info("港股功能未启用")
        return []
        
    hk_codes = []
    ds_path = os.path.join(BASE_PATH, 'ds', 'lday')
    
    if os.path.isdir(ds_path):
        for filename in os.listdir(ds_path):
            if filename.endswith('.day') and '#' in filename:
                stock_code = filename.split('.')[0]
                hk_codes.append(stock_code)
    
    return sorted(hk_codes)

def is_hk_stock(stock_code: str) -> bool:
    """判断是否为港股代码"""
    return '#' in stock_code

def get_stock_market_info(stock_code: str) -> dict:
    """获取股票市场信息"""
    market = _get_market_from_stock_code(stock_code)
    
    market_info = {
        'code': stock_code,
        'market': market,
        'is_hk': is_hk_stock(stock_code),
        'hk_enabled': ENABLE_HK_STOCKS,
        'price_divisor': _get_hk_price_divisor(stock_code) if is_hk_stock(stock_code) else 100.0
    }
    
    if is_hk_stock(stock_code):
        prefix = stock_code.split('#')[0]
        market_info['hk_prefix'] = prefix
        market_info['hk_code'] = stock_code.split('#')[1]
        
        # 港股市场分类
        if prefix == '31':
            market_info['hk_market'] = '港股主板'
        elif prefix == '43':
            market_info['hk_market'] = '港股创业板'
        elif prefix == '48':
            market_info['hk_market'] = '港股其他'
        else:
            market_info['hk_market'] = '港股未知'
    
    return market_info

def get_data_handler_config() -> dict:
    """获取数据处理器配置信息"""
    return {
        'hk_stocks_enabled': ENABLE_HK_STOCKS,
        'supported_markets': ALL_MARKETS,
        'base_path': BASE_PATH,
        'hk_stock_count': len(get_hk_stock_codes()) if ENABLE_HK_STOCKS else 0,
        'total_stock_count': len(get_all_stock_codes_from_filesystem())
    }

def set_hk_stocks_enabled(enabled: bool):
    """
    动态设置港股功能开关（仅在当前会话有效）
    
    Args:
        enabled: 是否启用港股功能
    """
    global ENABLE_HK_STOCKS
    import config
    config.ENABLE_HK_STOCKS = enabled
    logger.info(f"港股功能已{'启用' if enabled else '禁用'}")

def filter_stocks_by_market(stock_codes: List[str], include_hk: bool = None) -> List[str]:
    """
    根据市场配置过滤股票代码
    
    Args:
        stock_codes: 股票代码列表
        include_hk: 是否包含港股，None时使用全局配置
    
    Returns:
        过滤后的股票代码列表
    """
    if include_hk is None:
        include_hk = ENABLE_HK_STOCKS
    
    if include_hk:
        return stock_codes
    else:
        return [code for code in stock_codes if not is_hk_stock(code)]

def test_hk_data_loading():
    """测试港股数据加载功能"""
    print("=== 港股数据加载测试 ===")
    
    # 显示配置信息
    config_info = get_data_handler_config()
    print(f"配置信息: {config_info}")
    
    if not ENABLE_HK_STOCKS:
        print("港股功能未启用，测试跳过")
        return
    
    # 获取港股代码列表
    hk_codes = get_hk_stock_codes()
    print(f"发现港股数量: {len(hk_codes)}")
    
    if hk_codes:
        # 测试前3只港股
        test_codes = hk_codes[:3]
        print(f"测试股票: {test_codes}")
        
        for code in test_codes:
            print(f"\n--- 测试 {code} ---")
            
            # 获取市场信息
            market_info = get_stock_market_info(code)
            print(f"市场信息: {market_info}")
            
            # 加载数据
            df = get_full_data_with_indicators(code)
            if df is not None:
                print(f"数据行数: {len(df)}")
                print(f"日期范围: {df.index[0]} 到 {df.index[-1]}")
                print(f"最新价格: {df['close'].iloc[-1]:.3f}")
                print(f"包含指标: {[col for col in df.columns if col not in ['open', 'high', 'low', 'close', 'volume', 'amount']]}")
            else:
                print("数据加载失败")
    else:
        print("未找到港股数据")

def test_configurable_loading():
    """测试可配置的数据加载功能"""
    print("\n=== 可配置数据加载测试 ===")
    
    # 测试不同配置下的股票数量
    all_stocks = get_all_stock_codes_from_filesystem(include_hk=True)
    a_stocks_only = get_all_stock_codes_from_filesystem(include_hk=False)
    
    print(f"包含港股的总股票数: {len(all_stocks)}")
    print(f"仅A股的股票数: {len(a_stocks_only)}")
    print(f"港股数量: {len(all_stocks) - len(a_stocks_only)}")
    
    # 测试过滤功能
    sample_codes = ['sh600000', '31#00700', 'sz000001', '43#09988']
    filtered_no_hk = filter_stocks_by_market(sample_codes, include_hk=False)
    filtered_with_hk = filter_stocks_by_market(sample_codes, include_hk=True)
    
    print(f"\n原始代码: {sample_codes}")
    print(f"不含港股: {filtered_no_hk}")
    print(f"包含港股: {filtered_with_hk}")

if __name__ == "__main__":
    test_hk_data_loading()
    test_configurable_loading()