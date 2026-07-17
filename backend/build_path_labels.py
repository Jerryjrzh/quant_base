#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 1: 生成未来22天价格路径标签 (KMeans 三分类)

特征:
  - max_drawdown: 22天内从峰值到谷底的最大回撤
  - trend_smoothness: 收盘价线性拟合的 R² (趋势顺滑度)

输出:
  - doc/0613_super_trend_v2/path_labels.csv
  - doc/0613_super_trend_v2/path_labels_report.md
"""

import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

# 兼容放在 scripts/ 或 backend/ 下
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_SCRIPT_DIR) == 'backend':
    _BACKEND_DIR = _SCRIPT_DIR
    _PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
else:
    _PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
    _BACKEND_DIR = os.path.join(_PROJECT_ROOT, 'backend')
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pandas as pd
import numpy as np
from sklearn.cluster import KMeans

import data_loader

DOC_DIR = os.path.join(_PROJECT_ROOT, 'doc', '0613_super_trend_v2')
REVIEW4_CSV = os.path.join(DOC_DIR, 'review4_final_backtest.csv')
OUTPUT_CSV = os.path.join(DOC_DIR, 'path_labels.csv')
OUTPUT_MD = os.path.join(DOC_DIR, 'path_labels_report.md')

FUTURE_DAYS = 22
MIN_BARS = 15
# 22 个交易日 ≈ 30-32 日历天，放宽到 45 天保证覆盖
FUTURE_CALENDAR_DAYS = 45


def _aggregate_60m_to_daily(df_60m: pd.DataFrame) -> pd.DataFrame:
    """将 60m bar 按日期聚合为日线 OHLCV"""
    if df_60m is None or df_60m.empty:
        return pd.DataFrame()
    df = df_60m.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns:
            df = df.set_index(pd.to_datetime(df['datetime']))
        elif 'date' in df.columns:
            df = df.set_index(pd.to_datetime(df['date']))
        else:
            df.index = pd.to_datetime(df.index, errors='coerce')
    df = df.dropna(subset=['open'])
    df['date_key'] = df.index.normalize()
    grouped = df.groupby('date_key').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
    })
    return grouped.sort_index()


def _load_daily_via_60m(stock: str, start_date, end_date) -> pd.DataFrame:
    """通过 60m 数据聚合得到日线 (规避 get_daily_data 参数 bug)"""
    start = pd.to_datetime(start_date).strftime('%Y-%m-%d')
    end = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    try:
        df_60m = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        return pd.DataFrame()
    return _aggregate_60m_to_daily(df_60m)


def compute_path_metrics(close: np.ndarray, high: np.ndarray):
    """计算 max_drawdown 和 trend_smoothness (R²)"""
    peak = np.maximum.accumulate(high)
    dd = (peak - high) / peak
    max_dd = float(np.max(dd))

    x = np.arange(len(close), dtype=float)
    y = np.log(close)
    slope, intercept = np.polyfit(x, y, 1)
    y_pred = slope * x + intercept
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    # R² 可能因单调下降而为负，截断到 0
    r2 = max(r2, 0.0)
    return max_dd, float(r2), float(slope)


def run_label_generation():
    print("=" * 60)
    print("  Step 1: 生成未来22天路径标签")
    print("=" * 60)

    df = pd.read_csv(REVIEW4_CSV)
    df['t0_date'] = pd.to_datetime(df['t0_date'])
    print(f"  加载信号: {len(df)} 笔")

    t0 = time.time()
    results = []
    n_ok = 0
    n_short = 0
    n_no_data = 0

    for i, (idx, row) in enumerate(df.iterrows()):
        if (i + 1) % 200 == 0 or i == 0:
            print(f"  处理 {i + 1}/{len(df)} ...")
        stock = row['stock_code']
        t0_date = row['t0_date']
        start = (t0_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        end = (t0_date + pd.Timedelta(days=FUTURE_CALENDAR_DAYS)).strftime('%Y-%m-%d')

        daily = _load_daily_via_60m(stock, start, end)

        if daily is None or daily.empty:
            n_no_data += 1
            results.append({
                'signal_idx': idx,
                'stock_code': stock,
                't0_date': t0_date,
                'status': row.get('status', ''),
                'max_drawdown': np.nan,
                'trend_smoothness': np.nan,
                'trend_slope': np.nan,
                'n_future_bars': 0,
                'final_return': np.nan,
            })
            continue

        daily = daily.head(FUTURE_DAYS)
        if len(daily) < MIN_BARS:
            n_short += 1
            results.append({
                'signal_idx': idx,
                'stock_code': stock,
                't0_date': t0_date,
                'status': row.get('status', ''),
                'max_drawdown': np.nan,
                'trend_smoothness': np.nan,
                'trend_slope': np.nan,
                'n_future_bars': len(daily),
                'final_return': np.nan,
            })
            continue

        close = daily['close'].values.astype(float)
        high = daily['high'].values.astype(float)
        max_dd, r2, slope = compute_path_metrics(close, high)
        final_ret = (close[-1] / close[0] - 1) if close[0] > 0 else np.nan

        results.append({
            'signal_idx': idx,
            'stock_code': stock,
            't0_date': t0_date,
            'status': row.get('status', ''),
            'max_drawdown': max_dd,
            'trend_smoothness': r2,
            'trend_slope': slope,
            'n_future_bars': len(daily),
            'final_return': final_ret,
        })
        n_ok += 1

    elapsed = time.time() - t0
    metrics_df = pd.DataFrame(results)
    print(f"\n  完成，耗时 {elapsed:.1f}s")
    print(f"  成功: {n_ok}, 数据不足: {n_short}, 无数据: {n_no_data}")

    valid = metrics_df.dropna(subset=['max_drawdown', 'trend_smoothness']).copy()
    if len(valid) < 30:
        print("  样本过少，无法聚类，退出")
        metrics_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
        return

    # ---- KMeans 聚类 ----
    X = valid[['max_drawdown', 'trend_smoothness']].values
    km = KMeans(n_clusters=3, random_state=42, n_init=10)
    raw_labels = km.fit_predict(X)
    valid['raw_cluster'] = raw_labels

    # 分析每个 cluster 的统计，映射到业务标签 (0=Smooth, 1=Pullback, 2=Failure)
    stats = []
    for k in range(3):
        sub = valid[valid['raw_cluster'] == k]
        stats.append({
            'cluster': k,
            'n': len(sub),
            'avg_dd': sub['max_drawdown'].mean(),
            'avg_r2': sub['trend_smoothness'].mean(),
            'avg_ret': sub['final_return'].mean(),
        })
    stats_df = pd.DataFrame(stats).sort_values(['avg_dd', 'avg_r2'], ascending=[True, False])
    # Smooth: 最低回撤 + 最高R² (排序后第一行)
    # Pullback: 中等
    # Failure: 最高回撤或最低R² (排序后最后一行)
    mapping = {
        stats_df.iloc[0]['cluster']: 0,  # Smooth
        stats_df.iloc[1]['cluster']: 1,  # Pullback
        stats_df.iloc[2]['cluster']: 2,  # Failure
    }
    valid['path_label'] = valid['raw_cluster'].map(mapping)
    label_names = {0: 'Smooth', 1: 'Pullback', 2: 'Failure'}
    valid['path_label_name'] = valid['path_label'].map(label_names)

    print("\n  聚类统计:")
    for _, s in stats_df.iterrows():
        k = int(s['cluster'])
        biz = label_names[mapping[k]]
        print(f"    cluster {k} -> {biz}: n={int(s['n'])}, "
              f"avg_dd={s['avg_dd']:.3f}, avg_r2={s['avg_r2']:.3f}, avg_ret={s['avg_ret']:.4f}")

    # 合并回全量
    metrics_df = metrics_df.merge(
        valid[['signal_idx', 'raw_cluster', 'path_label', 'path_label_name']],
        on='signal_idx', how='left'
    )
    metrics_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"  已保存 {OUTPUT_CSV}")

    generate_report(metrics_df, valid, stats_df, mapping, elapsed,
                    n_ok, n_short, n_no_data)


def generate_report(metrics_df, valid, stats_df, mapping, elapsed,
                    n_ok, n_short, n_no_data):
    lines = []
    lines.append("# 路径标签生成报告 (Step 1)\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append(f"**耗时**: {elapsed:.1f}s\n")
    lines.append(f"**方法**: KMeans(k=3) 对 (max_drawdown, trend_smoothness) 聚类\n")
    lines.append("")

    lines.append("## 一、数据覆盖\n")
    lines.append("| 维度 | 数量 |")
    lines.append("|------|------|")
    lines.append(f"| 总信号 | {len(metrics_df)} |")
    lines.append(f"| 成功计算路径 | {n_ok} |")
    lines.append(f"| 数据不足 (<{MIN_BARS}天) | {n_short} |")
    lines.append(f"| 无日线数据 | {n_no_data} |")
    lines.append("")

    lines.append("## 二、聚类原始统计\n")
    lines.append("| cluster | n | avg max_dd | avg R² | avg final_return | 业务映射 |")
    lines.append("|---------|---|-----------|--------|------------------|----------|")
    label_names = {0: 'Smooth', 1: 'Pullback', 2: 'Failure'}
    for _, s in stats_df.iterrows():
        k = int(s['cluster'])
        biz = label_names[mapping[k]]
        lines.append(f"| {k} | {int(s['n'])} | {s['avg_dd']:.3f} | "
                     f"{s['avg_r2']:.3f} | {s['avg_ret']:.4f} | **{biz}** |")
    lines.append("")

    lines.append("## 三、业务标签分布\n")
    lines.append("| 路径 | n | 占比 | avg max_dd | avg R² | avg final_return |")
    lines.append("|------|---|------|-----------|--------|------------------|")
    for lbl in [0, 1, 2]:
        sub = valid[valid['path_label'] == lbl]
        if len(sub) == 0:
            continue
        lines.append(f"| {label_names[lbl]} | {len(sub)} | "
                     f"{len(sub)/len(valid):.1%} | {sub['max_drawdown'].mean():.3f} | "
                     f"{sub['trend_smoothness'].mean():.3f} | "
                     f"{sub['final_return'].mean():.4f} |")
    lines.append("")

    # 按 status 分层
    lines.append("## 四、按信号状态分层\n")
    lines.append("| status | 总数 | Smooth | Pullback | Failure |")
    lines.append("|--------|------|--------|----------|---------|")
    for st, grp in valid.groupby('status'):
        n = len(grp)
        s = (grp['path_label'] == 0).sum()
        p = (grp['path_label'] == 1).sum()
        f = (grp['path_label'] == 2).sum()
        lines.append(f"| {st} | {n} | {s} | {p} | {f} |")
    lines.append("")

    # traded 信号的 PnL 与路径标签关系
    traded = valid[valid['status'] == 'traded']
    lines.append("## 五、traded 信号的路径与 PnL 关系\n")
    if len(traded) > 0:
        lines.append(f"traded 且可计算路径: {len(traded)}\n")
        lines.append("| 路径 | n | 占比 | avg final_return | 胜率 (final_return>0) |")
        lines.append("|------|---|------|------------------|----------------------|")
        for lbl in [0, 1, 2]:
            sub = traded[traded['path_label'] == lbl]
            if len(sub) == 0:
                continue
            lines.append(f"| {label_names[lbl]} | {len(sub)} | "
                         f"{len(sub)/len(traded):.1%} | {sub['final_return'].mean():.4f} | "
                         f"{(sub['final_return']>0).mean():.1%} |")
    lines.append("")

    lines.append("## 六、结论\n")
    if len(traded) > 0:
        smooth_ret = traded[traded['path_label']==0]['final_return'].mean()
        fail_ret = traded[traded['path_label']==2]['final_return'].mean()
        if pd.notna(smooth_ret) and pd.notna(fail_ret):
            lines.append(f"- Smooth 类 traded 信号 avg final_return: {smooth_ret:.4f}")
            lines.append(f"- Failure 类 traded 信号 avg final_return: {fail_ret:.4f}")
            if smooth_ret > fail_ret:
                lines.append("- [PASS] 路径标签有区分度 (Smooth > Failure)")
            else:
                lines.append("- [FAIL] 路径标签区分度不足")
    lines.append("")
    lines.append("**下一步**: 用这些标签作为目标，训练小时线特征分类器 (Step 2+3)。")

    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"  已写入 {OUTPUT_MD}")


if __name__ == '__main__':
    run_label_generation()
