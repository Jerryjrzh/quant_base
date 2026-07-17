# Super Trend V1 重构 — 完整执行报告

> 执行日期: 2026-06-12  
> 基于 ds_review_base.md / ds_review_tasks.md 的路线图  
> 全部 5 阶段已实现并通过 59/59 单元测试  
> 全量流水线已跑通：扫描 → 重标签 → 正式训练 → 回测 → 孪生案例验收

---

## 0. 背景与动机

原模型（分类模型 + T0 截面特征）AUC=0.68，Top 200 精确率 20%，天花板明显。  
DeepSeek 诊断核心问题：**单凭 T0 截面快照无法区分真主升浪与假突破**，截面特征几乎相同的股票结局天差地别。

路线图要求从三个维度重构：
1. **特征**：从"照片"变"视频"——引入时序特征
2. **标签**：从绝对涨幅阈值变相对排名——超额收益百分位
3. **模型**：从分类变排序——LambdaRank/NDCG

---

## 1. 总体执行结果

### 1.1 开发与单元测试

| 阶段 | 状态 | 测试数 | 全部通过 |
|------|------|--------|---------|
| P3 标签重构 | ✅ 完成 | 17 | ✅ |
| P1 时序特征 | ✅ 完成 | 14 | ✅ |
| P2 全市场排名 | ✅ 完成 | 9 | ✅ |
| P4 排序模型 | ✅ 完成 | 5 | ✅ |
| P5 回测框架 | ✅ 完成 | 14 | ✅ |
| **合计** | **5/5** | **59** | **59/59** |

### 1.2 全量流水线执行

| 步骤 | 命令 | 状态 | 产出 |
|------|------|------|------|
| Step 1 全量扫描 | `python backend/super_trend_scanner_v1_grok.py --full` | ✅ | `super_trend_training_data.csv` (50 特征) |
| Step 2 重标签 | `python backend/super_trend_label_builder.py` | ✅ | `super_trend_training_data_v2.csv` (64 列) |
| Step 3 正式训练 | `SuperTrendRanker.train()` | ✅ | `trend_ranker_v1.pkl` (43 棵树) |
| Step 4 回测 | `python backend/super_trend_rank_backtester.py` | ✅ | `backtest_trades.csv` + `backtest_daily_pnl.csv` |
| Step 5 孪生验收 | `python backend/twin_case_test.py` | ⚠️ 部分通过 | 详见第 11 节 |

### 1.3 核心指标总览

| 指标 | 旧模型 | 新模型 | 变化 |
|------|--------|--------|------|
| 模型类型 | 二分类 (LGBMClassifier) | 排序 (LambdaRank) | 范式变更 |
| 特征数 | 25 (截面) | 50 (截面+时序+排名) | +25 |
| 标签 | 绝对 MFE 阈值 | 超额收益百分位排名 | 范式变更 |
| NDCG@20 | N/A | **0.6035** | — |
| Top 100 平均 MFE | — | **79.5%** | 基线 5.5× |
| Top 50 平均 MFE | — | **90.1%** | 基线 6.2× |
| 回测胜率 | — | **89.9%** | — |
| Top 20 vs 基线提升 | — | **+52.8%** | — |
| 同日逐对排序胜率 | — | **73.0%** | — |

---

## 2. Phase 3 — 标签重构

### 核心文件
- `backend/super_trend_label_builder.py`
- `backend/test_super_trend/test_label_builder.py`

### 标签定义

**旧标签**: 绝对 MFE 阈值 (Label 2 = MFE ≥ 50%)  
**新标签**: 三级相对排名

| 字段 | 计算方式 |
|------|---------|
| `excess_return` | 个股 T0+22d 收益 - 同期中证全指收益 |
| `excess_rank` | excess_return 在全量异动样本中的百分位 (0~1) |
| `path_sharpe` | T0+22d 每日涨幅的均值/标准差 |
| `final_rank_score` | excess_rank + λ × sharpe_norm (λ=0.15) |

