# v5_gt 回测问题诊断与修复方案

**日期**: 2026-06-17
**脚本**: `backend/path_analysis_v5_gt.py`
**状态**: 首次回测完成，需修复后重跑

---

## 一、回测结果摘要

| 指标 | v5 (固定%) | v5_gt (GT原生) | 判定 |
|------|-----------|---------------|------|
| 总信号 | 4403 | 4403 | — |
| 入场成交 | 874 (19.85%) | 92 (2.09%) | **严重不足** |
| 胜率 | 44.74% | 14.13% | **大幅恶化** |
| 盈利因子 | 1.18 | 0.71 | **亏损** |
| 平均盈亏 | +0.98% | -0.95% | **由盈转亏** |
| 最大亏损 | -12.46% | -10.00% | 略好 |

状态分布:
- **disabled**: 2886 (65.5%) — 参数格被禁用
- **observe_expire**: 1425 (32.4%) — 10天内未触及 GT 下轨
- **simulated**: 92 (2.1%) — 实际成交

---

## 二、根因分析

### 根因 1: GT 下轨距离现价过远，不能作为入场触发条件

GT 公式: `GT = (EMA_L - (EMA_H - EMA_L) * K) * offset`

GT 下轨位于 EMA_L 再减去通道宽度 × K，天然远低于现价。实测 T0 时刻各 Zone 的 GT/close 比值:

| Zone | 中位 GT/close | GT 低于 close | 含义 |
|------|-------------|--------------|------|
| abyss_bottom | 1.34 | GT **高于** close 34% | 股价已跌破 GT 支撑 |
| bottom_start | 0.92~1.05 | GT 在 close 附近 | 接近支撑 |
| main_wave | 0.78 | GT 低于 close **22%** | 远离支撑 |
| high_zone | 0.67 | GT 低于 close **33%** | 极远 |

**入场条件** `day_low <= gt_t0` 要求 10 个交易日内股价跌到 GT 下轨:
- main_wave 信号需跌 **22%+** → 几乎不可能
- high_zone 信号需跌 **33%+** → 完全不可能
- 仅 abyss_bottom (GT > close) 较容易触发，但入场后继续下跌概率极高

**典型数据验证** (signal_tags_v5.csv):
```
bj920152 main_wave: close=17.94, GT=11.67 → 需跌 35%
bj920171 high_zone: close=26.11, GT=17.80 → 需跌 32%
bj920249 main_wave: close=15.05, GT=9.42  → 需跌 37%
bj920092 main_wave: close=49.54, GT=32.92 → 需跌 34%
```

### 根因 2: `avg_channel_pct` 计算错误 — 度量了错误的物理量

```python
# step2_gt_param_inference() 中的错误代码:
gt_ratio = (sub['golden_trend_t0'] / sub['last_close']).median()
avg_channel_pct = max(1.0 - gt_ratio, 0.01)  # ← 错误!
```

`1 - gt_ratio` 度量的是 **close 到 GT 的距离百分比**，不是 **EMA_H 到 GT 的通道宽度**。

| Zone | `avg_channel_pct` (错误值) | 实际含义 | 真实通道宽度 (估计) |
|------|--------------------------|---------|-------------------|
| abyss_bottom | 0.01 (被 floor) | GT 在 close 上方 | 5~8% |
| main_wave | 0.18~0.22 | close 到 GT 距离 22% | 5~10% |
| high_zone | 0.26~0.33 | close 到 GT 距离 33% | 8~15% |

后果:
- **TP 被严重高估**: `entry + channel_width * tp_mult` 中 channel_width 实际是 close-GT 距离
  - main_wave: TP = entry + 22% × 2.0 = entry + **44%** (实际应 ~15%)
  - high_zone: TP = entry + 33% × 1.5 = entry + **50%** (实际应 ~20%)
- **SL buffer 被高估**: `channel * 0.5` 给出 9~10% buffer (实际 EMA 通道一半仅 3~5%)
  - 被 cap 到 10% 后，所有 main_wave/high_zone 都用 10% SL

### 根因 3: 65.5% 信号被 disabled 过滤

禁用条件 (继承自 v5):
- `high_trap` 全部禁用 → 1336 笔
- `>20%` DD tier 全部禁用 → ~730 笔
- `n < 10` 的格子 → ~350 笔
- `rebound_gt5_pct < 0.4` → ~470 笔

合计 ~2886 笔 (65.5%)。剩余 1517 笔中仅 92 笔能在 10 天内触及 GT 下轨。

---

## 三、成交信号特征分析

92 笔成交信号的特征:

| 特征 | 数值 | 解读 |
|------|------|------|
| 通道类型 | 100% 宽通道 (>8%) | 仅 GT 远低于 close 的信号才触发 |
| Zone 分布 | abyss_bottom: 73, main_wave: 15, bottom_start: 4 | 集中在 GT > close 或接近的区域 |
| 退出分布 | SL: 84.78%, TP: 2.17%, Expire: 13.04% | 绝大多数止损出局 |
| SL 平均亏损 | -3.84% | SL 触发时亏损可控 (因 GT 入场位本身较低) |
| TP 平均收益 | +21.38% | 极少触发 TP，但触发时收益可观 |
| Expire 平均收益 | +14.13% | 到期未触发 TP/SL 的反而有正收益 |

**关键洞察**: GT 入场后到期收益为正 (14.13%)，说明 GT 下轨附近确实是支撑位。但固定 TP/SL 参数设置不当导致大量止损。

