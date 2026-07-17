#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.2: 数据驱动的路径分析 + 分层入场回测

核心思路:
  1. 对4423信号计算T0后22天内的回调深度 + 反弹高度
  2. 按回调深度分层，统计每层的反弹潜力
  3. 从数据反推入场触发价 / 止盈 / 止损参数
  4. 对全量信号模拟回测，与原系统对比

输出:
  - doc/0613_super_trend_v2/path_analysis_v42.csv
  - doc/0613_super_trend_v2/path_analysis_v42_report.md
  - doc/0613_super_trend_v2/tiered_backtest_v42_report.md
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
OUTPUT_CSV = os.path.join(DOC_DIR, 'path_analysis_v42.csv')
ANALYSIS_MD = os.path.join(DOC_DIR, 'path_analysis_v42_report.md')
BACKTEST_MD = os.path.join(DOC_DIR, 'tiered_backtest_v42_report.md')

FUTURE_DAYS = 22
MIN_BARS = 15
FUTURE_CALENDAR_DAYS = 45

# 回调深度分层定义
DRAWDOWN_BINS = [
    (-float('inf'), -0.20),  # > 20%
    (-0.20, -0.15),          # 15~20%
    (-0.15, -0.10),          # 10~15%
    (-0.10, -0.05),          # 5~10%
    (-0.05, -0.03),          # 3~5%
    (-0.03, 0.001),          # 0~3%
]
DRAWDOWN_LABELS = [
    '>20%', '15~20%', '10~15%', '5~10%', '3~5%', '0~3%',
]


# ---------------------------------------------------------------------------
# 数据加载 (复用 v4.1 逻辑)
# ---------------------------------------------------------------------------
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
        'open': 'first', 'high': 'max',
        'low': 'min', 'close': 'last', 'volume': 'sum',
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


# ---------------------------------------------------------------------------
# Step 1: 全量路径分析
# ---------------------------------------------------------------------------
def compute_path_analysis(open_arr, high, low, close):
    """
    对单笔信号的22天路径，计算:
      - entry_price: T+1 开盘价
      - max_drawdown: 从入场价开始的最大跌幅 (负值)
      - dd_day_idx: 最大回调发生在第几天
      - rebound_pct: 从最低点之后的最大反弹幅度
      - subsequent_high: 最低点之后的最高价
      - effective_range: 有效波动区间宽度 (低点到后续高点的涨幅)
      - mfe: 最大有利偏移 (从入场价算)
      - final_return: 最终收益
    """
    entry_price = open_arr[0]
    n = len(close)

    # 回调深度: 从入场价算起的累计最低价
    cum_low = np.minimum.accumulate(low)
    drawdown = cum_low / entry_price - 1  # 负值
    max_dd = float(np.min(drawdown))
    dd_idx = int(np.argmin(drawdown))

    # 反弹: 从最低点之后的最高价
    if dd_idx < n - 1:
        subsequent_high = float(np.max(high[dd_idx:]))
        rebound_pct = subsequent_high / low[dd_idx] - 1 if low[dd_idx] > 0 else 0.0
    else:
        subsequent_high = float(high[-1])
        rebound_pct = 0.0

    # MFE: 从入场价算的最大涨幅
    mfe = float(np.max(high) / entry_price - 1) if entry_price > 0 else 0.0

    # 最终收益
    final_ret = float(close[-1] / entry_price - 1) if entry_price > 0 else 0.0

    # 有效波动区间
    effective_range = rebound_pct

    return {
        'entry_price': float(entry_price),
        'max_drawdown': max_dd,
        'dd_day_idx': dd_idx,
        'rebound_pct': float(rebound_pct),
        'subsequent_high': subsequent_high,
        'effective_range': float(effective_range),
        'mfe': mfe,
        'final_return': final_ret,
    }


