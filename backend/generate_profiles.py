#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【独立脚本】个股画像批量生成器

用于后台批量执行计算密集型的个股画像生成任务，并将结果存入数据库。
可选择为核心池、全市场或指定列表的股票生成画像。
"""

import argparse
import logging
import os
import sys
from datetime import datetime
#from typing import Optional, List
from typing import List
# 确保 backend 目录在 Python 路径中
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_profiler import StockProfiler
from stock_pool_manager import StockPoolManager
from data_handler import get_all_stock_codes_from_filesystem # 假设此函数已添加到data_handler

def setup_logging():
    """配置日志，使其同时输出到控制台和文件"""
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    log_filename = os.path.join(log_dir, f"profiling_job_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename, 'w', 'utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

#
# 文件: backend/generate_profiles.py
#

def main():
    """主执行函数"""
    setup_logging()
    logger = logging.getLogger(__name__)

    # --- 恢复完整的 parser 定义 ---
    parser = argparse.ArgumentParser(
        description="个股画像批量生成脚本",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        '--source',
        choices=['all', 'pool', 'list'],
        default='pool',
        help="""指定要生成画像的股票来源:
  all   - 全市场所有股票 (非常耗时)
  pool  - 核心观察池中的股票 (默认)
  list  - 通过 --stocks 参数指定的股票列表"""
    )
    parser.add_argument(
        '--stocks',
        type=str,
        help="要处理的股票列表，用逗号分隔 (例如: sz000001,sh600036)"
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help="指定使用的CPU核心数 (默认: 自动决定)"
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help="限制处理的股票数量 (用于测试)"
    )
    args = parser.parse_args()
    # --- parser 定义结束 ---

    logger.info("=" * 60)
    logger.info("🚀 启动个股画像批量生成任务")
    logger.info("=" * 60)

    profiler = StockProfiler()
    pool_manager = StockPoolManager()

    # 获取股票列表
    all_target_codes = []
    if args.source == 'all':
        logger.info("正在从文件系统获取全市场股票列表...")
        all_target_codes = get_all_stock_codes_from_filesystem()
        logger.info(f"发现 {len(all_target_codes)} 只股票。")
    elif args.source == 'pool':
        logger.info("正在从数据库获取核心观察池股票列表...")
        core_pool = pool_manager.get_core_pool()
        all_target_codes = [stock['stock_code'] for stock in core_pool]
        logger.info(f"核心池中有 {len(all_target_codes)} 只股票。")
    elif args.source == 'list':
        if not args.stocks:
            logger.error("错误: 使用 --source list 时必须提供 --stocks 参数。")
            sys.exit(1)
        all_target_codes = [s.strip().lower() for s in args.stocks.split(',')]
        logger.info(f"将处理指定的 {len(all_target_codes)} 只股票。")
    
    # 新增逻辑：跳过已有画像的股票
    logger.info("正在检查已有画像，将跳过已完成的股票...")
    existing_profiles = pool_manager.get_all_profiles()
    existing_codes = {stock['stock_code'] for stock in existing_profiles if stock.get('optimized_params')}
    
    stock_codes_to_process = [code for code in all_target_codes if code not in existing_codes]
    
    logger.info(f"目标总数: {len(all_target_codes)}, 已有画像: {len(existing_codes)}, 本次需处理: {len(stock_codes_to_process)}")

    if not stock_codes_to_process:
        logger.warning("没有需要处理的股票，任务退出。")
        return

    final_stock_list = stock_codes_to_process
    if args.limit:
        final_stock_list = stock_codes_to_process[:args.limit]
        logger.info(f"任务被限制为处理前 {len(final_stock_list)} 只股票。")

    start_time = datetime.now()
    results = profiler.run_profiling_for_pool(
        stock_codes=final_stock_list,
        use_multiprocessing=True,
        max_workers=args.workers
    )
    duration = (datetime.now() - start_time).total_seconds()

    # 输出任务总结
    logger.info("=" * 60)
    logger.info("✅ 批量生成任务完成")
    logger.info("=" * 60)
    logger.info(f"总计处理: {results.get('total', 0)} 只股票")
    logger.info(f"成功生成: {results.get('success', 0)} 只")
    logger.info(f"生成失败: {results.get('failed', 0)} 只")
    logger.info(f"总耗时: {duration:.2f} 秒")
    logger.info("=" * 60)

if __name__ == "__main__":
    main()