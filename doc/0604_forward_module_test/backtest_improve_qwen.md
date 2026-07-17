 Signal Materialization Pipeline - signal_generator.py

 Context

 当前回测架构（calendar_batch_runner_m.py +
 walk_forward_tester_s.py）是"在线流式回测"：每个交易日都重新扫描全市场 5000
 只股票、计算指标、打分、模拟交易。这导致：
 - 每次调参（如止盈比例从 60% 改为 50%）都要重跑 17 个月的全市场扫描
 - 无法做截面优选（每天 Top N 排名选股）
 - 多维验证困难

 本脚本实现文档 doc/0604_forward_module_test/backtest_improve.md
 描述的模块一：全局信号捕捉器，一次性将所有 70+ 分信号及其未来 7 天 OHLC 数据落盘为
 master_signals.csv，为后续极速矢量回测器（模块二）提供数据基础。

 Approach: Stock-First Traversal

 核心设计选择：按股票遍历（而非按日期遍历）。

 每只股票只加载一次数据、计算一次指标，然后遍历所有交易日检查信号。相比"按日期遍历、每天扫全市场"
 ，减少 99% 的 I/O 和指标计算开销。
  for stock in all_stocks:           # ~5000, parallelized
      df = load(stock)                # read once
      compute_indicators(df)          # compute once
      for date in trading_days:       # ~340 dates
          slice = df[:date]
          if score(slice) >= 70:
              forward = df[date+1 : date+8]   # T+1 to T+7
              emit_signal_row(...)
 Output Schema: master_signals.csv
 ┌─────────────────────┬──────────────────────────────┐
 │ Column              │ Description                  │
 ├─────────────────────┼──────────────────────────────┤
 │ signal_date         │ 信号触发日 (YYYY-MM-DD)      │
 │ stock_code          │ 股票代码 (e.g. sh600519)     │
 │ score               │ 莫尔斯狙击评分               │
 │ pattern_label       │ 形态标签 (T1_D/T1_U/T1_X 等) │
 │ board_type          │ 所属板块 (10CM/20CM/30CM)    │
 │ close_t0            │ T0 收盘价                    │
 │ trigger_buy         │ 挂单买入价                   │
 │ stop_loss           │ 初始止损价                   │
 │ take_profit         │ 初始止盈价                   │
 │ v44_entry           │ V4.4 动态入场价 (如有)       │
 │ v44_target          │ V4.4 止盈目标价 (如有)       │
 │ v44_stop            │ V4.4 止损价 (如有)           │
 │ v44_trend           │ V4.4 趋势阶段                │
 │ v44_bias_tier       │ V4.4 乖离率分层              │
 │ v44_grade           │ V4.4 质量等级                │
 │ ma_slope            │ MA20 斜率                    │
 │ bias_20             │ MA20 乖离率                  │
 │ morse_features      │ 莫尔斯特征串                 │
 │ market_env          │ 大盘环境标签                 │
 │ T1_Open .. T7_Close │ T+1 到 T+7 每日 OHLC (28列)  │
 │ future_mfe          │ 7天内最大有利偏移            │
 │ future_mae          │ 7天内最大不利偏移            │
 │ future_mfe_day      │ MFE 出现在第几天             │
 │ future_mae_day      │ MAE 出现在第几天             │
 └─────────────────────┴──────────────────────────────┘
 Verified Parameters

 - Strategy: MORSE_FACTOR_SNIPER only (apply_morse_sniper_strategy())
 - Date range: 2025-01-01 to 2026-04-30 (~340 trading days)
 - Score threshold: >= 70 (capture more signals for downstream cross-section filtering)
 - Forward window: 7 days (T+1 to T+7)

 Implementation Steps

 Step 1: Create backend/signal_generator.py

 Key components:

 get_real_trading_days(start, end) - Reuse logic from
 calendar_batch_runner_m.py:12-21，读取上证指数提取真实交易日历
 extract_forward_ohlc(df, signal_idx, forward_days=7) - 从信号日的下一天开始，提取 T+1 到 T+7 的
 OHLC 扁平化列 + MFE/MAE
 scan_stock(file_path, trading_days, score_threshold=70) - 核心 worker：
   - 加载日线数据 + 复权
   - 加载 15 分钟线
   - 对每个交易日：
       - 切片历史数据 df[:date]
     - 调用 apply_morse_sniper_strategy() 打分
     - 分数 >= 70 则提取 forward OHLC
   - 返回该股票所有信号行列表
 main() - 多进程编排：
   - 获取交易日历 2025-01-01 ~ 2026-04-30
   - 收集所有 .day 文件路径
   - Pool(cpu_count()).map(scan_stock, ...)
   - 汇总为 DataFrame，保存 data/result/master_signals.csv

 Step 2: Key Reuse Points
 ┌─────────────────────────────────────────────────┬─────────────────┐
 │ Reuse From                                      │ What            │
 ├─────────────────────────────────────────────────┼─────────────────┤
 │ data_loader.get_daily_data()                    │ 日线读取        │
 │ data_loader.get_min_data()                      │ 15分钟线        │
 │ adjustment_processor.AdjustmentProcessor        │ 前复权          │
 │ screenergf.apply_morse_sniper_strategy()        │ 莫尔斯打分+定价 │
 │ calendar_batch_runner_m.get_real_trading_days() │ 交易日历        │
 │ data_handler.get_full_data_with_indicators()    │ V4.4 指标数据   │
 └─────────────────────────────────────────────────┴─────────────────┘
 Step 3: Performance Optimizations

 - Stock-first traversal: 每只股票只加载一次数据
 - Pre-compute indicators once: 对完整 df 一次计算 MA20/MA60/MACD/RSI 等
 - Skip early: 数据不足 150 天或股票代码无效时立即跳过
 - Incremental CSV write: 每个 worker 返回 list，主进程 concat 后一次写入
 - Multiprocessing: Pool(cpu_count()) 并行处理

 Critical Files

 - Create: backend/signal_generator.py (new)
 - Read-only deps: backend/screenergf.py, backend/data_loader.py, backend/adjustment_processor.py,
  backend/data_handler.py, backend/confluence_scorer.py

 Verification

 1. Run on a small date range (e.g. 1 week) to verify output format
 2. Check CSV has expected columns and data types
 3. Verify MFE/MAE calculations match walk_forward_tester_s.py logic
 4. Spot-check a few known signals against existing latest_walk_forward.csv

