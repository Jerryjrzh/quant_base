"""
Super Trend V1 Phase 1: 时序特征提取器 V2
从"一张照片"(截面特征) → "一段视频"(时序特征)

两类新特征:
1. 均线束状态 (MA Bundle): 粘合→发散过程量化
2. 黄金坑/假破位 (Washout): 洗盘形态检测
"""

import pandas as pd
import numpy as np
from scipy.stats import linregress
import warnings
warnings.filterwarnings('ignore')


# ================================================================
# 1. 均线束状态特征 (MA Bundle / Convergence-Divergence)
# ================================================================

def extract_ma_bundle_features(df, t0_idx, lookback=60):
    """
    均线束状态特征：量化 T0 前 MA5/10/20/60 的"粘合→发散"过程。

    真主升浪前，均线经历粘合（收敛）然后快速发散；假突破则均线始终混乱或已过度发散。

    参数:
        df: 日线 DataFrame (需含 ma5, ma10, ma20, ma60, close 列)
        t0_idx: T0 在 df 中的位置
        lookback: 回溯天数 (默认 60)

    返回:
        dict:
          ma_dispersion_5d: T0前5天均线离散度均值
          ma_dispersion_20d: T0前20天均线离散度均值
          ma_glue_max_days: 离散度<2%的最长连续天数 (T0前20天内)
          ma_glue_recency: 最近一次离散度从<2%上穿>2%距T0的天数 (越小=刚发散)
          ma_divergence_speed: T0前5天离散度的线性回归斜率
          ma_convergence_flag: T0前10天内是否存在离散度<1.5%的窗口 (bool)
    """
    ma_cols = ['ma5', 'ma10', 'ma20', 'ma60']
    if not all(c in df.columns for c in ma_cols):
        return {}
    if t0_idx < 20 or t0_idx >= len(df):
        return {}

    start_idx = max(0, t0_idx - lookback)
    window = df.iloc[start_idx:t0_idx + 1]

    ma_matrix = window[ma_cols].values
    close_vals = window['close'].values

    valid_mask = ~np.isnan(ma_matrix).any(axis=1) & (close_vals > 0.01)
    if valid_mask.sum() < 10:
        return {}

    dispersion = np.full(len(window), np.nan)
    for i in range(len(window)):
        if valid_mask[i]:
            dispersion[i] = np.std(ma_matrix[i]) / close_vals[i]

    features = {}
    disp_valid = dispersion[~np.isnan(dispersion)]
    if len(disp_valid) < 5:
        return features

    last_5 = dispersion[-5:]
    last_5_valid = last_5[~np.isnan(last_5)]
    if len(last_5_valid) > 0:
        features['ma_dispersion_5d'] = float(np.mean(last_5_valid))

    last_20 = dispersion[-20:]
    last_20_valid = last_20[~np.isnan(last_20)]
    if len(last_20_valid) > 0:
        features['ma_dispersion_20d'] = float(np.mean(last_20_valid))

    glue_threshold = 0.02
    glue_mask = dispersion < glue_threshold
    glue_mask[np.isnan(dispersion)] = False

    max_streak = 0
    current_streak = 0
    for v in glue_mask[-20:]:
        if v:
            current_streak += 1
            max_streak = max(max_streak, current_streak)
        else:
            current_streak = 0
    features['ma_glue_max_days'] = max_streak

    recency = np.nan
    for i in range(len(dispersion) - 1, 0, -1):
        if not np.isnan(dispersion[i]) and not np.isnan(dispersion[i - 1]):
            if dispersion[i - 1] < glue_threshold and dispersion[i] >= glue_threshold:
                recency = len(dispersion) - 1 - i
                break
    features['ma_glue_recency'] = float(recency) if not np.isnan(recency) else np.nan

    if len(last_5_valid) >= 3:
        valid_indices = []
        valid_values = []
        for i, v in enumerate(last_5):
            if not np.isnan(v):
                valid_indices.append(i)
                valid_values.append(v)
        if len(valid_indices) >= 3:
            slope, _, _, _, _ = linregress(valid_indices, valid_values)
            features['ma_divergence_speed'] = float(slope)

    convergence_threshold = 0.015
    last_10 = dispersion[-10:]
    last_10_valid = last_10[~np.isnan(last_10)]
    features['ma_convergence_flag'] = int(np.any(last_10_valid < convergence_threshold)) if len(last_10_valid) > 0 else 0

    return features


# ================================================================
# 2. 黄金坑/假破位特征 (Washout / False Breakdown)
# ================================================================

