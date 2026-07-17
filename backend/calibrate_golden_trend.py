#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
金钻趋势公式校准: 固定参数网格搜索 + 个股自适应参数

两种模式:
  1. 固定参数: 网格搜索 120 组合，找全局最优
  2. 自适应参数: 基于 T0 前 250 天历史特征，逐笔动态计算 N/K/offset

评价指标:
  - 覆盖率 (coverage): actual_bottom >= Golden_Trend_T0 的信号占比
  - 平均距离 (mean_dist): (actual_bottom - GT_T0) / GT_T0 均值
  - 下穿率 (penetration_rate): actual_bottom < GT_T0 的占比
  - 下穿深度 (mean_penetration): 下穿时的平均跌幅
  - 综合得分: coverage * 0.5 + (1 - min(abs(mean_dist), 1)) * 0.3 - mean_penetration * 0.2

输出:
  - doc/0616_super_trend_V3/golden_trend_calibration.csv (固定参数网格结果)
  - doc/0616_super_trend_V3/adaptive_golden_trend.csv (自适应参数结果)
  - doc/0616_super_trend_V3/golden_trend_calibration_report.md
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
from itertools import product

import data_loader
from golden_trend import (
    calc_golden_trend, calc_adaptive_n, calc_adaptive_k,
    calc_adaptive_offset, calc_channel_ratio, calc_ema_rails,
)

DOC_DIR = os.path.join(_PROJECT_ROOT, 'doc', '0616_super_trend_V3')
DOC_DIR_V4 = os.path.join(_PROJECT_ROOT, 'doc', '0613_super_trend_v2')
REVIEW4_CSV = os.path.join(DOC_DIR_V4, 'review4_final_backtest.csv')
PATH_V42_CSV = os.path.join(DOC_DIR_V4, 'path_analysis_v42.csv')
FIXED_CSV = os.path.join(DOC_DIR, 'golden_trend_calibration.csv')
ADAPTIVE_CSV = os.path.join(DOC_DIR, 'adaptive_golden_trend.csv')
REPORT_MD = os.path.join(DOC_DIR, 'golden_trend_calibration_report.md')

LOOKBACK_DAYS = 400
MIN_PRE_BARS = 120

PARAM_GRID = {
    'n': [10, 15, 20, 25, 30],
    'double_smooth': [True, False],
    'k': [0.5, 1.0, 1.5],
    'offset_coef': [0.95, 0.98, 1.0, 1.02],
}




# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------
def load_daily_for_signal(stock: str, t0_date) -> pd.DataFrame:
    data = data_loader.get_multi_timeframe_data(stock)
    if not data or not data['data_status']['daily_available']:
        return None
    dfd = data['daily_data']
    cutoff = pd.Timestamp(t0_date)
    start = cutoff - pd.Timedelta(days=LOOKBACK_DAYS)
    pre = dfd[(dfd.index >= start) & (dfd.index <= cutoff)]
    if len(pre) < MIN_PRE_BARS:
        return None
    return pre[['open', 'high', 'low', 'close', 'volume']].copy()


def load_hourly_for_signal(stock: str, t0_date) -> pd.DataFrame:
    """加载 60m K线 (不聚合到日线), ~4 bars/天 × 400天 ≈ 1600 bars"""
    start = (pd.Timestamp(t0_date) - pd.Timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%d')
    end = pd.Timestamp(t0_date).strftime('%Y-%m-%d')
    try:
        df_60m = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        df_60m = None
    if df_60m is None or df_60m.empty:
        return None
    df = df_60m.copy()
    if 'datetime' in df.columns:
        df = df.set_index(pd.to_datetime(df['datetime']))
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index, errors='coerce')
    cutoff = pd.Timestamp(t0_date) + pd.Timedelta(hours=16)
    df = df[df.index <= cutoff]
    df = df.dropna(subset=['open'])
    df = df[df['open'] > 0]
    if len(df) < MIN_PRE_BARS * 2:
        return None
    return df[['open', 'high', 'low', 'close', 'volume']].copy()



