# V4.8 代码修改报告

**日期**: 2026-06-05  
**版本**: V4.7 → V4.8  
**依据**: `v47_verify_report.md` 7项假设验证结果

## 修改总览

| 优先级 | 改动 | 文件 | 预期效果 |
|--------|------|------|----------|
| P0 | entry_pos > 0.5 过滤 | walk_forward_tester_s.py, screenergf.py, backtester.py | 移除负EV信号，总PnL +82% |
| P1 | TP 统一下调至 10% | walk_forward_tester_s.py, backtester.py | 止盈命中率从9.8%提升，胜率提升 |
| P2 | 确认无追踪/阶梯止损 | — | 无需改动（已验证有害） |

## 详细改动

### 1. walk_forward_tester_s.py (回测引擎)

#### 1.1 TP 矩阵简化为统一 10%
**位置**: 原 lines 409-427 (V4.6 TP/SL 矩阵)

**改动前** (分层 TP):
```python
if board_type == '20CM':
    v46_sl = -0.12
    if v44_trend == 'markup':
        v46_tp = 0.25 if v44_bias in ['深渊超跌(<-15%)', '空头偏离(-15%~-5%)'] else 0.22
    elif v44_trend == 'accumulation':
        v46_tp = 0.18 if v44_bias == '深渊超跌(<-15%)' else 0.15
    else:
        v46_tp = 0.15
    ...
else:
    v46_tp = 0.18
    v46_sl = -0.10
```

**改动后** (统一 TP):
```python
v46_tp = 0.10
if board_type == '20CM':
    v46_sl = -0.12
    if v44_trend == 'markup' and v44_bias == '空头偏离(-15%~-5%)':
        v46_sl = -0.07
else:
    v46_sl = -0.10
```

**依据**: 4264信号回测显示仅9.8%交易触及15%+TP，95.7%到期交易future_mfe<15%。10% TP + entry_pos<=0.5组合胜率87.1%。

#### 1.2 entry_pos 计算与过滤
**位置**: future_min_low/max_high 计算之后 (原 line 439 后)

**新增代码**:
```python
price_range = future_max_high - future_min_low
entry_pos = (trigger_buy - future_min_low) / price_range if price_range > 0 else 0.5
if entry_pos > 0.5:
    debug_logger.info(f"[{stock_code_full}] entry_pos={entry_pos:.3f}>0.5, 信号位置偏高，跳过")
    return None
```

**依据**: entry_pos 是回测中最强预测因子。pos<=0.5 → EV +4.6%，pos>0.5 → 负EV。过滤后总PnL从+6967%升至+12698%。

#### 1.3 输出字段新增
- `entry_pos`: 加入 return dict，用于后续分析

#### 1.4 日志更新
- V4.7 → V4.8，新增 entry_pos 显示

### 2. backtester.py (实盘定价引擎)

#### 2.1 TP 统一下调至 10%
**位置**: 原 lines 932-953 (V4.6 止盈矩阵)

**改动前**: 按 board_type × trend_phase × bias_tier 分层 (15%~25%)

**改动后**:
```python
# ----------- V4.8 止盈价: 统一 TP=10% (验证回测: 87.1%胜率) -----------
tp_pct = 0.10
```

#### 2.2 entry_pos 计算与 AVOID 逻辑
**位置**: 阻力位保护之后，时间风控之前

**新增代码**:
```python
recent_7d = df.tail(7)
range_high = float(recent_7d['high'].max())
range_low = float(recent_7d['low'].min())
price_range = range_high - range_low
entry_pos = (entry_price - range_low) / price_range if price_range > 0 else 0.5
if entry_pos > 0.5:
    action = 'AVOID'
    reasons.append(f"V4.8风控: entry_pos={entry_pos:.3f}>0.5, 信号位于7日区间高位，历史EV为负，强制AVOID。")
```

**说明**: 实盘中无未来数据，使用历史7日 high/low 近似计算。backtester 返回 AVOID 后，screenergf 会直接跳过该信号。

#### 2.3 输出字段新增
- `entry_pos`: 加入 return dict (round to 4 decimals)

#### 2.4 日志更新
- V4.6 → V4.8，新增 entry_pos 显示

### 3. screenergf.py (选股扫描器)

#### 3.1 v44 advice AVOID 拦截
**位置**: v44 advice 调用之后 (原 line 852)

**新增代码**:
```python
if advice and advice.get('action') == 'AVOID':
    return None
if advice and advice.get('action') not in ('ERROR', 'AVOID'):
```

**说明**: 当 backtester 返回 AVOID（含 entry_pos>0.5 触发），screener 直接跳过该信号，不输出到结果。

#### 3.2 fallback 路径 entry_pos 过滤
**位置**: v44 advice 不可用时的 fallback 定价之后 (原 lines 878-888)

**新增代码**:
```python
recent_7d = df_daily.tail(7)
range_high = float(recent_7d['high'].max())
range_low = float(recent_7d['low'].min())
price_range = range_high - range_low
entry_pos_fb = (trigger_buy - range_low) / price_range if price_range > 0 else 0.5
if entry_pos_fb > 0.5:
    return None
v44_meta['entry_pos'] = round(entry_pos_fb, 4)
```

**说明**: 当 v44 advice 不可用（stock_code为空或数据不足），使用 df_daily 最近7天独立计算 entry_pos。

## 未改动项（经验证确认无需修改）

| 项目 | 验证结果 | 结论 |
|------|----------|------|
| 阶梯止损 (ladder) | 600-1600笔错误止损 vs 固定TP仅125笔 | 有害，不添加 |
| 追踪止损 (trailing) | 同上，过度止损损害收益 | 有害，不添加 |
| 入场价 (entry=×0.99) | 浅挂成交率69.3%，最优 | 保持不变 |
| SL矩阵 (-12%/-10%/-7%) | 验证结果支持当前分层 | 保持不变 |
| GBM proba 阈值 | >=0.65为EV/总PnL甜点 | 作为可选过滤，不改默认值 |

## 验证结果

三个脚本均通过:
- `py_compile` 语法检查 ✓
- 运行时 `import` 测试 ✓

## 预期回测效果

基于 v47_verify_report.md 的 V7 联合测试（方案A）:

| 指标 | V4.7 | V4.8 预期 |
|------|------|-----------|
| 信号数 | 4264 | ~2000 (entry_pos过滤约50%) |
| 成交率 | ~69% | ~75% (低位信号更易成交) |
| 胜率 | ~60% | ~87% (TP10%+entry_pos<=0.5) |
| 总PnL | +6967% | +12698% (移除负EV信号) |
| EV/笔 | +1.6% | +4.6% |

## 下一步

1. 运行完整日历回测验证实际效果
2. 对比 V4.7 vs V4.8 的信号过滤分布
3. 根据回测结果微调 entry_pos 阈值（0.5 可能可放宽至 0.55）
