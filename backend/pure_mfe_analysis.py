"""
纯 MFE 分析: 绕过入场/出场逻辑，直接评估精排 Top 20 选股信号的 MFE 质量

对比维度:
  1. 精排 Top 20 的 future_mfe 分布 vs 全量测试集
  2. 精排 Top 20 的 T+22 持有收益 (buy at T+1 open, sell at day 22 close)
  3. 按月分组的 MFE 趋势
  4. 精排分数与 MFE 的 rank correlation
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

from two_stage_ranker import TwoStageRanker, FINE_TOP_N
from real_path_backtester import load_stock_daily, HOLDING_DAYS, COMMISSION


def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


TEST_START = '2025-02-21'
TEST_END = '2026-12-31'


def compute_hold_to_end_return(stock_code, t0_date, holding_days=HOLDING_DAYS):
    """纯持有到期收益: T+1 开盘买, 第 22 天收盘卖, 不做任何止损/止盈"""
    df_stock = load_stock_daily(stock_code)
    if df_stock is None or len(df_stock) < 5:
        return None

    t0_ts = pd.Timestamp(t0_date)
    closest = df_stock.index.searchsorted(t0_ts)
    if closest >= len(df_stock):
        return None
    t0_idx = closest

    t0_close = df_stock.iloc[t0_idx]['close']
    t1_idx = t0_idx + 1
    if t1_idx >= len(df_stock):
        return None

    t1_open = df_stock.iloc[t1_idx]['open']
    gap_pct = (t1_open / t0_close) - 1.0 if t0_close > 0.01 else np.nan
    if pd.notna(gap_pct) and gap_pct > 0.05:
        return None

    end_idx = min(t1_idx + holding_days - 1, len(df_stock) - 1)
    end_close = df_stock.iloc[end_idx]['close']

    # 路径中的最大浮亏 (MAE proxy)
    path = df_stock.iloc[t1_idx:end_idx + 1]
    min_low = path['low'].min()
    max_dd = (min_low / t1_open) - 1.0

    return {
        'buy_price': float(t1_open),
        'end_close': float(end_close),
        'hold_return': (end_close / t1_open) - 1.0,
        'max_drawdown_in_path': max_dd,
        'gap_pct': float(gap_pct) if pd.notna(gap_pct) else 0.0,
    }


def main():
    print("=" * 60)
    print("  纯 MFE 分析: 绕过出入场，只看选股质量")
    print(f"  测试期: {TEST_START} ~ {TEST_END}")
    print("=" * 60)

    # 1. 加载数据
    data_path = _proj('data', 'result', 'super_trend', 'super_trend_training_data_v2.csv')
    df = pd.read_csv(data_path).sort_values('t0_date').reset_index(drop=True)
    split_idx = int(len(df) * 0.8)
    test_df = df.iloc[split_idx:].copy()
    test_df = test_df[(test_df['t0_date'] >= TEST_START) & (test_df['t0_date'] <= TEST_END)]

    print(f"\n全量测试集: {len(test_df)} 行, {test_df['t0_date'].nunique()} 个交易日")

    # 2. 全量 MFE 基线
    print(f"\n{'='*60}")
    print(f"  全量测试集 MFE 基线")
    print(f"{'='*60}")
    all_mfe = test_df['future_mfe'].dropna()
    print(f"  样本数:   {len(all_mfe)}")
    print(f"  均值:     {all_mfe.mean():.2%}")
    print(f"  中位数:   {all_mfe.median():.2%}")
    print(f"  25分位:   {all_mfe.quantile(0.25):.2%}")
    print(f"  75分位:   {all_mfe.quantile(0.75):.2%}")
    print(f"  >0 占比:  {(all_mfe > 0).mean():.1%}")
    print(f"  >20% 占比: {(all_mfe > 0.20).mean():.1%}")

    # 3. 两阶段排序
    print(f"\n[Step 1] 加载两阶段排序模型 ...")
    ranker = TwoStageRanker()
    ranker.load_coarse_model()
    ranker.train_fine_model()

    print(f"\n[Step 2] 运行两阶段排序 ...")
    _, daily_selections = ranker.run_two_stage_only(TEST_START, TEST_END)

    # 4. 收集精排 Top 20 的 MFE
    top20_records = []
    for date in sorted(daily_selections.keys()):
        sel = daily_selections[date]
        for _, row in sel.iterrows():
            top20_records.append({
                'date': date,
                'stock_code': row['stock_code'],
                'fine_score': row.get('_fine_score', 0),
                'coarse_score': row.get('_coarse_score', 0),
                'future_mfe': row.get('future_mfe', np.nan),
            })

    top20_df = pd.DataFrame(top20_records)
    print(f"\n精排 Top 20: {len(top20_df)} 条, {top20_df['date'].nunique()} 个交易日")

    # 5. Top 20 MFE 分析
    print(f"\n{'='*60}")
    print(f"  精排 Top 20 MFE 分布")
    print(f"{'='*60}")
    top_mfe = top20_df['future_mfe'].dropna()
    print(f"  样本数:   {len(top_mfe)}")
    print(f"  均值:     {top_mfe.mean():.2%}")
    print(f"  中位数:   {top_mfe.median():.2%}")
    print(f"  25分位:   {top_mfe.quantile(0.25):.2%}")
    print(f"  75分位:   {top_mfe.quantile(0.75):.2%}")
    print(f"  >0 占比:  {(top_mfe > 0).mean():.1%}")
    print(f"  >20% 占比: {(top_mfe > 0.20).mean():.1%}")

    # 6. 对比
    print(f"\n{'='*60}")
    print(f"  Top 20 vs 全量 MFE 对比")
    print(f"{'='*60}")
    lift = top_mfe.mean() - all_mfe.mean()
    print(f"  全量 MFE 均值:  {all_mfe.mean():.2%}")
    print(f"  Top20 MFE 均值: {top_mfe.mean():.2%}")
    print(f"  超额 MFE:       {lift:+.2%}")
    print(f"  提升比例:       {lift / all_mfe.mean():+.1%}" if all_mfe.mean() > 0 else "  基线MFE为负")
    ok = '✅ Top20 MFE > 全量' if lift > 0 else '❌ Top20 MFE ≤ 全量'
    print(f"  选股判定:       {ok}")

    # 7. 分数-MFE rank correlation
    valid = top20_df.dropna(subset=['future_mfe'])
    if len(valid) > 10:
        from scipy.stats import spearmanr
        corr_fine, p_fine = spearmanr(valid['fine_score'], valid['future_mfe'])
        corr_coarse, p_coarse = spearmanr(valid['coarse_score'], valid['future_mfe'])
        print(f"\n  精排分数-MFE Spearman r = {corr_fine:.4f} (p={p_fine:.4f})")
        print(f"  粗排分数-MFE Spearman r = {corr_coarse:.4f} (p={p_coarse:.4f})")
        corr_ok = '✅ 排序有效' if corr_fine > 0.05 else '❌ 排序无效'
        print(f"  排序判定: {corr_ok}")

    # 8. 纯持有到期收益 (无任何止损/止盈)
    print(f"\n[Step 3] 计算纯持有到期收益 (T+1 开盘买 → 第22天收盘卖) ...")
    hold_records = []
    for _, row in top20_df.iterrows():
        result = compute_hold_to_end_return(row['stock_code'], row['date'])
        if result is None:
            continue
        result['date'] = row['date']
        result['stock_code'] = row['stock_code']
        result['fine_score'] = row['fine_score']
        result['future_mfe'] = row['future_mfe']
        hold_records.append(result)

        if len(hold_records) % 500 == 0:
            print(f"  已计算 {len(hold_records)} 笔 ...")

    hold_df = pd.DataFrame(hold_records)
    hold_df['net_return'] = hold_df['hold_return'] - 2 * COMMISSION

    print(f"\n{'='*60}")
    print(f"  纯持有到期收益 (Top 20, 无止损无止盈)")
    print(f"{'='*60}")
    print(f"  样本数:         {len(hold_df)}")
    print(f"  平均收益:       {hold_df['net_return'].mean():+.2%}")
    print(f"  中位收益:       {hold_df['net_return'].median():+.2%}")
    print(f"  胜率:           {(hold_df['net_return'] > 0).mean():.1%}")
    print(f"  平均最大浮亏:   {hold_df['max_drawdown_in_path'].mean():.2%}")
    print(f"  平均 MFE:       {hold_df['future_mfe'].mean():.2%}")

    hold_ev = hold_df['net_return'].mean()
    hold_ok = '✅ 持有正期望' if hold_ev > 0 else '❌ 持有负期望'
    print(f"  持有判定:       {hold_ok}")

    # 9. 按月分组
    print(f"\n{'='*60}")
    print(f"  按月分组: MFE + 持有收益")
    print(f"{'='*60}")
    hold_df['month'] = pd.to_datetime(hold_df['date']).dt.to_period('M').astype(str)
    monthly = hold_df.groupby('month').agg(
        n=('net_return', 'count'),
        avg_mfe=('future_mfe', 'mean'),
        avg_hold=('net_return', 'mean'),
        wr=('net_return', lambda x: (x > 0).mean()),
        avg_dd=('max_drawdown_in_path', 'mean'),
    ).reset_index()

    print(f"  {'月份':<10} {'n':>5} {'avg_MFE':>10} {'avg_hold':>10} {'胜率':>8} {'avg_maxDD':>10}")
    print(f"  {'─'*10} {'─'*5} {'─'*10} {'─'*10} {'─'*8} {'─'*10}")
    for _, r in monthly.iterrows():
        print(f"  {r['month']:<10} {r['n']:>5} {r['avg_mfe']:>+10.2%} {r['avg_hold']:>+10.2%} "
              f"{r['wr']:>8.1%} {r['avg_dd']:>+10.2%}")

    # 10. 精排分数分组
    print(f"\n{'='*60}")
    print(f"  精排分数分组: Top 5 vs Top 6-10 vs Top 11-20")
    print(f"{'='*60}")
    hold_df['_rank_in_day'] = hold_df.groupby('date')['fine_score'].rank(ascending=False)
    for label, lo, hi in [('Top 5', 1, 5), ('Top 6-10', 6, 10), ('Top 11-20', 11, 20)]:
        sub = hold_df[(hold_df['_rank_in_day'] >= lo) & (hold_df['_rank_in_day'] <= hi)]
        if len(sub) > 0:
            print(f"  {label:<10} n={len(sub):>5}  MFE={sub['future_mfe'].mean():+.2%}  "
                  f"hold={sub['net_return'].mean():+.2%}  "
                  f"wr={((sub['net_return']>0).mean()):.1%}  "
                  f"maxDD={sub['max_drawdown_in_path'].mean():.2%}")

    # 11. 保存
    out_path = _proj('data', 'result', 'super_trend', 'pure_mfe_analysis.csv')
    hold_df.to_csv(out_path, index=False)
    print(f"\n详细数据已保存: {out_path}")


if __name__ == "__main__":
    main()
