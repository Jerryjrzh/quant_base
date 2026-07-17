"""
Super Trend V1 Phase 2: 全市场日涨幅排名序列特征
计算每只股票在全市场中的每日涨幅排名百分位，提取排名序列特征。
"""

import os
import glob
import pandas as pd
import numpy as np
import pickle
import time
from scipy.stats import linregress
import warnings
warnings.filterwarnings('ignore')


CACHE_DIR = os.path.join("data", "result", "super_trend", "cache")
RANK_CACHE_FILE = os.path.join(CACHE_DIR, "market_daily_rank.pkl")
os.makedirs(CACHE_DIR, exist_ok=True)


def _get_vipdoc_base():
    return os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")


def _load_all_stock_closes(max_stocks=None):
    """
    加载全市场股票日线 close 数据（仅原始数据，不计算指标）。

    返回:
        dict: {stock_code: pd.Series(close, index=DatetimeIndex)}
    """
    from data_handler import read_day_file

    vipdoc_base = _get_vipdoc_base()
    all_files = (
        glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day"))
        + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    )

    allowed_prefixes = ('sh60', 'sh68', 'sz00', 'sz30')
    filtered = []
    for f in all_files:
        code = os.path.basename(f).replace('.day', '')
        if any(code.startswith(p) for p in allowed_prefixes):
            filtered.append((code, f))

    if max_stocks:
        filtered = filtered[:max_stocks]

    print(f"  加载 {len(filtered)} 只股票的 close 数据...")
    closes = {}
    errors = 0
    for code, filepath in filtered:
        try:
            df = read_day_file(filepath, code)
            if df is not None and len(df) > 50:
                closes[code] = df['close']
        except Exception:
            errors += 1

    print(f"  成功加载: {len(closes)}, 失败: {errors}")
    return closes


def build_market_rank_cache(end_date=None, force_rebuild=False):
    """
    构建全市场日涨幅排名缓存。

    对每个交易日，计算所有股票的日涨幅百分位排名 (0~1)。
    结果保存为 pickle: {(date_str, stock_code): rank_percentile}

    返回:
        pd.DataFrame: index=date, columns=stock_code, values=rank_percentile
    """
    if os.path.exists(RANK_CACHE_FILE) and not force_rebuild:
        print(f"  加载已有缓存: {RANK_CACHE_FILE}")
        with open(RANK_CACHE_FILE, 'rb') as f:
            return pickle.load(f)

    print("=== 构建全市场排名缓存 ===")
    t0 = time.time()

    closes = _load_all_stock_closes()
    if not closes:
        raise ValueError("无法加载任何股票数据")

    all_dates = set()
    for s in closes.values():
        all_dates.update(s.index)
    all_dates = sorted(all_dates)

    if end_date:
        end_ts = pd.Timestamp(end_date)
        all_dates = [d for d in all_dates if d <= end_ts]

    print(f"  日期范围: {all_dates[0]} ~ {all_dates[-1]}, 共 {len(all_dates)} 天")
    print(f"  股票数: {len(closes)}")

    close_matrix = pd.DataFrame(index=all_dates, columns=list(closes.keys()), dtype=float)
    for code, series in closes.items():
        close_matrix[code] = series

    print("  计算日涨幅...")
    returns = close_matrix.pct_change()

    print("  计算每日百分位排名...")
    rank_matrix = returns.rank(axis=1, pct=True, na_option='keep')

    rank_matrix.to_pickle(RANK_CACHE_FILE)
    t1 = time.time()
    print(f"  缓存已保存: {RANK_CACHE_FILE}")
    print(f"  耗时: {t1-t0:.1f}s, 文件大小: {os.path.getsize(RANK_CACHE_FILE)/1024/1024:.0f}MB")

    return rank_matrix


def get_stock_rank_series(rank_matrix, stock_code, t0_date, lookback=30):
    """
    获取某只股票在 T0 前 lookback 天的每日排名序列。

    参数:
        rank_matrix: build_market_rank_cache() 返回的排名矩阵
        stock_code: 股票代码
        t0_date: T0 日期
        lookback: 回溯天数

    返回:
        np.array: 排名百分位序列 (0~1), 长度最多 lookback
    """
    if stock_code not in rank_matrix.columns:
        return np.array([])

    t0_ts = pd.Timestamp(t0_date)
    dates = rank_matrix.index
    t0_pos = dates.searchsorted(t0_ts)
    if t0_pos >= len(dates):
        t0_pos = len(dates) - 1

    start_pos = max(0, t0_pos - lookback)
    series = rank_matrix.iloc[start_pos:t0_pos][stock_code].values
    return series[~np.isnan(series)]


def extract_rank_features(rank_matrix, stock_code, t0_date):
    """
    从全市场排名矩阵中提取个股排名序列特征。

    参数:
        rank_matrix: 全市场排名矩阵
        stock_code: 股票代码
        t0_date: T0 日期

    返回:
        dict:
          rs_rank_mean_5d: T0前5天排名均值
          rs_rank_mean_10d: T0前10天排名均值
          rs_rank_mean_20d: T0前20天排名均值
          rs_rank_trend_20d: T0前20天排名的线性回归斜率
          rs_rank_std_10d: T0前10天排名标准差 (稳定性)
    """
    features = {}

    ranks_20 = get_stock_rank_series(rank_matrix, stock_code, t0_date, lookback=20)
    if len(ranks_20) < 5:
        return features

    if len(ranks_20) >= 5:
        features['rs_rank_mean_5d'] = float(np.mean(ranks_20[-5:]))
    if len(ranks_20) >= 10:
        features['rs_rank_mean_10d'] = float(np.mean(ranks_20[-10:]))
        features['rs_rank_std_10d'] = float(np.std(ranks_20[-10:]))
    if len(ranks_20) >= 15:
        features['rs_rank_mean_20d'] = float(np.mean(ranks_20))

    if len(ranks_20) >= 10:
        indices = np.arange(len(ranks_20))
        slope, _, _, _, _ = linregress(indices, ranks_20)
        features['rs_rank_trend_20d'] = float(slope)

    return features


def test_market_ranker():
    """快速测试"""
    print("=== 全市场排名测试 ===")

    rank_matrix = build_market_rank_cache(end_date='2026-03-11')
    print(f"\n排名矩阵: {rank_matrix.shape}")
    print(f"日期范围: {rank_matrix.index[0]} ~ {rank_matrix.index[-1]}")

    test_stocks = ['sh600036', 'sz000002', 'sh601318']
    test_date = '2024-06-15'

    for code in test_stocks:
        ranks = get_stock_rank_series(rank_matrix, code, test_date, lookback=10)
        print(f"\n{code} ({test_date} 前10天排名):")
        print(f"  序列: {np.round(ranks, 3)}")
        feats = extract_rank_features(rank_matrix, code, test_date)
        for k, v in feats.items():
            print(f"  {k}: {v:.4f}")


if __name__ == "__main__":
    test_market_ranker()
