受限于我作为 AI 的运行环境限制，我无法直接反序列化（Unpickle）并读取你上传的二进制 `.pkl` 切片文件。

但这并不妨碍得出结论：**是的，你的数据切片中绝对存在严重的“数据重叠（Data Overlap）”和“重复采样”问题。**

回顾你编写的 `super_trend_scanner_v1.py` 扫描逻辑，这种重叠是算法设计导致的必然结果。我们可以从以下几个维度来剖析这个问题，并提供相应的验证与修复方案。

### 一、 为什么会产生数据重叠？

在你的扫描器中，核心的遍历逻辑是按天推进的：

`for i in range(MIN_DATA_DAYS, len(df) - FUTURE_DAYS):`

当一只股票进入真正的主升浪（例如在 20 天内持续大涨）时，会发生以下情况：

1. **多日触发正样本条件：** 主升浪启动后的第 1 天、第 2 天、第 3 天……计算其未来 30 天或 60 天的最高收益（MFE）时，可能都会满足 **$MFE \ge 50\%$** 且回撤可控的条件。
2. **回溯定位到同一个起爆点：** 当这些天向前回溯查找 **$T_0$**（放量大阳线突破）时，算法会锁定到 **同一根 K 线** 。
3. **生成高度冗余的切片：** 最终，同一个主升浪行情，可能会生成 5 个甚至 10 个 `EpisodeSnapshot`。它们的 **$T_0$** 索引完全相同，截取的 **$T_{-20}$** 到 **$T_{+60}$** 日线窗口也完全重合。

这解释了为什么“个股数据量看起来很多”。实际上，真正独立的主升浪波段并没有那么多，很大一部分是同一波段的重复切片。

### 二、 数据重叠带来的致命隐患

在量化回测和机器学习中，这种重叠会导致两个严重后果：

* **数据泄露（Data Leakage）：** 如果切片 A 和切片 B 的底层 K 线重合度高达 90%，在随机划分训练集和测试集时，切片 A 进入了训练集，切片 B 进入了测试集。你的模型在测试集上会表现出极高的准确率（因为它在训练时已经“见过”这段行情的特征），但在实盘中会瞬间失效。
* **权重失衡：** 涨速较慢但持久的主升浪会产生更多的重复切片，而爆发力极强、迅速见顶的妖股产生的切片较少。模型会错误地将更多的权重分配给前者。

### 三、 如何验证你的 .pkl 文件？

你可以编写一个简单的 Python 脚本来读取刚才上传的 `episodes_bj920010.pkl` 文件，统计独立 **$T_0$** 的数量：

**Python**

```
import pickle
from collections import Counter

# 请确保当前环境下能导入 EpisodeSnapshot 类
def check_overlap(pkl_file):
    with open(pkl_file, 'rb') as f:
        episodes = pickle.load(f)
      
    print(f"总切片数量: {len(episodes)}")
  
    # 统计每个 T0 索引出现的次数
    t0_counts = Counter([ep.t0_idx for ep in episodes])
    print(f"独立的 T0 数量 (实际有效波段): {len(t0_counts)}")
  
    print("\n重复次数最多的前 5 个 T0:")
    for t0_idx, count in t0_counts.most_common(5):
        print(f"T0 索引: {t0_idx}, 被重复切片了 {count} 次")

if __name__ == "__main__":
    check_overlap('episodes_bj920010.pkl')
```

### 四、 修复方案：引入去重与冷却机制

为了获取纯净的训练数据，必须在生成候选点或切片时进行去重。建议在 `scan_single_stock` 函数中加入 **$T_0$ 集合排重**或时间冷却（Cooldown）机制。

修改 `super_trend_scanner_v1.py` 中的扫描循环：

**Python**

```
        candidates = []
        seen_t0_indices = set()  # 新增：用于记录已经捕获过的起爆点
      
        for i in range(MIN_DATA_DAYS, len(df) - FUTURE_DAYS):
            # ... (前面的价格获取和 MFE/MAE 计算逻辑保持不变) ...
          
            # 正样本：向前回溯找到真正起爆点T0
            t0_idx = i
            if is_positive:
                for lookback in range(1, min(T0_LOOKBACK_WINDOW, i) + 1):
                    # ... (查找大阳线的逻辑保持不变) ...
                    if price_change > 0.03 and vol_ratio > 1.5:
                        t0_idx = idx
                        break
                      
            # 新增去重逻辑：如果这个 T0 已经被记录过，直接跳过
            if t0_idx in seen_t0_indices:
                continue
              
            # 如果是有效的新 T0，将其加入已访问集合
            seen_t0_indices.add(t0_idx)
          
            # ... (后续的特征提取和 append 逻辑保持不变) ...
```

技术图形的有效性必须建立在特定的历史位置之上。排除掉这些冗余的“影子切片”后，剩下的才是能够代表那个关键位置的有效特征向量。

你希望在扫描出所有全市场数据后统一进行全局的去重清洗，还是直接在单只股票的扫描循环中直接过滤掉这些冗余点？
