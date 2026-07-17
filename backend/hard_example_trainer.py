"""
P1-1: 难例加权训练
在训练集中识别"截面相似但标签差异大"的样本对，赋予更高权重，
迫使模型在这些难分边界上投入更多梯度。
"""

import pandas as pd
import numpy as np
import os
import sys
import pickle
import warnings
warnings.filterwarnings('ignore')

import lightgbm as lgb
from sklearn.preprocessing import StandardScaler

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


CROSS_FEATS = [
    'bias_ma20', 'bias_ma60', 'vol_breakout_ratio', 'price_position_120d',
    'atr_percentile', 'boll_width', 'stock_return_20d', 'rs_20d',
]


def compute_hard_example_weights(df, cross_feats, dist_threshold=0.5, label_diff_threshold=15):
    """
    对每个交易日组内，找截面距离近但标签差异大的难例对，
    赋予更高的样本权重。

    返回: 与 df 等长的权重数组
    """
    available_cross = [f for f in cross_feats if f in df.columns]
    X_cross = df[available_cross].fillna(0).values

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_cross)

    weights = np.ones(len(df), dtype=float)

    groups = df.groupby('t0_date')
    hard_pair_count = 0

    for t0_date, group in groups:
        if len(group) < 5:
            continue

        idx = group.index.values
        X_g = X_scaled[idx]
        y_g = df.loc[idx, '_relevance'].values

        # 高效计算: 随机抽样而非全量两两比较
        n = len(idx)
        if n > 100:
            sample_size = min(100, n)
            sample_idx = np.random.choice(n, sample_size, replace=False)
        else:
            sample_idx = np.arange(n)

        for si in sample_idx:
            dists = np.sqrt(np.sum((X_g - X_g[si]) ** 2, axis=1))
            label_diffs = np.abs(y_g - y_g[si])

            hard_mask = (dists < dist_threshold) & (label_diffs >= label_diff_threshold)
            hard_mask[si] = False

            n_hard = hard_mask.sum()
            if n_hard > 0:
                boost = 1.0 + n_hard * 0.5
                global_idx = idx[hard_mask].tolist() + [idx[si]]
                for gi in global_idx:
                    pos = df.index.get_loc(gi)
                    weights[pos] = max(weights[pos], boost)
                hard_pair_count += n_hard

    print(f"  难例对总数: {hard_pair_count:,}")
    print(f"  加权样本占比: {(weights > 1).sum()}/{len(weights)} ({(weights > 1).mean():.1%})")
    print(f"  平均权重: {weights.mean():.3f}, 最大权重: {weights.max():.3f}")
    return weights


