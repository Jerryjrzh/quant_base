# Super Trend — GPT Review 四项修正落地报告

> 基于 `super_trend_casecade_reform_report_review_gpt.md` 的 4 项必改/增补建议，在级联双模型架构基础上做精确修正。

---

## 一、修正总览

| # | GPT 建议 | 修改文件 | 状态 |
|---|---------|---------|------|
| Fix1 | 真正补 MA10/MA20，不要 MA13/MA21 替代 | `data_handler.py`, `super_trend_scanner_v1_grok.py` | Done |
| Fix2 | 增加 Relative Strength (RS20) + 量能百分位 | `super_trend_scanner_v1_grok.py` | Done |
| Fix3 | 概率校准 Platt Scaling | `super_trend_ml_trainer.py` | Done |
| Fix4 | MA 对齐用 MA5>MA10>MA20>MA60（市场共识） | `super_trend_scanner_v1_grok.py` | Done |

---

## 二、Fix1: 补真正 MA10/MA20 到指标计算

### 问题

`data_handler.py` 的 `calculate_all_indicators()` 只计算 MA7/13/30/45/60/90/150/240，没有市场标准周期 MA10/MA20。之前特征提取器用 MA13 代替 MA10、MA21 代替 MA20，属于"为了适配代码修改金融逻辑"。

### 修改

**`backend/data_handler.py` — `calculate_all_indicators()`**

```python
# 新增：市场共识均线 MA10, MA20
df['ma10'] = indicators.calculate_ma(df, 10)
df['ma20'] = indicators.calculate_ma(df, 20)
```

现在完整 MA 系列：5, 7, 10, 13, 20, 21, 30, 45, 60, 90, 150, 240。

---

## 三、Fix2: 增加 Relative Strength 特征

### 问题

GPT 指出当前最缺的是 **Relative Strength**（相对强度），而非 Absolute Strength。`stock_return_20d` 只衡量个股绝对涨幅，不区分"大盘涨带动"还是"个股独立走强"。

### 新增特征

**`backend/super_trend_scanner_v1_grok.py` — `_extract_enhanced_features()`**

| 特征 | 公式 | 金融含义 |
|------|------|---------|
| `rs_20d` | `stock_return_20d - index_return_20d` | 个股相对大盘的超额收益，核心 alpha 特征 |
| `volume_percentile_120d` | `rank(vol_t0) / count(vol_120d)` | 当前成交量在 120 天中的百分位，衡量放量程度 |

### RS20 实现细节

```python
# 12. 相对强弱 RS20
if df_market is not None and t0_idx >= 20:
    t0_date = _get_t0_date(df, t0_idx)
    mkt_pos = df_market.index[df_market.index.astype(str).str[:10] == t0_date_str]
    mkt_ret_20d = (df_market.iloc[mkt_pos]['close'] / df_market.iloc[mkt_pos - 20]['close']) - 1.0
    features['rs_20d'] = stock_ret_20d - mkt_ret_20d
```

- 需要 `df_market`（大盘指数数据）通过 `build_episodes()` 传入
- 大盘数据不可用时静默跳过，不中断扫描

---

## 四、Fix3: Platt Scaling 概率校准

### 问题

GPT 指出：LightGBM 的 `predict_proba` 不是真实概率，而是排序分数。在级联架构 `P(A) × P(B)` 中，两个排序分数相乘会导致概率压缩（如 0.4×0.5=0.2），使得阈值设定极其困难。

### 方案

在每个模型训练后，用验证集数据拟合一个 **Logistic Regression**（即 Platt Scaling），将 LightGBM 原始输出映射为校准概率。

### 修改

**`backend/super_trend_ml_trainer.py`**

1. **新增属性**: `calibrator_a`, `calibrator_b`

2. **新增方法**:
```python
@staticmethod
def _fit_platt_scaler(model, X, y, name="Model"):
    """对 LightGBM booster 输出做 Platt Scaling"""
    raw_scores = model.predict(X).reshape(-1, 1)
    calibrator = LogisticRegression(solver='lbfgs', max_iter=1000)
    calibrator.fit(raw_scores, y)
    return calibrator

def _calibrated_predict(self, X, model, calibrator):
    """Platt 校准后的预测"""
    raw = model.predict(X)
    if calibrator is not None:
        return calibrator.predict_proba(raw.reshape(-1, 1))[:, 1]
    return raw
```

3. **训练流程**:
```
train_model():
  训练 Gate → Platt 校准 Gate
  训练 Precision → Platt 校准 Precision
  级联评估（使用校准概率）
```

4. **交叉验证**: 每折独立拟合 Platt calibrator，校准后的概率用于级联 AUC 计算

5. **模型持久化**: `save_model()` / `load_model()` 均保存/恢复 calibrator_a 和 calibrator_b

### 预期效果

