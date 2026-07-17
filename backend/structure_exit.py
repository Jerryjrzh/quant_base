#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化出场与仓位管理模块 (Structure-Based Exit & Position)
基于 sys_apply_tasks.md / sys_apply_steps.md 设计

功能:
1. 结构化止损 - 基于入场依据的支撑位设置止损
2. 分批止盈 - 阻力位减仓 + 追踪剩余仓位
3. 动态移动止损 - 上升趋势中上移止损到新低点下方
4. 仓位管理 - 基于风险的动态仓位计算
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from enum import Enum
import logging

from market_structure import MarketStructure, KeyLevel, SwingPoint

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 枚举和数据类
# ---------------------------------------------------------------------------

class ExitReason(Enum):
    STOP_LOSS = 'stop_loss'           # 止损
    TAKE_PROFIT_1 = 'take_profit_1'   # 第一目标止盈 (减仓50%)
    TAKE_PROFIT_2 = 'take_profit_2'   # 第二目标止盈 (清仓)
    TRAILING_STOP = 'trailing_stop'   # 追踪止损
    EXPIRY = 'expiry'                 # 到期离场
    BREAKEVEN_STOP = 'breakeven_stop' # 保本止损 (第一目标止盈后)


class PositionState(Enum):
    FULL = 'full'               # 满仓
    HALF = 'half'               # 半仓 (第一目标止盈后)
    CLOSED = 'closed'           # 已清仓


@dataclass
class ExitConfig:
    """出场配置"""
    # 止损缓冲 ATR 倍数
    stop_loss_atr_multiplier: float = 1.0
    # 硬性最大止损比例
    max_stop_loss_pct: float = 0.05
    # 第一止盈默认比例 (无阻力位时)
    default_tp1_pct: float = 0.10
    # 第二止盈默认比例
    default_tp2_pct: float = 0.20
    # 第一目标减仓比例
    tp1_reduce_ratio: float = 0.5
    # 追踪止损 ATR 倍数 (用于无阻力时)
    trailing_atr_multiplier: float = 2.0
    # 最大持仓天数
    max_hold_days: int = 22
    # 每笔交易最大风险比例 (占总资金)
    max_risk_per_trade: float = 0.005
    # A股最小交易单位
    min_lot_size: int = 100


@dataclass
class ExitPlan:
    """出场计划"""
    entry_price: float
    initial_stop: float              # 初始止损价
    stop_reason: str                 # 止损依据
    take_profit_levels: List[float]  # 止盈目标位列表
    position_size: int               # 买入股数
    risk_per_share: float            # 每股风险金额
    total_risk_pct: float            # 总风险比例


@dataclass
class TradeRecord:
    """交易记录"""
    entry_day_idx: int
    entry_price: float
    exit_day_idx: int
    exit_price: float
    exit_reason: ExitReason
    shares_traded: int              # 本次交易的股数
    pnl_pct: float                  # 本次盈亏比例
    pnl_amount: float               # 本次盈亏金额
    hold_days: int


@dataclass
class TradeResult:
    """完整交易结果"""
    entry_day_idx: int
    entry_price: float
    initial_stop: float
    exit_plan: ExitPlan
    records: List[TradeRecord] = field(default_factory=list)
    total_pnl_pct: float = 0.0
    total_pnl_amount: float = 0.0
    total_hold_days: int = 0
    final_exit_reason: Optional[ExitReason] = None
    weighted_pnl_pct: float = 0.0  # 加权盈亏 (考虑分批出场)


# ---------------------------------------------------------------------------
# 止损设置
# ---------------------------------------------------------------------------

