# V4.6 定价引擎 + 定价 GBM 技术报告

**日期**: 2026-06-05  
**模块**: backtester.py (V4.6 定价) + pricing_gbm.py (定价 GBM v1)  
**状态**: 已集成，待回测验证

---

## 一、V4.6 定价变更总结

### 1.1 变更依据

基于 `price_param_sweeper.py` 对 625 个全周期回测信号的 378 组参数扫描，核心发现:

| 发现 | 扫描器数据 | 当前 V4.5 | 影响 |
|------|:---:|:---:|------|
| 入场价越浅越好 | entry=0% EV=+2.35% | entry≈-5% EV=+0.48% | 成交率 35%→73% |
| 止损要宽 | SL=-10%~-12% 最优 | SL≈-8% | 减少洗盘出局 |
| TP 按趋势分层 | markup: 22-25%, accum: 15-18% | 统一 ATR 倍数 | 让利润充分发展 |
| 追踪止损有害 | off EV=2.35% vs 3%/50% EV=1.38% | MFE≥3% 激活 | 避免过早终止趋势 |
| 持仓 7 天 | 7天 EV=2.35% vs 3天 EV=1.99% | 3 天 | 多数 MFE 在 T3-T7 实现 |

### 1.2 20CM 板块差异化 (基于 508 个 20CM 信号专属扫描)

| 参数 | 10CM (N=117) | 20CM (N=508) | 差异原因 |
|------|:---:|:---:|------|
| **止损** | -10% | **-12%** | 20CM 日内波动大，宽止损避免正常洗盘被止损 |
| **TP (accumulation)** | 15% | 15% | 相同 |
| **TP (markup)** | 22% | **25%** | 20CM markup 阶段利润空间更大 |
| **TP (深渊超跌)** | 18% | **18%** | 相同 |

### 1.3 趋势 × 乖离层 TP 矩阵 (20CM)

| 趋势 \ 乖离层 | 深渊超跌(<-15%) | 空头偏离(-15%~-5%) | 其他 |
|:---:|:---:|:---:|:---:|
| **accumulation** | **18%** (EV=2.69%) | **15%** (EV=1.91%) | 15% |
| **markup** | **25%** (EV=5.67%) | **25%** (EV=3.24%) | 22% |
| **其他** | 15% | 15% | 15% |

### 1.4 代码变更位置

`backend/backtester.py` → `_generate_forward_advice_v4()` 第三阶段

```python
# V4.6 入场: T0 收盘浅挂
entry_price = round(current_price * 0.99, 2)

# V4.6 止损: 20CM=-12%, 10CM=-10%
sl_pct = -0.12 if board_type == '20CM' else -0.10

# V4.6 止盈: 按趋势×乖离层查表
tp_pct = TP_MATRIX[board_type][trend_phase][bias_tier]

# V4.6 风控: 7天持仓, 追踪止损关闭
time_stop_days = 7
trailing_stop_trigger = 0.99  #  effectively disabled
```

---

## 二、定价 GBM v1

### 2.1 模型目标

预测每笔信号应该**浅挂(T0收盘)**还是**深挂(-5%)**:

- **浅挂**: 成交率 81.9%, 成交均 PnL +3.15%, EV +2.57%
- **深挂**: 成交率 25.6%, 成交均 PnL +1.83%, EV +0.47%

目标变量 = `shallow_EV > deep_EV` (含成交率的期望收益对比)

### 2.2 数据与训练

| 维度 | 数值 |
|------|:---:|
| 数据源 | `scheme_c_signals.csv` (全部 20CM) |
| 总信号 | 17,484 |
| 训练集 | 12,773 (2025-01 ~ 2025-12) |
| 测试集 | 4,711 (2026-01 ~ 2026-04) |
| 目标正样本率 | 54.9% (基本平衡) |

### 2.3 特征工程 (21 个特征)

