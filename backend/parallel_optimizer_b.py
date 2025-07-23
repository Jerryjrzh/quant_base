"""
并行参数优化模块 - 多只股票同时进行参数优化
"""

import os
import json
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing
import itertools
import hashlib
import gc

class ParallelStockOptimizer:
    """并行股票参数优化器 - 同时优化多只股票的参数"""
    
    def __init__(self, max_workers=None, max_stocks_parallel=8, cache_dir="analysis_cache"):
        """
        初始化并行股票参数优化器
        
        Args:
            max_workers: 每只股票的参数优化使用的最大线程数
            max_stocks_parallel: 同时处理的最大股票数
            cache_dir: 缓存目录
        """
        # 自动确定线程数
        if max_workers is None:
            cpu_count = multiprocessing.cpu_count()
            # 每只股票使用的线程数 = 总CPU核心数 / 并行股票数
            max_workers = max(32, cpu_count // max_stocks_parallel)
        
        self.max_workers = max_workers
        self.max_stocks_parallel = max_stocks_parallel
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
        # 优化结果缓存
        self.optimization_cache = {}
        self.cache_lock = threading.Lock()
        
        print(f"🚀 并行股票优化器初始化: 同时处理 {max_stocks_parallel} 只股票, 每只股票 {max_workers} 个线程")
    
    def optimize_stocks_batch(self, stock_data_list):
        """
        批量优化多只股票的参数
        
        Args:
            stock_data_list: 股票数据列表，每项包含 stock_code, df, signals
        
        Returns:
            Dict[str, Any]: 股票代码到优化结果的映射
        """
        start_time = time.time()
        results = {}
        total_stocks = len(stock_data_list)
        
        print(f"⚙️ 开始并行优化 {total_stocks} 只股票的参数")
        
        # 使用线程池并行处理多只股票
        with ThreadPoolExecutor(max_workers=self.max_stocks_parallel) as executor:
            # 提交所有任务
            future_to_stock = {}
            for stock_data in stock_data_list:
                stock_code = stock_data['stock_code']
                df = stock_data['df']
                signals = stock_data['signals']
                
                # 检查缓存
                cached_result = self._get_cached_result(stock_code)
                if cached_result:
                    print(f"📂 {stock_code}: 使用缓存的优化参数")
                    results[stock_code] = cached_result
                    continue
                
                # 提交优化任务
                future = executor.submit(self._optimize_single_stock, stock_code, df, signals)
                future_to_stock[future] = stock_code
            
            # 处理完成的任务
            completed = 0
            for future in as_completed(future_to_stock):
                stock_code = future_to_stock[future]
                completed += 1
                
                try:
                    result = future.result()
                    results[stock_code] = result
                    
                    # 显示进度
                    progress = completed / len(future_to_stock) * 100
                    elapsed = time.time() - start_time
                    print(f"✅ [{completed}/{len(future_to_stock)}] {stock_code}: 参数优化完成 "
                          f"(进度: {progress:.1f}%, 耗时: {elapsed:.1f}秒)")
                    
                    # 缓存结果
                    self._cache_result(stock_code, result)
                    
                except Exception as e:
                    print(f"❌ [{completed}/{len(future_to_stock)}] {stock_code}: 参数优化失败 - {e}")
                    results[stock_code] = {'error': f'优化失败: {e}'}
        
        total_time = time.time() - start_time
        print(f"✅ 并行参数优化完成! 总耗时: {total_time:.2f}秒, 平均每只股票: {total_time/total_stocks:.2f}秒")
        
        # 执行垃圾回收
        gc.collect()
        
        return results
    
    def _optimize_single_stock(self, stock_code, df, signals):
        """优化单只股票的参数"""
        try:
            from parametric_advisor import TradingParameters, ParametricTradingAdvisor
            
            print(f"🔧 {stock_code}: 执行参数优化...")
            start_time = time.time()
            
            # 检查信号数量
            if signals is None or not signals.any():
                return {'error': '无有效信号，无法优化参数'}
            
            signal_count = len(signals[signals != ''])
            if signal_count < 3:
                return {'error': f'信号数量不足，需要至少3个信号，当前: {signal_count}'}
            
            # 参数搜索空间
            param_ranges = {
                'pre_entry_discount': [0.02, 0.03, 0.05],
                'moderate_stop': [0.03, 0.05, 0.08],
                'moderate_profit': [0.10, 0.15, 0.20],
                'max_holding_days': [20, 30]
            }
            
            combinations = list(itertools.product(*param_ranges.values()))
            total_combinations = len(combinations)
            
            print(f"⚙️ {stock_code}: 测试 {total_combinations} 种参数组合 (线程数: {self.max_workers})")
            
            best_params = None
            best_score = -1
            best_result = None
            
            # 使用线程池并行测试参数组合
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_combination = {
                    executor.submit(self._test_parameter_combination, df, signals, combo): combo 
                    for combo in combinations
                }
                
                # 处理完成的任务
                for future in as_completed(future_to_combination):
                    try:
                        score, params, result = future.result()
                        if score > best_score:
                            best_score = score
                            best_params = params
                            best_result = result
                    except Exception:
                        continue
            
            total_time = time.time() - start_time
            
            # 保存优化结果
            optimization_result = {
                'best_parameters': best_params.__dict__ if best_params else None,
                'best_score': best_score,
                'best_result': best_result,
                'optimization_target': 'composite_score',
                'combinations_tested': total_combinations,
                'optimization_time': total_time
            }
            
            # 保存到文件
            self._save_optimization_result(stock_code, optimization_result)
            
            return optimization_result
            
        except Exception as e:
            return {'error': f'参数优化失败: {e}'}
    
    def _test_parameter_combination(self, df, signals, combination):
        """测试单个参数组合"""
        try:
            from parametric_advisor import TradingParameters, ParametricTradingAdvisor
            
            test_params = TradingParameters()
            test_params.pre_entry_discount = combination[0]
            test_params.moderate_stop = combination[1]
            test_params.moderate_profit = combination[2]
            test_params.max_holding_days = combination[3]
            
            test_advisor = ParametricTradingAdvisor(test_params)
            result = test_advisor.backtest_parameters(df, signals, 'moderate')
            
            if 'error' not in result and result['total_trades'] >= 1:
                # 综合评分：胜率 * 0.6 + 平均收益 * 0.4
                score = result['win_rate'] * 0.6 + max(0, result['avg_pnl']) * 0.4
                return (score, test_params, result)
            else:
                return (0, None, None)
        except Exception as e:
            return (0, None, None)
    
    def _get_cached_result(self, stock_code):
        """获取缓存的优化结果"""
        # 先检查内存缓存
        with self.cache_lock:
            if stock_code in self.optimization_cache:
                return self.optimization_cache[stock_code]
        
        # 检查文件缓存
        file_path = f"{self.cache_dir}/optimized_parameters_{stock_code}.json"
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 更新内存缓存
                with self.cache_lock:
                    self.optimization_cache[stock_code] = data
                
                return data
            except:
                pass
        
        return None
    
    def _cache_result(self, stock_code, result):
        """缓存优化结果"""
        with self.cache_lock:
            self.optimization_cache[stock_code] = result
    
    def _save_optimization_result(self, stock_code, result):
        """保存优化结果到文件"""
        try:
            file_path = f"{self.cache_dir}/optimized_parameters_{stock_code}.json"
            
            # 准备保存数据
            save_data = {
                'stock_code': stock_code,
                'optimization_date': datetime.now().isoformat(),
                'best_parameters': result['best_parameters'],
                'best_score': result['best_score'],
                'optimization_target': result['optimization_target']
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"❌ 保存优化结果失败: {e}")

def optimize_stocks_parallel(stock_data_list, max_stocks_parallel=8):
    """
    并行优化多只股票的参数（便捷函数）
    
    Args:
        stock_data_list: 股票数据列表，每项包含 stock_code, df, signals
        max_stocks_parallel: 同时处理的最大股票数
    
    Returns:
        Dict[str, Any]: 股票代码到优化结果的映射
    """
    optimizer = ParallelStockOptimizer(max_stocks_parallel=max_stocks_parallel)
    return optimizer.optimize_stocks_batch(stock_data_list)