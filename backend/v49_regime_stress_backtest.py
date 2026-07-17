"""
v49 进阶回测:
  Part 2 - Tier × Market Regime (不同市场环境下调整 N / 仓位)
  Part 3 - 压力测试 (SLOT_COUNT = 20 / 10 / 5, 模拟资金受限)

数据: data/result/Calendar_Backtest/full_calendar_trades_v49.csv
"""
import os, sys, pandas as pd, numpy as np

CSV = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_v49.csv'
RISK_FREE_DAILY = 0.015 / 252


def slots_flat(_t): return 1.0


def run_backtest(df, N, slot_fn, slot_count=20, regime=None):
    """
    regime: None 表示不做过滤; 字符串表示只取该 market_env 的信号
    """
    df = df.sort_values(['回测日期', 'daily_signal_rank'])
    dates_all = sorted(df['回测日期'].unique())

    selected = []
    for day in dates_all:
        g = df[df['回测日期'] == day]
        if regime is not None:
            g = g[g['market_env'] == regime]
        selected.append(g.head(N))
    sel = pd.concat(selected)
    if len(sel) == 0:
        return None

    sel = sel.copy()
    sel['slots'] = sel['v5_tier'].apply(slot_fn)
    sel['entry'] = pd.to_datetime(sel['成交日期'])
    sel['exit']  = pd.to_datetime(sel['卖出日期'])
    sel['hold']  = (sel['exit'] - sel['entry']).dt.days.clip(lower=1)
    sel['daily_ret'] = sel['收益率'] / sel['hold']

    dates = pd.date_range(sel['entry'].min(), sel['exit'].max())
    day_slot_used = pd.Series(0.0, index=dates)
    day_ret_raw   = pd.Series(0.0, index=dates)
    for _, t in sel.iterrows():
        mask = (day_slot_used.index >= t['entry']) & (day_slot_used.index <= t['exit'])
        day_slot_used[mask] += t['slots']
        day_ret_raw[mask]   += t['daily_ret'] * t['slots']

    scale = day_slot_used.clip(lower=slot_count)
    port_ret = day_ret_raw / scale
    equity = (1 + port_ret).cumprod()
    total_ret = equity.iloc[-1] - 1
    days = len(port_ret)
    annual_ret = (1 + total_ret) ** (252 / max(days, 1)) - 1
    sharpe = (port_ret.mean() - RISK_FREE_DAILY) / (port_ret.std() + 1e-9) * np.sqrt(252)
    peak = equity.cummax()
    max_dd = ((equity - peak) / peak).min()

    r = sel['收益率']
    return {
        'trades': len(sel),
        'days': days,
        'annual': annual_ret,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'win': (r > 0).mean(),
        'pf': r[r > 0].sum() / (-r[r < 0].sum() + 1e-9),
        'tier_dist': dict(sel['v5_tier'].value_counts()),
        'equity': equity,
        'port_ret': port_ret,
    }


def row(label, res, prefix='  '):
    if res is None:
        print(f'{prefix}{label:<55} (无数据)')
        return
    print(f"{prefix}{label:<55} | n={res['trades']:>4} 年化{res['annual']:>+8.2%} "
          f"Sharpe{res['sharpe']:>+6.2f} MaxDD{res['max_dd']:>+7.2%} "
          f"胜率{res['win']:>5.1%} PF{res['pf']:>5.2f}")


def score_res(r):
    if r is None: return -1e9
    return r['annual'] * max(r['sharpe'], 0) * (1 + r['max_dd'])


