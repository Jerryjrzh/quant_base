#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场结构分析模块 (Market Structure Analyzer)
基于 sys_apply_tasks.md / sys_apply_steps.md 设计

功能:
1. Swing High/Low 检测 (zigzag 算法)
2. 支撑/阻力位计算 (静态 + 动态)
3. Volume Profile POC
4. 趋势方向识别 (UP / DOWN / RANGE)
5. 结构特征聚合 (用于模型特征输入)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Any
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class SwingPoint:
    """摆动点"""
    idx: int          # 位置索引 (iloc 位置)
    price: float
    test_count: int   # 被测试次数
    point_type: str   # 'high' | 'low'


@dataclass
class KeyLevel:
    """关键价位"""
    price: float
    level_type: str   # 'swing_high' | 'swing_low' | 'ma' | 'poc'
    test_count: int = 0
    strength: float = 1.0  # 强度: 测试次数越多越强


@dataclass
class SupportLevel:
    """带置信度的支撑位 (用于融合 V2 形态特征)"""
    price: float
    source: str          # 'swing_low', 'ma20', 'ma60', 'poc', 'ma_cluster', 'ma60_washed', 'pit_bottom'
    confidence: float = 0.5  # 0-1, 越高支撑越可靠
    tests: int = 0


@dataclass
class MarketStructure:
    """完整的市场结构描述"""
    trend_direction: str             # 'UP' | 'DOWN' | 'RANGE'
    swing_highs: List[SwingPoint]
    swing_lows: List[SwingPoint]
    supports: List[KeyLevel]
    resistances: List[KeyLevel]
    volume_poc: Optional[float]      # Volume Profile POC
    current_price: float
    ma20: Optional[float]
    ma60: Optional[float]
    atr: float
    structure_strength: float        # 结构强度 0-1


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------

def detect_swing_points(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    lookback: int = 5,
    min_tests: int = 1,
    tolerance: float = 0.01,
    breakthrough: float = 0.015,
) -> Tuple[List[SwingPoint], List[SwingPoint]]:
    """
    检测摆动高低点

    Args:
        high: 最高价序列
        low: 最低价序列
        close: 收盘价序列
        lookback: 左/右各看 lookback 天确认局部极值
        min_tests: 最少被测试次数
        tolerance: 触及容忍度 (±tolerance 视为测试)
        breakthrough: 有效突破阈值 (收盘突破 breakthrough 则视为突破)

    Returns:
        (swing_highs, swing_lows)
    """
    n = len(high)
    swing_highs: List[SwingPoint] = []
    swing_lows: List[SwingPoint] = []

    for i in range(lookback, n - lookback):
        # --- 局部高点 ---
        window_high = high.iloc[max(0, i - lookback): i + lookback + 1]
        if high.iloc[i] == window_high.max():
            tests = _count_tests_high(high, low, close, i, high.iloc[i],
                                      tolerance, breakthrough)
            if tests >= min_tests:
                swing_highs.append(SwingPoint(i, float(high.iloc[i]), tests, 'high'))

        # --- 局部低点 ---
        window_low = low.iloc[max(0, i - lookback): i + lookback + 1]
        if low.iloc[i] == window_low.min():
            tests = _count_tests_low(high, low, close, i, low.iloc[i],
                                     tolerance, breakthrough)
            if tests >= min_tests:
                swing_lows.append(SwingPoint(i, float(low.iloc[i]), tests, 'low'))

    return swing_highs, swing_lows


def _count_tests_high(
    high: pd.Series, low: pd.Series, close: pd.Series,
    peak_idx: int, peak_price: float, tolerance: float, breakthrough: float
) -> int:
    tests = 0
    for j in range(peak_idx + 1, len(close)):
        if high.iloc[j] >= peak_price * (1 - tolerance):
            tests += 1
            if close.iloc[j] > peak_price * (1 + breakthrough):
                break
    return tests


