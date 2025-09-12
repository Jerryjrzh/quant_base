#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成所有股票画像的脚本

这个脚本将为股票池中的所有股票生成个股画像，包括：
1. 核心观察池股票
2. 全部股票池股票
3. 提供进度监控和错误处理
4. 支持断点续传功能
"""

import os
import sys
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

# 添加backend目录到路径
sys.path.append('backend')

from stock_profiler import StockProfiler
from stock_pool_manager import StockPoolManager
from data_handler import get_all_stock_codes_from_filesystem


class ProfileGenerationManager:
    """股票画像生成管理器"""
    
    def __init__(self, db_path: str = "stock_pool.db"):
        self.profiler = StockProfiler(db_path)
        self.pool_manager = StockPoolManager(db_path)
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger('ProfileGenerator')
        logger.setLevel(logging.INFO)
        
        # 创建文件处理器
        log_filename = f"profile_generation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # 创建控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # 创建格式器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # 添加处理器
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger
    
    def generate_core_pool_profiles(self, use_multiprocessing: bool = True) -> Dict[str, int]:
        """为核心观察池生成画像"""
        self.logger.info("=" * 60)
        self.logger.info("开始为核心观察池生成股票画像")
        self.logger.info("=" * 60)
        
        start_time = time.time()
        results = self.profiler.run_profiling_for_pool(use_multiprocessing=use_multiprocessing)
        end_time = time.time()
        
        duration = end_time - start_time
        self.logger.info(f"核心池画像生成完成，耗时: {duration:.2f}秒")
        self.logger.info(f"结果统计: {results}")
        
        return results
    
    def generate_all_stock_profiles(self, batch_size: int = 50, use_multiprocessing: bool = True) -> Dict[str, int]:
        """为所有股票生成画像（分批处理）"""
        self.logger.info("=" * 60)
        self.logger.info("开始为所有股票生成画像")
        self.logger.info("=" * 60)
        
        # 获取所有股票代码（从文件系统扫描）
        self.logger.info("正在扫描本地股票数据...")
        all_stock_codes = get_all_stock_codes_from_filesystem()
        total_stocks = len(all_stock_codes)
        
        self.logger.info(f"扫描到股票数量: {total_stocks}")
        self.logger.info(f"批处理大小: {batch_size}")
        
        # 获取已有画像的股票
        existing_stocks_dict = {}
        existing_stocks = self.pool_manager.get_all_stocks()
        for stock in existing_stocks:
            if stock.get('optimized_params'):
                existing_stocks_dict[stock['stock_code']] = stock
        
        # 分类股票
        stocks_with_profiles = []
        stocks_without_profiles = []
        
        for stock_code in all_stock_codes:
            if stock_code in existing_stocks_dict:
                stocks_with_profiles.append(existing_stocks_dict[stock_code])
            else:
                # 创建基本股票信息
                stock_info = {
                    'stock_code': stock_code,
                    'stock_name': f'股票{stock_code}',
                    'optimized_params': None
                }
                stocks_without_profiles.append(stock_info)
        
        self.logger.info(f"已有画像股票: {len(stocks_with_profiles)}")
        self.logger.info(f"待生成画像股票: {len(stocks_without_profiles)}")
        
        if not stocks_without_profiles:
            self.logger.info("所有股票都已有画像，无需重新生成")
            return {'success': len(stocks_with_profiles), 'failed': 0, 'total': total_stocks}
        
        # 分批处理
        results = {'success': len(stocks_with_profiles), 'failed': 0, 'total': total_stocks}
        
        for i in range(0, len(stocks_without_profiles), batch_size):
            batch = stocks_without_profiles[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(stocks_without_profiles) + batch_size - 1) // batch_size
            
            self.logger.info(f"处理第 {batch_num}/{total_batches} 批，股票数量: {len(batch)}")
            
            batch_results = self._process_stock_batch(batch, use_multiprocessing)
            
            results['success'] += batch_results['success']
            results['failed'] += batch_results['failed']
            
            # 显示进度
            progress = (results['success'] + results['failed']) / total_stocks * 100
            self.logger.info(f"总体进度: {progress:.1f}% ({results['success'] + results['failed']}/{total_stocks})")
            
            # 批次间休息
            if i + batch_size < len(stocks_without_profiles):
                self.logger.info("批次间休息 5 秒...")
                time.sleep(1)
        
        self.logger.info("=" * 60)
        self.logger.info("所有股票画像生成完成")
        self.logger.info(f"最终结果: {results}")
        self.logger.info("=" * 60)
        
        return results
    
    def _process_stock_batch(self, batch: List[Dict], use_multiprocessing: bool) -> Dict[str, int]:
        """处理一批股票"""
        stock_codes = [stock['stock_code'] for stock in batch]
        
        if use_multiprocessing and len(stock_codes) > 1:
            return self._process_batch_multiprocessing(stock_codes)
        else:
            return self._process_batch_sequential(stock_codes)
    
    def _process_batch_multiprocessing(self, stock_codes: List[str]) -> Dict[str, int]:
        """多进程处理批次"""
        from concurrent.futures import ProcessPoolExecutor, as_completed
        from stock_profiler import _profiling_worker_process
        
        results = {'success': 0, 'failed': 0}
        
        tasks = [(sc, self.pool_manager.db_path, 'differential_evolution') for sc in stock_codes]
        
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(_profiling_worker_process, task): task[0] for task in tasks}
            
            for future in as_completed(futures):
                stock_code = futures[future]
                try:
                    if future.result():
                        results['success'] += 1
                        self.logger.info(f"✅ {stock_code} 画像生成成功")
                    else:
                        results['failed'] += 1
                        self.logger.warning(f"❌ {stock_code} 画像生成失败")
                except Exception as e:
                    results['failed'] += 1
                    self.logger.error(f"❌ {stock_code} 处理异常: {e}")
        
        return results
    
    def _process_batch_sequential(self, stock_codes: List[str]) -> Dict[str, int]:
        """顺序处理批次"""
        results = {'success': 0, 'failed': 0}
        
        for stock_code in stock_codes:
            try:
                if self.profiler.create_stock_profile(stock_code):
                    results['success'] += 1
                    self.logger.info(f"✅ {stock_code} 画像生成成功")
                else:
                    results['failed'] += 1
                    self.logger.warning(f"❌ {stock_code} 画像生成失败")
            except Exception as e:
                results['failed'] += 1
                self.logger.error(f"❌ {stock_code} 处理异常: {e}")
        
        return results
    
    def get_generation_summary(self) -> Dict:
        """获取画像生成情况摘要"""
        summary = self.profiler.get_profiling_summary()
        
        # 获取真实的股票池大小
        all_stock_codes = get_all_stock_codes_from_filesystem()
        all_stocks_in_db = self.pool_manager.get_all_stocks()
        core_stocks = self.pool_manager.get_core_pool()
        
        summary.update({
            'total_stocks_in_filesystem': len(all_stock_codes),
            'total_stocks_in_db': len(all_stocks_in_db),
            'core_pool_size': len(core_stocks),
            'profile_coverage': summary['profiled_stocks'] / len(all_stock_codes) * 100 if all_stock_codes else 0,
            'db_coverage': len(all_stocks_in_db) / len(all_stock_codes) * 100 if all_stock_codes else 0,
            'generation_timestamp': datetime.now().isoformat()
        })
        
        return summary
    
    def export_profiles_to_json(self, filename: Optional[str] = None) -> str:
        """导出所有画像到JSON文件"""
        if filename is None:
            filename = f"stock_profiles_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # 获取所有有画像的股票
        all_stocks_in_db = self.pool_manager.get_all_stocks()
        profiles_data = []
        
        for stock in all_stocks_in_db:
            if stock.get('optimized_params'):
                try:
                    if isinstance(stock['optimized_params'], str):
                        params = json.loads(stock['optimized_params'])
                    else:
                        params = stock['optimized_params']
                    
                    profile_data = {
                        'stock_code': stock['stock_code'],
                        'stock_name': stock.get('stock_name', ''),
                        'optimized_params': params,
                        'optimization_date': stock.get('optimization_date'),
                        'validation_score': params.get('validation_score', 0)
                    }
                    profiles_data.append(profile_data)
                except Exception as e:
                    self.logger.warning(f"导出 {stock['stock_code']} 画像数据失败: {e}")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(profiles_data, f, ensure_ascii=False, indent=2, default=str)
        
        self.logger.info(f"画像数据已导出到: {filename}")
        self.logger.info(f"导出股票数量: {len(profiles_data)}")
        
        return filename


def main():
    """主函数"""
    print("🚀 股票画像生成器启动")
    print("=" * 60)
    
    # 创建管理器
    manager = ProfileGenerationManager()
    
    # 显示当前状态
    summary = manager.get_generation_summary()
    print(f"当前画像状态:")
    print(f"  文件系统股票总数: {summary.get('total_stocks_in_filesystem', 0)}")
    print(f"  数据库中股票数: {summary.get('total_stocks_in_db', 0)}")
    print(f"  已有画像股票数: {summary.get('profiled_stocks', 0)}")
    print(f"  画像覆盖率: {summary.get('profile_coverage', 0):.1f}%")
    print(f"  数据库覆盖率: {summary.get('db_coverage', 0):.1f}%")
    print(f"  平均验证分数: {summary.get('avg_validation_score', 0):.3f}")
    print()
    
    # 用户选择
    print("请选择操作:")
    print("1. 为核心观察池生成画像 (推荐先执行)")
    print("2. 为所有股票生成画像 (耗时较长)")
    print("3. 查看画像生成摘要")
    print("4. 导出画像数据到JSON")
    print("5. 退出")
    
    while True:
        try:
            choice = input("\n请输入选择 (1-5): ").strip()
            
            if choice == '1':
                print("\n开始为核心观察池生成画像...")
                use_mp = input("是否使用多进程? (y/n, 默认y): ").strip().lower()
                use_multiprocessing = use_mp != 'n'
                
                results = manager.generate_core_pool_profiles(use_multiprocessing)
                print(f"\n核心池画像生成完成: {results}")
                
            elif choice == '2':
                print("\n开始为所有股票生成画像...")
                batch_size = input("批处理大小 (默认50): ").strip()
                batch_size = int(batch_size) if batch_size.isdigit() else 50
                
                use_mp = input("是否使用多进程? (y/n, 默认y): ").strip().lower()
                use_multiprocessing = use_mp != 'n'
                
                results = manager.generate_all_stock_profiles(batch_size, use_multiprocessing)
                print(f"\n全部股票画像生成完成: {results}")
                
            elif choice == '3':
                summary = manager.get_generation_summary()
                print("\n画像生成摘要:")
                for key, value in summary.items():
                    print(f"  {key}: {value}")
                
            elif choice == '4':
                filename = manager.export_profiles_to_json()
                print(f"\n画像数据已导出到: {filename}")
                
            elif choice == '5':
                print("退出程序")
                break
                
            else:
                print("无效选择，请重新输入")
                
        except KeyboardInterrupt:
            print("\n\n程序被用户中断")
            break
        except Exception as e:
            print(f"\n操作出错: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()