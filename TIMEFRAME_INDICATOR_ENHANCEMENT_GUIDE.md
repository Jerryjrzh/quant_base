# 多周期指标显示增强功能指南

## 功能概述

本次更新为前端指标显示系统增加了以下功能：

1. **指标名称和参数标注** - 在各指标区域左上角显示指标名称和参数
2. **多周期数据支持** - 支持日线、周线、月线数据切换
3. **分时数据支持** - 支持5分钟、10分钟、15分钟、30分钟、60分钟数据切换

## 新增控件

### 1. 周期选择器
```html
<select id="timeframe-select">
    <option value="daily">日线</option>
    <option value="weekly">周线</option>
    <option value="monthly">月线</option>
</select>
```

### 2. 分时选择器
```html
<select id="interval-select">
    <option value="5min">5分钟</option>
    <option value="10min">10分钟</option>
    <option value="15min">15分钟</option>
    <option value="30min">30分钟</option>
    <option value="60min">60分钟</option>
</select>
```

## 指标标注功能

### 实现方式
使用ECharts的`graphic`配置项在图表左上角添加文本标注：

```javascript
graphic: [
    {
        type: 'text',
        left: '8%',
        top: '8%',
        style: {
            text: 'K线 & MA(13,45)',
            fontSize: 12,
            fontWeight: 'bold',
            fill: '#666'
        }
    },
    // ... 其他指标标注
]
```

### 标注内容
- **K线区域**: `K线 & MA(13,45)`
- **RSI区域**: `RSI(6,12,24)`
- **KDJ区域**: `KDJ(27,3,3)`
- **MACD区域**: `MACD(12,26,9)`

## 后端API增强

### 新增参数支持

#### `/api/analysis/<stock_code>`
```
GET /api/analysis/sz000001?strategy=PRE_CROSS&adjustment=forward&timeframe=daily&interval=5min
```

参数说明：
- `timeframe`: 数据周期 (`daily`, `weekly`, `monthly`)
- `interval`: 分时间隔 (`5min`, `10min`, `15min`, `30min`, `60min`)

#### `/api/trading_advice/<stock_code>`
```
GET /api/trading_advice/sz000001?strategy=PRE_CROSS&adjustment=forward&timeframe=daily&interval=5min
```

### 数据处理逻辑

#### 1. 多周期数据获取
```python
def get_timeframe_data(stock_code, timeframe='daily', interval='5min'):
    """获取指定周期的数据"""
    # 分时数据处理
    if interval in ['5min', '10min', '15min', '30min', '60min']:
        # 从5分钟数据重采样
        
    # 日线数据处理
    elif timeframe == 'daily':
        # 直接加载日线数据
        
    # 周线/月线数据处理
    elif timeframe in ['weekly', 'monthly']:
        # 从日线数据重采样
```

#### 2. 时间格式处理
```python
# 根据周期类型格式化日期
if interval in ['5min', '10min', '15min', '30min', '60min']:
    # 分时数据显示时间
    df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d %H:%M')
else:
    # 日线、周线、月线数据只显示日期
    df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d')
```

## 前端交互增强

### 1. 自动刷新机制
当用户切换周期或分时设置时，自动重新加载图表数据：

```javascript
// 周期和分时设置变化时重新加载图表
if (timeframeSelect) timeframeSelect.addEventListener('change', () => {
    if (stockSelect.value) loadChart();
});

if (intervalSelect) intervalSelect.addEventListener('change', () => {
    if (stockSelect.value) loadChart();
});
```

### 2. 标题动态更新
图表标题会根据当前选择的周期和分时动态更新：

```javascript
const timeframeText = {
    'daily': '日线',
    'weekly': '周线', 
    'monthly': '月线'
}[timeframe] || '日线';

title: {
    text: `${stockCode} - ${strategy}策略分析 (${timeframeText} - ${interval})`,
    left: 'center',
    textStyle: { fontSize: 16 }
}
```

## 数据回退机制

为了确保系统稳定性，实现了多层数据回退机制：

1. **分时数据回退**: 如果分时数据文件不存在或加载失败，自动回退到日线数据
2. **重采样失败回退**: 如果数据重采样失败，回退到原始数据源
3. **错误处理**: 所有数据加载过程都有完整的错误处理和日志记录

## 测试验证

### 1. 功能测试脚本
```bash
python test_timeframe_indicator_display.py
```

### 2. 前端测试页面
```
test_indicator_labels_display.html
```

### 3. 测试覆盖范围
- ✅ 多周期数据加载 (日线、周线、月线)
- ✅ 分时数据加载 (5min-60min)
- ✅ 指标计算正确性
- ✅ 时间格式处理
- ✅ 交易建议生成
- ✅ 错误处理和回退机制

## 使用示例

### 1. 查看日线数据
1. 选择股票代码
2. 周期选择"日线"
3. 分时选择"5分钟"
4. 点击刷新或自动加载

### 2. 查看周线数据
1. 周期选择"周线"
2. 系统自动从日线数据重采样生成周线数据
3. 图表标题显示"周线"标识

### 3. 查看分时数据
1. 分时选择"15分钟"
2. 系统从5分钟数据重采样生成15分钟数据
3. 时间轴显示具体时间点

## 技术特点

### 1. 响应式设计
- 控件布局自适应
- 图表大小动态调整
- 移动端友好

### 2. 性能优化
- 数据缓存机制
- 按需加载
- 智能回退

### 3. 用户体验
- 实时反馈
- 错误提示
- 加载状态显示

## 配置说明

### 指标参数配置
当前使用的指标参数：
- **MA**: 13日、45日移动平均线
- **RSI**: 6日、12日、24日相对强弱指标
- **KDJ**: 27日RSV，3日K值，3日D值
- **MACD**: 12日快线，26日慢线，9日信号线

### 自定义参数
如需修改指标参数，可在后端`indicators.py`中调整相应配置。

## 故障排除

### 常见问题

1. **分时数据显示为日线数据**
   - 原因: 分时数据文件(.lc5)不存在
   - 解决: 系统自动回退到日线数据，这是正常行为

2. **周线/月线数据点较少**
   - 原因: 从日线数据重采样，数据点自然减少
   - 解决: 这是正常现象，周线约为日线的1/5，月线约为日线的1/20

3. **指标标注不显示**
   - 原因: ECharts版本兼容性问题
   - 解决: 确保使用ECharts 5.3.3或更高版本

### 调试信息
后端会输出详细的调试信息：
```
📊 复权处理 sz000001: forward
⚠️ 分时数据文件不存在，回退到日线数据
```

## 更新日志

### v1.0.0 (2025-07-29)
- ✅ 新增指标名称和参数标注功能
- ✅ 新增多周期数据支持 (日线、周线、月线)
- ✅ 新增分时数据支持 (5min-60min)
- ✅ 优化数据加载和错误处理机制
- ✅ 完善前端交互体验
- ✅ 添加完整的测试验证

## 后续计划

1. **更多指标支持**: 布林带、威廉指标等
2. **自定义参数**: 用户可自定义指标参数
3. **数据导出**: 支持图表和数据导出功能
4. **实时数据**: 集成实时行情数据源
5. **移动端优化**: 进一步优化移动端显示效果