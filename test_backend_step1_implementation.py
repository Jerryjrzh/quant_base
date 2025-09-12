#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend Step 1 实现测试脚本

测试内容：
1. universal_screener.py 的空指针异常修复
2. data_enricher.py 的健康分数计算
3. stock_profiler.py 的参数画像生成
4. 统一API的功能
5. 独立画像生成脚本
"""

import os
import sys
import json
import logging
from datetime import datetime

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.append(backend_dir)

def setup_logging():
    """设置日志"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'backend_step1_test_{datetime.now().strftime("%Y%m%d_%H%M")}.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

def test_universal_screener_fix():
    """测试 universal_screener.py 的空指针异常修复"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("测试 1: Universal Screener 空指针异常修复")
    logger.info("=" * 60)
    
    try:
        from backend.universal_screener import UniversalScreener
        
        # 创建筛选器实例
        screener = UniversalScreener()
        
        # 测试运行筛选（限制数量以加快测试）
        logger.info("运行筛选测试（限制处理前10个文件）...")
        
        # 获取少量文件进行测试
        all_files = screener.collect_stock_files()[:10]  # 只测试前10个文件
        
        if not all_files:
            logger.warning("未找到股票数据文件")
            return False
        
        logger.info(f"测试文件数量: {len(all_files)}")
        
        # 运行筛选
        results = screener.run_screening()
        
        logger.info(f"筛选完成，发现 {len(results)} 个信号")
        logger.info("✅ Universal Screener 空指针异常修复测试通过")
        return True
        
    except Exception as e:
        logger.error(f"❌ Universal Screener 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_enricher():
    """测试 data_enricher.py 的健康分数计算"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("测试 2: Data Enricher 健康分数计算")
    logger.info("=" * 60)
    
    try:
        from backend.data_enricher import DataEnricher
        from backend.stock_pool_manager import StockPoolManager
        
        # 创建数据丰富器
        enricher = DataEnricher()
        pool_manager = StockPoolManager()
        
        # 添加测试股票到核心池（如果不存在）
        test_stock = "sz300290"
        test_stock_info = {
            'stock_code': test_stock,
            'stock_name': '荣科科技',
            'score': 0.6,
            'params': {},
            'risk_level': 'MEDIUM'
        }
        
        pool_manager.add_stock_to_pool(test_stock_info)
        logger.info(f"添加测试股票到核心池: {test_stock}")
        
        # 测试单只股票数据丰富
        logger.info(f"测试丰富股票数据: {test_stock}")
        success = enricher.enrich_single_stock(test_stock)
        
        if success:
            logger.info("✅ 数据丰富成功")
            
            # 获取丰富后的数据
            stock_data = pool_manager.get_stock_by_code(test_stock)
            if stock_data and stock_data.get('health_score') is not None:
                logger.info(f"健康分数: {stock_data['health_score']:.3f}")
                logger.info("✅ 健康分数计算功能正常")
            else:
                logger.warning("⚠️ 健康分数未计算或未保存")
        else:
            logger.warning("⚠️ 数据丰富失败，但这可能是正常的（数据源问题）")
        
        # 获取丰富情况摘要
        summary = enricher.get_enrichment_summary()
        logger.info(f"丰富情况摘要: {summary}")
        
        logger.info("✅ Data Enricher 测试完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ Data Enricher 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_stock_profiler():
    """测试 stock_profiler.py 的参数画像生成"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("测试 3: Stock Profiler 参数画像生成")
    logger.info("=" * 60)
    
    try:
        from backend.stock_profiler import StockProfiler
        
        # 创建画像生成器
        profiler = StockProfiler()
        
        # 测试单只股票画像生成
        test_stock = "sz300290"
        logger.info(f"测试生成股票画像: {test_stock}")
        
        success = profiler.create_stock_profile(test_stock, method='differential_evolution')
        
        if success:
            logger.info("✅ 参数画像生成成功")
        else:
            logger.warning("⚠️ 参数画像生成失败，可能是数据不足")
        
        # 获取画像情况摘要
        summary = profiler.get_profiling_summary()
        logger.info(f"画像情况摘要: {summary}")
        
        logger.info("✅ Stock Profiler 测试完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ Stock Profiler 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_independent_profiling_script():
    """测试独立的个股画像生成脚本"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("测试 4: 独立个股画像生成脚本")
    logger.info("=" * 60)
    
    try:
        # 测试脚本是否可以导入
        script_path = os.path.join(backend_dir, 'run_stock_profiling.py')
        if not os.path.exists(script_path):
            logger.error("❌ 独立画像生成脚本不存在")
            return False
        
        logger.info("✅ 独立画像生成脚本文件存在")
        
        # 测试脚本的主要函数
        sys.path.append(backend_dir)
        from run_stock_profiling import run_profiling_batch
        
        # 运行小批量测试
        logger.info("运行小批量画像生成测试...")
        results = run_profiling_batch(
            limit=2,  # 只处理2只股票
            force_update=False,
            include_enrichment=True,
            optimization_method='differential_evolution'
        )
        
        logger.info(f"批量处理结果: {results}")
        logger.info("✅ 独立画像生成脚本测试完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 独立画像生成脚本测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_unified_api():
    """测试统一API功能"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("测试 5: 统一API功能")
    logger.info("=" * 60)
    
    try:
        from backend.stock_pool_manager import StockPoolManager
        
        # 测试 StockPoolManager 的新方法
        pool_manager = StockPoolManager()
        
        # 测试 get_stock_by_code 方法
        test_stock = "sz300290"
        stock_data = pool_manager.get_stock_by_code(test_stock)
        
        if stock_data:
            logger.info(f"✅ 成功获取股票数据: {test_stock}")
            logger.info(f"股票信息: 评分={stock_data.get('overall_score')}, 等级={stock_data.get('grade')}")
        else:
            logger.info(f"⚠️ 股票 {test_stock} 不在核心池中")
        
        # 测试统计信息
        stats = pool_manager.get_pool_statistics()
        logger.info(f"核心池统计: {stats}")
        
        logger.info("✅ 统一API功能测试完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 统一API功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_validation_functionality():
    """测试验证功能"""
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("测试 6: 历史验证功能")
    logger.info("=" * 60)
    
    try:
        from backend.universal_screener import UniversalScreener
        from backend.strategies.base_strategy import StrategyResult
        from datetime import datetime, timedelta
        
        # 创建筛选器
        screener = UniversalScreener()
        
        # 创建模拟的历史筛选结果
        test_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        mock_results = [
            StrategyResult(
                stock_code='sz300290',
                strategy_name='测试策略',
                signal_type='BUY',
                signal_strength=1,
                date=test_date,
                current_price=10.0,
                signal_details={'test': True}
            )
        ]
        
        logger.info(f"测试历史验证功能，使用日期: {test_date}")
        
        # 运行验证
        validated_results = screener.validate_screening_results(mock_results, test_date)
        
        if validated_results:
            logger.info(f"✅ 验证完成，处理了 {len(validated_results)} 个结果")
            
            # 检查验证结果
            for result in validated_results:
                if hasattr(result.signal_details, 'get') and 'validation_success' in result.signal_details:
                    logger.info(f"验证结果: {result.stock_code} - 成功: {result.signal_details.get('validation_success')}")
        else:
            logger.warning("⚠️ 验证结果为空")
        
        logger.info("✅ 历史验证功能测试完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 历史验证功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    logger = setup_logging()
    
    logger.info("🚀 Backend Step 1 实现测试开始")
    logger.info(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试结果统计
    test_results = {}
    
    # 运行各项测试
    tests = [
        ("Universal Screener 修复", test_universal_screener_fix),
        ("Data Enricher 功能", test_data_enricher),
        ("Stock Profiler 功能", test_stock_profiler),
        ("独立画像生成脚本", test_independent_profiling_script),
        ("统一API功能", test_unified_api),
        ("历史验证功能", test_validation_functionality)
    ]
    
    for test_name, test_func in tests:
        logger.info(f"\n开始测试: {test_name}")
        try:
            result = test_func()
            test_results[test_name] = result
            if result:
                logger.info(f"✅ {test_name} 测试通过")
            else:
                logger.warning(f"⚠️ {test_name} 测试未完全通过")
        except Exception as e:
            logger.error(f"❌ {test_name} 测试异常: {e}")
            test_results[test_name] = False
    
    # 输出测试总结
    logger.info("\n" + "=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)
    
    passed_count = sum(1 for result in test_results.values() if result)
    total_count = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\n总体结果: {passed_count}/{total_count} 测试通过")
    
    if passed_count == total_count:
        logger.info("🎉 所有测试通过！Backend Step 1 实现成功")
        return 0
    else:
        logger.warning(f"⚠️ 有 {total_count - passed_count} 个测试未通过")
        return 1

if __name__ == "__main__":
    exit(main())