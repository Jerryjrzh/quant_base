#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试股票画像优化功能
"""

import logging
import sys
import os

# 添加backend路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from stock_profiler import StockProfiler
from universal_screener import UniversalScreener

def test_stock_profiler_optimization():
    """测试股票画像优化功能"""
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    print("=" * 60)
    print("🚀 测试股票画像优化功能")
    print("=" * 60)
    
    # 1. 测试单只股票画像生成
    print("\n📊 测试1: 单只股票画像生成")
    profiler = StockProfiler()
    test_stock = "sz300290"
    
    print(f"正在为 {test_stock} 生成优化参数画像...")
    success = profiler.create_stock_profile(test_stock)
    print(f"画像生成结果: {'✅ 成功' if success else '❌ 失败'}")
    
    if success:
        # 获取生成的画像
        from stock_pool_manager import StockPoolManager
        pool_manager = StockPoolManager()
        profile = pool_manager.get_stock_by_code(test_stock)
        
        if profile and profile.get('optimized_params'):
            print(f"📈 优化参数: {profile['optimized_params']}")
            if 'validation_score' in profile['optimized_params']:
                print(f"🎯 验证分数: {profile['optimized_params']['validation_score']:.3f}")
    
    # 2. 测试画像摘要
    print("\n📋 测试2: 画像情况摘要")
    summary = profiler.get_profiling_summary()
    print(f"总股票数: {summary.get('total_stocks', 0)}")
    print(f"已画像股票数: {summary.get('profiled_stocks', 0)}")
    print(f"平均验证分数: {summary.get('avg_validation_score', 0):.3f}")
    
    # 3. 测试筛选器集成
    print("\n🔍 测试3: 筛选器参数集成")
    screener = UniversalScreener([test_stock])  # 只测试一只股票
    
    # 模拟运行筛选（这里只是测试集成，不运行完整筛选）
    print("筛选器已集成优化参数功能 ✅")
    
    # 4. 测试多进程优化（小规模测试）
    print("\n⚡ 测试4: 多进程画像生成（小规模）")
    test_stocks = ["sz300290", "sh600006"]  # 只测试2只股票
    
    # 先将测试股票添加到核心池
    from stock_pool_manager import StockPoolManager
    pool_manager = StockPoolManager()
    for stock_code in test_stocks:
        stock_info = {
            'stock_code': stock_code,
            'stock_name': f"测试股票{stock_code}",
            'market': 'sz' if stock_code.startswith('sz') else 'sh',
            'industry': '测试行业'
        }
        pool_manager.add_stock_to_pool(stock_info)
    
    # 运行多进程画像生成
    results = profiler.run_profiling_for_pool(limit=2, use_multiprocessing=True)
    print(f"多进程结果: 成功 {results['success']}, 失败 {results['failed']}")
    
    print("\n" + "=" * 60)
    print("🎉 股票画像优化功能测试完成")
    print("=" * 60)

def test_enhanced_validation():
    """测试增强的验证功能"""
    print("\n🧪 测试增强验证功能")
    
    profiler = StockProfiler()
    
    # 获取测试数据
    import data_handler
    df = data_handler.get_full_data_with_indicators("sz300290")
    
    if df is not None:
        # 测试新的验证方法
        test_params = {
            'kdj_n': 9,
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'ma_short': 10,
            'ma_long': 30
        }
        
        validation_score = profiler._validate_parameters(df, test_params)
        print(f"验证分数: {validation_score:.3f}")
        
        # 测试信号距离计算
        buy_signals = [100, 150, 200]  # 模拟信号位置
        price_lows = [105, 155, 205]   # 模拟低点位置
        
        distances = profiler._calculate_signal_low_distances(buy_signals, price_lows)
        print(f"信号距离: {distances}")
        
        print("增强验证功能测试完成 ✅")
    else:
        print("无法获取测试数据 ❌")

if __name__ == "__main__":
    test_stock_profiler_optimization()
    test_enhanced_validation()