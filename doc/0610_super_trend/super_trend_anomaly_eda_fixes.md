# Super Trend — 全量异动扫描器 & EDA 修复记录

> 基于 `super_trend_scan_dbg_review.md` 和 `super_trend_scan_dbg_review1.md` 的落地修复。

---

## 一、扫描器修复 (`super_trend_anomaly_scanner.py`)

### 修复 1：MFE/MAE 计算逻辑修正

**问题**：原始计算允许 MFE 为负数（未来最高价仍低于 T0 价格）或 MAE 为正数（未来最低价仍高于 T0 价格），在语义上不准确。

**修复**：MFE 最小为 0（从未超过 T0 则无涨幅），MAE 最大为 0（从未跌破 T0 则无回撤）。

```python
# 旧
record[f'future_mfe_{w}d'] = (future_high / t0_price) - 1.0
record[f'future_mae_{w}d'] = (future_low / t0_price) - 1.0

# 新
record[f'future_mfe_{w}d'] = max(0.0, (future_high / t0_price) - 1.0)
record[f'future_mae_{w}d'] = min(0.0, (future_low / t0_price) - 1.0)
```

---

### 修复 2：停牌/死水 K 线过滤

**问题**：停牌复牌首日或长期一字板的 K 线，`volume == 0`，无任何异动意义，会被错误采集。

**修复**：在计算 daily_gain 之前过滤 `volume == 0`。

```python
# 过滤停牌或一字死水
if df.iloc[i]['volume'] == 0:
    continue
```

---

### 暂不修改：大盘预加载

Review 建议预加载大盘指数避免多进程 I/O 拥堵。但该扫描器不涉及 `market_context` 字段，当前无此需求。标记为可选优化，待后续集成时再处理。

---

## 二、EDA 脚本修复 (`super_trend_eda_analysis.py`)

### 修复：脏数据清洗

**问题**：A 股 TDX 日线数据中存在两类脏数据会严重干扰分位数计算：
1. **停牌死水**：未来 MFE=0 且 MAE=0，无异动意义
2. **未复权断层**：除权除息导致价格"腰斩"或暴涨 1000%，MFE 畸高

**修复**：在 `load_data()` 返回前清洗。

```python
# 过滤完全死水（未来既没涨也没跌）
df = df[(df['future_mfe_22d'] > 0) | (df['future_mae_22d'] < 0)]
# 过滤极端异常值（22 天涨幅超 500%，多为未复权数据错误）
df = df[df['future_mfe_22d'] <= 5.0]
```

---

## 三、文件变更汇总

```
backend/super_trend_anomaly_scanner.py   # MFE/MAE 修正 + 停牌过滤
backend/super_trend_eda_analysis.py      # load_data() 脏数据清洗
```

---

## 四、使用流程

```bash
# Step 1: 全量异动扫描（多进程，约 10-30 分钟）
python super_trend_anomaly_scanner.py

# Step 2: EDA 分布分析（读取 CSV，秒级完成）
python super_trend_eda_analysis.py

# Step 3: 根据 derive_thresholds() 输出的建议，
#         回写到 super_trend_scanner_v1.py 的 MIN_GAIN / NEG_MAX_FUTURE_GAIN
```

---

## 五、验证状态

| 检查项 | 状态 |
|---|---|
| 两文件编译通过 | ✅ |
| MFE ≥ 0, MAE ≤ 0 语义修正 | ✅ |
| 停牌死水过滤 (volume == 0) | ✅ |
| EDA 脏数据清洗 (死水 + MFE > 500%) | ✅ |
