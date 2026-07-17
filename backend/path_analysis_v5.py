#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v5: 位置驱动状态机回测系统

核心升级 (相比 v4.2):
  - Step 0: T-N 评估周期打标 (Position_Zone / Trend / Volatility)
  - Step 2: Zone × DD_Tier 双维度交叉统计
  - Step 3: WAITING→OBSERVING→HOLDING 三态机回测
  - Step 4: 三方对比报告 (状态机 vs v4.2分层 vs 原系统)

数据策略:
  - T-N 评估: 60m→日线 (fallback 日线 .day)
  - T+1 路径: 复用 path_analysis_v42.csv

输出:
  - doc/0616_super_trend_V3/signal_tags_v5.csv
  - doc/0616_super_trend_V3/path_analysis_v5.csv
  - doc/0616_super_trend_V3/cross_tab_params_v5.csv
  - doc/0616_super_trend_V3/state_machine_backtest_v5.csv
  - doc/0616_super_trend_V3/v5_analysis_report.md
  - doc/0616_super_trend_V3/v5_backtest_report.md
"""

import os
import sys
import time
import warnings
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
    calc_adaptive_n,
    calc_adaptive_k,
    calc_adaptive_offset,
)
from indicators import calculate_macd, calculate_kdj, calculate_rsi

# 是否启用自适应参数模式 (True=自适应, False=固定 N=25 双平滑)
ADAPTIVE_MODE = True

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
DOC_DIR_V5 = os.path.join(_PROJECT_ROOT, 'doc', '0616_super_trend_V3')
DOC_DIR_V4 = os.path.join(_PROJECT_ROOT, 'doc', '0613_super_trend_v2')

REVIEW4_CSV = os.path.join(DOC_DIR_V4, 'review4_final_backtest.csv')
PATH_V42_CSV = os.path.join(DOC_DIR_V4, 'path_analysis_v42.csv')

TAGS_CSV = os.path.join(DOC_DIR_V5, 'signal_tags_v5.csv')
PATH_V5_CSV = os.path.join(DOC_DIR_V5, 'path_analysis_v5.csv')
CROSS_TAB_CSV = os.path.join(DOC_DIR_V5, 'cross_tab_params_v5.csv')
BACKTEST_CSV = os.path.join(DOC_DIR_V5, 'state_machine_backtest_v5.csv')
ANALYSIS_MD = os.path.join(DOC_DIR_V5, 'v5_analysis_report.md')
BACKTEST_MD = os.path.join(DOC_DIR_V5, 'v5_backtest_report.md')

FUTURE_DAYS = 22
FUTURE_CALENDAR_DAYS = 45
LOOKBACK_CALENDAR_DAYS = 300
MIN_PRE_BARS = 120
OBSERVE_WINDOW = 10

DRAWDOWN_BINS = [-float('inf'), -0.20, -0.15, -0.10, -0.05, -0.03, 0.001]
DRAWDOWN_LABELS = ['>20%', '15~20%', '10~15%', '5~10%', '3~5%', '0~3%']

ZONE_ORDER = ['abyss_bottom', 'bottom_start', 'main_wave', 'high_zone', 'high_trap']


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def _aggregate_60m_to_daily(df_60m: pd.DataFrame) -> pd.DataFrame:
    if df_60m is None or df_60m.empty:
        return pd.DataFrame()
    df = df_60m.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns:
            df = df.set_index(pd.to_datetime(df['datetime']))
        elif 'date' in df.columns:
            df = df.set_index(pd.to_datetime(df['date']))
        else:
            df.index = pd.to_datetime(df.index, errors='coerce')
    df = df.dropna(subset=['open'])
    df['date_key'] = df.index.normalize()
    grouped = df.groupby('date_key').agg({
        'open': 'first', 'high': 'max',
        'low': 'min', 'close': 'last', 'volume': 'sum',
    })
    return grouped.sort_index()


def _load_pre_signal_daily_60m(stock: str, t0_date, lookback_days=300) -> pd.DataFrame:
    start = (t0_date - pd.Timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    end = (t0_date - pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        df_60m = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        df_60m = None
    return _aggregate_60m_to_daily(df_60m)


def _load_pre_signal_daily_fallback(stock: str, t0_date, lookback_days=300) -> pd.DataFrame:
    data = data_loader.get_multi_timeframe_data(stock)
    if not data or not data['data_status']['daily_available']:
        return pd.DataFrame()
    dfd = data['daily_data']
    cutoff = pd.Timestamp(t0_date)
    start = cutoff - pd.Timedelta(days=lookback_days)
    pre = dfd[(dfd.index >= start) & (dfd.index < cutoff)]
    if pre.empty:
        return pre
    return pre[['open', 'high', 'low', 'close', 'volume']].copy()


# ---------------------------------------------------------------------------
# Step 0: SignalTagger
# ---------------------------------------------------------------------------
def compute_signal_tags(daily: pd.DataFrame, close_t0: float = None) -> dict:
    if daily is None or len(daily) < 30:
        return None

    c = daily['close'].astype(float)
    h = daily['high'].astype(float)
    l = daily['low'].astype(float)

    last_close = float(c.iloc[-1])
    n = len(daily)

    # Position_Ratio (120日)
    window = min(120, n)
    rolling_min = float(l.iloc[-window:].min())
    rolling_max = float(h.iloc[-window:].max())
    rng = rolling_max - rolling_min
    position_ratio = (last_close - rolling_min) / rng if rng > 1e-9 else 0.5

    # Golden_Trend
    n_param, k_param, offset_param = 25, 1.0, 1.0
    if ADAPTIVE_MODE:
        n_param = calc_adaptive_n(daily)
        k_param = calc_adaptive_k(daily)
        offset_param = calc_adaptive_offset(daily)
        gt_series = calc_golden_trend(h, l, n=n_param, double_smooth=True,
                                       k=k_param, offset_coef=offset_param)
        golden_trend = float(gt_series.iloc[-1])
    else:
        ema25_h = h.ewm(span=25, adjust=False).mean()
        ema25_l = l.ewm(span=25, adjust=False).mean()
        d_ema25_h = ema25_h.ewm(span=25, adjust=False).mean()
        d_ema25_l = ema25_l.ewm(span=25, adjust=False).mean()
        golden_trend = float(d_ema25_l.iloc[-1] - (d_ema25_h.iloc[-1] - d_ema25_l.iloc[-1]))

    # BBI
    ma5 = c.rolling(5).mean()
    ma10 = c.rolling(10).mean()
    ma20 = c.rolling(20).mean()
    ma30 = c.rolling(30).mean()
    bbi = (ma5 + ma10 + ma20 + ma30) / 4
    bbi_val = float(bbi.iloc[-1]) if not pd.isna(bbi.iloc[-1]) else last_close

    # MA13, MA55
    ma13 = c.rolling(13).mean()
    ma55 = c.rolling(55).mean()
    ma13_val = float(ma13.iloc[-1]) if not pd.isna(ma13.iloc[-1]) else last_close
    ma55_val = float(ma55.iloc[-1]) if not pd.isna(ma55.iloc[-1]) else last_close

    # MA13 斜率 (5日)
    if n >= 18 and not pd.isna(ma13.iloc[-6]):
        ma13_slope = float(ma13.iloc[-1] - ma13.iloc[-6])
    else:
        ma13_slope = 0.0

    # ATR20
    atr_window = min(20, n - 1)
    if atr_window > 0:
        hl = h - l
        hc = np.abs(h - c.shift(1))
        lc = np.abs(l - c.shift(1))
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr20 = float(tr.iloc[-atr_window:].mean())
    else:
        atr20 = 0.0
    atr20_pct = atr20 / last_close if last_close > 0 else 0.0

    # --- MA 距离模型 ---
    ma30_s = c.rolling(30).mean()
    ma45_s = c.rolling(45).mean()
    ma90_s = c.rolling(90).mean()
    ma150_s = c.rolling(150).mean()
    ma240_s = c.rolling(240).mean()

    ma30_val = float(ma30_s.iloc[-1]) if not pd.isna(ma30_s.iloc[-1]) else np.nan
    ma45_val = float(ma45_s.iloc[-1]) if not pd.isna(ma45_s.iloc[-1]) else np.nan
    ma90_val = float(ma90_s.iloc[-1]) if not pd.isna(ma90_s.iloc[-1]) else np.nan
    ma150_val = float(ma150_s.iloc[-1]) if not pd.isna(ma150_s.iloc[-1]) else np.nan
    ma240_val = float(ma240_s.iloc[-1]) if not pd.isna(ma240_s.iloc[-1]) else np.nan

    def _dist(ma_val):
        if pd.isna(ma_val) or ma_val <= 0:
            return np.nan
        return (last_close - ma_val) / ma_val

    dist_ma30 = _dist(ma30_val)
    dist_ma90 = _dist(ma90_val)
    dist_ma150 = _dist(ma150_val)
    dist_ma240 = _dist(ma240_val)

    def _slope(ma_s, lookback=5):
        if len(ma_s) < lookback + 1 or pd.isna(ma_s.iloc[-1]) or pd.isna(ma_s.iloc[-lookback - 1]):
            return 0.0
        prev = float(ma_s.iloc[-lookback - 1])
        curr = float(ma_s.iloc[-1])
        if prev <= 0:
            return 0.0
        return (curr - prev) / prev

    slope_ma30 = _slope(ma30_s)
    slope_ma90 = _slope(ma90_s)
    slope_ma240 = _slope(ma240_s)

    # 支撑评分 (0~7)
    support_score = 0
    if not pd.isna(ma30_val) and last_close > ma30_val:
        support_score += 1
    if not pd.isna(ma90_val) and last_close > ma90_val:
        support_score += 1
    if not pd.isna(ma150_val) and last_close > ma150_val:
        support_score += 1
    if not pd.isna(ma240_val) and last_close > ma240_val:
        support_score += 1
    if slope_ma30 > 0:
        support_score += 1
    if slope_ma90 > 0:
        support_score += 1
    if not pd.isna(ma150_val) and _slope(ma150_s) > 0:
        support_score += 1

    # MA Zone 分类
    above_90 = not pd.isna(ma90_val) and last_close > ma90_val
    above_150 = not pd.isna(ma150_val) and last_close > ma150_val
    above_240 = not pd.isna(ma240_val) and last_close > ma240_val
    slope_positive = slope_ma30 > 0 and slope_ma90 > 0

    if not above_90 and not above_240:
        ma_zone = 'bottom'
    elif above_90 and not above_240:
        ma_zone = 'transition'
    elif above_90 and above_150 and slope_positive:
        if not pd.isna(dist_ma90) and dist_ma90 > 0.25:
            ma_zone = 'extended'
        else:
            ma_zone = 'main_trend'
    elif above_90 and not slope_positive:
        ma_zone = 'high_risk'
    else:
        ma_zone = 'main_trend'

    # zone_tag
    if position_ratio < 0.2:
        zone_tag = 'abyss_bottom'
    elif position_ratio < 0.3:
        zone_tag = 'bottom_start'
    elif position_ratio <= 0.7:
        zone_tag = 'main_wave'
    elif position_ratio <= 0.8:
        zone_tag = 'high_zone'
    else:
        zone_tag = 'high_trap'

    # trend_tag
    if ma13_val > ma55_val and ma13_slope > 0 and last_close > bbi_val:
        trend_tag = 'bull_aligned'
    elif ma13_val < ma55_val and ma13_slope < 0 and last_close < bbi_val:
        trend_tag = 'bear_aligned'
    else:
        trend_tag = 'neutral'

    # vol_tag
    if atr20_pct < 0.03:
        vol_tag = 'low'
    elif atr20_pct < 0.06:
        vol_tag = 'medium'
    else:
        vol_tag = 'high'

    # --- 指标连续值 (MACD/RSI/KDJ) ---
    dif, dea = calculate_macd(daily, fast=8, slow=21, signal=6)
    hist = (dif - dea) * 2
    macd_hist_val = float(hist.iloc[-1]) if not pd.isna(hist.iloc[-1]) else 0.0
    macd_hist_slope_val = float(hist.iloc[-1] - hist.iloc[-4]) if n >= 4 and not pd.isna(hist.iloc[-4]) else 0.0
    hist_slope_series = hist.diff(3)
    macd_hist_accel_val = float(hist_slope_series.iloc[-1] - hist_slope_series.iloc[-4]) \
        if n >= 7 and not pd.isna(hist_slope_series.iloc[-4]) else 0.0

    rsi_s = calculate_rsi(daily, periods=14)
    rsi_val = float(rsi_s.iloc[-1]) if not pd.isna(rsi_s.iloc[-1]) else 50.0
    rsi_slope_val = float(rsi_s.iloc[-1] - rsi_s.iloc[-6]) if n >= 6 and not pd.isna(rsi_s.iloc[-6]) else 0.0

    k_s, d_s, j_s = calculate_kdj(daily, n=27, k_period=3, d_period=3)
    kdj_j_val = float(j_s.iloc[-1]) if not pd.isna(j_s.iloc[-1]) else 50.0
    kdj_j_slope_val = float(j_s.iloc[-1] - j_s.iloc[-4]) if n >= 4 and not pd.isna(j_s.iloc[-4]) else 0.0
    kdj_k_val = float(k_s.iloc[-1]) if not pd.isna(k_s.iloc[-1]) else 50.0

    return {
        'position_ratio': round(position_ratio, 4),
        'zone_tag': zone_tag,
        'trend_tag': trend_tag,
        'bbi_value': round(bbi_val, 4),
        'ma13': round(ma13_val, 4),
        'ma55': round(ma55_val, 4),
        'ma13_slope': round(ma13_slope, 4),
        'atr20': round(atr20, 4),
        'atr20_pct': round(atr20_pct, 4),
        'vol_tag': vol_tag,
        'golden_trend_t0': round(golden_trend, 4),
        'gt_n': n_param,
        'gt_k': round(k_param, 3),
        'gt_offset': round(offset_param, 3),
        'last_close': round(last_close, 4),
        # MA 距离模型
        'ma30': round(ma30_val, 4) if not pd.isna(ma30_val) else np.nan,
        'ma45': round(ma45_val, 4) if not pd.isna(ma45_val) else np.nan,
        'ma90': round(ma90_val, 4) if not pd.isna(ma90_val) else np.nan,
        'ma150': round(ma150_val, 4) if not pd.isna(ma150_val) else np.nan,
        'ma240': round(ma240_val, 4) if not pd.isna(ma240_val) else np.nan,
        'dist_ma30': round(dist_ma30, 4) if not pd.isna(dist_ma30) else np.nan,
        'dist_ma90': round(dist_ma90, 4) if not pd.isna(dist_ma90) else np.nan,
        'dist_ma150': round(dist_ma150, 4) if not pd.isna(dist_ma150) else np.nan,
        'dist_ma240': round(dist_ma240, 4) if not pd.isna(dist_ma240) else np.nan,
        'slope_ma30': round(slope_ma30, 6),
        'slope_ma90': round(slope_ma90, 6),
        'slope_ma240': round(slope_ma240, 6),
        'support_score': support_score,
        'ma_zone': ma_zone,
        # 指标连续值
        'macd_hist': round(macd_hist_val, 4),
        'macd_hist_slope': round(macd_hist_slope_val, 4),
        'macd_hist_accel': round(macd_hist_accel_val, 4),
        'rsi_value': round(rsi_val, 2),
        'rsi_slope': round(rsi_slope_val, 4),
        'kdj_j': round(kdj_j_val, 2),
        'kdj_j_slope': round(kdj_j_slope_val, 4),
        'kdj_k': round(kdj_k_val, 2),
    }


def step0_signal_tagger(df_signals: pd.DataFrame) -> pd.DataFrame:
    print("\n  [Step 0] 信号预标记...")
    results = []
    n_ok = n_fallback = n_skip = 0
    t0 = time.time()

    for i, (idx, row) in enumerate(df_signals.iterrows()):
        if (i + 1) % 200 == 0 or i == 0:
            print(f"    标记 {i + 1}/{len(df_signals)} ...")

        stock = row['stock_code']
        t0_date = row['t0_date']

        daily = _load_pre_signal_daily_60m(stock, t0_date)
        data_source = '60m'

        if daily is None or len(daily) < MIN_PRE_BARS:
            daily = _load_pre_signal_daily_fallback(stock, t0_date)
            data_source = 'daily'

        if daily is None or len(daily) < MIN_PRE_BARS:
            n_skip += 1
            results.append({
                'signal_idx': idx,
                'stock_code': stock,
                't0_date': t0_date,
                'position_ratio': np.nan,
                'zone_tag': 'unknown',
                'trend_tag': 'unknown',
                'bbi_value': np.nan,
                'ma13': np.nan,
                'ma55': np.nan,
                'ma13_slope': np.nan,
                'atr20': np.nan,
                'atr20_pct': np.nan,
                'vol_tag': 'unknown',
                'golden_trend_t0': np.nan,
                'last_close': np.nan,
                'ma30': np.nan, 'ma45': np.nan, 'ma90': np.nan,
                'ma150': np.nan, 'ma240': np.nan,
                'dist_ma30': np.nan, 'dist_ma90': np.nan,
                'dist_ma150': np.nan, 'dist_ma240': np.nan,
                'slope_ma30': np.nan, 'slope_ma90': np.nan, 'slope_ma240': np.nan,
                'support_score': np.nan, 'ma_zone': 'unknown',
                'macd_hist': np.nan, 'macd_hist_slope': np.nan, 'macd_hist_accel': np.nan,
                'rsi_value': np.nan, 'rsi_slope': np.nan,
                'kdj_j': np.nan, 'kdj_j_slope': np.nan, 'kdj_k': np.nan,
                'data_source': 'skip',
                'pre_bars': 0,
            })
            continue

        if data_source == 'daily':
            n_fallback += 1

        tags = compute_signal_tags(daily)
        if tags is None:
            n_skip += 1
            results.append({
                'signal_idx': idx,
                'stock_code': stock,
                't0_date': t0_date,
                'position_ratio': np.nan,
                'zone_tag': 'unknown',
                'trend_tag': 'unknown',
                'bbi_value': np.nan,
                'ma13': np.nan,
                'ma55': np.nan,
                'ma13_slope': np.nan,
                'atr20': np.nan,
                'atr20_pct': np.nan,
                'vol_tag': 'unknown',
                'golden_trend_t0': np.nan,
                'last_close': np.nan,
                'ma30': np.nan, 'ma45': np.nan, 'ma90': np.nan,
                'ma150': np.nan, 'ma240': np.nan,
                'dist_ma30': np.nan, 'dist_ma90': np.nan,
                'dist_ma150': np.nan, 'dist_ma240': np.nan,
                'slope_ma30': np.nan, 'slope_ma90': np.nan, 'slope_ma240': np.nan,
                'support_score': np.nan, 'ma_zone': 'unknown',
                'macd_hist': np.nan, 'macd_hist_slope': np.nan, 'macd_hist_accel': np.nan,
                'rsi_value': np.nan, 'rsi_slope': np.nan,
                'kdj_j': np.nan, 'kdj_j_slope': np.nan, 'kdj_k': np.nan,
                'data_source': 'skip',
                'pre_bars': len(daily),
            })
            continue

        tags['signal_idx'] = idx
        tags['stock_code'] = stock
        tags['t0_date'] = t0_date
        tags['data_source'] = data_source
        tags['pre_bars'] = len(daily)
        results.append(tags)
        n_ok += 1

    elapsed = time.time() - t0
    result_df = pd.DataFrame(results)
    print(f"    完成: {n_ok} OK ({n_fallback} fallback), {n_skip} skip, 耗时 {elapsed:.1f}s")
    return result_df


# ---------------------------------------------------------------------------
# Step 1: 路径分析合并
# ---------------------------------------------------------------------------
def step1_merge_path(tags_df: pd.DataFrame) -> pd.DataFrame:
    print("\n  [Step 1] 合并路径分析数据...")

    if os.path.exists(PATH_V42_CSV):
        path_df = pd.read_csv(PATH_V42_CSV)
        path_df['t0_date'] = pd.to_datetime(path_df['t0_date'])
        print(f"    加载 v4.2 路径数据: {len(path_df)} 行")
    else:
        print(f"    WARNING: {PATH_V42_CSV} 不存在，跳过路径合并")
        return tags_df

    merged = tags_df.merge(
        path_df[['signal_idx', 'entry_price', 'max_drawdown', 'dd_day_idx',
                 'rebound_pct', 'subsequent_high', 'effective_range', 'mfe', 'final_return']],
        on='signal_idx', how='left'
    )

    valid = merged['max_drawdown'].notna().sum()
    print(f"    合并完成: {valid}/{len(merged)} 有路径数据")

    merged.to_csv(PATH_V5_CSV, index=False, encoding='utf-8-sig')
    print(f"    已保存 {PATH_V5_CSV}")
    return merged


# ---------------------------------------------------------------------------
# Step 2: 交叉统计
# ---------------------------------------------------------------------------
def step2_cross_tab(merged_df: pd.DataFrame) -> tuple:
    print("\n  [Step 2] Zone × DD_Tier 交叉统计...")

    valid = merged_df.dropna(subset=['max_drawdown', 'rebound_pct', 'position_ratio']).copy()
    valid = valid[valid['zone_tag'] != 'unknown']

    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'],
        bins=DRAWDOWN_BINS,
        labels=DRAWDOWN_LABELS,
    )

    # 交叉聚合
    stats_rows = []
    for zone in ZONE_ORDER:
        for tier in DRAWDOWN_LABELS:
            sub = valid[(valid['zone_tag'] == zone) & (valid['dd_tier'] == tier)]
            if len(sub) == 0:
                continue
            dd = sub['max_drawdown']
            rb = sub['rebound_pct']
            mfe = sub['mfe']
            dd_day = sub['dd_day_idx']

            rb_gt5 = (rb > 0.05).mean()
            rb_gt10 = (rb > 0.10).mean()
            rb_p50 = rb.quantile(0.50)
            rb_p80 = rb.quantile(0.80)

            avg_atr = sub['atr20_pct'].mean() if 'atr20_pct' in sub.columns else 0.05

            stats_rows.append({
                'zone_tag': zone,
                'dd_tier': tier,
                'n': len(sub),
                'avg_dd': dd.mean(),
                'median_dd': dd.median(),
                'avg_rebound': rb.mean(),
                'median_rebound': rb.median(),
                'rebound_p50': rb_p50,
                'rebound_p80': rb_p80,
                'rebound_gt5_pct': rb_gt5,
                'rebound_gt10_pct': rb_gt10,
                'avg_mfe': mfe.mean(),
                'avg_dd_day': dd_day.mean(),
                'avg_atr20_pct': avg_atr,
            })

    stats_df = pd.DataFrame(stats_rows)

    # 参数反推
    param_rows = []
    for _, row in stats_df.iterrows():
        zone = row['zone_tag']
        tier = row['dd_tier']
        n = row['n']
        median_dd = row['median_dd']
        rb_p80 = row['rebound_p80']
        median_rb = row['median_rebound']
        rb_gt5 = row['rebound_gt5_pct']
        avg_atr = row.get('avg_atr20_pct', 0.05)

        # 入场触发: 从中位回调反推，必须为负值
        if zone in ('abyss_bottom', 'bottom_start'):
            entry_trigger = -0.03
        elif zone == 'main_wave':
            # 用中位回调深度的 70% 作为触发点，上限 -3%，下限 -10%
            raw = median_dd * 0.7
            entry_trigger = min(max(raw, -0.10), -0.03)
        elif zone == 'high_zone':
            entry_trigger = -0.05
        else:
            entry_trigger = -0.05

        # 止损: ATR-based, 1.5倍ATR百分比，最低 6%
        sl_pct = max(avg_atr * 1.5, 0.06)

        # 止盈: rebound 中位 * 0.6 (更保守折扣), 最低 5%
        # 考虑入场点不在绝对底部，实际反弹空间打折
        tp_pct = max(median_rb * 0.6, 0.05)

        # 确保盈亏比合理: TP 至少 > SL
        if tp_pct <= sl_pct:
            tp_pct = sl_pct * 1.5

        # 启用条件
        # >20% 回调太深，任何位置的结构大概率已破坏
        deep_broken = (tier == '>20%')
        enabled = (
            zone != 'high_trap'
            and not deep_broken
            and n >= 10
            and rb_gt5 > 0.4
        )

        param_rows.append({
            'zone_tag': zone,
            'dd_tier': tier,
            'n': int(n),
            'entry_trigger': round(entry_trigger, 4),
            'tp_pct': round(tp_pct, 4),
            'sl_pct': round(sl_pct, 4),
            'avg_atr20_pct': round(avg_atr, 4),
            'rebound_p80': round(rb_p80, 4),
            'rebound_gt5_pct': round(rb_gt5, 4),
            'enabled': enabled,
        })

    param_df = pd.DataFrame(param_rows)
    param_df.to_csv(CROSS_TAB_CSV, index=False, encoding='utf-8-sig')
    print(f"    交叉统计 {len(stats_df)} 格, 参数 {len(param_df)} 格")
    print(f"    已保存 {CROSS_TAB_CSV}")

    return stats_df, param_df


# ---------------------------------------------------------------------------
# Step 3: 状态机回测
# ---------------------------------------------------------------------------
STATE_WAITING = 0
STATE_OBSERVING = 1
STATE_HOLDING = 2


def _get_target_entry(zone_tag: str, t0_close: float, entry_trigger_pct: float) -> float:
    return t0_close * (1 + entry_trigger_pct)


def _build_param_lookup(param_df: pd.DataFrame) -> dict:
    lookup = {}
    for _, row in param_df.iterrows():
        key = (row['zone_tag'], row['dd_tier'])
        lookup[key] = row
    return lookup


def run_single_signal(daily_forward: pd.DataFrame, zone_tag: str,
                      t0_close: float,
                      dd_tier: str, param_lookup: dict) -> dict:
    if daily_forward is None or daily_forward.empty:
        return {'status': 'no_forward_data'}

    if zone_tag == 'high_trap':
        return {'status': 'high_trap_skip'}

    param_key = (zone_tag, dd_tier)
    param = param_lookup.get(param_key)
    if param is None or not param.get('enabled', False):
        # fallback: try any enabled param for this zone
        for k, v in param_lookup.items():
            if k[0] == zone_tag and v.get('enabled', False):
                param = v
                break
    if param is None or not param.get('enabled', False):
        # ultimate fallback
        entry_trigger_pct = -0.05
        tp_pct = 0.10
        sl_pct = 0.08
    else:
        entry_trigger_pct = param['entry_trigger']
        tp_pct = param['tp_pct']
        sl_pct = param['sl_pct']

    target_entry = _get_target_entry(zone_tag, t0_close, entry_trigger_pct)
    if target_entry <= 0:
        return {'status': 'invalid_target'}

    n = min(len(daily_forward), FUTURE_DAYS)
    state = STATE_OBSERVING
    countdown = OBSERVE_WINDOW

    entry_price = None
    entry_day_idx = None
    tp_price = None
    sl_price = None

    for day_i in range(n):
        day_low = float(daily_forward['low'].iloc[day_i])
        day_high = float(daily_forward['high'].iloc[day_i])
        day_close = float(daily_forward['close'].iloc[day_i])

        if state == STATE_OBSERVING:
            countdown -= 1
            if day_low <= target_entry:
                state = STATE_HOLDING
                entry_price = target_entry
                entry_day_idx = day_i
                tp_price = entry_price * (1 + tp_pct)
                sl_price = entry_price * (1 - sl_pct)
                if day_high >= tp_price:
                    return {
                        'status': 'simulated',
                        'target_entry_price': target_entry,
                        'actual_entry_price': entry_price,
                        'entry_day_idx': entry_day_idx,
                        'tp_price': tp_price,
                        'sl_price': sl_price,
                        'exit_price': tp_price,
                        'exit_day_idx': day_i,
                        'exit_reason': 'tp',
                        'pnl': tp_pct,
                    }
                if day_low <= sl_price:
                    return {
                        'status': 'simulated',
                        'target_entry_price': target_entry,
                        'actual_entry_price': entry_price,
                        'entry_day_idx': entry_day_idx,
                        'tp_price': tp_price,
                        'sl_price': sl_price,
                        'exit_price': sl_price,
                        'exit_day_idx': day_i,
                        'exit_reason': 'sl',
                        'pnl': -sl_pct,
                    }
            elif countdown <= 0:
                return {
                    'status': 'observe_expire',
                    'target_entry_price': target_entry,
                    'actual_entry_price': np.nan,
                    'entry_day_idx': np.nan,
                    'tp_price': np.nan,
                    'sl_price': np.nan,
                    'exit_price': np.nan,
                    'exit_day_idx': np.nan,
                    'exit_reason': 'observe_expire',
                    'pnl': np.nan,
                }

        elif state == STATE_HOLDING:
            if day_high >= tp_price:
                return {
                    'status': 'simulated',
                    'target_entry_price': target_entry,
                    'actual_entry_price': entry_price,
                    'entry_day_idx': entry_day_idx,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'exit_price': tp_price,
                    'exit_day_idx': day_i,
                    'exit_reason': 'tp',
                    'pnl': tp_pct,
                }
            if day_low <= sl_price:
                return {
                    'status': 'simulated',
                    'target_entry_price': target_entry,
                    'actual_entry_price': entry_price,
                    'entry_day_idx': entry_day_idx,
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'exit_price': sl_price,
                    'exit_day_idx': day_i,
                    'exit_reason': 'sl',
                    'pnl': -sl_pct,
                }

    # 持仓到期
    if state == STATE_HOLDING and entry_price is not None:
        last_close = float(daily_forward['close'].iloc[n - 1])
        pnl = last_close / entry_price - 1
        return {
            'status': 'simulated',
            'target_entry_price': target_entry,
            'actual_entry_price': entry_price,
            'entry_day_idx': entry_day_idx,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'exit_price': last_close,
            'exit_day_idx': n - 1,
            'exit_reason': 'expire',
            'pnl': pnl,
        }

    return {
        'status': 'observe_expire',
        'target_entry_price': target_entry,
        'actual_entry_price': np.nan,
        'entry_day_idx': np.nan,
        'tp_price': np.nan,
        'sl_price': np.nan,
        'exit_price': np.nan,
        'exit_day_idx': np.nan,
        'exit_reason': 'observe_expire',
        'pnl': np.nan,
    }


def step3_state_machine_backtest(merged_df: pd.DataFrame, param_df: pd.DataFrame) -> pd.DataFrame:
    print("\n  [Step 3] 状态机回测...")

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

    results = []
    t0 = time.time()

    for i, (idx, row) in enumerate(valid.iterrows()):
        if (i + 1) % 500 == 0:
            print(f"    回测 {i + 1}/{len(valid)} ...")

        stock = row['stock_code']
        t0_date = row['t0_date']
        zone_tag = row['zone_tag']
        golden_trend = row['golden_trend_t0']
        t0_close = row['last_close']
        dd_tier = row['dd_tier']

        # 加载 T+1 ~ T+22 日线
        start = (t0_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        end = (t0_date + pd.Timedelta(days=FUTURE_CALENDAR_DAYS)).strftime('%Y-%m-%d')
        try:
            df_60m = data_loader.get_min_data_in_range(stock, '60m', start, end)
        except Exception:
            df_60m = None
        daily_fwd = _aggregate_60m_to_daily(df_60m)

        sim = run_single_signal(
            daily_fwd, zone_tag, t0_close, dd_tier, param_lookup
        )

        results.append({
            'signal_idx': idx,
            'stock_code': stock,
            't0_date': t0_date,
            'zone_tag': zone_tag,
            'dd_tier': str(dd_tier),
            'position_ratio': row['position_ratio'],
            'trend_tag': row['trend_tag'],
            'golden_trend_t0': golden_trend,
            **sim,
        })

    result_df = pd.DataFrame(results)
    elapsed = time.time() - t0
    print(f"    回测完成, 耗时 {elapsed:.1f}s")

    result_df.to_csv(BACKTEST_CSV, index=False, encoding='utf-8-sig')
    print(f"    已保存 {BACKTEST_CSV}")
    return result_df


# ---------------------------------------------------------------------------
# Step 4: 报告
# ---------------------------------------------------------------------------
def _pct_fmt(val):
    if pd.isna(val):
        return '-'
    return f'{val:.2%}'


def _f4(val):
    if pd.isna(val):
        return '-'
    return f'{val:.4f}'


def generate_analysis_report(tags_df, stats_df, param_df):
    lines = []
    lines.append("# v5 路径分析 + 交叉统计报告\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append("")

    # Zone 分布
    valid_tags = tags_df[tags_df['zone_tag'] != 'unknown']
    lines.append("## 一、信号位置分布\n")
    lines.append("| Zone | n | 占比 | avg Position_Ratio | avg ATR20% |")
    lines.append("|------|---|------|--------------------|------------|")
    for zone in ZONE_ORDER:
        sub = valid_tags[valid_tags['zone_tag'] == zone]
        if len(sub) == 0:
            continue
        lines.append(f"| {zone} | {len(sub)} | {len(sub)/len(valid_tags):.1%} | "
                     f"{sub['position_ratio'].mean():.4f} | {sub['atr20_pct'].mean():.2%} |")
    lines.append(f"| **合计** | **{len(valid_tags)}** | **100%** | | |")
    lines.append("")

    # Trend 分布
    lines.append("## 二、趋势状态分布\n")
    lines.append("| Trend | n | 占比 |")
    lines.append("|-------|---|------|")
    for trend in ['bull_aligned', 'neutral', 'bear_aligned']:
        sub = valid_tags[valid_tags['trend_tag'] == trend]
        lines.append(f"| {trend} | {len(sub)} | {len(sub)/len(valid_tags):.1%} |")
    lines.append("")

    # Zone × Trend 交叉
    lines.append("## 三、Zone × Trend 交叉分布\n")
    lines.append("| Zone | bull_aligned | neutral | bear_aligned |")
    lines.append("|------|-------------|---------|-------------|")
    for zone in ZONE_ORDER:
        sub = valid_tags[valid_tags['zone_tag'] == zone]
        cells = []
        for trend in ['bull_aligned', 'neutral', 'bear_aligned']:
            cells.append(str(len(sub[sub['trend_tag'] == trend])))
        lines.append(f"| {zone} | {' | '.join(cells)} |")
    lines.append("")

    # 交叉热力表
    lines.append("## 四、Zone × DD_Tier 交叉热力表\n")
    lines.append("| Zone | DD Tier | n | avg回调 | avg反弹 | 反弹P50 | 反弹P80 | 反弹>5% | 反弹>10% |")
    lines.append("|------|---------|---|---------|---------|---------|---------|---------|----------|")
    for _, r in stats_df.iterrows():
        lines.append(f"| {r['zone_tag']} | {r['dd_tier']} | {r['n']} | "
                     f"{_pct_fmt(r['avg_dd'])} | {_pct_fmt(r['avg_rebound'])} | "
                     f"{_pct_fmt(r['rebound_p50'])} | {_pct_fmt(r['rebound_p80'])} | "
                     f"{_pct_fmt(r['rebound_gt5_pct'])} | {_pct_fmt(r['rebound_gt10_pct'])} |")
    lines.append("")

    # 参数矩阵
    lines.append("## 五、入场参数矩阵\n")
    lines.append("| Zone | DD Tier | n | Entry Trigger | TP% | SL% | ATR20% | 反弹P80 | 反弹>5% | Enabled |")
    lines.append("|------|---------|---|--------------|-----|-----|--------|---------|---------|---------|")
    for _, p in param_df.iterrows():
        lines.append(f"| {p['zone_tag']} | {p['dd_tier']} | {p['n']} | "
                     f"{_pct_fmt(p['entry_trigger'])} | {_pct_fmt(p['tp_pct'])} | "
                     f"{_pct_fmt(p['sl_pct'])} | {_pct_fmt(p.get('avg_atr20_pct', 0))} | "
                     f"{_pct_fmt(p['rebound_p80'])} | "
                     f"{_pct_fmt(p['rebound_gt5_pct'])} | "
                     f"{'Yes' if p['enabled'] else 'No'} |")
    lines.append("")

    with open(ANALYSIS_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"    已写入 {ANALYSIS_MD}")


def generate_backtest_report(bt_df: pd.DataFrame, review4_df: pd.DataFrame):
    lines = []
    lines.append("# v5 状态机回测报告\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append("")

    total = len(bt_df)
    simulated = bt_df[bt_df['status'] == 'simulated']
    observed_expire = bt_df[bt_df['status'] == 'observe_expire']
    high_trap_skip = bt_df[bt_df['status'] == 'high_trap_skip']

    lines.append("## 一、触发统计\n")
    lines.append("| 状态 | 数量 | 占比 |")
    lines.append("|------|------|------|")
    lines.append(f"| 总信号 | {total} | 100% |")
    lines.append(f"| 入场成交 | {len(simulated)} | {len(simulated)/total:.1%} |")
    lines.append(f"| 观察期放弃 | {len(observed_expire)} | {len(observed_expire)/total:.1%} |")
    lines.append(f"| 高位熔断 | {len(high_trap_skip)} | {len(high_trap_skip)/total:.1%} |")
    lines.append("")

    if len(simulated) == 0:
        lines.append("无触发交易。\n")
        with open(BACKTEST_MD, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return

    pnl = simulated['pnl'].dropna()
    win = (pnl > 0).sum()
    gp = float(pnl[pnl > 0].sum()) if win > 0 else 0
    gl = abs(float(pnl[pnl < 0].sum())) if (pnl < 0).sum() > 0 else 0.001
    pf = gp / gl if gl > 0 else 99.99

    # 原系统基线
    orig_traded = review4_df[review4_df['status'] == 'traded']
    orig_pnl = orig_traded['total_pnl_pct'].dropna() if 'total_pnl_pct' in orig_traded.columns else pd.Series(dtype=float)

    lines.append("## 二、整体表现\n")
    lines.append("| 指标 | v5 状态机 | 原系统 (Review4) |")
    lines.append("|------|----------|-----------------|")

    if len(orig_pnl) > 0:
        orig_avg = orig_pnl.mean()
        orig_wr = (orig_pnl > 0).mean()
        orig_gp = float(orig_pnl[orig_pnl > 0].sum()) if (orig_pnl > 0).any() else 0
        orig_gl = abs(float(orig_pnl[orig_pnl < 0].sum())) if (orig_pnl < 0).any() else 0.001
        orig_pf = orig_gp / orig_gl if orig_gl > 0 else 99.99
    else:
        orig_avg = orig_wr = orig_pf = 0

    lines.append(f"| 交易数 | {len(pnl)} | {len(orig_pnl)} |")
    lines.append(f"| 平均盈亏 | {_f4(pnl.mean())} ({_pct_fmt(pnl.mean())}) | {_f4(orig_avg)} ({_pct_fmt(orig_avg)}) |")
    lines.append(f"| 中位数 | {_f4(pnl.median())} | {_f4(orig_pnl.median() if len(orig_pnl) > 0 else 0)} |")
    lines.append(f"| 胜率 | {win/len(pnl):.1%} | {orig_wr:.1%} |")
    lines.append(f"| 盈利因子 | {pf:.2f} | {orig_pf:.2f} |")
    lines.append(f"| 最大盈利 | {_f4(pnl.max())} | {_f4(orig_pnl.max() if len(orig_pnl) > 0 else 0)} |")
    lines.append(f"| 最大亏损 | {_f4(pnl.min())} | {_f4(orig_pnl.min() if len(orig_pnl) > 0 else 0)} |")
    lines.append("")

    # 按 Zone 分组
    lines.append("## 三、按 Zone 分组表现\n")
    lines.append("| Zone | 交易数 | avg PnL | 中位 PnL | 胜率 | PF | 止盈% | 止损% | 到期% |")
    lines.append("|------|--------|---------|----------|------|------|------|------|------|")
    for zone in ZONE_ORDER:
        sub = simulated[simulated['zone_tag'] == zone]
        if len(sub) == 0:
            continue
        s_pnl = sub['pnl'].dropna()
        if len(s_pnl) == 0:
            continue
        s_win = (s_pnl > 0).sum()
        s_gp = float(s_pnl[s_pnl > 0].sum()) if s_win > 0 else 0
        s_gl = abs(float(s_pnl[s_pnl < 0].sum())) if (s_pnl < 0).sum() > 0 else 0.001
        s_pf = s_gp / s_gl if s_gl > 0 else 99.99

        reasons = sub['exit_reason'].value_counts()
        total_exit = len(sub)
        tp_n = reasons.get('tp', 0)
        sl_n = reasons.get('sl', 0)
        exp_n = reasons.get('expire', 0)

        lines.append(f"| {zone} | {len(s_pnl)} | {_f4(s_pnl.mean())} | {_f4(s_pnl.median())} | "
                     f"{s_win/len(s_pnl):.1%} | {s_pf:.2f} | "
                     f"{tp_n/total_exit:.0%} | {sl_n/total_exit:.0%} | {exp_n/total_exit:.0%} |")
    lines.append("")

    # 按 DD Tier 分组
    lines.append("## 四、按回调深度分组表现\n")
    lines.append("| DD Tier | 交易数 | avg PnL | 胜率 | PF |")
    lines.append("|---------|--------|---------|------|------|")
    for tier in DRAWDOWN_LABELS:
        sub = simulated[simulated['dd_tier'] == tier]
        if len(sub) == 0:
            continue
        s_pnl = sub['pnl'].dropna()
        if len(s_pnl) == 0:
            continue
        s_win = (s_pnl > 0).sum()
        s_gp = float(s_pnl[s_pnl > 0].sum()) if s_win > 0 else 0
        s_gl = abs(float(s_pnl[s_pnl < 0].sum())) if (s_pnl < 0).sum() > 0 else 0.001
        s_pf = s_gp / s_gl if s_gl > 0 else 99.99
        lines.append(f"| {tier} | {len(s_pnl)} | {_f4(s_pnl.mean())} | "
                     f"{s_win/len(s_pnl):.1%} | {s_pf:.2f} |")
    lines.append("")

    # 位置假设验证
    lines.append("## 五、位置假设验证\n")
    lines.append("| 假设 | Zone | 预期 | 实际 | 判定 |")
    lines.append("|------|------|------|------|------|")

    for zone in ['abyss_bottom', 'bottom_start', 'main_wave']:
        sub = simulated[simulated['zone_tag'] == zone]
        if len(sub) == 0:
            lines.append(f"| avg_pnl > 0 | {zone} | 正收益 | 无交易 | FAIL |")
            continue
        avg = sub['pnl'].mean()
        lines.append(f"| avg_pnl > 0 | {zone} | 正收益 | {_f4(avg)} | "
                     f"{'PASS' if avg > 0 else 'FAIL'} |")

    ht_sub = simulated[simulated['zone_tag'] == 'high_trap']
    lines.append(f"| 无交易 | high_trap | 0 笔 | {len(ht_sub)} 笔 | "
                 f"{'PASS' if len(ht_sub) == 0 else 'FAIL'} |")
    lines.append("")

    # 验收标准
    lines.append("## 六、验收标准\n")
    lines.append("| 标准 | 要求 | 实际 | 判定 |")
    lines.append("|------|------|------|------|")
    lines.append(f"| 交易量 | >= 100 笔 | {len(pnl)} 笔 | "
                 f"{'PASS' if len(pnl) >= 100 else 'FAIL'} |")
    lines.append(f"| 胜率 | >= 40% | {win/len(pnl):.1%} | "
                 f"{'PASS' if win/len(pnl) >= 0.40 else 'FAIL'} |")
    lines.append(f"| PF | >= 1.5 | {pf:.2f} | "
                 f"{'PASS' if pf >= 1.5 else 'FAIL'} |")

    abyss_sub = simulated[simulated['zone_tag'].isin(['abyss_bottom', 'bottom_start'])]
    if len(abyss_sub) > 0:
        abyss_avg = abyss_sub['pnl'].mean()
        lines.append(f"| 底部 avg_pnl | > 0 | {_f4(abyss_avg)} | "
                     f"{'PASS' if abyss_avg > 0 else 'FAIL'} |")
    else:
        lines.append("| 底部 avg_pnl | > 0 | 无交易 | FAIL |")

    mw_sub = simulated[simulated['zone_tag'] == 'main_wave']
    if len(mw_sub) > 0:
        mw_avg = mw_sub['pnl'].mean()
        lines.append(f"| 主升浪 avg_pnl | > 0 | {_f4(mw_avg)} | "
                     f"{'PASS' if mw_avg > 0 else 'FAIL'} |")
    else:
        lines.append("| 主升浪 avg_pnl | > 0 | 无交易 | FAIL |")
    lines.append("")

    with open(BACKTEST_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"    已写入 {BACKTEST_MD}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  v5 位置驱动状态机回测系统")
    print("=" * 70)

    os.makedirs(DOC_DIR_V5, exist_ok=True)

    # 加载信号
    df_signals = pd.read_csv(REVIEW4_CSV)
    df_signals['t0_date'] = pd.to_datetime(df_signals['t0_date'])
    print(f"  加载信号: {len(df_signals)} 笔")

    t_start = time.time()

    # Step 0
    tags_df = step0_signal_tagger(df_signals)
    tags_df.to_csv(TAGS_CSV, index=False, encoding='utf-8-sig')
    print(f"    已保存 {TAGS_CSV}")

    # Step 1
    merged_df = step1_merge_path(tags_df)

    # Step 2
    stats_df, param_df = step2_cross_tab(merged_df)

    # Step 3
    bt_df = step3_state_machine_backtest(merged_df, param_df)

    # Step 4
    print("\n  [Step 4] 生成报告...")
    generate_analysis_report(tags_df, stats_df, param_df)
    generate_backtest_report(bt_df, df_signals)

    total_elapsed = time.time() - t_start
    print(f"\n  全部完成, 总耗时 {total_elapsed:.1f}s")


if __name__ == '__main__':
    main()