def step1_path_analysis(df_signals: pd.DataFrame) -> pd.DataFrame:
    """对全量信号计算路径分析"""
    print("\n  [Step 1] 全量路径分析...")
    results = []
    n_ok = n_skip = 0
    t0 = time.time()

    for i, (idx, row) in enumerate(df_signals.iterrows()):
        if (i + 1) % 200 == 0 or i == 0:
            print(f"    处理 {i + 1}/{len(df_signals)} ...")

        stock = row['stock_code']
        t0_date = row['t0_date']
        start = (t0_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        end = (t0_date + pd.Timedelta(days=FUTURE_CALENDAR_DAYS)).strftime('%Y-%m-%d')

        daily = _load_daily_via_60m(stock, start, end)
        if daily is None or daily.empty or len(daily) < MIN_BARS:
            n_skip += 1
            results.append({
                'signal_idx': idx, 'stock_code': stock,
                't0_date': t0_date, 'status': row.get('status', ''),
                'entry_price': np.nan, 'max_drawdown': np.nan,
                'dd_day_idx': np.nan, 'rebound_pct': np.nan,
                'subsequent_high': np.nan, 'effective_range': np.nan,
                'mfe': np.nan, 'final_return': np.nan,
            })
            continue

        daily = daily.head(FUTURE_DAYS)
        o = daily['open'].values.astype(float)
        h = daily['high'].values.astype(float)
        l = daily['low'].values.astype(float)
        c = daily['close'].values.astype(float)

        metrics = compute_path_analysis(o, h, l, c)
        metrics['signal_idx'] = idx
        metrics['stock_code'] = stock
        metrics['t0_date'] = t0_date
        metrics['status'] = row.get('status', '')
        results.append(metrics)
        n_ok += 1

    elapsed = time.time() - t0
    result_df = pd.DataFrame(results)
    print(f"    完成: {n_ok} 成功, {n_skip} 跳过, 耗时 {elapsed:.1f}s")
    return result_df


# ---------------------------------------------------------------------------
# Step 2: 分层统计 + 参数制定
# ---------------------------------------------------------------------------
def step2_tier_statistics(path_df: pd.DataFrame) -> tuple:
    """按回调深度分层统计，生成参数表"""
    print("\n  [Step 2] 分层统计...")

    valid = path_df.dropna(subset=['max_drawdown', 'rebound_pct']).copy()

    # 分层标签
    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'],
        bins=[-float('inf'), -0.20, -0.15, -0.10, -0.05, -0.03, 0.001],
        labels=['>20%', '15~20%', '10~15%', '5~10%', '3~5%', '0~3%'],
    )

    # 分层统计
    tier_stats = []
    for tier_name in ['0~3%', '3~5%', '5~10%', '10~15%', '15~20%', '>20%']:
        sub = valid[valid['dd_tier'] == tier_name]
        if len(sub) == 0:
            continue
        dd = sub['max_drawdown']
        rb = sub['rebound_pct']
        mfe = sub['mfe']
        dd_day = sub['dd_day_idx']

        # 反弹>10% 的概率
        rb_gt10 = (rb > 0.10).mean()
        rb_gt5 = (rb > 0.05).mean()

        # 80%分位反弹高度作为止盈参考
        rb_p80 = rb.quantile(0.80)
        rb_p50 = rb.median()

        tier_stats.append({
            'tier': tier_name,
            'n': len(sub),
            'pct': len(sub) / len(valid),
            'avg_dd': dd.mean(),
            'median_dd': dd.median(),
            'avg_rebound': rb.mean(),
            'median_rebound': rb.median(),
            'rebound_p80': rb_p80,
            'rebound_gt10_pct': rb_gt10,
            'rebound_gt5_pct': rb_gt5,
            'avg_mfe': mfe.mean(),
            'avg_dd_day': dd_day.mean(),
            'median_dd_day': dd_day.median(),
        })

    tier_df = pd.DataFrame(tier_stats)

    # 制定入场参数表
    param_table = _derive_entry_params(tier_df, valid)

    return valid, tier_df, param_table


