"""
v49 未成交 / 到期交易分析

目标:
  1. 未成交 (is_entry=False): 挂单超时撤销 + 大幅低开放弃
     - 分布特征: 按 v5_tier / market_env / T1_D / GBM 切分
     - 如果能成交, 预期收益多少? (用 future_mfe / future_mae 估计)
     - 哪些特征子集"应该能赚钱却被挂单策略浪费", 可调整入场策略挽回
  2. 到期 (exit_type='expired'): 真正入场但持仓到期未达止盈止损
     - 15 日后续表现 (如果有 future_mfe 数据)
     - 特征画像: 哪些入场特征容易陷入"到期"泥潭
     - 能否通过调整止盈/止损/持仓周期挽回

数据: data/result/Calendar_Backtest/full_calendar_trades_v49.csv
"""
import os, pandas as pd, numpy as np

CSV = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_v49.csv'


def section(title):
    print(f"\n{'='*110}\n{title}\n{'='*110}")


def summarize(sub, label, prefix='  '):
    if len(sub) == 0:
        print(f'{prefix}{label:<55} (空)')
        return
    r = sub['收益率']
    wr = (r > 0).mean()
    avg = r.mean()
    pf = r[r > 0].sum() / (-r[r < 0].sum() + 1e-9)
    tp = (sub['exit_type'] == 'take_profit').mean()
    print(f"{prefix}{label:<55} | n={len(sub):>4} 胜率{wr:>5.1%} 均收益{avg:>+7.2%} "
          f"PF{pf:>5.2f} 止盈率{tp:>5.1%}")


