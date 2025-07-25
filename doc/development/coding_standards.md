# 代码规范指南

## 🎯 概览

本文档定义了股票筛选与分析平台的代码规范和最佳实践，确保代码的一致性、可读性和可维护性。

## 🐍 Python代码规范

### 1. 基础规范

#### PEP 8 遵循
严格遵循 [PEP 8](https://www.python.org/dev/peps/pep-0008/) 规范：

```python
# ✅ 正确示例
def calculate_macd(df: pd.DataFrame, fast_period: int = 12, 
                   slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """
    计算MACD指标
    
    Args:
        df: 包含close列的DataFrame
        fast_period: 快速EMA周期
        slow_period: 慢速EMA周期
        signal_period: 信号线EMA周期
    
    Returns:
        包含MACD指标的DataFrame
    """
    close = df['close']
    
    # 计算指数移动平均线
    ema_fast = close.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close.ewm(span=slow_period, adjust=False).mean()
    
    # 计算MACD线
    macd = ema_fast - ema_slow
    
    return pd.DataFrame({
        'macd': macd,
        'macd_signal': macd.ewm(span=signal_period, adjust=False).mean(),
        'macd_histogram': macd - macd.ewm(span=signal_period, adjust=False).mean()
    })

# ❌ 错误示例
def calc_macd(df,fast=12,slow=26,sig=9):
    c=df['close']
    f=c.ewm(span=fast).mean()
    s=c.ewm(span=slow).mean()
    m=f-s
    return pd.DataFrame({'macd':m,'signal':m.ewm(span=sig).mean()})
```

#### 命名规范

```python
# 变量和函数名：snake_case
stock_symbol = "000001"
current_price = 10.50
signal_strength = 85

def analyze_triple_cross(df: pd.DataFrame) -> dict:
    pass

def calculate_technical_indicators(data: pd.DataFrame) -> dict:
    pass

# 常量：UPPER_CASE
MAX_POSITION_SIZE = 0.2
DEFAULT_SIGNAL_THRESHOLD = 70
TRADING_COMMISSION_RATE = 0.0003

# 类名：PascalCase
class DataLoader:
    pass

class StrategyAnalyzer:
    pass

class BacktestingEngine:
    pass

# 私有方法和变量：前缀下划线
class TradingSystem:
    def __init__(self):
        self._positions = {}
        self._trade_history = []
    
    def _calculate_position_size(self, signal_strength: float) -> float:
        pass
    
    def _validate_trade_conditions(self) -> bool:
        pass

# 模块级私有：前缀下划线
_DEFAULT_CONFIG = {}
_CACHE_INSTANCE = None

def _internal_helper_function():
    pass
```

### 2. 类型注解

#### 强制使用类型注解

```python
from typing import Dict, List, Optional, Union, Tuple, Callable
import pandas as pd
from datetime import datetime

# ✅ 正确示例
def load_stock_data(symbol: str, start_date: Optional[str] = None) -> pd.DataFrame:
    """加载股票数据"""
    pass

def analyze_signals(data: Dict[str, pd.DataFrame]) -> List[dict]:
    """分析交易信号"""
    pass

def execute_strategy(strategy_func: Callable[[pd.DataFrame], dict], 
                    data: pd.DataFrame) -> dict:
    """执行策略分析"""
    pass

class Position:
    def __init__(self, symbol: str, shares: int, price: float, 
                 buy_date: datetime):
        self.symbol: str = symbol
        self.shares: int = shares
        self.price: float = price
        self.buy_date: datetime = buy_date
        self.can_sell: bool = False

# 复杂类型定义
SignalResult = Dict[str, Union[bool, float, str, Dict[str, float]]]
StrategyConfig = Dict[str, Dict[str, Union[int, float, bool]]]
BacktestResult = Dict[str, Union[float, int, List[dict], Dict[str, float]]]

def run_backtest(config: StrategyConfig) -> BacktestResult:
    pass
```

#### 自定义类型定义

```python
from typing import TypedDict, NewType
from enum import Enum

# 使用TypedDict定义结构化数据
class TradingSignal(TypedDict):
    symbol: str
    action: str
    price: float
    confidence: float
    timestamp: str
    reason: str

class PerformanceMetrics(TypedDict):
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float

# 使用NewType创建语义化类型
StockSymbol = NewType('StockSymbol', str)
Price = NewType('Price', float)
Percentage = NewType('Percentage', float)

def get_current_price(symbol: StockSymbol) -> Price:
    pass

# 使用Enum定义常量
class TradingAction(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    OBSERVE = "OBSERVE"

class TrendExpectation(Enum):
    STRONG_UP = "STRONG_UP"
    WEAK_UP = "WEAK_UP"
    SIDEWAYS = "SIDEWAYS"
    WEAK_DOWN = "WEAK_DOWN"
    STRONG_DOWN = "STRONG_DOWN"
```

### 3. 文档字符串规范

#### Google风格文档字符串

```python
def analyze_triple_cross(df: pd.DataFrame, config: dict) -> dict:
    """
    分析三线交叉策略信号
    
    该函数实现三线交叉策略的核心逻辑，通过分析MACD、KDJ、RSI三个
    技术指标的交叉情况来生成买入信号。
    
    Args:
        df: 股票历史数据，必须包含open, high, low, close, volume列
        config: 策略配置参数，包含以下键值：
            - macd: MACD参数配置 {'fast_period': 12, 'slow_period': 26}
            - kdj: KDJ参数配置 {'period': 27, 'k_smooth': 3}
            - rsi: RSI参数配置 {'period': 14}
            - signal_threshold: 信号强度阈值，默认70
    
    Returns:
        策略分析结果字典，包含以下键值：
            - signal: bool, 是否有买入信号
            - strength: float, 信号强度 (0-100)
            - conditions: dict, 各项条件的满足情况
            - indicators: dict, 最新的技术指标值
            - risk_factors: list, 风险因素列表
    
    Raises:
        ValueError: 当输入数据不足或格式错误时
        KeyError: 当配置参数缺失时
    
    Example:
        >>> df = load_stock_data("000001")
        >>> config = {
        ...     'macd': {'fast_period': 12, 'slow_period': 26},
        ...     'kdj': {'period': 27},
        ...     'rsi': {'period': 14},
        ...     'signal_threshold': 70
        ... }
        >>> result = analyze_triple_cross(df, config)
        >>> print(f"信号: {result['signal']}, 强度: {result['strength']}")
        信号: True, 强度: 85.5
    
    Note:
        - 该策略适用于中短期交易
        - 建议结合成交量分析使用
        - 在震荡市场中可能产生较多假信号
    """
    pass

class BacktestingSystem:
    """
    回测系统核心类
    
    提供完整的策略回测功能，支持多种性能指标计算和风险分析。
    
    Attributes:
        initial_capital: 初始资金
        current_cash: 当前现金
        positions: 当前持仓字典
        trade_history: 交易历史记录
        commission_rate: 手续费率
    
    Example:
        >>> backtester = BacktestingSystem(initial_capital=100000)
        >>> result = backtester.run_backtest(strategy_func, data, config)
        >>> print(f"总收益率: {result['performance']['total_return']:.2%}")
    """
    
    def __init__(self, initial_capital: float = 100000.0):
        """
        初始化回测系统
        
        Args:
            initial_capital: 初始资金，默认10万元
        """
        pass
    
    def run_backtest(self, strategy_func: Callable, data: pd.DataFrame, 
                     config: dict) -> dict:
        """
        运行回测
        
        Args:
            strategy_func: 策略函数，接受DataFrame和config，返回信号字典
            data: 历史数据
            config: 策略配置
        
        Returns:
            回测结果字典
        """
        pass
```

### 4. 错误处理规范

#### 异常定义和使用

```python
# 自定义异常类
class StockAnalysisError(Exception):
    """股票分析基础异常类"""
    pass

class DataLoadError(StockAnalysisError):
    """数据加载异常"""
    pass

class StrategyAnalysisError(StockAnalysisError):
    """策略分析异常"""
    pass

class BacktestError(StockAnalysisError):
    """回测异常"""
    pass

class ConfigurationError(StockAnalysisError):
    """配置错误异常"""
    pass

# 异常使用示例
def load_stock_data(symbol: str) -> pd.DataFrame:
    """加载股票数据"""
    
    if not symbol:
        raise ValueError("股票代码不能为空")
    
    if not isinstance(symbol, str):
        raise TypeError(f"股票代码必须是字符串，得到: {type(symbol)}")
    
    file_path = f"data/vipdoc/{symbol[:2]}/{symbol}.day"
    
    try:
        df = pd.read_csv(file_path, sep='\t', header=None)
        
        if df.empty:
            raise DataLoadError(f"股票 {symbol} 数据为空")
        
        return df
        
    except FileNotFoundError:
        raise DataLoadError(f"股票 {symbol} 数据文件不存在: {file_path}")
    
    except pd.errors.ParserError as e:
        raise DataLoadError(f"股票 {symbol} 数据格式错误: {str(e)}")
    
    except Exception as e:
        raise DataLoadError(f"加载股票 {symbol} 数据时发生未知错误: {str(e)}")

# 错误处理最佳实践
def analyze_strategy_with_error_handling(symbol: str, config: dict) -> dict:
    """带错误处理的策略分析"""
    
    try:
        # 数据加载
        df = load_stock_data(symbol)
        logger.info(f"成功加载 {symbol} 数据: {len(df)} 条记录")
        
        # 参数验证
        if not config:
            raise ConfigurationError("策略配置不能为空")
        
        # 策略分析
        result = analyze_triple_cross(df, config)
        logger.info(f"{symbol} 策略分析完成: 信号={result['signal']}")
        
        return result
        
    except DataLoadError as e:
        logger.error(f"数据加载失败: {str(e)}")
        return {'error': 'data_load_failed', 'message': str(e)}
    
    except StrategyAnalysisError as e:
        logger.error(f"策略分析失败: {str(e)}")
        return {'error': 'strategy_analysis_failed', 'message': str(e)}
    
    except Exception as e:
        logger.error(f"未知错误: {str(e)}", exc_info=True)
        return {'error': 'unknown_error', 'message': str(e)}
```

### 5. 日志记录规范

#### 日志配置和使用

```python
import logging
import sys
from datetime import datetime
from pathlib import Path

# 日志配置
def setup_logging(name: str, level: str = "INFO", 
                 log_file: str = None) -> logging.Logger:
    """
    配置日志系统
    
    Args:
        name: 日志器名称
        level: 日志级别
        log_file: 日志文件路径
    
    Returns:
        配置好的日志器
    """
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器
    if log_file:
        # 确保日志目录存在
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

# 日志使用示例
logger = setup_logging(__name__, "INFO", "logs/strategy_analysis.log")

def analyze_stock_with_logging(symbol: str) -> dict:
    """带日志记录的股票分析"""
    
    logger.info(f"开始分析股票: {symbol}")
    
    try:
        # 数据加载
        logger.debug(f"加载 {symbol} 数据...")
        df = load_stock_data(symbol)
        logger.info(f"成功加载 {symbol} 数据: {len(df)} 条记录")
        
        # 指标计算
        logger.debug("计算技术指标...")
        indicators = calculate_indicators(df)
        logger.debug(f"指标计算完成: {list(indicators.keys())}")
        
        # 策略分析
        logger.debug("执行策略分析...")
        result = analyze_strategy(df, indicators)
        
        if result['signal']:
            logger.info(f"🟢 {symbol} 产生买入信号: 强度={result['strength']:.1f}")
        else:
            logger.debug(f"🔴 {symbol} 无信号: 强度={result['strength']:.1f}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ {symbol} 分析失败: {str(e)}", exc_info=True)
        raise

# 性能日志记录
import time
from functools import wraps

def log_performance(func):
    """性能日志装饰器"""
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.debug(f"开始执行 {func.__name__}")
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            logger.info(f"✅ {func.__name__} 执行完成: {execution_time:.3f}秒")
            
            # 性能警告
            if execution_time > 10:
                logger.warning(f"⚠️  {func.__name__} 执行时间过长: {execution_time:.3f}秒")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"❌ {func.__name__} 执行失败: {execution_time:.3f}秒, 错误: {str(e)}")
            raise
    
    return wrapper

# 使用示例
@log_performance
def batch_analyze_stocks(symbols: List[str]) -> List[dict]:
    """批量分析股票"""
    results = []
    
    for symbol in symbols:
        try:
            result = analyze_stock_with_logging(symbol)
            results.append(result)
        except Exception as e:
            logger.error(f"跳过 {symbol}: {str(e)}")
    
    logger.info(f"批量分析完成: {len(results)}/{len(symbols)} 成功")
    return results
```

### 6. 配置管理规范

#### 配置类设计

```python
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import json
import os
from pathlib import Path

@dataclass
class MACDConfig:
    """MACD指标配置"""
    fast_period: int = 12
    slow_period: int = 26
    signal_period: int = 9
    
    def __post_init__(self):
        if self.fast_period >= self.slow_period:
            raise ValueError("快线周期必须小于慢线周期")

@dataclass
class KDJConfig:
    """KDJ指标配置"""
    period: int = 27
    k_smooth: int = 3
    d_smooth: int = 3
    
    def __post_init__(self):
        if self.period <= 0:
            raise ValueError("KDJ周期必须大于0")

@dataclass
class StrategyConfig:
    """策略配置"""
    name: str
    enabled: bool = True
    macd: MACDConfig = field(default_factory=MACDConfig)
    kdj: KDJConfig = field(default_factory=KDJConfig)
    rsi_period: int = 14
    signal_threshold: float = 70.0
    
    @classmethod
    def from_dict(cls, data: dict) -> 'StrategyConfig':
        """从字典创建配置"""
        macd_config = MACDConfig(**data.get('macd', {}))
        kdj_config = KDJConfig(**data.get('kdj', {}))
        
        return cls(
            name=data['name'],
            enabled=data.get('enabled', True),
            macd=macd_config,
            kdj=kdj_config,
            rsi_period=data.get('rsi_period', 14),
            signal_threshold=data.get('signal_threshold', 70.0)
        )
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'name': self.name,
            'enabled': self.enabled,
            'macd': {
                'fast_period': self.macd.fast_period,
                'slow_period': self.macd.slow_period,
                'signal_period': self.macd.signal_period
            },
            'kdj': {
                'period': self.kdj.period,
                'k_smooth': self.kdj.k_smooth,
                'd_smooth': self.kdj.d_smooth
            },
            'rsi_period': self.rsi_period,
            'signal_threshold': self.signal_threshold
        }

class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = "config/strategies.json"):
        self.config_file = Path(config_file)
        self.strategies: Dict[str, StrategyConfig] = {}
        self.load_config()
    
    def load_config(self) -> None:
        """加载配置文件"""
        if not self.config_file.exists():
            logger.warning(f"配置文件不存在: {self.config_file}")
            self._create_default_config()
            return
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for name, config_data in data.get('strategies', {}).items():
                config_data['name'] = name
                self.strategies[name] = StrategyConfig.from_dict(config_data)
            
            logger.info(f"成功加载配置: {len(self.strategies)} 个策略")
            
        except Exception as e:
            logger.error(f"加载配置失败: {str(e)}")
            self._create_default_config()
    
    def save_config(self) -> None:
        """保存配置文件"""
        try:
            # 确保目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {
                'strategies': {
                    name: config.to_dict() 
                    for name, config in self.strategies.items()
                }
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"配置已保存: {self.config_file}")
            
        except Exception as e:
            logger.error(f"保存配置失败: {str(e)}")
    
    def get_strategy_config(self, name: str) -> Optional[StrategyConfig]:
        """获取策略配置"""
        return self.strategies.get(name)
    
    def update_strategy_config(self, name: str, config: StrategyConfig) -> None:
        """更新策略配置"""
        self.strategies[name] = config
        self.save_config()
        logger.info(f"策略配置已更新: {name}")
    
    def _create_default_config(self) -> None:
        """创建默认配置"""
        self.strategies = {
            'TRIPLE_CROSS': StrategyConfig(
                name='TRIPLE_CROSS',
                enabled=True,
                signal_threshold=70.0
            ),
            'PRE_CROSS': StrategyConfig(
                name='PRE_CROSS',
                enabled=True,
                signal_threshold=60.0
            )
        }
        self.save_config()
```

## 🧪 测试规范

### 1. 单元测试

```python
import unittest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from backend.indicators import calculate_macd, calculate_kdj
from backend.strategies import analyze_triple_cross
from backend.data_loader import DataLoader

class TestIndicators(unittest.TestCase):
    """技术指标测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 创建测试数据
        dates = pd.date_range('2023-01-01', periods=100, freq='D')
        np.random.seed(42)  # 确保结果可重现
        
        prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        
        self.test_data = pd.DataFrame({
            'open': prices + np.random.randn(100) * 0.1,
            'high': prices + np.abs(np.random.randn(100) * 0.2),
            'low': prices - np.abs(np.random.randn(100) * 0.2),
            'close': prices,
            'volume': np.random.randint(1000, 10000, 100)
        }, index=dates)
    
    def test_calculate_macd_basic(self):
        """测试MACD基本计算"""
        result = calculate_macd(self.test_data)
        
        # 检查返回结果结构
        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn('macd', result.columns)
        self.assertIn('macd_signal', result.columns)
        self.assertIn('macd_histogram', result.columns)
        
        # 检查数据长度
        self.assertEqual(len(result), len(self.test_data))
        
        # 检查数值合理性
        self.assertFalse(result['macd'].isna().all())
        self.assertFalse(result['macd_signal'].isna().all())
    
    def test_calculate_macd_custom_params(self):
        """测试MACD自定义参数"""
        result = calculate_macd(self.test_data, fast_period=8, slow_period=21, signal_period=5)
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), len(self.test_data))
    
    def test_calculate_macd_invalid_params(self):
        """测试MACD无效参数"""
        with self.assertRaises(ValueError):
            calculate_macd(self.test_data, fast_period=26, slow_period=12)  # 快线周期大于慢线
    
    def test_calculate_macd_empty_data(self):
        """测试MACD空数据"""
        empty_df = pd.DataFrame()
        
        with self.assertRaises(ValueError):
            calculate_macd(empty_df)
    
    def test_calculate_kdj_basic(self):
        """测试KDJ基本计算"""
        result = calculate_kdj(self.test_data)
        
        # 检查返回结果
        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn('k', result.columns)
        self.assertIn('d', result.columns)
        self.assertIn('j', result.columns)
        
        # 检查数值范围 (K和D应该在0-100之间)
        self.assertTrue((result['k'] >= 0).all() or result['k'].isna().any())
        self.assertTrue((result['k'] <= 100).all() or result['k'].isna().any())

class TestStrategies(unittest.TestCase):
    """策略测试类"""
    
    def setUp(self):
        """测试前准备"""
        # 创建测试数据
        dates = pd.date_range('2023-01-01', periods=50, freq='D')
        self.test_data = pd.DataFrame({
            'open': [100] * 50,
            'high': [105] * 50,
            'low': [95] * 50,
            'close': list(range(100, 150)),  # 上升趋势
            'volume': [1000] * 50
        }, index=dates)
        
        self.test_config = {
            'macd': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
            'kdj': {'period': 27, 'k_smooth': 3, 'd_smooth': 3},
            'rsi': {'period': 14},
            'signal_threshold': 70
        }
    
    def test_analyze_triple_cross_basic(self):
        """测试三线交叉基本功能"""
        result = analyze_triple_cross(self.test_data, self.test_config)
        
        # 检查返回结果结构
        self.assertIsInstance(result, dict)
        self.assertIn('signal', result)
        self.assertIn('strength', result)
        self.assertIn('conditions', result)
        self.assertIn('indicators', result)
        
        # 检查数据类型
        self.assertIsInstance(result['signal'], bool)
        self.assertIsInstance(result['strength'], (int, float))
        self.assertIsInstance(result['conditions'], dict)
    
    def test_analyze_triple_cross_signal_strength(self):
        """测试信号强度计算"""
        result = analyze_triple_cross(self.test_data, self.test_config)
        
        # 信号强度应该在0-100之间
        self.assertGreaterEqual(result['strength'], 0)
        self.assertLessEqual(result['strength'], 100)
    
    @patch('backend.indicators.calculate_macd')
    def test_analyze_triple_cross_with_mock(self, mock_macd):
        """使用Mock测试策略分析"""
        # 设置Mock返回值
        mock_macd.return_value = pd.DataFrame({
            'macd': [0.5],
            'macd_signal': [0.3],
            'macd_histogram': [0.2]
        })
        
        result = analyze_triple_cross(self.test_data, self.test_config)
        
        # 验证Mock被调用
        mock_macd.assert_called_once()
        
        # 验证结果
        self.assertIsInstance(result, dict)

class TestDataLoader(unittest.TestCase):
    """数据加载器测试类"""
    
    def setUp(self):
        self.loader = DataLoader("test_data")
    
    @patch('os.path.exists')
    @patch('pandas.read_csv')
    def test_load_stock_data_success(self, mock_read_csv, mock_exists):
        """测试成功加载股票数据"""
        # 设置Mock
        mock_exists.return_value = True
        mock_read_csv.return_value = pd.DataFrame({
            'date': ['20230101', '20230102'],
            'open': [1000, 1010],
            'high': [1050, 1060],
            'low': [990, 1000],
            'close': [1020, 1030],
            'volume': [100000, 110000]
        })
        
        # 执行测试
        result = self.loader.load_stock_data('000001')
        
        # 验证结果
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        
        # 验证Mock调用
        mock_exists.assert_called()
        mock_read_csv.assert_called_once()
    
    @patch('os.path.exists')
    def test_load_stock_data_file_not_found(self, mock_exists):
        """测试文件不存在的情况"""
        mock_exists.return_value = False
        
        with self.assertRaises(FileNotFoundError):
            self.loader.load_stock_data('999999')

# 集成测试
class TestIntegration(unittest.TestCase):
    """集成测试类"""
    
    def test_complete_analysis_workflow(self):
        """测试完整分析流程"""
        # 这里测试从数据加载到策略分析的完整流程
        pass

# 性能测试
class TestPerformance(unittest.TestCase):
    """性能测试类"""
    
    def test_large_dataset_performance(self):
        """测试大数据集性能"""
        # 创建大数据集
        large_data = pd.DataFrame({
            'close': np.random.randn(10000)
        })
        
        import time
        start_time = time.time()
        
        result = calculate_macd(large_data)
        
        execution_time = time.time() - start_time
        
        # 性能要求：10000条数据处理时间应小于1秒
        self.assertLess(execution_time, 1.0)
        self.assertEqual(len(result), 10000)

if __name__ == '__main__':
    # 运行测试
    unittest.main(verbosity=2)
```

### 2. 测试配置

#### pytest配置 (pytest.ini)

```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --verbose
    --tb=short
    --cov=backend
    --cov-report=html
    --cov-report=term-missing
    --cov-fail-under=80
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    unit: marks tests as unit tests
```

#### 测试运行脚本

```bash
#!/bin/bash
# run_tests.sh

echo "🧪 运行测试套件..."

# 设置环境变量
export PYTHONPATH=$(pwd)
export TESTING=true

# 运行不同类型的测试
echo "📋 运行单元测试..."
pytest tests/unit/ -v --cov=backend --cov-report=html

echo "🔗 运行集成测试..."
pytest tests/integration/ -v

echo "⚡ 运行性能测试..."
pytest tests/performance/ -v -m "not slow"

echo "🎯 生成测试报告..."
coverage html -d htmlcov

echo "✅ 测试完成！"
echo "📊 查看覆盖率报告: htmlcov/index.html"
```

## 📝 代码审查规范

### 1. 审查清单

#### 功能性审查
- [ ] 代码是否实现了预期功能？
- [ ] 边界条件是否正确处理？
- [ ] 错误处理是否完善？
- [ ] 性能是否满足要求？

#### 代码质量审查
- [ ] 命名是否清晰有意义？
- [ ] 函数是否单一职责？
- [ ] 代码是否遵循DRY原则？
- [ ] 是否有适当的注释和文档？

#### 安全性审查
- [ ] 是否有SQL注入风险？
- [ ] 输入验证是否充分？
- [ ] 敏感信息是否正确处理？
- [ ] 权限控制是否合理？

#### 可维护性审查
- [ ] 代码结构是否清晰？
- [ ] 依赖关系是否合理？
- [ ] 是否便于测试？
- [ ] 是否便于扩展？

### 2. 审查工具配置

#### pre-commit配置 (.pre-commit-config.yaml)

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 23.7.0
    hooks:
      - id: black
        language_version: python3.9

  - repo: https://github.com/pycqa/flake8
    rev: 6.0.0
    hooks:
      - id: flake8
        args: [--max-line-length=88, --extend-ignore=E203,W503]

  - repo: https://github.com/pycqa/isort
    rev: 5.12.0
    hooks:
      - id: isort
        args: [--profile=black]

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.4.1
    hooks:
      - id: mypy
        additional_dependencies: [types-requests, types-redis]

  - repo: https://github.com/pycqa/bandit
    rev: 1.7.5
    hooks:
      - id: bandit
        args: [-r, backend/, -f, json, -o, bandit-report.json]

  - repo: local
    hooks:
      - id: pytest
        name: pytest
        entry: pytest
        language: system
        pass_filenames: false
        always_run: true
        args: [tests/unit/, --tb=short]
```

## 🚀 持续集成规范

### GitHub Actions配置

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, '3.10']

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install -r requirements-dev.txt

    - name: Lint with flake8
      run: |
        flake8 backend/ --count --select=E9,F63,F7,F82 --show-source --statistics
        flake8 backend/ --count --exit-zero --max-complexity=10 --max-line-length=88 --statistics

    - name: Format check with black
      run: |
        black --check backend/

    - name: Type check with mypy
      run: |
        mypy backend/

    - name: Test with pytest
      run: |
        pytest tests/ --cov=backend --cov-report=xml

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
        flags: unittests
        name: codecov-umbrella

  security:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Run Bandit Security Scan
      run: |
        pip install bandit
        bandit -r backend/ -f json -o bandit-report.json

    - name: Upload security scan results
      uses: actions/upload-artifact@v3
      with:
        name: bandit-report
        path: bandit-report.json
```

通过遵循这些代码规范，可以确保项目代码的高质量、可维护性和团队协作效率。规范不仅提高了代码质量，也为项目的长期发展奠定了坚实的基础。