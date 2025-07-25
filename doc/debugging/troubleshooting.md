# 常见问题解决指南

## 🚨 问题分类

### 1. 数据相关问题
### 2. 策略分析问题  
### 3. 回测系统问题
### 4. 工作流执行问题
### 5. 性能问题
### 6. 配置问题

---

## 📊 数据相关问题

### 问题1: 数据文件不存在或无法读取

**症状**:
```
FileNotFoundError: [Errno 2] No such file or directory: 'data/vipdoc/sh/000001.day'
```

**可能原因**:
- 数据目录路径配置错误
- 数据文件缺失或损坏
- 文件权限问题
- 股票代码格式错误

**解决方案**:

1. **检查数据目录结构**:
```bash
# 检查数据目录是否存在
ls -la data/vipdoc/

# 应该看到如下结构:
# data/vipdoc/
# ├── sh/     # 上海证券交易所
# ├── sz/     # 深圳证券交易所  
# └── bj/     # 北京证券交易所
```

2. **验证文件权限**:
```bash
# 检查文件权限
ls -la data/vipdoc/sh/000001.day

# 如果权限不足，修改权限
chmod 644 data/vipdoc/sh/*.day
```

3. **使用调试脚本检查**:
```python
from backend.data_loader import DataLoader

loader = DataLoader()

# 检查数据目录
print(f"数据目录: {loader.data_path}")
print(f"目录存在: {os.path.exists(loader.data_path)}")

# 检查股票列表
try:
    stock_list = loader.get_stock_list()
    print(f"找到 {len(stock_list)} 只股票")
    print(f"前10只: {stock_list[:10]}")
except Exception as e:
    print(f"获取股票列表失败: {e}")
```

4. **配置文件修正**:
```python
# 在 workflow_config.json 中设置正确的数据路径
{
    "data": {
        "vipdoc_path": "/path/to/your/vipdoc/data",
        "cache_enabled": true,
        "cache_size_limit": 100
    }
}
```

### 问题2: 数据格式错误或解析失败

**症状**:
```
ValueError: could not convert string to float: 'invalid_data'
pandas.errors.ParserError: Error tokenizing data
```

**可能原因**:
- 数据文件格式不符合预期
- 文件编码问题
- 数据中包含异常字符
- 文件损坏

**解决方案**:

1. **手动检查数据格式**:
```python
# 检查文件前几行
with open('data/vipdoc/sh/000001.day', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i < 5:  # 只看前5行
            print(f"第{i+1}行: {repr(line)}")
```

2. **使用数据验证工具**:
```python
from backend.data_loader import DataQualityMonitor

monitor = DataQualityMonitor()

# 加载并检查数据质量
try:
    df = loader.load_stock_data('000001')
    quality_report = monitor.check_data_quality(df, '000001')
    
    print(f"数据质量分数: {quality_report['quality_score']}")
    for issue in quality_report['issues']:
        print(f"问题: {issue['type']} - {issue['count']}个")
        
except Exception as e:
    print(f"数据加载失败: {e}")
```

3. **数据修复脚本**:
```python
def repair_data_file(file_path):
    """修复损坏的数据文件"""
    
    backup_path = file_path + '.backup'
    
    # 备份原文件
    shutil.copy2(file_path, backup_path)
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # 清理数据
        cleaned_lines = []
        for line in lines:
            # 移除异常字符
            cleaned_line = re.sub(r'[^\d\t\n.-]', '', line)
            if cleaned_line.strip():  # 跳过空行
                cleaned_lines.append(cleaned_line)
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(cleaned_lines)
        
        print(f"文件修复完成: {file_path}")
        
    except Exception as e:
        # 恢复备份
        shutil.copy2(backup_path, file_path)
        print(f"修复失败，已恢复备份: {e}")
```

### 问题3: 数据缺失或不完整

**症状**:
```
Warning: 000001 数据不足，跳过
Empty DataFrame: 数据为空
```

**解决方案**:

