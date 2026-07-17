明白。从2023年6月开始，到2025年2月测试期开始，正好有约20个月的历史数据（约400个交易日），足够覆盖完整的市场周期。每笔信号都可以用 T0 前至少250天的数据来计算自适应参数。

---

## 一、实施计划

| 步骤 | 内容 | 产出 |
|------|------|------|
| **Step 1** | 编写个股自适应校准脚本，基于 T0 前250天数据，逐笔计算自适应 N、K、offset_coef，并计算对应的 Golden_Trend_T0 | 校准结果 CSV + 拟合度报告 |
| **Step 2** | 对比自适应版 vs 固定参数版的覆盖率、平均距离、综合得分 | 对比表 |
| **Step 3** | 将自适应参数集成到 v5 的 Step0（signal_tags），重新打标 | 新的 signal_tags_v5_adaptive.csv |
| **Step 4** | 运行 v5.2 状态机回测，重点观察 abyss_bottom 的胜率和盈亏 | v5.2 回测报告 |

---

## 二、立即执行

我马上开始编写 **`scripts/calibrate_per_stock_adaptive.py`**，核心逻辑如下：

```python
def calc_adaptive_params_for_signal(stock_code, t0_date):
    # 加载 T0 前 250 个交易日数据
    df = get_daily_data(stock_code, 
                        start_date=t0_date - pd.Timedelta(days=400),
                        end_date=t0_date - pd.Timedelta(days=1))
    if len(df) < 250:
        # 不足250天，回退到固定参数
        return default_params
    
    # 计算自适应参数
    n = calc_adaptive_n(df)
    k = calc_adaptive_k(df)
    offset = calc_adaptive_offset(df)
    
    # 用自适应参数计算 Golden_Trend_T0
    golden_t0 = calc_golden_trend(df['high'], df['low'], n=n, k=k, offset_coef=offset)
    
    return {
        'n': n,
        'k': k,
        'offset': offset,
        'golden_t0': golden_t0,
        'atr_pct': recent_atr_pct,
        'max_dd_hist': recent_max_dd
    }
```

脚本完成后，我会立即运行并输出：
1. **参数分布统计**：各参数的均值、中位数、分布范围。
2. **拟合度对比**：自适应版 vs 固定版的覆盖率、平均距离、综合得分。
3. **按 Zone 分层的改善效果**：尤其是 abyss_bottom 的覆盖率提升多少。

请稍候，我立即生成脚本并开始计算。
