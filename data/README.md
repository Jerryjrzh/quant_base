# 数据目录结构说明

## 📁 目录结构

```
data/
├── backtest/                    # 回测数据目录
│   ├── cache/                   # 回测缓存文件
│   │   ├── backtest_cache_*.json    # 个股回测缓存
│   │   └── ...
│   └── reports/                 # 回测报告
│       ├── backtest_report_*.json   # 回测分析报告
│       └── ...
├── portfolio/                   # 持仓数据目录
│   ├── portfolio.json           # 主持仓数据文件
│   ├── portfolio_scan_cache.json   # 持仓扫描缓存
│   └── portfolio.json.backup_*  # 持仓数据备份
├── result/                      # 筛选结果目录
│   ├── ABYSS_BOTTOMING_OPTIMIZED/  # 深渊筑底策略结果
│   ├── TRIPLE_CROSS/            # 三重金叉策略结果
│   ├── MACD_ZERO_AXIS/          # MACD零轴策略结果
│   └── ...                      # 其他策略结果
├── cache/                       # 通用缓存目录
└── smart_cache/                 # 智能缓存目录
```

## 📊 各目录说明

### backtest/ - 回测数据
- **cache/**: 存储个股回测缓存数据，提升回测性能
- **reports/**: 存储回测分析报告和统计数据

### portfolio/ - 持仓管理
- **portfolio.json**: 主持仓数据文件，包含所有持仓记录
- **portfolio_scan_cache.json**: 持仓扫描缓存，提升分析速度
- **备份文件**: 自动生成的持仓数据备份

### result/ - 筛选结果
- 按策略名称分类存储筛选结果
- 包含信号数据、统计报告、日志文件等

### cache/ & smart_cache/ - 缓存系统
- 存储系统运行时的临时缓存数据
- 提升数据加载和处理性能

## 🔧 使用说明

### 回测缓存管理
```python
# 回测缓存文件命名规则
backtest_cache_{stock_code}.json

# 示例
backtest_cache_sz000001.json  # 平安银行回测缓存
backtest_cache_sh600036.json  # 招商银行回测缓存
```

### 持仓数据管理
```python
# 持仓数据结构
{
  "holdings": [
    {
      "stock_code": "sz000001",
      "purchase_price": 12.50,
      "quantity": 1000,
      "purchase_date": "2025-01-15",
      "notes": "技术面良好"
    }
  ]
}
```

### 筛选结果管理
- 每个策略有独立的结果目录
- 按日期时间戳命名结果文件
- 包含详细的筛选日志和统计信息

## 🚀 性能优化

### 缓存机制
- 回测缓存：避免重复计算历史数据
- 持仓缓存：提升持仓分析速度
- 智能缓存：根据数据变化自动更新

### 数据清理
```bash
# 清理过期缓存（建议定期执行）
find data/backtest/cache -name "*.json" -mtime +30 -delete

# 清理旧的筛选日志
find data/result -name "*.log" -mtime +7 -delete
```

## 📝 维护建议

1. **定期备份**: 重要数据定期备份到外部存储
2. **缓存清理**: 定期清理过期的缓存文件
3. **空间监控**: 监控数据目录磁盘使用情况
4. **权限管理**: 确保应用有足够的读写权限

## ⚠️ 注意事项

- 不要手动修改缓存文件，可能导致数据不一致
- 持仓数据修改前建议先备份
- 筛选结果文件较大时注意磁盘空间
- 系统升级前请备份整个data目录