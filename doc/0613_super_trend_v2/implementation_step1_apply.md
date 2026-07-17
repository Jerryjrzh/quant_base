我们将任务分解为四个阶段的具体实现思路和关键代码片段。这些片段基于你们现有的模块（`market_structure`, `structure_entry`, `structure_exit`, `structure_backtester`）和数据文件（`pure_mfe_analysis.csv`）设计，可直接嵌入到项目中。

---

## 阶段一：全量信号的结构化回测（P0）

**目标**：读取 `pure_mfe_analysis.csv` 中的 4423 笔精排 Top 20 信号，逐笔执行完整的“结构分析 → 入场等待 → 持仓管理”流程，并与原基准（T+1 买入，固定 -8% / +30% 或持有到期）进行对比。

### 1.1 数据接口约定

假设 `pure_mfe_analysis.csv` 包含以下关键列（请根据实际列名调整）：

- `stock_code`：股票代码（如 'sh600519'）
- `t0_date`：异动信号日 (YYYY-MM-DD)
- `buy_price`：T+1 开盘价（已有跳空过滤）
- 价格路径列：`high_0, high_1, ..., high_21` 对应 T+1 至 T+22 的每日最高价（共 22 天）
- `low_0, low_1, ..., low_21`：每日最低价
- `close_0, close_1, ..., close_21`：每日收盘价
- 可选指标列：`ma20, ma60, atr` 等（如果文件里没有，需通过 `data_handler` 补充计算）

我们还需要每笔信号的 **T0 前 60 天的 OHLCV 数据** 来计算摆动点、MA、ATR 等。这通过 `data_handler.get_full_data_with_indicators(stock_code, end_date=t0)` 获取（需要确保数据截止到 T0 当天，不包含未来）。

### 1.2 批量回测脚本框架

