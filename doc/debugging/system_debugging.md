# 系统调试指南

## 🔍 调试概览

本指南提供了系统各个层面的调试方法和工具，帮助开发者快速定位和解决问题。

## 🛠️ 调试工具配置

### 1. 日志系统配置

#### 基础日志配置
```python
import logging
import sys
from datetime import datetime

def setup_logging(level=logging.INFO, log_file=None):
    """配置日志系统"""
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # 文件处理器
    handlers = [console_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # 配置根日志器
    logging.basicConfig(
        level=level,
        handlers=handlers,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    return logging.getLogger(__name__)

# 使用示例
logger = setup_logging(logging.DEBUG, 'debug.log')
```

#### 模块级日志配置
```python
# 在每个模块中添加
import logging
logger = logging.getLogger(__name__)

class DataLoader:
    def load_stock_data(self, symbol: str):
        logger.info(f"开始加载股票数据: {symbol}")
        try:
            # 数据加载逻辑
            data = self._load_data(symbol)
            logger.info(f"成功加载数据: {symbol}, 记录数: {len(data)}")
            return data
        except Exception as e:
            logger.error(f"加载数据失败: {symbol}, 错误: {str(e)}")
            raise
```

### 2. 调试装饰器

#### 函数执行时间监控
```python
import functools
import time
from typing import Callable

def timing_debug(func: Callable) -> Callable:
    """监控函数执行时间"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.debug(f"开始执行 {func.__name__}")
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"完成执行 {func.__name__}, 耗时: {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"执行失败 {func.__name__}, 耗时: {execution_time:.3f}s, 错误: {str(e)}")
            raise
    
    return wrapper

# 使用示例
@timing_debug
def analyze_triple_cross(df, config):
    # 策略分析逻辑
    pass
```

#### 参数和返回值调试
```python
def debug_io(func: Callable) -> Callable:
    """调试函数输入输出"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger.debug(f"{func.__name__} 输入参数:")
        logger.debug(f"  args: {args}")
        logger.debug(f"  kwargs: {kwargs}")
        
        result = func(*args, **kwargs)
        
        logger.debug(f"{func.__name__} 返回值:")
        logger.debug(f"  result: {result}")
        
        return result
    
    return wrapper
```

## 🔧 模块级调试

### 1. 数据加载调试

#### 数据完整性检查
```python
def debug_data_loader():
    """调试数据加载器"""
    from backend.data_loader import DataLoader
    
    loader = DataLoader()
    
    # 测试股票列表获取
    try:
        stock_list = loader.get_stock_list()
        print(f"✅ 获取股票列表成功: {len(stock_list)} 只股票")
        print(f"前10只股票: {stock_list[:10]}")
    except Exception as e:
        print(f"❌ 获取股票列表失败: {e}")
        return
    
    # 测试数据加载
    test_symbols = stock_list[:5]  # 测试前5只股票
    
    for symbol in test_symbols:
        try:
            df = loader.load_stock_data(symbol)
            
            # 数据完整性检查
            if df.empty:
                print(f"⚠️  {symbol}: 数据为空")
                continue
            
            # 检查必要列
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                print(f"⚠️  {symbol}: 缺少列 {missing_columns}")
                continue
            
            # 检查数据质量
            null_counts = df.isnull().sum()
            if null_counts.any():
                print(f"⚠️  {symbol}: 存在空值 {null_counts[null_counts > 0].to_dict()}")
            
            print(f"✅ {symbol}: 数据正常, 记录数: {len(df)}, 日期范围: {df.index[0]} ~ {df.index[-1]}")
            
        except Exception as e:
            print(f"❌ {symbol}: 加载失败 - {e}")

# 运行调试
if __name__ == "__main__":
    debug_data_loader()
```

#### 5分钟数据调试
```python
def debug_5min_data():
    """调试5分钟数据加载"""
    from backend.data_loader import DataLoader
    
    loader = DataLoader()
    test_symbols = ['000001', '000002', '600000']
    
    for symbol in test_symbols:
        try:
            df = loader.load_5min_data(symbol)
            
            if df.empty:
                print(f"⚠️  {symbol}: 5分钟数据为空")
                continue
            
            # 检查时间连续性
            time_diff = df.index.to_series().diff()
            expected_diff = pd.Timedelta(minutes=5)
            
            irregular_intervals = time_diff[time_diff != expected_diff].dropna()
            if not irregular_intervals.empty:
                print(f"⚠️  {symbol}: 发现不规则时间间隔")
                print(f"    异常间隔数量: {len(irregular_intervals)}")
            
            print(f"✅ {symbol}: 5分钟数据正常, 记录数: {len(df)}")
            
        except Exception as e:
            print(f"❌ {symbol}: 5分钟数据加载失败 - {e}")
```

