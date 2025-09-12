#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端Step0调整演示脚本

演示新增的功能：
1. 数据库扩展
2. 数据丰富器
3. 个股画像生成器
4. 历史回测验证
"""

import os
import sys
import logging
from datetime import datetime, timedelta

# 添加backend路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.stock_pool_manager import StockPoolManager
from backend.data_enricher import DataEnricher
from backend.stock_profiler import StockProfiler
from backend.universal_screener import UniversalScreener


def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('demo_backend_step0.log', 'w', 'utf-8'),
            logging.StreamHandler()
        ]
    )


def demo_database_extension():
    """演示数据库扩展功能"""
    print("\n" + "="*60)
    print("1. 演示数据库扩展功能")
    print("="*60)
    
    # 创建管理器（会自动创建扩展后的数据库结构）
    manager = StockPoolManager("demo_stock_pool.db")
    
    # 添加测试股票
    test_stocks = [
        {
            'stock_code': 'sz300290',
            'stock_name': '荣科科技',
            'score': 0.75,
            'params': {'kdj_n': 9, 'rsi_period': 14},
            'risk_level': 'MEDIUM'
        },
        {
            'stock_code': 'sh600036',
            'stock_name': '招商银行',
            'score': 0.82,
            'params': {'kdj_n': 12, 'rsi_period': 16},
            'risk_level': 'LOW'
        }
    ]
    
    for stock in test_stocks:
        success = manager.add_stock_to_pool(stock)
        print(f"添加股票 {stock['stock_code']}: {'成功' if success else '失败'}")
    
    # 获取观察池统计
    stats = manager.get_pool_statistics()
    print(f"观察池统计: {stats}")


def demo_data_enricher():
    """演示数据丰富器功能"""
    print("\n" + "="*60)
    print("2. 演示数据丰富器功能")
    print("="*60)
    
    # 创建数据丰富器
    enricher = DataEnricher("demo_stock_pool.db")
    
    # 为单只股票丰富数据
    test_stock = "sz300290"
    print(f"为 {test_stock} 丰富数据...")
    success = enricher.enrich_single_stock(test_stock)
    print(f"丰富结果: {'成功' if success else '失败'}")
    
    # 获取丰富情况摘要
    summary = enricher.get_enrichment_summary()
    print(f"数据丰富摘要: {summary}")


def demo_stock_profiler():
    """演示个股画像生成器功能"""
    print("\n" + "="*60)
    print("3. 演示个股画像生成器功能")
    print("="*60)
    
    # 创建画像生成器
    profiler = StockProfiler("demo_stock_pool.db")
    
    # 为单只股票生成画像
    test_stock = "sz300290"
    print(f"为 {test_stock} 生成参数画像...")
    success = profiler.create_stock_profile(test_stock, method='differential_evolution')
    print(f"画像生成结果: {'成功' if success else '失败'}")
    
    # 获取画像情况摘要
    summary = profiler.get_profiling_summary()
    print(f"参数画像摘要: {summary}")


def demo_historical_backtest():
    """演示历史回测验证功能"""
    print("\n" + "="*60)
    print("4. 演示历史回测验证功能")
    print("="*60)
    
    # 创建筛选器
    screener = UniversalScreener()
    
    # 设置历史日期（30天前）
    historical_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    print(f"使用历史日期进行筛选: {historical_date}")
    
    # 运行历史筛选（限制策略以加快演示）
    try:
        results = screener.run_screening(
            selected_strategies=['abyss_strategy'],  # 只使用一个策略演示
            scan_date_str=historical_date
        )
        
        print(f"历史筛选发现 {len(results)} 个信号")
        
        # 显示前几个结果的验证信息
        for i, result in enumerate(results[:3], 1):
            print(f"\n信号 {i}: {result.stock_code}")
            print(f"  策略: {result.strategy_name}")
            print(f"  信号类型: {result.signal_type}")
            print(f"  当时价格: {result.current_price:.2f}")
            
            if hasattr(result.signal_details, 'get'):
                validation_success = result.signal_details.get('validation_success', 'N/A')
                max_profit = result.signal_details.get('validation_max_profit', 'N/A')
                final_return = result.signal_details.get('validation_final_return', 'N/A')
                
                print(f"  验证成功: {validation_success}")
                print(f"  最大收益: {max_profit}")
                print(f"  最终收益: {final_return}")
        
    except Exception as e:
        print(f"历史回测演示失败: {e}")
        print("这可能是因为缺少必要的数据文件或策略配置")


def demo_integrated_workflow():
    """演示完整的集成工作流"""
    print("\n" + "="*60)
    print("5. 演示完整集成工作流")
    print("="*60)
    
    try:
        # 1. 数据库管理
        manager = StockPoolManager("demo_stock_pool.db")
        
        # 2. 数据丰富
        enricher = DataEnricher("demo_stock_pool.db")
        print("运行数据丰富流程...")
        enrich_results = enricher.run_enrichment_for_pool(limit=5)  # 限制5只股票演示
        print(f"数据丰富结果: {enrich_results}")
        
        # 3. 参数画像生成
        profiler = StockProfiler("demo_stock_pool.db")
        print("运行参数画像生成流程...")
        profile_results = profiler.run_profiling_for_pool(limit=3)  # 限制3只股票演示
        print(f"参数画像结果: {profile_results}")
        
        # 4. 获取最终统计
        final_stats = manager.get_pool_statistics()
        enrichment_summary = enricher.get_enrichment_summary()
        profiling_summary = profiler.get_profiling_summary()
        
        print(f"\n最终统计:")
        print(f"  观察池: {final_stats}")
        print(f"  数据丰富: {enrichment_summary}")
        print(f"  参数画像: {profiling_summary}")
        
    except Exception as e:
        print(f"集成工作流演示失败: {e}")
        print("这可能是因为缺少必要的依赖或数据文件")


def cleanup():
    """清理演示文件"""
    demo_files = [
        "demo_stock_pool.db",
        "demo_backend_step0.log"
    ]
    
    print(f"\n清理演示文件...")
    for file in demo_files:
        if os.path.exists(file):
            os.remove(file)
            print(f"已删除: {file}")


def main():
    """主函数"""
    print("🚀 后端Step0调整功能演示")
    print("本演示将展示新增的数据库扩展、数据丰富器、参数画像生成器和历史回测功能")
    
    # 设置日志
    setup_logging()
    
    try:
        # 演示各个功能模块
        demo_database_extension()
        demo_data_enricher()
        demo_stock_profiler()
        demo_historical_backtest()
        demo_integrated_workflow()
        
        print("\n" + "="*60)
        print("✅ 所有演示完成！")
        print("="*60)
        print("\n主要新增功能:")
        print("1. ✅ 数据库结构扩展 - 支持健康分、龙虎榜、财务数据等字段")
        print("2. ✅ 数据丰富器 - 自动获取和整合多源数据")
        print("3. ✅ 个股画像生成器 - 为每只股票优化技术指标参数")
        print("4. ✅ 历史回测验证 - 支持历史日期筛选和结果验证")
        print("5. ✅ 集成工作流 - 各模块协同工作")
        
        print(f"\n📊 演示数据已保存到 demo_stock_pool.db")
        print(f"📝 详细日志已保存到 demo_backend_step0.log")
        
    except KeyboardInterrupt:
        print("\n用户中断演示")
    except Exception as e:
        print(f"\n演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    
    # 询问是否清理文件
    try:
        response = input("\n是否清理演示文件? (y/N): ").strip().lower()
        if response == 'y':
            cleanup()
        else:
            print("演示文件已保留，您可以手动检查数据库内容")
    except:
        print("保留演示文件")


if __name__ == "__main__":
    main()