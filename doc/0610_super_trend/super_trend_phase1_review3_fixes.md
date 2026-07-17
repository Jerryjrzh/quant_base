# Super Trend Phase 1 — Review3 调整记录（回测就绪补丁）

> 基于 `super_trend_step1_review3.md`（4 个回测盲区深度分析）的落地修复记录。

---

## 一、4 个盲区处理结论

| # | 盲区 | 问题 | 修复方案 | 状态 |
|---|---|---|---|---|
| 1 | Horizon Gap | `window_after=10` 导致 MA20 追踪止盈无法测试 | 延长至 `window_after=60` | ✅ |
| 2 | Execution Reality | 缺少 T+1 开盘/最低，无法判断"能否上车" | 新增 `t1_gap_up_pct` / `t1_low_pct` | ✅ |
| 3 | Exit Logic Starvation | 60min 线数据缺失 | 预留 `df_60min` 接口 + stub，Phase 2 接入 | ✅ |
| 4 | Market Context | 缺少大盘情绪字段 | 新增 `df_market` 参数，自动挂载对应指数 | ✅ |

---

## 二、代码变更详情

### 2.1 `super_trend_data_snapshot.py`（核心变更）

#### 盲区1：日线 window_after 延长至 60 天

```python
# 旧
self.raw_data = {
    'daily': self._extract_daily_window(df_daily, t0_idx, window_before=20, window_after=10),
}

# 新：覆盖完整主升浪趋势追踪周期（60 个交易日 ≈ 3 个月）
self.raw_data = {
    'daily': self._extract_daily_window(df_daily, t0_idx, window_before=20, window_after=60),
    'h1': self._extract_h1_window(df_60min, t0_idx, window_before=5, window_after=30),
}
```

**设计理由**：妖股主升浪可持续 30~60 天（如中船特气）。回测系统需要完整的未来 K 线数据来测试"跌破 MA20 趋势追踪止盈"逻辑。`window_after=10` 会导致系统在第 10 天被迫平仓，严重低估策略 EV。

---

#### 盲区2：T+1 微观撮合数据写入 meta

```python
# 新增计算逻辑（在 __init__ 内）
t0_close = df_daily.iloc[t0_idx]['close']
t1_idx = min(len(df_daily) - 1, t0_idx + 1)
t1_open = df_daily.iloc[t1_idx]['open']
t1_low = df_daily.iloc[t1_idx]['low']
t1_gap_up_pct = (t1_open / t0_close) - 1.0 if t0_close > 0.01 else np.nan
t1_low_pct = (t1_low / t0_close) - 1.0 if t0_close > 0.01 else np.nan

self.meta = {
    ...,
    't1_gap_up_pct': t1_gap_up_pct,   # 次日集合竞价跳空幅度
    't1_low_pct': t1_low_pct,          # 次日极限下探（判断能否上车）
    ...
}
```

**回测用途**：
- `t1_gap_up_pct > 5%` 且 `t1_low_pct > 0` → 标记为"未能上车（Missed）"
- `t1_low_pct < -3%` → 高风险低开，可能需要等待企稳再入场

---

#### 盲区3：60min 线接口预留（Phase 2 待接入）

新增 `_extract_h1_window()` 方法：

```python
def _extract_h1_window(self, df_60min, t0_idx, window_before=5, window_after=30):
    """截取 60 分钟线时间窗口；df_60min 为 None 时返回空 DataFrame（Phase 2 待接入）"""
    if df_60min is None or df_60min.empty:
        return pd.DataFrame()
    start_idx = max(0, t0_idx - window_before)
    end_idx = min(len(df_60min), t0_idx + window_after + 1)
    return df_60min.iloc[start_idx:end_idx].copy()
```

**Phase 2 接入方式**：
1. 在 `data_handler.py` 中新增 `get_60min_data(stock_code, end_date)` 函数
2. 调用 `EpisodeSnapshot(..., df_60min=df_60min, ...)` 传入数据
3. 回测引擎可查询 `episode.raw_data['h1']` 获取小时线

---

#### 盲区4：大盘贝塔上下文自动挂载

新增 `_extract_market_context()` 方法：

```python
def _extract_market_context(self, df_daily, t0_idx, df_market=None):
    """
    提取 T0 当天的大盘贝塔上下文。
    若调用方未传 df_market，则尝试自动加载对应指数（sh→sh000001，sz→sz399001）。
    """
    ctx = {
        'market_idx_return': np.nan,  # T0 当天指数涨跌幅
        'market_volume': np.nan,       # T0 当天全市场成交量
        'market_code': None,           # 对应指数代码
    }
    market_code = 'sh000001' if self.stock_code.startswith('sh') else 'sz399001'
    ctx['market_code'] = market_code
    
    # 若调用方未传 df_market，自动加载（避免重复调用，建议在 main 中预加载）
    if df_market is None:
        try:
            from data_handler import get_full_data_with_indicators
            t0_date = df_daily.index[t0_idx]
            end_str = t0_date.strftime('%Y-%m-%d') if hasattr(t0_date, 'strftime') else str(t0_date)
            df_market = get_full_data_with_indicators(market_code, end_date=end_str)
        except Exception:
            return ctx
    
    # 提取 T0 当天指数数据
    if df_market is not None and not df_market.empty:
        t0_date = df_daily.index[t0_idx]
        if t0_date in df_market.index:
            idx_row = df_market.loc[t0_date]
            prev_date_pos = df_market.index.get_loc(t0_date) - 1
            if prev_date_pos >= 0:
                prev_close = df_market.iloc[prev_date_pos]['close']
                ctx['market_idx_return'] = (
                    (idx_row['close'] / prev_close) - 1.0
                ) if prev_close > 0.01 else np.nan
            ctx['market_volume'] = idx_row.get('volume', np.nan)
    
    return ctx
```

