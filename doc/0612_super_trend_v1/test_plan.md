# Super Trend V1 测试计划

## 总览

本文档为改造计划的完整测试方案，覆盖 5 个 Phase 的单元、集成和端到端测试。

**测试原则**:
- 每个 Phase 独立可验收，交付物明确
- 用真实"孪生异动"案例贯穿全部测试
- 数据驱动：所有通过标准有量化指标

---

## 贯穿测试案例："孪生异动"

从现有 episodes 数据中挑选截面特征相似但结局迥异的股票对，作为每个阶段的"试金石"。

### 案例选取标准

| 条件 | 要求 |
|------|------|
| T0 截面特征相似度 | bias_ma60, vol_breakout_ratio, price_position_120d 三者差异 < 10% |
| 未来结局差异 | future_mfe 差异 > 30 个百分点 |
| 时间跨度 | 至少覆盖 2020-2024 年各 1 对 |
| 总数量 | 至少 5 对（10 只股票） |

### 案例选取方法

```python
# 在 post_scan_relabel 完成后执行
def find_twin_cases(training_df, top_pct=0.25):
    """从全量数据中筛选孪生异动对"""
    from itertools import combinations
    
    # 取截面特征相似的前 25% 样本对
    feature_cols = ['bias_ma60', 'vol_breakout_ratio', 'price_position_120d']
    df = training_df[feature_cols + ['future_mfe', 't0_date', 'stock_code']].dropna()
    
    # 标准化特征后计算欧氏距离
    from sklearn.preprocessing import StandardScaler
    scaler = StandardScaler()
    scaled = scaler.fit_transform(df[feature_cols])
    
    cases = []
    for i in range(len(df)):
        for j in range(i+1, min(i+100, len(df))):
            dist = np.linalg.norm(scaled[i] - scaled[j])
            mfe_diff = abs(df.iloc[i]['future_mfe'] - df.iloc[j]['future_mfe'])
            if dist < 0.5 and mfe_diff > 0.30:  # 特征近、结局远
                cases.append({
                    'stock_a': df.iloc[i]['stock_code'],
                    'date_a': df.iloc[i]['t0_date'],
                    'mfe_a': df.iloc[i]['future_mfe'],
                    'stock_b': df.iloc[j]['stock_code'],
                    'date_b': df.iloc[j]['t0_date'],
                    'mfe_b': df.iloc[j]['future_mfe'],
                    'feature_dist': dist,
                })
    
    # 按特征相似度排序，取 Top 10
    cases.sort(key=lambda x: x['feature_dist'])
    return cases[:10]
```

---

## Phase 1 测试计划: 时序特征工程

### T1.1 均线束特征单元测试

| # | 测试项 | 输入 | 期望输出 | 验证方法 |
|---|--------|------|---------|---------|
| 1 | 均线离散度公式 | MA5=10, MA10=10, MA20=10, MA60=10, close=10 | dispersion = 0.0 | 手算对比 |
| 2 | 均线离散度公式 | MA5=11, MA10=10, MA20=9, MA60=8, close=10 | dispersion = std([11,10,9,8])/10 ≈ 0.112 | 手算对比 |
| 3 | 粘合天数-全部粘合 | 20天离散度均为 0.01 | glue_max_days = 20 | 直接断言 |
| 4 | 粘合天数-无粘合 | 20天离散度均为 0.05 | glue_max_days = 0 | 直接断言 |
| 5 | 粘合天数-中段粘合 | 前5天>0.03, 中10天<0.02, 后5天>0.03 | glue_max_days = 10 | 直接断言 |
| 6 | 发散速度 | 5天离散度: [0.01, 0.015, 0.02, 0.025, 0.03] | slope ≈ 0.005/day (linregress) | scipy.linregress 对比 |
| 7 | convergence_flag | 10天内存在离散度<0.015的窗口 | True | 直接断言 |
| 8 | T0_idx 边界 | t0_idx < 20 | 返回空 dict | 直接断言 |

### T1.2 黄金坑特征单元测试

