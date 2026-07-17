"""
全周期止损方案验证
在全测试期 (2025-02-21 ~ 2026-03-11) 上对 A/B/C 三方案的完整参数网格逐一回测，
输出结构化对比表供人工确认。

用法:
  python backend/verify_stop_loss_schemes.py
"""

import os
import sys
import pickle
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from real_path_backtester import (
    _extract_raw_trade_path,
    run_backtest_with_v2,
    compute_real_stats,
    load_stock_daily,
    HOLDING_DAYS,
    COMMISSION,
)
from two_stage_ranker import TwoStageRanker, FINE_TOP_N


def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


OUT_DIR = _proj('data', 'result', 'super_trend')
TEST_START = '2025-02-21'
TEST_END = '2026-12-31'


# ---------------------------------------------------------------------------
# 参数网格
# ---------------------------------------------------------------------------

def build_scheme_a_grid():
    """方案A: 固定止损/止盈"""
    grid = []
    for sl in [-0.08, -0.10, -0.12, -0.15, -0.20]:
        for tp in [0.25, 0.30, 0.40, 0.50]:
            grid.append({
                'scheme': 'fixed',
                'stop_loss': sl,
                'take_profit': tp,
                'atr_mult': 0.0,
                'trailing_activation': 0.0,
                'trailing_pct': 0.0,
            })
    return grid


def build_scheme_b_grid():
    """方案B: ATR 动态止损"""
    grid = []
    for am in [1.5, 2.0, 2.5, 3.0]:
        for tp in [0.25, 0.30, 0.40, 0.50]:
            grid.append({
                'scheme': 'atr',
                'stop_loss': 0.0,
                'take_profit': tp,
                'atr_mult': am,
                'trailing_activation': 0.0,
                'trailing_pct': 0.0,
            })
    return grid


def build_scheme_c_grid():
    """方案C: 追踪止损"""
    grid = []
    for sl in [-0.10, -0.12, -0.15]:
        for act in [0.10, 0.15, 0.20]:
            for pct in [0.06, 0.08, 0.10, 0.12]:
                for tp in [0.30, 0.40]:
                    grid.append({
                        'scheme': 'trailing',
                        'stop_loss': sl,
                        'take_profit': tp,
                        'atr_mult': 0.0,
                        'trailing_activation': act,
                        'trailing_pct': pct,
                    })
    return grid


def _param_signature(p):
    if p['scheme'] == 'fixed':
        return f"A:fixed SL={p['stop_loss']:.0%} TP={p['take_profit']:.0%}"
    elif p['scheme'] == 'atr':
        return f"B:atr N={p['atr_mult']:.1f} TP={p['take_profit']:.0%}"
    else:
        return (f"C:trail SL={p['stop_loss']:.0%} "
                f"act={p['trailing_activation']:.0%} "
                f"tr={p['trailing_pct']:.0%} "
                f"TP={p['take_profit']:.0%}")


# ---------------------------------------------------------------------------
# 网格搜索
# ---------------------------------------------------------------------------

