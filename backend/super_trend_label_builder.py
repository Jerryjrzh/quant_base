"""
Super Trend V1: 标签重构模块
1. 超额收益排序标签（替代绝对 MFE 阈值）
2. 路径稳定性惩罚（惩罚脉冲式冲高回落）
3. 后处理流水线：扫描完成后统一计算排名
"""

import pandas as pd
import numpy as np
import os
import sys
from scipy.stats import linregress
import warnings
warnings.filterwarnings('ignore')

EVAL_DAYS = 22


def load_index_daily(index_code='sh000001', end_date=None):
    """加载大盘指数日线 close 序列，返回 pd.Series (index=DatetimeIndex)"""
    from data_handler import get_full_data_with_indicators
    df = get_full_data_with_indicators(index_code, end_date=end_date)
    if df is None or df.empty:
        raise ValueError(f"无法加载指数数据: {index_code}")
    return df['close']


def compute_index_return_22d(index_close, t0_date):
    """
    计算 T0 日起 22 个交易日的大盘累计收益率。
    返回 (index_return, valid) 元组。
    """
    if t0_date not in index_close.index:
        pos = index_close.index.searchsorted(t0_date)
        if pos >= len(index_close):
            return np.nan, False
        t0_date = index_close.index[pos]

    t0_pos = index_close.index.get_loc(t0_date)
    end_pos = min(t0_pos + EVAL_DAYS, len(index_close) - 1)
    if end_pos <= t0_pos:
        return np.nan, False

    t0_close = index_close.iloc[t0_pos]
    end_close = index_close.iloc[end_pos]
    if t0_close < 0.01:
        return np.nan, False
    return (end_close / t0_close) - 1.0, True


def compute_path_stability(daily_closes, t0_close):
    """
    从 T0+1 到 T0+22 的每日收盘价序列，计算路径稳定性指标。

    参数:
        daily_closes: list/array of T0后每日收盘价 (最多22个)
        t0_close: T0 当日收盘价

    返回:
        dict: path_sharpe, path_up_capture, path_smoothness, path_return_22d
    """
    if len(daily_closes) < 5 or t0_close < 0.01:
        return {
            'path_sharpe': np.nan,
            'path_up_capture': np.nan,
            'path_smoothness': np.nan,
            'path_return_22d': np.nan,
        }

    returns = np.array([(c / t0_close) - 1.0 for c in daily_closes])

    daily_changes = np.diff(returns)
    if len(daily_changes) < 2:
        return {
            'path_sharpe': np.nan,
            'path_up_capture': np.nan,
            'path_smoothness': np.nan,
            'path_return_22d': returns[-1] if len(returns) > 0 else np.nan,
        }

    mean_ret = np.mean(daily_changes)
    std_ret = np.std(daily_changes)
    if std_ret < 1e-8:
        path_sharpe = 10.0 if mean_ret > 0 else (-10.0 if mean_ret < 0 else 0.0)
    else:
        path_sharpe = mean_ret / std_ret

    up_days = np.sum(daily_changes > 0)
    path_up_capture = up_days / len(daily_changes)

    cv = std_ret / abs(mean_ret) if abs(mean_ret) > 0.001 else 10.0
    path_smoothness = max(0.0, 1.0 - cv)

    path_return_22d = returns[-1]

    return {
        'path_sharpe': float(path_sharpe),
        'path_up_capture': float(path_up_capture),
        'path_smoothness': float(path_smoothness),
        'path_return_22d': float(path_return_22d),
    }


def compute_path_stability_from_df(df, t0_idx, eval_days=22):
    """
    从日线 DataFrame 计算路径稳定性（供扫描器内调用）。

    参数:
        df: 个股完整日线 DataFrame (含 close 列)
        t0_idx: T0 在 df 中的位置
        eval_days: 评估窗口天数

    返回:
        dict: path_sharpe, path_up_capture, path_smoothness, path_return_22d
    """
    end_idx = min(t0_idx + eval_days, len(df) - 1)
    if end_idx <= t0_idx:
        return {
            'path_sharpe': np.nan,
            'path_up_capture': np.nan,
            'path_smoothness': np.nan,
            'path_return_22d': np.nan,
        }

    t0_close = df.iloc[t0_idx]['close']
    future_closes = df.iloc[t0_idx + 1:end_idx + 1]['close'].values
    return compute_path_stability(future_closes, t0_close)


