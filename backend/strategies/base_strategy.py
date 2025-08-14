#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略基类定义
所有策略都应该继承此基类
"""

from abc import ABC, abstractmethod
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化策略
        
        Args:
            config: 策略配置参数
        """
        self.config = config or {}
        self.name = self.get_strategy_name()
        self.version = self.get_strategy_version()
        self.description = self.get_strategy_description()
        
        # 验证配置
        self.validate_config()
        
        #logger.info(f"策略初始化: {self.name} v{self.version}")
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass
    
    @abstractmethod
    def get_strategy_version(self) -> str:
        """获取策略版本"""
        pass
    
    @abstractmethod
    def get_strategy_description(self) -> str:
        """获取策略描述"""
        pass
    
    @abstractmethod
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """验证配置参数"""
        pass
    
    @abstractmethod
    def get_required_data_length(self) -> int:
        """获取所需的最小数据长度"""
        pass
    
    @abstractmethod
    def apply_strategy(self, df: pd.DataFrame) -> Tuple[Optional[pd.Series], Optional[Dict[str, Any]]]:
        """
        应用策略
        
        Args:
            df: 股票数据DataFrame，包含OHLCV数据
            
        Returns:
            tuple: (信号Series, 信号详情字典)
                  如果没有信号则返回 (None, None)
        """
        pass
    
    def preprocess_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        数据预处理
        子类可以重写此方法进行特定的数据预处理
        
        Args:
            df: 原始数据
            
        Returns:
            处理后的数据
        """
        return df.copy()
    
    def calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标
        子类可以重写此方法添加特定的技术指标
        
        Args:
            df: 股票数据
            
        Returns:
            添加了技术指标的数据
        """
        try:
            # 基础移动平均线
            for period in [5, 10, 20, 30, 60]:
                df[f'ma{period}'] = df['close'].rolling(window=period).mean()
            
            # RSI指标
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # MACD指标
            exp1 = df['close'].ewm(span=12).mean()
            exp2 = df['close'].ewm(span=26).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
            
            # 成交量移动平均
            df['volume_ma20'] = df['volume'].rolling(window=20).mean()
            df['volume_ma60'] = df['volume'].rolling(window=60).mean()
            
            return df
            
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
            return df
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """获取策略信息"""
        return {
            'name': self.name,
            'version': self.version,
            'description': self.description,
            'config': self.config,
            'required_data_length': self.get_required_data_length()
        }
    
    def convert_numpy_types(self, obj):
        """递归转换numpy类型为Python原生类型"""
        if isinstance(obj, dict):
            return {key: self.convert_numpy_types(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self.convert_numpy_types(item) for item in obj]
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj


class StrategyResult:
    """策略结果封装类"""
    
    def __init__(self, 
                 stock_code: str,
                 strategy_name: str,
                 signal_type: str,
                 signal_strength: int,
                 date: str,
                 current_price: float,
                 signal_details: Dict[str, Any]):
        self.stock_code = stock_code
        self.strategy_name = strategy_name
        self.signal_type = signal_type
        self.signal_strength = signal_strength
        self.date = date
        self.current_price = current_price
        self.signal_details = signal_details
        self.scan_timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        def convert_value(value):
            """转换值为JSON可序列化格式"""
            if isinstance(value, (np.integer, np.int64, np.int32)):
                return int(value)
            elif isinstance(value, (np.floating, np.float64, np.float32)):
                return float(value)
            elif isinstance(value, np.ndarray):
                return value.tolist()
            elif isinstance(value, pd.Series):
                return value.tolist()
            elif isinstance(value, pd.Timestamp):
                return value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [convert_value(v) for v in value]
            elif hasattr(value, 'item'):  # numpy scalar
                return value.item()
            return value
        
        return {
            'stock_code': str(self.stock_code),
            'strategy': str(self.strategy_name),
            'signal_type': str(self.signal_type),
            'signal_strength': int(self.signal_strength),
            'date': str(self.date),
            'scan_timestamp': str(self.scan_timestamp),
            'current_price': float(self.current_price),
            'signal_details': convert_value(self.signal_details)
        }