def set_initial_stop(
    entry_price: float,
    support_used: Optional[KeyLevel],
    atr: float,
    config: Optional[ExitConfig] = None,
) -> Tuple[float, str]:
    """
    设置初始止损价

    逻辑: 止损设在入场依据的支撑位下方 N 倍 ATR
    融合支撑位: 根据置信度调整 ATR 倍数 (高置信度用更窄缓冲)
    硬性上限: 不超过入场价的 max_stop_loss_pct

    Returns:
        (止损价, 止损依据描述)
    """
    if config is None:
        config = ExitConfig()

    if support_used is not None and support_used.price < entry_price:
        # 融合支撑位置信度调整 ATR 倍数
        fused_sources = {'ma_cluster', 'ma60_washed', 'pit_bottom'}
        if support_used.level_type in fused_sources:
            confidence = support_used.strength
            if confidence >= 0.85:
                atr_mult = 0.5
            elif confidence >= 0.7:
                atr_mult = 0.75
            else:
                atr_mult = config.stop_loss_atr_multiplier
            stop_buffer = atr_mult * atr
            stop_reason = (
                f"融合支撑 {support_used.price:.2f} ({support_used.level_type}, "
                f"置信度={confidence:.2f}) 下方 {atr_mult}xATR={stop_buffer:.2f}"
            )
        else:
            stop_buffer = config.stop_loss_atr_multiplier * atr
            stop_reason = f"支撑位 {support_used.price:.2f} 下方 {stop_buffer:.2f} ({support_used.level_type})"

        stop_price = support_used.price - stop_buffer
    else:
        stop_price = entry_price * (1 - config.max_stop_loss_pct)
        stop_reason = f"无有效支撑依据, 使用最大止损 {config.max_stop_loss_pct:.0%}"

    # 硬性保护: 止损不能低于 max_stop_loss_pct
    hard_stop = entry_price * (1 - config.max_stop_loss_pct)
    if stop_price < hard_stop:
        stop_price = hard_stop
        stop_reason += f" (被硬性止损 {config.max_stop_loss_pct:.0%} 截断)"

    return stop_price, stop_reason


def set_initial_stop_by_pattern(
    entry_price: float,
    support_used: Optional[KeyLevel],
    atr: float,
    v2_features: Optional[dict] = None,
    config: Optional[ExitConfig] = None,
) -> Tuple[float, str]:
    """
    根据入场形态类型差异化止损:
    - 洗盘形态 (washout): 支撑被验证过，0.75×ATR 紧止损
    - 坑底反弹 (pit_rebound): 假反弹风险高，1.25×ATR 宽止损
    - 其他: 标准 1.0×ATR

    Args:
        entry_price: 入场价格
        support_used: 入场依据的支撑位
        atr: 平均真实波幅
        v2_features: V2 形态特征字典
        config: 出场配置

    Returns:
        (止损价, 止损依据描述)
    """
    if config is None:
        config = ExitConfig()

    if support_used is None or support_used.price >= entry_price:
        stop_price = entry_price * (1 - config.max_stop_loss_pct)
        return stop_price, f"无有效支撑, 使用最大止损 {config.max_stop_loss_pct:.0%}"

    is_washout = False
    is_pit_rebound = False
    if v2_features:
        is_washout = v2_features.get('washout_ma60_flag', 0) == 1
        is_pit_rebound = v2_features.get('price_rebound_from_pit', 0) > 0.03

    if is_washout:
        atr_mult = 0.75
        pattern_name = 'washout'
    elif is_pit_rebound:
        atr_mult = 1.25
        pattern_name = 'pit_rebound'
    else:
        atr_mult = 1.0
        pattern_name = 'standard'

    buffer = atr_mult * atr
    structural_stop = support_used.price - buffer

    hard_stop = entry_price * (1 - config.max_stop_loss_pct)
    final_stop = max(structural_stop, hard_stop)
    final_stop = min(final_stop, entry_price * 0.999)

    stop_reason = (
        f"形态止损: {pattern_name}, "
        f"支撑 {support_used.price:.2f} 下方 {atr_mult}xATR={buffer:.2f}"
    )
    if final_stop == hard_stop:
        stop_reason += f" (被硬性止损 {config.max_stop_loss_pct:.0%} 截断)"

    return final_stop, stop_reason

def set_take_profit_levels(
    entry_price: float,
    resistances: List[KeyLevel],
    config: Optional[ExitConfig] = None,
) -> List[float]:
    """
    设置止盈目标位

    第一目标: 最近阻力位 (或默认 10%)
    第二目标: 次近阻力位 (或默认 20%)
    """
    if config is None:
        config = ExitConfig()

    tp_levels = []

    for i, resistance in enumerate(resistances[:2]):
        if resistance.price > entry_price:
            tp_levels.append(resistance.price)

    # 补全不足的目标
    if len(tp_levels) == 0:
        tp_levels.append(entry_price * (1 + config.default_tp1_pct))
        tp_levels.append(entry_price * (1 + config.default_tp2_pct))
    elif len(tp_levels) == 1:
        second_target = max(
            tp_levels[0] * 1.1,
            entry_price * (1 + config.default_tp2_pct)
        )
        tp_levels.append(second_target)

    return tp_levels


