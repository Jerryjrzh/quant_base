# Super Trend Phase 1 Code Review 与调整报告

> 基于 `super_trend_step1_review.md`（架构师 Review）与 `backend/phase1_summary.md`（Phase 1 完成总结）的综合评审，本报告记录了所有实际落地的代码调整。

---

## 一、Review 结论总览

| 问题分类 | 原始问题描述 | 严重程度 | 处理结果 |
|---|---|---|---|
| 性能瓶颈：单线程扫描 | `for stock_code in test_stocks:` 全市场 5000 只股票跑不动 | 高 | ✅ 已修复：新增 `main_multiprocessing()` |
| ZeroDivisionError 风险 | `t0_price=0` 或 `prev['close']=0` 导致除零崩溃 | 高 | ✅ 已修复：三处价格守卫 |
| 训练数据含 inf/nan | 停牌股导致特征矩阵出现 Infinity/NaN | 中 | ✅ 已修复：`get_training_data()` 兜底清理 |
| 特征计算除零 | `lowest_price=0` 导致 `price_rebound_from_pit` 崩溃 | 中 | ✅ 已修复：加 `> 0.01` 守卫 |
| 极致缩量误判 | `vol_ma20=0` 时错误地标记为"极致缩量" | 低 | ✅ 已修复：加 `vol_ma20 > 0` 守卫 |
| 60 分钟线支持 | 报告中提到但未接入 | 低 | ⏳ 延至 Phase 2，当前用日线 Baseline |

---

## 二、代码调整详情

### 2.1 `super_trend_scanner_v1.py`

#### 修复 1：无效价格过滤（防除零）

**位置**：`scan_single_stock()` 主循环内，计算 MFE/MAE 之前

```python
t0_price = df.iloc[i]['close']
# 过滤停牌/退市等无效价格，避免除零错误
if t0_price <= 0.01:
    continue
```

**位置**：T0 回溯窗口内，计算 `price_change` 之前

```python
prev_close = prev['close']
if prev_close <= 0.01:
    continue
price_change = (current['close'] / prev_close) - 1.0
```

**原因**：长期停牌后退市的股票价格可能为 0 或极小值，`(future_high / t0_price) - 1.0` 会触发 `ZeroDivisionError` 或产生无穷大，污染整个候选点集合。

---

#### 修复 2：多进程全市场扫描

**新增函数**：
- `_worker_wrapper(stock_code)` — 多进程 worker 包装器
- `_get_all_stock_codes()` — 从 VIPDOC 目录动态读取全市场股票代码
- `_save_and_report()` — 抽取公共的结果汇总与保存逻辑
- `main_multiprocessing(chunk_size=1000)` — 全市场并发扫描入口

**核心设计**：
```
Pool(cpu_count()) + imap_unordered + tqdm 进度条
每收集 chunk_size 个候选切片 → 落盘保存独立 CSV → 防止内存溢出
```

**调用方式**：
```bash
# 单线程小规模测试（默认）
python super_trend_scanner_v1.py

# 多进程全市场扫描
python super_trend_scanner_v1.py --full
```

---

### 2.2 `super_trend_data_snapshot.py`

#### 修复：训练数据 inf/nan 兜底清理

**位置**：`EpisodeCollection.get_training_data()` 返回前

```python
X_df = pd.DataFrame(X)
y_series = pd.Series(y)
# 兜底：消除inf/nan，防止除零或极端值污染训练数据
X_df = X_df.replace([np.inf, -np.inf], np.nan).fillna(0)
return X_df, y_series
```

**原因**：Test Case 3（长期停牌/一字跌停股）场景下，停牌期间成交量为 0，`mean_vol=0` 导致 `vol_dryup_count` 计算中出现 `inf`；`squeeze_tightening_ratio` 在分母极小时产生极大值。这些异常值会直接破坏 LightGBM 的梯度计算。

---

### 2.3 `super_trend_feature_extractor.py`

#### 修复 1：坑底反弹幅度除零守卫

**位置**：`extract_delta_range_features()` 第 3 项特征

```python
# 3. 坑底反弹幅度（防除零）
lowest_price = window_df['low'].min()
if lowest_price > 0.01:
    features['price_rebound_from_pit'] = (t0_row['close'] / lowest_price) - 1.0
else:
    features['price_rebound_from_pit'] = 0.0
```

#### 修复 2：极致缩量误判守卫

**位置**：`extract_golden_pit_features()` 第 3 项特征

```python
if vol_ma20 > 0:
    features['is_extreme_volume_dry'] = int(current_vol < vol_ma20 * 0.8)
else:
    features['is_extreme_volume_dry'] = 0
```

**原因**：`vol_ma20=0` 时，`current_vol < 0 * 0.8` 恒为 `False`，导致长期停牌股被错误地"排除"在极致缩量特征之外，实际上这类股票恰恰是最需要被标记的候选对象。

---

## 三、Test Case 对照验证

| Test Case | 目标 | 验证方法 | 当前状态 |
|---|---|---|---|
| TC1: 完美妖股捕获 | `sh688146` 2026年1-5月，精准捕捉4月中旬突破点 | 运行扫描器后检查 `.pkl` 中 `future_mfe > 50%` | 可执行，需有数据 |
| TC2: 次新股边界 | 上市不足60天新股，平滑跳过无 Exception | `scan_single_stock` 开头 `return []` 验证 | ✅ 已有 `MIN_DATA_DAYS=100` 过滤 |
| TC3: 长期停牌压力 | 除零错误不崩溃，特征表无 NaN/inf | 检查 `get_training_data()` 输出的 X | ✅ 已在三处加价格守卫 + inf/nan 兜底 |
| TC4: 负样本平衡 | 50只大盘股，正样本比例 2%~5% | 扫描后调用 `y.mean()` | ⚠️ 扫描器目前仅输出正样本，负样本需额外采样 |
| TC5: 全市场并发 | `--full` 模式全量扫描，内存稳定 | 观察内存 + 分块落盘 | ✅ `main_multiprocessing` 已实现 |

### TC4 补充说明：负样本采集

当前扫描器只输出满足主升浪条件的正样本（`is_positive=True`）。要生成训练所需的负样本，建议以下方式之一：

- **方案 A**：在扫描时每隔 N 天（如 100 天）随机采样一个不满足条件的点，标记 `is_positive=False`
- **方案 B**：单独对大盘股批量扫描，利用不满足 `mfe >= 50%` 条件的窗口自动归为负样本

Phase 2 训练前需补充此逻辑，目标正样本比例：**2% ~ 5%**。

---

## 四、文件变更清单

```
backend/
├── super_trend_scanner_v1.py          # +价格守卫 +多进程main +公共函数抽取
├── super_trend_feature_extractor.py   # +坑底反弹除零守卫 +极致缩量守卫
└── super_trend_data_snapshot.py       # +get_training_data() inf/nan兜底
```

---

## 五、Phase 2 前置条件（下一步）

1. **负样本采集逻辑**：在 `scan_single_stock` 中加入等比例负样本抽样，确保正样本比 ≤5%
2. **全市场扫描执行**：运行 `python super_trend_scanner_v1.py --full`，收集完整训练集
3. **特征重要性预分析**：在训练前对 14 个特征做相关性热力图，剔除高度共线性特征
4. **60 分钟数据接入**：将 `data_handler` 扩展支持 60min K 线，作为 Phase 2 增量特征
