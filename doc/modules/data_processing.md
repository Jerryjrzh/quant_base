# 数据处理模块文档

## 📊 模块概览

数据处理模块是系统的基础层，负责股票数据的加载、解析、验证和缓存管理。支持多种数据格式，提供统一的数据访问接口。

## 🔧 核心组件

### 1. DataLoader (data_loader.py)

#### 类结构
```python
class DataLoader:
    def __init__(self, data_path: str = "data/vipdoc"):
        self.data_path = data_path
        self.cache = {}
        self.cache_size_limit = 100  # 最大缓存股票数
        self.supported_formats = ['.day', '.lc5']
```

#### 主要方法

##### load_stock_data()
```python
def load_stock_data(self, symbol: str, period: str = "daily") -> pd.DataFrame:
    """
    加载股票数据
    
    Args:
        symbol: 股票代码 (如 '000001', '600000')
        period: 数据周期 ('daily', '5min')
    
    Returns:
        DataFrame with columns: [open, high, low, close, volume, amount]
        Index: DatetimeIndex
    
    Raises:
        FileNotFoundError: 数据文件不存在
        ValueError: 数据格式错误
        DataQualityError: 数据质量问题
    """
    
    # 缓存检查
    cache_key = f"{symbol}_{period}"
    if cache_key in self.cache:
        logger.debug(f"从缓存加载数据: {symbol}")
        return self.cache[cache_key].copy()
    
    # 确定文件路径
    file_path = self._get_file_path(symbol, period)
    
    # 加载数据
    if period == "daily":
        df = self._load_daily_data(file_path)
    elif period == "5min":
        df = self._load_5min_data(file_path)
    else:
        raise ValueError(f"不支持的数据周期: {period}")
    
    # 数据验证和清洗
    df = self._validate_and_clean_data(df, symbol)
    
    # 更新缓存
    self._update_cache(cache_key, df)
    
    return df.copy()
```

##### _load_daily_data()
```python
def _load_daily_data(self, file_path: str) -> pd.DataFrame:
    """
    加载日线数据 (.day格式)
    
    数据格式:
    日期(YYYYMMDD) 开盘价*100 最高价*100 最低价*100 收盘价*100 成交量 成交额
    """
    try:
        # 读取原始数据
        df = pd.read_csv(
            file_path,
            sep='\t',
            header=None,
            names=['date', 'open', 'high', 'low', 'close', 'volume', 'amount'],
            dtype={
                'date': str,
                'open': int,
                'high': int,
                'low': int,
                'close': int,
                'volume': int,
                'amount': int
            }
        )
        
        # 数据转换
        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        df.set_index('date', inplace=True)
        
        # 价格数据除以100 (原始数据是价格*100)
        price_columns = ['open', 'high', 'low', 'close']
        df[price_columns] = df[price_columns] / 100.0
        
        # 按日期排序
        df.sort_index(inplace=True)
        
        return df
        
    except Exception as e:
        logger.error(f"加载日线数据失败: {file_path}, 错误: {str(e)}")
        raise DataLoadError(f"无法加载日线数据: {str(e)}")
```

##### _load_5min_data()
```python
def _load_5min_data(self, file_path: str) -> pd.DataFrame:
    """
    加载5分钟数据 (.lc5格式)
    
    数据格式:
    时间戳 开盘价*100 最高价*100 最低价*100 收盘价*100 成交量
    """
    try:
        # 读取原始数据
        df = pd.read_csv(
            file_path,
            sep='\t',
            header=None,
            names=['timestamp', 'open', 'high', 'low', 'close', 'volume'],
            dtype={
                'timestamp': int,
                'open': int,
                'high': int,
                'low': int,
                'close': int,
                'volume': int
            }
        )
        
        # 时间戳转换 (假设是Unix时间戳)
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        df.set_index('datetime', inplace=True)
        df.drop('timestamp', axis=1, inplace=True)
        
        # 价格数据除以100
        price_columns = ['open', 'high', 'low', 'close']
        df[price_columns] = df[price_columns] / 100.0
        
        # 过滤交易时间 (9:30-11:30, 13:00-15:00)
        df = self._filter_trading_hours(df)
        
        return df
        
    except Exception as e:
        logger.error(f"加载5分钟数据失败: {file_path}, 错误: {str(e)}")
        raise DataLoadError(f"无法加载5分钟数据: {str(e)}")
```

