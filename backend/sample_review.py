"""
Super Trend 样本人工抽检脚本
随机抽取正/负样本，展示 T0 前后价格走势，供人工确认标签合理性。
"""

import os
import sys
import pandas as pd
import numpy as np
from data_handler import get_full_data_with_indicators

CANDIDATES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "data", "result", "super_trend", "super_trend_candidates_full.csv"
)

DEFAULT_N_POS = 10
DEFAULT_N_NEG = 10
CONTEXT_BEFORE = 10
CONTEXT_AFTER = 22


def load_candidates(path=CANDIDATES_PATH):
    df = pd.read_csv(path)
    pos = df[df['is_positive'] == True]
    neg = df[df['is_positive'] == False]
    print(f"加载候选: {len(df)} 条 (正样本 {len(pos)}, 负样本 {len(neg)})")
    print(f"正样本比例: {len(pos)/len(df):.1%}")
    return pos, neg


def print_price_context(stock_code, t0_date_str, daily_gain, future_mfe, future_mae,
                        is_positive, sample_type, t1_gap_up_pct, t1_low_pct):
    """加载个股数据，打印 T0 前后价格走势"""
    df = get_full_data_with_indicators(stock_code)
    if df is None:
        print(f"  [!] 无法加载 {stock_code} 数据")
        return

    date_col = pd.to_datetime(df.index) if not isinstance(df.index, pd.DatetimeIndex) else df.index
    try:
        t0_date = pd.to_datetime(t0_date_str)
        t0_idx = date_col.get_loc(t0_date)
    except (KeyError, TypeError):
        dates_str = [str(d)[:10] for d in date_col]
        if t0_date_str[:10] in dates_str:
            t0_idx = dates_str.index(t0_date_str[:10])
        else:
            print(f"  [!] 日期 {t0_date_str} 在 {stock_code} 中找不到")
            return

    start = max(0, t0_idx - CONTEXT_BEFORE)
    end = min(len(df), t0_idx + CONTEXT_AFTER + 1)
    window = df.iloc[start:end]
    t0_price = df.iloc[t0_idx]['close']

    label = "POSITIVE" if is_positive else "NEGATIVE"
    print(f"\n{'='*78}")
    print(f"  [{label}] {stock_code}  T0: {t0_date_str[:10]}  收盘价: {t0_price:.2f}")
    print(f"  当日涨幅: {daily_gain:+.2%}   22d MFE: {future_mfe:+.2%}   22d MAE: {future_mae:+.2%}")
    print(f"  T+1 跳空: {t1_gap_up_pct:+.2%}   T+1 最低: {t1_low_pct:+.2%}")
    print(f"  样本类型: {sample_type}")
    print(f"{'='*78}")

    print(f"  {'日期':>12s}  {'开盘':>8s}  {'最高':>8s}  {'最低':>8s}  {'收盘':>8s}  {'涨跌%':>7s}  {'量比T0':>8s}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*7}  {'-'*8}")

    t0_vol = df.iloc[t0_idx]['volume']
    for offset in range(start - t0_idx, end - t0_idx):
        idx = t0_idx + offset
        if idx < 0 or idx >= len(df):
            continue
        row = df.iloc[idx]
        dt = str(df.index[idx])[:10]
        o, h, l, c = row['open'], row['high'], row['low'], row['close']
        chg = ((c / df.iloc[idx - 1]['close']) - 1.0) if idx > 0 and df.iloc[idx - 1]['close'] > 0.01 else 0
        vol_pct = (row['volume'] / t0_vol * 100) if t0_vol > 0 else 0

        marker = ""
        if offset == 0:
            marker = " << T0"
        elif 1 <= offset <= 5:
            marker = f"  T+{offset}"
        elif offset == CONTEXT_AFTER:
            marker = f"  T+{offset}"

        print(f"  {dt:>12s}  {o:8.2f}  {h:8.2f}  {l:8.2f}  {c:8.2f}  {chg:+7.2%}  {vol_pct:7.1f}%{marker}")

    mfe_check = (window.iloc[1:CONTEXT_AFTER + 1]['high'].max() / t0_price - 1.0) if t0_price > 0.01 else 0
    mae_check = (window.iloc[1:CONTEXT_AFTER + 1]['low'].min() / t0_price - 1.0) if t0_price > 0.01 else 0
    print(f"  ---")
    print(f"  窗口验证 MFE(22d): {mfe_check:+.2%}   MAE(22d): {mae_check:+.2%}")


