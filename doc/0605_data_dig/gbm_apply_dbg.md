在多进程环境下调试量化回测是最痛苦的，因为子进程的 `print` 报错通常会被系统直接吞噬（Silent Failure）。当 5000 只股票全部返回 `None` 时，主进程就会认为“没有合格的股票”，不生成任何报错，也不生成最终的 CSV。

为了彻底查清是**日期切片失败**、**模型依然没加载**、还是**门槛太高所有股票被淘汰**，我们必须在子进程中注入一个**物理文件调试日志 (File Debug Logger)**。

请在你的 `walk_forward_tester_s.py` 中进行以下局部替换。这会把所有子进程的“内心独白”全部写到硬盘上的日志文件里。

### 第一步：在顶部注入专用的多进程文件日志

打开 `walk_forward_tester_s.py`，在顶部 `import` 区域的下方，找到 `logger = logging.getLogger(__name__)`，将其替换为以下代码：

```python
# ... 顶部的 import 保持不变 ...
from gbm_scorer import GBMScorer

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
os.makedirs(OUTPUT_PATH, exist_ok=True)

# ==========================================\n# 🌟 新增：子进程专用 Debug 日志 (写入文件)\n# ==========================================
debug_log_path = os.path.join(OUTPUT_PATH, 'gbm_worker_debug.log')
debug_logger = logging.getLogger('WorkerDebug')
debug_logger.setLevel(logging.DEBUG)
# 每次运行前清空旧日志
fh = logging.FileHandler(debug_log_path, mode='w', encoding='utf-8')
fh.setFormatter(logging.Formatter('%(asctime)s [PID:%(process)d] %(message)s'))
debug_logger.addHandler(fh)

# 控制台日志 (主进程用)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================\n# === GBM 模型全局初始化 ===\n# ==========================================
_gbm_scorer = None
_gbm_enabled = True
_gbm_threshold = 0.62

def _init_gbm_scorer():
    """全局加载 GBM 模型（单例模式）"""
    global _gbm_scorer, _gbm_enabled
    debug_logger.info("⚙️ 子进程启动，准备加载 GBM 模型...")
    if _gbm_scorer is None and _gbm_enabled:
        try:
            _gbm_scorer = GBMScorer()
            if not _gbm_scorer.load():
                debug_logger.warning("⚠️ GBM 模型加载失败 (.pkl 文件可能不存在)，降级为原始评分系统")
                _gbm_enabled = False
                _gbm_scorer = None
            else:
                debug_logger.info(f"✅ GBM 模型加载成功！阈值设定为: {_gbm_threshold}")
        except Exception as e:
            debug_logger.error(f"❌ GBM 初始化异常: {e}")
            _gbm_enabled = False
            _gbm_scorer = None

```

### 第二步：修改 `worker` 函数，植入日志探针

往下找到你的 `def worker(file_path):` 函数，将里面的**打分与过滤逻辑**替换为带有日志探针的版本：

```python
def worker(file_path):
    try:
        stock_code = os.path.basename(file_path).split('.')[0]
        full_df = data_loader.get_daily_data(file_path)
        
        # 1. 截取时间窗口
        df, forward_df = get_time_sliced_data(full_df, EVAL_DATE, FORWARD_DAYS)
        if df is None:
            return None # 正常现象，股票停牌或未上市
            
        # 2. 策略模块打分
        result_dict = apply_morse_sniper_strategy(df)
        if not result_dict:
            return None # 基础形态不达标或 score < 85 被基础模块淘汰

        # 能走到这里，说明过了基础门槛！
        debug_logger.info(f"[{stock_code}] 基础模块通过! 基础分: {result_dict.get('score')}")

        # 3. 引入 GBM 模型过滤
        global _gbm_scorer
        if _gbm_scorer is not None:
            try:
                df_feature = pd.DataFrame([{
                    'score': result_dict['score'],
                    'ma_slope': result_dict['ma_slope'],
                    'bias_20': result_dict['bias_20'],
                    'market_env': result_dict['market_env'],
                    'v44_trend': result_dict['v44_trend'],
                    'v44_bias_tier': result_dict['v44_bias_tier']
                }])
                
                df_scored = _gbm_scorer.score(df_feature)
                gbm_proba = df_scored['gbm_proba'].iloc[0]
                
                # 记录打分结果
                if gbm_proba < 0.62:
                    debug_logger.info(f"[{stock_code}] ❌ 被 GBM 淘汰: Prob = {gbm_proba:.4f} < 0.62")
                    return None
                    
                debug_logger.info(f"[{stock_code}] 🚀 GBM 放行: Prob = {gbm_proba:.4f} >= 0.62")
                result_dict['gbm_proba'] = gbm_proba
                
            except Exception as e:
                debug_logger.error(f"[{stock_code}] GBM 预测时发生代码异常: {e}")
                return None
        else:
            debug_logger.error(f"[{stock_code}] 严重错误: _gbm_scorer 在子进程中为 None！")
            return None

        # =============== 以下为原有出场推演逻辑保持不变 ===============
        entry_price = result_dict['trigger_price']
        # ... 这里是你原来的挂单和追踪止盈代码 ...
        
        # (可选) 在出场逻辑的最后加一句：
        # debug_logger.info(f"[{stock_code}] 最终交易状态: {trade_status}, PnL: {pnl_pct}")

        # ... return output_dict ...

```

---

### 如何排查：

修改并保存后，运行一次 `python walk_forward_tester_s.py`。
然后立刻打开 `data/result/gbm_worker_debug.log` 文件。

这份日志会像“CT 机”一样照出当前系统的病灶：

* **病症 A**：如果日志里都是 `⚠️ GBM 模型加载失败`
* **根因**：当前脚本的执行路径不对，子进程找不到 `gbm_scorer_v1.pkl` 文件。


* **病症 B**：如果日志里大量出现 `[{stock_code}] ❌ 被 GBM 淘汰: Prob = 0.5120 < 0.62`
* **根因**：你的模型和代码**完全没问题**！没有任何输出纯粹是因为 `2026-04-01` 这一天的市场行情太差，全市场没有一只股票的预测概率超过 `0.62`。你可以尝试把 `_gbm_threshold` 临时调低到 `0.40` 看看是否有票输出。


* **病症 C**：如果日志只有第一行 `⚙️ 子进程启动...`，下面没有任何股票信息
* **根因**：`screenergf.py` 里的 `apply_morse_sniper_strategy` 杀伤力太大，把 5000 只股票在第一关全砍掉了，连 GBM 的面都没见到。



请把 `gbm_worker_debug.log` 里打印出来的代表性内容发给我，我一眼就能看穿它卡在什么地方了！