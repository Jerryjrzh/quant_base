"""
持仓到期优化方案回测
对2636笔到期交易分别模拟4种方案:
  A: 延长持仓至15天 (固定TP/SL)
  B: 条件续持 (markup + MFE>1% + gbm>=0.65)
  C: 阶梯时间止损 (收益>3%平仓, <3%续持)
  D: 动态追踪止盈 (回撤5%平仓, SL入场×0.90, 最长20天)
  基线: 当前7天到期
"""
import os, sys, json
import pandas as pd
import numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_loader

CSV_PATH = '/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades_27m.csv'
FULL_CSV = CSV_PATH
OUTPUT_DIR = '/home/hypnosis/data/quant_base/data/result'

def load_stock_daily(stock_code):
    paths = data_loader._build_paths(stock_code)
    day_file = paths[1] if isinstance(paths, tuple) and len(paths) > 1 else paths[0]
    if not os.path.exists(day_file):
        return None
    return data_loader.get_daily_data(day_file)


def simulate_trade(daily_df, entry_date_str, entry_price, tp_pct, sl_pct,
                   max_days=7, trailing_trigger=None, trailing_keep=None):
    """
    模拟单笔交易, 返回详细结果。
    daily_df: 完整日线 DataFrame (DatetimeIndex)
    entry_date_str: 成交日期 (T+1, 入场日)
    entry_price: 入场价
    tp_pct, sl_pct: 止盈止损百分比 (如 0.10, -0.10)
    max_days: 最长持仓天数
    trailing_trigger: 追踪止损触发 (如 0.05 = 浮盈5%后启动)
    trailing_keep: 追踪止损保持 (如 0.40 = 从最高点回撤40%触发)
    """
    entry_ts = pd.Timestamp(entry_date_str)
    mask = daily_df.index >= entry_ts
    if not mask.any():
        return None

    start_idx = daily_df.index[mask][0]
    loc = daily_df.index.get_loc(start_idx)

    tp_price = entry_price * (1 + tp_pct)
    sl_price = entry_price * (1 + sl_pct)

    peak_price = entry_price
    trailing_active = False
    trailing_stop = sl_price

    mfe = 0.0
    mae = 0.0
    exit_price = 0.0
    exit_day = 0
    exit_reason = '时间到期'

    end_loc = min(loc + max_days + 1, len(daily_df))

    for d in range(loc, end_loc):
        row = daily_df.iloc[d]
        day_num = d - loc  # 0 = entry day (T+1)
        if day_num == 0:
            continue  # skip entry day itself, start from T+2

        h = float(row['high'])
        l = float(row['low'])
        c = float(row['close'])

        pnl_h = (h - entry_price) / entry_price
        pnl_l = (l - entry_price) / entry_price
        pnl_c = (c - entry_price) / entry_price

        mfe = max(mfe, pnl_h)
        mae = min(mae, pnl_l)

        # Check SL first (pessimistic)
        if l <= sl_price:
            exit_price = sl_price
            exit_day = day_num
            exit_reason = '止损'
            break

        # Check TP
        if h >= tp_price:
            exit_price = tp_price
            exit_day = day_num
            exit_reason = '止盈'
            break

        # Trailing stop logic
        if trailing_trigger is not None:
            if pnl_h >= trailing_trigger:
                trailing_active = True
            if trailing_active:
                peak_price = max(peak_price, h)
                new_trailing_stop = peak_price * (1 - trailing_keep)
                trailing_stop = max(trailing_stop, new_trailing_stop)
                if l <= trailing_stop:
                    exit_price = trailing_stop
                    exit_day = day_num
                    exit_reason = '追踪止损'
                    break

    else:
        # Time stop: close at last available day's close
        last_d = min(loc + max_days, len(daily_df) - 1)
        exit_price = float(daily_df.iloc[last_d]['close'])
        exit_day = last_d - loc
        exit_reason = '时间到期'

    final_pnl = (exit_price - entry_price) / entry_price

    return {
        'exit_price': round(exit_price, 3),
        'exit_day': exit_day,
        'exit_reason': exit_reason,
        'pnl': round(final_pnl, 4),
        'mfe': round(mfe, 4),
        'mae': round(mae, 4),
    }


