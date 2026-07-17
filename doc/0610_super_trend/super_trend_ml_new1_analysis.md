# Super Trend — 级联模型训练结果分析 (ml_new1)

> 训练日志: `doc/0610_super_trend/super_trend_ml_new1.txt`
> 数据: 1,331,523 样本, 24 特征, 2020-05 至 2026-03

---

## 一、与 GPT 预期对照

| 指标 | GPT 预期 | 实际值 | 状态 |
|------|---------|--------|------|
| CV AUC | > 0.75 | **0.8240** (±0.067) | PASS |
| Test 级联 AUC | > 0.74 | **0.8306** | PASS |
| Gate AUC | > 0.80 | **0.6046** | **FAIL** |
| Precision AUC | > 0.65 | **0.6571** | PASS (barely) |
| Precision@0.50 | > 40% | **8.33%** | **FAIL** |
| Precision@0.65 | > 45% | **N/A (0 triggers)** | **FAIL** |
| 正负样本概率差 | > 0.12 | **0.0413** | **FAIL** |
| RS20 特征重要性 | Top 5 | **不存在于训练数据** | **CRITICAL BUG** |

---

## 二、数据分布

### Label 分布

| Label | 数量 | 比例 | GPT 预期 |
|-------|------|------|---------|
| 0 (死水) | 678,615 | 51.0% | ~60% |
| 1 (普通主升) | 612,818 | 46.0% | ~35% |
| 2 (超级主升) | 40,090 | 3.0% | ~5% |

- Label 0 vs (1+2) 几乎 50:50，Gate 模型面对的是接近平衡的二分类
- Label 2 仅 3%，低于预期的 5%
- `scale_pos_weight` for Gate = 1.02 (几乎无加权)

---

## 三、核心问题诊断

### 问题 1（致命）: rs_20d 完全缺失

**现象**: 训练数据 24 个特征中不包含 `rs_20d`。

**根因**: `_worker_wrapper()` 多进程 worker 传递 `df_market=None`。
全量扫描（`--full`）使用多进程路径，每只股票的子进程没有加载大盘指数数据，导致 `_extract_enhanced_features()` 中 RS20 计算分支永远不执行。

```python
# 旧代码（bug）
def _worker_wrapper(stock_code):
    candidates, collection = scan_and_build_episodes(
        stock_code, end_date=end_date, df_market=None  # ← RS20 永远跳过
    )
```

**修复**: 每个子进程内独立加载大盘指数（OS 页缓存保证高效）。

```python
# 修复后
def _worker_wrapper(stock_code):
    market_code = 'sh000001' if stock_code.startswith('sh') else 'sz399001'
    df_market = _load_market_index(market_code, end_date=end_date)
    candidates, collection = scan_and_build_episodes(
        stock_code, end_date=end_date, df_market=df_market
    )
```

**影响**: GPT 评价 RS20 为 ⭐⭐⭐⭐⭐ 级特征，预期 Top 5。缺失此特征直接导致模型丢失最强信号源之一。

---

### 问题 2（严重）: Gate 模型 AUC 仅 0.60

**现象**: Model A (Gate) AUC = 0.6046，远低于预期的 0.80+。

**分析**:
- Gate 的任务是区分 Label 0（死水）vs Label 1+2（有价值），训练数据几乎 50:50 平衡
- 这说明当前特征集**无法有效区分"死水异动"和"有价值异动"**
- Gate 本质上接近随机猜测，在级联中充当噪声乘法器，压缩了 Precision 模型的信号

**影响链条**:
```
Gate AUC=0.60 → 级联乘法引入噪声 → 概率严重压缩 → Precision@all thresholds 极低
```

**根因推测**:
1. RS20 缺失（修复后应能改善）
2. ma_bull_alignment_days 排名 #21（importance 26,960），远低于预期
3. 特征集缺乏"价值过滤"维度的信号

---

### 问题 3（中等）: 概率分布严重压缩

**现象**:
```
min=0.0000, max=0.6004, mean=0.0154, median=0.0000
Label 0 平均概率: 0.0000
Label 1 平均概率: 0.0306
Label 2 平均概率: 0.0413
```

- max 仅 0.6004，所以 0.65 阈值触发数为 0
- Label 2 均值 - Label 0 均值 = 0.0413（目标 > 0.12）
- 中位数为 0 说明超过一半样本的级联概率接近零

**根因**: Gate 输出集中在低值区间（AUC=0.60 → 大量样本的 prob_a 很小），乘以 prob_b 后进一步压缩。

---

### 问题 4（关注）: CV Fold 4 异常

```
Fold 4: Precision AUC=0.5655, trees=2  ← 模型几乎没有学习
Fold 4: 级联 AUC=0.6948
```

