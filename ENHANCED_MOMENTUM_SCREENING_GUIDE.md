# 增强版强势股筛选系统使用指南

## 🎯 系统概述

本系统基于你的需求设计，在399个季度筛选样本基础上，通过MA、RSI、KDJ、MACD等技术指标回测，识别强势股票（价格很少触及MA13或MA20），按强势弱势排序，并在不同周期测试确认。

### 核心特点
- ✅ 基于季度回测结果进一步筛选
- ✅ 识别强势股票（95%时间在MA之上）
- ✅ 多技术指标综合分析
- ✅ 多周期验证确认
- ✅ 智能操作建议生成

## 📋 系统架构

```
季度回测结果 (399个样本)
    ↓
强势股分析 (MA/RSI/KDJ/MACD)
    ↓
多周期验证 (日线/周线/月线)
    ↓
最终推荐 (按强势排序)
```

## 🚀 快速开始

### 1. 准备工作

确保你有季度回测结果文件：
```bash
# 检查是否有季度回测文件
ls precise_quarterly_strategy_*.json
```

### 2. 基础使用

```bash
# 使用最新的季度回测结果进行筛选
python enhanced_momentum_screener.py \
  --quarterly-result precise_quarterly_strategy_2025Q2_20250725_104330.json
```

### 3. 自定义参数

```bash
# 更严格的筛选条件
python enhanced_momentum_screener.py \
  --quarterly-result precise_quarterly_strategy_2025Q2_20250725_104330.json \
  --min-momentum-score 70 \
  --min-timeframe-strength 70 \
  --max-recommendations 10
```

## 📊 核心功能详解

### 1. 强势股分析 (`momentum_strength_analyzer.py`)

**核心指标：**
- **MA强势得分**：计算价格在MA13/MA20之上的时间比例
- **技术指标状态**：RSI、KDJ、MACD当前状态
- **动量分析**：5日、10日、20日价格动量
- **成交量分析**：量价配合情况

**强势判断标准：**
```python
# 强势股特征
- 95%时间价格在MA之上
- 很少触及MA13或MA20（容忍度2%）
- 技术指标配合良好
- 成交量有效放大
```

**使用示例：**
```bash
# 单独运行强势分析
python backend/momentum_strength_analyzer.py \
  --quarterly-result precise_quarterly_strategy_2025Q2_20250725_104330.json \
  --min-score 65 \
  --strength-threshold 0.95 \
  --save-report
```

### 2. 多周期验证 (`multi_timeframe_validator.py`)

**验证维度：**
- **日线分析**：60天短期趋势
- **周线分析**：20周中期趋势  
- **月线分析**：6月长期趋势

**验证指标：**
- 趋势方向一致性
- MA多头排列确认
- 支撑阻力位分析
- 成交量趋势验证

**使用示例：**
```bash
# 单独运行多周期验证
python backend/multi_timeframe_validator.py \
  --stock-list precise_quarterly_strategy_2025Q2_20250725_104330.json \
  --min-strength 65 \
  --save-report
```

## 📈 筛选流程详解

### 第一步：加载季度股票池
```python
# 从季度回测结果中提取核心股票池
quarterly_pool = screener.load_quarterly_results(quarterly_file)
# 示例：399个样本 → 提取核心股票池
```

### 第二步：强势股分析
```python
# 配置强势分析参数
momentum_config = MomentumConfig(
    ma_periods=[13, 20, 34, 55],     # MA周期
    strength_threshold=0.95,          # 95%时间在MA之上
    touch_tolerance=0.02,             # 2%触及容忍度
    lookback_days=60                  # 回测天数
)

# 执行分析
momentum_results = screener.run_momentum_analysis(quarterly_pool, momentum_config)
```

### 第三步：多周期验证
```python
# 配置多周期验证参数
timeframe_config = TimeframeConfig(
    daily_period=60,                  # 日线60天
    weekly_period=20,                 # 周线20周
    monthly_period=6,                 # 月线6月
    daily_strength_threshold=0.8,     # 日线强势阈值
    weekly_strength_threshold=0.85,   # 周线强势阈值
    monthly_strength_threshold=0.9    # 月线强势阈值
)

# 执行验证
validation_results = screener.run_timeframe_validation(qualified_stocks, timeframe_config)
```

### 第四步：生成最终推荐
```python
# 综合评分和推荐
final_recommendations = screener.generate_final_recommendations(
    min_momentum_score=60,            # 最低强势得分
    min_timeframe_strength=60,        # 最低多周期得分
    max_recommendations=20            # 最大推荐数量
)
```

## 📊 输出结果解读

### 1. 强势排行榜
```
排名  代码      综合得分  强势得分  多周期得分  趋势    操作信号
1     sh603238  85.2     88.5     82.1       上升    买入
2     sz300139  83.7     85.2     81.5       上升    买入
3     sh601606  82.1     87.3     78.9       上升    回调
```