def compute_excess_return_labels(df_candidates, index_close):
    """
    计算超额收益排名标签。

    参数:
        df_candidates: 候选点 DataFrame (需含 future_mfe, t0_date 列)
        index_close: 大盘指数 close Series

    返回:
        DataFrame 新增列:
          - index_return_22d: 同期大盘收益
          - excess_return: 超额收益
          - excess_rank: 百分位排名 (0~1)
    """
    df = df_candidates.copy()

    if 't0_date' in df.columns:
        df['_t0_date'] = pd.to_datetime(df['t0_date'])
    else:
        raise ValueError("候选数据缺少 t0_date 列")

    index_returns = []
    for _, row in df.iterrows():
        ret, valid = compute_index_return_22d(index_close, row['_t0_date'])
        index_returns.append(ret if valid else np.nan)

    df['index_return_22d'] = index_returns
    df['excess_return'] = df['future_mfe'] - df['index_return_22d']

    valid_mask = df['excess_return'].notna()
    df['excess_rank'] = np.nan
    if valid_mask.sum() > 0:
        df.loc[valid_mask, 'excess_rank'] = df.loc[valid_mask, 'excess_return'].rank(pct=True)

    df.drop(columns=['_t0_date'], inplace=True)
    return df


def apply_stability_penalty(df, lambda_val=0.15):
    """
    将路径稳定性融入排序得分。

    参数:
        df: 含 excess_rank 和 path_sharpe 列的 DataFrame
        lambda_val: 稳定性惩罚权重

    返回:
        DataFrame 新增列: final_rank_score
    """
    df = df.copy()

    sharpe_valid = df['path_sharpe'].notna()
    if sharpe_valid.sum() > 1:
        sharpe_vals = df.loc[sharpe_valid, 'path_sharpe']
        sharpe_min, sharpe_max = sharpe_vals.min(), sharpe_vals.max()
        if sharpe_max > sharpe_min:
            df['sharpe_norm'] = (df['path_sharpe'] - sharpe_min) / (sharpe_max - sharpe_min)
        else:
            df['sharpe_norm'] = 0.5
    else:
        df['sharpe_norm'] = 0.5

    df['sharpe_norm'] = df['sharpe_norm'].fillna(0.5)

    rank_valid = df['excess_rank'].notna()
    df['final_rank_score'] = np.nan
    if rank_valid.sum() > 0:
        df.loc[rank_valid, 'final_rank_score'] = (
            df.loc[rank_valid, 'excess_rank'] + lambda_val * df.loc[rank_valid, 'sharpe_norm']
        )

    df.drop(columns=['sharpe_norm'], inplace=True)
    return df


def post_scan_relabel(training_csv_path, output_csv_path=None, index_code='sh000001',
                      lambda_val=0.15):
    """
    后处理流水线：在扫描完成后，统一计算超额收益排名 + 稳定性惩罚。

    参数:
        training_csv_path: 原训练数据 CSV 路径
        output_csv_path: 输出路径（默认覆盖原路径加 _v2 后缀）
        index_code: 大盘指数代码
        lambda_val: 稳定性权重

    返回:
        处理后的 DataFrame
    """
    print(f"[Phase 3] 加载训练数据: {training_csv_path}")
    df = pd.read_csv(training_csv_path)
    print(f"  样本数: {len(df)}, 列数: {len(df.columns)}")

    print(f"[Phase 3] 加载大盘指数: {index_code}")
    index_close = load_index_daily(index_code)
    print(f"  指数范围: {index_close.index[0]} ~ {index_close.index[-1]}")

    print("[Phase 3] 计算超额收益排名...")
    df = compute_excess_return_labels(df, index_close)
    valid_excess = df['excess_rank'].notna().sum()
    print(f"  有效超额收益样本: {valid_excess} / {len(df)} ({valid_excess/len(df):.1%})")

    if 'path_sharpe' in df.columns:
        print(f"[Phase 3] 应用稳定性惩罚 (lambda={lambda_val})...")
        df = apply_stability_penalty(df, lambda_val)
        valid_final = df['final_rank_score'].notna().sum()
        print(f"  有效排序得分样本: {valid_final}")
    else:
        print("[Phase 3] path_sharpe 列缺失，跳过稳定性惩罚（将在扫描器更新后生效）")
        df['final_rank_score'] = df['excess_rank']

    _print_label_distribution(df)

    if output_csv_path is None:
        base, ext = os.path.splitext(training_csv_path)
        output_csv_path = f"{base}_v2{ext}"

    df.to_csv(output_csv_path, index=False)
    print(f"[Phase 3] 已保存: {output_csv_path}")

    return df