```python
# batch_structure_backtest.py

import pandas as pd
import numpy as np
from multiprocessing import Pool
from backend.market_structure import analyze_market_structure
from backend.structure_entry import structure_filter, run_entry_state_machine
from backend.structure_exit import set_initial_stop, set_take_profit_levels, calculate_position_size, run_position_manager
from backend.data_handler import get_full_data_with_indicators  # 假设已有

# 加载信号列表
signals_df = pd.read_csv('data/result/super_trend/pure_mfe_analysis.csv')

# 假设列名映射
REQUIRED_COLS = ['stock_code', 't0_date', 'buy_price'] + \
                [f'high_{i}' for i in range(22)] + \
                [f'low_{i}' for i in range(22)] + \
                [f'close_{i}' for i in range(22)]

# 若缺少指标列，可预先通过 data_handler 批量补充，这里略

def process_single_signal(args):
    """处理单个信号的完整回测，返回交易明细和对比指标"""
    idx, row = args
    stock = row['stock_code']
    t0 = pd.Timestamp(row['t0_date'])
    buy_price = row['buy_price']

    # 1. 获取 T0 前 60 天数据（含 T0 当天，用于计算指标，但不用于未来）
    try:
        df_hist = get_full_data_with_indicators(stock, end_date=t0, lookback=60)
    except Exception as e:
        return None  # 数据缺失，跳过

    if len(df_hist) < 30:
        return None

    # 2. 市场结构分析
    structure = analyze_market_structure(df_hist, current_price=buy_price)
    if structure is None:
        return None

    # 3. 结构过滤器
    if not structure_filter(structure):
        # 记录被过滤的信号
        return {
            'signal_idx': idx,
            'stock': stock,
            't0': t0,
            'status': 'filtered',
            'filter_reason': 'structure_filter'
        }

    # 4. 构建 T+1 之后的价格路径 DataFrame（用于入场和持仓模拟）
    path_data = {
        'date': pd.date_range(t0 + pd.Timedelta(days=1), periods=22, freq='D'),  # 简单处理
        'open': [buy_price] + [row[f'open_{i}'] for i in range(22)],  # 实际 csv 可能无 open，可用 close 前一日近似
        'high': [row[f'high_{i}'] for i in range(22)],
        'low': [row[f'low_{i}'] for i in range(22)],
        'close': [row[f'close_{i}'] for i in range(22)],
    }
    path_df = pd.DataFrame(path_data)

    # 5. 入场状态机（最多等待5天）
    entry_result = run_entry_state_machine(structure, path_df, max_wait_days=5)
    if entry_result is None or entry_result['status'] == 'EXPIRED':
        return {
            'signal_idx': idx,
            'stock': stock,
            't0': t0,
            'status': 'expired',
            'wait_days': 5
        }

    # 6. 获取入场信息
    entry_price = entry_result['entry_price']
    entry_date = entry_result['entry_date']
    support_used = entry_result.get('support_used')

    # 7. 设置止损与止盈
    atr = structure.atr  # 使用 T0 前的 ATR，也可动态更新
    stop_loss = set_initial_stop(entry_price, support_used, atr, max_stop_loss_pct=0.08)  # 可配置
    tp_levels = set_take_profit_levels(entry_price, structure.resistances)

    # 8. 仓位计算（假设初始资金 1000000，单笔风险 0.5%）
    capital = 1_000_000
    max_risk_per_trade = 0.005
    position_size = calculate_position_size(capital, entry_price, stop_loss, max_risk_per_trade)

    # 9. 持仓管理模拟
    # 需要从入场日之后的子 DataFrame 开始模拟
    start_idx = entry_date - path_df['date'].iloc[0]  # 计算偏移
    # 简便起见，直接传入完整路径和入场日索引
    trade_result = run_position_manager(
        path_df, entry_price, entry_date, stop_loss, tp_levels,
        position_size, max_hold_days=22
    )

    # 10. 基准策略收益（用于对比）
    # 基准1：T+1 买入，持有到期（22天收盘卖出）
    base_return = (row['close_21'] / buy_price - 1) if buy_price > 0 else 0

    # 基准2：固定止损 -8%，止盈 +30%（原始最优参数）
    base_return_fixed = simulate_fixed_exit(path_df, buy_price, stop_loss=-0.08, take_profit=0.30)

    return {
        'signal_idx': idx,
        'stock': stock,
        't0': t0,
        'status': 'traded',
        'entry_price': entry_price,
        'exit_price': trade_result['exit_price'],
        'exit_reason': trade_result['reason'],
        'pnl_pct': trade_result['pnl_pct'],
        'hold_days': trade_result['hold_days'],
        'base_return': base_return,
        'base_return_fixed': base_return_fixed,
        'structure': structure
    }

# 并行处理
pool = Pool(processes=8)  # 根据 CPU 核心数调整
results = pool.map(process_single_signal, signals_df.iterrows())
pool.close()
pool.join()

# 汇总统计
trades = [r for r in results if r and r['status'] == 'traded']
filtered = [r for r in results if r and r['status'] == 'filtered']
expired = [r for r in results if r and r['status'] == 'expired']

# 计算总盈亏、胜率等
pnls = [t['pnl_pct'] for t in trades]
print(f"交易次数: {len(trades)}, 过滤: {len(filtered)}, 过期: {len(expired)}")
print(f"平均盈亏: {np.mean(pnls):.2%}, 胜率: {np.mean(np.array(pnls) > 0):.1%}")
# 对比基准
base_pnls = [t['base_return'] for t in trades]
print(f"基准持有到期平均盈亏: {np.mean(base_pnls):.2%}")
```

### 1.3 关键函数补充说明

- `simulate_fixed_exit(path_df, entry_price, stop_loss, take_profit)`：模拟固定百分比止损/止盈逻辑，逐日检查最低价、最高价，返回最终收益。这个可以直接复用 `real_path_backtester` 里的部分代码。
- `run_entry_state_machine`：需要从 `structure_entry.py` 中调用，逐日检查是否出现回调/突破确认信号，返回入场日期和价格。注意不要使用未来数据。
- `run_position_manager`：需要实现持仓管理状态机，支持分批止盈、动态止损上移。如果当前代码中的 `run_position_manager` 还不支持分批止盈的半仓操作，则需要扩展。简单版可先实现一次性止损/止盈，以后再加入分批。

---

## 阶段二：参数网格搜索优化（P1）

**目标**：在全量回测可复现的基础上，搜索最优参数组合。

