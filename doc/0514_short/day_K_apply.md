我已经仔细阅读了 Grok 的 Review (`day_k_grok_review.md`) 以及它提供的修正版代码 (`day_k_grok_renew.md`)。

### 对 Grok Review 的确认与评估

Grok 的 Review **非常精准且切中要害**。它敏锐地指出了初版代码存在的几个致命弱点：

1. **静态贴合 vs 动态极性转换：** 初版确实只是算了一下“历史是否在均线下方”，而你真正的核心逻辑是“压力区 -> 放量突破 -> 缩量回踩支撑”的完整时序动态过程。Grok 新增的 `crossover`, `breakthrough`, `has_valid_retest` 完美补齐了这一闭环。
2. **“深踩”恐慌特征的缺失：** 真正的洗盘必须跌破短线（如 MA13、MA30）制造恐慌，然后在长期专属生命线企稳。Grok 引入的 `short_broken` 是神来之笔，极大地提升了过滤质量，去除了那些高位横盘的假信号。
3. **极值反转：** KDJ 必须是砸出深坑（<20 甚至 <10）后的极值拐头，而不是普通的上涨。

接下来，我将基于 Grok 的修正版代码，为你提供**完整集成到 `screenergf.py**` 的代码修改方案。这不仅包含了策略本身的替换，还包括了**主调度、多进程分配以及终端报告输出**的全链路打通。

---

### 完整集成方案：修改 `screenergf.py`

请在你的 `screenergf.py` 中进行如下修改和替换：

#### 第一步：替换策略函数

将原来的 `apply_adaptive_ma_support_optimized` 替换为 Grok 优化后的版本，并确保顶部导入了必要的库。

```python
import os
import glob
import json
import pandas as pd
import numpy as np 
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging
import data_loader
import strategies
import backtester
import indicators
from adjustment_processor import AdjustmentProcessor, AdjustmentConfig
from win_rate_filter import WinRateFilter, AdvancedTripleCrossFilter
import talib 

# =====================================================================
# === Phase 1 自适应均线右侧深踩选股策略 (Grok 强化版) ===
# =====================================================================
def apply_adaptive_ma_support_optimized(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略（强化版）
    严格按照「压力→支撑极性转换 + 短线破位恐慌 + 长线黄金坑」逻辑实现
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        # 更严格的容忍度（符合深踩特征）
        tolerance_upper = 0.025   # 2.5%
        tolerance_lower = -0.018  # 允许轻微刺穿

        best_ma = None
        highest_score = -999
        best_details = {}

        # 预计算指标
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        
        # 兼容你的 KDJ 计算模块
        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            # 1. 大基座：长期趋势必须向上
            if ma_series.iloc[-1] < ma_series.iloc[-20]:
                continue

            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # ==================== 核心强化逻辑 ====================

            # 【修复点1】压力支撑极性转换（时序验证）
            was_resistance = (historical['close'] < hist_ma).mean() > 0.62
            
            # 突破确认：最近120天内出现过放量上穿
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > recent['volume'].rolling(20).mean() * 1.8)
            has_breakthrough = breakthrough.any()

            # 突破后回踩确认（极性转换核心）
            post_breakthrough = recent[crossover.cumsum() > 0]  # 突破之后的数据
            if not post_breakthrough.empty and len(post_breakthrough) > 5:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (
                    (post_breakthrough['low'] <= post_ma * 1.015) & 
                    (post_breakthrough['close'] >= post_ma * 0.982)
                )
                has_valid_retest = valid_retest.sum() >= 1
            else:
                has_valid_retest = False

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 【修复点2】短线破位 + 长线支撑（深踩恐慌结构）
            ma13 = talib.MA(df['close'], timeperiod=13)
            ma30 = talib.MA(df['close'], timeperiod=30)
            
            short_broken = (recent['close'] < ma13.iloc[-120:]) & (recent['close'] < ma30.iloc[-120:])
            near_long_ma = (abs(recent['close'] - recent_ma) / recent_ma) <= 0.025
            deep_step_pattern = short_broken & near_long_ma

            valid_deep_touches = deep_step_pattern.sum()

            # 【修复点3】动量极值反转
            macd_bottom = macdhist.iloc[-120:]
            macd_improving = (macd_bottom > macd_bottom.shift(1)) & (macd_bottom < 0)
            
            j_series = j.iloc[-120:]
            j_extreme = (j_series < 20) | (j_series.shift(1) < 10)  # 极值区
            j_turning = (j_series > j_series.shift(1)) & j_extreme
            
            momentum_reversal = (macd_improving.any() | j_turning.any()) and j_turning.iloc[-5:].any()

            # 【修复点4】无效穿刺惩罚 + 其他维度打分
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            volume_on_retest = recent['volume'][deep_step_pattern].mean() if valid_deep_touches > 0 else 0
            vol_ratio = volume_on_retest / recent['volume'].rolling(20).mean().mean() if volume_on_retest > 0 else 0

            # 综合评分（大幅提升极性转换权重）
            score = 0
            score += valid_deep_touches * 8
            if polarity_confirmed:
                score += 55          # 重罚权重
            if has_valid_retest:
                score += 25
            score -= crosses * 3
            if momentum_reversal:
                score += 20
            if 0.5 < vol_ratio < 1.8:   # 缩量回踩更佳
                score += 12

            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed,
                    'valid_deep_touches': int(valid_deep_touches),
                    'momentum_reversal': bool(momentum_reversal),
                    'crosses': int(crosses)
                }

        # 门槛提高
        if best_ma is None or highest_score < 35:   
            return None

        # ==================== 生成最终信号序列 ====================
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series

        is_near_ma = (distance >= tolerance_lower) & (distance <= tolerance_upper)
        
        # 最终信号条件（更严谨）
        # 这里优化了 pd.Series 的生成方式，避免索引报错
        momentum_mask = pd.Series(momentum_reversal, index=df.index)
        
        signal_series = (
            is_near_ma & 
            (df['close'] > best_ma_series * 0.982) & 
            momentum_mask
        )

        # 绑定元数据（供主控脚本提取生成执行卡）
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('valid_deep_touches', 0)

        return signal_series

    except Exception as e:
        logger.error(f"自适应均线深踩策略异常: {e}", exc_info=True)
        return None

```