### 2. 技术指标调试

#### 指标计算验证
```python
def debug_indicators():
    """调试技术指标计算"""
    from backend.data_loader import DataLoader
    from backend.indicators import calculate_macd, calculate_kdj, calculate_rsi
    
    loader = DataLoader()
    df = loader.load_stock_data('000001')
    
    if df.empty:
        print("❌ 无法获取测试数据")
        return
    
    print(f"📊 使用数据: 000001, 记录数: {len(df)}")
    
    # 测试MACD
    try:
        macd_data = calculate_macd(df)
        
        # 检查结果完整性
        if macd_data.empty:
            print("❌ MACD计算结果为空")
        else:
            # 检查是否有异常值
            macd_stats = macd_data.describe()
            print("✅ MACD计算成功")
            print(f"   MACD统计: {macd_stats['macd'][['mean', 'std', 'min', 'max']].to_dict()}")
            
            # 检查最新值
            latest_macd = macd_data.iloc[-1]
            print(f"   最新MACD: {latest_macd['macd']:.4f}")
            print(f"   最新信号线: {latest_macd['macd_signal']:.4f}")
            print(f"   最新柱状图: {latest_macd['macd_histogram']:.4f}")
            
    except Exception as e:
        print(f"❌ MACD计算失败: {e}")
    
    # 测试KDJ
    try:
        kdj_data = calculate_kdj(df)
        
        if kdj_data.empty:
            print("❌ KDJ计算结果为空")
        else:
            latest_kdj = kdj_data.iloc[-1]
            print("✅ KDJ计算成功")
            print(f"   最新K值: {latest_kdj['k']:.2f}")
            print(f"   最新D值: {latest_kdj['d']:.2f}")
            print(f"   最新J值: {latest_kdj['j']:.2f}")
            
            # 检查数值范围
            if not (0 <= latest_kdj['k'] <= 100):
                print(f"⚠️  K值超出正常范围: {latest_kdj['k']}")
            if not (0 <= latest_kdj['d'] <= 100):
                print(f"⚠️  D值超出正常范围: {latest_kdj['d']}")
                
    except Exception as e:
        print(f"❌ KDJ计算失败: {e}")
    
    # 测试RSI
    try:
        rsi_data = calculate_rsi(df)
        
        if rsi_data.empty:
            print("❌ RSI计算结果为空")
        else:
            latest_rsi = rsi_data.iloc[-1]
            print("✅ RSI计算成功")
            print(f"   最新RSI: {latest_rsi:.2f}")
            
            # 检查数值范围
            if not (0 <= latest_rsi <= 100):
                print(f"⚠️  RSI值超出正常范围: {latest_rsi}")
                
    except Exception as e:
        print(f"❌ RSI计算失败: {e}")
```

### 3. 策略分析调试

#### 策略信号调试
```python
def debug_strategy_signals():
    """调试策略信号生成"""
    from backend.data_loader import DataLoader
    from backend.strategies import analyze_triple_cross
    from backend.config_manager import ConfigManager
    
    # 加载配置和数据
    config_manager = ConfigManager()
    strategy_config = config_manager.get_config('strategies.TRIPLE_CROSS')
    
    loader = DataLoader()
    test_symbols = ['000001', '000002', '600000']
    
    for symbol in test_symbols:
        try:
            df = loader.load_stock_data(symbol)
            
            if len(df) < 50:  # 确保有足够的数据
                print(f"⚠️  {symbol}: 数据不足，跳过")
                continue
            
            # 分析策略信号
            signal = analyze_triple_cross(df, strategy_config)
            
            print(f"📈 {symbol} 策略分析结果:")
            print(f"   信号: {'🟢 买入' if signal['signal'] else '🔴 无信号'}")
            print(f"   强度: {signal['strength']:.1f}")
            print(f"   条件: {signal['conditions']}")
            
            # 检查指标合理性
            indicators = signal.get('indicators', {})
            if 'macd' in indicators:
                macd_val = indicators['macd']['macd']
                if abs(macd_val) > 10:  # MACD值过大可能异常
                    print(f"⚠️  MACD值异常: {macd_val}")
            
            if 'rsi' in indicators:
                rsi_val = indicators['rsi']
                if not (0 <= rsi_val <= 100):
                    print(f"⚠️  RSI值异常: {rsi_val}")
            
        except Exception as e:
            print(f"❌ {symbol}: 策略分析失败 - {e}")
            import traceback
            traceback.print_exc()
```

### 4. 回测系统调试

