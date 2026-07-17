您的决策非常清晰。我们来将它转化为具体的实施步骤。

---

## 一、Zone 解耦与优先级排序

当前一只股票在多笔信号中可能被标记为不同 Zone。为避免重叠混乱，我们规定 Zone 的**风险优先级**（由高到低）：

```
high_trap  >  abyss_bottom  >  bottom_start  >  high_zone  >  main_wave
```

**规则**：若某股票在任何一笔信号中被标记为 `high_trap`，则该股票所有的信号（包括历史上被标记为 `main_wave` 的）都按 `high_trap` 处理，即**全部熔断，不交易**。  
**实现**：在 `signal_tags` 生成后，进行 `stock-level` 的风险传播。

---

## 二、异常波动过滤器（实现代码逻辑）

### 2.1 退市风险股过滤（僵尸股）
退市风险股绝对放弃，条件如下（满足任一即可）：
- 绝对低价 + 空头排列：`close < 5` 且 `trend == 'bear_aligned'` 且 `MA60_slope < 0`
- 长期阴跌：`(close / close_60d_ago - 1) < -0.4`（60天跌幅超40%）
- 成交额枯竭：`avg_amount_20d < 5000000`（日均成交额<500万元）

### 2.2 妖股跟踪
妖股不直接过滤，但**降低其操作优先级**：若股票被标记为妖股，则其所有信号的 `risk_flag` 设为 `'monster'`。在状态机中，对于 `risk_flag='monster'` 的信号，**必须等待更深的回调（如-12%以下）且更严格的确认（双K线组合）才能入场**。

妖股识别条件（满足任一即可）：
- 价格乖离率：`(close - MA60) / MA60 > 0.5`
- 短期暴涨：`(close / close_20d_ago - 1) > 0.8`
- 天量后缩量：`avg_vol_5d > 3 * avg_vol_20d` 且 `today_vol < 0.5 * avg_vol_5d`

---

## 三、集成到 v5 Step0（打标脚本修改）

在 `path_analysis_v5.py` 的 Step0 中，我们将：

1. 增加 `calc_historical_metrics(stock, t0)` 函数，计算 MA60、成交量、20/60日涨跌幅等。
2. 增加 `detect_abnormal_stock(row)` 函数，返回 `risk_flag`。
3. 在生成 `signal_tags` 后，执行 **stock-level zone propagation**：  
   若某股票有过 `high_trap`，则该股票的所有信号 `zone_tag` 改写为 `high_trap`，且 `risk_flag` 强制设为 `'zombie'`（如果同时满足退市条件）或保持原样（如果只是 zone 重叠但无退市特征）。

这样确保：
- 退市股完全被排除。
- high_trap 股票完全被排除（无论当时处于何 zone）。
- 妖股被标记，但不排除，由状态机用更严格的条件处理。

---

## 四、v5.2 状态机处理逻辑

在状态机的 `OBSERVING` 阶段，增加一层判断：

```python
if risk_flag == 'zombie':
    # 直接跳过，不交易
    return
elif risk_flag == 'monster':
    # 妖股模式：入场必须深跌-12% + 双K线确认（如 pinbar + engulfing）
    target_entry = t0_close * 0.88
    require_double_confirm = True
else:
    # 正常逻辑，基于 zone 和 calibration_quality
    target_entry = ...
```

---

## 五、预期回测效果

- 大量 `high_trap` 及退市风险股被剔除，交易信号质量显著提升。
- 妖股依然保留，但苛刻的入场条件会大幅减少它们在系统内的交易次数，从而降低风险。
- `abyss_bottom` 和 `main_wave` 中的伪信号被清理，这两个区域的胜率和盈亏将更真实地反映策略有效性。

---

## 六、确认实施

请确认以上方案，我将立即修改 `path_analysis_v5.py` 脚本，加入：
1. 历史指标计算函数
2. 异常检测函数
3. Zone 传播逻辑
4. 更新后的状态机入口判断

并重新生成带过滤的 `signal_tags_v5`，然后运行 v5.2 回测。