# ---------------------------------------------------------------------------
# 仓位计算
# ---------------------------------------------------------------------------

def calculate_position_size(
    capital: float,
    entry_price: float,
    stop_price: float,
    config: Optional[ExitConfig] = None,
) -> int:
    """
    基于风险的仓位计算

    每笔交易允许亏损: capital * max_risk_per_trade
    仓位 = 允许亏损金额 / 每股风险金额
    取整到 min_lot_size (A股100股)

    Returns:
        买入股数
    """
    if config is None:
        config = ExitConfig()

    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share <= 0:
        return 0

    max_loss_amount = capital * config.max_risk_per_trade
    position_size = max_loss_amount / risk_per_share

    # A股100股整数
    position_size = int(position_size / config.min_lot_size) * config.min_lot_size

    # 不能超过可用资金
    max_affordable = capital / entry_price
    position_size = min(position_size, int(max_affordable / config.min_lot_size) * config.min_lot_size)

    return max(position_size, config.min_lot_size)


# ---------------------------------------------------------------------------
# 动态移动止损
# ---------------------------------------------------------------------------

def update_trailing_stop(
    current_stop: float,
    new_swing_lows: List[SwingPoint],
    atr: float,
    entry_price: float,
    current_high: float,
    config: Optional[ExitConfig] = None,
) -> float:
    """
    更新移动止损 (只上移不下移)

    规则:
    1. 如果有新的更高低点 -> 止损上移到该低点下方 0.5*ATR
    2. 无新低点时 -> 使用追踪止损 (最高点 - trailing_atr_multiplier * ATR)
    """
    if config is None:
        config = ExitConfig()

    new_stop = current_stop

    # 方法 1: 基于新的 swing low
    for sl in new_swing_lows:
        if sl.price > current_stop:
            candidate = sl.price - 0.5 * atr
            if candidate > new_stop:
                new_stop = candidate

    # 方法 2: 追踪止损 (基于当前最高价)
    trailing_stop = current_high - config.trailing_atr_multiplier * atr
    if trailing_stop > new_stop and trailing_stop > entry_price:
        new_stop = trailing_stop

    return new_stop


# ---------------------------------------------------------------------------
# 出场计划制定
# ---------------------------------------------------------------------------

def create_exit_plan(
    entry_price: float,
    structure: MarketStructure,
    support_used: Optional[KeyLevel],
    capital: float = 1000000.0,
    config: Optional[ExitConfig] = None,
) -> ExitPlan:
    """
    制定完整的出场计划
    """
    if config is None:
        config = ExitConfig()

    # 止损
    stop_price, stop_reason = set_initial_stop(
        entry_price, support_used, structure.atr, config
    )

    # 止盈
    tp_levels = set_take_profit_levels(
        entry_price, structure.resistances, config
    )

    # 仓位
    position_size = calculate_position_size(
        capital, entry_price, stop_price, config
    )

    risk_per_share = abs(entry_price - stop_price)
    total_risk = (risk_per_share * position_size) / capital if capital > 0 else 0

    return ExitPlan(
        entry_price=entry_price,
        initial_stop=stop_price,
        stop_reason=stop_reason,
        take_profit_levels=tp_levels,
        position_size=position_size,
        risk_per_share=risk_per_share,
        total_risk_pct=total_risk,
    )


# ---------------------------------------------------------------------------
# 持仓管理状态机 (核心)
# ---------------------------------------------------------------------------

