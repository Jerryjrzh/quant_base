#!/usr/bin/env python3
"""
入场/出场价格参数扫描器
基于 future_7d_path 逐日 H/L 数据，扫描入场折扣、止盈、止损、追踪止损参数组合。

用法:
    cd backend
    python3 price_param_sweeper.py
"""

import pandas as pd
import numpy as np
import os
from itertools import product

CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'result',
                        'Calendar_Backtest', 'full_calendar_trades.csv')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'result',
                           'price_sweep_results.csv')


def parse_path(path_str):
    if pd.isna(path_str) or not isinstance(path_str, str) or 'H:' not in path_str:
        return None
    days = []
    for seg in path_str.split(' -> '):
        if '/L:' not in seg:
            continue
        h = float(seg.split('H:')[1].split('%')[0]) / 100.0
        l = float(seg.split('/L:')[1].split('%')[0]) / 100.0
        days.append((h, l))
    return days if days else None


def estimate_t0_close(trigger_buy):
    return trigger_buy / 0.95


def categorize_board(stock_code):
    s = str(stock_code).lower()
    n = ''.join(c for c in s if c.isdigit())
    if n.startswith('300'):
        return '20CM'
    elif n.startswith('688'):
        return '20CM'
    elif s.startswith('bj') or n.startswith('920'):
        return '30CM'
    return '10CM'


def simulate_trade(path, t0_close, entry_disc, tp_pct, sl_pct,
                   trail_trigger=999, trail_keep=0.6, time_stop=99):
    entry = t0_close * (1.0 + entry_disc)
    tp_price = entry * (1.0 + tp_pct)
    sl_price = entry * (1.0 + sl_pct)

    mfe = 0.0
    mae = 0.0

    for i, (h_pct, l_pct) in enumerate(path):
        day_high = t0_close * (1.0 + h_pct)
        day_low = t0_close * (1.0 + l_pct)
        day_mid = (day_high + day_low) / 2.0

        pnl_high = (day_high - entry) / entry
        pnl_low = (day_low - entry) / entry
        if pnl_high > mfe:
            mfe = pnl_high
        if pnl_low < mae:
            mae = pnl_low

        hit_sl = day_low <= sl_price
        hit_tp = day_high >= tp_price

        if hit_sl and hit_tp:
            sl_depth = sl_price - day_low
            tp_depth = day_high - tp_price
            if sl_depth > tp_depth:
                hit_tp = False
            else:
                hit_sl = False

        if hit_sl:
            exit_p = min(day_mid, sl_price)
            pnl = (exit_p - entry) / entry
            return {'pnl': pnl, 'filled': True, 'status': '止损',
                    'mfe': mfe, 'mae': mae, 'days': i + 1}

        if hit_tp:
            exit_p = max(day_mid, tp_price)
            pnl = (exit_p - entry) / entry
            return {'pnl': pnl, 'filled': True, 'status': '止盈',
                    'mfe': mfe, 'mae': mae, 'days': i + 1}

        if mfe >= trail_trigger:
            trail_sl = entry * (1.0 + mfe * trail_keep)
            if trail_sl > sl_price:
                sl_price = trail_sl

        day_idx = i + 1
        if day_idx >= time_stop and mfe < 0.01:
            pnl = (day_mid - entry) / entry
            return {'pnl': pnl, 'filled': True, 'status': '时间衰减',
                    'mfe': mfe, 'mae': mae, 'days': day_idx}

    last_h, last_l = path[-1]
    last_mid = t0_close * (1.0 + (last_h + last_l) / 2.0)
    pnl = (last_mid - entry) / entry
    return {'pnl': pnl, 'filled': True, 'status': '持仓到期',
            'mfe': mfe, 'mae': mae, 'days': len(path)}


def check_fill(path, t0_close, entry_disc):
    entry = t0_close * (1.0 + entry_disc)
    for h_pct, l_pct in path:
        day_low = t0_close * (1.0 + l_pct)
        day_high = t0_close * (1.0 + h_pct)
        approx_close = (day_high + day_low) / 2.0
        if day_low <= entry and approx_close >= entry * 0.995:
            return True
    return False


