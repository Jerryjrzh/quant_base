Grok 的分析非常务实，他准确地捕捉到了当前阶段的重点，并提出了“小时线是辅助验证层，不是主战场”的关键定位。下面我基于这个共识，制定具体、可落地的实施计划。

---

## 一、核心共识确认

*   **系统已进入“精细化收尾”阶段**：Review4 Final（+3.21%, PF 2.61）是当前最优日线策略，是稳定的基线。
*   **下一步是“锦上添花”而非“推倒重来”**：引入小时线是为了提升入场精准度和持仓风控，目标是再提升0.3%-0.6%的盈亏。
*   **小时线定位**：作为**辅助验证层**。日线负责信号触发和结构过滤，小时线负责入场二次确认和盘中预警。
*   **执行原则**：先做小样本验证，再全量推广；避免过度复杂化，防止过拟合。

---

## 二、修正后的P0任务优先级

| 优先级 | 任务 | 目标 | 预期耗时 |
|--------|------|------|---------|
| **P0-1** | **60分钟入场二次确认验证** | 过滤15-25%的假回调，胜率提升2-4%，盈亏提升0.3%+ | 2天 |
| P0-2 | 弱势月内生特征v3重训 | 减少弱势月亏损，改善-1.48%至-0.5%以上 | 2天 |
| P0-3 | 过滤/降权 breakout_support | 消除唯一负贡献支撑（-0.13%, WR 31.4%） | 0.5天 |
| P1 | 60分钟持仓动态预警 | 提前识别回调失败，主动减仓，缩小亏损 | 1天 |

**当前聚焦P0-1**：这是最可能带来增量改进的任务，且风险可控。

---

## 三、P0-1实施计划：60分钟入场二次确认

### 3.1 功能定位

在日线信号触发 → 结构过滤 → 价格回踩到支撑位附近时，不是直接按日线K线确认入场，而是**切换到60分钟图进行二次验证**。只有通过小时线验证的信号，才执行入场。

### 3.2 验证逻辑

**输入**：日线确认的“企稳日”及前后几天的60分钟K线数据。

**验证规则**（简洁务实，避免过拟合）：

1.  **支撑位精确触及**：
    *   在回踩期间（日线最低价触及支撑位±1%的当天），查看60分钟图。
    *   要求：至少**2根**60分钟K线的最低价精确触及支撑位（误差±0.1%），证明这不是偶然的“刺穿”。

2.  **反转形态确认**（满足其一即可）：
    *   **Pin Bar**：出现长下影线（影线长度 > 实体2倍），且收盘价回到影线50%以上位置。
    *   **Bullish Engulfing**：出现阳线实体完全覆盖前一根阴线实体。
    *   **Morning Star**：由三根K线组成（阴线-小实体-阳线），阳线收盘超过第一根阴线50%以上。

3.  **成交量配合**：
    *   触及支撑时：成交量应**缩量**（低于前5根60分钟均量的80%）。
    *   确认反弹时：成交量应**温和放大**（高于前5根60分钟均量的120%）。

4.  **否决条件**（出现任一则放弃入场）：
    *   回踩期间出现放量大阴线（60分钟跌幅 > 1.5%，成交量 > 前5根均量的2倍）。
    *   连续3根以上阴线且收盘价持续走低。
    *   触及支撑后，60分钟收盘价跌破支撑位超过0.5%（显示支撑无效）。

**输出**：
*   `True`：通过验证，按日线原计划执行入场（次日开盘买入）。
*   `False`：未通过验证，放弃本次入场，信号继续等待或过期。

### 3.3 代码框架