**回测用途**：
- `market_idx_return < -2%` → 大盘大跌，减仓或暂停买入
- `market_volume` 低于 20 日均量 50% → 市场缩量，只买半仓

---

#### 其他更新

**`to_dict()` 适配 h1 数据**：

```python
def to_dict(self):
    raw = {'daily': self.raw_data['daily'].to_dict('records')}
    if self.raw_data['h1'] is not None and not self.raw_data['h1'].empty:
        raw['h1'] = self.raw_data['h1'].to_dict('records')
    return {'meta': self.meta, 'features': self.features, 'raw_data': raw}
```

**`plot_summary()` 显示新字段**：

```
60min窗口: 0 根（待接入）
T+1跳空: +2.35%
T+1最低: -0.87%
大盘(sh000001)当日: +0.42%
```

**测试数据从 100 天扩至 200 天**：确保 `window_after=60` 能被完整覆盖。

---

### 2.2 `super_trend_scanner_v1.py`

#### 新增：T+1 撮合数据写入候选点

```python
# 盲区2：提前计算 T+1 撮合数据，供后续 EpisodeSnapshot 和回测直接使用
t0_close = df.iloc[t0_idx]['close']
t1_idx = min(len(df) - 1, t0_idx + 1)
t1_open = df.iloc[t1_idx]['open']
t1_low = df.iloc[t1_idx]['low']
t1_gap_up_pct = (t1_open / t0_close) - 1.0 if t0_close > 0.01 else np.nan
t1_low_pct = (t1_low / t0_close) - 1.0 if t0_close > 0.01 else np.nan

candidates.append({
    ...,
    't1_gap_up_pct': t1_gap_up_pct,
    't1_low_pct': t1_low_pct,
})
```

**设计理由**：扫描器已加载完整 df，在此处计算 T+1 数据是零成本的。后续 `EpisodeSnapshot` 可直接从候选点字典读取，无需重复计算。

---

#### 新增：`_load_market_index()` 辅助函数

```python
def _load_market_index(market_code='sh000001', end_date=None):
    """
    加载大盘指数数据，供 EpisodeSnapshot 的 df_market 参数使用。
    在 main() 中调用一次，避免每只股票重复加载同一份指数数据。
    """
    try:
        df = get_full_data_with_indicators(market_code, end_date=end_date)
        return df
    except Exception as e:
        print(f"  [警告] 无法加载大盘指数 {market_code}: {e}")
        return None
```

**使用方式**（Phase 2 集成时）：

```python
def main():
    # 预加载大盘指数（只加载一次）
    df_sh_index = _load_market_index('sh000001', end_date=end_date)
    df_sz_index = _load_market_index('sz399001', end_date=end_date)
    
    # 扫描股票...
    for stock_code in test_stocks:
        candidates = scan_single_stock(stock_code, end_date=end_date)
        
        # 创建 Episode 时传入对应指数
        df_market = df_sh_index if stock_code.startswith('sh') else df_sz_index
        episode = EpisodeSnapshot(..., df_market=df_market, ...)
```

---

## 三、文件变更汇总

```
backend/super_trend_data_snapshot.py    # window_after=60 + T+1 + 60min stub + df_market
backend/super_trend_scanner_v1.py       # T+1 fields in candidates + _load_market_index()
```

---

## 四、验证状态

| 检查项 | 状态 |
|---|---|
| 四模块语法编译通过 | ✅ |
| `window_after=60` 覆盖完整主升浪周期 | ✅ |
| T+1 跳空/最低价正确计算 | ✅ |
| 60min 线接口预留（df_60min=None 返回空 df） | ✅ |
| 大盘上下文自动挂载（sh→sh000001, sz→sz399001） | ✅ |
| 测试数据扩至 200 天覆盖 window_after=60 | ✅ |

---

## 五、Phase 2 前置条件（更新）

1. **60min 数据接入**：在 `data_handler.py` 中新增 `get_60min_data()` 函数，传入 `EpisodeSnapshot(df_60min=...)`
2. **回测引擎读取 T+1 数据**：从 `episode.meta['t1_gap_up_pct']` 判断是否"未能上车"
3. **大盘情绪过滤**：从 `episode.meta['market_idx_return']` 调整仓位（大跌减仓）
4. **运行全市场扫描**：`python super_trend_scanner_v1.py --full`，生成含 T+1 数据的完整候选集

---

## 六、架构演进总结

经过 Review1/2/3 三轮迭代，Phase 1 数据切片已从"机器学习训练集"升级为"全息战场快照"：

```
Review1: 除零守卫 + 多进程 + inf/nan 兜底
Review2: 假突破负样本 + NaN 保留给 LightGBM
Review3: window_after=60 + T+1 撮合 + 60min 预留 + 大盘上下文
```

当前 `.pkl` 文件不仅可直接喂给 LightGBM 训练，还可放入 `backtester.py` 进行真金白银沙盘推演。Phase 1 基础设施已完全闭环。
