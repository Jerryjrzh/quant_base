#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
动态出场管理器 (Dynamic Exit Manager)

基于持仓期间每日K线形态，动态调整止损/止盈:
- 危险信号 (D1-D5): 触发主动止损/减仓
- 强势信号 (S1-S3): 触发止损上移
- 衰竭信号 (E1-E3): 触发主动止盈

参照文档: doc/0613_super_trend_v2/fused_backtest_review1.md
"""

import numpy as np
import pandas as pd
from typing import List, Optional, Tuple, Dict
from dataclasses import dataclass


@dataclass
class SupportLevel:
    price: float
    source: str
    confidence: float = 0.5
    tests: int = 0


def extract_candle(day_row) -> dict:
    """从DataFrame的一行中提取标准K线字典"""
    return {
        'open': float(day_row['open']),
        'high': float(day_row['high']),
        'low': float(day_row['low']),
        'close': float(day_row['close']),
        'volume': float(day_row.get('volume', 0)),
    }


def get_dynamic_support(path_df: pd.DataFrame, idx: int, lookback: int = 5) -> Optional[float]:
    """
    取最近 lookback 日的最低点作为动态支撑。
    持仓期间价格创新低后，D4 用动态支撑替代固定入场支撑。

    Args:
        path_df: 从入场日开始的价格 DataFrame
        idx: 当前日在 path_df 中的索引位置
        lookback: 回看天数

    Returns:
        动态支撑价格，若数据不足则返回 None
    """
    if idx < lookback:
        return None
    recent_low = path_df['low'].iloc[idx - lookback:idx].min()
    return float(recent_low)


def detect_danger_signals(
    today: dict,
    prev_days: List[dict],
    entry_price: float,
    supports: List,
    position: float,
    dynamic_support: Optional[float] = None,
) -> Optional[Dict]:
    """
    检测危险信号，返回 {'code': str, 'severity': 'exit'/'reduce'} 或 None

    D1: 放量阴线吞没 — 收阴, 量 > 5日均量1.5倍, 收盘 < 前日最低
    D2: 连续缩量阴跌 — 连续3天收阴, 量递减, 累计跌幅 > 3%
    D4: 跌破动态支撑 — 收盘 < 动态支撑 (最近5日低点) 或入场支撑
    D5: 长上影线缩量 — 上影线 > 实体2倍, 量 < 5日均量
    """
    avg_vol_5 = (
        np.mean([d['volume'] for d in prev_days[-5:]])
        if len(prev_days) >= 5
        else today['volume']
    )

    # D1: 放量阴线吞没
    if today['close'] < today['open']:
        if today['volume'] > avg_vol_5 * 1.5:
            if prev_days and today['close'] < prev_days[-1]['low']:
                return {'code': 'D1', 'severity': 'exit'}

    # D2: 连续缩量阴跌
    if len(prev_days) >= 2:
        last3 = [prev_days[-2], prev_days[-1], today]
        if all(d['close'] < d['open'] for d in last3):
            if last3[0]['volume'] > last3[1]['volume'] > last3[2]['volume']:
                cum_drop = (today['close'] - last3[0]['open']) / last3[0]['open']
                if cum_drop < -0.03:
                    return {'code': 'D2', 'severity': 'exit'}

    # D4: 跌破动态支撑 (优先用动态支撑，取两者中较高的)
    fixed_support = supports[0].price if supports else entry_price * 0.95
    effective_support = fixed_support
    if dynamic_support is not None and dynamic_support > fixed_support:
        effective_support = dynamic_support
    if today['close'] < effective_support:
        return {'code': 'D4', 'severity': 'exit'}

    # D5: 长上影线缩量
    upper_shadow = today['high'] - max(today['open'], today['close'])
    body = abs(today['close'] - today['open']) + 0.001
    if upper_shadow > body * 2:
        if len(prev_days) >= 5 and today['volume'] < avg_vol_5:
            return {'code': 'D5', 'severity': 'reduce'}

    return None


def detect_strength_signals(
    today: dict,
    prev_days: List[dict],
    highest_close: float,
    entry_price: float,
) -> Optional[Dict]:
    """
    检测强势信号，返回 {'code': str, 'level': 'strong'/'moderate'} 或 None

    S1: 放量阳线创新高 — 收阳, 量 > 5日均量1.3倍, 收盘创持仓期新高
    S2: 缩量回踩不破 — 回踩至前日低点附近(±0.5%), 缩量, 收阳
    S3: 连续缩量小阳 — 连续3天收阳, 实体 < 2%, 量递减
    """
    avg_vol_5 = (
        np.mean([d['volume'] for d in prev_days[-5:]])
        if len(prev_days) >= 5
        else today['volume']
    )

    # S1: 放量阳线创新高
    if today['close'] > today['open'] and today['close'] > highest_close:
        if today['volume'] > avg_vol_5 * 1.3:
            return {'code': 'S1', 'level': 'strong'}

    # S2: 缩量回踩不破
    if prev_days:
        prev_low = prev_days[-1]['low']
        if abs(today['low'] - prev_low) / prev_low < 0.005:
            if today['close'] > today['open']:
                if today['volume'] < avg_vol_5:
                    return {'code': 'S2', 'level': 'moderate'}

    # S3: 连续缩量小阳
    if len(prev_days) >= 2:
        last3 = [prev_days[-2], prev_days[-1], today]
        if all(d['close'] > d['open'] for d in last3):
            bodies = [abs(d['close'] - d['open']) / d['open'] for d in last3]
            vols = [d['volume'] for d in last3]
            if all(b < 0.02 for b in bodies) and vols[0] > vols[1] > vols[2]:
                return {'code': 'S3', 'level': 'moderate'}

    return None


def detect_exhaustion_signals(
    today: dict,
    prev_days: List[dict],
    highest_close: float,
    entry_price: float,
) -> Optional[Dict]:
    """
    检测衰竭信号，返回 {'code': str, 'severity': 'exit'/'reduce'} 或 None

    E1: 高位十字星 — 实体 < 0.5%, 上下影线 > 实体3倍, 位于持仓期高位
    E2: 放量滞涨 — 收阳但涨幅 < 1%, 量 > 5日均量2倍
    E3: 连续冲高回落 — 连续2天最高价创新高但收盘回到前日收盘下方
    """
    body = abs(today['close'] - today['open'])
    upper_shadow = today['high'] - max(today['open'], today['close'])
    lower_shadow = min(today['open'], today['close']) - today['low']
    avg_vol_5 = (
        np.mean([d['volume'] for d in prev_days[-5:]])
        if len(prev_days) >= 5
        else today['volume']
    )

    # E1: 高位十字星 (V3 放宽: 实体 < 1%, 影线 > 实体2倍)
    if body < 0.01 * today['open'] and upper_shadow > body * 2 and lower_shadow > body * 2:
        if today['high'] >= highest_close * 0.98:
            return {'code': 'E1', 'severity': 'reduce'}

    # E2: 放量滞涨 (V3 放宽: 量比阈值 1.5x)
    if today['close'] > today['open']:
        gain = (today['close'] - today['open']) / today['open']
        if gain < 0.01 and today['volume'] > avg_vol_5 * 1.5:
            return {'code': 'E2', 'severity': 'exit'}

    # E3: 连续冲高回落
    if len(prev_days) >= 2:
        yesterday = prev_days[-1]
        day_before = prev_days[-2]
        if today['high'] > yesterday['high'] and today['close'] < yesterday['close']:
            if yesterday['high'] > day_before['high'] and yesterday['close'] < day_before['close']:
                return {'code': 'E3', 'severity': 'exit'}

    return None


def run_dynamic_exit_manager(
    entry_date,
    entry_price: float,
    initial_stop: float,
    initial_tp: float,
    path_df: pd.DataFrame,
    supports: List,
    atr: float,
    v2_features: Optional[dict] = None,
    max_hold_days: int = 22,
    enabled_signals: Optional[set] = None,
    max_stop_loss_pct: float = 0.08,
    resistances: Optional[List] = None,
) -> Tuple:
    """
    持仓期每日动态调整止损/止盈。

    Args:
        entry_date: 入场日期
        entry_price: 入场价格
        initial_stop: 初始止损价
        initial_tp: 初始止盈价
        path_df: 从入场日开始的价格DataFrame (open, high, low, close, volume)
        supports: 融合支撑位列表 (用于D4判断)
        atr: 平均真实波幅
        v2_features: V2 形态特征 (保留扩展)
        max_hold_days: 最大持仓天数
        enabled_signals: 启用的信号集合, 如 {'D1','D2','D4','S1'}. None=全部启用
        max_stop_loss_pct: 硬性止损上限, 动态出场不会超过此亏损

    Returns:
        (exit_date, exit_price, exit_reason, trigger_signal, pnl_pct)
    """
    position = 1.0
    current_stop = initial_stop
    current_tp = initial_tp
    highest_close = entry_price
    prev_days = []
    hard_stop_floor = entry_price * (1 - max_stop_loss_pct)

    if enabled_signals is None:
        enabled_signals = {'D1', 'D2', 'D4', 'D5', 'S1', 'S2', 'S3', 'E1', 'E2', 'E3'}

    limit = min(len(path_df), max_hold_days + 1)

    for i in range(limit):
        day = path_df.iloc[i]

        if i == 0:
            prev_days.append(extract_candle(day))
            continue

        today_candle = extract_candle(day)

        # 计算动态支撑 (V3: 最近5日低点)
        dyn_support = get_dynamic_support(path_df, i)

        # 1. 危险信号检测 (优先级最高)
        danger = detect_danger_signals(
            today_candle, prev_days, entry_price, supports, position,
            dynamic_support=dyn_support,
        )
        if danger and danger['code'] in enabled_signals:
            if danger['severity'] == 'exit':
                exit_price = max(day['open'], hard_stop_floor)
                pnl = (exit_price / entry_price - 1)
                return (path_df.index[i], exit_price, 'dynamic_stop', danger['code'], pnl)
            elif danger['severity'] == 'reduce':
                position *= 0.5
                current_stop = max(current_stop, day['close'])

        # 2. 衰竭信号检测
        exhaustion = detect_exhaustion_signals(
            today_candle, prev_days, highest_close, entry_price
        )
        if exhaustion and exhaustion['code'] in enabled_signals and position > 0:
            if exhaustion['severity'] == 'exit':
                exit_price = day['open']
                pnl = (exit_price / entry_price - 1)
                return (path_df.index[i], exit_price, 'dynamic_tp', exhaustion['code'], pnl)
            elif exhaustion['severity'] == 'reduce':
                position *= 0.5
                current_stop = max(current_stop, day['close'])
                # Phase 3: E1 衰竭 → 收紧止盈到 close+3%
                if exhaustion['code'] == 'E1':
                    tight_tp = day['close'] * 1.03
                    current_tp = min(current_tp, tight_tp)

        # 3. 强势信号 → 上移止损 + Phase 3: S1 上调止盈目标
        strength = detect_strength_signals(
            today_candle, prev_days, highest_close, entry_price
        )
        if strength and strength['code'] in enabled_signals:
            if strength['level'] == 'strong':
                current_stop = max(current_stop, day['low'] - 0.5 * atr)
                # Phase 3: S1 强势 → 上调止盈到第二阻力位
                if strength['code'] == 'S1' and resistances and len(resistances) >= 2:
                    r2_price = resistances[1].price
                    if r2_price > current_tp:
                        current_tp = r2_price
            elif strength['level'] == 'moderate':
                if prev_days:
                    current_stop = max(current_stop, prev_days[-1]['low'])

        # 更新最高收盘价
        highest_close = max(highest_close, day['close'])

        # 4. 检查原始止损/止盈是否触发
        if day['low'] <= current_stop:
            exit_price = current_stop
            pnl = (exit_price / entry_price - 1)
            return (path_df.index[i], exit_price, 'initial_stop', None, pnl)
        if day['high'] >= current_tp:
            exit_price = current_tp
            pnl = (exit_price / entry_price - 1)
            return (path_df.index[i], exit_price, 'initial_tp', None, pnl)

        prev_days.append(today_candle)

    # 持有到期
    last_idx = min(limit - 1, len(path_df) - 1)
    last_day = path_df.iloc[last_idx]
    exit_price = last_day['close']
    pnl = (exit_price / entry_price - 1)
    return (path_df.index[last_idx], exit_price, 'expiry', None, pnl)


def run_dynamic_exit_detailed(
    entry_date,
    entry_price: float,
    initial_stop: float,
    initial_tp: float,
    path_df: pd.DataFrame,
    supports: List,
    atr: float,
    v2_features: Optional[dict] = None,
    max_hold_days: int = 22,
    enabled_signals: Optional[set] = None,
) -> Tuple:
    """
    与 run_dynamic_exit_manager 相同，但额外记录每个信号触发日的详细信息。
    用于验证脚本分析信号有效性。

    Returns:
        (exit_date, exit_price, exit_reason, trigger_signal, pnl_pct, signal_log)
        signal_log: List[dict] — 每次信号触发的详细记录
    """
    position = 1.0
    current_stop = initial_stop
    current_tp = initial_tp
    highest_close = entry_price
    prev_days = []
    signal_log = []

    if enabled_signals is None:
        enabled_signals = {'D1', 'D2', 'D4', 'D5', 'S1', 'S2', 'S3', 'E1', 'E2', 'E3'}

    limit = min(len(path_df), max_hold_days + 1)

    for i in range(limit):
        day = path_df.iloc[i]

        if i == 0:
            prev_days.append(extract_candle(day))
            continue

        today_candle = extract_candle(day)

        # 计算动态支撑 (V3)
        dyn_support = get_dynamic_support(path_df, i)

        # 1. 危险信号
        danger = detect_danger_signals(
            today_candle, prev_days, entry_price, supports, position,
            dynamic_support=dyn_support,
        )
        if danger and danger['code'] in enabled_signals:
            signal_log.append({
                'day_idx': i,
                'date': path_df.index[i],
                'code': danger['code'],
                'type': 'danger',
                'severity': danger['severity'],
                'day_high': day['high'],
                'day_low': day['low'],
                'day_close': day['close'],
                'current_stop': current_stop,
                'pnl_at_signal': (day['close'] / entry_price - 1),
            })
            if danger['severity'] == 'exit':
                exit_price = day['open']
                pnl = (exit_price / entry_price - 1)
                return (path_df.index[i], exit_price, 'dynamic_stop', danger['code'], pnl, signal_log)
            elif danger['severity'] == 'reduce':
                position *= 0.5
                current_stop = max(current_stop, day['close'])

        # 2. 衰竭信号
        exhaustion = detect_exhaustion_signals(
            today_candle, prev_days, highest_close, entry_price
        )
        if exhaustion and exhaustion['code'] in enabled_signals and position > 0:
            signal_log.append({
                'day_idx': i,
                'date': path_df.index[i],
                'code': exhaustion['code'],
                'type': 'exhaustion',
                'severity': exhaustion['severity'],
                'day_high': day['high'],
                'day_low': day['low'],
                'day_close': day['close'],
                'current_stop': current_stop,
                'pnl_at_signal': (day['close'] / entry_price - 1),
            })
            if exhaustion['severity'] == 'exit':
                exit_price = day['open']
                pnl = (exit_price / entry_price - 1)
                return (path_df.index[i], exit_price, 'dynamic_tp', exhaustion['code'], pnl, signal_log)
            elif exhaustion['severity'] == 'reduce':
                position *= 0.5
                current_stop = max(current_stop, day['close'])

        # 3. 强势信号
        strength = detect_strength_signals(
            today_candle, prev_days, highest_close, entry_price
        )
        if strength and strength['code'] in enabled_signals:
            signal_log.append({
                'day_idx': i,
                'date': path_df.index[i],
                'code': strength['code'],
                'type': 'strength',
                'level': strength['level'],
                'day_high': day['high'],
                'day_low': day['low'],
                'day_close': day['close'],
                'current_stop': current_stop,
                'pnl_at_signal': (day['close'] / entry_price - 1),
            })
            if strength['level'] == 'strong':
                current_stop = max(current_stop, day['low'] - 0.5 * atr)
            elif strength['level'] == 'moderate':
                if prev_days:
                    current_stop = max(current_stop, prev_days[-1]['low'])

        highest_close = max(highest_close, day['close'])

        # 4. 止损/止盈检查
        if day['low'] <= current_stop:
            exit_price = current_stop
            pnl = (exit_price / entry_price - 1)
            return (path_df.index[i], exit_price, 'initial_stop', None, pnl, signal_log)
        if day['high'] >= current_tp:
            exit_price = current_tp
            pnl = (exit_price / entry_price - 1)
            return (path_df.index[i], exit_price, 'initial_tp', None, pnl, signal_log)

        prev_days.append(today_candle)

    last_idx = min(limit - 1, len(path_df) - 1)
    last_day = path_df.iloc[last_idx]
    exit_price = last_day['close']
    pnl = (exit_price / entry_price - 1)
    return (path_df.index[last_idx], exit_price, 'expiry', None, pnl, signal_log)
