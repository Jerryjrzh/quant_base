"""
复权拟合验证测试
================
核心验证思路：
  1. 读取除权除息记录，定位最近的权息事件
  2. 分别加载：原始日线 / 前复权日线 / 5分钟线(复权后聚合为日线)
  3. 对比除权日前后价格连续性
  4. 对比 5分钟聚合日线 vs 直接复权日线 的拟合精度

用法：
  source .venv/bin/activate && cd backend && python3 test_adjustment_verify.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from data_loader import (
    get_daily_data, get_5min_data,
    _apply_adjustment, _apply_minute_adjustment, _build_paths
)
from gbbq_reader import get_xdxr_for_stock, calc_adjust_factors

TEST_STOCKS = ['600519', '000001', '000858', '600036', '601318']
CLOSE_TOLERANCE = 0.02
SMOOTH_THRESHOLD = 0.05


def load_xdxr_events(stock_code, daily_df, max_events=5):
    """获取日线范围内的除权除息事件，返回最近 N 个"""
    xdxr = get_xdxr_for_stock(stock_code)
    if xdxr.empty:
        return pd.DataFrame()
    events = xdxr[
        (xdxr['date'] >= daily_df.index.min()) &
        (xdxr['date'] <= daily_df.index.max())
    ].copy()
    events = events.sort_values('date').tail(max_events)
    return events


def resample_5min_to_daily(df_5min):
    """将5分钟线聚合为日线"""
    if df_5min is None or df_5min.empty:
        return None
    df = df_5min.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    agg = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    }
    cols = {k: v for k, v in agg.items() if k in df.columns}
    daily = df.resample('1D').agg(cols).dropna(subset=['open'])
    daily = daily[daily['open'] > 0]
    return daily


def check_ex_date_continuity(adj_daily, raw_daily, ex_date):
    """检查除权日前后复权价格的连续性"""
    adj_before = adj_daily[adj_daily.index < ex_date]
    adj_after = adj_daily[adj_daily.index >= ex_date]
    raw_before = raw_daily[raw_daily.index < ex_date]
    raw_after = raw_daily[raw_daily.index >= ex_date]

    if adj_before.empty or adj_after.empty or raw_before.empty or raw_after.empty:
        return None

    adj_close_before = float(adj_before['close'].iloc[-1])
    adj_close_after = float(adj_after['close'].iloc[0])
    raw_close_before = float(raw_before['close'].iloc[-1])
    raw_close_after = float(raw_after['close'].iloc[0])

    adj_change_pct = (adj_close_after - adj_close_before) / adj_close_before
    raw_change_pct = (raw_close_after - raw_close_before) / raw_close_before

    return {
        'ex_date': ex_date.strftime('%Y-%m-%d'),
        'raw_close_before': round(raw_close_before, 2),
        'raw_close_after': round(raw_close_after, 2),
        'raw_change_pct': round(raw_change_pct * 100, 2),
        'adj_close_before': round(adj_close_before, 2),
        'adj_close_after': round(adj_close_after, 2),
        'adj_change_pct': round(adj_change_pct * 100, 2),
        'raw_has_gap': abs(raw_change_pct) > 0.01,
        'adj_is_smooth': abs(adj_change_pct) < SMOOTH_THRESHOLD,
    }


def check_daily_fit(adj_daily, min5_adj_daily, stock_code):
    """对比直接复权日线 vs 5分钟聚合复权日线 的拟合精度"""
    if adj_daily is None or min5_adj_daily is None:
        return None

    common_idx = adj_daily.index.intersection(min5_adj_daily.index)
    if len(common_idx) < 5:
        return None

    adj_c = adj_daily.loc[common_idx, 'close']
    min5_c = min5_adj_daily.loc[common_idx, 'close']

    diff = (adj_c - min5_c).abs()
    rel_diff = diff / adj_c

    return {
        'matched_days': len(common_idx),
        'max_abs_diff': round(float(diff.max()), 4),
        'mean_abs_diff': round(float(diff.mean()), 4),
        'std_abs_diff': round(float(diff.std()), 4),
        'max_rel_diff_pct': round(float(rel_diff.max()) * 100, 4),
        'mean_rel_diff_pct': round(float(rel_diff.mean()) * 100, 4),
        'within_tolerance': bool(diff.max() < CLOSE_TOLERANCE),
    }


def test_stock(stock_code):
    """测试单只股票"""
    print(f"\n{'='*70}")
    print(f"  测试股票: {stock_code}")
    print(f"{'='*70}")

    _, daily_file, min5_file = _build_paths(stock_code)

    if not os.path.exists(daily_file):
        print(f"  [SKIP] 日线文件不存在: {daily_file}")
        return False
    if not os.path.exists(min5_file):
        print(f"  [SKIP] 5分钟线文件不存在: {min5_file}")
        return False

    raw_daily = get_daily_data(daily_file, stock_code)
    adj_daily = _apply_adjustment(raw_daily.copy(), stock_code, 'forward')
    raw_5min = get_5min_data(min5_file)

    if raw_daily is None or raw_daily.empty:
        print("  [SKIP] 日线数据为空")
        return False
    if raw_5min is None or raw_5min.empty:
        print("  [SKIP] 5分钟线数据为空")
        return False

    adj_5min = _apply_minute_adjustment(raw_5min, stock_code, 'forward')
    min5_daily = resample_5min_to_daily(adj_5min)

    events = load_xdxr_events(stock_code, raw_daily, max_events=5)

    all_pass = True

    # ── 测试 1: 除权日前后价格连续性 ──
    print(f"\n  [测试1] 除权除息日前后价格连续性")
    if events.empty:
        print("  (无除权除息记录，跳过)")
    else:
        print(f"  {'除权日':<12} {'原始前收':>10} {'原始后收':>10} {'原始涨跌%':>10} "
              f"{'复权前收':>10} {'复权后收':>10} {'复权涨跌%':>10} {'原始跳空':>8} {'复权平滑':>8}")
        print(f"  {'-'*96}")

        for _, ev in events.iterrows():
            ex_date = ev['date']
            result = check_ex_date_continuity(adj_daily, raw_daily, ex_date)
            if result is None:
                continue

            raw_gap = "YES" if result['raw_has_gap'] else "no"
            adj_smooth = "YES" if result['adj_is_smooth'] else "NO"

            print(f"  {result['ex_date']:<12} "
                  f"{result['raw_close_before']:>10.2f} "
                  f"{result['raw_close_after']:>10.2f} "
                  f"{result['raw_change_pct']:>10.2f} "
                  f"{result['adj_close_before']:>10.2f} "
                  f"{result['adj_close_after']:>10.2f} "
                  f"{result['adj_change_pct']:>10.2f} "
                  f"{raw_gap:>8} {adj_smooth:>8}")

            if not result['adj_is_smooth']:
                all_pass = False

        # 验证原始数据确实存在跳空（证明除权事件真实存在）
        raw_gaps = sum(1 for _, ev in events.iterrows()
                       if check_ex_date_continuity(adj_daily, raw_daily, ev['date'])
                       and check_ex_date_continuity(adj_daily, raw_daily, ev['date'])['raw_has_gap'])
        print(f"\n  原始数据跳空事件: {raw_gaps}/{len(events)} (验证除权事件真实性)")

    # ── 测试 2: 5分钟聚合日线 vs 直接复权日线 拟合精度 ──
    print(f"\n  [测试2] 5分钟聚合日线 vs 直接复权日线 拟合精度")
    fit = check_daily_fit(adj_daily, min5_daily, stock_code)
    if fit is None:
        print("  (重叠天数不足，跳过)")
    else:
        print(f"  重叠交易日: {fit['matched_days']}")
        print(f"  最大绝对误差: {fit['max_abs_diff']:.4f}")
        print(f"  平均绝对误差: {fit['mean_abs_diff']:.4f}")
        print(f"  标准差:       {fit['std_abs_diff']:.4f}")
        print(f"  最大相对误差: {fit['max_rel_diff_pct']:.4f}%")
        print(f"  平均相对误差: {fit['mean_rel_diff_pct']:.4f}%")

        if fit['within_tolerance']:
            print(f"  拟合判定: PASS (误差 < {CLOSE_TOLERANCE})")
        else:
            print(f"  拟合判定: FAIL (误差 >= {CLOSE_TOLERANCE})")
            all_pass = False

    # ── 测试 3: 未复权5分钟聚合 vs 未复权日线 对比（基线检查）──
    print(f"\n  [测试3] 未复权5分钟聚合 vs 未复权日线 (基线)")
    raw_5min_daily = resample_5min_to_daily(raw_5min)
    baseline = check_daily_fit(raw_daily, raw_5min_daily, stock_code)
    if baseline:
        print(f"  最大绝对误差: {baseline['max_abs_diff']:.4f}")
        print(f"  平均绝对误差: {baseline['mean_abs_diff']:.4f}")
        if baseline['within_tolerance']:
            print(f"  基线判定: PASS")
        else:
            print(f"  基线判定: FAIL")
            all_pass = False

    return all_pass


def main():
    print("=" * 70)
    print("  复权拟合验证测试")
    print("  验证: 5分钟线复权聚合 → 日线 vs 直接复权日线 价格一致性")
    print("=" * 70)

    results = {}
    for code in TEST_STOCKS:
        try:
            results[code] = test_stock(code)
        except Exception as e:
            print(f"\n  [ERROR] {code}: {e}")
            import traceback
            traceback.print_exc()
            results[code] = False

    # ── 汇总 ──
    print(f"\n\n{'='*70}")
    print(f"  汇总报告")
    print(f"{'='*70}")
    print(f"  {'股票':<10} {'结果':<8}")
    print(f"  {'-'*18}")

    all_pass = True
    for code, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {code:<10} {status:<8}")
        if not passed:
            all_pass = False

    print(f"\n  最终结论: {'ALL PASS' if all_pass else 'HAS FAILURES'}")
    print(f"{'='*70}")

    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
