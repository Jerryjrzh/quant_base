# 📈 股票筛选与分析平台

一个完整的量化交易分析平台，集成了前后端分离架构、多策略筛选、持仓管理、多周期分析等功能。

## 🚀 核心功能特性

### 📊 策略筛选系统
- **统一配置架构**: 前后端共享配置文件，确保数据一致性
- **多策略支持**: 深渊筑底、三重金叉、MACD零轴、周线金叉等5+策略
- **动态策略加载**: 支持策略热插拔，无需重启系统
- **智能筛选引擎**: 集成胜率过滤器，自动排除低效信号
- **质量评分系统**: 基于多维度技术指标的信号质量评分

### 💼 持仓管理系统
- **完整持仓管理**: 添加、编辑、删除持仓记录
- **深度技术分析**: MA、MACD、KDJ、RSI、布林带等多指标分析
- **智能操作建议**: 买入、卖出、持有、加仓、减仓、止损建议
- **风险评估系统**: 高/中/低风险等级，波动率分析
- **时间周期分析**: 基于历史周期预测最佳操作时机

### 📈 多周期分析系统
- **6个时间周期**: 从5分钟到日线的协同分析
- **综合信号生成**: 多周期信号加权合成，提高准确性
- **实时监控模式**: 持续监控股票信号变化
- **回测验证系统**: 历史数据验证策略有效性
- **智能预警通知**: 关键信号变化及时提醒

### 🔧 技术架构特性
- **前后端解耦**: 策略与数据分离，逻辑与显示分离
- **模块化设计**: 每个功能独立模块，便于维护和扩展
- **REST API接口**: 完整的API体系，支持第三方集成
- **配置化管理**: 所有参数通过配置文件管理，支持热更新
- **多进程优化**: 并行处理提升筛选性能

## 📦 项目架构

```
├── backend/                          # 后端核心
│   ├── app.py                       # Flask API 主服务器
│   ├── config_manager.py            # 统一配置管理器
│   ├── strategy_manager.py          # 策略管理器
│   ├── universal_screener.py        # 通用筛选框架
│   ├── screening_api.py             # 筛选API接口
│   ├── portfolio_manager.py         # 持仓管理器
│   ├── multi_timeframe_*.py         # 多周期分析模块
│   ├── strategies/                  # 策略目录
│   │   ├── base_strategy.py         # 策略基类
│   │   ├── abyss_bottoming_strategy.py    # 深渊筑底策略
│   │   ├── triple_cross_strategy.py       # 三重金叉策略
│   │   ├── macd_zero_axis_strategy.py     # MACD零轴策略
│   │   └── weekly_golden_cross_ma_strategy.py  # 周线金叉策略
│   ├── indicators.py               # 技术指标库
│   ├── backtester.py              # 回测引擎
│   └── data_loader.py             # 数据加载器
├── frontend/                       # 前端界面
│   ├── index.html                 # 主界面
│   ├── js/
│   │   ├── app.js                 # 主应用逻辑
│   │   └── strategy-config.js     # 策略配置管理
│   └── css/                       # 样式文件
├── config/                        # 配置文件
│   └── unified_strategy_config.json  # 统一策略配置
├── data/                          # 数据目录
│   ├── portfolio.json             # 持仓数据
│   └── result/                    # 筛选结果
├── doc/                           # 技术文档
│   ├── README.md                  # 文档索引
│   ├── architecture/              # 架构文档
│   ├── modules/                   # 模块文档
│   └── debugging/                 # 调试指南
└── reports/                       # 分析报告
    └── multi_timeframe/           # 多周期分析报告
```

## 🎯 系统概览

### 设计理念

本平台采用现代化的微服务架构设计，实现了完全的前后端分离和模块化设计：

- **策略与数据解耦**: 策略修改不影响数据读取，支持策略热插拔
- **逻辑与显示分离**: 筛选逻辑与前端展示完全分离，便于维护
- **配置驱动**: 所有参数通过配置文件管理，支持动态调整
- **高可扩展性**: 插件式架构，便于添加新策略和功能模块

