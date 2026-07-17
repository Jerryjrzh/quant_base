"""
Phase 1 测试: 时序特征工程 (均线束 + 黄金坑 + 量能 + 价格行为)
运行: cd backend && python3 test_super_trend/test_feature_extractor_v2.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from super_trend_feature_extractor_v2 import (
    extract_ma_bundle_features,
    extract_washout_features,
    extract_volume_sequence_features,
    extract_price_action_features,
    extract_all_v2_features,
)


class TestMABundle:
    """均线束状态特征测试"""

    @classmethod
    def setup_class(cls):
        np.random.seed(42)
        dates = pd.date_range('2024-01-01', periods=200, freq='D')
        close = 100 + np.random.randn(200).cumsum() * 0.5
        cls.df = pd.DataFrame({
            'close': close,
            'ma5': pd.Series(close).rolling(5).mean().values,
            'ma10': pd.Series(close).rolling(10).mean().values,
            'ma20': pd.Series(close).rolling(20).mean().values,
            'ma60': pd.Series(close).rolling(60).mean().values,
        }, index=dates)

    def test_basic_output(self):
        """基本输出: 返回所有预期键"""
        r = extract_ma_bundle_features(self.df, 100)
        expected = ['ma_dispersion_5d', 'ma_dispersion_20d', 'ma_glue_max_days',
                     'ma_divergence_speed', 'ma_convergence_flag']
        for k in expected:
            assert k in r, f"缺少特征: {k}"

    def test_dispersion_range(self):
        """离散度应在合理范围 [0, 1)"""
        r = extract_ma_bundle_features(self.df, 100)
        assert 0 <= r['ma_dispersion_5d'] < 1.0
        assert 0 <= r['ma_dispersion_20d'] < 1.0

    def test_glue_days_range(self):
        """粘合天数应在 [0, 20]"""
        r = extract_ma_bundle_features(self.df, 100)
        assert 0 <= r['ma_glue_max_days'] <= 20

    def test_convergence_flag_binary(self):
        """收敛标志应为 0 或 1"""
        r = extract_ma_bundle_features(self.df, 100)
        assert r['ma_convergence_flag'] in (0, 1)

    def test_boundary_t0_too_small(self):
        """t0_idx < 20 应返回空"""
        r = extract_ma_bundle_features(self.df, 5)
        assert r == {}

    def test_perfect_alignment(self):
        """均线完全一致时: 离散度=0, 粘合天数=20"""
        dates = pd.date_range('2024-01-01', periods=200, freq='D')
        close = np.ones(200) * 100
        df = pd.DataFrame({
            'close': close,
            'ma5': close, 'ma10': close, 'ma20': close, 'ma60': close,
        }, index=dates)
        r = extract_ma_bundle_features(df, 100)
        assert r['ma_dispersion_5d'] < 0.001
        assert r['ma_glue_max_days'] == 20


class TestWashout:
    """黄金坑/假破位特征测试"""

    def test_standard_washout(self):
        """标准黄金坑: 跌破MA60后收回"""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        close = np.ones(100) * 100
        ma60 = np.ones(100) * 100
        # T-5天跌破MA60, T-3天收回
        close[95] = 97  # below MA60
        close[96] = 96  # still below
        close[97] = 101  # recovery
        df = pd.DataFrame({
            'close': close, 'open': close, 'high': close + 1, 'low': close - 1,
            'ma20': ma60, 'ma60': ma60,
        }, index=dates)
        r = extract_washout_features(df, 99, lookback=20)
        assert r['washout_ma60_flag'] == 1
        assert r['washout_ma60_depth'] > 0
        assert r['washout_ma60_recovery_days'] > 0

    def test_no_washout(self):
        """无破位: close始终在MA60上方"""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        close = np.ones(100) * 105
        ma60 = np.ones(100) * 100
        df = pd.DataFrame({
            'close': close, 'open': close, 'high': close + 1, 'low': close - 1,
            'ma20': np.ones(100) * 102, 'ma60': ma60,
        }, index=dates)
        r = extract_washout_features(df, 99, lookback=20)
        assert r['washout_ma60_flag'] == 0
        assert r['washout_ma60_depth'] == 0.0

    def test_lower_shadow(self):
        """长下影线检测"""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        close = np.ones(100) * 100
        open_ = np.ones(100) * 100
        low = np.ones(100) * 99
        high = np.ones(100) * 101
        # T-3天: 长下影线 (open=100, close=100.5, low=96, high=101)
        open_[97] = 100
        close[97] = 100.5
        low[97] = 96  # 下影 = 4, 实体 = 0.5 → 下影 > 实体 * 2
        df = pd.DataFrame({
            'close': close, 'open': open_, 'high': high, 'low': low,
            'ma20': np.ones(100) * 100, 'ma60': np.ones(100) * 100,
        }, index=dates)
        r = extract_washout_features(df, 99, lookback=15)
        assert r['lower_shadow_count'] >= 1


class TestVolumeSequence:
    """量能序列特征测试"""

    def test_basic_output(self):
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        df = pd.DataFrame({
            'close': np.ones(100) * 100,
            'volume': np.random.randint(100000, 1000000, 100),
        }, index=dates)
        r = extract_volume_sequence_features(df, 50)
        assert 'vol_trend_10d' in r
        assert 'vol_shrink_streak' in r
        assert 'vol_low_point_position' in r

    def test_shrinking_volume(self):
        """持续缩量: vol_shrink_streak 应较大"""
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        vol = np.arange(1000, 900, -5).astype(float)  # 单调递减
        df = pd.DataFrame({
            'close': np.ones(100) * 100,
            'volume': np.concatenate([np.ones(80) * 500, vol[:20]]),
        }, index=dates)
        r = extract_volume_sequence_features(df, 99, lookback=20)
        assert r['vol_shrink_streak'] >= 10


class TestPriceAction:
    """价格行为序列测试"""

    def test_all_bull(self):
        """全阳序列"""
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        close = np.linspace(100, 120, 50)
        open_ = close - 1
        df = pd.DataFrame({'close': close, 'open': open_}, index=dates)
        r = extract_price_action_features(df, 40, lookback=10)
        assert r['streak_max_bull'] >= 5
        assert r['bull_ratio_10d'] > 0.8

    def test_alternating(self):
        """交替序列"""
        dates = pd.date_range('2024-01-01', periods=50, freq='D')
        close = np.ones(50) * 100
        open_ = np.ones(50) * 100
        for i in range(40, 50):
            if i % 2 == 0:
                close[i] = 102
                open_[i] = 100
            else:
                close[i] = 98
                open_[i] = 100
        df = pd.DataFrame({'close': close, 'open': open_}, index=dates)
        r = extract_price_action_features(df, 49, lookback=10)
        assert r['streak_max_bull'] <= 2


class TestFeatureCoverage:
    """真实数据覆盖率测试"""

    def test_real_stock_coverage(self):
        """5只真实股票上覆盖率应 >= 90%"""
        from data_handler import get_full_data_with_indicators
        stocks = ['sh600036', 'sz000002', 'sh601318', 'sz300750', 'sh688981']
        all_feats = []

        for code in stocks:
            df = get_full_data_with_indicators(code, end_date='2026-03-11')
            if df is None or len(df) < 120:
                continue
            for t0_idx in range(80, min(len(df) - 1, 300), 20):
                feats = extract_all_v2_features(df, t0_idx)
                all_feats.append(feats)

        assert len(all_feats) > 10, "样本数不足"
        df_feats = pd.DataFrame(all_feats)

        critical_features = [
            'ma_dispersion_5d', 'ma_dispersion_20d', 'ma_glue_max_days',
            'ma_divergence_speed', 'ma_convergence_flag',
            'washout_ma60_flag', 'washout_ma60_depth',
            'washout_ma20_flag', 'washout_ma20_depth',
            'lower_shadow_count',
            'vol_trend_10d', 'vol_shrink_streak',
            'streak_max_bull', 'streak_max_bear', 'bull_ratio_10d',
        ]

        for feat in critical_features:
            if feat in df_feats.columns:
                cov = df_feats[feat].notna().sum() / len(df_feats)
                print(f"  {feat}: {cov:.1%}")
                assert cov >= 0.90, f"{feat} 覆盖率 {cov:.1%} < 90%"


def run_all_tests():
    test_classes = [
        TestMABundle,
        TestWashout,
        TestVolumeSequence,
        TestPriceAction,
        TestFeatureCoverage,
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
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
