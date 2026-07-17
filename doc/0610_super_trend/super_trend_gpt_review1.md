这版我认为已经到了**可以启动全量扫描和训练实验**的阶段。

如果按量化研发流程打分：

| 阶段       | 状态                |
| ---------- | ------------------- |
| 问题定位   | 95%                 |
| 架构设计   | 90%                 |
| 特征设计   | 85%                 |
| 工程实现   | 85%                 |
| 上线前风险 | 仍有3个需要重点关注 |

也就是说：

```text
现在最大的风险已经不是方向错了
而是实现细节和数据泄漏
```

下面是我最后一次 Review。

---

# 结论

## 可以运行

满足：

✅ Label Gap 已修复

✅ T0恢复

✅ P95恢复

✅ 三分类完成

✅ 级联完成

✅ RS20加入

✅ MA体系修正

✅ 概率校准加入

---

所以：

```text
值得跑一次完整实验
```

我不会再建议继续改架构。

---

# 但有三个高风险点

## 风险1（最高优先级）

RS20 可能存在未来函数

这里我最担心。

你写的是：

```python
mkt_pos = df_market.index[
    df_market.index.astype(str).str[:10] == t0_date_str
]
```

然后：

```python
mkt_ret_20d =
close[t0]
/
close[t0-20]
```

---

逻辑没问题。

但需要确认：

```python
df_market
```

和：

```python
df
```

是否同交易日对齐。

---

A股经常出现：

```text
停牌
节假日
缺失交易日
```

导致：

```python
mkt_pos - 20
```

并不对应：

```python
个股 t0_idx - 20
```

---

建议直接检查：

```python
assert market_date == stock_date
```

否则：

```text
RS20会产生噪音
```

甚至错误特征。

---

# 风险2

Platt Scaling 的训练集来源

这里最容易翻车。

你写：

```python
训练Gate
↓

拟合Platt
```

---

问题：

如果：

```python
Platt.fit(
训练集预测,
训练集标签
)
```

那么：

```text
严重过拟合
```

---

正确做法：

```python
Train
 ↓
Valid
 ↓
Platt
```

即：

```python
LightGBM
在Train训练

Platt
在Valid拟合
```

---

如果你用训练集拟合：

```text
AUC看起来更高
实盘更差
```

---

这是我第二担心的点。

---

# 风险3

Label2 阈值定义

这里我建议运行前再确认。

目前：

```text
Label2

MFE >= P95
AND
MAE >= -25%
```

---

这里有隐含问题：

P95是板块内定义。

例如：

```text
主板

43%
```

---

那么：

```text
44%
```

和：

```text
300%
```

都会变成：

```text
Label2
```

---

这会导致：

```text
超级牛股
+
刚过线股票
```

混在一起。

---

后续如果发现：

```text
Model B
AUC不上升
```

第一怀疑对象就是这里。

---

我会保留一个备用方案：

```text
Label2A
43~80%

Label2B
80%+
```

以后再实验。

当前不用改。

---

# 特征部分评价

这里我认为：

## 有价值

```text
rs_20d
```

⭐⭐⭐⭐⭐

---

```text
volume_percentile_120d
```

⭐⭐⭐⭐

---

```text
ma_bull_alignment_days
```

⭐⭐⭐⭐

---

## 一般

```text
atr_percentile
```

⭐⭐

---

```text
boll_width
```

⭐⭐

---

所以后面看重要性时：

如果出现：

```text
RS20 Top5
```

说明方向正确。

---

如果：

```text
RS20 排名20以后
```

那大概率实现有问题。

因为从经验看：

```text
Relative Strength
```

不应该这么弱。

---

# 关于 Precision 目标

这里我再修正一次预期。

报告写：

```text
Precision@0.65 >= 50%
```

---

我建议验收标准改成：

| 指标           | 合格  |
| -------------- | ----- |
| CV AUC         | >0.75 |
| Test AUC       | >0.74 |
| Precision@0.50 | >40%  |
| Precision@0.65 | >45%  |
| Precision@0.70 | >50%  |

---

原因：

级联+校准后：

```text
0.65
```

已经不一定对应旧模型的：

```text
0.65
```

了。

---

真正应该比较的是：

```text
Top N Precision
```

例如：

```text
Top 50
Top 100
Top 200
```

而不是固定阈值。

---

# 我最期待看到的结果

训练结束后，优先看下面几个输出：

### 1

Label分布

```text
0
1
2
```

是否接近：

```text
60%
35%
5%
```

---

### 2

Model A

```text
AUC
```

是否达到：

```text
0.80+
```

---

### 3

Model B

```text
AUC
```

是否达到：

```text
0.65+
```

---

### 4

Top10特征

理想情况：

```text
rs_20d
bias_ma60
price_position_120d
ma_bull_alignment_days
vol_breakout_ratio
```

进入Top10。

---

### 5

概率分布

重点观察：

```text
正样本均值
-
负样本均值
```

是否突破：

```text
0.12+
```

如果仍然：

```text
0.08
```

附近，

那说明问题还在特征，而不是标签。

---

最终结论：

**这版方案已经达到了“停止讨论、开始实验”的标准。**

我唯一建议在运行前再检查的只有两件事：

1. RS20 是否严格日期对齐（避免噪音和潜在未来函数）。
2. Platt Scaling 是否使用独立验证集拟合，而不是训练集拟合。

如果这两项确认无误，我会直接启动：

```bash
python3 backend/super_trend_scanner_v1_grok.py --full

python3 backend/super_trend_ml_trainer.py
```

然后根据第一轮结果再决定是继续优化特征，还是进一步细化 Label2。
