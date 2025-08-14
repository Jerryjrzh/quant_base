# 统一配置系统使用指南

## 概述

统一配置系统实现了前后端共享同一个策略配置文件的机制，解决了前后端配置不一致的问题。

## 系统架构

```
config/
└── unified_strategy_config.json    # 统一配置文件

backend/
├── config_manager.py               # 后端配置管理器
├── strategy_manager.py             # 策略管理器（已更新）
├── screening_api.py                # API接口（已更新）
└── app.py                          # 主应用（已更新）

frontend/js/
└── strategy-config.js              # 前端配置管理器
```

## 配置文件结构

### 统一配置文件 (`config/unified_strategy_config.json`)

```json
{
  "version": "2.0",
  "last_updated": "2025-08-14T10:00:00",
  "strategies": {
    "策略ID": {
      "id": "策略ID",
      "name": "策略名称",
      "version": "版本号",
      "enabled": true,
      "description": "策略描述",
      "priority": 1,
      "config": {
        // 策略参数配置
      },
      "risk_level": "风险等级",
      "expected_signals_per_day": "预期信号数",
      "suitable_market": ["适用市场"],
      "tags": ["标签"],
      "legacy_mapping": {
        "old_id": "旧策略ID",
        "api_id": "API调用ID"
      }
    }
  },
  "global_settings": {
    // 全局设置
  },
  "market_filters": {
    // 市场过滤器
  },
  "output_settings": {
    // 输出设置
  },
  "frontend_settings": {
    // 前端专用设置
  }
}
```

## 后端使用方法

### 1. 配置管理器

```python
from config_manager import config_manager

# 获取所有策略
strategies = config_manager.get_strategies()

# 获取单个策略
strategy = config_manager.get_strategy('策略ID')

# 启用/禁用策略
config_manager.enable_strategy('策略ID')
config_manager.disable_strategy('策略ID')

# 更新策略配置
config_manager.update_strategy('策略ID', new_config)

# 获取已启用的策略
enabled = config_manager.get_enabled_strategies()

# 兼容性映射
new_id = config_manager.find_strategy_by_old_id('OLD_ID')
```

### 2. 策略管理器集成

```python
from strategy_manager import strategy_manager

# 策略管理器自动使用统一配置
enabled_strategies = strategy_manager.get_enabled_strategies()
instance = strategy_manager.get_strategy_instance('策略ID')
```

### 3. API接口

新增API端点：
- `GET /api/config/unified` - 获取统一配置

## 前端使用方法

### 1. 配置管理器

```javascript
// 等待配置加载完成
await configManager.waitForLoad();

// 获取所有策略
const strategies = configManager.getStrategies();

// 获取已启用的策略
const enabled = configManager.getEnabledStrategies();

// 获取前端设置
const settings = configManager.getFrontendSettings();
```

### 2. 兼容性函数

```javascript
// 旧ID转新ID
const newId = mapOldToNewStrategyId('OLD_ID');

// 新ID转API ID
const apiId = mapNewToOldStrategyId('NEW_ID');

// 获取策略显示名称
const displayName = getStrategyDisplayName(strategy);
```

### 3. 自动加载策略列表

```javascript
// 在页面加载时调用
await loadAvailableStrategies();
```

## 兼容性处理

### 策略ID映射

系统支持旧策略ID到新策略ID的自动映射：

```json
{
  "legacy_mapping": {
    "old_id": "ABYSS_BOTTOMING",
    "api_id": "ABYSS_BOTTOMING"
  }
}
```

### 前端兼容性

前端保持了原有的函数接口，确保现有代码无需修改：

```javascript
// 这些函数仍然可用
mapOldToNewStrategyId()
mapNewToOldStrategyId()
getStrategyDisplayName()
```

## 配置验证

### 后端验证

```python
# 验证配置文件
errors = config_manager.validate_config()
if errors:
    print("配置错误:", errors)
```

### 前端验证

```javascript
// 检查策略兼容性
const compatible = isStrategyCompatible(strategy);
```

## 测试和调试

### 1. 后端测试

```bash
python test_unified_config.py
```

### 2. 前端测试

```bash
python start_unified_config_test.py
```

然后访问 http://localhost:5001 查看前端测试页面。

### 3. 完整系统测试

启动主应用并检查配置加载：

```bash
cd backend
python app.py
```

## 配置迁移

### 从旧配置迁移

如果你有现有的 `strategies_config.json`，可以手动迁移：

1. 复制策略配置到 `unified_strategy_config.json`
2. 添加兼容性映射
3. 更新配置结构

### 配置备份和恢复

```python
# 导出配置
backup_path = config_manager.export_config('backup.json')

# 导入配置
config_manager.import_config('backup.json', merge=True)
```

## 最佳实践

### 1. 配置管理

- 使用统一配置文件作为唯一数据源
- 定期备份配置文件
- 使用版本控制管理配置变更

### 2. 策略开发

- 新策略应在统一配置文件中注册
- 保持兼容性映射的准确性
- 使用描述性的策略ID和名称

### 3. 前端开发

- 使用 `configManager` 获取配置
- 等待配置加载完成再使用
- 使用兼容性函数处理ID映射

## 故障排除

### 常见问题

1. **配置加载失败**
   - 检查配置文件路径
   - 验证JSON格式
   - 查看日志错误信息

2. **策略映射错误**
   - 检查 `legacy_mapping` 配置
   - 验证策略ID的一致性

3. **前端配置不更新**
   - 清除浏览器缓存
   - 检查API接口是否正常
   - 验证CORS设置

### 调试技巧

1. 启用详细日志：
```python
logging.basicConfig(level=logging.DEBUG)
```

2. 检查配置验证：
```python
errors = config_manager.validate_config()
```

3. 前端控制台调试：
```javascript
console.log('配置状态:', configManager.loaded);
console.log('策略列表:', configManager.getStrategies());
```

## 更新日志

### v2.0 (2025-08-14)
- 实现统一配置系统
- 添加前后端配置管理器
- 支持兼容性映射
- 添加配置验证功能
- 完善测试和文档

## 总结

统一配置系统成功实现了前后端配置的统一管理，提供了：

✅ **统一数据源** - 单一配置文件管理所有策略
✅ **兼容性支持** - 自动处理旧ID到新ID的映射
✅ **实时同步** - 前后端配置自动同步
✅ **易于维护** - 集中化配置管理
✅ **向后兼容** - 保持现有代码接口不变

现在前后端可以通过同一个配置文件来加载策略配置，确保了数据的一致性和系统的可维护性。