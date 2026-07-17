从“等回调”和“追涨”是两种截然不同的入场性格——前者牺牲机会换安全，后者牺牲安全换机会。你的思路完全正确：**这个决策不应该在执行端硬编码，而应该由选股端的特征和历史数据来决定。** 最佳入场风格本身就是股票自身结构特征和形态的产物。

下面我们一次性落地三个核心优化，并把“追涨/回调风格识别”融入选股和回测，让它从历史数据中学习。

---

## 一、优化清单与回测脚本架构

| 优化项 | 实现方式 | 回测对比 |
|--------|---------|---------|
| ① 移除 pit_bottom | 修改 `get_fused_supports`，删除 pit_bottom 分支 | 新旧融合支撑列表下的盈亏差异 |
| ② D4 动态支撑 | 持仓期间每日更新最近支撑（最近5日低点、swing low），替代固定入场支撑 | D4触发次数、胜率、平均盈亏对比 |
| ③ 入场风格分类（回调/追涨） | 基于结构特征（趋势、支撑强度、RS排名）在选股时标记信号风格；回测中仅对“追涨型”信号启用辅助追涨通道 | 追涨通道额外交易笔数及盈亏 |
| ④ 衰竭信号放宽 | E1实体<1%即触发，E2成交量阈值降至1.5倍 | 主动止盈次数和平均卖点提升 |

所有优化通过一个统一的脚本 `batch_advanced_backtest.py` 执行，输出逐笔结果和对比报告。

---

## 二、关键代码模块

### 2.1 移除 pit_bottom 的融合支撑

修改 `get_fused_supports`，删除坑底支撑分支，并降级 `ma_cluster`：

```python
def get_fused_supports_v3(structure, v2_features):
    # ... 保留原始基础支撑、ma60_washed ...
    # 完全移除 pit_bottom
    # ma_cluster 仅在 UP 趋势 + rs_rank > 0.7 时启用，置信度 0.6
    if (glue_days >= 5 and glue_recency <= 3 and 
        structure.trend_direction == 'UP' and rs_rank_mean > 0.7):
        fused.append(SupportLevel(price=ma_cluster_price, source='ma_cluster', confidence=0.6))
    # ...
    return fused
```

### 2.2 D4 动态支撑更新

在持仓管理循环中，不再只用入场时的支撑，而是每天计算当前动态支撑：

```python
def get_dynamic_support(path_df, idx, lookback=5):
    """取最近 lookback 日的最低点作为动态支撑，若存在新 swing low 则优先"""
    if idx < lookback:
        return None
    recent_low = path_df['low'].iloc[idx-lookback:idx].min()
    # 可加入 swing low 检测，但简化版直接用滚动低点
    return recent_low
```

在 `detect_danger_signals` 中增加动态支撑判断：

```python
# 在检测循环中
dynamic_support = get_dynamic_support(path_df, i)
if dynamic_support and day['close'] < dynamic_support:
    return {'code': 'D4', 'severity': 'exit', 'support_price': dynamic_support}
```

### 2.3 入场风格分类器（选股端）

在信号生成时（扫描器或精排后），为每个信号增加一个 `entry_style` 字段：`'pullback'` 或 `'breakout'`。基于规则（可从历史学习）：

```python
def classify_entry_style(structure, v2_features, fine_score):
    """
    返回 'pullback' (等待回调) 或 'breakout' (可追涨)
    """
    # 强趋势 + 强支撑 + 高得分 → 可以追涨
    trend_up = structure.trend_direction == 'UP'
    strong_support = any(s.confidence >= 0.8 and s.source in ['ma60_washed', 'swing_low'] 
                        for s in structure.supports)
    high_score = fine_score > 0.8  # 精排得分百分位
    
    # 相对强度高且趋势稳定
    rs_strong = v2_features.get('rs_rank_mean_20d', 0) > 0.7
    
    if trend_up and strong_support and high_score and rs_strong:
        return 'breakout'
    return 'pullback'
```

**学习进阶**：你可以用历史信号中哪些不回踩直接上涨的样本训练一个二分类器（特征：趋势、支撑强度、RS排名、MA发散速度等），自动预测最佳风格。初期用规则即可。