##### _validate_and_clean_data()
```python
def _validate_and_clean_data(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """
    数据验证和清洗
    """
    if df.empty:
        raise DataQualityError(f"数据为空: {symbol}")
    
    # 检查必要列
    required_columns = ['open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        raise DataQualityError(f"缺少必要列: {missing_columns}")
    
    # 检查价格逻辑
    invalid_prices = (
        (df['high'] < df['low']) |
        (df['high'] < df['open']) |
        (df['high'] < df['close']) |
        (df['low'] > df['open']) |
        (df['low'] > df['close'])
    )
    
    if invalid_prices.any():
        logger.warning(f"{symbol}: 发现{invalid_prices.sum()}条价格逻辑错误")
        # 修正或删除异常数据
        df = df[~invalid_prices]
    
    # 检查空值
    null_counts = df.isnull().sum()
    if null_counts.any():
        logger.warning(f"{symbol}: 发现空值 {null_counts[null_counts > 0].to_dict()}")
        # 前向填充
        df.fillna(method='ffill', inplace=True)
    
    # 检查异常值 (价格变动超过20%可能异常)
    price_change = df['close'].pct_change().abs()
    outliers = price_change > 0.2
    if outliers.any():
        logger.warning(f"{symbol}: 发现{outliers.sum()}个价格异常值")
    
    # 检查成交量异常 (成交量为0或异常大)
    volume_outliers = (df['volume'] == 0) | (df['volume'] > df['volume'].quantile(0.99) * 10)
    if volume_outliers.any():
        logger.warning(f"{symbol}: 发现{volume_outliers.sum()}个成交量异常值")
    
    return df
```

### 2. 缓存管理系统

#### CacheManager
```python
class CacheManager:
    def __init__(self, max_size: int = 100, ttl: int = 3600):
        self.cache = {}
        self.access_times = {}
        self.max_size = max_size
        self.ttl = ttl  # 缓存生存时间(秒)
    
    def get(self, key: str) -> Optional[pd.DataFrame]:
        """获取缓存数据"""
        if key not in self.cache:
            return None
        
        # 检查TTL
        if time.time() - self.access_times[key] > self.ttl:
            self.remove(key)
            return None
        
        # 更新访问时间
        self.access_times[key] = time.time()
        return self.cache[key].copy()
    
    def put(self, key: str, data: pd.DataFrame):
        """存储缓存数据"""
        # 检查缓存大小限制
        if len(self.cache) >= self.max_size:
            self._evict_lru()
        
        self.cache[key] = data.copy()
        self.access_times[key] = time.time()
    
    def _evict_lru(self):
        """LRU淘汰策略"""
        if not self.access_times:
            return
        
        # 找到最久未访问的key
        lru_key = min(self.access_times.keys(), 
                     key=lambda k: self.access_times[k])
        self.remove(lru_key)
    
    def remove(self, key: str):
        """移除缓存项"""
        self.cache.pop(key, None)
        self.access_times.pop(key, None)
    
    def clear(self):
        """清空缓存"""
        self.cache.clear()
        self.access_times.clear()
    
    def get_stats(self) -> dict:
        """获取缓存统计信息"""
        total_memory = sum(
            df.memory_usage(deep=True).sum() 
            for df in self.cache.values()
        )
        
        return {
            'cache_size': len(self.cache),
            'max_size': self.max_size,
            'memory_usage_mb': total_memory / 1024 / 1024,
            'hit_rate': getattr(self, '_hit_count', 0) / max(getattr(self, '_total_requests', 1), 1)
        }
```

### 3. 数据质量监控

