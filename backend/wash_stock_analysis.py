"""
洗盘票特征分析 — 在筛选阶段能否区分"洗盘待爆发" vs "真亏损"
基于 expired_15d_analysis.csv (2636笔到期交易的15日后续表现)
"""
import os, sys, pandas as pd, numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CSV_MAIN = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_27m.csv'
CSV_15D = '/home/hypnosis/data/quant_base/data/result/expired_15d_analysis.csv'


def main():
    df_main = pd.read_csv(CSV_MAIN)
    df_15d = pd.read_csv(CSV_15D)

    # Merge: 将15日后续表现 join 到主表
    expired = df_main[df_main['交易状态'].isin(['持仓到期', '时间衰减平仓'])].copy()
    df_15d['_key'] = df_15d['stock_code'] + '_' + df_15d['回测日期']
    expired['_key'] = expired['stock_code'] + '_' + expired['回测日期']
    merged = expired.merge(df_15d[['_key', 'mfe_15d', 'mae_15d', 'return_15d',
                                    'would_tp10', 'would_sl10',
                                    'total_mfe_from_entry', 'tp_hit_day']],
                           on='_key', how='inner')
    print(f"到期交易: {len(expired)}, 合并成功: {len(merged)}")

    # 定义: "洗盘票" = 后续MFE > 10% (有爆发潜力)
    #       "真亏损" = 后续MFE < 5% 且 return_15d < 0 (确实不行)
    merged['is_wash'] = merged['total_mfe_from_entry'] > 0.10
    merged['is_loser'] = (merged['mfe_15d'] < 0.05) & (merged['return_15d'] < 0)

    wash_count = merged['is_wash'].sum()
    loser_count = merged['is_loser'].sum()
    other_count = len(merged) - wash_count - loser_count

    print(f"\n{'='*80}")
    print("到期交易分类")
    print(f"{'='*80}")
    print(f"  洗盘票 (入场后总MFE>10%): {wash_count} ({wash_count/len(merged):.1%})")
    print(f"  真亏损 (后续MFE<5%且下跌): {loser_count} ({loser_count/len(merged):.1%})")
    print(f"  中间地带: {other_count} ({other_count/len(merged):.1%})")
    print(f"  洗盘票均收益: {merged[merged['is_wash']]['return_15d'].mean():+.2%}")
    print(f"  真亏损均收益: {merged[merged['is_loser']]['return_15d'].mean():+.2%}")

    # === 逐特征分析: 哪些筛选时特征能区分 ===
    features = ['v44_trend', 'v44_bias_tier', 'gbm_proba', 'pricing_proba',
                'ma_slope', 'bias_20', 'swing', 'close_t0', '评估分']

    print(f"\n{'='*80}")
    print("特征区分能力分析")
    print(f"{'='*80}")

    # 1. v44_trend
    print(f"\n--- v44_trend ---")
    for trend in merged['v44_trend'].unique():
        sub = merged[merged['v44_trend'] == trend]
        if len(sub) < 5:
            continue
        wash_r = sub['is_wash'].mean()
        loser_r = sub['is_loser'].mean()
        avg_mfe = sub['total_mfe_from_entry'].mean()
        print(f"  {trend}: {len(sub)}笔, 洗盘率{wash_r:.1%}, 亏损率{loser_r:.1%}, 总MFE={avg_mfe:+.2%}")

    # 2. v44_bias_tier
    print(f"\n--- v44_bias_tier ---")
    for tier in merged['v44_bias_tier'].unique():
        sub = merged[merged['v44_bias_tier'] == tier]
        if len(sub) < 5:
            continue
        wash_r = sub['is_wash'].mean()
        loser_r = sub['is_loser'].mean()
        avg_mfe = sub['total_mfe_from_entry'].mean()
        print(f"  {tier}: {len(sub)}笔, 洗盘率{wash_r:.1%}, 亏损率{loser_r:.1%}, 总MFE={avg_mfe:+.2%}")

    # 3. 连续特征分箱
    for feat in ['gbm_proba', 'pricing_proba', 'ma_slope', 'bias_20', 'swing', '评估分']:
        if feat not in merged.columns:
            continue
        print(f"\n--- {feat} ---")
        vals = merged[feat].dropna()
        if len(vals) == 0:
            continue
        q25, q50, q75 = vals.quantile([0.25, 0.5, 0.75])
        bins = [(-np.inf, q25), (q25, q50), (q50, q75), (q75, np.inf)]
        labels = [f'<Q25({q25:.3f})', f'Q25-Q50', f'Q50-Q75', f'>Q75({q75:.3f})']
        for (lo, hi), label in zip(bins, labels):
            sub = merged[(merged[feat] >= lo) & (merged[feat] < hi)]
            if len(sub) < 10:
                continue
            wash_r = sub['is_wash'].mean()
            loser_r = sub['is_loser'].mean()
            avg_mfe = sub['total_mfe_from_entry'].mean()
            avg_ret = merged.loc[sub.index, 'return_15d'].mean()
            print(f"  {label}: {len(sub)}笔, 洗盘率{wash_r:.1%}, 亏损率{loser_r:.1%}, "
                  f"总MFE={avg_mfe:+.2%}, 15日收益={avg_ret:+.2%}")

    # === 组合条件测试: 能否在筛选时识别洗盘票 ===
    print(f"\n{'='*80}")
    print("组合条件过滤测试")
    print(f"{'='*80}")
    print(f"目标: 在筛选时剔除'真亏损', 保留'洗盘票'")
    print(f"{'方案':<35} {'保留':>6} {'洗盘':>6} {'亏损':>6} "
          f"{'洗盘率':>7} {'亏损率':>7} {'总MFE':>8} {'15日收益':>8}")
    print('-' * 95)

    # 基线
    n = len(merged)
    print(f"{'无过滤(基线)':<35} {n:>6} {wash_count:>6} {loser_count:>6} "
          f"{wash_count/n:>6.1%} {loser_count/n:>6.1%} "
          f"{merged['total_mfe_from_entry'].mean():>+7.2%} {merged['return_15d'].mean():>+7.2%}")

    # 条件组合测试
    conditions = [
        ('v44_trend==accumulation', merged['v44_trend'] == 'accumulation'),
        ('v44_trend==markup', merged['v44_trend'] == 'markup'),
        ('gbm_proba>=0.65', merged['gbm_proba'] >= 0.65),
        ('gbm_proba>=0.70', merged['gbm_proba'] >= 0.70),
        ('ma_slope>=0 (上升)', merged['ma_slope'] >= 0),
        ('ma_slope<0 (下降)', merged['ma_slope'] < 0),
        ('bias_20<-5% (超跌)', merged['bias_20'] < -0.05),
        ('bias_20 in [-5%,0%]', (merged['bias_20'] >= -0.05) & (merged['bias_20'] < 0)),
        ('bias_20>=0 (偏高)', merged['bias_20'] >= 0),
        ('swing<5% (窄幅)', merged['swing'] < 0.05),
        ('swing 5-10%', (merged['swing'] >= 0.05) & (merged['swing'] < 0.10)),
        ('swing>=10% (宽幅)', merged['swing'] >= 0.10),
        ('pricing_proba<0.4', merged['pricing_proba'] < 0.4),
        ('pricing_proba>=0.5', merged['pricing_proba'] >= 0.5),
    ]

    for name, cond in conditions:
        sub = merged[cond]
        if len(sub) < 10:
            continue
        w = sub['is_wash'].sum()
        l = sub['is_loser'].sum()
        print(f"{name:<35} {len(sub):>6} {w:>6} {l:>6} "
              f"{w/len(sub):>6.1%} {l/len(sub):>6.1%} "
              f"{sub['total_mfe_from_entry'].mean():>+7.2%} {sub['return_15d'].mean():>+7.2%}")

    # 组合条件
    combos = [
        ('accum+gbm>=0.65+ma>=0',
         (merged['v44_trend'] == 'accumulation') & (merged['gbm_proba'] >= 0.65) & (merged['ma_slope'] >= 0)),
        ('accum+bias<-5%',
         (merged['v44_trend'] == 'accumulation') & (merged['bias_20'] < -0.05)),
        ('markup+gbm>=0.65',
         (merged['v44_trend'] == 'markup') & (merged['gbm_proba'] >= 0.65)),
        ('markup+swing<10%',
         (merged['v44_trend'] == 'markup') & (merged['swing'] < 0.10)),
        ('gbm>=0.65+bias<-5%',
         (merged['gbm_proba'] >= 0.65) & (merged['bias_20'] < -0.05)),
        ('gbm>=0.70+ma>=0',
         (merged['gbm_proba'] >= 0.70) & (merged['ma_slope'] >= 0)),
        ('swing<5%+bias<-5%',
         (merged['swing'] < 0.05) & (merged['bias_20'] < -0.05)),
        ('accum+swing<5%',
         (merged['v44_trend'] == 'accumulation') & (merged['swing'] < 0.05)),
        ('markup+accum排除dist',
         merged['v44_trend'].isin(['accumulation', 'markup'])),
    ]

    print(f"\n{'组合条件':<35}")
    print('-' * 95)
    for name, cond in combos:
        sub = merged[cond]
        if len(sub) < 10:
            continue
        w = sub['is_wash'].sum()
        l = sub['is_loser'].sum()
        print(f"{name:<35} {len(sub):>6} {w:>6} {l:>6} "
              f"{w/len(sub):>6.1%} {l/len(sub):>6.1%} "
              f"{sub['total_mfe_from_entry'].mean():>+7.2%} {sub['return_15d'].mean():>+7.2%}")

    # === 反向测试: 哪些条件的"亏损率"特别高 (应该剔除) ===
    print(f"\n{'='*80}")
    print("高风险特征 (亏损率>40%, 建议筛选时剔除)")
    print(f"{'='*80}")
    risk_conditions = [
        ('distribution', merged['v44_trend'] == 'distribution'),
        ('bias_20>=5%', merged['bias_20'] >= 0.05),
        ('swing>=15%', merged['swing'] >= 0.15),
        ('gbm_proba<0.50', merged['gbm_proba'] < 0.50),
        ('ma_slope<-0.05', merged['ma_slope'] < -0.05),
        ('评估分<80', merged['评估分'] < 80),
        ('dist+bias>=0',
         (merged['v44_trend'] == 'distribution') & (merged['bias_20'] >= 0)),
        ('bias>=5%+swing>=10%',
         (merged['bias_20'] >= 0.05) & (merged['swing'] >= 0.10)),
        ('gbm<0.5+ma<-0.05',
         (merged['gbm_proba'] < 0.50) & (merged['ma_slope'] < -0.05)),
    ]

    print(f"{'条件':<35} {'笔数':>6} {'亏损':>6} {'亏损率':>7} {'洗盘':>6} {'洗盘率':>7} {'总MFE':>8}")
    print('-' * 85)
    for name, cond in risk_conditions:
        sub = merged[cond]
        if len(sub) < 3:
            continue
        w = sub['is_wash'].sum()
        l = sub['is_loser'].sum()
        print(f"{name:<35} {len(sub):>6} {l:>6} {l/len(sub):>6.1%} {w:>6} {w/len(sub):>6.1%} "
              f"{sub['total_mfe_from_entry'].mean():>+7.2%}")


if __name__ == '__main__':
    main()
