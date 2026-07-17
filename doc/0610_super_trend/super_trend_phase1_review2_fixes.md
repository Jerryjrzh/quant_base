# Super Trend Phase 1 — Review2 调整记录

> 基于 `super_trend_step1_review2.md`（深度排雷报告）与 `super_trend_step1_review2_ext.md`（128G 内存补充说明）的落地修复记录。

---

## 一、三项问题处理结论

| # | 问题 | 严重程度 | 处理结论 |
|---|---|---|---|
| 1 | OOM 内存爆炸（`all_candidates` 积累 11.5 万条 DataFrame） | 原 P0 | **降级，不修复**：`review2_ext` 确认 128G 内存下 40~60G 占用不会 OOM，保持原架构 |
| 2 | 负样本随机陷阱（随机采样无法区分真/假突破） | P0 | **已修复**：改为"假突破"定向采集 |
| 3 | `fillna(0)` 误导 LightGBM（macd_pit_depth=0 误读为"无坑"） | 中 | **已修复**：保留 NaN 给树模型自行处理 |

---

## 二、代码变更详情

### 2.1 `super_trend_scanner_v1.py`

#### 新增：假突破负样本采集逻辑

**新增配置常量**：

```python
NEG_MIN_DAILY_GAIN  = 0.03   # 当天涨幅 >= 3% 才算"有起爆迹象"
NEG_MAX_FUTURE_GAIN = 0.15   # 未来30天最高涨幅 < 15% 才算"假突破"
```

**重构 `scan_single_stock()` 主循环**：

原来的逻辑只在 `mfe >= 50%` 时追加正样本（`is_positive=True`）。新逻辑同时打标两类样本：

```
正样本：mfe >= 50%  且  mae >= -15%  → is_positive=True, sample_type='positive'
负样本：daily_gain >= 3%  且  mfe < 15%  → is_positive=False, sample_type='fake_breakout'
其余：全部跳过（摒弃无价值的横盘垃圾时间）
```

**关键设计意图**：负样本专门挑"看起来像起爆点、但最后坑了人"的交易日。这样 LightGBM 才能学会区分"真突破"和"假突破（骗炮）"，而不是只学会"大阳线=正样本"。

**输出日志变更**：

```
# 旧：发现 N 个候选点
# 新：发现 X 个正样本 + Y 个假突破负样本
```

**`candidates` 字段新增**：
- `daily_gain`：当天涨幅（用于判断假突破）
- `sample_type`：`'positive'` 或 `'fake_breakout'`

**新增辅助函数 `_get_t0_date(df, idx)`**：统一日期提取逻辑，避免重复判断。

---

### 2.2 `super_trend_data_snapshot.py`

#### 修复 1：`fillna(0)` → 保留 NaN

```python
# 旧（误导树模型）
X_df = X_df.replace([np.inf, -np.inf], np.nan).fillna(0)

# 新（让 LightGBM 自行寻找 NaN 的最优分裂方向）
X_df = X_df.replace([np.inf, -np.inf], np.nan)
```

**原理**：LightGBM 原生支持缺失值处理——训练时会自动为 NaN 值分配最优的分裂方向（走左子树或右子树）。`fillna(0)` 会把"上市时间不足导致指标缺失"与"真实数值为0（无坑/无水下）"混为一谈，污染模型学习。

#### 修复 2：`EpisodeSnapshot.__init__` 新增 `is_positive` 参数

```python
def __init__(self, ..., is_positive=None):
    # 优先使用调用方传入的标签；否则以 MIN_GAIN=0.50 作为默认阈值
    self.is_positive = is_positive if is_positive is not None else (future_mfe > 0.50)
```

**修复原因**：旧版硬编码 `future_mfe > 0.40` 作为阈值，与扫描器的 `MIN_GAIN = 0.50` 不一致，导致部分样本在两个模块中被打上不同标签。

---

### 2.3 `test_super_trend_phase1.py`

#### 修复：模拟数据改为正负样本混合

```python
# 旧：只有涨幅 > 40% 的模拟点
future_mfe = np.random.uniform(0.2, 0.8)
if future_mfe > 0.40: ...

# 新：包含正样本 + 假突破负样本
future_mfe = np.random.uniform(0.0, 0.8)
daily_gain = np.random.uniform(-0.02, 0.08)
is_positive = future_mfe >= 0.50
is_fake_breakout = (daily_gain >= 0.03) and (future_mfe < 0.15)
```

`EpisodeSnapshot` 创建时显式传入 `is_positive=cand['is_positive']`，避免从 `future_mfe` 重新推断导致的阈值不一致。

特征值显示也已适配 NaN：

```python
# 旧：val:.4f（NaN 会抛 ValueError）
# 新：pd.notna(val) 判断后再格式化，NaN 显示提示信息
```

---

## 三、文件变更汇总

```
backend/super_trend_scanner_v1.py       # 假突破负样本逻辑 + daily_gain/sample_type 字段
backend/super_trend_data_snapshot.py    # 去除 fillna(0) + is_positive 参数化 + 阈值对齐 0.50
backend/test_super_trend_phase1.py      # 正负样本混合模拟 + is_positive 显式传入 + NaN 显示适配
```

---

## 四、验证状态

| 检查项 | 状态 |
|---|---|
| 四模块语法编译通过 | ✅ |
| 假突破负样本采集逻辑正确（daily_gain >= 3% & mfe < 15%） | ✅ |
| `is_positive` 阈值扫描器/快照一致（0.50） | ✅ |
| NaN 保留给 LightGBM，不再 fillna(0) | ✅ |
| 测试脚本含正负样本混合 | ✅ |

---

## 五、Phase 2 前置条件（更新）

1. **运行全市场扫描**：`python super_trend_scanner_v1.py --full`，收集正样本 + 假突破负样本
2. **检查正样本比例**：目标 2%~5%，若过高则适当提高 `MIN_GAIN` 或降低 `NEG_MAX_FUTURE_GAIN`
3. **LightGBM 训练**：直接使用含 NaN 的 DataFrame 训练，无需额外填充
4. **特征重要性分析**：训练后输出 `feature_importances_`，剔除贡献度 < 1% 的特征