def _print_label_distribution(df):
    """打印新旧标签分布统计"""
    print("\n── 标签分布 ──")
    if 'label' in df.columns:
        print("旧标签 (三分类):")
        for lbl in sorted(df['label'].unique()):
            n = (df['label'] == lbl).sum()
            print(f"  Label {lbl}: {n} ({n/len(df):.1%})")

    if 'excess_rank' in df.columns:
        print("\n新标签 (超额收益排名):")
        valid = df['excess_rank'].dropna()
        if len(valid) > 0:
            print(f"  有效样本: {len(valid)}")
            print(f"  均值: {valid.mean():.4f} (期望 ~0.5)")
            print(f"  标准差: {valid.std():.4f}")
            for pct in [10, 25, 50, 75, 90, 95]:
                print(f"  P{pct}: {valid.quantile(pct/100):.4f}")

    if 'excess_return' in df.columns:
        valid_er = df['excess_return'].dropna()
        if len(valid_er) > 0:
            print(f"\n超额收益分布:")
            print(f"  均值: {valid_er.mean():.4f}")
            print(f"  中位数: {valid_er.median():.4f}")
            print(f"  标准差: {valid_er.std():.4f}")

    if 'final_rank_score' in df.columns:
        valid_fs = df['final_rank_score'].dropna()
        if len(valid_fs) > 0:
            print(f"\n最终排序得分分布:")
            print(f"  均值: {valid_fs.mean():.4f}")
            print(f"  中位数: {valid_fs.median():.4f}")
            print(f"  P95: {valid_fs.quantile(0.95):.4f}")

    if 'label' in df.columns and 'excess_rank' in df.columns:
        print("\n旧标签 vs 新排名交叉分析:")
        for lbl in sorted(df['label'].unique()):
            mask = df['label'] == lbl
            sub = df.loc[mask, 'excess_rank'].dropna()
            if len(sub) > 0:
                print(f"  Label {lbl}: excess_rank 中位数={sub.median():.4f}, "
                      f"均值={sub.mean():.4f}")