def run_position_manager(
    df: pd.DataFrame,
    entry_day_idx: int,
    exit_plan: ExitPlan,
    structure: MarketStructure,
    config: Optional[ExitConfig] = None,
) -> TradeResult:
    """
    运行持仓管理状态机

    从入场日开始，逐日检查:
    1. 止损 (最低价触及止损)
    2. 第一目标止盈 (最高价触及 TP1, 减仓50%, 止损上移到成本价)
    3. 第二目标止盈 (最高价触及 TP2, 清仓)
    4. 动态移动止损 (上升趋势中上移止损)
    5. 到期离场 (超过 max_hold_days)

    Returns:
        TradeResult
    """
    if config is None:
        config = ExitConfig()

    entry_price = exit_plan.entry_price
    current_stop = exit_plan.initial_stop
    tp_levels = list(exit_plan.take_profit_levels)
    total_shares = exit_plan.position_size
    remaining_shares = total_shares

    result = TradeResult(
        entry_day_idx=entry_day_idx,
        entry_price=entry_price,
        initial_stop=current_stop,
        exit_plan=exit_plan,
    )

    position_state = PositionState.FULL
    current_high_since_entry = entry_price
    tp1_triggered = False

    # 逐日模拟
    max_day = min(entry_day_idx + config.max_hold_days, len(df) - 1)

    for day_idx in range(entry_day_idx + 1, max_day + 1):
        day_high = float(df.iloc[day_idx]['high'])
        day_low = float(df.iloc[day_idx]['low'])
        day_close = float(df.iloc[day_idx]['close'])

        current_high_since_entry = max(current_high_since_entry, day_high)

        # --- 止损检查 ---
        if day_low <= current_stop:
            exit_price = current_stop
            pnl_pct = (exit_price - entry_price) / entry_price
            pnl_amount = pnl_pct * exit_price * remaining_shares

            reason = ExitReason.BREAKEVEN_STOP if abs(exit_price - entry_price) < 0.001 else ExitReason.STOP_LOSS
            if tp1_triggered and exit_price >= entry_price:
                reason = ExitReason.BREAKEVEN_STOP

            record = TradeRecord(
                entry_day_idx=entry_day_idx,
                entry_price=entry_price,
                exit_day_idx=day_idx,
                exit_price=exit_price,
                exit_reason=reason,
                shares_traded=remaining_shares,
                pnl_pct=pnl_pct,
                pnl_amount=pnl_amount,
                hold_days=day_idx - entry_day_idx,
            )
            result.records.append(record)
            remaining_shares = 0
            position_state = PositionState.CLOSED
            result.final_exit_reason = reason
            break

        # --- 第一目标止盈 ---
        if not tp1_triggered and tp_levels and day_high >= tp_levels[0]:
            sell_shares = int(total_shares * config.tp1_reduce_ratio / config.min_lot_size) * config.min_lot_size
            if sell_shares <= 0:
                sell_shares = config.min_lot_size
            sell_shares = min(sell_shares, remaining_shares)

            exit_price = tp_levels[0]
            pnl_pct = (exit_price - entry_price) / entry_price
            pnl_amount = pnl_pct * exit_price * sell_shares

            record = TradeRecord(
                entry_day_idx=entry_day_idx,
                entry_price=entry_price,
                exit_day_idx=day_idx,
                exit_price=exit_price,
                exit_reason=ExitReason.TAKE_PROFIT_1,
                shares_traded=sell_shares,
                pnl_pct=pnl_pct,
                pnl_amount=pnl_amount,
                hold_days=day_idx - entry_day_idx,
            )
            result.records.append(record)
            remaining_shares -= sell_shares
            tp1_triggered = True
            position_state = PositionState.HALF

            # 止损上移到成本价 (保本)
            current_stop = max(current_stop, entry_price)

            # 移除第一目标
            if tp_levels:
                tp_levels.pop(0)

            if remaining_shares <= 0:
                position_state = PositionState.CLOSED
                result.final_exit_reason = ExitReason.TAKE_PROFIT_1
                break

        # --- 第二目标止盈 ---
        if tp_levels and day_high >= tp_levels[0]:
            exit_price = tp_levels[0]
            pnl_pct = (exit_price - entry_price) / entry_price
            pnl_amount = pnl_pct * exit_price * remaining_shares

            record = TradeRecord(
                entry_day_idx=entry_day_idx,
                entry_price=entry_price,
                exit_day_idx=day_idx,
                exit_price=exit_price,
                exit_reason=ExitReason.TAKE_PROFIT_2,
                shares_traded=remaining_shares,
                pnl_pct=pnl_pct,
                pnl_amount=pnl_amount,
                hold_days=day_idx - entry_day_idx,
            )
            result.records.append(record)
            remaining_shares = 0
            position_state = PositionState.CLOSED
            result.final_exit_reason = ExitReason.TAKE_PROFIT_2
            break

        # --- 动态移动止损 (每日更新) ---
        # 简单实现: 如果当日形成新的高点, 尝试上移止损
        if day_high > current_high_since_entry * 0.98:
            # 寻找新的 swing low (简化: 最近 5 天最低点)
            lookback_start = max(entry_day_idx, day_idx - 5)
            recent_lows = df.iloc[lookback_start:day_idx + 1]['low']
            if len(recent_lows) >= 3:
                recent_min = float(recent_lows.min())
                candidate_stop = recent_min - 0.5 * structure.atr
                if candidate_stop > current_stop and candidate_stop > entry_price * 0.95:
                    current_stop = candidate_stop

    # --- 到期离场 ---
    if remaining_shares > 0 and position_state != PositionState.CLOSED:
        exit_day = max_day
        if exit_day < len(df):
            exit_price = float(df.iloc[exit_day]['close'])
        else:
            exit_price = entry_price

        pnl_pct = (exit_price - entry_price) / entry_price
        pnl_amount = pnl_pct * exit_price * remaining_shares

        record = TradeRecord(
            entry_day_idx=entry_day_idx,
            entry_price=entry_price,
            exit_day_idx=exit_day,
            exit_price=exit_price,
            exit_reason=ExitReason.EXPIRY,
            shares_traded=remaining_shares,
            pnl_pct=pnl_pct,
            pnl_amount=pnl_amount,
            hold_days=exit_day - entry_day_idx,
        )
        result.records.append(record)
        remaining_shares = 0
        result.final_exit_reason = ExitReason.EXPIRY

    # --- 汇总 ---
    _summarize_result(result, total_shares)

    return result


