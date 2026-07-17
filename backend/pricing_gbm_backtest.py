#!/usr/bin/env python3
"""
定价 GBM 回测脚本
在 full_calendar_trades.csv (625 信号) 上验证定价 GBM 的实际回测效果

对比三种策略:
  A) 固定浅挂 (T0 收盘 × 0.99)
  B) 固定深挂 (T0 收盘 × 0.95)
  C) GBM 自适应 (proba>0.7 浅挂, proba<0.3 深挂, 中间中性)

用法:
    cd backend
    python3 pricing_gbm_backtest.py
"""

import os, sys, re, json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pricing_gbm import load_pricing_gbm, build_features

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, '..', 'data', 'result', 'Calendar_Backtest', 'full_calendar_trades.csv')

TP_PCT = 0.18
SL_PCT = -0.12


def parse_path(path_str):
    """解析 future_7d_path → list of (H_pct, L_pct)"""
    if pd.isna(path_str) or not isinstance(path_str, str) or not path_str.strip():
        return []
    days = []
    for seg in path_str.split(' -> '):
        m_h = re.search(r'H:([+-]?\d+\.?\d*)%', seg)
        m_l = re.search(r'L:([+-]?\d+\.?\d*)%', seg)
        if m_h and m_l:
            days.append((float(m_h.group(1)) / 100.0, float(m_l.group(1)) / 100.0))
    return days


def simulate_on_path(path, t0_close, entry_price, tp_pct, sl_pct):
    """
    在 future_7d_path 上模拟交易 (含成交判定)
    返回: {pnl, filled, mfe, mae, status, hold_days}
    """
    entry = entry_price
    tp_price = entry * (1.0 + tp_pct)
    sl_price = entry * (1.0 + sl_pct)
    mfe = 0.0
    mae = 0.0
    filled = False
    fill_day = -1

    for i, (h_pct, l_pct) in enumerate(path):
        day_high = t0_close * (1.0 + h_pct)
        day_low = t0_close * (1.0 + l_pct)
        day_mid = (day_high + day_low) / 2.0

        if not filled:
            if day_low <= entry and day_mid >= entry * 0.995:
                filled = True
                fill_day = i
            else:
                continue

        pnl_h = (day_high - entry) / entry
        pnl_l = (day_low - entry) / entry
        if pnl_h > mfe:
            mfe = pnl_h
        if pnl_l < mae:
            mae = pnl_l

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
            return {'pnl': (exit_p - entry) / entry, 'filled': True,
                    'mfe': mfe, 'mae': mae, 'status': '止损', 'hold_days': i + 1}

        if hit_tp:
            exit_p = max(day_mid, tp_price)
            return {'pnl': (exit_p - entry) / entry, 'filled': True,
                    'mfe': mfe, 'mae': mae, 'status': '止盈', 'hold_days': i + 1}

    if not filled:
        return {'pnl': 0.0, 'filled': False, 'mfe': 0.0, 'mae': 0.0,
                'status': '未成交', 'hold_days': 0}

    last_h, last_l = path[-1]
    last_close = t0_close * (1.0 + (last_h + last_l) / 2.0)
    return {'pnl': (last_close - entry) / entry, 'filled': True,
            'mfe': mfe, 'mae': mae, 'status': '到期', 'hold_days': len(path)}