| # | 测试项 | 输入 | 期望输出 | 验证方法 |
|---|--------|------|---------|---------|
| 1 | 标准黄金坑 | T-8天 close<MA60, T-7天 close>MA60 | washout_ma60_flag=1, recovery=1 | 构造数据 |
| 2 | 深度破位 | close 跌破 MA60 达 5% | washout_ma60_depth=0.05 | 手算对比 |
| 3 | 无破位 | 20天内 close 始终 > MA60 | washout_ma60_flag=0 | 直接断言 |
| 4 | 多次破位 | 3次跌破MA60 | 取最大 depth，recovery 取最后一次 | 构造数据 |
| 5 | 长下影线 | 下影线长度 > 实体2倍 | lower_shadow_count +1 | 构造数据 |
| 6 | MA20/MA60 同时检测 | 分别检测两条均线 | 两组独立特征 | 构造数据 |

### T1.3 特征覆盖率集成测试

```
测试环境: 全量 episodes (data/result/super_trend/episodes/)
测试步骤:
  1. 加载所有 episodes_collection.pkl
  2. 对每个 episode 的 raw_data['daily'] 重算新特征
  3. 统计每个新特征的 NaN 比例
  
通过标准:
  - ma_glue_max_days: 缺失率 < 3%（仅 t0_idx<20 的样本）
  - washout_ma60_flag: 缺失率 < 5%
  - ma_divergence_speed: 缺失率 < 5%
  - 所有新特征: 缺失率 < 5%
```

### T1.4 孪生案例区分度测试

```
测试步骤:
  1. 在 5 对孪生案例上计算所有新特征
  2. 对比每对中真主升 vs 假突破的新特征值
  3. 计算新旧特征在 Label 2 vs Label 0 上的 KS 统计量

通过标准:
  - ma_divergence_speed: 真主升 > 假突破（至少 3/5 对）
  - washout_ma60_flag: 真主升中至少 2 对触发，假突破中 0 对触发
  - 新特征平均 KS > 旧特征平均 KS
```

---

## Phase 2 测试计划: 全市场排名序列

### T2.1 排名计算单元测试

| # | 测试项 | 输入 | 期望输出 |
|---|--------|------|---------|
| 1 | 单日排名 | 5只股票涨幅: [5%, 3%, 1%, -1%, -3%] | rank = [1.0, 0.75, 0.5, 0.25, 0.0] |
| 2 | 停牌处理 | 某股当日 volume=0 | rank = NaN |
| 3 | 涨停处理 | 某股涨幅=10%（涨停） | rank = 1.0 |
| 4 | 新股首日 | 上市首日涨幅 44% | rank 正常计算 |

### T2.2 排名缓存性能测试

```
测试步骤:
  1. 全量预计算 2020-01-01 至 2026-06-12 的每日排名
  2. 记录: 耗时、内存峰值、磁盘文件大小
  
通过标准:
  - 耗时 < 60 分钟（首次全量构建）
  - 内存峰值 < 4 GB
  - 磁盘文件 < 2 GB
  - 增量更新（新增1天）耗时 < 5 分钟
```

### T2.3 排名序列特征集成测试

```
测试步骤:
  1. 选取 10 只已知牛股（未来 MFE > 50%）和 10 只已知弱股（MFE < 5%）
  2. 计算 rs_rank_mean_5d, rs_rank_mean_10d, rs_rank_mean_20d
  3. 对比两组分布

通过标准:
  - 牛股 rs_rank_mean_10d 中位数 > 0.7
  - 弱股 rs_rank_mean_10d 中位数 < 0.5
  - 两组 t-test p < 0.05
```

### T2.4 K线 n-gram 编码测试

| # | 测试项 | 输入 | 期望输出 |
|---|--------|------|---------|
| 1 | 全阳序列 | 10天涨幅均>0.5% | streak_max_bull=10, "阳阳"频率=1.0 |
| 2 | 交替序列 | 阳阴阳阴阳阴... | "阴阳"频率≈0.5, streak_max_bull=1 |
| 3 | 平盘处理 | 涨幅=0.1%（<0.5%阈值） | 归类为"平" |
| 4 | 边界处理 | T0前不足10天 | 按实际天数计算 |

### T2.5 n-gram 区分度测试

```
测试步骤:
  1. 在全量数据上计算所有 2-gram 和 3-gram 特征
  2. 对每个 n-gram 做卡方检验（Label 2 vs Label 0+1）
  3. 输出 Top 10 最有区分度的 pattern

通过标准:
  - 至少 5 个 n-gram 的卡方检验 p < 0.05
  - Top 1 pattern 在 Label 2 中出现频率 > Label 0 的 2 倍
```

---

