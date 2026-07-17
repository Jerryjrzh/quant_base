"""
Super Trend策略：EDA 分布分析脚本
读取全量异动数据，通过分位数统计倒推最优的正/负样本阈值。
"""

import os
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

OUTPUT_DIR = os.path.join("data", "result", "super_trend", "eda")
INPUT_PATH = os.path.join(OUTPUT_DIR, 'all_market_anomalies.csv')

MARKET_LABELS = {
    'main_sh': '沪主板(10%)',
    'main_sz': '深主板(10%)',
    'chinext': '创业板(20%)',
    'star': '科创板(20%)',
    'bse': '北交所(30%)',
    'other': '其他',
}


def load_data():
    if not os.path.exists(INPUT_PATH):
        raise FileNotFoundError(
            f"未找到异动数据: {INPUT_PATH}\n"
            f"请先运行: python super_trend_anomaly_scanner.py"
        )
    df = pd.read_csv(INPUT_PATH)

    # 去噪与异常值清洗
    initial_len = len(df)
    # 过滤完全死水（未来既没涨也没跌的停牌/一字板数据）
    mfe_col = 'future_mfe_22d'
    mae_col = 'future_mae_22d'
    if mfe_col in df.columns and mae_col in df.columns:
        df = df[(df[mfe_col] > 0) | (df[mae_col] < 0)]
    # 过滤极端异常值（22 天涨幅超 500%，多为未复权数据错误）
    if mfe_col in df.columns:
        df = df[df[mfe_col] <= 5.0]

    cleaned = initial_len - len(df)
    print(f"数据清洗: 移除 {cleaned} 条异常数据 ({cleaned / initial_len:.1%})")
    print(f"加载异动数据: {len(df)} 条, {df['stock_code'].nunique()} 只股票")
    print(f"时间范围: {df['t0_date'].min()} → {df['t0_date'].max()}\n")
    return df


def analyze_mfe_distribution(df):
    """未来最高涨幅 (MFE) 分位数分析"""
    print("=" * 60)
    print("一、未来 MFE 分位数分析（倒推正样本阈值）")
    print("=" * 60)

    for window in [10, 22, 60]:
        col = f'future_mfe_{window}d'
        if col not in df.columns:
            continue
        valid = df[col].dropna()
        print(f"\n--- 未来 {window} 天最高涨幅 (N={len(valid)}) ---")
        quantiles = valid.quantile([0.50, 0.75, 0.90, 0.95, 0.97, 0.99])
        for q, val in quantiles.items():
            print(f"  P{int(q*100):>2}: {val:>8.2%}")
        print(f"  均值: {valid.mean():.2%}  最大: {valid.max():.2%}")

    print(f"\n>> 建议: 正样本阈值取 P95~P97 之间的值")


def analyze_mae_distribution(df):
    """未来最大回撤 (MAE) 分位数分析"""
    print(f"\n{'=' * 60}")
    print("二、未来 MAE 分位数分析（倒推止损/回撤容忍度）")
    print("=" * 60)

    for window in [10, 22, 60]:
        col = f'future_mae_{window}d'
        if col not in df.columns:
            continue
        valid = df[col].dropna()
        print(f"\n--- 未来 {window} 天最大回撤 (N={len(valid)}) ---")
        quantiles = valid.quantile([0.01, 0.05, 0.10, 0.25, 0.50])
        for q, val in quantiles.items():
            print(f"  P{int(q*100):>2}: {val:>8.2%}")
        print(f"  均值: {valid.mean():.2%}  最小: {valid.min():.2%}")


def analyze_by_market_type(df):
    """分板块统计异动特征"""
    print(f"\n{'=' * 60}")
    print("三、分板块异动特征对比")
    print("=" * 60)

    if 'market_type' not in df.columns:
        print("无 market_type 列，跳过")
        return

    print(f"\n{'板块':<14} {'异动数':>6} {'当日涨幅中位':>12} {'量比中位':>8} "
          f"{'22dMFE中位':>10} {'22dMFE_P95':>10}")
    print("-" * 72)

    for mtype, group in df.groupby('market_type'):
        label = MARKET_LABELS.get(mtype, mtype)
        n = len(group)
        gain_med = group['daily_gain'].median()
        vol_med = group['vol_ratio'].median()
        mfe_22 = group['future_mfe_22d'].dropna()
        mfe_med = mfe_22.median() if len(mfe_22) > 0 else np.nan
        mfe_p95 = mfe_22.quantile(0.95) if len(mfe_22) > 0 else np.nan
        print(f"{label:<14} {n:>6} {gain_med:>12.2%} {vol_med:>8.2f} "
              f"{mfe_med:>10.2%} {mfe_p95:>10.2%}")


def analyze_daily_gain_thresholds(df):
    """当日涨幅门槛 vs 未来表现的关系"""
    print(f"\n{'=' * 60}")
    print("四、当日涨幅门槛 vs 未来 22 天表现（倒推异动触发门槛）")
    print("=" * 60)

    mfe_col = 'future_mfe_22d'
    if mfe_col not in df.columns:
        print("无 future_mfe_22d 列，跳过")
        return

    valid = df.dropna(subset=[mfe_col])
    thresholds = [0.03, 0.04, 0.05, 0.07, 0.10]

    print(f"\n{'涨幅门槛':>8} {'触发数':>8} {'MFE中位':>10} {'MFE>30%概率':>12} {'MFE>50%概率':>12}")
    print("-" * 60)

    for thr in thresholds:
        subset = valid[valid['daily_gain'] >= thr]
        if len(subset) == 0:
            continue
        mfe_med = subset[mfe_col].median()
        prob_30 = (subset[mfe_col] > 0.30).mean()
        prob_50 = (subset[mfe_col] > 0.50).mean()
        print(f"{thr:>8.0%} {len(subset):>8} {mfe_med:>10.2%} {prob_30:>12.2%} {prob_50:>12.2%}")


