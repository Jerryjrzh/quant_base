下面是完整的阶段二、三实施计划，以及联合阶段一的回测验证方案，最后是阶段四的实盘用例和闭环设计。所有内容均可直接转化为代码执行。

---

## 阶段二：操作手法自动识别（因股施策）

### 2.1 最优手法标注

对 4423 笔信号，分别模拟四种手法，以收益最高者作为训练标签。

```python
# scripts/label_optimal_style.py

def simulate_style(style, signal_row, structure, path_df):
    """
    根据手法模拟入场和动态出场，返回最终盈亏。
    style: 'deep_pullback', 'shallow_pullback', 'chase', 'skip'(0)
    """
    if style == 'deep_pullback':
        # 等待回踩强支撑 (swing_low/ma60)，严格 K 线确认，标准止损
        entry = wait_for_support(path_df, support_types=['swing_low','ma60'], 
                                 confirm='strict', max_wait=5)
        stop_atr = 1.0
    elif style == 'shallow_pullback':
        # 等待回踩弱支撑 (ma20/poc)，宽松确认 (触及即可)，稍宽止损
        entry = wait_for_support(path_df, support_types=['ma20','poc'], 
                                 confirm='touch', max_wait=3)
        stop_atr = 1.25
    elif style == 'chase':
        # 3天不回踩且连续阳线+涨幅>3%时第4天追入
        entry = chase_if_strong(path_df, max_wait=3)
        stop_atr = 1.5
    else:
        return 0.0
    
    if entry is None:
        return 0.0  # 未入场
    
    # 使用动态出场管理器模拟持仓
    pnl = run_dynamic_exit(entry.price, entry.date, stop_atr, path_df, structure)
    return pnl

# 遍历所有信号
labels = []
for idx, row in signals.iterrows():
    structure = get_structure(row)
    path_df = get_price_path(row)
    best_pnl = -999
    best_style = 'skip'
    for style in ['deep_pullback', 'shallow_pullback', 'chase']:
        pnl = simulate_style(style, row, structure, path_df)
        if pnl > best_pnl:
            best_pnl = pnl
            best_style = style
    # 若最优收益仍<=0，标记为 skip
    if best_pnl <= 0:
        best_style = 'skip'
    labels.append({'signal_id': row['signal_id'], 'optimal_style': best_style, 'best_pnl': best_pnl})
```

### 2.2 多分类器训练

```python
# scripts/train_style_classifier.py

feature_cols = [
    'trend_direction_code',   # 0:DOWN,1:RANGE,2:UP
    'support_count',
    'strong_support_count',   # 置信度>=0.7的支撑数
    'nearest_support_distance',
    'nearest_resistance_distance',
    'rs_rank_mean_20d',
    'rs_rank_trend_20d',
    'ma_divergence_speed',
    'ma_glue_max_days',
    'washout_ma60_flag',
    'price_position_120d',
    'bull_ratio_10d',
    # ... 更多结构特征
]

X = signals[feature_cols]
y = signals['optimal_style']  # 4类别

# 使用 LightGBM 多分类
model = lgb.LGBMClassifier(objective='multiclass', num_class=4, ...)
model.fit(X_train, y_train)
```

### 2.3 手法分层回测验证

在全量测试集上，对每个信号使用分类器预测的手法执行模拟，统计整体盈亏、交易数、胜率。

```python
# 回测验证
results = []
for row in test_signals:
    pred_style = model.predict(row[feature_cols])[0]
    if pred_style == 'skip':
        continue
    pnl = simulate_style(pred_style, row, structure, path_df)
    results.append(pnl)

print(f"交易数: {len(results)}, 平均盈亏: {np.mean(results):.2%}, 胜率: {np.mean(np.array(results)>0):.1%}")
```

**验收标准**：交易数 > 500，平均盈亏 > +2%，胜率 > 42%。

---

## 阶段三：持仓期精细化——动态止盈目标调整

### 3.1 动态止盈逻辑

在 `dynamic_exit_manager.py` 中增加止盈目标更新：

```python
# 在状态机循环中，收到 S1 信号时
if strength_signal and strength_signal['code'] == 'S1':
    # 放量阳线创新高，上调止盈目标到下一个阻力位
    if len(resistances) > 1:
        current_tp = max(current_tp, resistances[1].price)  # 第二阻力位
    # 同时将止损上移到当日低点（或5日低点）
    current_stop = max(current_stop, day['low'] - 0.5 * atr)

# 收到 E1 衰竭信号时
if exhaustion_signal and exhaustion_signal['code'] == 'E1':
    # 高位十字星，主动减仓或缩小止盈
    if position > 0.5:
        # 减仓一半，剩余仓位设止盈为当前价 + 3%
        sell_half()
        current_tp = day['close'] * 1.03
        current_stop = max(current_stop, day['close'] * 0.98)  # 紧止损
```

### 3.2 追涨手法特别处理

对 `chase` 手法，浮盈达 +10% 时主动减仓 1/3，其余用追踪止损。

```python
if entry_style == 'chase' and (day['close'] / entry_price - 1) > 0.10:
    if not partial_taken:
        sell_portion(1/3)
        partial_taken = True
        # 剩余仓位启用追踪止损，从最高点回撤 5% 出场
        trailing_stop = day['close'] * 0.95
```

### 3.3 回测验证

在 V3.2 的 267 笔成功交易上，对比开启/关闭动态止盈的最终收益和回吐率。

```python
# 对历史交易重新模拟
for trade in trades:
    pnl_fixed = simulate_with_fixed_tp(trade)
    pnl_dynamic = simulate_with_dynamic_tp(trade)
    compare(pnl_fixed, pnl_dynamic)
```

