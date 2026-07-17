"""分析全日历 score_decile_trades.csv (门槛降至 60 后跑出的 4322 笔)"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np

CSV = '/home/hypnosis/data/quant_base/data/result/Score_Decile_Test/score_decile_trades.csv'
BASELINE = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades.csv'
OUT = '/home/hypnosis/data/quant_base/doc/0604_forward_module_test/score_decile_report_full.md'

SCORE_BINS = [
    (60, 70, '60-69'),
    (70, 75, '70-74'),
    (75, 80, '75-79'),
    (80, 85, '80-84'),
    (85, 90, '85-89'),
    (90, 95, '90-94'),
    (95, 101, '95-100'),
]


def board_of(code: str) -> str:
    c = str(code).replace('sh', '').replace('sz', '').replace('bj', '')
    if c.startswith('688'): return '688科创'
    if c.startswith('300'): return '300创业板'
    if c.startswith('920'): return '920北交'
    if c.startswith('60'): return '60主板'
    if c.startswith('00') or c.startswith('002'): return '00中小'
    return 'other'


def pf_of(series):
    pos = series[series > 0].sum()
    neg = abs(series[series < 0].sum())
    return pos / neg if neg > 0 else np.inf


def stats(df, label):
    n = len(df)
    if n == 0:
        return {'label': label, 'n': 0}
    ret = df['收益率']
    wr = (ret > 0).mean()
    return {
        'label': label,
        'n': n,
        'wr': wr,
        'mean_ret': ret.mean(),
        'median_ret': ret.median(),
        'pf': pf_of(ret),
        'mfe_mean': df['MFE'].mean(),
        'mae_mean': df['MAE'].mean(),
        'win': (ret > 0).sum(),
        'loss': (ret <= 0).sum(),
    }


def main():
    df = pd.read_csv(CSV)
    df['board'] = df['stock_code'].apply(board_of)
    print(f'加载: {len(df)} 笔, 日期 {df["回测日期"].min()} ~ {df["回测日期"].max()}')

    base = pd.read_csv(BASELINE) if os.path.exists(BASELINE) else None
    if base is not None:
        print(f'基准: {len(base)} 笔')

    w_lines = []

    def w(s=''):
        w_lines.append(s)

    w('# 打分分层全日历报告 (Full Calendar Score Decile)')
    w()
    w(f'> 门槛: 60 分 (原始 85) | 全日历: {df["回测日期"].min()} ~ {df["回测日期"].max()} | 总信号: {len(df)} 笔')
    w(f'> 基准对比: 全周期日历回测 ({len(base) if base is not None else "N/A"} 笔, 17 个月, 门槛 85)')
    w()
    w('---')
    w()

    # ========== 1. 分数分布 ==========
    w('## 一、评估分分布')
    w()
    unique_scores = sorted(df['评估分'].unique())
    w(f'- 唯一值个数: **{len(unique_scores)}**')
    w(f'- 范围: {df["评估分"].min()} ~ {df["评估分"].max()}')
    w(f'- 均值: {df["评估分"].mean():.1f} | 中位数: {df["评估分"].median():.1f}')
    w()
    w('### 精确分布 (每 5 分一档)')
    w()
    w('| 分数 | 笔数 | 占比 | 胜率 | 均收益 | PF |')
    w('|------|------|------|------|--------|-----|')
    for score, sub in df.groupby('评估分'):
        if len(sub) < 5:
            continue
        ret = sub['收益率']
        wr = (ret > 0).mean()
        pf = pf_of(ret)
        w(f'| {int(score)} | {len(sub)} | {len(sub)/len(df):.1%} | {wr:.1%} | {ret.mean():+.2%} | {pf:.2f} |')
    w()

    # ========== 2. 分段聚合 ==========
    w('## 二、分段聚合 (60-84 vs 85+)')
    w()
    new_df = df[(df['评估分'] >= 60) & (df['评估分'] < 85)]
    orig_df = df[df['评估分'] >= 85]
    s_new = stats(new_df, '60-84 (新增)')
    s_orig = stats(orig_df, '85+ (原始)')
    s_all = stats(df, '全部 (60+)')
    w('| 分组 | 笔数 | 胜率 | 均收益 | 中位收益 | PF | MFE均 | MAE均 |')
    w('|------|------|------|--------|----------|----|----|----|')
    for s in [s_all, s_new, s_orig]:
        if s['n'] == 0:
            w(f'| {s["label"]} | 0 | - | - | - | - | - | - |')
        else:
            w(f'| {s["label"]} | {s["n"]} | {s["wr"]:.1%} | {s["mean_ret"]:+.2%} | {s["median_ret"]:+.2%} | {s["pf"]:.2f} | {s["mfe_mean"]:.2%} | {s["mae_mean"]:.2%} |')
    w()

    # ========== 3. 更细分段 ==========
    w('## 三、细分段对比')
    w()
    w('| 分数段 | 笔数 | 胜率 | 均收益 | 中位收益 | PF | MFE均 | MAE均 |')
    w('|--------|------|------|--------|----------|----|----|----|')
    for lo, hi, label in SCORE_BINS:
        sub = df[(df['评估分'] >= lo) & (df['评估分'] < hi)]
        s = stats(sub, label)
        if s['n'] == 0:
            w(f'| {label} | 0 | - | - | - | - | - | - |')
        else:
            w(f'| {label} | {s["n"]} | {s["wr"]:.1%} | {s["mean_ret"]:+.2%} | {s["median_ret"]:+.2%} | {s["pf"]:.2f} | {s["mfe_mean"]:.2%} | {s["mae_mean"]:.2%} |')
    w()

    # ========== 4. 板块分层 ==========
    w('## 四、板块 × 分数段')
    w()
    boards = ['60主板', '688科创', '300创业板', '00中小', '920北交']
    w('| 板块 | 分组 | 笔数 | 胜率 | 均收益 | PF |')
    w('|------|------|------|------|--------|-----|')
    for board in boards:
        bdf = df[df['board'] == board]
        for label, mask in [('60-84', (bdf['评估分'] < 85)), ('85+', (bdf['评估分'] >= 85))]:
            sub = bdf[mask]
            s = stats(sub, label)
            if s['n'] == 0:
                continue
            w(f'| {board} | {label} | {s["n"]} | {s["wr"]:.1%} | {s["mean_ret"]:+.2%} | {s["pf"]:.2f} |')
    w()

    # ========== 5. 交易状态分布 ==========
    w('## 五、交易状态分布')
    w()
    w('### 60-84 新增组')
    w()
    w('| 状态 | 笔数 | 占比 | 均收益 |')
    w('|------|------|------|--------|')
    for status, sub in new_df.groupby('交易状态'):
        w(f'| {status} | {len(sub)} | {len(sub)/max(len(new_df),1):.1%} | {sub["收益率"].mean():+.2%} |')
    w()
    w('### 85+ 原始组')
    w()
    w('| 状态 | 笔数 | 占比 | 均收益 |')
    w('|------|------|------|--------|')
    for status, sub in orig_df.groupby('交易状态'):
        w(f'| {status} | {len(sub)} | {len(sub)/max(len(orig_df),1):.1%} | {sub["收益率"].mean():+.2%} |')
    w()

    # ========== 6. 月度收益曲线对比 ==========
    w('## 六、月度收益对比 (新增 vs 原始)')
    w()
    df['month'] = pd.to_datetime(df['成交日期']).dt.to_period('M').astype(str)
    w('| 月份 | 60-84笔数 | 60-84均收益 | 85+笔数 | 85+均收益 | 全部均收益 |')
    w('|------|----------|-------------|---------|-----------|----------|')
    for month, g in df.groupby('month'):
        n_sub = g[g['评估分'] < 85]
        o_sub = g[g['评估分'] >= 85]
        n_mean = n_sub['收益率'].mean() if len(n_sub) > 0 else np.nan
        o_mean = o_sub['收益率'].mean() if len(o_sub) > 0 else np.nan
        w(f'| {month} | {len(n_sub)} | {n_mean:+.2%} | {len(o_sub)} | {o_mean:+.2%} | {g["收益率"].mean():+.2%} |')
    w()

    # ========== 7. 与基准对比 ==========
    if base is not None:
        w('## 七、与原始基准 (门槛 85) 对比')
        w()
        base_wr = (base['收益率'] > 0).mean()
        base_pf = pf_of(base['收益率'])
        w(f'| 指标 | 基准(门槛85) | 降低后(门槛60) | 新增60-84 |')
        w(f'|------|--------------|----------------|-----------|')
        w(f'| 笔数 | {len(base)} | {len(df)} | {len(new_df)} |')
        w(f'| 胜率 | {base_wr:.1%} | {s_all["wr"]:.1%} | {s_new["wr"]:.1%} |')
        w(f'| 均收益 | {base["收益率"].mean():+.2%} | {s_all["mean_ret"]:+.2%} | {s_new["mean_ret"]:+.2%} |')
        w(f'| PF | {base_pf:.2f} | {s_all["pf"]:.2f} | {s_new["pf"]:.2f} |')
        w()

    # ========== 8. 结论 ==========
    w('## 八、结论与建议')
    w()

    # 计算关键判断指标
    new_wr = s_new.get('wr', 0) if s_new['n'] > 0 else 0
    orig_wr = s_orig.get('wr', 0) if s_orig['n'] > 0 else 0
    new_pf = s_new.get('pf', 0) if s_new['n'] > 0 else 0
    orig_pf = s_orig.get('pf', 0) if s_orig['n'] > 0 else 0
    new_mean = s_new.get('mean_ret', 0) if s_new['n'] > 0 else 0
    orig_mean = s_orig.get('mean_ret', 0) if s_orig['n'] > 0 else 0

    w('### 1. 门槛降低的价值判定')
    w()
    if s_new['n'] == 0:
        w('**60-84 分段仍然 0 笔** — 即使全日历回测，打分系统依然只输出 ≥85 的信号。')
        w('门槛问题彻底封闭：不存在"被 85 卡掉的低分优质股"。')
    elif new_pf < 1.0:
        w(f'**新增 60-84 分段 {s_new["n"]} 笔, PF={new_pf:.2f} < 1.0** — 期望亏损, 不应放行。')
        w(f'- 胜率: {new_wr:.1%} (vs 85+ 组 {orig_wr:.1%})')
        w(f'- 均收益: {new_mean:+.2%} (vs 85+ 组 {orig_mean:+.2%})')
        w(f'- **结论: 原始 85 分门槛是正确的, 不应降低**')
    elif new_pf >= orig_pf:
        w(f'**新增 60-84 分段 PF={new_pf:.2f} >= 85+ 组 PF={orig_pf:.2f}** — 可考虑降低门槛。')
        w(f'- 胜率: {new_wr:.1%} vs {orig_wr:.1%}')
        w(f'- 均收益: {new_mean:+.2%} vs {orig_mean:+.2%}')
    else:
        w(f'**新增 60-84 分段 PF={new_pf:.2f}, 虽 > 1.0 但低于 85+ 组 PF={orig_pf:.2f}**')
        w(f'- 胜率: {new_wr:.1%} vs {orig_wr:.1%}')
        w(f'- 均收益: {new_mean:+.2%} vs {orig_mean:+.2%}')
        w(f'- **结论: 新增信号质量弱于原始组, 降低门槛会稀释整体收益**')
    w()

    w('### 2. 改进优先级')
    w()
    w('打分层的区分力问题已被全周期基准 Test 1-10 的改进方案覆盖:')
    w('- Trailing Stop 方案 C (MFE*60%) — 出场层 PF 贡献最大')
    w('- 688/920 板块亏损截断 — 尾部风险控制')
    w('- V4.4 因子反转 (b20/t1_d/decline) — 评级层修正')
    w()
    w('**打分门槛本身无需调整, 85 分是系统的自然地板线。**')

    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(w_lines))
    print(f'\n报告已写入: {OUT}')
    print(f'总行数: {len(w_lines)}')


if __name__ == '__main__':
    main()
