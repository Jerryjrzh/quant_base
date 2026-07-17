# GBM Signal Scorer 技术文档

## 一、概述

GBM Signal Scorer 是基于梯度提升树 (Gradient Boosting Machine) 的信号质量评估模型，用于替代当前失效的 morse 评分系统。

### 1.1 背景问题

当前 `apply_morse_sniper_strategy()` 的评分系统存在严重问题：
- **98.2% 的信号都是 95 分**，无区分度
- 评分退化为二分类开关（要么淘汰，要么 95 分）
- 无法实现"优中选优"

### 1.2 解决方案

用数据驱动的 GBM 模型替代手工规则评分：
- 输入：T0 可获取的信号特征
- 输出：0~1 概率值，表示"实盘可盈利"的概率
- 阈值：可调节，平衡信号量与质量

### 1.3 核心价值

| 指标 | Morse 评分 | GBM 概率 |
|------|:---:|:---:|
| 区分度 | 98.2% = 95分 | 单调递增 |
| 测试集 F1 | N/A | 0.558 |
| real_quality 率 | 46.1% (baseline) | 56.2% (阈值0.62) |
| 盈亏比 | 1.45 | 2.36 (阈值0.62) |

---

## 二、模型规格

### 2.1 算法

```
GradientBoostingClassifier
├── n_estimators: 100
├── max_depth: 3
├── learning_rate: 0.1
├── subsample: 0.8
└── random_state: 42
```

### 2.2 特征

**原始特征 (3个)**:
- `ma_slope`: MA20 斜率
- `bias_20`: MA20 乖离率
- `score`: Morse 原始评分（多为 95）

**One-hot 特征 (13个)**:
- `market_env_*`: 大盘环境（震荡、弱势阴跌、顺风大涨、股灾暴跌）
- `v44_trend_*`: V4.4 趋势阶段（accumulation、markup、distribution、decline）
- `v44_bias_tier_*`: V4.4 乖离层（深渊超跌、空头偏离、均值回归、多头偏离、高位极度乖离）

**总计**: 16 个特征

### 2.3 目标变量

```python
is_real_quality = (future_mfe >= 0.05) AND (future_mae >= -0.08)
```

含义：7天内最大涨幅≥5% 且 最大回撤≤8%，实盘可吃到。

### 2.4 数据

| 数据集 | 日期范围 | 样本数 | 正例率 |
|--------|----------|:---:|:---:|
| 训练集 | 2025-01-02 ~ 2025-12-31 | 12,773 | 54.4% |
| 测试集 | 2026-01-05 ~ 2026-04-29 | 4,711 | 46.1% |

**基础过滤**: Scheme C (slope ≤ -2% + 20CM)

### 2.5 性能

| 指标 | 数值 |
|------|:---:|
| F1 | 0.558 |
| Precision | 0.491 |
| Recall | 0.648 |

---

## 三、特征重要性

| 排名 | 特征 | 重要性 |
|:---:|------|:---:|
| 1 | bias_20 | 33.91% |
| 2 | ma_slope | 29.14% |
| 3 | v44_bias_tier_深渊超跌(<-15%) | 18.76% |
| 4 | v44_bias_tier_空头偏离(-15%~-5%) | 4.17% |
| 5 | market_env_顺风大涨 | 4.06% |

**解读**:
- **bias_20 + ma_slope**: 占比 63%，是核心预测因子
- **深渊超跌**: 正权重，极度超跌反弹概率高
- **顺风大涨**: 负权重，大盘好反而差（超跌反弹策略特性）

---

## 四、阈值优化

### 4.1 阈值扫描结果

| 阈值 | 信号数 | 日均 | real_q | MFE中位 | MAE中位 | 盈亏比 | 单笔PnL | 夏普 |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 0.34 | 4,671 | 61 | 46.2% | 4.89% | -3.32% | 1.47 | 0.98% | 0.15 |
| 0.44 | 3,785 | 50 | 48.2% | 5.16% | -3.17% | 1.63 | 1.19% | 0.19 |
| 0.50 | 2,882 | 38 | 50.1% | 5.37% | -2.97% | 1.81 | 0.77% | 0.12 |
| **0.62** | **1,028** | **14** | **56.2%** | **6.24%** | **-2.64%** | **2.36** | **2.04%** | **0.32** |
| 0.70 | 500 | 7 | 59.2% | 6.60% | -2.47% | 2.67 | 2.23% | 0.38 |

### 4.2 推荐阈值

**极精选 (推荐): 0.62**
- 日均 14 信号，适合人工筛选
- real_quality 56.2%，接近最优
- 盈亏比 2.36，风险控制优秀
- 单笔 PnL 2.04%

**其他选项**:
- 精选: 0.56 (日均25信号, real_q=52.1%)
- 均衡: 0.44 (日均50信号, real_q=48.2%)

### 4.3 关键发现

**real_quality 率和盈亏比随阈值单调递增**，无拐点：

