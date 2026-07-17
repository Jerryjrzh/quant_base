"""
Phase 4 测试: 排序模型 (LambdaRank)
运行: cd backend && source .venv/bin/activate && python test_super_trend/test_ranker_trainer.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np


class TestRelevanceGrades:
    """离散化等级转换测试"""

    def test_basic_conversion(self):
        from super_trend_ranker_trainer import SuperTrendRanker
        scores = np.array([0.1, 0.5, 0.9, 0.3])
        grades = SuperTrendRanker._to_relevance_grades(scores, max_grade=31)
        assert grades.dtype == int
        assert grades[2] > grades[1] > grades[0]  # 0.9 > 0.5 > 0.1
        assert grades[2] <= 31
        assert grades[0] >= 0

    def test_all_same(self):
        from super_trend_ranker_trainer import SuperTrendRanker
        scores = np.array([0.5, 0.5, 0.5])
        grades = SuperTrendRanker._to_relevance_grades(scores)
        assert all(g == 15 for g in grades)  # max_grade//2

    def test_with_nan(self):
        from super_trend_ranker_trainer import SuperTrendRanker
        scores = np.array([0.1, np.nan, 0.9])
        grades = SuperTrendRanker._to_relevance_grades(scores)
        assert grades[1] == 0  # NaN → 0


class TestDataLoading:
    """数据加载测试"""

    def test_load_and_group(self):
        from super_trend_ranker_trainer import SuperTrendRanker
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        csv_path = os.path.join(project_root, 'data', 'result', 'super_trend',
                                'super_trend_training_data_v2.csv')
        if not os.path.exists(csv_path):
            print(f"  跳过: {csv_path} 不存在")
            return

        ranker = SuperTrendRanker(training_data_path=csv_path)
        df = ranker.load_training_data()

        assert '_relevance' not in ranker.feature_columns, "数据泄露!"
        assert len(ranker.feature_columns) >= 20, f"特征数不足: {len(ranker.feature_columns)}"
        assert '_relevance' in df.columns
        assert '_group' in df.columns
        assert df['_relevance'].dtype == int

        group_sizes = df.groupby('t0_date').size()
        assert group_sizes.min() >= 3, "存在组大小 < 3"
        print(f"  样本: {len(df)}, 组: {df['t0_date'].nunique()}, 特征: {len(ranker.feature_columns)}")


class TestQuickTraining:
    """快速训练测试"""

    def test_training_pipeline(self):
        from super_trend_ranker_trainer import SuperTrendRanker
        import lightgbm as lgb
        from sklearn.metrics import ndcg_score

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        csv_path = os.path.join(project_root, 'data', 'result', 'super_trend',
                                'super_trend_training_data_v2.csv')
        if not os.path.exists(csv_path):
            print(f"  跳过: {csv_path} 不存在")
            return

        ranker = SuperTrendRanker(training_data_path=csv_path)
        df = ranker.load_training_data()

        split_date = df.iloc[int(len(df) * 0.8)]['t0_date']
        df_train = df[df['t0_date'] < split_date]
        df_test = df[df['t0_date'] >= split_date]

        X_tr = df_train[ranker.feature_columns].fillna(0)
        y_tr = df_train['_relevance'].values
        g_tr = ranker._prepare_groups(df_train)

        train_data = lgb.Dataset(X_tr, label=y_tr, group=g_tr)
        model = lgb.train(
            {**ranker.params, 'verbose': -1, 'num_leaves': 15},
            train_data, num_boost_round=30,
        )
        assert model.num_trees() > 0

        X_te = df_test[ranker.feature_columns].fillna(0)
        y_te = df_test['_relevance'].values
        g_te = ranker._prepare_groups(df_test)
        preds = model.predict(X_te)

        offset = 0
        ndcg_scores = []
        for gs in g_te:
            true_rel = y_te[offset:offset + gs]
            pred_rel = preds[offset:offset + gs]
            if gs >= 20 and true_rel.max() > true_rel.min():
                try:
                    s = ndcg_score(np.array([true_rel]), np.array([pred_rel]), k=20)
                    ndcg_scores.append(s)
                except Exception:
                    pass
            offset += gs

        mean_ndcg = np.mean(ndcg_scores) if ndcg_scores else 0.0
        print(f"  NDCG@20: {mean_ndcg:.4f}")
        assert mean_ndcg > 0.4, f"NDCG 过低: {mean_ndcg}"

        # Top N MFE 应高于基线
        df_eval = df_test.copy()
        df_eval['_score'] = preds
        top100_mfe = df_eval.nlargest(100, '_score')['future_mfe'].mean()
        base_mfe = df_eval['future_mfe'].mean()
        print(f"  Top100 MFE: {top100_mfe:.4f}, 基线: {base_mfe:.4f}")
        assert top100_mfe > base_mfe * 2, "Top100 未显著优于基线"


def run_all_tests():
    test_classes = [
        TestRelevanceGrades,
        TestDataLoading,
        TestQuickTraining,
    ]
    total = passed = failed = 0
    for cls in test_classes:
        print(f"\n{'='*60}\n  {cls.__name__}\n{'='*60}")
        instance = cls()
        for m in [m for m in dir(instance) if m.startswith('test_')]:
            total += 1
            try:
                getattr(instance, m)()
                passed += 1
                print(f"  ✓ {m}")
            except Exception as e:
                failed += 1
                print(f"  ✗ {m}: {e}")
    print(f"\n{'='*60}\n总计: {total} | 通过: {passed} | 失败: {failed}")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
