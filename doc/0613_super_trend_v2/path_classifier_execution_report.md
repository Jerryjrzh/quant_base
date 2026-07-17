# 小时线路径分类器 P0 任务执行报告

**日期**: 2026-06-15

**依据**: final_debug_apply_hour_v3.1.md / v3.2.md

**状态**: 已完成，分类器效果不足，未达到集成标准

---

## 一、执行概要

| 步骤 | 任务 | 状态 | 结果 |
|------|------|------|------|
| Step 1 | 路径标签生成 (KMeans 聚类) | PASS | 4408/4423 成功，三类区分度良好 |
| Step 2 | 小时线特征提取 | PASS | 1143/1163 成功，15维特征 |
| Step 3 | 分类器训练 (LightGBM) | FAIL | Accuracy 0.386 (基线 0.333) |
| Step 4 | 集成回测 | FAIL | path_quality 无区分度，过滤无效 |

**结论**: 60m 微观结构特征对未来 22 天路径类型的预测力极弱，v3.1/v3.2 假设未被数据支持。

---

## 二、Step 1: 路径标签生成

### 2.1 方法

- 输入: `review4_final_backtest.csv` (4423 信号)
- 特征: `max_drawdown` (22天最大回撤) + `trend_smoothness` (收盘价 log 线性拟合 R²)
- 聚类: KMeans(k=3, random_state=42)
- 映射: 按 `avg_ret` 降序 → Smooth(最好) / Pullback / Failure(最差)

### 2.2 结果

| 路径 | n | 占比 | avg max_dd | avg R² | avg final_return |
|------|---|------|-----------|--------|------------------|
| Smooth | 1573 | 35.7% | 0.212 | 0.084 | **-0.95%** |
| Pullback | 1318 | 29.9% | 0.225 | 0.417 | -2.97% |
| Failure | 1517 | 34.4% | 0.263 | 0.742 | **-9.00%** |

### 2.3 关键发现

- R² 与收益**负相关**: 高 R² = 平滑下跌 (失败路径)，低 R² = 震荡抗跌 (Smooth)
- 三类收益单调递减: -0.95% > -2.97% > -9.00%，区分度良好
- Smooth 与 Failure 差距 8 个百分点

### 2.4 修复记录

| 问题 | 原因 | 修复 |
|------|------|------|
| 成功: 0, 无数据: 4423 | `get_daily_data_in_range` 参数 bug | 改用 60m 聚合日线 (`_load_daily_via_60m`) |
| 标签映射倒置 | 按 (dd, R²) 排序，R² 与 dd 负相关 | 改为按 `avg_ret` 排序 |

### 2.5 产出

- `doc/0613_super_trend_v2/path_labels.csv` (4423 行)
- `doc/0613_super_trend_v2/path_labels_report.md`

---

## 三、Step 2: 小时线特征提取

### 3.1 方法

- 输入: 每笔信号 T0 日及之前 35 日历天的 60m K 线
- 窗口: tail(400) 根 60m bar
- 特征: 15 维

| 维度 | 特征 |
|------|------|
| 趋势 | ma20_slope, close_ma20_ratio, close_ma60_ratio, momentum_20 |
| 波动 | volatility_20, avg_amplitude, gap_freq |
| 量价 | up_down_vol_ratio, volume_trend, vol_5_20_ratio |
| 形态 | drawdown_depth_80, rebound_ratio_80, new_high_freq, ma20_touch_freq |

### 3.2 结果

- 目标信号: traded(394) + expired(769) = 1163
- 成功提取: 1143 (98.3%)
- 耗时: 30.8s

### 3.3 特征重要性 (LightGBM)

| 排名 | 特征 | 重要性 |
|------|------|--------|
| 1 | up_down_vol_ratio | 52 |
| 2 | gap_freq | 40 |
| 3 | drawdown_depth_80 | 39 |
| 4 | volatility_20 | 37 |
| 5 | volume_trend | 36 |

---

## 四、Step 3: 分类器训练

### 4.1 数据划分

| 分割 | 时间范围 | n | 标签分布 (0/1/2) |
|------|---------|---|-----------------|
| 训练 | <2025-09-01 | 835 | 346/263/226 |
| 验证 | 2025-09~2026-01 | 176 | 42/56/78 |
| 测试 | ≥2026-01-01 | 132 | 43/39/50 |

### 4.2 模型配置

```
LightGBM:
  objective: multiclass, num_class=3
  num_leaves: 31, learning_rate: 0.05
  n_estimators: 200, subsample: 0.8
  colsample_bytree: 0.8, early_stopping: 30
```

### 4.3 测试集结果

| 指标 | 值 | 达标 |
|------|------|------|
| Accuracy | 0.386 | FAIL (>0.6 要求) |
| Smooth recall | 0.95 | 模型偏向预测 Smooth |
| Pullback recall | 0.10 | 几乎不预测 |
| Failure recall | 0.12 | 几乎不预测 |