def main():
    df = pd.read_csv(CSV)
    print(f'总信号: {len(df)}')
    print(f'  is_entry=True:  {(df["is_entry"]==True).sum()}')
    print(f'  is_entry=False: {(df["is_entry"]==False).sum()}')

    # =====================================================================
    # Part A: 未成交 (is_entry=False)
    # =====================================================================
    section('Part A: 未成交交易 (is_entry=False)')
    not_entry = df[df['is_entry'] == False].copy()
    print(f'未成交笔数: {len(not_entry)}')
    print(f'\n出场类型分布:')
    print(not_entry['exit_type'].value_counts())

    # 用 future_mfe / future_mae 估算"如果入场"的潜在表现
    #   对 order_timeout: trigger_buy 挂单, 但没成交, 看后续价格是否触及目标
    #   对 gap_abandoned: 大幅低开被放弃, 看后续走势
    print(f"\n--- 未成交信号的 future_mfe / future_mae 分布 ---")
    for et in not_entry['exit_type'].unique():
        sub = not_entry[not_entry['exit_type'] == et]
        print(f"\n  [{et}] (n={len(sub)})")
        for col in ['future_mfe', 'future_mae', '价格偏离']:
            if col in sub.columns:
                vals = sub[col].dropna()
                if len(vals) > 0:
                    print(f"    {col:<15}: mean={vals.mean():>+.3f}  "
                          f"median={vals.median():>+.3f}  "
                          f"[Q25={vals.quantile(0.25):>+.3f}, Q75={vals.quantile(0.75):>+.3f}]  "
                          f"正比例{(vals>0).mean():.1%}")

    # A.1 order_timeout (挂单超时撤销) 分析
    section('A.1 挂单超时撤销 (order_timeout) - 可能挽回')
    ot = not_entry[not_entry['exit_type'] == 'order_timeout']
    print(f'样本: {len(ot)}')

    # 按 v5_tier 分层
    print(f'\n  按 v5_tier:')
    for tier, sub in ot.groupby('v5_tier'):
        summarize(sub, tier)

    # 按 future_mfe >= 10% (如果入场本来能赚 10%+)
    big_win = ot[ot['future_mfe'] >= 0.10]
    print(f"\n  ⭐ 其中 future_mfe>=10% 的 (被浪费的牛股): {len(big_win)} ({len(big_win)/max(len(ot),1):.1%})")
    if len(big_win) > 0:
        print(f'    v5_tier 分布: {dict(big_win["v5_tier"].value_counts())}')
        print(f'    market_env 分布: {dict(big_win["market_env"].value_counts())}')
        print(f'    均 future_mfe: {big_win["future_mfe"].mean():+.2%}')
        print(f'    GBM 分布: mean={big_win["gbm_proba"].mean():.3f}, '
              f'Q25={big_win["gbm_proba"].quantile(0.25):.3f}, '
              f'Q75={big_win["gbm_proba"].quantile(0.75):.3f}')
        print(f'    价格偏离 (入场价 vs 低点): mean={big_win["价格偏离"].mean():+.3%}')

    # 按特征子集找"被浪费最多"的
    print(f'\n  特征子集过滤 (找出挽回价值最高的):')
    conds = [
        ('v5_tier == S',          ot['v5_tier'] == 'S'),
        ('v5_tier == A',          ot['v5_tier'] == 'A'),
        ('v5_tier in (B_T1D, B_GBM)', ot['v5_tier'].isin(['B_T1D', 'B_GBM'])),
        ('v5_tier == C',          ot['v5_tier'] == 'C'),
        ('T1_D == 1',             ot['T1_D'] == 1),
        ('GBM >= 0.75',           ot['gbm_proba'] >= 0.75),
        ('GBM >= 0.80',           ot['gbm_proba'] >= 0.80),
        ('未来 MFE>=10%',          ot['future_mfe'] >= 0.10),
        ('S + future_mfe>=10%',   (ot['v5_tier'] == 'S') & (ot['future_mfe'] >= 0.10)),
        ('B + future_mfe>=10%',   (ot['v5_tier'].isin(['B_T1D','B_GBM'])) & (ot['future_mfe'] >= 0.10)),
    ]
    print(f'  {"条件":<45} {"n":>5} {"future_mfe均值":>14} {"正比例":>7} {"可挽回 EV (n × mean)":>20}')
    for name, cond in conds:
        sub = ot[cond]
        if len(sub) == 0: continue
        mfe = sub['future_mfe'].mean()
        ev = len(sub) * mfe
        pos = (sub['future_mfe'] > 0).mean()
        print(f'  {name:<45} {len(sub):>5} {mfe:>+13.3%} {pos:>6.1%} {ev:>+19.2f} (标准化 EV)')

    # A.2 大幅低开放弃 (gap_abandoned) 分析
    section('A.2 大幅低开放弃 (gap_abandoned) - 可能挽回')
    ga = not_entry[not_entry['exit_type'] == 'gap_abandoned']
    print(f'样本: {len(ga)}')
    print(f'\n  按 v5_tier:')
    for tier, sub in ga.groupby('v5_tier'):
        summarize(sub, tier)
    big_win_ga = ga[ga['future_mfe'] >= 0.10]
    print(f"\n  ⭐ future_mfe>=10% 的: {len(big_win_ga)} ({len(big_win_ga)/max(len(ga),1):.1%})")
    if len(big_win_ga) > 0:
        print(f'    均 future_mfe: {big_win_ga["future_mfe"].mean():+.2%}')
        print(f'    v5_tier: {dict(big_win_ga["v5_tier"].value_counts())}')

    # =====================================================================
    # Part B: 到期交易 (exit_type='expired')
    # =====================================================================
    section('Part B: 到期交易 (exit_type=expired)')
    exp = df[(df['is_entry'] == True) & (df['exit_type'] == 'expired')].copy()
    entered = df[df['is_entry'] == True]
    print(f'到期笔数: {len(exp)} / 入场{len(entered)} ({len(exp)/max(len(entered),1):.1%})')

    # B.1 基础表现
    print(f'\n  --- B.1 到期 vs 其他出场的表现对比 ---')
    for et in ['take_profit', 'expired', 'stop_loss', 'circuit_breaker', 'time_decay', 'form_break']:
        sub = entered[entered['exit_type'] == et]
        summarize(sub, et)

    # B.2 到期交易的特征画像
    print(f'\n  --- B.2 到期交易特征画像 (中位数 vs 其他入场) ---')
    other = entered[entered['exit_type'] != 'expired']
    feats = ['gbm_proba', 'pricing_proba', 'ma_slope', 'bias_20', 'swing',
             'v5_score', 'entry_slip', '持仓天数', 'MFE', 'MAE']
    print(f'  {"特征":<15} {"到期(中位)":>12} {"其他(中位)":>12} {"差异":>10}')
    for f in feats:
        if f not in exp.columns: continue
        a = exp[f].median()
        b = other[f].median()
        print(f'  {f:<15} {a:>+12.3f} {b:>+12.3f} {a-b:>+10.3f}')

    # B.3 到期交易按 v5_tier 切分
    print(f'\n  --- B.3 到期交易按 v5_tier 切分 ---')
    for tier, sub in exp.groupby('v5_tier'):
        summarize(sub, tier)

    # B.4 到期交易的 future_mfe (7 日最大潜在收益) 分布
    print(f'\n  --- B.4 到期交易的 future_mfe / future_mae ---')
    for col in ['future_mfe', 'future_mae', 'MFE', 'MAE', '持仓天数']:
        vals = exp[col].dropna()
        if len(vals) == 0: continue
        print(f'  {col:<15}: mean={vals.mean():>+.3f} median={vals.median():>+.3f} '
              f'Q25={vals.quantile(0.25):>+.3f} Q75={vals.quantile(0.75):>+.3f}')

    # B.5 到期但 MFE 接近止盈 (差一点就吃到) 的"遗憾单"
    near_tp = exp[exp['MFE'] >= 0.07]   # MFE 接近 10% 止盈线
    print(f'\n  --- B.5 遗憾单: MFE>=7% 但未达止盈 ---')
    print(f'  样本: {len(near_tp)} / {len(exp)} ({len(near_tp)/max(len(exp),1):.1%})')
    if len(near_tp) > 0:
        print(f'  均 MFE: {near_tp["MFE"].mean():+.2%}')
        print(f'  均收益率: {near_tp["收益率"].mean():+.2%}')
        print(f'  v5_tier 分布: {dict(near_tp["v5_tier"].value_counts())}')
        print(f'  均持仓天数: {near_tp["持仓天数"].mean():.1f}')
        print(f'  market_env: {dict(near_tp["market_env"].value_counts())}')

    # B.6 遗憾单按特征子集过滤, 找可优化
    print(f'\n  --- B.6 挽回策略: 遗憾单中按特征切分 ---')
    conds_exp = [
        ('S/A-tier',               near_tp['v5_tier'].isin(['S', 'A'])),
        ('B-tier',                 near_tp['v5_tier'].isin(['B_T1D', 'B_GBM'])),
        ('C-tier',                 near_tp['v5_tier'] == 'C'),
        ('GBM>=0.75',              near_tp['gbm_proba'] >= 0.75),
        ('T1_D=1',                 near_tp['T1_D'] == 1),
        ('market=震荡',             near_tp['market_env'] == '震荡'),
        ('market=股灾',             near_tp['market_env'] == '股灾暴跌'),
        ('持仓<5天 (短平快)',        near_tp['持仓天数'] < 5),
        ('持仓>=5天 (磨底)',         near_tp['持仓天数'] >= 5),
    ]
    print(f'  {"条件":<35} {"n":>4} {"MFE":>8} {"收益率":>8} {"天数":>6}')
    for name, cond in conds_exp:
        sub = near_tp[cond]
        if len(sub) == 0: continue
        print(f'  {name:<35} {len(sub):>4} {sub["MFE"].mean():>+7.2%} '
              f'{sub["收益率"].mean():>+7.2%} {sub["持仓天数"].mean():>5.1f}')

    # =====================================================================
    # 综合: 挽回策略建议
    # =====================================================================
    section('综合: 挽回策略建议')

    # 计算: 如果所有 order_timeout 的 S-tier 都强制市价成交, 额外收益
    print('\n  【挽回机会 1】order_timeout 中的高价值信号')
    recoverable_ot = ot[ot['v5_tier'].isin(['S', 'A'])]
    if len(recoverable_ot) > 0:
        print(f'    S+A tier order_timeout: {len(recoverable_ot)} 笔')
        print(f'    如果强制入场 (按 future_mfe 的 50% 估算实际收益):')
        est = recoverable_ot['future_mfe'].mean() * 0.5
        print(f'    单笔 EV ≈ {est:>+.2%}, 总 EV ≈ {est * len(recoverable_ot):>+.2f} (normalized)')

    print('\n  【挽回机会 2】遗憾单 (MFE>=7% 但未止盈)')
    print(f'    样本: {len(near_tp)} 笔, 均 MFE {near_tp["MFE"].mean():+.2%} 但均收益 {near_tp["收益率"].mean():+.2%}')
    if len(near_tp) > 0:
        gap = near_tp['MFE'].mean() - near_tp['收益率'].mean()
        print(f'    潜在挽回空间: {gap:+.2%} / 笔 (通过降低止盈线 / 移动止盈)')

    print('\n  【挽回机会 3】到期交易中持仓过长 (>5 天) 的信号')
    long_exp = exp[exp['持仓天数'] >= 5]
    if len(long_exp) > 0:
        print(f'    样本: {len(long_exp)} 笔, 均收益 {long_exp["收益率"].mean():+.2%}')
        print(f'    建议: 对持仓>=5 天且 MFE<3% 的票强制提前平仓, 减少时间成本')


if __name__ == '__main__':
    main()