## Phase 3 测试计划: 标签重构

### T3.1 超额收益计算测试

| # | 测试项 | 输入 | 期望输出 |
|---|--------|------|---------|
| 1 | 标准计算 | future_mfe=0.68, index_22d=0.021 | excess_return=0.659 |
| 2 | 负超额 | future_mfe=0.03, index_22d=0.05 | excess_return=-0.02 |
| 3 | 指数缺失 | 某天无指数数据 | excess_return=NaN |
| 4 | 极端值 | future_mfe=5.0（极端牛股） | winsorize 后不超过 P99 |

### T3.2 排名分布测试

```
测试步骤:
  1. 在全量异动样本上计算 excess_rank
  2. 绘制直方图
  3. 检查分布形态

通过标准:
  - 分布近似均匀（非极端偏态）
  - 10%分位桶的样本数差异 < 30%
  - 无大量样本聚集于 0 或 1
```

### T3.3 过程稳定性测试

| # | 测试项 | 输入 | 期望输出 |
|---|--------|------|---------|
| 1 | 流畅主升 | 22天每日涨幅 +1% | path_sharpe 高, up_capture=1.0 |
| 2 | 脉冲式 | 第3天+15%, 之后连跌 | path_sharpe 低, up_capture<0.5 |
| 3 | 震荡 | 日涨幅交替 +/-2% | path_smoothness 低 |

### T3.4 新旧标签一致性测试

```
测试步骤:
  1. 对比旧 Label 2 样本在新 excess_rank 中的分布
  2. 对比旧 Label 0 样本在新 excess_rank 中的分布
  
通过标准:
  - 旧 Label 2 的 excess_rank 中位数 > 0.70
  - 旧 Label 0 的 excess_rank 中位数 < 0.40
  - 两组差异显著（Mann-Whitney p < 0.001）
```

### T3.5 λ 调优测试

```
测试步骤:
  1. 在验证集上扫描 λ ∈ [0.05, 0.1, 0.15, 0.2, 0.25, 0.3]
  2. 对每个 λ 值，计算 final_score = excess_rank + λ * normalize(path_sharpe)
  3. 用 LightGBM Ranker 快速训练，记录 NDCG@20

通过标准:
  - 存在明确的 λ 最优点（非边界值）
  - 最优 λ 的 NDCG 比 λ=0 提升 > 0.02
```

---

## Phase 4 测试计划: 排序模型

### T4.1 分组正确性测试

```
测试步骤:
  1. 加载训练数据，按 t0_date 分组
  2. 检查每组大小
  3. 验证 group 参数与 LightGBM 期望一致

通过标准:
  - 无组大小 < 3（已被过滤）
  - 组总数与唯一交易日数一致
  - 总样本数与训练数据行数一致
```

### T4.2 训练指标测试

| 指标 | 通过标准 | 说明 |
|------|---------|------|
| NDCG@10 | > 0.4 | 排序质量核心指标 |
| NDCG@20 | > 0.5 | 选股池大小对应指标 |
| NDCG@50 | > 0.6 | 宽松筛选指标 |
| 训练 vs 验证 NDCG 差距 | < 0.15 | 过拟合检查 |
| 收敛性 | 训练在 500 轮内停止 | early stopping 有效 |

### T4.3 时序交叉验证

```
测试步骤:
  1. 5-fold TimeSeriesSplit
  2. 每 fold 独立训练 Ranker
  3. 记录各 fold 的 NDCG@20

通过标准:
  - 各 fold NDCG 标准差 < 0.10
  - 无单 fold NDCG < 0.3（严重退化）
  - 后 2 个 fold（近期数据）NDCG 不低于前 3 个 fold 均值
```

### T4.4 特征重要性分析

```
测试步骤:
  1. 输出 gain 类型特征重要性 Top 15
  2. 分类统计：截面特征 vs 时序特征 vs 排名特征

通过标准:
  - Top 10 中至少有 3 个是新时序特征
  - 排名特征至少 1 个进入 Top 10
  - 旧截面特征不全占 Top 5（说明新特征有增量信息）
```

### T4.5 孪生案例排序测试

```
测试步骤:
  1. 在 5 对孪生异动案例上，模型打分
  2. 对比每对中真主升 vs 假突破的得分

通过标准:
  - 至少 4/5 对中，真主升得分 > 假突破
  - 得分差异 > 20%（相对值）
```

