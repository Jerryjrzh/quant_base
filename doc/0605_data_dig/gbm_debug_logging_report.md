# GBM Debug 日志配置报告

**日期**: 2026-06-05  
**状态**: ✅ 配置完成  
**目的**: 诊断多进程环境下 GBM 过滤无输出的问题

---

## 一、新增功能

### 1.1 子进程专用 Debug 日志

**文件位置**: `data/result/gbm_worker_debug.log`

**特点**:
- 每次运行自动清空旧日志 (`mode='w'`)
- 记录进程 ID (`[PID:xxxxx]`)
- 记录每只股票的完整决策路径
- DEBUG 级别，信息最全

### 1.2 日志内容

#### A. 子进程初始化

```
2026-06-05 12:00:00,123 [PID:12345] ⚙️ 子进程启动 (PID:12345)，准备加载 GBM 模型...
2026-06-05 12:00:00,234 [PID:12345] ✅ GBM 模型加载成功！阈值设定为: 0.62
```

#### B. 基础模块通过

```
2026-06-05 12:00:01,456 [PID:12345] [sh600519.day] 基础模块通过! 基础分: 95
```

#### C. Scheme C 淘汰

```
2026-06-05 12:00:01,567 [PID:12345] [sh600519.day] ❌ Scheme C 淘汰: slope=0.015, board=10CM
```

#### D. GBM 淘汰

```
2026-06-05 12:00:01,678 [PID:12345] [sz000858.day] ❌ 被 GBM 淘汰: Prob = 0.5120 < 0.62
```

#### E. GBM 放行

```
2026-06-05 12:00:01,789 [PID:12345] [sz300750.day] 🚀 GBM 放行: Prob = 0.6842 >= 0.62
```

#### F. 错误信息

```
2026-06-05 12:00:01,890 [PID:12345] [sh688981.day] GBM 预测时发生代码异常: KeyError 'ma_slope'
2026-06-05 12:00:01,991 [PID:12346] [sz002230.day] 严重错误: _gbm_scorer 在子进程中为 None！
```

---

## 二、代码修改详情

### 2.1 新增 debug_logger (line 54-63)

```python
# ==========================================
# 🌟 新增：子进程专用 Debug 日志 (写入文件)
# ==========================================
debug_log_path = os.path.join(OUTPUT_PATH, 'gbm_worker_debug.log')
debug_logger = logging.getLogger('WorkerDebug')
debug_logger.setLevel(logging.DEBUG)
# 每次运行前清空旧日志
fh = logging.FileHandler(debug_log_path, mode='w', encoding='utf-8')
fh.setFormatter(logging.Formatter('%(asctime)s [PID:%(process)d] %(message)s'))
debug_logger.addHandler(fh)
```

### 2.2 _init_gbm_scorer 增加 debug 日志 (line 24-38)

```python
def _init_gbm_scorer():
    global _gbm_scorer, _gbm_enabled
    debug_logger.info(f"⚙️ 子进程启动 (PID:{os.getpid()})，准备加载 GBM 模型...")
    if _gbm_scorer is None and _gbm_enabled:
        try:
            _gbm_scorer = GBMScorer()
            if not _gbm_scorer.load():
                debug_logger.warning(f"⚠️ GBM 模型加载失败 (.pkl 文件可能不存在)，降级为原始评分系统")
                # ...
            else:
                debug_logger.info(f"✅ GBM 模型加载成功！阈值设定为: {_gbm_threshold}")
                # ...
        except Exception as e:
            debug_logger.error(f"❌ GBM 初始化异常: {e}")
            # ...
```

### 2.3 worker 函数增加 debug 日志

**基础模块通过** (line 201):
```python
debug_logger.info(f"[{stock_code_full}] 基础模块通过! 基础分: {res.get('score')}")
```

**Scheme C 淘汰** (line 214):
```python
debug_logger.info(f"[{stock_code_full}] ❌ Scheme C 淘汰: slope={ma_slope:.3f}, board={board_type}")
```

**GBM 淘汰** (line 230):
```python
debug_logger.info(f"[{stock_code_full}] ❌ 被 GBM 淘汰: Prob = {gbm_proba:.4f} < {_gbm_threshold}")
```

**GBM 放行** (line 233):
```python
debug_logger.info(f"[{stock_code_full}] 🚀 GBM 放行: Prob = {gbm_proba:.4f} >= {_gbm_threshold}")
```

**错误处理** (line 236-238):
```python
debug_logger.error(f"[{stock_code_full}] GBM 预测时发生代码异常: {e}")
# ...
debug_logger.error(f"[{stock_code_full}] 严重错误: _gbm_scorer 在子进程中为 None！")
```

---

## 三、诊断指南

运行回测后，打开 `data/result/gbm_worker_debug.log`，根据日志内容判断问题：

### 病症 A: 模型加载失败

**日志特征**:
```
⚠️ GBM 模型加载失败 (.pkl 文件可能不存在)，降级为原始评分系统
```

**根因**: 子进程找不到 `data/model/gbm_scorer_v1.pkl` 文件

