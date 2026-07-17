"""
Phase 3 测试: 标签重构（超额收益排名 + 路径稳定性）
运行: cd backend && python -m pytest test_super_trend/test_label_builder.py -v
或:   cd backend && python test_super_trend/test_label_builder.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from super_trend_label_builder import (
    compute_path_stability,
    compute_path_stability_from_df,
    load_index_daily,
    compute_index_return_22d,
    compute_excess_return_labels,
    apply_stability_penalty,
)


class TestPathStability:
    """路径稳定性单元测试"""

    def test_smooth_uptrend(self):
        """流畅主升: 每日+1%, sharpe应很高"""
        closes = [10.0 * (1.01 ** i) for i in range(1, 23)]
        r = compute_path_stability(closes, 10.0)
        assert r['path_sharpe'] > 5.0, f"流畅主升 sharpe 应 > 5, got {r['path_sharpe']}"
        assert r['path_up_capture'] > 0.9, f"up_capture 应 > 0.9, got {r['path_up_capture']}"
        assert r['path_smoothness'] > 0.9, f"smoothness 应 > 0.9, got {r['path_smoothness']}"
        assert r['path_return_22d'] > 0.20, f"22d收益应 > 20%"

    def test_spike_then_drop(self):
        """脉冲式: 第3天暴涨后连跌, sharpe应很低"""
        closes = [10.0] * 22
        closes[2] = 11.5
        for i in range(3, 22):
            closes[i] = closes[i-1] * 0.97
        r = compute_path_stability(closes, 10.0)
        assert r['path_sharpe'] < 1.0, f"脉冲式 sharpe 应 < 1, got {r['path_sharpe']}"
        assert r['path_up_capture'] < 0.3, f"up_capture 应 < 0.3"

    def test_smooth_vs_spike(self):
        """流畅主升 sharpe > 脉冲式 sharpe"""
        smooth = [10.0 * (1.01 ** i) for i in range(1, 23)]
        spike = [10.0] * 22
        spike[2] = 11.5
        for i in range(3, 22):
            spike[i] = spike[i-1] * 0.97
        r_smooth = compute_path_stability(smooth, 10.0)
        r_spike = compute_path_stability(spike, 10.0)
        assert r_smooth['path_sharpe'] > r_spike['path_sharpe']

    def test_oscillating(self):
        """震荡: up_capture 接近 0.5"""
        osc = [10.0 * (1 + 0.02 * (1 if i % 2 == 0 else -1)) for i in range(22)]
        r = compute_path_stability(osc, 10.0)
        assert 0.3 < r['path_up_capture'] < 0.7

    def test_insufficient_data(self):
        """不足5天返回 NaN"""
        r = compute_path_stability([10.1, 10.2], 10.0)
        assert np.isnan(r['path_sharpe'])
        assert np.isnan(r['path_up_capture'])

    def test_from_df(self):
        """从 DataFrame 计算路径稳定性"""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        df = pd.DataFrame({
            'close': 100 + np.arange(100) * 0.5,
            'volume': np.ones(100) * 100000,
        }, index=dates)
        r = compute_path_stability_from_df(df, 50, eval_days=22)
        assert not np.isnan(r['path_sharpe'])
        assert r['path_sharpe'] > 0  # 单调上升


class TestIndexReturn:
    """指数收益计算测试"""

    @classmethod
    def setup_class(cls):
        cls.index_close = load_index_daily('sh000001')

    def test_index_loads(self):
        assert len(self.index_close) > 1000

    def test_normal_date(self):
        ret, valid = compute_index_return_22d(self.index_close, pd.Timestamp('2024-01-15'))
        assert valid
        assert -0.3 < ret < 0.3, f"22d指数收益异常: {ret}"

    def test_date_not_in_index(self):
        """非交易日: 应使用最近交易日"""
        ret, valid = compute_index_return_22d(self.index_close, pd.Timestamp('2024-01-14'))  # 周日
        assert valid

    def test_boundary_date(self):
        """接近数据末尾"""
        last_date = self.index_close.index[-1]
        ret, valid = compute_index_return_22d(self.index_close, last_date)
        # 可能 valid=False (不够22天), 但不应报错


class TestExcessReturnLabels:
    """超额收益排名标签测试"""

    @classmethod
    def setup_class(cls):
        cls.index_close = load_index_daily('sh000001')

    def test_basic_computation(self):
        df = pd.DataFrame({
            'stock_code': ['sh600036', 'sz000002', 'sh601318'],
            't0_date': ['2024-01-15', '2024-03-20', '2024-06-10'],
            'future_mfe': [0.68, 0.03, 0.52],
        })
        result = compute_excess_return_labels(df, self.index_close)
        assert 'excess_return' in result.columns
        assert 'excess_rank' in result.columns
        assert result['excess_rank'].notna().sum() == 3

    def test_rank_ordering(self):
        """牛股排名 > 弱股排名"""
        df = pd.DataFrame({
            'stock_code': ['bull', 'weak'],
            't0_date': ['2024-01-15', '2024-01-15'],
            'future_mfe': [0.80, 0.02],
        })
        result = compute_excess_return_labels(df, self.index_close)
        bull_rank = result.loc[result['stock_code'] == 'bull', 'excess_rank'].values[0]
        weak_rank = result.loc[result['stock_code'] == 'weak', 'excess_rank'].values[0]
        assert bull_rank > weak_rank

    def test_rank_distribution(self):
        """大量样本时排名应近似均匀"""
        np.random.seed(42)
        n = 1000
        df = pd.DataFrame({
            'stock_code': [f'stock_{i}' for i in range(n)],
            't0_date': pd.date_range('2024-01-01', periods=100).repeat(10).strftime('%Y-%m-%d')[:n],
            'future_mfe': np.random.exponential(0.15, n),
        })
        result = compute_excess_return_labels(df, self.index_close)
        valid_ranks = result['excess_rank'].dropna()
        assert abs(valid_ranks.mean() - 0.5) < 0.05, f"排名均值应接近0.5, got {valid_ranks.mean()}"


class TestStabilityPenalty:
    """稳定性惩罚测试"""

    def test_penalty_applied(self):
        df = pd.DataFrame({
            'excess_rank': [0.5, 0.5, 0.5],
            'path_sharpe': [5.0, 0.0, -2.0],
        })
        result = apply_stability_penalty(df, lambda_val=0.2)
        assert 'final_rank_score' in result.columns
        scores = result['final_rank_score'].values
        assert scores[0] > scores[1] > scores[2], "高sharpe得分应 > 低sharpe得分"

    def test_lambda_zero(self):
        """λ=0 时 final_score = excess_rank"""
        df = pd.DataFrame({
            'excess_rank': [0.3, 0.7],
            'path_sharpe': [10.0, -5.0],
        })
        result = apply_stability_penalty(df, lambda_val=0.0)
        np.testing.assert_array_almost_equal(
            result['final_rank_score'].values,
            [0.3, 0.7],
            decimal=3,
        )

    def test_missing_sharpe(self):
        """path_sharpe 缺失时使用中位数填充"""
        df = pd.DataFrame({
            'excess_rank': [0.5, 0.8],
            'path_sharpe': [np.nan, 2.0],
        })
        result = apply_stability_penalty(df, lambda_val=0.15)
        assert result['final_rank_score'].notna().sum() == 2


class TestOldVsNewLabel:
    """新旧标签一致性测试"""

    def test_label_separation(self):
        """旧 Label 2 排名中位数应显著高于 Label 0"""
        # test file is at backend/test_super_trend/, project root is 2 levels up
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        csv_path = os.path.join(
            project_root,
            'data', 'result', 'super_trend', 'super_trend_training_data_v2.csv'
        )
        if not os.path.exists(csv_path):
            print(f"跳过 (文件不存在): {csv_path}")
            return

        df = pd.read_csv(csv_path)
        assert 'excess_rank' in df.columns, "需要 _v2 CSV"

        for lbl in [0, 1, 2]:
            median = df.loc[df['label'] == lbl, 'excess_rank'].median()
            print(f"  Label {lbl}: excess_rank 中位数 = {median:.4f}")

        l0_median = df.loc[df['label'] == 0, 'excess_rank'].median()
        l2_median = df.loc[df['label'] == 2, 'excess_rank'].median()
        assert l2_median > 0.9, f"Label 2 中位数应 > 0.9, got {l2_median}"
        assert l0_median < 0.4, f"Label 0 中位数应 < 0.4, got {l0_median}"


def run_all_tests():
    """手动运行所有测试"""
    test_classes = [
        TestPathStability,
        TestIndexReturn,
        TestExcessReturnLabels,
        TestStabilityPenalty,
        TestOldVsNewLabel,
    ]

    total = 0
    passed = 0
    failed = 0

    for cls in test_classes:
        print(f"\n{'='*60}")
        print(f"  {cls.__name__}")
        print(f"{'='*60}")

        instance = cls()
        if hasattr(cls, 'setup_class'):
            try:
                cls.setup_class()
            except Exception as e:
                print(f"  setup_class 失败: {e}")
                continue

        methods = [m for m in dir(instance) if m.startswith('test_')]
        for method_name in methods:
            total += 1
            try:
                getattr(instance, method_name)()
                passed += 1
                print(f"  ✓ {method_name}")
            except Exception as e:
                failed += 1
                print(f"  ✗ {method_name}: {e}")

    print(f"\n{'='*60}")
    print(f"总计: {total} | 通过: {passed} | 失败: {failed}")
    print(f"{'='*60}")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
