"""
孪生案例验收测试
验收标准: 截面特征相似但结局迥异的股票对，模型能否正确排序

方法:
  1. 从真实数据中自动搜索孪生对（截面特征欧氏距离最近 + MFE 差异最大）
  2. 对每对孪生股，用模型打分并比较排名
  3. 验收: 真主升(A)得分 >> 假突破(B)得分
"""

import pandas as pd
import numpy as np
import pickle
import os
import sys
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import pairwise_distances

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


CROSS_SECTIONAL_FEATURES = [
    'bias_ma20', 'bias_ma60', 'vol_breakout_ratio', 'price_position_120d',
    'atr_percentile', 'boll_width', 'stock_return_20d', 'rs_20d',
    'vol_turnover_ratio', 'volume_percentile_120d',
]

V2_FEATURES = [
    'ma_dispersion_5d', 'ma_dispersion_20d', 'ma_glue_max_days',
    'ma_glue_recency', 'ma_divergence_speed', 'ma_convergence_flag',
    'washout_ma60_flag', 'washout_ma60_depth', 'washout_ma60_recovery_days',
    'washout_ma20_flag', 'washout_ma20_depth', 'washout_ma20_recovery_days',
    'lower_shadow_count', 'vol_trend_10d', 'vol_shrink_streak',
    'vol_low_point_position', 'streak_max_bull', 'streak_max_bear',
    'bull_ratio_10d', 'last_3_pattern',
    'rs_rank_mean_5d', 'rs_rank_mean_10d', 'rs_rank_std_10d',
    'rs_rank_mean_20d', 'rs_rank_trend_20d',
]


def load_model_and_data():
    """加载模型和训练数据"""
    model_path = _proj('data', 'result', 'super_trend', 'models', 'trend_ranker_v1.pkl')
    data_path = _proj('data', 'result', 'super_trend', 'super_trend_training_data_v2.csv')

    with open(model_path, 'rb') as f:
        model_data = pickle.load(f)
    model = model_data['model']
    feature_columns = model_data['feature_columns']

    df = pd.read_csv(data_path)
    df = df.sort_values('t0_date').reset_index(drop=True)

    available_features = [c for c in feature_columns if c in df.columns]
    X = df[available_features].fillna(0)
    scores = model.predict(X)
    df['_score'] = scores

    return df, model, feature_columns


def find_twin_pairs(df, n_pairs=5, mfe_threshold_high=0.5, mfe_threshold_low=0.10):
    """
    自动搜索孪生对:
      - 截面特征距离最近（标准化后欧氏距离）
      - MFE 差异最大（A >> B）
    """
    df = df.reset_index(drop=True)

    cross_feats = [f for f in CROSS_SECTIONAL_FEATURES if f in df.columns]
    if not cross_feats:
        print("截面特征缺失，无法搜索孪生对")
        return []

    scaler = StandardScaler()
    X_cross = scaler.fit_transform(df[cross_feats].fillna(0))

    stock_a_mask = df['future_mfe'] >= mfe_threshold_high
    stock_b_mask = df['future_mfe'] <= mfe_threshold_low

    candidates_a = df[stock_a_mask].index.tolist()
    candidates_b = df[stock_b_mask].index.tolist()

    print(f"候选 A (MFE≥{mfe_threshold_high}): {len(candidates_a)} 个")
    print(f"候选 B (MFE≤{mfe_threshold_low}): {len(candidates_b)} 个")

    if len(candidates_a) == 0 or len(candidates_b) == 0:
        print("候选不足，放宽阈值重试...")
        return find_twin_pairs(df, n_pairs=n_pairs,
                              mfe_threshold_high=0.30, mfe_threshold_low=0.15)

    pairs = []
    used_a = set()

    sample_a = candidates_a[:min(500, len(candidates_a))]
    sample_b = candidates_b[:min(2000, len(candidates_b))]

    dist_matrix = pairwise_distances(X_cross[sample_a], X_cross[sample_b])

    flat_indices = np.argsort(dist_matrix, axis=None)

    for flat_idx in flat_indices:
        if len(pairs) >= n_pairs:
            break

        i = flat_idx // len(sample_b)
        j = flat_idx % len(sample_b)

        idx_a = sample_a[i]
        idx_b = sample_b[j]

        if idx_a in used_a:
            continue

        row_a = df.iloc[idx_a]
        row_b = df.iloc[idx_b]

        if row_a['stock_code'] == row_b['stock_code']:
            continue

        dist = dist_matrix[i, j]

        pairs.append({
            'idx_a': idx_a, 'idx_b': idx_b,
            'stock_a': row_a['stock_code'], 'stock_b': row_b['stock_code'],
            'date_a': row_a['t0_date'], 'date_b': row_b['t0_date'],
            'mfe_a': row_a['future_mfe'], 'mfe_b': row_b['future_mfe'],
            'excess_rank_a': row_a.get('excess_rank', 0),
            'excess_rank_b': row_b.get('excess_rank', 0),
            'score_a': row_a['_score'], 'score_b': row_b['_score'],
            'label_a': row_a.get('label', -1), 'label_b': row_b.get('label', -1),
            'cross_distance': dist,
            'cross_a': {f: row_a[f] for f in cross_feats},
            'cross_b': {f: row_b[f] for f in cross_feats},
            'v2_a': {f: row_a.get(f, np.nan) for f in V2_FEATURES if f in df.columns},
            'v2_b': {f: row_b.get(f, np.nan) for f in V2_FEATURES if f in df.columns},
        })
        used_a.add(idx_a)

    return pairs


