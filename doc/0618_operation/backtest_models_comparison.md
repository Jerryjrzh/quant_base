# 回测操作模型对比: v5 基线 vs v5_gt MA增强

**日期**: 2026-06-18

---

## 一、两套模型概览

| 维度 | v5 基线 (Zone-Based) | v5_gt (MA-Enhanced) |
|------|---------------------|---------------------|
| 文件 | `path_analysis_v5.py` | `path_analysis_v5_gt.py` |
| Zone分类 | position_ratio (120日高低分位) | position_ratio + ma_zone (双轨) |
| 入场方式 | 固定回调 (entry_trigger -3%~-10%) | 浅挂单 (t0_close*0.99) + MA支撑调整 |
| 观察窗口 | 10个交易日 | 5个交易日 |
| TP/SL | ATR动态 (tp_pct/sl_pct) | 板块固定% + MA压力/支撑调整 |
| 退出机制 | tp / sl / expire (3种) | tp / sl / ma_support_break / circuit_break / form_break / time_decay / expire (7种) |
| 防御机制 | 无 | 跳空低开 / 无承接 / 熔断 / 形态破坏 |
| 过滤机制 | high_zone + enabled矩阵 | support_score + ma_zone + enabled全开 |

---

## 二、v5 基线模型 — 详细逻辑

### 2.1 Zone 分类 (position_ratio)

```python
position_ratio = (close - low120) / (high120 - low120)
```

| Zone | 条件 | 含义 |
|------|------|------|
| abyss_bottom | ratio < 0.10 | 极底部 |
| bottom_start | 0.10 ≤ ratio < 0.25 | 底部起步 |
| main_wave | 0.25 ≤ ratio < 0.60 | 主升浪区间 |
| high_zone | 0.60 ≤ ratio < 0.80 | 高位区 |
| high_trap | ratio ≥ 0.80 | 高位陷阱 (直接跳过) |

### 2.2 参数矩阵 (Zone × DD Tier)

按 `(zone_tag, dd_tier)` 交叉分组，每组推断:

```python
entry_trigger = median_rebound * clip_factor   # 典型: -3% ~ -10%
tp_pct = median_rebound * 0.6                  # 取反弹的60%
sl_pct = avg_atr * 1.5                         # 1.5倍ATR
```

约束:
- `tp_pct >= sl_pct * 1.5` (保证 R:R ≥ 1.5:1)
- `entry_trigger` 限定在 [-10%, -3%]

### 2.3 入场逻辑

```
T0: 信号日
target_entry = t0_close * (1 + entry_trigger)

T+0 ~ T+9 (10日观察窗口):
  每日检测:
    if day_low <= target_entry:
      → 成交, entry_price = target_entry
      → 设置 tp_price = entry * (1 + tp_pct)
      → 设置 sl_price = entry * (1 - sl_pct)

  若10日内未触及:
    → observe_expire (观察到期)
```

特点:
- 入场价 = 目标价 (无滑点模拟)
- 不区分开盘价/最低价
- 无跳空防御

### 2.4 持仓逻辑

```
state = HOLDING (最多22个交易日):

每日检测 (顺序):
  1. day_high >= tp_price → 止盈, pnl = +tp_pct
  2. day_low <= sl_price  → 止损, pnl = -sl_pct

到期 (T+22):
  → expire, pnl = last_close / entry - 1
```

### 2.5 退出类型汇总

| 退出类型 | 触发条件 | 平均PnL |
|---------|---------|---------|
| tp | day_high ≥ tp_price | +16.41% |
| sl | day_low ≤ sl_price | -11.21% |
| expire | 持仓到期 (T+22) | -0.90% |

### 2.6 回测结果

```
总信号: 4403
成交: 874 (19.85%)
胜率: 44.85%
PF: 1.21
中位收益: -3.34%
```

退出分布: tp(37%) + sl(43%) + expire(20%)

**核心问题**: 43% 的交易止损出局，止损幅度大 (-11.21%)，拉低整体收益。

---

## 三、v5_gt MA增强模型 — 详细逻辑

### 3.1 双重 Zone 分类

保留旧 position_ratio zone，新增 ma_zone:

```python
# MA 距离
dist_ma30  = (close - ma30) / ma30
dist_ma90  = (close - ma90) / ma90
dist_ma150 = (close - ma150) / ma150
dist_ma240 = (close - ma240) / ma240

# 支撑评分 (0~7)
support_score = 0
close > ma30  → +1
close > ma90  → +1
close > ma150 → +1
close > ma240 → +1
slope(ma30) > 0  → +1
slope(ma90) > 0  → +1
slope(ma150) > 0 → +1
```

| MA Zone | 条件 | 含义 |
|---------|------|------|
| bottom | close < MA90 且 < MA240 | 深熊/超跌 |
| transition | close > MA90 但 < MA240 | 趋势转换 |
| main_trend | close > MA90, MA150; slope > 0 | 主升浪 |
| extended | close > 所有MA; dist_ma90 > 25% | 超买/高位 |
| high_risk | close > MA; slope 转负 | 趋势衰竭 |

