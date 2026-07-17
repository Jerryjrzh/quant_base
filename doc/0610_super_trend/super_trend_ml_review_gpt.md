我认为你们现在的分析已经接近真实问题了，但有一个关键判断我会修正：

> **我支持先修复 rs_20d 覆盖率，但不支持把希望寄托在 rs_20d 身上。**
>
> 从你给出的结果看，rs_20d 已经基本证明不是决定性特征，真正的问题已经暴露为：
>
> **Gate任务本身定义错误。**

这是一个重要转折点。

---

# 一、rs_20d 已经被证伪了

先看数据：

| Label | rs_20d |
| ----- | -----: |
| 0     |  0.057 |
| 1     |  0.068 |
| 2     |  0.078 |

差异：

```text
0.078 - 0.057 = 0.021
```

这个量级太小了。

即使覆盖率达到：

```text
41%
→
95%
```

你得到的大概率是：

```text
importance:
#15
→
#10
```

而不是：

```text
#15
→
#1
```

---

从统计角度：

如果特征真的有价值，

即使只有：

```text
40%覆盖
```

也会看到明显信号。

例如：

```text
Label0 = -0.05

Label2 = +0.15
```

这种情况。

---

而现在：

```text
0.057
0.078
```

实际上已经说明：

```text
RS20信号弱
```

至少远弱于：

```text
bias_ma60
vol_breakout_ratio
price_position_120d
```

---

所以：

## 建议

修

```text
nearest date fallback
```

没问题。

但别期待：

```text
Gate AUC
0.60 → 0.80
```

这种事情发生。

不会的。

---

# 二、Gate AUC=0.60 暴露了更大的问题

这是整个实验最重要的信息。

---

Gate定义：

```text
Label0

vs

Label1 + Label2
```

---

实际比例：

```text
51%

vs

49%
```

几乎平衡。

---

理论上：

如果 Label0 真的是：

```text
垃圾股
```

而：

```text
Label1+2
```

真的是：

```text
好股票
```

那么：

```text
AUC
0.75+
```

很正常。

---

结果：

```text
AUC
0.60
```

说明什么？

说明：

```text
Label0
和
Label1
本质很像
```

---

换句话说：

你定义的：

```text
22d MFE < 10%
```

并不等于：

```text
垃圾股
```

---

很多样本其实是：

```text
突破失败

震荡

慢牛

横盘
```

---

这些样本在T0时刻长得和：

```text
Label1
```

极其接近。

---

所以：

Gate根本学不会。

---

# 三、这意味着级联设计可能不成立

这是最关键结论。

---

级联成立的前提：

第一层：

```text
容易
```

第二层：

```text
困难
```

---

例如：

### 人脸识别

Gate：

```text
是不是人脸
```

容易。

---

Precision：

```text
是谁
```

困难。

---

你的系统：

Gate：

```text
普通上涨
vs
不上涨
```

结果：

```text
AUC=0.60
```

已经证明：

```text
并不容易
```

---

反而：

Precision：

```text
Label2
vs
Label1
```

AUC：

```text
0.657
```

---

竟然比Gate更好。

这很反常。

---

这通常意味着：

```text
级联拆错了
```

---

# 四、我现在倾向于直接做一个实验

不要猜。

直接做AB。

---

## 实验A

当前级联：

```text
Gate

0

vs

1+2

↓

Precision

2

vs

1

```

---

最终：

```text
P(A)*P(B)
```

---

## 实验B

直接单模型：

```text
2

vs

0+1
```

---

训练同样特征。

---

然后比较：

```text
Test AUC
Precision
TopN Precision
```

---

我怀疑会出现：

```text
单模型
>
级联
```

---

# 五、为什么我怀疑单模型会赢

看看你的重要性。

Top10：

```text
bias_ma60
vol_breakout_ratio
price_position_120d
...
```

---

这些特征描述的是：

```text
超级主升浪
```

---

而不是：

```text
普通上涨
```

---

所以它们天然更适合：

```text
Label2

vs

其它
```

---

不适合：

```text
Label1+2

vs

Label0
```

---

也就是说：

你当前特征体系本质是：

```text
Precision Feature Set
```

不是：

```text
Gate Feature Set
```

---

# 六、如果坚持做级联

那必须换Gate任务

不是：

```text
0

vs

1+2
```

---

而是：

### 方案1

```text
0

vs

2
```

训练Gate。

---

### 方案2

```text
Label1高位

+
Label2

vs

Label0
```

---

### 方案3

直接回归：

```text
预测22d MFE
```

再切阈值。

---

这些都比：

```text
0

vs

1+2
```

更合理。

---

# 我现在的建议顺序

优先级排序：

### P0

修复 rs_20d 覆盖率

因为是Bug。

---

### P1

立刻增加实验：

```text
单模型

Label2

vs

Label0+1
```

这是当前最有价值实验。

---

### P2

比较：

```text
级联
vs
单模型
```

的：

* Test AUC
* Top50 Precision
* Top100 Precision
* Top200 Precision

---

### P3

如果单模型胜出

直接废弃：

```text
Gate(0 vs 1+2)
```

这条路线。

---

从你目前贴出来的数据看，我对下面这个判断已经有七八成把握：

```text
当前失败原因
不是RS20

不是Platt

甚至不是特征数量

而是：

Gate任务定义本身没有可学习信号
```

而 Gate AUC=0.6046 恰恰是这个结论最强的证据。
