#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立的个股画像生成脚本

这个脚本负责：
- 批量为核心池中的股票生成最优参数画像
- 可以通过定时任务调用
- 支持增量更新和全量更新
"""

import os
import sys
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Optional

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(backend_dir)

from stock_profiler import StockProfiler
from data_enricher import DataEnricher
from stock_pool_manager import StockPoolManager


def setup_logging(log_level: str = 'INFO') -> logging.Logger:
    """设置日志配置"""
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        handlers=[
            logging.FileHandler(f'stock_profiling_{datetime.now().strftime("%Y%m%d_%H%M")}.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


def run_profiling_batch(
    limit: Optional[int] = None,
    force_update: bool = False,
    include_enrichment: bool = True,
    optimization_method: str = 'differential_evolution'
) -> dict:
    """
    批量运行个股画像生成
    
    Args:
        limit: 限制处理的股票数量
        force_update: 是否强制更新已有画像
        include_enrichment: 是否包含数据丰富
        optimization_method: 优化方法
        
    Returns:
        处理结果统计
    """
    logger = logging.getLogger(__name__)
    logger.info("=" * 60)
    logger.info("开始批量个股画像生成")
    logger.info("=" * 60)
    
    # 初始化组件
    pool_manager = StockPoolManager()
    profiler = StockProfiler()
    enricher = DataEnricher() if include_enrichment else None
    
    # 获取需要处理的股票列表
    core_pool = pool_manager.get_core_pool(limit=limit)
    logger.info(f"核心池股票总数: {len(core_pool)}")
    
    # 筛选需要更新的股票
    stocks_to_process = []
    for stock in core_pool:
        stock_code = stock['stock_code']
        
        # 检查是否需要更新
        needs_update = force_update
        
        if not needs_update:
            # 检查是否已有画像
            if not stock.get('optimized_params'):
                needs_update = True
                logger.debug(f"{stock_code} 无画像数据，需要生成")
            else:
                # 检查画像是否过期（超过30天）
                try:
                    if isinstance(stock['optimized_params'], str):
                        params = json.loads(stock['optimized_params'])
                    else:
                        params = stock['optimized_params']
                    
                    optimization_date = params.get('optimization_date')
                    if optimization_date:
                        opt_date = datetime.fromisoformat(optimization_date.replace('Z', '+00:00'))
                        if (datetime.now() - opt_date).days > 30:
                            needs_update = True
                            logger.debug(f"{stock_code} 画像过期，需要更新")
                except:
                    needs_update = True
                    logger.debug(f"{stock_code} 画像数据异常，需要重新生成")
        
        if needs_update:
            stocks_to_process.append(stock_code)
    
    logger.info(f"需要处理的股票数量: {len(stocks_to_process)}")
    
    # 处理结果统计
    results = {
        'total_stocks': len(core_pool),
        'processed_stocks': len(stocks_to_process),
        'profiling_success': 0,
        'profiling_failed': 0,
        'enrichment_success': 0,
        'enrichment_failed': 0,
        'start_time': datetime.now().isoformat(),
        'end_time': None,
        'processing_time': 0,
        'failed_stocks': []
    }
    
    # 开始处理
    start_time = datetime.now()
    
    for i, stock_code in enumerate(stocks_to_process, 1):
        logger.info(f"处理进度 [{i}/{len(stocks_to_process)}]: {stock_code}")
        
        try:
            # 1. 数据丰富（如果启用）
            if enricher:
                logger.info(f"  正在丰富数据...")
                if enricher.enrich_single_stock(stock_code):
                    results['enrichment_success'] += 1
                    logger.info(f"  数据丰富成功")
                else:
                    results['enrichment_failed'] += 1
                    logger.warning(f"  数据丰富失败")
            
            # 2. 参数画像生成
            logger.info(f"  正在生成参数画像...")
            if profiler.create_stock_profile(stock_code, method=optimization_method):
                results['profiling_success'] += 1
                logger.info(f"  参数画像生成成功")
            else:
                results['profiling_failed'] += 1
                results['failed_stocks'].append(stock_code)
                logger.error(f"  参数画像生成失败")
                
        except Exception as e:
            logger.error(f"处理 {stock_code} 时出错: {e}")
            results['profiling_failed'] += 1
            results['failed_stocks'].append(stock_code)
    
    # 完成处理
    end_time = datetime.now()
    results['end_time'] = end_time.isoformat()
    results['processing_time'] = (end_time - start_time).total_seconds()
    
    # 输出统计结果
    logger.info("=" * 60)
    logger.info("批量个股画像生成完成")
    logger.info("=" * 60)
    logger.info(f"处理时间: {results['processing_time']:.1f} 秒")
    logger.info(f"核心池总数: {results['total_stocks']}")
    logger.info(f"处理股票数: {results['processed_stocks']}")
    logger.info(f"画像生成成功: {results['profiling_success']}")
    logger.info(f"画像生成失败: {results['profiling_failed']}")
    
    if enricher:
        logger.info(f"数据丰富成功: {results['enrichment_success']}")
        logger.info(f"数据丰富失败: {results['enrichment_failed']}")
    
    if results['failed_stocks']:
        logger.warning(f"失败的股票: {', '.join(results['failed_stocks'])}")
    
    # 获取最终统计
    profiling_summary = profiler.get_profiling_summary()
    logger.info(f"当前画像覆盖率: {profiling_summary.get('profiled_stocks', 0)}/{profiling_summary.get('total_stocks', 0)}")
    logger.info(f"平均验证分数: {profiling_summary.get('avg_validation_score', 0):.3f}")
    
    if enricher:
        enrichment_summary = enricher.get_enrichment_summary()
        logger.info(f"数据丰富覆盖率: {enrichment_summary.get('enriched_stocks', 0)}/{enrichment_summary.get('total_stocks', 0)}")
        logger.info(f"平均健康分数: {enrichment_summary.get('avg_health_score', 0):.3f}")
    
    return results


def run_incremental_update() -> dict:
    """增量更新模式 - 只处理新股票和过期画像"""
    logger = logging.getLogger(__name__)
    logger.info("运行增量更新模式")
    
    return run_profiling_batch(
        limit=None,
        force_update=False,
        include_enrichment=True,
        optimization_method='differential_evolution'
    )


def run_full_update(limit: Optional[int] = None) -> dict:
    """全量更新模式 - 重新生成所有画像"""
    logger = logging.getLogger(__name__)
    logger.info("运行全量更新模式")
    
    return run_profiling_batch(
        limit=limit,
        force_update=True,
        include_enrichment=True,
        optimization_method='differential_evolution'
    )


def run_profiling_only(limit: Optional[int] = None) -> dict:
    """仅参数画像模式 - 不进行数据丰富"""
    logger = logging.getLogger(__name__)
    logger.info("运行仅参数画像模式")
    
    return run_profiling_batch(
        limit=limit,
        force_update=False,
        include_enrichment=False,
        optimization_method='differential_evolution'
    )


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='个股画像生成脚本')
    parser.add_argument('--mode', choices=['incremental', 'full', 'profiling-only'], 
                       default='incremental', help='运行模式')
    parser.add_argument('--limit', type=int, help='限制处理的股票数量')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], 
                       default='INFO', help='日志级别')
    parser.add_argument('--method', choices=['differential_evolution', 'minimize'], 
                       default='differential_evolution', help='优化方法')
    parser.add_argument('--save-results', action='store_true', help='保存结果到JSON文件')
    
    args = parser.parse_args()
    
    # 设置日志
    logger = setup_logging(args.log_level)
    
    try:
        # 根据模式运行
        if args.mode == 'incremental':
            results = run_incremental_update()
        elif args.mode == 'full':
            results = run_full_update(args.limit)
        elif args.mode == 'profiling-only':
            results = run_profiling_only(args.limit)
        else:
            raise ValueError(f"未知的运行模式: {args.mode}")
        
        # 保存结果
        if args.save_results:
            result_file = f"profiling_results_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            logger.info(f"结果已保存到: {result_file}")
        
        # 返回码
        if results['profiling_failed'] == 0:
            logger.info("所有股票处理成功")
            return 0
        else:
            logger.warning(f"有 {results['profiling_failed']} 只股票处理失败")
            return 1
            
    except Exception as e:
        logger.error(f"脚本执行失败: {e}")
        return 2


if __name__ == "__main__":
    exit(main())