**诊断**: 模型将 94/97 笔预测为 Smooth，退化为单类预测器。Precision/Recall 严重失衡。

### 4.4 修复记录

| 问题 | 原因 | 修复 |
|------|------|------|
| 训练集 0 样本 | TRAIN_CUTOFF=2025-02 但数据从 2025-02 开始 | 调整为 TRAIN_CUTOFF=2025-09 |
| LightGBM LabelEncoder 报错 | 训练集缺类别时内部编码器失败 | 预编码 int32 + 借用验证集样本 |
| pd.qcut ValueError | path_quality 值过于集中 | 加 try/except 回退 pd.cut |

---

## 五、Step 4: 集成回测

### 5.1 方法

```python
path_quality = p_smooth * 1.0 + p_pullback * 0.5 + p_failure * 0.0
final_score = operable_score * path_quality
```

### 5.2 path_quality 分位分析

| 分位 | n | avg path_quality | avg PnL | 胜率 |
|------|---|-----------------|---------|------|
| low | 131 | 0.542 | 2.78% | 51.9% |
| mid | 130 | 0.584 | **4.81%** | **57.7%** |
| high | 130 | 0.617 | 3.45% | 53.1% |

### 5.3 过滤阈值测试

| 阈值 | 通过数 | 通过 avg PnL | 基线 avg PnL | 差值 | 通过 WR |
|------|--------|-------------|-------------|------|---------|
| ≥0.3 | 391 (100%) | 3.68% | 3.68% | +0.00% | 54.2% |
| ≥0.4 | 391 (100%) | 3.68% | 3.68% | +0.00% | 54.2% |
| ≥0.5 | 389 (99.5%) | 3.72% | 3.68% | +0.04% | 54.5% |
| ≥0.6 | 130 (33.2%) | 3.45% | 3.68% | **-0.23%** | 53.1% |

**结论**: path_quality 范围极窄 (0.54~0.62)，无任何有效过滤能力。阈值 0.6 过滤掉 67% 信号但被过滤的 PnL 反而更高 (3.79% vs 3.45%)。

### 5.4 产出

- `doc/0613_super_trend_v2/path_predictions.csv` (391 行)
- `doc/0613_super_trend_v2/path_classifier_report.md`

---

## 六、根因分析

### 6.1 为什么分类器失败？

1. **预测目标本质上是收益率**: Smooth/Failure 的区分依据是 `avg_ret`，而股票 22 天收益率本身极难预测
2. **微观结构与宏观路径的鸿沟**: 60m K 线的形态特征（量价、波动、趋势）反映的是短期交易行为，与 22 天路径类型之间缺乏因果联系
3. **信噪比过低**: 相同的小时线形态在不同市场环境、不同行业下可能对应完全不同的后续路径

### 6.2 与 v3.1 假设的对比

| v3.1 假设 | 实际结果 |
|-----------|---------|
| 小时线能区分 Smooth/Pullback/Failure | Accuracy 38.6%，接近随机 |
| Smooth 满仓，Failure 过滤 | path_quality 范围过窄，无法过滤 |
| 最终提升整体盈亏 | 无提升，甚至略有下降 |

---

## 七、后续建议

### 7.1 可选优化 (低优先级)

| 方案 | 预期提升 | 工作量 |
|------|---------|--------|
| 二分类 (Smooth vs Not-Smooth) | 可能略好，但根因不变 | 0.5天 |
| 加入日线特征融合 (趋势强度、行业RS) | 可能增加信息量 | 1天 |
| 缩短预测窗口 (5天而非22天) | 短期路径可能更可预测 | 1天 |

### 7.2 推荐方向 (高优先级)

| 方案 | 理由 |
|------|------|
| **P1: 行业动量特征** | 日线系统已验证，行业RS 是已知的 alpha 因子 |
| **P3: 资金流向** | 北向资金/大单流向有独立信息增量 |

### 7.3 总结

**v3.1/v3.2 的"小时线路径分类器"方案在当前数据和特征下未达到预期效果。** 核心假设（小时线微观结构能预测 22 天路径类型）未被数据支持。建议放弃此方向，转向信息增量更确定的 P1（行业动量）和 P3（资金流向）。

---

## 八、文件清单

| 文件 | 说明 |
|------|------|
| `scripts/build_path_labels.py` | Step 1 路径标签生成 |
| `backend/hourly_features.py` | Step 2 小时线特征提取 |
| `scripts/train_path_classifier.py` | Step 2+3+4 分类器训练+集成 |
| `doc/0613_super_trend_v2/path_labels.csv` | 路径标签 (4423 行) |
| `doc/0613_super_trend_v2/path_labels_report.md` | Step 1 报告 |
| `doc/0613_super_trend_v2/path_predictions.csv` | 预测结果 (391 行) |
| `doc/0613_super_trend_v2/path_classifier_report.md` | Step 2+3+4 报告 |
| `doc/0613_super_trend_v2/path_classifier_execution_report.md` | 本报告 |
