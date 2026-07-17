已经为你实现了三个核心融合函数。这些代码可以直接嵌入到现有项目中，将选股端的形态判断与执行端的压力/支撑判断彻底缝合。

---

## 一、数据结构扩展

首先，在 `market_structure.py` 中增加一个带置信度的 `SupportLevel` 数据类（如果还没有）和融合函数：

```python
# market_structure.py 中新增或修改

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class SupportLevel:
    price: float
    source: str            # 'swing_low', 'ma20', 'ma60', 'poc', 'ma_cluster', 'ma60_washed', 'pit_bottom'
    confidence: float = 0.5  # 0-1，越高支撑越可靠
    tests: int = 0           # 被测试次数
```

---

## 二、get_fused_supports 实现

```python
def get_fused_supports(structure: 'MarketStructure', 
                       v2_features: Optional[Dict[str, Any]] = None) -> List[SupportLevel]:
    """
    将 market_structure 的支撑位与 V2 形态特征融合，生成带权重的支撑位列表。
    
    Args:
        structure: 由 analyze_market_structure 返回的结构对象
        v2_features: V2 特征字典，应包含类似 ma_glue_max_days, washout_ma60_flag 等字段
        
    Returns:
        按置信度从高到低排序的支撑位列表
    """
    fused = []
    
    # ---- 1. 基础支撑位（来自 market_structure） ----
    # 假设 structure.supports 已经是 List[SupportLevel] 或类似结构
    for level in structure.supports:
        # 基础置信度：基于测试次数，最多 5 次满分，转换成 0.2-1.0
        base_conf = min(level.tests / 5.0, 1.0) if hasattr(level, 'tests') else 0.5
        # 来源类型微调
        if level.source == 'swing_low':
            base_conf = max(base_conf, 0.4)  # 摆动低点有一定参考价值
        elif level.source in ['ma20', 'ma60']:
            base_conf = max(base_conf, 0.3)  # 均线支撑单独使用时较弱
        
        fused.append(SupportLevel(
            price=level.price,
            source=level.source,
            confidence=round(base_conf, 2),
            tests=getattr(level, 'tests', 0)
        ))
    
    # ---- 2. 均线束粘合支撑（来自 V2 形态判断） ----
    if v2_features:
        glue_days = v2_features.get('ma_glue_max_days', 0)
        glue_recency = v2_features.get('ma_glue_recency', 999)
        if glue_days >= 5 and glue_recency <= 3:
            # 刚完成均线束粘合并开始发散，均线密集区是强支撑
            # 近似取 MA20 和 MA60 的均值作为均线束价格中枢
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
                    confidence=0.85,   # 高置信度
                    tests=glue_days   # 粘合天数作为强度参考
                ))
        
        # ---- 3. MA60 洗盘支撑（破位后收回，支撑极强） ----
        washout_flag = v2_features.get('washout_ma60_flag', 0)
        if washout_flag == 1 and structure.ma60 and structure.ma60 < structure.current_price:
            fused.append(SupportLevel(
                price=structure.ma60,
                source='ma60_washed',
                confidence=0.9,
                tests=2   # 经历了一次假破位收回，相当于两次测试
            ))
        
        # ---- 4. 黄金坑底部支撑（从坑底反弹） ----
        # price_rebound_from_pit 是 V1 特征，但在 V2 中可能保留
        rebound = v2_features.get('price_rebound_from_pit', 0)
        pit_depth = v2_features.get('pit_depth', 0)  # 可能需要计算，此处假设存在
        if rebound > 0 and pit_depth:
            pit_price = structure.current_price * (1 - pit_depth)
            if pit_price < structure.current_price:
                # 坑底被确认，是强支撑
                fused.append(SupportLevel(
                    price=round(pit_price, 2),
                    source='pit_bottom',
                    confidence=0.8,
                    tests=1
                ))
        
        # ---- 5. 相对强度趋势确认支撑可信度 ----
        rs_rank_mean = v2_features.get('rs_rank_mean_20d', 0.5)
        rs_trend = v2_features.get('rs_rank_trend_20d', 0)
        # 如果排名持续高位且趋势向上，所有支撑位的置信度可以上调
        if rs_rank_mean > 0.7 and rs_trend > 0:
            for level in fused:
                level.confidence = min(level.confidence * 1.1, 1.0)  # 提升10%
    
    # 去重：相同价格来源保留置信度最高的
    seen = {}
    unique_fused = []
    for level in fused:
        key = (round(level.price, 2), level.source)
        if key not in seen or level.confidence > seen[key].confidence:
            seen[key] = level
    unique_fused = list(seen.values())
    
    # 按置信度降序排列
    unique_fused.sort(key=lambda x: x.confidence, reverse=True)
    return unique_fused
```

---

## 三、修改后的 check_pullback_entry

在 `structure_entry.py` 中修改，使其接收融合支撑位列表并优先使用高置信度支撑：

