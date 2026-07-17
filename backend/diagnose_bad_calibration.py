#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断: 校准后偏差 > 8% 的信号分析
- 分布 (个股/Zone/时间)
- 同一股票历史信号是否可对齐
- 不可对齐原因分析
- 典型案例输出
"""

import os
import sys
import warnings
warnings.filterwarnings('ignore')

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import pandas as pd
import numpy as np

DOC_DIR_V5 = os.path.join(_PROJECT_ROOT, 'doc', '0616_super_trend_V3')

adaptive_csv = os.path.join(DOC_DIR_V5, 'adaptive_golden_trend.csv')
tags_csv = os.path.join(DOC_DIR_V5, 'signal_tags_v5.csv')
path_csv = os.path.join(_PROJECT_ROOT, 'doc', '0613_super_trend_v2', 'path_analysis_v42.csv')

def main():
    adf = pd.read_csv(adaptive_csv)
    adf['t0_date'] = pd.to_datetime(adf['t0_date'])

    tags = pd.read_csv(tags_csv)
    tags['t0_date'] = pd.to_datetime(tags['t0_date'])

    path = pd.read_csv(path_csv)
    path['t0_date'] = pd.to_datetime(path['t0_date'])

    # 合并
    merged = adf.merge(
        tags[['signal_idx', 'zone_tag', 'position_ratio', 'trend_tag', 'atr20_pct']],
        on='signal_idx', how='left'
    )
    merged = merged.merge(
        path[['signal_idx', 'max_drawdown', 'rebound_pct', 'dd_day_idx']],
        on='signal_idx', how='left'
    )

    # 筛选偏差 > 8%
    bad = merged[merged['best_abs_dist_pct'] > 0.08].copy()
    bad = bad.sort_values('best_abs_dist_pct', ascending=False)

    print("=" * 80)
    print(f"  校准后偏差 > 8% 的信号分析")
    print(f"  总信号: {len(merged)}, 偏差>8%: {len(bad)} ({len(bad)/len(merged):.1%})")
    print("=" * 80)

    # === 1. 个股分布 ===
    print("\n## 一、偏差>8% 的个股分布 (Top 20)")
    stock_stats = bad.groupby('stock_code').agg(
        n_bad=('best_abs_dist_pct', 'size'),
        avg_dev=('best_abs_dist_pct', 'mean'),
        max_dev=('best_abs_dist_pct', 'max'),
        zones=('zone_tag', lambda x: ','.join(sorted(x.dropna().unique()))),
    ).sort_values('n_bad', ascending=False)

    print(f"  共 {len(stock_stats)} 只股票有偏差>8% 的信号")
    print(f"\n  {'个股':<12} {'偏差>8%笔数':>10} {'平均偏差':>10} {'最大偏差':>10}  涉及Zone")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10}  {'-'*30}")
    for stock, row in stock_stats.head(20).iterrows():
        print(f"  {stock:<12} {int(row['n_bad']):>10} {row['avg_dev']:>10.2%} {row['max_dev']:>10.2%}  {row['zones']}")

    # === 2. Zone 分布 ===
    print("\n## 二、偏差>8% 的 Zone 分布")
    zone_stats = bad.groupby('zone_tag').agg(
        n=('best_abs_dist_pct', 'size'),
        avg_dev=('best_abs_dist_pct', 'mean'),
        median_dev=('best_abs_dist_pct', 'median'),
    ).sort_values('n', ascending=False)

    total_by_zone = merged.groupby('zone_tag').size()
    print(f"\n  {'Zone':<16} {'偏差>8%':>8} {'Zone总数':>8} {'占比':>8} {'平均偏差':>10}")
    print(f"  {'-'*16} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")
    for zone, row in zone_stats.iterrows():
        total = total_by_zone.get(zone, 0)
        print(f"  {zone:<16} {int(row['n']):>8} {total:>8} {row['n']/total:>8.1%} {row['avg_dev']:>10.2%}")

    # === 3. 同一股票历史信号对齐情况 ===
    print("\n## 三、同一股票多信号对齐分析")
    # 有>=2笔偏差>8%的股票
    repeat_stocks = stock_stats[stock_stats['n_bad'] >= 2].index.tolist()
    print(f"  有 ≥2 笔偏差>8% 的股票: {len(repeat_stocks)} 只")

    for stock in repeat_stocks[:10]:
        stock_all = merged[merged['stock_code'] == stock].sort_values('t0_date')
        stock_bad = stock_all[stock_all['best_abs_dist_pct'] > 0.08]
        print(f"\n  === {stock} (共 {len(stock_all)} 笔信号, {len(stock_bad)} 笔偏差>8%) ===")
        print(f"  {'日期':<12} {'Zone':<14} {'实际底':>8} {'GT_T0':>8} {'偏差':>8} {'回撤':>8} {'反弹':>8}")
        print(f"  {'-'*12} {'-'*14} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        for _, r in stock_all.iterrows():
            marker = " ***" if r['best_abs_dist_pct'] > 0.08 else ""
            print(f"  {str(r['t0_date'].date()):<12} {str(r.get('zone_tag','')):<14} "
                  f"{r['actual_bottom']:>8.2f} {r['best_gt_t0']:>8.2f} "
                  f"{r['best_abs_dist_pct']:>8.2%} "
                  f"{r.get('max_drawdown', 0):>8.2%} "
                  f"{r.get('rebound_pct', 0):>8.2%}{marker}")

    # === 4. 不可对齐原因分析 ===
    print("\n## 四、不可对齐原因分类")

    # 4a. 极端回撤 (>20%)
    deep_dd = bad[bad['max_drawdown'] < -0.20]
    print(f"\n  A. 极端回撤 (>20%): {len(deep_dd)} 笔 ({len(deep_dd)/len(bad):.1%})")

    # 4b. 高波动 (ATR>8%)
    high_vol = bad[bad['atr20_pct'] > 0.08]
    print(f"  B. 高波动 (ATR20%>8%): {len(high_vol)} 笔 ({len(high_vol)/len(bad):.1%})")

    # 4c. 趋势方向 (bear_aligned)
    bear = bad[bad['trend_tag'] == 'bear_aligned']
    print(f"  C. 空头排列 (bear_aligned): {len(bear)} 笔 ({len(bear)/len(bad):.1%})")

    # 4d. high_trap zone
    ht = bad[bad['zone_tag'] == 'high_trap']
    print(f"  D. 高位陷阱 (high_trap): {len(ht)} 笔 ({len(ht)/len(bad):.1%})")

    # 4e. 底部极快反弹 (dd_day_idx <= 2 且 rebound > 20%)
    fast_rebound = bad[(bad['dd_day_idx'] <= 2) & (bad['rebound_pct'] > 0.20)]
    print(f"  E. 极速反弹 (底部≤2天+反弹>20%): {len(fast_rebound)} 笔 ({len(fast_rebound)/len(bad):.1%})")

    # 4f. GT_T0 方向分析: 偏高 vs 偏低
    gt_too_high = bad[bad['best_dist_pct'] < -0.08]  # GT > actual (GT偏高)
    gt_too_low = bad[bad['best_dist_pct'] > 0.08]     # GT < actual (GT偏低)
    print(f"\n  F. 偏差方向:")
    print(f"     GT偏高 (GT>实际底, 保守): {len(gt_too_high)} 笔 ({len(gt_too_high)/len(bad):.1%})")
    print(f"     GT偏低 (GT<实际底, 宽松): {len(gt_too_low)} 笔 ({len(gt_too_low)/len(bad):.1%})")

    # 重叠分析
    overlap = bad.copy()
    overlap['reason'] = ''
    overlap.loc[overlap['max_drawdown'] < -0.20, 'reason'] += '极端回撤;'
    overlap.loc[overlap['atr20_pct'] > 0.08, 'reason'] += '高波动;'
    overlap.loc[overlap['trend_tag'] == 'bear_aligned', 'reason'] += '空头;'
    overlap.loc[overlap['zone_tag'] == 'high_trap', 'reason'] += '高位;'
    overlap['reason'] = overlap['reason'].apply(lambda x: x[:-1] if x else '未知')
    reason_dist = overlap['reason'].value_counts().head(10)
    print(f"\n  G. 原因组合分布:")
    for reason, cnt in reason_dist.items():
        print(f"     {reason}: {cnt} ({cnt/len(bad):.1%})")

    # === 5. 典型案例 (Top 10 偏差最大) ===
    print("\n## 五、典型案例 (偏差最大的 10 笔)")
    print(f"\n  {'#':>2} {'个股':<12} {'日期':<12} {'Zone':<14} {'实际底':>8} {'GT_T0':>8} "
          f"{'偏差':>8} {'回撤':>8} {'ATR%':>6} {'趋势':<14}")
    print(f"  {'-'*2} {'-'*12} {'-'*12} {'-'*14} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*6} {'-'*14}")
    for ci, (_, r) in enumerate(bad.head(10).iterrows()):
        print(f"  {ci+1:>2} {r['stock_code']:<12} {str(r['t0_date'].date()):<12} "
              f"{str(r.get('zone_tag','')):<14} "
              f"{r['actual_bottom']:>8.2f} {r['best_gt_t0']:>8.2f} "
              f"{r['best_abs_dist_pct']:>8.2%} "
              f"{r.get('max_drawdown', 0):>8.2%} "
              f"{r.get('atr20_pct', 0):>6.2%} "
              f"{str(r.get('trend_tag','')):<14}")

    # === 6. 对每笔偏差>8%信号，检查120组合中最小可能偏差 ===
    print("\n## 六、校准极限: 偏差>8%信号在120组合中的最小偏差分布")
    print(f"  (这些信号已经是120组合中的最优结果，偏差>8%说明公式本身的局限)")
    print(f"\n  偏差分位:")
    for p in [0.0, 0.25, 0.50, 0.75, 1.0]:
        v = bad['best_abs_dist_pct'].quantile(p)
        print(f"    P{int(p*100):>3}: {v:.2%}")

    # 偏差>20% 的详细列表
    very_bad = bad[bad['best_abs_dist_pct'] > 0.20]
    print(f"\n  偏差>20% 的信号: {len(very_bad)} 笔")
    if len(very_bad) > 0:
        print(f"  {'个股':<12} {'日期':<12} {'Zone':<14} {'实际底':>8} {'GT_T0':>8} {'偏差':>8} {'回撤':>8}")
        print(f"  {'-'*12} {'-'*12} {'-'*14} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
        for _, r in very_bad.head(20).iterrows():
            print(f"  {r['stock_code']:<12} {str(r['t0_date'].date()):<12} "
                  f"{str(r.get('zone_tag','')):<14} "
                  f"{r['actual_bottom']:>8.2f} {r['best_gt_t0']:>8.2f} "
                  f"{r['best_abs_dist_pct']:>8.2%} "
                  f"{r.get('max_drawdown', 0):>8.2%}")


if __name__ == '__main__':
    main()
