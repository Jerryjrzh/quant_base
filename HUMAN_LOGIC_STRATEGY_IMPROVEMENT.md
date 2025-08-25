# 基于人工分析逻辑的策略改进方案

**创建时间**: 2025-08-24  
**目标**: 策略与人工分析逻辑统一，提升实战效果

---

## 🎯 核心分析逻辑

### 📊 年度机会特征
- **频率**: 一年2-5次真正的见底机会
- **四重指标**: RSI见底 + MACD低位 + KDJ强势 + MA13关键位
- **成交量**: 见底时成交量特别低
- **强势股**: 价格低于MA13回调完会继续上涨

---

## 🚀 改进策略设计

### 策略1: 年度见底机会捕捉策略

```python
def annual_bottom_opportunity_strategy(df, config):
    """年度见底机会捕捉策略 - 一年2-5次精准机会"""
    
    # 1. RSI见底确认
    rsi = indicators.calculate_rsi(df, period=14)
    rsi_bottom = (rsi < 30) & (rsi > rsi.shift(1))
    
    # 2. MACD低位且成交量萎缩
    dif, dea = indicators.calculate_macd(df)
    macd_low = (dif < 0) & (dea < 0) & (abs(dif - dea) < 0.01)
    volume_shrink = df['volume'] < df['volume'].rolling(20).mean() * 0.7
    
    # 3. KDJ强势背离潜力
    k, d, j = indicators.calculate_kdj(df)
    kdj_potential = (k < 20) & (k > d) & (k > k.shift(1))
    
    # 4. 综合见底信号
    bottom_signal = rsi_bottom & macd_low & volume_shrink & kdj_potential
    
    # 5. 年度频率控制（60个交易日间隔）
    return validate_signal_spacing(bottom_signal, min_days=60)
```

### 策略2: 强势股MA13回调策略

```python
def strong_stock_ma13_pullback_strategy(df, config):
    """强势股MA13回调策略 - 专门针对强势股回调机会"""
    
    # 1. 强势股识别
    ma13 = df['close'].rolling(13).mean()
    ma45 = df['close'].rolling(45).mean()
    strong_trend = (ma13 > ma45) & (ma13 > ma13.shift(5))
    
    # 2. 回调到MA13附近
    near_ma13 = (df['close'] >= ma13 * 0.95) & (df['close'] <= ma13 * 1.02)
    
    # 3. 技术指标确认
    rsi = indicators.calculate_rsi(df, period=14)
    rsi_suitable = rsi > 35  # 避免过度超卖
    
    # 4. 成交量萎缩确认
    volume_pullback = df['volume'] < df['volume'].rolling(10).mean()
    
    return strong_trend & near_ma13 & rsi_suitable & volume_pullback
```

### 策略3: 长周期横盘突破策略

```python
def long_term_consolidation_breakout_strategy(df, config):
    """长周期横盘突破策略 - 筹码充足后的稳定强势"""
    
    # 1. 长期横盘识别（60个交易日）
    price_range = df['high'].rolling(60).max() - df['low'].rolling(60).min()
    avg_price = (df['high'].rolling(60).max() + df['low'].rolling(60).min()) / 2
    is_consolidating = (price_range / avg_price) < 0.15
    
    # 2. 突破确认
    recent_high = df['high'].rolling(60).max()
    breakout_signal = df['close'] > recent_high * 1.02
    
    # 3. 成交量放大确认
    volume_surge = df['volume'] > df['volume'].rolling(20).mean() * 1.3
    
    # 4. MACD金叉确认
    dif, dea = indicators.calculate_macd(df)
    macd_positive = dif > dea
    
    return is_consolidating & breakout_signal & volume_surge & macd_positive
```

---

## 📊 多时间周期分析

### 强势股小时线分析
- **强势股**: 使用小时线精准入场
- **一般股票**: 使用日线稳健分析
- **智能切换**: 自动识别股票强弱属性

```python
def get_analysis_timeframe(df):
    """智能选择分析时间周期"""
    if is_strong_stock(df):
        return "hourly"  # 强势股用小时线
    else:
        return "daily"   # 一般股票用日线
```

---

## 🔄 配置文件更新

```json
{
  "年度见底机会策略_v1.0": {
    "name": "年度见底机会策略",
    "description": "基于一年2-5次机会的精准见底捕捉",
    "config": {
      "rsi_oversold": 30,
      "macd_convergence": 0.01,
      "volume_shrink_ratio": 0.7,
      "signal_spacing_days": 60,
      "max_annual_signals": 5
    },
    "risk_level": "low",
    "timeframe": "daily"
  },
  
  "强势股MA13回调策略_v1.0": {
    "name": "强势股MA13回调策略", 
    "description": "强势股在MA13附近的回调机会",
    "config": {
      "ma13_tolerance": 0.05,
      "rsi_min_level": 35,
      "strong_trend_days": 5
    },
    "risk_level": "medium",
    "timeframe": "daily_with_hourly"
  }
}
```

---

## 🎯 回测优化

### 差异化成功标准
- **年度机会策略**: 15%收益目标，持有30-120天
- **强势股回调策略**: 8%收益目标，持有5-45天  
- **横盘突破策略**: 20%收益目标，持有45-180天

---

## 📋 实施计划

### 第一阶段 (1周)
- [ ] 实现三个核心策略
- [ ] 年度频率控制机制
- [ ] 四重指标协同逻辑

### 第二阶段 (3-5天)  
- [ ] 小时线数据接入
- [ ] 强势股智能识别
- [ ] 时间周期自动选择

### 第三阶段 (3-5天)
- [ ] 差异化回测标准
- [ ] 历史数据验证
- [ ] 参数优化调整

---

## 💡 关键改进点

1. **年度频率控制** - 确保一年只捕捉2-5次真正机会
2. **四重指标协同** - RSI、MACD、KDJ、MA综合判断  
3. **强势股特殊处理** - 强势股用小时线，普通股用日线
4. **实战逻辑贴合** - 完全基于您的人工分析经验

这个方案将您的实战交易经验转化为量化策略，保持人工分析的精准性同时提高执行效率。