"""
P0 任务一: 止损策略优化 + 真实回测重跑

工作流程:
  1. 在验证集 (2024) 上预计算所有候选交易的原始价格路径
  2. 对 3 种出场方案 (fixed/atr/trailing) 做网格搜索
  3. 按综合得分 (Sharpe + 年化 - 回撤惩罚) 挑选最优参数
  4. 在测试集 (2025-02-21 ~ 2026-03-11) 上应用最优参数重跑真实路径回测
  5. 对照孪生案例，确认"旧止损误杀"的牛股被修复为盈利
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
    precompute_raw_trade_paths,
    run_backtest_with_v2,
    simulate_real_path_trade_v2,
    compute_real_stats,
    print_results,
    load_stock_daily,
    _extract_raw_trade_path,
    HOLDING_DAYS,
    COMMISSION,
)
from two_stage_ranker import TwoStageRanker, FINE_TOP_N


def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


OUT_DIR = _proj('data', 'result', 'super_trend')
VAL_START = '2025-01-01'
VAL_END = '2025-02-20'
TEST_START = '2025-02-21'
TEST_END = '2026-12-31'

TWIN_CASES = [
    {'stock': 'sz002294', 'mfe': 0.811, 'note': '真主升, MFE 81.1%'},
    {'stock': 'sz002958', 'mfe': 0.784, 'note': '真主升, MFE 78.4%'},
    {'stock': 'sz000516', 'mfe': 0.737, 'note': '真主升, MFE 73.7%'},
    {'stock': 'sh600976', 'mfe': 0.554, 'note': '真主升, MFE 55.4%'},
    {'stock': 'sh603169', 'mfe': 0.792, 'note': '真主升, MFE 79.2%'},
    {'stock': 'sz300721', 'mfe': 0.488, 'note': '真主升, MFE 48.8%'},
    {'stock': 'sz000722', 'mfe': 0.495, 'note': '真主升, MFE 49.5%'},
]

BEST_PARAMS_PATH = _proj('data', 'result', 'super_trend', 'models', 'best_stop_loss_params.pkl')


# ---------------------------------------------------------------------------
# 参数网格
# ---------------------------------------------------------------------------

def build_param_grid(quick=False):
    """
    生成 3 种方案 × 多种参数的网格。
    quick=True 时退化为精简网格 (仅 ~20 组合)，用于快速冒烟测试。
    """
    grid = []

    if quick:
        fixed_sl = [-0.12, -0.15]
        fixed_tp = [0.30, 0.40]
        atr_mults = [2.0, 2.5]
        atr_tps = [0.30]
        trail_sl = [-0.12]
        trail_act = [0.15]
        trail_pcts = [0.08, 0.10]
        trail_tps = [0.30]
    else:
        fixed_sl = [-0.10, -0.12, -0.15, -0.20]
        fixed_tp = [0.25, 0.30, 0.40]
        atr_mults = [1.5, 2.0, 2.5, 3.0]
        atr_tps = [0.25, 0.30, 0.40, 0.50]
        trail_sl = [-0.10, -0.12, -0.15]
        trail_act = [0.10, 0.15, 0.20]
        trail_pcts = [0.06, 0.08, 0.10, 0.12]
        trail_tps = [0.30, 0.40]

    for sl in fixed_sl:
        for tp in fixed_tp:
            grid.append({
                'scheme': 'fixed',
                'stop_loss': sl,
                'take_profit': tp,
                'atr_mult': 0.0,
                'trailing_activation': 0.0,
                'trailing_pct': 0.0,
            })

    for am in atr_mults:
        for tp in atr_tps:
            grid.append({
                'scheme': 'atr',
                'stop_loss': 0.0,
                'take_profit': tp,
                'atr_mult': am,
                'trailing_activation': 0.0,
                'trailing_pct': 0.0,
            })

    for sl in trail_sl:
        for act in trail_act:
            for pct in trail_pcts:
                for tp in trail_tps:
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
        return f"fixed_SL{p['stop_loss']:.0%}_TP{p['take_profit']:.0%}"
    elif p['scheme'] == 'atr':
        return f"atr_N{p['atr_mult']:.1f}_TP{p['take_profit']:.0%}"
    else:
        return (f"trail_SL{p['stop_loss']:.0%}_act{p['trailing_activation']:.0%}_"
                f"tr{p['trailing_pct']:.0%}_TP{p['take_profit']:.0%}")


# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def _load_model_and_test_df():
    from super_trend_ranker_trainer import SuperTrendRanker  # noqa: F401

    model_path = _proj('data', 'result', 'super_trend', 'models', 'trend_ranker_v1.pkl')
    data_path = _proj('data', 'result', 'super_trend', 'super_trend_training_data_v2.csv')

    with open(model_path, 'rb') as f:
        md = pickle.load(f)
    model = md['model']
    feature_columns = md['feature_columns']

    df = pd.read_csv(data_path).sort_values('t0_date').reset_index(drop=True)
    return model, feature_columns, df


# ---------------------------------------------------------------------------
# 网格搜索
# ---------------------------------------------------------------------------

def run_grid_search(raw_paths, param_grid, label=''):
    """
    对每组参数在 raw_paths 上跑回测，返回按综合得分排序的结果 DataFrame。

    综合得分 = sharpe * log_compound - 3 * max(0, |dd| - 0.30)
    其中 log_compound = log(max(avg_return * trades_per_year + 1, 0.01))
    强烈惩罚超过 -30% 的回撤，避免"高年化 + 爆仓"组合被误选。
    """
    print(f"\n{'='*60}")
    print(f"  网格搜索 {label}")
    print(f"  raw_paths: {len(raw_paths)}, 参数组合: {len(param_grid)}")
    print(f"{'='*60}")

    # 估算年化交易频次 (用于 log compound)
    if raw_paths:
        dates = sorted({r['date'] for r in raw_paths})
        n_days = len(dates)
        trades_per_year = len(raw_paths) / max(n_days / 252, 0.5)
    else:
        trades_per_year = 200

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

        # 综合得分: 惩罚爆仓式回撤，奖励稳健正期望
        log_compound = np.log(max(avg_ret * trades_per_year + 1.0, 0.01))
        dd_excess = max(0.0, abs(max_dd) - 0.30)
        score = sharpe * log_compound - 3.0 * dd_excess

        results.append({
            'scheme': params['scheme'],
            'stop_loss': params['stop_loss'],
            'take_profit': params['take_profit'],
            'atr_mult': params['atr_mult'],
            'trailing_activation': params['trailing_activation'],
            'trailing_pct': params['trailing_pct'],
            'signature': _param_signature(params),
            'n_trades': stats['total_trades'],
            'win_rate': win_rate,
            'avg_return': avg_ret,
            'annualized_return': annualized,
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'profit_factor': stats['profit_factor'],
            'avg_exit_day': stats['avg_exit_day'],
            'n_stop_loss': len(sl_trades),
            'n_take_profit': len(tp_trades),
            'n_trailing_stop': len(trail_trades),
            'n_hold': len(hold_trades),
            'score': score,
        })

        if (i + 1) % 10 == 0 or (i + 1) == len(param_grid):
            print(f"  [{i+1}/{len(param_grid)}] {params['scheme']:<8} "
                  f"win={win_rate:.1%} ann={annualized:+.1%} dd={max_dd:.1%} "
                  f"sharpe={sharpe:.2f} score={score:.3f}")

    result_df = pd.DataFrame(results).sort_values('score', ascending=False).reset_index(drop=True)
    return result_df


# ---------------------------------------------------------------------------
# 孪生案例检查 (false-kill 恢复验证)
# ---------------------------------------------------------------------------

def check_twin_cases(raw_paths, params, old_params=None):
    """
    检查 TWIN_CASES 中的真主升案例在新参数下的出场方式与收益。
    返回 DataFrame。
    """
    print(f"\n── 孪生案例检查 (新参数: {_param_signature(params)}) ──")

    results = []
    target_map = {}
    for r in raw_paths:
        for c in TWIN_CASES:
            if r['stock_code'] == c['stock']:
                target_map.setdefault(c['stock'], []).append(r)

    for case in TWIN_CASES:
        stock = case['stock']
        paths = target_map.get(stock, [])
        if not paths:
            results.append({
                'stock': stock,
                'mfe': case['mfe'],
                'note': case['note'],
                'n_signals': 0,
                'new_reason': 'NO_SIGNAL',
                'new_return': np.nan,
                'old_reason': 'NO_SIGNAL' if old_params else '-',
                'old_return': np.nan,
                'recovered': False,
            })
            continue

        new_returns = []
        old_returns = []
        new_reasons = []
        old_reasons = []
        for p in paths:
            res_new = simulate_real_path_trade_v2(p, **params)
            if res_new:
                new_returns.append(res_new['return_pct'])
                new_reasons.append(res_new['exit_reason'])
            if old_params:
                res_old = simulate_real_path_trade_v2(p, **old_params)
                if res_old:
                    old_returns.append(res_old['return_pct'])
                    old_reasons.append(res_old['exit_reason'])

        avg_new = np.mean(new_returns) if new_returns else np.nan
        avg_old = np.mean(old_returns) if old_returns else np.nan
        # 恢复: 旧方案亏损/止损出局 + 新方案正收益
        recovered = (avg_old is not None and not np.isnan(avg_old) and avg_old < 0
                     and avg_new is not None and not np.isnan(avg_new) and avg_new > 0)

        results.append({
            'stock': stock,
            'mfe': case['mfe'],
            'note': case['note'],
            'n_signals': len(paths),
            'new_reason': pd.Series(new_reasons).mode().iloc[0] if new_reasons else 'NO_TRADE',
            'new_return': avg_new,
            'old_reason': pd.Series(old_reasons).mode().iloc[0] if old_reasons else '-',
            'old_return': avg_old,
            'recovered': recovered,
        })
        print(f"  {stock:<10} MFE={case['mfe']:.1%}  n={len(paths):>2}  "
              f"旧:{(pd.Series(old_reasons).mode().iloc[0] if old_reasons else '-'):>14}"
              f"({avg_old:+.2%})  →  新:{(pd.Series(new_reasons).mode().iloc[0] if new_reasons else 'NO'):>14}"
              f"({avg_new:+.2%})  {'✅ 修复' if recovered else ''}")

    df = pd.DataFrame(results)
    n_recovered = df['recovered'].sum() if not df.empty else 0
    print(f"  共修复 {n_recovered} 个旧止损误杀案例 (目标 ≥ 3)")
    return df


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    print("=== P0 任务一: 止损策略优化 (两阶段选股) ===")

    quick = '--quick' in sys.argv

    # 1. 两阶段排序: 在完整日期区间上产生每日 Top 20 推荐
    print(f"\n[Step 1] 加载两阶段排序模型 ...")
    ranker = TwoStageRanker()
    ranker.load_coarse_model()
    ranker.train_fine_model()

    full_start = min(VAL_START, TEST_START)
    full_end = max(VAL_END, TEST_END)
    print(f"\n[Step 2] 运行两阶段排序 ({full_start} ~ {full_end}) ...")
    _, daily_selections = ranker.run_two_stage_only(full_start, full_end)

    # 2. 构造 raw paths
    print(f"\n[Step 3] 预计算 raw trade paths (每日 Top {FINE_TOP_N}) ...")
    all_raw_paths = _build_raw_paths(daily_selections)
    print(f"  总 raw paths: {len(all_raw_paths)}")

    # 3. 按日期切分 val / test
    val_paths = [r for r in all_raw_paths if VAL_START <= r['date'] <= VAL_END]
    test_paths = [r for r in all_raw_paths if r['date'] >= TEST_START]
    print(f"  验证集 ({VAL_START}~{VAL_END}): {len(val_paths)}")
    print(f"  测试集 ({TEST_START}~): {len(test_paths)}")

    if len(val_paths) < 100 or len(test_paths) < 100:
        print("  [ERROR] 数据不足，退出")
        sys.exit(1)

    # 4. 网格搜索 (在验证集上)
    param_grid = build_param_grid(quick=quick)
    val_results = run_grid_search(val_paths, param_grid, label='(验证集 2024)')
    val_results.to_csv(os.path.join(OUT_DIR, 'stop_loss_grid_val.csv'), index=False)
    print(f"\n网格搜索结果已保存: stop_loss_grid_val.csv")

    if val_results.empty:
        print("  [ERROR] 无有效参数组合，退出")
        sys.exit(1)

    # Top 5
    print(f"\n── 验证集 Top 5 ──")
    for i, row in val_results.head(5).iterrows():
        print(f"  #{i+1} {row['signature']:<38} win={row['win_rate']:.1%} "
              f"ann={row['annualized_return']:+.1%} dd={row['max_drawdown']:.1%} "
              f"sharpe={row['sharpe']:.2f} score={row['score']:.3f}")

    best = val_results.iloc[0]
    best_params = {
        'scheme': best['scheme'],
        'stop_loss': float(best['stop_loss']),
        'take_profit': float(best['take_profit']),
        'atr_mult': float(best['atr_mult']),
        'trailing_activation': float(best['trailing_activation']),
        'trailing_pct': float(best['trailing_pct']),
    }
    old_params = {
        'scheme': 'fixed',
        'stop_loss': -0.08,
        'take_profit': 0.30,
        'atr_mult': 0.0,
        'trailing_activation': 0.0,
        'trailing_pct': 0.0,
    }

    # 5. 验证集新旧对比 + 孪生案例
    print(f"\n[Step 4] 验证集新旧参数对比 ...")
    _, _, old_stats_val = run_backtest_with_v2(val_paths, **old_params)
    _, _, new_stats_val = run_backtest_with_v2(val_paths, **best_params)
    _print_old_vs_new(old_stats_val, new_stats_val, old_params, best_params,
                      '验证集 (2024)')

    print(f"\n[Step 5] 验证集孪生案例检查 ...")
    check_twin_cases(val_paths, best_params, old_params)

    # 6. 测试集新旧对比 + 孪生案例
    print(f"\n[Step 6] 测试集新旧参数对比 ...")
    old_trades_test, _, old_stats_test = run_backtest_with_v2(test_paths, **old_params)
    new_trades_test, _, new_stats_test = run_backtest_with_v2(test_paths, **best_params)
    _print_old_vs_new(old_stats_test, new_stats_test, old_params, best_params,
                      '测试集 (2025-02-21 ~ 2026-03-11)')

    print(f"\n[Step 7] 测试集孪生案例检查 ...")
    twin_df = check_twin_cases(test_paths, best_params, old_params)

    # 7. 保存最优参数
    with open(BEST_PARAMS_PATH, 'wb') as f:
        pickle.dump({
            'params': best_params,
            'val_score': float(best['score']),
            'val_stats': new_stats_val,
            'test_stats': new_stats_test,
            'param_grid_size': len(param_grid),
            'selection_mode': 'two_stage_top20',
        }, f)
    print(f"\n最优参数已保存: {BEST_PARAMS_PATH}")
    print(f"\n最优参数: {best_params}")

    # 8. 保存新旧测试集交易明细
    new_trades_test.to_csv(os.path.join(OUT_DIR, 'backtest_real_trades_optimized.csv'),
                           index=False)
    old_trades_test.to_csv(os.path.join(OUT_DIR, 'backtest_real_trades_baseline.csv'),
                           index=False)

    # 9. 输出任务一验收摘要
    print(f"\n{'='*60}")
    print(f"  任务一验收摘要 (两阶段 Top {FINE_TOP_N} 选股)")
    print(f"{'='*60}")
    s = new_stats_test
    print(f"  胜率:         {s['win_rate']:.2%}  (目标 ≥ 40%)")
    print(f"  最大回撤:     {s['max_drawdown']:.2%}  (目标 > -25%)")
    print(f"  年化收益:     {s['annualized_return']:.2%}  (目标 > 0%)")
    print(f"  夏普比率:     {s['sharpe_ratio']:.2f}")
    n_recovered = int(twin_df['recovered'].sum()) if not twin_df.empty else 0
    print(f"  孪生误杀修复: {n_recovered} 个  (目标 ≥ 3)")
    ok = (s['win_rate'] >= 0.40 and s['max_drawdown'] > -0.25
          and s['annualized_return'] > 0 and n_recovered >= 3)
    print(f"  整体验收:     {'✅ 通过' if ok else '⚠️ 未完全达标 (任务二做端到端最终确认)'}")
    print(f"{'='*60}")


def _build_raw_paths(daily_selections):
    """基于两阶段排序结果构造 raw trade paths"""
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
    return raw_paths


def _print_old_vs_new(old_stats, new_stats, old_params, new_params, label):
    print(f"\n── {label}: 旧 vs 新 ──")
    print(f"  {'指标':<14} {'旧 (' + _param_signature(old_params) + ')':>30} "
          f"{'新 (' + _param_signature(new_params) + ')':>30}")
    print(f"  {'─'*14} {'─'*30} {'─'*30}")
    keys = [
        ('total_trades', '总交易笔数', '{:>10d}'),
        ('win_rate', '胜率', '{:>10.2%}'),
        ('avg_return', '平均收益', '{:>+10.4f}'),
        ('annualized_return', '年化收益', '{:>+10.2%}'),
        ('max_drawdown', '最大回撤', '{:>10.2%}'),
        ('sharpe_ratio', '夏普比率', '{:>10.2f}'),
        ('profit_factor', '盈亏比', '{:>10.2f}'),
        ('avg_exit_day', '平均持仓天数', '{:>10.1f}'),
        ('n_stop_loss', '止损出场', '{:>10d}'),
        ('n_take_profit', '止盈出场', '{:>10d}'),
        ('n_hold', '持有到期', '{:>10d}'),
    ]
    for k, name, fmt in keys:
        v1 = old_stats.get(k, 0)
        v2 = new_stats.get(k, 0)
        print(f"  {name:<14} {fmt.format(v1):>30} {fmt.format(v2):>30}")


if __name__ == "__main__":
    main()