1. **检查数据完整性**:
```python
def check_data_completeness():
    """检查数据完整性"""
    
    loader = DataLoader()
    stock_list = loader.get_stock_list()
    
    incomplete_stocks = []
    
    for symbol in stock_list[:20]:  # 检查前20只
        try:
            df = loader.load_stock_data(symbol)
            
            if df.empty:
                incomplete_stocks.append((symbol, "数据为空"))
            elif len(df) < 30:
                incomplete_stocks.append((symbol, f"数据不足: {len(df)}条"))
            else:
                # 检查日期连续性
                date_gaps = check_date_gaps(df)
                if date_gaps > 10:
                    incomplete_stocks.append((symbol, f"日期缺失: {date_gaps}天"))
                    
        except Exception as e:
            incomplete_stocks.append((symbol, f"加载失败: {str(e)}"))
    
    return incomplete_stocks
```

2. **数据补全策略**:
```python
def fill_missing_data(df):
    """填充缺失数据"""
    
    # 价格数据前向填充
    price_columns = ['open', 'high', 'low', 'close']
    df[price_columns] = df[price_columns].fillna(method='ffill')
    
    # 成交量用0填充
    df['volume'] = df['volume'].fillna(0)
    
    # 成交额根据价格和成交量估算
    df['amount'] = df['amount'].fillna(df['close'] * df['volume'])
    
    return df
```

---

## 🎯 策略分析问题

### 问题4: 技术指标计算异常

**症状**:
```
RuntimeWarning: invalid value encountered in divide
ValueError: Input contains NaN, infinity or a value too large
```

**可能原因**:
- 数据中包含NaN值
- 除零错误
- 数据类型不匹配
- 计算参数设置不当

**解决方案**:

1. **数据预处理**:
```python
def safe_calculate_indicators(df):
    """安全的指标计算"""
    
    # 检查数据有效性
    if df.empty or len(df) < 30:
        raise ValueError("数据不足，无法计算指标")
    
    # 清理异常值
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.fillna(method='ffill').fillna(method='bfill')
    
    # 确保数据类型正确
    numeric_columns = ['open', 'high', 'low', 'close', 'volume']
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # 计算指标
    try:
        macd_data = calculate_macd(df)
        kdj_data = calculate_kdj(df)
        rsi_data = calculate_rsi(df)
        
        # 检查结果
        if macd_data.isnull().all().any():
            raise ValueError("MACD计算结果包含全部NaN")
        
        return {
            'macd': macd_data,
            'kdj': kdj_data,
            'rsi': rsi_data
        }
        
    except Exception as e:
        logger.error(f"指标计算失败: {str(e)}")
        raise
```

2. **参数验证**:
```python
def validate_indicator_params(params):
    """验证指标参数"""
    
    errors = []
    
    # MACD参数检查
    if 'macd' in params:
        macd_params = params['macd']
        if macd_params.get('fast_period', 12) >= macd_params.get('slow_period', 26):
            errors.append("MACD快线周期必须小于慢线周期")
        
        if macd_params.get('signal_period', 9) <= 0:
            errors.append("MACD信号线周期必须大于0")
    
    # KDJ参数检查
    if 'kdj' in params:
        kdj_params = params['kdj']
        if kdj_params.get('period', 27) <= 0:
            errors.append("KDJ周期必须大于0")
    
    # RSI参数检查
    if 'rsi' in params:
        rsi_params = params['rsi']
        if rsi_params.get('period', 14) <= 1:
            errors.append("RSI周期必须大于1")
    
    return errors
```

### 问题5: 策略信号异常

**症状**:
```
所有股票都没有信号
信号强度异常高/低
策略条件判断错误
```

**解决方案**:

1. **策略调试工具**:
```python
def debug_strategy_logic(symbol, strategy_func, config):
    """调试策略逻辑"""
    
    loader = DataLoader()
    df = loader.load_stock_data(symbol)
    
    print(f"=== 调试策略: {symbol} ===")
    print(f"数据长度: {len(df)}")
    print(f"日期范围: {df.index[0]} ~ {df.index[-1]}")
    
    # 计算指标
    indicators = safe_calculate_indicators(df)
    
    # 显示最新指标值
    print("\n最新指标值:")
    for name, data in indicators.items():
        if isinstance(data, pd.DataFrame):
            latest = data.iloc[-1]
            print(f"{name}: {latest.to_dict()}")
        else:
            print(f"{name}: {data.iloc[-1]}")
    
    # 执行策略
    try:
        result = strategy_func(df, config)
        
        print(f"\n策略结果:")
        print(f"信号: {result.get('signal', False)}")
        print(f"强度: {result.get('strength', 0)}")
        print(f"条件: {result.get('conditions', {})}")
        
        # 分析每个条件
        conditions = result.get('conditions', {})
        for condition, value in conditions.items():
            status = "✅" if value else "❌"
            print(f"  {status} {condition}: {value}")
        
    except Exception as e:
        print(f"策略执行失败: {e}")
        import traceback
        traceback.print_exc()
```

2. **信号质量检查**:
```python
def check_signal_quality(signals):
    """检查信号质量"""
    
    if not signals:
        print("⚠️  没有生成任何信号")
        return
    
    print(f"📊 信号统计:")
    print(f"总信号数: {len(signals)}")
    
    # 强度分布
    strengths = [s.get('strength', 0) for s in signals]
    print(f"强度分布:")
    print(f"  平均: {np.mean(strengths):.1f}")
    print(f"  最大: {np.max(strengths):.1f}")
    print(f"  最小: {np.min(strengths):.1f}")
    
    # 策略分布
    strategies = {}
    for signal in signals:
        strategy = signal.get('strategy', 'UNKNOWN')
        strategies[strategy] = strategies.get(strategy, 0) + 1
    
    print(f"策略分布:")
    for strategy, count in strategies.items():
        print(f"  {strategy}: {count}")
    
    # 质量分数分布
    quality_scores = [s.get('quality_score', 0) for s in signals if 'quality_score' in s]
    if quality_scores:
        print(f"质量分数:")
        print(f"  平均: {np.mean(quality_scores):.1f}")
        print(f"  >70分: {sum(1 for s in quality_scores if s > 70)}")
```

---

## 🔄 回测系统问题

### 问题6: 回测结果异常

**症状**:
```
收益率异常高 (>1000%)
夏普比率为负数或异常值
交易次数为0
最大回撤超过100%
```

**解决方案**:

1. **回测参数验证**:
```python
def validate_backtest_params(params):
    """验证回测参数"""
    
    issues = []
    
    # 检查初始资金
    initial_capital = params.get('initial_capital', 100000)
    if initial_capital <= 0:
        issues.append("初始资金必须大于0")
    
    # 检查手续费率
    commission_rate = params.get('commission_rate', 0.0003)
    if commission_rate < 0 or commission_rate > 0.01:
        issues.append("手续费率异常")
    
    # 检查最大仓位
    max_position = params.get('max_position_size', 0.2)
    if max_position <= 0 or max_position > 1:
        issues.append("最大仓位设置异常")
    
    return issues
```

2. **回测结果验证**:
```python
def validate_backtest_results(result):
    """验证回测结果"""
    
    performance = result.get('performance', {})
    
    warnings = []
    
    # 检查收益率
    total_return = performance.get('total_return', 0)
    if abs(total_return) > 5:  # 收益率超过500%
        warnings.append(f"收益率异常: {total_return:.2%}")
    
    # 检查夏普比率
    sharpe_ratio = performance.get('sharpe_ratio', 0)
    if sharpe_ratio < -2 or sharpe_ratio > 5:
        warnings.append(f"夏普比率异常: {sharpe_ratio:.2f}")
    
    # 检查最大回撤
    max_drawdown = performance.get('max_drawdown', 0)
    if max_drawdown > 1:
        warnings.append(f"最大回撤异常: {max_drawdown:.2%}")
    
    # 检查交易次数
    total_trades = performance.get('total_trades', 0)
    if total_trades == 0:
        warnings.append("没有执行任何交易")
    
    return warnings
```