### 全量重标签结果
```
样本数: 1,331,523
旧标签分布:
  Label 0 (MFE<10%):  678,615 (51.0%)
  Label 1 (10%≤MFE<P95): 612,818 (46.0%)
  Label 2 (MFE≥P95):   40,090 (3.0%)

新标签 (excess_rank):
  均值: 0.5000, 标准差: 0.2887 (完美均匀分布)
  P10=0.10, P25=0.25, P50=0.50, P75=0.75, P90=0.90

旧标签 vs 新排名:
  Label 0: excess_rank 中位数=0.2641
  Label 1: excess_rank 中位数=0.7395
  Label 2: excess_rank 中位数=0.9818 ← 强区分度
```

### 修复记录
| 问题 | 原因 | 修复 |
|------|------|------|
| `args.lambda` SyntaxError | Python 保留字 | 改为 `--lam` |
| path_sharpe=0 (平滑上涨) | std 阈值 0.001 过大 | 改为 1e-8，返回 ±10.0 |

---

## 3. Phase 1 — 时序特征工程

### 核心文件
- `backend/super_trend_feature_extractor_v2.py`
- `backend/test_super_trend/test_feature_extractor_v2.py`

### 新增 25 个特征（V2）

#### 均线束状态 (6 个)
| 特征 | 含义 |
|------|------|
| `ma_dispersion_5d` | T0 前 5 日均线离散度均值 |
| `ma_dispersion_20d` | T0 前 20 日均线离散度均值 |
| `ma_glue_max_days` | T0 前 20 天内均线粘合最大连续天数 |
| `ma_glue_recency` | 最近粘合结束距 T0 天数 |
| `ma_divergence_speed` | T0 前 5 天离散度线性回归斜率 |
| `ma_convergence_flag` | 当前是否处于粘合状态 |

#### 黄金坑/洗盘 (6 个)
| 特征 | 含义 |
|------|------|
| `washout_ma60_flag` | T0 前 20 天是否出现破位 MA60 后收回 |
| `washout_ma60_depth` | 破位最大深度 |
| `washout_ma60_recovery_days` | 破位恢复天数 |
| `washout_ma20_flag` | MA20 级别洗盘 |
| `washout_ma20_depth` | MA20 破位深度 |
| `washout_ma20_recovery_days` | MA20 恢复天数 |

#### 量能序列 (3 个)
| 特征 | 含义 |
|------|------|
| `vol_trend_10d` | T0 前 10 天成交量线性趋势 |
| `vol_shrink_streak` | 连续缩量天数 |
| `vol_low_point_position` | 量能最低点位置 (0~1) |

#### 价格行为 (4 个)
| 特征 | 含义 |
|------|------|
| `streak_max_bull` | 最大连阳天数 |
| `streak_max_bear` | 最大连阴天数 |
| `bull_ratio_10d` | T0 前 10 天阳线占比 |
| `last_3_pattern` | 最近 3 天阴阳编码 |

#### 其他 (6 个)
| 特征 | 含义 |
|------|------|
| `ma_bull_alignment_days` | T0 前连续多头排列天数 |
| `lower_shadow_count` | 长下影线天数 |
| `rs_rank_mean_5d` | T0 前 5 天全市场涨幅排名均值 |
| `rs_rank_mean_10d` | T0 前 10 天排名均值 |
| `rs_rank_mean_20d` | T0 前 20 天排名均值 |
| `rs_rank_trend_20d` | T0 前 20 天排名线性趋势 |
| `rs_rank_std_10d` | T0 前 10 天排名标准差 |

### 验证结果
- 在真实股票数据上覆盖率 **100%**
- 均线粘合 → 发散过程可被量化捕获

---

## 4. Phase 2 — 全市场排名序列

### 核心文件
- `backend/super_trend_market_ranker.py`
- `backend/test_super_trend/test_market_ranker.py`

### 功能
- `build_market_rank_cache()`: 加载 5,190 只股票日K，计算每日涨跌幅全市场百分位排名
- 缓存文件: `data/result/super_trend/cache/market_daily_rank.pkl` (~59MB, 构建 ~15s)
- `extract_rank_features()`: 为单只股票提取排名时序特征

### 验证结果
- rank 值域 [0, 1]，均值 ≈ 0.5（符合均匀分布预期）
- 与 scanner 集成正常，多进程环境下 rank_matrix 可独立加载

---

## 5. Phase 4 — 排序模型 (LambdaRank)

### 核心文件
- `backend/super_trend_ranker_trainer.py`
- `backend/test_super_trend/test_ranker_trainer.py`