def run_phase1(df, parsed_paths):
    print("\n" + "=" * 60)
    print("Phase 1: 入场折扣 × 止盈 × 止损 扫描 (trailing=off, time_stop=7)")
    print("=" * 60)

    entry_discs = [0.0, -0.01, -0.02, -0.03, -0.04, -0.05, -0.06, -0.08, -0.10]
    tp_pcts = [0.08, 0.10, 0.12, 0.15, 0.18, 0.22, 0.25]
    sl_pcts = [-0.04, -0.05, -0.06, -0.07, -0.08, -0.10]

    t0s = df['_t0_close'].values
    n = len(df)
    results = []

    for disc in entry_discs:
        fills = np.array([check_fill(p, t0s[i], disc) for i, p in enumerate(parsed_paths)])
        fill_rate = fills.sum() / n

        for tp, sl in product(tp_pcts, sl_pcts):
            if tp <= abs(sl) * 0.5:
                continue

            pnls = []
            filled_count = 0
            for i, p in enumerate(parsed_paths):
                if not fills[i]:
                    continue
                res = simulate_trade(p, t0s[i], disc, tp, sl)
                if res['filled']:
                    filled_count += 1
                    pnls.append(res['pnl'])

            if not pnls:
                continue

            avg = np.mean(pnls)
            med = np.median(pnls)
            win = np.mean([x > 0 for x in pnls])
            ev = fill_rate * avg
            total_pnl = sum(pnls)

            results.append({
                'entry_disc': disc, 'tp_pct': tp, 'sl_pct': sl,
                'trail': 'off', 'time_stop': 7,
                'signals': n, 'filled': filled_count,
                'fill_rate': fill_rate, 'win_rate': win,
                'avg_pnl': avg, 'med_pnl': med, 'ev': ev,
                'total_pnl': total_pnl,
            })

    res_df = pd.DataFrame(results).sort_values('ev', ascending=False)
    print(f"\n扫描完成: {len(results)} 组合")
    print("\n--- Top 20 (按 EV 排序) ---")
    top = res_df.head(20).copy()
    top['entry_disc'] = top['entry_disc'].apply(lambda x: f"{x*100:+.0f}%")
    top['tp_pct'] = top['tp_pct'].apply(lambda x: f"{x*100:.0f}%")
    top['sl_pct'] = top['sl_pct'].apply(lambda x: f"{x*100:.0f}%")
    top['fill_rate'] = top['fill_rate'].apply(lambda x: f"{x:.1%}")
    top['win_rate'] = top['win_rate'].apply(lambda x: f"{x:.1%}")
    top['avg_pnl'] = top['avg_pnl'].apply(lambda x: f"{x*100:+.2f}%")
    top['med_pnl'] = top['med_pnl'].apply(lambda x: f"{x*100:+.2f}%")
    top['ev'] = top['ev'].apply(lambda x: f"{x*100:+.3f}%")
    top['total_pnl'] = top['total_pnl'].apply(lambda x: f"{x*100:+.1f}%")
    print(top[['entry_disc', 'tp_pct', 'sl_pct', 'fill_rate', 'win_rate',
               'avg_pnl', 'med_pnl', 'ev', 'total_pnl']].to_string(index=False))

    return res_df


