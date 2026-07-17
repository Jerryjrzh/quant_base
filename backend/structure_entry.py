#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化入场模块 (Structure-Based Entry)
基于 sys_apply_tasks.md / sys_apply_steps.md 设计

功能:
1. 结构过滤器 - 过滤不适合入场的信号
2. 回调入场 (Pullback Entry) - 等待回踩支撑位企稳后买入
3. 突破确认入场 (Breakout Confirmation) - 突破阻力后回踩确认
4. 入场状态机 - 管理 WAITING -> ENTERED / EXPIRED 状态
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from enum import Enum
import logging

from market_structure import MarketStructure, KeyLevel, SupportLevel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 枚举和数据类
# ---------------------------------------------------------------------------

class EntryState(Enum):
    WAITING = 'WAITING'
    ENTRY_SIGNAL = 'ENTRY_SIGNAL'
    ENTERED = 'ENTERED'
    EXPIRED = 'EXPIRED'
    FILTERED = 'FILTERED'


class EntryType(Enum):
    PULLBACK = 'pullback'        # 回调到支撑位买入
    BREAKOUT = 'breakout'        # 突破阻力后买入
    NONE = 'none'


@dataclass
class EntryConfig:
    """入场配置"""
    # 等待入场的最大天数
    max_wait_days: int = 5
    # 支撑位触及容忍度 (±1%)
    support_tolerance: float = 0.01
    # 企稳确认: 阳线最小实体比例 (相对全日振幅)
    bullish_body_ratio: float = 0.3
    # 企稳确认: 下影线长度至少是实体的 N 倍
    lower_shadow_ratio: float = 1.5
    # 结构过滤器: 最近阻力位在 X% 以内且支撑在 Y% 以外则过滤
    resistance_filter_pct: float = 0.02
    support_filter_pct: float = 0.05
    # 下降趋势中是否允许入场
    allow_downtrend_entry: bool = False


@dataclass
class EntrySignal:
    """入场信号"""
    entry_type: EntryType
    trigger_day_idx: int     # 触发入场的 iloc 位置
    entry_day_idx: int       # 实际入场的 iloc 位置 (触发次日)
    entry_price: float       # 入场价格 (次日开盘价)
    support_used: Optional[KeyLevel]   # 入场依据的支撑位
    confirmation_type: str   # 'bullish_candle' | 'long_lower_shadow' | 'breakout_pullback'
    confidence: float        # 入场信心度 0-1


@dataclass
class StructureFilterResult:
    """结构过滤结果"""
    passed: bool
    reason: str
    trend_direction: str
    nearest_support_dist: Optional[float]   # 最近支撑距离 (%)
    nearest_resistance_dist: Optional[float]  # 最近阻力距离 (%)
    structure_strength: float


# ---------------------------------------------------------------------------
# 结构过滤器
# ---------------------------------------------------------------------------

def structure_filter(
    structure: MarketStructure,
    config: Optional[EntryConfig] = None,
) -> StructureFilterResult:
    """
    结构过滤器: 判断信号是否值得入场

    过滤条件:
    1. 下降趋势中不做多 (可配置)
    2. 最近阻力位在 2% 以内且最近支撑在 5% 以外 -> 盈亏比差
    3. 无任何支撑位 -> 入场无依据
    """
    if config is None:
        config = EntryConfig()

    current = structure.current_price
    trend = structure.trend_direction

    # 计算距离
    nearest_support_dist = None
    nearest_resistance_dist = None

    if structure.supports:
        nearest_support_dist = (current - structure.supports[0].price) / current
    if structure.resistances:
        nearest_resistance_dist = (structure.resistances[0].price - current) / current

    # --- 过滤规则 1: 下降趋势 ---
    if trend == 'DOWN' and not config.allow_downtrend_entry:
        return StructureFilterResult(
            passed=False,
            reason=f"下降趋势中不做多 (趋势: {trend})",
            trend_direction=trend,
            nearest_support_dist=nearest_support_dist,
            nearest_resistance_dist=nearest_resistance_dist,
            structure_strength=structure.structure_strength,
        )

    # --- 过滤规则 2: 盈亏比差 ---
    if (nearest_resistance_dist is not None and nearest_support_dist is not None):
        if (nearest_resistance_dist < config.resistance_filter_pct and
                nearest_support_dist > config.support_filter_pct):
            return StructureFilterResult(
                passed=False,
                reason=f"上方空间不足: 阻力 {nearest_resistance_dist:.1%} vs 支撑 {nearest_support_dist:.1%}",
                trend_direction=trend,
                nearest_support_dist=nearest_support_dist,
                nearest_resistance_dist=nearest_resistance_dist,
                structure_strength=structure.structure_strength,
            )

    # --- 过滤规则 3: 无支撑位 ---
    if not structure.supports:
        return StructureFilterResult(
            passed=False,
            reason="无任何支撑位，入场缺乏依据",
            trend_direction=trend,
            nearest_support_dist=nearest_support_dist,
            nearest_resistance_dist=nearest_resistance_dist,
            structure_strength=structure.structure_strength,
        )

    return StructureFilterResult(
        passed=True,
        reason="通过结构过滤",
        trend_direction=trend,
        nearest_support_dist=nearest_support_dist,
        nearest_resistance_dist=nearest_resistance_dist,
        structure_strength=structure.structure_strength,
    )