#### DataQualityMonitor
```python
class DataQualityMonitor:
    def __init__(self):
        self.quality_reports = {}
    
    def check_data_quality(self, df: pd.DataFrame, symbol: str) -> dict:
        """检查数据质量"""
        report = {
            'symbol': symbol,
            'total_records': len(df),
            'date_range': {
                'start': df.index.min().strftime('%Y-%m-%d'),
                'end': df.index.max().strftime('%Y-%m-%d')
            },
            'issues': []
        }
        
        # 检查数据连续性
        date_gaps = self._check_date_continuity(df)
        if date_gaps:
            report['issues'].append({
                'type': 'date_gaps',
                'count': len(date_gaps),
                'details': date_gaps[:5]  # 只显示前5个
            })
        
        # 检查价格异常
        price_anomalies = self._check_price_anomalies(df)
        if price_anomalies:
            report['issues'].append({
                'type': 'price_anomalies',
                'count': len(price_anomalies),
                'details': price_anomalies[:5]
            })
        
        # 检查成交量异常
        volume_anomalies = self._check_volume_anomalies(df)
        if volume_anomalies:
            report['issues'].append({
                'type': 'volume_anomalies',
                'count': len(volume_anomalies),
                'details': volume_anomalies[:5]
            })
        
        # 计算质量分数
        report['quality_score'] = self._calculate_quality_score(report)
        
        self.quality_reports[symbol] = report
        return report
    
    def _check_date_continuity(self, df: pd.DataFrame) -> list:
        """检查日期连续性"""
        gaps = []
        dates = df.index.to_series()
        
        for i in range(1, len(dates)):
            current_date = dates.iloc[i]
            prev_date = dates.iloc[i-1]
            
            # 计算工作日差异
            expected_next = prev_date + pd.Timedelta(days=1)
            while expected_next.weekday() >= 5:  # 跳过周末
                expected_next += pd.Timedelta(days=1)
            
            if current_date > expected_next:
                gaps.append({
                    'start': prev_date.strftime('%Y-%m-%d'),
                    'end': current_date.strftime('%Y-%m-%d'),
                    'days': (current_date - prev_date).days
                })
        
        return gaps
    
    def _check_price_anomalies(self, df: pd.DataFrame) -> list:
        """检查价格异常"""
        anomalies = []
        
        # 检查价格逻辑错误
        logic_errors = (
            (df['high'] < df['low']) |
            (df['high'] < df['open']) |
            (df['high'] < df['close']) |
            (df['low'] > df['open']) |
            (df['low'] > df['close'])
        )
        
        for date in df[logic_errors].index:
            anomalies.append({
                'date': date.strftime('%Y-%m-%d'),
                'type': 'logic_error',
                'data': df.loc[date].to_dict()
            })
        
        # 检查异常波动
        price_change = df['close'].pct_change().abs()
        extreme_changes = price_change > 0.2  # 单日涨跌超过20%
        
        for date in df[extreme_changes].index:
            if pd.isna(price_change.loc[date]):
                continue
            anomalies.append({
                'date': date.strftime('%Y-%m-%d'),
                'type': 'extreme_change',
                'change_pct': price_change.loc[date] * 100
            })
        
        return anomalies
    
    def _check_volume_anomalies(self, df: pd.DataFrame) -> list:
        """检查成交量异常"""
        anomalies = []
        
        # 零成交量
        zero_volume = df['volume'] == 0
        for date in df[zero_volume].index:
            anomalies.append({
                'date': date.strftime('%Y-%m-%d'),
                'type': 'zero_volume'
            })
        
        # 异常大成交量
        volume_threshold = df['volume'].quantile(0.99) * 5
        extreme_volume = df['volume'] > volume_threshold
        
        for date in df[extreme_volume].index:
            anomalies.append({
                'date': date.strftime('%Y-%m-%d'),
                'type': 'extreme_volume',
                'volume': int(df.loc[date, 'volume'])
            })
        
        return anomalies
    
    def _calculate_quality_score(self, report: dict) -> float:
        """计算数据质量分数 (0-100)"""
        base_score = 100
        
        for issue in report['issues']:
            if issue['type'] == 'date_gaps':
                base_score -= min(issue['count'] * 2, 20)
            elif issue['type'] == 'price_anomalies':
                base_score -= min(issue['count'] * 1, 15)
            elif issue['type'] == 'volume_anomalies':
                base_score -= min(issue['count'] * 0.5, 10)
        
        return max(base_score, 0)
```

