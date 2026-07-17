"""精确统计 GT 回测的个股表现和操作动作指标。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
import numpy as np

DOC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       'doc', '0616_super_trend_V3')

def main():
    df = pd.read_csv(os.path.join(DOC_DIR, 'state_machine_backtest_v5_gt.csv'))
    t = df[df['status'] == 'simulated'].copy()
    print(f'成交: {len(t)} 笔\n')

    # 1. 个股汇总
    print('=' * 80)
    print('  个股表现汇总 (按总 PnL 排序)')
    print('=' * 80)
    rows = []
    for code, g in t.groupby('stock_code'):
        n_sl = (g['exit_reason'] == 'sl').sum()
        n_tp = (g['exit_reason'] == 'tp').sum()
        n_exp = (g['exit_reason'] == 'expire').sum()
        rows.append(dict(
            stock=code, trades=len(g),
            tp=n_tp, sl=n_sl, expire=n_exp,
            total_pnl=g['pnl'].sum(),
            avg_pnl=g['pnl'].mean(),
            avg_gap=g['gap_at_entry'].mean(),
            avg_hold_low=(g['hold_low'] / g['actual_entry_price'] - 1).mean(),
            avg_fwd_high=(g['fwd_high'] / g['actual_entry_price'] - 1).mean(),
        ))
    sdf = pd.DataFrame(rows).sort_values('total_pnl', ascending=False)
    print(f'{"股票":>12} {"笔数":>4} {"TP":>3} {"SL":>3} {"Exp":>3} {"总PnL":>8} {"均PnL":>8} {"avg_gap":>8} {"hold低":>8} {"fwd高":>8}')
    for _, r in sdf.iterrows():
        print(f'{r["stock"]:>12} {r["trades"]:>4} {r["tp"]:>3} {r["sl"]:>3} {r["expire"]:>3} '
              f'{r["total_pnl"]:>8.2%} {r["avg_pnl"]:>8.2%} {r["avg_gap"]:>8.2%} {r["avg_hold_low"]:>8.2%} {r["avg_fwd_high"]:>8.2%}')

    # 2. SL 退出: 入场到低点天数
    sl = t[t['exit_reason'] == 'sl']
    sl_days = sl['hold_low_day'].values - sl['entry_day_idx'].values
    print(f'\n{"=" * 60}')
    print(f'  SL 退出 ({len(sl)} 笔): 入场到低点天数分布')
    print(f'{"=" * 60}')
    for d in sorted(set(sl_days)):
        cnt = (sl_days == d).sum()
        print(f'  {d:>3}天: {cnt:>3} 笔 ({cnt/len(sl):.1%})')

    # 3. TP 退出: 入场到止盈天数
    tp = t[t['exit_reason'] == 'tp']
    tp_days = tp['exit_day_idx'].values - tp['entry_day_idx'].values
    print(f'\n{"=" * 60}')
    print(f'  TP 退出 ({len(tp)} 笔): 入场到止盈天数分布')
    print(f'{"=" * 60}')
    for d in sorted(set(tp_days)):
        cnt = (tp_days == d).sum()
        print(f'  {d:>3}天: {cnt:>3} 笔 ({cnt/len(tp):.1%})')
    print(f'  TP交易入场后最大回撤: median={(tp["hold_low"]/tp["actual_entry_price"]-1).median():.2%}, '
          f'min={(tp["hold_low"]/tp["actual_entry_price"]-1).min():.2%}')

    # 4. EXPIRE 退出
    exp = t[t['exit_reason'] == 'expire']
    print(f'\n{"=" * 60}')
    print(f'  EXPIRE 退出 ({len(exp)} 笔): 高点/低点时序')
    print(f'{"=" * 60}')
    exp_hi = exp['hold_high_day'].values - exp['entry_day_idx'].values
    exp_lo = exp['hold_low_day'].values - exp['entry_day_idx'].values
    print(f'  hold_high 距入场天: median={np.median(exp_hi):.0f}, mean={np.mean(exp_hi):.1f}')
    print(f'  hold_low  距入场天: median={np.median(exp_lo):.0f}, mean={np.mean(exp_lo):.1f}')
    for _, r in exp.iterrows():
        hi_d = int(r['hold_high_day'] - r['entry_day_idx'])
        lo_d = int(r['hold_low_day'] - r['entry_day_idx'])
        hi_pct = r['hold_high'] / r['actual_entry_price'] - 1
        lo_pct = r['hold_low'] / r['actual_entry_price'] - 1
        print(f'  {r["stock_code"]:>12} {r["t0_date"][:10]}  pnl={r["pnl"]:>7.2%}  '
              f'低{"T+" if lo_d>=0 else "T"}{lo_d}({lo_pct:.1%})  高T+{hi_d}({hi_pct:.1%})')

    # 5. GT vs 实际底部
    print(f'\n{"=" * 60}')
    print(f'  GT vs 实际底部 (fwd_low)')
    print(f'{"=" * 60}')
    fwd_low_vs_gt = (t['fwd_low'] / t['gt_at_entry'] - 1) * 100
    for pct in [3, 5, 10]:
        within = fwd_low_vs_gt.abs().le(pct).sum()
        print(f'  fwd_low 在 GT ±{pct}% 以内: {within} 笔 ({within/len(t):.1%})')
    below_gt = (fwd_low_vs_gt < 0).sum()
    print(f'  fwd_low 低于 GT: {below_gt} 笔 ({below_gt/len(t):.1%})')
    print(f'  fwd_low vs GT: median={fwd_low_vs_gt.median():.2f}%, mean={fwd_low_vs_gt.mean():.2f}%')
    print(f'  fwd_low vs GT: min={fwd_low_vs_gt.min():.2f}%, max={fwd_low_vs_gt.max():.2f}%')

    # 6. missed TP ratio
    print(f'\n{"=" * 60}')
    print(f'  冲高未触 TP 分析 (hold_high vs tp_price)')
    print(f'{"=" * 60}')
    t['miss_ratio'] = (t['hold_high'] - t['actual_entry_price']) / (t['tp_price'] - t['actual_entry_price'])
    for reason in ['tp', 'sl', 'expire']:
        sub = t[t['exit_reason'] == reason]
        mr = sub['miss_ratio'].dropna()
        if len(mr) > 0:
            exceeded = (mr >= 1.0).sum()
            close = ((mr >= 0.8) & (mr < 1.0)).sum()
            print(f'  {reason:>6} ({len(mr)} 笔): 超过TP目标 {exceeded} 笔, 接近(80%+) {close} 笔, '
                  f'median={mr.median():.2f}, mean={mr.mean():.2f}')

    # 7. 即时入场 vs 延迟入场
    print(f'\n{"=" * 60}')
    print(f'  即时入场(T+0) vs 延迟入场(T+1+)')
    print(f'{"=" * 60}')
    imm = t[t['entry_day_idx'] == 0]
    delayed = t[t['entry_day_idx'] > 0]
    for label, sub in [('T+0 即时', imm), ('T+1+ 延迟', delayed)]:
        if len(sub) > 0:
            wr = (sub['pnl'] > 0).mean()
            pf = abs(sub[sub['pnl']>0]['pnl'].sum() / sub[sub['pnl']<0]['pnl'].sum()) if sub[sub['pnl']<0]['pnl'].sum() != 0 else float('inf')
            print(f'  {label}: {len(sub)} 笔, 胜率={wr:.1%}, PF={pf:.2f}, '
                  f'avg PnL={sub["pnl"].mean():.2%}, median PnL={sub["pnl"].median():.2%}')

    # 8. 同股重复入场统计
    print(f'\n{"=" * 60}')
    print(f'  同股重复入场分析')
    print(f'{"=" * 60}')
    multi = sdf[sdf['trades'] >= 3]
    print(f'  入场 >=3 次的股票: {len(multi)} 只')
    for _, r in multi.iterrows():
        print(f'    {r["stock"]:>12}: {r["trades"]} 笔, TP={r["tp"]}, SL={r["sl"]}, '
              f'总PnL={r["total_pnl"]:.2%}')
    total_dup_trades = multi['sl'].sum()
    print(f'  重复股票 SL 总笔数: {total_dup_trades}, 如果只保留首次入场可减少 ~{total_dup_trades - len(multi)} 笔 SL')

    # 9. trend_tag 分析
    print(f'\n{"=" * 60}')
    print(f'  按 trend_tag 分析')
    print(f'{"=" * 60}')
    for tag in ['bear_aligned', 'neutral', 'bull_aligned']:
        sub = t[t['trend_tag'] == tag]
        if len(sub) > 0:
            wr = (sub['pnl'] > 0).mean()
            print(f'  {tag:>14}: {len(sub)} 笔, 胜率={wr:.1%}, avg PnL={sub["pnl"].mean():.2%}')

if __name__ == '__main__':
    main()