### 典型优势案例 (GT > v5):
| 股票 | Zone | GT PnL | v5 PnL | GT退出 | v5退出 |
|------|------|--------|--------|--------|--------|
| bj920570 | main_wave | +41.81% | -11.96% | expire | sl |
| sz300472 | abyss_bottom | -3.00% | -12.46% | sl | sl |

bj920570: GT 入场位低，SL 缓冲足够，到期获利 +41.81%。v5 入场位高 (-10%)，先触发 SL。
sz300472: 两者都 SL，但 GT 入场位更低 (GT 支撑)，亏损仅 -3% vs v5 的 -12.46%。

### 典型劣势案例 (GT < v5):
| 股票 | Zone | GT PnL | v5 PnL | GT退出 | v5退出 |
|------|------|--------|--------|--------|--------|
| sz002076 | abyss_bottom | -3.00% | +26.36% | sl | tp |
| sz002713 | main_wave | -10.00% | +17.69% | sl | tp |

GT 方案 SL 过早触发 (buffer 太小)，而 v5 方案持有到 TP。

---

## 四、修复方案: 混合策略

核心思路: **v5 入场 + GT 持仓管理**

GT 下轨已被校准验证为精准支撑位 (median deviation 0.12%)，其价值在于:
- 作为 **止损参考** (不应跌破 GT 支撑)
- 作为 **持仓信心** (价格在 GT 上方 = 安全)
- 通道宽度决定 **止盈空间**

### 4.1 入场: 保留 v5 入场触发

```
entry_price = t0_close * (1 + entry_trigger_pct)
```

- abyss_bottom/bottom_start: -3%
- main_wave: median_dd * 0.7, cap [-10%, -3%]
- high_zone: -5%

理由: v5 入场率 19.85%，胜率 44.74%，已被验证合理。

### 4.2 止损: GT 下轨作为止损硬底

```
sl_price = max(
    entry_price * (1 - v5_sl_pct),     # v5 原始 ATR-based SL
    gt_t0                               # GT 支撑位 = 绝对底线
)
```

- 止损不低于 GT 支撑 (GT 是校准过的底部)
- 如果 GT 高于 v5 SL → 用 GT (更保守，减少亏损)
- 如果 GT 低于 v5 SL → 用 v5 SL (避免过宽止损)

### 4.3 止盈: 基于实际 EMA 通道宽度

需要新增存储 `ema_h_t0` (EMA 上轨 T0 值):

```
actual_channel = ema_h_t0 - gt_t0       # 真实 EMA 通道宽度
tp_price = entry_price + actual_channel * tp_mult
```

tp_mult 按 Zone 分级:
- abyss_bottom: 2.5 (深底反弹空间大)
- bottom_start: 2.0
- main_wave: 1.5
- high_zone: 1.2

### 4.4 需要的代码修改

1. **`compute_signal_tags()` / `_compute_gt_on_combined()`**: 新增存储 `ema_h_t0`
2. **`step2_gt_param_inference()`**: 用 `ema_h_t0 - gt_t0` 计算真实通道宽度
3. **`run_single_signal_gt()`**: 
   - 入场: `t0_close * (1 + entry_trigger_pct)` (从 v5 param_lookup)
   - 止损: `max(entry * (1 - sl_pct), gt_t0)`
   - 止盈: `entry + (ema_h_t0 - gt_t0) * tp_mult`
4. **`step3_gt_backtest()`**: 传入 v5 param_lookup 的 entry_trigger_pct

### 4.5 预期效果

| 指标 | v5 原 | v5_gt (修复前) | v5_gt (修复后预期) |
|------|-------|---------------|------------------|
| 入场率 | 19.85% | 2.09% | ~19.85% (同 v5) |
| 止损率 | 43.25% | 84.78% | 降低 (GT 提供支撑底线) |
| 平均亏损 | -11.42% | -3.84% | -5~8% (GT 底线保护) |
| 胜率 | 44.74% | 14.13% | ~45~50% (GT 止损更优) |
| PF | 1.18 | 0.71 | >1.3 (止损改善 + 通道TP) |

---

## 五、附录: 参数矩阵 (当前)

| Zone | DD Tier | n | avg_channel_pct (错误) | sl_buffer | tp_mult | enabled |
|------|---------|---|----------------------|-----------|---------|---------|
| abyss_bottom | 15~20% | 28 | 0.01 | 0.03 | 3.0 | Yes |
| abyss_bottom | 10~15% | 37 | 0.01 | 0.03 | 3.0 | Yes |
| abyss_bottom | 5~10% | 35 | 0.01 | 0.03 | 3.0 | Yes |
| main_wave | 15~20% | 265 | 0.21 | 0.10 | 2.0 | Yes |
| main_wave | 10~15% | 280 | 0.20 | 0.10 | 2.0 | Yes |
| main_wave | 5~10% | 231 | 0.18 | 0.09 | 2.0 | Yes |
| high_zone | 15~20% | 118 | 0.28 | 0.10 | 1.5 | Yes |
| high_zone | 10~15% | 132 | 0.29 | 0.10 | 1.5 | Yes |
| high_zone | 5~10% | 99 | 0.26 | 0.10 | 1.5 | Yes |

所有 high_trap 和 >20% DD 格均被禁用。

---

## 六、下一步

1. 修改 `path_analysis_v5_gt.py`:
   - `_compute_gt_on_combined()` 返回 `ema_h_t0`
   - `step2_gt_param_inference()` 使用真实通道宽度
   - `run_single_signal_gt()` 改为混合入场/止损/止盈逻辑
2. 重新运行回测
3. 对比 v5 vs v5_gt_v2 报告