def run_grid(raw_paths, param_grid, scheme_label):
    """对一组参数跑回测，返回结果 DataFrame"""
    n = len(raw_paths)
    g = len(param_grid)
    print(f"\n{'='*60}")
    print(f"  {scheme_label}: {g} 组参数, {n} 笔候选交易")
    print(f"{'='*60}")

    dates = sorted({r['date'] for r in raw_paths})
    n_days = len(dates)
    trades_per_year = n / max(n_days / 252, 0.5)

    results = []
    for i, params in enumerate(param_grid):
        trades_df, daily_df, stats = run_backtest_with_v2(raw_paths, **params)
        if 'error' in stats or stats.get('total_trades', 0) < 50:
            continue

        sl_trades = trades_df[trades_df['exit_reason'].isin(['stop_loss', 'stop_loss_atr'])]
        tp_trades = trades_df[trades_df['exit_reason'] == 'take_profit']
        trail_trades = trades_df[trades_df['exit_reason'] == 'trailing_stop']
        hold_trades = trades_df[trades_df['exit_reason'] == 'hold_to_end']

        annualized = stats['annualized_return']
        sharpe = stats['sharpe_ratio']
        max_dd = stats['max_drawdown']
        win_rate = stats['win_rate']
        avg_ret = stats['avg_return']

        ev_bps = stats.get('ev_bps', avg_ret * 10000)
        hold_avg = stats.get('hold_avg_return', 0)
        hold_wr = stats.get('hold_win_rate', 0)
        mfe_cap = stats.get('mfe_capture', 0)
        sl_mfe = stats.get('stop_loss_avg_mfe', 0)

        # 得分 = EV(bps) 为基准, 正期望加分, MFE捕获率加成
        score = ev_bps + (hold_avg * 10000 if hold_avg > 0 else 0) * 0.5

        results.append({
            'scheme_label': scheme_label,
            'signature': _param_signature(params),
            'stop_loss': params['stop_loss'],
            'take_profit': params['take_profit'],
            'atr_mult': params['atr_mult'],
            'trailing_activation': params['trailing_activation'],
            'trailing_pct': params['trailing_pct'],
            'n_trades': stats['total_trades'],
            'win_rate': win_rate,
            'ev_bps': ev_bps,
            'avg_return': avg_ret,
            'simple_annual': stats.get('simple_annual', avg_ret * trades_per_year),
            'annualized_return': annualized,
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'profit_factor': stats['profit_factor'],
            'avg_exit_day': stats['avg_exit_day'],
            'pct_stop_loss': len(sl_trades) / stats['total_trades'],
            'pct_take_profit': len(tp_trades) / stats['total_trades'],
            'pct_trailing': len(trail_trades) / stats['total_trades'],
            'pct_hold': len(hold_trades) / stats['total_trades'],
            'hold_avg_return': hold_avg,
            'hold_win_rate': hold_wr,
            'mfe_capture': mfe_cap,
            'stop_loss_avg_mfe': sl_mfe,
            'score': score,
        })

        if (i + 1) % 10 == 0 or (i + 1) == g:
            print(f"  [{i+1}/{g}] {params['scheme']:<8} "
                  f"win={win_rate:.1%} ev={ev_bps:+.0f}bps hold={hold_avg:+.2%} "
                  f"mfe_cap={mfe_cap:.1%} score={score:.0f}")

    result_df = pd.DataFrame(results).sort_values('score', ascending=False).reset_index(drop=True)
    return result_df


# ---------------------------------------------------------------------------
# 结果输出
# ---------------------------------------------------------------------------

def print_scheme_top5(df, scheme_label):
    """打印某方案 Top 5"""
    sub = df[df['scheme_label'] == scheme_label].head(5)
    if sub.empty:
        print(f"\n  {scheme_label}: 无有效结果")
        return
    print(f"\n── {scheme_label} Top 5 ──")
    for i, (_, r) in enumerate(sub.iterrows()):
        ev_sign = '✅' if r['ev_bps'] > 0 else '❌'
        print(f"  #{i+1} {r['signature']}  {ev_sign} EV={r['ev_bps']:+.0f}bps")
        print(f"     胜率={r['win_rate']:.1%}  盈亏比={r['profit_factor']:.2f}  "
              f"简单年化={r['simple_annual']:+.1%}  持仓={r['avg_exit_day']:.1f}天")
        print(f"     止损={r['pct_stop_loss']:.0%}  止盈={r['pct_take_profit']:.0%}  "
              f"追踪={r['pct_trailing']:.0%}  到期={r['pct_hold']:.0%}")
        print(f"     持有到期: avg={r['hold_avg_return']:+.2%} wr={r['hold_win_rate']:.0%}  "
              f"MFE捕获={r['mfe_capture']:.1%}  止损avg_MFE={r['stop_loss_avg_mfe']:.2%}")


