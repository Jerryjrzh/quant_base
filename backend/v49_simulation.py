"""
V4.9 回测模拟 — 基于 full_calendar_trades_27m.csv
在已有4264笔交易上叠加 V4.9 改动:
  1. entry_pos > 0.5 过滤 (从CSV回测底/回测顶计算)
  2. TP=10% 统一
  3. 15天持仓 + 梯度时间衰减 (T+7 MFE<-5%, T+10 MFE<1%, T+15硬止)
对比 V4.7 基线。
"""
import os, sys, pandas as pd, numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_loader

CSV = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_27m.csv'
OUTPUT = '/home/hypnosis/data/quant_base/data/result/v49_simulated.csv'


def load_stock(code):
    p = data_loader._build_paths(code)
    f = p[1] if isinstance(p, tuple) and len(p) > 1 else p[0]
    if not os.path.exists(f):
        return None
    return data_loader.get_daily_data(f)


def sim_15d(daily, entry_date, entry_price, tp_pct=0.10, sl_pct=-0.10):
    """V4.9 模拟: 15天 + 梯度时间衰减"""
    ts = pd.Timestamp(entry_date)
    mask = daily.index >= ts
    if not mask.any():
        return None
    start = daily.index[mask][0]
    loc = daily.index.get_loc(start)

    tp_p = entry_price * (1 + tp_pct)
    sl_p = entry_price * (1 + sl_pct)

    mfe, mae = 0.0, 0.0
    end = min(loc + 21, len(daily))

    for i in range(loc, end):
        r = daily.iloc[i]
        dn = i - loc
        if dn == 0:
            continue

        h, l, c = float(r['high']), float(r['low']), float(r['close'])
        mfe = max(mfe, (h - entry_price) / entry_price)
        mae = min(mae, (l - entry_price) / entry_price)

        if l <= sl_p:
            return {'pnl': round((sl_p - entry_price) / entry_price, 4),
                    'exit_day': dn, 'exit_reason': '止损',
                    'mfe': round(mfe, 4), 'mae': round(mae, 4)}
        if h >= tp_p:
            return {'pnl': round((tp_p - entry_price) / entry_price, 4),
                    'exit_day': dn, 'exit_reason': '止盈',
                    'mfe': round(mfe, 4), 'mae': round(mae, 4)}

        # V4.9 梯度时间衰减
        if dn >= 7 and mfe < -0.05:
            return {'pnl': round((c - entry_price) / entry_price, 4),
                    'exit_day': dn, 'exit_reason': '时间衰减(MFE<-5%@T+7)',
                    'mfe': round(mfe, 4), 'mae': round(mae, 4)}
        if dn >= 10 and mfe < 0.01:
            return {'pnl': round((c - entry_price) / entry_price, 4),
                    'exit_day': dn, 'exit_reason': '时间衰减(MFE<1%@T+10)',
                    'mfe': round(mfe, 4), 'mae': round(mae, 4)}
        if dn >= 15:
            return {'pnl': round((c - entry_price) / entry_price, 4),
                    'exit_day': dn, 'exit_reason': '持仓到期',
                    'mfe': round(mfe, 4), 'mae': round(mae, 4)}

    # fallback
    last = min(loc + 15, len(daily) - 1)
    c = float(daily.iloc[last]['close'])
    return {'pnl': round((c - entry_price) / entry_price, 4),
            'exit_day': last - loc, 'exit_reason': '持仓到期',
            'mfe': round(mfe, 4), 'mae': round(mae, 4)}


