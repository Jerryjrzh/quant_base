"""分析 GT、入场价、实际底部的比例关系。

对每笔成交信号，在 T+0~T+21 前瞻窗口内计算:
  - GT at entry (入场日 GT 下轨)
  - entry_price (入场收盘价)
  - actual_bottom (前瞻窗口内最低价)
  - 三者比例关系
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from path_analysis_v5_gt import (
    _load_forward_daily,
    _compute_gt_on_combined, FUTURE_DAYS,
)
from path_analysis_v5 import (
    _load_pre_signal_daily_60m,
    _load_pre_signal_daily_fallback,
    ZONE_ORDER, DRAWDOWN_BINS, DRAWDOWN_LABELS,
)

DOC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'doc', '0616_super_trend_V3')


def main():
    bt_csv = os.path.join(DOC_DIR, 'state_machine_backtest_v5_gt.csv')
    bt_df = pd.read_csv(bt_csv)
    traded = bt_df[bt_df['status'] == 'simulated'].copy()
    print(f'成交信号: {len(traded)} 笔')

    rows = []
    for _, sig in traded.iterrows():
        idx = int(sig['signal_idx'])
        code = sig['stock_code']
        t0 = pd.Timestamp(sig['t0_date'])
        entry_day = int(sig['entry_day_idx']) if not np.isnan(sig['entry_day_idx']) else -1
        if entry_day < 0:
            continue

        daily_fwd = _load_forward_daily(code, t0)
        if daily_fwd is None or daily_fwd.empty:
            continue

        daily_pre = _load_pre_signal_daily_60m(code, t0)
        if daily_pre is None or daily_pre.empty:
            daily_pre = _load_pre_signal_daily_fallback(code, t0)

        n = min(len(daily_fwd), FUTURE_DAYS)
        fwd_slice = daily_fwd.iloc[:n]

        entry_price = sig['actual_entry_price']
        gt_at_entry = sig['gt_at_entry']

        fwd_lows = fwd_slice['low'].values
        fwd_closes = fwd_slice['close'].values

        actual_bottom = float(np.min(fwd_lows))
        bottom_day = int(np.argmin(fwd_lows))

        bottom_to_entry = (actual_bottom - entry_price) / entry_price
        bottom_to_gt = (actual_bottom - gt_at_entry) / gt_at_entry if gt_at_entry > 0 else np.nan
        gt_to_entry = (gt_at_entry - entry_price) / entry_price if entry_price > 0 else np.nan
        gt_ratio = gt_at_entry / entry_price if entry_price > 0 else np.nan

        rows.append({
            'signal_idx': idx,
            'stock_code': code,
            't0_date': str(t0.date()),
            'zone_tag': sig['zone_tag'],
            'dd_tier': sig['dd_tier'],
            'entry_day': entry_day,
            'entry_price': round(entry_price, 4),
            'gt_at_entry': round(gt_at_entry, 4),
            'gt_ratio': round(gt_ratio, 4),
            'gt_to_entry_pct': round(gt_to_entry * 100, 2),
            'actual_bottom': round(actual_bottom, 4),
            'bottom_day': bottom_day,
            'bottom_to_entry_pct': round(bottom_to_entry * 100, 2),
            'bottom_to_gt_pct': round(bottom_to_gt * 100, 2),
            'exit_reason': sig['exit_reason'],
            'pnl': sig['pnl'],
        })

    result_df = pd.DataFrame(rows)
    out_csv = os.path.join(DOC_DIR, 'gt_vs_bottom_analysis.csv')
    result_df.to_csv(out_csv, index=False)
    print(f'已保存 {out_csv} ({len(result_df)} 笔)')
    print()

    if len(result_df) == 0:
        print('无数据')
        return

    print('=' * 70)
    print('  GT vs 入场价 vs 实际底部 比例分析')
    print('=' * 70)

    print('\n## 1. 整体统计\n')
    print(f'  样本: {len(result_df)} 笔')
    print()

    for col, label in [
        ('gt_ratio', 'GT/Entry (GT是入场价的倍数)'),
        ('gt_to_entry_pct', 'GT相对入场价偏移%'),
        ('bottom_to_entry_pct', '实际底部相对入场价偏移%'),
        ('bottom_to_gt_pct', '实际底部相对GT偏移%'),
    ]:
        vals = result_df[col].dropna()
        print(f'  {label}:')
        print(f'    median={vals.median():.4f}, mean={vals.mean():.4f}, '
              f'std={vals.std():.4f}')
        print(f'    min={vals.min():.4f}, 25%={vals.quantile(0.25):.4f}, '
              f'50%={vals.quantile(0.5):.4f}, 75%={vals.quantile(0.75):.4f}, '
              f'max={vals.max():.4f}')
        print()

    print('\n## 2. GT 与入场价的关系\n')
    gt_above = (result_df['gt_ratio'] > 1.0).sum()
    gt_below = (result_df['gt_ratio'] <= 1.0).sum()
    print(f'  GT > 入场价 (gt_ratio > 1): {gt_above} 笔 ({gt_above/len(result_df):.1%})')
    print(f'  GT < 入场价 (gt_ratio < 1): {gt_below} 笔 ({gt_below/len(result_df):.1%})')
    print()

    for lo, hi, label in [(0, 0.8, 'GT < 80% Entry'), (0.8, 0.95, 'GT 80~95%'),
                           (0.95, 1.05, 'GT ≈ Entry (95~105%)'),
                           (1.05, 1.2, 'GT 105~120%'), (1.2, 99, 'GT > 120%')]:
        mask = (result_df['gt_ratio'] >= lo) & (result_df['gt_ratio'] < hi)
        sub = result_df[mask]
        if len(sub) > 0:
            print(f'  {label}: {len(sub)} 笔, avg bottom_to_entry={sub["bottom_to_entry_pct"].mean():.2f}%, '
                  f'avg bottom_to_gt={sub["bottom_to_gt_pct"].mean():.2f}%')
    print()

    print('\n## 3. 实际底部 vs GT 的偏差\n')
    within_3 = (result_df['bottom_to_gt_pct'].abs() <= 3).sum()
    within_5 = (result_df['bottom_to_gt_pct'].abs() <= 5).sum()
    within_10 = (result_df['bottom_to_gt_pct'].abs() <= 10).sum()
    below_gt = (result_df['bottom_to_gt_pct'] < 0).sum()
    print(f'  实际底部在 GT ±3% 以内: {within_3} 笔 ({within_3/len(result_df):.1%})')
    print(f'  实际底部在 GT ±5% 以内: {within_5} 笔 ({within_5/len(result_df):.1%})')
    print(f'  实际底部在 GT ±10% 以内: {within_10} 笔 ({within_10/len(result_df):.1%})')
    print(f'  实际底部低于 GT: {below_gt} 笔 ({below_gt/len(result_df):.1%})')
    print()

    print('\n## 4. 按 Zone 分析\n')
    for zone in ['abyss_bottom', 'bottom_start', 'main_wave', 'high_zone']:
        sub = result_df[result_df['zone_tag'] == zone]
        if len(sub) == 0:
            continue
        print(f'  [{zone}] {len(sub)} 笔')
        print(f'    GT/Entry: median={sub["gt_ratio"].median():.4f}, mean={sub["gt_ratio"].mean():.4f}')
        print(f'    GT vs Entry%: median={sub["gt_to_entry_pct"].median():.2f}%')
        print(f'    Bottom vs Entry%: median={sub["bottom_to_entry_pct"].median():.2f}%, mean={sub["bottom_to_entry_pct"].mean():.2f}%')
        print(f'    Bottom vs GT%: median={sub["bottom_to_gt_pct"].median():.2f}%, mean={sub["bottom_to_gt_pct"].mean():.2f}%')
        gt_is_bottom = (sub['bottom_to_gt_pct'].abs() <= 5).mean()
        print(f'    GT ≈ 实际底部 (±5%): {gt_is_bottom:.1%}')
        print()

    print('\n## 5. 按 DD Tier 分析\n')
    for tier in ['0~3%', '3~5%', '5~10%', '10~15%', '15~20%']:
        sub = result_df[result_df['dd_tier'] == tier]
        if len(sub) == 0:
            continue
        print(f'  [{tier}] {len(sub)} 笔')
        print(f'    GT/Entry: median={sub["gt_ratio"].median():.4f}')
        print(f'    Bottom vs Entry%: median={sub["bottom_to_entry_pct"].median():.2f}%')
        print(f'    Bottom vs GT%: median={sub["bottom_to_gt_pct"].median():.2f}%')
        gt_is_bottom = (sub['bottom_to_gt_pct'].abs() <= 5).mean()
        print(f'    GT ≈ 实际底部 (±5%): {gt_is_bottom:.1%}')
        print()

    print('\n## 6. 三者比例散点 (GT > Entry vs GT < Entry)\n')
    gt_above_df = result_df[result_df['gt_ratio'] > 1.0]
    gt_below_df = result_df[result_df['gt_ratio'] <= 1.0]

    if len(gt_above_df) > 0:
        print(f'  GT > Entry ({len(gt_above_df)} 笔):')
        print(f'    entry 平均在 GT 下方 {abs(gt_above_df["gt_to_entry_pct"].mean()):.2f}%')
        print(f'    actual bottom 平均在 entry 下方 {abs(gt_above_df["bottom_to_entry_pct"].mean()):.2f}%')
        print(f'    actual bottom 平均在 GT 下方 {abs(gt_above_df["bottom_to_gt_pct"].mean()):.2f}%')
        print(f'    → GT 高于现价，入场即为"跌破GT"，底部比 GT 低 {abs(gt_above_df["bottom_to_gt_pct"].mean()):.2f}%')
    print()
    if len(gt_below_df) > 0:
        print(f'  GT < Entry ({len(gt_below_df)} 笔):')
        print(f'    entry 平均在 GT 上方 {gt_below_df["gt_to_entry_pct"].mean():.2f}%')
        print(f'    actual bottom 平均在 entry 下方 {abs(gt_below_df["bottom_to_entry_pct"].mean()):.2f}%')
        btm_gt = gt_below_df['bottom_to_gt_pct'].mean()
        if btm_gt < 0:
            print(f'    actual bottom 平均在 GT 下方 {abs(btm_gt):.2f}%')
        else:
            print(f'    actual bottom 平均在 GT 上方 {btm_gt:.2f}%')
        print(f'    → GT 低于现价，价格回调可能触及 GT，GT 作为支撑参考')
    print()

    print('\n## 7. 典型样本 (前 20 笔)\n')
    display_cols = ['stock_code', 't0_date', 'zone_tag', 'entry_price',
                    'gt_at_entry', 'gt_to_entry_pct', 'actual_bottom',
                    'bottom_to_entry_pct', 'bottom_to_gt_pct', 'exit_reason', 'pnl']
    print(result_df[display_cols].head(20).to_string(index=False))


if __name__ == '__main__':
    main()
