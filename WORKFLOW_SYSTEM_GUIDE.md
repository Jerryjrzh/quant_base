# 三阶段交易决策支持系统 - 工作流系统使用指南

## 系统概述

根据 `nextstep.md` 中的第一步迭代计划，我们已经成功实现了**系统架构升级**中的核心组件：

### ✅ 已完成的功能

1. **主控工作流脚本** (`run_workflow.py`)
   - 实现三阶段工作流的调度与管理
   - 支持命令行参数控制执行不同阶段
   - 添加日志记录与错误处理机制

2. **工作流管理器** (`workflow_manager.py`)
   - 核心业务逻辑实现
   - 配置管理与状态跟踪
   - 三阶段执行框架

3. **配置系统** (`workflow_config.json`)
   - 统一配置文件管理所有参数
   - 支持不同阶段的独立配置
   - 灵活的执行频率控制

4. **演示系统** (`quick_start.py`)
   - 交互式演示界面
   - 模拟三阶段工作流程
   - 用户友好的体验

5. **测试框架** (`test_workflow_system.py`)
   - 基本功能测试
   - 单元测试支持
   - 环境验证机制

## 系统架构

```
三阶段交易决策支持系统
├── 主控脚本 (run_workflow.py)
├── 工作流管理器 (workflow_manager.py)
├── 配置文件 (workflow_config.json)
├── 快速启动 (quick_start.py)
├── 测试系统 (test_workflow_system.py)
└── 数据目录
    ├── analysis_cache/     # 分析结果缓存
    ├── reports/           # 每日交易报告
    ├── logs/              # 系统日志
    └── core_stock_pool.json # 核心观察池
```

## 三阶段工作流

### 第一阶段：深度海选与参数优化
- **目标**：对大量股票进行参数优化，建立高质量核心观察池
- **频率**：每周执行（可配置）
- **输出**：优化参数缓存 + 核心观察池

### 第二阶段：每日验证与信号触发
- **目标**：快速验证核心池股票，生成交易信号
- **频率**：每日执行（可配置）
- **输出**：交易信号报告

### 第三阶段：绩效跟踪与反馈
- **目标**：跟踪信号表现，动态调整核心池
- **频率**：每日执行（可配置）
- **输出**：绩效报告 + 池调整

## 使用方法

### 1. 基本命令

```bash
# 查看系统状态
python run_workflow.py --status

# 运行完整工作流
python run_workflow.py

# 运行指定阶段
python run_workflow.py --phase phase1  # 深度海选
python run_workflow.py --phase phase2  # 每日验证
python run_workflow.py --phase phase3  # 绩效跟踪

# 强制执行（忽略时间限制）
python run_workflow.py --force

# 详细输出模式
python run_workflow.py --verbose
```

### 2. 演示模式

```bash
# 启动交互式演示
python quick_start.py
```

### 3. 系统测试

```bash
# 运行完整测试
python test_workflow_system.py
```

## 配置说明

### 主要配置项 (`workflow_config.json`)

```json
{
  "phase1": {
    "enabled": true,
    "frequency_days": 7,           # 执行频率（天）
    "max_stocks": 1000,            # 最大处理股票数
    "min_score_threshold": 0.6,    # 最低评分阈值
    "parallel_workers": 4          # 并行工作进程数
  },
  "phase2": {
    "enabled": true,
    "frequency_days": 1,           # 每日执行
    "core_pool_size": 200,         # 核心池大小
    "signal_confidence_threshold": 0.7  # 信号置信度阈值
  },
  "phase3": {
    "enabled": true,
    "frequency_days": 1,           # 每日执行
    "tracking_days": 30,           # 绩效跟踪天数
    "performance_threshold": 0.5,   # 绩效阈值
    "credibility_decay": 0.95      # 信任度衰减因子
  }
}
```

## 文件说明

### 核心文件
- `run_workflow.py`: 主控脚本，系统入口点
- `workflow_manager.py`: 工作流管理器，核心业务逻辑
- `workflow_config.json`: 系统配置文件
- `core_stock_pool.json`: 核心观察池数据

### 状态文件
- `workflow_state.json`: 工作流运行状态
- `workflow.log`: 系统运行日志
- `reports/daily_signals_YYYYMMDD.json`: 每日交易信号报告

### 辅助文件
- `quick_start.py`: 快速启动演示
- `test_workflow_system.py`: 系统测试脚本

## 系统特性

### 1. 智能调度
- 基于时间频率的自动调度
- 状态持久化，支持中断恢复
- 灵活的强制执行模式

### 2. 配置管理
- 统一的JSON配置文件
- 支持运行时配置合并
- 环境适应性配置

### 3. 日志系统
- 分级日志记录
- 文件轮转支持
- 实时控制台输出

### 4. 错误处理
- 完善的异常捕获
- 优雅的错误恢复
- 详细的错误报告

### 5. 扩展性
- 模块化设计
- 插件式架构
- 易于集成现有组件

## 下一步开发计划

根据 `nextstep.md` 的规划，接下来需要实现：

### 1. 核心观察池数据库设计 (`stock_pool_manager.py`)
- 使用SQLite实现持久化存储
- 设计股票评级、参数、信任度等字段
- 提供API接口供其他模块调用

### 2. 功能模块开发
- **第一阶段模块**：整合现有的参数优化和筛选功能
- **第二阶段模块**：开发每日信号扫描器
- **第三阶段模块**：实现绩效跟踪和反馈机制

### 3. 用户界面优化
- 交互式报告生成器
- 可视化图表展示
- 邮件/消息推送功能

## 故障排除

### 常见问题

1. **导入错误**
   ```
   ImportError: cannot import name 'ParallelOptimizer'
   ```
   - 检查backend目录中的模块是否存在
   - 确认类名是否正确

2. **配置文件错误**
   ```
   KeyError: 'frequency_days'
   ```
   - 删除现有配置文件，让系统重新生成
   - 或手动添加缺失的配置项

3. **权限问题**
   ```
   PermissionError: [Errno 13] Permission denied
   ```
   - 确保有写入logs、reports目录的权限
   - 检查文件系统空间是否充足

### 调试模式

```bash
# 启用详细日志
python run_workflow.py --verbose

# 试运行模式
python run_workflow.py --dry-run

# 查看系统状态
python run_workflow.py --status
```

## 总结

我们已经成功完成了nextstep.md第一步计划中的**系统架构升级**：

✅ **创建主控工作流脚本** - 完成
- 实现了完整的三阶段工作流调度系统
- 支持灵活的命令行参数控制
- 添加了完善的日志记录与错误处理

这为后续的功能模块开发奠定了坚实的基础。系统现在具备了：
- 统一的配置管理
- 智能的调度机制  
- 完善的状态跟踪
- 用户友好的界面
- 可靠的错误处理

下一步可以开始实现核心观察池数据库和具体的功能模块。