def extract_features_from_csv(df):
    """从 full_calendar_trades.csv 提取 GBM 所需特征
    优先使用 V4.7+ 直接输出列，兼容旧 CSV 回退到派生计算"""
    df = df.copy()

    has_direct = 'close_t0' in df.columns and 't1_open' in df.columns

    if has_direct and df['close_t0'].notna().sum() > 0:
        print("  使用 V4.7+ 直接列 (close_t0, t1_open/high/low/close, swing, bias_20, ma_slope)")
        df['t0_close'] = df['close_t0'].fillna(df['trigger_buy'] / 0.95)
        df['T1_Open'] = df['t1_open'].fillna(df['t0_close'])
        df['T1_High'] = df['t1_high'].fillna(df['t0_close'])
        df['T1_Low'] = df['t1_low'].fillna(df['t0_close'])
        df['T1_Close'] = df['t1_close'].fillna(df['t0_close'])
        if 'swing' not in df.columns or df['swing'].isna().all():
            df['swing'] = df.get('swing', 0.0)
        else:
            df['swing'] = df['swing'].fillna(0.0)
        if 'bias_20' not in df.columns or df['bias_20'].isna().all():
            df['bias_20'] = _parse_morse_bias(df['morse_features'])
        else:
            df['bias_20'] = df['bias_20'].fillna(0.0)
        if 'ma_slope' not in df.columns or df['ma_slope'].isna().all():
            df['ma_slope'] = 0.0
        else:
            df['ma_slope'] = df['ma_slope'].fillna(0.0)
    else:
        print("  旧 CSV 格式，使用派生计算 (trigger_buy/0.95, future_7d_path)")
        df['t0_close'] = df['trigger_buy'] / 0.95

        t1_highs, t1_lows, t1_opens, t1_closes, swings = [], [], [], [], []
        for _, row in df.iterrows():
            path = parse_path(row['future_7d_path'])
            t0c = row['t0_close']
            if path:
                h1, l1 = path[0]
                t1h = t0c * (1.0 + h1)
                t1l = t0c * (1.0 + l1)
                t1_highs.append(t1h)
                t1_lows.append(t1l)
                t1_opens.append(t1l)
                t1_closes.append((t1h + t1l) / 2.0)
                all_h = [p[0] for p in path]
                all_l = [p[1] for p in path]
                swings.append(max(all_h) - min(all_l))
            else:
                t1_highs.append(t0c)
                t1_lows.append(t0c)
                t1_opens.append(t0c)
                t1_closes.append(t0c)
                swings.append(0.0)

        df['T1_High'] = t1_highs
        df['T1_Low'] = t1_lows
        df['T1_Open'] = t1_opens
        df['T1_Close'] = t1_closes
        df['swing'] = swings
        df['bias_20'] = _parse_morse_bias(df['morse_features'])
        df['ma_slope'] = 0.0

    df['close_t0'] = df['t0_close']

    if 'market_env' not in df.columns or df['market_env'].isna().all():
        df['market_env'] = df['morse_features'].apply(
            lambda x: re.search(r'MKT:([^|]+)', str(x)).group(1)
            if re.search(r'MKT:([^|]+)', str(x)) else '震荡'
        )

    df = build_features(df)
    return df


def _parse_morse_bias(morse_series):
    """从 morse_features 提取 bias_20"""
    return morse_series.apply(
        lambda x: float(re.search(r'B20:([-+]?\d+\.?\d*)', str(x)).group(1))
        if re.search(r'B20:([-+]?\d+\.?\d*)', str(x)) else 0.0
    )