def analyze_position_impact(df):
    """位置（距底部/顶部距离）对未来爆发力的影响"""
    print(f"\n{'=' * 60}")
    print("五、异动位置 vs 未来爆发力（位置决定性质）")
    print("=" * 60)

    mfe_col = 'future_mfe_22d'
    pos_col = 'position_from_bottom'
    if mfe_col not in df.columns or pos_col not in df.columns:
        print("缺少必要列，跳过")
        return

    valid = df.dropna(subset=[mfe_col, pos_col])

    bins = [
        ('深坑底部 (<20%)', valid[pos_col] < 0.20),
        ('底部区域 (20-40%)', (valid[pos_col] >= 0.20) & (valid[pos_col] < 0.40)),
        ('中部区域 (40-60%)', (valid[pos_col] >= 0.40) & (valid[pos_col] < 0.60)),
        ('高位区域 (60-80%)', (valid[pos_col] >= 0.60) & (valid[pos_col] < 0.80)),
        ('高位顶部 (>80%)', valid[pos_col] >= 0.80),
    ]

    print(f"\n{'位置区间':<20} {'样本数':>6} {'MFE中位':>10} {'MFE>30%':>10} {'MFE>50%':>10}")
    print("-" * 62)

    for label, mask in bins:
        subset = valid[mask]
        if len(subset) == 0:
            continue
        mfe_med = subset[mfe_col].median()
        prob_30 = (subset[mfe_col] > 0.30).mean()
        prob_50 = (subset[mfe_col] > 0.50).mean()
        print(f"{label:<20} {len(subset):>6} {mfe_med:>10.2%} {prob_30:>10.2%} {prob_50:>10.2%}")


def analyze_vol_ratio_impact(df):
    """量比对未来表现的影响"""
    print(f"\n{'=' * 60}")
    print("六、量比 vs 未来 22 天表现")
    print("=" * 60)

    mfe_col = 'future_mfe_22d'
    vol_col = 'vol_ratio'
    if mfe_col not in df.columns or vol_col not in df.columns:
        print("缺少必要列，跳过")
        return

    valid = df.dropna(subset=[mfe_col, vol_col])

    bins = [
        ('量比 1.5-2.0', (valid[vol_col] >= 1.5) & (valid[vol_col] < 2.0)),
        ('量比 2.0-3.0', (valid[vol_col] >= 2.0) & (valid[vol_col] < 3.0)),
        ('量比 3.0-5.0', (valid[vol_col] >= 3.0) & (valid[vol_col] < 5.0)),
        ('量比 5.0-10', (valid[vol_col] >= 5.0) & (valid[vol_col] < 10.0)),
        ('量比 >10', valid[vol_col] >= 10.0),
    ]

    print(f"\n{'量比区间':<16} {'样本数':>6} {'MFE中位':>10} {'MFE>30%':>10} {'MFE>50%':>10}")
    print("-" * 58)

    for label, mask in bins:
        subset = valid[mask]
        if len(subset) == 0:
            continue
        mfe_med = subset[mfe_col].median()
        prob_30 = (subset[mfe_col] > 0.30).mean()
        prob_50 = (subset[mfe_col] > 0.50).mean()
        print(f"{label:<16} {len(subset):>6} {mfe_med:>10.2%} {prob_30:>10.2%} {prob_50:>10.2%}")


def derive_thresholds(df):
    """金字塔法则：根据分布倒推正/负样本阈值"""
    print(f"\n{'=' * 60}")
    print("七、金字塔法则 — 阈值倒推建议")
    print("=" * 60)

    mfe_col = 'future_mfe_22d'
    if mfe_col not in df.columns:
        return

    valid = df[mfe_col].dropna()
    total = len(valid)

    p95 = valid.quantile(0.95)
    p97 = valid.quantile(0.97)
    p99 = valid.quantile(0.99)
    p50 = valid.quantile(0.50)
    p25 = valid.quantile(0.25)

    print(f"\n基于 {total} 个异动日的 22 天 MFE 分布：")
    print(f"  极品正样本 (Top 3-5%):  future_mfe >= {p95:.2%} ~ {p97:.2%}")
    print(f"  绝对负样本 (Bottom 50%): future_mfe <= {p50:.2%}")
    print(f"  模糊中间层:             {p50:.2%} < future_mfe < {p95:.2%} → 训练时丢弃")

    print(f"\n建议参数：")
    print(f"  MIN_GAIN = {p95:.2f}  (P95，正样本)")
    print(f"  NEG_MAX_FUTURE_GAIN = {p50:.2f}  (P50 以下，负样本)")
    print(f"  预期正样本比例: ~{(valid >= p95).mean():.1%}")
    print(f"  预期负样本比例: ~{(valid <= p50).mean():.1%}")
    print(f"  训练丢弃比例: ~{((valid > p50) & (valid < p95)).mean():.1%}")


def main():
    print("=== Super Trend EDA 分布分析 ===\n")

    df = load_data()

    analyze_mfe_distribution(df)
    analyze_mae_distribution(df)
    analyze_by_market_type(df)
    analyze_daily_gain_thresholds(df)
    analyze_position_impact(df)
    analyze_vol_ratio_impact(df)
    derive_thresholds(df)

    # 保存分析摘要
    summary_path = os.path.join(OUTPUT_DIR, 'eda_summary.txt')
    print(f"\n分析完成。如需保存，请重定向输出:")
    print(f"  python super_trend_eda_analysis.py | tee {summary_path}")


if __name__ == "__main__":
    main()