def load_signals_with_bottom() -> pd.DataFrame:
    df_signals = pd.read_csv(REVIEW4_CSV)
    df_signals['t0_date'] = pd.to_datetime(df_signals['t0_date'])
    path_df = pd.read_csv(PATH_V42_CSV)
    path_df['t0_date'] = pd.to_datetime(path_df['t0_date'])
    merged = df_signals.merge(
        path_df[['signal_idx', 'entry_price', 'max_drawdown']],
        on='signal_idx', how='left',
        suffixes=('_review', '_path')
    )
    merged['entry_price'] = merged['entry_price_path'].fillna(merged['entry_price_review'])
    merged = merged.dropna(subset=['entry_price', 'max_drawdown'])
    merged['actual_bottom'] = merged['entry_price'] * (1 + merged['max_drawdown'])
    return merged


# ---------------------------------------------------------------------------
# Part 1: 固定参数网格搜索
# ---------------------------------------------------------------------------
def run_fixed_grid_search(merged: pd.DataFrame, cache: dict) -> pd.DataFrame:
    print("\n  [Part 1] 固定参数网格搜索...")

    signal_data = []
    for _, row in merged.iterrows():
        key = (row['stock_code'], row['t0_date'])
        daily = cache.get(key)
        if daily is None:
            continue
        signal_data.append({
            'high': daily['high'].values.astype(float),
            'low': daily['low'].values.astype(float),
            'actual_bottom': row['actual_bottom'],
            'entry_price': row['entry_price'],
        })
    print(f"    有效信号: {len(signal_data)}")

    param_combos = list(product(
        PARAM_GRID['n'], PARAM_GRID['double_smooth'],
        PARAM_GRID['k'], PARAM_GRID['offset_coef']
    ))
    print(f"    搜索 {len(param_combos)} 组合...")

    t0 = time.time()
    results = []
    for ci, (n, double_smooth, k, offset_coef) in enumerate(param_combos):
        if (ci + 1) % 20 == 0:
            print(f"    {ci+1}/{len(param_combos)}...")

        dists = []
        pens = []
        cov = 0
        for sd in signal_data:
            gt = calc_golden_trend(
                pd.Series(sd['high']), pd.Series(sd['low']),
                n, double_smooth, k, offset_coef
            )
            gt_t0 = float(gt.iloc[-1])
            if gt_t0 <= 0:
                continue
            d = (sd['actual_bottom'] - gt_t0) / gt_t0
            dists.append(d)
            if sd['actual_bottom'] >= gt_t0:
                cov += 1
            else:
                pens.append(abs(d))

        valid = len(dists)
        if valid < 100:
            continue

        coverage = cov / valid
        mean_dist = np.mean(dists)
        median_dist = np.median(dists)
        mean_pen = np.mean(pens) if pens else 0.0
        pen_rate = len(pens) / valid
        score = coverage * 0.5 + (1 - min(abs(mean_dist), 1)) * 0.3 - mean_pen * 0.2

        results.append({
            'n': n, 'double_smooth': double_smooth,
            'k': k, 'offset_coef': offset_coef,
            'valid_signals': valid,
            'coverage': round(coverage, 4),
            'mean_dist': round(mean_dist, 4),
            'median_dist': round(median_dist, 4),
            'mean_penetration': round(mean_pen, 4),
            'penetration_rate': round(pen_rate, 4),
            'score': round(score, 4),
        })

    elapsed = time.time() - t0
    result_df = pd.DataFrame(results).sort_values('score', ascending=False)
    result_df.to_csv(FIXED_CSV, index=False, encoding='utf-8-sig')
    print(f"    完成, 耗时 {elapsed:.1f}s, 已保存 {FIXED_CSV}")
    return result_df


