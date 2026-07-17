"""
Super Trend策略：简化版历史数据扫描脚本
用于快速验证数据加载和T0定位逻辑
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 临时简化数据加载
def load_test_data():
    """生成测试数据用于验证逻辑"""
    dates = pd.date_range(start='2023-01-01', end='2025-01-01', freq='D')
    n_days = len(dates)
    
    # 模拟价格数据
    np.random.seed(42)
    base_price = 100
    daily_returns = np.random.normal(0.0005, 0.02, n_days)
    prices = base_price * np.exp(np.cumsum(daily_returns))
    
    # 创建一个主升浪段 (模拟)
    burst_start = 200  # 第200天开始
    burst_length = 60  # 持续60天
    burst_multiplier = 2.5  # 涨幅2.5倍
    
    for i in range(burst_length):
        idx = burst_start + i
        if idx < n_days:
            # 主升浪期间每天涨2%
            daily_returns[idx] = 0.02
    
    # 重新计算价格
    prices = base_price * np.exp(np.cumsum(daily_returns))
    
    # 创建DataFrame
    df = pd.DataFrame({
        'date': dates,
        'open': prices * (1 - np.random.uniform(0, 0.01, n_days)),
        'high': prices * (1 + np.random.uniform(0, 0.02, n_days)),
        'low': prices * (1 - np.random.uniform(0, 0.02, n_days)),
        'close': prices,
        'volume': np.random.randint(100000, 1000000, n_days)
    })
    
    return df

def find_super_trend_candidates(df):
    """查找主升浪候选点"""
    min_lookback = 60
    future_days = 30
    min_gain = 0.50  # 50%
    max_drawdown = -0.15  # -15%
    
    candidates = []
    
    for i in range(min_lookback, len(df) - future_days):
        t0_date = df.iloc[i]['date']
        t0_price = df.iloc[i]['close']
        
        # 未来30天窗口
        future_window = df.iloc[i+1:i+future_days+1]
        if len(future_window) < future_days:
            continue
        
        future_high = future_window['high'].max()
        future_low = future_window['low'].min()
        
        mfe = (future_high / t0_price) - 1.0
        mae = (future_low / t0_price) - 1.0
        
        # 判断是否为主升浪
        if mfe >= min_gain and mae >= max_drawdown:
            # 向前查找起爆点
            t0_index = i
            for lookback in range(1, min(5, i) + 1):
                idx = i - lookback
                current = df.iloc[idx]
                prev = df.iloc[idx-1] if idx > 0 else current
                
                price_change = (current['close'] / prev['close']) - 1.0
                
                if price_change > 0.03:  # 3%以上大阳线
                    t0_index = idx
                    break
            
            candidates.append({
                't0_date': df.iloc[t0_index]['date'],
                't0_price': df.iloc[t0_index]['close'],
                'future_mfe': mfe,
                'future_mae': mae,
                'mfe_pct': mfe * 100,
                'mae_pct': mae * 100
            })
    
    return candidates

def main():
    print("Super Trend简化扫描器启动...")
    
    # 加载测试数据
    print("生成测试数据...")
    df = load_test_data()
    print(f"数据长度: {len(df)} 天")
    
    # 查找候选点
    print("扫描主升浪候选点...")
    candidates = find_super_trend_candidates(df)
    
    if candidates:
        print(f"\n发现 {len(candidates)} 个候选点:")
        for i, cand in enumerate(candidates[:5]):  # 只显示前5个
            print(f"{i+1}. T0日期: {cand['t0_date'].date()}, "
                  f"价格: {cand['t0_price']:.2f}, "
                  f"未来涨幅: {cand['mfe_pct']:.1f}%, "
                  f"最大回撤: {cand['mae_pct']:.1f}%")
        
        # 保存结果
        df_results = pd.DataFrame(candidates)
        df_results.to_csv('super_trend_test_candidates.csv', index=False)
        print(f"\n结果已保存至: super_trend_test_candidates.csv")
    else:
        print("未发现主升浪候选点")
    
    return candidates

if __name__ == "__main__":
    main()