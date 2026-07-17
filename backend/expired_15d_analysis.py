"""
持仓到期后续15日表现分析
分析 full_calendar_trades_27m.csv 中持仓到期/时间衰减平仓的股票，
在卖出日期后15个交易日内的 MFE/MAE/收益率/是否触及10%止盈。
"""
import os
import sys
import pandas as pd
import numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_loader

CSV_PATH = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_27m.csv'
OUTPUT_PATH = '/home/hypnosis/data/quant_base/data/result/expired_15d_analysis.csv'

def load_stock_daily(stock_code):
    paths = data_loader._build_paths(stock_code)
    day_file = paths[1] if isinstance(paths, tuple) and len(paths) > 1 else paths[0]
    if not os.path.exists(day_file):
        return None
    return data_loader.get_daily_data(day_file)

def analyze_expired_trades():
    df = pd.read_csv(CSV_PATH)
    expired = df[df['交易状态'].isin(['持仓到期', '时间衰减平仓'])].copy()
    print(f"总交易: {len(df)}, 持仓到期: {len(expired)}")

    grouped = defaultdict(list)
    for idx, row in expired.iterrows():
        grouped[row['stock_code']].append(row)
    print(f"涉及 {len(grouped)} 只个股")

    results = []
    loaded = 0
    failed = 0

    for stock_code, trades in grouped.items():
        daily = load_stock_daily(stock_code)
        if daily is None:
            failed += len(trades)
            continue
        loaded += 1

        for trade in trades:
            sell_date = trade['卖出日期']
            entry_price = trade['trigger_buy']
            exit_pnl = trade['收益率']

            if sell_date not in daily.index.astype(str).str[:10].values:
                sell_ts = pd.Timestamp(sell_date)
                mask = daily.index >= sell_ts
                if not mask.any():
                    continue
                sell_idx = daily.index[mask][0]
            else:
                sell_idx = pd.Timestamp(sell_date)

            if sell_idx not in daily.index:
                continue

            loc = daily.index.get_loc(sell_idx)
            exit_close = float(daily.iloc[loc]['close'])

            future_end = min(loc + 16, len(daily))
            if future_end <= loc + 1:
                continue

            future_slice = daily.iloc[loc + 1:future_end]
            if len(future_slice) == 0:
                continue

            actual_days = len(future_slice)
            future_highs = future_slice['high'].values
            future_lows = future_slice['low'].values
            future_closes = future_slice['close'].values

            max_high = float(future_highs.max())
            min_low = float(future_lows.min())

            mfe_15d = (max_high - exit_close) / exit_close
            mae_15d = (min_low - exit_close) / exit_close
            final_return = (float(future_closes[-1]) - exit_close) / exit_close

            tp_hit_day = -1
            sl_hit_day = -1
            tp_level = exit_close * 1.10
            sl_level = exit_close * 0.90

            for d in range(actual_days):
                if tp_hit_day < 0 and float(future_highs[d]) >= tp_level:
                    tp_hit_day = d + 1
                if sl_hit_day < 0 and float(future_lows[d]) <= sl_level:
                    sl_hit_day = d + 1

            would_tp10 = tp_hit_day > 0 and (sl_hit_day < 0 or tp_hit_day < sl_hit_day)
            would_sl10 = sl_hit_day > 0 and (tp_hit_day < 0 or sl_hit_day < tp_hit_day)

            entry_from_exit = (exit_close - entry_price) / entry_price
            total_mfe_from_entry = (max_high - entry_price) / entry_price
            total_return_from_entry = (float(future_closes[-1]) - entry_price) / entry_price

            results.append({
                'stock_code': trade['stock_code'],
                '回测日期': trade['回测日期'],
                '成交日期': trade['成交日期'],
                '卖出日期': sell_date,
                '交易状态': trade['交易状态'],
                'entry_price': round(entry_price, 3),
                'exit_close': round(exit_close, 3),
                'exit_pnl': round(exit_pnl, 4),
                'v44_trend': trade.get('v44_trend', ''),
                'v44_bias_tier': trade.get('v44_bias_tier', ''),
                'gbm_proba': trade.get('gbm_proba', 0),
                'pricing_proba': trade.get('pricing_proba', 0.5),
                'future_days': actual_days,
                'mfe_15d': round(mfe_15d, 4),
                'mae_15d': round(mae_15d, 4),
                'return_15d': round(final_return, 4),
                'tp_hit_day': tp_hit_day,
                'sl_hit_day': sl_hit_day,
                'would_tp10': would_tp10,
                'would_sl10': would_sl10,
                'total_mfe_from_entry': round(total_mfe_from_entry, 4),
                'total_return_from_entry': round(total_return_from_entry, 4),
            })

    print(f"加载 {loaded} 只, 分析 {len(results)} 笔, 数据缺失 {failed} 笔")
    return pd.DataFrame(results)