def tune_lambda(training_csv_path, lambda_candidates=None, index_code='sh000001'):
    """
    在验证集上扫描不同 λ 值，选择最优稳定性惩罚权重。
    使用简易 LightGBM Ranker 评估 NDCG@20。

    参数:
        training_csv_path: 含 path_sharpe 的训练数据
        lambda_candidates: λ 候选值列表
        index_code: 大盘指数代码

    返回:
        (最优 λ, 各 λ 的 NDCG 列表)
    """
    import lightgbm as lgb
    from sklearn.metrics import ndcg_score

    if lambda_candidates is None:
        lambda_candidates = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]

    df = pd.read_csv(training_csv_path)
    index_close = load_index_daily(index_code)
    df = compute_excess_return_labels(df, index_close)

    drop_cols = ['target', 'label', 'stock_code', 't0_date', 'is_positive',
                 'future_mfe', 'index_return_22d', 'excess_return', 'excess_rank',
                 'final_rank_score', 'path_sharpe', 'path_up_capture',
                 'path_smoothness', 'path_return_22d']
    feature_cols = [c for c in df.columns if c not in drop_cols and df[c].dtype in ('float64', 'float32', 'int64')]

    df = df.sort_values('t0_date').reset_index(drop=True)
    split_idx = int(len(df) * 0.8)
    df_val = df.iloc[split_idx:].copy()

    if 'path_sharpe' not in df_val.columns:
        print("[tune_lambda] path_sharpe 列缺失，无法调优，返回默认 λ=0.15")
        return 0.15, {}

    df_val = apply_stability_penalty(df_val, lambda_val=0.0)
    X_val = df_val[feature_cols].fillna(0)
    groups_val = df_val.groupby('t0_date').size().values
    group_mask = groups_val >= 3
    if group_mask.sum() == 0:
        print("[tune_lambda] 无有效分组，返回默认 λ=0.15")
        return 0.15, {}

    results = {}
    for lam in lambda_candidates:
        df_tmp = df_val.copy()
        df_tmp = apply_stability_penalty(df_tmp, lambda_val=lam)
        y_val = df_tmp['final_rank_score'].fillna(0).values

        params = {
            'objective': 'lambdarank',
            'metric': 'ndcg',
            'eval_at': [10, 20, 50],
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.05,
            'verbose': -1,
            'seed': 42,
        }

        df_train = df.iloc[:split_idx].copy()
        df_train = compute_excess_return_labels(df_train, index_close)
        df_train = apply_stability_penalty(df_train, lambda_val=lam)
        X_train = df_train[feature_cols].fillna(0)
        y_train = df_train['final_rank_score'].fillna(0).values

        train_groups = df_train.groupby('t0_date').size().values
        train_groups = train_groups[train_groups >= 3]

        if len(X_train) == 0 or len(X_val) == 0:
            continue

        try:
            train_data = lgb.Dataset(X_train, label=y_train, group=train_groups)
            model = lgb.train(params, train_data, num_boost_round=50)

            preds = model.predict(X_val)
            ndcg_vals = []
            offset = 0
            group_idx = 0
            for gs in groups_val:
                if gs < 3:
                    offset += gs
                    continue
                true_rel = y_val[offset:offset + gs]
                pred_rel = preds[offset:offset + gs]
                if len(true_rel) >= 20 and true_rel.max() > true_rel.min():
                    from sklearn.metrics import ndcg_score as _ndcg
                    ndcg_vals.append(_ndcg(
                        np.array([true_rel]), np.array([pred_rel]), k=20))
                offset += gs
                group_idx += 1

            mean_ndcg = np.mean(ndcg_vals) if ndcg_vals else 0.0
            results[lam] = mean_ndcg
            print(f"  λ={lam:.2f}: NDCG@20 = {mean_ndcg:.4f} ({len(ndcg_vals)} groups)")
        except Exception as e:
            print(f"  λ={lam:.2f}: 训练失败 - {e}")
            results[lam] = 0.0

    if results:
        best_lam = max(results, key=results.get)
        print(f"\n最优 λ = {best_lam:.2f} (NDCG@20 = {results[best_lam]:.4f})")
        return best_lam, results
    return 0.15, results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Super Trend V1: 标签重构")
    parser.add_argument('--input', type=str,
                        default=os.path.join("data", "result", "super_trend",
                                             "super_trend_training_data.csv"),
                        help="输入训练数据 CSV")
    parser.add_argument('--output', type=str, default=None,
                        help="输出 CSV 路径（默认加 _v2 后缀）")
    parser.add_argument('--index', type=str, default='sh000001',
                        help="大盘指数代码")
    parser.add_argument('--lam', type=float, default=0.15,
                        help="稳定性惩罚权重")
    parser.add_argument('--tune', action='store_true',
                        help="自动调优 λ")

    args = parser.parse_args()

    if args.tune:
        print("=== λ 自动调优 ===")
        best_lam, _ = tune_lambda(args.input, index_code=args.index)
        print(f"\n使用最优 λ={best_lam:.2f} 重新生成标签...")
        post_scan_relabel(args.input, args.output, args.index, best_lam)
    else:
        post_scan_relabel(args.input, args.output, args.index, args.lam)