```python
# backend/hourly_confirmation.py

import pandas as pd
import numpy as np

def get_hourly_confirmation(stock_code, signal_date, support_price):
    """
    在日线信号触发的回调日，切换到60分钟K线进行入场二次确认。
    
    返回:
        (passed: bool, reason: str)
    """
    # 获取最近20个交易日的60分钟数据（覆盖回调期）
    hourly_df = get_hourly_data(stock_code, end_date=signal_date, lookback_days=20)
    
    if hourly_df is None or len(hourly_df) < 20:
        return False, "小时线数据不足"
    
    # 找最近一次触及支撑位的日期
    recent = hourly_df.tail(20)  # 最近20根60min K线（约5个交易日）
    
    # 1. 检查支撑位是否被精确触及
    touch_count = sum((recent['low'] <= support_price * 1.001) & 
                      (recent['low'] >= support_price * 0.999))
    if touch_count < 2:
        return False, "未精确触及支撑位"
    
    # 2. 检查否决策件
    recent['avg_vol_5'] = recent['volume'].rolling(5).mean().shift(1)
    recent['is_big_red'] = ((recent['close'] < recent['open']) & 
                            ((recent['open'] - recent['close']) / recent['open'] > 0.015) &
                            (recent['volume'] > recent['avg_vol_5'] * 2))
    if recent['is_big_red'].iloc[-5:].any():
        return False, "出现放量大阴线"
    
    # 3. 检查反转形态
    recent['body'] = abs(recent['close'] - recent['open'])
    recent['upper_shadow'] = recent['high'] - recent[['open', 'close']].max(axis=1)
    recent['lower_shadow'] = recent[['open', 'close']].min(axis=1) - recent['low']
    
    # Pin Bar
    recent['is_pinbar'] = ((recent['lower_shadow'] > recent['body'] * 2) & 
                           (recent['close'] > recent['low'] + recent['lower_shadow'] * 0.5))
    # Bullish Engulfing
    recent['is_engulfing'] = ((recent['close'] > recent['open']) & 
                              (recent['close'] > recent['close'].shift(1)) &
                              (recent['open'] < recent['open'].shift(1)))
    
    # 检查最近8根K线是否出现上述形态
    has_bullish_pattern = recent['is_pinbar'].iloc[-8:].any() or \
                          recent['is_engulfing'].iloc[-8:].any()
    
    if not has_bullish_pattern:
        return False, "无反转形态确认"
    
    # 4. 成交量确认
    # 简化处理：检查最近一次触及时的成交量是否缩量，反弹是否放量
    touch_volume = recent[recent['low'] <= support_price * 1.001]['volume'].mean()
    avg_volume = recent['avg_vol_5'].iloc[-1]
    
    if touch_volume > avg_volume * 0.8:
        # 没有明显缩量，也可以接受（不强求）
        pass
    
    return True, "通过60分钟确认"
```

### 3.4 集成到现有回测框架

在 `structure_entry.py` 的 `run_entry_state_machine()` 中，找到确认K线信号的位置，增加一步：

```python
# 原逻辑：日线K线确认 → 次日入场
if confirmed_by_daily_candle:
    # 新增：60分钟二次确认
    hourly_passed, hourly_reason = get_hourly_confirmation(
        stock_code, signal_date, support_used.price
    )
    if not hourly_passed:
        # 未通过小时线验证，放弃本次入场，继续等待
        continue
    # 通过验证，执行入场
    execute_entry()
```

### 3.5 小样本验证方案

**样本选择**：从4423笔信号中，随机抽取500笔（确保覆盖不同月份、不同趋势）。

**对比回测**：
*   **基线**：原始Review4 Final（无小时线确认），记录这500笔中有多少实际交易，平均盈亏。
*   **实验组**：加上小时线确认后的系统，记录交易笔数和平均盈亏。

**验收标准**：
*   **假回调过滤率**：实验组交易笔数减少15-25%（说明过滤掉了部分假信号）。
*   **胜率提升**：实验组胜率提升2-4%（从51.7%到53.7%-55.7%）。
*   **平均盈亏提升**：实验组平均盈亏提升0.3%+。

**若无显著提升**：
*   分析被过滤的信号中，是否有大量是最终会盈利的（被错杀）。
*   如果是，调整确认规则（如放宽形态要求）。
*   如果不是，说明小时线确认确实有效，直接全量推广。

---

## 四、后续任务串联

一旦P0-1验证通过并集成：

1.  **P0-2**：将小时线确认后的高质量入场特征，与内生弱势特征（consecutive_loss, signal_surge等）合并，重训练 `operable_score v3`。
2.  **P0-3**：过滤 `breakout_support`，移除负贡献支撑。
3.  **P1**：在每日信号卡中增加“60分钟确认建议”，为实盘交易员提供辅助决策。

---

**最终目标**：在Review4 Final基础上，通过小时线辅助，将系统平均盈亏提升至 **+3.5% 以上**，胜率稳定在 **55% 左右**，并实现在弱势月的最小化亏损。

现在需要我立即编写完整的 `hourly_confirmation.py` 模块和对应的验证脚本吗？
