# 核心模块实现文档

## 🎯 模块概览

核心模块是系统的基础组件，提供数据处理、策略分析、回测验证等核心功能。

## 📊 数据处理模块

### DataLoader (data_loader.py)

#### 功能描述
负责加载和解析各种格式的股票数据文件，支持.day和.lc5格式。

#### 核心类和方法

```python
class DataLoader:
    def __init__(self, data_path: str = "data/vipdoc"):
        self.data_path = data_path
        self.cache = {}
    
    def load_stock_data(self, symbol: str, period: str = "daily") -> pd.DataFrame:
        """加载股票数据"""
        
    def load_5min_data(self, symbol: str) -> pd.DataFrame:
        """加载5分钟数据"""
        
    def get_stock_list(self) -> List[str]:
        """获取所有可用股票列表"""
        
    def validate_data(self, df: pd.DataFrame) -> bool:
        """验证数据完整性"""
```

#### 数据格式支持

**日线数据 (.day格式)**:
```
日期(YYYYMMDD) 开盘价 最高价 最低价 收盘价 成交量 成交额
20250101      1000   1050   990    1020   100000  102000000
```

**5分钟数据 (.lc5格式)**:
```
时间戳 开盘价 最高价 最低价 收盘价 成交量
```

#### 使用示例
```python
# 初始化数据加载器
loader = DataLoader("data/vipdoc")

# 加载日线数据
daily_data = loader.load_stock_data("000001", "daily")

# 加载5分钟数据
min5_data = loader.load_5min_data("000001")

# 获取股票列表
stock_list = loader.get_stock_list()
```

### IndicatorCalculator (indicators.py)

#### 功能描述
计算各种技术指标，包括MACD、KDJ、RSI、移动平均线等。

#### 核心指标实现

**MACD指标**:
```python
def calculate_macd(df: pd.DataFrame, fast_period: int = 12, 
                   slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """
    计算MACD指标
    
    Returns:
        DataFrame with columns: macd, macd_signal, macd_histogram
    """
    close = df['close']
    
    # 计算EMA
    ema_fast = close.ewm(span=fast_period).mean()
    ema_slow = close.ewm(span=slow_period).mean()
    
    # 计算MACD线
    macd = ema_fast - ema_slow
    
    # 计算信号线
    macd_signal = macd.ewm(span=signal_period).mean()
    
    # 计算柱状图
    macd_histogram = macd - macd_signal
    
    return pd.DataFrame({
        'macd': macd,
        'macd_signal': macd_signal,
        'macd_histogram': macd_histogram
    })
```

**KDJ指标**:
```python
def calculate_kdj(df: pd.DataFrame, period: int = 27, 
                  k_smooth: int = 3, d_smooth: int = 3) -> pd.DataFrame:
    """
    计算KDJ指标
    
    Returns:
        DataFrame with columns: k, d, j
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 计算RSV
    lowest_low = low.rolling(window=period).min()
    highest_high = high.rolling(window=period).max()
    rsv = (close - lowest_low) / (highest_high - lowest_low) * 100
    
    # 计算K值
    k = rsv.ewm(alpha=1/k_smooth).mean()
    
    # 计算D值
    d = k.ewm(alpha=1/d_smooth).mean()
    
    # 计算J值
    j = 3 * k - 2 * d
    
    return pd.DataFrame({'k': k, 'd': d, 'j': j})
```

**RSI指标**:
```python
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """计算RSI指标"""
    close = df['close']
    delta = close.diff()
    
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi
```

#### 使用示例
```python
from indicators import calculate_macd, calculate_kdj, calculate_rsi

# 计算技术指标
macd_data = calculate_macd(df)
kdj_data = calculate_kdj(df)
rsi_data = calculate_rsi(df)

# 合并指标数据
df = pd.concat([df, macd_data, kdj_data], axis=1)
df['rsi'] = rsi_data
```

## 🎯 策略分析模块

### StrategyEngine (strategies.py)

#### 功能描述
实现各种交易策略的分析逻辑，包括TRIPLE_CROSS、PRE_CROSS、MACD_ZERO_AXIS等。

#### 核心策略实现