3. **回测修复工具**:
```python
def fix_backtest_issues(backtest_system):
    """修复回测问题"""
    
    # 重置异常状态
    if backtest_system.current_cash < 0:
        logger.warning("现金为负，重置为初始资金的10%")
        backtest_system.current_cash = backtest_system.initial_capital * 0.1
    
    # 清理异常持仓
    invalid_positions = []
    for symbol, position in backtest_system.positions.items():
        if position.get('shares', 0) <= 0:
            invalid_positions.append(symbol)
    
    for symbol in invalid_positions:
        del backtest_system.positions[symbol]
        logger.warning(f"清理异常持仓: {symbol}")
    
    # 验证交易历史
    valid_trades = []
    for trade in backtest_system.trade_history:
        if (trade.get('price', 0) > 0 and 
            trade.get('shares', 0) > 0):
            valid_trades.append(trade)
    
    backtest_system.trade_history = valid_trades
```

---

## 🔄 工作流执行问题

### 问题7: 工作流阶段执行失败

**症状**:
```
Phase1执行失败: 参数优化超时
Phase2执行失败: 核心观察池为空
Phase3执行失败: 历史数据不足
```

**解决方案**:

1. **阶段依赖检查**:
```python
def check_phase_dependencies():
    """检查阶段依赖"""
    
    issues = []
    
    # Phase1依赖检查
    if not os.path.exists('data/vipdoc'):
        issues.append("Phase1: 数据目录不存在")
    
    # Phase2依赖检查
    if not os.path.exists('core_stock_pool.json'):
        issues.append("Phase2: 核心观察池文件不存在")
    else:
        try:
            with open('core_stock_pool.json', 'r') as f:
                pool = json.load(f)
                if not pool.get('stocks'):
                    issues.append("Phase2: 核心观察池为空")
        except:
            issues.append("Phase2: 核心观察池文件损坏")
    
    # Phase3依赖检查
    reports_dir = 'reports'
    if not os.path.exists(reports_dir):
        issues.append("Phase3: 报告目录不存在")
    else:
        signal_files = [f for f in os.listdir(reports_dir) if f.startswith('daily_signals_')]
        if not signal_files:
            issues.append("Phase3: 没有历史交易信号")
    
    return issues
```

2. **工作流恢复机制**:
```python
def recover_workflow_state():
    """恢复工作流状态"""
    
    recovery_actions = []
    
    # 检查并创建必要目录
    required_dirs = ['reports', 'logs', 'cache']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            recovery_actions.append(f"创建目录: {dir_name}")
    
    # 检查配置文件
    if not os.path.exists('workflow_config.json'):
        # 创建默认配置
        default_config = get_default_workflow_config()
        with open('workflow_config.json', 'w') as f:
            json.dump(default_config, f, indent=2)
        recovery_actions.append("创建默认配置文件")
    
    # 检查核心观察池
    if not os.path.exists('core_stock_pool.json'):
        # 触发Phase1执行
        recovery_actions.append("需要执行Phase1生成核心观察池")
    
    return recovery_actions
```

### 问题8: 配置文件问题

**症状**:
```
ConfigError: 配置文件格式错误
KeyError: 'phases' key not found
ValueError: 无效的配置值
```

**解决方案**:

1. **配置验证工具**:
```python
def validate_config_file(config_path):
    """验证配置文件"""
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        return {'valid': False, 'error': f'JSON格式错误: {str(e)}'}
    except FileNotFoundError:
        return {'valid': False, 'error': '配置文件不存在'}
    
    # 检查必要的配置项
    required_keys = ['phases', 'logging']
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        return {'valid': False, 'error': f'缺少必要配置项: {missing_keys}'}
    
    # 检查阶段配置
    phases = config.get('phases', {})
    required_phases = ['phase1', 'phase2', 'phase3']
    missing_phases = [phase for phase in required_phases if phase not in phases]
    
    if missing_phases:
        return {'valid': False, 'error': f'缺少阶段配置: {missing_phases}'}
    
    # 检查频率设置
    for phase_name, phase_config in phases.items():
        frequency = phase_config.get('frequency_hours')
        if frequency is None or frequency <= 0:
            return {'valid': False, 'error': f'{phase_name}频率设置无效'}
    
    return {'valid': True}
```

