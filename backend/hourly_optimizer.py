#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
60分钟K线入场/出场优化模块 (v2)

定位: 在日线确认的入场日/持仓期间，用小时线执行价格优化和风险预警。
      不是过滤器，而是执行层增强。

三类规则:
  1. 优化入场价格: 入场日触及支撑后出现反转形态，以更低的反转收盘价入场
  2. 开盘高开保护: 入场日开盘 > 支撑*1.03，放弃当日入场
  3. 盘中破位预警: 60m 收盘跌破支撑且未收回，提前预警
  4. 持仓止损增强: 连续2根60m收盘跌破动态支撑且不放量
  5. 持仓止盈增强: 盈利>5%且出现高位衰竭形态
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, Any


def optimize_entry_with_hourly(df_60m_entry_day: pd.DataFrame,
                               support_price: float,
                               original_entry_price: float,
                               config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    在日线确认的入场日当天，寻找比原系统入场价更优的入场点。

    Args:
        df_60m_entry_day: 入场日当天的60分钟K线 (至少4根)
        support_price: 日线支撑位
        original_entry_price: 原系统的入场价 (buy_price)
        config: 参数覆盖

    Returns:
        {
            'optimized_price': float,
            'is_optimized': bool,
            'reason': str,
            'skip_entry': bool,
            'early_warning': bool,
            'warning_reason': str,
            'touch_count': int,
            'pattern_type': str
        }
    """
    cfg = config or {}
    gap_up_threshold = cfg.get('gap_up_threshold', 0.015)  # 1.5% vs 原入场价
    touch_tolerance = cfg.get('touch_tolerance', 0.015)
    pinbar_ratio = cfg.get('pinbar_ratio', 2.0)
    breach_threshold = cfg.get('breach_threshold', 0.005)

    result = {
        'optimized_price': original_entry_price,
        'is_optimized': False,
        'reason': '未找到优化机会',
        'skip_entry': False,
        'early_warning': False,
        'warning_reason': '',
        'touch_count': 0,
        'pattern_type': ''
    }

    if df_60m_entry_day is None or df_60m_entry_day.empty:
        result['reason'] = '60分钟数据为空'
        return result

    day_bars = df_60m_entry_day.copy()
    if len(day_bars) < 4:
        result['reason'] = f'60分钟K线不足 ({len(day_bars)}<4)'
        return result

    # ---- 规则2: 开盘高开保护 (v2修正: 对比原入场价, 而非支撑位) ----
    open_price = day_bars['open'].iloc[0]
    if original_entry_price > 0 and open_price > original_entry_price * (1 + gap_up_threshold):
        result['skip_entry'] = True
        result['reason'] = (f'开盘{open_price:.2f}高于原入场价{original_entry_price:.2f} '
                            f'{open_price/original_entry_price-1:.1%} '
                            f'(>{gap_up_threshold:.1%})，放弃当日入场')
        return result

    # ---- 规则1: 寻找支撑触及 + 反转形态 ----
    touch_mask = ((day_bars['low'] <= support_price * (1 + touch_tolerance)) &
                  (day_bars['low'] >= support_price * (1 - touch_tolerance)))
    touch_count = int(touch_mask.sum())
    result['touch_count'] = touch_count

    if touch_count == 0:
        result['reason'] = (f'当日未触及支撑区 (support={support_price:.2f}, '
                            f'tol={touch_tolerance:.1%}, day_low={day_bars["low"].min():.2f})')
        # 未触及支撑但仍检查破位预警
        _check_breach(day_bars, support_price, breach_threshold, result)
        return result

    first_touch_idx = touch_mask.idxmax()
    touch_pos = day_bars.index.get_loc(first_touch_idx)
    subsequent_bars = day_bars.iloc[touch_pos:].copy()

    if len(subsequent_bars) < 2:
        result['reason'] = '触及支撑后K线不足'
        _check_breach(day_bars, support_price, breach_threshold, result)
        return result

    # 计算形态特征
    subsequent_bars['body'] = abs(subsequent_bars['close'] - subsequent_bars['open'])
    subsequent_bars['lower_shadow'] = (subsequent_bars[['open', 'close']].min(axis=1)
                                       - subsequent_bars['low'])
    subsequent_bars['upper_shadow'] = (subsequent_bars['high']
                                       - subsequent_bars[['open', 'close']].max(axis=1))
    subsequent_bars['vol_ma5'] = (subsequent_bars['volume'].rolling(5, min_periods=1)
                                  .mean().shift(1))

    # Pin Bar
    is_pinbar = ((subsequent_bars['lower_shadow'] > subsequent_bars['body'] * pinbar_ratio) &
                 (subsequent_bars['close'] >
                  subsequent_bars['low'] + subsequent_bars['lower_shadow'] * 0.5))

    # Bullish Engulfing
    prev_open = subsequent_bars['open'].shift(1)
    prev_close = subsequent_bars['close'].shift(1)
    is_engulf = ((subsequent_bars['close'] > subsequent_bars['open']) &
                 (prev_close < prev_open) &
                 (subsequent_bars['open'] < prev_close) &
                 (subsequent_bars['close'] > prev_open))

    # 缩量企稳
    subsequent_bars['vol_ma20'] = (subsequent_bars['volume'].rolling(20, min_periods=5)
                                   .mean().shift(1))
    vol_shrink = subsequent_bars['volume'] < subsequent_bars['vol_ma20'] * 0.8
    gain = (subsequent_bars['close'] - subsequent_bars['open']) / subsequent_bars['open']
    mild_bull = (subsequent_bars['close'] > subsequent_bars['open']) & gain.between(0.002, 0.008)
    is_shrink_stable = vol_shrink & mild_bull

    # 首个反转信号 (跳过第一根，因为需要前一根对比)
    pattern_mask = is_pinbar | is_engulf | is_shrink_stable
    if pattern_mask.iloc[1:].any():
        first_pattern_idx = pattern_mask.iloc[1:].idxmax()
        optimized_price = float(subsequent_bars.loc[first_pattern_idx, 'close'])

        pattern_type = ('pinbar' if is_pinbar.loc[first_pattern_idx]
                        else ('engulf' if is_engulf.loc[first_pattern_idx]
                              else 'shrink_stable'))
        result['pattern_type'] = pattern_type

        # 优化价需优于原入场价且仍在支撑区附近
        if (optimized_price < original_entry_price and
                optimized_price >= support_price * 0.98):
            improvement = (original_entry_price - optimized_price) / original_entry_price
            result['optimized_price'] = optimized_price
            result['is_optimized'] = True
            result['reason'] = (f'{pattern_type}反转，入场价 '
                                f'{optimized_price:.2f} < {original_entry_price:.2f} '
                                f'(改善{improvement:.2%})')
        else:
            result['reason'] = (f'反转{pattern_type}出现但价格未优于原价 '
                                f'(opt={optimized_price:.2f} vs orig={original_entry_price:.2f})')
    else:
        result['reason'] = '触及支撑后未出现有效反转形态'

    # ---- 规则3: 盘中破位预警 ----
    _check_breach(day_bars, support_price, breach_threshold, result)

    return result


def _check_breach(day_bars: pd.DataFrame, support_price: float,
                  breach_threshold: float, result: Dict[str, Any]) -> None:
    """检查60m收盘跌破支撑且未收回的预警"""
    close_below = day_bars['close'] < support_price * (1 - breach_threshold)
    if not close_below.any():
        return
    first_breach_pos = np.where(close_below.values)[0][0]
    # 随后2根K线 (约1小时) 是否收回支撑
    recovery = day_bars.iloc[first_breach_pos + 1: first_breach_pos + 3]
    if len(recovery) > 0 and (recovery['close'] > support_price).any():
        return
    result['early_warning'] = True
    result['warning_reason'] = (f'60m收盘跌破支撑{breach_threshold:.1%}且未收回 '
                                f'(support={support_price:.2f})')


def hourly_stop_loss_enhancement(df_60m_current_day: pd.DataFrame,
                                 dynamic_support: float,
                                 config: Optional[Dict[str, Any]] = None
                                 ) -> Tuple[bool, str, Optional[float]]:
    """
    持仓期间，利用60分钟K线提前判断是否应止损。
    返回: (should_exit_early, reason, exit_price or None)
    """
    cfg = config or {}
    breach_threshold = cfg.get('breach_threshold', 0.005)
    vol_expand_cap = cfg.get('vol_expand_cap', 1.2)

    if df_60m_current_day is None or df_60m_current_day.empty:
        return False, '无数据', None
    bars = df_60m_current_day.copy()
    if len(bars) < 4:
        return False, '数据不足', None

    bars['close_below'] = bars['close'] < dynamic_support * (1 - breach_threshold)
    bars['vol_ma5'] = bars['volume'].rolling(5, min_periods=1).mean().shift(1)
    bars['vol_not_expanding'] = bars['volume'] <= bars['vol_ma5'] * vol_expand_cap

    below = bars['close_below'] & bars['vol_not_expanding']
    consecutive_two = below & below.shift(1)
    if consecutive_two.any():
        exit_idx = consecutive_two.idxmax()
        exit_price = float(bars.loc[exit_idx, 'close'])
        return True, f'60m连续2根收盘破支撑且不放量 ({exit_idx})', exit_price
    return False, '未触发', None


def hourly_exit_warning(df_60m_current_day: pd.DataFrame,
                        config: Optional[Dict[str, Any]] = None
                        ) -> Tuple[bool, str, Optional[float]]:
    """
    v2 放宽版出场预警: 不要求跌破支撑，仅检测"连续3根60m阴线且累计跌幅>2%"。
    触发后建议次日开盘卖出。
    返回: (triggered, reason, exit_price or None)
    """
    cfg = config or {}
    min_consecutive = cfg.get('consecutive_red_min', 3)
    min_cum_drop = cfg.get('cum_drop_min', 0.02)

    if df_60m_current_day is None or df_60m_current_day.empty:
        return False, '无数据', None
    bars = df_60m_current_day.copy()
    if len(bars) < min_consecutive:
        return False, '数据不足', None

    bars['is_red'] = bars['close'] < bars['open']

    # 扫描是否存在连续 min_consecutive 根阴线
    red_flags = bars['is_red'].values
    run = 0
    run_start = -1
    for i, is_red in enumerate(red_flags):
        if is_red:
            if run == 0:
                run_start = i
            run += 1
            if run >= min_consecutive:
                # 计算该段累计跌幅 (从段首 open 到当前 close)
                seg_open = float(bars.iloc[run_start]['open'])
                seg_close = float(bars.iloc[i]['close'])
                if seg_open > 0:
                    cum_drop = (seg_open - seg_close) / seg_open
                    if cum_drop >= min_cum_drop:
                        return True, (f'连续{run}根60m阴线, '
                                      f'累计跌幅{cum_drop:.2%}'), seg_close
        else:
            run = 0
            run_start = -1

    return False, '未触发', None


def hourly_take_profit_enhancement(df_60m_current_day: pd.DataFrame,
                                   profit_ratio: float,
                                   config: Optional[Dict[str, Any]] = None
                                   ) -> Tuple[bool, str]:
    """
    持仓期间，利用60分钟衰竭形态提前止盈。
    仅在盈利 > 5% 时启用。
    """
    cfg = config or {}
    min_profit = cfg.get('min_profit_for_tp', 0.05)
    stall_vol_mult = cfg.get('stall_vol_mult', 3.0)
    shooting_star_ratio = cfg.get('shooting_star_ratio', 2.0)

    if df_60m_current_day is None or df_60m_current_day.empty:
        return False, '无数据'
    if profit_ratio < min_profit:
        return False, f'盈利不足 ({profit_ratio:.2%}<{min_profit:.0%})'

    bars = df_60m_current_day.tail(8).copy()
    if len(bars) < 4:
        return False, '数据不足'

    bars['body'] = abs(bars['close'] - bars['open'])
    bars['upper_shadow'] = bars['high'] - bars[['open', 'close']].max(axis=1)
    bars['vol_ma5'] = bars['volume'].rolling(5, min_periods=1).mean().shift(1)

    # 放量滞涨
    is_stall = ((bars['close'] > bars['open']) &
                ((bars['close'] - bars['open']) / bars['open'] < 0.005) &
                (bars['volume'] > bars['vol_ma5'] * stall_vol_mult))

    # 长上影线 + 缩量
    is_shooting = ((bars['upper_shadow'] > bars['body'] * shooting_star_ratio) &
                   (bars['volume'] < bars['vol_ma5'] * 0.7))

    if is_stall.any() or is_shooting.any():
        return True, '60m出现衰竭形态 (滞涨/射击之星)'
    return False, '无衰竭信号'