**TRIPLE_CROSS策略**:
```python
def analyze_triple_cross(df: pd.DataFrame, config: dict) -> dict:
    """
    三线交叉策略分析
    
    策略逻辑:
    1. MACD金叉 (MACD > Signal)
    2. KDJ金叉 (K > D)
    3. RSI适中 (30 < RSI < 70)
    """
    # 计算技术指标
    macd_data = calculate_macd(df, **config['macd'])
    kdj_data = calculate_kdj(df, **config['kdj'])
    rsi_data = calculate_rsi(df, config['rsi']['period'])
    
    # 获取最新数据
    latest = df.iloc[-1]
    latest_macd = macd_data.iloc[-1]
    latest_kdj = kdj_data.iloc[-1]
    latest_rsi = rsi_data.iloc[-1]
    
    # 判断信号条件
    macd_golden = latest_macd['macd'] > latest_macd['macd_signal']
    kdj_golden = latest_kdj['k'] > latest_kdj['d']
    rsi_normal = 30 < latest_rsi < 70
    
    # 计算信号强度
    signal_strength = 0
    if macd_golden:
        signal_strength += 40
    if kdj_golden:
        signal_strength += 35
    if rsi_normal:
        signal_strength += 25
    
    return {
        'signal': signal_strength > 70,
        'strength': signal_strength,
        'conditions': {
            'macd_golden': macd_golden,
            'kdj_golden': kdj_golden,
            'rsi_normal': rsi_normal
        },
        'indicators': {
            'macd': latest_macd.to_dict(),
            'kdj': latest_kdj.to_dict(),
            'rsi': latest_rsi
        }
    }
```

**PRE_CROSS策略**:
```python
def analyze_pre_cross(df: pd.DataFrame, config: dict) -> dict:
    """
    预交叉策略分析
    
    策略逻辑:
    1. MACD接近金叉但未交叉
    2. KDJ处于低位准备上升
    3. 成交量放大
    """
    # 计算指标
    macd_data = calculate_macd(df, **config['macd'])
    kdj_data = calculate_kdj(df, **config['kdj'])
    
    # 获取最近几天数据
    recent_macd = macd_data.tail(5)
    recent_kdj = kdj_data.tail(5)
    recent_volume = df['volume'].tail(5)
    
    # 判断预交叉条件
    macd_approaching = (
        recent_macd['macd'].iloc[-1] > recent_macd['macd'].iloc[-2] and
        recent_macd['macd'].iloc[-1] < recent_macd['macd_signal'].iloc[-1] and
        abs(recent_macd['macd'].iloc[-1] - recent_macd['macd_signal'].iloc[-1]) < 0.1
    )
    
    kdj_low_rising = (
        recent_kdj['k'].iloc[-1] < 30 and
        recent_kdj['k'].iloc[-1] > recent_kdj['k'].iloc[-2]
    )
    
    volume_increasing = recent_volume.iloc[-1] > recent_volume.mean() * 1.2
    
    # 计算信号强度
    signal_strength = 0
    if macd_approaching:
        signal_strength += 50
    if kdj_low_rising:
        signal_strength += 30
    if volume_increasing:
        signal_strength += 20
    
    return {
        'signal': signal_strength > 60,
        'strength': signal_strength,
        'stage': 'PRE_CROSS',
        'conditions': {
            'macd_approaching': macd_approaching,
            'kdj_low_rising': kdj_low_rising,
            'volume_increasing': volume_increasing
        }
    }
```

#### 策略配置管理
```python
class StrategyConfig:
    def __init__(self, config_file: str = "strategy_configs.json"):
        self.config_file = config_file
        self.configs = self.load_configs()
    
    def load_configs(self) -> dict:
        """加载策略配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return self.get_default_configs()
    
    def get_strategy_config(self, strategy_name: str) -> dict:
        """获取指定策略配置"""
        return self.configs.get(strategy_name, {})
    
    def update_strategy_config(self, strategy_name: str, config: dict):
        """更新策略配置"""
        self.configs[strategy_name] = config
        self.save_configs()
    
    def save_configs(self):
        """保存配置到文件"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.configs, f, indent=2, ensure_ascii=False)
```

### WinRateFilter (win_rate_filter.py)

#### 功能描述
基于历史胜率过滤低质量信号，提高策略效果。

