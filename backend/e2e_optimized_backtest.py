"""
P0 任务二: 端到端验证 —— 两阶段排序 × 优化止损

工作流程:
  1. 加载任务一训练得到的最优止损参数 (best_stop_loss_params.pkl)
  2. 在测试期 (2025-02-21 ~ 2026-03-11) 跑两阶段排序，得到每日 Top 20 推荐
  3. 对每只推荐股票预计算 raw trade path
  4. 应用最优参数结算，输出净值曲线、胜率、最大回撤、夏普、年化
  5. 与 (a) 旧参数 + 单阶段 (b) 旧参数 + 两阶段 (c) 全量基线 做对比
  6. 在孪生案例所在交易日做逐笔复盘
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
from stop_loss_optimizer import (
    BEST_PARAMS_PATH,
    TEST_START,
    TEST_END,
    TWIN_CASES,
    _param_signature,
    check_twin_cases,
)


def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


OUT_DIR = _proj('data', 'result', 'super_trend')
BASELINE_PARAMS = {
    'scheme': 'fixed',
    'stop_loss': -0.08,
    'take_profit': 0.30,
    'atr_mult': 0.0,
    'trailing_activation': 0.0,
    'trailing_pct': 0.0,
}


def _build_raw_paths_from_selections(daily_selections):
    """
    基于两阶段排序结果 (每日 DataFrame)，构造 raw trade paths。
    每个 selected row 对应一次候选交易。
    """
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
            raw['coarse_score'] = row.get('_coarse_score', 0)
            raw['fine_score'] = row.get('_fine_score', 0)
            raw['future_mfe'] = row.get('future_mfe', np.nan)
            raw_paths.append(raw)
    return raw_paths


def _baseline_all_mfe(df, start_date, end_date):
    """全量等权基线 (仅用 future_mfe * 0.5 估算，与 execution_report_v2 对齐)。"""
    sub = df[(df['t0_date'] >= start_date) & (df['t0_date'] <= end_date)]
    mfe = sub['future_mfe'].fillna(0).mean()
    avg_ret = mfe * 0.5 - 2 * COMMISSION
    return {
        'total_trades': len(sub),
        'avg_return': avg_ret,
        'avg_mfe': mfe,
        'note': '全量等权基线 (MFE × 0.5 估算)',
    }


def run_e2e():
    """端到端回测: 两阶段排序 + 优化止损"""
    print("=== P0 任务二: 端到端回测 ===")

    # 1. 加载最优参数
    if not os.path.exists(BEST_PARAMS_PATH):
        print(f"  [ERROR] 未找到最优参数文件: {BEST_PARAMS_PATH}")
        print(f"  请先运行 stop_loss_optimizer.py 完成任务一")
        sys.exit(1)
    with open(BEST_PARAMS_PATH, 'rb') as f:
        best_data = pickle.load(f)
    best_params = best_data['params']
    print(f"\n最优参数 (任务一): {_param_signature(best_params)}")
    print(f"  {best_params}")

    # 2. 两阶段排序
    ranker = TwoStageRanker()
    ranker.load_coarse_model()
    ranker.train_fine_model()

    _, daily_selections = ranker.run_two_stage_only(TEST_START, TEST_END)
    n_days = len(daily_selections)
    print(f"\n两阶段排序完成: {n_days} 个交易日, 每日 Top {FINE_TOP_N}")

    # 3. 构造 raw paths
    print(f"\n预计算 raw trade paths ...")
    raw_paths = _build_raw_paths_from_selections(daily_selections)
    print(f"  raw paths: {len(raw_paths)}")

    # 4. 三种配置对比
    # (a) 单阶段 + 旧参数 (来自 v1 报告: avg_return=0.1066, 胜率=89.9% 为 MFE 模拟产物)
    # (b) 两阶段 + 旧参数
    # (c) 两阶段 + 新参数 (最终方案)
    _, _, old_stats = run_backtest_with_v2(raw_paths, **BASELINE_PARAMS)
    trades_new, daily_new, new_stats = run_backtest_with_v2(raw_paths, **best_params)

    # 5. 全量基线
    data_path = _proj('data', 'result', 'super_trend', 'super_trend_training_data_v2.csv')
    full_df = pd.read_csv(data_path).sort_values('t0_date').reset_index(drop=True)
    baseline = _baseline_all_mfe(full_df, TEST_START, TEST_END)

    # 6. 打印结果
    _print_e2e_results(old_stats, new_stats, best_params, baseline, n_days, len(raw_paths))

    # 7. 孪生案例复盘
    twin_df = check_twin_cases(raw_paths, best_params, BASELINE_PARAMS)

    # 8. 保存
    trades_new.to_csv(os.path.join(OUT_DIR, 'backtest_e2e_two_stage_optimized.csv'),
                      index=False)
    daily_new.to_csv(os.path.join(OUT_DIR, 'backtest_e2e_daily_pnl.csv'), index=False)
    print(f"\n交易明细已保存: backtest_e2e_two_stage_optimized.csv")

    # 9. 最终验收
    s = new_stats
    print(f"\n{'='*60}")
    print(f"  任务二验收摘要")
    print(f"{'='*60}")
    print(f"  年化收益:     {s['annualized_return']:.2%}  (目标 > 10%)")
    print(f"  最大回撤:     {s['max_drawdown']:.2%}  (目标 > -25%)")
    print(f"  夏普比率:     {s['sharpe_ratio']:.2f}")
    print(f"  胜率:         {s['win_rate']:.2%}")
    baseline_avg = baseline['avg_return']
    excess = s['avg_return'] - baseline_avg
    print(f"  平均净收益:   {s['avg_return']:+.4f}  vs  基线 {baseline_avg:+.4f}  "
          f"超额 {excess:+.4f}  (目标超额 > +0.05 为 MFE 估算下)")
    ok = (s['annualized_return'] > 0.10 and s['max_drawdown'] > -0.25)
    print(f"  整体验收:     {'✅ 通过 — 可进入实盘辅助' if ok else '⚠️ 未达标'}")
    print(f"{'='*60}")

    return {
        'baseline_stats': old_stats,
        'optimized_stats': new_stats,
        'twin_df': twin_df,
        'trades': trades_new,
        'daily': daily_new,
    }


def _print_e2e_results(old_stats, new_stats, best_params, baseline, n_days, n_trades_raw):
    print(f"\n{'='*70}")
    print(f"  端到端回测对比: 两阶段 Top {FINE_TOP_N} × 止损方案")
    print(f"  测试期: {TEST_START} ~ {TEST_END}  (共 {n_days} 个交易日)")
    print(f"{'='*70}")

    rows = [
        ('指标', f'旧 ({_param_signature(BASELINE_PARAMS)})',
         f'新 ({_param_signature(best_params)})'),
        ('─' * 14, '─' * 25, '─' * 25),
        ('总交易笔数', f"{old_stats['total_trades']}", f"{new_stats['total_trades']}"),
        ('胜率', f"{old_stats['win_rate']:.2%}", f"{new_stats['win_rate']:.2%}"),
        ('平均收益', f"{old_stats['avg_return']:+.4f}",
         f"{new_stats['avg_return']:+.4f}"),
        ('年化收益', f"{old_stats['annualized_return']:+.2%}",
         f"{new_stats['annualized_return']:+.2%}"),
        ('最大回撤', f"{old_stats['max_drawdown']:.2%}",
         f"{new_stats['max_drawdown']:.2%}"),
        ('夏普比率', f"{old_stats['sharpe_ratio']:.2f}",
         f"{new_stats['sharpe_ratio']:.2f}"),
        ('盈亏比', f"{old_stats['profit_factor']:.2f}",
         f"{new_stats['profit_factor']:.2f}"),
        ('平均持仓天数', f"{old_stats['avg_exit_day']:.1f}",
         f"{new_stats['avg_exit_day']:.1f}"),
        ('止损出场',
         f"{old_stats['n_stop_loss']} ({old_stats['n_stop_loss']/old_stats['total_trades']:.0%})",
         f"{new_stats['n_stop_loss']} ({new_stats['n_stop_loss']/new_stats['total_trades']:.0%})"),
        ('止盈出场',
         f"{old_stats['n_take_profit']} ({old_stats['n_take_profit']/old_stats['total_trades']:.0%})",
         f"{new_stats['n_take_profit']} ({new_stats['n_take_profit']/new_stats['total_trades']:.0%})"),
    ]
    for a, b, c in rows:
        print(f"  {a:<14} {b:>25} {c:>25}")

    print(f"\n  全量等权基线: {baseline['note']}")
    print(f"    avg_return={baseline['avg_return']:+.4f}  avg_mfe={baseline['avg_mfe']:.4f}")


if __name__ == "__main__":
    run_e2e()
