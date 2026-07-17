"""
评估分倒推 → 条件组合
对每个离散评分 (85/90/95/110/115), 分析其对应入场特征分布,
找出能区分"洗盘票/短期爆发/真亏损"的核心条件, 叠加 GBM 确认,
最后给出以收益+安全为目标的评分规则重构建议.

数据来源:
  - full_calendar_trades_27m.csv  (入场回测 + 评估分 + gbm_proba)
  - expired_15d_analysis.csv      (15 日后续表现, 区分洗盘/真亏损)
"""
import os, sys, pandas as pd, numpy as np

CSV_MAIN = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_27m.csv'
CSV_15D = '/home/hypnosis/data/quant_base/data/result/expired_15d_analysis.csv'

def load_merged():
    df = pd.read_csv(CSV_MAIN)
    d15 = pd.read_csv(CSV_15D)
    expired = df[df['交易状态'].isin(['持仓到期', '时间衰减平仓'])].copy()
    d15['_key'] = d15['stock_code'] + '_' + d15['回测日期']
    expired['_key'] = expired['stock_code'] + '_' + expired['回测日期']
    m = expired.merge(d15[['_key', 'mfe_15d', 'mae_15d', 'return_15d',
                            'would_tp10', 'would_sl10',
                            'total_mfe_from_entry', 'tp_hit_day']],
                      on='_key', how='inner')
    m['is_wash'] = m['total_mfe_from_entry'] > 0.10             # 洗盘(入场后总MFE>10%)
    m['is_boom'] = (m['tp_hit_day'] >= 0) & (m['tp_hit_day'] <= 5)  # 短期爆发(5日内触10%止盈)
    m['is_loser'] = (m['mfe_15d'] < 0.05) & (m['return_15d'] < 0)
    return m


def label_row(r):
    if r['is_boom']: return '短期爆发'
    if r['is_wash']: return '洗盘(慢牛)'
    if r['is_loser']: return '真亏损'
    return '中间'


def section(title):
    print(f"\n{'='*90}\n{title}\n{'='*90}")


def summarize(sub, label):
    n = len(sub)
    if n == 0:
        return
    boom = sub['is_boom'].sum()
    wash = sub['is_wash'].sum() - boom   # 洗盘慢牛(非短期爆发)
    loser = sub['is_loser'].sum()
    mid = n - boom - wash - loser
    mfe = sub['total_mfe_from_entry'].mean()
    r15 = sub['return_15d'].mean()
    # 安全指标
    mae = sub['MAE'].mean() if 'MAE' in sub.columns else np.nan
    wr = (sub['收益率'] > 0).mean()
    pf_num = sub[sub['收益率'] > 0]['收益率'].sum()
    pf_den = -sub[sub['收益率'] < 0]['收益率'].sum()
    pf = pf_num / pf_den if pf_den > 0 else np.inf
    print(f"{label:<50} n={n:>5}  爆发{boom/n:>6.1%}  洗盘{wash/n:>6.1%}  "
          f"亏损{loser/n:>6.1%}  中间{mid/n:>6.1%}  "
          f"MFE{mfe:>+6.2%}  15d{r15:>+6.2%}  胜率{wr:>5.1%}  PF{pf:>5.2f}")