#### 核心实现
```python
class WinRateFilter:
    def __init__(self, min_win_rate: float = 0.4, min_samples: int = 3):
        self.min_win_rate = min_win_rate
        self.min_samples = min_samples
        self.history_cache = {}
    
    def calculate_historical_win_rate(self, symbol: str, strategy: str) -> dict:
        """计算历史胜率"""
        # 加载历史信号数据
        history = self.load_signal_history(symbol, strategy)
        
        if len(history) < self.min_samples:
            return {
                'win_rate': 0.0,
                'sample_count': len(history),
                'avg_return': 0.0,
                'status': 'insufficient_data'
            }
        
        # 计算胜率统计
        wins = sum(1 for signal in history if signal['return'] > 0)
        total = len(history)
        win_rate = wins / total
        
        avg_return = sum(signal['return'] for signal in history) / total
        
        return {
            'win_rate': win_rate,
            'sample_count': total,
            'avg_return': avg_return,
            'status': 'passed' if win_rate >= self.min_win_rate else 'filtered'
        }
    
    def should_filter_signal(self, symbol: str, strategy: str) -> bool:
        """判断是否应该过滤信号"""
        stats = self.calculate_historical_win_rate(symbol, strategy)
        
        # 数据不足时不过滤
        if stats['sample_count'] < self.min_samples:
            return False
        
        # 胜率过低时过滤
        return stats['win_rate'] < self.min_win_rate
```

## 🔄 回测系统模块

### BacktestingSystem (backtester.py)

#### 功能描述
提供完整的策略回测功能，支持多种性能指标计算。

#### 核心实现
```python
class BacktestingSystem:
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.positions = {}
        self.trade_history = []
    
    def run_backtest(self, strategy_func, data: pd.DataFrame, 
                     config: dict) -> dict:
        """运行回测"""
        results = {
            'trades': [],
            'daily_returns': [],
            'positions': [],
            'performance': {}
        }
        
        for i in range(len(data)):
            current_data = data.iloc[:i+1]
            date = data.index[i]
            
            # 生成交易信号
            signal = strategy_func(current_data, config)
            
            # 执行交易
            if signal['signal']:
                trade_result = self.execute_trade(
                    symbol=data.attrs.get('symbol', 'UNKNOWN'),
                    price=data.iloc[i]['close'],
                    signal=signal,
                    date=date
                )
                if trade_result:
                    results['trades'].append(trade_result)
            
            # 更新持仓价值
            portfolio_value = self.calculate_portfolio_value(data.iloc[i])
            results['daily_returns'].append({
                'date': date,
                'portfolio_value': portfolio_value,
                'return': (portfolio_value - self.initial_capital) / self.initial_capital
            })
        
        # 计算性能指标
        results['performance'] = self.calculate_performance_metrics(results)
        
        return results
    
    def calculate_performance_metrics(self, results: dict) -> dict:
        """计算性能指标"""
        returns = [r['return'] for r in results['daily_returns']]
        
        if not returns:
            return {}
        
        total_return = returns[-1]
        volatility = np.std(returns) * np.sqrt(252)  # 年化波动率
        
        # 计算最大回撤
        peak = returns[0]
        max_drawdown = 0
        for ret in returns:
            if ret > peak:
                peak = ret
            drawdown = (peak - ret) / (1 + peak)
            max_drawdown = max(max_drawdown, drawdown)
        
        # 计算夏普比率
        risk_free_rate = 0.03  # 假设无风险利率3%
        excess_return = total_return - risk_free_rate
        sharpe_ratio = excess_return / volatility if volatility > 0 else 0
        
        return {
            'total_return': total_return,
            'volatility': volatility,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'trade_count': len(results['trades']),
            'win_rate': self.calculate_win_rate(results['trades'])
        }
```

### T1IntelligentTradingSystem (t1_intelligent_trading_system.py)

#### 功能描述
专门针对中国股市T+1规则设计的智能交易系统。

#### 核心特性
- **T+1规则严格执行**: 当日买入次日才能卖出
- **智能交易决策**: 买入/卖出/持有/观察四种动作
- **风险控制**: 动态止盈止损和仓位管理
- **走势预期判断**: 基于技术分析的趋势预测

