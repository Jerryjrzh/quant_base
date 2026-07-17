# Super Trend — GPT Review1 回应与修正

> 针对 `super_trend_gpt_review1.md` 提出的 3 个风险点逐一验证与处理。

---

## 验证结论

| 风险 | GPT 判断 | 实际验证 | 处理 |
|------|---------|---------|------|
| Risk1: RS20 日期对齐 | 潜在未来函数 | **确认为真 bug** | **已修复** |
| Risk2: Platt 训练集来源 | 可能过拟合 | 实现已正确 | 无需改动 |
| Risk3: Label2 阈值范围 | 刚过线 vs 超级牛混杂 | 合理但当前不改 | 保留备用方案 |

---

## Risk1: RS20 日期对齐 — 已修复（最高优先级）

### 问题根因

原代码：

```python
# 个股: t0_idx → t0_idx-20 (20 行)
stock_ret_20d = close[t0_idx] / close[t0_idx - 20] - 1

# 大盘: mkt_pos → mkt_pos-20 (20 行)
mkt_ret_20d = mkt_close[mkt_pos] / mkt_close[mkt_pos - 20] - 1
```

个股 20 行 ≠ 大盘 20 行的日历时间，当个股有停牌/缺失时产生错位。

### 修复方案

用个股 `t0_idx - 20` 行的**实际日历日期**去大盘数据中查找对应位置，确保两侧跨越完全相同的日历区间：

```python
t0_date = _get_t0_date(df, t0_idx)          # 个股 T0 日期
start_date = _get_t0_date(df, t0_idx - 20)  # 个股 20 行前的实际日期

mkt_t0_pos = market 中 t0_date 的位置
mkt_start_pos = market 中 start_date 的位置

mkt_ret = mkt_close[mkt_t0_pos] / mkt_close[mkt_start_pos] - 1
```

- 如果大盘数据中找不到 `start_date`（极端情况），静默跳过不计算 `rs_20d`
- 增加了 `mkt_t0_pos > mkt_start_pos` 防御性检查

### 文件变更

`backend/super_trend_scanner_v1_grok.py` — `_extract_enhanced_features()` 第 12 项 RS20

---

## Risk2: Platt Scaling — 实现已正确，无需改动

### GPT 担心的场景

```
Platt.fit(训练集预测, 训练集标签) → 严重过拟合
```

### 当前实际实现

```python
# 时序切割
X_train, X_test = X.iloc[:80%], X.iloc[80%:]

# LightGBM 在 Train 训练
self.model_a = train(X_train, y_train, X_test, y_test)

# Platt 在 Test 拟合（out-of-sample 预测）
self.calibrator_a = _fit_platt_scaler(self.model_a, X_test, ya_test)
```

LightGBM 训练用的是 `X_train`，Platt 拟合用的是 `X_test` 上的预测值——这是标准的 out-of-sample 校准，不存在过拟合。

这与 Platt (1999) 原始论文和 sklearn `CalibratedClassifierCV` 的 `cv='prefit'` 模式一致：模型在 train 上训练，calibrator 在独立数据上拟合。

### 可选进一步优化

如果追求极致，可以做 3-way split（train 60% / calibrate 20% / evaluate 20%），但对 20% test set 来说收益微小。当前方案已满足工程标准。

---

## Risk3: Label2 阈值 — 同意暂不改动

### GPT 观察

```
Label2 = MFE >= P95（如主板 43%）
→ 44% 和 300% 都是 Label2
→ 刚过线 vs 超级牛股混在一起
```

### 回应

同意 GPT 判断：当前不改，保留备用方案 `Label2A (43-80%)` / `Label2B (80%+)`。

如果 Model B AUC 不达预期（<0.65），第一怀疑对象就是这里。届时可以实验细粒度标签。

---

## GPT 预期指标验证标准

采纳 GPT 调整后的验收标准：

| 指标 | 合格线 |
|------|--------|
| CV AUC | > 0.75 |
| Test AUC | > 0.74 |
| Precision@0.50 | > 40% |
| Precision@0.65 | > 45% |
| Precision@0.70 | > 50% |

同时关注 **Top N Precision**（Top 50/100/200），不局限于固定阈值。

---

## 训练后重点观察项

| # | 观察项 | 预期 |
|---|--------|------|
| 1 | Label 分布 (0/1/2) | ~60/35/5% |
| 2 | Model A (Gate) AUC | > 0.80 |
| 3 | Model B (Precision) AUC | > 0.65 |
| 4 | RS20 特征重要性排名 | Top 5（若排名 20+ 则实现有问题） |
| 5 | 正负样本概率均值差 | > 0.12 |

---

## 文件变更汇总

```
backend/super_trend_scanner_v1_grok.py
  └── _extract_enhanced_features():
      └── RS20 日期对齐修复：用个股实际日历日期匹配大盘
          - 新增 start_date = _get_t0_date(df, t0_idx - 20)
          - 双向日期查找：mkt_t0_idx + mkt_start_idx
          - 防御性检查：mkt_t0_pos > mkt_start_pos
```

---

## 最终状态

| 检查项 | 状态 |
|--------|------|
| RS20 严格日期对齐 | Fixed |
| Platt Scaling 使用 out-of-sample 数据 | Confirmed Correct |
| Label2 阈值暂不拆分 | Agreed |
| 语法检查 | OK |
| 可以启动全量扫描+训练 | Yes |