def stratified_sample(df, n, by='stock_code'):
    """分层抽样：每只股票最多取1条，确保覆盖不同个股"""
    if len(df) <= n:
        return df
    unique_codes = df[by].unique()
    chosen = np.random.choice(unique_codes, size=min(n, len(unique_codes)), replace=False)
    subset = df[df[by].isin(chosen)]
    return subset.groupby(by, group_keys=False).head(1)


def classify_market(stock_code):
    if stock_code.startswith('sh60'):
        return '沪主板'
    elif stock_code.startswith('sz00'):
        return '深主板'
    elif stock_code.startswith('sz30'):
        return '创业板'
    elif stock_code.startswith('sh68'):
        return '科创板'
    elif stock_code.startswith('bj'):
        return '北交所'
    return '其他'


def main():
    n_pos = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N_POS
    n_neg = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_N_NEG
    market_filter = sys.argv[3] if len(sys.argv) > 3 else None

    pos_df, neg_df = load_candidates()

    pos_df = pos_df.copy()
    neg_df = neg_df.copy()
    pos_df['board'] = pos_df['stock_code'].apply(classify_market)
    neg_df['board'] = neg_df['stock_code'].apply(classify_market)

    print(f"\n正样本板块分布: {dict(pos_df['board'].value_counts())}")
    print(f"负样本板块分布: {dict(neg_df['board'].value_counts())}")

    if market_filter:
        pos_df = pos_df[pos_df['board'] == market_filter]
        neg_df = neg_df[neg_df['board'] == market_filter]
        print(f"\n已过滤板块: {market_filter} (正样本 {len(pos_df)}, 负样本 {len(neg_df)})")

    print(f"\n{'#'*78}")
    print(f"# 正样本抽检 ({n_pos} 条)")
    print(f"{'#'*78}")
    pos_sample = stratified_sample(pos_df, n_pos).reset_index(drop=True)
    for _, row in pos_sample.iterrows():
        try:
            print_price_context(
                row['stock_code'], str(row['t0_date']),
                row['daily_gain'], row['future_mfe'], row['future_mae'],
                row['is_positive'], row['sample_type'],
                row.get('t1_gap_up_pct', np.nan), row.get('t1_low_pct', np.nan)
            )
        except KeyError as e:
            print(f"  [!] 字段缺失 {e}, 跳过")

    print(f"\n{'#'*78}")
    print(f"# 负样本抽检 ({n_neg} 条)")
    print(f"{'#'*78}")
    neg_sample = stratified_sample(neg_df, n_neg).reset_index(drop=True)
    for _, row in neg_sample.iterrows():
        try:
            print_price_context(
                row['stock_code'], str(row['t0_date']),
                row['daily_gain'], row['future_mfe'], row['future_mae'],
                row['is_positive'], row['sample_type'],
                row.get('t1_gap_up_pct', np.nan), row.get('t1_low_pct', np.nan)
            )
        except KeyError as e:
            print(f"  [!] 字段缺失 {e}, 跳过")

    print(f"\n{'='*78}")
    print("抽检完毕。请逐条确认：")
    print("  正样本：T0 是否为合理的主升浪起爆点？未来走势是否匹配 MFE？")
    print("  负样本：T0 是否确实像假突破？未来走势是否拉胯？")
    print(f"{'='*78}")


if __name__ == "__main__":
    main()