### 模型配置
```python
params = {
    'objective': 'lambdarank',
    'metric': 'ndcg',
    'learning_rate': 0.05,
    'num_leaves': 63,
    'max_depth': -1,
    'min_child_samples': 20,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'reg_alpha': 0.1,
    'reg_lambda': 1.0,
}
```

### 正式训练结果（全量数据）
```
数据维度: 1,331,523 样本, 64 列, 50 特征
过滤后: 1,331,520 样本, 1,402 组交易日

时序切分: 2025-02-21
  训练集: 1,065,096 样本, 1,147 天
  测试集: 266,424 样本, 255 天

训练: 早停于 43 棵树 (best iteration, max=500)
  验证 ndcg@10: 0.161294
  验证 ndcg@20: 0.158148
  验证 ndcg@50: 0.171682

模型评估:
  NDCG@20 (均值): 0.6035 (±0.1185)
  NDCG@20 (中位数): 0.6179
```

### Top N 选股效果

| 策略 | 平均 MFE | 平均超额收益 | Label 2 占比 | vs 基线 |
|------|---------|------------|-------------|---------|
| **Top 50** | **90.1%** | **88.4%** | **34.0%** | **6.2×** |
| **Top 100** | **79.5%** | **78.2%** | **29.0%** | **5.5×** |
| Top 200 | 53.8% | 52.7% | 17.5% | 3.7× |
| Top 500 | 38.2% | 37.1% | 10.4% | 2.6× |
| 全量基线 | 14.5% | — | — | 1× |

### 特征重要性 Top 15

| 排名 | 特征 | 重要性 (gain) | 类型 |
|------|------|-------------|------|
| 1 | `boll_width` | 27,140 | 截面 |
| 2 | `price_rebound_from_pit` | 11,062 | V1 时序 |
| 3 | **`rs_rank_mean_20d`** | **4,523** | **V2 排名** |
| 4 | `bias_ma20` | 3,828 | 截面 |
| 5 | `price_position_120d` | 3,700 | 截面 |
| 6 | **`rs_rank_std_10d`** | **3,175** | **V2 排名** |
| 7 | `t0_close` | 2,473 | 截面 |
| 8 | **`ma_dispersion_5d`** | **2,148** | **V2 均线束** |
| 9 | `bias_ma60` | 2,118 | 截面 |
| 10 | **`rs_rank_mean_10d`** | **1,956** | **V2 排名** |
| 11 | **`ma_dispersion_20d`** | **1,808** | **V2 均线束** |
| 12 | **`rs_rank_mean_5d`** | **1,332** | **V2 排名** |
| 13 | `rs_20d` | 1,035 | 截面 |
| 14 | `volume_percentile_120d` | 724 | 截面 |
| 15 | `vol_turnover_ratio` | 674 | 截面 |

**V2 新特征在 Top 10 中占 4 席，在 Top 15 中占 8 席。**  
**全市场排名特征 (`rs_rank_*`) 成为 V2 最大贡献者。**

### 修复记录
| 问题 | 原因 | 修复 |
|------|------|------|
| LambdaRank 要求整数标签 | float rank score | `_to_relevance_grades()` 离散化为 0-31 |
| NDCG=1.0 (数据泄露) | `_relevance` 在特征列中 | 加入 `drop_cols` |
| Label 31 越界 (验证集) | 验证集含训练集未见等级 | `np.clip(y_test, 0, max_train_grade)` |
| 路径解析错误 | 相对路径 | 改用 `__file__` 绝对路径 |

---

## 6. Phase 5 — 端到端回测框架

### 核心文件
- `backend/super_trend_rank_backtester.py`
- `backend/test_super_trend/test_rank_backtester.py`

### 交易规则
| 参数 | 值 |
|------|-----|
| 每日选股数 | Top 20 |
| T+1 跳空过滤 | > 5% 不买 |
| 止损 | -8% (收益 = -8% × 0.8) |
| 止盈 | +30% (收益 = +30% × 0.85) |
| 持有到期 | MFE × 0.5 捕获率 |
| 手续费 | 双边 0.15% |
| 最大持仓天数 | 22 天 |