def _derive_entry_params(tier_df: pd.DataFrame, valid: pd.DataFrame) -> pd.DataFrame:
    """从数据反推入场参数"""
    params = []

    for _, row in tier_df.iterrows():
        tier = row['tier']
        avg_dd = row['avg_dd']
        median_dd = row['median_dd']
        rb_p80 = row['rebound_p80']
        rb_gt10 = row['rebound_gt10_pct']
        rb_gt5 = row['rebound_gt5_pct']
        avg_dd_day = row['avg_dd_day']

        # 入场触发: 在该层中位回调深度附近 (给1%缓冲)
        entry_trigger = median_dd + 0.01  # 比中位略浅时入场

        # 止盈: 反弹高度的50%分位 * 0.8 (保守折扣)
        tp_pct = row['median_rebound'] * 0.8

        # 止损: 入场价下方再跌 5% (相对入场价)
        sl_pct = 0.05

        # 是否建议启用
        enabled = rb_gt5 > 0.5 and tp_pct > sl_pct

        params.append({
            'tier': tier,
            'entry_trigger': round(entry_trigger, 4),
            'tp_pct': round(max(tp_pct, 0.03), 4),
            'sl_pct': round(sl_pct, 4),
            'avg_dd_day': round(avg_dd_day, 1),
            'rebound_gt5_pct': round(rb_gt5, 4),
            'enabled': enabled,
            'n_signals': int(row['n']),
        })

    return pd.DataFrame(params)


# ---------------------------------------------------------------------------
# Step 3: 分层策略回测
# ---------------------------------------------------------------------------
def step3_tiered_backtest(path_df: pd.DataFrame, tiered_valid: pd.DataFrame,
                           param_table: pd.DataFrame,
                           review4_df: pd.DataFrame) -> pd.DataFrame:
    """
    对每笔信号模拟分层策略:
    - 根据信号的回调深度找到所属分层
    - 应用该层的入场触发 / 止盈 / 止损
    - 模拟逐日判断是否触发入场/止盈/止损
    """
    print("\n  [Step 3] 分层策略回测...")

    valid = path_df.dropna(subset=['max_drawdown', 'rebound_pct', 'entry_price']).copy()

    # 给每笔信号分配分层
    valid['dd_tier'] = pd.cut(
        valid['max_drawdown'],
        bins=[-float('inf'), -0.20, -0.15, -0.10, -0.05, -0.03, 0.001],
        labels=['>20%', '15~20%', '10~15%', '5~10%', '3~5%', '0~3%'],
    )

    # 建立参数查找表
    param_dict = {}
    for _, p in param_table.iterrows():
        param_dict[p['tier']] = p

    # 合并 review4 的原始 PnL (如果有)
    review4_pnl = {}
    if 'total_pnl_pct' in review4_df.columns:
        for _, r in review4_df.iterrows():
            review4_pnl[r.name] = r.get('total_pnl_pct', np.nan)
    elif 'signal_idx' in review4_df.columns:
        for _, r in review4_df.iterrows():
            review4_pnl[r['signal_idx']] = r.get('total_pnl_pct', np.nan)

    results = []
    t0 = time.time()

    for i, (idx, row) in enumerate(valid.iterrows()):
        if (i + 1) % 500 == 0:
            print(f"    回测 {i + 1}/{len(valid)} ...")

        stock = row['stock_code']
        t0_date = row['t0_date']
        tier = row['dd_tier']
        entry_price = row['entry_price']

        param = param_dict.get(tier)
        if param is None or not param['enabled']:
            results.append({
                'signal_idx': idx, 'stock_code': stock,
                't0_date': t0_date, 'dd_tier': tier,
                'max_drawdown': row['max_drawdown'],
                'status': 'disabled_tier',
                'sim_entry_triggered': False,
                'sim_pnl': np.nan,
                'sim_exit_reason': '',
                'original_pnl': review4_pnl.get(idx, np.nan),
                'original_status': row.get('status', ''),
            })
            continue

        # 加载22天日线数据用于逐日模拟
        start = (t0_date + pd.Timedelta(days=1)).strftime('%Y-%m-%d')
        end = (t0_date + pd.Timedelta(days=FUTURE_CALENDAR_DAYS)).strftime('%Y-%m-%d')
        daily = _load_daily_via_60m(stock, start, end)
        if daily is None or daily.empty:
            results.append({
                'signal_idx': idx, 'stock_code': stock,
                't0_date': t0_date, 'dd_tier': tier,
                'max_drawdown': row['max_drawdown'],
                'status': 'no_data',
                'sim_entry_triggered': False,
                'sim_pnl': np.nan,
                'sim_exit_reason': '',
                'original_pnl': review4_pnl.get(idx, np.nan),
                'original_status': row.get('status', ''),
            })
            continue

        daily = daily.head(FUTURE_DAYS)
        trigger_price = entry_price * (1 + param['entry_trigger'])
        tp_price = trigger_price * (1 + param['tp_pct'])
        sl_price = trigger_price * (1 - param['sl_pct'])

        # 逐日模拟
        entered = False
        entry_actual = None
        exit_pnl = None
        exit_reason = ''

        for day_i in range(len(daily)):
            day_low = float(daily['low'].iloc[day_i])
            day_high = float(daily['high'].iloc[day_i])
            day_close = float(daily['close'].iloc[day_i])

            if not entered:
                # 检查是否触发入场 (当日最低价 <= 触发价)
                if day_low <= trigger_price:
                    entered = True
                    entry_actual = trigger_price
                    # 入场当日也可能触发止盈/止损
                    if day_high >= tp_price:
                        exit_pnl = (tp_price / entry_actual) - 1
                        exit_reason = 'tp'
                        break
                    if day_low <= sl_price:
                        exit_pnl = (sl_price / entry_actual) - 1
                        exit_reason = 'sl'
                        break
            else:
                # 已入场: 检查止盈止损
                if day_high >= tp_price:
                    exit_pnl = (tp_price / entry_actual) - 1
                    exit_reason = 'tp'
                    break
                if day_low <= sl_price:
                    exit_pnl = (sl_price / entry_actual) - 1
                    exit_reason = 'sl'
                    break

        if entered and exit_pnl is None:
            # 持仓到期, 以最后一天收盘价平仓
            exit_pnl = (float(daily['close'].iloc[-1]) / entry_actual) - 1
            exit_reason = 'expire'

        results.append({
            'signal_idx': idx, 'stock_code': stock,
            't0_date': t0_date, 'dd_tier': tier,
            'max_drawdown': row['max_drawdown'],
            'status': 'simulated',
            'sim_entry_triggered': entered,
            'sim_entry_price': entry_actual if entered else np.nan,
            'sim_tp_price': tp_price if entered else np.nan,
            'sim_sl_price': sl_price if entered else np.nan,
            'sim_pnl': exit_pnl if exit_pnl is not None else np.nan,
            'sim_exit_reason': exit_reason,
            'original_pnl': review4_pnl.get(idx, np.nan),
            'original_status': row.get('status', ''),
        })

    result_df = pd.DataFrame(results)
    elapsed = time.time() - t0
    print(f"    回测完成, 耗时 {elapsed:.1f}s")
    return result_df