def main():
    df = pd.read_csv(CSV)
    df = df[df['is_entry'] == True].copy()
    print(f'数据: {len(df)} 笔成交, {df["回测日期"].min()} ~ {df["回测日期"].max()}')
    regimes = ['震荡', '弱势阴跌', '股灾暴跌', '顺风大涨']
    print(f'market_env 分布: {dict(df["market_env"].value_counts())}')
    print()

    # =====================================================================
    # Part 2: Tier × Market Regime
    # =====================================================================
    print('=' * 130)
    print('【Part 2】Tier × Market Regime 分析')
    print('=' * 130)

    print('\n--- 2.1 各环境基础表现 (N=10, 等权, slot_count=20) ---')
    for env in regimes:
        r = run_backtest(df, 10, slots_flat, slot_count=20, regime=env)
        row(env, r)

    print('\n--- 2.2 各环境下扫描 N (找最佳 N) ---')
    best_n_per_regime = {}
    for env in regimes:
        print(f'\n  [{env}]')
        scored = []
        for N in [1, 2, 3, 5, 8, 10, 15, 20]:
            r = run_backtest(df, N, slots_flat, slot_count=20, regime=env)
            if r is None: continue
            row(f'N={N}', r)
            scored.append((N, r, score_res(r)))
        if scored:
            scored.sort(key=lambda x: -x[2])
            best_n_per_regime[env] = scored[0][0]
            print(f'    >> 该环境最佳 N = {scored[0][0]} '
                  f'(年化{scored[0][1]["annual"]:>+.2%}, Sharpe{scored[0][1]["sharpe"]:>+.2f}, '
                  f'MaxDD{scored[0][1]["max_dd"]:>+.2%})')

    print('\n--- 2.3 动态 N 策略 vs 固定 N 策略 ---')
    # 动态 N: 每日按该日 signal 的 market_env 众数决定 N
    df_sorted = df.sort_values(['回测日期', 'daily_signal_rank'])
    selected_dyn = []
    used_n_hist = []
    for day, g in df_sorted.groupby('回测日期'):
        mode_env = g['market_env'].mode().iloc[0] if len(g) > 0 else '震荡'
        n_today = best_n_per_regime.get(mode_env, 10)
        selected_dyn.append(g.head(n_today))
        used_n_hist.append((day, mode_env, n_today))
    dyn_sel = pd.concat(selected_dyn).copy()
    dyn_sel['slots'] = 1.0
    dyn_sel['entry'] = pd.to_datetime(dyn_sel['成交日期'])
    dyn_sel['exit']  = pd.to_datetime(dyn_sel['卖出日期'])
    dyn_sel['hold']  = (dyn_sel['exit'] - dyn_sel['entry']).dt.days.clip(lower=1)
    dyn_sel['daily_ret'] = dyn_sel['收益率'] / dyn_sel['hold']
    dates = pd.date_range(dyn_sel['entry'].min(), dyn_sel['exit'].max())
    day_slot = pd.Series(0.0, index=dates); day_ret = pd.Series(0.0, index=dates)
    for _, t in dyn_sel.iterrows():
        m = (day_slot.index >= t['entry']) & (day_slot.index <= t['exit'])
        day_slot[m] += 1; day_ret[m] += t['daily_ret']
    port_ret = day_ret / day_slot.clip(lower=20)
    equity = (1 + port_ret).cumprod()
    annual = equity.iloc[-1] ** (252/len(port_ret)) - 1
    sharpe = (port_ret.mean() - RISK_FREE_DAILY) / port_ret.std() * np.sqrt(252)
    max_dd = ((equity - equity.cummax()) / equity.cummax()).min()
    r = dyn_sel['收益率']
    print(f'  动态 N (regime 映射): 交易{len(dyn_sel):>4}笔, '
          f'年化{annual:>+.2%}, Sharpe{sharpe:>+.2f}, MaxDD{max_dd:>+.2%}, '
          f'胜率{(r>0).mean():.1%}, PF={r[r>0].sum()/(-r[r<0].sum()+1e-9):.2f}')
    for N_fixed in [5, 10, 20]:
        fixed = run_backtest(df, N_fixed, slots_flat, 20)
        print(f'  固定 N={N_fixed:<2}:                    交易{fixed["trades"]:>4}笔, '
              f'年化{fixed["annual"]:>+.2%}, Sharpe{fixed["sharpe"]:>+.2f}, MaxDD{fixed["max_dd"]:>+.2%}, '
              f'胜率{fixed["win"]:.1%}, PF={fixed["pf"]:.2f}')
    print()
    print(f'  regime → 最佳 N 映射: {best_n_per_regime}')

    # =====================================================================
    # Part 3: 压力测试
    # =====================================================================
    print()
    print('=' * 130)
    print('【Part 3】压力测试: 不同 SLOT_COUNT (资金规模)')
    print('=' * 130)
    print('  占用 > slot_count 时, 当日收益等比例缩减 (模拟资金不足)')
    print()

    best_per_slot = {}
    for slot_count in [5, 10, 20]:
        print(f'--- SLOT_COUNT = {slot_count} ---')
        scored = []
        for N in [1, 2, 3, 5, 8, 10, 15, 20]:
            r = run_backtest(df, N, slots_flat, slot_count=slot_count)
            row(f'N={N}', r)
            if r: scored.append((N, r, score_res(r)))
        scored.sort(key=lambda x: -x[2])
        if scored:
            N, r, _ = scored[0]
            best_per_slot[slot_count] = (N, r)
            print(f'  >> 该 slot_count 最佳 N = {N} '
                  f'(年化{r["annual"]:>+.2%}, Sharpe{r["sharpe"]:>+.2f}, MaxDD{r["max_dd"]:>+.2%}, '
                  f'PF={r["pf"]:.2f})')
        print()

    # =====================================================================
    # 综合矩阵
    # =====================================================================
    print('=' * 130)
    print('【总结】SLOT_COUNT × N 推荐矩阵')
    print('=' * 130)
    print()
    print('| SLOT_COUNT | 推荐 N | 年化 | Sharpe | MaxDD | 胜率 | PF | 适用场景 |')
    print('|---|---|---|---|---|---|---|---|')
    for slot_count in [5, 10, 20]:
        if slot_count not in best_per_slot: continue
        N, r = best_per_slot[slot_count]
        scenario = {5: '小资金 (<50万)', 10: '中等资金 (50-200万)',
                    20: '大资金 (>200万)'}.get(slot_count, '')
        print(f'| {slot_count} | {N} | {r["annual"]:>+.2%} | {r["sharpe"]:>+.2f} | '
              f'{r["max_dd"]:>+.2%} | {r["win"]:>5.1%} | {r["pf"]:.2f} | {scenario} |')

    # 保存 Part 2 + Part 3 的 equity 曲线
    out_frames = []
    for slot_count in [5, 10, 20]:
        for N in [5, 10, 20]:
            r = run_backtest(df, N, slots_flat, slot_count=slot_count)
            if r is None: continue
            out_frames.append(r['equity'].rename(f'eq_slot{slot_count}_N{N}'))
    # 动态 N equity
    dyn_equity = equity.rename('eq_dynamic_N')
    # 对齐 index
    all_dates = sorted(set().union(*[s.index for s in out_frames + [dyn_equity]]))
    combined = pd.DataFrame(index=all_dates)
    for s in out_frames + [dyn_equity]:
        combined[s.name] = s.reindex(all_dates)
    combined.index.name = 'date'
    combined.to_csv('/home/hypnosis/data/quant_base/data/result/v49_regime_stress_equity.csv')
    print('\nPart 2/3 的 equity 曲线已保存: data/result/v49_regime_stress_equity.csv')


if __name__ == '__main__':
    main()
