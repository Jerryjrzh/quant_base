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

from config import BASE_PATH

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
    # 港股代码以数字+#开头
    if '#' in stock_code:
        return 'ds'
    
    # A股代码
    prefix = stock_code[:2]
    if prefix in ['sh', 'sz', 'bj']:
        return prefix
    
    # 默认返回前两位作为市场代码
    return prefix

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
    读取通达信.day文件
    
    Args:
        file_path: .day文件路径
        stock_code: 股票代码，用于确定价格除数
    
    Returns:
        DataFrame或None
    """
    try:
        # 根据市场确定价格除数
        price_divisor = 100.0  # A股默认除以100
        if stock_code and '#' in stock_code:
            # 港股价格除数可能不同，先尝试1000
            price_divisor = 1000.0
        
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
        market = _get_market_from_stock_code(stock_code)
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
        return read_day_file(file_path, stock_code)
    except Exception as e:
        logger.error(f"获取股票基础数据失败 {stock_code}: {e}")
        return None
    
def get_all_stock_codes_from_filesystem() -> List[str]:
    """从本地数据目录扫描所有A股和港股的股票代码"""
    all_codes = []
    market_folders = {
        'sh': 'lday',
        'sz': 'lday',
        'ds': 'lday' # 港股
    }
    
    for market, folder in market_folders.items():
        market_path = os.path.join(BASE_PATH, market, folder)
        if not os.path.isdir(market_path):
            continue
        
        for filename in os.listdir(market_path):
            if filename.endswith('.day'):
                stock_code = filename.split('.')[0]
                all_codes.append(stock_code)
                
    return all_codes    