# ---------------------------------------------------------------------------
# Step 4: 生成报告
# ---------------------------------------------------------------------------
def generate_analysis_report(path_df, tiered_valid, tier_df, param_table, elapsed):
    """生成 Step 1+2 的路径分析报告"""
    valid = path_df.dropna(subset=['max_drawdown'])
    lines = []
    lines.append("# 数据驱动路径分析报告 (v4.2 Step 1+2)\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append(f"**耗时**: {elapsed:.1f}s\n")
    lines.append("")

    # 全量统计
    dd = valid['max_drawdown']
    rb = valid['rebound_pct'].dropna()
    lines.append("## 一、全量信号回调深度统计\n")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 信号总数 | {len(valid)} |")
    lines.append(f"| 平均最大回调 | {dd.mean():.4f} ({dd.mean():.2%}) |")
    lines.append(f"| 中位最大回调 | {dd.median():.4f} ({dd.median():.2%}) |")
    lines.append(f"| 回调>10% 占比 | {(dd < -0.10).mean():.1%} |")
    lines.append(f"| 回调>15% 占比 | {(dd < -0.15).mean():.1%} |")
    lines.append(f"| 回调>20% 占比 | {(dd < -0.20).mean():.1%} |")
    lines.append("")

    lines.append("## 二、回调后反弹统计\n")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 平均反弹幅度 | {rb.mean():.4f} ({rb.mean():.2%}) |")
    lines.append(f"| 中位反弹幅度 | {rb.median():.4f} ({rb.median():.2%}) |")
    lines.append(f"| 反弹>5% 占比 | {(rb > 0.05).mean():.1%} |")
    lines.append(f"| 反弹>10% 占比 | {(rb > 0.10).mean():.1%} |")
    lines.append(f"| 反弹>20% 占比 | {(rb > 0.20).mean():.1%} |")
    lines.append("")

    # 回调深度分布直方图
    lines.append("## 三、回调深度分布\n")
    lines.append("| 深度范围 | n | 占比 | 累计占比 |")
    lines.append("|---------|---|------|---------|")
    cum_pct = 0
    for _, r in tier_df.iterrows():
        cum_pct += r['pct']
        lines.append(f"| {r['tier']} | {r['n']} | {r['pct']:.1%} | {cum_pct:.1%} |")
    lines.append("")

    # 分层统计详表
    lines.append("## 四、分层统计详表\n")
    lines.append("| 回调层 | n | 占比 | avg回调 | avg反弹 | 反弹中位 | 反弹80%位 | 反弹>5% | 反弹>10% | avg MFE | avg回调天数 |")
    lines.append("|--------|---|------|---------|---------|---------|----------|---------|----------|---------|-----------|")
    for _, r in tier_df.iterrows():
        lines.append(f"| {r['tier']} | {r['n']} | {r['pct']:.1%} | "
                     f"{r['avg_dd']:.2%} | {r['avg_rebound']:.2%} | "
                     f"{r['median_rebound']:.2%} | {r['rebound_p80']:.2%} | "
                     f"{r['rebound_gt5_pct']:.1%} | {r['rebound_gt10_pct']:.1%} | "
                     f"{r['avg_mfe']:.2%} | {r['avg_dd_day']:.1f} |")
    lines.append("")

    # 参数表
    lines.append("## 五、数据驱动的入场参数表\n")
    lines.append("| 回调层 | 入场触发 | 止盈% | 止损% | 反弹>5%概率 | 建议启用 | 信号数 |")
    lines.append("|--------|---------|-------|-------|------------|---------|--------|")
    for _, p in param_table.iterrows():
        lines.append(f"| {p['tier']} | {p['entry_trigger']:.2%} | "
                     f"{p['tp_pct']:.2%} | {p['sl_pct']:.2%} | "
                     f"{p['rebound_gt5_pct']:.1%} | "
                     f"{'Yes' if p['enabled'] else 'No'} | {p['n_signals']} |")
    lines.append("")

    lines.append("**说明**: 入场触发 = 回调到中位深度+1%时入场; 止盈 = 反弹中位*0.8; 止损 = 入场价下方5%\n")

    with open(ANALYSIS_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"    已写入 {ANALYSIS_MD}")


def generate_backtest_report(bt_df, param_table, review4_df):
    """生成 Step 3+4 的回测对比报告"""
    lines = []
    lines.append("# 分层策略回测报告 (v4.2 Step 3+4)\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append("")

    # 触发统计
    simulated = bt_df[bt_df['status'] == 'simulated']
    triggered = simulated[simulated['sim_entry_triggered'] == True]
    disabled = bt_df[bt_df['status'] == 'disabled_tier']

    lines.append("## 一、触发统计\n")
    lines.append(f"| 维度 | 数量 |")
    lines.append(f"|------|------|")
    lines.append(f"| 总信号 | {len(bt_df)} |")
    lines.append(f"| 可交易分层 | {len(simulated)} |")
    lines.append(f"| 禁用分层 | {len(disabled)} |")
    lines.append(f"| 触发入场 | {len(triggered)} ({len(triggered)/len(bt_df):.1%}) |")
    lines.append(f"| 未触发 (未达触发价) | {len(simulated) - len(triggered)} |")
    lines.append("")

    if len(triggered) == 0:
        lines.append("无触发交易，无法生成回测报告。\n")
        with open(BACKTEST_MD, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        return

    pnl = triggered['sim_pnl'].dropna()
    win = (pnl > 0).sum()
    gp = float(pnl[pnl > 0].sum()) if win > 0 else 0
    gl = abs(float(pnl[pnl < 0].sum())) if (pnl < 0).sum() > 0 else 0.001
    pf = gp / gl if gl > 0 else 99.99

    lines.append("## 二、分层策略整体表现\n")
    lines.append(f"| 指标 | 分层策略 | 原系统 (Review4) |")
    lines.append(f"|------|---------|-----------------|")

    # 原系统基线
    orig_traded = review4_df[review4_df['status'] == 'traded']
    orig_pnl = orig_traded['total_pnl_pct'].dropna() if 'total_pnl_pct' in orig_traded.columns else pd.Series(dtype=float)
    if len(orig_pnl) > 0:
        orig_avg = orig_pnl.mean()
        orig_wr = (orig_pnl > 0).mean()
        orig_gp = float(orig_pnl[orig_pnl > 0].sum()) if (orig_pnl > 0).any() else 0
        orig_gl = abs(float(orig_pnl[orig_pnl < 0].sum())) if (orig_pnl < 0).any() else 0.001
        orig_pf = orig_gp / orig_gl if orig_gl > 0 else 99.99
    else:
        orig_avg = orig_wr = orig_pf = 0

    lines.append(f"| 交易数 | {len(pnl)} | {len(orig_pnl)} |")
    lines.append(f"| 平均盈亏 | {pnl.mean():.4f} ({pnl.mean():.2%}) | {orig_avg:.4f} ({orig_avg:.2%}) |")
    lines.append(f"| 中位数 | {pnl.median():.4f} | {orig_pnl.median():.4f} |")
    lines.append(f"| 胜率 | {win/len(pnl):.1%} | {orig_wr:.1%} |")
    lines.append(f"| 盈利因子 | {pf:.2f} | {orig_pf:.2f} |")
    lines.append(f"| 最大盈利 | {pnl.max():.4f} | {orig_pnl.max():.4f} |")
    lines.append(f"| 最大亏损 | {pnl.min():.4f} | {orig_pnl.min():.4f} |")
    lines.append("")

    # 按分层统计
    lines.append("## 三、按回调分层回测\n")
    lines.append("| 分层 | 触发数 | avg PnL | 胜率 | PF | 止盈占比 | 止损占比 | 到期占比 |")
    lines.append("|------|--------|---------|------|------|---------|---------|---------|")
    for tier_name in ['0~3%', '3~5%', '5~10%', '10~15%', '15~20%', '>20%']:
        sub = triggered[triggered['dd_tier'] == tier_name]
        if len(sub) == 0:
            continue
        s_pnl = sub['sim_pnl'].dropna()
        if len(s_pnl) == 0:
            continue
        s_win = (s_pnl > 0).sum()
        s_gp = float(s_pnl[s_pnl > 0].sum()) if s_win > 0 else 0
        s_gl = abs(float(s_pnl[s_pnl < 0].sum())) if (s_pnl < 0).sum() > 0 else 0.001
        s_pf = s_gp / s_gl if s_gl > 0 else 99.99

        exit_reasons = sub['sim_exit_reason'].value_counts()
        tp_n = exit_reasons.get('tp', 0)
        sl_n = exit_reasons.get('sl', 0)
        exp_n = exit_reasons.get('expire', 0)
        total_exit = tp_n + sl_n + exp_n
        if total_exit == 0:
            total_exit = 1

        lines.append(f"| {tier_name} | {len(s_pnl)} | {s_pnl.mean():.4f} | "
                     f"{s_win/len(s_pnl):.1%} | {s_pf:.2f} | "
                     f"{tp_n/total_exit:.0%} | {sl_n/total_exit:.0%} | {exp_n/total_exit:.0%} |")
    lines.append("")

    # 深回调信号专项分析 (原系统放弃的)
    lines.append("## 四、深回调信号专项 (原系统 traded vs 分层策略)\n")
    deep_tiers = ['10~15%', '15~20%', '>20%']
    deep_triggered = triggered[triggered['dd_tier'].isin(deep_tiers)]
    deep_pnl = deep_triggered['sim_pnl'].dropna()
    if len(deep_pnl) > 0:
        d_win = (deep_pnl > 0).sum()
        d_gp = float(deep_pnl[deep_pnl > 0].sum()) if d_win > 0 else 0
        d_gl = abs(float(deep_pnl[deep_pnl < 0].sum())) if (deep_pnl < 0).sum() > 0 else 0.001
        d_pf = d_gp / d_gl if d_gl > 0 else 99.99
        lines.append(f"深回调 (>10%) 触发交易: {len(deep_pnl)} 笔\n")
        lines.append(f"- avg PnL: {deep_pnl.mean():.4f} ({deep_pnl.mean():.2%})")
        lines.append(f"- 胜率: {d_win/len(deep_pnl):.1%}")
        lines.append(f"- PF: {d_pf:.2f}")
    else:
        lines.append("深回调层无触发交易。\n")
    lines.append("")

    # 按月统计
    if 't0_date' in triggered.columns:
        triggered_copy = triggered.copy()
        triggered_copy['month'] = pd.to_datetime(triggered_copy['t0_date']).dt.strftime('%Y-%m')
        lines.append("## 五、按月回测对比\n")
        lines.append("| 月份 | 分层触发数 | 分层 avg PnL | 原系统 traded 数 | 原系统 avg PnL |")
        lines.append("|------|----------|-------------|----------------|---------------|")

        orig_traded_copy = orig_traded.copy()
        if len(orig_traded_copy) > 0:
            orig_traded_copy['month'] = pd.to_datetime(orig_traded_copy['t0_date']).dt.strftime('%Y-%m')

        all_months = sorted(set(triggered_copy['month'].unique()) |
                           set(orig_traded_copy['month'].unique() if len(orig_traded_copy) > 0 else []))
        for m in all_months:
            sim_m = triggered_copy[triggered_copy['month'] == m]
            orig_m = orig_traded_copy[orig_traded_copy['month'] == m] if len(orig_traded_copy) > 0 else pd.DataFrame()

            sim_pnl_m = sim_m['sim_pnl'].dropna()
            sim_str = f"{sim_pnl_m.mean():.4f}" if len(sim_pnl_m) > 0 else "-"

            orig_pnl_m = orig_m['total_pnl_pct'].dropna() if 'total_pnl_pct' in orig_m.columns and len(orig_m) > 0 else pd.Series(dtype=float)
            orig_str = f"{orig_pnl_m.mean():.4f}" if len(orig_pnl_m) > 0 else "-"

            lines.append(f"| {m} | {len(sim_pnl_m)} | {sim_str} | "
                         f"{len(orig_pnl_m)} | {orig_str} |")
        lines.append("")

    # 验收标准
    lines.append("## 六、验收标准\n")
    lines.append(f"| 标准 | 要求 | 实际 | 判定 |")
    lines.append(f"|------|------|------|------|")
    lines.append(f"| 交易量 | 接近日均5笔 | {len(pnl)}笔/{len(set(pd.to_datetime(triggered['t0_date']).dt.strftime('%Y-%m')))}月 = "
                 f"日均{len(pnl)/max(len(set(pd.to_datetime(triggered['t0_date']).dt.strftime('%Y-%m')))*22,1):.1f}笔 | "
                 f"{'PASS' if len(pnl)/max(len(set(pd.to_datetime(triggered['t0_date']).dt.strftime('%Y-%m')))*22,1) >= 3 else 'FAIL'} |")
    lines.append(f"| 深回调盈亏 | > 0 | {deep_pnl.mean():.4f} | "
                 f"{'PASS' if len(deep_pnl) > 0 and deep_pnl.mean() > 0 else 'FAIL'} |")
    lines.append(f"| 胜率 | >= 45% | {win/len(pnl):.1%} | {'PASS' if win/len(pnl) >= 0.45 else 'FAIL'} |")
    lines.append(f"| PF | >= 1.8 | {pf:.2f} | {'PASS' if pf >= 1.8 else 'FAIL'} |")
    lines.append("")

    with open(BACKTEST_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"    已写入 {BACKTEST_MD}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("  v4.2 数据驱动路径分析 + 分层入场回测")
    print("=" * 70)

    # 加载信号
    df_signals = pd.read_csv(REVIEW4_CSV)
    df_signals['t0_date'] = pd.to_datetime(df_signals['t0_date'])
    print(f"  加载信号: {len(df_signals)} 笔")

    t_start = time.time()

    # Step 1: 全量路径分析
    path_df = step1_path_analysis(df_signals)
    path_df.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"    已保存 {OUTPUT_CSV}")

    # Step 2: 分层统计 + 参数制定
    tiered_valid, tier_df, param_table = step2_tier_statistics(path_df)

    elapsed_s12 = time.time() - t_start

    # 生成分析报告
    generate_analysis_report(path_df, tiered_valid, tier_df, param_table, elapsed_s12)

    # Step 3: 分层回测
    bt_df = step3_tiered_backtest(path_df, tiered_valid, param_table, df_signals)

    # Step 4: 对比报告
    generate_backtest_report(bt_df, param_table, df_signals)

    total_elapsed = time.time() - t_start
    print(f"\n  全部完成, 总耗时 {total_elapsed:.1f}s")


if __name__ == '__main__':
    main()