#### 核心实现
```python
@dataclass
class Position:
    symbol: str
    shares: int
    buy_price: float
    buy_date: str
    can_sell: bool = False  # T+1规则控制

class T1IntelligentTradingSystem:
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.current_cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trading_history: List[TradingSignal] = []
        
        # 交易参数
        self.max_position_size = 0.2  # 单股最大仓位20%
        self.stop_loss_pct = 0.08     # 止损8%
        self.take_profit_pct = 0.15   # 止盈15%
    
    def generate_trading_signal(self, symbol: str, df: pd.DataFrame, 
                               date: datetime) -> TradingSignal:
        """生成交易信号"""
        # 市场分析
        analysis = self._analyze_market(df)
        
        # 获取当前持仓
        current_position = self.positions.get(symbol)
        
        # 决策逻辑
        if current_position:
            # 已有持仓，判断是否卖出或持有
            return self._decide_sell_or_hold(symbol, analysis, current_position, date)
        else:
            # 无持仓，判断是否买入或观察
            return self._decide_buy_or_observe(symbol, analysis, date)
    
    def _analyze_market(self, df: pd.DataFrame) -> MarketAnalysis:
        """市场分析"""
        # 计算技术指标
        macd_data = calculate_macd(df)
        kdj_data = calculate_kdj(df)
        rsi_data = calculate_rsi(df)
        
        # 计算移动平均线
        df['ma5'] = df['close'].rolling(5).mean()
        df['ma10'] = df['close'].rolling(10).mean()
        df['ma20'] = df['close'].rolling(20).mean()
        
        latest = df.iloc[-1]
        latest_macd = macd_data.iloc[-1]
        latest_kdj = kdj_data.iloc[-1]
        latest_rsi = rsi_data.iloc[-1]
        
        # 综合评分
        technical_score = self._calculate_technical_score(df)
        momentum_score = self._calculate_momentum_score(df)
        risk_score = self._calculate_risk_score(df)
        
        # 趋势预期
        trend_expectation = self._determine_trend_expectation(
            technical_score, momentum_score, risk_score
        )
        
        return MarketAnalysis(
            # 技术指标
            ma5=latest['ma5'],
            ma10=latest['ma10'],
            ma20=latest['ma20'],
            rsi=latest_rsi,
            macd=latest_macd['macd'],
            macd_signal=latest_macd['macd_signal'],
            
            # 综合评分
            technical_score=technical_score,
            momentum_score=momentum_score,
            risk_score=risk_score,
            
            # 趋势预期
            trend_expectation=trend_expectation
        )
```

## 🔧 配置管理模块

### ConfigManager (config_manager.py)

#### 功能描述
统一管理系统配置，支持动态配置更新和环境适配。

#### 核心实现
```python
class ConfigManager:
    def __init__(self, config_file: str = "workflow_config.json"):
        self.config_file = config_file
        self.config = self.load_config()
        self.user_config = {}
    
    def load_config(self) -> dict:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return self.get_default_config()
    
    def get_config(self, key: str, default=None):
        """获取配置值"""
        # 用户配置优先
        if key in self.user_config:
            return self.user_config[key]
        
        # 然后是文件配置
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def update_config(self, key: str, value):
        """更新配置"""
        self.user_config[key] = value
    
    def save_config(self):
        """保存配置到文件"""
        # 合并用户配置到主配置
        merged_config = self.merge_configs(self.config, self.user_config)
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(merged_config, f, indent=2, ensure_ascii=False)
```

## 🎯 使用示例

### 完整的策略分析流程
```python
from data_loader import DataLoader
from indicators import calculate_macd, calculate_kdj, calculate_rsi
from strategies import analyze_triple_cross
from win_rate_filter import WinRateFilter
from backtester import BacktestingSystem

# 1. 加载数据
loader = DataLoader()
df = loader.load_stock_data("000001")

# 2. 计算技术指标
macd_data = calculate_macd(df)
kdj_data = calculate_kdj(df)
rsi_data = calculate_rsi(df)

# 3. 策略分析
config = {
    'macd': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
    'kdj': {'period': 27, 'k_smooth': 3, 'd_smooth': 3},
    'rsi': {'period': 14}
}

signal = analyze_triple_cross(df, config)

# 4. 胜率过滤
win_filter = WinRateFilter()
if not win_filter.should_filter_signal("000001", "TRIPLE_CROSS"):
    print(f"信号通过胜率过滤: {signal}")

# 5. 回测验证
backtester = BacktestingSystem()
backtest_result = backtester.run_backtest(analyze_triple_cross, df, config)
print(f"回测结果: {backtest_result['performance']}")
```

这些核心模块构成了系统的基础架构，为上层的业务逻辑和用户界面提供了强大的支撑。每个模块都经过精心设计，具有良好的可扩展性和可维护性。