def run_backtest():
    print("=" * 70)
    print("  定价 GBM 回测 — full_calendar_trades.csv (625 信号)")
    print("=" * 70)

    df = pd.read_csv(CSV_PATH)
    print(f"\n加载: {len(df)} 信号")
    print(f"交易状态: {df['交易状态'].value_counts().to_dict()}")

    df = extract_features_from_csv(df)

    model, meta = load_pricing_gbm()
    print(f"\nGBM 模型加载成功: {len(meta['feature_cols'])} 特征")

    df_orig_trend = df['v44_trend'].copy()
    df_orig_bias = df['v44_bias_tier'].copy()
    df = pd.get_dummies(df, columns=meta['onehot_prefixes'], prefix=meta['onehot_prefixes'])
    for col in meta['feature_cols']:
        if col not in df.columns:
            df[col] = 0

    X = df[meta['feature_cols']].fillna(0)
    df['pricing_proba'] = model.predict_proba(X)[:, 1]

    if 'v44_trend' not in df.columns:
        df['v44_trend'] = df_orig_trend
    if 'v44_bias_tier' not in df.columns:
        df['v44_bias_tier'] = df_orig_bias

    paths = df['future_7d_path'].apply(parse_path)

    results = {'shallow': [], 'deep': [], 'gbm_adaptive': []}

    for i, row in df.iterrows():
        path = paths.iloc[i]
        t0c = row['t0_close']
        proba = row['pricing_proba']

        if not path:
            for k in results:
                results[k].append({'pnl': 0.0, 'filled': False, 'mfe': 0.0,
                                   'mae': 0.0, 'status': '无数据', 'hold_days': 0})
            continue

        r_shallow = simulate_on_path(path, t0c, t0c * 0.99, TP_PCT, SL_PCT)
        r_deep = simulate_on_path(path, t0c, t0c * 0.95, TP_PCT, SL_PCT)

        if proba > 0.7:
            r_adaptive = r_shallow.copy()
            r_adaptive['strategy_choice'] = 'shallow'
        elif proba < 0.3:
            r_adaptive = r_deep.copy()
            r_adaptive['strategy_choice'] = 'deep'
        else:
            r_adaptive = simulate_on_path(path, t0c, t0c * 0.97, TP_PCT, SL_PCT)
            r_adaptive['strategy_choice'] = 'neutral'

        results['shallow'].append(r_shallow)
        results['deep'].append(r_deep)
        results['gbm_adaptive'].append(r_adaptive)

    for k in results:
        df[f'{k}_pnl'] = [r['pnl'] for r in results[k]]
        df[f'{k}_filled'] = [r['filled'] for r in results[k]]
        df[f'{k}_status'] = [r['status'] for r in results[k]]
        df[f'{k}_mfe'] = [r['mfe'] for r in results[k]]
        df[f'{k}_mae'] = [r['mae'] for r in results[k]]

    df['gbm_choice'] = [r.get('strategy_choice', '') for r in results['gbm_adaptive']]

    print("\n" + "=" * 70)
    print("  一、三种策略总览对比")
    print("=" * 70)

    for label, key in [('A) 固定浅挂(×0.99)', 'shallow'),
                        ('B) 固定深挂(×0.95)', 'deep'),
                        ('C) GBM自适应', 'gbm_adaptive')]:
        filled = df[f'{key}_filled']
        pnls = df[f'{key}_pnl']
        filled_pnls = pnls[filled]
        fill_rate = filled.mean()
        avg_pnl = filled_pnls.mean() if len(filled_pnls) > 0 else 0
        ev = (filled * pnls).mean()
        win_rate = (filled_pnls > 0).mean() if len(filled_pnls) > 0 else 0
        max_loss = pnls.min()
        avg_mfe = df[f'{key}_mfe'].mean()
        avg_mae = df[f'{key}_mae'].mean()

        status_counts = df[f'{key}_status'].value_counts()
        tp_n = status_counts.get('止盈', 0)
        sl_n = status_counts.get('止损', 0)
        exp_n = status_counts.get('到期', 0)
        unfill_n = status_counts.get('未成交', 0)

        cum_ret = (1 + pnls[filled]).prod() - 1 if fill_rate > 0 else 0

        print(f"\n  {label}:")
        print(f"    成交率: {fill_rate:.1%} ({filled.sum()}/{len(df)})")
        print(f"    成交均PnL: {avg_pnl*100:+.3f}%")
        print(f"    EV(含未成交): {ev*100:+.3f}%")
        print(f"    胜率: {win_rate:.1%}")
        print(f"    最大单笔亏损: {max_loss*100:.2f}%")
        print(f"    平均MFE: {avg_mfe*100:+.2f}%  平均MAE: {avg_mae*100:.2f}%")
        print(f"    止盈{tp_n}笔 | 止损{sl_n}笔 | 到期{exp_n}笔 | 未成交{unfill_n}笔")
        if fill_rate > 0:
            print(f"    累计复合收益: {cum_ret*100:+.2f}%")

    print("\n" + "=" * 70)
    print("  二、GBM 概率分组验证")
    print("=" * 70)

    for lo, hi, label in [(0, 0.3, '低概率(<0.3, 推荐深挂)'),
                           (0.3, 0.7, '中性(0.3~0.7)'),
                           (0.7, 1.001, '高概率(>0.7, 推荐浅挂)')]:
        mask = (df['pricing_proba'] >= lo) & (df['pricing_proba'] < hi)
        sub = df[mask]
        if len(sub) == 0:
            print(f"\n  {label}: 无信号")
            continue

        s_fill = sub['shallow_filled'].mean()
        d_fill = sub['deep_filled'].mean()
        s_ev = (sub['shallow_filled'] * sub['shallow_pnl']).mean()
        d_ev = (sub['deep_filled'] * sub['deep_pnl']).mean()
        s_avg = sub.loc[sub['shallow_filled'], 'shallow_pnl'].mean() if sub['shallow_filled'].any() else 0
        d_avg = sub.loc[sub['deep_filled'], 'deep_pnl'].mean() if sub['deep_filled'].any() else 0
        gbm_ev = (sub['gbm_adaptive_filled'] * sub['gbm_adaptive_pnl']).mean()

        print(f"\n  {label}  (N={len(sub)})")
        print(f"    浅挂: 成交率={s_fill:.1%}  成交均PnL={s_avg*100:+.3f}%  EV={s_ev*100:+.3f}%")
        print(f"    深挂: 成交率={d_fill:.1%}  成交均PnL={d_avg*100:+.3f}%  EV={d_ev*100:+.3f}%")
        print(f"    GBM选择: EV={gbm_ev*100:+.3f}%")
        better = '浅挂' if s_ev > d_ev else '深挂'
        print(f"    该组更优策略: {better} (GBM建议: {'浅挂' if lo >= 0.7 else '深挂' if hi <= 0.3 else '中性'})")

    print("\n" + "=" * 70)
    print("  三、按板块/趋势/乖离分组效果")
    print("=" * 70)

    df['board_type'] = df['stock_code'].apply(
        lambda x: '20CM' if str(x).lower().startswith(('sz300', 'sz301', 'sh688', 'sh689'))
        else '30CM' if str(x).lower().startswith('bj') or '920' in str(x)
        else '10CM'
    )

    for col, label in [('board_type', '板块'), ('v44_trend', '趋势'), ('v44_bias_tier', '乖离')]:
        print(f"\n  --- 按{label}分组 ---")
        for name, grp in df.groupby(col):
            if len(grp) < 10:
                continue
            s_fill = grp['shallow_filled'].mean()
            d_fill = grp['deep_filled'].mean()
            s_ev = (grp['shallow_filled'] * grp['shallow_pnl']).mean()
            d_ev = (grp['deep_filled'] * grp['deep_pnl']).mean()
            g_ev = (grp['gbm_adaptive_filled'] * grp['gbm_adaptive_pnl']).mean()
            best = max(s_ev, d_ev, g_ev)
            winner = '浅挂' if s_ev >= d_ev and s_ev >= g_ev else ('深挂' if d_ev >= g_ev else 'GBM')
            print(f"    {name:<30} N={len(grp):<4} 浅EV={s_ev*100:+.3f}% 深EV={d_ev*100:+.3f}% GBM_EV={g_ev*100:+.3f}% → {winner}")

    print("\n" + "=" * 70)
    print("  四、GBM 自适应 vs 最优固定策略 — 逐笔对比")
    print("=" * 70)

    gbm_filled = df['gbm_adaptive_filled']
    gbm_pnls = df['gbm_adaptive_pnl']
    best_fixed_ev_s = (df['shallow_filled'] * df['shallow_pnl']).mean()
    best_fixed_ev_d = (df['deep_filled'] * df['deep_pnl']).mean()
    best_fixed = '浅挂' if best_fixed_ev_s >= best_fixed_ev_d else '深挂'
    best_fixed_ev = max(best_fixed_ev_s, best_fixed_ev_d)
    gbm_ev = (gbm_filled * gbm_pnls).mean()

    improvement = gbm_ev - best_fixed_ev
    print(f"\n  最优固定策略: {best_fixed} (EV={best_fixed_ev*100:+.3f}%)")
    print(f"  GBM自适应:    EV={gbm_ev*100:+.3f}%")
    print(f"  增量提升:     {improvement*100:+.3f}% ({improvement/best_fixed_ev*100 if best_fixed_ev != 0 else 0:+.1f}%)")

    gbm_choice = df['gbm_choice'].value_counts()
    print(f"\n  GBM 策略选择分布:")
    for choice, cnt in gbm_choice.items():
        print(f"    {choice}: {cnt} ({cnt/len(df):.1%})")

    better_than_shallow = ((gbm_filled * gbm_pnls) > (df['shallow_filled'] * df['shallow_pnl'])).sum()
    better_than_deep = ((gbm_filled * gbm_pnls) > (df['deep_filled'] * df['deep_pnl'])).sum()
    print(f"\n  GBM 逐笔优于固定浅挂: {better_than_shallow}/{len(df)} ({better_than_shallow/len(df):.1%})")
    print(f"  GBM 逐笔优于固定深挂: {better_than_deep}/{len(df)} ({better_than_deep/len(df):.1%})")

    print("\n" + "=" * 70)
    print("  五、Top 20 盈利信号 (GBM自适应)")
    print("=" * 70)

    filled_df = df[gbm_filled].copy()
    top20 = filled_df.nlargest(20, 'gbm_adaptive_pnl')[
        ['stock_code', '回测日期', 'pricing_proba', 'gbm_choice',
         'gbm_adaptive_pnl', 'gbm_adaptive_mfe', 'gbm_adaptive_status',
         'v44_trend', 'v44_bias_tier']
    ]
    top20['gbm_adaptive_pnl'] = (top20['gbm_adaptive_pnl'] * 100).round(2).astype(str) + '%'
    top20['gbm_adaptive_mfe'] = (top20['gbm_adaptive_mfe'] * 100).round(2).astype(str) + '%'
    top20['pricing_proba'] = top20['pricing_proba'].round(3)
    print(top20.to_string(index=False))

    print("\n" + "=" * 70)
    print("  六、Top 10 亏损信号 (GBM自适应)")
    print("=" * 70)

    bot10 = filled_df.nsmallest(10, 'gbm_adaptive_pnl')[
        ['stock_code', '回测日期', 'pricing_proba', 'gbm_choice',
         'gbm_adaptive_pnl', 'gbm_adaptive_mae', 'gbm_adaptive_status',
         'v44_trend', 'v44_bias_tier']
    ]
    bot10['gbm_adaptive_pnl'] = (bot10['gbm_adaptive_pnl'] * 100).round(2).astype(str) + '%'
    bot10['gbm_adaptive_mae'] = (bot10['gbm_adaptive_mae'] * 100).round(2).astype(str) + '%'
    bot10['pricing_proba'] = bot10['pricing_proba'].round(3)
    print(bot10.to_string(index=False))

    out_path = os.path.join(BASE_DIR, '..', 'data', 'result', 'pricing_gbm_backtest.csv')
    df.to_csv(out_path, index=False, float_format='%.4f')
    print(f"\n完整结果已保存: {out_path}")

    report = {
        'total_signals': len(df),
        'tp_pct': TP_PCT,
        'sl_pct': SL_PCT,
        'strategies': {}
    }
    for label, key in [('shallow', 'shallow'), ('deep', 'deep'), ('gbm_adaptive', 'gbm_adaptive')]:
        filled = df[f'{key}_filled']
        pnls = df[f'{key}_pnl']
        fp = pnls[filled]
        report['strategies'][label] = {
            'fill_rate': round(float(filled.mean()), 4),
            'filled_count': int(filled.sum()),
            'avg_pnl': round(float(fp.mean()) if len(fp) > 0 else 0, 6),
            'ev': round(float((filled * pnls).mean()), 6),
            'win_rate': round(float((fp > 0).mean()) if len(fp) > 0 else 0, 4),
            'max_loss': round(float(pnls.min()), 4),
        }
    report['gbm_proba_groups'] = {}
    for lo, hi, gl in [(0, 0.3, 'low'), (0.3, 0.7, 'mid'), (0.7, 1.001, 'high')]:
        mask = (df['pricing_proba'] >= lo) & (df['pricing_proba'] < hi)
        sub = df[mask]
        if len(sub) == 0:
            continue
        report['gbm_proba_groups'][gl] = {
            'count': int(len(sub)),
            'shallow_ev': round(float((sub['shallow_filled'] * sub['shallow_pnl']).mean()), 6),
            'deep_ev': round(float((sub['deep_filled'] * sub['deep_pnl']).mean()), 6),
            'gbm_ev': round(float((sub['gbm_adaptive_filled'] * sub['gbm_adaptive_pnl']).mean()), 6),
        }

    report_path = os.path.join(BASE_DIR, '..', 'data', 'result', 'pricing_gbm_backtest_summary.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"摘要已保存: {report_path}")

    return df, report


if __name__ == '__main__':
    run_backtest()
