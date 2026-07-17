"""
Super Trend 特征分布诊断脚本
用于分析正样本 vs 负样本在各个特征上的区分度
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats
import os
from datetime import datetime

# 配置
DATA_PATH = os.path.join("data", "result", "super_trend", "super_trend_training_data.csv")
OUTPUT_DIR = os.path.join("data", "result", "super_trend", "diagnosis")
os.makedirs(OUTPUT_DIR, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'Noto Sans CJK SC']
plt.rcParams['axes.unicode_minus'] = False

def load_data():
    """加载训练数据"""
    if not os.path.exists(DATA_PATH):
        raise FileNotFoundError(f"训练数据不存在: {DATA_PATH}")
    
    df = pd.read_csv(DATA_PATH)
    print(f"加载数据: {df.shape}")
    
    # 确保 target 列存在
    if 'target' not in df.columns and 'is_positive' in df.columns:
        df['target'] = df['is_positive']
    
    pos = df[df['target'] == 1]
    neg = df[df['target'] == 0]
    
    print(f"正样本: {len(pos)} ({len(pos)/len(df):.2%})")
    print(f"负样本: {len(neg)}")
    
    return df, pos, neg

def calculate_separation(pos, neg, feature):
    """计算特征分离度"""
    if feature not in pos.columns:
        return 0.0
    
    pos_mean = pos[feature].mean()
    neg_mean = neg[feature].mean()
    pos_std = pos[feature].std()
    neg_std = neg[feature].std()
    
    # 标准化均值差
    pooled_std = np.sqrt((pos_std**2 + neg_std**2) / 2)
    separation = abs(pos_mean - neg_mean) / pooled_std if pooled_std > 0 else 0
    
    # KS检验
    ks_stat, p_value = stats.ks_2samp(pos[feature].dropna(), neg[feature].dropna())
    
    return {
        'feature': feature,
        'pos_mean': pos_mean,
        'neg_mean': neg_mean,
        'mean_diff': abs(pos_mean - neg_mean),
        'separation_sigma': separation,
        'ks_stat': ks_stat,
        'p_value': p_value
    }

def plot_feature_dist(pos, neg, feature, ax=None):
    """绘制单个特征分布"""
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, 6))
    
    sns.kdeplot(data=pos[feature].dropna(), label='正样本 (主升浪)', fill=True, alpha=0.6, ax=ax)
    sns.kdeplot(data=neg[feature].dropna(), label='负样本', fill=True, alpha=0.4, ax=ax)
    
    ax.set_title(f'{feature} 分布对比')
    ax.set_xlabel(feature)
    ax.legend()
    return ax

def main():
    print("=== Super Trend 特征分布诊断 ===")
    df, pos, neg = load_data()
    
    # 特征列（排除元数据）
    meta_cols = ['target', 'stock_code', 't0_date', 'is_positive', 'future_mfe']
    feature_cols = [col for col in df.columns if col not in meta_cols]
    
    # 统计分析
    results = []
    for feat in feature_cols:
        stat = calculate_separation(pos, neg, feat)
        results.append(stat)
    
    report_df = pd.DataFrame(results)
    report_df = report_df.sort_values('separation_sigma', ascending=False)
    
    # 保存报告
    report_path = os.path.join(OUTPUT_DIR, f'feature_diagnosis_{datetime.now().strftime("%Y%m%d_%H%M")}.csv')
    report_df.to_csv(report_path, index=False)
    
    print(f"\n=== Top 15 最具区分度特征 ===")
    print(report_df.head(15)[['feature', 'separation_sigma', 'mean_diff', 'ks_stat']])
    
    # 可视化 Top 10
    top_features = report_df.head(10)['feature'].tolist()
    fig, axes = plt.subplots(5, 2, figsize=(16, 20))
    axes = axes.flatten()
    
    for i, feat in enumerate(top_features):
        plot_feature_dist(pos, neg, feat, ax=axes[i])
    
    plt.tight_layout()
    plot_path = os.path.join(OUTPUT_DIR, 'top_features_distribution.png')
    plt.savefig(plot_path, dpi=300, bbox_inches='tight')
    print(f"\n分布图已保存: {plot_path}")
    
    # 生成 Markdown 摘要
    md_path = os.path.join(OUTPUT_DIR, 'feature_diagnosis_summary.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write("# Super Trend 特征分布诊断报告\n\n")
        f.write(f"生成时间: {datetime.now()}\n\n")
        f.write(f"正样本数量: {len(pos)} ({len(pos)/len(df):.2%})\n\n")
        f.write("## Top 10 区分度特征\n\n")
        f.write(report_df.head(10)[['feature', 'separation_sigma', 'pos_mean', 'neg_mean', 'mean_diff']].to_markdown())
        f.write("\n\n**分离度 (σ) 越高，特征区分能力越强**\n")
    
    print(f"诊断报告已生成: {md_path}")
    print("\n✅ 诊断完成！请查看 diagnosis 目录下的报告和图表。")

if __name__ == "__main__":
    main()
