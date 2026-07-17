#!/usr/bin/env python3
"""
分析 GBM 概率与交易收益的相关性
从 latest_walk_forward.csv 提取特征，用 GBM 打分，验证相关性
"""

import pandas as pd
import numpy as np
from gbm_scorer import GBMScorer
import re

# 加载回测数据
df = pd.read_csv('latest_walk_forward.csv')
print(f"总交易记录: {len(df)}")

# 从 morse_features 解析 bias_20 和 market_env
def parse_morse_features(row):
    """从 morse_features 列提取特征"""
    features_str = row['morse_features']
    if pd.isna(features_str):
        return pd.Series({'bias_20': 0, 'market_env': '未知'})

    # 解析 B20 (bias_20)
    bias_match = re.search(r'B20:([+-]?\d+\.?\d*)', features_str)
    bias_20 = float(bias_match.group(1)) if bias_match else 0

    # 解析 MKT (market_env)
    mkt_match = re.search(r'MKT:([^|]+)', features_str)
    market_env = mkt_match.group(1) if mkt_match else '未知'

    return pd.Series({'bias_20': bias_20, 'market_env': market_env})

# 提取特征
features_df = df.apply(parse_morse_features, axis=1)
df = pd.concat([df, features_df], axis=1)

# 准备 GBM 输入
df_gbm_input = df[['stock_code', 'ma_slope', 'bias_20', '评估分', 'market_env', 'v44_trend', 'v44_bias_tier', '收益率', 'MFE', '交易状态']].copy()
df_gbm_input.rename(columns={'评估分': 'score'}, inplace=True)

# 过滤有效交易
df_valid = df_gbm_input[df_gbm_input['交易状态'] != '挂单超时撤销'].copy()
print(f"有效交易记录: {len(df_valid)}")

# 加载 GBM 模型并打分
scorer = GBMScorer()
if not scorer.load('gbm_scorer_v1'):
    print("ERROR: GBM 模型加载失败")
    exit(1)

print(f"\n模型加载成功: {scorer.summary()}")

df_valid['gbm_proba'] = scorer.score(df_valid)

# 保存结果
df_valid.to_csv('gbm_correlation_analysis.csv', index=False)
print(f"\n结果已保存到 gbm_correlation_analysis.csv")

# 相关性分析
print("\n" + "="*60)
print("GBM 概率与收益的相关性分析")
print("="*60)

# 1. 基础统计
print(f"\n1. GBM 概率分布:")
print(f"   均值: {df_valid['gbm_proba'].mean():.3f}")
print(f"   中位: {df_valid['gbm_proba'].median():.3f}")
print(f"   标准差: {df_valid['gbm_proba'].std():.3f}")
print(f"   最小: {df_valid['gbm_proba'].min():.3f}")
print(f"   最大: {df_valid['gbm_proba'].max():.3f}")

# 2. 皮尔逊相关系数
corr_return = df_valid['gbm_proba'].corr(df_valid['收益率'])
corr_mfe = df_valid['gbm_proba'].corr(df_valid['MFE'])

print(f"\n2. 皮尔逊相关系数:")
print(f"   GBM proba vs 收益率: {corr_return:.4f}")
print(f"   GBM proba vs MFE: {corr_mfe:.4f}")

# 3. 分位数分析
print(f"\n3. GBM 概率分位数分析:")
df_valid['gbm_decile'] = pd.qcut(df_valid['gbm_proba'], q=5, labels=['Q1(最低)', 'Q2', 'Q3', 'Q4', 'Q5(最高)'])

decile_stats = df_valid.groupby('gbm_decile').agg({
    '收益率': ['count', 'mean', 'median'],
    'MFE': ['mean', 'median'],
    '交易状态': lambda x: (x == '止盈成功').sum() / len(x)
}).round(4)

print(decile_stats)

# 4. 按阈值过滤的效果
print(f"\n4. 按 GBM 阈值过滤的效果:")
for threshold in [0.4, 0.5, 0.6, 0.62, 0.7]:
    df_filtered = df_valid[df_valid['gbm_proba'] >= threshold]
    if len(df_filtered) > 0:
        win_rate = (df_filtered['交易状态'] == '止盈成功').sum() / len(df_filtered)
        avg_return = df_filtered['收益率'].mean()
        avg_mfe = df_filtered['MFE'].mean()
        print(f"   阈值≥{threshold:.2f}: {len(df_filtered):3d}笔 | 胜率{win_rate:.1%} | 均收益{avg_return:+.2%} | MFE{avg_mfe:.2%}")

# 5. 交易成功 vs 失败的 GBM 概率对比
print(f"\n5. 交易结果与 GBM 概率:")
for status in ['止盈成功', '止损出局', '时间衰减平仓']:
    subset = df_valid[df_valid['交易状态'] == status]
    if len(subset) > 0:
        print(f"   {status:12s}: {len(subset):3d}笔 | GBM均值{subset['gbm_proba'].mean():.3f} | GBM中位{subset['gbm_proba'].median():.3f}")

print("\n" + "="*60)
