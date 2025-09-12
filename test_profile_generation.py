#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试股票画像生成功能

这个脚本用于测试和验证股票画像生成功能，包括：
1. 测试单只股票画像生成
2. 测试小批量股票画像生成
3. 验证画像数据的正确性
"""

import os
import sys
import json
import logging
from datetime import datetime

# 添加backend目录到路径
sys.path.append('backend')

from stock_profiler import StockProfiler
from stock_pool_manager import StockPoolManager


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def test_single_stock_profile(stock_code: str = "sz300290"):
    """测试单只股票画像生成"""
    print(f"🧪 测试单只股票画像生成: {stock_code}")
    print("-" * 50)
    
    profiler = StockProfiler()
    
    # 生成画像
    success = profiler.create_stock_profile(stock_code)
    print(f"画像生成结果: {'✅ 成功' if success else '❌ 失败'}")
    
    if success:
        # 验证画像数据
        pool_manager = StockPoolManager()
        stock_data = pool_manager.get_stock_by_code(stock_code)
        
        if stock_data and stock_data.get('optimized_params'):
            try:
                if isinstance(stock_data['optimized_params'], str):
                    params = json.loads(stock_data['optimized_params'])
                else:
                    params = stock_data['optimized_params']
                
                print(f"优化参数: {params}")
                print(f"验证分数: {params.get('validation_score', 'N/A')}")
                print(f"优化成功: {params.get('optimization_success', 'N/A')}")
                print(f"优化误差: {params.get('optimization_error', 'N/A')}")
                
            except Exception as e:
                print(f"解析画像数据失败: {e}")
        else:
            print("未找到画像数据")
    
    print()


def test_batch_profile_generation(limit: int = 5):
    """测试批量画像生成"""
    print(f"🧪 测试批量画像生成 (限制{limit}只股票)")
    print("-" * 50)
    
    profiler = StockProfiler()
    
    # 单进程测试
    print("单进程模式:")
    results_single = profiler.run_profiling_for_pool(limit=limit, use_multiprocessing=False)
    print(f"单进程结果: {results_single}")
    
    print()
    
    # 多进程测试
    print("多进程模式:")
    results_multi = profiler.run_profiling_for_pool(limit=limit, use_multiprocessing=True)
    print(f"多进程结果: {results_multi}")
    
    print()


def validate_profile_data():
    """验证画像数据的完整性"""
    print("🧪 验证画像数据完整性")
    print("-" * 50)
    
    pool_manager = StockPoolManager()
    profiler = StockProfiler()
    
    # 获取画像摘要
    summary = profiler.get_profiling_summary()
    print(f"画像摘要: {summary}")
    
    # 检查核心池画像覆盖率
    core_pool = pool_manager.get_core_pool()
    profiled_count = 0
    validation_scores = []
    
    print(f"\n核心池股票画像检查:")
    for stock in core_pool[:10]:  # 只检查前10只
        stock_code = stock['stock_code']
        if stock.get('optimized_params'):
            profiled_count += 1
            try:
                if isinstance(stock['optimized_params'], str):
                    params = json.loads(stock['optimized_params'])
                else:
                    params = stock['optimized_params']
                
                validation_score = params.get('validation_score', 0)
                validation_scores.append(validation_score)
                
                print(f"  ✅ {stock_code}: 验证分数 {validation_score:.3f}")
            except Exception as e:
                print(f"  ❌ {stock_code}: 数据解析失败 - {e}")
        else:
            print(f"  ⚪ {stock_code}: 无画像数据")
    
    if validation_scores:
        avg_score = sum(validation_scores) / len(validation_scores)
        print(f"\n平均验证分数: {avg_score:.3f}")
        print(f"最高验证分数: {max(validation_scores):.3f}")
        print(f"最低验证分数: {min(validation_scores):.3f}")
    
    print()


def test_parameter_optimization():
    """测试参数优化算法"""
    print("🧪 测试参数优化算法")
    print("-" * 50)
    
    import data_handler
    
    # 测试股票
    test_stock = "sz300290"
    
    print(f"获取 {test_stock} 数据...")
    df = data_handler.get_full_data_with_indicators(test_stock)
    
    if df is None or len(df) < 250:
        print(f"❌ {test_stock} 数据不足")
        return
    
    print(f"数据长度: {len(df)} 天")
    
    profiler = StockProfiler()
    recent_df = df.tail(250)
    
    print("运行差分进化优化...")
    start_time = datetime.now()
    
    optimal_params = profiler._optimize_with_differential_evolution(recent_df)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"优化耗时: {duration:.2f} 秒")
    
    if optimal_params:
        print(f"优化结果: {optimal_params}")
        
        # 验证参数
        validation_score = profiler._validate_parameters(df, optimal_params)
        print(f"验证分数: {validation_score:.3f}")
    else:
        print("❌ 优化失败")
    
    print()


def main():
    """主函数"""
    setup_logging()
    
    print("🚀 股票画像生成功能测试")
    print("=" * 60)
    
    try:
        # 1. 测试单只股票
        test_single_stock_profile()
        
        # 2. 测试批量生成
        test_batch_profile_generation(3)
        
        # 3. 验证数据完整性
        validate_profile_data()
        
        # 4. 测试优化算法
        test_parameter_optimization()
        
        print("✅ 所有测试完成")
        
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()