#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
60分钟入场二次确认模块 (Phase 1)

动态锚定: 在全部60m数据中搜索支撑触及，围绕最后触及点分析。
规则 (统一规则，无行情自适应):
  1. 支撑精确触及: 全部60m数据中至少1根 low 在支撑 ±1.5% 内
  2. 无否决信号: 放量大阴线 / 连续3阴 / 收盘跌破支撑0.5%
  3. 反转形态确认: Pin Bar / Bullish Engulfing / 缩量企稳 (三选一)
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, Any


def get_hourly_confirmation(df_60m: pd.DataFrame,
                            support_price: float,
                            config: Optional[Dict[str, Any]] = None) -> Tuple[bool, str]:
    """
    对单笔信号进行60分钟二次确认。

    在全量60m数据中搜索支撑触及，动态锚定到最后触及点，
    然后检查否决条件和反转形态。

    Args:
        df_60m: 信号等待窗口期间的60分钟K线数据
                列: open, high, low, close, volume
        support_price: 入场依据的支撑位价格
        config: 可选参数覆盖

    Returns:
        (是否通过, 原因描述)
    """
    if config is None:
        config = {}

    touch_tolerance = config.get('touch_tolerance', 0.015)
    min_touch_count = config.get('min_touch_count', 1)
    big_red_drop = config.get('big_red_drop', 0.015)
    big_red_vol_mult = config.get('big_red_vol_mult', 2.0)
    pinbar_ratio = config.get('pinbar_ratio', 2.0)

    if df_60m is None or df_60m.empty or len(df_60m) < 8:
        return False, "60分钟K线数据不足"

    # ── 第一层: 在全量数据中搜索支撑触及 ──
    touch_mask = ((df_60m['low'] <= support_price * (1 + touch_tolerance)) &
                  (df_60m['low'] >= support_price * (1 - touch_tolerance)))
    touch_indices = df_60m.index[touch_mask]

    if len(touch_indices) < min_touch_count:
        return False, f"支撑精确触及不足 ({len(touch_indices)}/{min_touch_count})"

    # 动态锚定: 以最后一次触及点为中心
    last_touch_idx = touch_indices[-1]
    touch_pos = df_60m.index.get_loc(last_touch_idx)

    # 分析窗口: 触及点前8根 + 后8根
    win_start = max(0, touch_pos - 8)
    win_end = min(len(df_60m), touch_pos + 9)
    window = df_60m.iloc[win_start:win_end].copy()

    # 触及点在窗口中的相对位置
    touch_offset = touch_pos - win_start
    # 否决/形态检查范围: 触及点附近到窗口末尾
    after_start = max(0, touch_offset - 3)

    # ── 第二层: 否决条件 ──
    window['vol_ma5'] = window['volume'].rolling(5, min_periods=1).mean().shift(1)
    window['body_drop'] = (window['open'] - window['close']) / window['open']
    window['is_big_red'] = ((window['close'] < window['open']) &
                            (window['body_drop'] > big_red_drop) &
                            (window['volume'] > window['vol_ma5'] * big_red_vol_mult))
    if window['is_big_red'].iloc[after_start:].any():
        return False, "放量大阴线"

    # 连续3根阴线且收盘持续走低
    after_bars = window.iloc[after_start:]
    consecutive_red = 0
    for i in range(len(after_bars)):
        row = after_bars.iloc[i]
        if row['close'] < row['open']:
            if i > 0 and row['close'] < after_bars.iloc[i - 1]['close']:
                consecutive_red += 1
                if consecutive_red >= 3:
                    return False, "连续3根阴线走低"
            else:
                consecutive_red = 1
        else:
            consecutive_red = 0

    # 收盘有效跌破支撑
    close_breach = after_bars['close'] < support_price * 0.995
    if close_breach.any():
        return False, "收盘跌破支撑>0.5%"

    # ── 第三层: 反转形态确认 ──
    window['body'] = abs(window['close'] - window['open'])
    window['lower_shadow'] = window[['open', 'close']].min(axis=1) - window['low']
    window['upper_shadow'] = window['high'] - window[['open', 'close']].max(axis=1)

    # Pin Bar
    window['is_pinbar'] = ((window['lower_shadow'] > window['body'] * pinbar_ratio) &
                           (window['close'] > window['low'] + window['lower_shadow'] * 0.5))

    # Bullish Engulfing
    prev_open = window['open'].shift(1)
    prev_close = window['close'].shift(1)
    window['is_engulf'] = ((window['close'] > window['open']) &
                           (prev_close < prev_open) &
                           (window['open'] < prev_close) &
                           (window['close'] > prev_open))

    # 缩量企稳: vol < 0.8x MA20, 涨幅 0.2%~0.8%, 下影线 > 上影线
    vol_ma20 = df_60m['volume'].rolling(20, min_periods=5).mean()
    window['vol_ma20'] = vol_ma20.iloc[win_start:win_end].values
    vol_shrink = window['volume'] < window['vol_ma20'] * 0.8
    gain = (window['close'] - window['open']) / window['open']
    mild_bull = (window['close'] > window['open']) & gain.between(0.002, 0.008)
    lower_gt_upper = window['lower_shadow'] > window['upper_shadow']
    window['is_shrink_stable'] = vol_shrink & mild_bull & lower_gt_upper

    # 在触及点附近到窗口末尾检查反转形态
    rev_start = max(0, touch_offset - 2)
    rev_end = min(len(window), touch_offset + 6)
    check_range = window.iloc[rev_start:rev_end]

    has_pattern = (check_range['is_pinbar'].any() or
                   check_range['is_engulf'].any() or
                   check_range['is_shrink_stable'].any())

    if not has_pattern:
        return False, "无反转形态"

    return True, "通过60分钟确认"
