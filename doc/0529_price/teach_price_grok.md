**✅ 已完成技术支撑逻辑 Review**

### 问题诊断总结

你提供的案例**非常典型**，暴露了当前支撑位计算的**核心缺陷**：

- **当前价格**：¥91.00
- **技术支撑底**：¥90.88（仅低0.12元，基本无效）
- **趋势**：**DECLINE** + **空头偏离 -8.47%**

**问题本质**：`_calculate_price_targets` 函数在**下跌趋势**中计算出的 `next_support` 过于**贴近当前价**，失去了实际参考意义。

---

### 根源代码分析（`_calculate_price_targets`）

```python
def _calculate_price_targets(df: pd.DataFrame, current_price: float) -> dict:
    recent_data = df.tail(60)                    # 只看最近60天
    ...
    lows = recent_data['low'].rolling(window=5).min()
    
    for i in range(5, len(recent_data)-5):
        if lows.iloc[i] == recent_data['low'].iloc[i]:
            support_levels.append(...)           # 只收集局部低点
            
    next_support = next((level for level in reversed(support_levels) if level < current_price), None)
```

**主要问题**：

1. **时间窗口太短**（60天）+ **局部极值**：在持续下跌中，最近的低点往往就是当前价附近，导致支撑位“假支撑”。
2. **没有趋势过滤**：在 `DECLINE` 阶段，仍然把最近的微小低点当作有效支撑。
3. **没有分位数或结构化支撑**：缺少更稳健的**前高/前低结构**或**斐波那契/均线支撑**。

---

### **优化后的 `_calculate_price_targets`**

请**替换** `backtester.py` 中的这个函数：

```python
def _calculate_price_targets(df: pd.DataFrame, current_price: float, trend_phase: str = 'unknown') -> dict:
    """
    【已优化】更稳健的支撑/阻力计算，特别处理下跌趋势
    """
    try:
        # 1. 多时间尺度数据
        recent_60 = df.tail(60)
        recent_120 = df.tail(120)
        
        support_levels = []
        resistance_levels = []
        
        # ================== 更稳健的局部极值 ==================
        for data in [recent_60, recent_120]:
            # 支撑位：局部低点（窗口扩大）
            lows = data['low'].rolling(window=8, center=True, min_periods=3).min()
            for i in range(5, len(data)-5):
                if abs(data['low'].iloc[i] - lows.iloc[i]) < 0.001:  # 接近局部最低
                    support_levels.append(float(data['low'].iloc[i]))
            
            # 阻力位：局部高点
            highs = data['high'].rolling(window=8, center=True, min_periods=3).max()
            for i in range(5, len(data)-5):
                if abs(data['high'].iloc[i] - highs.iloc[i]) < 0.001:
                    resistance_levels.append(float(data['high'].iloc[i]))
        
        # ================== 关键修复：趋势过滤 ==================
        support_levels = sorted(list(set(support_levels)))
        resistance_levels = sorted(list(set(resistance_levels)), reverse=True)
        
        # 在 DECLINE 趋势下，降低对最近微弱支撑的信任
        if trend_phase in ['decline', 'distribution']:
            # 优先使用更早、更强的历史支撑（过滤最近10天过于接近当前价的假支撑）
            valid_supports = [s for s in support_levels if s < current_price * 0.96]
            if valid_supports:
                next_support = valid_supports[-1]  # 最接近但有明显距离的
            else:
                next_support = None
        else:
            next_support = next((level for level in reversed(support_levels) if level < current_price), None)
        
        next_resistance = next((level for level in resistance_levels if level > current_price), None)
        
        # 兜底：如果支撑太接近当前价，强制下调
        if next_support and (current_price - next_support) / current_price < 0.015:  # 小于1.5%
            # 尝试找更远的支撑
            farther_supports = [s for s in support_levels if s < current_price * 0.96]
            if farther_supports:
                next_support = farther_supports[-1]
        
        return {
            'next_resistance': next_resistance,
            'next_support': next_support,
            'support_levels': support_levels[-5:],   # 返回最近几个供调试
        }
        
    except Exception as e:
        print(f"计算价格目标失败: {e}")
        return {'next_resistance': None, 'next_support': None}
```

---

### 在 `_generate_forward_advice_v4` 中调用时也需同步修改

找到调用位置，改为：

```python
# 5. 计算支撑位和阻力位
price_targets = _calculate_price_targets(df, current_price, trend_phase=trend_phase)
support_level = price_targets.get('next_support')
resistance_level = price_targets.get('next_resistance')
```

---

### 预期效果

- **DECLINE** 趋势下，支撑位会**显著下移**（不再贴着当前价）。
- 挂单伏击价（`entry_price`）会更合理地反映潜在低点。
- 输出中 `技术支撑底` 不再离谱。

---

**请执行以下步骤**：

1. 替换 `_calculate_price_targets` 函数（使用我上面给出的新版本）。
2. 更新调用处的参数（传入 `trend_phase`）。
3. 重新运行测试：

```bash
python3 get_trading_advice_enhanced_1.py sh603023   # 用你刚才的股票测试
```

把**新输出**贴给我，我再看是否需要进一步加强“多重支撑确认”或加入成交量过滤。