Precision 模型在 Fold 4 仅 2 棵树就 early stop，说明该折数据中 label 2 vs 1 的信号极弱。可能是时序上某个时间段的市场环境导致。

---

## 四、特征重要性分析

### 全排名（Precision 模型 gain）

| 排名 | 特征 | importance | 类别 |
|------|------|------------|------|
| 1 | bias_ma60 | 551,410 | 乖离率 |
| 2 | vol_breakout_ratio | 371,567 | 量能 |
| 3 | t0_close | 216,238 | 基础 |
| 4 | price_position_120d | 182,142 | 位置 |
| 5 | vol_turnover_ratio | 152,922 | 量能 |
| 6 | volume_percentile_120d | 145,364 | 量能 |
| 7 | bias_ma20 | 144,330 | 乖离率 |
| 8 | t0_macd | 137,764 | 基础 |
| 9 | atr_percentile | 137,040 | 波动率 |
| 10 | t0_volume | 130,118 | 基础 |
| 11 | t0_rsi | 118,013 | 基础 |
| 12 | rsi_explosion_force | 111,352 | 极值 |
| 13 | macd_pit_depth | 98,289 | 极值 |
| 14 | boll_width | 90,916 | 波动率 |
| 15 | stock_return_20d | 88,517 | 动量 |
| 16 | vol_dryup_count | 87,887 | 量能 |
| 17 | is_extreme_volume_dry | 64,661 | 黄金坑 |
| 18 | price_rebound_from_pit | 61,884 | 极值 |
| 19 | pre_breakout_vol_shrink_days | 44,404 | 量能 |
| 20 | days_below_ma30 | 32,126 | 计数 |
| 21 | ma_bull_alignment_days | 26,960 | 结构 |
| 22 | days_underwater | 22,211 | 计数 |
| 23 | is_water_ignition | 18,036 | 黄金坑 |
| 24 | is_fake_breakdown | 1,433 | 黄金坑 |
| — | **rs_20d** | **缺失** | **相对强度** |

### 与 GPT 特征星级对照

| 特征 | GPT 星级 | 实际排名 | 结论 |
|------|---------|---------|------|
| rs_20d | ⭐⭐⭐⭐⭐ | **不存在** | BUG: 未进入训练数据 |
| volume_percentile_120d | ⭐⭐⭐⭐ | **#6** | 符合预期 |
| ma_bull_alignment_days | ⭐⭐⭐⭐ | #21 | 远低于预期（RS20缺失后的连带影响？）|
| atr_percentile | ⭐⭐ | #9 | 高于预期 |
| boll_width | ⭐⭐ | #14 | 符合预期 |

### 关键发现

- **量能类特征主导**: vol_breakout_ratio (#2), vol_turnover_ratio (#5), volume_percentile_120d (#6) 三个量能特征进入 Top 10
- **乖离率最强**: bias_ma60 排名第一，说明距离长期均线的偏离度是主升浪最关键的信号
- **结构特征偏弱**: ma_bull_alignment_days 仅排 #21，可能因为缺少 RS20 后结构 Alpha 信号不足
- **黄金坑特征几乎无用**: is_fake_breakdown (#24), is_water_ignition (#23), is_extreme_volume_dry (#17) 排名靠后

---

## 五、结论

### 当前结果不可用于实盘

核心原因：
1. RS20（GPT 认定的最强特征）因工程 bug 完全缺失
2. Gate 模型接近随机，级联乘法将概率压扁
3. Precision@任何阈值都远低于目标

### 修复方案（已执行）

`_worker_wrapper()` 已修复：每个子进程独立加载大盘指数，确保 RS20 在全量扫描中被计算。

### 下一步

1. **全量重新扫描**: `python3 backend/super_trend_scanner_v1_grok.py --full`
   - 验证输出 CSV 中是否包含 `rs_20d` 列
   - 观察 RS20 的非空率（预期 >90%）

2. **重新训练**: `python3 backend/super_trend_ml_trainer.py`
   - 重点关注：
     - rs_20d 是否进入 Top 5 特征
     - Gate AUC 是否从 0.60 提升到 0.70+
     - 概率分布 max 是否突破 0.70
     - Precision@0.50 是否达到 30%+

3. **如果 Gate 仍然弱**:
   - 考虑方案 A: 放弃 Gate 模型，只用 Precision 单模型
   - 考虑方案 B: 给 Gate 添加更多"价值过滤"特征（如基本面、市值、换手率绝对值）
   - 考虑方案 C: Gate 改用更高阈值（如 label >= 1.5，即在 Label 1 中取 top 部分作为 Gate 正样本）