### 2. 详细分析报告
```
⭐ 强烈推荐详细分析:
1. sh603238 - 综合得分: 85.2
   📈 技术面分析:
     • 强势等级: 强势
     • 整体强势得分: 0.96
     • RSI: 65.2 (正常)
     • MACD: 金叉
     • 成交量: 放量
   
   🔍 多周期分析:
     • 综合趋势: 上升
     • 趋势一致性: 0.85
     • 多周期强势: 82.1
     • 持有周期: 中期
   
   💰 操作建议:
     • 入场时机: 立即
     • 风险等级: 低
     • 信心度: 0.82
   
   📊 关键价位:
     • 关键支撑: ¥12.80
     • 关键阻力: ¥15.20
     • 建议止损: ¥12.16
     • 目标价位: ¥15.20 ¥16.72
```

### 3. 操作建议分类

**立即买入**：
- 多周期趋势一致向上
- 技术指标配合良好
- 接近关键支撑位

**回调买入**：
- 整体趋势向上
- 当前位置偏高
- 等待回调机会

**突破买入**：
- 震荡整理状态
- 等待向上突破确认

**观望**：
- 趋势不明确
- 技术指标混乱
- 风险较高

## 🛠️ 高级配置

### 1. 严格筛选模式
```python
# 更严格的强势要求
momentum_config = MomentumConfig(
    strength_threshold=0.98,    # 98%时间在MA之上
    touch_tolerance=0.01,       # 1%触及容忍度
    lookback_days=90           # 更长回测期
)

# 更严格的多周期要求
timeframe_config = TimeframeConfig(
    daily_strength_threshold=0.85,
    weekly_strength_threshold=0.90,
    monthly_strength_threshold=0.95
)
```

### 2. 宽松筛选模式
```python
# 适中的强势要求
momentum_config = MomentumConfig(
    strength_threshold=0.85,    # 85%时间在MA之上
    touch_tolerance=0.05,       # 5%触及容忍度
    lookback_days=45           # 较短回测期
)
```

## 📁 文件结构

```
├── enhanced_momentum_screener.py          # 主筛选系统
├── demo_enhanced_momentum_screening.py    # 演示脚本
├── backend/
│   ├── momentum_strength_analyzer.py      # 强势股分析器
│   ├── multi_timeframe_validator.py       # 多周期验证器
│   └── precise_quarterly_backtester.py    # 精确季度回测器
├── results/                               # 结果输出目录
└── ENHANCED_MOMENTUM_SCREENING_GUIDE.md   # 本指南
```

## 🎯 实战使用建议

### 1. 日常筛选流程
```bash
# 每周执行一次完整筛选
python enhanced_momentum_screener.py \
  --quarterly-result latest_quarterly_result.json \
  --min-momentum-score 65 \
  --min-timeframe-strength 65 \
  --max-recommendations 15
```

### 2. 市场强势时
```bash
# 提高筛选标准
python enhanced_momentum_screener.py \
  --quarterly-result latest_quarterly_result.json \
  --min-momentum-score 75 \
  --min-timeframe-strength 75 \
  --max-recommendations 10
```

### 3. 市场弱势时
```bash
# 降低筛选标准，重点防守
python enhanced_momentum_screener.py \
  --quarterly-result latest_quarterly_result.json \
  --min-momentum-score 55 \
  --min-timeframe-strength 55 \
  --max-recommendations 20
```

## ⚠️ 风险控制建议

### 1. 仓位管理
- 单股仓位不超过20%
- 总仓位根据市场环境调整
- 强烈推荐股票可适当加仓

### 2. 止损策略
- 严格按照系统建议的止损位执行
- 跌破关键支撑位及时止损
- 技术形态破坏时果断离场

### 3. 止盈策略
- 分批止盈，不要一次性清仓
- 达到第一目标价位减仓1/3
- 达到第二目标价位减仓1/2
- 剩余仓位设置移动止损

## 🔧 故障排除

### 1. 常见问题

**Q: 提示"没有找到季度回测结果文件"**
```bash
# 检查文件是否存在
ls precise_quarterly_strategy_*.json

# 如果没有，先运行季度回测
python quick_start_quarterly_backtest.py
```

**Q: 分析结果为空**
```bash
# 降低筛选标准重试
python enhanced_momentum_screener.py \
  --quarterly-result your_file.json \
  --min-momentum-score 50 \
  --min-timeframe-strength 50
```

**Q: 数据加载失败**
```bash
# 检查数据路径
ls ~/.local/share/tdxcfv/drive_c/tc/vipdoc/

# 确保有足够的历史数据
```

### 2. 性能优化

**并发处理**：
- 系统默认使用4个线程并行处理
- 可以根据机器性能调整线程数

**缓存机制**：
- 数据会自动缓存，避免重复加载
- 重启程序会清空缓存

## 📞 技术支持

如果遇到问题，请检查：
1. Python环境和依赖包
2. 数据文件路径和权限
3. 季度回测结果文件格式
4. 系统内存和CPU资源

## 🎉 总结

这个增强版强势股筛选系统完全按照你的需求设计：

✅ **基于季度筛选结果**：从399个样本开始筛选  
✅ **技术指标回测**：MA、RSI、KDJ、MACD综合分析  
✅ **强势股识别**：价格很少触及MA13/MA20  
✅ **多周期验证**：日线、周线、月线确认  
✅ **智能排序**：按强势程度和综合得分排序  
✅ **操作建议**：提供具体的买卖时机建议  

通过这个系统，你可以从大量股票中快速筛选出真正的强势股票，提高投资胜率！