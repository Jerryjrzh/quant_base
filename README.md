# 📈 股票筛选与分析平台

一个前后端分离、模块化的股票技术分析平台，支持多种技术指标和筛选策略。

## 🚀 功能特性

- **模块化架构**: 策略与数据解耦，逻辑与显示分离
- **多策略支持**: 内置 TRIPLE_CROSS、PRE_CROSS、MACD_ZERO_AXIS 等策略
- **🆕 可配置参数系统**: 所有技术指标参数都可动态调整，无需修改代码
- **🆕 参数优化工具**: 自动寻找最佳参数组合，提升策略效果
- **智能筛选**: 集成胜率过滤器，自动排除低效信号
- **交叉阶段分析**: 识别PRE_CROSS、CROSS_MOMENT、POST_CROSS等最佳入场时机
- **质量评分系统**: 基于多项技术指标的信号质量评分
- **多时间框架分析**: 支持不同时间周期的策略对比
- **技术指标库**: 支持 MACD、KDJ、RSI 等常用技术指标
- **实时分析**: 基于 Flask API 的实时数据处理
- **可视化界面**: 使用 ECharts 进行交互式图表展示
- **批量筛选**: 支持批量股票筛选和信号生成

## 📦 项目结构

```
├── backend/                 # 后端代码
│   ├── app.py              # Flask API 服务器
│   ├── screener.py         # 批量筛选引擎
│   ├── data_loader.py      # 数据加载器
│   ├── indicators.py       # 技术指标库
│   ├── strategies.py       # 策略库
│   ├── backtester.py       # 回测引擎
│   └── data/               # 数据目录
├── frontend/               # 前端代码
│   ├── index.html          # 主页面
│   └── js/app.js           # 前端逻辑
├── data/result/            # 筛选结果
│   ├── MACD_ZERO_AXIS/     # MACD零轴策略结果
│   ├── PRE_CROSS/          # 预交叉策略结果
│   └── TRIPLE_CROSS/       # 三线交叉策略结果
└── README.md               # 项目说明
```

## 📦 项目交付包：模块化股票筛选与分析平台 V1.0

### 一、 设计文档 (Design Document)

#### 1\. 项目目标

构建一个前后端分离、模块化的股票分析平台。后端负责数据处理和策略执行，前端负责交互式的数据可视化。该平台旨在：

  * **策略与数据解耦**：策略的修改不影响数据读取。
  * **逻辑与显示解耦**：筛选逻辑的修改不影响前端展示。
  * **高可扩展性**：可以方便地增加新的数据源、新的筛选策略和新的分析维度。

#### 2\. 架构概览

本平台采用经典的三层模块化架构：

  * **数据层 (Data Layer)**：负责从本地 `.day` 和 `_5min` 文件中读取原始数据。
  * **后端 (Python Backend)**：负责执行策略筛选、实时计算指标和信号，并通过API提供数据服务。
  * **前端 (JavaScript Frontend)**：负责调用后端API，使用ECharts库将数据渲染为可交互的图表和表格，供用户复盘分析。

**数据流示意图**:

```
1. 批量筛选 (离线):
[本地.day文件] -> [Python筛选引擎 screener.py] -> [signals_summary.json (当日信号汇总)]

2. 交互式复盘 (在线):
                         <-(2. API请求)- [Python API服务器 app.py] <-(3. 读取数据)- [本地.day/.lc5文件]
                        /                                          /
[浏览器 index.html] --(1. 读取信号汇总)--> [signals_summary.json]
                        \
                         ->(4. 接收数据并渲染)- [ECharts 图表]
```