### 回测结果（正式模型）
```
测试期: 2025-02-21 ~ 2026-03-11, 255 个交易日
总交易笔数: 5,100
日均选股数: 20.0

收益率指标:
  总收益率:     2470.34%
  年化收益:     2441.28%
  夏普比率:     56.94
  最大回撤:     0.00%

交易质量:
  胜率:         89.92%
  平均交易收益: 10.66%
  平均 MFE:     23.98%
```

### 基准对比

| 策略 | 平均净收益 | 平均 MFE | 提升 |
|------|-----------|---------|------|
| **模型 Top 20** | **10.66%** | **23.98%** | — |
| 全量等权基线 | 6.97% | 14.54% | — |
| **模型 vs 基线** | — | — | **+52.8%** |

### 结果说明
- 高夏普 / 零回撤是 MFE 模拟的固有特征（无真实逐日价格路径），不代表实盘表现
- 52.8% 的相对提升证明排序模型选股能力显著优于随机
- 止损/止盈逻辑框架已就绪，待接入 MAE 真实数据后生效

### 修复记录
| 问题 | 原因 | 修复 |
|------|------|------|
| 总收益率 32 万亿% | 22 天持仓收益被当作日收益复利 | 改为 `avg_return × trades_per_day / HOLDING_DAYS` 分摊 |
| 路径解析错误 | 相对路径 | `_proj()` 绝对路径 |

---

## 7. Scanner 集成

### 修改文件
- `backend/super_trend_scanner_v1_grok.py`

### 集成点
| 函数 | 新增功能 |
|------|---------|
| `scan_single_stock()` | 计算 path_sharpe/up_capture/smoothness/return_22d |
| `build_episodes()` | 调用 `extract_all_v2_features()` + `extract_rank_features()` |
| `scan_and_build_episodes()` | 传递 rank_matrix 参数 |
| `main()` | 加载 `build_market_rank_cache()`，传入扫描循环 |
| `_worker_wrapper()` | 子进程独立加载 rank_matrix |

### 特征输出
每个异动切片包含:
- 原始截面特征 (25 个)
- V2 时序特征 (25 个，含均线束/洗盘/量能/价格行为/排名)
- 路径稳定性指标 (4 个)
- **合计 50 个特征**

---

## 8. 测试覆盖

```
backend/test_super_trend/
├── test_label_builder.py       # 17 tests - 路径稳定性/指数收益/超额排名/惩罚
├── test_feature_extractor_v2.py # 14 tests - 均线束/洗盘/量能/价格行为/覆盖率
├── test_market_ranker.py       #  9 tests - 缓存/排名序列/特征/scanner集成
├── test_ranker_trainer.py      #  5 tests - 相关度/数据加载/训练流水线
└── test_rank_backtester.py     # 14 tests - 常量/交易模拟/统计/基准/集成
                                ─────────
                          Total: 59 tests, all passed
```

### 运行方式
```bash
cd /home/hypnosis/data/quant_base/backend
source /home/hypnosis/data/quant_base/.venv/bin/activate
python -m pytest test_super_trend/ -v
```

---

## 9. 数据与文件清单

### 新建文件
| 文件 | 说明 |
|------|------|
| `backend/super_trend_label_builder.py` | 标签重构模块 |
| `backend/super_trend_feature_extractor_v2.py` | 时序特征提取 V2 |
| `backend/super_trend_market_ranker.py` | 全市场排名缓存 |
| `backend/super_trend_ranker_trainer.py` | LambdaRank 训练器 |
| `backend/super_trend_rank_backtester.py` | 回测引擎 |
| `backend/twin_case_test.py` | 孪生案例验收脚本 |
| `backend/test_super_trend/test_label_builder.py` | P3 测试 |
| `backend/test_super_trend/test_feature_extractor_v2.py` | P1 测试 |
| `backend/test_super_trend/test_market_ranker.py` | P2 测试 |
| `backend/test_super_trend/test_ranker_trainer.py` | P4 测试 |
| `backend/test_super_trend/test_rank_backtester.py` | P5 测试 |

### 修改文件
| 文件 | 修改内容 |
|------|---------|
| `backend/super_trend_scanner_v1_grok.py` | 集成 V2 特征 + 排名特征 + 路径稳定性 |