def run_backtest():
    df = pd.read_csv(FULL_CSV)
    expired = df[df['交易状态'].isin(['持仓到期', '时间衰减平仓'])].copy()
    print(f"到期交易: {len(expired)} 笔")

    grouped = defaultdict(list)
    for idx, row in expired.iterrows():
        grouped[row['stock_code']].append(row)

    # Also load non-expired executed trades for baseline total PnL
    executed = df[~df['交易状态'].isin(['挂单超时撤销', '大幅低开放弃'])].copy()
    non_expired_executed = executed[~executed['交易状态'].isin(['持仓到期', '时间衰减平仓'])]
    baseline_other_pnl = non_expired_executed['收益率'].sum()
    baseline_other_count = len(non_expired_executed)
    print(f"非到期成交: {baseline_other_count} 笔, 累计PnL: {baseline_other_pnl:+.2f}%")

    stock_cache = {}
    results = {
        'baseline': [],  # 当前7天
        'A_extend15': [],  # 延长至15天
        'B_conditional': [],  # 条件续持
        'C_ladder': [],  # 阶梯时间止损
        'D_trailing': [],  # 动态追踪止盈
    }

    loaded = 0
    skipped = 0

    for stock_code, trades in grouped.items():
        if stock_code not in stock_cache:
            daily = load_stock_daily(stock_code)
            stock_cache[stock_code] = daily
        daily = stock_cache[stock_code]
        if daily is None:
            skipped += len(trades)
            continue
        loaded += 1

        for trade in trades:
            entry_date = trade['成交日期']
            entry_price = trade['trigger_buy']
            sell_date = trade['卖出日期']
            v44_trend = trade.get('v44_trend', '')
            gbm_proba = trade.get('gbm_proba', 0)
            exit_pnl_orig = trade['收益率']
            trade_mfe = trade.get('MFE', 0)

            # --- Baseline (current 7-day) ---
            r_base = simulate_trade(daily, entry_date, entry_price,
                                    tp_pct=0.10, sl_pct=-0.10, max_days=7)
            if r_base is None:
                skipped += 1
                continue

            results['baseline'].append({**r_base, 'stock_code': stock_code,
                                        '回测日期': trade['回测日期'],
                                        'v44_trend': v44_trend,
                                        'gbm_proba': gbm_proba,
                                        'orig_exit_pnl': exit_pnl_orig})

            # --- A: 延长至15天 ---
            r_a = simulate_trade(daily, entry_date, entry_price,
                                 tp_pct=0.10, sl_pct=-0.10, max_days=15)
            results['A_extend15'].append({**r_a, 'stock_code': stock_code,
                                          'v44_trend': v44_trend})

            # --- B: 条件续持 ---
            # 条件: markup + MFE>1% + gbm>=0.65
            should_extend_b = (v44_trend == 'markup' and
                               trade_mfe > 0.01 and
                               gbm_proba >= 0.65)
            if should_extend_b:
                r_b = simulate_trade(daily, entry_date, entry_price,
                                     tp_pct=0.10, sl_pct=-0.10, max_days=15)
            else:
                r_b = r_base  # 不满足条件, 保持7天
            results['B_conditional'].append({**r_b, 'stock_code': stock_code,
                                             'v44_trend': v44_trend,
                                             'extended': should_extend_b})

            # --- C: 阶梯时间止损 ---
            # 第7天: 收益>3%平仓, <3%续持至14天
            if r_base['exit_reason'] == '时间到期':
                pnl_at_7d = r_base['pnl']
                if pnl_at_7d >= 0.03:
                    r_c = r_base  # 收益不错, 锁定
                else:
                    r_c = simulate_trade(daily, entry_date, entry_price,
                                         tp_pct=0.10, sl_pct=-0.10, max_days=14)
            else:
                r_c = r_base  # 已TP/SL, 不变
            results['C_ladder'].append({**r_c, 'stock_code': stock_code,
                                        'v44_trend': v44_trend})

            # --- D: 动态追踪止盈 ---
            # 7天内正常TP/SL, 到期后改为追踪止损
            # 先跑7天, 如果到期则从第7天开始追踪
            if r_base['exit_reason'] == '时间到期':
                # 获取第7天后的数据继续模拟
                entry_ts = pd.Timestamp(entry_date)
                mask = daily.index >= entry_ts
                if mask.any():
                    start_loc = daily.index.get_loc(daily.index[mask][0])
                    day7_loc = min(start_loc + 7, len(daily) - 1)
                    close_at_7d = float(daily.iloc[day7_loc]['close'])

                    # 前7天的MFE
                    peak_7d = entry_price * (1 + r_base['mfe'])

                    # 从第8天开始追踪 (trigger=0%, keep=5%回撤)
                    r_d_extra = simulate_trade(daily,
                                               daily.index[day7_loc + 1].strftime('%Y-%m-%d') if day7_loc + 1 < len(daily) else daily.index[day7_loc].strftime('%Y-%m-%d'),
                                               entry_price,
                                               tp_pct=999,  # 不设TP, 纯追踪
                                               sl_pct=-0.10,  # 硬止损入场×0.90
                                               max_days=13,  # 总共20天
                                               trailing_trigger=0.0,
                                               trailing_keep=0.05)
                    if r_d_extra and r_d_extra['exit_reason'] != '时间到期':
                        r_d = {
                            'exit_price': r_d_extra['exit_price'],
                            'exit_day': 7 + r_d_extra['exit_day'],
                            'exit_reason': r_d_extra['exit_reason'],
                            'pnl': r_d_extra['pnl'],
                            'mfe': max(r_base['mfe'], r_d_extra['mfe']),
                            'mae': min(r_base['mae'], r_d_extra['mae']),
                        }
                    else:
                        # 追踪也没触发, 20天到期
                        r_d_full = simulate_trade(daily, entry_date, entry_price,
                                                  tp_pct=999, sl_pct=-0.10,
                                                  max_days=20,
                                                  trailing_trigger=0.0,
                                                  trailing_keep=0.05)
                        r_d = r_d_full if r_d_full else r_base
                else:
                    r_d = r_base
            else:
                r_d = r_base
            results['D_trailing'].append({**r_d, 'stock_code': stock_code,
                                          'v44_trend': v44_trend})

    print(f"\n加载 {loaded} 只, 跳过 {skipped} 笔")

    # Convert to DataFrames
    dfs = {}
    for name, records in results.items():
        dfs[name] = pd.DataFrame(records)

    return dfs, baseline_other_pnl, baseline_other_count