2. **配置修复工具**:
```python
def repair_config_file(config_path):
    """修复配置文件"""
    
    # 备份原文件
    backup_path = config_path + '.backup'
    if os.path.exists(config_path):
        shutil.copy2(config_path, backup_path)
    
    # 加载默认配置
    default_config = get_default_workflow_config()
    
    # 尝试合并现有配置
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
            
            # 递归合并配置
            merged_config = merge_configs(default_config, existing_config)
            
        except:
            merged_config = default_config
    else:
        merged_config = default_config
    
    # 保存修复后的配置
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(merged_config, f, indent=2, ensure_ascii=False)
    
    print(f"配置文件已修复: {config_path}")
    if os.path.exists(backup_path):
        print(f"原文件备份: {backup_path}")
```

---

## ⚡ 性能问题

### 问题9: 系统运行缓慢

**症状**:
```
数据加载耗时过长
策略分析超时
内存使用过高
CPU占用率100%
```

**解决方案**:

1. **性能监控工具**:
```python
import psutil
import time
from functools import wraps

def monitor_performance(func):
    """性能监控装饰器"""
    
    @wraps(func)
    def wrapper(*args, **kwargs):
        # 记录开始状态
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024
        start_cpu = psutil.cpu_percent()
        
        try:
            result = func(*args, **kwargs)
            
            # 记录结束状态
            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024
            end_cpu = psutil.cpu_percent()
            
            # 输出性能统计
            print(f"🔍 性能统计 - {func.__name__}")
            print(f"  执行时间: {end_time - start_time:.2f}秒")
            print(f"  内存变化: {end_memory - start_memory:+.1f}MB")
            print(f"  CPU使用: {end_cpu:.1f}%")
            
            return result
            
        except Exception as e:
            print(f"❌ 函数执行失败: {func.__name__} - {str(e)}")
            raise
    
    return wrapper
```

2. **缓存优化**:
```python
def optimize_data_cache():
    """优化数据缓存"""
    
    from backend.data_loader import DataLoader
    
    loader = DataLoader()
    
    # 检查缓存状态
    cache_stats = loader.cache_manager.get_stats()
    print(f"缓存统计:")
    print(f"  缓存大小: {cache_stats['cache_size']}/{cache_stats['max_size']}")
    print(f"  内存使用: {cache_stats['memory_usage_mb']:.1f}MB")
    print(f"  命中率: {cache_stats['hit_rate']:.2%}")
    
    # 如果内存使用过高，清理缓存
    if cache_stats['memory_usage_mb'] > 500:  # 超过500MB
        print("内存使用过高，清理缓存...")
        loader.cache_manager.clear()
        print("缓存已清理")
```

3. **并行处理优化**:
```python
def optimize_parallel_processing():
    """优化并行处理"""
    
    import multiprocessing as mp
    
    # 检查CPU核心数
    cpu_count = mp.cpu_count()
    print(f"CPU核心数: {cpu_count}")
    
    # 推荐的工作进程数
    recommended_workers = max(1, cpu_count - 1)
    print(f"推荐工作进程数: {recommended_workers}")
    
    # 检查内存限制
    memory_gb = psutil.virtual_memory().total / 1024 / 1024 / 1024
    print(f"系统内存: {memory_gb:.1f}GB")
    
    # 根据内存调整进程数
    if memory_gb < 8:
        recommended_workers = min(recommended_workers, 2)
        print("内存不足，建议减少并行进程数")
    
    return recommended_workers
```

---

## 🛠️ 综合诊断工具