#### 第二步：启用策略配置

在 `screenergf.py` 的顶部配置区，将当前策略切换为新策略：

```python
# --- 您可以在这里切换要运行的策略 ---
#STRATEGY_TO_RUN = 'PRE_CROSS'
#STRATEGY_TO_RUN = 'REVERSED_SHORT' 
STRATEGY_TO_RUN = 'ADAPTIVE_MA_SUPPORT'  # <--- 启用该策略

```

#### 第三步：集成多进程 Worker 分支

在 `worker(args)` 函数的策略路由分支中，添加对新策略的调用：

```python
        # 根据策略执行相应逻辑
        if STRATEGY_TO_RUN == 'PRE_CROSS':
            return _process_pre_cross_strategy(df, result_base)
        elif STRATEGY_TO_RUN == 'TRIPLE_CROSS':
            return _process_triple_cross_strategy(df, result_base, stock_code_full)
        elif STRATEGY_TO_RUN == 'MACD_ZERO_AXIS':
            return _process_macd_zero_axis_strategy(df, result_base, stock_code_full)
        elif STRATEGY_TO_RUN == 'WEEKLY_GOLDEN_CROSS_MA':
            return _process_weekly_golden_cross_ma_strategy(df, result_base, stock_code_full)
        elif STRATEGY_TO_RUN == 'REVERSED_SHORT':
            return _process_reversed_short_strategy_optimized(df, result_base, stock_code_full)
            
        # --- 新增: 处理自适应均线策略 ---
        elif STRATEGY_TO_RUN == 'ADAPTIVE_MA_SUPPORT':
            return _process_adaptive_ma_support_strategy(df, result_base, stock_code_full)
            
        return None

```

#### 第四步：实现策略 Processor 处理器

在 `_process_reversed_short_strategy_optimized` 的下方，新增对应的处理器函数，这是**提取元数据生成条件单**的核心：