def _count_tests_low(
    high: pd.Series, low: pd.Series, close: pd.Series,
    peak_idx: int, peak_price: float, tolerance: float, breakthrough: float
) -> int:
    tests = 0
    for j in range(peak_idx + 1, len(close)):
        if low.iloc[j] <= peak_price * (1 + tolerance):
            tests += 1
            if close.iloc[j] < peak_price * (1 - breakthrough):
                break
    return tests


# ---------------------------------------------------------------------------
# 趋势方向识别
# ---------------------------------------------------------------------------

def identify_trend_direction(
    swing_highs: List[SwingPoint],
    swing_lows: List[SwingPoint],
    close: pd.Series,
    ma20: Optional[float] = None,
    ma60: Optional[float] = None,
) -> str:
    """
    根据最近 2-3 个摆动点判断趋势方向

    Returns: 'UP' | 'DOWN' | 'RANGE'
    """
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return _fallback_trend(close, ma20, ma60)

    recent_highs = sorted(swing_highs, key=lambda p: p.idx, reverse=True)[:3]
    recent_lows = sorted(swing_lows, key=lambda p: p.idx, reverse=True)[:3]

    higher_highs = all(
        recent_highs[i].price > recent_highs[i + 1].price
        for i in range(len(recent_highs) - 1)
    )
    higher_lows = all(
        recent_lows[i].price > recent_lows[i + 1].price
        for i in range(len(recent_lows) - 1)
    )
    lower_highs = all(
        recent_highs[i].price < recent_highs[i + 1].price
        for i in range(len(recent_highs) - 1)
    )
    lower_lows = all(
        recent_lows[i].price < recent_lows[i + 1].price
        for i in range(len(recent_lows) - 1)
    )

    if higher_highs and higher_lows:
        return 'UP'
    elif lower_highs and lower_lows:
        return 'DOWN'
    else:
        return _fallback_trend(close, ma20, ma60)


def _fallback_trend(
    close: pd.Series,
    ma20: Optional[float],
    ma60: Optional[float],
) -> str:
    if ma20 is not None and ma60 is not None:
        current = float(close.iloc[-1])
        if current > ma20 > ma60:
            return 'UP'
        elif current < ma20 < ma60:
            return 'DOWN'
    return 'RANGE'


# ---------------------------------------------------------------------------
# Volume Profile POC
# ---------------------------------------------------------------------------

