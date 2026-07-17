# Super Trend V1 改造计划与测试计划

## 基于 DeepSeek Review 的路线重构

### 核心结论

当前模型（单模型 AUC=0.68, Top200 Precision=20%）已触达天花板。根本原因：
- **截面快照特征**（bias_ma60, vol_breakout_ratio 等）只描述 T0 当天的"照片"，无法区分真主升 vs 假突破
- **绝对涨幅标签**（MFE≥P95）有幸存者偏差，牛股之所以涨，往往因为 T0 后的事件驱动
- **分类目标**不适合 Top N 选股场景，应该用排序模型

### 改造路线图总览

| 阶段 | 任务 | 涉及文件 | 预估工作量 |
|------|------|----------|-----------|
| Phase 1 | 时序特征工程（均线束 + 黄金坑） | `super_trend_feature_extractor_v2.py` (新建) | 中 |
| Phase 2 | 全市场排名序列特征 | `super_trend_market_ranker.py` (新建) | 大 |
| Phase 3 | 标签重构（超额收益百分位 + 过程稳定性） | `super_trend_label_builder.py` (新建) | 中 |
| Phase 4 | 排序模型（LambdaRank） | `super_trend_ranker_trainer.py` (新建) | 中 |
| Phase 5 | 端到端回测框架 | `super_trend_rank_backtester.py` (新建) | 中 |

---

## Phase 1: 时序特征工程（从"照片"到"视频"）

### 1.1 均线束状态特征

**业务逻辑**: 真主升浪前，MA5/10/20/60 经历"粘合→发散"过程。假突破则均线乱序或已过度发散。

**实现方案**:
```
新建文件: backend/super_trend_feature_extractor_v2.py

函数: extract_ma_bundle_features(df, t0_idx)
输入: df (含 ma5/ma10/ma20/ma60 列), t0_idx
输出: dict 包含以下特征:
  - ma_dispersion_20d: T0前20天每日 std([MA5,MA10,MA20,MA60])/close 序列
  - ma_glue_max_days: 离散度 < 2% 的最长连续天数
  - ma_glue_recency: 最近一次离散度从<2%上穿到>2%距T0的天数
  - ma_divergence_speed: T0前5天离散度的线性回归斜率
  - ma_convergence_flag: T0前10天内是否存在离散度<1.5%的窗口（布尔值）
```

**代码位置**: 在 `super_trend_feature_extractor_v2.py` 中实现，被 `scanner_v1_grok.py` 的 `build_episodes()` 调用。

### 1.2 黄金坑/假破位特征

**业务逻辑**: 主力洗盘 → 跌破关键均线 → 快速收回 → 主升浪启动。

**实现方案**:
```
函数: extract_washout_features(df, t0_idx)
输入: df (含 close, ma20, ma60 列), t0_idx
输出: dict:
  - washout_ma60_flag: T0前20天内是否存在 close<MA60 且次日 close>MA60
  - washout_ma60_depth: 跌破 MA60 的最大百分比深度
  - washout_ma60_recovery_days: 从跌破到收回的天数
  - washout_ma20_flag: 同上，基于 MA20
  - washout_ma20_depth: 同上
  - lower_shadow_count: T0前15天内长下影线（下影>实体2倍）的天数
```

### 1.3 保留精华截面特征（从原 25 个中精选）

