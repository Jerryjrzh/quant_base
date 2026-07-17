#!/usr/bin/env python3
"""分析双轨校准中偏差 >8% 的信号"""
import os, sys
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _SCRIPT_DIR)

import pandas as pd
import numpy as np
import data_loader

DOC_DIR = os.path.join(_PROJECT_ROOT, 'doc', '0616_super_trend_V3')
DOC_DIR_V4 = os.path.join(_PROJECT_ROOT, 'doc', '0613_super_trend_v2')
ADAPTIVE_CSV = os.path.join(DOC_DIR, 'adaptive_golden_trend.csv')
TAGS_CSV = os.path.join(DOC_DIR, 'signal_tags_v5.csv')
REVIEW4_CSV = os.path.join(DOC_DIR_V4, 'review4_final_backtest.csv')
PATH_V42_CSV = os.path.join(DOC_DIR_V4, 'path_analysis_v42.csv')

THRESHOLD = 0.08

def main():
    # 加载数据
    adf = pd.read_csv(ADAPTIVE_CSV)
    adf['t0_date'] = pd.to_datetime(adf['t0_date'])

    # Zone tags
    if os.path.exists(TAGS_CSV):
        tags = pd.read_csv(TAGS_CSV)
        adf = adf.merge(tags[['signal_idx', 'zone_tag', 'position_ratio']],
                        on='signal_idx', how='left')

    # Path analysis (max_drawdown, mfe, final_return)
    path = pd.read_csv(PATH_V42_CSV)
    path_cols = ['signal_idx', 'max_drawdown', 'mfe', 'final_return', 'dd_day_idx', 'rebound_pct']
    avail = [c for c in path_cols if c in path.columns]
    adf = adf.merge(path[avail], on='signal_idx', how='left')

    total = len(adf)
    bad = adf[adf['best_abs_dist_pct'] > THRESHOLD].copy()
    print(f"{'='*70}")
    print(f"  偏差 >{THRESHOLD:.0%} 信号分类分析")
    print(f"{'='*70}")
    print(f"\n  总信号: {total}, 偏差>{THRESHOLD:.0%}: {len(bad)} ({len(bad)/total:.1%})")
    print(f"  偏差>15%: {(adf['best_abs_dist_pct']>0.15).sum()} ({(adf['best_abs_dist_pct']>0.15).sum()/total:.1%})")
    print(f"  偏差>20%: {(adf['best_abs_dist_pct']>0.20).sum()} ({(adf['best_abs_dist_pct']>0.20).sum()/total:.1%})")

    # ===================================================================
    # 1. Zone 分布 (stock-level 去重, 风险优先级: high_trap > abyss_bottom > bottom_start > high_zone > main_wave)
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [1] Zone 分布 (个股去重, 风险优先级)")
    print(f"{'='*70}")

    ZONE_PRIORITY = ['high_trap', 'abyss_bottom', 'bottom_start', 'high_zone', 'main_wave']

    if 'zone_tag' in adf.columns:
        def stock_priority_zone(group):
            for z in ZONE_PRIORITY:
                if (group['zone_tag'] == z).any():
                    return z
            return group['zone_tag'].iloc[0]

        stock_zone_all = adf.groupby('stock_code').apply(stock_priority_zone).reset_index()
        stock_zone_all.columns = ['stock_code', 'priority_zone']

        bad_stocks = bad['stock_code'].unique()
        stock_zone_bad = adf[adf['stock_code'].isin(bad_stocks)].groupby('stock_code').apply(stock_priority_zone).reset_index()
        stock_zone_bad.columns = ['stock_code', 'priority_zone']

        print(f"\n  全量个股 Zone 分配 (去重后):")
        print(f"  {'Zone':<16} {'偏差>8%个股':>10} {'该Zone总个股':>12} {'占比':>8}")
        print(f"  {'-'*50}")
        for z in ZONE_PRIORITY:
            all_in_z = stock_zone_all[stock_zone_all['priority_zone'] == z]['stock_code']
            bad_in_z = stock_zone_bad[stock_zone_bad['priority_zone'] == z]['stock_code']
            total = len(all_in_z)
            bc = len(bad_in_z)
            pct = bc / total * 100 if total > 0 else 0
            print(f"  {z:<16} {bc:>10} {total:>12} {pct:>7.1f}%")

        for z in ZONE_PRIORITY:
            bad_in_z = stock_zone_bad[stock_zone_bad['priority_zone'] == z]['stock_code'].tolist()
            if len(bad_in_z) == 0:
                continue
            print(f"\n  --- {z}: {len(bad_in_z)} 只偏差>8% 个股 ---")

            for stock in bad_in_z:
                sub_bad = bad[bad['stock_code'] == stock]
                sub_all = adf[adf['stock_code'] == stock]
                n_bad = len(sub_bad)
                n_all = len(sub_all)
                avg_dist = sub_bad['best_abs_dist_pct'].mean()
                max_dist = sub_bad['best_abs_dist_pct'].max()
                zones_raw = sub_all['zone_tag'].unique().tolist()
                zones_str = ','.join(zones_raw) if len(zones_raw) <= 3 else ','.join(zones_raw[:3]) + '...'
                tfs = sub_bad['best_timeframe'].value_counts().to_dict()
                tf_str = ','.join(f'{k}:{v}' for k, v in tfs.items())

                dd_vals = sub_bad['max_drawdown'].dropna()
                dd_str = f'{dd_vals.min():.1%}~{dd_vals.max():.1%}' if len(dd_vals) > 0 else 'N/A'

                print(f"    {stock}: {n_bad}/{n_all}信号偏差>8%, "
                      f"avg={avg_dist:.2%}, max={max_dist:.2%}, "
                      f"DD={dd_str}, TF={tf_str}, 原始zones=[{zones_str}]")

    # ===================================================================
    # 2. 时间框架分布
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [2] 胜出时间框架分布")
    print(f"{'='*70}")
    tf_bad = bad['best_timeframe'].value_counts()
    tf_all = adf['best_timeframe'].value_counts()
    for tf in ['daily', 'hourly']:
        t = tf_all.get(tf, 0)
        b = tf_bad.get(tf, 0)
        print(f"  {tf:<10} {b:>6}/{t:<6} ({b/t*100:.1f}%)")

    # ===================================================================
    # 3. 个股集中度
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [3] 个股集中度 (Top 20)")
    print(f"{'='*70}")
    stock_bad = bad['stock_code'].value_counts()
    stock_all = adf['stock_code'].value_counts()
    print(f"  {'股票':>12} {'偏差>8%':>8} {'总信号':>8} {'占比':>8}")
    print(f"  {'-'*40}")
    for s, cnt in stock_bad.head(20).items():
        t = stock_all.get(s, 0)
        print(f"  {s:>12} {cnt:>8} {t:>8} {cnt/t*100:>7.1f}%")
    print(f"\n  涉及个股数: {bad['stock_code'].nunique()}/{adf['stock_code'].nunique()}")

    # ===================================================================
    # 4. 偏差方向
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [4] 偏差方向分析")
    print(f"{'='*70}")
    gt_high = (bad['best_dist_pct'] < 0).sum()
    gt_low = (bad['best_dist_pct'] > 0).sum()
    print(f"  GT_T0 > actual (网格偏高): {gt_high} ({gt_high/len(bad):.1%})")
    print(f"  GT_T0 < actual (网格偏低): {gt_low} ({gt_low/len(bad):.1%})")
    print(f"  平均偏差方向: {bad['best_dist_pct'].mean():+.2%}")

    # ===================================================================
    # 5. 分类归因
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [5] 偏差归因分类")
    print(f"{'='*70}")

    # Build stock-level priority zone map
    stock_pzone = {}
    if 'zone_tag' in adf.columns:
        for stock, grp in adf.groupby('stock_code'):
            for z in ZONE_PRIORITY:
                if (grp['zone_tag'] == z).any():
                    stock_pzone[stock] = z
                    break
            else:
                stock_pzone[stock] = grp['zone_tag'].iloc[0]

    reasons = []
    for _, r in bad.iterrows():
        dd = r.get('max_drawdown', np.nan)
        dist = r['best_abs_dist_pct']
        direction = r['best_dist_pct']
        zone = stock_pzone.get(r['stock_code'], 'unknown')
        tf = r['best_timeframe']
        daily_dist = r.get('daily_best_abs_dist_pct', np.nan)
        hourly_dist = r.get('hourly_best_abs_dist_pct', np.nan)
        overlap = r.get('daily_rail_overlap', False)

        # 分类逻辑
        reason = 'unknown'

        # A: 极端回撤 - max_drawdown 很深 (>30%)
        if not np.isnan(dd) and dd < -0.30:
            reason = 'extreme_drawdown'
        # B: 快速反弹 - dd_day_idx 靠前 + rebound_pct 高
        elif not np.isnan(r.get('dd_day_idx', np.nan)) and not np.isnan(r.get('rebound_pct', np.nan)):
            if r['dd_day_idx'] <= 3 and r['rebound_pct'] > 0.3:
                reason = 'fast_rebound'
        # C: 双轨均无法对齐 (两个时间框架偏差都大)
        elif not np.isnan(daily_dist) and not np.isnan(hourly_dist):
            if daily_dist > 0.10 and hourly_dist > 0.10:
                reason = 'both_tf_fail'
            elif daily_dist > 0.10 and hourly_dist <= 0.10:
                reason = 'daily_only_fail'
            elif hourly_dist > 0.10 and daily_dist <= 0.10:
                reason = 'hourly_only_fail'
        # D: 日线重叠
        elif overlap:
            reason = 'rail_overlap'
        # E: high_trap zone
        elif zone == 'high_trap':
            reason = 'high_trap_zone'
        # F: abyss_bottom
        elif zone == 'abyss_bottom':
            reason = 'abyss_bottom_zone'
        else:
            reason = 'other'

        reasons.append(reason)

    bad['reason'] = reasons

    reason_counts = bad['reason'].value_counts()
    reason_labels = {
        'extreme_drawdown': '极端回撤 (DD>30%)',
        'fast_rebound': '快速反弹 (≤3天见底+反弹>30%)',
        'both_tf_fail': '双轨均无法对齐 (>10%)',
        'daily_only_fail': '仅日线偏差大 (小时线可对齐)',
        'hourly_only_fail': '仅小时线偏差大 (日线可对齐)',
        'rail_overlap': '日线双轨重叠',
        'high_trap_zone': '高位陷阱区',
        'abyss_bottom_zone': '深渊底部区',
        'other': '其他',
    }
    print(f"  {'原因':<36} {'数量':>6} {'占比':>8} {'平均偏差':>10}")
    print(f"  {'-'*64}")
    for r, cnt in reason_counts.items():
        label = reason_labels.get(r, r)
        avg_d = bad[bad['reason'] == r]['best_abs_dist_pct'].mean()
        print(f"  {label:<36} {cnt:>6} {cnt/len(bad)*100:>7.1f}% {avg_d:>9.2%}")

    # ===================================================================
    # 6. 按原因分桶详细分析
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [6] 各原因详细分析")
    print(f"{'='*70}")

    for r in reason_counts.index:
        sub = bad[bad['reason'] == r]
        label = reason_labels.get(r, r)
        print(f"\n  --- {label} ({len(sub)} 笔) ---")
        print(f"  偏差: avg={sub['best_abs_dist_pct'].mean():.2%}, "
              f"med={sub['best_abs_dist_pct'].median():.2%}, "
              f"max={sub['best_abs_dist_pct'].max():.2%}")

        # Show priority zone distribution
        pz_counts = {}
        for s in sub['stock_code'].unique():
            pz = stock_pzone.get(s, 'unknown')
            pz_counts[pz] = pz_counts.get(pz, 0) + 1
        pzstr = ', '.join(f'{z}:{c}' for z, c in sorted(pz_counts.items(), key=lambda x: -x[1]))
        print(f"  Zone(优先级): {pzstr}")

        tfc = sub['best_timeframe'].value_counts()
        tfstr = ', '.join(f'{t}:{c}' for t, c in tfc.items())
        print(f"  时间框架: {tfstr}")

        stock_c = sub['stock_code'].value_counts()
        if len(stock_c) <= 5:
            sstr = ', '.join(f'{s}:{c}' for s, c in stock_c.items())
        else:
            sstr = ', '.join(f'{s}:{c}' for s, c in stock_c.head(5).items()) + f' +{len(stock_c)-5}只'
        print(f"  个股: {sstr}")

    # ===================================================================
    # 7. Top 20 最差案例
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [7] Top 20 最差校准案例")
    print(f"{'='*70}")
    worst = bad.nlargest(20, 'best_abs_dist_pct')
    cols = ['signal_idx', 'stock_code', 't0_date', 'zone_tag',
            'best_timeframe', 'best_abs_dist_pct', 'best_dist_pct',
            'daily_best_abs_dist_pct', 'hourly_best_abs_dist_pct',
            'best_n', 'best_k', 'best_offset',
            'actual_bottom', 'best_gt_t0', 'reason']
    avail_cols = [c for c in cols if c in worst.columns]

    for _, r in worst.iterrows():
        print(f"\n  #{int(r['signal_idx'])} {r['stock_code']} @ {r['t0_date'].strftime('%Y-%m-%d')}")
        pzone = stock_pzone.get(r['stock_code'], 'N/A')
        raw_zones = adf[adf['stock_code']==r['stock_code']]['zone_tag'].unique().tolist() if 'zone_tag' in adf.columns else []
        tf = r.get('best_timeframe', 'N/A')
        reason = r.get('reason', 'N/A')
        print(f"    优先级Zone: {pzone} (原始: {','.join(raw_zones)}), TF: {tf}, 原因: {reason_labels.get(reason, reason)}")
        print(f"    偏差: {r['best_abs_dist_pct']:.2%} (方向: {r['best_dist_pct']:+.2%})")
        dd_pct = r.get('daily_best_abs_dist_pct', np.nan)
        hd_pct = r.get('hourly_best_abs_dist_pct', np.nan)
        print(f"    日线偏差: {dd_pct:.2%} | 小时线偏差: {hd_pct:.2%}" if not (np.isnan(dd_pct) or np.isnan(hd_pct)) else
              f"    日线偏差: {dd_pct} | 小时线偏差: {hd_pct}")
        print(f"    参数: N={int(r['best_n'])}, k={r['best_k']}, offset={r['best_offset']}")
        print(f"    actual_bottom={r['actual_bottom']:.2f}, GT_T0={r['best_gt_t0']:.2f}")
        if 'max_drawdown' in r and not np.isnan(r['max_drawdown']):
            print(f"    max_drawdown={r['max_drawdown']:.2%}, mfe={r.get('mfe',np.nan)}")

    # ===================================================================
    # 8. 改善可能性分析: 双轨中另一轨是否更优
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [8] 双轨偏差对比 (另一时间框架是否更优)")
    print(f"{'='*70}")
    both = bad[bad['daily_best_abs_dist_pct'].notna() & bad['hourly_best_abs_dist_pct'].notna()]
    if len(both) > 0:
        daily_better = (both['daily_best_abs_dist_pct'] < both['hourly_best_abs_dist_pct']).sum()
        hourly_better = (both['hourly_best_abs_dist_pct'] < both['daily_best_abs_dist_pct']).sum()
        print(f"  双轨均可用: {len(both)} 笔")
        print(f"  日线更优: {daily_better} ({daily_better/len(both):.1%})")
        print(f"  小时线更优: {hourly_better} ({hourly_better/len(both):.1%})")
        print(f"  日线平均偏差: {both['daily_best_abs_dist_pct'].mean():.2%}")
        print(f"  小时线平均偏差: {both['hourly_best_abs_dist_pct'].mean():.2%}")

        # 看看另一轨的偏差
        daily_win_bad = both[(both['best_timeframe']=='daily')]
        hourly_win_bad = both[(both['best_timeframe']=='hourly')]
        if len(daily_win_bad) > 0:
            print(f"\n  日线胜出但偏差>8% ({len(daily_win_bad)}笔):")
            print(f"    日线 avg: {daily_win_bad['daily_best_abs_dist_pct'].mean():.2%}")
            print(f"    小时线 avg: {daily_win_bad['hourly_best_abs_dist_pct'].mean():.2%}")
        if len(hourly_win_bad) > 0:
            print(f"\n  小时线胜出但偏差>8% ({len(hourly_win_bad)}笔):")
            print(f"    小时线 avg: {hourly_win_bad['hourly_best_abs_dist_pct'].mean():.2%}")
            print(f"    日线 avg: {hourly_win_bad['daily_best_abs_dist_pct'].mean():.2%}")

    # ===================================================================
    # 9. 同股票多信号分析
    # ===================================================================
    print(f"\n{'='*70}")
    print(f"  [9] 同股票多信号一致性")
    print(f"{'='*70}")
    multi = bad.groupby('stock_code').size()
    multi = multi[multi > 1].sort_values(ascending=False)
    print(f"  偏差>8%且有多个信号的个股: {len(multi)} 只")
    for s, cnt in multi.head(10).items():
        sub = bad[bad['stock_code'] == s]
        total_s = adf[adf['stock_code'] == s]
        avg_bad = sub['best_abs_dist_pct'].mean()
        # check all signals for this stock
        avg_all = total_s['best_abs_dist_pct'].mean()
        print(f"  {s}: {cnt}/{len(total_s)} 信号偏差>8%, "
              f"偏差>8%均值={avg_bad:.2%}, 全部均值={avg_all:.2%}")

    print(f"\n{'='*70}")
    print(f"  分析完成")
    print(f"{'='*70}")


if __name__ == '__main__':
    main()
