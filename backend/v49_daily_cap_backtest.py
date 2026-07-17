"""
v49 新数据回测: 挂单数优化 + 分 Tier 仓位

数据: data/result/Calendar_Backtest/full_calendar_trades_v49.csv
      1236 笔信号 (954 笔成交, 282 笔未成交), 2024-01-18 ~ 2026-05-28

实验维度:
  1. 每日挂单上限 N in {1,2,3,4,5,6,8,10,12,15,20}
  2. 仓位模式:
       - 等权   (每笔 1/N 当日分配)
       - 分 Tier (S=2 槽, A=1.5 槽, B=1 槽, C=拒绝)
       - C-tier 硬拒绝 (即使有空槽也不挂)
  3. 排序: (v5_score, gbm_proba, pricing_proba) 降序
  4. 资金: 固定 20 槽, 每槽 1/20, 未用槽位闲置

输出: 各维度组合的 总收益/年化/Sharpe/MaxDD/胜率/PF, 并给出最佳配置
"""
import os, sys, pandas as pd, numpy as np

CSV = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_v49.csv'
SLOT_COUNT = 20
RISK_FREE_DAILY = 0.015 / 252


# =============================================================
# 仓位方案 (函数: tier -> 槽位数)
# =============================================================
def slots_flat(_tier):
    return 1.0

def slots_tiered(tier):
    return {'S': 2.0, 'A': 1.5, 'B_T1D': 1.0, 'B_GBM': 1.0, 'C': 0.0}.get(tier, 1.0)

def slots_s_aggressive(tier):
    return {'S': 3.0, 'A': 1.5, 'B_T1D': 1.0, 'B_GBM': 0.5, 'C': 0.0}.get(tier, 1.0)


# =============================================================
# 回测核心
# =============================================================
def run_backtest(df, N, slot_fn, reject_c=True):
    """
    每日取前 N 信号, 按 slot_fn(tier) 分配槽位, 计算组合日收益
    reject_c=True: C-tier 即使有空槽也不挂
    返回: dict(指标) + equity 序列
    """
    # 按回测日期 + daily_signal_rank 排序 (rank 已预计算: 1=最佳)
    df = df.sort_values(['回测日期', 'daily_signal_rank'])
    dates_all = sorted(df['回测日期'].unique())

    # 每日选取
    selected = []
    total_skipped = 0
    for day in dates_all:
        g = df[df['回测日期'] == day]
        # 硬拒绝 C-tier
        if reject_c:
            g = g[g['v5_tier'] != 'C']
        take = g.head(N)
        selected.append(take)
        total_skipped += len(g) - len(take)
    sel = pd.concat(selected)
    if len(sel) == 0:
        return None

    # 为每笔交易分配槽位 (相对权重)
    sel = sel.copy()
    sel['slots'] = sel['v5_tier'].apply(slot_fn)

    # 准备每日时间序列
    sel['entry'] = pd.to_datetime(sel['成交日期'])
    sel['exit']  = pd.to_datetime(sel['卖出日期'])
    sel['hold']  = (sel['exit'] - sel['entry']).dt.days.clip(lower=1)
    sel['daily_ret'] = sel['收益率'] / sel['hold']

    dates = pd.date_range(sel['entry'].min(), sel['exit'].max())

    # 按 (entry, exit) 区间累加每日槽位占用 & 收益贡献
    day_slot_used = pd.Series(0.0, index=dates)   # 当日占用的槽位总数
    day_ret_raw   = pd.Series(0.0, index=dates)   # 当日收益 (未归一化)
    for _, t in sel.iterrows():
        mask = (day_slot_used.index >= t['entry']) & (day_slot_used.index <= t['exit'])
        day_slot_used[mask] += t['slots']
        day_ret_raw[mask]   += t['daily_ret'] * t['slots']

    # 每日实际收益: 收益贡献 / max(占用槽位, SLOT_COUNT)
    #   - 占用少于 SLOT_COUNT: 剩余槽位闲置 (不产生收益)
    #   - 占用多于 SLOT_COUNT: 等比例缩减 (资金不足)
    scale = day_slot_used.clip(lower=SLOT_COUNT)
    port_ret = day_ret_raw / scale

    equity = (1 + port_ret).cumprod()
    total_ret = equity.iloc[-1] - 1
    days = len(port_ret)
    annual_ret = (1 + total_ret) ** (252 / max(days, 1)) - 1
    sharpe = (port_ret.mean() - RISK_FREE_DAILY) / (port_ret.std() + 1e-9) * np.sqrt(252)
    peak = equity.cummax()
    dd = (equity - peak) / peak
    max_dd = dd.min()

    r = sel['收益率']
    win_rate = (r > 0).mean()
    pf = r[r > 0].sum() / (-r[r < 0].sum() + 1e-9)

    # Tier 分布
    tdist = sel['v5_tier'].value_counts()

    return {
        'trades': len(sel),
        'skipped': total_skipped,
        'days': days,
        'total_ret': total_ret,
        'annual_ret': annual_ret,
        'sharpe': sharpe,
        'max_dd': max_dd,
        'win_rate': win_rate,
        'pf': pf,
        'daily_mean': port_ret.mean(),
        'daily_std': port_ret.std(),
        'tier_dist': dict(tdist),
        'equity': equity,
        'port_ret': port_ret,
    }


