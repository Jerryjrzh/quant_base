#
# 文件: profile_cluster_analyzer.py
#
import pandas as pd
import json
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from stock_pool_manager import StockPoolManager

def analyze_and_cluster_profiles():
    # 1. 加载所有已分析的画像
    pool_manager = StockPoolManager()
    all_stocks = pool_manager.get_all_profiles() 
    
    profiled_stocks = []
    for stock in all_stocks:
        # --- 这是核心修改点 ---
        # get_all_profiles 已经将 optimized_params 解析为字典
        # 我们只需检查它是否存在并且是一个字典即可
        params = stock.get('optimized_params')
        
        if isinstance(params, dict) and params.get('optimization_success'):
            stock_info = {
                'stock_code': stock['stock_code'],
                'industry': stock.get('industry', 'Unknown'), 
                'volatility': stock.get('volatility', 0.0), # 假设未来会添加这个字段
                **params
            }
            profiled_stocks.append(stock_info)

    if not profiled_stocks:
        print("错误：没有找到任何成功生成的画像数据，无法进行聚类。")
        return

    df = pd.DataFrame(profiled_stocks)

    n_samples = len(df)
    desired_clusters = 8

    if n_samples < desired_clusters:
        print(f"警告：样本数量 ({n_samples}) 小于期望的聚类数量 ({desired_clusters})，将使用样本数量作为聚类数。")
        n_clusters = n_samples
    else:
        n_clusters = desired_clusters

    if n_clusters < 2:
        print("错误：样本数量不足以进行有效聚类，至少需要 2 个样本。")
        return
    # 2. 准备聚类用的特征
    param_cols = ['kdj_n', 'rsi_period', 'macd_fast', 'macd_slow', 'ma_short', 'ma_long']
    features = df[param_cols]
    
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)

    # 3. 运行K-Means聚类
    
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df['cluster_id'] = kmeans.fit_predict(features_scaled)

    # 4. 计算每个簇的“模板画像”
    template_profiles = df.groupby('cluster_id')[param_cols].mean().astype(int)
    
    # 5. 保存聚类结果和模板画像
    template_profiles.to_json("profile_templates.json", orient='index', indent=2)
    df[['stock_code', 'cluster_id']].to_csv("stock_clusters.csv", index=False)
    
    print("模板画像已生成：\n", template_profiles)

if __name__ == '__main__':
    analyze_and_cluster_profiles()
