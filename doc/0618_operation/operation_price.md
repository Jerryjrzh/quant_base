你的这个观察，其实比很多量化里常见的「120日价格分位」更接近真实交易者的行为逻辑。

但需要把它从“看图经验”转化成“可量化特征”。

---

# 一、为什么 MA 会成为支撑/压力

本质上不是 MA 有魔法。

而是：

```text
大量资金的持仓成本
+
趋势交易者的观察窗口
+
自我强化
```

例如：

```text
MA60
≈ 3个月成本区

MA120
≈ 半年成本区

MA240
≈ 年线成本区
```

很多机构：

```text
跌破年线减仓
回踩半年线加仓
```

于是：

```text
价格 ↔ MA
```

自然形成支撑压力。

---

# 二、你观察到的现象是合理的

你说：

> 高点对应的 MA 是压力位，到低点支撑位还会和这个 MA 形成干涉

实际上很多主升浪都是这样：

```text
上涨

↑

MA30

↑

MA60

↑

MA90
```

然后：

```text
价格远离MA90

偏离过大

↓

回归

↓

回踩MA90
```

例如：

```text
价格 = 150

MA90 = 120

偏离 = +25%
```

市场会倾向于：

```text
价格回调
MA继续上移

最终相遇
```

这就是：

```text
Mean Reversion
均值回归
```

---

# 三、比 Position_Ratio 更好的位置定义

我反而建议：

不要：

```python
position_ratio
=
(close-low120)
/
(high120-low120)
```

改成：

```python
MA Distance Model
```

---

例如：

```python
dist_ma90 =
(close-ma90)
/ ma90

dist_ma150 =
(close-ma150)
/ ma150

dist_ma240 =
(close-ma240)
/ ma240
```

得到：

```text
+40%

+20%

+5%
```

这种特征。

---

# 四、支撑压力其实是多MA共振

你列的：

```text
MA7
MA13
MA30
MA45
MA90
MA150
MA240
```

非常有价值。

因为：

```text
短期
中期
长期
```

都覆盖了。

---

我会这样分层：

### 第一层

趋势层

```python
MA30
MA90
MA240
```

判断：

```text
牛市
震荡
熊市
```

---

### 第二层

结构层

```python
MA7
MA13
MA30
```

判断：

```text
短期回调
加速
衰竭
```

---

### 第三层

成本层

```python
MA90
MA150
MA240
```

判断：

```text
机构成本区
```

---

# 五、你说的“干涉”可以量化

例如：

```python
gap90 =
(close-ma90)
/ ma90
```

---

定义：

```python
gap90 > 0.25
```

说明：

```text
远离MA90

超买
```

---

定义：

```python
-0.05 < gap90 < 0.05
```

说明：

```text
正在测试MA90
```

---

定义：

```python
gap90 < -0.15
```

说明：

```text
跌穿长期均线
```

---

这比：

```python
position_ratio=0.2
```

信息量更大。

---

# 六、我认为最有价值的是 MA 共振评分

例如：

```python
support_score = 0
```

---

价格高于均线：

```python
close > ma30
+1

close > ma90
+1

close > ma150
+1

close > ma240
+1
```

---

均线斜率向上：

```python
slope(ma30) > 0
+1

slope(ma90) > 0
+1

slope(ma150) > 0
+1
```

---

最终：

```python
score
=
0~7
```

例如：

```text
0~2
深熊

3~4
震荡

5~7
主升浪
```

---

# 七、对于你的回调策略，最重要的是“回调目标位”

你现在的方案：

```python
主升浪

等 -8%~12%
```

实际上不够稳定。

更好的方法：

```python
目标位 =
最近支撑MA
```

例如：

当前：

```text
价格 100

MA30 95
MA90 88
```

---

那么：

### 强势股

```text
回踩MA30

95附近
```

---

### 中等强势

```text
回踩MA90

88附近
```

---

而不是：

```text
固定跌8%
```

因为：

```text
100→92
```

可能：

```text
离MA90还远
```

并不是真支撑。

---

# 如果是你这个 v5 项目

我会把 Position_Zone 完全重构成：

```python
Zone_Score
```

由以下组成：

```python
1. close相对MA90位置

2. close相对MA150位置

3. close相对MA240位置

4. MA90斜率

5. MA150斜率

6. MA240斜率

7. MA多头排列程度
```

最后得到：

```text
Bottom Zone
Transition Zone
Main Trend Zone
Extended Zone
High Risk Zone
```

这比单纯的：

```python
120日高低点分位
```

对你要研究的

```text
Position × Drawdown → Future Rebound
```

预测力大概率更强，因为它直接刻画了市场参与者实际关注的支撑/压力结构，而不仅仅是价格在区间中的相对位置。