def extract_washout_features(df, t0_idx, lookback=20):
    """
    黄金坑/假破位特征：检测 T0 前是否存在"跌破关键均线→快速收回"的洗盘形态。

    主力洗盘典型模式: 跌破 MA60 → 1~3天内收回 → 主升浪启动。

    参数:
        df: 日线 DataFrame (需含 close, ma20, ma60 列)
        t0_idx: T0 在 df 中的位置
        lookback: 回溯天数 (默认 20)

    返回:
        dict:
          washout_ma60_flag: 是否存在 MA60 假破位 (bool)
          washout_ma60_depth: 跌破 MA60 的最大深度 (百分比)
          washout_ma60_recovery_days: 从跌破到收回的天数
          washout_ma20_flag: 是否存在 MA20 假破位
          washout_ma20_depth: 跌破 MA20 的最大深度
          washout_ma20_recovery_days: 从跌破到收回的天数
          lower_shadow_count: T0前15天内长下影线天数
    """
    if t0_idx < 15 or t0_idx >= len(df):
        return {}

    start_idx = max(0, t0_idx - lookback)
    window = df.iloc[start_idx:t0_idx + 1]

    features = {}

    for ma_name, ma_col in [('ma60', 'ma60'), ('ma20', 'ma20')]:
        if ma_col not in df.columns:
            features[f'washout_{ma_name}_flag'] = 0
            features[f'washout_{ma_name}_depth'] = 0.0
            features[f'washout_{ma_name}_recovery_days'] = np.nan
            continue

        close_vals = window['close'].values
        ma_vals = window[ma_col].values

        valid = ~np.isnan(ma_vals) & ~np.isnan(close_vals) & (ma_vals > 0.01)
        if valid.sum() < 5:
            features[f'washout_{ma_name}_flag'] = 0
            features[f'washout_{ma_name}_depth'] = 0.0
            features[f'washout_{ma_name}_recovery_days'] = np.nan
            continue

        flag = 0
        max_depth = 0.0
        recovery_days = np.nan
        breakdown_start = None

        for i in range(len(close_vals)):
            if not valid[i]:
                continue

            below = close_vals[i] < ma_vals[i]
            pct_below = (ma_vals[i] - close_vals[i]) / ma_vals[i] if ma_vals[i] > 0.01 else 0

            if below:
                if breakdown_start is None:
                    breakdown_start = i
                max_depth = max(max_depth, pct_below)
            else:
                if breakdown_start is not None:
                    flag = 1
                    recovery_days = i - breakdown_start
                    breakdown_start = None

        features[f'washout_{ma_name}_flag'] = flag
        features[f'washout_{ma_name}_depth'] = float(max_depth) if flag else 0.0
        features[f'washout_{ma_name}_recovery_days'] = float(recovery_days) if not np.isnan(recovery_days) else np.nan

    shadow_start = max(0, t0_idx - 15)
    shadow_window = df.iloc[shadow_start:t0_idx + 1]
    shadow_count = 0
    for i in range(len(shadow_window)):
        row = shadow_window.iloc[i]
        body = abs(row['close'] - row['open'])
        lower_shadow = min(row['close'], row['open']) - row['low']
        if body > 0.001 and lower_shadow > body * 2:
            shadow_count += 1
    features['lower_shadow_count'] = shadow_count

    return features


# ================================================================
# 3. 量能时序特征 (Volume Sequence)
# ================================================================

def extract_volume_sequence_features(df, t0_idx, lookback=20):
    """
    量能时序特征：量化 T0 前的成交量变化模式。

    参数:
        df: 日线 DataFrame (需含 volume 列)
        t0_idx: T0 在 df 中的位置
        lookback: 回溯天数

    返回:
        dict:
          vol_trend_10d: T0前10天成交量的线性回归斜率 (标准化)
          vol_shrink_streak: T0前最长连续缩量天数
          vol_expansion_ratio: T0当天量 / T0前5天均量 (已在旧特征中, 此处保留)
          vol_low_point_position: T0前20天内最低量出现的位置 (0=最远, 1=最近)
    """
    if 'volume' not in df.columns or t0_idx < 20:
        return {}

    features = {}

    vol_10 = df['volume'].iloc[max(0, t0_idx - 10):t0_idx].values
    if len(vol_10) >= 5 and np.mean(vol_10) > 0:
        indices = np.arange(len(vol_10))
        slope, _, _, _, _ = linregress(indices, vol_10)
        features['vol_trend_10d'] = float(slope / np.mean(vol_10))

    vol_window = df['volume'].iloc[max(0, t0_idx - lookback):t0_idx].values
    if len(vol_window) >= 5:
        max_streak = 0
        current_streak = 0
        for i in range(1, len(vol_window)):
            if vol_window[i] < vol_window[i - 1]:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        features['vol_shrink_streak'] = max_streak

        min_pos = np.argmin(vol_window)
        features['vol_low_point_position'] = float(min_pos / (len(vol_window) - 1))

    return features


