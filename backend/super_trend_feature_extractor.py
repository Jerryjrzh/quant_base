"""
Super Trend策略：时序特征提取器
实现三大时序特征提取方案
"""

import pandas as pd
import numpy as np
from scipy.stats import linregress
import warnings
warnings.filterwarnings('ignore')

# 方案1：区间极值与落差特征
def extract_delta_range_features(df, t0_idx, window=15):
    """提取区间极值与落差特征"""
    start_idx = max(0, t0_idx - window)
    window_df = df.iloc[start_idx:t0_idx+1]
    t0_row = window_df.iloc[-1]
    
    features = {}
    
    # 1. RSI爆发力
    rsi_col = 'rsi6' if 'rsi6' in window_df.columns else ('rsi14' if 'rsi14' in window_df.columns else None)
    if rsi_col:
        rsi_min = window_df[rsi_col].min()
        features['rsi_explosion_force'] = t0_row[rsi_col] - rsi_min
    
    # 2. MACD坑深
    if 'macd' in window_df.columns:
        features['macd_pit_depth'] = window_df['macd'].min()
    
    # 3. 坑底反弹幅度（防除零）
    lowest_price = window_df['low'].min()
    if lowest_price > 0.01:
        features['price_rebound_from_pit'] = (t0_row['close'] / lowest_price) - 1.0
    else:
        features['price_rebound_from_pit'] = 0.0
    
    return features

# 方案2：持续状态与计数特征
def extract_duration_counting_features(df, t0_idx, window=15):
    """提取持续状态与计数特征"""
    start_idx = max(0, t0_idx - window)
    window_df = df.iloc[start_idx:t0_idx+1]
    
    features = {}
    
    # 1. 水下窒息天数 (MACD水下)
    if 'dif' in window_df.columns and 'dea' in window_df.columns:
        underwater_mask = (window_df['dif'] < 0) & (window_df['dea'] < 0)
        features['days_underwater'] = underwater_mask.sum()
    
    # 2. 假破位天数 (收盘价跌破MA30)
    if 'ma30' in window_df.columns:
        fake_breakdown_mask = window_df['close'] < window_df['ma30']
        features['days_below_ma30'] = fake_breakdown_mask.sum()
    
    # 3. 地量天数
    if 'volume' in window_df.columns:
        avg_vol = window_df['volume'].mean()
        if avg_vol > 0:
            dry_up_mask = window_df['volume'] < (avg_vol * 0.5)
            features['vol_dryup_count'] = dry_up_mask.sum()
    
    return features

# 方案3：黄金坑特征检测
def extract_golden_pit_features(df, t0_idx):
    """提取黄金坑特征"""
    if t0_idx < 20:
        return {}
    
    current = df.iloc[t0_idx]
    features = {}
    
    # 1. 中期均线破位但长期均线向上
    if all(col in df.columns for col in ['ma30', 'ma60', 'ma240']):
        features['is_fake_breakdown'] = int(
            current['close'] < current['ma30'] and 
            current['close'] < current['ma60'] and 
            current['close'] > current['ma240'] and 
            current['ma240'] > df.iloc[t0_idx-20]['ma240']
        )
    
    # 2. 水下点火 (MACD刚翻红)
    if all(col in df.columns for col in ['macd', 'dif', 'dea']):
        features['is_water_ignition'] = int(
            current['macd'] > 0 and 
            df.iloc[t0_idx-1]['macd'] <= 0 and
            current['dif'] < 0 and current['dea'] < 0
        )
    
    # 3. 极致缩量
    if 'volume' in df.columns:
        vol_ma20 = df['volume'].iloc[t0_idx-20:t0_idx].mean()
        current_vol = current['volume']
        if vol_ma20 > 0:
            features['is_extreme_volume_dry'] = int(current_vol < vol_ma20 * 0.8)
        else:
            features['is_extreme_volume_dry'] = 0
    
    return features

# 主特征提取函数
def extract_all_features(df, t0_idx):
    """提取所有时序特征"""
    features = {}
    
    # 基础特征
    if t0_idx < len(df):
        current = df.iloc[t0_idx]
        features.update({
            't0_close': current['close'],
            't0_volume': current['volume'] if 'volume' in current else 0,
            't0_rsi': current.get('rsi6', current.get('rsi14', 0)),
            't0_macd': current.get('macd', 0),
        })
    
    # 方案1: 区间极值与落差
    features.update(extract_delta_range_features(df, t0_idx, window=15))
    
    # 方案2: 持续状态与计数
    features.update(extract_duration_counting_features(df, t0_idx, window=15))
    
    # 方案3: 黄金坑特征
    features.update(extract_golden_pit_features(df, t0_idx))
    
    return features

# 测试函数
def test_feature_extraction():
    """测试特征提取功能"""
    # 创建测试数据（包含实际数据所需的所有列）
    dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
    df = pd.DataFrame({
        'open': 100 + np.random.randn(100).cumsum() * 1,
        'high': 102 + np.random.randn(100).cumsum() * 1.5,
        'low': 98 + np.random.randn(100).cumsum() * 1,
        'close': 100 + np.random.randn(100).cumsum() * 2,
        'volume': np.random.randint(100000, 1000000, 100),
        'rsi': 30 + np.random.rand(100) * 40,
        'macd': np.random.randn(100) * 2,
        'dif': np.random.randn(100) * 2,
        'dea': np.random.randn(100) * 2,
        'ma5': 100 + np.random.randn(100).cumsum() * 1.8,
        'ma10': 100 + np.random.randn(100).cumsum() * 1.6,
        'ma20': 100 + np.random.randn(100).cumsum() * 1.5,
        'ma30': 100 + np.random.randn(100).cumsum() * 1.5,
        'ma60': 100 + np.random.randn(100).cumsum() * 1.2,
        'ma240': 100 + np.random.randn(100).cumsum() * 0.8,
    }, index=dates)
    
    # 测试T0=50的特征提取
    t0_idx = 50
    features = extract_all_features(df, t0_idx)
    
    print("=== 特征提取测试 ===")
    print(f"T0索引: {t0_idx}")
    print(f"提取特征数: {len(features)}")
    print(f"特征示例: {list(features.keys())[:10]}")
    
    return features

if __name__ == "__main__":
    features = test_feature_extraction()
    print("特征提取测试完成")