```python
def check_pullback_entry(day_data: Dict, 
                         fused_supports: List[SupportLevel],
                         v2_features: Optional[Dict] = None) -> Optional[Dict]:
    """
    检查是否触发回调入场。优先回踩高置信度支撑位，且企稳信号可根据形态放宽。
    
    Args:
        day_data: 当日数据 {'open', 'high', 'low', 'close', 'volume', 'date'}
        fused_supports: 融合支撑位列表（已按置信度排序）
        v2_features: 可选，形态特征，用于调整确认要求
        
    Returns:
        入场信号字典或 None
    """
    if not fused_supports:
        return None
    
    low = day_data['low']
    close = day_data['close']
    open_ = day_data['open']
    
    # 检查是否触及任意支撑位的 ±1.5% 范围
    touched_support = None
    for sup in fused_supports:
        if low <= sup.price * 1.015:  # 进入支撑区域
            touched_support = sup
            break
    
    if touched_support is None:
        return None
    
    # ---- 企稳确认，可根据支撑置信度和形态调整 ----
    # 基础要求：收阳且收盘在支撑上方，或长下影线
    bullish_close = close > open_ and close > touched_support.price
    long_shadow = (min(open_, close) - low) > (high := day_data.get('high', close)) - max(open_, close) * 1.5 if 'high' in day_data else False
    
    # 动态调整：如果支撑置信度 >= 0.8，且存在多头形态，放宽对 K 线要求
    confident_support = touched_support.confidence >= 0.8
    bull_morphology = False
    if v2_features:
        bull_ratio = v2_features.get('bull_ratio_10d', 0)
        streak_bull = v2_features.get('streak_max_bull', 0)
        if bull_ratio >= 0.6 and streak_bull >= 3:
            bull_morphology = True
    
    entry_allowed = False
    if confident_support and bull_morphology:
        # 高置信支撑 + 多头形态：只需收盘在支撑上方即可，不强求阳线
        if close > touched_support.price:
            entry_allowed = True
    else:
        # 标准要求：阳线或长下影
        if bullish_close or long_shadow:
            entry_allowed = True
    
    if not entry_allowed:
        return None
    
    # 返回入场信号，次日开盘执行
    return {
        'type': 'pullback',
        'entry_date': day_data['date'] + pd.Timedelta(days=1),  # 次日
        'entry_price': None,  # 具体执行时会用次日开盘价
        'support_used': touched_support,
        'confidence': touched_support.confidence
    }
```

---

## 四、修改后的 set_initial_stop

在 `structure_exit.py` 中修改，根据融合支撑位的置信度动态调整止损缓冲：

```python
def set_initial_stop(entry_price: float, 
                     support_used: Optional[SupportLevel], 
                     atr: float,
                     max_stop_loss_pct: float = 0.05) -> float:
    """
    基于融合支撑位设置初始止损。
    高置信度支撑 → 更窄的缓冲（因为支撑更可靠）。
    
    Args:
        entry_price: 实际入场价格
        support_used: 触发入场的那个支撑位对象（可能包含 confidence）
        atr: 平均真实波幅
        max_stop_loss_pct: 硬性最大亏损百分比 (默认5%)
        
    Returns:
        止损价
    """
    # 硬性保护止损（不允许超过最大亏损）
    hard_stop = entry_price * (1 - max_stop_loss_pct)
    
    if support_used is None:
        return hard_stop
    
    # 如果支撑位在入场价上方（不应该发生，但以防万一），直接用硬止损
    if support_used.price >= entry_price:
        return hard_stop
    
    # 根据置信度选择 ATR 倍数
    confidence = getattr(support_used, 'confidence', 0.5)
    if confidence >= 0.85:
        atr_mult = 0.5   # 极高置信度，窄缓冲
    elif confidence >= 0.7:
        atr_mult = 0.75
    else:
        atr_mult = 1.0   # 标准缓冲
    
    # 基于支撑位的理论止损
    buffer = atr_mult * atr
    structural_stop = support_used.price - buffer
    
    # 取两者中较高的（更紧的止损），但不能低于硬止损
    final_stop = max(structural_stop, hard_stop)
    
    # 确保止损确实在入场价下方
    return min(final_stop, entry_price * 0.999)
```

---

## 五、如何集成到现有回测脚本

在你的 `batch_structure_backtest.py` 的 `process_single_signal` 函数中，需要做以下调整：

1. **加载 V2 特征**  
   从 `super_trend_training_data_v2.csv` 中按 `(stock_code, t0_date)` 匹配每个信号的 V2 特征。可以预先构建一个字典缓存。

2. **替换支撑位生成**  
   将原来直接使用 `structure.supports` 的地方改为：
   ```python
   v2_features = precomputed_v2_features.get((stock, t0), {})
   fused_supports = get_fused_supports(structure, v2_features)
   ```

3. **修改入场检查**  
   在 `run_entry_state_machine` 中调用新的 `check_pullback_entry(day_data, fused_supports, v2_features)`。

4. **修改止损设置**  
   在入场成功时，将触发入场的 `support_used` 传入 `set_initial_stop(entry_price, support_used, atr, max_stop_loss_pct=0.05)`。

5. **重新全量回测**  
   应用参数 `max_wait_days=3`, `max_stop_loss_pct=5%`，运行全部 4423 笔信号，得到新的统计数据。

---

## 六、预期验证效果

| 指标 | 当前值 (未融合) | 融合后预期 |
|------|----------------|------------|
| 平均盈亏 | +0.21% | **+1.5% ~ +2.5%** |
| 胜率 | 44.4% | **48% ~ 52%** |
| 止损出场率 | 54% | **38% ~ 42%** |
| 中位数盈亏 | -7.77% | **-4% ~ -2%** |

**逻辑**：  
- 高置信度支撑（如洗盘后的 MA60、均线束下沿）不再被当作普通支撑，止损缓冲缩小，止盈目标不变 → 盈亏比提高。  
- 多头形态信号在回踩时更容易获得入场确认，减少“假回调”被拒之门外（但不会大幅增加假入场，因为形态信号本身质量较高）。  
- 无形态信号则维持原标准，不会恶化。

如果需要，我可以接着写出完整的**融合版本 batch_structure_backtest.py 的修改代码**，包括 V2 特征预加载和状态机调整。