### 2.1 思路

使用网格搜索或随机搜索，对 `max_wait_days`、`stop_loss_atr_multiplier`、`tp1_reduce_ratio`、`max_stop_loss_pct` 等参数进行遍历。由于单次全量回测耗时较长，需要：

1. **缓存重复计算**：同一只股票、同一 T0 前的市场结构可以复用。信号列表中有许多股票在不同日期出现，但 `analyze_market_structure` 针对每个 (stock_code, t0) 是独立的。可以预先计算所有信号的 `MarketStructure` 并序列化缓存，避免每次网格搜索都重新计算。
2. **并行化**：使用 `multiprocessing` 或 `joblib` 并行评估不同参数组合。
3. **验证集划分**：不能在全量测试集上优化参数，否则过拟合。需要指定一段验证期，例如 2024 年的数据（如果 `pure_mfe_analysis.csv` 包含该时期）或从训练集中划出。目前测试集是 2025-02~2026-03，建议使用 2023-2024 数据作为验证集。

### 2.2 缓存市场结构

```python
# 预计算所有信号的 MarketStructure 并保存为字典 {(stock, t0): structure}
from collections import defaultdict
import pickle

structure_cache = {}
for idx, row in signals_df.iterrows():
    key = (row['stock_code'], row['t0_date'])
    if key not in structure_cache:
        df_hist = get_full_data_with_indicators(row['stock_code'], end_date=row['t0_date'], lookback=60)
        structure_cache[key] = analyze_market_structure(df_hist, current_price=row['buy_price'])

# 保存
with open('structure_cache.pkl', 'wb') as f:
    pickle.dump(structure_cache, f)
```

之后在参数搜索时直接加载缓存，大幅节省时间。

### 2.3 参数搜索框架

```python
from itertools import product

param_grid = {
    'max_wait_days': [3, 5, 7],
    'stop_atr_mult': [1.0, 1.5, 2.0],
    'tp1_reduce_ratio': [0.3, 0.5, 1.0],  # 1.0 表示不分批，一次性止盈
    'max_stop_loss_pct': [0.05, 0.08, 0.12]
}

def evaluate_params(params, signals_df, cache, parallel=True):
    # 修改 process_single_signal 以接收 params 参数
    # 这里调用并行计算
    pass

# 遍历所有组合
results_list = []
for combo in product(*param_grid.values()):
    param_dict = dict(zip(param_grid.keys(), combo))
    metrics = evaluate_params(param_dict, signals_df, structure_cache)
    results_list.append((param_dict, metrics))

# 选择平均收益最高或风险调整后收益最高的参数
best = max(results_list, key=lambda x: x[1]['avg_pnl'])
print("Best params:", best[0], "Avg PnL:", best[1]['avg_pnl'])
```

### 2.4 注意事项

- 确保验证集和测试集严格分离，避免参数优化污染最终结果。
- 对于包含分批止盈的模拟，`run_position_manager` 需要支持减仓操作，并记录剩余仓位。可以分两步：先模拟到第一止盈触发，记录收益，剩余仓位继续模拟（使用新的 `path_df` 子集），最终合并总收益。

---

## 阶段三：结构化特征引入模型（P2）

**目标**：将市场结构质量编码为特征，加入 LightGBM 训练。

### 3.1 特征构建

对于每个训练样本（即每个异动日切片），在原 50 个特征基础上，添加以下特征：

- `dist_to_nearest_support`：当前价距离最近支撑位的百分比（负值为下方支撑，正值为阻力？这里应标准化： (support_price / current_price - 1) ）
- `support_strength`：最近支撑位的测试次数（或者归一化）
- `num_supports_within_5pct`：5% 范围内的支撑位数量
- `dist_to_nearest_resistance`：到最近阻力位的百分比（ current_price / resistance_price - 1 ）
- `trend_score`：定量趋势强度，例如基于 Swing 点的 HH/LL 序列，计算一个分数（如 +1 表示 HH, +0.5 表示 HL 等）
- `pullback_depth_pct`：历史上最近一次回调从高点回落的幅度
- `volume_profile_concentration`：POC 附近的成交量集中度（成交量占比）

