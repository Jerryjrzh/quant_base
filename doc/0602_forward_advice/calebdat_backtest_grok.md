**Comprehensive System Architecture Review & Backtest Analysis Report**

**Date:** 2026-06-04 (based on provided data)  
**Data Source:** `full_calendar_trades.csv` (3,760 trades, 2025-01-03 ~ 2026-05-11)  
**Key References:** Diagnosis Report (`calendar_backtest_diagnosis.md`), Gemini Review, code files (`calendar_batch_runner_m.py`, `screenergf.py`, `walk_forward_tester_s.py`, `backtester.py`).

### 1. Current System Implementation Architecture

The system is a **mature, production-oriented calendar-based walk-forward backtesting framework** with strong engineering practices for isolation and scalability.

- **Parallel Scheduling Layer** (`calendar_batch_runner_m.py`):  
  Uses real trading calendar (from SH000001) + multiprocessing (`Pool`/`imap_unordered`). Each trading day runs in an isolated subprocess with UUID-based temp scripts/CSV outputs to prevent file conflicts. This enables efficient full-period simulation.

- **Signal Generation & Stock Selection Layer** (`screenergf.py`):  
  Core strategies include optimized reversal (MACD bottom divergence + MA20 volume breakout + RSI oversold) and adaptive MA support. Integrates multi-factor confluence, historical win-rate self-calibration, and Morse features (market env, B20 bias, T1/M15 candles). Outputs trigger prices, initial TP/SL, and V4.4 metadata.

- **Dynamic Evaluation & Forward Simulation Layer** (`walk_forward_tester_s.py` + `backtester.py`):  
  - **V4.1 Confluence Center**: `confluence_scorer` + `pattern_recognizer` for phase (Markup/Accumulation/Distribution/Decline), score, and daily journal with dynamic TP/SL adjustments.  
  - **Entry/Exit Engine**: Golden limit orders (discount entry), jump-gap protection, morphological breakdown stops, time-decay exits (3 days), and trailing logic based on MFE.  
  - **Board-Aware Params**: Differentiated TP/SL for 688 (科创20CM), 300, 920 (北交30CM) vs. main board.  
  - **Backtesting**: Cycle-grouped signals, optimal entry (PRE/MID/POST), MFE/MAE tracking, selection_verdict (合理/失败/边际).

**Strengths**: High engineering quality (isolation, parallelism, forward-looking daily adjustments), data-rich features, and realistic slippage/MFE tracking.  
**Core Style**: Ultra-short-term sniper (mean holding ~1.22 days) focused on reversal momentum with post-entry dynamic risk management.

### 2. Backtest Data Validation & Multi-Dimensional Analysis

**Overall Performance** (validated from CSV + diagnosis):  
- **3,760 trades** over ~17 months. Win rate **60.9%**, avg return **+0.83%**, Profit Factor **1.81** (positive expectancy). Only 1 losing month. Net cumulative ~+31%.  
- **Robust but leaky**: High signal volume but profit leakage from exits and tail risks.

#### Stock Selection
- **Positive**: Underlying reversal logic captures alpha (60%+ win rate, sufficient signals). Sweet spots: B20 bias -10%~-5% (+1.24% avg), 85-score tier (+1.46%).  
- **Issues**: Phase variance high. Decline phase surprisingly strong (+1.62%) but often flagged high-risk. Selection_verdict ("合理") dominates outcomes; V4.4 grades add little value.

#### Operating Period Volatility (MFE/MAE)
- **Strong MFE**: Avg **+3.92%** (excellent selection upside, many +15-35% outliers in North Exchange rebounds).  
- **Problem**: Realized avg only +0.83%. MAE **-2.41%**. Profits are "given back" due to tight/rigid exits. Extreme tails (-20% to -30%) in 688/920 boards.

#### Scoring System (V4.4)
- **Complete Failure**: D-grade has highest win rate/returns. AVOID action outperforms BUY. Grades show **reverse or no correlation** with PnL. Overfitting from too many factors (multi-collinearity).

#### Risk Assessment
- **Daily Journal**: Proactive (phase-based tightening).  
- **Major Weakness**: Board-specific volatility ignored initially → massive gap-down breaches in volatile boards. Morphological stops are "nuclear" (-6.55% avg, some -30%).