# ---------------------------------------------------------------------------
# 回调入场检测 (Pullback Entry)
# ---------------------------------------------------------------------------

def check_pullback_entry(
    day_data: dict,
    supports: List[KeyLevel],
    config: Optional[EntryConfig] = None,
) -> Optional[Tuple[KeyLevel, str]]:
    """
    检查当日是否出现回调到支撑位并企稳

    Args:
        day_data: {'open', 'high', 'low', 'close'}
        supports: 支撑位列表 (按距离从近到远排序)
        config: 入场配置

    Returns:
        (支撑位, 确认类型) 或 None
    """
    if config is None:
        config = EntryConfig()

    if not supports:
        return None

    open_p = day_data['open']
    high_p = day_data['high']
    low_p = day_data['low']
    close_p = day_data['close']

    for support in supports[:3]:  # 只看最近的 3 个支撑
        support_price = support.price
        tolerance = support_price * config.support_tolerance

        # 检查是否回踩到支撑区 (最低价触及支撑位 ± tolerance)
        if low_p <= support_price + tolerance:
            # --- 企稳确认 1: 收阳线且收盘在支撑上方 ---
            body = abs(close_p - open_p)
            full_range = high_p - low_p if high_p > low_p else 0.001
            body_ratio = body / full_range if full_range > 0 else 0

            bullish_candle = (
                close_p > open_p and
                close_p > support_price and
                body_ratio >= config.bullish_body_ratio
            )

            # --- 企稳确认 2: 长下影线 ---
            lower_shadow = min(open_p, close_p) - low_p
            upper_shadow = high_p - max(open_p, close_p)
            real_body = abs(close_p - open_p)
            long_lower = (
                lower_shadow >= real_body * config.lower_shadow_ratio and
                close_p > support_price
            )

            if bullish_candle:
                return support, 'bullish_candle'
            elif long_lower:
                return support, 'long_lower_shadow'

    return None


# ---------------------------------------------------------------------------
# 融合支撑位的回调入场检测 (V2 Feature Fusion)
# ---------------------------------------------------------------------------

def check_pullback_entry_fused(
    day_data: dict,
    fused_supports: List[SupportLevel],
    v2_features: Optional[dict] = None,
    config: Optional[EntryConfig] = None,
) -> Optional[Tuple[SupportLevel, str]]:
    """
    使用融合支撑位检测回调入场。统一严格 K 线确认，不根据形态放宽。

    Args:
        day_data: {'open', 'high', 'low', 'close'}
        fused_supports: 融合支撑位列表 (按置信度排序)
        v2_features: V2 形态特征字典 (保留参数，供后续止损区分使用)
        config: 入场配置

    Returns:
        (融合支撑位, 确认类型) 或 None
    """
    if config is None:
        config = EntryConfig()

    if not fused_supports:
        return None

    open_p = day_data['open']
    high_p = day_data['high']
    low_p = day_data['low']
    close_p = day_data['close']

    for sup in fused_supports[:5]:
        tolerance = sup.price * config.support_tolerance

        if low_p <= sup.price + tolerance:
            body = abs(close_p - open_p)
            full_range = high_p - low_p if high_p > low_p else 0.001
            body_ratio = body / full_range if full_range > 0 else 0

            bullish_candle = (
                close_p > open_p and
                close_p > sup.price and
                body_ratio >= config.bullish_body_ratio
            )

            lower_shadow = min(open_p, close_p) - low_p
            real_body = abs(close_p - open_p)
            long_lower = (
                lower_shadow >= real_body * config.lower_shadow_ratio and
                close_p > sup.price
            )

            if bullish_candle:
                return sup, 'bullish_candle'
            elif long_lower:
                return sup, 'long_lower_shadow'

    return None

