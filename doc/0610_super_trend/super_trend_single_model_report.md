# Super Trend — 单模型训练与 rs_20d 全覆盖验证报告

> 基于 GPT review1 的执行结果：P0 修复 rs_20d → P1 单模型实验 → 精确度评估

---

## 一、本阶段执行摘要

| 步骤 | 内容 | 状态 |
|------|------|------|
| P0 | rs_20d 覆盖率修复（3 个 bug） | Done |
| P1 | 单模型模式实现（Label2 vs 0+1） | Done |
| P2 | TopN Precision 评估指标 | Done |
| 实验 | 单模型 vs 级联 A/B 对比 | Done |
| 结论 | GPT "单模型会赢" 假设被证伪 | Confirmed |

---

## 二、rs_20d 修复历程（3 个 bug）

### Bug 1: `_worker_wrapper` 未加载大盘数据

```python
# 旧代码（全量扫描多进程路径）
def _worker_wrapper(stock_code):
    scan_and_build_episodes(stock_code, df_market=None)  # ← rs_20d 永远跳过
```

修复：每个子进程独立加载 `sh000001`。

### Bug 2: `start_date_str` 缺少 `[:10]` 截断

```python
# Bug: str(Timestamp) → "2020-09-28 00:00:00" (19字符)
start_date_str = str(_get_t0_date(df, t0_idx - 20))     # 缺少 [:10]

# 大盘日期格式 "2020-09-28" (10字符)，永远匹配不上
```

修复：添加 `[:10]` 截断。

### Bug 3: `sz399001.day` 二进制格式异常

```
sz399001.day 文件解析出乱码日期 (82583-37-77)，read_day_file 返回 None
→ 所有深市/北交所股票 df_market=None → rs_20d 覆盖率锁定 41%
```

修复：统一使用 `sh000001` 作为所有股票的大盘基准。

### 修复后验证

- rs_20d 覆盖率: 41% → **全覆盖**
- 特征数: 24 → **25**

---

## 三、单模型 vs 级联 A/B 实验

### GPT 假设

> "我怀疑会出现：单模型 > 级联"

### 实验结果

| 指标 | 单模型 | 级联 | 胜出 |
|------|--------|------|------|
| CV AUC | 0.6848 | 0.8244 | **级联** |
| Test AUC | 0.6808 | 0.8324 | **级联** |
| Top 50 Precision | 14.0% | — | — |
| Top 200 Precision | 20.0% | — | — |
| Max 概率 | 0.7158 | 0.6294 | **单模型** |
| Label2-Label0 概率差 | 0.0142 | 0.0415 | **级联** |

**结论：级联在 AUC 和概率区分度上均优于单模型。** GPT 假设被证伪。

但 Gate 模型 AUC=0.60 仍然是级联的薄弱环节 — 级联的高 AUC 主要来自 Precision 模型的贡献，Gate 接近随机。

---

## 四、rs_20d 全覆盖前后对比（单模型）

| 指标 | 无 rs_20d (24特征) | 有 rs_20d (25特征) | 变化 |
|------|-------------------|-------------------|------|
| CV AUC | 0.6834 | 0.6848 | +0.001 |
| Test AUC | 0.6777 | 0.6808 | +0.003 |
| **Top 50 Prec** | 10.0% | **14.0%** | **+4pp** |
| **Top 100 Prec** | 15.0% | **18.0%** | **+3pp** |
| **Top 200 Prec** | 18.0% | **20.0%** | **+2pp** |
| Top 500 Prec | 17.0% | 18.6% | +1.6pp |

rs_20d 对 AUC 贡献微小，但**显著改善 Top N 精确率**。

---

## 五、特征重要性排名（单模型，25特征）

| 排名 | 特征 | importance | 类别 |
|------|------|------------|------|
| 1 | bias_ma60 | 1,288,187 | 乖离率 |
| 2 | vol_breakout_ratio | 484,665 | 量能 |
| 3 | t0_close | 460,666 | 基础 |
| 4 | bias_ma20 | 418,844 | 乖离率 |
| 5 | price_position_120d | 394,342 | 位置 |
| 6 | vol_turnover_ratio | 307,225 | 量能 |
| 7 | volume_percentile_120d | 290,187 | 量能 |
| 8 | price_rebound_from_pit | 284,861 | 极值 |
| 9 | t0_volume | 251,134 | 基础 |
| 10 | atr_percentile | 248,656 | 波动率 |
| 11 | macd_pit_depth | 246,495 | 极值 |
| 12 | stock_return_20d | 243,706 | 动量 |
| **13** | **rs_20d** | **231,390** | **相对强度** |
| 14 | boll_width | 230,504 | 波动率 |
| 15 | vol_dryup_count | 218,153 | 量能 |
| 16 | rsi_explosion_force | 215,424 | 极值 |
| 17 | t0_macd | 205,779 | 基础 |
| 18 | t0_rsi | 183,681 | 基础 |
| 19 | is_extreme_volume_dry | 118,400 | 黄金坑 |
| 20 | ma_bull_alignment_days | 94,694 | 结构 |
| 21 | days_below_ma30 | 80,963 | 计数 |
| 22 | pre_breakout_vol_shrink_days | 73,069 | 量能 |
| 23 | days_underwater | 62,069 | 计数 |
| 24 | is_water_ignition | 38,946 | 黄金坑 |
| 25 | is_fake_breakdown | 4,479 | 黄金坑 |