# ---------------------------------------------------------------------------
# Part 2: 个股自适应参数
# ---------------------------------------------------------------------------
def _search_best_on_bars(h, l, actual_bottom, param_combos):
    """在给定 high/low 序列上搜索最优参数组合, 返回 (best_abs_dist, best_params, best_gt_t0)"""
    best_abs_dist = float('inf')
    best_params = None
    best_gt_t0 = None
    for n, ds, k, offset in param_combos:
        gt = calc_golden_trend(h, l, n=n, double_smooth=ds, k=k, offset_coef=offset)
        gt_t0 = float(gt.iloc[-1])
        if gt_t0 <= 0:
            continue
        abs_dist = abs(gt_t0 - actual_bottom) / actual_bottom
        if abs_dist < best_abs_dist:
            best_abs_dist = abs_dist
            best_params = (n, ds, k, offset)
            best_gt_t0 = gt_t0
    return best_abs_dist, best_params, best_gt_t0


def run_adaptive_calibration(merged: pd.DataFrame, daily_cache: dict,
                              hourly_cache: dict) -> pd.DataFrame:
    print("\n  [Part 2] 双轨校准搜索 (日线 + 小时线)...")

    param_combos = list(product(
        PARAM_GRID['n'], PARAM_GRID['double_smooth'],
        PARAM_GRID['k'], PARAM_GRID['offset_coef']
    ))

    results = []
    n_ok = n_skip = n_hourly_only = n_daily_only = n_both = n_hourly_wins = 0
    t0 = time.time()

    for i, (idx, row) in enumerate(merged.iterrows()):
        if (i + 1) % 500 == 0:
            print(f"    {i+1}/{len(merged)}...")

        key = (row['stock_code'], row['t0_date'])
        daily = daily_cache.get(key)
        hourly = hourly_cache.get(key)
        actual_bottom = row['actual_bottom']
        if actual_bottom <= 0:
            n_skip += 1
            continue

        # 日线搜索
        daily_abs_dist = float('inf')
        daily_params = None
        daily_gt_t0 = None
        daily_overlap = False
        if daily is not None:
            dh = daily['high'].reset_index(drop=True)
            dl = daily['low'].reset_index(drop=True)
            daily_abs_dist, daily_params, daily_gt_t0 = _search_best_on_bars(
                dh, dl, actual_bottom, param_combos)
            if daily_params:
                daily_overlap = calc_channel_ratio(dh, dl, daily_params[0], daily_params[1]) < 0.02

        # 小时线搜索
        hourly_abs_dist = float('inf')
        hourly_params = None
        hourly_gt_t0 = None
        if hourly is not None:
            hh = hourly['high'].reset_index(drop=True)
            hl = hourly['low'].reset_index(drop=True)
            hourly_abs_dist, hourly_params, hourly_gt_t0 = _search_best_on_bars(
                hh, hl, actual_bottom, param_combos)

        # 取最优
        if daily_params is None and hourly_params is None:
            n_skip += 1
            continue

        if hourly_abs_dist < daily_abs_dist:
            best_tf = 'hourly'
            best_abs_dist = hourly_abs_dist
            best_params = hourly_params
            best_gt_t0 = hourly_gt_t0
            n_hourly_wins += 1
        else:
            best_tf = 'daily'
            best_abs_dist = daily_abs_dist
            best_params = daily_params
            best_gt_t0 = daily_gt_t0

        n_best, ds_best, k_best, off_best = best_params
        dist_pct = (actual_bottom - best_gt_t0) / best_gt_t0
        covered = actual_bottom >= best_gt_t0

        # 固定参数对照 (日线)
        fixed_gt_t0 = np.nan
        fixed_abs_dist = np.nan
        fixed_dist = np.nan
        fixed_covered = False
        if daily is not None:
            gt_fixed = calc_golden_trend(dh, dl, n=25, double_smooth=True, k=1.0, offset_coef=1.0)
            fixed_gt_t0 = float(gt_fixed.iloc[-1])
            if fixed_gt_t0 > 0:
                fixed_dist = (actual_bottom - fixed_gt_t0) / fixed_gt_t0
                fixed_abs_dist = abs(fixed_gt_t0 - actual_bottom) / actual_bottom
                fixed_covered = actual_bottom >= fixed_gt_t0

        if daily is not None and hourly is not None:
            n_both += 1
        elif hourly is not None:
            n_hourly_only += 1
        else:
            n_daily_only += 1

        results.append({
            'signal_idx': idx,
            'stock_code': row['stock_code'],
            't0_date': row['t0_date'],
            'actual_bottom': actual_bottom,
            'entry_price': row['entry_price'],
            'best_timeframe': best_tf,
            'best_n': n_best,
            'best_double_smooth': ds_best,
            'best_k': k_best,
            'best_offset': off_best,
            'best_gt_t0': round(best_gt_t0, 4),
            'best_abs_dist_pct': round(best_abs_dist, 4),
            'best_dist_pct': round(dist_pct, 4),
            'best_covered': covered,
            'daily_rail_overlap': daily_overlap,
            'daily_best_abs_dist_pct': round(daily_abs_dist, 4) if daily_abs_dist < float('inf') else np.nan,
            'hourly_best_abs_dist_pct': round(hourly_abs_dist, 4) if hourly_abs_dist < float('inf') else np.nan,
            'fixed_gt_t0': round(fixed_gt_t0, 4) if not np.isnan(fixed_gt_t0) else np.nan,
            'fixed_abs_dist_pct': round(fixed_abs_dist, 4) if not np.isnan(fixed_abs_dist) else np.nan,
            'fixed_dist_pct': round(fixed_dist, 4) if not np.isnan(fixed_dist) else np.nan,
            'fixed_covered': fixed_covered,
        })
        n_ok += 1

    elapsed = time.time() - t0
    result_df = pd.DataFrame(results)
    result_df.to_csv(ADAPTIVE_CSV, index=False, encoding='utf-8-sig')
    print(f"    完成: {n_ok} OK, {n_skip} skip, 耗时 {elapsed:.1f}s")
    print(f"    双轨可用: {n_both}, 仅日线: {n_daily_only}, 仅小时线: {n_hourly_only}")
    print(f"    小时线胜出: {n_hourly_wins} ({n_hourly_wins/max(n_ok,1):.1%})")
    print(f"    已保存 {ADAPTIVE_CSV}")
    return result_df


