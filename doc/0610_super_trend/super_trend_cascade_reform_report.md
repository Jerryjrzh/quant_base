# Super Trend 三分类标签 + 级联模型改造报告

> 时间：2026-06-12  
> 来源：GPT Review / Gemini Confirm / Gemini Adv 三方共识  
> 核心问题：Label Gap（中间层丢弃）+ T0 偏晚 + 特征同质化

---

## 一、三方 Review 共识总结

| 诊断 | 三方一致性 | 核心论据 |
|------|-----------|---------|
| Label Gap 是 Precision 瓶颈的元凶 | **全部同意** | 10%-80% MFE 样本被丢弃，模型在"普通强势 vs 超级主升"边界完全盲猜 |
| T0 定位偏晚 | **全部同意** | Top 特征（bias_ma60, price_rebound_from_pit）表达"已启动"而非"即将启动" |
| 收紧阈值不能解决根本问题 | **全部同意** | AUC 涨但 Precision 不涨，正/负概率分离度无变化 |
| 补齐同质化指标收益有限 | **全部同意** | boll_width/atr 在 A 股历史中通常只有 0.1-0.3σ，无法突破 0.48σ 天花板 |
| 需要结构性 Alpha 特征 | **全部同意** | 相对强弱/板块联动/筹码结构可贡献 1σ+ 分离度 |

### 分歧点

| 议题 | GPT 建议 | Gemini 建议 | 本次采纳 |
|------|---------|------------|---------|
| 标签体系 | 三分类 0/1/2 | 三分类 + 困难负样本 | **三分类**（简洁，级联模型自然实现） |
| 模型架构 | 多分类 LightGBM | 级联双模型 | **级联双模型**（独立优化，可解释性强） |
| MIN_GAIN | 恢复 EDA P95 | 恢复 EDA P95 | **恢复 EDA P95**（Grok 版 1.0 太激进） |
| T0 门槛 | 3% + 1.5x | 2% + 1.2x | **3% + 1.5x**（EDA 校准值，保守优先） |

---

## 二、架构设计

### 2.1 三分类标签体系

```
异动触发 (daily_gain≥3% OR vol_ratio≥1.5)
         │
         ▼
┌─────────────────────┐
│  Label 0: 死水/陷阱   │  22d MFE < 10%
│  (教会模型什么是坑)    │  ~50% 样本
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Label 1: 普通强势    │  10% ≤ 22d MFE < P95
│  (困难负样本，填补盲区) │  ~44% 样本
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Label 2: 超级主升    │  22d MFE ≥ P95 + MAE ≥ -25%
│  (真正的起爆信号)      │  ~6% 样本
└─────────────────────┘
```

### 2.2 级联模型架构

```
输入特征 X
    │
    ├──→ Model A (Gate) ──→ P(有价值 | X)
    │    label > 0 vs 0
    │    全量样本训练
    │
    └──→ Model B (Precision) ──→ P(超级主升 | 有价值, X)
         label == 2 vs 1
         仅在 label 1+2 样本上训练
    
    最终预测 = P(A) × P(B)
```

**优势**：
- Model A 在全量数据上训练，区分力强（~50% vs ~50%）
- Model B 专注"普通强势 vs 超级主升"的精细边界
- 两模型独立优化，互不干扰
- 级联概率天然过滤低置信度预测

---

## 三、文件变更清单

### 3.1 `super_trend_scanner_v1_grok.py`

| 区域 | 变更 | 说明 |
|------|------|------|
| 配置参数 | `MIN_GAIN` → `LABEL1_THRESHOLD=0.10, LABEL2_GLOBAL=0.51` | 三分类阈值替代单一阈值 |
| 配置参数 | `BOARD_MIN_GAIN` 恢复 EDA P95 值 | 43%/47%/54%/53%/106% |
| 配置参数 | `ANOMALY_MIN_DAILY_GAIN=0.03` 替代 `NEG_MIN_DAILY_GAIN` | 语义更清晰 |
| 打标逻辑 | 二分类 → **三分类** (label 0/1/2) | 填补 Label Gap |
| T0 回溯 | 5%+2.0 → **3%+1.5** | 恢复原始宽松门槛，避免 T0 偏晚 |
| 候选字典 | `is_positive/sample_type/neg_subtype` → `label` | 三分类标签 |
| 增强特征 | 修正 `boll_upper` → `bb_upper` | 匹配 `calculate_all_indicators` 实际列名 |
| 增强特征 | 修正 `ma10/ma20` → `ma13/ma30` | 使用实际计算的均线列 |
| 增强特征 | 新增 `stock_return_20d` | 相对强弱（结构性 Alpha） |
| 增强特征 | 新增 `vol_turnover_ratio` | 筹码活跃度代理 |
| 合并输出 | 三分类分布打印 | Label 0/1/2 各自计数和占比 |

