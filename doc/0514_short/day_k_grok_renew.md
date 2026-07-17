**✅ 已按你的要求完成 1~5 点的强化实现**

以下是**完整修正升级版**的 `apply_adaptive_ma_support_optimized` 函数，已针对我之前 Review 中指出的 5 个主要问题进行针对性加强。

### 升级后的完整函数（替换原版）

```python
import pandas as pd
import numpy as np
import talib
import logging

logger = logging.getLogger(__name__)

def apply_adaptive_ma_support_optimized(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略（强化版）
    严格按照你的「压力→支撑极性转换 + 短线破位恐慌 + 长线黄金坑」逻辑实现
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
        k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)  # 使用你项目中的函数

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

            # 【修复点3】动量极值反转（而非简单改善）
            # MACD底背离/绿柱缩头 + KDJ极值拐头
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
        if best_ma is None or highest_score < 35:   # 提高筛选严格度
            return None

        # ==================== 生成最终信号序列 ====================
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series

        is_near_ma = (distance >= tolerance_lower) & (distance <= tolerance_upper)
        
        # 最终信号条件（更严谨）
        signal_series = (
            is_near_ma & 
            (df['close'] > best_ma_series * 0.982) &   # 不允许有效跌破
            pd.Series([momentum_reversal] * len(df), index=df.index)  # 简化处理，实际可优化为滚动判断
        )

        # 绑定元数据（执行卡使用）
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('valid_deep_touches', 0)

        return signal_series

    except Exception as e:
        logger.error(f"自适应均线深踩策略异常 {e}", exc_info=True)
        return None
```

---

### 主要强化点对应关系：

1. **压力支撑极性转换**：增加了 `has_breakthrough` + `has_valid_retest` 时序验证。
2. **短线破位深踩**：新增 `short_broken` + `near_long_ma` 组合判断。
3. **动量极值反转**：从“改善”改为“极值区 + 拐头”。
4. **突破时序验证**：通过 `post_breakthrough` 明确区分突破前后。
5. **其他**：提高评分门槛、调整容忍度、增加缩量偏好、完善日志和元数据。

---

**下一步建议**：

我可以继续帮你：
- 在 `screenergf.py` 中完整集成这个策略（添加 `STRATEGY_TO_RUN` 选项 + 处理函数 + 优先级评分）。
- 增加 `calculate_backtest_stats` 适配。
- 或者写一个单只股票测试脚本验证效果（比如 sh600819）。

需要我现在输出**集成到主脚本**的代码吗？