def train_hard_example_model():
    """训练难例加权模型"""
    data_path = _proj('data', 'result', 'super_trend', 'super_trend_training_data_v2.csv')
    df = pd.read_csv(data_path)
    df = df.sort_values('t0_date').reset_index(drop=True)

    drop_cols = [
        'target', 'label', 'stock_code', 't0_date', 'is_positive',
        'future_mfe', 'index_return_22d', 'excess_return', 'excess_rank',
        'final_rank_score', 'path_sharpe', 'path_up_capture',
        'path_smoothness', 'path_return_22d', '_relevance', '_group',
    ]

    feature_columns = [
        c for c in df.columns
        if c not in drop_cols and df[c].dtype in ('float64', 'float32', 'int64', 'int32')
    ]
    print(f"特征数: {len(feature_columns)}")

    scores = df['final_rank_score'].fillna(0).values
    s = scores.copy()
    valid = ~np.isnan(s)
    grades = np.zeros(len(s), dtype=int)
    s_valid = s[valid]
    s_min, s_max = s_valid.min(), s_valid.max()
    if s_max > s_min:
        grades[valid] = np.clip(
            ((s_valid - s_min) / (s_max - s_min) * 31).astype(int), 0, 31)

    df['_relevance'] = grades
    df['_group'] = df.groupby('t0_date').ngroup()
    group_sizes = df.groupby('_group').size()
    valid_groups = group_sizes[group_sizes >= 3].index
    df = df[df['_group'].isin(valid_groups)].copy()
    df['_group'] = df.groupby('t0_date').ngroup()

    print(f"\n计算难例权重...")
    df = df.reset_index(drop=True)
    weights = compute_hard_example_weights(df, CROSS_FEATS)

    split_idx = int(len(df) * 0.8)
    split_date = df.iloc[split_idx]['t0_date']
    df_train = df[df['t0_date'] < split_date]
    df_test = df[df['t0_date'] >= split_date]

    X_tr = df_train[feature_columns].fillna(0)
    y_tr = df_train['_relevance'].values
    g_tr = df_train.groupby('t0_date').size().values
    w_tr = weights[:len(df_train)]

    X_te = df_test[feature_columns].fillna(0)
    y_te = df_test['_relevance'].values
    g_te = df_test.groupby('t0_date').size().values

    max_train_grade = y_tr.max()
    y_te = np.clip(y_te, 0, max_train_grade)

    train_data = lgb.Dataset(X_tr, label=y_tr, group=g_tr, weight=w_tr)
    val_data = lgb.Dataset(X_te, label=y_te, group=g_te, reference=train_data)

    print(f"\n训练难例加权模型...")
    model = lgb.train(
        {
            'objective': 'lambdarank',
            'metric': 'ndcg',
            'learning_rate': 0.05,
            'num_leaves': 63,
            'max_depth': -1,
            'min_child_samples': 20,
            'subsample': 0.8,
            'colsample_bytree': 0.4,
            'reg_alpha': 0.1,
            'reg_lambda': 1.0,
            'verbose': -1,
        },
        train_data,
        valid_sets=[val_data],
        num_boost_round=500,
        callbacks=[
            lgb.early_stopping(stopping_rounds=50),
            lgb.log_evaluation(period=50),
        ],
    )
    print(f"训练完成: {model.num_trees()} 棵树")

    # 对比特征重要性
    importance = pd.DataFrame({
        'feature': feature_columns,
        'importance': model.feature_importance(importance_type='gain'),
    }).sort_values('importance', ascending=False)

    print(f"\n── 难例加权模型特征重要性 Top 15 ──")
    for _, row in importance.head(15).iterrows():
        print(f"  {row['feature']}: {row['importance']:.0f}")

    boll_imp = importance[importance['feature'] == 'boll_width']['importance'].values
    boll_imp = boll_imp[0] if len(boll_imp) > 0 else 0
    print(f"\n  boll_width 重要性: {boll_imp:.0f} (原始: 27140)")
    print(f"  boll_width 下降: {(1 - boll_imp/27140)*100:.1f}%")

    v2_feats = [f for f in importance['feature'] if any(
        x in f for x in ['ma_dispersion', 'ma_glue', 'ma_divergence', 'ma_convergence',
                         'washout', 'lower_shadow', 'vol_trend', 'vol_shrink_streak',
                         'vol_low_point', 'streak_max', 'bull_ratio', 'last_3_pattern',
                         'rs_rank'])]
    v2_in_top10 = importance.head(10)['feature'].isin(v2_feats).sum()
    v2_total_imp = importance[importance['feature'].isin(v2_feats)]['importance'].sum()
    total_imp = importance['importance'].sum()
    print(f"  V2 特征在 Top 10: {v2_in_top10}")
    print(f"  V2 特征重要性占比: {v2_total_imp/total_imp*100:.1f}%")

    # 保存
    model_path = _proj('data', 'result', 'super_trend', 'models', 'trend_ranker_v1_hard.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump({
            'model': model,
            'feature_columns': feature_columns,
            'model_type': 'hard_ranker',
        }, f)
    print(f"\n模型已保存: {model_path}")

    return model, feature_columns


if __name__ == "__main__":
    print("=== P1-1: 难例加权训练 ===")
    model, features = train_hard_example_model()
