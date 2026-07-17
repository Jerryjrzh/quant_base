#!/usr/bin/env python3
"""
V4.7 全周期回测验证脚本
根据 doc/0606_calendar_backtest/ 文档提出的命题逐一回测验证

用法: cd backend && python3 v47_backtest_verify.py
"""
import os, sys, re, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pricing_gbm_backtest import parse_path, simulate_on_path

BASE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(BASE, '..', 'data', 'result', 'Calendar_Backtest', 'full_calendar_trades.csv')

def get_board(code):
    c = str(code).lower()
    n = ''.join(ch for ch in c if ch.isdigit())
    if n.startswith('300') or n.startswith('688'):
        return '20CM'
    if c.startswith('bj') or n.startswith('920'):
        return '30CM'
    return '10CM'


def sim_trade(path, t0c, entry, tp, sl, time_stop=7, ladder=None):
    """
    通用交易模拟器
    ladder: [(trigger_pct, new_sl_pct), ...] 阶梯锁利
    """
    tp_price = entry * (1 + tp)
    sl_price = entry * (1 + sl)
    mfe = 0.0
    mae = 0.0
    filled = False

    for i, (hp, lp) in enumerate(path):
        dh = t0c * (1 + hp)
        dl = t0c * (1 + lp)
        dm = (dh + dl) / 2

        if not filled:
            if dl <= entry and dm >= entry * 0.995:
                filled = True
            else:
                continue

        pnl_h = (dh - entry) / entry
        pnl_l = (dl - entry) / entry
        if pnl_h > mfe: mfe = pnl_h
        if pnl_l < mae: mae = pnl_l

        if ladder:
            for trig, new_sl in ladder:
                if mfe >= trig:
                    sl_price = max(sl_price, entry * (1 + new_sl))

        hit_sl = dl <= sl_price
        hit_tp = dh >= tp_price

        if hit_sl and hit_tp:
            if (sl_price - dl) > (dh - tp_price):
                hit_tp = False
            else:
                hit_sl = False

        if hit_sl:
            ep = min(dm, sl_price)
            return {'pnl': (ep - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae,
                    'status': '止损', 'days': i + 1}
        if hit_tp:
            ep = max(dm, tp_price)
            return {'pnl': (ep - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae,
                    'status': '止盈', 'days': i + 1}

        if i + 1 >= time_stop and mfe < 0.01:
            return {'pnl': (dm - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae,
                    'status': '时间衰减', 'days': i + 1}

    if not filled:
        return {'pnl': 0.0, 'filled': False, 'mfe': 0.0, 'mae': 0.0,
                'status': '未成交', 'days': 0}

    lh, ll = path[-1]
    lc = t0c * (1 + (lh + ll) / 2)
    return {'pnl': (lc - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae,
            'status': '到期', 'days': len(path)}


def run_all(df):
    df['board'] = df['stock_code'].apply(get_board)
    df['dow'] = pd.to_datetime(df['回测日期']).dt.dayofweek
    df['month'] = pd.to_datetime(df['回测日期']).dt.month
    df['year'] = pd.to_datetime(df['回测日期']).dt.year
    df['entry_pos'] = ((df['trigger_buy'] - df['回测底']) / (df['回测顶'] - df['回测底'])).clip(0, 1)
    filled = ~df['交易状态'].isin(['挂单超时撤销', '大幅低开放弃'])
    df['is_filled'] = filled

    paths = df['future_7d_path'].apply(parse_path)
    t0c_arr = df['close_t0'].values

    # ============================================================
    print("=" * 70)
    print("  V1: TP 档位扫描 (SL=-12%, 20CM)")
    print("=" * 70)

    tp_levels = [0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.22, 0.25]
    mask_20 = df['board'] == '20CM'

    print(f"\n  {'TP':>6} {'成交率':>7} {'止盈率':>7} {'胜率':>6} {'均PnL':>8} {'EV':>8} {'总PnL':>10}")
    for tp in tp_levels:
        results = []
        for idx in df[mask_20].index:
            p = paths.iloc[idx]
            if not p: continue
            r = sim_trade(p, t0c_arr[idx], t0c_arr[idx] * 0.99, tp, -0.12, time_stop=7)
            results.append(r)
        if not results: continue
        res = pd.DataFrame(results)
        fill = res['filled'].mean()
        tp_rate = (res['status'] == '止盈').sum() / len(res)
        fpnl = res.loc[res['filled'], 'pnl']
        wr = (fpnl > 0).mean() if len(fpnl) > 0 else 0
        avg = fpnl.mean() if len(fpnl) > 0 else 0
        ev = (res['filled'] * res['pnl']).mean()
        total = res.loc[res['filled'], 'pnl'].sum()
        print(f"  {tp*100:5.0f}% {fill:6.1%} {tp_rate:6.1%} {wr:5.1%} {avg*100:+7.3f}% {ev*100:+7.3f}% {total*100:+9.1f}%")

    # 10CM
    mask_10 = df['board'] == '10CM'
    if mask_10.sum() > 50:
        print(f"\n  10CM (N={mask_10.sum()}):")
        print(f"  {'TP':>6} {'成交率':>7} {'止盈率':>7} {'胜率':>6} {'均PnL':>8} {'EV':>8}")
        for tp in [0.08, 0.10, 0.12, 0.15, 0.18]:
            results = []
            for idx in df[mask_10].index:
                p = paths.iloc[idx]
                if not p: continue
                r = sim_trade(p, t0c_arr[idx], t0c_arr[idx] * 0.99, tp, -0.10, time_stop=7)
                results.append(r)
            if not results: continue
            res = pd.DataFrame(results)
            fill = res['filled'].mean()
            tp_rate = (res['status'] == '止盈').sum() / len(res)
            fpnl = res.loc[res['filled'], 'pnl']
            wr = (fpnl > 0).mean() if len(fpnl) > 0 else 0
            avg = fpnl.mean() if len(fpnl) > 0 else 0
            ev = (res['filled'] * res['pnl']).mean()
            print(f"  {tp*100:5.0f}% {fill:6.1%} {tp_rate:6.1%} {wr:5.1%} {avg*100:+7.3f}% {ev*100:+7.3f}%")

    # ============================================================
    print("\n" + "=" * 70)
    print("  V2: 阶梯锁利 vs 固定止盈 vs 追踪止损")
    print("=" * 70)

    strategies = {
        'A) 固定TP=12% SL=-12%': {'tp': 0.12, 'sl': -0.12, 'ladder': None},
        'B) 固定TP=15% SL=-12%': {'tp': 0.15, 'sl': -0.12, 'ladder': None},
        'C) 阶梯锁利(8%→SL+1%,15%→SL+8%)': {'tp': 0.25, 'sl': -0.12, 'ladder': [(0.08, 0.01), (0.15, 0.08)]},
        'D) 阶梯锁利(8%→SL+1%,12%→SL+6%)': {'tp': 0.25, 'sl': -0.12, 'ladder': [(0.08, 0.01), (0.12, 0.06)]},
        'E) 追踪止损(trigger=5%,keep=60%)': {'tp': 0.25, 'sl': -0.12, 'ladder': None, 'trailing': (0.05, 0.60)},
    }

    for name, params in strategies.items():
        results = []
        for idx in df[mask_20].index:
            p = paths.iloc[idx]
            if not p: continue
            if 'trailing' in params:
                trail_trig, trail_keep = params['trailing']
                r = sim_trailing(p, t0c_arr[idx], t0c_arr[idx] * 0.99, params['tp'], params['sl'],
                                 trail_trig, trail_keep, time_stop=7)
            else:
                r = sim_trade(p, t0c_arr[idx], t0c_arr[idx] * 0.99, params['tp'], params['sl'],
                              time_stop=7, ladder=params.get('ladder'))
            results.append(r)

        res = pd.DataFrame(results)
        fill = res['filled'].mean()
        fpnl = res.loc[res['filled'], 'pnl']
        wr = (fpnl > 0).mean() if len(fpnl) > 0 else 0
        avg = fpnl.mean() if len(fpnl) > 0 else 0
        ev = (res['filled'] * res['pnl']).mean()
        total = res.loc[res['filled'], 'pnl'].sum()
        tp_n = (res['status'] == '止盈').sum()
        sl_n = (res['status'] == '止损').sum()
        exp_n = (res['status'].isin(['到期', '时间衰减'])).sum()
        print(f"\n  {name}")
        print(f"    成交={fill:.1%} 胜率={wr:.1%} 均PnL={avg*100:+.3f}% EV={ev*100:+.3f}% 总PnL={total*100:+.1f}%")
        print(f"    止盈{tp_n}笔 止损{sl_n}笔 到期/衰减{exp_n}笔")

    # ============================================================
    print("\n" + "=" * 70)
    print("  V3: 周几效应验证")
    print("=" * 70)

    dow_names = {0: '周一', 1: '周二', 2: '周三', 3: '周四', 4: '周五'}
    for d in range(5):
        sub = df[df['dow'] == d]
        if len(sub) < 50: continue
        f = sub['is_filled']
        ev = (f * sub['收益率']).mean()
        fp = sub.loc[f, '收益率']
        wr = (fp > 0).mean() if len(fp) > 0 else 0
        avg = fp.mean() if len(fp) > 0 else 0
        print(f"  {dow_names[d]}: N={len(sub):<5} 成交率={f.mean():.1%} 胜率={wr:.1%} 均PnL={avg*100:+.3f}% EV={ev*100:+.3f}%")

    # GBM proba threshold by DOW
    print(f"\n  --- GBM门槛分层 (EV) ---")
    print(f"  {'':>12}", end='')
    for g in [0.5, 0.6, 0.65, 0.70, 0.75]:
        print(f" GBM>={g:.2f}", end='')
    print()
    for d in range(5):
        sub = df[df['dow'] == d]
        print(f"  {dow_names[d]:<12}", end='')
        for g in [0.5, 0.6, 0.65, 0.70, 0.75]:
            gs = sub[sub['gbm_proba'] >= g]
            if len(gs) < 20:
                print(f" {'N/A':>11}", end='')
                continue
            ev = (gs['is_filled'] * gs['收益率']).mean()
            print(f" {ev*100:>+10.3f}%", end='')
        print()

    # ============================================================
    print("\n" + "=" * 70)
    print("  V4: Distribution 否决 + GBM 门槛分层")
    print("=" * 70)

    for trend in ['accumulation', 'markup', 'distribution', 'decline']:
        sub = df[df['v44_trend'] == trend]
        if len(sub) < 5: continue
        f = sub['is_filled']
        ev = (f * sub['收益率']).mean()
        fp = sub.loc[f, '收益率']
        wr = (fp > 0).mean() if len(fp) > 0 else 0
        avg = fp.mean() if len(fp) > 0 else 0
        print(f"  {trend:<15} N={len(sub):<5} 成交率={f.mean():.1%} 胜率={wr:.1%} 均PnL={avg*100:+.3f}% EV={ev*100:+.3f}%")

    print(f"\n  --- GBM 门槛对 EV 的影响 ---")
    for g in [0.0, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8]:
        sub = df[df['gbm_proba'] >= g]
        if len(sub) < 50: continue
        f = sub['is_filled']
        ev = (f * sub['收益率']).mean()
        fp = sub.loc[f, '收益率']
        wr = (fp > 0).mean() if len(fp) > 0 else 0
        avg = fp.mean() if len(fp) > 0 else 0
        total = fp.sum()
        print(f"  GBM>={g:.2f}: N={len(sub):<5} 成交率={f.mean():.1%} 胜率={wr:.1%} "
              f"均PnL={avg*100:+.3f}% EV={ev*100:+.3f}% 总PnL={total*100:+.1f}%")

    # ============================================================
    print("\n" + "=" * 70)
    print("  V5: 板块效应 — 10CM/20CM 止损差异化")
    print("=" * 70)

    for board in ['10CM', '20CM']:
        mask = df['board'] == board
        sub = df[mask]
        sl_default = -0.10 if board == '10CM' else -0.12
        print(f"\n  --- {board} (N={len(sub)}) SL扫描 ---")
        print(f"  {'SL':>6} {'成交率':>7} {'胜率':>6} {'均PnL':>8} {'EV':>8} {'最大单笔亏':>10}")
        for sl in [-0.06, -0.08, -0.10, -0.12, -0.15]:
            results = []
            for idx in sub.index:
                p = paths.iloc[idx]
                if not p: continue
                r = sim_trade(p, t0c_arr[idx], t0c_arr[idx] * 0.99, 0.12, sl, time_stop=7)
                results.append(r)
            if not results: continue
            res = pd.DataFrame(results)
            fill = res['filled'].mean()
            fpnl = res.loc[res['filled'], 'pnl']
            wr = (fpnl > 0).mean() if len(fpnl) > 0 else 0
            avg = fpnl.mean() if len(fpnl) > 0 else 0
            ev = (res['filled'] * res['pnl']).mean()
            max_loss = fpnl.min() if len(fpnl) > 0 else 0
            print(f"  {sl*100:+5.0f}% {fill:6.1%} {wr:5.1%} {avg*100:+7.3f}% {ev*100:+7.3f}% {max_loss*100:+9.2f}%")

    # ============================================================
    print("\n" + "=" * 70)
    print("  V6: entry_pos 过滤验证")
    print("=" * 70)

    for threshold in [0.3, 0.4, 0.5, 0.6]:
        sub = df[df['entry_pos'] <= threshold]
        excluded = df[df['entry_pos'] > threshold]
        if len(sub) < 50: continue
        f = sub['is_filled']
        ev = (f * sub['收益率']).mean()
        fp = sub.loc[f, '收益率']
        wr = (fp > 0).mean() if len(fp) > 0 else 0
        avg = fp.mean() if len(fp) > 0 else 0
        total = fp.sum()
        exc_ev = (excluded['is_filled'] * excluded['收益率']).mean() if len(excluded) > 0 else 0
        print(f"  entry_pos <= {threshold:.1f}: N={len(sub):<5} 过滤{len(excluded)}笔 "
              f"胜率={wr:.1%} 均PnL={avg*100:+.3f}% EV={ev*100:+.3f}% 总PnL={total*100:+.1f}% "
              f"(被过滤EV={exc_ev*100:+.3f}%)")

    # ============================================================
    print("\n" + "=" * 70)
    print("  V7: 最优组合方案对比")
    print("=" * 70)

    schemes = {
        '基准(V4.7当前)': {'tp': 0.15, 'sl_map': {'20CM': -0.12, '10CM': -0.10}, 'pos_filter': 1.0, 'gbm_min': 0.0},
        'A) TP=10% + pos<=0.5': {'tp': 0.10, 'sl_map': {'20CM': -0.12, '10CM': -0.10}, 'pos_filter': 0.5, 'gbm_min': 0.0},
        'B) TP=12% + 阶梯锁利 + pos<=0.5': {'tp': 0.22, 'sl_map': {'20CM': -0.12, '10CM': -0.10},
                                          'pos_filter': 0.5, 'gbm_min': 0.0,
                                          'ladder': [(0.08, 0.01), (0.12, 0.06)]},
        'C) TP=10% + GBM>=0.6 + pos<=0.5': {'tp': 0.10, 'sl_map': {'20CM': -0.12, '10CM': -0.10},
                                           'pos_filter': 0.5, 'gbm_min': 0.6},
        'D) TP=10% + GBM>=0.65 + pos<=0.4': {'tp': 0.10, 'sl_map': {'20CM': -0.12, '10CM': -0.10},
                                            'pos_filter': 0.4, 'gbm_min': 0.65},
        'E) TP=12% + 阶梯 + GBM>=0.6 + pos<=0.5': {'tp': 0.22, 'sl_map': {'20CM': -0.12, '10CM': -0.10},
                                                  'pos_filter': 0.5, 'gbm_min': 0.6,
                                                  'ladder': [(0.08, 0.01), (0.12, 0.06)]},
    }

    for sname, params in schemes.items():
        results = []
        for idx in df.index:
            row = df.iloc[idx]
            if row['entry_pos'] > params['pos_filter']:
                continue
            if row['gbm_proba'] < params['gbm_min']:
                continue
            p = paths.iloc[idx]
            if not p:
                continue
            board = row['board']
            sl = params['sl_map'].get(board, -0.10)
            r = sim_trade(p, t0c_arr[idx], t0c_arr[idx] * 0.99, params['tp'], sl,
                          time_stop=7, ladder=params.get('ladder'))
            results.append(r)

        if not results:
            continue
        res = pd.DataFrame(results)
        fill = res['filled'].mean()
        fpnl = res.loc[res['filled'], 'pnl']
        wr = (fpnl > 0).mean() if len(fpnl) > 0 else 0
        avg = fpnl.mean() if len(fpnl) > 0 else 0
        ev = (res['filled'] * res['pnl']).mean()
        total = fpnl.sum()
        tp_n = (res['status'] == '止盈').sum()
        sl_n = (res['status'] == '止损').sum()
        print(f"\n  {sname}")
        print(f"    信号={len(res)} 成交={fill:.1%}({res['filled'].sum()}) 胜率={wr:.1%} "
              f"均PnL={avg*100:+.3f}% EV={ev*100:+.3f}% 总PnL={total*100:+.1f}%")
        print(f"    止盈{tp_n} 止损{sl_n} 到期/衰减{len(res)-tp_n-sl_n-res[~res['filled']].shape[0]}")


def sim_trailing(path, t0c, entry, tp, sl, trail_trig, trail_keep, time_stop=7):
    """追踪止损模拟器"""
    tp_price = entry * (1 + tp)
    sl_price = entry * (1 + sl)
    mfe = 0.0
    mae = 0.0
    filled = False

    for i, (hp, lp) in enumerate(path):
        dh = t0c * (1 + hp)
        dl = t0c * (1 + lp)
        dm = (dh + dl) / 2

        if not filled:
            if dl <= entry and dm >= entry * 0.995:
                filled = True
            else:
                continue

        pnl_h = (dh - entry) / entry
        pnl_l = (dl - entry) / entry
        if pnl_h > mfe: mfe = pnl_h
        if pnl_l < mae: mae = pnl_l

        if mfe >= trail_trig:
            trail_sl = entry * (1 + mfe * trail_keep)
            sl_price = max(sl_price, trail_sl)

        hit_sl = dl <= sl_price
        hit_tp = dh >= tp_price

        if hit_sl and hit_tp:
            if (sl_price - dl) > (dh - tp_price):
                hit_tp = False
            else:
                hit_sl = False

        if hit_sl:
            ep = min(dm, sl_price)
            return {'pnl': (ep - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae,
                    'status': '止损', 'days': i + 1}
        if hit_tp:
            ep = max(dm, tp_price)
            return {'pnl': (ep - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae,
                    'status': '止盈', 'days': i + 1}

        if i + 1 >= time_stop and mfe < 0.01:
            return {'pnl': (dm - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae,
                    'status': '时间衰减', 'days': i + 1}

    if not filled:
        return {'pnl': 0.0, 'filled': False, 'mfe': 0.0, 'mae': 0.0,
                'status': '未成交', 'days': 0}

    lh, ll = path[-1]
    lc = t0c * (1 + (lh + ll) / 2)
    return {'pnl': (lc - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae,
            'status': '到期', 'days': len(path)}


if __name__ == '__main__':
    print("=" * 70)
    print("  V4.7 回测验证 — doc/0606_calendar_backtest/ 命题逐一验证")
    print("=" * 70)

    df = pd.read_csv(CSV)
    print(f"\n数据: {len(df)} 信号 ({df['回测日期'].min()} ~ {df['回测日期'].max()})")
    run_all(df)
