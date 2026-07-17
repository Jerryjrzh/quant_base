"""
v5 评分机制下的每日挂单数优化回测

核心问题: 每天最多挂 N 单 (N in 1..20), 按新评分排序选取, 哪个 N 让收益最理想?

设计要点:
  1. 新评分 (v5) 计算: 复用 walk_forward_tester_s 的 T1_D 定义 + GBM 门控
     - S 120 : T1_D=1 + GBM>=0.80
     - A 110 : T1_D=1 + GBM>=0.75
     - B  95 : T1_D=1 + GBM<0.75  或  GBM>=0.70
     - C  70 : 其他
  2. 排序 key = (score, gbm_proba, pricing_proba)  高到低
  3. 对每个 N in {1,2,3,4,5,6,8,10,12,15,20}, 每天取前 N 个挂单
  4. 模拟: 等权仓位 (每笔仓位 = 总资金/20, 未用仓位闲置)
  5. 逐日计算组合收益: 当日持仓中所有交易的"当日分摊收益"
  6. 指标: 总收益, 年化收益, Sharpe, MaxDD, 胜率, PF, 交易笔数
"""
import os, sys, pandas as pd, numpy as np
from pathlib import Path

CSV = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_27m.csv'
MAX_DAILY = 20    # 每日最大挂单数
SLOT_COUNT = 20   # 资金槽位 (固定 20 个仓位槽, 不论 N 多少)
RISK_FREE_DAILY = 0.015 / 252   # 年化 1.5% 无风险收益


def compute_v5_score(row):
    """根据 T1_D 与 GBM 计算新评分 (复刻 walk_forward_tester_s v5 块)"""
    T1_D = 1 if row.get('T1_D') == 1 else 0
    gbm = float(row.get('gbm_proba', 0))
    if gbm == 0:                          # GBM 模块未启用, 用旧分
        return float(row.get('评估分', 95))
    if T1_D == 1:
        if gbm >= 0.80: return 120
        if gbm >= 0.75: return 110
        return 95
    if gbm >= 0.70: return 95
    return 70


def prepare_trades():
    """读取回测 CSV, 过滤未成交, 计算新评分与交易生命周期"""
    df = pd.read_csv(CSV)
    # 只取"已成交"交易 (剔除挂单超时/大幅低开放弃)
    df = df[~df['交易状态'].isin(['挂单超时撤销', '大幅低开放弃'])].copy()
    print(f'原始交易: {len(pd.read_csv(CSV))}  入场成交: {len(df)}')

    # 解析 morse_features 拿 T1_D (原始数据)
    def parse_mf(s):
        out = {}
        if not isinstance(s, str): return out
        for kv in s.split('|'):
            if ':' in kv:
                k, v = kv.split(':', 1)
                try: out[k] = float(v)
                except: out[k] = v
        return out
    feats = df['morse_features'].apply(parse_mf).apply(pd.Series)
    # 兼容新旧 morse_features 格式 (旧版没有 GBM 标签, 用 csv 列)
    if 'T1_D' in feats.columns:
        df['T1_D'] = feats['T1_D'].fillna(0).astype(int)
    else:
        # 回退: 通过 d_pct 重算 (需要 raw data, 这里用 评估分=85 作为代理)
        df['T1_D'] = (df['评估分'] == 85).astype(int)

    df['v5_score'] = df.apply(compute_v5_score, axis=1)
    df['entry'] = pd.to_datetime(df['成交日期'])
    df['exit']  = pd.to_datetime(df['卖出日期'])
    df['hold']  = (df['exit'] - df['entry']).dt.days.clip(lower=1)
    df['daily_ret'] = df['收益率'] / df['hold']    # 每日分摊收益

    # 排序 key: v5_score desc, gbm desc, pricing desc, 收益 (用于后续 tie-break)
    df['_rank_key'] = (
        df['v5_score'] * 1e9 +
        df['gbm_proba'] * 1e6 +
        df['pricing_proba'] * 1e3
    )
    return df