### 核心架构

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   前端界面层     │    │   API接口层     │    │   业务逻辑层     │
│                │    │                │    │                │
│ • 策略配置界面   │◄──►│ • 策略管理API   │◄──►│ • 策略管理器     │
│ • 持仓管理界面   │    │ • 筛选API      │    │ • 筛选引擎      │
│ • 图表展示      │    │ • 持仓API      │    │ • 持仓管理器     │
│ • 多周期分析    │    │ • 分析API      │    │ • 多周期分析器   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                      │
                       ┌─────────────────┐    ┌─────────────────┐
                       │   配置管理层     │    │   数据访问层     │
                       │                │    │                │
                       │ • 统一配置管理   │◄──►│ • 数据加载器     │
                       │ • 策略配置      │    │ • 技术指标库     │
                       │ • 参数验证      │    │ • 缓存管理      │
                       └─────────────────┘    └─────────────────┘
```

### 数据流程

```
1. 策略筛选流程:
[股票数据] → [策略管理器] → [筛选引擎] → [结果存储] → [API接口] → [前端展示]

2. 持仓管理流程:
[持仓数据] → [持仓管理器] → [技术分析] → [操作建议] → [风险评估] → [前端展示]

3. 多周期分析流程:
[多周期数据] → [数据同步器] → [信号生成器] → [综合分析] → [报告生成] → [前端展示]
```

## 🚀 快速开始

### 环境准备

```bash
# 1. 克隆项目
git clone <repository-url>
cd stock-analysis-platform

# 2. 安装依赖
pip install -r requirement.txt

# 3. 验证系统
python test_unified_config.py
```

### 启动系统

```bash
# 启动主服务器
cd backend
python app.py

# 浏览器访问
http://localhost:5000
```

## 📊 主要功能使用

### 1. 策略筛选系统

#### 统一筛选器使用
```bash
# 运行所有启用的策略
python backend/universal_screener.py

# 运行特定策略
python backend/universal_screener.py --strategy 深渊筑底策略_v2.0

# 查看可用策略
python backend/universal_screener.py --list
```

#### 深渊筑底策略
```bash
# 专门运行深渊筑底筛选
python run_abyss_screener.py

# 查看筛选结果
ls data/result/ABYSS_BOTTOMING_OPTIMIZED/
```

#### Web界面操作
1. 打开浏览器访问 `http://localhost:5000`
2. 点击 "⚙️ 策略配置" 管理策略
3. 选择策略进行筛选
4. 查看筛选结果和图表分析

### 2. 持仓管理系统

#### 基本操作
```bash
# 演示持仓管理功能
python demo_portfolio_management.py

# 启动Web界面
python backend/app.py
# 访问 http://localhost:5000 点击 "💼 持仓管理"
```

#### 功能特性
- **添加持仓**: 股票代码、价格、数量、日期
- **深度扫描**: 技术指标分析、操作建议、风险评估
- **智能提醒**: 补仓价、减仓价、止损价提醒
- **时间分析**: 持仓周期、预期到顶时间

### 3. 多周期分析系统

#### 三种运行模式
```bash
# 综合分析模式
python run_multi_timeframe_analysis.py --mode analysis --stocks sz300290

# 回测分析模式
python run_multi_timeframe_analysis.py --mode backtest --stocks sz300290 --days 90

# 实时监控模式
python run_multi_timeframe_analysis.py --mode monitor --stocks sz300290 --duration 60
```

#### API使用示例
```python
from backend.multi_timeframe_signal_generator import MultiTimeframeSignalGenerator

# 初始化
signal_generator = MultiTimeframeSignalGenerator()

# 生成信号
signals = signal_generator.generate_composite_signals('sz300290')
print(f"信号强度: {signals['composite_signal']['signal_strength']}")
print(f"置信度: {signals['composite_signal']['confidence_level']:.3f}")
```

## 🔧 配置管理

### 统一配置系统

所有策略配置统一管理在 `config/unified_strategy_config.json`：

```json
{
  "深渊筑底策略_v2.0": {
    "enabled": true,
    "config": {
      "long_term_days": 400,
      "min_drop_percent": 0.40,
      "price_low_percentile": 0.35
    }
  }
}
```

### 配置管理API
```python
from backend.config_manager import config_manager

# 获取策略配置
strategies = config_manager.get_strategies()

# 启用/禁用策略
config_manager.enable_strategy('策略ID')
config_manager.disable_strategy('策略ID')

# 更新配置
config_manager.update_strategy('策略ID', new_config)
```