这些特征需要在生成训练数据（即扫描器中的 `build_episodes`）时计算。改造 `super_trend_scanner_v1_grok.py`，在提取特征时调用 `analyze_market_structure`（使用 T0 之前的数据），将上述特征添加到特征字典中。

### 3.2 训练流程调整

- 保持 LambdaRank 训练框架不变，特征列增加。
- 可以用网格搜索或者仅加入新特征重新训练精排模型，然后重新做两阶段排序评估。
- 验证新的孪生案例区分度和 Top 20 的 MFE。

代码示例（扩展特征提取器）：

```python
# 在 extract_features 函数末尾添加
from market_structure import analyze_market_structure

def add_structure_features(features_dict, df_hist, t0_idx, current_price):
    # df_hist 为 T0 及之前的 K 线数据
    structure = analyze_market_structure(df_hist.iloc[:t0_idx+1], current_price=current_price)
    if structure:
        supports = structure.supports
        resistances = structure.resistances
        features_dict['dist_to_support'] = (supports[0].price / current_price - 1) if supports else -0.2  # 默认值
        features_dict['support_tests'] = supports[0].tests if supports else 0
        features_dict['dist_to_resistance'] = (resistances[0].price / current_price - 1) if resistances else 0.2
        features_dict['trend_strength'] = structure.structure_strength
        # ... 更多
    else:
        # 填充默认值
        features_dict['dist_to_support'] = -0.2
        # ...
    return features_dict
```

然后重新运行全量扫描，生成新的训练数据，再训练模型。

---

## 阶段四：集成到现有回测/实盘流水线（P1）

**目标**：将结构感知的入场/出场逻辑融合到每日实盘信号生成和回测框架中，形成可操作的推荐列表。

### 4.1 实盘信号处理流程

每日扫描结束后，对每个进入 Top N 的股票：

1. 获取其历史数据，计算 `MarketStructure`。
2. 判断当前结构是否允许入场（结构过滤器）。如果过滤，标记为“结构不匹配，不入场”。
3. 如果允许，计算关键支撑/阻力，给出**建议入场区域**（例如最近支撑位附近 ±1%）、**建议止损价**、**第一第二止盈价**。
4. 输出一张“信号卡”，包含：
   - 股票代码、模型得分
   - 当前价格、趋势方向
   - 最近支撑/阻力价位和强度
   - 建议入场方式（等待回调至 XX 元企稳后买入）
   - 仓位建议（基于 ATR 的风险计算）

### 4.2 回测集成

修改 `backtester.py` 或直接使用 `structure_backtester.py`，将 `run_position_manager` 替换原有的简单止损止盈逻辑。为了保持灵活性，可以增加一个 `exit_strategy` 参数，可选 `'fixed'` 或 `'structure'`。

在 `run_backtest` 循环中：
```python
if exit_strategy == 'structure':
    # 需要预先为每个信号计算 MarketStructure（可在回测前批量缓存）
    structure = precomputed_structures[(stock, t0)]
    # 执行入场状态机
    entry = run_entry_state_machine(structure, future_path_df)
    if entry is None:
        continue  # 未入场
    # 执行持仓管理
    trade = run_position_manager(...)
else:
    # 原有固定止损止盈
    trade = simulate_fixed_exit(...)
```

### 4.3 与前端对接

如果需要展示，可以在前端请求某个股票时，调用 `analyze_market_structure` 并返回结构化数据（支撑/阻力列表、趋势、分数），以图表形式展示。

---

## 总结与行动

以上四个阶段的代码框架可直接用于你们的项目。关键点在于：

- **阶段一**：抓紧完成全量 4423 笔的回测，这是判断结构方法是否有效的最关键一步。
- **阶段二**：只有在阶段一结果显示改善但不够显著时，才开始参数优化。如果阶段一直接出正期望，可以直接跳到阶段四集成。
- **阶段三**：是长期提升模型区分能力的方向，不急于执行。
- **阶段四**：一旦确认结构方法有效，应尽快集成，让实盘信号更智能。

请优先执行阶段一，过程中若遇到数据格式或函数接口的具体问题，可随时调整上述代码。祝顺利！