### 3.2 `super_trend_data_snapshot.py`

| 区域 | 变更 | 说明 |
|------|------|------|
| `__init__` | 新增 `label` 参数 | 三分类标签存储 |
| `get_feature_vector` | 新增 `label` 字段 | 导出训练数据时携带标签 |
| `get_training_data` | `y` 从 binary → **三分类 label** | 级联模型的训练目标 |
| `get_summary` | 三分类分布统计 | label_0/1/2 各自计数和占比 |

### 3.3 `super_trend_ml_trainer.py`

| 区域 | 变更 | 说明 |
|------|------|------|
| 模块头 | 更新为"级联模型训练模块" | 架构定位变更 |
| `__init__` | 新增 `model_a/model_b` 属性 | 双模型存储 |
| `drop_cols` | 新增 `'label'` | 标签列不作为特征 |
| `load_training_data` | 优先使用 `label` 列 | 三分类标签加载 |
| `_train_single_model` | **新增** | 抽取单模型训练逻辑，复用 |
| `train_model` | **重写为级联** | Model A (Gate) + Model B (Precision) |
| `evaluate_model` | **重写为级联评估** | combined_prob = prob_A × prob_B |
| `cross_validation` | **重写为级联 CV** | 每折训练双模型，评估级联 AUC |
| `save_model` | 保存 model_a + model_b | 级联模型序列化 |
| `load_model` | 加载双模型 + 向后兼容 | 可加载旧版单模型 |
| 阈值列表 | [0.50, 0.65, 0.70] → [0.10, 0.20, 0.30, 0.40, 0.50, 0.65] | 级联概率更小，需更宽阈值范围 |

### 3.4 `data_handler.py`

| 区域 | 变更 | 说明 |
|------|------|------|
| `calculate_all_indicators` | **新增 ATR 计算** | `df['atr'] = indicators.calculate_atr(df)` |

---

## 四、特征体系变更

### 4.1 预期特征维度：13 → 23

| 来源 | 特征数 | 列表 |
|------|--------|------|
| 原有基础特征 | 13 | t0_close, t0_volume, t0_rsi, t0_macd, rsi_explosion_force, macd_pit_depth, price_rebound_from_pit, days_underwater, days_below_ma30, vol_dryup_count, is_fake_breakdown, is_water_ignition, is_extreme_volume_dry |
| 增强特征（修正列名后） | 8 | ma_bull_alignment_days, bias_ma20, bias_ma60, atr_percentile, boll_width, pre_breakout_vol_shrink_days, vol_breakout_ratio, price_position_120d |
| 结构性 Alpha（新增） | 2 | stock_return_20d, vol_turnover_ratio |

### 4.2 Bug 修复

| 问题 | 修复 |
|------|------|
| `boll_width` 使用 `boll_upper/boll_mid/boll_lower` | 修正为 `bb_upper/bb_middle/bb_lower` |
| `ma_bull_alignment_days` 使用 `ma10/ma20`（不存在） | 修正为 `ma13/ma30` |
| `bias_ma20` 使用 `ma20`（不存在） | 修正为 `ma21`（fallback `ma20`） |
| `atr_percentile` 因 `atr` 未计算而缺失 | 在 `data_handler.py` 中新增 ATR 计算 |

---

## 五、预期效果

| 指标 | 原版 (EDA) | Grok 版 | 本次改造预期 |
|------|-----------|---------|------------|
| 标签体系 | 二分类 (丢弃中间层) | 二分类 (极端阈值) | **三分类 (完整覆盖)** |
| 正样本定义 | MFE ≥ P95 (43-54%) | MFE ≥ 80-200% | MFE ≥ P95 (43-54%) |
| 困难负样本 | 无 | 无 | **Label 1 (10%-P95%)** |
| 特征维度 | 13 | 17 | **23** |
| 模型架构 | 单模型 | 单模型 | **级联双模型** |
| T0 门槛 | 3%+1.5x | 5%+2.0x | **3%+1.5x (恢复)** |
| Precision 预期 | 32.5% | 33.7% | **目标 ≥ 50%** |

---

## 六、执行步骤

### Step 1: 全量扫描
```bash
cd backend && python3 super_trend_scanner_v1_grok.py --full
```
预期：Label 0 ~50% / Label 1 ~44% / Label 2 ~6%

### Step 2: 训练级联模型
```bash
cd backend && python3 super_trend_ml_trainer.py
```
观察：
- 级联 CV AUC（应 > 0.70）
- Model A Gate AUC（应 > 0.75，区分力强）
- Model B Precision AUC（关键指标）
- 多阈值 Precision/Recall 表

### Step 3: 特征重要性分析
- 检查新增特征（stock_return_20d, ma_bull_alignment_days, boll_width）的排名
- 如果结构性特征进入 Top 5，说明方向正确

---

*报告生成时间：2026-06-12*
