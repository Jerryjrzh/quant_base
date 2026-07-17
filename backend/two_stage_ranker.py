"""
P0-2: 两阶段排序
  粗排: 全特征模型 → Top 100
  精排: 仅 V2 时序/排名特征 → Top 20 (禁用 boll_width 等截面特征)
"""

import pandas as pd
import numpy as np
import os
import sys
import pickle
import warnings
warnings.filterwarnings('ignore')

import lightgbm as lgb

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


CROSS_SECTIONAL_FEATURES = [
    't0_close', 't0_volume', 't0_rsi', 't0_macd',
    'bias_ma20', 'bias_ma60', 'atr_percentile', 'boll_width',
    'pre_breakout_vol_shrink_days', 'vol_breakout_ratio',
    'price_position_120d', 'stock_return_20d', 'rs_20d',
    'vol_turnover_ratio', 'volume_percentile_120d',
    'rsi_explosion_force', 'macd_pit_depth', 'days_underwater',
    'days_below_ma30', 'vol_dryup_count', 'ma_bull_alignment_days',
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
    'price_rebound_from_pit', 'is_fake_breakdown', 'is_water_ignition',
    'is_extreme_volume_dry',
]

COARSE_TOP_N = 100
FINE_TOP_N = 20
COMMISSION = 0.0015
MAX_GAP_PCT = 0.05