def calculate_volume_profile_poc(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    volume: pd.Series,
    n_bins: int = 50,
) -> Optional[float]:
    """
    计算 Volume Profile POC (成交量最密集的价格)
    """
    try:
        if volume.isna().all() or (volume == 0).all():
            return None

        price_min = float(low.min())
        price_max = float(high.max())
        if price_max <= price_min:
            return None

        bin_edges = np.linspace(price_min, price_max, n_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_volume = np.zeros(n_bins)

        mid_prices = (high + low + close) / 3.0
        mid_arr = mid_prices.values
        vol_arr = volume.values

        for i in range(len(mid_arr)):
            if np.isnan(mid_arr[i]) or np.isnan(vol_arr[i]):
                continue
            bin_idx = np.searchsorted(bin_edges, mid_arr[i]) - 1
            bin_idx = max(0, min(bin_idx, n_bins - 1))
            bin_volume[bin_idx] += vol_arr[i]

        poc_idx = int(np.argmax(bin_volume))
        return float(bin_centers[poc_idx])

    except Exception as e:
        logger.warning(f"Volume Profile POC 计算失败: {e}")
        return None


# ---------------------------------------------------------------------------
# 关键支撑/阻力位计算
# ---------------------------------------------------------------------------

def get_key_levels(
    swing_highs: List[SwingPoint],
    swing_lows: List[SwingPoint],
    ma20: Optional[float],
    ma60: Optional[float],
    volume_poc: Optional[float],
    current_price: float,
    atr: float = 0.0,
    min_separation_pct: float = 0.02,
) -> Tuple[List[KeyLevel], List[KeyLevel]]:
    """
    计算当前价格上方和下方的关键价位

    Returns:
        (supports, resistances) 按距离从近到远排序
    """
    supports: List[KeyLevel] = []
    resistances: List[KeyLevel] = []

    # 摆动低点 -> 支撑
    for sp in swing_lows:
        if sp.price < current_price:
            supports.append(KeyLevel(
                sp.price, 'swing_low', sp.test_count,
                strength=min(sp.test_count / 3.0, 1.0)
            ))

    # 摆动高点 -> 阻力
    for sp in swing_highs:
        if sp.price > current_price:
            resistances.append(KeyLevel(
                sp.price, 'swing_high', sp.test_count,
                strength=min(sp.test_count / 3.0, 1.0)
            ))

    # 均线支撑/阻力
    for ma_val, ma_name in [(ma20, 'ma20'), (ma60, 'ma60')]:
        if ma_val is not None and not np.isnan(ma_val):
            if ma_val < current_price:
                supports.append(KeyLevel(ma_val, f'ma_{ma_name}', 0, 0.7))
            else:
                resistances.append(KeyLevel(ma_val, f'ma_{ma_name}', 0, 0.7))

    # Volume POC
    if volume_poc is not None:
        if volume_poc < current_price:
            supports.append(KeyLevel(volume_poc, 'poc', 0, 0.8))
        else:
            resistances.append(KeyLevel(volume_poc, 'poc', 0, 0.8))

    # 去重合并 (距离 < min_separation_pct 的合并)
    supports = _merge_levels(supports, min_separation_pct)
    resistances = _merge_levels(resistances, min_separation_pct)

    # 按距离排序 (近 -> 远)
    supports.sort(key=lambda l: abs(l.price - current_price))
    resistances.sort(key=lambda l: abs(l.price - current_price))

    return supports, resistances


def _merge_levels(levels: List[KeyLevel], min_sep_pct: float) -> List[KeyLevel]:
    """合并距离过近的价位"""
    if not levels:
        return levels
    merged: List[KeyLevel] = []
    used = [False] * len(levels)
    for i, lv in enumerate(levels):
        if used[i]:
            continue
        group = [lv]
        used[i] = True
        for j in range(i + 1, len(levels)):
            if used[j]:
                continue
            if abs(levels[j].price - lv.price) / lv.price < min_sep_pct:
                group.append(levels[j])
                used[j] = True
        # 取组内测试次数最多的价位
        best = max(group, key=lambda x: x.test_count)
        avg_price = np.mean([x.price for x in group])
        total_tests = sum(x.test_count for x in group)
        best_strength = max(x.strength for x in group)
        merged.append(KeyLevel(
            float(avg_price), best.level_type,
            total_tests, best_strength
        ))
    return merged


# ---------------------------------------------------------------------------
# ATR 计算 (复用 indicators 模块逻辑)
# ---------------------------------------------------------------------------

def compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """计算 ATR，返回最新一个 ATR 值"""
    if 'atr' in df.columns:
        val = df['atr'].iloc[-1]
        if not pd.isna(val):
            return float(val)

    high = df['high']
    low = df['low']
    close = df['close']
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr = tr.ewm(span=period, adjust=False).mean()
    return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else float(df['close'].iloc[-1]) * 0.03


# ---------------------------------------------------------------------------
# 完整结构分析入口
# ---------------------------------------------------------------------------

def analyze_market_structure(
    df: pd.DataFrame,
    lookback_days: int = 60,
    swing_lookback: int = 5,
    min_tests: int = 1,
) -> MarketStructure:
    """
    对给定数据做完整的市场结构分析

    Args:
        df: 完整 OHLCV + 指标数据 (至少 lookback_days + 30 行)
        lookback_days: 用于结构分析的回看天数
        swing_lookback: 摆动点检测的回看窗口
        min_tests: 摆动点最少测试次数

    Returns:
        MarketStructure 数据对象
    """
    # 截取分析窗口 (保留额外 30 天用于 MA 计算)
    total_needed = lookback_days + 30
    if len(df) > total_needed:
        analysis_df = df.tail(total_needed).reset_index(drop=True)
    else:
        analysis_df = df.reset_index(drop=True)

    n = len(analysis_df)
    current_price = float(analysis_df['close'].iloc[-1])

    # --- MA ---
    ma20_series = analysis_df['close'].rolling(20).mean()
    ma60_series = analysis_df['close'].rolling(60).mean()
    ma20 = float(ma20_series.iloc[-1]) if not pd.isna(ma20_series.iloc[-1]) else None
    ma60 = float(ma60_series.iloc[-1]) if not pd.isna(ma60_series.iloc[-1]) else None

    # --- ATR ---
    atr = compute_atr(analysis_df)

    # --- 摆动点检测 (在 lookback_days 窗口内) ---
    window_df = analysis_df.tail(lookback_days).reset_index(drop=True)
    swing_highs, swing_lows = detect_swing_points(
        window_df['high'], window_df['low'], window_df['close'],
        lookback=swing_lookback, min_tests=min_tests,
    )

    # --- 趋势方向 ---
    trend = identify_trend_direction(swing_highs, swing_lows,
                                     window_df['close'], ma20, ma60)

    # --- Volume Profile POC ---
    volume_poc = calculate_volume_profile_poc(
        window_df['close'], window_df['high'],
        window_df['low'], window_df['volume'],
    )

    # --- 关键价位 ---
    supports, resistances = get_key_levels(
        swing_highs, swing_lows, ma20, ma60, volume_poc, current_price, atr,
    )

    # --- 结构强度 ---
    strength = _calculate_structure_strength(
        trend, supports, resistances, swing_highs, swing_lows,
    )

    return MarketStructure(
        trend_direction=trend,
        swing_highs=swing_highs,
        swing_lows=swing_lows,
        supports=supports,
        resistances=resistances,
        volume_poc=volume_poc,
        current_price=current_price,
        ma20=ma20,
        ma60=ma60,
        atr=atr,
        structure_strength=strength,
    )


def _calculate_structure_strength(
    trend: str,
    supports: List[KeyLevel],
    resistances: List[KeyLevel],
    swing_highs: List[SwingPoint],
    swing_lows: List[SwingPoint],
) -> float:
    """
    计算结构强度 (0-1): 支撑越多、测试次数越多、趋势越明确 -> 越强
    """
    score = 0.0

    # 趋势明确度 (UP=0.4, RANGE=0.2, DOWN=0.0)
    trend_score = {'UP': 0.4, 'RANGE': 0.2, 'DOWN': 0.0}.get(trend, 0.2)
    score += trend_score

    # 支撑数量和质量
    if supports:
        support_quality = min(len(supports) / 3.0, 1.0) * 0.3
        avg_tests = np.mean([s.test_count for s in supports[:3]]) if supports else 0
        test_bonus = min(avg_tests / 3.0, 1.0) * 0.15
        score += support_quality + test_bonus

    # 摆动点确认度
    total_swings = len(swing_highs) + len(swing_lows)
    swing_bonus = min(total_swings / 6.0, 1.0) * 0.15
    score += swing_bonus

    return min(score, 1.0)


# ---------------------------------------------------------------------------
# V2 形态特征融合支撑位
# ---------------------------------------------------------------------------

def get_fused_supports(
    structure: MarketStructure,
    v2_features: Optional[Dict[str, Any]] = None,
) -> List[SupportLevel]:
    """
    将 market_structure 的支撑位与 V2 形态特征融合，
    生成带置信度的支撑位列表。

    Args:
        structure: analyze_market_structure 返回的结构对象
        v2_features: V2 特征字典

    Returns:
        按置信度从高到低排序的支撑位列表
    """
    fused: List[SupportLevel] = []

    # 1. 基础支撑位 (来自 market_structure)
    for level in structure.supports:
        base_conf = min(level.test_count / 5.0, 1.0) if level.test_count > 0 else 0.4
        if level.level_type in ('swing_low',):
            base_conf = max(base_conf, 0.4)
        elif level.level_type.startswith('ma_'):
            base_conf = max(base_conf, 0.3)

        fused.append(SupportLevel(
            price=level.price,
            source=level.level_type,
            confidence=round(base_conf, 2),
            tests=level.test_count,
        ))

    if v2_features is None:
        fused.sort(key=lambda x: x.confidence, reverse=True)
        return fused

    # 2. 均线束粘合支撑 (ma_glue) - 方向不确定，严格限制使用条件
    glue_days = v2_features.get('ma_glue_max_days', 0)
    glue_recency = v2_features.get('ma_glue_recency', 999)
    rs_rank_mean = v2_features.get('rs_rank_mean_20d', 0.5)
    rs_trend = v2_features.get('rs_rank_trend_20d', 0)
    trend_up = (structure.trend_direction == 'UP')

    if glue_days >= 5 and glue_recency <= 3:
        # V3: 仅在 UP 趋势 + rs_rank > 0.7 时启用 ma_cluster
        if trend_up and rs_rank_mean > 0.7:
            ma_cluster_price = None
            if structure.ma20 is not None and structure.ma60 is not None:
                ma_cluster_price = (structure.ma20 + structure.ma60) / 2
            elif structure.ma20 is not None:
                ma_cluster_price = structure.ma20
            elif structure.ma60 is not None:
                ma_cluster_price = structure.ma60

            if ma_cluster_price is not None and ma_cluster_price < structure.current_price:
                fused.append(SupportLevel(
                    price=round(ma_cluster_price, 2),
                    source='ma_cluster',
                    confidence=0.6,
                    tests=int(glue_days),
                ))

    # 3. MA60 洗盘支撑 (破位后收回)
    washout_flag = v2_features.get('washout_ma60_flag', 0)
    if washout_flag == 1 and structure.ma60 is not None and structure.ma60 < structure.current_price:
        fused.append(SupportLevel(
            price=structure.ma60,
            source='ma60_washed',
            confidence=0.9,
            tests=2,
        ))

    # 4. (V3: pit_bottom 已移除 — 历史验证负贡献 -0.36%)

    # 5. 相对强度确认: 上调非 ma_cluster 支撑的置信度
    if rs_rank_mean > 0.7 and rs_trend > 0:
        for level in fused:
            if level.source != 'ma_cluster':
                level.confidence = round(min(level.confidence * 1.1, 1.0), 2)

    # 去重: 相同 (price, source) 保留置信度最高的
    seen: Dict[Tuple[float, str], SupportLevel] = {}
    for level in fused:
        key = (round(level.price, 2), level.source)
        if key not in seen or level.confidence > seen[key].confidence:
            seen[key] = level
    unique_fused = list(seen.values())

    unique_fused.sort(key=lambda x: x.confidence, reverse=True)
    return unique_fused


# ---------------------------------------------------------------------------
# 便捷函数: 将结构分析转为 dict (便于 JSON 序列化)
# ---------------------------------------------------------------------------

def structure_to_dict(structure: MarketStructure) -> dict:
    """将 MarketStructure 转为 dict"""
    return {
        'trend_direction': structure.trend_direction,
        'current_price': structure.current_price,
        'ma20': structure.ma20,
        'ma60': structure.ma60,
        'atr': structure.atr,
        'volume_poc': structure.volume_poc,
        'structure_strength': structure.structure_strength,
        'supports': [
            {'price': s.price, 'type': s.level_type, 'tests': s.test_count, 'strength': s.strength}
            for s in structure.supports
        ],
        'resistances': [
            {'price': r.price, 'type': r.level_type, 'tests': r.test_count, 'strength': r.strength}
            for r in structure.resistances
        ],
        'swing_highs': [
            {'idx': s.idx, 'price': s.price, 'tests': s.test_count}
            for s in structure.swing_highs
        ],
        'swing_lows': [
            {'idx': s.idx, 'price': s.price, 'tests': s.test_count}
            for s in structure.swing_lows
        ],
    }