## 📈 输出结果说明

### 筛选结果文件
```
data/result/
├── ABYSS_BOTTOMING_OPTIMIZED/     # 深渊筑底策略结果
│   ├── abyss_signals_*.json       # 详细信号
│   ├── abyss_summary_*.json       # 汇总报告
│   └── abyss_report_*.txt         # 可读报告
├── TRIPLE_CROSS/                  # 三重金叉策略结果
└── MACD_ZERO_AXIS/               # MACD零轴策略结果
```

### 持仓分析报告
```
data/portfolio.json                # 持仓数据
reports/portfolio_analysis_*.json  # 持仓分析报告
```

### 多周期分析报告
```
reports/multi_timeframe/
├── daily_report_*.json           # 每日分析报告
├── strategy_performance_*.json   # 策略绩效报告
└── monitoring_summary_*.json     # 监控摘要报告
```

## 🗺️ 项目发展历程与规划

### ✅ V1.0 - 核心功能完成 (已完成)

#### 系统架构 ✅
- [x] **前后端分离架构**: 完全解耦的模块化设计
- [x] **统一配置系统**: 前后端共享配置文件
- [x] **策略管理框架**: 支持策略热插拔和动态加载
- [x] **REST API体系**: 完整的API接口支持

#### 策略筛选系统 ✅
- [x] **5个核心策略**: 深渊筑底、三重金叉、MACD零轴、周线金叉、临界金叉
- [x] **智能筛选引擎**: 胜率过滤、质量评分、信号分级
- [x] **多进程优化**: 并行处理提升性能
- [x] **结果导出**: 多格式报告生成

#### 持仓管理系统 ✅
- [x] **完整持仓管理**: 增删改查、数据持久化
- [x] **深度技术分析**: 多指标综合分析
- [x] **智能操作建议**: 买卖持有、加减仓、止损建议
- [x] **风险评估**: 三级风险等级、波动率分析
- [x] **时间周期分析**: 基于历史周期的预测

#### 多周期分析系统 ✅
- [x] **6个时间周期**: 5分钟到日线的协同分析
- [x] **综合信号生成**: 多周期加权合成
- [x] **三种运行模式**: 分析、回测、监控
- [x] **智能预警**: 关键信号变化提醒

### 🎯 V1.1 - 性能优化与用户体验 (进行中)
- [ ] **数据缓存机制**: Redis缓存提升加载速度
- [ ] **前端优化**: 图表懒加载、虚拟滚动
- [ ] **响应式设计**: 移动端适配
- [ ] **用户界面改进**: 交互体验优化
- [ ] **实时通信**: WebSocket支持

### 🔧 V1.2 - 功能扩展 (规划中)
- [ ] **新增技术指标**: 布林带、威廉指标、成交量指标
- [ ] **策略组合**: 多策略组合筛选
- [ ] **自定义策略**: 可视化策略编辑器
- [ ] **实时预警**: 邮件/微信推送
- [ ] **数据导出**: Excel/CSV导出

### 📊 V1.3 - 高级分析 (规划中)
- [ ] **回测系统增强**: 多周期回测、风险指标
- [ ] **机器学习集成**: 预测模型、异常检测
- [ ] **量化分析**: 因子分析、相关性分析
- [ ] **组合优化**: 投资组合构建

### 🌐 V2.0 - 企业级功能 (远期规划)
- [ ] **多数据源**: 实时行情、基本面数据
- [ ] **用户管理**: 多用户、权限管理
- [ ] **API开放平台**: SDK、第三方集成
- [ ] **云部署**: Docker、Kubernetes

### 📈 当前系统状态

| 模块 | 完成度 | 状态 | 说明 |
|------|--------|------|------|
| 策略筛选 | 100% | ✅ 生产就绪 | 5个策略，智能筛选 |
| 持仓管理 | 100% | ✅ 生产就绪 | 完整功能，深度分析 |
| 多周期分析 | 100% | ✅ 生产就绪 | 6周期协同，三种模式 |
| 配置管理 | 100% | ✅ 生产就绪 | 统一配置，热更新 |
| Web界面 | 95% | ✅ 基本完成 | 功能完整，待优化 |
| API接口 | 100% | ✅ 生产就绪 | REST API完整 |
| 文档系统 | 100% | ✅ 完整齐全 | 技术文档完善 |