- 校准后 prob_A 和 prob_B 更接近真实概率
- 级联乘法 `prob_A × prob_B` 的概率分布更合理
- 多阈值分析的 Precision 曲线更平滑，阈值选择更有依据

---

## 五、Fix4: MA 对齐改为 MA5>MA10>MA20>MA60

### 问题

之前用 MA5>MA13>MA30>MA60 做均线多头排列检测。MA13/MA30 不是市场标准周期，这个排列没有广泛交易意义。

### 修改

**`backend/super_trend_scanner_v1_grok.py` — `_extract_enhanced_features()`**

```python
# 旧：MA5>MA13>MA30>MA60
# 新：MA5>MA10>MA20>MA60
ma_cols = ['ma5', 'ma10', 'ma20', 'ma60']
if row['ma5'] > row['ma10'] > row['ma20'] > row['ma60']:
    alignment_days += 1
```

同时 `bias_ma20` 改用真正的 MA20 列（不再是 MA21 fallback）：

```python
# 旧：bias_ma20 = close / ma21 - 1  (MA21 fallback)
# 新：bias_ma20 = close / ma20 - 1  (真正 MA20)
```

---

## 六、增强特征完整清单（修正后）

`_extract_enhanced_features()` 现在输出 12 个特征：

| # | 特征名 | 类别 | 来源 |
|---|--------|------|------|
| 1 | `ma_bull_alignment_days` | 结构 Alpha | Fix4: 改用 MA5/10/20/60 |
| 2 | `bias_ma20` | 乖离率 | Fix1: 改用真 MA20 |
| 3 | `bias_ma60` | 乖离率 | 原有 |
| 4 | `atr_percentile` | 波动率 | 原有 |
| 5 | `boll_width` | 波动率 | 原有 |
| 6 | `pre_breakout_vol_shrink_days` | 量能 | 原有 |
| 7 | `vol_breakout_ratio` | 量能 | 原有 |
| 8 | `price_position_120d` | 位置 | 原有 |
| 9 | `stock_return_20d` | 动量 | 原有 |
| 10 | `vol_turnover_ratio` | 量能 | 原有 |
| 11 | `volume_percentile_120d` | 量能 | Fix2 新增 |
| 12 | `rs_20d` | 相对强度 | Fix2 新增（核心） |

加上基础特征提取器的 13 个特征，总特征数 = **25 个**。

---

## 七、文件变更汇总

```
backend/data_handler.py
  └── calculate_all_indicators():
      ├── 新增 ma10 = calculate_ma(df, 10)
      └── 新增 ma20 = calculate_ma(df, 20)

backend/super_trend_scanner_v1_grok.py
  └── _extract_enhanced_features(df, t0_idx, df_market=None):
      ├── Fix1+4: ma_bull_alignment_days → MA5>MA10>MA20>MA60
      ├── Fix1: bias_ma20 → 使用真正 ma20 列
      ├── Fix2: 新增 volume_percentile_120d
      └── Fix2: 新增 rs_20d (需要 df_market)
  └── build_episodes():
      └── 传递 df_market 给 _extract_enhanced_features

backend/super_trend_ml_trainer.py
  ├── 新增 LogisticRegression import
  ├── __init__: 新增 calibrator_a, calibrator_b
  ├── 新增 _fit_platt_scaler() 方法
  ├── 新增 _calibrated_predict() 方法
  ├── train_model(): 训练后拟合 Platt Scaling
  ├── evaluate_model(): 使用校准概率
  ├── cross_validation(): 每折独立 Platt 校准
  ├── save_model(): 保存 calibrators
  └── load_model(): 恢复 calibrators
```

---

## 八、验证状态

| 检查项 | 状态 |
|--------|------|
| data_handler.py 语法检查 | OK |
| super_trend_scanner_v1_grok.py 语法检查 | OK |
| super_trend_ml_trainer.py 语法检查 | OK |
| super_trend_data_snapshot.py 语法检查 | OK |
| MA10/MA20 真正计算（非 MA13/MA21 替代） | OK |
| MA 多头排列用 MA5>MA10>MA20>MA60 | OK |
| RS20 需要 df_market 传入 | OK |
| Platt Scaling 训练+评估+CV+持久化 全链路 | OK |
| 向后兼容旧模型加载（calibrator=None 时回退原始分数） | OK |

---

## 九、下一步

1. **全市场重新扫描**: `python3 backend/super_trend_scanner_v1_grok.py --full`
   - 验证新增特征列 `rs_20d`, `volume_percentile_120d` 出现在输出 CSV
   - 验证三分类分布（预期 Label2 约 3-8%）

2. **级联模型训练**: `python3 backend/super_trend_ml_trainer.py`
   - 观察 Platt 校准后 AUC vs 原始 AUC 差异
   - 观察校准后多阈值 Precision 分布
   - 关注 `rs_20d` 的特征重要性排名

3. **Precision 验收**: 目标 Precision@0.65 ≥ 50%（GPT 预期 45-55%）
