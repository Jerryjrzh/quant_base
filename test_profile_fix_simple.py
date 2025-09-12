#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试画像保存修复
"""

import sys
import os
sys.path.append('backend')

from stock_profiler import StockProfiler
from stock_pool_manager import StockPoolManager
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_profile_fix():
    """测试画像保存修复"""
    print("=" * 60)
    print("测试画像保存修复")
    print("=" * 60)
    
    # 创建实例
    profiler = StockProfiler()
    pool_manager = StockPoolManager()
    
    # 测试一个不在观察池中的股票
    test_stock = "sz000001"  # 平安银行
    
    print(f"1. 检查股票 {test_stock} 是否在观察池中...")
    stock_info = pool_manager.get_stock_by_code(test_stock)
    if stock_info:
        print(f"   股票已存在于观察池中")
    else:
        print(f"   股票不在观察池中，将测试自动添加功能")
    
    print(f"2. 为股票 {test_stock} 生成画像...")
    success = profiler.create_stock_profile(test_stock)
    
    if success:
        print(f"   ✅ 画像生成成功")
        
        # 验证是否保存成功
        print(f"3. 验证画像是否保存成功...")
        stock_info = pool_manager.get_stock_by_code(test_stock)
        if stock_info and stock_info.get('optimized_params'):
            print(f"   ✅ 画像保存成功")
            print(f"   参数: {stock_info['optimized_params']}")
        else:
            print(f"   ❌ 画像保存失败")
    else:
        print(f"   ❌ 画像生成失败")
    
    print("=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    test_profile_fix()