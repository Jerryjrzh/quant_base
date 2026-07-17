我仔细查阅了你提供的代码文件。你的数据流水线整体架构设计得很清晰，各个模块的分工也很明确。

针对你遇到的问题，下面是详细的 review 结果和修复方案：

### 一、 为什么没有生成切片（Episode）文件？

**回答你的第一个问题：`super_trend_scanner_v1.py` 确实可以调用到附件中的模块，导入路径是正确的。但切片文件没有生成，是因为多进程逻辑中存在一个“短路” Bug。**

如果你是通过 `python super_trend_scanner_v1.py --full` 运行的代码，它会执行 `main_multiprocessing()`。请看这段代码的调用链：

1. `main_multiprocessing()` 使用进程池调用了 `_worker_wrapper()`。
2. `_worker_wrapper()` 内部直接调用了 `scan_single_stock()`。
3. `scan_single_stock()` 的功能仅仅是返回候选点（`candidates`）的字典列表。

**发现问题了吗？** 在多进程模式下，代码完全跳过了 `build_episodes()` 和生成 `EpisodeSnapshot` 的环节，只提取了基本信息并保存了 CSV。只有单线程的 `main()` 函数才执行了完整的 `scan_and_build_episodes()`。

#### 修复方案

为了在多进程下也能生成切片，且防止进程间传递庞大对象导致内存溢出，最优雅的做法是让每个 Worker 自己生成切片并独立落盘。你需要修改 `super_trend_scanner_v1.py` 中的 `_worker_wrapper` 和 `main_multiprocessing`：

**Python**

```
# 修改 1：重写 _worker_wrapper，让它处理完整的提取和切片生成
def _worker_wrapper(stock_code):
    """多进程 worker：扫描并直接落盘单个股票的切片"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    try:
        # 这里需要注意，如果在多进程里频繁加载大盘指数会非常耗时
        # 可以暂时不传 df_market，让 EpisodeSnapshot 使用备用逻辑，或传入 None
        candidates, collection = scan_and_build_episodes(stock_code, end_date=end_date, df_market=None)
      
        # 如果生成了切片，直接在子进程落盘，避免 IPC 传输大文件
        if collection and collection.episodes:
            # 单独保存该股票的切片文件
            save_path = os.path.join(EPISODE_DIR, f"episodes_{stock_code}.pkl")
            collection.save_all(save_path)
          
        return candidates
    except Exception as e:
        print(f"[{stock_code}] 处理异常: {e}")
        return []

# 修改 2：多进程跑完后，可以加一个小脚本把所有零散的 .pkl 合并（可选）
```

*注：修复后，每个有候选点的股票都会在 `episodes` 文件夹下生成一个独立的 `.pkl` 文件，这样既能生成切片，又能极大地节省内存。*

### 二、 样本数量（180正 / 72负）够不够？

**直白地说：远远不够，而且比例完全“倒挂”了。**

1. **绝对数量不足** ：对于机器学习（哪怕是像 LightGBM 这样的树模型），252 个总样本太少了。模型很容易在这么小的数据集上严重过拟合，无法学到市场的真实规律。通常至少需要数千个高质量样本。
2. **正负样本比例失调** ：你的结果是 180 个正样本、72 个负样本。在真实的 A 股市场中，“假突破 / 骗炮”的次数是远远多于“真主升浪”的。正常合理的正负样本比例应该是 1:3 甚至 1:5。目前的比例会导致模型变得极度盲目乐观，实盘中会频繁发出假信号。

**为什么负样本这么少？**

看你代码里的负样本定义：`daily_gain >= 0.03 and mfe < 0.15`。

也就是说，当天涨幅超过 3%，且未来 30 天最高涨幅不到 15% 才算负样本。这个条件有点过于严苛了，很多实际上的“诱多假突破”可能未来 30 天最高涨到了 18%，然后暴跌，这在你的代码里既不算正样本也不算负样本，直接被丢弃了。

### 三、 筛选“周期内爆发超过1倍（100%）”的新方案

如果你想把目标锚定在真正的“大妖股”或“超级主升浪”（涨幅 **$\ge$** 100%），原有的 30 天周期和阈值需要重新设计。要在全市场中把这类标的筛出来，建议对 `super_trend_scanner_v1.py` 顶部的全局配置进行如下修改：

#### 1. 调整核心参数

**Python**

```
# 放宽观察窗口，1个月翻倍太极端，2-3个月（40-60个交易日）翻倍是典型的超级主升浪
FUTURE_DAYS = 60  
MIN_GAIN = 1.00  # 最小涨幅100%（即翻一倍）

# 放宽回撤容忍度，妖股在启动初期洗盘通常极其剧烈，-15%很容易被洗掉
MAX_DRAWDOWN = -0.25  

T0_LOOKBACK_WINDOW = 8  # 妖股启动前可能有多根大阳线，向前回溯窗口拉长一点
```

#### 2. 扩充负样本池（极其关键）

既然目标是 100% 的大牛股，那么只要是出现了异动（突破动作）但最终**没有翻倍**的，其实都可以作为训练模型时的“非正样本”（或者区分为“普通上涨”和“假突破”）。

修改负样本判定逻辑：

**Python**

```
# 负样本判定条件放宽，收集更多的"陷阱"
NEG_MIN_DAILY_GAIN = 0.04   # 异动日涨幅>=4% (或者是放量突破)
NEG_MAX_FUTURE_GAIN = 0.30  # 未来60天最高涨幅<30%，对于"翻倍预期"来说，这就是失败的诱多
```

#### 3. 修改代码中的打标逻辑（`scan_single_stock` 内）

将原本的 `is_valuable_negative` 判定稍微调整得更有层次：

**Python**

```
            # 正样本：超级主升浪（涨幅>=100%，回撤可控）
            if mfe >= MIN_GAIN and mae >= MAX_DRAWDOWN:
                is_positive = True
          
            # 负样本：出现明显起爆迹象（大阳线），但后续涨幅拉胯（连30%都没摸到）
            elif daily_gain >= NEG_MIN_DAILY_GAIN and mfe < NEG_MAX_FUTURE_GAIN:
                is_valuable_negative = True
```

**执行建议：** 按照上述修改更新参数后，通过修复过的多进程逻辑（`--full`）重新跑一次全市场扫描。因为翻倍股本身就是极少数，你可能需要扫描过去 5 年甚至 10 年的全市场数据，才能积累出 500-1000 个高质量的“翻倍正样本”，以及对应的 2000-3000 个负样本，这样训练出来的模型才具备真正的实战价值。