| 特征 | 重要性 | 说明 |
|------|:---:|------|
| **t1_low_drop** | **41.5%** | T+1 最低价相对 T0 收盘的跌幅 |
| **swing** | **19.7%** | 7天总振幅 |
| **t1_close_strength** | 12.6% | T+1 收盘在日内区间的位置 |
| **t1_body** | 9.5% | T+1 实体大小 |
| t1_range | 4.1% | T+1 振幅 |
| t1_open_gap | 3.6% | T+1 开盘跳空幅度 |
| bias_20 | 3.0% | MA20 乖离率 |
| ma_slope | 1.6% | MA20 斜率 |
| v44_bias_tier_* | ~1.0% | 乖离层 one-hot |
| v44_trend_* | ~0.8% | 趋势 one-hot |
| market_env_* | ~0.7% | 大盘环境 one-hot |

**核心洞察**: T+1 日内表现(t1_low_drop, t1_close_strength)是定价决策的最关键因子。如果 T+1 大幅低开(t1_low_drop 很负)，深挂更优；如果 T+1 表现稳健，浅挂更优。

### 2.4 模型性能

| 指标 | 数值 |
|------|:---:|
| F1 | 0.646 |
| Precision | 0.596 |
| Recall | 0.705 |
| AUC | 0.657 |

### 2.5 概率分组验证 (测试集)

| 定价概率 | N | 浅挂 EV | 深挂 EV | 最优选择 EV | 建议 |
|:---:|:---:|:---:|:---:|:---:|------|
| **<0.3** | 628 | +0.57% | +0.47% | +1.52% | 考虑深挂 |
| **0.3~0.7** | 3,067 | +0.85% | +0.39% | +2.54% | 中性，默认浅挂 |
| **>0.7** | 1,016 | **+5.37%** | +0.10% | **+6.99%** | **强烈浅挂** |

高概率组(>0.7)的浅挂 EV 是低概率组的 **9.4 倍**，模型有效区分了入场策略的适用场景。

### 2.6 实盘使用流程

```python
from pricing_gbm import load_pricing_gbm, score_entry_strategy

model, meta = load_pricing_gbm()

# 对候选信号打分
pricing_proba = score_entry_strategy(signal_df, model, meta)

# 根据概率调整入场价
for i, proba in enumerate(pricing_proba):
    if proba > 0.7:
        entry = close_t0 * 0.99    # 浅挂
    elif proba < 0.3:
        entry = close_t0 * 0.95    # 深挂
    else:
        entry = close_t0 * 0.97    # 折中
```

---

## 三、集成文件清单

| 文件 | 变更 | 说明 |
|------|------|------|
| `backend/backtester.py` | 修改 | V4.6 定价引擎 (入场/止损/止盈/时间) |
| `backend/pricing_gbm.py` | 新建 | 定价 GBM 训练 + 打分 + 加载 |
| `backend/walk_forward_tester_s.py` | 修改 | 集成定价 GBM，输出 pricing_proba |
| `backend/price_param_sweeper.py` | 新建 | 参数扫描器 (工具) |
| `data/model/pricing_gbm_v1.pkl` | 新建 | 定价 GBM 模型文件 |
| `data/model/pricing_gbm_v1_meta.json` | 新建 | 模型元数据 |
| `data/result/price_sweep_results.csv` | 新建 | 378 组参数扫描完整结果 |
| `doc/0605_data_dig/price_sweep_report.md` | 新建 | 参数扫描分析报告 |
| `doc/0605_data_dig/v46_pricing_gbm_report.md` | 新建 | 本报告 |

---

## 四、回测验证计划

1. 修改 `walk_forward_tester_s.py` 加载定价 GBM
2. 在 `worker_scan_stock` 中调用 `score_entry_strategy()` 获取 pricing_proba
3. 根据 pricing_proba 动态调整 trigger_buy:
   - proba > 0.7 → trigger_buy = t0_close × 0.99
   - proba < 0.3 → trigger_buy = t0_close × 0.95
   - 其他 → trigger_buy = t0_close × 0.97
4. 同步修改 TP/SL/追踪止损/时间衰减为 V4.6 参数
5. 运行完整回测，对比 V4.5 vs V4.6 的成交率/胜率/累计收益

---

**报告生成时间**: 2026-06-05  
**分析师**: Qoder CLI
