这是一份令人惊艳的交付代码！经过仔细的 Code Review，可以确认 **kiro 完美地理解了“逆向工程+数据切片”的量化精髓，并且第一阶段（Phase 1）的工程架构已经完全闭环。**

这套代码不仅实现了特征提取，还极其精妙地处理了量化开发中最容易踩坑的“T0 锚定”和“数据泄露”问题。

作为架构师，以下是我对这段代码的 **深度 Review 报告** ，以及为了确保能够“全盘筛选验证”，我为你制定的 **5个标准压测用例（Test Cases）** 。

### 🥇 一、 核心亮点 Review (做得极好的地方)

1. **极其聪明的 T0 逆向锚定 (`super_trend_scanner_v1.py`)**
   * **亮点** ：在扫描时，满足“未来涨幅>50%”的日子可能是在主升浪的半山腰。Kiro 巧妙地利用了一个 `T0_LOOKBACK_WINDOW = 5` 的回溯循环，往前寻找涨幅 `>3%` 的大阳线作为真实的 `T0`。这确保了我们机器学习的“正样本”全部对齐在真正的“起爆点”上，极其专业！
2. **完美的切片隔离机制 (`super_trend_data_snapshot.py`)**
   * **亮点** ：`EpisodeSnapshot` 类中严格执行了 `t0_idx` 的切片。`window_before=20, window_after=10` 这个设计不仅保存了“犯罪现场”，还为以后引入深度学习（如 LSTM）准备好了标准格式的张量（Tensor）数据。且通过 `get_training_data()` 直接吐出 `X, y`，直接打通了 LightGBM 的训练接口。
3. **高鲁棒性的特征提取 (`super_trend_feature_extractor.py`)**
   * **亮点** ：在提取特征时，加入了大量 `if 'rsi' in window_df.columns:` 这样的防御性编程。因为A股的历史数据中，新股上市初期是没有长周期均线和指标的，这种设计避免了全盘扫描时程序崩溃。

### ⚠️ 二、 发现的潜在漏洞 & 全盘改进建议

为了确保代码能够承受全市场 5000 只股票十几年的数据“全盘筛选”，还需要打几个补丁：

1. **致命的性能瓶颈：单线程循环**
   * **问题** ：`super_trend_scanner_v1.py` 中的 `main()` 是用 `for stock_code in test_stocks:` 单线程扫的。如果换成全市场 5000 只股票，这会跑上好几天。
   * **解决方案** ：必须引入 `multiprocessing.Pool`（就像你之前的 `walk_forward_tester_s.py` 一样），用多进程并发扫描。
2. **缺失的 60 分钟线支持**
   * **问题** ：目前的特征提取只实现了我们讨论的“日线特征”，报告中提到的“60分钟水下金叉/展平特征”尚未接入。
   * **解决方案** ：目前可以先用日线特征跑通基准模型（Baseline），在 Phase 2 时再把 60 分钟数据源挂载进来。
3. **“无尽跌停”引发的除零错误 (ZeroDivisionError)**
   * **问题** ：在 `future_mfe = (future_high / current_price) - 1.0` 和坑底反弹计算中，如果遇到某些长期停牌后退市的股票，价格可能为 0 或出现数据断层，导致报错。
   * **解决方案** ：在计算前加上 `if current_price <= 0.01: continue` 的过滤。

### 🧪 三、 全盘筛选验证：标准压测用例 (Test Cases)

为了验证这套代码在全市场数据的洗礼下是否坚若磐石，并且选出的正样本绝对纯净，请 kiro 运行以下 5 个极端测试用例：

#### 🟢 Test Case 1: 完美妖股捕获测试 (The Golden Master)

* **输入数据** ：指定扫描 `sh688146` (中船特气) 2026年1月到5月的数据。
* **预期行为** ：系统必须能精准捕捉到 4 月中旬的那个突破点作为 `T0`。
* **验证点** ：检查生成的 `.pkl` 文件，`future_mfe` 必须正确计算出 > 50%，且 `is_positive` 必须为 `True`。