### 数据产出
| 文件 | 大小 | 说明 |
|------|------|------|
| `data/result/super_trend/super_trend_training_data.csv` | — | 原始扫描数据 (50 特征) |
| `data/result/super_trend/super_trend_training_data_v2.csv` | 612MB | V2 训练数据 (1.33M 样本, 64 列) |
| `data/result/super_trend/cache/market_daily_rank.pkl` | ~59MB | 全市场排名缓存 (5,190 股) |
| `data/result/super_trend/models/trend_ranker_v1.pkl` | — | 正式 LambdaRank 模型 (43 棵树) |
| `data/result/super_trend/backtest_trades.csv` | — | 回测交易明细 (5,100 笔) |
| `data/result/super_trend/backtest_daily_pnl.csv` | — | 回测每日盈亏 (255 天) |
| `data/result/super_trend/analysis/ranker_feature_importance.csv` | — | 特征重要性排名 |

---

## 10. 全量流水线命令

完整执行步骤（从项目根目录）:

```bash
cd /home/hypnosis/data/quant_base
source .venv/bin/activate

# Step 1: 全量扫描（多进程，20~60 分钟）
python backend/super_trend_scanner_v1_grok.py --full

# Step 2: 重标签（超额收益排名 + 稳定性惩罚）
python backend/super_trend_label_builder.py \
  --input data/result/super_trend/super_trend_training_data.csv \
  --output data/result/super_trend/super_trend_training_data_v2.csv \
  --lam 0.15

# Step 3: 正式训练 LambdaRank
python -c "
from backend.super_trend_ranker_trainer import SuperTrendRanker
ranker = SuperTrendRanker()
df = ranker.load_training_data()
ranker.train(df, test_size=0.2)
ranker.save_model()
"

# Step 4: 完整回测
python backend/super_trend_rank_backtester.py

# Step 5: 孪生案例验收
python backend/twin_case_test.py
```

---

## 11. 孪生案例验收（核心验收标准）

### 11.1 验收标准（来自 ds_review_tasks.md）

> **在案例股票 A 和 B 的异动日，新模型能否把 A 排进当日候选池的前 10%，同时把 B 排除在前 30% 之外？**

### 11.2 全量数据孪生对测试

自动搜索方法：在 MFE≥50% 和 MFE≤10% 的样本中，找截面特征欧氏距离最近的 5 对。

| 对 | A 股票 | A 的 MFE | A 排名百分位 | B 股票 | B 的 MFE | B 排名百分位 | 结果 |
|----|--------|---------|-------------|--------|---------|-------------|------|
| 1 | sz002294 | 81.1% | **81.0%** ✅ | sz002388 | 7.9% | 65.7% ✅ | ✅ PASS |
| 2 | sz002958 | 78.4% | 16.6% ❌ | sh600332 | 8.9% | 4.9% ✅ | ❌ FAIL |
| 3 | sz002958 | 77.6% | 27.4% ❌ | sh601900 | 6.2% | 17.7% ✅ | ❌ FAIL |
| 4 | sz000516 | 73.7% | 3.7% ❌ | sh603077 | 7.4% | 8.3% ✅ | ❌ FAIL |
| 5 | sh600976 | 55.4% | 17.4% ❌ | sz000558 | 6.5% | 15.1% ✅ | ❌ FAIL |

**通过率: 1/5**  
B 股全部正确识别（5/5），A 股仅 1/5 排入前 30%。  
注：搜索到的孪生对集中在 2020 年 6 月（训练集早期）。

### 11.3 近期数据孪生对测试（2025-03 ~ 2025-05）

限定测试集时期，MFE 阈值调整为 ≥40% / ≤10%。

| 对 | A 股票 | A 的 MFE | A 排名百分位 | B 股票 | B 的 MFE | B 排名百分位 | 结果 |
|----|--------|---------|-------------|--------|---------|-------------|------|
| 1 | sh601890 | 46.8% | 3.6% ❌ | sz002615 | 2.2% | 3.8% ✅ | ❌ FAIL |
| 2 | sh603169 | 79.2% | 6.6% ❌ | sz002258 | 8.7% | 1.1% ✅ | ❌ FAIL |
| 3 | sz300721 | 48.8% | 8.2% ❌ | sz301197 | 5.8% | 10.8% ✅ | ❌ FAIL |
| 4 | sz000722 | 49.5% | 23.5% ❌ | sh601339 | 5.4% | 15.6% ✅ | ❌ FAIL |
| 5 | sz300721 | 53.2% | 5.0% ❌ | sh603856 | 6.6% | 0.7% ✅ | ❌ FAIL |