# ================================================================
# 4. 价格行为序列特征 (Price Action Sequence)
# ================================================================

def extract_price_action_features(df, t0_idx, lookback=10):
    """
    价格行为序列编码：将 T0 前 K 线转为"阳/阴/平"三元序列，提取模式特征。

    参数:
        df: 日线 DataFrame (需含 open, close 列)
        t0_idx: T0 在 df 中的位置
        lookback: 回溯天数

    返回:
        dict:
          streak_max_bull: 最长连续阳线天数
          streak_max_bear: 最长连续阴线天数
          bull_ratio_10d: T0前10天阳线占比
          last_3_pattern: 最近3天的模式编码 (数值化)
    """
    if t0_idx < lookback:
        return {}

    start_idx = t0_idx - lookback
    window = df.iloc[start_idx:t0_idx]

    if 'open' not in window.columns or 'close' not in window.columns:
        return {}

    features = {}

    changes = (window['close'] - window['open']) / window['open']
    symbols = []
    for c in changes:
        if c > 0.005:
            symbols.append('bull')
        elif c < -0.005:
            symbols.append('bear')
        else:
            symbols.append('flat')

    max_bull = 0
    max_bear = 0
    cur_bull = 0
    cur_bear = 0
    for s in symbols:
        if s == 'bull':
            cur_bull += 1
            max_bull = max(max_bull, cur_bull)
            cur_bear = 0
        elif s == 'bear':
            cur_bear += 1
            max_bear = max(max_bear, cur_bear)
            cur_bull = 0
        else:
            cur_bull = 0
            cur_bear = 0

    features['streak_max_bull'] = max_bull
    features['streak_max_bear'] = max_bear
    features['bull_ratio_10d'] = symbols.count('bull') / len(symbols) if symbols else 0

    if len(symbols) >= 3:
        last3 = symbols[-3:]
        pattern_code = 0
        for i, s in enumerate(last3):
            val = {'bull': 2, 'flat': 1, 'bear': 0}[s]
            pattern_code += val * (3 ** i)
        features['last_3_pattern'] = pattern_code

    return features


# ================================================================
# 主入口: 提取所有 V2 时序特征
# ================================================================

def extract_all_v2_features(df, t0_idx):
    """
    提取所有 V2 时序特征（均线束 + 黄金坑 + 量能 + 价格行为）。

    参数:
        df: 个股完整日线 DataFrame
        t0_idx: T0 在 df 中的位置

    返回:
        dict: 所有新特征
    """
    features = {}
    features.update(extract_ma_bundle_features(df, t0_idx))
    features.update(extract_washout_features(df, t0_idx))
    features.update(extract_volume_sequence_features(df, t0_idx))
    features.update(extract_price_action_features(df, t0_idx))
    return features


def test_v2_features():
    """V2 特征提取单元测试"""
    print("=== V2 时序特征测试 ===")

    np.random.seed(42)
    dates = pd.date_range('2024-01-01', periods=200, freq='D')
    close = 100 + np.random.randn(200).cumsum() * 0.5
    df = pd.DataFrame({
        'open': close - np.random.rand(200) * 0.5,
        'high': close + np.abs(np.random.randn(200)),
        'low': close - np.abs(np.random.randn(200)),
        'close': close,
        'volume': np.random.randint(100000, 1000000, 200),
        'ma5': pd.Series(close).rolling(5).mean().values,
        'ma10': pd.Series(close).rolling(10).mean().values,
        'ma20': pd.Series(close).rolling(20).mean().values,
        'ma60': pd.Series(close).rolling(60).mean().values,
    }, index=dates)

    t0_idx = 100
    features = extract_all_v2_features(df, t0_idx)

    print(f"T0索引: {t0_idx}")
    print(f"提取特征数: {len(features)}")
    print(f"特征列表:")
    for k, v in sorted(features.items()):
        if isinstance(v, float):
            print(f"  {k}: {v:.6f}")
        else:
            print(f"  {k}: {v}")

    expected_keys = [
        'ma_dispersion_5d', 'ma_dispersion_20d', 'ma_glue_max_days',
        'ma_glue_recency', 'ma_divergence_speed', 'ma_convergence_flag',
        'washout_ma60_flag', 'washout_ma60_depth',
        'washout_ma20_flag', 'washout_ma20_depth',
        'lower_shadow_count',
        'vol_trend_10d', 'vol_shrink_streak', 'vol_low_point_position',
        'streak_max_bull', 'streak_max_bear', 'bull_ratio_10d',
    ]
    missing = [k for k in expected_keys if k not in features]
    if missing:
        print(f"\n⚠ 缺失特征: {missing}")
    else:
        print(f"\n✓ 所有预期特征已生成")

    return features


if __name__ == "__main__":
    test_v2_features()