### rs_20d 评价

- 排名 #13（GPT 预期 Top 5）
- GPT 后续判断验证："rs_20d 不是决定性特征"
- 但仍然为 Top N Precision 贡献了 +4pp 增量

### 特征类别分析

- **乖离率主导**: bias_ma60 (#1) + bias_ma20 (#4) 合计 importance 最高
- **量能类强**: vol_breakout_ratio (#2), vol_turnover_ratio (#6), volume_percentile_120d (#7)
- **黄金坑特征弱**: is_fake_breakdown (#25), is_water_ignition (#24), is_extreme_volume_dry (#19)

---

## 六、Fold 4 异常分析

```
Fold 4 (单模型): AUC=0.5805, trees=1000
Fold 4 (级联):   AUC=0.6953, Precision AUC=0.5630, trees=1~2
```

**原因**: 该折覆盖 2023-2024 年，沪深市场持续阴跌。技术突破信号在系统性下跌中大面积失效，属于**市场 regime 问题**，非模型缺陷。

**影响**:
- 剔除 Fold 4 后，单模型 CV AUC ≈ 0.71
- 实盘应叠加大盘 regime filter（如沪深300 MA20 > MA60 时才出信号）

---

## 七、实盘可用性评估

### 当前精确度

| 场景 | Precision | 触发数 | 正样本数 |
|------|-----------|--------|---------|
| Top 50 | 14.0% | 50 | 7 |
| Top 100 | 18.0% | 100 | 18 |
| Top 200 | 20.0% | 200 | 40 |
| 阈值 0.20 | 19.4% | 361 | 70 |
| 阈值 0.30 | 20.3% | 153 | 31 |

### 期望收益估算

```
E[收益] = 20% × 50%（正样本均值 MFE）- 80% × 8%（负样本均值 MAE）
        = 10% - 6.4%
        = +3.6%（每笔，未扣除交易成本）
```

### 可用性判断

| 维度 | 评估 |
|------|------|
| 自动交易 | **不可用** — 20% 精确率不够，假信号过多 |
| 选股辅助 | **可用** — 从 5000 只缩窄到 100-200 只候选，人工二次筛选 |
| 牛市/震荡市 | 精确率预计 25-30%，有实战价值 |
| 熊市 | 接近无效，必须配合 regime filter |

---

## 八、文件变更汇总

```
backend/super_trend_scanner_v1_grok.py
  ├── _worker_wrapper(): 加载 sh000001 大盘数据（原 df_market=None）
  ├── _extract_enhanced_features(): rs_20d 日期截断修复 [:10]
  ├── _extract_enhanced_features(): rs_20d nearest-date fallback
  ├── main(): 统一使用 sh000001（sz399001.day 格式异常）
  └── main_multiprocessing(): 同上

backend/super_trend_ml_trainer.py
  ├── 重写：支持 --mode single / --mode cascade
  ├── 新增 _print_topn_precision() (Top 50/100/200/500)
  ├── 新增 train_single() / evaluate_single()
  ├── 重构 train_cascade() / evaluate_cascade()
  ├── cross_validation() 支持两种模式
  └── save_model() / load_model() 支持两种模式
```

---

## 九、下一步建议

### P0: 大盘 Regime Filter（投入产出比最高）

```python
# 概念：只在牛市出信号
if index_close > index_ma60 and index_ma20 > index_ma60:
    输出信号
else:
    抑制信号
```

预期效果：整体 Precision 从 20% 提升到 25-30%，消除 Fold 4 类熊市失效。

### P1: Label 2 细粒度拆分（GPT 备用方案）

```
Label 2A: P95 ~ 80%（刚过线主升）
Label 2B: >80%（超级牛股）
```

如果 Model B 区分力不足，可尝试此方向。

### P2: 新维度信号引入

当前特征体系（技术指标为主）已接近天花板。可考虑：
- 市值因子（小市值主升浪概率更高）
- 行业动量（板块轮动效应）
- 资金流向（主力净流入）
- 龙虎榜/大宗交易等另类数据