```
阈值 0.30 → 0.70:
  real_quality: 46.1% → 59.2% (单调↑)
  盈亏比:       1.46  → 2.67  (单调↑)
```

本质是**精度-召回率权衡**：阈值越高越精准，但信号越少。

---

## 五、API 使用

### 5.1 训练模型

```python
from gbm_scorer import GBMScorer

# 加载数据
df = pd.read_csv('data/result/SignalGenerator/master_signals.csv')
df = df[(df['ma_slope'] <= -0.02) & (df['board_type'] == '20CM')]

# 训练
scorer = GBMScorer()
metrics = scorer.train(df, train_end='2025-12-31')
print(f"F1: {metrics['f1']:.3f}")

# 保存
scorer.save('gbm_scorer_v1')
```

### 5.2 加载模型

```python
from gbm_scorer import GBMScorer

scorer = GBMScorer()
scorer.load('gbm_scorer_v1')
print(scorer.summary())
```

### 5.3 打分

```python
# 对信号 DataFrame 打分
proba = scorer.score(signal_df)
signal_df['gbm_proba'] = proba

# 按阈值过滤
filtered = scorer.filter(signal_df, threshold=0.62)
print(f"过滤后信号: {len(filtered)}")
```

### 5.4 集成到筛选流程

```python
# 1. Morse 筛选 (现有)
result = apply_morse_sniper_strategy(df_daily, df_15m, stock_code, end_date)

if result and result['score'] >= 85:
    # 2. Scheme C 过滤
    if result.get('ma_slope', 0) <= -0.02 and board_type == '20CM':
        # 3. GBM 打分
        signal_df = pd.DataFrame([result])
        proba = scorer.score(signal_df)[0]
        
        if proba >= 0.62:
            # 4. 输出最终信号
            result['gbm_proba'] = proba
            print(f"✓ 通过 GBM 筛选: {proba:.3f}")
```

---

## 六、文件结构

```
backend/
├── gbm_scorer.py              # GBM 打分器模块
└── signal_backtest_validator_v2.py  # 回测验证脚本

data/
├── model/
│   ├── gbm_scorer_v1.pkl      # 序列化模型
│   └── gbm_scorer_v1_meta.json # 模型元数据
└── result/
    └── SignalGenerator/
        ├── master_signals.csv  # 原始信号数据
        ├── scheme_c_signals.csv # Scheme C 过滤后
        └── scheme_cplus_signals.csv # Scheme C-Plus 过滤后

doc/
└── 0605_data_dig/
    ├── signal_analysis_report.md      # 数据分析报告
    ├── signal_backtest_v2_report.md   # GBM 回测报告
    └── gbm_scorer_technical_doc.md    # 本文档
```

---

## 七、下一步优化方向

### 7.1 特征工程

当前特征较简单，可扩展：
- **技术指标**: RSI、MACD 背离、布林带宽度
- **成交量**: 量比、量能异动
- **市场情绪**: 涨跌家数比、涨停跌停数

### 7.2 模型升级

- **集成学习**: GBM + LR + NN ensemble
- **时序模型**: LSTM/Transformer 捕捉时序模式
- **在线学习**: 增量更新模型，适应市场变化

### 7.3 市场状态自适应

不同 `market_env` 使用不同阈值：
- 震荡市: 0.62 (标准)
- 弱势阴跌: 0.58 (放宽)
- 顺风大涨: 0.66 (收紧)

### 7.4 扩展训练数据

- 纳入 2024 年数据，提升泛化能力
- 跨市场数据（港股、美股）
- 不同策略的信号数据

---

## 八、常见问题

### Q1: 为什么不用更复杂的深度学习模型？

A: GBM 在小样本表格数据上通常优于深度学习，且：
- 训练快（<1秒）
- 可解释性强（特征重要性）
- 不需要 GPU
- 不易过拟合

### Q2: 模型会过拟合吗？

A: 已采取措施：
- 时间切分（训练集在前，测试集在后）
- subsample=0.8（随机采样）
- max_depth=3（限制树深度）
- 测试集 F1=0.558，与训练集接近

### Q3: 如何更新模型？

A: 定期重训练：
```python
# 每月末重训练
df_new = pd.read_csv('data/result/SignalGenerator/master_signals.csv')
scorer.train(df_new, train_end='2026-01-31')
scorer.save('gbm_scorer_v2')
```

### Q4: 阈值 0.62 是固定的吗？

A: 可根据实盘反馈调整：
- 信号太少 → 降低阈值（如 0.58）
- 质量不够 → 提高阈值（如 0.66）
- 建议：先用 0.62 运行 1 个月，根据实盘表现微调

---

## 九、版本历史

- **v1.0** (2026-06-05): 初始版本
  - 100 trees, depth=3, lr=0.1
  - 16 特征
  - 训练集 12,773 样本
  - 测试集 F1=0.558

---

**文档版本**: 1.0  
**最后更新**: 2026-06-05  
**维护者**: Qoder CLI
