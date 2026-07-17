"""
Phase 2 测试: 全市场排名序列特征
运行: cd backend && python3 test_super_trend/test_market_ranker.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from super_trend_market_ranker import (
    build_market_rank_cache,
    get_stock_rank_series,
    extract_rank_features,
)


class TestMarketRankCache:
    """排名缓存构建测试"""

    @classmethod
    def setup_class(cls):
        cls.rank_matrix = build_market_rank_cache(end_date='2026-03-11')

    def test_cache_shape(self):
        """缓存应有合理的行(天)和列(股票)数"""
        assert self.rank_matrix.shape[0] > 1000, f"天数不足: {self.rank_matrix.shape[0]}"
        assert self.rank_matrix.shape[1] > 3000, f"股票数不足: {self.rank_matrix.shape[1]}"
        print(f"  shape: {self.rank_matrix.shape}")

    def test_rank_range(self):
        """排名值应在 (0, 1] 范围内"""
        sample = self.rank_matrix.iloc[-100:].dropna(how='all')
        valid = sample.values[~np.isnan(sample.values)]
        assert np.all(valid > 0) and np.all(valid <= 1.0), "排名值超出 (0,1] 范围"

    def test_rank_mean_near_half(self):
        """每日排名均值应接近 0.5"""
        daily_mean = self.rank_matrix.iloc[-100:].mean(axis=1)
        assert abs(daily_mean.mean() - 0.5) < 0.05, f"排名均值偏离: {daily_mean.mean()}"


class TestRankSeries:
    """排名序列提取测试"""

    @classmethod
    def setup_class(cls):
        cls.rank_matrix = build_market_rank_cache(end_date='2026-03-11')

    def test_known_stock(self):
        """sh600036 应有排名数据"""
        ranks = get_stock_rank_series(self.rank_matrix, 'sh600036', '2024-06-15', lookback=20)
        assert len(ranks) >= 10, f"排名序列过短: {len(ranks)}"
        assert np.all(ranks > 0) and np.all(ranks <= 1.0)

    def test_unknown_stock(self):
        """不存在的股票应返回空数组"""
        ranks = get_stock_rank_series(self.rank_matrix, 'xx999999', '2024-06-15')
        assert len(ranks) == 0


class TestRankFeatures:
    """排名特征提取测试"""

    @classmethod
    def setup_class(cls):
        cls.rank_matrix = build_market_rank_cache(end_date='2026-03-11')

    def test_feature_keys(self):
        """应返回所有预期特征键"""
        feats = extract_rank_features(self.rank_matrix, 'sh600036', '2024-06-15')
        expected = ['rs_rank_mean_5d', 'rs_rank_mean_10d', 'rs_rank_mean_20d',
                     'rs_rank_trend_20d', 'rs_rank_std_10d']
        for k in expected:
            assert k in feats, f"缺少特征: {k}"

    def test_feature_values_range(self):
        """特征值应在合理范围"""
        feats = extract_rank_features(self.rank_matrix, 'sh600036', '2024-06-15')
        for k in ['rs_rank_mean_5d', 'rs_rank_mean_10d', 'rs_rank_mean_20d']:
            assert 0 < feats[k] <= 1.0, f"{k} 值异常: {feats[k]}"
        assert feats['rs_rank_std_10d'] >= 0, "标准差应为非负"

    def test_multiple_stocks(self):
        """多只股票的特征应各不相同"""
        stocks = ['sh600036', 'sz000002', 'sh601318']
        results = {}
        for code in stocks:
            results[code] = extract_rank_features(self.rank_matrix, code, '2024-06-15')
        vals = [results[c].get('rs_rank_mean_10d', 0) for c in stocks]
        assert len(set([round(v, 3) for v in vals])) > 1, "不同股票的排名特征应不同"


class TestScannerIntegration:
    """扫描器集成测试"""

    def test_scanner_produces_rank_features(self):
        """扫描器应产出排名特征"""
        from super_trend_scanner_v1_grok import scan_and_build_episodes, _load_market_index

        rank_matrix = build_market_rank_cache(end_date='2026-03-11')
        df_market = _load_market_index('sh000001', end_date='2026-03-11')

        candidates, collection = scan_and_build_episodes(
            'sh600036', end_date='2026-03-11',
            df_market=df_market, rank_matrix=rank_matrix,
        )

        assert len(collection.episodes) > 0, "无 Episode 生成"

        rank_key = 'rs_rank_mean_10d'
        has_rank = sum(1 for ep in collection.episodes if rank_key in ep.features)
        total = len(collection.episodes)
        coverage = has_rank / total
        print(f"  排名特征覆盖率: {has_rank}/{total} ({coverage:.1%})")
        assert coverage >= 0.90, f"覆盖率过低: {coverage:.1%}"


def run_all_tests():
    test_classes = [
        TestMarketRankCache,
        TestRankSeries,
        TestRankFeatures,
        TestScannerIntegration,
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