#### 3\. 模块说明

  * **`backend/`**: 后端所有代码。
      * `data_loader.py`: **数据加载器**。统一负责解析 `.day` 和5分钟 `.lc5` 文件。
      * `indicators.py`: **指标库**。包含所有技术指标（MACD, KDJ, RSI）的计算函数。
      * `strategies.py`: **策略库**。包含所有筛选策略（`TRIPLE_CROSS`, `PRE_CROSS`）的逻辑函数。
      * `screener.py`: **批量筛选引擎**。每日运行一次，遍历所有股票，执行策略，生成当日信号汇总 `signals_summary.json`。
      * `app.py`: **实时API服务器**。基于Flask框架，接收前端请求，实时加载个股数据、计算指标、标记信号，并返回给前端。
      * `requirements.txt`: 后端所需的所有Python依赖库。
  * **`frontend/`**: 前端所有代码。
      * `index.html`: **主页面**。承载图表和交互控件。
      * `js/app.js`: **前端核心逻辑**。负责API调用、ECharts图表渲染和用户交互。
  * **`README.md`**: 主说明文档（即本文）。

-----

### 二、 参考实现 (Reference Implementation)

以下是项目各核心文件的参考实现代码。

#### **`backend/requirements.txt`**

```
pandas
numpy
flask
flask-cors
pyecharts
```

-----

### 三、 使用说明 (User Instructions)

#### 基础环境设置

1.  **环境准备**:
      * 确保已安装 Python 3.8+。
      * 在 `backend` 目录下创建并激活虚拟环境（推荐）。
      * 执行 `pip install -r requirements.txt` 安装所有后端依赖。

2.  **数据准备**:
      * 将您的 `vipdoc` 数据文件夹（包含 `sh`, `sz`, `bj` 等子目录）放在 `backend/data/` 目录下，或创建一个符号链接。

#### 🚀 增强版筛选系统使用

**快速开始 - 一键运行增强版分析**:
```bash
# 运行完整的增强版分析
python run_enhanced_screening.py

# 查看帮助信息
python run_enhanced_screening.py help
```

**分步骤运行**:

1. **增强版TRIPLE_CROSS筛选**:
   ```bash
   # 运行带有胜率过滤和质量评分的筛选
   cd backend
   python screener.py
   ```
   
2. **深度分析**:
   ```bash
   # 运行交叉阶段分析和多策略对比
   python enhanced_analyzer.py
   ```
   
3. **多时间框架分析**:
   ```bash
   # 对最近筛选的股票进行全面分析
   python multi_timeframe.py
   ```

#### 📊 核心改进功能

**1. 胜率筛选系统**
- 自动排除历史胜率低于40%的股票
- 基于最少3个历史信号的统计分析
- 要求平均收益率不低于8%

**2. 交叉阶段识别**
- **PRE_CROSS**: 交叉前阶段，指标接近但未交叉
- **CROSS_MOMENT**: 交叉时刻，正在发生金叉
- **POST_CROSS**: 交叉后确认阶段
- **BOTTOM_FORMATION**: 多指标同时触底

**3. 质量评分系统**
- 基于MACD强度、KDJ位置、RSI背离等多项指标
- 0-100分评分制，70分以上为高质量信号
- 自动过滤高位追涨和假突破信号

#### 📈 结果文件说明

**主要输出文件**:
```
data/result/
├── TRIPLE_CROSS/
│   ├── signals_summary.json      # 筛选出的股票信号
│   ├── scan_summary_report.json  # 筛选统计报告
│   └── scan_report_*.txt         # 文本格式报告
├── ENHANCED_ANALYSIS/
│   └── enhanced_analysis_*.json  # 深度分析报告
└── MULTI_TIMEFRAME_ANALYSIS/
    └── multi_timeframe_analysis_*.json  # 多策略对比报告
```

**关键字段解释**:
- `quality_score`: 信号质量评分 (0-100)
- `cross_stage`: 交叉阶段标识
- `win_rate`: 历史胜率百分比
- `avg_max_profit`: 平均最大收益率
- `filter_status`: 筛选状态 (passed/filtered)

#### 🎯 策略优化效果

**TRIPLE_CROSS策略改进对比**:
- **原始版本**: 平均胜率 29.5%，信号质量参差不齐
- **增强版本**: 预期胜率 >45%，信号质量显著提升
- **过滤效果**: 自动排除约60-70%的低质量信号

