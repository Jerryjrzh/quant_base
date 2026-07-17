#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
结构化回测引擎 (Structure Backtester)
基于 sys_apply_tasks.md / sys_apply_steps.md 设计

将 market_structure + structure_entry + structure_exit 整合为完整回测流程:
信号触发 → 结构分析 → 结构过滤 → 等待入场 → 基于结构的出场和仓位管理

同时提供与原 backtester 的对比分析功能。
"""

import os
import sys
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import logging
import json

# 确保可以导入同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from market_structure import (
    analyze_market_structure, MarketStructure,
    structure_to_dict, detect_swing_points,
)
from structure_entry import (
    run_entry_state_machine, structure_filter,
    EntryState, EntrySignal, EntryConfig, EntryType,
    find_entry_opportunity,
)
from structure_exit import (
    create_exit_plan, run_position_manager, simulate_trade,
    ExitConfig, ExitReason, TradeResult, TradeRecord,
    trade_result_to_dict,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class StructureBacktestConfig:
    """结构化回测配置"""
    # 市场结构分析参数
    structure_lookback_days: int = 60
    swing_lookback: int = 5
    min_swing_tests: int = 1

    # 入场配置
    entry_config: EntryConfig = field(default_factory=EntryConfig)

    # 出场配置
    exit_config: ExitConfig = field(default_factory=ExitConfig)

    # 回测参数
    initial_capital: float = 1000000.0
    # 信号日列表 (外部提供) 或自动检测
    signal_dates: Optional[List[int]] = None


# ---------------------------------------------------------------------------
# 信号检测 (简单的异动检测, 可替换为现有 screener)
# ---------------------------------------------------------------------------

def detect_simple_signals(
    df: pd.DataFrame,
    volume_multiplier: float = 2.0,
    price_change_pct: float = 0.05,
    min_gap_days: int = 5,
) -> List[int]:
    """
    简单的异动信号检测 (放量 + 涨幅)
    可替换为项目现有的 screener 信号

    Args:
        df: OHLCV 数据
        volume_multiplier: 成交量相对均量的倍数
        price_change_pct: 日内涨幅阈值
        min_gap_days: 信号最小间隔天数

    Returns:
        信号日的 iloc 位置列表
    """
    if len(df) < 80:
        return []

    signals = []
    vol_ma = df['volume'].rolling(20).mean()

    last_signal_idx = -min_gap_days - 1

    for i in range(60, len(df) - 30):  # 留足前后数据
        if pd.isna(vol_ma.iloc[i]):
            continue

        vol_ratio = df['volume'].iloc[i] / vol_ma.iloc[i] if vol_ma.iloc[i] > 0 else 0
        price_change = (df['high'].iloc[i] - df['open'].iloc[i]) / df['open'].iloc[i] if df['open'].iloc[i] > 0 else 0

        if vol_ratio >= volume_multiplier and price_change >= price_change_pct:
            if i - last_signal_idx >= min_gap_days:
                signals.append(i)
                last_signal_idx = i

    return signals


# ---------------------------------------------------------------------------
# 单笔交易回测
# ---------------------------------------------------------------------------

@dataclass
class SingleTradeResult:
    """单笔交易完整结果"""
    signal_day_idx: int
    entry_result: dict
    trade_result: Optional[TradeResult]
    structure_info: dict
    skipped: bool = False
    skip_reason: str = ""


def backtest_single_signal(
    df: pd.DataFrame,
    signal_day_idx: int,
    config: StructureBacktestConfig,
    capital: float = 1000000.0,
) -> SingleTradeResult:
    """
    对单个信号进行完整的结构化回测

    流程:
    1. 分析信号日的市场结构
    2. 结构过滤
    3. 等待入场机会
    4. 制定出场计划
    5. 模拟持仓管理
    """
    # 确保信号日有足够的前置数据
    if signal_day_idx < config.structure_lookback_days:
        return SingleTradeResult(
            signal_day_idx=signal_day_idx,
            entry_result={},
            trade_result=None,
            structure_info={},
            skipped=True,
            skip_reason=f"信号日 ({signal_day_idx}) 前置数据不足",
        )

    # --- Step 1: 市场结构分析 ---
    pre_data = df.iloc[:signal_day_idx + 1]
    structure = analyze_market_structure(
        pre_data,
        lookback_days=config.structure_lookback_days,
        swing_lookback=config.swing_lookback,
        min_tests=config.min_swing_tests,
    )
    structure_info = structure_to_dict(structure)

    # --- Step 2 + 3: 入场状态机 (包含结构过滤) ---
    entry_result = find_entry_opportunity(
        df, structure, signal_day_idx, config.entry_config
    )

    state = entry_result.get('state')
    signal = entry_result.get('signal')

    if state == EntryState.FILTERED.value:
        return SingleTradeResult(
            signal_day_idx=signal_day_idx,
            entry_result=entry_result,
            trade_result=None,
            structure_info=structure_info,
            skipped=True,
            skip_reason=f"结构过滤: {entry_result.get('filter_result', {}).reason if entry_result.get('filter_result') else 'N/A'}",
        )

    if state == EntryState.EXPIRED.value:
        return SingleTradeResult(
            signal_day_idx=signal_day_idx,
            entry_result=entry_result,
            trade_result=None,
            structure_info=structure_info,
            skipped=True,
            skip_reason="等待期内未出现入场机会",
        )

    if signal is None:
        return SingleTradeResult(
            signal_day_idx=signal_day_idx,
            entry_result=entry_result,
            trade_result=None,
            structure_info=structure_info,
            skipped=True,
            skip_reason="入场信号异常",
        )

    # --- Step 4: 制定出场计划 ---
    # 入场后重新分析结构 (使用入场日之前的数据)
    entry_structure_data = df.iloc[:signal.entry_day_idx + 1]
    if len(entry_structure_data) >= config.structure_lookback_days:
        entry_structure = analyze_market_structure(
            entry_structure_data,
            lookback_days=config.structure_lookback_days,
            swing_lookback=config.swing_lookback,
            min_tests=config.min_swing_tests,
        )
    else:
        entry_structure = structure

    trade_result = simulate_trade(
        df=df,
        entry_day_idx=signal.entry_day_idx,
        entry_price=signal.entry_price,
        structure=entry_structure,
        support_used=signal.support_used,
        capital=capital,
        config=config.exit_config,
    )

    return SingleTradeResult(
        signal_day_idx=signal_day_idx,
        entry_result=entry_result,
        trade_result=trade_result,
        structure_info=structure_info,
    )


# ---------------------------------------------------------------------------
# 批量回测
# ---------------------------------------------------------------------------

@dataclass
class BacktestSummary:
    """回测汇总统计"""
    total_signals: int
    filtered_signals: int
    expired_signals: int
    traded_signals: int
    win_count: int
    loss_count: int
    win_rate: float
    avg_pnl_pct: float
    avg_weighted_pnl_pct: float
    max_profit_pct: float
    max_loss_pct: float
    avg_hold_days: float
    total_pnl_amount: float
    profit_factor: float
    avg_risk_reward: float
    entry_type_distribution: Dict[str, int]
    exit_reason_distribution: Dict[str, int]
    # 对比基准
    baseline_avg_pnl: Optional[float] = None
    improvement_pct: Optional[float] = None


def run_structure_backtest(
    df: pd.DataFrame,
    config: Optional[StructureBacktestConfig] = None,
    signal_indices: Optional[List[int]] = None,
) -> Tuple[BacktestSummary, List[SingleTradeResult]]:
    """
    运行完整的结构化回测

    Args:
        df: 完整 OHLCV 数据
        config: 回测配置
        signal_indices: 信号日 iloc 列表 (不传则自动检测)

    Returns:
        (BacktestSummary, 所有交易结果列表)
    """
    if config is None:
        config = StructureBacktestConfig()

    # 获取信号列表
    if signal_indices is not None:
        signals = signal_indices
    elif config.signal_dates is not None:
        signals = config.signal_dates
    else:
        signals = detect_simple_signals(df)

    if not signals:
        return _empty_summary(), []

    all_results: List[SingleTradeResult] = []
    capital = config.initial_capital

    for sig_idx in signals:
        result = backtest_single_signal(df, sig_idx, config, capital)
        all_results.append(result)

    # --- 汇总统计 ---
    summary = _compute_summary(all_results, config)

    return summary, all_results


def _compute_summary(
    results: List[SingleTradeResult],
    config: StructureBacktestConfig,
) -> BacktestSummary:
    """计算回测汇总"""
    total = len(results)
    filtered = sum(1 for r in results if r.skipped and '过滤' in r.skip_reason)
    expired = sum(1 for r in results if r.skipped and '未出现' in r.skip_reason)
    traded = [r for r in results if r.trade_result is not None]
    traded_count = len(traded)

    if traded_count == 0:
        return BacktestSummary(
            total_signals=total,
            filtered_signals=filtered,
            expired_signals=expired,
            traded_signals=0,
            win_count=0, loss_count=0,
            win_rate=0.0,
            avg_pnl_pct=0.0, avg_weighted_pnl_pct=0.0,
            max_profit_pct=0.0, max_loss_pct=0.0,
            avg_hold_days=0.0,
            total_pnl_amount=0.0,
            profit_factor=0.0, avg_risk_reward=0.0,
            entry_type_distribution={},
            exit_reason_distribution={},
        )

    pnl_pcts = [r.trade_result.weighted_pnl_pct for r in traded]
    pnl_amounts = [r.trade_result.total_pnl_amount for r in traded]
    hold_days = [r.trade_result.total_hold_days for r in traded]

    wins = [p for p in pnl_pcts if p > 0]
    losses = [p for p in pnl_pcts if p <= 0]

    gross_profit = sum(p for p in pnl_amounts if p > 0)
    gross_loss = abs(sum(p for p in pnl_amounts if p < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0.001
    avg_rr = avg_win / avg_loss if avg_loss > 0 else 0

    # 入场类型分布
    entry_dist = {}
    for r in traded:
        sig = r.entry_result.get('signal')
        if sig is not None:
            etype = sig.entry_type.value
            entry_dist[etype] = entry_dist.get(etype, 0) + 1

    # 出场原因分布
    exit_dist = {}
    for r in traded:
        if r.trade_result and r.trade_result.final_exit_reason:
            reason = r.trade_result.final_exit_reason.value
            exit_dist[reason] = exit_dist.get(reason, 0) + 1

    return BacktestSummary(
        total_signals=total,
        filtered_signals=filtered,
        expired_signals=expired,
        traded_signals=traded_count,
        win_count=len(wins),
        loss_count=len(losses),
        win_rate=len(wins) / traded_count if traded_count > 0 else 0,
        avg_pnl_pct=float(np.mean(pnl_pcts)),
        avg_weighted_pnl_pct=float(np.mean(pnl_pcts)),
        max_profit_pct=float(max(pnl_pcts)) if pnl_pcts else 0,
        max_loss_pct=float(min(pnl_pcts)) if pnl_pcts else 0,
        avg_hold_days=float(np.mean(hold_days)),
        total_pnl_amount=float(sum(pnl_amounts)),
        profit_factor=float(profit_factor) if profit_factor != float('inf') else 99.99,
        avg_risk_reward=float(avg_rr),
        entry_type_distribution=entry_dist,
        exit_reason_distribution=exit_dist,
    )


def _empty_summary() -> Tuple[BacktestSummary, List]:
    return BacktestSummary(
        total_signals=0, filtered_signals=0, expired_signals=0,
        traded_signals=0, win_count=0, loss_count=0,
        win_rate=0, avg_pnl_pct=0, avg_weighted_pnl_pct=0,
        max_profit_pct=0, max_loss_pct=0, avg_hold_days=0,
        total_pnl_amount=0, profit_factor=0, avg_risk_reward=0,
        entry_type_distribution={}, exit_reason_distribution={},
    ), []


# ---------------------------------------------------------------------------
# 与原 backtester 的对比分析
# ---------------------------------------------------------------------------

def compare_with_baseline(
    df: pd.DataFrame,
    signal_indices: List[int],
    structure_config: Optional[StructureBacktestConfig] = None,
) -> Dict:
    """
    对比结构化回测 vs 原始 T+1 开盘买入 (基准)

    Returns:
        对比结果字典
    """
    if structure_config is None:
        structure_config = StructureBacktestConfig()

    # --- 结构化回测 ---
    struct_summary, struct_results = run_structure_backtest(
        df, structure_config, signal_indices
    )

    # --- 基准回测: T+1 开盘买入, 固定止损-8%, 止盈+30%, 持有22天 ---
    baseline_results = _run_baseline_backtest(df, signal_indices)
    baseline_pnls = [r['pnl_pct'] for r in baseline_results if r.get('pnl_pct') is not None]
    baseline_win_rate = len([p for p in baseline_pnls if p > 0]) / len(baseline_pnls) if baseline_pnls else 0
    baseline_avg_pnl = float(np.mean(baseline_pnls)) if baseline_pnls else 0

    improvement = struct_summary.avg_pnl_pct - baseline_avg_pnl

    return {
        'structure_backtest': {
            'total_signals': struct_summary.total_signals,
            'traded_signals': struct_summary.traded_signals,
            'filtered_signals': struct_summary.filtered_signals,
            'expired_signals': struct_summary.expired_signals,
            'win_rate': round(struct_summary.win_rate * 100, 1),
            'avg_pnl_pct': round(struct_summary.avg_pnl_pct * 100, 2),
            'profit_factor': round(struct_summary.profit_factor, 2),
            'avg_hold_days': round(struct_summary.avg_hold_days, 1),
            'entry_distribution': struct_summary.entry_type_distribution,
            'exit_distribution': struct_summary.exit_reason_distribution,
        },
        'baseline_backtest': {
            'total_signals': len(baseline_results),
            'win_rate': round(baseline_win_rate * 100, 1),
            'avg_pnl_pct': round(baseline_avg_pnl * 100, 2),
        },
        'improvement': {
            'pnl_improvement_pct': round(improvement * 100, 2),
            'win_rate_improvement': round(
                (struct_summary.win_rate - baseline_win_rate) * 100, 1
            ),
            'filter_effective': struct_summary.filtered_signals > 0,
            'filter_count': struct_summary.filtered_signals,
        },
    }


def _run_baseline_backtest(
    df: pd.DataFrame,
    signal_indices: List[int],
    stop_loss_pct: float = -0.08,
    take_profit_pct: float = 0.30,
    max_hold_days: int = 22,
) -> List[dict]:
    """
    基准回测: T+1 开盘买入, 固定止损/止盈, 最大持有 max_hold_days 天
    """
    results = []

    for sig_idx in signal_indices:
        entry_day = sig_idx + 1
        if entry_day >= len(df):
            continue

        entry_price = float(df.iloc[entry_day]['open'])
        if entry_price <= 0:
            continue

        stop_price = entry_price * (1 + stop_loss_pct)
        target_price = entry_price * (1 + take_profit_pct)

        pnl = None
        exit_reason = 'unknown'

        for d in range(entry_day + 1, min(entry_day + max_hold_days + 1, len(df))):
            day_low = float(df.iloc[d]['low'])
            day_high = float(df.iloc[d]['high'])

            if day_low <= stop_price:
                pnl = stop_loss_pct
                exit_reason = 'stop_loss'
                break
            if day_high >= target_price:
                pnl = take_profit_pct
                exit_reason = 'take_profit'
                break

        if pnl is None:
            # 到期: 用最后一天收盘价
            last_day = min(entry_day + max_hold_days, len(df) - 1)
            exit_price = float(df.iloc[last_day]['close'])
            pnl = (exit_price - entry_price) / entry_price
            exit_reason = 'expiry'

        results.append({
            'signal_idx': sig_idx,
            'entry_price': entry_price,
            'pnl_pct': pnl,
            'exit_reason': exit_reason,
        })

    return results


# ---------------------------------------------------------------------------
# 结果输出
# ---------------------------------------------------------------------------

def print_summary(summary: BacktestSummary, title: str = "结构化回测结果"):
    """打印回测汇总"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    print(f"  总信号数:       {summary.total_signals}")
    print(f"  被过滤信号:     {summary.filtered_signals}")
    print(f"  等待过期信号:   {summary.expired_signals}")
    print(f"  实际交易数:     {summary.traded_signals}")
    print(f"  ---")
    print(f"  胜率:           {summary.win_rate:.1%}")
    print(f"  平均盈亏:       {summary.avg_pnl_pct:.2%}")
    print(f"  加权平均盈亏:   {summary.avg_weighted_pnl_pct:.2%}")
    print(f"  最大单笔盈利:   {summary.max_profit_pct:.2%}")
    print(f"  最大单笔亏损:   {summary.max_loss_pct:.2%}")
    print(f"  平均持仓天数:   {summary.avg_hold_days:.1f}")
    print(f"  总盈亏金额:     {summary.total_pnl_amount:,.2f}")
    print(f"  盈利因子:       {summary.profit_factor:.2f}")
    print(f"  平均盈亏比:     {summary.avg_risk_reward:.2f}")
    print(f"  ---")
    print(f"  入场类型分布:   {summary.entry_type_distribution}")
    print(f"  出场原因分布:   {summary.exit_reason_distribution}")
    print(f"{'='*60}\n")