#### Price Assessment & Entry
- **Good**: Mean slippage -0.40%. Golden orders + gap protection.  
- **Bias**: Over-reliance on discount limits may cause adverse selection (miss strong breakouts, catch weak pullbacks).

#### Backtesting
- Robust walk-forward with cycle grouping and realistic entry optimization. Captures real trading calendar.

#### Exit Logic
- **Biggest Leak**: 70.3% stop-outs (52.4% win rate but negative avg). Time decay hurts. Trailing too aggressive early (MFE → tight SL). No strong ATR/chandelier or profit-running.

**Top Performers**: North Exchange (bj920) rebounds in crash bounces.  
**Worst**: 688/920 gap-downs + morphological breaks.

### 3. Professional Quant Institution Perspective: Unreasonable Aspects

The architecture is **engineered well** but exhibits classic "retail quant" pitfalls:

1. **Signal-Risk Mismatch** ("Garbage In, Tight Stop Out"): Entering Distribution/Decline phases then tightening stops is contradictory. Institutions **pre-filter** (one-vote veto) rather than trade and defend.

2. **Over-Complex Scoring Overfitting**: V4.4 layers too many features → no monotonicity. Simple base reversal logic polluted. Institutions prioritize parsimony + regularization (e.g., logistic regression on features).

3. **Rigid/Ex-Post Exits**: Fixed time-decay + score-based tightening lags intraday momentum. MFE leakage indicates poor profit capture. Pros use **regime-adaptive, volatility-scaled trailing** (ATR multiples, Chandelier).

4. **Microstructure Blind Spots**: Insufficient open-price/gap handling for 20/30CM boards → tail risk explosion.

5. **Lack of Position/Regime Sizing**: No dynamic bet sizing based on conviction, volatility, or portfolio correlation.

6. **Evaluation Drift**: selection_verdict is useful but post-hoc; V4.4 pre-trade signals are counterproductive.

### 4. Improvement Directions (Prioritized)

**P0: Hemorrhage Control (Immediate, Highest Impact)**  
- **Board Risk Firewall**: Pre-entry volatility filter (reject high ATR 688/920). Strict open-price gap check (`if open < SL → immediate exit at open`).  
- **Phase Veto**: In `backtester.py`/`_generate_forward_advice`, if Distribution/Decline → hard `AVOID` (no entry).  
- **Morphological Stop Upgrade**: Volume-confirmed + tighter thresholds for volatile boards.

**P1: Exit Logic Overhaul (MFE Rescue)**  
- Replace rigid rules with **ATR-based dynamic trailing** (e.g., Chandelier Exit: trail from high by N×ATR).  
- Soften early trailing; allow more room after +3% MFE. Shorten time-decay to 2 days or MFE<1-2%.  
- Tiered profit-taking (scale out at +5%, +10%).

**P2: Simplify & Re-calibrate Scoring**  
- **Decommission/Retraining V4.4**: Use the 3,760 trades for feature importance (logistic regression / SHAP). Prioritize B20 sweet spot, 85-score, decline-phase rebounds.  
- Focus on core reversal + selection_verdict as primary filter.

**P3: Entry & Execution Enhancements**  
- **Adaptive Order Type**: Markup → market/sweep; Accumulation → limit discount.  
- **Beta/Board Scaling**: Volatility-adjusted position sizes and SL multiples.  
- Improve gap modeling in backtester for realism.

**P4: Advanced Features**  
- Portfolio-level risk (correlation, max drawdown control).  
- Regime detection (market env) for dynamic params.  
- Live paper-trading bridge with real-time open-price enforcement.

### Conclusion & Expected Outcome

The system has a **solid foundation** (PF 1.81, consistent, scalable architecture, strong selection alpha). It is **not fundamentally broken** — it is bottlenecked by **post-selection risk management and over-engineered (counterproductive) scoring**.

Implementing P0-P1 (phase veto + ATR trailing + board firewalls) should realistically push PF toward **2.2+**, reduce tail losses dramatically, and improve realized capture of the high MFE. The diagnosis and Gemini insights align perfectly: **simplify, pre-filter ruthlessly, and let winners run with volatility-aware exits**.

This is a classic maturation path for quant systems. With these targeted "surgical" changes, the sniper strategy can evolve from "promising but leaky" to **robust, deployable edge**. 

Next steps: Prioritize P0 code changes in `walk_forward_tester_s.py` + `backtester.py`, re-run calendar backtest, and validate.