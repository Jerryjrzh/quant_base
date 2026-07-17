#!/usr/bin/env python3
"""分析入场日 day_close 与 day_low 的距离关系"""
import os, sys
import pandas as pd
import numpy as np

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _SCRIPT_DIR)

import data_loader
from path_analysis_v5 import _aggregate_60m_to_daily

DOC_DIR = os.path.join(_PROJECT_ROOT, 'doc', '0616_super_trend_V3')
BT_CSV = os.path.join(DOC_DIR, 'state_machine_backtest_v5_gt.csv')
FUTURE_CALENDAR_DAYS = 45


def _load_fwd_daily(stock, t0_date):
    start = (t0_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    end = (t0_date + pd.Timedelta(days=FUTURE_CALENDAR_DAYS)).strftime('%Y-%m-%d')
    try:
        df_60m = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        df_60m = None
    return _aggregate_60m_to_daily(df_60m)


def main():
    bt = pd.read_csv(BT_CSV)
    sim = bt[bt['status'] == 'simulated'].copy()
    print(f"成交信号: {len(sim)} 笔\n")

    rows = []
    for _, r in sim.iterrows():
        stock = r['stock_code']
        t0 = pd.Timestamp(r['t0_date'])
        entry_day = int(r['entry_day_idx'])
        entry_price = r['actual_entry_price']
        gt_at_entry = r['gt_at_entry']
        sl_price = r['sl_price']
        tp_price = r['tp_price']

        daily_fwd = _load_fwd_daily(stock, t0)
        if daily_fwd is None or daily_fwd.empty or entry_day >= len(daily_fwd):
            continue

        day_row = daily_fwd.iloc[entry_day]
        day_open = float(day_row['open'])
        day_high = float(day_row['high'])
        day_low = float(day_row['low'])
        day_close = float(day_row['close'])
        day_range = day_high - day_low

        if day_range <= 0 or entry_price <= 0:
            continue

        close_from_low_pct = (day_close - day_low) / day_low * 100
        close_pos_ratio = (day_close - day_low) / day_range
        entry_vs_low_pct = (entry_price - day_low) / entry_price * 100

        rows.append({
            'stock': stock,
            't0': str(t0.date()),
            'zone': r['zone_tag'],
            'entry_day': entry_day,
            'day_low': round(day_low, 4),
            'day_close': round(day_close, 4),
            'day_high': round(day_high, 4),
            'day_range': round(day_range, 4),
            'gt_at_entry': round(gt_at_entry, 4),
            'entry_price': round(entry_price, 4),
            'close_from_low_pct': round(close_from_low_pct, 2),
            'close_pos_ratio': round(close_pos_ratio, 4),
            'entry_vs_low_pct': round(entry_vs_low_pct, 2),
            'sl_price': round(sl_price, 4),
            'tp_price': round(tp_price, 4),
            'exit_reason': r['exit_reason'],
            'pnl': r['pnl'],
        })

    df = pd.DataFrame(rows)
    print(f"成功加载入场日数据: {len(df)} 笔\n")

    print("=" * 70)
    print("一、入场日收盘价 vs 最低价 距离统计")
    print("=" * 70)
    print(f"\n  (close - low) / low 分布:")
    print(f"    均值: {df['close_from_low_pct'].mean():.2f}%")
    print(f"    中位: {df['close_from_low_pct'].median():.2f}%")
    print(f"    min:  {df['close_from_low_pct'].min():.2f}%")
    print(f"    max:  {df['close_from_low_pct'].max():.2f}%")

    print(f"\n  收盘价在日内区间的位置 (0=最低, 1=最高):")
    print(f"    均值: {df['close_pos_ratio'].mean():.4f}")
    print(f"    中位: {df['close_pos_ratio'].median():.4f}")
    print(f"    收盘在下半区 (<0.5): {(df['close_pos_ratio'] < 0.5).sum()} 笔 ({(df['close_pos_ratio'] < 0.5).mean():.1%})")
    print(f"    收盘在上半区 (>=0.5): {(df['close_pos_ratio'] >= 0.5).sum()} 笔 ({(df['close_pos_ratio'] >= 0.5).mean():.1%})")

    print(f"\n  入场价(收盘)偏离最低价幅度 (entry - low) / entry:")
    print(f"    均值: {df['entry_vs_low_pct'].mean():.2f}%")
    print(f"    中位: {df['entry_vs_low_pct'].median():.2f}%")

    print("\n" + "=" * 70)
    print("二、按 Zone 分组")
    print("=" * 70)
    for zone in ['abyss_bottom', 'bottom_start', 'main_wave']:
        sub = df[df['zone'] == zone]
        if len(sub) == 0:
            continue
        print(f"\n  {zone} ({len(sub)}笔):")
        print(f"    close偏离low: 均值={sub['close_from_low_pct'].mean():.2f}% 中位={sub['close_from_low_pct'].median():.2f}%")
        print(f"    close位置比: 均值={sub['close_pos_ratio'].mean():.4f} 中位={sub['close_pos_ratio'].median():.4f}")

    print("\n" + "=" * 70)
    print("三、按退出结果分组对比")
    print("=" * 70)
    for reason in ['tp', 'sl', 'expire']:
        sub = df[df['exit_reason'] == reason]
        if len(sub) == 0:
            continue
        print(f"\n  {reason} ({len(sub)}笔, avg pnl={sub['pnl'].mean():.2%}):")
        print(f"    close偏离low: 均值={sub['close_from_low_pct'].mean():.2f}% 中位={sub['close_from_low_pct'].median():.2f}%")
        print(f"    close位置比: 均值={sub['close_pos_ratio'].mean():.4f} 中位={sub['close_pos_ratio'].median():.4f}")

    print("\n" + "=" * 70)
    print("四、入场日 T+0 vs T+N 对比")
    print("=" * 70)
    t0_entry = df[df['entry_day'] <= 2]
    tn_entry = df[df['entry_day'] > 2]
    print(f"\n  T+0~2 入场 ({len(t0_entry)}笔):")
    if len(t0_entry) > 0:
        print(f"    close偏离low: 均值={t0_entry['close_from_low_pct'].mean():.2f}% 中位={t0_entry['close_from_low_pct'].median():.2f}%")
        print(f"    close位置比: 均值={t0_entry['close_pos_ratio'].mean():.4f} 中位={t0_entry['close_pos_ratio'].median():.4f}")
    print(f"\n  T+3+ 入场 ({len(tn_entry)}笔):")
    if len(tn_entry) > 0:
        print(f"    close偏离low: 均值={tn_entry['close_from_low_pct'].mean():.2f}% 中位={tn_entry['close_from_low_pct'].median():.2f}%")
        print(f"    close位置比: 均值={tn_entry['close_pos_ratio'].mean():.4f} 中位={tn_entry['close_pos_ratio'].median():.4f}")

    print("\n" + "=" * 70)
    print("五、用 day_low 入场的假设分析")
    print("=" * 70)
    print(f"\n  当前 (day_close 入场):")
    print(f"    平均止损距离: {((df['entry_price'] - df['sl_price']) / df['entry_price']).mean():.2%}")

    hypothetical_sl_from_low = df['day_low'] * 0.97
    low_entry_sl_dist = (df['day_low'] - hypothetical_sl_from_low) / df['day_low']
    print(f"\n  假设 (day_low 入场, SL = low * 0.97):")
    print(f"    平均止损距离: {low_entry_sl_dist.mean():.2%}")

    print(f"\n  对比: day_close 入场比 day_low 入场多付出的成本:")
    cost = (df['entry_price'] - df['day_low']) / df['day_low']
    print(f"    均值: {cost.mean():.2%}")
    print(f"    中位: {cost.median():.2%}")

    print("\n" + "=" * 70)
    print("六、典型案例: 收盘价远离最低价")
    print("=" * 70)
    top10 = df.nlargest(10, 'close_from_low_pct')
    print(f"\n  close偏离low最大的10笔:")
    print(f"  {'股票':12} {'日期':12} {'zone':15} {'day_low':>8} {'close':>8} {'偏离%':>8} {'位置比':>8} {'退出':>6} {'PnL':>8}")
    for _, r in top10.iterrows():
        print(f"  {r['stock']:12} {r['t0']:12} {r['zone']:15} {r['day_low']:8.2f} {r['day_close']:8.2f} {r['close_from_low_pct']:8.2f} {r['close_pos_ratio']:8.4f} {r['exit_reason']:>6} {r['pnl']:8.4f}")


if __name__ == '__main__':
    main()