```python
def _process_adaptive_ma_support_strategy(df, result_base, stock_code_full):
    """处理 Phase 1 自适应均线右侧深踩策略"""
    try:
        signal_series = apply_adaptive_ma_support_optimized(df)
        
        # 判断最后一天是否触发信号
        if signal_series is not None and signal_series.iloc[-1]:
            # 获取快速回测数据，用于评分排序
            backtest_stats = calculate_backtest_stats_fast(df, signal_series)
            priority_score = _calculate_priority_score(df, backtest_stats)
            
            # 安全提取绑定在 Series 上的元数据
            best_ma = getattr(signal_series, 'best_ma_period', 0)
            fit_score = getattr(signal_series, 'fit_score', 0.0)
            current_ma_val = getattr(signal_series, 'current_ma_val', 0.0)
            polarity_confirmed = getattr(signal_series, 'polarity_confirmed', False)
            deep_touches = getattr(signal_series, 'deep_touches', 0)
            
            current_price = df['close'].iloc[-1]
            
            # 组装“明日交易执行卡”核心参数
            result_base.update({
                'signal_state': 'BUY_CANDIDATE',
                'filter_status': 'passed_adaptive_ma',
                'priority_score': priority_score,
                # --- 交易执行卡/条件单专属数据 ---
                'best_ma_period': best_ma,
                'fit_score': fit_score,
                'polarity_confirmed': polarity_confirmed,
                'deep_touches': deep_touches,
                'current_price': current_price,
                'trigger_buy_price': round(current_ma_val * 1.005, 2), # 专属均线上方0.5%设买点
                'hard_stop_loss': round(current_ma_val * 0.96, 2),     # 跌破专属均线4%无条件离场
                **backtest_stats
            })
            return result_base
        return None
    except Exception as e:
        logger.error(f"处理ADAPTIVE_MA_SUPPORT策略失败 {stock_code_full}: {e}")
        return None

```

#### 第五步：让终端报告输出执行卡信息

为了在运行后终端直接看到需要挂单的价格，在 `main()` 函数底部写入 `txt` 报告的部分稍作修改：

找到 `main()` 中生成 `scan_report_{DATE}.txt` 的这段代码：

```python
        if summary_report['top_performers']:
            f.write("=== 前10名表现最佳股票 ===\n")
            for i, stock in enumerate(summary_report['top_performers'], 1):
                f.write(f"{i:2d}. {stock['stock_code']} - 胜率: {stock.get('win_rate', 'N/A')}, "
                       f"收益: {stock.get('avg_max_profit', 'N/A')}, "
                       f"天数: {stock.get('avg_days_to_peak', 'N/A')}\n")

```

**替换为以下内容**：

```python
        if summary_report['top_performers']:
            f.write("=== 前10名表现最佳股票 (推荐优先交易) ===\n")
            for i, stock in enumerate(summary_report['top_performers'], 1):
                base_info = (f"{i:2d}. {stock['stock_code']} - 胜率: {stock.get('win_rate', 'N/A')}, "
                             f"收益: {stock.get('avg_max_profit', 'N/A')}, "
                             f"天数: {stock.get('avg_days_to_peak', 'N/A')}")
                
                # 如果是自适应均线策略，输出额外的条件单执行卡数据
                if 'best_ma_period' in stock:
                    polarity_mark = "⚡极性转换确认" if stock.get('polarity_confirmed') else ""
                    extra_info = (f"\n    └─ 专属MA: {stock['best_ma_period']} (拟合分: {stock['fit_score']}) {polarity_mark}\n"
                                  f"    └─ 💡 条件单买点: ¥{stock.get('trigger_buy_price', 0)} | 🛑 破位止损: ¥{stock.get('hard_stop_loss', 0)}\n")
                    f.write(base_info + extra_info)
                else:
                    f.write(base_info + "\n")

```

---

### 全链路测试与验收

完成上述修改后，你可以直接运行 `screenergf.py`。
由于策略要求十分苛刻（要求长期趋势向上、发生过压力到支撑的极性转换、且当前跌破短线制造了恐慌），你会发现最终筛出来的股票数量会**大幅减少**，但这正是量化系统想要追求的高胜率“深坑”标的。

运行后，查看日志生成的 `scan_report_xxx.txt`，你将看到可以直接用于交易软件挂单的具体价位卡片。