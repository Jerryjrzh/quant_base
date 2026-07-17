#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v5_gt: GT 原生状态机回测

基于已验证的 GT 双轨校准，将入场/止盈/止损从固定百分比替换为 GT 通道原生逻辑:
  - 入场: GT 下轨 (golden_trend_t0) 作为支撑位
  - 止盈: entry + channel_width * tp_mult (通道宽度倍数)
  - 止损: entry * (1 - sl_buffer) (GT 下方缓冲)

复用 v5 管线结构 (Step 0~4)，直接对比效果差异。

输入:
  - doc/0616_super_trend_V3/signal_tags_v5.csv
  - doc/0616_super_trend_V3/path_analysis_v5.csv
  - doc/0616_super_trend_V3/state_machine_backtest_v5.csv (对比基线)

输出:
  - doc/0616_super_trend_V3/state_machine_backtest_v5_gt.csv
  - doc/0616_super_trend_V3/cross_tab_params_v5_gt.csv
  - doc/0616_super_trend_V3/v5_gt_backtest_report.md
"""

import os
import sys
import time
import warnings
from multiprocessing import Pool, cpu_count
warnings.filterwarnings('ignore')

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
_BACKEND_DIR = _SCRIPT_DIR
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pandas as pd
import numpy as np

import data_loader
from golden_trend import (
    calc_golden_trend,
    calc_ema_rails,
    calc_adaptive_n,
    calc_adaptive_k,
    calc_adaptive_offset,
)
from indicators import calculate_rsi, calculate_kdj, calculate_macd
from path_analysis_v5 import (
    _aggregate_60m_to_daily,
    _load_pre_signal_daily_60m,
    _load_pre_signal_daily_fallback,
    ZONE_ORDER,
    DRAWDOWN_BINS,
    DRAWDOWN_LABELS,
)

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
DOC_DIR = os.path.join(_PROJECT_ROOT, 'doc', '0616_super_trend_V3')

TAGS_CSV = os.path.join(DOC_DIR, 'signal_tags_v5.csv')
PATH_V5_CSV = os.path.join(DOC_DIR, 'path_analysis_v5.csv')
BACKTEST_V5_CSV = os.path.join(DOC_DIR, 'state_machine_backtest_v5.csv')

BACKTEST_GT_CSV = os.path.join(DOC_DIR, 'state_machine_backtest_v5_gt.csv')
CROSS_TAB_GT_CSV = os.path.join(DOC_DIR, 'cross_tab_params_v5_gt.csv')
REPORT_GT_MD = os.path.join(DOC_DIR, 'v5_gt_backtest_report.md')

FUTURE_DAYS = 22
FUTURE_CALENDAR_DAYS = 45
LOOKBACK_CALENDAR_DAYS = 300
MIN_PRE_BARS = 120
OBSERVE_WINDOW = 10

STATE_OBSERVING = 1
STATE_HOLDING = 2

TP_MULT_MAP = {
    'abyss_bottom': 3.0,
    'bottom_start': 2.5,
    'main_wave': 2.0,
    'high_zone': 1.5,
}


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _load_forward_daily(stock: str, t0_date) -> pd.DataFrame:
    start = (t0_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    end = (t0_date + pd.Timedelta(days=FUTURE_CALENDAR_DAYS)).strftime('%Y-%m-%d')
    try:
        df_60m = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        df_60m = None
    return _aggregate_60m_to_daily(df_60m)


def _load_forward_60m(stock: str, t0_date) -> pd.DataFrame:
    """加载前视期间的原始 60m K线 (不聚合)。"""
    start = (t0_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    end = (t0_date + pd.Timedelta(days=FUTURE_CALENDAR_DAYS)).strftime('%Y-%m-%d')
    try:
        df = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        df = None
    if df is None or df.empty:
        return pd.DataFrame()
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns:
            df = df.set_index(pd.to_datetime(df['datetime']))
        elif 'date' in df.columns:
            df = df.set_index(pd.to_datetime(df['date']))
    return df[['open', 'high', 'low', 'close', 'volume']].copy()


def _load_pre_60m(stock: str, t0_date, lookback_days=60) -> pd.DataFrame:
    """加载信号前的原始 60m K线 (用于计算 60m MA)。"""
    start = (t0_date - pd.Timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    end = (t0_date - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        df = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        df = None
    if df is None or df.empty:
        return pd.DataFrame()
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns:
            df = df.set_index(pd.to_datetime(df['datetime']))
        elif 'date' in df.columns:
            df = df.set_index(pd.to_datetime(df['date']))
    return df[['open', 'high', 'low', 'close', 'volume']].copy()


def _load_60m_for_day(stock: str, day_date) -> pd.DataFrame:
    """加载指定日期当天的 60m K线数据 (不聚合为日线)。"""
    start = pd.Timestamp(day_date).strftime('%Y-%m-%d')
    end = (pd.Timestamp(day_date) + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        df = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        df = None
    if df is None or df.empty:
        return pd.DataFrame()
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns:
            df = df.set_index(pd.to_datetime(df['datetime']))
        elif 'date' in df.columns:
            df = df.set_index(pd.to_datetime(df['date']))
    return df


def _check_60m_rail_confirm(stock: str, day_date, n_param: int) -> bool:
    """检查入场日 60m EMA_L 是否拐头向上 (双轨过底确认)。

    返回 True 表示小时线下轨已确认反弹, 可以入场。
    """
    df_60m = _load_60m_for_day(stock, day_date)
    if df_60m.empty or len(df_60m) < 3:
        return True
    low = df_60m['low'].astype(float)
    ema_l = low.ewm(span=n_param, adjust=False).mean().ewm(span=n_param, adjust=False).mean()
    return float(ema_l.iloc[-1]) > float(ema_l.iloc[-2])


def _load_60m_with_warmup(stock: str, day_date, warmup_calendar_days: int = 120) -> pd.DataFrame:
    """加载指定日期及之前的 60m K线数据 (含预热期)。"""
    day_date = pd.Timestamp(day_date)
    start = (day_date - pd.Timedelta(days=warmup_calendar_days)).strftime('%Y-%m-%d')
    end = (day_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        df = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        df = None
    if df is None or df.empty:
        return pd.DataFrame()
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns:
            df = df.set_index(pd.to_datetime(df['datetime']))
        elif 'date' in df.columns:
            df = df.set_index(pd.to_datetime(df['date']))
    return df


def _find_60m_trend_buy_entry(stock: str, day_date) -> dict | None:
    """在60m级别检测趋势buy信号，返回确认bar的close价格和时间。

    加载含预热期的60m数据，计算 MTL/EMA 指标，
    在目标日当天找到第一个趋势buy金叉信号，
    以该bar收盘价作为入场价。

    Returns: dict with 'entry_price', 'entry_time' or None
    """
    df_60m = _load_60m_with_warmup(stock, day_date)
    if df_60m.empty or len(df_60m) < 40:
        return None

    c = df_60m['close'].astype(float)
    ema13 = c.ewm(span=5, adjust=False).mean()
    mtl = ema13.ewm(span=5, adjust=False).mean()
    mtl_rising = (mtl > mtl.shift(1)).astype(int)

    buy_sig = (c > mtl) & (c.shift(1) <= mtl.shift(1)) & (mtl_rising == 1)

    day_date = pd.Timestamp(day_date)
    day_mask = (df_60m.index >= day_date) & (df_60m.index < day_date + pd.Timedelta(days=1))
    day_bars = df_60m[day_mask]
    day_buy = buy_sig[day_mask]

    if day_bars.empty:
        return None

    for bar_i in range(len(day_bars)):
        if day_buy.iloc[bar_i]:
            return {
                'entry_price': float(day_bars['close'].iloc[bar_i]),
                'entry_time': day_bars.index[bar_i],
            }

    return None


def _compute_gt_on_combined(daily_pre: pd.DataFrame, daily_fwd: pd.DataFrame):
    """合并历史+前瞻数据，计算完整 GT 序列。

    Returns:
        (gt_t0, ema_h_t0, channel_width_t0, gt_params, fwd_gt, fwd_ema_h)
        如果数据不足返回 None
    """
    if daily_pre is None or daily_pre.empty or len(daily_pre) < MIN_PRE_BARS:
        return None
    if 'high' not in daily_pre.columns or 'low' not in daily_pre.columns:
        return None

    if daily_fwd is None or daily_fwd.empty:
        daily_fwd = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])

    combined = pd.concat([daily_pre, daily_fwd]).reset_index(drop=True)
    h = combined['high'].astype(float)
    l = combined['low'].astype(float)
    n_pre = len(daily_pre)

    gt_params = {
        'n': calc_adaptive_n(daily_pre),
        'k': calc_adaptive_k(daily_pre),
        'offset': calc_adaptive_offset(daily_pre),
    }

    ema_h, ema_l = calc_ema_rails(h, l, gt_params['n'], True)
    gt_series = calc_golden_trend(
        h, l, gt_params['n'], True, gt_params['k'], gt_params['offset']
    )

    gt_t0 = float(gt_series.iloc[n_pre - 1])
    ema_h_t0 = float(ema_h.iloc[n_pre - 1])
    ema_l_t0 = float(ema_l.iloc[n_pre - 1])
    channel_width_t0 = ema_h_t0 - gt_t0

    fwd_gt = gt_series.iloc[n_pre:].values if len(daily_fwd) > 0 else np.array([])
    fwd_ema_h = ema_h.iloc[n_pre:].values if len(daily_fwd) > 0 else np.array([])

    # 趋势 EMA 指标 (回测用 span=5, 比前端 span=13 更灵敏)
    c = combined['close'].astype(float)
    ema13 = c.ewm(span=5, adjust=False).mean()
    mtl = ema13.ewm(span=5, adjust=False).mean()
    mtl_rising = (mtl > mtl.shift(1)).astype(int)

    ema5 = c.ewm(span=5, adjust=False).mean()
    ema10 = c.ewm(span=10, adjust=False).mean()
    ema20 = c.ewm(span=20, adjust=False).mean()

    _aa = ema5 > ema20
    _bb = ema5 < ema20
    _cc = ema5 > ema10
    _cc1 = ema5 < ema10
    candle_color = pd.Series(0, index=combined.index)
    candle_color[_aa] = 1
    candle_color[_bb] = -1
    candle_color[_bb & _cc] = 0
    candle_color[_aa & _cc1] = 0

    trend_buy = (c > mtl) & (c.shift(1) <= mtl.shift(1)) & (mtl_rising == 1)
    sell_cond = (candle_color == -1) & (c < combined['low'].shift(1))
    trend_sell = sell_cond & ~sell_cond.shift(1).fillna(False)

    fwd_trend_buy = trend_buy.iloc[n_pre:].values if len(daily_fwd) > 0 else np.array([])
    fwd_trend_sell = trend_sell.iloc[n_pre:].values if len(daily_fwd) > 0 else np.array([])
    fwd_candle_color = candle_color.iloc[n_pre:].values if len(daily_fwd) > 0 else np.array([])

    return {
        'gt_t0': gt_t0,
        'ema_h_t0': ema_h_t0,
        'ema_l_t0': ema_l_t0,
        'channel_width_t0': channel_width_t0,
        'gt_params': gt_params,
        'fwd_gt': fwd_gt,
        'fwd_ema_h': fwd_ema_h,
        'fwd_trend_buy': fwd_trend_buy,
        'fwd_trend_sell': fwd_trend_sell,
        'fwd_candle_color': fwd_candle_color,
    }


# ---------------------------------------------------------------------------
# Step 2: GT 参数推断
# ---------------------------------------------------------------------------
def step2_gt_param_inference(merged_df: pd.DataFrame) -> pd.DataFrame:
    print("\n  [Step 2] GT 通道参数推断...")

    valid = merged_df.dropna(
        subset=['golden_trend_t0', 'last_close', 'position_ratio']
    ).copy()
    valid = valid[valid['zone_tag'] != 'unknown']
    if 'ma_zone' in valid.columns:
        valid = valid[valid['ma_zone'] != 'unknown']

    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'],
        bins=DRAWDOWN_BINS,
        labels=DRAWDOWN_LABELS,
    )

    param_rows = []
    for zone in ZONE_ORDER:
        for tier in DRAWDOWN_LABELS:
            sub = valid[(valid['zone_tag'] == zone) & (valid['dd_tier'] == tier)]
            if len(sub) == 0:
                continue

            gt_ratio = (sub['golden_trend_t0'] / sub['last_close']).median()
            avg_atr = sub['atr20_pct'].mean() if 'atr20_pct' in sub.columns else 0.05

            entry_buffer = 0.03
            sl_buffer = 0.03
            tp_mult = TP_MULT_MAP.get(zone, 2.0)

            rb_gt5 = (sub['rebound_pct'] > 0.05).mean() if 'rebound_pct' in sub.columns else 0
            deep_broken = (tier == '>20%')

            avg_support = sub['support_score'].mean() if 'support_score' in sub.columns else 0
            avg_dist90 = sub['dist_ma90'].mean() if 'dist_ma90' in sub.columns else np.nan
            ma_zone_dist = (
                sub['ma_zone'].value_counts(normalize=True).to_dict()
                if 'ma_zone' in sub.columns else {}
            )
            main_trend_pct = ma_zone_dist.get('main_trend', 0) + ma_zone_dist.get('transition', 0)

            enabled = True

            param_rows.append({
                'zone_tag': zone,
                'dd_tier': tier,
                'n': int(len(sub)),
                'avg_atr20_pct': round(avg_atr, 4),
                'entry_buffer': round(entry_buffer, 4),
                'sl_buffer': round(sl_buffer, 4),
                'tp_mult': round(tp_mult, 2),
                'gt_ratio': round(gt_ratio, 4),
                'rebound_gt5_pct': round(rb_gt5, 4),
                'avg_support_score': round(avg_support, 2),
                'avg_dist_ma90': round(avg_dist90, 4) if not pd.isna(avg_dist90) else np.nan,
                'main_trend_pct': round(main_trend_pct, 4),
                'enabled': enabled,
            })

    param_df = pd.DataFrame(param_rows)
    param_df.to_csv(CROSS_TAB_GT_CSV, index=False, encoding='utf-8-sig')
    print(f"    参数矩阵 {len(param_df)} 格")
    print(f"    已保存 {CROSS_TAB_GT_CSV}")
    return param_df


# ---------------------------------------------------------------------------
# Step 3: GT 状态机回测
# ---------------------------------------------------------------------------
def _empty_result(status):
    return {
        'status': status,
        'target_entry_price': np.nan,
        'actual_entry_price': np.nan,
        'entry_day_idx': np.nan,
        'tp_price': np.nan,
        'sl_price': np.nan,
        'exit_price': np.nan,
        'exit_day_idx': np.nan,
        'exit_reason': status,
        'pnl': np.nan,
        'gt_t0': np.nan,
        'gt_channel_width': np.nan,
        'gt_n': np.nan,
        'gt_k': np.nan,
        'gt_offset': np.nan,
        'tp_mult': np.nan,
        'sl_buffer': np.nan,
        'gt_at_entry': np.nan,
        'ema_h_at_entry': np.nan,
        'channel_at_entry': np.nan,
        'gap_at_entry': np.nan,
        'fwd_low': np.nan,
        'fwd_low_day': np.nan,
        'fwd_high': np.nan,
        'fwd_high_day': np.nan,
        'hold_low': np.nan,
        'hold_low_day': np.nan,
        'hold_high': np.nan,
        'hold_high_day': np.nan,
    }


def _get_board_params(stock_code: str) -> dict:
    """根据股票代码前缀返回板块对应的 TP/SL 参数。"""
    code = stock_code.replace('sh', '').replace('sz', '').replace('bj', '')
    if code.startswith(('688', '689')):
        return {'tp_pct': 0.15, 'sl_pct': -0.10, 'board': '30CM'}
    elif code.startswith('30'):
        return {'tp_pct': 0.12, 'sl_pct': -0.10, 'board': '20CM'}
    elif code.startswith('92'):
        return {'tp_pct': 0.18, 'sl_pct': -0.10, 'board': '30CM'}
    else:
        return {'tp_pct': 0.10, 'sl_pct': -0.10, 'board': '10CM'}


def run_single_signal_gt(daily_pre: pd.DataFrame, daily_fwd: pd.DataFrame,
                         zone_tag: str, param: dict,
                         stock_code: str = '',
                         support_score: float = np.nan,
                         ma_zone: str = '',
                         pre_60m: pd.DataFrame = None,
                         fwd_60m: pd.DataFrame = None,
                         h60_trend_pair: tuple = (7, 30),
                         indicator_mode: str = 'none',
                         indicator_exit: bool = True,
                         rsi_periods: tuple = (10, 20, 40),
                         kdj_n: int = 27,
                         exit_mode: str = 'standard') -> dict:
    """V5: 双周期 MA 入场/出场。

    入场确认: 日线 MA 确认窗口 (price near daily support MA)
    入场定价: 60m MA 判断入场价格 (hourly support MA)
    TP:   +10% (主板) / +12% (创业板) / +15% (科创板)
    SL:   -10% (主板) / -7% (创业板) / -8% (科创板)
    时间衰减: T+7 MFE<-5% | T+10 MFE<1% | T+15 强制平仓
    形态破坏: 日实体跌幅 > 6.5% → 收盘斩仓
    防御: 跳空低开(开<=入场*0.965)放弃, 收盘无承接(收<低*1.005)放弃
    """
    if daily_fwd is None or daily_fwd.empty:
        return _empty_result('no_forward_data')

    if param is None or not param.get('enabled', False):
        return _empty_result('disabled')

    if not pd.isna(support_score) and support_score < 3:
        return _empty_result('low_support_skip')

    if ma_zone in ('bottom', 'extended', 'high_risk'):
        return _empty_result(f'ma_zone_skip_{ma_zone}')

    t0_close = float(daily_pre['close'].iloc[-1])

    ma_levels = []
    for span in (30, 90, 150, 240):
        if len(daily_pre) >= span:
            ma_val = float(daily_pre['close'].rolling(span).mean().iloc[-1])
            if not np.isnan(ma_val):
                ma_levels.append((f'ma{span}', ma_val))

    supports = sorted([(name, v) for name, v in ma_levels if v < t0_close],
                      key=lambda x: x[1], reverse=True)
    resistances = sorted([(name, v) for name, v in ma_levels if v >= t0_close],
                         key=lambda x: x[1])

    nearest_support = supports[0][1] if supports else None
    next_resistance = resistances[0][1] if resistances else None

    entry_price = round(t0_close * 0.99, 4)
    if nearest_support is not None:
        ma_entry = round(nearest_support * 1.02, 4)
        entry_price = min(entry_price, ma_entry)

    board = _get_board_params(stock_code)
    tp_pct = board['tp_pct']
    sl_pct = board['sl_pct']
    tp_price = round(entry_price * (1 + tp_pct), 4)
    sl_price = round(entry_price * (1 + sl_pct), 4)

    if nearest_support is not None:
        ma_sl = round(nearest_support * 0.97, 4)
        if ma_sl > sl_price:
            sl_price = ma_sl
    if next_resistance is not None:
        ma_tp = round(next_resistance * 0.995, 4)
        if ma_tp < tp_price and ma_tp > entry_price * 1.03:
            tp_price = ma_tp

    gt_info = _compute_gt_on_combined(daily_pre, daily_fwd)
    gt_t0 = gt_info['gt_t0'] if gt_info else 0
    channel_w = gt_info['channel_width_t0'] if gt_info else 0
    gt_params = gt_info['gt_params'] if gt_info else {'n': 0, 'k': 0, 'offset': 0}

    n = min(len(daily_fwd), FUTURE_DAYS)
    fwd_lows = daily_fwd['low'].values[:n].astype(float)
    fwd_highs = daily_fwd['high'].values[:n].astype(float)
    fwd_opens = daily_fwd['open'].values[:n].astype(float)
    fwd_closes = daily_fwd['close'].values[:n].astype(float)

    fwd_low = float(np.min(fwd_lows))
    fwd_low_day = int(np.argmin(fwd_lows))
    fwd_high = float(np.max(fwd_highs))
    fwd_high_day = int(np.argmax(fwd_highs))
    fwd_kw = dict(fwd_low=fwd_low, fwd_low_day=fwd_low_day,
                  fwd_high=fwd_high, fwd_high_day=fwd_high_day)

    entry_day_idx = -1
    entry_type = 'none'
    mfe = 0.0
    mae = 0.0
    pending_days = 0
    holding_days = 0
    rsi_consec_bars = 0
    kdj_consec_bars = 0
    rsi_peak_val = 0.0
    j_peak_val = 0.0
    rsi_peak_highest = False
    j_peak_highest = False

    def _hold_stats(e_day, x_day):
        lo_slice = fwd_lows[e_day:x_day + 1]
        hi_slice = fwd_highs[e_day:x_day + 1]
        return dict(
            hold_low=float(np.min(lo_slice)),
            hold_low_day=e_day + int(np.argmin(lo_slice)),
            hold_high=float(np.max(hi_slice)),
            hold_high_day=e_day + int(np.argmax(hi_slice)),
        )

    def _exit(hs, **kw):
        merged = {**fwd_kw, **hs, **kw}
        return merged

    h60_by_day = {}
    if fwd_60m is not None and not fwd_60m.empty:
        for ts, bar in fwd_60m.iterrows():
            d = ts.normalize()
            if d not in h60_by_day:
                h60_by_day[d] = []
            h60_by_day[d].append(bar)

    fwd_h60_mas = {}
    h60_day_bars = {}
    fwd_h60_rsi6 = fwd_h60_rsi12 = fwd_h60_rsi24 = None
    fwd_h60_k = fwd_h60_d = fwd_h60_j = None
    fast_span, slow_span = h60_trend_pair
    min_pre_len = max(slow_span, 30)
    if (pre_60m is not None and not pre_60m.empty and len(pre_60m) >= min_pre_len
            and fwd_60m is not None and not fwd_60m.empty):
        combined_60m = pd.concat([pre_60m, fwd_60m])
        h60_c = combined_60m['close'].astype(float)
        n_pre_60 = len(pre_60m)
        for span in set([fast_span, slow_span]):
            ma_all = h60_c.rolling(span).mean()
            fwd_h60_mas[span] = ma_all.iloc[n_pre_60:].reset_index(drop=True)

        h60_rsi_fast = calculate_rsi(combined_60m, periods=rsi_periods[0])
        h60_rsi_mid = calculate_rsi(combined_60m, periods=rsi_periods[1])
        h60_rsi_slow = calculate_rsi(combined_60m, periods=rsi_periods[2])
        fwd_h60_rsi6 = h60_rsi_fast.iloc[n_pre_60:].reset_index(drop=True)
        fwd_h60_rsi12 = h60_rsi_mid.iloc[n_pre_60:].reset_index(drop=True)
        fwd_h60_rsi24 = h60_rsi_slow.iloc[n_pre_60:].reset_index(drop=True)

        h60_k, h60_d, h60_j = calculate_kdj(combined_60m, n=kdj_n, k_period=3, d_period=3)
        fwd_h60_k = h60_k.iloc[n_pre_60:].reset_index(drop=True)
        fwd_h60_d = h60_d.iloc[n_pre_60:].reset_index(drop=True)
        fwd_h60_j = h60_j.iloc[n_pre_60:].reset_index(drop=True)

        idx = 0
        for d in sorted(h60_by_day.keys()):
            bars = h60_by_day[d]
            h60_day_bars[d] = [(idx + j, bar) for j, bar in enumerate(bars)]
            idx += len(bars)

    fwd_dates = daily_fwd.index if isinstance(daily_fwd.index, pd.DatetimeIndex) else None

    for day_i in range(n):
        day_low = float(fwd_lows[day_i])
        day_high = float(fwd_highs[day_i])
        day_open = float(fwd_opens[day_i])
        day_close = float(fwd_closes[day_i])

        if entry_day_idx < 0:
            pending_days += 1
            if pending_days > 12:
                break

            if day_open <= entry_price * 0.965:
                continue

            entered_via_60m = False
            actual_entry_60m = None
            has_h60_data = False
            if h60_day_bars and fwd_dates is not None:
                day_date = fwd_dates[day_i].normalize()
                indexed_bars = h60_day_bars.get(day_date, [])
                has_h60_data = len(indexed_bars) > 0
                for bar_idx, bar in indexed_bars:
                    fast_ma = fwd_h60_mas.get(fast_span)
                    slow_ma = fwd_h60_mas.get(slow_span)
                    if fast_ma is None or slow_ma is None:
                        continue
                    if bar_idx >= len(fast_ma) or bar_idx >= len(slow_ma):
                        continue
                    if bar_idx < 1:
                        continue
                    fast_v = float(fast_ma.iloc[bar_idx])
                    slow_v = float(slow_ma.iloc[bar_idx])
                    if np.isnan(fast_v) or np.isnan(slow_v):
                        continue
                    prev_fast = float(fast_ma.iloc[bar_idx - 1])
                    prev_slow = float(slow_ma.iloc[bar_idx - 1])
                    if np.isnan(prev_fast) or np.isnan(prev_slow):
                        continue
                    ma7_rising = fast_v > prev_fast
                    ma7_cross_up = fast_v > slow_v and prev_fast <= prev_slow
                    b_low = float(bar['low'])

                    rsi_bull_aligned = False
                    if fwd_h60_rsi6 is not None and bar_idx < len(fwd_h60_rsi6):
                        r6 = float(fwd_h60_rsi6.iloc[bar_idx])
                        r12 = float(fwd_h60_rsi12.iloc[bar_idx])
                        r24 = float(fwd_h60_rsi24.iloc[bar_idx])
                        if not any(np.isnan(x) for x in [r6, r12, r24]):
                            rsi_bull_aligned = r6 > r12 > r24

                    kdj_jd_cross = False
                    if fwd_h60_j is not None and bar_idx >= 1 and bar_idx < len(fwd_h60_j):
                        j_now = float(fwd_h60_j.iloc[bar_idx])
                        d_now = float(fwd_h60_d.iloc[bar_idx])
                        j_prev = float(fwd_h60_j.iloc[bar_idx - 1])
                        d_prev = float(fwd_h60_d.iloc[bar_idx - 1])
                        if not any(np.isnan(x) for x in [j_now, d_now, j_prev, d_prev]):
                            kdj_jd_cross = j_now > d_now and j_prev <= d_prev

                    if indicator_mode == 'rsi':
                        confirm = rsi_bull_aligned
                    elif indicator_mode == 'kdj':
                        confirm = kdj_jd_cross
                    elif indicator_mode == 'any':
                        confirm = rsi_bull_aligned or kdj_jd_cross
                    else:
                        confirm = True

                    if ma7_rising and ma7_cross_up and b_low <= slow_v and confirm:
                        actual_entry_60m = slow_v
                        entered_via_60m = True
                        break

            if entered_via_60m:
                entry_day_idx = day_i
                entry_type = '60m'
                actual_entry = actual_entry_60m
                tp_price = round(actual_entry * (1 + tp_pct), 4)
                sl_price = round(actual_entry * (1 + sl_pct), 4)
                entry_price = actual_entry

                post_high = actual_entry
                post_low = actual_entry
                entry_bar_pos = -1
                for bi, (bidx, bar) in enumerate(indexed_bars):
                    if bidx == bar_idx:
                        entry_bar_pos = bi
                        break
                if entry_bar_pos >= 0:
                    for bidx2, bar2 in indexed_bars[entry_bar_pos + 1:]:
                        post_high = max(post_high, float(bar2['high']))
                        post_low = min(post_low, float(bar2['low']))

                if post_high >= tp_price:
                    hs = _hold_stats(entry_day_idx, day_i)
                    return _make_result('simulated', entry_price, tp_price, sl_price,
                                        tp_price, entry_day_idx, day_i, 'tp',
                                        tp_price / entry_price - 1,
                                        gt_t0, channel_w, gt_params, param,
                                        np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))
                if post_low <= sl_price:
                    hs = _hold_stats(entry_day_idx, day_i)
                    return _make_result('simulated', entry_price, tp_price, sl_price,
                                        sl_price, entry_day_idx, day_i, 'sl',
                                        sl_price / entry_price - 1,
                                        gt_t0, channel_w, gt_params, param,
                                        np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))

            elif not has_h60_data and day_low <= entry_price:
                if day_close < day_low * 1.005:
                    continue

                entry_day_idx = day_i
                entry_type = 'daily'
                actual_entry = min(entry_price, day_open * 0.995)
                tp_price = round(actual_entry * (1 + tp_pct), 4)
                sl_price = round(actual_entry * (1 + sl_pct), 4)
                entry_price = actual_entry

                if day_high >= tp_price:
                    hs = _hold_stats(entry_day_idx, day_i)
                    return _make_result('simulated', entry_price, tp_price, sl_price,
                                        tp_price, entry_day_idx, day_i, 'tp',
                                        tp_price / entry_price - 1,
                                        gt_t0, channel_w, gt_params, param,
                                        np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))
                if day_low <= sl_price or day_close <= sl_price:
                    hs = _hold_stats(entry_day_idx, day_i)
                    return _make_result('simulated', entry_price, tp_price, sl_price,
                                        sl_price, entry_day_idx, day_i, 'sl',
                                        sl_price / entry_price - 1,
                                        gt_t0, channel_w, gt_params, param,
                                        np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))
        else:
            holding_days += 1
            curr_profit = (day_high - entry_price) / entry_price
            curr_dd = (day_low - entry_price) / entry_price
            mfe = max(mfe, curr_profit)
            mae = min(mae, curr_dd)

            code = stock_code.replace('sh', '').replace('sz', '').replace('bj', '')

            if day_high >= tp_price:
                hs = _hold_stats(entry_day_idx, day_i)
                exit_p = max(day_open, tp_price)
                return _make_result('simulated', entry_price, tp_price, sl_price,
                                    exit_p, entry_day_idx, day_i, 'tp',
                                    exit_p / entry_price - 1,
                                    gt_t0, channel_w, gt_params, param,
                                    np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))
            if day_low <= sl_price:
                hs = _hold_stats(entry_day_idx, day_i)
                exit_p = min(day_open, sl_price)
                return _make_result('simulated', entry_price, tp_price, sl_price,
                                    exit_p, entry_day_idx, day_i, 'sl',
                                    exit_p / entry_price - 1,
                                    gt_t0, channel_w, gt_params, param,
                                    np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))

            if nearest_support is not None and day_close < nearest_support * 0.98:
                hs = _hold_stats(entry_day_idx, day_i)
                return _make_result('simulated', entry_price, tp_price, sl_price,
                                    day_close, entry_day_idx, day_i, 'ma_support_break',
                                    day_close / entry_price - 1,
                                    gt_t0, channel_w, gt_params, param,
                                    np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))

            body_drop = (day_close - day_open) / (day_open + 1e-9)
            if code.startswith(('688', '689', '300', '920')):
                breakdown_th = -0.09
            else:
                breakdown_th = -0.065
            if body_drop <= breakdown_th:
                hs = _hold_stats(entry_day_idx, day_i)
                return _make_result('simulated', entry_price, tp_price, sl_price,
                                    day_close, entry_day_idx, day_i, 'form_break',
                                    day_close / entry_price - 1,
                                    gt_t0, channel_w, gt_params, param,
                                    np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))

            if indicator_exit and h60_day_bars and fwd_dates is not None and day_close > entry_price:
                day_date = fwd_dates[day_i].normalize()
                ind_bars = h60_day_bars.get(day_date, [])
                for bidx, _bar in ind_bars:
                    _rsi_sig = False
                    if fwd_h60_rsi6 is not None and bidx < len(fwd_h60_rsi6) and bidx < len(fwd_h60_rsi12):
                        r6 = float(fwd_h60_rsi6.iloc[bidx])
                        r12 = float(fwd_h60_rsi12.iloc[bidx])
                        if not (np.isnan(r6) or np.isnan(r12)) and r6 < r12:
                            _rsi_sig = True

                    _kdj_sig = False
                    if fwd_h60_j is not None and bidx < len(fwd_h60_j) and bidx < len(fwd_h60_d):
                        j_v = float(fwd_h60_j.iloc[bidx])
                        d_v = float(fwd_h60_d.iloc[bidx])
                        if not (np.isnan(j_v) or np.isnan(d_v)) and j_v < d_v:
                            _kdj_sig = True

                    do_exit = None
                    if exit_mode == '2bar':
                        if _rsi_sig:
                            rsi_consec_bars += 1
                            if rsi_consec_bars >= 2:
                                do_exit = 'rsi_exit'
                        else:
                            rsi_consec_bars = 0
                        if _kdj_sig:
                            kdj_consec_bars += 1
                            if kdj_consec_bars >= 2:
                                do_exit = 'kdj_exit'
                        else:
                            kdj_consec_bars = 0
                    elif exit_mode == 'peak':
                        if fwd_h60_rsi6 is not None and bidx < len(fwd_h60_rsi6):
                            r6 = float(fwd_h60_rsi6.iloc[bidx])
                            if not np.isnan(r6):
                                if r6 > rsi_peak_val:
                                    rsi_peak_val = r6
                                    rsi_peak_highest = True
                                if rsi_peak_highest and r6 < rsi_peak_val * 0.95 and _rsi_sig:
                                    do_exit = 'rsi_peak_exit'
                        if fwd_h60_j is not None and bidx < len(fwd_h60_j):
                            j_v = float(fwd_h60_j.iloc[bidx])
                            if not np.isnan(j_v):
                                if j_v > j_peak_val:
                                    j_peak_val = j_v
                                    j_peak_highest = True
                                if j_peak_highest and j_v < j_peak_val * 0.95 and _kdj_sig:
                                    do_exit = 'kdj_peak_exit'
                    else:
                        if _rsi_sig:
                            do_exit = 'rsi_exit'
                        elif _kdj_sig:
                            do_exit = 'kdj_exit'

                    if do_exit:
                        hs = _hold_stats(entry_day_idx, day_i)
                        return _make_result('simulated', entry_price, tp_price, sl_price,
                                            day_close, entry_day_idx, day_i, do_exit,
                                            day_close / entry_price - 1,
                                            gt_t0, channel_w, gt_params, param,
                                            np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))

            if holding_days >= 7 and mfe < -0.05:
                hs = _hold_stats(entry_day_idx, day_i)
                return _make_result('simulated', entry_price, tp_price, sl_price,
                                    day_close, entry_day_idx, day_i, 'time_decay',
                                    day_close / entry_price - 1,
                                    gt_t0, channel_w, gt_params, param,
                                    np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))
            if holding_days >= 10 and mfe < 0.01:
                hs = _hold_stats(entry_day_idx, day_i)
                return _make_result('simulated', entry_price, tp_price, sl_price,
                                    day_close, entry_day_idx, day_i, 'time_decay',
                                    day_close / entry_price - 1,
                                    gt_t0, channel_w, gt_params, param,
                                    np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))
            if holding_days >= 15:
                hs = _hold_stats(entry_day_idx, day_i)
                return _make_result('simulated', entry_price, tp_price, sl_price,
                                    day_close, entry_day_idx, day_i, 'expire',
                                    day_close / entry_price - 1,
                                    gt_t0, channel_w, gt_params, param,
                                    np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))

    if entry_day_idx >= 0:
        last_close = float(fwd_closes[n - 1])
        pnl = last_close / entry_price - 1
        hs = _hold_stats(entry_day_idx, n - 1)
        return _make_result('simulated', entry_price, tp_price, sl_price,
                            last_close, entry_day_idx, n - 1, 'expire', pnl,
                            gt_t0, channel_w, gt_params, param,
                            np.nan, np.nan, np.nan, entry_type=entry_type, **_exit(hs))

    return _make_result('order_timeout', np.nan, np.nan, np.nan,
                        np.nan, -1, -1, 'order_timeout', np.nan,
                        gt_t0, channel_w, gt_params, param,
                        np.nan, np.nan, np.nan, **fwd_kw)


def _make_result(status, entry_price, tp_price, sl_price,
                 exit_price, entry_day_idx, exit_day_idx, exit_reason, pnl,
                 gt_t0, channel_width_t0, gt_params, param,
                 gt_at_entry, ema_h_at_entry, channel_at_entry,
                 fwd_low=np.nan, fwd_low_day=np.nan,
                 fwd_high=np.nan, fwd_high_day=np.nan,
                 hold_low=np.nan, hold_low_day=np.nan,
                 hold_high=np.nan, hold_high_day=np.nan,
                 entry_type='none'):
    gap = np.nan
    if not np.isnan(gt_at_entry) and not np.isnan(entry_price) and gt_at_entry > 0:
        gap = (entry_price - gt_at_entry) / gt_at_entry

    return {
        'status': status,
        'target_entry_price': round(gt_t0, 4) if not np.isnan(gt_t0) else np.nan,
        'actual_entry_price': round(entry_price, 4) if not np.isnan(entry_price) else np.nan,
        'entry_day_idx': entry_day_idx if entry_day_idx >= 0 else np.nan,
        'tp_price': round(tp_price, 4) if not np.isnan(tp_price) else np.nan,
        'sl_price': round(sl_price, 4) if not np.isnan(sl_price) else np.nan,
        'exit_price': round(exit_price, 4) if not np.isnan(exit_price) else np.nan,
        'exit_day_idx': exit_day_idx if exit_day_idx >= 0 else np.nan,
        'exit_reason': exit_reason,
        'pnl': round(pnl, 6) if not np.isnan(pnl) else np.nan,
        'gt_t0': round(gt_t0, 4),
        'gt_channel_width': round(channel_width_t0, 4),
        'gt_n': gt_params['n'],
        'gt_k': round(gt_params['k'], 3),
        'gt_offset': round(gt_params['offset'], 3),
        'tp_mult': param.get('tp_mult', np.nan),
        'sl_buffer': param.get('sl_buffer', np.nan),
        'gt_at_entry': round(gt_at_entry, 4) if not np.isnan(gt_at_entry) else np.nan,
        'ema_h_at_entry': round(ema_h_at_entry, 4) if not np.isnan(ema_h_at_entry) else np.nan,
        'channel_at_entry': round(channel_at_entry, 4) if not np.isnan(channel_at_entry) else np.nan,
        'gap_at_entry': round(gap, 4) if not np.isnan(gap) else np.nan,
        'fwd_low': round(fwd_low, 4) if not np.isnan(fwd_low) else np.nan,
        'fwd_low_day': int(fwd_low_day) if not np.isnan(fwd_low_day) else np.nan,
        'fwd_high': round(fwd_high, 4) if not np.isnan(fwd_high) else np.nan,
        'fwd_high_day': int(fwd_high_day) if not np.isnan(fwd_high_day) else np.nan,
        'hold_low': round(hold_low, 4) if not np.isnan(hold_low) else np.nan,
        'hold_low_day': int(hold_low_day) if not np.isnan(hold_low_day) else np.nan,
        'hold_high': round(hold_high, 4) if not np.isnan(hold_high) else np.nan,
        'hold_high_day': int(hold_high_day) if not np.isnan(hold_high_day) else np.nan,
        'entry_type': entry_type,
    }


def _build_param_lookup(param_df: pd.DataFrame) -> dict:
    lookup = {}
    for _, row in param_df.iterrows():
        key = (row['zone_tag'], row['dd_tier'])
        lookup[key] = row.to_dict()
    return lookup


# ---------------------------------------------------------------------------
# Step 2.5: 参数倒推分析
# ---------------------------------------------------------------------------
PARAM_ANALYSIS_REPORT = os.path.join(DOC_DIR, 'param_analysis_report.md')
SCAN_SPANS = [3, 5, 8, 10, 13, 17, 21]
TARGET_RR = 2.0
TARGET_SL_BUFFER = 0.03


def _analyze_ideal_params(merged_df: pd.DataFrame, param_df: pd.DataFrame):
    """从底部/顶部价格倒推合理参数值。"""
    print("\n  [Step 2.5] 参数倒推分析...")

    valid = merged_df.dropna(
        subset=['max_drawdown', 'golden_trend_t0', 'last_close', 'position_ratio']
    ).copy()
    valid = valid[valid['zone_tag'] != 'unknown']

    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'], bins=DRAWDOWN_BINS, labels=DRAWDOWN_LABELS,
    )

    param_lookup = _build_param_lookup(param_df)

    rows = []
    for i, (idx, row) in enumerate(valid.iterrows()):
        if (i + 1) % 500 == 0:
            print(f"    分析 {i + 1}/{len(valid)} ...")

        stock = row['stock_code']
        t0_date = pd.Timestamp(row['t0_date'])
        zone = row['zone_tag']
        gt_t0 = row['golden_trend_t0']
        dd_tier = row['dd_tier']

        param = param_lookup.get((zone, str(dd_tier)))
        if param is None:
            for k, v in param_lookup.items():
                if k[0] == zone and v.get('enabled', False):
                    param = v
                    break
        if param is None or not param.get('enabled', False):
            continue

        daily_pre = _load_pre_signal_daily_60m(stock, t0_date)
        if daily_pre is None or len(daily_pre) < MIN_PRE_BARS:
            daily_pre = _load_pre_signal_daily_fallback(stock, t0_date)
        daily_fwd = _load_forward_daily(stock, t0_date)
        if daily_fwd is None or daily_fwd.empty:
            continue

        gt_info = _compute_gt_on_combined(daily_pre, daily_fwd)
        if gt_info is None:
            continue

        fwd_gt = gt_info['fwd_gt']
        fwd_ema_h = gt_info['fwd_ema_h']
        n = min(len(daily_fwd), FUTURE_DAYS)
        fwd_lows = daily_fwd['low'].values[:n].astype(float)
        fwd_highs = daily_fwd['high'].values[:n].astype(float)
        fwd_low = float(np.min(fwd_lows))
        fwd_high = float(np.max(fwd_highs))
        gt_val = float(gt_info['gt_t0'])
        channel_w = float(gt_info['channel_width_t0'])

        if fwd_low <= 0 or gt_val <= 0 or fwd_high <= fwd_low:
            continue

        rec = {
            'stock': stock, 't0_date': t0_date, 'zone': zone,
            'gt_t0': gt_val, 'last_close': row['last_close'],
            'fwd_low': fwd_low, 'fwd_high': fwd_high,
            'channel_width': channel_w,
            'gt_position': (gt_val - fwd_low) / (fwd_high - fwd_low),
            'fwd_range_pct': (fwd_high - fwd_low) / fwd_low,
            'mfe_from_gt': (fwd_high - gt_val) / gt_val,
            'mae_from_gt': (fwd_low - gt_val) / gt_val,
        }

        last_c = float(daily_pre['close'].iloc[-1])
        for span in (30, 90, 150, 240):
            if len(daily_pre) >= span:
                ma_v = float(daily_pre['close'].rolling(span).mean().iloc[-1])
                rec[f'dist_ma{span}'] = (last_c - ma_v) / ma_v if ma_v > 0 else np.nan
            else:
                rec[f'dist_ma{span}'] = np.nan

        supports = 0
        for span in (30, 90, 150, 240):
            if len(daily_pre) >= span:
                ma_v = float(daily_pre['close'].rolling(span).mean().iloc[-1])
                if ma_v > 0 and last_c > ma_v:
                    supports += 1
        rec['above_ma_count'] = supports

        # --- 分析 2: 多 span 金叉扫描 ---
        combined = pd.concat([daily_pre, daily_fwd]).reset_index(drop=True)
        c = combined['close'].astype(float)
        n_pre = len(daily_pre)

        for span in SCAN_SPANS:
            ema_s = c.ewm(span=span, adjust=False).mean()
            mtl_s = ema_s.ewm(span=span, adjust=False).mean()
            mtl_r = (mtl_s > mtl_s.shift(1)).astype(int)
            buy = (c > mtl_s) & (c.shift(1) <= mtl_s.shift(1)) & (mtl_r == 1)
            fwd_buy = buy.iloc[n_pre:].values

            cross_day = -1
            cross_gap = np.nan
            cross_close = np.nan
            for d in range(min(len(fwd_buy), n)):
                if fwd_buy[d]:
                    cross_day = d
                    cross_close = float(c.iloc[n_pre + d])
                    gt_d = float(fwd_gt[d]) if d < len(fwd_gt) and fwd_gt[d] > 0 else gt_val
                    cross_gap = (cross_close - gt_d) / gt_d
                    break

            rec[f'span{span}_day'] = cross_day
            rec[f'span{span}_gap'] = cross_gap
            rec[f'span{span}_close'] = cross_close

        # --- 分析 3: 理想入场价倒推 ---
        # TP 可达: entry * (1 + tp_pct) <= fwd_high
        # SL 安全: entry * (1 - sl_buffer) >= fwd_low
        sl_buf = TARGET_SL_BUFFER
        tp_pct = sl_buf * TARGET_RR  # e.g. 3% * 2 = 6%

        ideal_entry_max = fwd_high / (1 + tp_pct)
        ideal_entry_min = fwd_low / (1 - sl_buf)
        rec['ideal_entry_max'] = ideal_entry_max
        rec['ideal_entry_min'] = ideal_entry_min
        rec['ideal_gap_max'] = (ideal_entry_max - gt_val) / gt_val
        rec['ideal_gap_min'] = (ideal_entry_min - gt_val) / gt_val
        rec['ideal_feasible'] = ideal_entry_min <= ideal_entry_max

        rows.append(rec)

    df = pd.DataFrame(rows)
    print(f"    分析完成: {len(df)} 个 enabled 信号")

    if df.empty:
        print("    无 enabled 信号，跳过参数倒推报告")
        return

    # === 生成报告 ===
    lines = []
    lines.append('# 参数倒推分析报告\n')
    lines.append(f'**日期**: {pd.Timestamp.now().strftime("%Y-%m-%d")}\n')
    lines.append(f'**样本数**: {len(df)} enabled 信号\n')

    # --- 表 1: 前视价格解剖 ---
    lines.append('\n## 一、前视价格解剖 (按 Zone)\n')
    lines.append('| Zone | N | GT位置(中位) | 前视振幅(中位) | MFE从GT(中位) | MAE从GT(中位) | dist_MA30 | dist_MA90 | dist_MA150 | dist_MA240 | >MA数 |')
    lines.append('|------|---|-------------|---------------|--------------|--------------|-----------|-----------|------------|------------|-------|')
    for zone in ZONE_ORDER:
        sub = df[df['zone'] == zone]
        if len(sub) == 0:
            continue

        def _med(col):
            v = sub[col].dropna().median()
            return f'{v:.2%}' if not np.isnan(v) else '-'

        above_med = sub['above_ma_count'].dropna().median()
        lines.append(
            f'| {zone} | {len(sub)} | '
            f'{sub["gt_position"].median():.2%} | '
            f'{sub["fwd_range_pct"].median():.2%} | '
            f'{sub["mfe_from_gt"].median():.2%} | '
            f'{sub["mae_from_gt"].median():.2%} | '
            f'{_med("dist_ma30")} | {_med("dist_ma90")} | '
            f'{_med("dist_ma150")} | {_med("dist_ma240")} | '
            f'{above_med:.0f} |'
        )

    # --- 表 2: span × zone 金叉 gap 矩阵 ---
    lines.append('\n## 二、多 Span MTL 金叉扫描\n')
    lines.append('### 中位入场 gap (entry_close - GT) / GT\n')
    header = '| Zone |'
    sep = '|------|'
    for s in SCAN_SPANS:
        header += f' span={s} |'
        sep += '------|'
    lines.append(header)
    lines.append(sep)

    for zone in ZONE_ORDER:
        sub = df[df['zone'] == zone]
        if len(sub) == 0:
            continue
        row_str = f'| {zone} |'
        for s in SCAN_SPANS:
            col = f'span{s}_gap'
            vals = sub[col].dropna()
            if len(vals) > 0:
                row_str += f' {vals.median():.2%} |'
            else:
                row_str += ' - |'
        lines.append(row_str)

    lines.append('\n### 中位金叉日 (T+N)\n')
    header = '| Zone |'
    sep = '|------|'
    for s in SCAN_SPANS:
        header += f' span={s} |'
        sep += '------|'
    lines.append(header)
    lines.append(sep)

    for zone in ZONE_ORDER:
        sub = df[df['zone'] == zone]
        if len(sub) == 0:
            continue
        row_str = f'| {zone} |'
        for s in SCAN_SPANS:
            col = f'span{s}_day'
            vals = sub[sub[col] >= 0][col]
            if len(vals) > 0:
                row_str += f' T+{vals.median():.0f} |'
            else:
                row_str += ' - |'
        lines.append(row_str)

    lines.append('\n### 金叉触发率\n')
    header = '| Zone |'
    sep = '|------|'
    for s in SCAN_SPANS:
        header += f' span={s} |'
        sep += '------|'
    lines.append(header)
    lines.append(sep)

    for zone in ZONE_ORDER:
        sub = df[df['zone'] == zone]
        if len(sub) == 0:
            continue
        row_str = f'| {zone} |'
        for s in SCAN_SPANS:
            col = f'span{s}_day'
            hit = (sub[col] >= 0).sum()
            row_str += f' {hit / len(sub):.0%} |'
        lines.append(row_str)

    # --- 表 3: 理想入场 gap ---
    lines.append('\n## 三、理想入场价倒推\n')
    lines.append(f'假设: R:R = {TARGET_RR}:1, SL buffer = {TARGET_SL_BUFFER:.0%}\n')
    lines.append(f'→ TP = entry × (1 + {TARGET_SL_BUFFER * TARGET_RR:.0%}), SL = entry × (1 - {TARGET_SL_BUFFER:.0%})\n')
    lines.append('| Zone | N | 可行率 | ideal_gap_min(中位) | ideal_gap_max(中位) |')
    lines.append('|------|---|-------|-------------------|-------------------|')
    for zone in ZONE_ORDER:
        sub = df[df['zone'] == zone]
        if len(sub) == 0:
            continue
        feasible = sub['ideal_feasible'].sum()
        feas_sub = sub[sub['ideal_feasible']]
        ig_min = feas_sub['ideal_gap_min'].median() if len(feas_sub) > 0 else np.nan
        ig_max = feas_sub['ideal_gap_max'].median() if len(feas_sub) > 0 else np.nan
        lines.append(
            f'| {zone} | {len(sub)} | {feasible / len(sub):.0%} | '
            f'{ig_min:.2%} | {ig_max:.2%} |'
        )

    # --- 表 4: 推荐参数 ---
    lines.append('\n## 四、推荐参数\n')

    # 最优 span: 使整体 median gap 最接近 ideal_gap 中位数
    all_feasible = df[df['ideal_feasible']]
    if len(all_feasible) > 0:
        ideal_median = all_feasible['ideal_gap_max'].median()
        lines.append(f'**目标 gap (ideal_gap_max 中位数)**: {ideal_median:.2%}\n')

        best_span = None
        best_diff = 999
        lines.append('| Span | 整体中位 gap | 与目标差距 |')
        lines.append('|------|-------------|-----------|')
        for s in SCAN_SPANS:
            col = f'span{s}_gap'
            vals = df[col].dropna()
            if len(vals) == 0:
                continue
            med = vals.median()
            diff = abs(med - ideal_median)
            lines.append(f'| {s} | {med:.2%} | {diff:.2%} |')
            if diff < best_diff:
                best_diff = diff
                best_span = s

        if best_span:
            lines.append(f'\n**推荐 MTL span**: {best_span}\n')

    # 推荐 sl_buffer: 基于 mae_from_gt 分布
    mae = df['mae_from_gt']
    mae_p10 = mae.quantile(0.10)
    lines.append(f'\n### SL buffer 建议')
    lines.append(f'- MAE从GT (10th percentile): {mae_p10:.2%}')
    lines.append(f'- 含义: 10% 的信号价格跌破 GT 超过 {-mae_p10:.2%}')
    rec_sl = max(-mae_p10, 0.02)
    lines.append(f'- 推荐 sl_buffer: {rec_sl:.2%} (确保 SL 在 GT 下方安全距离)\n')

    # 推荐 tp_mult
    if len(all_feasible) > 0:
        mfe = all_feasible['mfe_from_gt']
        ch = all_feasible['channel_width']
        ch_ratio = (mfe / (ch / all_feasible['gt_t0'])).median() if (ch > 0).any() else 2.0
        lines.append(f'### TP mult 建议')
        lines.append(f'- MFE从GT (中位): {mfe.median():.2%}')
        lines.append(f'- MFE / channel_ratio (中位): {ch_ratio:.2f}')
        lines.append(f'- 当前 TP_MULT_MAP: {TP_MULT_MAP}\n')

    # 推荐 entry_buffer
    gt_pos = df['gt_position']
    lines.append(f'### Entry buffer 建议')
    lines.append(f'- GT 在前视区间位置 (中位): {gt_pos.median():.2%}')
    lines.append(f'- GT 在前视区间位置 (25th): {gt_pos.quantile(0.25):.2%}')
    below_price = (df['gt_t0'] < df['last_close']).mean()
    lines.append(f'- GT < last_close 的比例: {below_price:.0%}')

    report = '\n'.join(lines)
    with open(PARAM_ANALYSIS_REPORT, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"    已写入 {PARAM_ANALYSIS_REPORT}")
    print(f"\n{'=' * 70}")
    print(report[:3000])


def _process_stock_signals(args):
    """单只股票的信号处理 worker (multiprocessing 安全)。

    同一只股票的信号按日期顺序处理，内部维护 cooldown 状态。
    不同股票之间完全独立，可并行。

    Args:
        args: (stock_code, signals_list, param_lookup, fallback_param,
               ma_pairs_or_none, cooldown_days, indicator_mode, indicator_exit)
              ma_pairs_or_none: list of (fast, slow) tuples → comparison mode
                                None → single backtest mode (default pair)
              indicator_mode: 'none'|'rsi'|'kdj'|'any' — 指标确认模式
              indicator_exit: bool — 是否启用指标退出
    """
    if len(args) >= 8:
        stock_code, signals, param_lookup, fallback_param, ma_pairs, cooldown_days, indicator_mode, indicator_exit = args[:8]
    else:
        stock_code, signals, param_lookup, fallback_param, ma_pairs, cooldown_days = args[:6]
        indicator_mode = 'none'
        indicator_exit = False
    ind_configs = args[8] if len(args) >= 9 else None
    results = []
    last_entry_date = None

    for sig in signals:
        t0_date = pd.Timestamp(sig['t0_date'])
        zone_tag = sig['zone_tag']
        dd_tier = sig['dd_tier']
        support_score = sig.get('support_score', np.nan)
        ma_zone = sig.get('ma_zone', '')

        param = param_lookup.get((zone_tag, str(dd_tier)))
        if param is None:
            for k, v in param_lookup.items():
                if k[0] == zone_tag and v.get('enabled', False):
                    param = v
                    break
        if param is None:
            param = fallback_param

        base_rec = {
            'signal_idx': sig['signal_idx'],
            'stock_code': stock_code,
            't0_date': t0_date,
            'zone_tag': zone_tag,
            'dd_tier': str(dd_tier),
            'position_ratio': sig.get('position_ratio', np.nan),
            'trend_tag': sig.get('trend_tag', ''),
            'golden_trend_t0': sig.get('golden_trend_t0', np.nan),
            'support_score': support_score,
            'ma_zone': ma_zone,
        }

        if not param.get('enabled', False):
            daily_fwd = _load_forward_daily(stock_code, t0_date)
            fwd_stats = {}
            if daily_fwd is not None and not daily_fwd.empty:
                nn = min(len(daily_fwd), FUTURE_DAYS)
                fl = daily_fwd['low'].values[:nn].astype(float)
                fh = daily_fwd['high'].values[:nn].astype(float)
                fwd_stats = dict(
                    fwd_low=round(float(np.min(fl)), 4),
                    fwd_low_day=int(np.argmin(fl)),
                    fwd_high=round(float(np.max(fh)), 4),
                    fwd_high_day=int(np.argmax(fh)),
                )
            er = _empty_result('disabled')
            er.update(fwd_stats)
            results.append({**base_rec, **er})
            continue

        if not pd.isna(support_score) and support_score < 3:
            results.append({**base_rec, **_empty_result('low_support_skip')})
            continue

        if ma_zone in ('bottom', 'extended', 'high_risk'):
            results.append({**base_rec, **_empty_result(f'ma_zone_skip_{ma_zone}')})
            continue

        if last_entry_date is not None:
            if (t0_date - last_entry_date).days < cooldown_days:
                results.append({**base_rec, **_empty_result('cooldown')})
                continue

        daily_pre = _load_pre_signal_daily_60m(stock_code, t0_date)
        if daily_pre is None or len(daily_pre) < MIN_PRE_BARS:
            daily_pre = _load_pre_signal_daily_fallback(stock_code, t0_date)
        daily_fwd = _load_forward_daily(stock_code, t0_date)
        pre_60m = _load_pre_60m(stock_code, t0_date)
        fwd_60m = _load_forward_60m(stock_code, t0_date)

        if ma_pairs is not None:
            any_traded = False
            for pair in ma_pairs:
                sim = run_single_signal_gt(
                    daily_pre, daily_fwd, zone_tag, param,
                    stock_code=stock_code, support_score=support_score,
                    ma_zone=ma_zone, pre_60m=pre_60m, fwd_60m=fwd_60m,
                    h60_trend_pair=pair,
                    indicator_mode=indicator_mode, indicator_exit=indicator_exit,
                )
                rec = {**base_rec, '_ma_pair': pair, **sim}
                results.append(rec)
                if sim['status'] == 'simulated':
                    any_traded = True
            if any_traded:
                last_entry_date = t0_date
        else:
            configs = ind_configs if ind_configs is not None else [(indicator_mode, indicator_exit)]
            any_traded = False
            for cfg in configs:
                _im = cfg[0]
                _ie = cfg[1]
                _rp = cfg[2] if len(cfg) > 2 else (6, 12, 24)
                _kn = cfg[3] if len(cfg) > 3 else 27
                _em = cfg[4] if len(cfg) > 4 else 'standard'
                sim = run_single_signal_gt(
                    daily_pre, daily_fwd, zone_tag, param,
                    stock_code=stock_code, support_score=support_score,
                    ma_zone=ma_zone, pre_60m=pre_60m, fwd_60m=fwd_60m,
                    indicator_mode=_im, indicator_exit=_ie,
                    rsi_periods=_rp, kdj_n=_kn, exit_mode=_em,
                )
                rec = {**base_rec, '_ind_config': cfg, **sim}
                results.append(rec)
                if sim['status'] == 'simulated':
                    any_traded = True
            if any_traded:
                last_entry_date = t0_date

    return results


def run_h60_ma_comparison(merged_df: pd.DataFrame, param_df: pd.DataFrame):
    """对比不同 60m MA 趋势对的入场效果。

    每个信号加载一次数据，对所有 MA pair 分别模拟入场/出场，最后汇总对比。
    """
    print("\n  [H60 MA Comparison] 对比不同小时线 MA 趋势对...")

    ma_pairs = [(7, 13), (7, 20), (7, 30), (10, 30), (13, 30)]

    valid = merged_df.dropna(
        subset=['max_drawdown', 'golden_trend_t0', 'last_close', 'position_ratio']
    ).copy()
    valid = valid[valid['zone_tag'] != 'unknown']
    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'], bins=DRAWDOWN_BINS, labels=DRAWDOWN_LABELS,
    )
    param_lookup = _build_param_lookup(param_df)
    fallback_param = {'enabled': True, 'tp_mult': 2.0, 'sl_buffer': 0.03, 'entry_buffer': 0.03}
    cooldown_days = 5

    all_results = {pair: [] for pair in ma_pairs}
    n_total = len(valid)

    # --- 按股票分组，准备并行处理 ---
    stock_groups = {}
    for idx, row in valid.iterrows():
        stock = row['stock_code']
        if stock not in stock_groups:
            stock_groups[stock] = []
        stock_groups[stock].append({
            'signal_idx': idx,
            't0_date': row['t0_date'],
            'zone_tag': row['zone_tag'],
            'dd_tier': row['dd_tier'],
            'position_ratio': row.get('position_ratio', np.nan),
            'trend_tag': row.get('trend_tag', ''),
            'golden_trend_t0': row.get('golden_trend_t0', np.nan),
            'support_score': row.get('support_score', np.nan),
            'ma_zone': row.get('ma_zone', ''),
        })

    # 确保每组内按日期排序 (cooldown 依赖顺序)
    for stock in stock_groups:
        stock_groups[stock].sort(key=lambda s: pd.Timestamp(s['t0_date']))

    n_stocks = len(stock_groups)
    n_cpus = min(cpu_count(), n_stocks, 31)
    print(f"    {n_total} 信号, {n_stocks} 只股票, {n_cpus} 进程并行...")

    worker_args = [
        (stock, sigs, param_lookup, fallback_param, ma_pairs, cooldown_days)
        for stock, sigs in stock_groups.items()
    ]

    t0 = time.time()
    with Pool(processes=n_cpus) as pool:
        chunk_results = pool.map(_process_stock_signals, worker_args)
    elapsed = time.time() - t0

    # --- 汇总结果，按 ma_pair 分组 ---
    n_filtered = n_cooldown = n_traded = 0
    for stock_res in chunk_results:
        for rec in stock_res:
            pair = rec.pop('_ma_pair', None)
            if pair is not None and pair in all_results:
                all_results[pair].append(rec)
            status = rec.get('status', '')
            if status == 'simulated':
                n_traded += 1
            elif status in ('low_support_skip', 'ma_zone_skip_bottom',
                            'ma_zone_skip_extended', 'ma_zone_skip_high_risk',
                            'disabled'):
                n_filtered += 1
            elif status == 'cooldown':
                n_cooldown += 1

    print(f"    并行完成: 耗时 {elapsed:.1f}s, traded={n_traded}, "
          f"filtered={n_filtered}, cooldown={n_cooldown}")

    print(f"\n    {'=' * 85}")
    print(f"    60m MA 趋势对对比结果")
    print(f"    {'=' * 85}")
    print(f"    {'MA pair':<12} {'trades':>7} {'entry%':>8} {'WR':>8} "
          f"{'PF':>6} {'avg PnL':>9} {'median':>8} {'max_loss':>9} {'circuit%':>9}")
    print(f"    {'-' * 85}")

    for pair in ma_pairs:
        rdf = pd.DataFrame(all_results[pair])
        sim = rdf[rdf['status'] == 'simulated']
        pnl = sim['pnl'].dropna()
        if len(pnl) == 0:
            print(f"    MA{pair[0]}/MA{pair[1]:<6} {'0':>7}")
            continue
        s = _calc_stats(pnl)
        entry_rate = len(sim) / len(rdf) if len(rdf) > 0 else 0
        cb = (sim['exit_reason'] == 'circuit_break').sum()
        cb_pct = cb / len(sim) if len(sim) > 0 else 0
        print(f"    MA{pair[0]}/MA{pair[1]:<6} {s['n']:>7} {entry_rate:>7.1%} "
              f"{s['wr']:>7.1%} {s['pf']:>6.2f} {s['avg']:>8.2%} "
              f"{s['median']:>7.2%} {s['max_loss']:>8.2%} {cb_pct:>8.1%}")

    print(f"    {'=' * 85}")

    print(f"\n    按 Zone 细分 (trades / WR / PF):")
    print(f"    {'MA pair':<12}", end='')
    for z in ZONE_ORDER:
        print(f" {z:>24}", end='')
    print()
    print(f"    {'-' * (12 + 25 * len(ZONE_ORDER))}")

    for pair in ma_pairs:
        rdf = pd.DataFrame(all_results[pair])
        sim = rdf[rdf['status'] == 'simulated']
        print(f"    MA{pair[0]}/MA{pair[1]:<6}", end='')
        for z in ZONE_ORDER:
            sub = sim[sim['zone_tag'] == z]['pnl'].dropna()
            if len(sub) == 0:
                print(f" {'0':>24}", end='')
            else:
                zs = _calc_stats(sub)
                print(f" {zs['n']:>4}/{zs['wr']:.0%}/{zs['pf']:.2f}{'':>9}", end='')
        print()

    print(f"\n    入场方式分布 (60m vs daily):")
    print(f"    {'MA pair':<12} {'60m入场':>8} {'daily入场':>10} {'60m WR':>8} {'daily WR':>9} {'60m PF':>8} {'daily PF':>9}")
    print(f"    {'-' * 72}")

    for pair in ma_pairs:
        rdf = pd.DataFrame(all_results[pair])
        sim = rdf[rdf['status'] == 'simulated']
        if sim.empty:
            continue
        n_60m = (sim['entry_type'] == '60m').sum()
        n_daily = (sim['entry_type'] == 'daily').sum()
        pnl_60m = sim[sim['entry_type'] == '60m']['pnl'].dropna()
        pnl_daily = sim[sim['entry_type'] == 'daily']['pnl'].dropna()
        s60 = _calc_stats(pnl_60m)
        sd = _calc_stats(pnl_daily)
        print(f"    MA{pair[0]}/MA{pair[1]:<6} {n_60m:>8} {n_daily:>10} "
              f"{s60['wr']:>7.1%} {sd['wr']:>8.1%} {s60['pf']:>7.2f} {sd['pf']:>8.2f}")


def run_h60_indicator_comparison(merged_df: pd.DataFrame, param_df: pd.DataFrame):
    """对比不同 60m 指标确认模式 + 指标退出的效果。

    模式:
      - baseline: 无指标确认 (仅 MA7/MA30 交叉)
      - rsi: RSI(6,12,24) 多头排列确认
      - kdj: KDJ(27,3,3) J-D 金叉确认
      - any: RSI 或 KDJ 任一满足
    每种模式 × 指标退出 (on/off) = 8 种组合
    """
    print("\n  [H60 Indicator Comparison] 对比指标确认模式 + 指标退出...")

    ind_configs = [
        ('none', False, (6, 12, 24), 27, 'standard'),
        ('none', True, (6, 12, 24), 27, 'standard'),
        ('rsi', False, (6, 12, 24), 27, 'standard'),
        ('rsi', True, (6, 12, 24), 27, 'standard'),
        ('kdj', False, (6, 12, 24), 27, 'standard'),
        ('kdj', True, (6, 12, 24), 27, 'standard'),
        ('any', False, (6, 12, 24), 27, 'standard'),
        ('any', True, (6, 12, 24), 27, 'standard'),
        ('rsi', True, (10, 20, 40), 27, 'standard'),
    ]

    valid = merged_df.dropna(
        subset=['max_drawdown', 'golden_trend_t0', 'last_close', 'position_ratio']
    ).copy()
    valid = valid[valid['zone_tag'] != 'unknown']
    if 'ma_zone' in valid.columns:
        valid = valid[valid['ma_zone'] != 'unknown']
    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'], bins=DRAWDOWN_BINS, labels=DRAWDOWN_LABELS,
    )
    param_lookup = _build_param_lookup(param_df)
    fallback_param = {'enabled': True, 'tp_mult': 2.0, 'sl_buffer': 0.03, 'entry_buffer': 0.03}
    cooldown_days = 5

    stock_groups = {}
    for idx, row in valid.iterrows():
        stock = row['stock_code']
        if stock not in stock_groups:
            stock_groups[stock] = []
        stock_groups[stock].append({
            'signal_idx': idx,
            't0_date': row['t0_date'],
            'zone_tag': row['zone_tag'],
            'dd_tier': row['dd_tier'],
            'position_ratio': row.get('position_ratio', np.nan),
            'trend_tag': row.get('trend_tag', ''),
            'golden_trend_t0': row.get('golden_trend_t0', np.nan),
            'support_score': row.get('support_score', np.nan),
            'ma_zone': row.get('ma_zone', ''),
        })

    for stock in stock_groups:
        stock_groups[stock].sort(key=lambda s: pd.Timestamp(s['t0_date']))

    n_stocks = len(stock_groups)
    n_cpus = min(cpu_count(), n_stocks, 31)
    print(f"    {len(valid)} 信号, {n_stocks} 只股票, {n_cpus} 进程并行...")

    worker_args = [
        (stock, sigs, param_lookup, fallback_param, None, cooldown_days,
         'none', False, ind_configs)
        for stock, sigs in stock_groups.items()
    ]

    t0 = time.time()
    with Pool(processes=n_cpus) as pool:
        chunk_results = pool.map(_process_stock_signals, worker_args)
    elapsed = time.time() - t0

    all_results = {cfg: [] for cfg in ind_configs}
    n_filtered = n_cooldown = 0
    for stock_res in chunk_results:
        for rec in stock_res:
            cfg = rec.pop('_ind_config', None)
            if cfg is not None and cfg in all_results:
                all_results[cfg].append(rec)
            status = rec.get('status', '')
            if status in ('low_support_skip', 'ma_zone_skip_bottom',
                          'ma_zone_skip_extended', 'ma_zone_skip_high_risk',
                          'disabled'):
                n_filtered += 1
            elif status == 'cooldown':
                n_cooldown += 1

    print(f"    并行完成: 耗时 {elapsed:.1f}s, filtered={n_filtered}, cooldown={n_cooldown}")

    def _cfg_label(cfg):
        m, e = cfg[0], cfg[1]
        rsi_p = cfg[2] if len(cfg) > 2 else (6, 12, 24)
        rsi_str = f"({','.join(str(x) for x in rsi_p)})" if rsi_p != (6, 12, 24) else ""
        return f"{m:>6}{rsi_str} + exit={'ON' if e else 'OFF'}"

    print(f"\n    {'=' * 105}")
    print(f"    60m 指标确认 + 指标退出 对比结果")
    print(f"    {'=' * 105}")
    print(f"    {'Config':<32} {'trades':>7} {'entry%':>8} {'WR':>8} "
          f"{'PF':>6} {'avg PnL':>9} {'median':>8} {'max_loss':>9} {'exit_type_dist'}")
    print(f"    {'-' * 105}")

    for cfg in ind_configs:
        rdf = pd.DataFrame(all_results[cfg])
        sim = rdf[rdf['status'] == 'simulated']
        pnl = sim['pnl'].dropna()
        if len(pnl) == 0:
            print(f"    {_cfg_label(cfg):<32} {'0':>7}")
            continue
        s = _calc_stats(pnl)
        entry_rate = len(sim) / len(rdf) if len(rdf) > 0 else 0

        exit_counts = sim['exit_reason'].value_counts().to_dict()
        exit_str = ', '.join(f'{k}:{v}' for k, v in sorted(exit_counts.items()))

        print(f"    {_cfg_label(cfg):<32} {s['n']:>7} {entry_rate:>7.1%} "
              f"{s['wr']:>7.1%} {s['pf']:>6.2f} {s['avg']:>8.2%} "
              f"{s['median']:>7.2%} {s['max_loss']:>8.2%} {exit_str}")

    print(f"    {'=' * 105}")

    print(f"\n    按 Zone 细分 (trades / WR / PF):")
    header = f"    {'Config':<32}"
    for z in ZONE_ORDER:
        header += f" {z:>24}"
    print(header)
    print(f"    {'-' * (32 + 25 * len(ZONE_ORDER))}")

    for cfg in ind_configs:
        rdf = pd.DataFrame(all_results[cfg])
        sim = rdf[rdf['status'] == 'simulated']
        row_str = f"    {_cfg_label(cfg):<32}"
        for z in ZONE_ORDER:
            sub = sim[sim['zone_tag'] == z]['pnl'].dropna()
            if len(sub) == 0:
                row_str += f" {'0':>24}"
            else:
                zs = _calc_stats(sub)
                row_str += f" {zs['n']:>4}/{zs['wr']:.0%}/{zs['pf']:.2f}{'':>9}"
        print(row_str)

    print(f"\n    入场方式分布 (60m vs daily):")
    print(f"    {'Config':<32} {'60m':>6} {'daily':>6} {'60m WR':>8} {'daily WR':>9} {'60m PF':>8} {'daily PF':>9}")
    print(f"    {'-' * 82}")

    for cfg in ind_configs:
        rdf = pd.DataFrame(all_results[cfg])
        sim = rdf[rdf['status'] == 'simulated']
        if sim.empty:
            continue
        n_60m = (sim['entry_type'] == '60m').sum()
        n_daily = (sim['entry_type'] == 'daily').sum()
        pnl_60m = sim[sim['entry_type'] == '60m']['pnl'].dropna()
        pnl_daily = sim[sim['entry_type'] == 'daily']['pnl'].dropna()
        s60 = _calc_stats(pnl_60m)
        sd = _calc_stats(pnl_daily)
        print(f"    {_cfg_label(cfg):<32} {n_60m:>6} {n_daily:>6} "
              f"{s60['wr']:>7.1%} {sd['wr']:>8.1%} {s60['pf']:>7.2f} {sd['pf']:>8.2f}")

    print(f"\n{'=' * 70}\n")


def run_indicator_window_analysis(merged_df: pd.DataFrame, param_df: pd.DataFrame):
    """提取每笔交易价格高点前后5根60m K线的指标快照，用于分析最优退出时机。

    1. 先用 baseline (无指标退出) 跑回测，获取所有成交信号
    2. 对每笔成交，重新加载 60m 数据并计算指标
    3. 在持仓区间找到价格最高的 60m bar (price peak)
    4. 提取 peak ± 5 bars 的指标值
    5. 输出 CSV + 统计报告
    """
    print("\n  [Indicator Window] 提取价格高点前后指标窗口...")

    valid = merged_df.dropna(
        subset=['max_drawdown', 'golden_trend_t0', 'last_close', 'position_ratio']
    ).copy()
    valid = valid[valid['zone_tag'] != 'unknown']
    if 'ma_zone' in valid.columns:
        valid = valid[valid['ma_zone'] != 'unknown']
    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'], bins=DRAWDOWN_BINS, labels=DRAWDOWN_LABELS,
    )
    param_lookup = _build_param_lookup(param_df)
    fallback_param = {'enabled': True, 'tp_mult': 2.0, 'sl_buffer': 0.03, 'entry_buffer': 0.03}
    cooldown_days = 5

    stock_groups = {}
    for idx, row in valid.iterrows():
        stock = row['stock_code']
        if stock not in stock_groups:
            stock_groups[stock] = []
        stock_groups[stock].append({
            'signal_idx': idx,
            't0_date': row['t0_date'],
            'zone_tag': row['zone_tag'],
            'dd_tier': row['dd_tier'],
            'position_ratio': row.get('position_ratio', np.nan),
            'trend_tag': row.get('trend_tag', ''),
            'golden_trend_t0': row.get('golden_trend_t0', np.nan),
            'support_score': row.get('support_score', np.nan),
            'ma_zone': row.get('ma_zone', ''),
        })

    for stock in stock_groups:
        stock_groups[stock].sort(key=lambda s: pd.Timestamp(s['t0_date']))

    n_stocks = len(stock_groups)
    n_cpus = min(cpu_count(), n_stocks, 31)

    baseline_cfg = [('none', False)]
    worker_args = [
        (stock, sigs, param_lookup, fallback_param, None, cooldown_days,
         'none', False, baseline_cfg)
        for stock, sigs in stock_groups.items()
    ]

    print(f"    回测: {len(valid)} 信号, {n_stocks} 只股票, {n_cpus} 进程...")
    t0 = time.time()
    with Pool(processes=n_cpus) as pool:
        chunk_results = pool.map(_process_stock_signals, worker_args)
    elapsed = time.time() - t0
    print(f"    回测完成: {elapsed:.1f}s")

    all_recs = []
    for stock_res in chunk_results:
        for rec in stock_res:
            rec.pop('_ind_config', None)
            all_recs.append(rec)

    rdf = pd.DataFrame(all_recs)
    sim = rdf[rdf['status'] == 'simulated'].copy()
    print(f"    成交信号: {len(sim)} 笔")

    if sim.empty:
        print("    无成交信号，跳过窗口分析")
        return

    rows = []
    for i, (_, trade) in enumerate(sim.iterrows()):
        if (i + 1) % 50 == 0:
            print(f"    处理窗口 {i + 1}/{len(sim)} ...")

        stock = trade['stock_code']
        t0_date = pd.Timestamp(trade['t0_date'])
        entry_day = int(trade['entry_day_idx']) if not pd.isna(trade['entry_day_idx']) else 0
        exit_day = int(trade['exit_day_idx']) if not pd.isna(trade['exit_day_idx']) else 0

        pre_60m = _load_pre_60m(stock, t0_date)
        fwd_60m = _load_forward_60m(stock, t0_date)

        if (pre_60m is None or pre_60m.empty or len(pre_60m) < 30
                or fwd_60m is None or fwd_60m.empty):
            continue

        combined_60m = pd.concat([pre_60m, fwd_60m])
        h60_c = combined_60m['close'].astype(float)
        h60_h = combined_60m['high'].astype(float)
        n_pre_60 = len(pre_60m)

        fwd_h60_c = h60_c.iloc[n_pre_60:].reset_index(drop=True)
        fwd_h60_h = h60_h.iloc[n_pre_60:].reset_index(drop=True)
        fwd_h60_l = combined_60m['low'].astype(float).iloc[n_pre_60:].reset_index(drop=True)

        rsi_periods = (6, 12, 24)
        fwd_rsi = []
        for p in rsi_periods:
            rsi_all = calculate_rsi(combined_60m, periods=p)
            fwd_rsi.append(rsi_all.iloc[n_pre_60:].reset_index(drop=True))

        k_all, d_all, j_all = calculate_kdj(combined_60m, n=27, k_period=3, d_period=3)
        fwd_k = k_all.iloc[n_pre_60:].reset_index(drop=True)
        fwd_d = d_all.iloc[n_pre_60:].reset_index(drop=True)
        fwd_j = j_all.iloc[n_pre_60:].reset_index(drop=True)

        dif_all, dea_all = calculate_macd(combined_60m, fast=8, slow=21, signal=6)
        hist_all = (dif_all - dea_all) * 2
        fwd_dif = dif_all.iloc[n_pre_60:].reset_index(drop=True)
        fwd_dea = dea_all.iloc[n_pre_60:].reset_index(drop=True)
        fwd_hist = hist_all.iloc[n_pre_60:].reset_index(drop=True)

        hold_start = max(0, entry_day * 4)
        hold_end = min(len(fwd_h60_h), (exit_day + 1) * 4)
        if hold_start >= hold_end:
            hold_end = min(len(fwd_h60_h), hold_start + 40)

        if hold_start >= len(fwd_h60_h):
            continue

        hold_highs = fwd_h60_h.iloc[hold_start:hold_end].astype(float)
        if hold_highs.empty:
            continue
        peak_local = int(hold_highs.idxmax())
        peak_bar_idx = hold_start + peak_local

        window_start = max(0, peak_bar_idx - 5)
        window_end = min(len(fwd_h60_c), peak_bar_idx + 6)

        for bar_pos in range(window_start, window_end):
            offset = bar_pos - peak_bar_idx
            c = float(fwd_h60_c.iloc[bar_pos]) if bar_pos < len(fwd_h60_c) else np.nan
            h = float(fwd_h60_h.iloc[bar_pos]) if bar_pos < len(fwd_h60_h) else np.nan
            l = float(fwd_h60_l.iloc[bar_pos]) if bar_pos < len(fwd_h60_l) else np.nan

            ma7_v = float(h60_c.rolling(7).mean().iloc[n_pre_60 + bar_pos]) \
                if n_pre_60 + bar_pos < len(h60_c) else np.nan
            ma30_v = float(h60_c.rolling(30).mean().iloc[n_pre_60 + bar_pos]) \
                if n_pre_60 + bar_pos < len(h60_c) else np.nan

            r6 = float(fwd_rsi[0].iloc[bar_pos]) if bar_pos < len(fwd_rsi[0]) else np.nan
            r12 = float(fwd_rsi[1].iloc[bar_pos]) if bar_pos < len(fwd_rsi[1]) else np.nan
            r24 = float(fwd_rsi[2].iloc[bar_pos]) if bar_pos < len(fwd_rsi[2]) else np.nan

            kv = float(fwd_k.iloc[bar_pos]) if bar_pos < len(fwd_k) else np.nan
            dv = float(fwd_d.iloc[bar_pos]) if bar_pos < len(fwd_d) else np.nan
            jv = float(fwd_j.iloc[bar_pos]) if bar_pos < len(fwd_j) else np.nan

            dif_v = float(fwd_dif.iloc[bar_pos]) if bar_pos < len(fwd_dif) else np.nan
            dea_v = float(fwd_dea.iloc[bar_pos]) if bar_pos < len(fwd_dea) else np.nan
            hist_v = float(fwd_hist.iloc[bar_pos]) if bar_pos < len(fwd_hist) else np.nan

            rsi_aligned = (not any(np.isnan(x) for x in [r6, r12, r24])) and r6 > r12 > r24
            j_above_d = (not any(np.isnan(x) for x in [jv, dv])) and jv > dv

            rows.append({
                'signal_idx': trade.get('signal_idx', np.nan),
                'stock_code': stock,
                't0_date': t0_date,
                'zone_tag': trade.get('zone_tag', ''),
                'entry_day': entry_day,
                'exit_day': exit_day,
                'entry_price': trade.get('actual_entry_price', np.nan),
                'pnl': trade.get('pnl', np.nan),
                'exit_reason': trade.get('exit_reason', ''),
                'bar_offset': offset,
                'bar_idx': bar_pos,
                'is_peak': offset == 0,
                'bar_close': round(c, 4) if not np.isnan(c) else np.nan,
                'bar_high': round(h, 4) if not np.isnan(h) else np.nan,
                'bar_low': round(l, 4) if not np.isnan(l) else np.nan,
                'ma7': round(ma7_v, 4) if not np.isnan(ma7_v) else np.nan,
                'ma30': round(ma30_v, 4) if not np.isnan(ma30_v) else np.nan,
                'rsi6': round(r6, 2) if not np.isnan(r6) else np.nan,
                'rsi12': round(r12, 2) if not np.isnan(r12) else np.nan,
                'rsi24': round(r24, 2) if not np.isnan(r24) else np.nan,
                'rsi_aligned': rsi_aligned,
                'kdj_k': round(kv, 2) if not np.isnan(kv) else np.nan,
                'kdj_d': round(dv, 2) if not np.isnan(dv) else np.nan,
                'kdj_j': round(jv, 2) if not np.isnan(jv) else np.nan,
                'j_above_d': j_above_d,
                'macd_dif': round(dif_v, 4) if not np.isnan(dif_v) else np.nan,
                'macd_dea': round(dea_v, 4) if not np.isnan(dea_v) else np.nan,
                'macd_hist': round(hist_v, 4) if not np.isnan(hist_v) else np.nan,
            })

    window_df = pd.DataFrame(rows)
    out_csv = os.path.join(DOC_DIR, 'indicator_window_v5.csv')
    window_df.to_csv(out_csv, index=False)
    print(f"    已写入 {out_csv}")
    print(f"    共 {len(rows)} 行窗口数据, {len(sim)} 笔交易")

    ind_cols = {
        'RSI6': 'rsi6', 'RSI12': 'rsi12', 'RSI24': 'rsi24',
        'K': 'kdj_k', 'D': 'kdj_d', 'J': 'kdj_j',
        'MACD_hist': 'macd_hist',
    }

    print(f"\n    {'=' * 90}")
    print(f"    价格高点 (T=0) 前后指标中位数趋势")
    print(f"    {'=' * 90}")
    print(f"    {'Offset':>7} {'RSI6':>7} {'RSI12':>7} {'RSI24':>7} "
          f"{'K':>7} {'D':>7} {'J':>7} {'MACD_H':>8}")
    print(f"    {'-' * 62}")

    for offset in range(-5, 6):
        sub = window_df[window_df['bar_offset'] == offset]
        vals = []
        for col in ind_cols.values():
            v = sub[col].dropna().median() if not sub[col].dropna().empty else np.nan
            vals.append(v)
        peak_mark = ' <--peak' if offset == 0 else ''
        val_str = ' '.join(f'{v:>7.1f}' if not np.isnan(v) else f'{"nan":>7}' for v in vals)
        print(f"    {offset:>7} {val_str}{peak_mark}")

    print(f"\n    盈利 vs 亏损信号在 peak 前后的指标对比 (中位数):")
    print(f"    {'Offset':>7} {'Group':>6} {'RSI6':>7} {'J':>7} {'MACD_H':>8} {'Close':>8}")
    print(f"    {'-' * 48}")

    for offset in [-3, -2, -1, 0, 1, 2, 3]:
        sub = window_df[window_df['bar_offset'] == offset]
        for pnl_group, label in [(True, 'WIN'), (False, 'LOSS')]:
            if pnl_group:
                g = sub[sub['pnl'] > 0]
            else:
                g = sub[sub['pnl'] <= 0]
            if g.empty:
                continue
            r6 = g['rsi6'].dropna().median()
            jv = g['kdj_j'].dropna().median()
            mh = g['macd_hist'].dropna().median()
            cl = g['bar_close'].dropna().median()
            print(f"    {offset:>7} {label:>6} "
                  f"{'%7.1f' % r6 if not np.isnan(r6) else 'nan':>7} "
                  f"{'%7.1f' % jv if not np.isnan(jv) else 'nan':>7} "
                  f"{'%8.4f' % mh if not np.isnan(mh) else 'nan':>8} "
                  f"{'%8.2f' % cl if not np.isnan(cl) else 'nan':>8}")

    print(f"\n    peak 后各 bar 收益率 (相对 peak 价格):")
    peak_rows = window_df[window_df['is_peak'] == True].copy()
    if not peak_rows.empty:
        peak_prices = peak_rows.set_index('signal_idx')['bar_high']
        for offset in range(1, 6):
            after = window_df[window_df['bar_offset'] == offset].copy()
            if after.empty:
                continue
            merged = after.merge(peak_prices, left_on='signal_idx', right_index=True,
                                 suffixes=('', '_peak'))
            if 'bar_high_peak' in merged.columns and 'bar_close' in merged.columns:
                valid_m = merged.dropna(subset=['bar_close', 'bar_high_peak'])
                if not valid_m.empty:
                    rets = (valid_m['bar_close'] / valid_m['bar_high_peak'] - 1) * 100
                    print(f"    T+{offset}: median={rets.median():>+.2f}%, "
                          f"mean={rets.mean():>+.2f}%, n={len(rets)}")

    print(f"    {'=' * 90}")
    print(f"\n{'=' * 70}\n")


def run_indicator_param_scan(merged_df: pd.DataFrame, param_df: pd.DataFrame):
    """扫描 RSI/KDJ/MACD 参数组合，找到最优入场确认 + 退出配置。

    扫描维度:
      入场: RSI periods (4组) + KDJ n (3组) + MACD (1组) × mode (rsi/kdj/macd/any/none)
      退出: on/off × exit_mode (standard/2bar/peak)
    """
    print("\n  [Indicator Param Scan] 参数扫描回测...")

    valid = merged_df.dropna(
        subset=['max_drawdown', 'golden_trend_t0', 'last_close', 'position_ratio']
    ).copy()
    valid = valid[valid['zone_tag'] != 'unknown']
    if 'ma_zone' in valid.columns:
        valid = valid[valid['ma_zone'] != 'unknown']
    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'], bins=DRAWDOWN_BINS, labels=DRAWDOWN_LABELS,
    )
    param_lookup = _build_param_lookup(param_df)
    fallback_param = {'enabled': True, 'tp_mult': 2.0, 'sl_buffer': 0.03, 'entry_buffer': 0.03}
    cooldown_days = 5

    stock_groups = {}
    for idx, row in valid.iterrows():
        stock = row['stock_code']
        if stock not in stock_groups:
            stock_groups[stock] = []
        stock_groups[stock].append({
            'signal_idx': idx,
            't0_date': row['t0_date'],
            'zone_tag': row['zone_tag'],
            'dd_tier': row['dd_tier'],
            'position_ratio': row.get('position_ratio', np.nan),
            'trend_tag': row.get('trend_tag', ''),
            'golden_trend_t0': row.get('golden_trend_t0', np.nan),
            'support_score': row.get('support_score', np.nan),
            'ma_zone': row.get('ma_zone', ''),
        })

    for stock in stock_groups:
        stock_groups[stock].sort(key=lambda s: pd.Timestamp(s['t0_date']))

    rsi_param_options = [(4, 8, 16), (6, 12, 24), (8, 16, 32), (10, 20, 40)]
    kdj_n_options = [18, 27, 36]

    entry_configs = []
    for rp in rsi_param_options:
        entry_configs.append(('rsi', rp, 27))
    for kn in kdj_n_options:
        entry_configs.append(('kdj', (6, 12, 24), kn))
    entry_configs.append(('macd', (6, 12, 24), 27))

    exit_options = [(False, 'standard'), (True, 'standard'), (True, '2bar'), (True, 'peak')]

    all_configs = []
    for mode, rsi_p, kdj_n in entry_configs:
        for exit_on, exit_m in exit_options:
            all_configs.append((mode, exit_on, rsi_p, kdj_n, exit_m))

    baseline_cfg = ('none', False, (6, 12, 24), 27, 'standard')
    if baseline_cfg not in all_configs:
        all_configs.insert(0, baseline_cfg)

    print(f"    共 {len(all_configs)} 种参数组合")

    n_stocks = len(stock_groups)
    n_cpus = min(cpu_count(), n_stocks, 31)

    results_by_config = {cfg: [] for cfg in all_configs}

    for cfg in all_configs:
        cfg_list = [cfg]
        worker_args = [
            (stock, sigs, param_lookup, fallback_param, None, cooldown_days,
             'none', False, cfg_list)
            for stock, sigs in stock_groups.items()
        ]

        t0 = time.time()
        with Pool(processes=n_cpus) as pool:
            chunk_results = pool.map(_process_stock_signals, worker_args)
        elapsed = time.time() - t0

        for stock_res in chunk_results:
            for rec in stock_res:
                rec.pop('_ind_config', None)
                results_by_config[cfg].append(rec)

        mode, exit_on, rsi_p, kdj_n, exit_m = cfg
        rdf = pd.DataFrame(results_by_config[cfg])
        sim = rdf[rdf['status'] == 'simulated']
        pnl = sim['pnl'].dropna()
        s = _calc_stats(pnl)
        print(f"    [{elapsed:.1f}s] {mode:>5} rsi={rsi_p} kdj_n={kdj_n:>2} "
              f"exit={exit_on}/{exit_m:>8}: "
              f"n={s['n']:>4} WR={s['wr']:.1%} PF={s['pf']:.2f}")

    print(f"\n    {'=' * 110}")
    print(f"    参数扫描结果 (按 PF 排序 Top-10)")
    print(f"    {'=' * 110}")
    print(f"    {'#':>3} {'mode':>5} {'RSI_periods':>14} {'KDJ_n':>5} {'exit':>5} "
          f"{'exit_mode':>9} {'trades':>6} {'WR':>7} {'PF':>6} "
          f"{'avg':>7} {'median':>7} {'max_loss':>8}")
    print(f"    {'-' * 100}")

    all_stats = []
    for cfg in all_configs:
        rdf = pd.DataFrame(results_by_config[cfg])
        sim = rdf[rdf['status'] == 'simulated']
        pnl = sim['pnl'].dropna()
        s = _calc_stats(pnl)
        mode, exit_on, rsi_p, kdj_n, exit_m = cfg
        all_stats.append({
            'cfg': cfg, 'mode': mode, 'rsi_periods': str(rsi_p),
            'kdj_n': kdj_n, 'exit_on': exit_on, 'exit_mode': exit_m,
            **s,
        })

    stats_df = pd.DataFrame(all_stats)
    if not stats_df.empty and stats_df['pf'].max() > 0:
        top_pf = stats_df.nlargest(10, 'pf')
        for rank, (_, row) in enumerate(top_pf.iterrows(), 1):
            print(f"    {rank:>3} {row['mode']:>5} {row['rsi_periods']:>14} "
                  f"{int(row['kdj_n']):>5} "
                  f"{'ON' if row['exit_on'] else 'OFF':>5} {row['exit_mode']:>9} "
                  f"{int(row['n']):>6} {row['wr']:.1%} "
                  f"{row['pf']:>6.2f} {row['avg']:.2%} "
                  f"{row['median']:.2%} {row['max_loss']:.2%}")

    print(f"\n    按 trades × PF 排序 Top-10 (平衡质量与数量):")
    print(f"    {'-' * 100}")
    if not stats_df.empty:
        stats_df['score'] = stats_df['n'] * stats_df['pf']
        top_score = stats_df.nlargest(10, 'score')
        for rank, (_, row) in enumerate(top_score.iterrows(), 1):
            print(f"    {rank:>3} {row['mode']:>5} {row['rsi_periods']:>14} "
                  f"{int(row['kdj_n']):>5} "
                  f"{'ON' if row['exit_on'] else 'OFF':>5} {row['exit_mode']:>9} "
                  f"{int(row['n']):>6} {row['wr']:.1%} "
                  f"{row['pf']:>6.2f} {row['avg']:.2%} "
                  f"{row['median']:.2%} (score={row['score']:.0f})")

    if not stats_df.empty:
        best_pf_row = stats_df.loc[stats_df['pf'].idxmax()]
        print(f"\n    PF 最优: {best_pf_row['mode']} rsi={best_pf_row['rsi_periods']} "
              f"kdj_n={int(best_pf_row['kdj_n'])} "
              f"exit={'ON' if best_pf_row['exit_on'] else 'OFF'}/{best_pf_row['exit_mode']} "
              f"→ PF={best_pf_row['pf']:.2f} WR={best_pf_row['wr']:.1%} "
              f"n={int(best_pf_row['n'])}")

        best_score_row = stats_df.loc[stats_df['score'].idxmax()]
        print(f"    综合最优: {best_score_row['mode']} rsi={best_score_row['rsi_periods']} "
              f"kdj_n={int(best_score_row['kdj_n'])} "
              f"exit={'ON' if best_score_row['exit_on'] else 'OFF'}/{best_score_row['exit_mode']} "
              f"→ PF={best_score_row['pf']:.2f} WR={best_score_row['wr']:.1%} "
              f"n={int(best_score_row['n'])} score={best_score_row['score']:.0f}")

    print(f"    {'=' * 110}")
    print(f"\n{'=' * 70}\n")


def run_best_config_verification(merged_df: pd.DataFrame, param_df: pd.DataFrame):
    """用最佳配置 RSI(10,20,40) + exit=ON/standard 进行验证回测，输出详细报告。

    报告内容:
      - 整体指标 (与 baseline 对比)
      - Zone 细分
      - 退出原因分析 (含平均PnL)
      - 入场方式分布
      - 持仓天数分布
      - PnL 分布 (分桶统计)
      - 按日期月度表现
      - 连续亏损分析
      - 稳定性检查 (前半/后半)
    """
    print("\n  [Best Config Verification] 最佳配置验证回测...")
    print(f"    配置: RSI(10,20,40) + exit=ON + standard 退出")

    valid = merged_df.dropna(
        subset=['max_drawdown', 'golden_trend_t0', 'last_close', 'position_ratio']
    ).copy()
    valid = valid[valid['zone_tag'] != 'unknown']
    if 'ma_zone' in valid.columns:
        valid = valid[valid['ma_zone'] != 'unknown']
    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'], bins=DRAWDOWN_BINS, labels=DRAWDOWN_LABELS,
    )
    param_lookup = _build_param_lookup(param_df)
    fallback_param = {'enabled': True, 'tp_mult': 2.0, 'sl_buffer': 0.03, 'entry_buffer': 0.03}
    cooldown_days = 5

    stock_groups = {}
    for idx, row in valid.iterrows():
        stock = row['stock_code']
        if stock not in stock_groups:
            stock_groups[stock] = []
        stock_groups[stock].append({
            'signal_idx': idx,
            't0_date': row['t0_date'],
            'zone_tag': row['zone_tag'],
            'dd_tier': row['dd_tier'],
            'position_ratio': row.get('position_ratio', np.nan),
            'trend_tag': row.get('trend_tag', ''),
            'golden_trend_t0': row.get('golden_trend_t0', np.nan),
            'support_score': row.get('support_score', np.nan),
            'ma_zone': row.get('ma_zone', ''),
        })

    for stock in stock_groups:
        stock_groups[stock].sort(key=lambda s: pd.Timestamp(s['t0_date']))

    n_stocks = len(stock_groups)
    n_cpus = min(cpu_count(), n_stocks, 31)

    best_cfg = [('rsi', True, (10, 20, 40), 27, 'standard')]
    worker_args = [
        (stock, sigs, param_lookup, fallback_param, None, cooldown_days,
         'rsi', True, best_cfg)
        for stock, sigs in stock_groups.items()
    ]

    print(f"    {len(valid)} 信号, {n_stocks} 只股票, {n_cpus} 进程并行...")
    t0 = time.time()
    with Pool(processes=n_cpus) as pool:
        chunk_results = pool.map(_process_stock_signals, worker_args)
    elapsed = time.time() - t0

    all_recs = []
    for stock_res in chunk_results:
        for rec in stock_res:
            rec.pop('_ind_config', None)
            all_recs.append(rec)

    rdf = pd.DataFrame(all_recs)
    sim = rdf[rdf['status'] == 'simulated'].copy()
    pnl = sim['pnl'].dropna()
    s = _calc_stats(pnl)

    print(f"    回测完成: {elapsed:.1f}s")

    # ── 保存结果 ──
    out_csv = os.path.join(DOC_DIR, 'best_config_verification_v5.csv')
    sim.to_csv(out_csv, index=False)
    print(f"    已保存 {out_csv}")

    # ══════════════════════════════════════════════════════════════════
    # 一、整体表现
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print(f"  最佳配置验证报告: RSI(10,20,40) + exit=ON/standard")
    print(f"{'=' * 80}")

    print(f"\n  一、整体表现")
    print(f"  {'─' * 55}")
    print(f"    总信号数:         {len(rdf)}")
    print(f"    成交笔数:         {s['n']}")
    print(f"    入场率:           {len(sim) / len(rdf):.1%}")
    print(f"    胜率 (WR):        {s['wr']:.1%}")
    print(f"    盈利因子 (PF):    {s['pf']:.2f}")
    print(f"    平均收益:         {s['avg']:.2%}")
    print(f"    中位收益:         {s['median']:.2%}")
    print(f"    最大盈利:         {s['max_win']:.2%}")
    print(f"    最大亏损:         {s['max_loss']:.2%}")

    # ── 对比 baseline ──
    baseline_pnl = rdf[rdf['status'] == 'simulated']['pnl'].dropna()
    print(f"\n    对比基线 (none + exit=OFF):")
    print(f"    {'指标':<16} {'基线':>10} {'最佳配置':>10} {'变化':>10}")
    print(f"    {'─' * 48}")
    bl_wr, bl_pf = 46.4, 1.30
    bl_avg, bl_med = 1.39, -2.32
    bl_n = 647
    print(f"    {'交易数':<16} {bl_n:>10} {s['n']:>10} {s['n'] - bl_n:>+10}")
    print(f"    {'胜率':<16} {bl_wr:>9.1f}% {s['wr'] * 100:>9.1f}% {s['wr'] * 100 - bl_wr:>+9.1f}%")
    print(f"    {'盈利因子':<14} {bl_pf:>10.2f} {s['pf']:>10.2f} {s['pf'] - bl_pf:>+10.2f}")
    print(f"    {'平均收益':<14} {bl_avg:>9.2f}% {s['avg'] * 100:>9.2f}% {(s['avg'] - bl_avg / 100) * 100:>+9.2f}%")
    print(f"    {'中位收益':<14} {bl_med:>9.2f}% {s['median'] * 100:>9.2f}% {(s['median'] - bl_med / 100) * 100:>+9.2f}%")

    # ══════════════════════════════════════════════════════════════════
    # 二、Zone 细分
    # ══════════════════════════════════════════════════════════════════
    print(f"\n  二、Zone 细分")
    print(f"  {'─' * 75}")
    print(f"    {'Zone':<18} {'trades':>7} {'WR':>8} {'PF':>6} "
          f"{'avg':>8} {'median':>8} {'max_loss':>9}")
    print(f"    {'─' * 68}")

    for z in ZONE_ORDER:
        sub = sim[sim['zone_tag'] == z]['pnl'].dropna()
        if len(sub) == 0:
            print(f"    {z:<18} {'0':>7}")
            continue
        zs = _calc_stats(sub)
        print(f"    {z:<18} {zs['n']:>7} {zs['wr']:>7.1%} {zs['pf']:>6.2f} "
              f"{zs['avg']:>7.2%} {zs['median']:>7.2%} {zs['max_loss']:>8.2%}")

    # ══════════════════════════════════════════════════════════════════
    # 三、退出原因分析
    # ══════════════════════════════════════════════════════════════════
    print(f"\n  三、退出原因分析")
    print(f"  {'─' * 75}")
    print(f"    {'退出原因':<22} {'笔数':>6} {'占比':>6} {'avg PnL':>9} "
          f"{'median':>8} {'WR':>8}")
    print(f"    {'─' * 62}")

    exit_groups = sim.groupby('exit_reason')['pnl']
    for reason, group in sorted(exit_groups, key=lambda x: -len(x[1])):
        pnl_g = group.dropna()
        if pnl_g.empty:
            continue
        es = _calc_stats(pnl_g)
        pct = len(pnl_g) / len(sim) * 100
        print(f"    {reason:<22} {es['n']:>6} {pct:>5.1f}% {es['avg']:>8.2%} "
              f"{es['median']:>7.2%} {es['wr']:>7.1%}")

    # ══════════════════════════════════════════════════════════════════
    # 四、入场方式
    # ══════════════════════════════════════════════════════════════════
    if 'entry_type' in sim.columns:
        print(f"\n  四、入场方式分布")
        print(f"  {'─' * 55}")
        for et in ['60m', 'daily']:
            sub = sim[sim['entry_type'] == et]['pnl'].dropna()
            if len(sub) == 0:
                print(f"    {et}: 0 笔")
                continue
            es = _calc_stats(sub)
            print(f"    {et}: {es['n']} 笔, WR={es['wr']:.1%}, PF={es['pf']:.2f}, "
                  f"avg={es['avg']:.2%}")

    # ══════════════════════════════════════════════════════════════════
    # 五、持仓天数分布
    # ══════════════════════════════════════════════════════════════════
    if 'entry_day_idx' in sim.columns and 'exit_day_idx' in sim.columns:
        print(f"\n  五、持仓天数分布")
        print(f"  {'─' * 55}")
        sim_valid = sim.dropna(subset=['entry_day_idx', 'exit_day_idx'])
        sim_valid = sim_valid.copy()
        sim_valid['hold_days'] = (sim_valid['exit_day_idx'].astype(int)
                                  - sim_valid['entry_day_idx'].astype(int))
        for bucket, label in [(range(0, 2), '0-1天'), (range(2, 4), '2-3天'),
                              (range(4, 8), '4-7天'), (range(8, 12), '8-11天'),
                              (range(12, 30), '12天+')]:
            sub = sim_valid[sim_valid['hold_days'].isin(bucket)]['pnl'].dropna()
            if len(sub) == 0:
                continue
            es = _calc_stats(sub)
            print(f"    {label:>8}: {es['n']:>4} 笔, WR={es['wr']:.1%}, "
                  f"PF={es['pf']:.2f}, avg={es['avg']:.2%}")

    # ══════════════════════════════════════════════════════════════════
    # 六、PnL 分布
    # ══════════════════════════════════════════════════════════════════
    print(f"\n  六、PnL 分布")
    print(f"  {'─' * 55}")
    bins = [(-100, -10), (-10, -5), (-5, -2), (-2, 0), (0, 2), (2, 5),
            (5, 10), (10, 15), (15, 100)]
    labels_b = ['<-10%', '-10~-5%', '-5~-2%', '-2~0%', '0~2%', '2~5%',
                '5~10%', '10~15%', '>15%']
    pnl_pct = pnl * 100
    for (lo, hi), label in zip(bins, labels_b):
        cnt = ((pnl_pct >= lo) & (pnl_pct < hi)).sum()
        bar = '█' * max(1, cnt // 5)
        print(f"    {label:>8}: {cnt:>4} 笔 ({cnt / len(pnl) * 100:>5.1f}%) {bar}")

    # ══════════════════════════════════════════════════════════════════
    # 七、按日期月度表现
    # ══════════════════════════════════════════════════════════════════
    if 't0_date' in sim.columns:
        print(f"\n  七、按月度表现")
        print(f"  {'─' * 65}")
        sim_monthly = sim.copy()
        sim_monthly['month'] = pd.to_datetime(sim_monthly['t0_date']).dt.to_period('M')
        print(f"    {'月份':<12} {'trades':>7} {'WR':>8} {'PF':>6} {'avg':>8} {'cum PnL':>9}")
        print(f"    {'─' * 54}")
        cum_pnl = 0.0
        for month, group in sim_monthly.groupby('month'):
            mp = group['pnl'].dropna()
            if mp.empty:
                continue
            ms = _calc_stats(mp)
            cum_pnl += float(mp.sum())
            print(f"    {str(month):<12} {ms['n']:>7} {ms['wr']:>7.1%} {ms['pf']:>6.2f} "
                  f"{ms['avg']:>7.2%} {cum_pnl * 100:>+8.1f}%")

    # ══════════════════════════════════════════════════════════════════
    # 八、连续亏损分析
    # ══════════════════════════════════════════════════════════════════
    print(f"\n  八、连续亏损分析")
    print(f"  {'─' * 45}")
    pnl_list = (pnl > 0).astype(int).tolist()
    max_consec_loss = 0
    curr_loss = 0
    loss_streaks = []
    for w in pnl_list:
        if w == 0:
            curr_loss += 1
            max_consec_loss = max(max_consec_loss, curr_loss)
        else:
            if curr_loss > 0:
                loss_streaks.append(curr_loss)
            curr_loss = 0
    if curr_loss > 0:
        loss_streaks.append(curr_loss)

    print(f"    最大连续亏损: {max_consec_loss} 笔")
    if loss_streaks:
        from collections import Counter
        streak_counts = Counter(loss_streaks)
        print(f"    连续亏损分布:")
        for streak_len in sorted(streak_counts.keys()):
            print(f"      {streak_len}连败: {streak_counts[streak_len]} 次")

    # ══════════════════════════════════════════════════════════════════
    # 九、稳定性检查
    # ══════════════════════════════════════════════════════════════════
    print(f"\n  九、稳定性检查 (前半 / 后半)")
    print(f"  {'─' * 55}")
    half = len(pnl) // 2
    if half > 10:
        first_half = pnl.iloc[:half]
        second_half = pnl.iloc[half:]
        s1 = _calc_stats(first_half)
        s2 = _calc_stats(second_half)
        print(f"    {'期间':<10} {'trades':>7} {'WR':>8} {'PF':>6} {'avg':>8}")
        print(f"    {'─' * 42}")
        print(f"    {'前半':<10} {s1['n']:>7} {s1['wr']:>7.1%} {s1['pf']:>6.2f} {s1['avg']:>7.2%}")
        print(f"    {'后半':<10} {s2['n']:>7} {s2['wr']:>7.1%} {s2['pf']:>6.2f} {s2['avg']:>7.2%}")

        pf_diff = abs(s1['pf'] - s2['pf']) / max(s1['pf'], s2['pf'], 0.01)
        if pf_diff < 0.3:
            print(f"    ✓ 前后半 PF 差异 {pf_diff:.0%} — 策略稳定")
        elif pf_diff < 0.5:
            print(f"    ⚠ 前后半 PF 差异 {pf_diff:.0%} — 存在一定漂移")
        else:
            print(f"    ✗ 前后半 PF 差异 {pf_diff:.0%} — 策略不稳定，需关注")

    print(f"\n{'=' * 80}")
    print(f"  验证完成")
    print(f"{'=' * 80}\n")

    return sim


def step3_gt_backtest(merged_df: pd.DataFrame, param_df: pd.DataFrame) -> pd.DataFrame:
    print("\n  [Step 3] GT 状态机回测...")

    valid = merged_df.dropna(
        subset=['max_drawdown', 'golden_trend_t0', 'last_close', 'position_ratio']
    ).copy()
    valid = valid[valid['zone_tag'] != 'unknown']

    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'],
        bins=DRAWDOWN_BINS,
        labels=DRAWDOWN_LABELS,
    )

    param_lookup = _build_param_lookup(param_df)

    fallback_param = {
        'enabled': True,
        'tp_mult': 2.0,
        'sl_buffer': 0.03,
        'entry_buffer': 0.03,
    }

    cooldown_days = 5

    # --- 按股票分组，准备并行处理 ---
    stock_groups = {}
    for idx, row in valid.iterrows():
        stock = row['stock_code']
        if stock not in stock_groups:
            stock_groups[stock] = []
        stock_groups[stock].append({
            'signal_idx': idx,
            't0_date': row['t0_date'],
            'zone_tag': row['zone_tag'],
            'dd_tier': row['dd_tier'],
            'position_ratio': row.get('position_ratio', np.nan),
            'trend_tag': row.get('trend_tag', ''),
            'golden_trend_t0': row.get('golden_trend_t0', np.nan),
            'support_score': row.get('support_score', np.nan),
            'ma_zone': row.get('ma_zone', ''),
        })

    for stock in stock_groups:
        stock_groups[stock].sort(key=lambda s: pd.Timestamp(s['t0_date']))

    n_stocks = len(stock_groups)
    n_cpus = min(cpu_count(), n_stocks, 31)
    print(f"    {len(valid)} 信号, {n_stocks} 只股票, {n_cpus} 进程并行...")

    worker_args = [
        (stock, sigs, param_lookup, fallback_param, None, cooldown_days)
        for stock, sigs in stock_groups.items()
    ]

    t0 = time.time()
    with Pool(processes=n_cpus) as pool:
        chunk_results = pool.map(_process_stock_signals, worker_args)
    elapsed = time.time() - t0

    results = []
    n_ok = n_skip = n_cooldown = 0
    for stock_res in chunk_results:
        for rec in stock_res:
            results.append(rec)
            status = rec.get('status', '')
            if status == 'simulated':
                n_ok += 1
            elif status == 'cooldown':
                n_cooldown += 1
            else:
                n_skip += 1

    result_df = pd.DataFrame(results)
    print(f"    并行完成: {n_ok} 成交, {n_skip} 跳过, {n_cooldown} 冷却期跳过, 耗时 {elapsed:.1f}s")

    result_df.to_csv(BACKTEST_GT_CSV, index=False, encoding='utf-8-sig')
    print(f"    已保存 {BACKTEST_GT_CSV}")
    return result_df


# ---------------------------------------------------------------------------
# Step 4: 对比报告
# ---------------------------------------------------------------------------
def _pct_fmt(val):
    if pd.isna(val):
        return '-'
    return f'{val:.2%}'


def _f4(val):
    if pd.isna(val):
        return '-'
    return f'{val:.4f}'


def _calc_stats(pnl_series):
    if len(pnl_series) == 0:
        return {'n': 0, 'avg': 0, 'median': 0, 'wr': 0, 'pf': 0,
                'max_win': 0, 'max_loss': 0}
    win = (pnl_series > 0).sum()
    gp = float(pnl_series[pnl_series > 0].sum()) if win > 0 else 0
    gl = abs(float(pnl_series[pnl_series < 0].sum())) if (pnl_series < 0).any() else 0.001
    return {
        'n': len(pnl_series),
        'avg': float(pnl_series.mean()),
        'median': float(pnl_series.median()),
        'wr': win / len(pnl_series),
        'pf': gp / gl if gl > 0 else 99.99,
        'max_win': float(pnl_series.max()),
        'max_loss': float(pnl_series.min()),
    }


def generate_gt_comparison_report(gt_bt_df: pd.DataFrame, v5_bt_df: pd.DataFrame):
    lines = []
    lines.append("# GT 原生状态机回测对比报告\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append("")

    # ---- 一、整体对比 ----
    gt_sim = gt_bt_df[gt_bt_df['status'] == 'simulated']
    v5_sim = v5_bt_df[v5_bt_df['status'] == 'simulated']
    gt_pnl = gt_sim['pnl'].dropna()
    v5_pnl = v5_sim['pnl'].dropna()
    gt_s = _calc_stats(gt_pnl)
    v5_s = _calc_stats(v5_pnl)

    gt_entry_rate = len(gt_sim) / len(gt_bt_df) if len(gt_bt_df) > 0 else 0
    v5_entry_rate = len(v5_sim) / len(v5_bt_df) if len(v5_bt_df) > 0 else 0

    lines.append("## 一、整体对比\n")
    lines.append("| 指标 | v5 (固定%) | v5_gt (GT原生) | 差异 |")
    lines.append("|------|-----------|---------------|------|")
    lines.append(f"| 总信号 | {len(v5_bt_df)} | {len(gt_bt_df)} | |")
    lines.append(f"| 入场成交 | {v5_s['n']} | {gt_s['n']} | {gt_s['n'] - v5_s['n']:+d} |")
    lines.append(f"| 入场率 | {_pct_fmt(v5_entry_rate)} | {_pct_fmt(gt_entry_rate)} | "
                 f"{gt_entry_rate - v5_entry_rate:+.1%} |")
    lines.append(f"| 胜率 | {_pct_fmt(v5_s['wr'])} | {_pct_fmt(gt_s['wr'])} | "
                 f"{gt_s['wr'] - v5_s['wr']:+.1%} |")
    lines.append(f"| 盈利因子 | {v5_s['pf']:.2f} | {gt_s['pf']:.2f} | "
                 f"{gt_s['pf'] - v5_s['pf']:+.2f} |")
    lines.append(f"| 平均盈亏 | {_pct_fmt(v5_s['avg'])} | {_pct_fmt(gt_s['avg'])} | "
                 f"{gt_s['avg'] - v5_s['avg']:+.2%} |")
    lines.append(f"| 中位数 | {_pct_fmt(v5_s['median'])} | {_pct_fmt(gt_s['median'])} | "
                 f"{gt_s['median'] - v5_s['median']:+.2%} |")
    lines.append(f"| 最大盈利 | {_pct_fmt(v5_s['max_win'])} | {_pct_fmt(gt_s['max_win'])} | |")
    lines.append(f"| 最大亏损 | {_pct_fmt(v5_s['max_loss'])} | {_pct_fmt(gt_s['max_loss'])} | |")
    lines.append("")

    # ---- 二、按 Zone 对比 ----
    lines.append("## 二、按 Zone 对比\n")
    lines.append("| Zone | v5 交易 | v5 胜率 | v5 PF | v5_gt 交易 | v5_gt 胜率 | v5_gt PF | 胜率低差异 | PF 差异 |")
    lines.append("|------|--------|--------|------|-----------|-----------|---------|----------|---------|")
    for zone in ZONE_ORDER:
        v5_sub = v5_sim[v5_sim['zone_tag'] == zone]['pnl'].dropna()
        gt_sub = gt_sim[gt_sim['zone_tag'] == zone]['pnl'].dropna()
        vs = _calc_stats(v5_sub)
        gs = _calc_stats(gt_sub)
        lines.append(
            f"| {zone} | {vs['n']} | {_pct_fmt(vs['wr'])} | {vs['pf']:.2f} "
            f"| {gs['n']} | {_pct_fmt(gs['wr'])} | {gs['pf']:.2f} "
            f"| {gs['wr'] - vs['wr']:+.1%} | {gs['pf'] - vs['pf']:+.2f} |"
        )
    lines.append("")

    # ---- 三、动态入场分析 ----
    lines.append("## 三、动态入场分析\n")

    gt_with_entry = gt_sim.dropna(subset=['entry_day_idx'])
    if len(gt_with_entry) > 0:
        lines.append("### 入场日分布 (T+N)\n")
        lines.append("| 入场日 | 交易数 | 占比 | avg PnL | 胜率 |")
        lines.append("|--------|--------|------|---------|------|")
        for d_start in [0, 3, 6, 10, 15, 20]:
            d_end = min(d_start + 3, FUTURE_DAYS)
            sub = gt_with_entry[
                (gt_with_entry['entry_day_idx'] >= d_start) &
                (gt_with_entry['entry_day_idx'] < d_end)
            ]
            if len(sub) == 0:
                continue
            s = _calc_stats(sub['pnl'].dropna())
            lines.append(f"| T+{d_start}~{d_end-1} | {s['n']} "
                         f"| {s['n']/len(gt_with_entry):.1%} "
                         f"| {_pct_fmt(s['avg'])} | {_pct_fmt(s['wr'])} |")
        lines.append("")

        gap_data = gt_with_entry['gap_at_entry'].dropna()
        if len(gap_data) > 0:
            lines.append("### 入场时 gap 分布 (entry_price 离 GT 的距离)\n")
            lines.append(f"- 中位 gap: {_pct_fmt(gap_data.median())}")
            lines.append(f"- 均值 gap: {_pct_fmt(gap_data.mean())}")
            lines.append(f"- min/max: {_pct_fmt(gap_data.min())} / {_pct_fmt(gap_data.max())}")
            lines.append("")

        ch_data = gt_with_entry.dropna(subset=['channel_at_entry'])
        if len(ch_data) > 0:
            ch_pct = ch_data['channel_at_entry'] / ch_data['actual_entry_price']
            lines.append("### 入场时真实通道宽度 (channel_at_entry / entry_price)\n")
            lines.append(f"- 中位通道比: {_pct_fmt(ch_pct.median())}")
            lines.append(f"- 均值通道比: {_pct_fmt(ch_pct.mean())}")
            lines.append("")
    else:
        lines.append("无入场数据。\n")

    # ---- 四、止盈/止损/趋势卖出/到期分布 ----
    lines.append("## 四、退出原因分布对比\n")
    lines.append("| 退出原因 | v5 占比 | v5 avg PnL | v5_gt 占比 | v5_gt avg PnL |")
    lines.append("|---------|--------|-----------|-----------|-------------|")
    for reason in ['tp', 'sl', 'time_decay', 'form_break', 'circuit_break', 'ma_support_break', 'expire', 'order_timeout']:
        v5_sub = v5_sim[v5_sim['exit_reason'] == reason]
        gt_sub = gt_sim[gt_sim['exit_reason'] == reason]
        v5_pct = len(v5_sub) / len(v5_sim) if len(v5_sim) > 0 else 0
        gt_pct = len(gt_sub) / len(gt_sim) if len(gt_sim) > 0 else 0
        v5_avg = v5_sub['pnl'].mean() if len(v5_sub) > 0 else 0
        gt_avg = gt_sub['pnl'].mean() if len(gt_sub) > 0 else 0
        lines.append(f"| {reason} | {_pct_fmt(v5_pct)} | {_pct_fmt(v5_avg)} "
                     f"| {_pct_fmt(gt_pct)} | {_pct_fmt(gt_avg)} |")
    lines.append("")

    # ---- 五、过滤统计 ----
    lines.append("## 五、过滤统计\n")
    n_total = len(gt_bt_df)
    n_sim = len(gt_sim)
    n_disabled = len(gt_bt_df[gt_bt_df['status'] == 'disabled'])
    n_cooldown = len(gt_bt_df[gt_bt_df['status'] == 'cooldown'])
    n_order_timeout = len(gt_bt_df[gt_bt_df['status'] == 'order_timeout'])
    n_other_skip = len(gt_bt_df[gt_bt_df['status'].isin(['no_forward_data', 'high_trap_skip', 'insufficient_pre_data', 'invalid_gt'])])
    n_low_support = len(gt_bt_df[gt_bt_df['status'] == 'low_support_skip'])
    n_ma_zone_skip = len(gt_bt_df[gt_bt_df['status'].str.startswith('ma_zone_skip', na=False)])
    lines.append("| 状态 | 数量 | 占比 |")
    lines.append("|------|------|------|")
    lines.append(f"| 总信号 | {n_total} | 100% |")
    lines.append(f"| disabled (参数关闭) | {n_disabled} | {n_disabled/n_total:.1%} |" if n_total > 0 else "| disabled | 0 | - |")
    lines.append(f"| low_support (支撑评分<3) | {n_low_support} | {n_low_support/n_total:.1%} |" if n_total > 0 else "| low_support | 0 | - |")
    lines.append(f"| ma_zone_skip (MA区域过滤) | {n_ma_zone_skip} | {n_ma_zone_skip/n_total:.1%} |" if n_total > 0 else "| ma_zone_skip | 0 | - |")
    lines.append(f"| cooldown (冷却期) | {n_cooldown} | {n_cooldown/n_total:.1%} |" if n_total > 0 else "| cooldown | 0 | - |")
    lines.append(f"| order_timeout (5日未成交) | {n_order_timeout} | {n_order_timeout/n_total:.1%} |" if n_total > 0 else "| order_timeout | 0 | - |")
    lines.append(f"| other_skip (无数据等) | {n_other_skip} | {n_other_skip/n_total:.1%} |" if n_total > 0 else "| other_skip | 0 | - |")
    lines.append(f"| **simulated (成交)** | {n_sim} | {n_sim/n_total:.1%} |" if n_total > 0 else "| simulated | 0 | - |")
    lines.append("")

    # ---- 六、按 DD Tier 对比 ----
    lines.append("## 六、按回调深度对比\n")
    lines.append("| DD Tier | v5 交易 | v5 胜率 | v5 PF | v5_gt 交易 | v5_gt 胜率 | v5_gt PF |")
    lines.append("|---------|--------|--------|------|-----------|-----------|---------|")
    for tier in DRAWDOWN_LABELS:
        v5_sub = v5_sim[v5_sim['dd_tier'] == tier]['pnl'].dropna()
        gt_sub = gt_sim[gt_sim['dd_tier'] == tier]['pnl'].dropna()
        vs = _calc_stats(v5_sub)
        gs = _calc_stats(gt_sub)
        lines.append(
            f"| {tier} | {vs['n']} | {_pct_fmt(vs['wr'])} | {vs['pf']:.2f} "
            f"| {gs['n']} | {_pct_fmt(gs['wr'])} | {gs['pf']:.2f} |"
        )
    lines.append("")

    # ---- 六B、按 MA Zone 分析 ----
    lines.append("## 六B、按 MA Zone 分析\n")
    if 'ma_zone' in gt_sim.columns:
        ma_zones = ['main_trend', 'transition', 'bottom', 'extended', 'high_risk']
        lines.append("| MA Zone | 成交数 | 胜率 | PF | 平均收益 | 中位数 |")
        lines.append("|---------|--------|------|------|---------|--------|")
        for mz in ma_zones:
            sub = gt_sim[gt_sim['ma_zone'] == mz]['pnl'].dropna()
            s = _calc_stats(sub)
            if s['n'] > 0:
                lines.append(
                    f"| {mz} | {s['n']} | {_pct_fmt(s['wr'])} | {s['pf']:.2f} "
                    f"| {_pct_fmt(s['avg'])} | {_pct_fmt(s['median'])} |"
                )
        lines.append("")
    else:
        lines.append("ma_zone 列不存在，跳过。\n")

    # ---- 六C、支撑评分 vs 胜率 ----
    lines.append("## 六C、支撑评分 vs 胜率\n")
    if 'support_score' in gt_sim.columns:
        lines.append("| 支撑评分 | 成交数 | 胜率 | PF | 平均收益 |")
        lines.append("|---------|--------|------|------|---------|")
        for score in range(0, 8):
            sub = gt_sim[gt_sim['support_score'] == score]['pnl'].dropna()
            s = _calc_stats(sub)
            if s['n'] >= 3:
                lines.append(
                    f"| {score} | {s['n']} | {_pct_fmt(s['wr'])} | {s['pf']:.2f} "
                    f"| {_pct_fmt(s['avg'])} |"
                )
        lines.append("")
    else:
        lines.append("support_score 列不存在，跳过。\n")

    # ---- 六D、旧 Zone vs 新 MA Zone 对比 ----
    lines.append("## 六D、旧 Zone vs 新 MA Zone 预测力对比\n")
    if 'ma_zone' in gt_sim.columns:
        old_zones = gt_sim['zone_tag'].value_counts()
        new_zones = gt_sim['ma_zone'].value_counts()
        lines.append("| 分类方式 | 最优Zone | 最差Zone | 区分度(最优WR-最差WR) |")
        lines.append("|---------|---------|---------|---------------------|")

        old_wr = {}
        for z in ZONE_ORDER:
            sub = gt_sim[gt_sim['zone_tag'] == z]['pnl'].dropna()
            if len(sub) >= 10:
                old_wr[z] = (sub > 0).mean()
        if old_wr:
            best_old = max(old_wr, key=old_wr.get)
            worst_old = min(old_wr, key=old_wr.get)
            lines.append(
                f"| zone_tag | {best_old}({_pct_fmt(old_wr[best_old])}) "
                f"| {worst_old}({_pct_fmt(old_wr[worst_old])}) "
                f"| {old_wr[best_old] - old_wr[worst_old]:.1%} |"
            )

        new_wr = {}
        for z in ma_zones:
            sub = gt_sim[gt_sim['ma_zone'] == z]['pnl'].dropna()
            if len(sub) >= 10:
                new_wr[z] = (sub > 0).mean()
        if new_wr:
            best_new = max(new_wr, key=new_wr.get)
            worst_new = min(new_wr, key=new_wr.get)
            lines.append(
                f"| ma_zone | {best_new}({_pct_fmt(new_wr[best_new])}) "
                f"| {worst_new}({_pct_fmt(new_wr[worst_new])}) "
                f"| {new_wr[best_new] - new_wr[worst_new]:.1%} |"
            )
        lines.append("")
    else:
        lines.append("ma_zone 列不存在，跳过。\n")

    # ---- 六E、入场方式对比 (60m vs daily) ----
    lines.append("## 六E、入场方式对比 (60m双确认 vs daily)\n")
    if 'entry_type' in gt_sim.columns:
        lines.append("| 入场方式 | 成交数 | 胜率 | PF | 平均收益 | 中位数 | 最大亏损 |")
        lines.append("|---------|--------|------|------|---------|--------|---------|")
        for et in ['60m', 'daily']:
            sub = gt_sim[gt_sim['entry_type'] == et]['pnl'].dropna()
            s = _calc_stats(sub)
            if s['n'] > 0:
                lines.append(
                    f"| {et} | {s['n']} | {_pct_fmt(s['wr'])} | {s['pf']:.2f} "
                    f"| {_pct_fmt(s['avg'])} | {_pct_fmt(s['median'])} "
                    f"| {_pct_fmt(s['max_loss'])} |"
                )
        lines.append("")

        lines.append("### 按入场方式的退出原因分布\n")
        lines.append("| 入场方式 | tp | sl | circuit_break | ma_support_break | form_break | time_decay | expire |")
        lines.append("|---------|------|------|-------------|----------------|----------|----------|--------|")
        for et in ['60m', 'daily']:
            et_sub = gt_sim[gt_sim['entry_type'] == et]
            if len(et_sub) == 0:
                continue
            n_et = len(et_sub)
            cells = [et]
            for reason in ['tp', 'sl', 'circuit_break', 'ma_support_break', 'form_break', 'time_decay', 'expire']:
                cnt = (et_sub['exit_reason'] == reason).sum()
                cells.append(f'{cnt}({cnt/n_et:.0%})')
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    else:
        lines.append("entry_type 列不存在，跳过。\n")

    # ---- 七、典型差异案例 ----
    lines.append("## 七、典型差异案例\n")

    merged = gt_bt_df.merge(
        v5_bt_df[['signal_idx', 'pnl', 'exit_reason', 'status']].rename(
            columns={'pnl': 'v5_pnl', 'exit_reason': 'v5_exit', 'status': 'v5_status'}
        ),
        on='signal_idx', how='inner',
    )
    both_sim = merged[
        (merged['status'] == 'simulated') & (merged['v5_status'] == 'simulated')
    ].copy()

    if len(both_sim) > 0:
        both_sim['pnl_diff'] = both_sim['pnl'] - both_sim['v5_pnl']

        gt_wins = both_sim.nlargest(5, 'pnl_diff')
        gt_loses = both_sim.nsmallest(5, 'pnl_diff')

        lines.append("### GT 优势案例 (GT PnL > v5 PnL)\n")
        lines.append("| 股票 | 日期 | Zone | GT PnL | v5 PnL | 差异 | GT退出 | v5退出 |")
        lines.append("|------|------|------|--------|--------|------|--------|--------|")
        for _, r in gt_wins.iterrows():
            lines.append(
                f"| {r['stock_code']} | {r['t0_date']} | {r['zone_tag']} "
                f"| {_pct_fmt(r['pnl'])} | {_pct_fmt(r['v5_pnl'])} "
                f"| {_pct_fmt(r['pnl_diff'])} | {r['exit_reason']} | {r['v5_exit']} |"
            )
        lines.append("")

        lines.append("### GT 劣势案例 (GT PnL < v5 PnL)\n")
        lines.append("| 股票 | 日期 | Zone | GT PnL | v5 PnL | 差异 | GT退出 | v5退出 |")
        lines.append("|------|------|------|--------|--------|------|--------|--------|")
        for _, r in gt_loses.iterrows():
            lines.append(
                f"| {r['stock_code']} | {r['t0_date']} | {r['zone_tag']} "
                f"| {_pct_fmt(r['pnl'])} | {_pct_fmt(r['v5_pnl'])} "
                f"| {_pct_fmt(r['pnl_diff'])} | {r['exit_reason']} | {r['v5_exit']} |"
            )
        lines.append("")
    else:
        lines.append("无共同成交信号可对比。\n")

    # ---- 八、结论 ----
    lines.append("## 八、结论\n")
    if gt_s['n'] > 0 and v5_s['n'] > 0:
        wr_diff = gt_s['wr'] - v5_s['wr']
        pf_diff = gt_s['pf'] - v5_s['pf']
        avg_diff = gt_s['avg'] - v5_s['avg']

        if wr_diff > 0.02:
            lines.append(f"- **胜率提升**: GT 方案胜率高 {wr_diff:.1%}，GT 下轨作为入场位更精准")
        elif wr_diff < -0.02:
            lines.append(f"- **胜率下降**: GT 方案胜率降低 {abs(wr_diff):.1%}，需检查入场位设置")
        else:
            lines.append("- **胜率持平**: 两种方案胜率差异在 2% 以内")

        if pf_diff > 0.2:
            lines.append(f"- **盈亏比改善**: PF 提升 {pf_diff:.2f}，通道宽度自适应止盈有效")
        elif pf_diff < -0.2:
            lines.append(f"- **盈亏比恶化**: PF 下降 {abs(pf_diff):.2f}，通道宽度参数需调优")
        else:
            lines.append("- **盈亏比持平**: PF 差异在 0.2 以内")

        if avg_diff > 0.005:
            lines.append(f"- **平均收益提升**: 每笔多赚 {avg_diff:.2%}")
        elif avg_diff < -0.005:
            lines.append(f"- **平均收益下降**: 每笔少赚 {abs(avg_diff):.2%}")

        lines.append("")
        lines.append("### 建议\n")
        if pf_diff > 0 and wr_diff > 0:
            lines.append("- GT 原生方案全面优于固定百分比方案，建议采用")
        elif pf_diff > 0 and wr_diff <= 0:
            lines.append("- GT 方案盈亏比更好但胜率略低，适合趋势跟踪风格")
        elif pf_diff <= 0 and wr_diff > 0:
            lines.append("- GT 方案胜率更高但盈亏比不足，建议调大 tp_mult")
        else:
            lines.append("- GT 方案暂无明显优势，需进一步调参或增加过滤条件")
    else:
        lines.append("数据不足，无法生成结论。\n")
    lines.append("")

    report_text = '\n'.join(lines)
    with open(REPORT_GT_MD, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(f"    已写入 {REPORT_GT_MD}")
    return report_text


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  v5_gt: GT 原生状态机回测")
    print("=" * 70)

    os.makedirs(DOC_DIR, exist_ok=True)

    if not os.path.exists(TAGS_CSV):
        print(f"  ERROR: {TAGS_CSV} 不存在，请先运行 path_analysis_v5.py")
        return
    if not os.path.exists(PATH_V5_CSV):
        print(f"  ERROR: {PATH_V5_CSV} 不存在，请先运行 path_analysis_v5.py")
        return

    tags_df = pd.read_csv(TAGS_CSV)
    tags_df['t0_date'] = pd.to_datetime(tags_df['t0_date'])
    print(f"  加载信号标签: {len(tags_df)} 笔")

    merged_df = pd.read_csv(PATH_V5_CSV)
    merged_df['t0_date'] = pd.to_datetime(merged_df['t0_date'])
    print(f"  加载路径合并数据: {len(merged_df)} 行")

    t_start = time.time()

    param_df = step2_gt_param_inference(merged_df)

    # _analyze_ideal_params(merged_df, param_df)  # skipped: 参数倒推分析

    bt_df = step3_gt_backtest(merged_df, param_df)

    run_h60_ma_comparison(merged_df, param_df)

    run_h60_indicator_comparison(merged_df, param_df)

    run_best_config_verification(merged_df, param_df)

    # run_indicator_window_analysis(merged_df, param_df)  # 已完成，结果见 indicator_window_v5.csv
    # run_indicator_param_scan(merged_df, param_df)       # 已完成，最优参数已采用

    print("\n  [Step 4] 生成对比报告...")
    if os.path.exists(BACKTEST_V5_CSV):
        v5_bt_df = pd.read_csv(BACKTEST_V5_CSV)
        v5_bt_df['t0_date'] = pd.to_datetime(v5_bt_df['t0_date'])
        report = generate_gt_comparison_report(bt_df, v5_bt_df)
        print("\n" + "=" * 70)
        print(report[:2000])
    else:
        print(f"  WARNING: {BACKTEST_V5_CSV} 不存在，跳过对比报告")

    total_elapsed = time.time() - t_start
    print(f"\n  全部完成, 总耗时 {total_elapsed:.1f}s")


if __name__ == '__main__':
    main()