def print_comparison(dfs, baseline_other_pnl, baseline_other_count):
    print("\n" + "=" * 90)
    print("持仓到期优化方案回测对比")
    print("=" * 90)

    schemes = [
        ('baseline', '基线 (7天到期)'),
        ('A_extend15', 'A: 延长至15天'),
        ('B_conditional', 'B: 条件续持'),
        ('C_ladder', 'C: 阶梯时间止损'),
        ('D_trailing', 'D: 动态追踪止盈'),
    ]

    # === 到期交易对比 ===
    print(f"\n{'─' * 90}")
    print(f"{'方案':<22} {'笔数':>6} {'胜率':>8} {'均收益':>8} {'累计PnL':>10} {'EV':>8} "
          f"{'止盈':>6} {'止损':>6} {'到期':>6} {'追踪':>6}")
    print(f"{'─' * 90}")

    for key, label in schemes:
        d = dfs[key]
        n = len(d)
        wins = (d['pnl'] > 0).sum()
        wr = wins / n if n > 0 else 0
        avg_pnl = d['pnl'].mean()
        total_pnl = d['pnl'].sum()
        ev = avg_pnl

        tp_n = (d['exit_reason'] == '止盈').sum()
        sl_n = (d['exit_reason'] == '止损').sum()
        exp_n = (d['exit_reason'] == '时间到期').sum()
        trail_n = (d['exit_reason'] == '追踪止损').sum()

        print(f"{label:<22} {n:>6} {wr:>7.1%} {avg_pnl:>+7.2%} {total_pnl:>+9.1f}% "
              f"{ev:>+7.2%} {tp_n:>6} {sl_n:>6} {exp_n:>6} {trail_n:>6}")

    # === 全系统对比 (含非到期交易) ===
    print(f"\n{'─' * 90}")
    print("全系统对比 (到期方案 + 非到期交易)")
    print(f"{'─' * 90}")
    print(f"{'方案':<22} {'总笔数':>8} {'总PnL':>12} {'到期PnL':>12} {'到期胜率':>8} {'到期EV':>8} "
          f"{'ΔPnL':>10}")
    print(f"{'─' * 90}")

    base_total_pnl = baseline_other_pnl + dfs['baseline']['pnl'].sum()
    for key, label in schemes:
        d = dfs[key]
        total = baseline_other_pnl + d['pnl'].sum()
        expired_pnl = d['pnl'].sum()
        expired_wr = (d['pnl'] > 0).mean()
        expired_ev = d['pnl'].mean()
        delta = total - base_total_pnl
        total_count = baseline_other_count + len(d)

        print(f"{label:<22} {total_count:>8} {total:>+11.1f}% {expired_pnl:>+11.1f}% "
              f"{expired_wr:>7.1%} {expired_ev:>+7.2%} {delta:>+9.1f}%")

    # === 按趋势分组 ===
    print(f"\n{'─' * 90}")
    print("按趋势阶段分组 (到期交易)")
    print(f"{'─' * 90}")

    for trend in ['accumulation', 'markup']:
        print(f"\n  [{trend}]")
        print(f"  {'方案':<22} {'笔数':>6} {'胜率':>8} {'均收益':>8} {'累计PnL':>10}")
        for key, label in schemes:
            d = dfs[key]
            sub = d[d['v44_trend'] == trend] if 'v44_trend' in d.columns else pd.DataFrame()
            if len(sub) == 0:
                continue
            n = len(sub)
            wr = (sub['pnl'] > 0).mean()
            avg = sub['pnl'].mean()
            total = sub['pnl'].sum()
            print(f"  {label:<22} {n:>6} {wr:>7.1%} {avg:>+7.2%} {total:>+9.1f}%")

    # === 方案B详细 ===
    if 'extended' in dfs['B_conditional'].columns:
        b = dfs['B_conditional']
        ext = b[b['extended'] == True]
        noext = b[b['extended'] == False]
        print(f"\n{'─' * 90}")
        print("方案B 条件续持详情")
        print(f"{'─' * 90}")
        print(f"  续持: {len(ext)}笔, 胜率 {(ext['pnl']>0).mean():.1%}, "
              f"均收益 {ext['pnl'].mean():+.2%}, 累计 {ext['pnl'].sum():+.1f}%")
        print(f"  不续: {len(noext)}笔, 胜率 {(noext['pnl']>0).mean():.1%}, "
              f"均收益 {noext['pnl'].mean():+.2%}, 累计 {noext['pnl'].sum():+.1f}%")

    # === 方案D出场分布 ===
    d_df = dfs['D_trailing']
    print(f"\n{'─' * 90}")
    print("方案D 动态追踪止盈 出场分布")
    print(f"{'─' * 90}")
    for reason in ['止盈', '止损', '追踪止损', '时间到期']:
        sub = d_df[d_df['exit_reason'] == reason]
        if len(sub) == 0:
            continue
        print(f"  {reason}: {len(sub)}笔 ({len(sub)/len(d_df):.1%}), "
              f"胜率 {(sub['pnl']>0).mean():.1%}, 均收益 {sub['pnl'].mean():+.2%}, "
              f"平均天数 {sub['exit_day'].mean():.1f}")

    # === MFE/MAE 对比 ===
    print(f"\n{'─' * 90}")
    print("MFE / MAE 对比")
    print(f"{'─' * 90}")
    for key, label in schemes:
        d = dfs[key]
        print(f"  {label:<22} MFE均值={d['mfe'].mean():+.2%}  MAE均值={d['mae'].mean():+.2%}")


if __name__ == '__main__':
    dfs, other_pnl, other_count = run_backtest()
    print_comparison(dfs, other_pnl, other_count)

    # Save per-scheme results
    for name, d in dfs.items():
        path = os.path.join(OUTPUT_DIR, f'expired_scheme_{name}.csv')
        d.to_csv(path, index=False, float_format='%.4f')
    print(f"\n各方案明细已保存至 {OUTPUT_DIR}/expired_scheme_*.csv")