def main():
    df = pd.read_csv(CSV)
    print(f"原始交易: {len(df)}")

    # === Step 1: 计算 entry_pos 并过滤 ===
    price_range = df['回测顶'] - df['回测底']
    df['entry_pos'] = np.where(
        price_range > 0,
        (df['trigger_buy'] - df['回测底']) / price_range,
        0.5
    )

    # V4.7 基线 (排除未成交)
    v47_executed = df[~df['交易状态'].isin(['挂单超时撤销', '大幅低开放弃'])].copy()
    v47_pnl = v47_executed['收益率'].sum()
    v47_count = len(v47_executed)

    print(f"\n{'='*80}")
    print("V4.7 基线")
    print(f"{'='*80}")
    print(f"  总信号: {len(df)}")
    print(f"  成交: {v47_count} ({v47_count/len(df):.1%})")
    print(f"  胜率: {(v47_executed['收益率']>0).mean():.1%}")
    print(f"  均收益: {v47_executed['收益率'].mean():+.2%}")
    print(f"  累计PnL: {v47_pnl:+.1f}%")
    print(f"  交易状态分布:")
    for s, c in v47_executed['交易状态'].value_counts().items():
        print(f"    {s}: {c}")

    # === Step 2: V4.9 entry_pos 过滤 ===
    ep_filtered = df[df['entry_pos'] > 0.5]
    ep_passed = df[df['entry_pos'] <= 0.5]
    print(f"\n{'='*80}")
    print(f"V4.9 entry_pos 过滤: 移除 {len(ep_filtered)} 笔 ({len(ep_filtered)/len(df):.1%})")
    print(f"  保留: {len(ep_passed)} 笔")
    print(f"  被过滤的信号特征:")
    ep_f_exec = ep_filtered[~ep_filtered['交易状态'].isin(['挂单超时撤销', '大幅低开放弃'])]
    if len(ep_f_exec) > 0:
        print(f"    成交: {len(ep_f_exec)}, 均收益: {ep_f_exec['收益率'].mean():+.2%}, "
              f"累计: {ep_f_exec['收益率'].sum():+.1f}%")

    # === Step 3: 对保留信号进行15天模拟 ===
    v49_trades = ep_passed[~ep_passed['交易状态'].isin(['挂单超时撤销', '大幅低开放弃'])].copy()
    need_resim = v49_trades[v49_trades['交易状态'].isin(['持仓到期', '时间衰减平仓'])]
    keep_as_is = v49_trades[~v49_trades['交易状态'].isin(['持仓到期', '时间衰减平仓'])]

    print(f"\n{'='*80}")
    print(f"V4.9 15天模拟")
    print(f"{'='*80}")
    print(f"  保留的成交信号: {len(v49_trades)}")
    print(f"  需要重新模拟 (到期): {len(need_resim)}")
    print(f"  保持不变 (TP/SL/其他): {len(keep_as_is)}")

    # Load stocks and re-simulate expired trades
    cache = {}
    resim_results = []
    failed = 0

    grouped = defaultdict(list)
    for idx, row in need_resim.iterrows():
        grouped[row['stock_code']].append((idx, row))

    for code, items in grouped.items():
        if code not in cache:
            cache[code] = load_stock(code)
        daily = cache[code]
        if daily is None:
            failed += len(items)
            continue
        for idx, row in items:
            # Determine SL based on board type
            board = '10CM'
            if code.startswith('30') or code.startswith('68') or code.startswith('92'):
                board = '20CM'
            sl = -0.07 if (row.get('v44_trend', '') == 'markup' and
                           row.get('v44_bias_tier', '') == '空头偏离(-15%~-5%)' and
                           board == '20CM') else (-0.12 if board == '20CM' else -0.10)

            r = sim_15d(daily, row['成交日期'], row['trigger_buy'],
                        tp_pct=0.10, sl_pct=sl)
            if r:
                resim_results.append({
                    'idx': idx, **r,
                    'stock_code': code,
                    'v44_trend': row.get('v44_trend', ''),
                })
            else:
                failed += 1

    print(f"  重新模拟完成: {len(resim_results)} 笔, 失败: {failed}")

    # === Step 4: 合并结果 ===
    v49_pnl_parts = []
    v49_details = []

    # 保持不变的 (TP/SL within 7 days)
    for _, row in keep_as_is.iterrows():
        v49_pnl_parts.append(row['收益率'])
        v49_details.append({
            'stock_code': row['stock_code'],
            '回测日期': row['回测日期'],
            '成交日期': row['成交日期'],
            '交易状态': row['交易状态'],
            'entry_pos': row['entry_pos'],
            'v44_trend': row.get('v44_trend', ''),
            'pnl': row['收益率'],
            'exit_day': row['持仓天数'],
            'exit_reason': row['交易状态'],
            'mfe': row['MFE'],
            'mae': row['MAE'],
        })

    # 重新模拟的
    for r in resim_results:
        v49_pnl_parts.append(r['pnl'])
        v49_details.append({
            'stock_code': r['stock_code'],
            '回测日期': need_resim.loc[r['idx'], '回测日期'],
            '成交日期': need_resim.loc[r['idx'], '成交日期'],
            '交易状态': r['exit_reason'],
            'entry_pos': need_resim.loc[r['idx'], 'entry_pos'],
            'v44_trend': r['v44_trend'],
            'pnl': r['pnl'],
            'exit_day': r['exit_day'],
            'exit_reason': r['exit_reason'],
            'mfe': r['mfe'],
            'mae': r['mae'],
        })

    v49_total_pnl = sum(v49_pnl_parts)
    v49_count = len(v49_pnl_parts)
    v49_wins = sum(1 for p in v49_pnl_parts if p > 0)

    # === Step 5: 对比报告 ===
    print(f"\n{'='*80}")
    print("V4.7 vs V4.9 全系统对比")
    print(f"{'='*80}")
    print(f"{'指标':<20} {'V4.7 基线':>15} {'V4.9':>15} {'变化':>12}")
    print(f"{'-'*65}")
    print(f"{'总信号':<20} {len(df):>15} {len(ep_passed):>15} {-len(ep_filtered):>+12}")
    print(f"{'成交笔数':<20} {v47_count:>15} {v49_count:>15} {v49_count-v47_count:>+12}")
    print(f"{'胜率':<20} {(v47_executed['收益率']>0).mean():>14.1%} {v49_wins/v49_count:>14.1%} "
          f"{v49_wins/v49_count - (v47_executed['收益率']>0).mean():>+11.1%}")
    v47_avg = v47_executed['收益率'].mean()
    v49_avg = v49_total_pnl / v49_count if v49_count > 0 else 0
    print(f"{'均收益':<20} {v47_avg:>+14.2%} {v49_avg:>+14.2%} {v49_avg-v47_avg:>+11.2%}")
    print(f"{'累计PnL':<20} {v47_pnl:>+14.1f}% {v49_total_pnl:>+14.1f}% {v49_total_pnl-v47_pnl:>+11.1f}%")

    # 到期交易对比
    v47_expired = v47_executed[v47_executed['交易状态'].isin(['持仓到期', '时间衰减平仓'])]
    v49_resim_df = pd.DataFrame([r for r in resim_results])
    if len(v49_resim_df) > 0:
        print(f"\n{'='*80}")
        print("到期交易对比 (仅重新模拟部分)")
        print(f"{'='*80}")
        print(f"{'指标':<20} {'V4.7':>12} {'V4.9':>12}")
        print(f"{'-'*48}")
        print(f"{'笔数':<20} {len(v47_expired):>12} {len(v49_resim_df):>12}")
        print(f"{'胜率':<20} {(v47_expired['收益率']>0).mean():>11.1%} {(v49_resim_df['pnl']>0).mean():>11.1%}")
        print(f"{'均收益':<20} {v47_expired['收益率'].mean():>+11.2%} {v49_resim_df['pnl'].mean():>+11.2%}")
        print(f"{'累计PnL':<20} {v47_expired['收益率'].sum():>+11.1f}% {v49_resim_df['pnl'].sum():>+11.1f}%")

        print(f"\n  V4.9 出场分布:")
        for reason in v49_resim_df['exit_reason'].value_counts().index:
            sub = v49_resim_df[v49_resim_df['exit_reason'] == reason]
            print(f"    {reason}: {len(sub)}笔 ({len(sub)/len(v49_resim_df):.1%}), "
                  f"胜率 {(sub['pnl']>0).mean():.1%}, 均收益 {sub['pnl'].mean():+.2%}, "
                  f"平均天数 {sub['exit_day'].mean():.1f}")

    # 按趋势分组
    print(f"\n{'='*80}")
    print("按趋势阶段分组")
    print(f"{'='*80}")
    v49_df = pd.DataFrame(v49_details)
    for trend in ['accumulation', 'markup']:
        v47_sub = v47_executed[v47_executed['v44_trend'] == trend]
        v49_sub = v49_df[v49_df['v44_trend'] == trend]
        if len(v47_sub) == 0 or len(v49_sub) == 0:
            continue
        print(f"\n  [{trend}]")
        print(f"    V4.7: {len(v47_sub)}笔, 胜率 {(v47_sub['收益率']>0).mean():.1%}, "
              f"均收益 {v47_sub['收益率'].mean():+.2%}, 累计 {v47_sub['收益率'].sum():+.1f}%")
        print(f"    V4.9: {len(v49_sub)}笔, 胜率 {(v49_sub['pnl']>0).mean():.1%}, "
              f"均收益 {v49_sub['pnl'].mean():+.2%}, 累计 {v49_sub['pnl'].sum():+.1f}%")

    # Save
    v49_df.to_csv(OUTPUT, index=False, float_format='%.4f')
    print(f"\nV4.9 模拟结果已保存: {OUTPUT}")


if __name__ == '__main__':
    main()