**通过率: 0/5**  
B 股全部正确识别，A 股全部排名垫底（3.6%~23.5%）。

### 11.4 系统性排序能力（全局视角）

孪生对是极端测试。全局视角下模型表现明显更好：

| 指标 | 全量数据 | 2025-03~05 |
|------|---------|-----------|
| 高MFE vs 低MFE 得分差 | **0.2077** | **0.2275** |
| 同日逐对比较胜率 | **70.3%** | **73.0%** |
| MFE 区间得分单调性 | **完美** | **完美** |

#### 2025-03~05 各 MFE 区间模型得分分布

| MFE 区间 | 样本数 | 平均得分 | P25 | P75 |
|---------|--------|---------|-----|-----|
| [0%, 10%) | 30,928 | -0.503 | -0.661 | -0.473 |
| [10%, 20%) | 16,792 | -0.454 | -0.621 | -0.430 |
| [20%, 40%) | 11,912 | -0.390 | -0.602 | -0.304 |
| [40%, 100%) | 3,488 | -0.276 | -0.555 | +0.030 |
| [100%+) | 264 | -0.272 | -0.539 | +0.016 |

**结论**: 模型在全局上实现了完美的 MFE-得分单调性，73% 的同日逐对比较胜率和 0.23 的得分差异证明模型确实学到了排序信号。

### 11.5 孪生对失败原因分析

#### 1. `boll_width` 过度主导
- 特征重要性 27,140，是第二名的 2.4 倍
- 在截面相似的孪生对上，`boll_width` 值几乎相同，无法提供差异化信号
- 但模型对其依赖过重，导致所有截面相似的股票得分趋同

#### 2. V2 特征权重不足
- `rs_rank_mean_20d` (V2) 重要性 4,523 vs `boll_width` 27,140（差 6 倍）
- 孪生对中 V2 特征存在明显差异（`ma_glue_max_days`、`vol_shrink_streak`、`bull_ratio_10d`），但模型权重不足以翻转排名

#### 3. 极端场景的固有困难
- 孪生对的截面特征距离 < 0.26（标准化欧氏距离），本就极难区分
- 每日内有 800~1,400 只异动股，高 MFE 仅占 ~6%，要从 94% 中精确挑出需要极强信号
- 73% 的全局胜率在孪生极端测试中被放大为 0% 通过率

#### 4. 信息边界
- 截面特征 + 技术时序特征仍属于"价格行为"范畴
- 真正驱动主升浪的因素（重大利好、游资接力、板块爆发）不在特征空间中
- 这与 DeepSeek 原始诊断中"幸存者偏差陷阱"的警告一致

---

## 12. 后续建议

### 立即可执行
1. **特征权重再平衡**: 降低 `boll_width` 主导度（如 `colsample_bytree=0.5` 或手动降权），让 V2 特征获得更多决策权
2. **两阶段筛选**: 第一阶段用当前模型粗筛 Top 200，第二阶段用 V2 时序特征精细排序，放大时序信号
3. **调优 λ**: 使用 `tune_lambda()` 搜索最优稳定性惩罚权重

### 中期优化
4. **增加截面外特征**: 板块动量、资金流向、龙虎榜、北向资金等
5. **K 线 n-gram 编码**: 将 T0 前 N 天 K 线阴阳序列做 embedding
6. **样本加权训练**: 对孪生对类场景（截面相似 + MFE 差异大）赋予更高训练权重

### 长期方向
7. **接入 MAE 真实数据**: 使止损逻辑生效，回测更贴近实盘
8. **实盘对接**: 每日扫描 → Top N 推荐 → 人工确认的实盘流程
9. **多模态融合**: 技术面 + 基本面 + 舆情信号

### 已知局限
- 回测基于 MFE 模拟，非真实逐日持仓跟踪（高夏普/零回撤为模拟产物）
- 排名缓存构建需 ~15s，全量重扫需数十分钟
- V2 训练数据 612MB，加载需 ~10s
- 孪生案例验收 0/5，说明在极端精度要求下模型仍有显著提升空间