#### 回测结果验证
```python
def debug_backtesting():
    """调试回测系统"""
    from backend.backtester import BacktestingSystem
    from backend.data_loader import DataLoader
    from backend.strategies import analyze_triple_cross
    from backend.config_manager import ConfigManager
    
    # 初始化组件
    backtester = BacktestingSystem(initial_capital=100000)
    loader = DataLoader()
    config_manager = ConfigManager()
    
    # 获取测试数据
    symbol = '000001'
    df = loader.load_stock_data(symbol)
    
    if len(df) < 100:
        print("❌ 测试数据不足")
        return
    
    # 使用最近6个月数据进行回测
    test_data = df.tail(120)  # 约6个月
    test_data.attrs['symbol'] = symbol
    
    strategy_config = config_manager.get_config('strategies.TRIPLE_CROSS')
    
    try:
        print(f"🔄 开始回测 {symbol}")
        print(f"   数据期间: {test_data.index[0]} ~ {test_data.index[-1]}")
        print(f"   初始资金: ¥{backtester.initial_capital:,.2f}")
        
        # 运行回测
        result = backtester.run_backtest(analyze_triple_cross, test_data, strategy_config)
        
        # 验证回测结果
        print("\n📊 回测结果验证:")
        
        # 检查交易记录
        trades = result['trades']
        print(f"   交易次数: {len(trades)}")
        
        if trades:
            for i, trade in enumerate(trades):
                print(f"   交易{i+1}: {trade['action']} @ ¥{trade['price']:.2f} on {trade['date']}")
        
        # 检查性能指标
        performance = result['performance']
        print(f"\n📈 性能指标:")
        print(f"   总收益率: {performance.get('total_return', 0):.2%}")
        print(f"   最大回撤: {performance.get('max_drawdown', 0):.2%}")
        print(f"   夏普比率: {performance.get('sharpe_ratio', 0):.2f}")
        print(f"   胜率: {performance.get('win_rate', 0):.2%}")
        
        # 检查异常值
        if performance.get('total_return', 0) > 2:  # 收益率超过200%可能异常
            print("⚠️  收益率异常高，请检查计算逻辑")
        
        if performance.get('max_drawdown', 0) > 0.5:  # 回撤超过50%
            print("⚠️  最大回撤过大，请检查风险控制")
        
    except Exception as e:
        print(f"❌ 回测失败: {e}")
        import traceback
        traceback.print_exc()
```

## 🚨 常见问题调试

### 1. 数据问题调试

#### 数据文件不存在
```python
def debug_missing_data_files():
    """调试数据文件缺失问题"""
    import os
    from backend.data_loader import DataLoader
    
    loader = DataLoader()
    data_path = loader.data_path
    
    print(f"🔍 检查数据目录: {data_path}")
    
    if not os.path.exists(data_path):
        print(f"❌ 数据目录不存在: {data_path}")
        print("💡 解决方案:")
        print("   1. 检查数据目录路径配置")
        print("   2. 确保vipdoc数据文件夹存在")
        print("   3. 检查文件权限")
        return
    
    # 检查子目录
    expected_dirs = ['sh', 'sz', 'bj']
    for dir_name in expected_dirs:
        dir_path = os.path.join(data_path, dir_name)
        if os.path.exists(dir_path):
            file_count = len([f for f in os.listdir(dir_path) if f.endswith('.day')])
            print(f"✅ {dir_name}: {file_count} 个.day文件")
        else:
            print(f"❌ {dir_name}: 目录不存在")
```

#### 数据格式错误
```python
def debug_data_format():
    """调试数据格式问题"""
    from backend.data_loader import DataLoader
    import pandas as pd
    
    loader = DataLoader()
    
    # 手动检查数据文件格式
    test_file = "data/vipdoc/sh/000001.day"
    
    try:
        # 尝试不同的读取方式
        print(f"🔍 检查文件: {test_file}")
        
        # 方式1: 原始读取
        with open(test_file, 'rb') as f:
            first_bytes = f.read(100)
            print(f"文件前100字节: {first_bytes}")
        
        # 方式2: 文本读取
        with open(test_file, 'r', encoding='utf-8', errors='ignore') as f:
            first_lines = [f.readline().strip() for _ in range(5)]
            print(f"文件前5行: {first_lines}")
        
        # 方式3: pandas读取
        df = pd.read_csv(test_file, sep='\t', header=None, nrows=5)
        print(f"pandas读取结果: {df.shape}")
        print(df.head())
        
    except Exception as e:
        print(f"❌ 文件读取失败: {e}")
```

### 2. 性能问题调试