class TwoStageRanker:
    """两阶段排序引擎"""

    def __init__(self):
        self.coarse_model = None
        self.fine_model = None
        self.coarse_features = []
        self.fine_features = []

    def load_coarse_model(self):
        """加载粗排模型（全特征）"""
        model_path = _proj('data', 'result', 'super_trend', 'models', 'trend_ranker_v1.pkl')
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
        self.coarse_model = data['model']
        self.coarse_features = data['feature_columns']
        print(f"粗排模型加载: {self.coarse_model.num_trees()} 棵树, {len(self.coarse_features)} 特征")

    def train_fine_model(self):
        """训练精排模型（仅 V2 特征）"""
        from super_trend_ranker_trainer import SuperTrendRanker

        data_path = _proj('data', 'result', 'super_trend', 'super_trend_training_data_v2.csv')
        df = pd.read_csv(data_path)
        df = df.sort_values('t0_date').reset_index(drop=True)

        self.fine_features = [f for f in V2_FEATURES if f in df.columns]
        print(f"精排特征: {len(self.fine_features)} 个 (V2 时序+排名)")

        drop_cols = [
            'target', 'label', 'stock_code', 't0_date', 'is_positive',
            'future_mfe', 'index_return_22d', 'excess_return', 'excess_rank',
            'final_rank_score', 'path_sharpe', 'path_up_capture',
            'path_smoothness', 'path_return_22d', '_relevance', '_group',
        ]

        all_cols = [c for c in df.columns if c not in drop_cols
                    and df[c].dtype in ('float64', 'float32', 'int64', 'int32')]
        self.fine_features = [f for f in self.fine_features if f in all_cols]

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

        split_idx = int(len(df) * 0.8)
        split_date = df.iloc[split_idx]['t0_date']
        df_train = df[df['t0_date'] < split_date]

        X_tr = df_train[self.fine_features].fillna(0)
        y_tr = df_train['_relevance'].values
        g_tr = df_train.groupby('t0_date').size().values

        train_data = lgb.Dataset(X_tr, label=y_tr, group=g_tr)
        self.fine_model = lgb.train(
            {
                'objective': 'lambdarank',
                'metric': 'ndcg',
                'learning_rate': 0.05,
                'num_leaves': 31,
                'max_depth': -1,
                'min_child_samples': 20,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'reg_alpha': 0.1,
                'reg_lambda': 1.0,
                'verbose': -1,
            },
            train_data, num_boost_round=200,
        )
        print(f"精排模型训练完成: {self.fine_model.num_trees()} 棵树")

        importance = pd.DataFrame({
            'feature': self.fine_features,
            'importance': self.fine_model.feature_importance(importance_type='gain'),
        }).sort_values('importance', ascending=False)

        print(f"\n── 精排模型特征重要性 Top 10 ──")
        for _, row in importance.head(10).iterrows():
            print(f"  {row['feature']}: {row['importance']:.0f}")

        self._fine_test_df = df[df['t0_date'] >= split_date]

        fine_model_path = _proj('data', 'result', 'super_trend', 'models', 'trend_ranker_v1_fine.pkl')
        with open(fine_model_path, 'wb') as f:
            pickle.dump({
                'model': self.fine_model,
                'feature_columns': self.fine_features,
                'model_type': 'fine_ranker',
            }, f)
        print(f"精排模型已保存: {fine_model_path}")

    def predict_two_stage(self, day_df):
        """
        两阶段排序预测:
          1. 粗排模型打分 → Top COARSE_TOP_N
          2. 精排模型在 Top N 内重排 → Top FINE_TOP_N
        """
        if len(day_df) < FINE_TOP_N:
            return day_df

        coarse_feats = [c for c in self.coarse_features if c in day_df.columns]
        X_coarse = day_df[coarse_feats].fillna(0)
        coarse_scores = self.coarse_model.predict(X_coarse)
        day_df = day_df.copy()
        day_df['_coarse_score'] = coarse_scores

        top_coarse = day_df.nlargest(COARSE_TOP_N, '_coarse_score')

        fine_feats = [c for c in self.fine_features if c in top_coarse.columns]
        X_fine = top_coarse[fine_feats].fillna(0)
        fine_scores = self.fine_model.predict(X_fine)
        top_coarse = top_coarse.copy()
        top_coarse['_fine_score'] = fine_scores

        result = top_coarse.nlargest(FINE_TOP_N, '_fine_score')
        result['_score'] = result['_fine_score']
        return result

    def run_two_stage_only(self, start_date=None, end_date=None):
        """
        在指定日期区间上执行两阶段排序（仅选股，不做结算）。

        返回:
            test_df: 测试期完整 DataFrame
            daily_selections: dict, {date: DataFrame (with _coarse_score, _fine_score)}
        """
        if self.coarse_model is None:
            self.load_coarse_model()
        if self.fine_model is None:
            self.train_fine_model()

        data_path = _proj('data', 'result', 'super_trend', 'super_trend_training_data_v2.csv')
        df = pd.read_csv(data_path)
        df = df.sort_values('t0_date').reset_index(drop=True)
        split_idx = int(len(df) * 0.8)
        test_df = df.iloc[split_idx:].copy()

        if start_date is not None:
            test_df = test_df[test_df['t0_date'] >= start_date]
        if end_date is not None:
            test_df = test_df[test_df['t0_date'] <= end_date]

        test_dates = sorted(test_df['t0_date'].unique())
        print(f"\n=== 两阶段排序 (仅选股) ===")
        print(f"区间: {test_dates[0]} ~ {test_dates[-1]}, {len(test_dates)} 天")

        daily_selections = {}
        for date in test_dates:
            day_df = test_df[test_df['t0_date'] == date].copy()
            if len(day_df) < FINE_TOP_N:
                continue
            selected = self.predict_two_stage(day_df)
            daily_selections[date] = selected

        print(f"完成: {len(daily_selections)} 个交易日产生推荐")
        return test_df, daily_selections

    def run_backtest(self):
        """用两阶段排序跑回测"""
        if self.coarse_model is None:
            self.load_coarse_model()
        if self.fine_model is None:
            self.train_fine_model()

        data_path = _proj('data', 'result', 'super_trend', 'super_trend_training_data_v2.csv')
        df = pd.read_csv(data_path)
        df = df.sort_values('t0_date').reset_index(drop=True)
        split_idx = int(len(df) * 0.8)
        test_df = df.iloc[split_idx:].copy()

        test_dates = sorted(test_df['t0_date'].unique())
        print(f"\n=== 两阶段回测 ===")
        print(f"测试期: {test_dates[0]} ~ {test_dates[-1]}, {len(test_dates)} 天")
        print(f"粗排 Top {COARSE_TOP_N} → 精排 Top {FINE_TOP_N}")

        all_trades = []
        daily_pnl = []

        for date in test_dates:
            day_df = test_df[test_df['t0_date'] == date].copy()
            if len(day_df) < FINE_TOP_N:
                continue

            selected = self.predict_two_stage(day_df)

            day_return = 0.0
            n_bought = 0
            for _, row in selected.iterrows():
                t1_gap = row.get('t1_gap_up_pct', np.nan)
                if pd.notna(t1_gap) and t1_gap > MAX_GAP_PCT:
                    continue

                future_mfe = row.get('future_mfe', 0)
                if pd.isna(future_mfe):
                    future_mfe = 0

                simulated_return = future_mfe * 0.5
                net_return = simulated_return - 2 * COMMISSION

                trade = {
                    'date': date,
                    'stock_code': row.get('stock_code', ''),
                    'coarse_score': row.get('_coarse_score', 0),
                    'fine_score': row.get('_fine_score', row.get('_score', 0)),
                    'future_mfe': future_mfe,
                    'net_return': net_return,
                }
                all_trades.append(trade)
                day_return += net_return
                n_bought += 1

            if n_bought > 0:
                daily_pnl.append({
                    'date': date,
                    'n_stocks': n_bought,
                    'avg_return': day_return / n_bought,
                })

        trades_df = pd.DataFrame(all_trades)
        daily_df = pd.DataFrame(daily_pnl)

        self._print_two_stage_results(trades_df, daily_df, test_df)
        return trades_df, daily_df

    def _print_two_stage_results(self, trades_df, daily_df, test_df):
        """打印两阶段结果"""
        print(f"\n{'='*60}")
        print(f"  两阶段排序结果")
        print(f"{'='*60}")

        avg_return = trades_df['net_return'].mean()
        avg_mfe = trades_df['future_mfe'].mean()
        win_rate = len(trades_df[trades_df['net_return'] > 0]) / len(trades_df)

        baseline_mfe = test_df['future_mfe'].mean()
        baseline_return = baseline_mfe * 0.5 - 2 * COMMISSION

        print(f"  总交易笔数:   {len(trades_df)}")
        print(f"  平均净收益:   {avg_return:.4f}")
        print(f"  平均 MFE:     {avg_mfe:.4f}")
        print(f"  胜率:         {win_rate:.2%}")
        print(f"\n  ── 与单阶段对比 ──")
        print(f"  单阶段 Top 20: avg MFE=0.2398, 净收益=0.1066")
        print(f"  两阶段 Top 20: avg MFE={avg_mfe:.4f}, 净收益={avg_return:.4f}")
        print(f"  全量基线:      avg MFE={baseline_mfe:.4f}, 净收益={baseline_return:.4f}")

        improvement = (avg_return - 0.1066) / 0.1066
        print(f"  vs 单阶段提升: {improvement:+.1%}")
        print(f"{'='*60}")


def main():
    print("=== P0-2: 两阶段排序 ===")
    ranker = TwoStageRanker()
    ranker.load_coarse_model()
    ranker.train_fine_model()
    trades_df, daily_df = ranker.run_backtest()

    out_dir = _proj('data', 'result', 'super_trend')
    trades_df.to_csv(os.path.join(out_dir, 'backtest_two_stage_trades.csv'), index=False)
    print(f"\n交易明细已保存")


if __name__ == "__main__":
    main()