def check_breakout_entry(
    prev_day: dict,
    curr_day: dict,
    resistances: List[KeyLevel],
    config: Optional[EntryConfig] = None,
) -> Optional[Tuple[KeyLevel, str]]:
    """
    检查是否出现突破阻力后回踩确认

    Args:
        prev_day: 前一天数据
        curr_day: 当天数据
        resistances: 阻力位列表
        config: 入场配置

    Returns:
        (阻力位, 'breakout_pullback') 或 None
    """
    if config is None:
        config = EntryConfig()

    if not resistances:
        return None

    for resistance in resistances[:2]:
        r_price = resistance.price
        tolerance = r_price * config.support_tolerance

        # 前一天最高价突破阻力位
        if prev_day['high'] > r_price:
            # 当天回踩到阻力位附近 (原阻力变支撑)
            if curr_day['low'] <= r_price + tolerance and curr_day['close'] > r_price:
                return resistance, 'breakout_pullback'

    return None


# ---------------------------------------------------------------------------
# 入场风格分类器 (V3)
# ---------------------------------------------------------------------------

def classify_entry_style(
    structure: MarketStructure,
    v2_features: Optional[dict] = None,
    fine_score: float = 0.5,
) -> str:
    """
    基于结构特征分类入场风格: 'pullback' (等回调) 或 'breakout' (可追涨)

    强趋势 + 优质支撑 + 高得分 + 高 RS → breakout (可追涨)
    其他 → pullback (等回调)

    Args:
        structure: 市场结构分析结果
        v2_features: V2 形态特征
        fine_score: 精排得分

    Returns:
        'pullback' 或 'breakout'
    """
    trend_up = structure.trend_direction == 'UP'
    strong_types = {'swing_low', 'ma_ma20', 'ma_ma60', 'poc'}
    strong_support = any(
        s.level_type in strong_types
        for s in structure.supports
    )

    high_score = fine_score > 0.8
    rs_strong = (v2_features or {}).get('rs_rank_mean_20d', 0) > 0.7

    if trend_up and strong_support and high_score and rs_strong:
        return 'breakout'
    return 'pullback'


# ---------------------------------------------------------------------------
# 入场状态机 (核心)
# ---------------------------------------------------------------------------

def run_entry_state_machine(
    df: pd.DataFrame,
    structure: MarketStructure,
    signal_day_idx: int,
    config: Optional[EntryConfig] = None,
    fused_supports: Optional[List[SupportLevel]] = None,
    v2_features: Optional[dict] = None,
) -> Tuple[EntryState, Optional[EntrySignal]]:
    """
    运行入场状态机

    流程:
    1. 信号日 (signal_day_idx) 触发后进入 WAITING
    2. 在 signal_day+1 到 signal_day+max_wait_days 之间逐日检查:
       a. 回调到支撑位企稳 -> ENTRY_SIGNAL (次日开盘入场)
       b. 突破阻力后回踩确认 -> ENTRY_SIGNAL (次日开盘入场)
    3. 等待期满无信号 -> EXPIRED

    Args:
        df: 完整 OHLCV 数据
        structure: 信号日的市场结构
        signal_day_idx: 信号日的 iloc 位置
        config: 入场配置
        fused_supports: 融合支撑位列表 (提供时使用融合入场逻辑)
        v2_features: V2 形态特征

    Returns:
        (最终状态, 入场信号)
    """
    if config is None:
        config = EntryConfig()

    # 先过结构过滤器
    filter_result = structure_filter(structure, config)
    if not filter_result.passed:
        return EntryState.FILTERED, None

    # 入场检查窗口
    wait_start = signal_day_idx + 1
    wait_end = min(signal_day_idx + 1 + config.max_wait_days, len(df) - 1)

    if wait_start >= len(df) - 1:
        return EntryState.EXPIRED, None

    for day_idx in range(wait_start, wait_end + 1):
        day_data = {
            'open': float(df.iloc[day_idx]['open']),
            'high': float(df.iloc[day_idx]['high']),
            'low': float(df.iloc[day_idx]['low']),
            'close': float(df.iloc[day_idx]['close']),
        }

        # --- 检查回调入场 ---
        if fused_supports is not None:
            pullback_result = check_pullback_entry_fused(
                day_data, fused_supports, v2_features, config
            )
        else:
            pullback_result = check_pullback_entry(
                day_data, structure.supports, config
            )

        if pullback_result is not None:
            support_used, confirm_type = pullback_result
            # 入场日: 次日开盘
            entry_day = day_idx + 1
            if entry_day < len(df):
                entry_price = float(df.iloc[entry_day]['open'])
                # 融合模式下 support_used 是 SupportLevel, 转为 KeyLevel 以保持兼容
                if isinstance(support_used, SupportLevel):
                    kl_support = KeyLevel(
                        price=support_used.price,
                        level_type=support_used.source,
                        test_count=support_used.tests,
                        strength=support_used.confidence,
                    )
                else:
                    kl_support = support_used

                signal = EntrySignal(
                    entry_type=EntryType.PULLBACK,
                    trigger_day_idx=day_idx,
                    entry_day_idx=entry_day,
                    entry_price=entry_price,
                    support_used=kl_support,
                    confirmation_type=confirm_type,
                    confidence=_calc_entry_confidence(
                        day_data, kl_support, structure
                    ),
                )
                return EntryState.ENTRY_SIGNAL, signal

        # --- 检查突破入场 ---
        if day_idx > wait_start:
            prev_data = {
                'open': float(df.iloc[day_idx - 1]['open']),
                'high': float(df.iloc[day_idx - 1]['high']),
                'low': float(df.iloc[day_idx - 1]['low']),
                'close': float(df.iloc[day_idx - 1]['close']),
            }
            breakout_result = check_breakout_entry(
                prev_data, day_data, structure.resistances, config
            )
            if breakout_result is not None:
                resistance_used, confirm_type = breakout_result
                entry_day = day_idx + 1
                if entry_day < len(df):
                    entry_price = float(df.iloc[entry_day]['open'])
                    signal = EntrySignal(
                        entry_type=EntryType.BREAKOUT,
                        trigger_day_idx=day_idx,
                        entry_day_idx=entry_day,
                        entry_price=entry_price,
                        support_used=KeyLevel(
                            resistance_used.price, 'breakout_support',
                            resistance_used.test_count, resistance_used.strength
                        ),
                        confirmation_type=confirm_type,
                        confidence=_calc_entry_confidence(
                            day_data, resistance_used, structure
                        ),
                    )
                    return EntryState.ENTRY_SIGNAL, signal

    return EntryState.EXPIRED, None


