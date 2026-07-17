"""
Phase 5: 端到端回测框架测试
验证 RankBacktester 的交易模拟、统计计算和基准对比
"""

import pytest
import pandas as pd
import numpy as np
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from super_trend_rank_backtester import (
    RankBacktester, COMMISSION, STOP_LOSS, TAKE_PROFIT, HOLDING_DAYS, TOP_N
)


# ── 常量验证 ──

def test_constants():
    """交易参数常量验证"""
    assert COMMISSION == 0.0015
    assert STOP_LOSS == -0.08
    assert TAKE_PROFIT == 0.30
    assert HOLDING_DAYS == 22
    assert TOP_N == 20


# ── 交易模拟 ──

def test_simulate_trade_stop_loss():
    """MAE 触及止损线时，收益为 STOP_LOSS * 0.8"""
    bt = RankBacktester()
    ret = bt._simulate_trade(future_mfe=0.05, future_mae=-0.10)
    assert ret == pytest.approx(STOP_LOSS * 0.8, abs=1e-6)
    assert ret < 0


def test_simulate_trade_take_profit():
    """MFE 触及止盈线时，收益为 TAKE_PROFIT * 0.85"""
    bt = RankBacktester()
    ret = bt._simulate_trade(future_mfe=0.35, future_mae=-0.02)
    assert ret == pytest.approx(TAKE_PROFIT * 0.85, abs=1e-6)


def test_simulate_trade_hold():
    """未触及止损/止盈时，收益 = MFE * 0.5 捕获率"""
    bt = RankBacktester()
    mfe = 0.15
    ret = bt._simulate_trade(future_mfe=mfe, future_mae=-0.03)
    assert ret == pytest.approx(mfe * 0.5, abs=1e-6)


def test_simulate_trade_edge_cases():
    """边界情况: MFE=0, MAE=0"""
    bt = RankBacktester()
    ret = bt._simulate_trade(0, 0)
    assert ret == 0.0


def test_simulate_trade_stop_loss_priority():
    """同时触及止损和止盈时，止损优先（因为先检查 MAE）"""
    bt = RankBacktester()
    ret = bt._simulate_trade(future_mfe=0.40, future_mae=-0.10)
    assert ret == pytest.approx(STOP_LOSS * 0.8, abs=1e-6)


# ── 统计计算 ──

def _build_mock_backtester(n_trades=100, avg_return=0.05):
    """构造带模拟交易数据的 backtester"""
    bt = RankBacktester()

    dates = pd.date_range('2025-01-01', periods=20, freq='B')
    trades = []
    daily_pnl = []
    trades_per_day = n_trades // len(dates)

    for i, d in enumerate(dates):
        day_returns = np.random.normal(avg_return, 0.02, trades_per_day)
        for j, r in enumerate(day_returns):
            trades.append({
                'date': d,
                'stock_code': f'S{i:03d}',
                'score': 1.0 - j * 0.01,
                'future_mfe': r + 0.05,
                'future_mae': -0.02,
                'simulated_return': r,
                'net_return': r - 2 * COMMISSION,
                'filtered_gap': False,
            })
        day_avg = day_returns.mean() - 2 * COMMISSION
        daily_pnl.append({
            'date': d,
            'n_stocks': trades_per_day,
            'avg_return': day_avg,
            'total_return': day_avg * trades_per_day,
        })

    bt.trades = pd.DataFrame(trades)
    bt.daily_pnl = pd.DataFrame(daily_pnl)
    return bt


def test_compute_stats_basic():
    """基础统计字段完整性"""
    bt = _build_mock_backtester(n_trades=100, avg_return=0.05)
    stats = bt._compute_stats()

    required_keys = [
        'total_trades', 'trading_days', 'total_return',
        'annualized_return', 'sharpe_ratio', 'max_drawdown',
        'win_rate', 'avg_trade_return', 'avg_future_mfe',
        'avg_daily_stocks',
    ]
    for k in required_keys:
        assert k in stats, f"缺少统计字段: {k}"


def test_compute_stats_win_rate():
    """胜率在合理范围"""
    bt = _build_mock_backtester(n_trades=200, avg_return=0.05)
    stats = bt._compute_stats()
    assert 0.5 < stats['win_rate'] < 1.0


def test_compute_stats_positive_return():
    """正平均收益 → 正总收益和正年化"""
    bt = _build_mock_backtester(n_trades=200, avg_return=0.08)
    stats = bt._compute_stats()
    assert stats['total_return'] > 0
    assert stats['annualized_return'] > 0
    assert stats['sharpe_ratio'] > 0


def test_compute_stats_max_drawdown_non_positive():
    """最大回撤 ≤ 0"""
    bt = _build_mock_backtester(n_trades=100, avg_return=0.03)
    stats = bt._compute_stats()
    assert stats['max_drawdown'] <= 0


def test_compute_stats_empty():
    """空交易记录返回 error"""
    bt = RankBacktester()
    bt.trades = pd.DataFrame()
    bt.daily_pnl = pd.DataFrame()
    stats = bt._compute_stats()
    assert 'error' in stats


# ── 基准对比 ──

def test_compare_with_baseline():
    """基准对比不报错"""
    bt = _build_mock_backtester(n_trades=100, avg_return=0.05)
    bt._test_df = pd.DataFrame({
        'future_mfe': np.random.uniform(0.05, 0.20, 100),
    })
    bt.compare_with_baseline()


# ── 集成测试（需要训练数据）──

@pytest.fixture
def v2_data_path():
    from super_trend_rank_backtester import _proj
    path = _proj("data", "result", "super_trend", "super_trend_training_data_v2.csv")
    if not os.path.exists(path):
        pytest.skip("V2 训练数据不存在")
    return path


def test_quick_train_and_predict(v2_data_path):
    """快速训练 → 预测 → 回测完整流水线"""
    bt = RankBacktester(training_data_path=v2_data_path)
    assert bt._train_quick_model()
    assert bt.ranker is not None
    assert bt.ranker.model is not None

    test_df = bt._test_df
    assert len(test_df) > 0
    assert 't0_date' in test_df.columns

    feature_cols = bt.ranker.feature_columns
    available = [c for c in feature_cols if c in test_df.columns]
    assert len(available) > 0

    scores = bt.ranker.model.predict(test_df[available].fillna(0))
    assert len(scores) == len(test_df)
    assert not np.any(np.isnan(scores))


def test_full_backtest_run(v2_data_path):
    """端到端回测完整运行"""
    bt = RankBacktester(training_data_path=v2_data_path)
    results = bt.run(top_n=10)

    assert results is not None
    assert 'error' not in results
    assert results['total_trades'] > 0
    assert results['trading_days'] > 0
    assert results['win_rate'] > 0
    assert len(bt.trades) > 0
    assert len(bt.daily_pnl) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