# ---------------------------------------------------------------------------
# Part 3: 对比报告
# ---------------------------------------------------------------------------
def generate_report(fixed_df: pd.DataFrame, adaptive_df: pd.DataFrame):
    lines = []
    lines.append("# 金钻趋势公式校准报告\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")

    # === 固定参数 Top 15 ===
    lines.append("## 一、固定参数网格搜索 Top 15\n")
    lines.append("| # | N | 双平滑 | k | offset | 覆盖率 | 平均距离 | 中位距离 | 下穿率 | 下穿深度 | 得分 |")
    lines.append("|---|---|--------|---|--------|--------|---------|---------|--------|---------|------|")
    for i, (_, r) in enumerate(fixed_df.head(15).iterrows()):
        lines.append(f"| {i+1} | {r['n']} | {'Yes' if r['double_smooth'] else 'No'} | "
                     f"{r['k']} | {r['offset_coef']} | "
                     f"{r['coverage']:.2%} | {r['mean_dist']:.2%} | {r['median_dist']:.2%} | "
                     f"{r['penetration_rate']:.2%} | {r['mean_penetration']:.2%} | "
                     f"{r['score']:.4f} |")
    lines.append("")

    # 原始参数
    orig = fixed_df[(fixed_df['n'] == 25) & (fixed_df['double_smooth'] == True) &
                    (fixed_df['k'] == 1.0) & (fixed_df['offset_coef'] == 1.0)]
    if len(orig) > 0:
        o = orig.iloc[0]
        best = fixed_df.iloc[0]
        lines.append("**原始参数** (N=25, 双平滑, k=1.0, offset=1.0):\n")
        lines.append(f"- 覆盖率: {o['coverage']:.2%}, 平均距离: {o['mean_dist']:.2%}, "
                     f"下穿率: {o['penetration_rate']:.2%}, 得分: {o['score']:.4f}\n")
        lines.append(f"**全局最优** (N={int(best['n'])}, ds={'Yes' if best['double_smooth'] else 'No'}, "
                     f"k={best['k']}, offset={best['offset_coef']}):\n")
        lines.append(f"- 覆盖率: {best['coverage']:.2%}, 平均距离: {best['mean_dist']:.2%}, "
                     f"下穿率: {best['penetration_rate']:.2%}, 得分: {best['score']:.4f}\n")
    lines.append("")

    # === 校准后偏差分析 ===
    lines.append("## 二、校准后 GT_T0 vs 操作周期底部 (T+1~T+22) 偏差\n")

    n_total = len(adaptive_df)
    d = adaptive_df['best_dist_pct']          # (actual - GT) / GT, 有方向
    abs_d = adaptive_df['best_abs_dist_pct']  # |actual - GT| / actual
    d_fixed = adaptive_df['fixed_dist_pct']
    abs_d_fixed = adaptive_df['fixed_abs_dist_pct']

    lines.append(f"**信号数**: {n_total}\n")
    lines.append("### 2.1 偏差概览 (校准后)\n")
    lines.append("| 指标 | 校准后 | 固定参数 (N=25) |")
    lines.append("|------|--------|---------------|")
    lines.append(f"| 平均绝对偏差 | {abs_d.mean():.2%} | {abs_d_fixed.mean():.2%} |")
    lines.append(f"| 中位绝对偏差 | {abs_d.median():.2%} | {abs_d_fixed.median():.2%} |")
    lines.append(f"| P10 | {abs_d.quantile(0.10):.2%} | {abs_d_fixed.quantile(0.10):.2%} |")
    lines.append(f"| P25 | {abs_d.quantile(0.25):.2%} | {abs_d_fixed.quantile(0.25):.2%} |")
    lines.append(f"| P50 | {abs_d.quantile(0.50):.2%} | {abs_d_fixed.quantile(0.50):.2%} |")
    lines.append(f"| P75 | {abs_d.quantile(0.75):.2%} | {abs_d_fixed.quantile(0.75):.2%} |")
    lines.append(f"| P90 | {abs_d.quantile(0.90):.2%} | {abs_d_fixed.quantile(0.90):.2%} |")
    lines.append("")

    # 方向性: GT 偏高(actual < GT) vs 偏低(actual > GT)
    gt_high = (d < 0).sum()   # GT > actual, 网格底高于实际底 → 网格偏保守
    gt_low = (d > 0).sum()    # GT < actual, 网格底低于实际底 → 网格偏宽松
    gt_match = (d == 0).sum()
    lines.append("### 2.2 偏差方向\n")
    lines.append("| 方向 | 信号数 | 占比 | 含义 |")
    lines.append("|------|--------|------|------|")
    lines.append(f"| GT_T0 > 实际底部 | {gt_high} | {gt_high/n_total:.1%} | 网格偏高，实际底更低 |")
    lines.append(f"| GT_T0 < 实际底部 | {gt_low} | {gt_low/n_total:.1%} | 网格偏低，实际底更高 |")
    lines.append(f"| 完全匹配 | {gt_match} | {gt_match/n_total:.1%} | |")
    lines.append(f"| 平均偏差方向 | {d.mean():+.2%} | | {'偏保守' if d.mean() < 0 else '偏宽松'} |")
    lines.append("")

    # 偏差分桶
    lines.append("### 2.3 偏差分桶\n")
    lines.append("| 偏差范围 | 信号数 | 占比 | 累计占比 |")
    lines.append("|----------|--------|------|---------|")
    bins = [0, 0.01, 0.02, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20, 1.0]
    cum = 0
    for i in range(len(bins) - 1):
        lo, hi = bins[i], bins[i + 1]
        cnt = ((abs_d >= lo) & (abs_d < hi)).sum()
        cum += cnt
        label = f"{lo:.0%}~{hi:.0%}" if hi < 1.0 else f"≥{lo:.0%}"
        lines.append(f"| {label} | {cnt} | {cnt/n_total:.1%} | {cum/n_total:.1%} |")
    lines.append("")

    # === 双轨对比: 日线 vs 小时线 ===
    if 'best_timeframe' in adaptive_df.columns:
        lines.append("### 2.4 双轨对比 (日线 vs 小时线)\n")

        tf_counts = adaptive_df['best_timeframe'].value_counts()
        n_daily_wins = tf_counts.get('daily', 0)
        n_hourly_wins = tf_counts.get('hourly', 0)

        lines.append("| 胜出时间框架 | 信号数 | 占比 |")
        lines.append("|-------------|--------|------|")
        lines.append(f"| 日线 | {n_daily_wins} | {n_daily_wins/n_total:.1%} |")
        lines.append(f"| 小时线 | {n_hourly_wins} | {n_hourly_wins/n_total:.1%} |")
        lines.append("")

        # Rail overlap 统计
        overlap_mask = adaptive_df['daily_rail_overlap'] == True
        n_overlap = overlap_mask.sum()
        lines.append(f"**日线双轨重叠** (通道宽度<2%): {n_overlap} 笔 ({n_overlap/n_total:.1%})\n")

        if n_overlap > 0:
            overlap_df = adaptive_df[overlap_mask]
            d_overlap = overlap_df['daily_best_abs_dist_pct']
            h_overlap = overlap_df['hourly_best_abs_dist_pct']
            h_valid = h_overlap.dropna()
            lines.append("**重叠信号中, 小时线改善情况**:\n")
            lines.append("| 指标 | 日线最优偏差 | 小时线最优偏差 |")
            lines.append("|------|------------|--------------|")
            lines.append(f"| 平均 | {d_overlap.mean():.2%} | {h_valid.mean():.2%} |")
            lines.append(f"| 中位 | {d_overlap.median():.2%} | {h_valid.median():.2%} |")
            improved = (h_valid < overlap_df.loc[h_valid.index, 'daily_best_abs_dist_pct']).sum()
            lines.append(f"| 小时线改善占比 | | {improved/len(h_valid):.1%} |")
            lines.append("")

        # 两者都有数据的信号: 对比
        both_mask = adaptive_df['daily_best_abs_dist_pct'].notna() & adaptive_df['hourly_best_abs_dist_pct'].notna()
        if both_mask.sum() > 0:
            both_df = adaptive_df[both_mask]
            d_avg = both_df['daily_best_abs_dist_pct'].mean()
            h_avg = both_df['hourly_best_abs_dist_pct'].mean()
            d_med = both_df['daily_best_abs_dist_pct'].median()
            h_med = both_df['hourly_best_abs_dist_pct'].median()
            lines.append("**双轨均可用的信号**:\n")
            lines.append("| 指标 | 日线最优 | 小时线最优 | 差异 |")
            lines.append("|------|---------|----------|------|")
            lines.append(f"| 平均偏差 | {d_avg:.2%} | {h_avg:.2%} | {h_avg-d_avg:+.2%} |")
            lines.append(f"| 中位偏差 | {d_med:.2%} | {h_med:.2%} | {h_med-d_med:+.2%} |")
            lines.append("")

    # === 按 Zone 分层 ===
    tags_csv = os.path.join(DOC_DIR, 'signal_tags_v5.csv')
    if os.path.exists(tags_csv):
        tags = pd.read_csv(tags_csv)
        tags['t0_date'] = pd.to_datetime(tags['t0_date'])
        adf = adaptive_df.merge(
            tags[['signal_idx', 'zone_tag', 'position_ratio']],
            on='signal_idx', how='left'
        )

        lines.append("## 三、按 Zone 分层偏差\n")
        lines.append("| Zone | n | 校准后 avg |GT-底| | 固定 avg |GT-底| | 中位偏差 | P75 | 小时线胜出% | 双轨重叠% |")
        lines.append("|------|---|-------------------|-------------------|---------|------|-----------|----------|")
        for zone in ['abyss_bottom', 'bottom_start', 'main_wave', 'high_zone', 'high_trap']:
            sub = adf[adf['zone_tag'] == zone]
            if len(sub) == 0:
                continue
            ba = sub['best_abs_dist_pct'].mean()
            fa = sub['fixed_abs_dist_pct'].mean()
            bm = sub['best_abs_dist_pct'].median()
            bp75 = sub['best_abs_dist_pct'].quantile(0.75)
            h_win = (sub['best_timeframe'] == 'hourly').mean() if 'best_timeframe' in sub.columns else 0
            overlap = sub['daily_rail_overlap'].mean() if 'daily_rail_overlap' in sub.columns else 0
            lines.append(f"| {zone} | {len(sub)} | {ba:.2%} | {fa:.2%} | {bm:.2%} | {bp75:.2%} | {h_win:.0%} | {overlap:.0%} |")
        lines.append("")

    # === 结论 ===
    lines.append("## 四、结论\n")
    lines.append(f"- 校准后，GT_T0 与操作周期(T+1~T+22)实际底部的中位偏差为 **{abs_d.median():.2%}**")
    lines.append(f"- P75 偏差为 **{abs_d.quantile(0.75):.2%}**，即 75% 的信号偏差在此范围内")
    lines.append(f"- 固定参数(N=25)中位偏差为 {abs_d_fixed.median():.2%}，校准改善 {abs_d_fixed.median() - abs_d.median():.2%}")
    lines.append("")

    within_5pct = (abs_d <= 0.05).sum()
    within_3pct = (abs_d <= 0.03).sum()
    lines.append(f"- 偏差 ≤3%: {within_3pct} 笔 ({within_3pct/n_total:.1%})")
    lines.append(f"- 偏差 ≤5%: {within_5pct} 笔 ({within_5pct/n_total:.1%})")
    lines.append("")
    lines.append("**判断**: 若校准后中位偏差足够小(如 ≤5%)，说明 Golden Trend 公式在合适的参数下")
    lines.append("能够使网格底部与操作周期内实际底部对齐，可作为 v5 状态机的支撑参考价。\n")
    lines.append("")

    with open(REPORT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"    已写入 {REPORT_MD}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  金钻趋势公式校准: 固定参数 + 双轨(日线+小时线)最优搜索")
    print("=" * 70)

    os.makedirs(DOC_DIR, exist_ok=True)

    # 加载信号
    merged = load_signals_with_bottom()
    print(f"  有效信号: {len(merged)} 笔")

    unique_pairs = merged[['stock_code', 't0_date']].drop_duplicates()

    # 预加载日线数据
    print("\n  [Step 0a] 预加载日线数据...")
    daily_cache = {}
    t0 = time.time()
    for i, (_, row) in enumerate(unique_pairs.iterrows()):
        if (i + 1) % 200 == 0:
            print(f"    {i+1}/{len(unique_pairs)}...")
        key = (row['stock_code'], row['t0_date'])
        daily = load_daily_for_signal(row['stock_code'], row['t0_date'])
        if daily is not None:
            daily_cache[key] = daily
    elapsed = time.time() - t0
    print(f"    日线缓存 {len(daily_cache)} 组, 耗时 {elapsed:.1f}s")

    # 预加载小时线数据
    print("\n  [Step 0b] 预加载小时线(60m)数据...")
    hourly_cache = {}
    t0 = time.time()
    for i, (_, row) in enumerate(unique_pairs.iterrows()):
        if (i + 1) % 200 == 0:
            print(f"    {i+1}/{len(unique_pairs)}...")
        key = (row['stock_code'], row['t0_date'])
        hourly = load_hourly_for_signal(row['stock_code'], row['t0_date'])
        if hourly is not None:
            hourly_cache[key] = hourly
    elapsed = time.time() - t0
    print(f"    小时线缓存 {len(hourly_cache)} 组, 耗时 {elapsed:.1f}s")

    # Part 1: 固定参数网格搜索 (日线)
    fixed_df = run_fixed_grid_search(merged, daily_cache)

    # Part 2: 双轨校准搜索
    adaptive_df = run_adaptive_calibration(merged, daily_cache, hourly_cache)

    # Part 3: 对比报告
    print("\n  [Part 3] 生成对比报告...")
    generate_report(fixed_df, adaptive_df)

    print("\n  全部完成!")


if __name__ == '__main__':
    main()
