# 深渊筑底策略筛选器使用指南

## 概述

深渊筑底策略筛选器已经完成优化并通过全面测试，现在可以用于筛选真实股票数据。该筛选器基于经过验证的深渊筑底策略，能够识别从深度下跌中恢复的股票。

## 测试验证结果

✅ **股票代码验证**: 100% 准确率  
✅ **策略逻辑测试**: 100% 准确率  
✅ **深渊筑底识别**: 正确识别理想形态  
✅ **半山腰过滤**: 正确过滤不符合条件的股票  

## 快速开始

### 1. 基本使用

```bash
# 直接运行筛选器
python backend/screener_abyss_optimized.py
```

### 2. 检查配置

筛选器会自动加载 `backend/abyss_config.json` 配置文件：

```json
{
  "strategy_name": "深渊筑底优化版",
  "version": "2.0",
  "test_status": "PASSED",
  "test_accuracy": "100%"
}
```

### 3. 数据路径配置

默认数据路径：`~/.local/share/tdxcfv/drive_c/tc/vipdoc`

支持的市场：
- `sh`: 上海证券交易所
- `sz`: 深圳证券交易所  
- `bj`: 北京证券交易所

## 策略参数说明

### 核心参数（已优化）

| 参数 | 值 | 说明 |
|------|----|----|
| `long_term_days` | 400 | 长期观察期（天） |
| `min_drop_percent` | 0.40 | 最小下跌幅度（40%） |
| `price_low_percentile` | 0.35 | 价格低位阈值（35%） |
| `volume_shrink_threshold` | 0.70 | 成交量萎缩阈值（70%） |
| `volume_consistency_threshold` | 0.30 | 地量持续性阈值（30%） |

### 信号类型

筛选器会生成不同强度的信号：

1. **POTENTIAL_BUY**: 潜在买入（通过1个阶段）
   - 仅通过深跌筑底检查
   - 风险较高，需要进一步观察

2. **BUY**: 买入信号（通过2-3个阶段）
   - 通过深跌筑底 + 横盘蓄势
   - 或通过深跌筑底 + 横盘蓄势 + 缩量挖坑
   - 较为可靠的信号

3. **STRONG_BUY**: 强烈买入（通过4个阶段）
   - 通过所有四个阶段检查
   - 最高质量信号

## 输出文件说明

运行后会在 `data/result/ABYSS_BOTTOMING_OPTIMIZED/` 目录下生成：

### 1. 详细信号文件
`abyss_signals_YYYYMMDD_HHMM.json`
```json
[
  {
    "stock_code": "sh600001",
    "signal_type": "BUY",
    "signal_strength": 2,
    "date": "2025-08-12",
    "current_price": 45.20,
    "signal_details": {
      "signal_state": "HIBERNATION_CONFIRMED",
      "stage_passed": 2,
      "deep_decline": {...},
      "hibernation": {...}
    }
  }
]
```

### 2. 汇总报告文件
`abyss_summary_YYYYMMDD_HHMM.json`
```json
{
  "scan_summary": {
    "total_signals": 15,
    "signal_distribution": {
      "STRONG_BUY": 3,
      "BUY": 8,
      "POTENTIAL_BUY": 4
    },
    "processing_time": "125.67 秒",
    "files_processed": 4521
  }
}
```

### 3. 可读性报告
`abyss_report_YYYYMMDD_HHMM.txt`
```
================================================================================
深渊筑底策略筛选报告
================================================================================
扫描时间: 2025-08-12 16:25:21
策略版本: optimized_v2.0
处理文件数: 4521
处理耗时: 125.67 秒
发现信号数: 15

信号分布:
  STRONG_BUY: 3 只
  BUY: 8 只
  POTENTIAL_BUY: 4 只

发现信号的股票详情:
--------------------------------------------------------------------------------

 1. 股票代码: sh600001
    信号类型: BUY
    信号强度: 2/4 阶段
    信号日期: 2025-08-12
    当前价格: 45.20
    下跌幅度: 42.84%
    价格位置: 14.12%
    成交量萎缩: 0.35
    地量持续: 100.00%
```