def export_results(
    summary: BacktestSummary,
    results: List[SingleTradeResult],
    output_path: str,
):
    """导出回测结果到 JSON"""
    data = {
        'summary': {
            'total_signals': summary.total_signals,
            'filtered_signals': summary.filtered_signals,
            'expired_signals': summary.expired_signals,
            'traded_signals': summary.traded_signals,
            'win_rate': round(summary.win_rate * 100, 1),
            'avg_pnl_pct': round(summary.avg_pnl_pct * 100, 2),
            'max_profit_pct': round(summary.max_profit_pct * 100, 2),
            'max_loss_pct': round(summary.max_loss_pct * 100, 2),
            'avg_hold_days': round(summary.avg_hold_days, 1),
            'total_pnl_amount': round(summary.total_pnl_amount, 2),
            'profit_factor': round(summary.profit_factor, 2),
            'avg_risk_reward': round(summary.avg_risk_reward, 2),
            'entry_distribution': summary.entry_type_distribution,
            'exit_distribution': summary.exit_reason_distribution,
        },
        'trades': [],
        'skipped': [],
    }

    for r in results:
        if r.trade_result is not None:
            trade_data = trade_result_to_dict(r.trade_result)
            trade_data['signal_day_idx'] = r.signal_day_idx
            trade_data['entry_type'] = r.entry_result.get('signal', {}).entry_type.value if r.entry_result.get('signal') else 'unknown'
            trade_data['structure_info'] = {
                'trend': r.structure_info.get('trend_direction'),
                'strength': r.structure_info.get('structure_strength'),
                'supports_count': len(r.structure_info.get('supports', [])),
                'resistances_count': len(r.structure_info.get('resistances', [])),
            }
            data['trades'].append(trade_data)
        elif r.skipped:
            data['skipped'].append({
                'signal_day_idx': r.signal_day_idx,
                'reason': r.skip_reason,
            })

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"结果已导出到: {output_path}")
