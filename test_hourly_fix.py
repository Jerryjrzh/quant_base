#!/usr/bin/env python3
"""
测试小时线数据修复
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.data_loader import fetch_hourly_kline

def test_hourly_fix():
    stock_code = 'sz002021'
    
    print(f"测试股票: {stock_code}")
    print("=" * 40)
    
    # 测试小时线数据生成
    hourly_df = fetch_hourly_kline(stock_code, '2025-09-01', '2025-09-17')
    
    if not hourly_df.empty:
        print(f"✓ 小时线数据生成成功")
        print(f"数据量: {len(hourly_df)} 条")
        print(f"列名: {hourly_df.columns.tolist()}")
        print(f"数据范围: {hourly_df['date'].iloc[0]} 到 {hourly_df['date'].iloc[-1]}")
        
        print("\n前5条数据:")
        print(hourly_df.head())
        
        print("\n最后5条数据:")
        print(hourly_df.tail())
        
        return True
    else:
        print("✗ 小时线数据生成失败")
        return False

if __name__ == "__main__":
    success = test_hourly_fix()
    if success:
        print("\n🎉 小时线数据修复成功！")
    else:
        print("\n❌ 小时线数据修复失败")