---

## 📋 完整功能清单

### 🔍 策略筛选功能
| 功能 | 状态 | 描述 |
|------|------|------|
| 深渊筑底策略 | ✅ | 识别深跌后筑底形态，四阶段渐进式信号 |
| 三重金叉策略 | ✅ | MACD、KDJ、RSI三重金叉确认 |
| MACD零轴策略 | ✅ | MACD零轴上方金叉信号 |
| 周线金叉策略 | ✅ | 周线金叉+日线MA确认 |
| 临界金叉策略 | ✅ | 金叉前临界状态识别 |
| 统一筛选框架 | ✅ | 支持多策略并行筛选 |
| 智能过滤器 | ✅ | 胜率过滤、质量评分 |
| 多进程优化 | ✅ | 并行处理提升性能 |

### 💼 持仓管理功能
| 功能 | 状态 | 描述 |
|------|------|------|
| 持仓CRUD | ✅ | 添加、编辑、删除持仓记录 |
| 深度技术分析 | ✅ | MA、MACD、KDJ、RSI、布林带分析 |
| 操作建议 | ✅ | 买入、卖出、持有、加仓、减仓、止损 |
| 风险评估 | ✅ | 高/中/低风险等级，波动率分析 |
| 价格目标 | ✅ | 支撑阻力位、目标价计算 |
| 时间分析 | ✅ | 持仓周期、预期到顶时间 |
| 智能提醒 | ✅ | 补仓价、减仓价、止损价提醒 |
| 批量扫描 | ✅ | 一键扫描所有持仓 |

### 📊 多周期分析功能
| 功能 | 状态 | 描述 |
|------|------|------|
| 6周期数据同步 | ✅ | 5分钟到日线数据协同 |
| 综合信号生成 | ✅ | 多周期加权合成信号 |
| 分析模式 | ✅ | 全面技术分析和投资建议 |
| 回测模式 | ✅ | 历史数据验证策略有效性 |
| 监控模式 | ✅ | 实时监控信号变化 |
| 智能预警 | ✅ | 关键信号变化提醒 |
| 绩效分析 | ✅ | 夏普比率、最大回撤计算 |
| 报告生成 | ✅ | 多格式分析报告 |

### 🔧 系统管理功能
| 功能 | 状态 | 描述 |
|------|------|------|
| 统一配置管理 | ✅ | 前后端共享配置文件 |
| 策略热插拔 | ✅ | 动态加载策略，无需重启 |
| 配置热更新 | ✅ | 运行时配置修改 |
| API接口 | ✅ | 完整的REST API体系 |
| 兼容性映射 | ✅ | 新旧策略ID自动映射 |
| 错误处理 | ✅ | 完善的异常处理机制 |
| 日志系统 | ✅ | 详细的运行日志 |
| 性能监控 | ✅ | 系统性能统计 |

### 🌐 Web界面功能
| 功能 | 状态 | 描述 |
|------|------|------|
| 策略配置界面 | ✅ | 可视化策略管理 |
| 持仓管理界面 | ✅ | 完整的持仓管理UI |
| 图表展示 | ✅ | ECharts交互式图表 |
| 响应式设计 | 🔄 | 基本完成，待优化 |
| 实时更新 | 🔄 | 部分支持，待完善 |
| 移动端适配 | ⏳ | 规划中 |

## 🤝 贡献指南

### 开发环境设置
```bash
# 1. 克隆项目
git clone <repository-url>
cd stock-analysis-platform

# 2. 安装依赖
pip install -r requirement.txt

# 3. 验证系统
python test_unified_config.py

# 4. 启动开发服务器
cd backend && python app.py
```

### 添加新策略
```python
# 1. 创建策略文件 backend/strategies/my_strategy.py
from .base_strategy import BaseStrategy

class MyStrategy(BaseStrategy):
    def get_strategy_name(self):
        return "我的策略"
    
    def apply_strategy(self, df):
        # 实现策略逻辑
        pass

# 2. 更新配置文件 config/unified_strategy_config.json
{
  "我的策略_v1.0": {
    "enabled": true,
    "config": {...}
  }
}
```

### 提交规范
- `feat`: 新功能
- `fix`: 修复bug  
- `docs`: 文档更新
- `style`: 代码格式
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建工具

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