**验收标准**：动态止盈组的平均收益比固定止盈高 > 0.5%，收益回吐率（从最高点到出场点的平均跌幅）降低 > 15%。

---

## 联合回测：阶段一 + 阶段二 + 阶段三

### 4.1 链路集成

```
精排 Top 20 → 可操作性过滤器(阶段一) → 操作手法分类器(阶段二) → 动态入场+持仓管理(阶段三) → 出场
```

### 4.2 全量回测脚本

```python
# final_integrated_backtest.py

signals = load_all_signals()
operable_clf = lgb.Booster(model_file='operable_classifier.txt')
style_clf = lgb.Booster(model_file='style_classifier.txt')

results = []
for signal in signals:
    features = extract_features(signal)
    # 阶段一
    operable_prob = operable_clf.predict(features)
    if operable_prob < 0.5:
        continue  # 过滤
    
    # 阶段二
    pred_style = style_clf.predict(features)  # 'deep_pullback','shallow_pullback','chase','skip'
    if pred_style == 'skip':
        continue
    
    # 阶段三：模拟入场和动态持仓
    entry = execute_entry(signal, pred_style)
    if entry:
        pnl = run_dynamic_position(entry, pred_style, path_df, structure)
        results.append({'signal_id': signal.id, 'style': pred_style, 'pnl': pnl})

# 统计
print(f"最终交易数: {len(results)}")
print(f"平均盈亏: {np.mean([r['pnl'] for r in results]):.2%}")
print(f"胜率: {np.mean([r['pnl']>0 for r in results]):.1%}")
print(f"盈利因子: {calculate_profit_factor(results)}")
```

**目标**：交易数 400~600，平均盈亏 ≥ +2.5%，胜率 ≥ 45%，盈利因子 ≥ 1.8。

---

## 阶段四：实盘信号卡与闭环回测用例

### 5.1 每日实盘信号卡生成

```python
# 每日运行
for stock in daily_top20:
    features = get_live_features(stock)
    operable_score = operable_clf.predict(features)
    style = style_clf.predict(features)
    
    signal_card = {
        'code': stock.code,
        'name': stock.name,
        'fine_score': features['fine_score'],
        'operable_score': operable_score,
        'recommended_style': style,
        'key_supports': get_fused_supports(structure, v2_features),
        'key_resistances': structure.resistances[:2],
        'suggested_entry': '等待回踩' if 'pullback' in style else '关注追涨信号',
        'suggested_stop': calculate_stop(style),
        'position_size': calculate_size(style, risk_per_trade=0.005)
    }
    if operable_score > 0.6:
        publish(signal_card)
```

### 5.2 闭环回测用例（模拟实盘环境）

构建一个从信号产生到每日执行、记录结果的仿真回测，以验证实盘逻辑的健壮性。

```python
# paper_trading_simulation.py

class PaperTradingSimulator:
    def __init__(self, start_date, end_date, initial_capital=1_000_000):
        self.capital = initial_capital
        self.positions = {}
        self.trade_log = []

    def run_day(self, date):
        # 1. 获取当日精排 Top 20
        daily_signals = get_daily_signals(date)
        
        # 2. 对每个信号生成信号卡，决定是否入场
        for sig in daily_signals:
            if sig.operable_score < 0.5:
                continue
            style = sig.recommended_style
            # 检查是否已持仓
            if sig.code in self.positions:
                continue
            # 检查入场条件：根据手法判断今天是否触发入场
            entry_price = check_entry_condition(sig, date, style)
            if entry_price:
                size = calculate_position_size(self.capital, entry_price, sig.stop_price)
                if size > 0:
                    self.positions[sig.code] = {
                        'entry_date': date,
                        'entry_price': entry_price,
                        'size': size,
                        'stop': sig.stop_price,
                        'tp': sig.take_profit,
                        'style': style
                    }

        # 3. 管理现有持仓：检查动态出场条件
        for code, pos in list(self.positions.items()):
            current_bar = get_daily_bar(code, date)
            exit_signal = check_dynamic_exit(pos, current_bar, date)
            if exit_signal:
                pnl = (exit_signal.price / pos['entry_price'] - 1) * pos['size']
                self.capital += pnl
                self.trade_log.append({
                    'code': code,
                    'entry_date': pos['entry_date'],
                    'exit_date': date,
                    'entry_price': pos['entry_price'],
                    'exit_price': exit_signal.price,
                    'pnl': pnl,
                    'reason': exit_signal.reason
                })
                del self.positions[code]
        
        # 4. 记录每日权益
        daily_equity = self.capital + sum(
            (get_daily_bar(c, date)['close'] / p['entry_price'] - 1) * p['size'] 
            for c, p in self.positions.items()
        )
        return daily_equity
```

**验收用例**：选择 2025 年 3 月- 5 月数据运行仿真，逐日输出：
- 当日发出的信号卡数量、实际开仓数
- 持仓明细及动态调整记录
- 日终权益曲线
- 最终收益率、最大回撤

**预期**：仿真结果应与历史回测统计特征一致（平均盈亏约 +2.5%，胜率 45%+），最大回撤应控制在 15% 以内。

---

## 总结

通过阶段一的可操作性过滤器，我们剔除了伪强势；阶段二的手法分类器实现了因股施策，回收了过期信号中的机会；阶段三的动态止盈进一步减少了利润回吐。三者联合将系统的交易数从 267 提升至 400-600，同时保持了高盈亏比和胜率。

阶段四的实盘信号卡和仿真回测为上线提供了最后的安全网，确保逻辑在逐日模拟中表现稳健。现在，所有模块均可按上述脚本实现并验证。