基于特征重要性排序，保留以下 8 个核心截面特征:
1. `bias_ma60` (重要性 #1)
2. `vol_breakout_ratio` (#2)
3. `price_position_120d` (#5)
4. `vol_turnover_ratio` (#6)
5. `volume_percentile_120d` (#7)
6. `atr_percentile` (#10)
7. `boll_width` (#15)
8. `rs_20d` (#13)

**废弃特征理由**:
- `t0_close`, `t0_volume`: 绝对值特征，跨股票不可比
- `t0_rsi`, `t0_macd`: 已被时序特征覆盖
- `is_fake_breakdown`, `is_water_ignition`, `is_extreme_volume_dry`: 布尔稀疏特征，信息量低
- `days_underwater`, `days_below_ma30`, `ma_bull_alignment_days`: 被新的均线束特征覆盖
- `pre_breakout_vol_shrink_days`, `vol_dryup_count`: 被新的量能序列特征覆盖
- `stock_return_20d`: 被全市场排名特征覆盖

### Phase 1 测试计划

| 测试项 | 测试方法 | 通过标准 |
|--------|---------|---------|
| 均线离散度计算正确性 | 用已知均线数据手算 3 只股票的离散度序列 | 数值误差 < 0.001 |
| 粘合天数逻辑 | 构造粘合→发散→粘合的模拟数据 | 正确识别粘合区间 |
| 黄金坑检测 | 在真实数据中人工标注 5 个黄金坑案例 | 全部检出，误报率 < 20% |
| 特征覆盖率 | 在全量 episodes 上统计每个新特征的缺失率 | 所有新特征覆盖率 > 95% |
| 特征区分度 | 计算 Label 2 vs Label 0 在新特征上的 KS 统计量 | KS > 0.15（优于旧特征的 0.08） |
| 案例验证 | 在"孪生异动"案例对上，新特征值差异显著 | divergence_speed 差异 > 2x |

---

## Phase 2: 全市场排名序列特征

### 2.1 个股日涨幅全市场排名

**业务逻辑**: 真牛股在爆发前，已连续多日在全市场悄然走强。

**实现方案**:
```
新建文件: backend/super_trend_market_ranker.py

类: MarketDailyRanker
  - 初始化时一次性加载全市场日线数据（或分批加载）
  - 方法: compute_daily_rank(date) → 返回当日所有股票的涨幅排名百分位
  - 方法: get_stock_rank_series(stock_code, t0_date, lookback=30) → 返回该股票过去30天的每日排名

函数: extract_rank_features(rank_series)
输出: dict:
  - rs_rank_mean_5d: T0前5天排名均值
  - rs_rank_mean_10d: T0前10天排名均值
  - rs_rank_mean_20d: T0前20天排名均值
  - rs_rank_trend_20d: T0前20天排名的线性回归斜率
  - rs_rank_std_10d: T0前10天排名的标准差（稳定性）
```

**性能设计**:
- 全市场约 5000 只股票 × 2500 交易日 → 预计算排名缓存为 `market_daily_rank.pkl`
- 首次构建耗时约 30 分钟，后续增量更新
- 排名计算: 每日对全市场涨幅做 `rank(pct=True)`

### 2.2 价格行为序列编码（K线 n-gram）

**实现方案**:
```
函数: extract_price_pattern_features(df, t0_idx, lookback=10)
逻辑:
  1. T0前10天日线 → 三类符号: 阳(涨>0.5%), 阴(跌>0.5%), 平(其余)
  2. 生成 10 字符的符号序列，如 "阳阴阳阳平阴阳阳阴"
  3. 提取 2-gram 和 3-gram 频率
  4. 输出 top 5 最有区分度的 n-gram 特征（通过全量数据卡方检验筛选）

输出: dict:
  - pattern_2gram_XX: 各 2-gram 的出现频率（如 "阳阳", "阴阳" 等，共 9 种）
  - pattern_3gram_XXX: 各 3-gram 的出现频率（如 "阳阳阳", "阴阳阳" 等，共 27 种）
  - streak_max_bull: 最长连续阳线天数
  - streak_max_bear: 最长连续阴线天数
```

### Phase 2 测试计划

| 测试项 | 测试方法 | 通过标准 |
|--------|---------|---------|
| 排名计算正确性 | 选取 5 个日期，手算前 10 名涨幅股排名 | 完全一致 |
| 排名缓存性能 | 测试全量预计算的内存占用和耗时 | 内存 < 4GB, 耗时 < 60 分钟 |
| 排名特征覆盖率 | 在全量 episodes 上统计排名特征缺失率 | > 90%（部分新股不足30天历史） |
| 排名特征区分度 | Label 2 vs Label 0 的 rs_rank_mean_10d 分布对比 | Label 2 均值排名显著高于 Label 0 (t-test p<0.01) |
| n-gram 编码正确性 | 用已知K线序列手算 n-gram 频率 | 完全一致 |
| n-gram 区分度 | 卡方检验 Top 5 对 Label 2 有显著区分的 pattern | p < 0.05 |
| 增量更新 | 新增一天数据后，排名缓存正确更新 | 与全量重算一致 |

---

## Phase 3: 标签重构（从绝对涨幅到超额收益排名）

### 3.1 超额收益排序标签

**业务逻辑**: 放弃"MFE≥50%"绝对阈值，改为个股相对全市场的超额收益排名。

**实现方案**:
```
新建文件: backend/super_trend_label_builder.py

函数: compute_excess_return_labels(candidates_df, index_code='sh000001')
输入: candidates_df (含 stock_code, t0_date, future_mfe 列)
逻辑:
  1. 对每个异动样本，计算 T0后22日个股累计收益率（已有 future_mfe）
  2. 加载同期大盘指数 22 日收益率
  3. 超额收益 = future_mfe - index_return_22d
  4. 新标签 = 超额收益在全量异动样本中的百分位排名（0~1）
输出: candidates_df 新增列:
  - excess_return: 超额收益值
  - excess_rank: 百分位排名（0~1），作为排序模型目标
  - index_return_22d: 同期大盘收益（调试用）
```

### 3.2 过程稳定性惩罚

**业务逻辑**: 脉冲式冲高回落不是优质主升浪，需在标签中惩罚不稳定的路径。

**实现方案**:
```
函数: compute_path_stability(df, t0_idx, eval_days=22)
逻辑:
  1. 取 T0后22天每日收盘价，计算相对 T0 收盘价的每日涨幅序列
  2. 计算该序列的夏普比率 = mean / std
  3. 计算上行捕获率 = 上涨天数 / 总天数
  4. 计算路径平滑度 = 1 - (涨幅序列的变异系数)

输出: dict:
  - path_sharpe: 22天涨幅序列的夏普比率
  - path_up_capture: 上涨天数占比
  - path_smoothness: 路径平滑度

最终排序得分:
  final_score = excess_rank + λ * normalize(path_sharpe)
  λ 通过验证集调优（候选值: 0.1, 0.2, 0.3）
```

### 3.3 扫描器标签输出改造

**修改文件**: `backend/super_trend_scanner_v1_grok.py`

```
在 scan_single_stock() 中:
  - 保留原有 Label 0/1/2 逻辑（向后兼容）
  - 新增: 计算 path_sharpe, path_up_capture
  - 新增: 在 candidate dict 中加入 path_sharpe, path_up_capture

在 build_episodes() 中:
  - 调用新标签构建函数，追加 excess_rank 列
  - EpisodeSnapshot.meta 中追加新标签字段

新增函数: post_scan_relabel(all_candidates, df_market)
  - 在全量扫描完成后，统一计算超额收益排名
  - 这是因为排名需要全量数据作为参照系
```

### Phase 3 测试计划

| 测试项 | 测试方法 | 通过标准 |
|--------|---------|---------|
| 超额收益计算 | 手算 5 个样本的超额收益 | 误差 < 0.001 |
| 排名分布 | 绘制 excess_rank 分布直方图 | 近似均匀分布，不集中于 0 或 1 |
| 过程稳定性 | 对 10 只已知"脉冲股"和 10 只"流畅主升股"计算 path_sharpe | 流畅主升股 sharpe 显著高于脉冲股 |
| λ 调优 | 在验证集上扫描 λ∈[0.05, 0.1, 0.2, 0.3]，选 NDCG 最高的 | 有明确的 λ 最优点 |
| 新标签 vs 旧标签 | 对比旧 Label 2 样本在新排名中的分布 | Label 2 样本的 excess_rank 中位数 > 0.7 |
| 案例验证 | 股票A(+68%)排名应接近0.99，股票B(+3%)排名约0.45 | 符合预期 |

---

## Phase 4: 排序模型（LambdaRank）

### 4.1 模型架构

**核心变更**: 从分类 (binary cross-entropy) → 排序 (LambdaRank/NDCG)

**实现方案**:
```
新建文件: backend/super_trend_ranker_trainer.py

类: SuperTrendRanker
  __init__:
    - LightGBM params: objective='lambdarank', metric='ndcg'
    - eval_at: [10, 20, 50]
    - feature_columns: Phase1(均线束+黄金坑) + Phase2(排名+ngram) + 精选截面
  
  load_training_data():
    - 加载带 excess_rank 标签的训练数据
    - 按 t0_date 时序排序
    - 按交易日分组（同一天异动的股票为一组）
  
  train(X, y, groups, test_size=0.2):
    - 时序切割: 前 80% 训练，后 20% 测试
    - lgb.train() with group 参数
    - 输出 NDCG@10, NDCG@20, NDCG@50
  
  evaluate(X_test, y_test, groups_test):
    - NDCG 指标
    - Top N 平均未来收益
    - 与随机选股基准对比
  
  predict(X):
    - 输出排序得分（不是概率）
  
  save_model() / load_model():
    - pickle 序列化
```

### 4.2 分组策略

- **分组键**: `t0_date`（同一天异动的股票互相比较）
- **组大小**: 每组 5~50 只股票（取决于当天异动数量）
- **过滤**: 丢弃组大小 < 3 的日期（排序无意义）

### 4.3 特征清单（预计 ~45 个）

| 类别 | 特征 | 数量 | 来源 |
|------|------|------|------|
| 精选截面 | bias_ma60, vol_breakout_ratio, price_position_120d, vol_turnover_ratio, volume_percentile_120d, atr_percentile, boll_width, rs_20d | 8 | 旧系统保留 |
| 均线束 | ma_glue_max_days, ma_glue_recency, ma_divergence_speed, ma_convergence_flag | 4 | Phase 1.1 |
| 黄金坑 | washout_ma60_flag, washout_ma60_depth, washout_ma60_recovery_days, washout_ma20_flag, washout_ma20_depth, lower_shadow_count | 6 | Phase 1.2 |
| 全市场排名 | rs_rank_mean_5d, rs_rank_mean_10d, rs_rank_mean_20d, rs_rank_trend_20d, rs_rank_std_10d | 5 | Phase 2.1 |
| K线 n-gram | pattern_2gram_XX (9种), pattern_3gram_XXX (27种), streak_max_bull, streak_max_bear | 38 | Phase 2.2 |

> 注: n-gram 特征维度较高(36种)，训练时可通过卡方检验筛选 Top 10~15，最终总特征控制在 30~40 个。

### Phase 4 测试计划

| 测试项 | 测试方法 | 通过标准 |
|--------|---------|---------|
| 分组正确性 | 检查每个 group 内的样本数 | 每组 ≥ 3 个样本 |
| NDCG 指标 | 训练日志中 NDCG@10/20/50 | NDCG@20 > 0.5（随机=0.5以下） |
| 时序交叉验证 | 5-fold TimeSeriesSplit | 各 fold NDCG 标准差 < 0.1 |
| 特征重要性 | 输出 Top 10 特征 | 新特征（均线束/排名）至少 3 个进入 Top 10 |
| 案例验证 | 检查 3 组"孪生异动"的排序结果 | 真主升股排名 > 假突破股 |
| 与旧模型对比 | 同一测试集上，排序模型 Top 200 平均 future_mfe vs 旧分类模型 | 排序模型 Top 200 平均 MFE > 旧模型 |
| 过拟合检查 | 训练集 vs 测试集 NDCG 差距 | 差距 < 0.15 |

---

## Phase 5: 端到端回测框架

### 5.1 Top N 等权买入模拟

**实现方案**:
```
新建文件: backend/super_trend_rank_backtester.py

类: RankBacktester
  __init__(model_path, holding_days=22):
    - 加载训练好的 Ranker 模型
  
  run(dates, top_n=20):
    对每个交易日:
      1. 获取当天所有异动股票
      2. 模型打分 → 排序 → 取 Top N
      3. 过滤: 涨停买不到的、T+1 开盘跳空>5%的
      4. 等权买入
      5. 持有 22 天或触发止损(-8%)/止盈(+30%)
      6. 记录每笔交易的进出场、收益、最大回撤
    
    输出:
      - 净值曲线
      - 年化收益、夏普比率、最大回撤
      - 逐年收益分解
      - 与基准（全市场异动日等权）对比
  
  compare_with_old_model(old_model_path):
    - 旧模型（分类）在同期的 Top 200 精确率和收益
    - 新模型（排序）在同期的 Top N 收益
    - 输出对比表格
```

### 5.2 交易规则

| 规则 | 参数 |
|------|------|
| 持仓天数 | 22 个交易日（与 MFE 评估窗口一致） |
| 止损 | -8%（基于 MAE P5 分析） |
| 止盈 | +30% |
| T+1 过滤 | 次日开盘跳空 > 5% 则放弃（买不到） |
| 仓位 | 等权分配，每日最多持有 20 只 |
| 手续费 | 双边 0.15%（含印花税） |

### Phase 5 测试计划

| 测试项 | 测试方法 | 通过标准 |
|--------|---------|---------|
| 回测引擎正确性 | 用 3 个已知案例手算收益 | 与引擎输出误差 < 0.1% |
| T+1 过滤逻辑 | 统计被过滤的信号数量和原因分布 | 涨停过滤占比 < 10% |
| 净值曲线合理性 | 检查是否存在异常跳变 | 日波动 < 5% |
| 基准对比 | Top 20 组合 vs 全市场异动等权 | 超额收益 > 5% |
| 案例验证 | 股票A必须在某日 Top 20 中，股票B不得进入 | 符合预期 |
| 逐年分解 | 检查各年度收益 | 至少 3/5 年正收益 |
| 与旧模型对比 | 同期同数据集的收益对比 | 新模型夏普比率 > 旧模型 |

---

## 执行顺序与依赖关系

```
Phase 1 (时序特征)  ─┐
                      ├──→ Phase 4 (排序模型) ──→ Phase 5 (回测)
Phase 2 (排名特征)  ─┤
                      │
Phase 3 (标签重构)  ─┘
```

- Phase 1 和 Phase 2 可以**并行开发**
- Phase 3 需要全量扫描数据，依赖 Phase 1/2 的特征写入
- Phase 4 依赖 Phase 1/2/3 全部完成
- Phase 5 依赖 Phase 4 的模型

**建议执行顺序**: Phase 3 → Phase 1 → Phase 2 → Phase 4 → Phase 5

理由: Phase 3 (标签重构) 改动最小，可快速验证新标签的分布是否合理，为后续特征工程提供方向。

---

## 关键风险与缓解措施

| 风险 | 影响 | 缓解 |
|------|------|------|
| 全市场排名计算耗时过长 | Phase 2 延期 | 预计算缓存 + 增量更新；或先用 Top 1000 股票试点 |
| n-gram 特征维度爆炸(36种) | Phase 4 过拟合 | 卡方检验筛选 Top 15；L1 正则化 |
| LambdaRank 组大小不均 | 训练不稳定 | 截断过大组(>50)为随机子组；丢弃过小组(<3) |
| 超额收益排名受极端值影响 | Phase 3 标签噪声 | 使用 winsorize（1%/99%缩尾）后再排名 |
| 新特征覆盖率不足(<95%) | 有效样本减少 | 缺失值用中位数填充；或调整回溯窗口 |

---

## 全局验收标准

**项目成功的唯一判据**:

> 在测试集的每个交易日，排序模型给出的 Top 20 股票池，其未来 22 天平均收益
> **显著跑赢**（t-test p<0.05）全市场异动日等权买入的基准收益，
> 且夏普比率 > 1.0。

不满足此条件，则需要回到 Phase 1/2 迭代特征工程。