def print_cross_comparison(all_df):
    """三方案最优参数横向对比"""
    best_per_scheme = []
    for label in ['方案A (固定)', '方案B (ATR)', '方案C (追踪)']:
        sub = all_df[all_df['scheme_label'] == label]
        if not sub.empty:
            best_per_scheme.append(sub.iloc[0])

    if not best_per_scheme:
        print("\n无有效方案可比对")
        return

    print(f"\n{'='*70}")
    print(f"  三方案最优参数横向对比 (全周期 {TEST_START} ~ {TEST_END})")
    print(f"{'='*70}")

    header = f"  {'指标':<18}"
    for b in best_per_scheme:
        header += f" {b['signature']:>36}"
    print(header)
    print(f"  {'─'*18}" + f" {'─'*36}" * len(best_per_scheme))

    rows = [
        ('每笔EV (bps)', 'ev_bps', '{:>+10.0f}'),
        ('期望值判定', 'ev_bps', lambda v: '✅ 正期望' if v > 0 else '❌ 负期望'),
        ('胜率', 'win_rate', '{:>10.1%}'),
        ('盈亏比', 'profit_factor', '{:>10.2f}'),
        ('简单年化', 'simple_annual', '{:>+10.1%}'),
        ('平均持仓天数', 'avg_exit_day', '{:>10.1f}'),
        ('止损出场占比', 'pct_stop_loss', '{:>10.0%}'),
        ('止盈出场占比', 'pct_take_profit', '{:>10.0%}'),
        ('追踪出场占比', 'pct_trailing', '{:>10.0%}'),
        ('持有到期占比', 'pct_hold', '{:>10.0%}'),
        ('持有到期平均收益', 'hold_avg_return', '{:>+10.2%}'),
        ('持有到期胜率', 'hold_win_rate', '{:>10.0%}'),
        ('MFE 捕获率', 'mfe_capture', '{:>10.1%}'),
        ('止损交易avg MFE', 'stop_loss_avg_mfe', '{:>10.2%}'),
    ]
    for name, key, fmt in rows:
        line = f"  {name:<18}"
        for b in best_per_scheme:
            val = b[key]
            if callable(fmt):
                s = fmt(val)
            else:
                s = fmt.format(val)
            line += " " + s
            line += " " * (36 - len(s))
        print(line)

    print(f"\n  ── 组合净值 (100% daily rebalance, 仅供参考) ──")
    header2 = f"  {'':>18}"
    for b in best_per_scheme:
        header2 += f" {b['signature']:>36}"
    print(header2)
    rows2 = [
        ('日复利年化', 'annualized_return', '{:>+10.1%}'),
        ('最大回撤', 'max_drawdown', '{:>10.1%}'),
        ('夏普比率', 'sharpe', '{:>10.2f}'),
    ]
    for name, key, fmt in rows2:
        line = f"  {name:<18}"
        for b in best_per_scheme:
            s = fmt.format(b[key])
            line += " " + s
            line += " " * (36 - len(s))
        print(line)

    print(f"{'='*70}")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  全周期止损方案验证 A / B / C")
    print(f"  测试期: {TEST_START} ~ {TEST_END}")
    print("=" * 60)

    # 1. 两阶段排序
    print(f"\n[Step 1] 加载两阶段排序模型 ...")
    ranker = TwoStageRanker()
    ranker.load_coarse_model()
    ranker.train_fine_model()

    print(f"\n[Step 2] 运行两阶段排序 ({TEST_START} ~ {TEST_END}) ...")
    _, daily_selections = ranker.run_two_stage_only(TEST_START, TEST_END)

    # 2. 预计算 raw trade paths
    print(f"\n[Step 3] 预计算 raw trade paths ...")
    raw_paths = []
    for date in sorted(daily_selections.keys()):
        sel = daily_selections[date]
        for _, row in sel.iterrows():
            stock_code = row['stock_code']
            df_stock = load_stock_daily(stock_code)
            raw = _extract_raw_trade_path(df_stock, date, HOLDING_DAYS)
            if raw is None:
                continue
            raw['date'] = date
            raw['stock_code'] = stock_code
            raw['score'] = row.get('_fine_score', row.get('_score', 0))
            raw['future_mfe'] = row.get('future_mfe', np.nan)
            raw_paths.append(raw)

    print(f"  raw paths: {len(raw_paths)}")
    if len(raw_paths) < 100:
        print("  [ERROR] 数据不足，退出")
        sys.exit(1)

    # 3. 三方案网格搜索
    grid_a = build_scheme_a_grid()
    grid_b = build_scheme_b_grid()
    grid_c = build_scheme_c_grid()

    total = len(grid_a) + len(grid_b) + len(grid_c)
    print(f"\n参数网格: A={len(grid_a)}组, B={len(grid_b)}组, C={len(grid_c)}组, 共{total}组")

    res_a = run_grid(raw_paths, grid_a, '方案A (固定)')
    res_b = run_grid(raw_paths, grid_b, '方案B (ATR)')
    res_c = run_grid(raw_paths, grid_c, '方案C (追踪)')

    all_df = pd.concat([res_a, res_b, res_c], ignore_index=True)

    # 4. 输出
    print_scheme_top5(all_df, '方案A (固定)')
    print_scheme_top5(all_df, '方案B (ATR)')
    print_scheme_top5(all_df, '方案C (追踪)')
    print_cross_comparison(all_df)

    # 5. 保存
    out_path = os.path.join(OUT_DIR, 'verify_schemes_full.csv')
    all_df.to_csv(out_path, index=False)
    print(f"\n完整结果已保存: {out_path}")
    print(f"共 {len(all_df)} 组有效参数组合")


if __name__ == "__main__":
    main()
