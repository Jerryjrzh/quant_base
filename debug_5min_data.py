#!/usr/bin/env python3
"""
调试5分钟数据结构
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.data_loader import get_multi_timeframe_data

def debug_5min_data():
    stock_code = 'sz002021'
    
    print(f"调试股票: {stock_code}")
    
    multi_data = get_multi_timeframe_data(stock_code)
    
    if multi_data['data_status']['min5_available']:
        df_5min = multi_data['min5_data']
        print(f"5分钟数据形状: {df_5min.shape}")
        print(f"5分钟数据列名: {df_5min.columns.tolist()}")
        print(f"5分钟数据索引: {df_5min.index.name}")
        print(f"5分钟数据前5行:")
        print(df_5min.head())
        print(f"5分钟数据索引类型: {type(df_5min.index)}")
        
        # 检查是否有datetime列
        if 'datetime' in df_5min.columns:
            print("✓ 有datetime列")
        elif df_5min.index.name == 'datetime':
            print("✓ datetime是索引")
        else:
            print("✗ 没有找到datetime")
            
    else:
        print("无5分钟数据")

if __name__ == "__main__":
    debug_5min_data()