# ---------------------------------------------------------------------------
# 入场信心度计算
# ---------------------------------------------------------------------------

def _calc_entry_confidence(
    day_data: dict,
    support: KeyLevel,
    structure: MarketStructure,
) -> float:
    """
    计算入场信心度 (0-1)

    因素:
    1. 支撑位强度 (测试次数越多越强)
    2. 趋势方向 (上升趋势更强)
    3. 结构强度
    """
    confidence = 0.5

    # 支撑位强度加成
    confidence += support.strength * 0.2

    # 趋势加成
    if structure.trend_direction == 'UP':
        confidence += 0.15
    elif structure.trend_direction == 'DOWN':
        confidence -= 0.15

    # 结构强度加成
    confidence += structure.structure_strength * 0.15

    return max(0.0, min(1.0, confidence))


# ---------------------------------------------------------------------------
# 便捷入口
# ---------------------------------------------------------------------------

def find_entry_opportunity(
    df: pd.DataFrame,
    structure: MarketStructure,
    signal_day_idx: int,
    config: Optional[EntryConfig] = None,
    fused_supports: Optional[List[SupportLevel]] = None,
    v2_features: Optional[dict] = None,
) -> Dict:
    """
    寻找入场机会的便捷入口

    Returns:
        dict with keys: state, signal, filter_result, summary
    """
    if config is None:
        config = EntryConfig()

    # 结构过滤
    filter_result = structure_filter(structure, config)

    if not filter_result.passed:
        return {
            'state': EntryState.FILTERED.value,
            'signal': None,
            'filter_result': filter_result,
            'summary': f"信号被过滤: {filter_result.reason}",
        }

    # 运行状态机
    state, signal = run_entry_state_machine(
        df, structure, signal_day_idx, config,
        fused_supports=fused_supports, v2_features=v2_features,
    )

    summary = ""
    if signal is not None:
        support_price_str = f"{signal.support_used.price:.2f}" if signal.support_used else "N/A"
        summary = (
            f"{signal.entry_type.value}入场: "
            f"触发日 {signal.trigger_day_idx}, "
            f"入场日 {signal.entry_day_idx}, "
            f"入场价 {signal.entry_price:.2f}, "
            f"依据支撑 {support_price_str}, "
            f"信心度 {signal.confidence:.2f}"
        )
    else:
        summary = f"等待 {config.max_wait_days} 天内未出现入场机会"

    return {
        'state': state.value,
        'signal': signal,
        'filter_result': filter_result,
        'summary': summary,
    }
