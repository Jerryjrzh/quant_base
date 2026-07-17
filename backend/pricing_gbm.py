#!/usr/bin/env python3
"""
定价 GBM — 预测每笔信号的最优入场策略
基于 scheme_c_signals.csv (17K 20CM 信号) 训练

目标: shallow_entry_better = 1 (T0收盘入场 > 深挂5%入场)
特征: ma_slope, bias_20, v44_trend, v44_bias_tier, market_env, swing, T1 开盘特征

用法:
    cd backend
    python3 pricing_gbm.py
"""

import os
import json
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNALS_PATH = os.path.join(BASE_DIR, '..', 'data', 'result', 'SignalGenerator', 'scheme_c_signals.csv')
MODEL_PATH = os.path.join(BASE_DIR, '..', 'data', 'model', 'pricing_gbm_v1.pkl')
META_PATH = os.path.join(BASE_DIR, '..', 'data', 'model', 'pricing_gbm_v1_meta.json')

RAW_FEATURES = ['ma_slope', 'bias_20', 'swing',
                't1_open_gap', 't1_low_drop', 't1_close_strength',
                't1_range', 't1_body']
ONEHOT_PREFIXES = ['market_env', 'v44_trend', 'v44_bias_tier']


def simulate_trade_ohlc(close_t0, t_data, entry_price, tp_pct, sl_pct):
    """用真实 T1-T7 OHLC 模拟交易 (含成交判定)"""
    entry = entry_price
    tp_price = entry * (1 + tp_pct)
    sl_price = entry * (1 + sl_pct)
    mfe = 0.0
    mae = 0.0
    filled = False

    for d in range(1, 8):
        h = t_data.get(f'T{d}_High')
        l = t_data.get(f'T{d}_Low')
        if pd.isna(h) or pd.isna(l):
            break

        if not filled:
            day_mid = (h + l) / 2.0
            if l <= entry and day_mid >= entry * 0.995:
                filled = True
            else:
                continue

        pnl_h = (h - entry) / entry
        pnl_l = (l - entry) / entry
        if pnl_h > mfe:
            mfe = pnl_h
        if pnl_l < mae:
            mae = pnl_l

        hit_sl = l <= sl_price
        hit_tp = h >= tp_price

        if hit_sl and hit_tp:
            sl_depth = sl_price - l
            tp_depth = h - tp_price
            if sl_depth > tp_depth:
                hit_tp = False
            else:
                hit_sl = False

        if hit_sl:
            exit_p = min((h + l) / 2, sl_price)
            return {'pnl': (exit_p - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae}

        if hit_tp:
            exit_p = max((h + l) / 2, tp_price)
            return {'pnl': (exit_p - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae}

    if not filled:
        return {'pnl': 0.0, 'filled': False, 'mfe': 0.0, 'mae': 0.0}

    last_c = t_data.get('T7_Close')
    if pd.isna(last_c):
        last_h = t_data.get('T7_High', 0)
        last_l = t_data.get('T7_Low', 0)
        last_c = (last_h + last_l) / 2
    return {'pnl': (last_c - entry) / entry, 'filled': True, 'mfe': mfe, 'mae': mae}


def build_features(df):
    """构造 T1 日内特征"""
    df = df.copy()

    df['t1_open_gap'] = (df['T1_Open'] - df['close_t0']) / df['close_t0']
    df['t1_low_drop'] = (df['T1_Low'] - df['close_t0']) / df['close_t0']
    df['t1_close_strength'] = (df['T1_Close'] - df['T1_Low']) / (df['T1_High'] - df['T1_Low'] + 1e-9)
    df['t1_range'] = (df['T1_High'] - df['T1_Low']) / df['close_t0']
    df['t1_body'] = (df['T1_Close'] - df['T1_Open']) / df['close_t0']

    return df


def train_pricing_gbm():
    print("=" * 60)
    print("  定价 GBM v1 — 入场策略预测器")
    print("=" * 60)

    df = pd.read_csv(SIGNALS_PATH)
    print(f"\n加载数据: {len(df)} 信号")

    df['signal_date'] = pd.to_datetime(df['signal_date'])
    df = build_features(df)

    tp_pct, sl_pct = 0.18, -0.12

    shallow_results = []
    deep_results = []
    valid_mask = []

    for i, row in df.iterrows():
        close_t0 = row['close_t0']
        if pd.isna(close_t0) or close_t0 <= 0:
            valid_mask.append(False)
            continue

        t_data = {}
        for d in range(1, 8):
            for k in ['Open', 'High', 'Low', 'Close']:
                t_data[f'T{d}_{k}'] = row.get(f'T{d}_{k}')

        shallow_entry = close_t0
        deep_entry = close_t0 * 0.95

        r_shallow = simulate_trade_ohlc(close_t0, t_data, shallow_entry, tp_pct, sl_pct)
        r_deep = simulate_trade_ohlc(close_t0, t_data, deep_entry, tp_pct, sl_pct)

        shallow_results.append(r_shallow)
        deep_results.append(r_deep)
        valid_mask.append(True)

    df = df[valid_mask].copy().reset_index(drop=True)

    shallow_filled = np.array([r['filled'] for r in shallow_results])
    deep_filled = np.array([r['filled'] for r in deep_results])
    shallow_pnls = np.array([r['pnl'] for r in shallow_results])
    deep_pnls = np.array([r['pnl'] for r in deep_results])

    shallow_ev = np.nan_to_num(shallow_filled * shallow_pnls, nan=0.0)
    deep_ev = np.nan_to_num(deep_filled * deep_pnls, nan=0.0)

    s_filled_pnls = shallow_pnls[shallow_filled.astype(bool)]
    d_filled_pnls = deep_pnls[deep_filled.astype(bool)]
    s_avg = np.nanmean(s_filled_pnls) if len(s_filled_pnls) > 0 else 0
    d_avg = np.nanmean(d_filled_pnls) if len(d_filled_pnls) > 0 else 0
    s_ev_mean = np.nanmean(shallow_ev)
    d_ev_mean = np.nanmean(deep_ev)

    print(f"有效信号: {len(df)}")
    print(f"浅挂(T0收盘): 成交率={shallow_filled.mean():.1%}, 成交均PnL={s_avg*100:+.2f}%, EV={s_ev_mean*100:+.3f}%")
    print(f"深挂(-5%):     成交率={deep_filled.mean():.1%}, 成交均PnL={d_avg*100:+.2f}%, EV={d_ev_mean*100:+.3f}%")

    df['shallow_ev'] = shallow_ev
    df['deep_ev'] = deep_ev
    df['shallow_better'] = (shallow_ev > deep_ev).astype(int)

    print(f"\n目标分布: shallow_better=1: {df['shallow_better'].sum()} "
          f"({df['shallow_better'].mean():.1%})")

    df = pd.get_dummies(df, columns=ONEHOT_PREFIXES, prefix=ONEHOT_PREFIXES)

    train_mask = df['signal_date'] <= pd.to_datetime('2025-12-31')
    test_mask = df['signal_date'] > pd.to_datetime('2025-12-31')

    onehot_cols = [c for c in df.columns if any(c.startswith(p + '_') for p in ONEHOT_PREFIXES)]
    feature_cols = RAW_FEATURES + onehot_cols

    X_train = df.loc[train_mask, feature_cols].fillna(0)
    y_train = df.loc[train_mask, 'shallow_better']
    X_test = df.loc[test_mask, feature_cols].fillna(0)
    y_test = df.loc[test_mask, 'shallow_better']

    print(f"\n训练集: {len(X_train)} (2025)")
    print(f"测试集: {len(X_test)} (2026)")

    model = GradientBoostingClassifier(
        n_estimators=100,
        max_depth=3,
        learning_rate=0.1,
        subsample=0.8,
        random_state=42
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]

    f1 = f1_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_proba)

    print(f"\n=== 测试集评估 ===")
    print(f"  F1:        {f1:.4f}")
    print(f"  Precision: {prec:.4f}")
    print(f"  Recall:    {rec:.4f}")
    print(f"  AUC:       {auc:.4f}")

    importance = dict(zip(feature_cols, [round(float(x), 6) for x in model.feature_importances_]))
    top_feats = sorted(importance.items(), key=lambda x: -x[1])[:10]
    print(f"\n=== Top 10 特征重要性 ===")
    for feat, imp in top_feats:
        print(f"  {feat:<40} {imp:.4f}")

    # 验证: 按 GBM 概率分组看 PnL 差异
    print(f"\n=== 按定价概率分组的 PnL 验证 ===")
    test_df = df[test_mask].copy()
    test_df['pricing_proba'] = y_proba

    for lo, hi, label in [(0, 0.3, '深挂更好(<0.3)'), (0.3, 0.7, '中性(0.3~0.7)'), (0.7, 1.01, '浅挂更好(>0.7)')]:
        sub = test_df[(test_df['pricing_proba'] >= lo) & (test_df['pricing_proba'] < hi)]
        if len(sub) == 0:
            continue
        s_ev = sub['shallow_ev'].mean()
        d_ev = sub['deep_ev'].mean()
        best_ev = sub.apply(lambda r: max(r['shallow_ev'], r['deep_ev']), axis=1).mean()
        print(f"  {label:<25} N={len(sub):<5} 浅挂EV={s_ev*100:+.3f}% 深挂EV={d_ev*100:+.3f}% "
              f"最优选择EV={best_ev*100:+.3f}%")

    # 保存模型
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, 'wb') as f:
        pickle.dump(model, f)

    metadata = {
        'feature_cols': feature_cols,
        'onehot_cols': onehot_cols,
        'raw_features': RAW_FEATURES,
        'onehot_prefixes': ONEHOT_PREFIXES,
        'metrics': {
            'f1': round(f1, 4),
            'precision': round(prec, 4),
            'recall': round(rec, 4),
            'auc': round(auc, 4),
            'train_samples': int(len(X_train)),
            'test_samples': int(len(X_test)),
            'positive_rate': round(float(y_train.mean()), 4),
        },
        'feature_importance': importance,
        'tp_pct': tp_pct,
        'sl_pct': sl_pct,
        'model_version': 'pricing_gbm_v1',
    }
    with open(META_PATH, 'w') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    print(f"\n模型已保存: {MODEL_PATH}")
    print(f"元数据已保存: {META_PATH}")

    return model, metadata


def load_pricing_gbm():
    with open(MODEL_PATH, 'rb') as f:
        model = pickle.load(f)
    with open(META_PATH) as f:
        meta = json.load(f)
    return model, meta


def score_entry_strategy(df, model, meta):
    """
    对新信号打分，返回浅挂概率 [0,1]
    高概率(>0.7) → 推荐 T0 收盘浅挂
    低概率(<0.3) → 推荐 -5% 深挂
    """
    df = build_features(df.copy())
    df = pd.get_dummies(df, columns=meta['onehot_prefixes'], prefix=meta['onehot_prefixes'])

    for col in meta['feature_cols']:
        if col not in df.columns:
            df[col] = 0

    X = df[meta['feature_cols']].fillna(0)
    return model.predict_proba(X)[:, 1]


if __name__ == "__main__":
    train_pricing_gbm()
