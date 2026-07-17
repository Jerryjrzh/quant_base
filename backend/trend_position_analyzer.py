import os
import glob
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
import data_loader

def analyze_stock_trend(file_path):
    stock_code = os.path.basename(file_path).split('.')[0]
    
    # =======================================================
    # 🚨 核心过滤：剔除 sh880 等板块指数，只保留纯正 A 股个股
    # =======================================================
    stock_num = stock_code.replace('sh', '').replace('sz', '').replace('bj', '')
    if not (stock_num.startswith(('60', '688', '00', '300', '92')) and len(stock_num) == 6):
        return None
        
    try:
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 100: return None
        
        # 只取最近 2 年的数据进行统计，保持时效性
        df = df.iloc[-500:].copy()
        
        # 计算未来3天最高反弹
        df['future_3d_high'] = df['high'].shift(-3).rolling(3, min_periods=1).max()
        df['future_rebound'] = (df['future_3d_high'] - df['close']) / df['close']
        
        # 提取起爆样本 (未来3天能打出 15% 以上空间的票)
        explosion_indices = np.where(df['future_rebound'] >= 0.28)[0]
        
        records = []
        for idx in explosion_indices:
            if idx < 60 or idx >= len(df) - 3: continue
            
            # T-1 日 (起爆前夜)
            t1_idx = idx
            row = df.iloc[t1_idx]
            close = row['close']
            
            # 使用 MA13 (游资/短期趋势核心线)
            ma13 = df['close'].iloc[t1_idx-12:t1_idx+1].mean()
            ma60 = df['close'].iloc[t1_idx-59:t1_idx+1].mean()
            ma13_prev5 = df['close'].iloc[t1_idx-17:t1_idx-4].mean()
            high_13d = df['high'].iloc[t1_idx-12:t1_idx+1].max()
            
            # 1. 计算乖离率
            bias_13 = (close - ma13) / ma13
            # 2. 计算 13日线斜率 (5天内的涨跌幅)
            slope_13 = (ma13 - ma13_prev5) / ma13_prev5
            # 3. 计算距离前高回撤
            drawdown_13d = (close - high_13d) / high_13d
            # 4. 是否符合传统的 "多头排列"
            is_naive_bull = int(close > ma13 and ma13 > ma60)
            
            records.append({
                'bias_13': bias_13,
                'slope_13': slope_13,
                'drawdown_13d': drawdown_13d,
                'is_naive_bull': is_naive_bull
            })
        return records
    except Exception:
        return None

def main():
    print("🚀 启动 [真·起爆位 (纯净版)] 逆向工程透视仪...")
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day"))
    
    with Pool(processes=max(1, cpu_count()-1)) as pool:
        raw_results = pool.map(analyze_stock_trend, files)
        
    flat_records = [item for sublist in raw_results if sublist for item in sublist]
    df_res = pd.DataFrame(flat_records)
    
    print("\n" + "="*60)
    print(" 📊 纯正大牛股起爆前夜 (T-1) 真实位置画像 (过滤后有效样本数: {})".format(len(df_res)))
    print("="*60)
    
    print("\n1. 传统的 'close > ma13 > ma60' 占比是多少？")
    naive_pct = df_res['is_naive_bull'].mean() * 100
    print(f"   只有 {naive_pct:.1f}% 的牛股在起爆前夜完全符合传统多头排列！")

    print("\n2. MA13 乖离率 (Bias) 真实分布 (核心防追高标尺)：")
    bias_desc = df_res['bias_13'].describe(percentiles=[0.1, 0.25, 0.5, 0.75, 0.9])
    print(f"   - 10% 的牛股起爆前贴地飞行 (乖离率 < {bias_desc['10%']*100:.1f}%)")
    print(f"   - 50% 的牛股起爆前乖离率在中位数附近 (约 {bias_desc['50%']*100:.1f}%)")
    print(f"   - 只有 10% 的疯牛是在极高位置继续接力 (乖离率 > {bias_desc['90%']*100:.1f}%)")
    print(f"   💡 实战建议：乖离率应限制在 [{bias_desc['10%']:.3f}, {bias_desc['90%']:.3f}] 之间。")

    print("\n3. MA13 动能斜率真实分布 (核心防死鱼标尺)：")
    slope_desc = df_res['slope_13'].describe(percentiles=[0.1, 0.5, 0.9])
    print(f"   - 绝大多数牛股的 13 日线斜率中位数是 {slope_desc['50%']*100:.1f}% / 5天")
    print(f"   💡 实战建议：如果斜率 < {slope_desc['10%']:.3f}，说明处于下降通道，一票否决！")

if __name__ == "__main__":
    main()