def run_phase2(df, parsed_paths, best_entry, best_tp, best_sl):
    print("\n" + "=" * 60)
    print(f"Phase 2: 追踪止损 × 时间衰减 扫描")
    print(f"固定: entry={best_entry*100:+.0f}%, TP={best_tp*100:.0f}%, SL={best_sl*100:.0f}%")
    print("=" * 60)

    trail_configs = [
        (999, 0.6, 'off'),
        (0.03, 0.5, '3%/50%'),
        (0.03, 0.6, '3%/60%'),
        (0.03, 0.7, '3%/70%'),
        (0.05, 0.5, '5%/50%'),
        (0.05, 0.6, '5%/60%'),
    ]
    time_stops = [3, 5, 7]

    t0s = df['_t0_close'].values
    n = len(df)
    results = []

    for (trig, gb, label), ts in product(trail_configs, time_stops):
        pnls = []
        statuses = []
        fill_count = 0

        for i, p in enumerate(parsed_paths):
            if not check_fill(p, t0s[i], best_entry):
                continue
            fill_count += 1
            res = simulate_trade(p, t0s[i], best_entry, best_tp, best_sl,
                                trail_trigger=trig, trail_keep=gb, time_stop=ts)
            pnls.append(res['pnl'])
            statuses.append(res['status'])

        if not pnls:
            continue

        fill_rate = fill_count / n
        avg = np.mean(pnls)
        med = np.median(pnls)
        win = np.mean([x > 0 for x in pnls])
        ev = fill_rate * avg

        status_counts = {}
        for s in statuses:
            status_counts[s] = status_counts.get(s, 0) + 1

        results.append({
            'entry_disc': best_entry, 'tp_pct': best_tp, 'sl_pct': best_sl,
            'trail': label, 'time_stop': ts,
            'signals': n, 'filled': fill_count,
            'fill_rate': fill_rate, 'win_rate': win,
            'avg_pnl': avg, 'med_pnl': med, 'ev': ev,
            'total_pnl': sum(pnls),
            '止盈': status_counts.get('止盈', 0),
            '止损': status_counts.get('止损', 0),
            '衰减': status_counts.get('时间衰减', 0),
            '到期': status_counts.get('持仓到期', 0),
        })

    res_df = pd.DataFrame(results).sort_values('ev', ascending=False)
    print(f"\n扫描完成: {len(results)} 组合")
    print("\n--- 全部结果 ---")
    disp = res_df.copy()
    disp['fill_rate'] = disp['fill_rate'].apply(lambda x: f"{x:.1%}")
    disp['win_rate'] = disp['win_rate'].apply(lambda x: f"{x:.1%}")
    disp['avg_pnl'] = disp['avg_pnl'].apply(lambda x: f"{x*100:+.2f}%")
    disp['med_pnl'] = disp['med_pnl'].apply(lambda x: f"{x*100:+.2f}%")
    disp['ev'] = disp['ev'].apply(lambda x: f"{x*100:+.3f}%")
    disp['total_pnl'] = disp['total_pnl'].apply(lambda x: f"{x*100:+.1f}%")
    cols = ['trail', 'time_stop', 'fill_rate', 'win_rate', 'avg_pnl',
            'med_pnl', 'ev', 'total_pnl', '止盈', '止损', '衰减', '到期']
    print(disp[cols].to_string(index=False))

    return res_df


def compare_with_actual(df, parsed_paths, best_params):
    print("\n" + "=" * 60)
    print("最优参数 vs 当前实际结果对比")
    print("=" * 60)

    executed = df[df['交易状态'].isin(['止盈成功', '止损出局', '时间衰减平仓', '持仓到期',
                                        '板块熔断强平', '形态破坏斩仓'])]

    actual_fill = len(executed) / len(df)
    actual_win = (executed['收益率'] > 0).mean()
    actual_avg = executed['收益率'].mean()
    actual_total = executed['收益率'].sum()

    t0s = df['_t0_close'].values
    bp = best_params
    sim_pnls = []
    for i, p in enumerate(parsed_paths):
        if not check_fill(p, t0s[i], bp['entry_disc']):
            continue
        res = simulate_trade(p, t0s[i], bp['entry_disc'], bp['tp_pct'], bp['sl_pct'],
                            trail_trigger=bp.get('trail_trigger', 999),
                            trail_keep=bp.get('trail_keep', 0.6),
                            time_stop=bp.get('time_stop', 7))
        sim_pnls.append(res['pnl'])

    sim_fill = len(sim_pnls) / len(df)
    sim_win = np.mean([x > 0 for x in sim_pnls]) if sim_pnls else 0
    sim_avg = np.mean(sim_pnls) if sim_pnls else 0
    sim_total = sum(sim_pnls) if sim_pnls else 0

    print(f"\n{'指标':<20} {'当前实际':<15} {'最优参数模拟':<15} {'提升':<15}")
    print("-" * 65)
    print(f"{'成交率':<20} {actual_fill:<15.1%} {sim_fill:<15.1%} {(sim_fill-actual_fill)/actual_fill:+.1%}")
    print(f"{'胜率':<20} {actual_win:<15.1%} {sim_win:<15.1%} {(sim_win-actual_win)/max(actual_win,0.01):+.1%}")
    print(f"{'平均收益':<18} {actual_avg*100:<15.2f}% {sim_avg*100:<15.2f}% {(sim_avg-actual_avg)*100:+.2f}pp")
    print(f"{'累计收益':<18} {actual_total*100:<15.1f}% {sim_total*100:<15.1f}% {(sim_total-actual_total)*100:+.1f}pp")
    print(f"{'成交笔数':<18} {len(executed):<15} {len(sim_pnls):<15}")
    print(f"\n最优参数: 入场={bp['entry_disc']*100:+.0f}%, TP={bp['tp_pct']*100:.0f}%, "
          f"SL={bp['sl_pct']*100:.0f}%, 追踪={bp.get('trail_label','off')}, "
          f"时间衰减={bp.get('time_stop',7)}天")


