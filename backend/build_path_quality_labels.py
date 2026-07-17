#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 1 (v4.1): 构建路径质量标签 (连续值 path_quality)

公式:
  mfe = (future_high.max() / future_open[0]) - 1
  max_dd = max(cummax(high) - high) / cummax(high)
  path_quality = (1 + mfe) / (1 + max_dd) - 1

输出:
  - doc/0613_super_trend_v2/path_quality_labels.csv
  - doc/0613_super_trend_v2/path_quality_labels_report.md
"""

import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

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

import data_loader

DOC_DIR = os.path.join(_PROJECT_ROOT, 'doc', '0613_super_trend_v2')
REVIEW4_CSV = os.path.join(DOC_DIR, 'review4_final_backtest.csv')
OUTPUT_CSV = os.path.join(DOC_DIR, 'path_quality_labels.csv')
OUTPUT_MD = os.path.join(DOC_DIR, 'path_quality_labels_report.md')

FUTURE_DAYS = 22
MIN_BARS = 15
FUTURE_CALENDAR_DAYS = 45


def _aggregate_60m_to_daily(df_60m: pd.DataFrame) -> pd.DataFrame:
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
    start = pd.to_datetime(start_date).strftime('%Y-%m-%d')
    end = pd.to_datetime(end_date).strftime('%Y-%m-%d')
    try:
        df_60m = data_loader.get_min_data_in_range(stock, '60m', start, end)
    except Exception:
        return pd.DataFrame()
    return _aggregate_60m_to_daily(df_60m)


def compute_path_quality_metrics(open_arr: np.ndarray, high: np.ndarray,
                                  close: np.ndarray):
    """计算 MFE, max_drawdown, path_quality"""
    peak = np.maximum.accumulate(high)
    dd = (peak - high) / peak
    max_dd = float(np.max(dd))

    mfe = float(high.max() / open_arr[0] - 1) if open_arr[0] > 0 else 0.0

    pq = (1 + mfe) / (1 + max_dd) - 1

    final_ret = float(close[-1] / open_arr[0] - 1) if open_arr[0] > 0 else np.nan

    return max_dd, mfe, pq, final_ret


def run():
    print("=" * 60)
    print("  Task 1 (v4.1): 构建路径质量标签")
    print("  path_quality = (1+MFE)/(1+max_DD) - 1")
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
                'mfe': np.nan,
                'path_quality': np.nan,
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
                'mfe': np.nan,
                'path_quality': np.nan,
                'n_future_bars': len(daily),
                'final_return': np.nan,
            })
            continue

        open_arr = daily['open'].values.astype(float)
        high = daily['high'].values.astype(float)
        close = daily['close'].values.astype(float)
        max_dd, mfe, pq, final_ret = compute_path_quality_metrics(open_arr, high, close)

        results.append({
            'signal_idx': idx,
            'stock_code': stock,
            't0_date': t0_date,
            'status': row.get('status', ''),
            'max_drawdown': max_dd,
            'mfe': mfe,
            'path_quality': pq,
            'n_future_bars': len(daily),
            'final_return': final_ret,
        })
        n_ok += 1

    elapsed = time.time() - t0
    metrics_df = pd.DataFrame(results)
    print(f"\n  完成，耗时 {elapsed:.1f}s")
    print(f"  成功: {n_ok}, 数据不足: {n_short}, 无数据: {n_no_data}")

    metrics_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"  已保存 {OUTPUT_CSV}")

    # 合并 review4 的 PnL 数据用于报告
    base = pd.read_csv(REVIEW4_CSV)
    if 'total_pnl_pct' in base.columns:
        metrics_df = metrics_df.merge(
            base[['total_pnl_pct']].rename_axis('signal_idx').reset_index(),
            on='signal_idx', how='left'
        )

    generate_report(metrics_df, elapsed, n_ok, n_short, n_no_data)


def generate_report(metrics_df, elapsed, n_ok, n_short, n_no_data):
    valid = metrics_df.dropna(subset=['path_quality']).copy()
    lines = []
    lines.append("# 路径质量标签报告 (v4.1 Task 1)\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append(f"**耗时**: {elapsed:.1f}s\n")
    lines.append(f"**公式**: `path_quality = (1+MFE)/(1+max_DD) - 1`\n")
    lines.append("")

    lines.append("## 一、数据覆盖\n")
    lines.append("| 维度 | 数量 |")
    lines.append("|------|------|")
    lines.append(f"| 总信号 | {len(metrics_df)} |")
    lines.append(f"| 成功计算 | {n_ok} |")
    lines.append(f"| 数据不足 (<{MIN_BARS}天) | {n_short} |")
    lines.append(f"| 无数据 | {n_no_data} |")
    lines.append("")

    lines.append("## 二、path_quality 分布\n")
    if len(valid) > 0:
        pq = valid['path_quality']
        lines.append(f"| 统计 | 值 |")
        lines.append(f"|------|------|")
        lines.append(f"| 均值 | {pq.mean():.4f} |")
        lines.append(f"| 中位数 | {pq.median():.4f} |")
        lines.append(f"| 标准差 | {pq.std():.4f} |")
        lines.append(f"| 最小值 | {pq.min():.4f} |")
        lines.append(f"| 25% | {pq.quantile(0.25):.4f} |")
        lines.append(f"| 75% | {pq.quantile(0.75):.4f} |")
        lines.append(f"| 最大值 | {pq.max():.4f} |")
        lines.append("")

        bins = [(-float('inf'), -0.1), (-0.1, 0), (0, 0.05), (0.05, 0.10),
                (0.10, 0.20), (0.20, 0.50), (0.50, float('inf'))]
        labels = ['<-10%', '-10~0%', '0~5%', '5~10%', '10~20%', '20~50%', '>50%']
        lines.append("| 区间 | n | 占比 |")
        lines.append("|------|---|------|")
        for (lo, hi), label in zip(bins, labels):
            n = ((pq > lo) & (pq <= hi)).sum()
            lines.append(f"| {label} | {n} | {n/len(pq):.1%} |")
        lines.append("")

    lines.append("## 三、MFE 与 max_DD 的联合分布\n")
    if len(valid) > 0:
        mfe = valid['mfe']
        dd = valid['max_drawdown']
        lines.append(f"| 指标 | 均值 | 中位数 | 最小 | 最大 |")
        lines.append(f"|------|------|--------|------|------|")
        lines.append(f"| MFE | {mfe.mean():.4f} | {mfe.median():.4f} | {mfe.min():.4f} | {mfe.max():.4f} |")
        lines.append(f"| max_DD | {dd.mean():.4f} | {dd.median():.4f} | {dd.min():.4f} | {dd.max():.4f} |")
        lines.append("")

    lines.append("## 四、按 status 分层\n")
    if len(valid) > 0:
        lines.append("| status | n | avg path_quality | avg MFE | avg max_DD | avg final_return |")
        lines.append("|--------|---|-----------------|---------|----------|------------------|")
        for st, grp in valid.groupby('status'):
            lines.append(f"| {st} | {len(grp)} | {grp['path_quality'].mean():.4f} | "
                         f"{grp['mfe'].mean():.4f} | {grp['max_drawdown'].mean():.4f} | "
                         f"{grp['final_return'].mean():.4f} |")
        lines.append("")

    traded = valid[valid['status'] == 'traded']
    lines.append("## 五、traded 信号的 path_quality 与实际 PnL\n")
    if len(traded) > 0 and 'total_pnl_pct' in traded.columns:
        pnl = traded['total_pnl_pct'].dropna()
        pq_t = traded.loc[pnl.index, 'path_quality']

        lines.append(f"traded 且有 PnL: {len(pnl)}\n")

        try:
            traded_copy = traded.loc[pnl.index].copy()
            traded_copy['pnl'] = pnl
            traded_copy['pq_bin'] = pd.qcut(pq_t, 3, labels=['low', 'mid', 'high'],
                                             duplicates='drop')
            lines.append("按 path_quality 三分位:\n")
            lines.append("| 分位 | n | avg path_quality | avg PnL | 胜率 |")
            lines.append("|------|---|-----------------|---------|------|")
            for q in ['low', 'mid', 'high']:
                sub = traded_copy[traded_copy['pq_bin'] == q]
                if len(sub) == 0:
                    continue
                lines.append(f"| {q} | {len(sub)} | {sub['path_quality'].mean():.4f} | "
                             f"{sub['pnl'].mean():.4f} | {(sub['pnl']>0).mean():.1%} |")
            lines.append("")
        except ValueError:
            pass

        corr = pq_t.corr(pnl)
        lines.append(f"path_quality 与 PnL 的相关系数: **{corr:.4f}**\n")
    lines.append("")

    lines.append("## 六、结论\n")
    if len(valid) > 0:
        lines.append(f"- 成功计算 {len(valid)} 笔信号的 path_quality")
        lines.append(f"- path_quality 均值: {valid['path_quality'].mean():.4f}, "
                     f"中位数: {valid['path_quality'].median():.4f}")
        if len(traded) > 0 and 'total_pnl_pct' in traded.columns:
            pnl = traded['total_pnl_pct'].dropna()
            pq_t = traded.loc[pnl.index, 'path_quality']
            corr = pq_t.corr(pnl)
            lines.append(f"- path_quality 与 PnL 相关性: {corr:.4f}")
    lines.append("")
    lines.append("**下一步**: 用 path_quality 作为连续标签，训练小时线回归模型 (Task 2)。")

    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"  已写入 {OUTPUT_MD}")


if __name__ == '__main__':
    run()
