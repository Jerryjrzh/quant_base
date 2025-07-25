# 多周期分析系统使用指南

## 🚀 快速开始

多周期分析系统是一个完整的量化交易分析平台，支持从5分钟到日线的6个时间周期协同分析。

### 系统要求
- Python 3.8+
- pandas, numpy 等依赖包
- 至少 2GB 可用内存

### 安装和启动
```bash
# 确保所有依赖已安装
pip install pandas numpy

# 验证系统功能
python test_multi_timeframe_system.py

# 开始使用
python run_multi_timeframe_analysis.py --help
```

## 📊 三种运行模式

### 1. 综合分析模式 (analysis)
**用途**: 对股票进行全面的多周期分析，生成投资建议

```bash
# 分析单只股票
python run_multi_timeframe_analysis.py --mode analysis --stocks sz300290

# 分析多只股票
python run_multi_timeframe_analysis.py --mode analysis --stocks sz300290 sz002691 sh600690

# 使用默认股票池
python run_multi_timeframe_analysis.py --mode analysis
```

**输出内容**:
- 数据质量评估
- 多周期信号分析
- 风险评估报告
- 投资建议和建议操作

### 2. 回测分析模式 (backtest)
**用途**: 验证多周期策略的历史表现

```bash
# 回测单只股票（默认90天）
python run_multi_timeframe_analysis.py --mode backtest --stocks sz300290

# 自定义回测期间
python run_multi_timeframe_analysis.py --mode backtest --stocks sz300290 --days 180

# 回测多只股票
python run_multi_timeframe_analysis.py --mode backtest --stocks sz300290 sz002691 --days 60
```

**输出内容**:
- 回测期间收益率
- 夏普比率和最大回撤
- 胜率和交易统计
- 策略绩效报告

### 3. 实时监控模式 (monitor)
**用途**: 实时监控股票的多周期信号变化

```bash
# 监控单只股票（默认60分钟）
python run_multi_timeframe_analysis.py --mode monitor --stocks sz300290

# 自定义监控时长
python run_multi_timeframe_analysis.py --mode monitor --stocks sz300290 --duration 120

# 监控多只股票
python run_multi_timeframe_analysis.py --mode monitor --stocks sz300290 sz002691 --duration 30
```

**输出内容**:
- 实时信号更新
- 智能预警通知
- 监控统计报告
- 系统性能分析

## 🔧 API 使用方式

### 基础API调用

```python
from backend.multi_timeframe_data_manager import MultiTimeframeDataManager
from backend.multi_timeframe_signal_generator import MultiTimeframeSignalGenerator
from backend.multi_timeframe_report_generator import MultiTimeframeReportGenerator

# 初始化组件
data_manager = MultiTimeframeDataManager()
signal_generator = MultiTimeframeSignalGenerator(data_manager)
report_generator = MultiTimeframeReportGenerator()

# 获取多周期数据
stock_code = 'sz300290'
sync_data = data_manager.get_synchronized_data(stock_code)
print(f"获取到 {len(sync_data['timeframes'])} 个时间周期的数据")

# 生成交易信号
signals = signal_generator.generate_composite_signals(stock_code)
composite_signal = signals['composite_signal']
print(f"信号强度: {composite_signal['signal_strength']}")
print(f"置信度: {composite_signal['confidence_level']:.3f}")

# 生成分析报告
daily_report = report_generator.generate_daily_multi_timeframe_report([stock_code])
recommendations = daily_report['recommendations']
print(f"买入建议: {len(recommendations['buy_list'])}")
print(f"卖出建议: {len(recommendations['sell_list'])}")
```

### 高级API使用

```python
# 批量分析多只股票
stock_list = ['sz300290', 'sz002691', 'sh600690']

for stock_code in stock_list:
    try:
        # 生成信号
        signals = signal_generator.generate_composite_signals(stock_code)
        
        if 'error' not in signals:
            composite = signals['composite_signal']
            risk = signals['risk_assessment']
            
            print(f"{stock_code}:")
            print(f"  信号: {composite['signal_strength']}")
            print(f"  评分: {composite['final_score']:.3f}")
            print(f"  置信度: {composite['confidence_level']:.3f}")
            print(f"  风险: {risk['overall_risk_level']}")
            print()
        else:
            print(f"{stock_code}: 分析失败 - {signals['error']}")
            
    except Exception as e:
        print(f"{stock_code}: 处理异常 - {e}")
```

