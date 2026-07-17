def apply_adaptive_ma_support_optimized(df):
    """
    Phase 1: 自适应均线右侧深踩选股策略（全向量化回测兼容版）
    结合了 Grok 的极性转换逻辑 + 修复了历史回测信号失真 + 引入了"死鱼"剔除机制
    """
    if len(df) < 250:
        return None

    try:
        ma_candidates = [60, 90, 120, 150, 200, 240]
        tolerance_upper = 0.025
        tolerance_lower = -0.018

        best_ma = None
        highest_score = -999
        best_details = {}

        # 1. 预计算全局指标 (Vectorized for backtesting)
        macd, signal, macdhist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
        try:
            k, d, j = indicators.calculate_kdj(df, n=27, k_period=3, d_period=3)
        except Exception:
            j = pd.Series(50, index=df.index)

        # 动量反转的全历史布尔序列 (解决回测失效的核心)
        macd_improving = (macdhist > macdhist.shift(1)) & (macdhist < 0)
        j_extreme = (j < 25) | (j.shift(1) < 12)
        j_turning = (j > j.shift(1)) & j_extreme
        # 允许 J 值在最近6天内发生过拐头
        j_turning_recent = j_turning.rolling(window=6, min_periods=1).max() > 0
        momentum_reversal_series = (macd_improving | j_turning) & j_turning_recent

        # 短线破位序列 (全历史)
        ma13_full = talib.MA(df['close'], timeperiod=13)
        ma30_full = talib.MA(df['close'], timeperiod=30)
        short_broken_full = (df['close'] < ma13_full) & (df['close'] < ma30_full)

        # 2. 遍历寻找专属生命线
        for ma_period in ma_candidates:
            ma_series = talib.MA(df['close'], timeperiod=ma_period)
            if pd.isna(ma_series.iloc[-1]):
                continue

            # 长期趋势必须向上
            if ma_series.iloc[-1] < ma_series.iloc[-20]:
                continue

            recent = df.iloc[-120:].copy()
            historical = df.iloc[-250:-120].copy()
            recent_ma = ma_series.iloc[-120:]
            hist_ma = ma_series.iloc[-250:-120]

            # 【极性转换评估】
            was_resistance = (historical['close'] < hist_ma).mean() > 0.60
            
            # 放量突破
            vol_ma20 = recent['volume'].rolling(20).mean()
            crossover = (recent['close'].shift(1) < recent_ma.shift(1)) & (recent['close'] > recent_ma)
            breakthrough = crossover & (recent['volume'] > vol_ma20 * 1.6)
            has_breakthrough = breakthrough.any()

            has_valid_retest = False
            post_breakthrough = recent[crossover.cumsum() > 0]
            if not post_breakthrough.empty and len(post_breakthrough) > 8:
                post_ma = recent_ma.loc[post_breakthrough.index]
                valid_retest = (
                    (post_breakthrough['low'] <= post_ma * 1.018) & 
                    (post_breakthrough['close'] >= post_ma * 0.98)
                )
                has_valid_retest = valid_retest.sum() >= 1

            polarity_confirmed = was_resistance and has_breakthrough and has_valid_retest

            # 【深踩结构与平底锅熔断】
            near_long_ma = (abs(recent['close'] - recent_ma) / recent_ma) <= 0.028
            deep_step_pattern = short_broken_full.iloc[-120:] & near_long_ma
            valid_deep_touches = deep_step_pattern.sum()

            # 熔断：如果在长线附近趴了太久（>22天），说明股性已死，直接跳过
            if valid_deep_touches > 22:
                continue

            # 【穿刺与量能评估】
            crosses = (np.sign(recent['close'] - recent_ma).diff().ne(0)).sum()
            vol_on_retest = recent['volume'][deep_step_pattern].mean() if valid_deep_touches > 0 else 0
            vol_ratio = vol_on_retest / vol_ma20.mean() if vol_on_retest > 0 else 999

            # 【打分系统重构】
            # 适度奖励深踩（证明支撑有效），但重赏极性转换
            score = valid_deep_touches * 4  
            if polarity_confirmed:
                score += 65
            elif has_valid_retest:
                score += 25
            
            score -= crosses * 3 # 严惩反复无效穿刺
            
            # 评价最后几天的动能
            if momentum_reversal_series.iloc[-5:].any():
                score += 20
                
            # 缩量回踩加分
            if 0.3 < vol_ratio < 1.5:
                score += 15

            # 保存最佳 MA
            if score > highest_score:
                highest_score = score
                best_ma = ma_period
                best_details = {
                    'polarity_confirmed': polarity_confirmed,
                    'valid_deep_touches': int(valid_deep_touches),
                    'crosses': int(crosses),
                    'vol_ratio': round(vol_ratio, 2)
                }

        # 提高门槛：动态门槛，必须有一定的确信度才通过
        if best_ma is None or highest_score < 40:   
            return None

        # =======================================================
        # 3. 生成全历史的信号序列 (完美支持 backtester 算胜率)
        # =======================================================
        best_ma_series = talib.MA(df['close'], timeperiod=best_ma)
        distance = (df['close'] - best_ma_series) / best_ma_series
        is_near_ma_full = (distance >= tolerance_lower) & (distance <= tolerance_upper)

        # 历史买点信号：跌破短线 + 靠近专属长线 + 动量反转 + 收盘不深跌
        signal_series = (
            short_broken_full & 
            is_near_ma_full & 
            momentum_reversal_series & 
            (df['close'] > best_ma_series * 0.982)
        )

        # 如果最后一天没有触发，直接返回 None (过滤掉历史牛股但今天没买点的标的)
        if not signal_series.iloc[-1]:
            return None

        # 绑定元数据（供主控提取）
        signal_series.best_ma_period = best_ma
        signal_series.fit_score = round(highest_score, 1)
        signal_series.current_ma_val = round(best_ma_series.iloc[-1], 2)
        signal_series.polarity_confirmed = best_details.get('polarity_confirmed', False)
        signal_series.deep_touches = best_details.get('valid_deep_touches', 0)
        signal_series.vol_ratio = best_details.get('vol_ratio', 0)

        return signal_series

    except Exception as e:
        logger.error(f"自适应均线深踩策略异常: {e}", exc_info=True)
        return None