**解决方案**:
```bash
# 检查模型文件是否存在
ls -lh data/model/gbm_scorer_v1.pkl

# 如果不存在，重新训练
cd backend
python3 gbm_scorer.py
```

---

### 病症 B: GBM 阈值过高

**日志特征**:
```
[sh600519.day] 基础模块通过! 基础分: 95
[sh600519.day] ❌ 被 GBM 淘汰: Prob = 0.5120 < 0.62
[sz000858.day] 基础模块通过! 基础分: 95
[sz000858.day] ❌ 被 GBM 淘汰: Prob = 0.4890 < 0.62
... (大量类似的淘汰日志)
```

**根因**: `2026-04-01` 当天市场行情太差，没有股票的预测概率超过 0.62

**解决方案**:
```python
# 临时降低阈值测试
_gbm_threshold = 0.40  # 从 0.62 降到 0.40
```

重新运行后，如果有股票通过，说明模型正常，只是阈值太高。

---

### 病症 C: 基础模块杀伤力太大

**日志特征**:
```
⚙️ 子进程启动 (PID:12345)，准备加载 GBM 模型...
✅ GBM 模型加载成功！阈值设定为: 0.62
⚙️ 子进程启动 (PID:12346)，准备加载 GBM 模型...
✅ GBM 模型加载成功！阈值设定为: 0.62
... (只有初始化日志，没有任何股票处理日志)
```

**根因**: `screenergf.py` 的 `apply_morse_sniper_strategy` 把所有股票在第一关就淘汰了，连 GBM 都没见到

**解决方案**:
```bash
# 检查 screenergf.py 的过滤条件是否过于严格
# 临时放宽条件测试
```

---

### 病症 D: 子进程模型未加载

**日志特征**:
```
[sh600519.day] 基础模块通过! 基础分: 95
[sh600519.day] 严重错误: _gbm_scorer 在子进程中为 None！
```

**根因**: `Pool(initializer=_init_gbm_scorer)` 没有生效，或 initializer 执行失败

**解决方案**:
```python
# 检查 Pool 调用是否正确
with Pool(processes=cpu_count(), initializer=_init_gbm_scorer) as pool:
    raw_results = pool.map(worker, files)
```

---

### 病症 E: 特征缺失

**日志特征**:
```
[sh600519.day] 基础模块通过! 基础分: 95
[sh600519.day] GBM 预测时发生代码异常: KeyError 'ma_slope'
```

**根因**: `screenergf.py` 没有返回 `ma_slope` 或 `bias_20`

**解决方案**:
```python
# 检查 screenergf.py 的返回值
return {
    'signal': True,
    'score': score,
    # ...
    'ma_slope': slope_13,  # 确保有这一行
    'bias_20': bias_13,    # 确保有这一行
    **v44_meta
}
```

---

## 四、使用步骤

### 4.1 运行回测

```bash
cd /home/hypnosis/data/quant_base/backend
python3 walk_forward_tester_s.py
```

### 4.2 查看 Debug 日志

```bash
# 查看完整日志
cat data/result/gbm_worker_debug.log

# 查看前 50 行
head -50 data/result/gbm_worker_debug.log

# 统计关键信息
grep "基础模块通过" data/result/gbm_worker_debug.log | wc -l
grep "Scheme C 淘汰" data/result/gbm_worker_debug.log | wc -l
grep "被 GBM 淘汰" data/result/gbm_worker_debug.log | wc -l
grep "GBM 放行" data/result/gbm_worker_debug.log | wc -l
```

### 4.3 分析日志

根据上述"诊断指南"判断问题所在，然后采取相应措施。

---

## 五、预期结果

### 5.1 正常情况

```bash
$ grep "GBM 放行" data/result/gbm_worker_debug.log | wc -l
12  # 约 12 只股票通过 GBM 过滤

$ grep "被 GBM 淘汰" data/result/gbm_worker_debug.log | wc -l
43  # 约 43 只股票被 GBM 淘汰

$ grep "Scheme C 淘汰" data/result/gbm_worker_debug.log | wc -l
200  # 约 200 只股票被 Scheme C 淘汰
```

### 5.2 异常情况

```bash
$ grep "GBM 放行" data/result/gbm_worker_debug.log | wc -l
0  # ❌ 无股票通过，需要诊断

$ grep "严重错误" data/result/gbm_worker_debug.log | wc -l
50  # ❌ 子进程模型未加载，检查 initializer
```

---

## 六、总结

### 6.1 新增功能

✅ **子进程专用 Debug 日志**: `data/result/gbm_worker_debug.log`  
✅ **完整决策路径**: 每只股票的每个过滤阶段都有记录  
✅ **进程 ID**: 可追踪哪个子进程处理了哪只股票  
✅ **错误捕获**: 所有异常都会记录到日志文件

### 6.2 下一步

1. 运行回测: `python3 walk_forward_tester_s.py`
2. 查看日志: `cat data/result/gbm_worker_debug.log`
3. 诊断问题: 根据本文档"诊断指南"判断
4. 修复问题: 采取相应措施
5. 重新运行: 验证修复效果

---

**报告版本**: 1.0  
**生成时间**: 2026-06-05  
**配置者**: Qoder CLI  
**基于**: Gemini Review 建议
