# 入场/出场价格参数回测工具 — 实施计划

## 目标

构建一个基于 `future_7d_path` 的参数化价格模拟器，无需重跑完整日历回测，直接在现有 CSV 上扫描入场/出场参数组合，找到最优配置。

## 数据基础

`full_calendar_trades.csv` 已包含:
- `future_7d_path`: 7天逐日 H/L 百分比路径 (相对于 T0 收盘)
- `trigger_buy`: 当前 V4.5 挂单价
- `v44_trend`, `v44_bias_tier`: 分组维度
- `gbm_proba`: GBM 概率

## 核心思路

`future_7d_path` 的百分比基于 T0 收盘价。通过估算 T0 收盘 ≈ trigger_buy / 0.95，可以:
1. 将任意入场折扣映射到同一坐标系
2. 判断每天 low 是否触及入场价 (成交判定)
3. 模拟入场后的 TP/SL/追踪止损/时间衰减

## 新建文件

`backend/price_param_sweeper.py` — 单文件，约 300 行

## 函数设计

### 1. `parse_path(path_str)` 
解析 `"H:+1.0%/L:-2.5% -> ..."` → list of (H, L) float tuples

### 2. `estimate_t0_close(trigger_buy)`
`trigger_buy / 0.95` (V4.5 典型入场折扣约 5%)

### 3. `simulate_trade(path, t0_close, entry_discount, tp_pct, sl_pct, trailing_trigger, trailing_keep, time_stop_days)`
- entry = t0_close × (1 + entry_discount)
- 逐日遍历:
  - daily_low/high → 转为相对 entry 的盈亏比
  - **悲观优先**: 先检查止损再检查止盈
  - **追踪止损**: 浮盈 ≥ trailing_trigger → stop 上移至 peak × (1 - trailing_giveback)
  - **时间衰减**: day ≥ time_stop_days 且 MFE < 1% → 以 (H+L)/2 近似收盘平仓
- 返回: {pnl, filled, status, mfe, mae, hold_days}

### 4. `run_sweep(df, param_grid)`
- 遍历参数组合
- 对每个组合遍历所有 625 信号
- 计算: 成交率, 胜率, 平均PnL, EV, Sharpe, 最大回撤

### 5. `compare_with_actual(df, best_params)`
- 用最优参数模拟 vs 当前实际交易结果
- 对比: 成交率, 胜率, 平均收益, 累计收益

### 6. `analyze_by_group(results, df)`
按 v44_trend / v44_bias_tier / board_type 分组输出最优参数

## 参数网格

```python
entry_discounts: [0, -0.01, -0.02, -0.03, -0.04, -0.05, -0.06, -0.08, -0.10]
tp_pcts:         [0.08, 0.10, 0.12, 0.15, 0.18, 0.22, 0.25]
sl_pcts:         [-0.04, -0.05, -0.06, -0.07, -0.08, -0.10]
trailing:        [off, (3%, 40%), (5%, 40%)]
time_stop:       [3, 5, 7]
```

全量 = 9×7×6×3×3 = 6804 组合 × 625 信号 ≈ 425万次迭代 (~10秒)

为效率考虑，分两阶段:
- **Phase 1**: 固定 trailing=off, time_stop=7, 扫 entry×TP×SL (378组合) → 找入场+TP/SL最优
- **Phase 2**: 固定 Phase 1 最优 entry/TP/SL, 扫 trailing×time_stop (9组合) → 精细化出场

## 输出

1. 控制台表格: Top 20 参数组合 (按 EV 排序)
2. 与当前实际结果对比表
3. 按板块/趋势/乖离分层的最优参数
4. 保存完整结果到 `data/result/price_sweep_results.csv`

## 使用方式

```bash
cd backend
python3 price_param_sweeper.py
```

一行命令出结果，无需修改其他文件。