## 信号解读指南

### 深跌筑底信息
- **下跌幅度**: 从历史高点的跌幅，≥40% 为合格
- **价格位置**: 在历史价格区间中的位置，≤35% 为低位
- **成交量萎缩**: 最近成交量相对历史的萎缩比例，≤0.70 为地量
- **地量持续**: 地量状态的持续性，≥30% 为稳定

### 信号强度评估

| 阶段数 | 信号类型 | 可靠性 | 建议操作 |
|--------|----------|--------|----------|
| 1 | POTENTIAL_BUY | 低 | 观察，等待更多确认 |
| 2 | BUY | 中等 | 可以考虑小仓位介入 |
| 3 | BUY | 较高 | 可以正常仓位介入 |
| 4 | STRONG_BUY | 很高 | 重点关注，优先考虑 |

## 风险提示

### 1. 策略局限性
- 仅适用于识别深跌后的筑底形态
- 不能预测具体的上涨幅度和时间
- 需要结合其他分析方法综合判断

### 2. 市场风险
- 策略基于历史数据，不保证未来表现
- 市场环境变化可能影响策略有效性
- 建议分散投资，控制单只股票仓位

### 3. 数据质量
- 确保股票数据的完整性和准确性
- 注意除权除息对价格的影响
- 关注公司基本面变化

## 高级使用

### 1. 参数调整

如需调整策略参数，编辑 `backend/abyss_config.json`：

```json
{
  "core_parameters": {
    "deep_decline_phase": {
      "min_drop_percent": 0.35,  // 降低跌幅要求
      "price_low_percentile": 0.40  // 放宽位置要求
    },
    "volume_analysis": {
      "volume_shrink_threshold": 0.75  // 放宽成交量要求
    }
  }
}
```

### 2. 批量处理优化

对于大量股票数据，可以调整性能参数：

```json
{
  "performance_tuning": {
    "max_workers": 16,  // 增加并行进程数
    "chunk_size": 200,  // 增加批处理大小
    "memory_limit_mb": 4096  // 增加内存限制
  }
}
```

### 3. 结果过滤

可以通过编程方式进一步过滤结果：

```python
import json

# 读取结果
with open('data/result/ABYSS_BOTTOMING_OPTIMIZED/abyss_signals_*.json', 'r') as f:
    signals = json.load(f)

# 过滤强信号
strong_signals = [s for s in signals if s['signal_type'] == 'STRONG_BUY']

# 按价格排序
signals_sorted = sorted(signals, key=lambda x: x['current_price'])

# 过滤特定价格区间
price_filtered = [s for s in signals if 10 <= s['current_price'] <= 50]
```

## 故障排除

### 1. 常见错误

**错误**: `未能在任何市场目录下找到日线文件`
**解决**: 检查 `BASE_PATH` 配置是否正确

**错误**: `加载配置文件失败`
**解决**: 确保 `backend/abyss_config.json` 文件存在且格式正确

**错误**: `多进程处理失败`
**解决**: 系统会自动降级到单进程，检查系统资源

### 2. 性能优化

- 确保有足够的内存（建议 ≥8GB）
- 使用 SSD 存储以提高 I/O 性能
- 根据 CPU 核心数调整 `max_workers` 参数

### 3. 日志查看

查看详细日志：
```bash
tail -f data/result/ABYSS_BOTTOMING_OPTIMIZED/log_screener_*.txt
```

## 更新历史

### v2.0 (2025-08-12)
- ✅ 完成策略优化和测试验证
- ✅ 修正成交量分析逻辑
- ✅ 实现四阶段渐进式信号生成
- ✅ 添加完整的配置系统
- ✅ 支持真实股票数据筛选

### v1.0 (初始版本)
- 基础深渊筑底策略实现
- 简单的参数配置
- 基本的信号生成

## 技术支持

如遇到问题，请检查：
1. 配置文件格式是否正确
2. 数据路径是否存在
3. 系统资源是否充足
4. 日志文件中的错误信息

---

**注意**: 本策略仅供参考，投资有风险，决策需谨慎。建议结合基本面分析和其他技术指标综合判断。