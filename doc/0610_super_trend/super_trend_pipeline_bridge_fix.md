# Super Trend Phase 1 — 切片断层修复记录

> 问题：扫描器 `scan_single_stock()` 只输出候选点字典，`EpisodeSnapshot` 从未在真实扫描流水线中被创建。测试脚本 `test_super_trend_phase1.py` 使用 `np.random.uniform()` 模拟假数据，而非真实扫描结果。

---

## 一、问题诊断

### 流水线断层

```
scan_single_stock()          → 候选点字典（stock_code, t0_idx, future_mfe, ...）
                                     ↓
                              【断层！】没有人把候选点转化为 EpisodeSnapshot
                                     ↓
EpisodeSnapshot / Collection → 只在 test 脚本中出现，且用随机数模拟
```

### 具体表现

| 问题 | 位置 | 影响 |
|---|---|---|
| 扫描器只返回元数据字典 | `scan_single_stock()` | 无 K 线切片、无特征向量 |
| 测试用 `np.random.uniform()` | `test_super_trend_phase1.py:44` | 训练数据全是假数据 |
| `build_episodes()` 不存在 | 全局 | 扫描→训练 之间没有桥接 |

---

## 二、修复方案

### 新增 `build_episodes()` 桥接函数

**位置**：`super_trend_scanner_v1.py`

```python
def build_episodes(candidates, df, df_market=None):
    """
    桥接函数：将扫描器产出的候选点字典 → 特征提取 → EpisodeSnapshot 切片。
    这是扫描与训练之间缺失的关键一环。
    """
    collection = EpisodeCollection(data_dir=EPISODE_DIR)

    for cand in candidates:
        t0_idx = cand['t0_idx']
        if t0_idx >= len(df):
            continue

        # 真实特征提取（不再是模拟数据）
        features = extract_all_features(df, t0_idx)

        episode = EpisodeSnapshot(
            stock_code=cand['stock_code'],
            t0_date=cand['t0_date'],
            t0_idx=t0_idx,
            df_daily=df,
            df_market=df_market,
            features=features,
            future_mfe=cand['future_mfe'],
            is_positive=cand['is_positive'],
        )
        collection.add_episode(episode)

    return collection
```

### 新增 `scan_and_build_episodes()` 便捷函数

```python
def scan_and_build_episodes(stock_code, end_date=None, df_market=None):
    """单只股票的完整流水线：加载数据 → 扫描候选点 → 特征提取 → 生成切片"""
    df = get_full_data_with_indicators(stock_code, end_date=end_date)
    if df is None or len(df) < MIN_DATA_DAYS + FUTURE_DAYS:
        return [], EpisodeCollection(data_dir=EPISODE_DIR)

    candidates = scan_single_stock(stock_code, end_date=end_date)
    if not candidates:
        return [], EpisodeCollection(data_dir=EPISODE_DIR)

    collection = build_episodes(candidates, df, df_market=df_market)
    return candidates, collection
```

### 重写 `main()` 为完整流水线

```python
def main():
    """单线程测试版：扫描 + 生成真实数据切片"""
    # 预加载大盘指数（只加载一次）
    df_sh_index = _load_market_index('sh000001', end_date=end_date)
    df_sz_index = _load_market_index('sz399001', end_date=end_date)

    for stock_code in test_stocks:
        df_market = df_sh_index if stock_code.startswith('sh') else df_sz_index
        candidates, collection = scan_and_build_episodes(
            stock_code, end_date=end_date, df_market=df_market
        )
        # ... 汇总并保存

    # 保存 Episode 切片 + 训练数据 CSV
    all_episodes.save_all('episodes_v1.pkl')
    X, y = all_episodes.get_training_data()
    # ...
```

### 重写 `test_super_trend_phase1.py`

**核心变更**：彻底删除所有 `np.random` 模拟代码，改用 `scan_and_build_episodes()` 执行真实扫描。

```python
# 旧（假数据）
future_mfe = np.random.uniform(0.0, 0.8)
is_positive = future_mfe >= 0.50

# 新（真实扫描）
candidates, collection = scan_and_build_episodes(stock_code, end_date=end_date)
```

新增验证环节：
- T+1 跳空/最低价的实际数值输出
- 大盘上下文字段验证
- NaN 数量统计（确认 LightGBM 兼容）

---

## 三、修复后的完整流水线

```
scan_single_stock()             → 候选点字典
        ↓
build_episodes(candidates, df)  → 特征提取 + EpisodeSnapshot 创建
        ↓
EpisodeCollection               → 真实 K 线切片 + 真实特征向量
        ↓
get_training_data()             → X, y（可直接喂给 LightGBM）
        ↓
save_all() / to_csv()           → .pkl 切片 + .csv 训练数据
```

---

## 四、文件变更汇总

```
backend/super_trend_scanner_v1.py       # +build_episodes() +scan_and_build_episodes() +重写main()
backend/test_super_trend_phase1.py      # 全文重写：删除模拟数据，改用真实扫描流水线
```

---

## 五、验证状态

| 检查项 | 状态 |
|---|---|
| 四模块语法编译通过 | ✅ |
| `build_episodes()` 桥接函数连接扫描器与切片器 | ✅ |
| `main()` 端到端生成真实 EpisodeSnapshot | ✅ |
| 测试脚本不再使用 `np.random` 模拟数据 | ✅ |
| 预加载大盘指数避免重复 IO | ✅ |
| T+1 撮合字段和大盘上下文在测试中可验证 | ✅ |