def print_report(df):
    print("\n" + "=" * 80)
    print("持仓到期后续15日表现分析")
    print("=" * 80)
    print(f"分析样本: {len(df)} 笔持仓到期交易")

    print(f"\n--- 整体统计 (卖出后15个交易日) ---")
    print(f"  后续 MFE 均值:   {df['mfe_15d'].mean():+.2%}")
    print(f"  后续 MFE 中位数: {df['mfe_15d'].median():+.2%}")
    print(f"  后续 MAE 均值:   {df['mae_15d'].mean():+.2%}")
    print(f"  后续 MAE 中位数: {df['mae_15d'].median():+.2%}")
    print(f"  后续15日收益率均值:   {df['return_15d'].mean():+.2%}")
    print(f"  后续15日收益率中位数: {df['return_15d'].median():+.2%}")
    print(f"  后续上涨比例: {(df['return_15d'] > 0).mean():.1%}")

    tp_count = df['would_tp10'].sum()
    sl_count = df['would_sl10'].sum()
    neither = len(df) - tp_count - sl_count
    print(f"\n--- 假设继续持有 (TP=10%, SL=10%) ---")
    print(f"  触及+10%止盈: {tp_count} ({tp_count/len(df):.1%})")
    print(f"  触及-10%止损: {sl_count} ({sl_count/len(df):.1%})")
    print(f"  两者均未触及: {neither} ({neither/len(df):.1%})")
    if tp_count > 0:
        avg_tp_day = df[df['would_tp10']]['tp_hit_day'].mean()
        print(f"  止盈平均天数: {avg_tp_day:.1f}")

    print(f"\n--- 到期时盈亏分布 ---")
    print(f"  到期时亏损: {(df['exit_pnl'] < 0).sum()} ({(df['exit_pnl'] < 0).mean():.1%})")
    print(f"  到期时盈利: {(df['exit_pnl'] >= 0).sum()} ({(df['exit_pnl'] >= 0).mean():.1%})")

    for label, sub in [('到期亏损', df[df['exit_pnl'] < 0]), ('到期盈利', df[df['exit_pnl'] >= 0])]:
        if len(sub) == 0:
            continue
        tp_c = sub['would_tp10'].sum()
        sl_c = sub['would_sl10'].sum()
        print(f"\n  [{label}] {len(sub)}笔:")
        print(f"    后续 MFE:   {sub['mfe_15d'].mean():+.2%} (中位数 {sub['mfe_15d'].median():+.2%})")
        print(f"    后续 MAE:   {sub['mae_15d'].mean():+.2%}")
        print(f"    后续收益率: {sub['return_15d'].mean():+.2%} (中位数 {sub['return_15d'].median():+.2%})")
        print(f"    后续触及TP: {tp_c} ({tp_c/len(sub):.1%})")
        print(f"    后续触及SL: {sl_c} ({sl_c/len(sub):.1%})")

    print(f"\n--- 按趋势阶段分组 ---")
    for trend in ['accumulation', 'markup', 'decline', 'distribution']:
        sub = df[df['v44_trend'] == trend]
        if len(sub) == 0:
            continue
        tp_c = sub['would_tp10'].sum()
        sl_c = sub['would_sl10'].sum()
        print(f"\n  [{trend}] {len(sub)}笔:")
        print(f"    后续 MFE:   {sub['mfe_15d'].mean():+.2%} (中位数 {sub['mfe_15d'].median():+.2%})")
        print(f"    后续 MAE:   {sub['mae_15d'].mean():+.2%}")
        print(f"    后续收益率: {sub['return_15d'].mean():+.2%}")
        print(f"    触及TP: {tp_c} ({tp_c/len(sub):.1%}), 触及SL: {sl_c} ({sl_c/len(sub):.1%})")

    print(f"\n--- 按到期时MFE分组 ---")
    bins = [(-1, 0.01), (0.01, 0.03), (0.03, 0.05), (0.05, 0.08), (0.08, 1.0)]
    for lo, hi in bins:
        sub = df[(df['exit_pnl'] >= lo) & (df['exit_pnl'] < hi)]
        if len(sub) < 10:
            continue
        tp_c = sub['would_tp10'].sum()
        print(f"\n  [到期收益 {lo:+.0%}~{hi:+.0%}] {len(sub)}笔:")
        print(f"    后续 MFE: {sub['mfe_15d'].mean():+.2%}, 后续收益率: {sub['return_15d'].mean():+.2%}")
        print(f"    触及TP: {tp_c} ({tp_c/len(sub):.1%})")

    print(f"\n--- 从入场价计算的总 MFE (含持仓期+后续15日) ---")
    print(f"  总MFE均值:   {df['total_mfe_from_entry'].mean():+.2%}")
    print(f"  总MFE中位数: {df['total_mfe_from_entry'].median():+.2%}")
    print(f"  总MFE>10%:   {(df['total_mfe_from_entry'] > 0.10).sum()} ({(df['total_mfe_from_entry'] > 0.10).mean():.1%})")
    print(f"  总MFE>15%:   {(df['total_mfe_from_entry'] > 0.15).sum()} ({(df['total_mfe_from_entry'] > 0.15).mean():.1%})")
    print(f"  总MFE>20%:   {(df['total_mfe_from_entry'] > 0.20).sum()} ({(df['total_mfe_from_entry'] > 0.20).mean():.1%})")

    print(f"\n--- 关键发现 ---")
    high_mfe_low_ret = df[(df['mfe_15d'] > 0.10) & (df['return_15d'] < 0.02)]
    print(f"  后续MFE>10% 但15日收益<2%: {len(high_mfe_low_ret)} ({len(high_mfe_low_ret)/len(df):.1%}) → 冲高回落")
    
    quick_reversal = df[(df['exit_pnl'] < -0.02) & (df['return_15d'] > 0.05)]
    print(f"  到期亏>2% 但后续涨>5%: {len(quick_reversal)} ({len(quick_reversal)/len(df):.1%}) → 洗盘反转")
    
    continued_drop = df[(df['exit_pnl'] < 0) & (df['return_15d'] < -0.05)]
    print(f"  到期亏损 且后续跌>5%: {len(continued_drop)} ({len(continued_drop)/len(df):.1%}) → 正确止损")


if __name__ == '__main__':
    result_df = analyze_expired_trades()
    if len(result_df) > 0:
        result_df.to_csv(OUTPUT_PATH, index=False, float_format='%.4f')
        print(f"\n结果已保存: {OUTPUT_PATH}")
        print_report(result_df)
