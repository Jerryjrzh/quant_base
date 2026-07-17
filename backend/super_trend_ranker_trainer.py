"""
Super Trend V1 Phase 4: 排序模型训练器 (LambdaRank)
从分类 (binary cross-entropy) → 排序 (LambdaRank/NDCG)

核心变更:
  - objective='lambdarank', metric='ndcg'
  - 按 t0_date 分组（同日异动股票互相比较）
  - 目标: final_rank_score (超额收益排名 + 路径稳定性)
  - 评估: NDCG@10/20/50, Top N 平均未来收益
"""

import pandas as pd
import numpy as np
import pickle
import os
import sys
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import ndcg_score

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)

MODEL_OUTPUT_DIR = _proj("data", "result", "super_trend", "models")
ANALYSIS_DIR = _proj("data", "result", "super_trend", "analysis")
os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
os.makedirs(ANALYSIS_DIR, exist_ok=True)


class SuperTrendRanker:
    """Super Trend 排序模型训练器 (LambdaRank)"""

    def __init__(self, training_data_path=None):
        self.model = None
        self.feature_columns = []
        self.training_data_path = training_data_path or _proj(
            "data", "result", "super_trend", "super_trend_training_data_v2.csv"
        )
        self.drop_cols = [
            'target', 'label', 'stock_code', 't0_date', 'is_positive',
            'future_mfe', 'index_return_22d', 'excess_return', 'excess_rank',
            'final_rank_score', 'path_sharpe', 'path_up_capture',
            'path_smoothness', 'path_return_22d',
            '_relevance', '_group',
        ]
        self.min_group_size = 3

        self.params = {
            'objective': 'lambdarank',
            'metric': 'ndcg',
            'eval_at': [10, 20, 50],
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.02,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': -1,
            'seed': 42,
            'min_data_in_leaf': 20,
        }

    @staticmethod
    def _to_relevance_grades(scores, max_grade=31):
        """将浮点排序得分离散化为 0~max_grade 的整数等级（LambdaRank 要求整数标签）"""
        scores = np.asarray(scores, dtype=float)
        valid = ~np.isnan(scores)
        grades = np.zeros(len(scores), dtype=int)
        if valid.sum() > 0:
            s = scores[valid]
            s_min, s_max = s.min(), s.max()
            if s_max > s_min:
                grades[valid] = np.clip(
                    ((s - s_min) / (s_max - s_min) * max_grade).astype(int),
                    0, max_grade
                )
            else:
                grades[valid] = max_grade // 2
        return grades

    def load_training_data(self):
        """加载训练数据，按 t0_date 分组"""
        print(f"加载训练数据: {self.training_data_path}")

        if not os.path.exists(self.training_data_path):
            raise FileNotFoundError(f"训练数据不存在: {self.training_data_path}")

        df = pd.read_csv(self.training_data_path)
        print(f"数据维度: {df.shape}")

        if 'final_rank_score' not in df.columns:
            raise ValueError("缺少 final_rank_score 列，请先运行 Phase 3 标签重构")

        df = df.sort_values('t0_date').reset_index(drop=True)

        # LambdaRank 要求整数标签，将浮点排序得分离散化为 0~31
        df['_relevance'] = self._to_relevance_grades(df['final_rank_score'].values)
        print(f"相关度等级分布: {np.bincount(df['_relevance'], minlength=32)[:8]}... (前8级)")

        self.feature_columns = [
            c for c in df.columns
            if c not in self.drop_cols and df[c].dtype in ('float64', 'float32', 'int64', 'int32')
        ]
        print(f"特征数: {len(self.feature_columns)}")
        print(f"特征列表: {self.feature_columns}")

        df['_group'] = df.groupby('t0_date').ngroup()
        group_sizes = df.groupby('_group').size()
        valid_groups = group_sizes[group_sizes >= self.min_group_size].index
        df = df[df['_group'].isin(valid_groups)].copy()
        df['_group'] = df.groupby('t0_date').ngroup()

        print(f"过滤后: {len(df)} 样本, {df['_group'].nunique()} 组 (组大小≥{self.min_group_size})")

        self._df = df
        return df

    def _prepare_groups(self, df):
        """准备 LightGBM group 数组"""
        return df.groupby('t0_date').size().values

    def train(self, df=None, test_size=0.2):
        """训练排序模型，时序切割"""
        if df is None:
            df = self._df

        print(f"\n=== 排序模型训练 ===")

        split_idx = int(len(df) * (1 - test_size))
        split_date = df.iloc[split_idx]['t0_date']

        train_mask = df['t0_date'] < split_date
        test_mask = df['t0_date'] >= split_date

        df_train = df[train_mask].copy()
        df_test = df[test_mask].copy()

        print(f"时序切分: {split_date}")
        print(f"  训练: {len(df_train)} 样本, {df_train['t0_date'].nunique()} 天")
        print(f"  测试: {len(df_test)} 样本, {df_test['t0_date'].nunique()} 天")

        X_train = df_train[self.feature_columns].fillna(0)
        y_train = df_train['_relevance'].values
        groups_train = self._prepare_groups(df_train)

        X_test = df_test[self.feature_columns].fillna(0)
        y_test = df_test['_relevance'].values
        groups_test = self._prepare_groups(df_test)

        max_train_grade = y_train.max()
        y_test = np.clip(y_test, 0, max_train_grade)

        train_data = lgb.Dataset(X_train, label=y_train, group=groups_train)
        val_data = lgb.Dataset(X_test, label=y_test, group=groups_test, reference=train_data)

        print(f"\n训练 LambdaRank...")
        self.model = lgb.train(
            self.params,
            train_data,
            valid_sets=[val_data],
            num_boost_round=500,
            callbacks=[
                lgb.early_stopping(stopping_rounds=50),
                lgb.log_evaluation(period=50),
            ],
        )
        print(f"训练完成: {self.model.num_trees()} 棵树")

        self._evaluate(X_test, y_test, groups_test, df_test)
        return df_test

    def _evaluate(self, X_test, y_test, groups_test, df_test):
        """评估排序模型"""
        print(f"\n=== 模型评估 ===")

        preds = self.model.predict(X_test)

        ndcg_scores = []
        offset = 0
        for gs in groups_test:
            true_rel = y_test[offset:offset + gs]
            pred_rel = preds[offset:offset + gs]
            if gs >= 20 and true_rel.max() > true_rel.min():
                try:
                    score = ndcg_score(
                        np.array([true_rel]), np.array([pred_rel]), k=20)
                    ndcg_scores.append(score)
                except Exception:
                    pass
            offset += gs

        if ndcg_scores:
            print(f"NDCG@20 (均值): {np.mean(ndcg_scores):.4f} (±{np.std(ndcg_scores):.4f})")
            print(f"NDCG@20 (中位数): {np.median(ndcg_scores):.4f}")

        self._evaluate_topn(preds, df_test)
        self._analyze_feature_importance()

    def _evaluate_topn(self, preds, df_test):
        """Top N 评估: 模型选出的 Top N 的平均 future_mfe"""
        print(f"\n── Top N 平均未来收益 ──")

        df_eval = df_test.copy()
        df_eval['_pred_score'] = preds

        for n in [50, 100, 200, 500]:
            top_n = df_eval.nlargest(n, '_pred_score')
            avg_mfe = top_n['future_mfe'].mean()
            avg_excess = top_n['excess_return'].mean() if 'excess_return' in top_n.columns else np.nan
            label2_ratio = (top_n['label'] == 2).mean() if 'label' in top_n.columns else np.nan
            print(f"  Top {n:>4}: avg MFE={avg_mfe:.4f}, "
                  f"avg excess={avg_excess:.4f}, "
                  f"Label2比例={label2_ratio:.2%}")

        all_avg_mfe = df_eval['future_mfe'].mean()
        print(f"  全量基线: avg MFE={all_avg_mfe:.4f}")

    def _analyze_feature_importance(self):
        """特征重要性分析"""
        if self.model is None:
            return

        importance = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': self.model.feature_importance(importance_type='gain'),
        }).sort_values('importance', ascending=False)

        print(f"\n── 特征重要性 Top 15 ──")
        for _, row in importance.head(15).iterrows():
            print(f"  {row['feature']}: {row['importance']:.0f}")

        v2_features = [f for f in importance['feature'] if any(
            x in f for x in ['ma_dispersion', 'ma_glue', 'ma_divergence', 'ma_convergence',
                             'washout', 'lower_shadow', 'vol_trend', 'vol_shrink_streak',
                             'vol_low_point', 'streak_max', 'bull_ratio', 'last_3_pattern',
                             'rs_rank'])]
        v2_in_top10 = importance.head(10)['feature'].isin(v2_features).sum()
        print(f"\n  V2新特征在Top10中: {v2_in_top10} 个")
        print(f"  V2新特征总数: {len(v2_features)}")

        importance.to_csv(os.path.join(ANALYSIS_DIR, 'ranker_feature_importance.csv'), index=False)

    def cross_validation(self, df=None, n_splits=5):
        """时序交叉验证"""
        if df is None:
            df = self._df

        print(f"\n=== {n_splits}-折时序交叉验证 ===")

        tscv = TimeSeriesSplit(n_splits=n_splits)
        fold_ndcgs = []

        for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(df)):
            df_tr = df.iloc[train_idx]
            df_val = df.iloc[val_idx]

            X_tr = df_tr[self.feature_columns].fillna(0)
            y_tr = df_tr['_relevance'].values
            groups_tr = self._prepare_groups(df_tr)

            X_val = df_val[self.feature_columns].fillna(0)
            y_val = df_val['_relevance'].values
            groups_val = self._prepare_groups(df_val)

            max_train_grade = y_tr.max()
            y_val = np.clip(y_val, 0, max_train_grade)

            if len(groups_tr) == 0 or len(groups_val) == 0:
                continue

            train_data = lgb.Dataset(X_tr, label=y_tr, group=groups_tr)
            model = lgb.train(
                {**self.params, 'verbose': -1},
                train_data,
                num_boost_round=200,
            )

            preds = model.predict(X_val)
            fold_scores = []
            offset = 0
            for gs in groups_val:
                true_rel = y_val[offset:offset + gs]
                pred_rel = preds[offset:offset + gs]
                if gs >= 20 and true_rel.max() > true_rel.min():
                    try:
                        s = ndcg_score(np.array([true_rel]), np.array([pred_rel]), k=20)
                        fold_scores.append(s)
                    except Exception:
                        pass
                offset += gs

            mean_ndcg = np.mean(fold_scores) if fold_scores else 0.0
            fold_ndcgs.append(mean_ndcg)
            print(f"  Fold {fold_idx+1}: NDCG@20 = {mean_ndcg:.4f} ({len(fold_scores)} groups)")

        if fold_ndcgs:
            print(f"\nCV 结果: NDCG@20 = {np.mean(fold_ndcgs):.4f} (±{np.std(fold_ndcgs):.4f})")
        return fold_ndcgs

    def save_model(self, model_name='trend_ranker_v1.pkl'):
        """保存模型"""
        if self.model is None:
            raise ValueError("模型未训练")

        model_path = os.path.join(MODEL_OUTPUT_DIR, model_name)
        model_data = {
            'model': self.model,
            'feature_columns': self.feature_columns,
            'params': self.params,
            'training_date': datetime.now().isoformat(),
            'model_type': 'ranker',
        }
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)
        print(f"模型已保存: {model_path}")
        return model_path

    @staticmethod
    def load_model(model_path):
        """加载模型"""
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
        ranker = SuperTrendRanker()
        ranker.model = data['model']
        ranker.feature_columns = data['feature_columns']
        ranker.params = data.get('params', {})
        print(f"模型已加载: {model_path}")
        return ranker

    def predict(self, X):
        """预测排序得分"""
        if self.model is None:
            raise ValueError("模型未训练")
        return self.model.predict(X[self.feature_columns].fillna(0))


def main():
    """主训练流程"""
    print("=== Super Trend V1: 排序模型训练 (LambdaRank) ===")

    try:
        ranker = SuperTrendRanker()
        df = ranker.load_training_data()
        cv_results = ranker.cross_validation(df, n_splits=5)
        df_test = ranker.train(df)
        model_path = ranker.save_model('trend_ranker_v1.pkl')

        print(f"\n排序模型训练完成!")
        print(f"模型文件: {model_path}")
        return ranker

    except Exception as e:
        print(f"\n训练失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    ranker = main()