def compute_intraday_rank(df, stock_code, t0_date, score_col='_score'):
    """计算某只股票在其异动日当天的排名百分位"""
    day_df = df[df['t0_date'] == t0_date].copy()
    if len(day_df) == 0:
        return None, None, None

    day_df = day_df.sort_values(score_col, ascending=False).reset_index(drop=True)
    day_df['_rank'] = range(1, len(day_df) + 1)
    day_df['_rank_pct'] = 1 - (day_df['_rank'] - 1) / (len(day_df) - 1) if len(day_df) > 1 else 0.5

    target = day_df[day_df['stock_code'] == stock_code]
    if len(target) == 0:
        return None, None, None

    rank = target.iloc[0]['_rank']
    rank_pct = target.iloc[0]['_rank_pct']
    total = len(day_df)
    return rank, rank_pct, total


def print_twin_report(pairs, df):
    """打印孪生案例验收报告"""
    print(f"\n{'='*80}")
    print(f"  孪生案例验收报告")
    print(f"{'='*80}")

    pass_count = 0

    for i, p in enumerate(pairs):
        rank_a, pct_a, total_a = compute_intraday_rank(df, p['stock_a'], p['date_a'])
        rank_b, pct_b, total_b = compute_intraday_rank(df, p['stock_b'], p['date_b'])

        verdict_a = "PASS" if pct_a is not None and pct_a >= 0.70 else "FAIL"
        verdict_b = "PASS" if pct_b is not None and pct_b <= 0.70 else "FAIL"
        pair_pass = verdict_a == "PASS" and verdict_b == "PASS"
        if pair_pass:
            pass_count += 1

        print(f"\n{'─'*80}")
        print(f"  孪生对 #{i+1}  (截面距离: {p['cross_distance']:.3f})")
        print(f"{'─'*80}")

        print(f"\n  {'维度':<25} {'股票A (真主升)':<25} {'股票B (假突破)':<25}")
        print(f"  {'─'*75}")
        print(f"  {'代码':<25} {p['stock_a']:<25} {p['stock_b']:<25}")
        print(f"  {'T0日期':<25} {str(p['date_a'])[:10]:<25} {str(p['date_b'])[:10]:<25}")
        print(f"  {'MFE (真实结局)':<25} {p['mfe_a']:.1%}{'':>15} {p['mfe_b']:.1%}{'':>15}")
        print(f"  {'旧标签':<25} {int(p['label_a']):<25} {int(p['label_b']):<25}")
        print(f"  {'超额收益排名':<25} {p['excess_rank_a']:.2f}{'':>17} {p['excess_rank_b']:.2f}{'':>17}")

        cross_feats = [f for f in CROSS_SECTIONAL_FEATURES if f in p['cross_a']]
        for f in cross_feats:
            va = p['cross_a'][f]
            vb = p['cross_b'][f]
            print(f"  {f:<25} {va:<25.4f} {vb:<25.4f}")

        print(f"\n  {'── 模型输出 ──'}")
        print(f"  {'预测得分':<25} {p['score_a']:<25.4f} {p['score_b']:<25.4f}")
        if rank_a is not None:
            print(f"  {'当日排名':<25} {rank_a}/{total_a}{'':>13} {rank_b}/{total_b}{'':>13}")
            print(f"  {'排名百分位':<25} {pct_a:.1%}{'':>17} {pct_b:.1%}{'':>17}")
            print(f"  {'A 排入前30%':<25} {'✅ ' + verdict_a:<25}")
            print(f"  {'B 排出前30%':<25} {'':>25} {'✅ ' + verdict_b}")
        else:
            print(f"  {'当日排名':<25} {'N/A (非同一交易日)':<25}")

        key_v2 = ['rs_rank_mean_20d', 'ma_dispersion_5d', 'ma_glue_max_days',
                   'washout_ma60_flag', 'vol_shrink_streak', 'bull_ratio_10d']
        print(f"\n  {'── V2 特征差异（区分关键）──'}")
        for f in key_v2:
            if f in p['v2_a']:
                va = p['v2_a'][f]
                vb = p['v2_b'][f]
                diff = abs(va - vb) if not (pd.isna(va) or pd.isna(vb)) else 0
                marker = " ◀ 区分!" if diff > 0.1 else ""
                print(f"  {f:<25} {va:<25.4f} {vb:<25.4f}{marker}")

        print(f"\n  验收: {'✅ PASS' if pair_pass else '❌ FAIL'}")

    print(f"\n{'='*80}")
    print(f"  总体验收: {pass_count}/{len(pairs)} 对通过")
    print(f"  验收标准: A 排入当日前 30%, B 排出前 30%")
    print(f"{'='*80}")
    return pass_count, len(pairs)