# =============================================================
# 打印行
# =============================================================
def row(label, res):
    if res is None:
        print(f'{label:<40} (无数据)')
        return
    print(f"{label:<40} | n={res['trades']:>4} 年化{res['annual_ret']:>+8.2%} "
          f"Sharpe{res['sharpe']:>+6.2f} MaxDD{res['max_dd']:>+7.2%} "
          f"胜率{res['win_rate']:>5.1%} PF{res['pf']:>5.2f} "
          f"S={res['tier_dist'].get('S',0):>3} A={res['tier_dist'].get('A',0):>3} "
          f"B={res['tier_dist'].get('B_T1D',0)+res['tier_dist'].get('B_GBM',0):>4} "
          f"C={res['tier_dist'].get('C',0):>3}")


def main():
    df = pd.read_csv(CSV)
    df = df[df['is_entry'] == True].copy()   # 只保留成交笔
    print(f'数据就绪: {len(df)} 笔成交, 日期 {df["回测日期"].min()} ~ {df["回测日期"].max()}')
    print(f'Tier 分布: {dict(df["v5_tier"].value_counts())}')
    print()

    # =====================================================
    # 实验 1: 扫描 N, 等权仓位, 硬拒绝 C-tier
    # =====================================================
    print('=' * 130)
    print('【实验 1】等权 + 拒绝 C-tier')
    print('=' * 130)
    results_eq = []
    for N in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]:
        res = run_backtest(df, N, slots_flat, reject_c=True)
        results_eq.append((N, res))
        row(f'N={N}', res)

    # =====================================================
    # 实验 2: 扫描 N, 分 Tier 仓位 (S=2, A=1.5, B=1, C=0)
    # =====================================================
    print()
    print('=' * 130)
    print('【实验 2】分 Tier (S=2, A=1.5, B=1, C=0) + 拒绝 C-tier')
    print('=' * 130)
    results_tier = []
    for N in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]:
        res = run_backtest(df, N, slots_tiered, reject_c=True)
        results_tier.append((N, res))
        row(f'N={N}', res)

    # =====================================================
    # 实验 3: S 激进 (S=3, A=1.5, B_T1D=1, B_GBM=0.5, C=0)
    # =====================================================
    print()
    print('=' * 130)
    print('【实验 3】S 激进 (S=3, A=1.5, B_T1D=1, B_GBM=0.5, C=0) + 拒绝 C-tier')
    print('=' * 130)
    results_s = []
    for N in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]:
        res = run_backtest(df, N, slots_s_aggressive, reject_c=True)
        results_s.append((N, res))
        row(f'N={N}', res)

    # =====================================================
    # 实验 4: 不拒绝 C-tier 的对比 (验证 C 的边际价值)
    # =====================================================
    print()
    print('=' * 130)
    print('【实验 4】等权 + 不拒绝 C-tier (对比实验 1, 验证 C-tier 的边际价值)')
    print('=' * 130)
    for N in [5, 10, 15, 20]:
        res = run_backtest(df, N, slots_flat, reject_c=False)
        row(f'N={N} (含 C)', res)

    # =====================================================
    # 综合排名: 年化 × Sharpe × (1 + MaxDD)
    # =====================================================
    print()
    print('=' * 130)
    print('【综合排名】score = 年化 × Sharpe × (1 + MaxDD)')
    print('=' * 130)
    all_runs = (
        [(f'等权 N={N} + 拒C',     n, r) for n, r in results_eq] +
        [(f'Tier N={n} + 拒C',     n, r) for n, r in results_tier] +
        [(f'S激进 N={n} + 拒C',    n, r) for n, r in results_s]
    )
    scored = []
    for label, n, r in all_runs:
        if r is None: continue
        s = r['annual_ret'] * max(r['sharpe'], 0) * (1 + r['max_dd'])
        scored.append((label, n, r, s))
    scored.sort(key=lambda x: -x[3])
    print(f'{"排名":>4} {"方案":<38} {"N":>3} {"年化":>9} {"Sharpe":>8} {"MaxDD":>8} '
          f'{"胜率":>6} {"PF":>5} {"综合":>8}')
    print('-' * 110)
    for i, (label, n, r, s) in enumerate(scored[:15], 1):
        marker = ' ⭐' if i == 1 else ''
        print(f'{i:>4} {label:<38} {n:>3} {r["annual_ret"]:>+8.2%} {r["sharpe"]:>+7.2f} '
              f'{r["max_dd"]:>+7.2%} {r["win_rate"]:>5.1%} {r["pf"]:>5.2f} {s:>+7.3f}{marker}')

    best_label, best_n, best, _ = scored[0]
    print()
    print('=' * 100)
    print(f'🎯 最佳配置: {best_label}  (N={best_n})')
    print(f'   年化收益 : {best["annual_ret"]:>+.2%}')
    print(f'   Sharpe  : {best["sharpe"]:>+.2f}')
    print(f'   MaxDD   : {best["max_dd"]:>+.2%}')
    print(f'   胜率    : {best["win_rate"]:>+.1%}   PF: {best["pf"]:>+.2f}')
    print(f'   Tier 分布: {best["tier_dist"]}')
    print('=' * 100)

    # 保存最佳 equity 曲线
    out = pd.DataFrame({
        'date': best['equity'].index,
        'equity': best['equity'].values,
        'daily_ret': best['port_ret'].values,
    })
    out_path = '/home/hypnosis/data/quant_base/data/result/v49_best_equity.csv'
    out.to_csv(out_path, index=False)
    print(f'\n最佳 equity 曲线: {out_path}')


if __name__ == '__main__':
    main()