## 📈 信号解读指南

### 信号强度分类
- **strong_buy**: 强烈买入信号 (评分 > 0.7)
- **buy**: 买入信号 (评分 > 0.4)
- **weak_buy**: 弱买入信号 (评分 > 0.2)
- **neutral**: 中性信号 (评分 -0.2 ~ 0.2)
- **weak_sell**: 弱卖出信号 (评分 < -0.2)
- **sell**: 卖出信号 (评分 < -0.4)
- **strong_sell**: 强烈卖出信号 (评分 < -0.7)

### 置信度评估
- **高置信度** (> 0.7): 信号可靠性高，可重点关注
- **中置信度** (0.4 - 0.7): 信号有一定参考价值
- **低置信度** (< 0.4): 信号不确定性较大，谨慎操作

### 风险等级
- **low**: 低风险，适合稳健投资
- **medium**: 中等风险，需要适度关注
- **high**: 高风险，建议谨慎或避免

## 📊 报告文件说明

系统会在 `reports/multi_timeframe/` 目录下生成以下报告：

### 每日分析报告
- **文件名**: `daily_report_YYYYMMDD_HHMMSS.json`
- **内容**: 市场概览、个股分析、投资建议、风险警告

### 策略绩效报告
- **文件名**: `strategy_performance_YYYYMMDD_HHMMSS.json`
- **内容**: 回测结果、绩效指标、策略对比、优化建议

### 监控摘要报告
- **文件名**: `monitoring_summary_YYYYMMDD_HHMMSS.json`
- **内容**: 监控统计、预警记录、系统性能、股票排名

## ⚙️ 配置和自定义

### 修改时间周期权重
```python
# 在 MultiTimeframeSignalGenerator 中修改
signal_weights = {
    '1day': 0.35,    # 主趋势权重
    '4hour': 0.25,   # 中期趋势权重
    '1hour': 0.20,   # 短期趋势权重
    '30min': 0.12,   # 入场时机权重
    '15min': 0.05,   # 精确入场权重
    '5min': 0.03     # 微调权重
}
```

### 调整信号阈值
```python
# 在 MultiTimeframeSignalGenerator 中修改
signal_thresholds = {
    'strong_buy': 0.7,
    'buy': 0.4,
    'weak_buy': 0.2,
    'neutral': 0.0,
    'weak_sell': -0.2,
    'sell': -0.4,
    'strong_sell': -0.7
}
```

### 自定义股票池
创建或修改 `core_stock_pool.json` 文件：
```json
{
  "stocks": {
    "sz300290": {"name": "荣科科技", "sector": "科技"},
    "sz002691": {"name": "冀凯股份", "sector": "制造"},
    "sh600690": {"name": "海尔智家", "sector": "家电"}
  }
}
```

## 🚨 注意事项

### 数据要求
- 确保有足够的历史数据（建议至少100个交易日）
- 5分钟数据和日线数据都需要可用
- 数据质量会影响分析结果的准确性

### 性能优化
- 单次分析建议不超过50只股票
- 监控模式下建议不超过20只股票
- 定期清理缓存以释放内存

### 风险提示
- 本系统仅供分析参考，不构成投资建议
- 任何投资决策都应结合基本面分析
- 请根据自身风险承受能力进行投资

## 🔧 故障排除

### 常见问题

**Q: 提示"数据获取失败"**
A: 检查股票代码格式，确保数据文件存在

**Q: 信号置信度很低**
A: 可能是数据质量问题或市场波动较大，建议观望

**Q: 回测结果异常**
A: 检查回测期间设置，确保有足够的历史数据

**Q: 监控系统无法启动**
A: 检查股票列表，确保至少有一只股票可以正常分析

### 日志查看
系统会输出详细的运行日志，可以通过日志信息定位问题：
- 数据加载问题
- 指标计算异常
- 信号生成错误
- 系统性能警告

## 📞 技术支持

如果遇到技术问题或需要功能定制，可以：
1. 查看系统日志获取详细错误信息
2. 运行测试脚本验证系统状态
3. 检查配置文件和数据文件
4. 参考API文档进行自定义开发

---

**版本**: v1.0  
**更新时间**: 2025年1月24日  
**系统状态**: 🟢 生产就绪