#### 内存使用监控
```python
import psutil
import os

def debug_memory_usage():
    """监控内存使用情况"""
    process = psutil.Process(os.getpid())
    
    def print_memory_info(stage):
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        print(f"{stage}: 内存使用 {memory_mb:.1f} MB")
    
    print_memory_info("开始")
    
    # 模拟大量数据加载
    from backend.data_loader import DataLoader
    loader = DataLoader()
    
    print_memory_info("初始化后")
    
    # 加载多只股票数据
    stock_list = loader.get_stock_list()[:10]
    data_cache = {}
    
    for symbol in stock_list:
        try:
            data_cache[symbol] = loader.load_stock_data(symbol)
            print_memory_info(f"加载{symbol}后")
        except:
            continue
    
    print_memory_info("全部加载后")
    
    # 清理缓存
    data_cache.clear()
    print_memory_info("清理后")
```

#### 执行时间分析
```python
import cProfile
import pstats
from io import StringIO

def debug_performance():
    """性能分析"""
    
    def test_function():
        """测试函数"""
        from backend.data_loader import DataLoader
        from backend.strategies import analyze_triple_cross
        from backend.config_manager import ConfigManager
        
        loader = DataLoader()
        config_manager = ConfigManager()
        
        # 加载数据并分析
        for symbol in loader.get_stock_list()[:5]:
            try:
                df = loader.load_stock_data(symbol)
                config = config_manager.get_config('strategies.TRIPLE_CROSS')
                analyze_triple_cross(df, config)
            except:
                continue
    
    # 性能分析
    pr = cProfile.Profile()
    pr.enable()
    
    test_function()
    
    pr.disable()
    
    # 输出结果
    s = StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumulative')
    ps.print_stats(20)  # 显示前20个最耗时的函数
    
    print("🔍 性能分析结果:")
    print(s.getvalue())
```

## 🔧 调试工具脚本

### 综合调试脚本
```python
#!/usr/bin/env python3
"""
系统综合调试脚本
使用方法: python debug_system.py [module]
"""

import sys
import argparse

def main():
    parser = argparse.ArgumentParser(description='系统调试工具')
    parser.add_argument('module', nargs='?', default='all', 
                       choices=['all', 'data', 'indicators', 'strategies', 'backtest'],
                       help='要调试的模块')
    parser.add_argument('--verbose', '-v', action='store_true', help='详细输出')
    
    args = parser.parse_args()
    
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    print("🔧 开始系统调试...")
    
    if args.module in ['all', 'data']:
        print("\n📊 调试数据模块...")
        debug_data_loader()
        debug_5min_data()
    
    if args.module in ['all', 'indicators']:
        print("\n📈 调试指标模块...")
        debug_indicators()
    
    if args.module in ['all', 'strategies']:
        print("\n🎯 调试策略模块...")
        debug_strategy_signals()
    
    if args.module in ['all', 'backtest']:
        print("\n🔄 调试回测模块...")
        debug_backtesting()
    
    print("\n✅ 调试完成!")

if __name__ == "__main__":
    main()
```

### 快速健康检查脚本
```python
def quick_health_check():
    """快速系统健康检查"""
    checks = []
    
    # 检查1: 数据目录
    try:
        from backend.data_loader import DataLoader
        loader = DataLoader()
        stock_list = loader.get_stock_list()
        checks.append(("数据目录", len(stock_list) > 0, f"找到{len(stock_list)}只股票"))
    except Exception as e:
        checks.append(("数据目录", False, str(e)))
    
    # 检查2: 配置文件
    try:
        from backend.config_manager import ConfigManager
        config = ConfigManager()
        strategy_config = config.get_config('strategies.TRIPLE_CROSS')
        checks.append(("配置文件", strategy_config is not None, "配置加载正常"))
    except Exception as e:
        checks.append(("配置文件", False, str(e)))
    
    # 检查3: 技术指标
    try:
        from backend.indicators import calculate_macd
        import pandas as pd
        test_data = pd.DataFrame({
            'close': [10, 11, 12, 13, 14, 15, 16, 17, 18, 19] * 10
        })
        macd_result = calculate_macd(test_data)
        checks.append(("技术指标", not macd_result.empty, "指标计算正常"))
    except Exception as e:
        checks.append(("技术指标", False, str(e)))
    
    # 输出结果
    print("🏥 系统健康检查结果:")
    for name, status, message in checks:
        status_icon = "✅" if status else "❌"
        print(f"   {status_icon} {name}: {message}")
    
    # 总体状态
    all_passed = all(check[1] for check in checks)
    overall_status = "✅ 系统正常" if all_passed else "⚠️  发现问题"
    print(f"\n{overall_status}")
    
    return all_passed

if __name__ == "__main__":
    quick_health_check()
```

这个调试指南提供了全面的调试方法和工具，帮助开发者快速定位和解决系统中的各种问题。通过系统化的调试流程，可以确保系统的稳定性和可靠性。