### 系统健康检查
```python
def system_health_check():
    """系统健康检查"""
    
    print("🏥 系统健康检查")
    print("=" * 50)
    
    health_score = 100
    issues = []
    
    # 1. 数据检查
    try:
        loader = DataLoader()
        stock_list = loader.get_stock_list()
        if len(stock_list) > 0:
            print("✅ 数据系统: 正常")
        else:
            print("❌ 数据系统: 无股票数据")
            health_score -= 30
            issues.append("数据系统异常")
    except Exception as e:
        print(f"❌ 数据系统: {str(e)}")
        health_score -= 30
        issues.append("数据系统异常")
    
    # 2. 配置检查
    config_validation = validate_config_file('workflow_config.json')
    if config_validation['valid']:
        print("✅ 配置系统: 正常")
    else:
        print(f"❌ 配置系统: {config_validation['error']}")
        health_score -= 20
        issues.append("配置系统异常")
    
    # 3. 工作流检查
    dependency_issues = check_phase_dependencies()
    if not dependency_issues:
        print("✅ 工作流系统: 正常")
    else:
        print("❌ 工作流系统: 存在依赖问题")
        for issue in dependency_issues:
            print(f"  - {issue}")
        health_score -= 25
        issues.append("工作流系统异常")
    
    # 4. 性能检查
    memory_usage = psutil.virtual_memory().percent
    cpu_usage = psutil.cpu_percent(interval=1)
    
    if memory_usage < 80 and cpu_usage < 80:
        print("✅ 系统性能: 正常")
    else:
        print(f"⚠️  系统性能: 内存{memory_usage:.1f}% CPU{cpu_usage:.1f}%")
        if memory_usage > 90 or cpu_usage > 90:
            health_score -= 15
            issues.append("系统性能异常")
    
    # 5. 磁盘空间检查
    disk_usage = psutil.disk_usage('.').percent
    if disk_usage < 90:
        print("✅ 磁盘空间: 正常")
    else:
        print(f"⚠️  磁盘空间: {disk_usage:.1f}%已使用")
        health_score -= 10
        issues.append("磁盘空间不足")
    
    # 总结
    print("\n" + "=" * 50)
    print(f"🎯 系统健康评分: {health_score}/100")
    
    if health_score >= 90:
        print("🟢 系统状态: 优秀")
    elif health_score >= 70:
        print("🟡 系统状态: 良好")
    elif health_score >= 50:
        print("🟠 系统状态: 一般")
    else:
        print("🔴 系统状态: 需要维护")
    
    if issues:
        print("\n🔧 需要解决的问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    
    return {
        'health_score': health_score,
        'issues': issues,
        'status': 'healthy' if health_score >= 70 else 'needs_attention'
    }

# 运行系统健康检查
if __name__ == "__main__":
    system_health_check()
```

### 一键修复工具
```python
def auto_fix_system():
    """一键修复系统问题"""
    
    print("🔧 开始自动修复...")
    
    fixed_issues = []
    
    # 1. 修复配置文件
    try:
        repair_config_file('workflow_config.json')
        fixed_issues.append("配置文件已修复")
    except Exception as e:
        print(f"配置文件修复失败: {e}")
    
    # 2. 恢复工作流状态
    try:
        recovery_actions = recover_workflow_state()
        fixed_issues.extend(recovery_actions)
    except Exception as e:
        print(f"工作流状态恢复失败: {e}")
    
    # 3. 清理缓存
    try:
        optimize_data_cache()
        fixed_issues.append("缓存已优化")
    except Exception as e:
        print(f"缓存优化失败: {e}")
    
    # 4. 创建必要目录
    required_dirs = ['reports', 'logs', 'cache', 'backups']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            fixed_issues.append(f"创建目录: {dir_name}")
    
    print(f"\n✅ 修复完成，共解决 {len(fixed_issues)} 个问题:")
    for issue in fixed_issues:
        print(f"  - {issue}")
    
    # 重新检查系统健康状态
    print("\n🔄 重新检查系统状态...")
    health_result = system_health_check()
    
    return health_result

# 使用方法
if __name__ == "__main__":
    # 先检查系统状态
    health_result = system_health_check()
    
    # 如果有问题，尝试自动修复
    if health_result['status'] == 'needs_attention':
        print("\n检测到系统问题，开始自动修复...")
        auto_fix_system()
```

这个故障排除指南涵盖了系统运行中可能遇到的主要问题，提供了详细的诊断方法和解决方案。通过系统化的问题分类和自动化的修复工具，可以快速定位和解决大部分常见问题。