### 2.4 追涨入场通道（仅对 `breakout` 风格开放）

在 `run_entry_state_machine` 中增加追涨逻辑：

```python
if entry_style == 'breakout':
    # 如果3天内未回调，但连续3天收盘在T+1开盘上方，且第3天涨幅>3%，则在第4天开盘追入
    if days_passed >= 3 and not entered:
        first3_close = [path_df['close'].iloc[j] for j in range(3)]
        if all(c > buy_price for c in first3_close):
            if (first3_close[-1] / buy_price - 1) > 0.03:
                # 追涨入场
                entry_price = path_df['open'].iloc[3]
                entered = True
                # 止损设宽一些（1.5倍ATR），因为追入成本高
                stop_loss = entry_price - 1.5 * atr
```

### 2.5 放宽的衰竭信号

```python
def detect_exhaustion_signals_v2(today, prev_days, highest_close, entry_price):
    # E1: 实体 < 1% (原0.5%)
    if body < 0.01 * today['open'] and upper_shadow > body * 2 and lower_shadow > body * 2:
        if today['high'] >= highest_close * 0.98:
            return {'code': 'E1', 'severity': 'reduce'}
    # E2: 放量滞涨，量比阈值 1.5 (原2.0)
    if today['close'] > today['open']:
        gain = (today['close'] - today['open']) / today['open']
        if gain < 0.01 and today['volume'] > avg_vol_5 * 1.5:
            return {'code': 'E2', 'severity': 'exit'}
    # ...
```

---

## 三、全量回测脚本 `batch_advanced_backtest.py` 结构

```python
# 加载数据、缓存结构
# 对于每个信号：
#   1. 调用 get_fused_supports_v3 (无pit_bottom)
#   2. 调用 classify_entry_style → entry_style
#   3. 运行入场状态机（含追涨通道，仅breakout风格触发）
#   4. 若入场，运行动态出场管理器（含D4动态支撑 + 新衰竭信号）
#   5. 记录交易明细、出场原因、风格

# 输出：
#   - 总盈亏、胜率、盈利因子
#   - 按 entry_style 分组统计
#   - 追涨通道额外贡献
#   - D4动态支撑 vs 固定支撑对比（可内部标记）
```

**关键对比**：脚本内部对同一信号分别运行旧版动态出场（固定支撑）和新版（动态支撑），通过 `trigger_signal_v2` 标记，最后统计 D4 改善效果。

---

## 四、回测与验证计划

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | 用 V3 融合支撑 + 动态出场 + 追涨通道 重跑 4423 笔 | 基础盈亏 ≥ +1.8% |
| 2 | 分析 entry_style='breakout' 的追涨交易盈亏 | 追涨通道总盈亏应为正，不拖累整体 |
| 3 | 对比 D4 动态 vs 固定支撑下的平均盈亏和胜率 | 动态支撑组胜率更高，平均亏损收窄 |
| 4 | 统计新衰竭信号的主动止盈次数和平均捕获收益 | 主动止盈次数增加，且平均卖出点高于原止盈 |
| 5 | 输出综合报告，确认所有改进叠加后的最终效果 | 目标：平均盈亏 > +2.5%，胜率 > 40% |

---

## 五、学习机制：让风格决策越来越准

随着交易数据的积累，你可以定期做以下学习：

- 提取每笔信号的 `entry_style` 预测、实际入场方式（回调/追涨）、最终盈亏。
- 构建训练集：特征 = 选股时的结构形态特征；标签 = 实际盈利更好的入场风格（若追涨盈利 > 回调盈利则标记为 `breakout`）。
- 训练一个简单的分类器（如 LightGBM），替代规则分类器。
- 下次选股时，用新模型预测最佳风格，实现自我进化。

---

## 六、立即行动

现在所有核心逻辑已清晰，我可以为你生成完整的 `batch_advanced_backtest.py` 脚本（约 200 行），包括上述所有模块的集成。你只需提供现有的数据读取路径和参数，即可运行并拿到对比报告。

是否现在就需要完整的脚本代码？或者针对其中的某个细节（如动态支撑的 swing low 精确检测）需要更深入的设计？