### 4. 数据预处理工具

#### DataPreprocessor
```python
class DataPreprocessor:
    def __init__(self):
        self.processors = {
            'fill_missing': self._fill_missing_values,
            'remove_outliers': self._remove_outliers,
            'smooth_prices': self._smooth_prices,
            'adjust_splits': self._adjust_for_splits
        }
    
    def preprocess(self, df: pd.DataFrame, operations: list) -> pd.DataFrame:
        """执行数据预处理"""
        result_df = df.copy()
        
        for operation in operations:
            if operation in self.processors:
                result_df = self.processors[operation](result_df)
                logger.debug(f"执行预处理操作: {operation}")
            else:
                logger.warning(f"未知的预处理操作: {operation}")
        
        return result_df
    
    def _fill_missing_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """填充缺失值"""
        # 价格数据使用前向填充
        price_columns = ['open', 'high', 'low', 'close']
        df[price_columns] = df[price_columns].fillna(method='ffill')
        
        # 成交量使用0填充
        df['volume'] = df['volume'].fillna(0)
        
        return df
    
    def _remove_outliers(self, df: pd.DataFrame) -> pd.DataFrame:
        """移除异常值"""
        # 使用IQR方法检测价格异常值
        for col in ['open', 'high', 'low', 'close']:
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            
            lower_bound = Q1 - 1.5 * IQR
            upper_bound = Q3 + 1.5 * IQR
            
            # 标记异常值但不删除，而是用边界值替换
            df.loc[df[col] < lower_bound, col] = lower_bound
            df.loc[df[col] > upper_bound, col] = upper_bound
        
        return df
    
    def _smooth_prices(self, df: pd.DataFrame) -> pd.DataFrame:
        """价格平滑处理"""
        # 使用3日移动平均平滑价格
        window = 3
        
        for col in ['open', 'high', 'low', 'close']:
            df[f'{col}_smoothed'] = df[col].rolling(window=window, center=True).mean()
            # 用平滑后的值替换原值
            df[col] = df[f'{col}_smoothed'].fillna(df[col])
            df.drop(f'{col}_smoothed', axis=1, inplace=True)
        
        return df
    
    def _adjust_for_splits(self, df: pd.DataFrame) -> pd.DataFrame:
        """股票分割调整"""
        # 检测可能的股票分割 (价格突然减半)
        price_ratio = df['close'] / df['close'].shift(1)
        
        # 检测分割点 (价格比率在0.4-0.6之间，可能是1:2分割)
        split_points = (price_ratio > 0.4) & (price_ratio < 0.6)
        
        if split_points.any():
            logger.info(f"检测到可能的股票分割点: {split_points.sum()}个")
            
            # 对分割前的数据进行调整
            for split_date in df[split_points].index:
                split_ratio = price_ratio.loc[split_date]
                
                # 调整分割前的价格数据
                before_split = df.index < split_date
                price_columns = ['open', 'high', 'low', 'close']
                df.loc[before_split, price_columns] *= split_ratio
                
                # 调整成交量 (分割后成交量应该增加)
                df.loc[before_split, 'volume'] /= split_ratio
        
        return df
```

## 🔧 使用示例

### 基本数据加载
```python
from backend.data_loader import DataLoader

# 初始化数据加载器
loader = DataLoader("data/vipdoc")

# 加载日线数据
daily_data = loader.load_stock_data("000001", "daily")
print(f"加载了 {len(daily_data)} 条日线数据")

# 加载5分钟数据
min5_data = loader.load_stock_data("000001", "5min")
print(f"加载了 {len(min5_data)} 条5分钟数据")

# 获取股票列表
stock_list = loader.get_stock_list()
print(f"共有 {len(stock_list)} 只股票")
```