### T4.6 与旧模型对比测试

```
测试步骤:
  1. 同一测试集上，旧分类模型输出 Top 200 概率
  2. 新排序模型输出 Top 200 得分
  3. 对比两组的平均 future_mfe

通过标准:
  - 新模型 Top 200 平均 MFE > 旧模型 Top 200 平均 MFE
  - 新模型 Top 50 平均 MFE > 旧模型 Top 50 平均 MFE
  - 改善幅度 > 10%（相对值）
```

---

## Phase 5 测试计划: 端到端回测

### T5.1 回测引擎正确性测试

| # | 测试项 | 输入 | 期望输出 |
|---|--------|------|---------|
| 1 | 单只股票收益计算 | 买入价10元, 22天后12元, 手续费0.15% | 收益 = 19.7% |
| 2 | 止损触发 | 买入价10元, 第5天跌到9.2元(-8%) | 第5天卖出, 收益≈-8.15% |
| 3 | 止盈触发 | 买入价10元, 第8天涨到13元(+30%) | 第8天卖出, 收益≈29.85% |
| 4 | T+1过滤 | T0收盘10元, T+1开盘10.6元(+6%) | 该信号被过滤, 不买入 |
| 5 | 等权分配 | 20只股票, 总资金100万 | 每只5万 |

### T5.2 净值曲线合理性测试

```
测试步骤:
  1. 运行完整回测，输出每日净值
  2. 检查净值序列

通过标准:
  - 无单日跳变 > 10%（除非极端行情）
  - 无 NaN 或负值
  - 最大回撤 < 40%
  - 交易笔数 > 100（统计显著）
```

### T5.3 基准对比测试

```
基准策略: 全市场异动日等权买入（每日买入所有异动信号，等权持有22天）

通过标准:
  - Top 20 组合年化收益 > 基准年化收益 + 5%
  - Top 20 组合夏普比率 > 基准夏普比率
  - Top 20 组合最大回撤 < 基准最大回撤
  - t-test: 组合日收益 vs 基准日收益, p < 0.05
```

### T5.4 新旧模型回测对比

```
测试步骤:
  1. 旧模型: 每日取 Top 200 概率最高的 20 只，等权买入
  2. 新模型: 每日取 Top 20 得分最高的，等权买入
  3. 同一测试期，对比两者

输出指标:
  - 年化收益、夏普比率、最大回撤、胜率
  - 逐年收益分解
  - 月度收益热力图

通过标准:
  - 新模型夏普比率 > 旧模型夏普比率
  - 新模型胜率 > 旧模型胜率
```

### T5.5 案例级验证

```
测试步骤:
  1. 在 5 对孪生案例中，检查真主升股是否进入当日 Top 20
  2. 检查假突破股是否被排除在 Top 20 之外

通过标准:
  - 真主升股: 至少 3/5 进入 Top 20
  - 假突破股: 至少 4/5 未进入 Top 20
```

---

## 回归测试（全流程）

### 每次代码变更后的必检项

1. **扫描器回归**: 运行 5 只测试股票扫描，检查候选点数量与标签分布无异常变化
2. **特征覆盖率回归**: 全量 episodes 上新特征缺失率不升高
3. **训练回归**: 快速训练（50轮），NDCG 不低于历史最佳 - 0.05
4. **数据一致性**: 新旧特征在同一 episode 上的值不冲突

### 自动化测试脚本

```
backend/tests/
  test_feature_extractor_v2.py     # Phase 1 单元测试
  test_market_ranker.py            # Phase 2 单元测试
  test_label_builder.py            # Phase 3 单元测试
  test_ranker_trainer.py           # Phase 4 集成测试
  test_rank_backtester.py          # Phase 5 集成测试
  test_twin_cases.py               # 孪生案例测试（全流程）
  test_regression.py               # 回归测试
```

---

## 测试执行时间表

| 阶段 | 开发完成后测试时间 | 关键依赖 |
|------|-------------------|---------|
| Phase 1 | 1 天 | 无 |
| Phase 2 | 2 天（含性能测试） | 全市场数据加载 |
| Phase 3 | 1 天 | Phase 1/2 特征写入 |
| Phase 4 | 2 天（含 CV） | Phase 1/2/3 完成 |
| Phase 5 | 2 天 | Phase 4 模型完成 |
| **总计** | **~8 天** | |