#### 🔧 配置系统使用

**新增的可配置参数系统让你可以轻松调整策略参数，无需修改代码：**

```bash
# 查看策略配置
python config_tool.py show TRIPLE_CROSS

# 测试当前配置效果
python config_tool.py test TRIPLE_CROSS

# 优化MACD参数
python config_tool.py optimize TRIPLE_CROSS --indicator macd

# 更新配置
python config_tool.py update TRIPLE_CROSS --config '{"macd": {"fast_period": 10}}'
```

**配置文件位置**: `backend/strategy_configs.json`

**主要可配置参数**:
- **MACD**: 快线周期(12)、慢线周期(26)、信号线周期(9)
- **KDJ**: 计算周期(27)、K值平滑(3)、D值平滑(3)
- **RSI**: 短周期(6)、长周期(12)
- **过滤器**: 最低胜率(40%)、质量评分阈值(70分)

详细使用方法请参考 [CONFIG_USAGE.md](CONFIG_USAGE.md)

#### 传统使用方式

如需使用传统方式：

1.  **执行批量筛选**: 运行 `python screener.py`
2.  **启动API服务**: 运行 `python app.py`
3.  **打开前端页面**: 浏览器打开 `frontend/index.html`
4.  **开始复盘**: 选择股票进行图表分析

## 🗺️ 开发路线图 (Roadmap)

### 🎯 V1.1 - 性能优化与用户体验提升 (Q1 2025)
- [ ] **数据缓存机制**: 实现Redis缓存，提升数据加载速度
- [ ] **异步处理**: 优化批量筛选的并发处理能力
- [ ] **前端优化**: 实现图表懒加载和虚拟滚动
- [ ] **响应式设计**: 支持移动端和平板设备访问
- [ ] **用户界面改进**: 优化交互体验和视觉设计

### 🔧 V1.2 - 功能扩展 (Q2 2025)
- [ ] **新增技术指标**: 
  - 布林带 (Bollinger Bands)
  - 威廉指标 (%R)
  - 成交量指标 (OBV, VWAP)
- [ ] **策略组合**: 支持多策略组合筛选
- [ ] **自定义策略**: 可视化策略编辑器
- [ ] **实时预警**: 邮件/微信推送功能
- [ ] **数据导出**: 支持Excel/CSV格式导出

### 📊 V1.3 - 高级分析功能 (Q3 2025)
- [ ] **回测系统增强**: 
  - 多周期回测
  - 风险指标计算 (夏普比率、最大回撤)
  - 策略对比分析
- [ ] **机器学习集成**: 
  - 股价预测模型
  - 异常检测算法
- [ ] **量化分析**: 
  - 因子分析
  - 相关性分析
- [ ] **组合管理**: 投资组合构建和优化

### 🌐 V2.0 - 企业级功能 (Q4 2025)
- [ ] **多数据源支持**: 
  - 实时行情接入
  - 基本面数据集成
  - 新闻情感分析
- [ ] **用户管理系统**: 
  - 多用户支持
  - 权限管理
  - 个人设置保存
- [ ] **API开放平台**: 
  - RESTful API文档
  - SDK开发包
  - 第三方集成支持
- [ ] **云部署支持**: 
  - Docker容器化
  - Kubernetes部署
  - 微服务架构

### 🔮 未来展望 (2026+)
- [ ] **AI驱动分析**: GPT集成的智能分析助手
- [ ] **区块链集成**: 去中心化数据验证
- [ ] **跨市场支持**: 港股、美股、期货市场
- [ ] **社区功能**: 策略分享和讨论平台

---

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request 来帮助改进项目！

### 开发环境设置
```bash
# 克隆项目
git clone <repository-url>
cd stock-analysis-platform

# 后端环境
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 启动开发服务器
python app.py
```

### 提交规范
- feat: 新功能
- fix: 修复bug
- docs: 文档更新
- style: 代码格式调整
- refactor: 代码重构
- test: 测试相关
- chore: 构建过程或辅助工具的变动

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