def backtest(df, N, verbose=False):
    """
    模拟: 每天最多挂 N 单 (按 _rank_key 降序取前 N)
    资金模型: 固定 20 槽, 每槽占总资金 1/20
    组合日收益 = sum(每笔持仓当日分摊收益 * 1/20)
    """
    # 按回测日期分组, 每天选前 N
    daily_groups = df.groupby('回测日期')
    selected = []
    skipped_by_cap = 0
    for day, g in daily_groups:
        g_sorted = g.sort_values('_rank_key', ascending=False)
        take = g_sorted.head(N)
        selected.append(take)
        skipped_by_cap += max(0, len(g) - N)
    sel = pd.concat(selected)

    if len(sel) == 0:
        return None

    # 构建每日时间序列: 从第一天入场到最后一天卖出
    dates = pd.date_range(sel['entry'].min(), sel['exit'].max())
    # 为性能, 用向量化: 每笔交易对每日组合收益的贡献
    #   trade_ret_on_day(d) = daily_ret  如果 entry <= d <= exit
    #   组合日收益 = sum(trade_ret_on_day) / SLOT_COUNT

    # 用区间树加速: 将每笔交易的 daily_ret 累加到对应日期
    day_contrib = pd.Series(0.0, index=dates)
    for _, t in sel.iterrows():
        mask = (day_contrib.index >= t['entry']) & (day_contrib.index <= t['exit'])
        day_contrib[mask] += t['daily_ret'] / SLOT_COUNT

    port_ret = day_contrib
    equity = (1 + port_ret).cumprod()

    total_ret = equity.iloc[-1] - 1
    days = len(port_ret)
    annual_ret = (1 + total_ret) ** (252 / max(days, 1)) - 1
    sharpe = (port_ret.mean() - RISK_FREE_DAILY) / (port_ret.std() + 1e-9) * np.sqrt(252)
    # MaxDD
    peak = equity.cummax()
    dd = (equity - peak) / peak
    max_dd = dd.min()
    # 胜率 / PF (按交易维度)
    r = sel['收益率']
    win_rate = (r > 0).mean()
    pf = r[r > 0].sum() / (-r[r < 0].sum() + 1e-9)
    # Tier 分布
    tier_s = (sel['v5_score'] == 120).sum()
    tier_a = (sel['v5_score'] == 110).sum()
    tier_b = (sel['v5_score'] == 95).sum()
    tier_c = (sel['v5_score'] == 70).sum()

    return {
        'N': N,
        '总交易笔数': len(sel),
        '被限额剔除': skipped_by_cap,
        '剔除率': skipped_by_cap / (len(sel) + skipped_by_cap),
        '持仓天数': days,
        '总收益': total_ret,
        '年化收益': annual_ret,
        'Sharpe': sharpe,
        'MaxDD': max_dd,
        '胜率': win_rate,
        'PF': pf,
        '日均收益': port_ret.mean(),
        '日均波动': port_ret.std(),
        'S单数': tier_s,
        'A单数': tier_a,
        'B单数': tier_b,
        'C单数': tier_c,
        'S+A占比': (tier_s + tier_a) / len(sel),
        'equity': equity,
        'port_ret': port_ret,
    }


def main():
    df = prepare_trades()
    print(f'回测数据就绪: {len(df)} 笔成交, 日期范围 {df["entry"].min().date()} ~ {df["exit"].max().date()}')
    print()

    # 基线: 不做任何限额 (N=∞), 相当于 N=200
    base = backtest(df, 999)
    print(f"基线 (不限挂单数): {base['总交易笔数']} 笔, 总收益{base['总收益']:>+.2%}, "
          f"年化{base['年化收益']:>+.2%}, Sharpe{base['Sharpe']:>+5.2f}, MaxDD{base['MaxDD']:>+6.2%}")
    print()

    # 扫描 N in 1..20
    print(f'{"N":>3} | {"笔数":>6} {"剔除率":>7} | {"总收益":>9} {"年化":>8} {"Sharpe":>7} {"MaxDD":>7} | '
          f'{"胜率":>6} {"PF":>5} | {"S":>4} {"A":>4} {"B":>5} {"C":>5} {"S+A":>5}')
    print('-' * 115)
    results = []
    for N in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20]:
        res = backtest(df, N)
        results.append(res)
        print(f"{res['N']:>3} | {res['总交易笔数']:>6} {res['剔除率']:>6.1%} | "
              f"{res['总收益']:>+8.2%} {res['年化收益']:>+7.2%} {res['Sharpe']:>+6.2f} {res['MaxDD']:>+6.2%} | "
              f"{res['胜率']:>5.1%} {res['PF']:>5.2f} | "
              f"{res['S单数']:>4} {res['A单数']:>4} {res['B单数']:>5} {res['C单数']:>5} {res['S+A占比']:>4.1%}")

    # 综合评分: 年化 * Sharpe * (1 + 最小(MaxDD, 0)的绝对值惩罚)
    print()
    print('=== 综合排名 (综合得分 = 年化收益 × Sharpe × (1 - |MaxDD|)) ===')
    for r in results:
        r['综合'] = r['年化收益'] * max(r['Sharpe'], 0) * (1 + r['MaxDD'])   # MaxDD 为负
    results.sort(key=lambda x: -x['综合'])
    print(f'{"排名":>4} {"N":>3} {"年化":>8} {"Sharpe":>7} {"MaxDD":>7} {"胜率":>6} {"PF":>5} {"综合":>8}')
    print('-' * 65)
    for i, r in enumerate(results, 1):
        marker = ' ⭐' if i == 1 else ''
        print(f"{i:>4} {r['N']:>3} {r['年化收益']:>+7.2%} {r['Sharpe']:>+6.2f} {r['MaxDD']:>+6.2%} "
              f"{r['胜率']:>5.1%} {r['PF']:>5.2f} {r['综合']:>+7.3f}{marker}")

    best = results[0]
    print()
    print('=' * 80)
    print(f'🎯 最佳每日挂单数: N = {best["N"]}')
    print(f'   年化收益: {best["年化收益"]:>+.2%}')
    print(f'   Sharpe : {best["Sharpe"]:>+.2f}')
    print(f'   MaxDD  : {best["MaxDD"]:>+.2%}')
    print(f'   胜率   : {best["胜率"]:>+.1%}  PF: {best["PF"]:>+.2f}')
    print(f'   S+A 占比: {best["S+A占比"]:>+.1%}')
    print(f'   被剔除 : {best["剔除率"]:>+.1%} ({best["被限额剔除"]} 笔)')
    print('=' * 80)

    # 保存 equity 曲线供可视化
    out = pd.DataFrame({
        'date': best['equity'].index,
        f'equity_N{best["N"]}': best['equity'].values,
    })
    out_path = '/home/hypnosis/data/quant_base/data/result/v5_daily_cap_best.csv'
    out.to_csv(out_path, index=False)
    print(f'\n最佳 N 的 equity 曲线已保存: {out_path}')


if __name__ == '__main__':
    main()