def analyze_by_group(df, parsed_paths, best_params):
    print("\n" + "=" * 60)
    print("分层最优参数分析")
    print("=" * 60)

    bp = best_params
    entry_discs_to_test = [0.0, -0.01, -0.02, -0.03, -0.04, -0.05, -0.06, -0.08]
    tp_pcts_to_test = [0.08, 0.10, 0.12, 0.15, 0.18, 0.22]
    sl_pcts_to_test = [-0.05, -0.06, -0.07, -0.08, -0.10]

    for group_col in ['v44_trend', 'v44_bias_tier']:
        print(f"\n--- 按 {group_col} 分层 ---")
        for group_val, grp_df in df.groupby(group_col):
            if len(grp_df) < 20:
                continue

            grp_indices = grp_df.index.tolist()
            grp_paths = [parsed_paths[df.index.get_loc(i)] for i in grp_indices]
            grp_t0s = grp_df['_t0_close'].values
            n = len(grp_df)

            best_ev = -999
            best_p = None

            for disc in entry_discs_to_test:
                fills = [check_fill(p, grp_t0s[j], disc) for j, p in enumerate(grp_paths)]
                fill_rate = sum(fills) / n

                for tp, sl in product(tp_pcts_to_test, sl_pcts_to_test):
                    if tp <= abs(sl) * 0.5:
                        continue
                    pnls = []
                    for j, p in enumerate(grp_paths):
                        if not fills[j]:
                            continue
                        res = simulate_trade(p, grp_t0s[j], disc, tp, sl)
                        if res['filled']:
                            pnls.append(res['pnl'])
                    if not pnls:
                        continue
                    ev = fill_rate * np.mean(pnls)
                    if ev > best_ev:
                        best_ev = ev
                        best_p = {
                            'entry': disc, 'tp': tp, 'sl': sl,
                            'fill_rate': fill_rate,
                            'win': np.mean([x > 0 for x in pnls]),
                            'avg': np.mean(pnls), 'ev': ev,
                        }

            if best_p:
                print(f"  {group_val:<25} N={n:<5} "
                      f"入场={best_p['entry']*100:+.0f}% TP={best_p['tp']*100:.0f}% "
                      f"SL={best_p['sl']*100:.0f}% "
                      f"成交率={best_p['fill_rate']:.1%} 胜率={best_p['win']:.1%} "
                      f"均PnL={best_p['avg']*100:+.2f}% EV={best_p['ev']*100:+.3f}%")


def main():
    print("=" * 60)
    print("  入场/出场价格参数扫描器")
    print("=" * 60)

    df = pd.read_csv(CSV_PATH)
    df['_path'] = df['future_7d_path'].apply(parse_path)
    df = df[df['_path'].notna()].reset_index(drop=True)
    df['_t0_close'] = df['trigger_buy'].apply(estimate_t0_close)
    df['board'] = df['stock_code'].apply(categorize_board)
    parsed_paths = df['_path'].tolist()

    print(f"有效信号: {len(df)} / 625 (过滤无路径数据)")

    # Phase 1
    p1_df = run_phase1(df, parsed_paths)
    best_row = p1_df.iloc[0]
    best_entry = best_row['entry_disc']
    best_tp = best_row['tp_pct']
    best_sl = best_row['sl_pct']
    print(f"\nPhase 1 最优: entry={best_entry*100:+.0f}%, TP={best_tp*100:.0f}%, "
          f"SL={best_sl*100:.0f}%, EV={best_row['ev']*100:+.3f}%")

    # Phase 2
    p2_df = run_phase2(df, parsed_paths, best_entry, best_tp, best_sl)
    p2_best = p2_df.iloc[0]

    # Merge best params
    best_params = {
        'entry_disc': best_entry, 'tp_pct': best_tp, 'sl_pct': best_sl,
        'trail_label': p2_best['trail'],
        'trail_trigger': 999 if p2_best['trail'] == 'off' else float(p2_best['trail'].split('/')[0].replace('%', '')) / 100,
        'trail_keep': 0.6 if p2_best['trail'] == 'off' else float(p2_best['trail'].split('/')[1].replace('%', '')) / 100,
        'time_stop': int(p2_best['time_stop']),
    }

    # Compare with actual
    compare_with_actual(df, parsed_paths, best_params)

    # Group analysis
    analyze_by_group(df, parsed_paths, best_params)

    # Save
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    p1_df.to_csv(OUTPUT_PATH, index=False)
    print(f"\n完整结果已保存: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