def main():
    m = load_merged()
    print(f"到期交易合并: {len(m)}")
    m['label'] = m.apply(label_row, axis=1)
    print(f"分类统计:\n{m['label'].value_counts()}")

    # ====== 1. 各评估分的特征画像 ======
    section("1. 各评估分对应的入场特征画像 (中位数)")
    feats = ['gbm_proba', 'pricing_proba', 'ma_slope', 'bias_20', 'swing', 'close_t0']
    rows = []
    for sc, sub in m.groupby('评估分'):
        row = {'score': sc, 'n': len(sub)}
        for f in feats:
            if f in sub.columns:
                row[f] = sub[f].median()
        row['trend_acc'] = (sub['v44_trend'] == 'accumulation').mean()
        row['trend_mkup'] = (sub['v44_trend'] == 'markup').mean()
        row['tier_abyss'] = (sub['v44_bias_tier'] == '深渊超跌(<-15%)').mean()
        row['tier_short'] = (sub['v44_bias_tier'] == '空头偏离(-15%~-5%)').mean()
        rows.append(row)
    df_profile = pd.DataFrame(rows).set_index('score')
    print(df_profile.to_string(float_format=lambda x: f"{x:.3f}"))

    # ====== 2. 评分 + GBM 确认 联合分层 ======
    section("2. 评分 × GBM 联合分层 (短期爆发/洗盘/真亏损 比例)")
    gbm_med = m['gbm_proba'].median()
    print(f"GBM 中位数: {gbm_med:.3f}  (用于划 low/high)")
    header = f"{'评分层':<28} {'n':>5} {'爆发':>7} {'洗盘':>7} {'亏损':>7} {'MFE':>8} {'15d':>8} {'胜率':>6} {'PF':>6}"
    print(header); print('-'*90)
    for label, mask in [
        ('85 + GBM low',       (m['评估分']==85)  & (m['gbm_proba'] < gbm_med)),
        ('85 + GBM high',      (m['评估分']==85)  & (m['gbm_proba'] >= gbm_med)),
        ('90 + GBM low',       (m['评估分']==90)  & (m['gbm_proba'] < gbm_med)),
        ('90 + GBM high',      (m['评估分']==90)  & (m['gbm_proba'] >= gbm_med)),
        ('95 + GBM low',       (m['评估分']==95)  & (m['gbm_proba'] < gbm_med)),
        ('95 + GBM high',      (m['评估分']==95)  & (m['gbm_proba'] >= gbm_med)),
        ('110 + GBM low',      (m['评估分']==110) & (m['gbm_proba'] < gbm_med)),
        ('110 + GBM high',     (m['评估分']==110) & (m['gbm_proba'] >= gbm_med)),
        ('115 (全 sample)',    (m['评估分']==115)),
    ]:
        sub = m[mask]
        if len(sub) < 3:
            continue
        summarize(sub, label)

    # ====== 3. 把"评估分=95 vs <95"拆开, 看哪些特征真正决定了评分 ======
    section("3. 评估分 <95 vs =95 vs >95 的特征差异")
    for label, mask in [
        ('<95 (85/90)',  m['评估分'] < 95),
        ('=95',          m['评估分'] == 95),
        ('>95 (110/115)', m['评估分'] > 95),
    ]:
        sub = m[mask]
        summarize(sub, label)
        print(f"    features_median: " +
              ", ".join(f"{f}={sub[f].median():+.3f}" for f in feats if f in sub.columns))
        print(f"    trend分布: " +
              ", ".join(f"{k}={v:.1%}" for k, v in sub['v44_trend'].value_counts(normalize=True).items()))
        print(f"    bias_tier分布: " +
              ", ".join(f"{k}={v:.1%}" for k, v in sub['v44_bias_tier'].value_counts(normalize=True).items()))

    # ====== 4. 评分倒推: 用特征区间重建"<95 的画像" ======
    section("4. 评分<95 的特征画像 → 倒推成条件组合")
    low = m[m['评估分'] < 95]
    hi = m[m['评估分'] >= 95]
    for f in feats:
        if f not in low.columns:
            continue
        lo_q = low[f].quantile([0.25, 0.5, 0.75])
        hi_q = hi[f].quantile([0.25, 0.5, 0.75])
        print(f"  {f:<15}  <95: Q25={lo_q.iloc[0]:+.3f} med={lo_q.iloc[1]:+.3f} Q75={lo_q.iloc[2]:+.3f}  "
              f"  >=95: Q25={hi_q.iloc[0]:+.3f} med={hi_q.iloc[1]:+.3f} Q75={hi_q.iloc[2]:+.3f}")

    # ====== 5. 候选新评分规则: 用可观测特征重建"低分高爆发"信号 ======
    section("5. 候选新评分规则 — 哪些特征组合能复刻 <95 的高爆发/低亏损特性")
    # 根据画像, 提出多个条件组合, 对比基线
    rules = [
        ('基线 (全部到期)',                pd.Series(True, index=m.index)),
        ('原评估分<95',                    m['评估分'] < 95),
        ('原评估分=95',                    m['评估分'] == 95),
        ('原评估分>95',                    m['评估分'] > 95),
        # ---- 单特征 ----
        ('swing<7%',                       m['swing'] < 0.07),
        ('swing<10%',                      m['swing'] < 0.10),
        ('|bias_20|<5%',                   m['bias_20'].abs() < 0.05),
        ('bias_20 in [-5%,0%]',            (m['bias_20'] >= -0.05) & (m['bias_20'] < 0)),
        ('gbm_proba>=0.70',                m['gbm_proba'] >= 0.70),
        ('pricing_proba<0.4',              m['pricing_proba'] < 0.4),
        ('ma_slope in [-0.04,-0.02]',      (m['ma_slope'] >= -0.04) & (m['ma_slope'] <= -0.02)),
        # ---- 多特征(模拟 confluence 子项) ----
        ('窄幅+近均线 (swing<10% & |bias|<5%)',
         (m['swing'] < 0.10) & (m['bias_20'].abs() < 0.05)),
        ('窄幅+GBM高 (swing<10% & gbm>=0.70)',
         (m['swing'] < 0.10) & (m['gbm_proba'] >= 0.70)),
        ('窄幅+低定价 (swing<10% & pricing<0.4)',
         (m['swing'] < 0.10) & (m['pricing_proba'] < 0.4)),
        ('markup + 窄幅',                  (m['v44_trend']=='markup') & (m['swing'] < 0.10)),
        ('accum + 窄幅',                   (m['v44_trend']=='accumulation') & (m['swing'] < 0.10)),
        ('accum + 超跌(bias<-10%)',        (m['v44_trend']=='accumulation') & (m['bias_20'] < -0.10)),
        ('markup + GBM>=0.70',             (m['v44_trend']=='markup') & (m['gbm_proba'] >= 0.70)),
        # ---- 组合: 复刻 "低分牛股" 画像 ----
        ('(评分<95特征) swing<8% & |bias|<3% & gbm>=0.65',
         (m['swing'] < 0.08) & (m['bias_20'].abs() < 0.03) & (m['gbm_proba'] >= 0.65)),
        ('(评分<95特征) swing<10% & bias in [-8%,0%] & pricing<0.5',
         (m['swing'] < 0.10) & (m['bias_20'] >= -0.08) & (m['bias_20'] < 0) & (m['pricing_proba'] < 0.5)),
        # ---- 严格高分(排除亏损) ----
        ('gbm>=0.70 & swing<10% & bias in [-5%,0%]',
         (m['gbm_proba'] >= 0.70) & (m['swing'] < 0.10) & (m['bias_20'] >= -0.05) & (m['bias_20'] < 0)),
        ('gbm>=0.70 & markup & swing<10%',
         (m['gbm_proba'] >= 0.70) & (m['v44_trend']=='markup') & (m['swing'] < 0.10)),
        # ---- 复刻 "<95" 高爆发/低亏损画像 ----
        ('GBM>=0.80 (复刻<95的GBM)',         m['gbm_proba'] >= 0.80),
        ('pricing>=0.70 (复刻<95的pricing)',  m['pricing_proba'] >= 0.70),
        ('GBM>=0.80 & pricing>=0.70',        (m['gbm_proba'] >= 0.80) & (m['pricing_proba'] >= 0.70)),
        ('GBM>=0.80 & swing>=10%',           (m['gbm_proba'] >= 0.80) & (m['swing'] >= 0.10)),
        ('GBM>=0.80 & bias<-3%',             (m['gbm_proba'] >= 0.80) & (m['bias_20'] < -0.03)),
        ('GBM>=0.80 & 深渊超跌',              (m['gbm_proba'] >= 0.80) & (m['v44_bias_tier']=='深渊超跌(<-15%)')),
        ('GBM>=0.80 & accum',                (m['gbm_proba'] >= 0.80) & (m['v44_trend']=='accumulation')),
        ('pricing>=0.70 & swing>=10%',       (m['pricing_proba'] >= 0.70) & (m['swing'] >= 0.10)),
        ('pricing>=0.70 & 深渊超跌',           (m['pricing_proba'] >= 0.70) & (m['v44_bias_tier']=='深渊超跌(<-15%)')),
        ('(画像复刻) GBM>=0.80 & pricing>=0.65 & bias<-3% & swing>=8%',
         (m['gbm_proba'] >= 0.80) & (m['pricing_proba'] >= 0.65) &
         (m['bias_20'] < -0.03) & (m['swing'] >= 0.08)),
        ('(画像复刻) GBM>=0.75 & pricing>=0.70 & 深渊超跌',
         (m['gbm_proba'] >= 0.75) & (m['pricing_proba'] >= 0.70) &
         (m['v44_bias_tier']=='深渊超跌(<-15%)')),
        ('(画像复刻) GBM>=0.80 & accum & 深渊超跌',
         (m['gbm_proba'] >= 0.80) & (m['v44_trend']=='accumulation') &
         (m['v44_bias_tier']=='深渊超跌(<-15%)')),
        ('(画像复刻宽松) GBM>=0.75 & pricing>=0.65 & bias<-3%',
         (m['gbm_proba'] >= 0.75) & (m['pricing_proba'] >= 0.65) & (m['bias_20'] < -0.03)),
    ]
    print(f"{'规则':<70} {'n':>5} {'爆发':>7} {'洗盘':>7} {'亏损':>7} {'MFE':>8} {'15d':>8} {'胜率':>6} {'PF':>6}")
    print('-'*130)
    for name, mask in rules:
        sub = m[mask]
        if len(sub) < 5:
            print(f"{name:<55} {len(sub):>5}   (样本过少)")
            continue
        summarize(sub, name)

    # ====== 6. 最终推荐: 按 "收益 x 安全" 排序 ======
    section("6. 候选规则按 [收益*安全] 排序 (综合评分 = 15d收益 * 胜率 * PF)")
    ranking = []
    for name, mask in rules[1:]:   # 跳过基线
        sub = m[mask]
        if len(sub) < 10:
            continue
        r15 = sub['return_15d'].mean()
        wr = (sub['收益率'] > 0).mean()
        pf_num = sub[sub['收益率'] > 0]['收益率'].sum()
        pf_den = -sub[sub['收益率'] < 0]['收益率'].sum()
        pf = pf_num / pf_den if pf_den > 0 else 0
        loser_rate = sub['is_loser'].mean()
        boom_rate = sub['is_boom'].mean()
        wash_rate = sub['is_wash'].mean() - boom_rate
        # 综合得分: 偏向安全(PF, 胜率) + 收益(r15) + 爆发率
        score = (r15 * 100) * wr * min(pf, 3) * (1 + boom_rate)
        ranking.append((name, len(sub), boom_rate, wash_rate, loser_rate,
                        r15, wr, pf, score))
    ranking.sort(key=lambda x: -x[-1])
    print(f"{'排名':>4} {'规则':<70} {'n':>5} {'爆发':>6} {'洗盘':>6} {'亏损':>6} "
          f"{'15d':>7} {'胜率':>6} {'PF':>5} {'综合':>7}")
    print('-'*145)
    for i, r in enumerate(ranking[:20], 1):
        print(f"{i:>4} {r[0]:<70} {r[1]:>5} {r[2]:>5.1%} {r[3]:>5.1%} {r[4]:>5.1%} "
              f"{r[5]:>+6.2%} {r[6]:>5.1%} {r[7]:>5.2f} {r[8]:>7.2f}")


if __name__ == '__main__':
    main()
