代码修改已完成，以下是每个修改点的具体实现。修改后的系统将严格区分“形态在选股端的作用”和“形态在入场端的含义”，不再盲目融合。

---

## 一、修改 `get_fused_supports`：降低 ma_glue 置信度，只在上升趋势且相对强度高时启用

```python
# market_structure.py 中 get_fused_supports() 的修改部分

if v2_features:
    glue_days = v2_features.get('ma_glue_max_days', 0)
    glue_recency = v2_features.get('ma_glue_recency', 999)
    rs_rank_mean = v2_features.get('rs_rank_mean_20d', 0.5)
    trend_up = (structure.trend_direction == 'UP')
    
    # 均线束粘合支撑：方向不确定，降低置信度并严格限制使用条件
    if glue_days >= 5 and glue_recency <= 3:
        # 只在上升趋势 + 相对强度排名靠前时才视为有效支撑
        if trend_up and rs_rank_mean > 0.6:
            confidence = 0.6  # 中等置信度
        else:
            confidence = 0.4  # 低置信度，不会优先使用
        # 计算均线束价格（MA20/MA60均值），仅当价格低于当前价时加入
        ma_cluster_price = None
        if structure.ma20 and structure.ma60:
            ma_cluster_price = (structure.ma20 + structure.ma60) / 2
        elif structure.ma20:
            ma_cluster_price = structure.ma20
        elif structure.ma60:
            ma_cluster_price = structure.ma60
        if ma_cluster_price and ma_cluster_price < structure.current_price:
            fused.append(SupportLevel(
                price=round(ma_cluster_price, 2),
                source='ma_cluster',
                confidence=round(confidence, 2),
                tests=glue_days
            ))
```

**变化**：  
- `ma_cluster` 置信度从 0.85 降至 0.4~0.6，且仅在 `UP` 趋势 + 相对强度排名 > 0.6 时才给 0.6，否则 0.4（基本不会被优先使用）。  
- 其他融合项（洗盘、坑底）保持不变。

---

## 二、修改 `check_pullback_entry`：移除放宽入场，统一严格 K 线确认

```python
# structure_entry.py 中 check_pullback_entry_fused() 的简化版本

def check_pullback_entry(day_data, fused_supports, v2_features=None):
    if not fused_supports:
        return None
    
    low, close, open_ = day_data['low'], day_data['close'], day_data['open']
    high = day_data.get('high', close)
    
    # 寻找触及的支撑位（优先高置信度）
    touched_support = None
    for sup in fused_supports:
        if low <= sup.price * 1.015:
            touched_support = sup
            break
    if touched_support is None:
        return None
    
    # 严格 K 线确认：阳线实体 > 30% 或 长下影线
    bullish_candle = (close > open_) and (close - open_) > 0.3 * (high - low + 0.001)
    long_lower_shadow = (min(open_, close) - low) > 1.5 * (high - max(open_, close) + 0.001)
    
    if not (bullish_candle or long_lower_shadow):
        return None
    
    # 额外条件：收盘价必须在支撑位上方
    if close <= touched_support.price:
        return None
    
    return {
        'type': 'pullback',
        'entry_date': day_data['date'] + pd.Timedelta(days=1),
        'entry_price': None,  # 次日开盘执行
        'support_used': touched_support,
        'confidence': touched_support.confidence
    }
```

**变化**：  
- 删除了 `relaxed_confident` 相关的所有逻辑。  
- 所有入场都必须满足严格的阳线实体或长下影线条件，且收盘价在支撑上方。  
- `v2_features` 仅用于后续止损策略区分（在调用时保留参数）。

---

## 三、新增 `set_initial_stop_by_pattern`：按形态差异化止损

```python
# structure_exit.py 中新增函数

def set_initial_stop_by_pattern(entry_price, support_used, atr, v2_features, max_stop_loss_pct=0.05):
    """
    根据入场形态类型差异化止损：
    - 洗盘形态 (washout)：支撑验证可靠，用 0.75×ATR 紧止损
    - 坑底反弹 (pit_rebound)：假反弹风险高，用 1.25×ATR 宽止损
    - 其他：标准 1.0×ATR
    """
    hard_stop = entry_price * (1 - max_stop_loss_pct)
    
    if support_used is None or support_used.price >= entry_price:
        return hard_stop
    
    # 判断形态类型
    is_washout = v2_features.get('washout_ma60_flag', 0) == 1 if v2_features else False
    is_pit_rebound = v2_features.get('price_rebound_from_pit', 0) > 0.03 if v2_features else False
    
    if is_washout:
        atr_mult = 0.75
    elif is_pit_rebound:
        atr_mult = 1.25
    else:
        atr_mult = 1.0
    
    buffer = atr_mult * atr
    structural_stop = support_used.price - buffer
    final_stop = max(structural_stop, hard_stop)
    return min(final_stop, entry_price * 0.999)
```

**变化**：  
- 用形态类型决定 ATR 倍数，而非置信度。  
- 洗盘：止损紧，盈亏比高。  
- 坑底反弹：止损宽，容忍假反弹。

---

## 四、修改 `batch_fused_backtest.py`：接入新止损函数，保持参数

在模拟交易循环中，将原来的 `set_initial_stop` 替换为：

```python
# 原代码：
stop_loss = set_initial_stop(entry_price, support_used, atr, max_stop_loss_pct=0.05)

# 修改为：
stop_loss = set_initial_stop_by_pattern(entry_price, support_used, atr, v2_features, max_stop_loss_pct=0.05)
```

同时确保 `max_wait_days=3` 和 `max_stop_loss_pct=0.05` 参数已设置。

---

## 五、全量回测计划

已部署以上修改，即将在 4423 笔信号上重跑 `batch_fused_backtest.py`，产出三组对比数据：

- **A 组（旧融合版）**：放宽入场 + 置信度止损（已跑）  
- **B 组（修正融合版）**：严格入场 + 形态差异化止损  
- **C 组（原始未融合）**：无 V2 特征，标准入场止损（基线）

**验收标准（修正版 vs 旧融合版）**：  
- 胜率从 35.1% 回升至 **40% 以上**  
- 止损率从 64.9% 下降至 **55% 以下**  
- 平均盈亏保持 **+0.3% 以上**，盈利因子 > 1.1  
- washout 组胜率 **> 40%**，pit_rebound 组胜率 **> 35%**，且 ma_glue 组因置信度低被自然过滤，不再产生大量亏损交易。

修改完成后立即启动批量回测，预计耗时约 40 秒。结果将更新到任务状态报告。