### 3.2 入场前过滤

```
信号进入 → 逐层过滤:

1. support_score < 3 → low_support_skip
   (价格低于大多数MA，深熊不做)

2. ma_zone ∈ {bottom, extended, high_risk} → ma_zone_skip
   (结构性不利区域不做)

3. enabled 参数矩阵 → 全部打开 (True)
   (不再按 zone × dd_tier 门控)
```

### 3.3 MA 价格结构计算

```python
# 从 daily_pre 计算 4 条 MA
ma30  = close.rolling(30).mean()[-1]
ma90  = close.rolling(90).mean()[-1]
ma150 = close.rolling(150).mean()[-1]
ma240 = close.rolling(240).mean()[-1]

# 分类
supports    = [ma for ma in levels if ma < t0_close]  # 价格下方
resistances = [ma for ma in levels if ma >= t0_close]  # 价格上方

nearest_support  = max(supports)     # 最近支撑 (最高且低于价格)
next_resistance  = min(resistances)  # 最近压力 (最低且高于价格)
```

### 3.4 入场逻辑

```
T0: 信号日, last_close = daily_pre.close[-1]

# --- 入场价计算 ---
base_entry = t0_close * 0.99                    # 浅挂1%
ma_entry   = nearest_support * 1.02             # MA支撑上方2%
entry_price = min(base_entry, ma_entry)          # 取更保守的

# --- TP/SL 计算 ---
board = get_board_params(stock_code):
  10CM (主板):   tp=+10%, sl=-10%
  20CM (创/科):  tp=+12~15%, sl=-7~-8%
  30CM (北交所): tp=+18%, sl=-10%

tp_price = entry * (1 + tp_pct)
sl_price = entry * (1 + sl_pct)

# MA 调整
if nearest_support:
  ma_sl = nearest_support * 0.97        # 支撑下方3%
  sl_price = max(sl_price, ma_sl)        # 取更高的 (更紧)

if next_resistance:
  ma_tp = next_resistance * 0.995        # 压力下方0.5%
  if ma_tp < tp_price and ma_tp > entry * 1.03:
    tp_price = ma_tp                     # 压力近时提前止盈

# --- 5日挂单等待 ---
T+0 ~ T+4:
  每日检测:

  [防御1] 跳空低开
    if day_open <= entry * 0.965:
      → 放弃本日 (跳空太大不追)

  [成交判断]
    if day_low <= entry_price:
      [防御2] 无承接
        if day_close < day_low * 1.005:
          → 放弃 (收盘在最低价附近，承接不足)

      → 成交
        actual_entry = min(entry_price, day_open * 0.995)
        重新计算 tp_price, sl_price

      → 当日 TP/SL 检测
        if day_high >= tp_price → tp 退出
        if day_low <= sl_price  → sl 退出

  5日内未触及:
    → order_timeout (挂单超时)
```

### 3.5 持仓逻辑

```
state = HOLDING (最多22个交易日):

每日检测 (顺序):

  [1] 熔断检测 (20CM板块)
    code ∈ {688,689,300,920}:
      if (day_low - entry) / entry <= -8%:
        exit_p = min(day_open, entry * 0.92)
        → circuit_break 退出

  [2] 止盈
    if day_high >= tp_price:
      exit_p = max(day_open, tp_price)
      → tp 退出

  [3] 止损
    if day_low <= sl_price:
      exit_p = min(day_open, sl_price)
      → sl 退出

  [4] MA 支撑破位
    if nearest_support and day_close < nearest_support * 0.98:
      → ma_support_break 退出 (收盘价跌破支撑MA 2%)

  [5] 形态破坏
    body_drop = (day_close - day_open) / day_open
    20CM: threshold = -9%
    10CM: threshold = -6.5%
    if body_drop <= threshold:
      → form_break 退出 (收盘斩仓)

  [6] 时间衰减
    holding_days >= 7  且 mfe < -5%  → time_decay
    holding_days >= 10 且 mfe < +1%  → time_decay
    holding_days >= 15               → expire (强制平仓)

到期 (T+22):
  → expire, pnl = last_close / entry - 1
```

### 3.6 退出类型汇总

| 退出类型 | 触发条件 | avg PnL | 设计意图 |
|---------|---------|---------|---------|
| tp | day_high ≥ tp_price | +15.81% | 到达目标盈利 |
| sl | day_low ≤ sl_price | -9.10% | 硬止损 (极少触发 3.88%) |
| ma_support_break | close < support_MA * 0.98 | -4.72% | MA结构破位，提前撤退 |
| circuit_break | 20CM 日内跌 ≥ 8% | -8.14% | 防闪崩 |
| form_break | 日实体跌幅超限 | -3.55% | 大阴线斩仓 |
| time_decay | 持仓7-15日 + MFE差 | ~0% | 不浪费时间 |
| expire | 持仓到期 | +2.79% | 到期结算 |

### 3.7 回测结果

```
总信号: 4403
成交: 258 (5.86%)
胜率: 43.41%
PF: 1.95
中位收益: -2.94%
```