def systematic_analysis(df):
    """系统性分析: 全量数据中，模型对高MFE vs 低MFE的排序能力"""
    print(f"\n{'='*80}")
    print(f"  系统性排序能力分析")
    print(f"{'='*80}")

    test_dates = sorted(df['t0_date'].unique())
    split_idx = int(len(test_dates) * 0.8)
    test_date_set = set(test_dates[split_idx:])
    test_df = df[df['t0_date'].isin(test_date_set)].copy()

    high_mfe = test_df[test_df['future_mfe'] >= 0.5]
    low_mfe = test_df[test_df['future_mfe'] <= 0.10]

    print(f"\n  测试集: {len(test_df)} 样本, {len(test_date_set)} 天")
    print(f"  高MFE (≥50%): {len(high_mfe)} 个, 平均得分: {high_mfe['_score'].mean():.4f}")
    print(f"  低MFE (≤10%): {len(low_mfe)} 个, 平均得分: {low_mfe['_score'].mean():.4f}")

    score_diff = high_mfe['_score'].mean() - low_mfe['_score'].mean()
    print(f"  得分差异: {score_diff:.4f} ({'显著' if abs(score_diff) > 0.01 else '不显著'})")

    a_wins = 0
    b_wins = 0
    total_comparisons = 0

    for date in test_date_set:
        day = test_df[test_df['t0_date'] == date]
        if len(day) < 20:
            continue

        day_high = day[day['future_mfe'] >= 0.5]
        day_low = day[day['future_mfe'] <= 0.10]

        for _, ha in day_high.iterrows():
            for _, lb in day_low.iterrows():
                total_comparisons += 1
                if ha['_score'] > lb['_score']:
                    a_wins += 1
                else:
                    b_wins += 1

    if total_comparisons > 0:
        win_rate = a_wins / total_comparisons
        print(f"\n  逐对比较 (同日内高MFE vs 低MFE):")
        print(f"    总比较次数: {total_comparisons:,}")
        print(f"    高MFE胜出: {a_wins:,} ({win_rate:.1%})")
        print(f"    低MFE胜出: {b_wins:,} ({1-win_rate:.1%})")
    else:
        print(f"\n  同日高/低MFE对不足，跳过逐对比较")

    quantiles = [0.1, 0.25, 0.5, 0.75, 0.9]
    print(f"\n  各 MFE 区间的模型得分分布:")
    print(f"  {'MFE 区间':<20} {'样本数':<10} {'平均得分':<12} {'P25得分':<12} {'P75得分':<12}")
    bins = [(0, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.50), (0.50, 1.0), (1.0, 10.0)]
    for lo, hi in bins:
        subset = test_df[(test_df['future_mfe'] >= lo) & (test_df['future_mfe'] < hi)]
        if len(subset) > 0:
            print(f"  [{lo:.0%}, {hi:.0%}){'':>8} {len(subset):<10} {subset['_score'].mean():<12.4f} "
                  f"{subset['_score'].quantile(0.25):<12.4f} {subset['_score'].quantile(0.75):<12.4f}")


def main():
    print("=== 孪生案例验收测试 ===\n")

    df, model, feature_columns = load_model_and_data()
    print(f"数据: {len(df)} 样本, {df['stock_code'].nunique()} 只股票")
    print(f"模型: {model.num_trees()} 棵树, {len(feature_columns)} 特征")

    pairs = find_twin_pairs(df, n_pairs=5)

    if pairs:
        print_twin_report(pairs, df)
    else:
        print("未找到孪生对")

    systematic_analysis(df)


if __name__ == "__main__":
    main()
