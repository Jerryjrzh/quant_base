import pandas as pd
import json
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from stock_pool_manager import StockPoolManager

def analyze_and_cluster_profiles():
    # 1. 加载所有已分析的画像
    pool_manager = StockPoolManager()
    all_stocks = pool_manager.get_all_profiles() # 假设有这个方法
    
    profiled_stocks = []
    for stock in all_stocks:
        params = stock.get('optimized_params')
        if isinstance(params, dict) and params.get('optimization_success'):
            # 假设能获取到行业和波动率
            stock_info = {
                'stock_code': stock['stock_code'],
                'industry': stock.get('industry', 'Unknown'), 
                'volatility': stock.get('volatility', 0.0),
                **params
            }
            profiled_stocks.append(stock_info)
    if not profiled_stocks:
        print("错误：没有找到任何成功生成的画像数据，无法进行聚类。")
        return

    df = pd.DataFrame(profiled_stocks)

    # 2. 准备聚类用的特征
    # 选择用于聚类的参数列
    param_cols = ['kdj_n', 'rsi_period', 'macd_fast', 'macd_slow', 'ma_short', 'ma_long']
    features = df[param_cols]
    
    # 标准化
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(features)

    # 3. 运行K-Means聚类
    n_clusters = 8 # 例如，分成8类
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    df['cluster_id'] = kmeans.fit_predict(features_scaled)

    # 4. 计算每个簇的“模板画像” (参数的均值或中位数)
    template_profiles = df.groupby('cluster_id')[param_cols].mean().astype(int)
    
    # 5. 保存聚类结果和模板画像
    # 例如，存成 JSON 文件
    template_profiles.to_json("profile_templates.json", orient='index', indent=2)
    df[['stock_code', 'cluster_id']].to_csv("stock_clusters.csv", index=False)
    
    print("模板画像已生成：\n", template_profiles)

if __name__ == '__main__':
    analyze_and_cluster_profiles()