退出分布: tp(38%) + ma_support_break(38%) + circuit_break(12%) + expire(7%) + sl(4%) + form_break(0.4%)

---

## 四、关键差异对比

### 4.1 入场机制

| 维度 | v5 基线 | v5_gt MA增强 |
|------|---------|-------------|
| 入场价 | `close * (1 + trigger)` | `min(close*0.99, support_MA*1.02)` |
| 观察窗口 | 10 天 | 5 天 |
| 入场率 | 19.85% | 5.86% |
| 跳空防御 | 无 | 开盘 ≤ 入场*0.965 → 放弃 |
| 承接防御 | 无 | 收盘 < 最低*1.005 → 放弃 |
| 价格锚 | 固定百分比回调 | MA支撑结构 |

**分析**: MA模型入场更保守 (入场率低14pp)，但跳空+承接两道防御有效过滤了弱势入场。

### 4.2 持仓管理

| 维度 | v5 基线 | v5_gt MA增强 |
|------|---------|-------------|
| 止损 | 固定 sl_pct | max(固定SL, 支撑MA*0.97) |
| 止盈 | 固定 tp_pct | min(固定TP, 压力MA*0.995) |
| MA支撑破位 | 无 | close < support_MA * 0.98 → 退出 |
| 熔断 | 无 | 20CM 日内跌≥8% → 退出 |
| 形态破坏 | 无 | 大阴线(实体跌>6.5%/9%) → 斩仓 |
| 时间衰减 | 无 | T+7 MFE<-5%, T+10 MFE<1%, T+15 强平 |

**分析**: MA模型退出路径丰富(7种 vs 3种)，核心改善是 `ma_support_break` 替代了硬止损:
- 旧 SL: avg -11.21%, 占比 43%
- 新 MA破位: avg -4.72%, 占比 38%

### 4.3 过滤体系

| 层级 | v5 基线 | v5_gt MA增强 |
|------|---------|-------------|
| Zone | high_trap 跳过 | 全部开放 |
| 参数矩阵 | enabled 按 zone×dd | 全部 True |
| MA 支撑分 | 无 | score<3 跳过 |
| MA 区域 | 无 | bottom/extended/high_risk 跳过 |
| 冷却期 | 无 | 同股5日 |

### 4.4 绩效对比

| 指标 | v5 基线 | v5_gt MA增强 | 差异 |
|------|---------|-------------|------|
| 成交数 | 874 | 258 | -70% |
| 入场率 | 19.85% | 5.86% | -14pp |
| 胜率 | 44.85% | 43.41% | -1.4pp |
| PF | 1.21 | 1.95 | +0.75 |
| 中位收益 | -3.34% | -2.94% | +0.4pp |
| 最大亏损 | -12.46% | -10.00% | 改善 |
| SL 占比 | 43% | 4% | -39pp |

---

## 五、当前瓶颈分析

### 5.1 order_timeout 问题

```
4403 信号 → 3730 (84.7%) order_timeout
```

挂单价 `t0_close * 0.99` 在5天内极少被触及。

参数倒推报告确认:
```
ideal_gap_max 中位 = 88%  → 理想入场需距GT 88%
最佳 span(3) gap = 50%   → 实际仅 50%
差距 = 38pp
```

GT 作为价格锚已失效，但 MA 入场逻辑 (`nearest_support * 1.02`) 提供了替代锚点。

### 5.2 两种改进方向

**A. 放宽挂单价**
```python
# 当前
entry_price = t0_close * 0.99    # 1%回调

# 改进
entry_price = t0_close * 0.995   # 0.5%回调
# 或
entry_price = t0_close * 0.998   # 0.2%回调
```
预期: 入场率从 5.9% 提升到 15-25%

**B. MA 支撑直接入场**
```python
# 不再用浅挂单等待
# 当 close 接近 MA 支撑时直接市价入场
if abs(day_close - nearest_support) / nearest_support < 0.02:
    → 市价入场 (消除 order_timeout)
```
预期: 入场率提升，但需要更精确的 MA 距离判断

---

## 六、代码结构

```
path_analysis_v5.py (基线)
├── compute_signal_tags()      → 信号标签 (含 MA 距离模型)
├── step2_cross_tab()          → 参数矩阵 (zone × dd_tier)
├── run_single_signal()        → 回测引擎 (3种退出)
└── generate_comparison_report()

path_analysis_v5_gt.py (MA增强)
├── step2_gt_param_inference() → 参数矩阵 (全部 enabled=True)
├── _analyze_ideal_params()    → 参数倒推分析
├── run_single_signal_gt()     → 回测引擎 (7种退出 + MA体系)
│   ├── _get_board_params()    → 板块 TP/SL
│   ├── MA 支撑/压力计算        → nearest_support / next_resistance
│   └── 入场/持仓/出场          → MA 增强逻辑
└── generate_gt_comparison_report()
    ├── 六B: MA Zone 分析
    ├── 六C: 支撑评分 vs 胜率
    └── 六D: 旧Zone vs 新MA Zone 对比
```