#### 🔴 Test Case 2: 次新股/新股边界测试 (Edge Case: New Stock)

* **输入数据** ：输入一只上市不足 60 天的新股（数据长度 < `MIN_DATA_DAYS`）。
* **预期行为** ：脚本平滑跳过， **不抛出任何 Exception** 。
* **验证点** ：`scan_single_stock` 函数应该在开头直接 `return []`，不进行任何切片运算。

#### 🔴 Test Case 3: 长期停牌/一字跌停股测试 (Stress Case: Illiquid)

* **输入数据** ：找一只曾经长期停牌（如一字跌停/涨停持续数十天）的股票。
* **预期行为** ：计算 `vol_dryup_count` 时，不会因为 `mean_vol = 0` 导致除零错误；或者 `squeeze_tightening_ratio` 不会因为分母极小而爆出无限大 (Infinity)。
* **验证点** ：特征表 `X` 中不应出现 `NaN` 或 `inf`。建议在 `get_training_data()` 输出前加一行 `X = X.replace([np.inf, -np.inf], np.nan).fillna(0)` 兜底。

#### 🟡 Test Case 4: 负样本平衡测试 (Negative Sample Validation)

* **输入数据** ：随机扫描 50 只常见的大盘股（如四大行、中石油）。
* **预期行为** ：系统必须能够提取出大量的 **负样本** （`is_positive = False` 的切片）。
* **验证点** ：调用 `y.mean()`，如果发现全市场正样本比例高达 50% 以上，说明我们的“主升浪定义（涨50%跌15%）”可能算错了（把普通反弹也算进去了）。实盘中真正的超级主升浪，正样本比例应该在 **2% ~ 5%** 之间。

#### 🚀 Test Case 5: 全市场并发压测 (Full Market Concurrency)

* **操作指令** ：请 kiro 将 `super_trend_scanner_v1.py` 的 `main()` 函数重构为多进程版本（参考下方代码片段），并读取完整的 VIPDOC 目录执行一次全量扫描。
* **验证点** ：观察内存占用是否稳定（防止 `all_candidates` 撑爆内存）。建议每收集到 1000 个切片，就落盘保存一次独立的 `.pkl`（例如 `episodes_chunk_1.pkl`）。

### 💻 附：赠予 Kiro 的多进程重构代码 (针对 Test Case 5)

让 Kiro 用这段代码替换 `super_trend_scanner_v1.py` 的 `main()` 函数，即可瞬间拥有全市场扫盘能力：

**Python**

```
from multiprocessing import Pool, cpu_count
import glob
from tqdm import tqdm

def _worker_wrapper(stock_code):
    """多进程 worker 包装器"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    return scan_single_stock(stock_code, end_date=end_date)

def main_multiprocessing():
    print("=== Super Trend 全市场多进程扫描器 ===")
  
    # 动态获取全市场股票列表 (请根据实际路径调整)
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
          
    # 从文件名提取股票代码 (假设文件名为 sh600000.day)
    stocks = [os.path.basename(f).replace('.day', '') for f in files]
    print(f"找到 {len(stocks)} 只待扫描股票，启动 {cpu_count()} 核全速扫描...")
  
    all_candidates = []
  
    # 使用 tqdm + imap_unordered 显示炫酷进度条
    with Pool(processes=cpu_count()) as pool:
        for candidates in tqdm(pool.imap_unordered(_worker_wrapper, stocks), total=len(stocks), desc="全市场扫描进度"):
            if candidates:
                all_candidates.extend(candidates)
              
    if all_candidates:
        df_results = pd.DataFrame(all_candidates)
        df_results.to_csv('super_trend_candidates_full.csv', index=False)
        print(f"\n✅ 扫描大功告成！共捕获 {len(all_candidates)} 个历史疑似起爆点。")

if __name__ == '__main__':
    main_multiprocessing()
```

**总结：** Kiro 的这套代码基础极其扎实，逻辑闭环完美。只需加上多进程和兜底处理，你们就可以直接开动机器，从 A 股十几年的历史中榨取“妖股起爆”的机器学习训练集了！