### 数据质量检查
```python
from backend.data_loader import DataQualityMonitor

# 初始化质量监控器
monitor = DataQualityMonitor()

# 检查数据质量
quality_report = monitor.check_data_quality(daily_data, "000001")

print(f"数据质量分数: {quality_report['quality_score']}")
print(f"发现问题: {len(quality_report['issues'])} 个")

for issue in quality_report['issues']:
    print(f"- {issue['type']}: {issue['count']} 个")
```

### 数据预处理
```python
from backend.data_loader import DataPreprocessor

# 初始化预处理器
preprocessor = DataPreprocessor()

# 执行预处理
processed_data = preprocessor.preprocess(
    daily_data, 
    ['fill_missing', 'remove_outliers', 'smooth_prices']
)

print("数据预处理完成")
```

### 批量数据处理
```python
def batch_load_and_process():
    """批量加载和处理数据"""
    loader = DataLoader()
    monitor = DataQualityMonitor()
    preprocessor = DataPreprocessor()
    
    stock_list = loader.get_stock_list()[:10]  # 处理前10只股票
    
    results = {}
    
    for symbol in stock_list:
        try:
            # 加载数据
            df = loader.load_stock_data(symbol)
            
            # 质量检查
            quality_report = monitor.check_data_quality(df, symbol)
            
            # 如果质量分数太低，跳过
            if quality_report['quality_score'] < 70:
                logger.warning(f"{symbol}: 数据质量过低，跳过处理")
                continue
            
            # 预处理
            processed_df = preprocessor.preprocess(df, ['fill_missing', 'remove_outliers'])
            
            results[symbol] = {
                'data': processed_df,
                'quality_score': quality_report['quality_score'],
                'record_count': len(processed_df)
            }
            
            logger.info(f"{symbol}: 处理完成，质量分数 {quality_report['quality_score']}")
            
        except Exception as e:
            logger.error(f"{symbol}: 处理失败 - {str(e)}")
    
    return results

# 执行批量处理
batch_results = batch_load_and_process()
print(f"成功处理 {len(batch_results)} 只股票")
```

## 🎯 性能优化

### 1. 并行数据加载
```python
import concurrent.futures
from typing import List, Dict

def parallel_load_stocks(symbols: List[str], max_workers: int = 4) -> Dict[str, pd.DataFrame]:
    """并行加载多只股票数据"""
    loader = DataLoader()
    results = {}
    
    def load_single_stock(symbol):
        try:
            return symbol, loader.load_stock_data(symbol)
        except Exception as e:
            logger.error(f"加载 {symbol} 失败: {str(e)}")
            return symbol, None
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {
            executor.submit(load_single_stock, symbol): symbol 
            for symbol in symbols
        }
        
        for future in concurrent.futures.as_completed(future_to_symbol):
            symbol, data = future.result()
            if data is not None:
                results[symbol] = data
    
    return results
```

### 2. 内存优化
```python
def optimize_dataframe_memory(df: pd.DataFrame) -> pd.DataFrame:
    """优化DataFrame内存使用"""
    # 转换数据类型以节省内存
    for col in df.columns:
        if df[col].dtype == 'int64':
            if df[col].min() >= 0:
                if df[col].max() < 2**16:
                    df[col] = df[col].astype('uint16')
                elif df[col].max() < 2**32:
                    df[col] = df[col].astype('uint32')
            else:
                if df[col].min() >= -2**15 and df[col].max() < 2**15:
                    df[col] = df[col].astype('int16')
                elif df[col].min() >= -2**31 and df[col].max() < 2**31:
                    df[col] = df[col].astype('int32')
        
        elif df[col].dtype == 'float64':
            df[col] = df[col].astype('float32')
    
    return df
```

数据处理模块为整个系统提供了可靠、高效的数据基础，通过完善的缓存机制、质量监控和预处理功能，确保了数据的准确性和系统的性能。