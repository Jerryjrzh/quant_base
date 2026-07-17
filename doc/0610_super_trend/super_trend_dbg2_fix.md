# Super Trend Scanner 数据重叠（Data Overlap）验证与修复

## 问题描述

`scan_single_stock` 按天遍历 K 线，当一只股票进入主升浪后，连续多天都会满足正样本条件（MFE>=100% 且回撤可控），且向前回溯 T0 时会锁定到同一根大阳线，导致同一个起爆点生成多个高度冗余的 `EpisodeSnapshot`。

**隐患：**
- **数据泄露（Data Leakage）**：重叠切片在随机划分训练/测试集时，模型在测试集上虚高，实盘失效
- **权重失衡**：持久主升浪产生更多重复切片，模型偏向慢牛而非爆发妖股

## 验证结果

对全市场 5408 个 per-stock `.pkl` 文件进行 T0 去重统计：

```
Total slices: 488,011
Unique T0:    437,027
Overall dup ratio: 1.12x

Top 10 worst duplicates:
  sz301626: 39 slices / 17 unique T0 = 2.3x
  sh688411: 70 slices / 32 unique T0 = 2.2x
  sz301658: 48 slices / 23 unique T0 = 2.1x
  bj920252: 216 slices / 114 unique T0 = 1.9x
  bj920273: 152 slices / 89 unique T0 = 1.7x
  ...
```

**结论**：总体重复率 12%，部分个股高达 2.3x。问题确认存在。

## 修复方案

在 `scan_single_stock` 的遍历循环中引入 `seen_t0_indices` 集合，T0 回溯完成后检查去重：

```python
candidates = []
seen_t0_indices = set()  # 新增

for i in range(MIN_DATA_DAYS, len(df) - FUTURE_DAYS):
    # ... MFE/MAE 计算、打标逻辑不变 ...

    # 正样本向前回溯 T0（逻辑不变）
    t0_idx = i
    if is_positive:
        for lookback in ...:
            ...
            if price_change > 0.03 and vol_ratio > 1.5:
                t0_idx = idx
                break

    # 新增：T0 去重
    if t0_idx in seen_t0_indices:
        continue
    seen_t0_indices.add(t0_idx)

    # ... 后续 T+1 撮合数据计算和 append 不变 ...
```

## 修改文件

- `backend/super_trend_scanner_v1.py`
  - L54: 新增 `seen_t0_indices = set()`
  - L108-110: 新增 T0 去重检查 `if t0_idx in seen_t0_indices: continue`

## 预期效果

修复后每只股票的每个独立起爆点只生成一个切片，消除冗余，训练数据的独立性得到保证。重新运行 `--full` 扫描后，总切片数预计从 ~488K 降至 ~437K。

---

## 重新扫描后验证结果

去重修复完全生效，Duplicate T0 = 0。

```
Total episodes:  437,027
Positive (Y=1):  116,493 (26.7%)
Negative (Y=0):  320,534 (73.3%)
Pos/Neg ratio:   1:2.8
Duplicate T0:    0
```

### Positive MFE 分布

| 阈值 | 数量 | 占比 |
|------|------|------|
| >=100% | 116,493 | 100% |
| >=150% | 39,574 | 34.0% |
| >=200% | 17,359 | 14.9% |
| >=500% | 910 | 0.8% |
| >=1000% | 73 | 0.1% |

### Negative MFE 分布

- mean: 12.5%, max: 30.0%, min: -20.0%

---

## 额外修复：特征提取器 RSI 列名 Bug

### 问题

`super_trend_feature_extractor.py` 中有两处引用了不存在的 `'rsi'` 列名：

1. **L114** `extract_all_features`: `current.get('rsi', 0)` → 实际列名为 `rsi6`/`rsi14`，导致 `t0_rsi` 始终为 0
2. **L22** `extract_delta_range_features`: `'rsi' in window_df.columns` → 条件永远为 False，`rsi_explosion_force` 特征从未生成

### 修复

- L114: `current.get('rsi', 0)` → `current.get('rsi6', current.get('rsi14', 0))`
- L22-24: 动态检测 `rsi6` / `rsi14` 列名

### 验证

修复后在 sz300675 负样本上重新提取：
- `t0_rsi`: 0 → 88.85
- `rsi_explosion_force`: 缺失 → 59.01
- 特征维度: 12 → 13

**注意**：现有 pkl 文件中的 `t0_rsi` 和 `rsi_explosion_force` 仍为旧值，需重新运行 `--full` 扫描才能全量修正。