def _summarize_result(result: TradeResult, total_shares: int):
    """汇总交易结果"""
    if not result.records:
        return

    total_pnl_amount = sum(r.pnl_amount for r in result.records)
    total_entry_value = result.entry_price * total_shares

    result.total_pnl_amount = total_pnl_amount
    result.total_pnl_pct = total_pnl_amount / total_entry_value if total_entry_value > 0 else 0
    result.total_hold_days = max(r.hold_days for r in result.records)

    # 加权盈亏比例
    weighted_pnl = 0.0
    for r in result.records:
        weight = r.shares_traded / total_shares if total_shares > 0 else 0
        weighted_pnl += r.pnl_pct * weight
    result.weighted_pnl_pct = weighted_pnl


# ---------------------------------------------------------------------------
# 便捷函数
# ---------------------------------------------------------------------------

def simulate_trade(
    df: pd.DataFrame,
    entry_day_idx: int,
    entry_price: float,
    structure: MarketStructure,
    support_used: Optional[KeyLevel],
    capital: float = 1000000.0,
    config: Optional[ExitConfig] = None,
) -> TradeResult:
    """
    模拟一笔完整交易的便捷入口
    """
    if config is None:
        config = ExitConfig()

    exit_plan = create_exit_plan(
        entry_price, structure, support_used, capital, config
    )

    return run_position_manager(
        df, entry_day_idx, exit_plan, structure, config
    )


def trade_result_to_dict(result: TradeResult) -> dict:
    """将 TradeResult 转为 dict"""
    return {
        'entry_day_idx': result.entry_day_idx,
        'entry_price': result.entry_price,
        'initial_stop': result.initial_stop,
        'position_size': result.exit_plan.position_size,
        'risk_per_share': result.exit_plan.risk_per_share,
        'total_risk_pct': result.exit_plan.total_risk_pct,
        'take_profit_levels': result.exit_plan.take_profit_levels,
        'records': [
            {
                'exit_day': r.exit_day_idx,
                'exit_price': r.exit_price,
                'exit_reason': r.exit_reason.value,
                'shares': r.shares_traded,
                'pnl_pct': round(r.pnl_pct * 100, 2),
                'pnl_amount': round(r.pnl_amount, 2),
                'hold_days': r.hold_days,
            }
            for r in result.records
        ],
        'total_pnl_pct': round(result.total_pnl_pct * 100, 2),
        'weighted_pnl_pct': round(result.weighted_pnl_pct * 100, 2),
        'total_hold_days': result.total_hold_days,
        'final_exit_reason': result.final_exit_reason.value if result.final_exit_reason else None,
    }
