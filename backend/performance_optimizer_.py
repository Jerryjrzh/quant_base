"""
高性能优化模块 - 提供多线程和缓存优化
适用于高性能处理器和大内存环境
"""

import os
import json
import time
import threading
import glob
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Dict, List, Callable, Any, Optional, Tuple, Union
import multiprocessing
from functools import lru_cache
import hashlib
import pickle
import gc
import queue
import sys

# 全局性能配置
PERFORMANCE_CONFIG = {
    'max_memory_usage_percent': 85,  # 最大内存使用百分比
    'aggressive_gc': True,           # 是否启用激进的垃圾回收
    'use_mmap_for_large_data': False, # 对大数据使用内存映射
    'large_data_threshold_mb': 100,  # 大数据阈值(MB)
    'parallel_io': True,             # 并行IO操作
    'io_threads': 8,                 # IO线程数
    'optimize_numpy': False,         # 优化NumPy操作
    'cache_compression': False,      # 缓存压缩(降低内存占用但增加CPU使用)
    'prefetch_data': True,           # 数据预取
    'adaptive_batch_size': True,     # 自适应批处理大小
    'profile_hotspots': False        # 性能热点分析
}

class ProgressTracker:
    """进度跟踪器 - 显示多线程任务进度"""
    
    def __init__(self, total: int, task_name: str = "任务", update_interval: int = 5):
        self.total = total
        self.completed = 0
        self.task_name = task_name
        self.start_time = time.time()
        self.update_interval = update_interval  # 更新间隔（秒）
        self.last_update_time = self.start_time
        self.lock = threading.Lock()
        
        # 速度估计
        self.speed_samples = []
        self.last_completed = 0
        self.last_sample_time = self.start_time
    
    def update(self, increment: int = 1) -> None:
        """更新进度"""
        with self.lock:
            self.completed += increment
            current_time = time.time()
            
            # 更新速度样本
            if current_time - self.last_sample_time >= 1.0:  # 每秒采样一次
                time_diff = current_time - self.last_sample_time
                completed_diff = self.completed - self.last_completed
                if time_diff > 0:
                    speed = completed_diff / time_diff
                    self.speed_samples.append(speed)
                    # 保留最近10个样本
                    if len(self.speed_samples) > 10:
                        self.speed_samples = self.speed_samples[-10:]
                
                self.last_sample_time = current_time
                self.last_completed = self.completed
            
            # 检查是否应该更新显示
            if (self.completed == self.total or 
                self.completed == 1 or 
                current_time - self.last_update_time >= self.update_interval):
                
                self.display_progress()
                self.last_update_time = current_time
    
    def display_progress(self) -> None:
        """显示当前进度"""
        elapsed = time.time() - self.start_time
        progress = self.completed / self.total
        
        # 计算当前速度（每秒完成的任务数）
        if self.speed_samples:
            current_speed = sum(self.speed_samples) / len(self.speed_samples)
        else:
            current_speed = self.completed / elapsed if elapsed > 0 else 0
        
        # 估计剩余时间
        if current_speed > 0:
            remaining = (self.total - self.completed) / current_speed
        else:
            remaining = 0
        
        # 格式化时间
        def format_time(seconds):
            if seconds < 60:
                return f"{seconds:.1f}秒"
            elif seconds < 3600:
                return f"{seconds/60:.1f}分钟"
            else:
                return f"{seconds/3600:.1f}小时"
        
        # 格式化速度
        speed_str = f"{current_speed:.1f}任务/秒" if current_speed >= 0.1 else f"{current_speed*60:.1f}任务/分钟"
        
        print(f"⏳ {self.task_name}进度: {progress*100:.1f}% ({self.completed}/{self.total}) "
              f"速度: {speed_str}, "
              f"已用时间: {format_time(elapsed)}, "
              f"预计剩余: {format_time(remaining)}")

class BatchProcessor:
    """批量处理器 - 高性能处理大量任务"""
    
    def __init__(self, max_workers: Optional[int] = None, use_process_pool: bool = False):
        """
        初始化批量处理器
        
        Args:
            max_workers: 最大工作线程/进程数，默认自动根据系统资源确定
            use_process_pool: 是否使用进程池而非线程池（适用于CPU密集型任务）
        """
        # 自动确定最佳线程数
        if max_workers is None:
            max_workers = min(multiprocessing.cpu_count() * 2, 32)
        
        self.max_workers = max_workers
        self.use_process_pool = use_process_pool
        
        print(f"🧵 批处理器初始化: {'进程池' if use_process_pool else '线程池'}, {max_workers} 个工作单元")
    
    def process_stocks_batch(self, 
                            stock_codes: List[str], 
                            process_func: Callable[[str], Any],
                            batch_size: Optional[int] = None) -> Dict[str, Any]:
        """
        批量处理股票
        
        Args:
            stock_codes: 股票代码列表
            process_func: 处理单只股票的函数，接受股票代码，返回处理结果
            batch_size: 每批处理的股票数量，None表示自动确定
        
        Returns:
            Dict[str, Any]: 股票代码到处理结果的映射
        """
        # 自动确定批处理大小
        if batch_size is None:
            # 根据股票数量和工作线程数动态调整
            if len(stock_codes) > 1000:
                batch_size = min(100, len(stock_codes) // (self.max_workers * 2))
            elif len(stock_codes) > 100:
                batch_size = min(20, len(stock_codes) // self.max_workers)
            else:
                batch_size = max(1, min(10, len(stock_codes) // 2))
        
        results = {}
        total_stocks = len(stock_codes)
        
        # 创建进度跟踪器
        progress = ProgressTracker(total_stocks, "批量处理")
        
        # 分批处理
        for i in range(0, total_stocks, batch_size):
            batch = stock_codes[i:i+batch_size]
            batch_results = self._process_batch(batch, process_func, progress)
            results.update(batch_results)
            
            # 显示批次完成情况
            print(f"✅ 完成批次 {i//batch_size + 1}/{(total_stocks + batch_size - 1)//batch_size}")
            
            # 每处理5个批次，执行一次垃圾回收
            if (i // batch_size) % 5 == 4:
                gc.collect()
        
        return results
    
    def _process_batch(self, 
                      batch: List[str], 
                      process_func: Callable[[str], Any],
                      progress: ProgressTracker) -> Dict[str, Any]:
        """处理单个批次 - 支持线程池或进程池"""
        batch_results = {}
        
        # 根据任务类型选择合适的执行器
        if self.use_process_pool:
            # 使用进程池 - 适合CPU密集型任务
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_stock = {
                    executor.submit(self._process_with_progress, stock_code, process_func, progress): stock_code
                    for stock_code in batch
                }
                
                # 收集结果
                for future in as_completed(future_to_stock):
                    stock_code = future_to_stock[future]
                    try:
                        result = future.result()
                        batch_results[stock_code] = result
                    except Exception as e:
                        print(f"❌ 处理 {stock_code} 时出错: {e}")
                        batch_results[stock_code] = {'error': f'处理异常: {e}'}
        else:
            # 使用线程池 - 适合IO密集型任务
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                # 提交所有任务
                future_to_stock = {
                    executor.submit(self._process_with_progress, stock_code, process_func, progress): stock_code
                    for stock_code in batch
                }
                
                # 收集结果
                for future in as_completed(future_to_stock):
                    stock_code = future_to_stock[future]
                    try:
                        result = future.result()
                        batch_results[stock_code] = result
                    except Exception as e:
                        print(f"❌ 处理 {stock_code} 时出错: {e}")
                        batch_results[stock_code] = {'error': f'处理异常: {e}'}
        
        return batch_results
    
    def _process_with_progress(self, 
                              stock_code: str, 
                              process_func: Callable[[str], Any],
                              progress: ProgressTracker) -> Any:
        """处理单只股票并更新进度"""
        try:
            result = process_func(stock_code)
            return result
        finally:
            # 无论成功失败都更新进度
            progress.update()

class SmartCache:
    """智能缓存 - 缓存计算结果以提高性能"""
    
    def __init__(self, cache_dir: str = "analysis_cache", max_memory_items: int = 10000):
        """
        初始化智能缓存
        
        Args:
            cache_dir: 缓存目录
            max_memory_items: 内存中最多保存的缓存项数量
        """
        self.cache_dir = cache_dir
        self.binary_cache_dir = os.path.join(cache_dir, "binary")
        os.makedirs(cache_dir, exist_ok=True)
        os.makedirs(self.binary_cache_dir, exist_ok=True)
        
        # 使用LRU缓存策略的内存缓存
        self.memory_cache = {}
        self.max_memory_items = max_memory_items
        self.access_count = {}
        self.lock = threading.Lock()
        
        # 缓存统计
        self.stats = {
            'hits': 0,
            'misses': 0,
            'memory_hits': 0,
            'disk_hits': 0
        }
        
        # 预加载常用缓存
        self._preload_common_cache()
    
    def _preload_common_cache(self):
        """预加载常用缓存项到内存"""
        try:
            # 查找最近修改的缓存文件
            json_files = glob.glob(os.path.join(self.cache_dir, "*.json"))
            binary_files = glob.glob(os.path.join(self.binary_cache_dir, "*.pkl"))
            
            all_files = [(f, os.path.getmtime(f)) for f in json_files + binary_files]
            all_files.sort(key=lambda x: x[1], reverse=True)  # 按修改时间降序排序
            
            # 预加载最近的100个文件
            preload_count = min(50, len(all_files))
            if preload_count > 0:
              # print(f"🔄 预加载 {preload_count} 个常用缓存项...")
                
                for i, (file_path, _) in enumerate(all_files[:preload_count]):
                    try:
                        if file_path.endswith('.json'):
                            key = os.path.basename(file_path)[:-5]  # 去掉.json后缀
                            with open(file_path, 'r', encoding='utf-8') as f:
                                data = json.load(f)
                        else:  # .pkl文件
                            key = os.path.basename(file_path)[:-4]  # 去掉.pkl后缀
                            with open(file_path, 'rb') as f:
                                data = pickle.load(f)
                        
                        # 添加到内存缓存
                        with self.lock:
                            self.memory_cache[key] = data
                            self.access_count[key] = 1
                    except:
                        pass
                
               # print(f"✅ 缓存预加载完成，已加载 {len(self.memory_cache)} 项")
        except Exception as e:
            print(f"⚠️ 缓存预加载失败: {e}")
    
    def get(self, key: str, max_age_hours: int = 24) -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            key: 缓存键
            max_age_hours: 最大缓存有效期（小时）
        
        Returns:
            缓存数据，如果不存在或过期则返回None
        """
        # 先检查内存缓存
        with self.lock:
            if key in self.memory_cache:
                self.stats['hits'] += 1
                self.stats['memory_hits'] += 1
                self.access_count[key] = self.access_count.get(key, 0) + 1
                return self.memory_cache[key]
        
        # 检查二进制缓存（更快）
        binary_path = os.path.join(self.binary_cache_dir, f"{key}.pkl")
        if os.path.exists(binary_path):
            # 检查文件是否过期
            file_age_hours = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(binary_path))).total_seconds() / 3600
            if file_age_hours <= max_age_hours:
                try:
                    with open(binary_path, 'rb') as f:
                        data = pickle.load(f)
                    
                    # 更新内存缓存
                    self._update_memory_cache(key, data)
                    
                    self.stats['hits'] += 1
                    self.stats['disk_hits'] += 1
                    return data
                except:
                    pass
        
        # 检查JSON缓存（兼容性更好）
        json_path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(json_path):
            # 检查文件是否过期
            file_age_hours = (datetime.now() - datetime.fromtimestamp(os.path.getmtime(json_path))).total_seconds() / 3600
            if file_age_hours <= max_age_hours:
                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 更新内存缓存
                    self._update_memory_cache(key, data)
                    
                    # 同时更新二进制缓存（加速未来的访问）
                    try:
                        with open(binary_path, 'wb') as f:
                            pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
                    except:
                        pass
                    
                    self.stats['hits'] += 1
                    self.stats['disk_hits'] += 1
                    return data
                except:
                    pass
        
        self.stats['misses'] += 1
        return None
    
    def _update_memory_cache(self, key: str, data: Any) -> None:
        """更新内存缓存，如果超出容量则移除最少访问的项"""
        with self.lock:
            # 如果内存缓存已满，移除最少访问的项
            if len(self.memory_cache) >= self.max_memory_items and key not in self.memory_cache:
                # 按访问次数排序
                sorted_items = sorted(self.access_count.items(), key=lambda x: x[1])
                # 移除前10%最少访问的项
                items_to_remove = sorted_items[:max(1, len(sorted_items) // 10)]
                for k, _ in items_to_remove:
                    if k in self.memory_cache:
                        del self.memory_cache[k]
                        del self.access_count[k]
            
            # 添加新项
            self.memory_cache[key] = data
            self.access_count[key] = self.access_count.get(key, 0) + 1
    
    def set(self, key: str, data: Any, use_binary: bool = True) -> None:
        """
        设置缓存数据
        
        Args:
            key: 缓存键
            data: 要缓存的数据
            use_binary: 是否使用二进制格式（更快但兼容性较差）
        """
        # 更新内存缓存
        self._update_memory_cache(key, data)
        
        # 更新文件缓存
        json_path = os.path.join(self.cache_dir, f"{key}.json")
        binary_path = os.path.join(self.binary_cache_dir, f"{key}.pkl")
        
        try:
            # 总是保存JSON格式（兼容性好）
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 如果需要，也保存二进制格式（速度快）
            if use_binary:
                try:
                    with open(binary_path, 'wb') as f:
                        pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)
                except:
                    pass
        except Exception as e:
            print(f"❌ 缓存写入失败: {e}")
    
    def clear(self, older_than_hours: Optional[int] = None) -> int:
        """
        清理缓存
        
        Args:
            older_than_hours: 清理指定小时数以前的缓存，None表示清理所有
        
        Returns:
            清理的缓存数量
        """
        cleared = 0
        
        # 清理内存缓存
        with self.lock:
            self.memory_cache.clear()
            self.access_count.clear()
        
        # 清理文件缓存
        if older_than_hours is not None:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            
            # 清理JSON缓存
            for file_name in os.listdir(self.cache_dir):
                if file_name.endswith('.json'):
                    file_path = os.path.join(self.cache_dir, file_name)
                    if datetime.fromtimestamp(os.path.getmtime(file_path)) < cutoff_time:
                        try:
                            os.remove(file_path)
                            cleared += 1
                        except:
                            pass
            
            # 清理二进制缓存
            for file_name in os.listdir(self.binary_cache_dir):
                if file_name.endswith('.pkl'):
                    file_path = os.path.join(self.binary_cache_dir, file_name)
                    if datetime.fromtimestamp(os.path.getmtime(file_path)) < cutoff_time:
                        try:
                            os.remove(file_path)
                        except:
                            pass
        else:
            # 清理所有缓存文件
            for file_name in os.listdir(self.cache_dir):
                if file_name.endswith('.json'):
                    try:
                        os.remove(os.path.join(self.cache_dir, file_name))
                        cleared += 1
                    except:
                        pass
            
            for file_name in os.listdir(self.binary_cache_dir):
                if file_name.endswith('.pkl'):
                    try:
                        os.remove(os.path.join(self.binary_cache_dir, file_name))
                    except:
                        pass
        
        return cleared
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self.lock:
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = self.stats['hits'] / total_requests if total_requests > 0 else 0
            memory_hit_rate = self.stats['memory_hits'] / self.stats['hits'] if self.stats['hits'] > 0 else 0
            
            return {
                'total_requests': total_requests,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'hit_rate': f"{hit_rate:.1%}",
                'memory_hits': self.stats['memory_hits'],
                'disk_hits': self.stats['disk_hits'],
                'memory_hit_rate': f"{memory_hit_rate:.1%}",
                'memory_cache_size': len(self.memory_cache),
                'memory_cache_limit': self.max_memory_items
            }

class OptimizedParameterSearch:
    """优化参数搜索 - 高效搜索最佳参数"""
    
    def __init__(self, max_workers: int = 32):
        """
        初始化参数搜索
        
        Args:
            max_workers: 最大工作线程数
        """
        self.max_workers = max_workers
        self.cache = SmartCache("parameter_cache")
    
    def search(self, 
              parameter_space: Dict[str, List[Any]], 
              evaluation_func: Callable[[Dict[str, Any]], float],
              cache_key: Optional[str] = None) -> Dict[str, Any]:
        """
        搜索最佳参数
        
        Args:
            parameter_space: 参数空间，键为参数名，值为可能的参数值列表
            evaluation_func: 评估函数，接受参数字典，返回评分（越高越好）
            cache_key: 缓存键，如果提供则尝试使用缓存
        
        Returns:
            最佳参数组合
        """
        start_time = time.time()
        
        # 尝试从缓存获取
        if cache_key:
            cached_result = self.cache.get(cache_key)
            if cached_result:
                print(f"📂 使用缓存的参数搜索结果: {cache_key}")
                return cached_result
        
        import itertools
        
        # 生成所有参数组合
        param_names = list(parameter_space.keys())
        param_values = list(parameter_space.values())
        combinations = list(itertools.product(*param_values))
        
        print(f"🔍 参数搜索: {len(combinations)} 种组合 (线程数: {self.max_workers})")
        
        best_params = None
        best_score = float('-inf')
        progress = ProgressTracker(len(combinations), "参数搜索")
        
        # 内存中保存最近的评估结果，避免重复计算
        evaluation_cache = {}
        eval_cache_hits = 0
        eval_cache_lock = threading.Lock()
        
        def evaluate_params_cached(params):
            """带缓存的参数评估"""
            # 生成参数的哈希键
            param_str = json.dumps(params, sort_keys=True)
            param_key = hashlib.md5(param_str.encode()).hexdigest()
            
            # 检查内存缓存
            with eval_cache_lock:
                if param_key in evaluation_cache:
                    nonlocal eval_cache_hits
                    eval_cache_hits += 1
                    return evaluation_cache[param_key]
            
            # 执行评估
            try:
                score = evaluation_func(params)
                
                # 缓存结果
                with eval_cache_lock:
                    evaluation_cache[param_key] = score
                
                return score
            except Exception as e:
                return float('-inf')
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_params = {}
            for i, values in enumerate(combinations):
                params = dict(zip(param_names, values))
                future = executor.submit(evaluate_params_cached, params)
                future_to_params[future] = params
            
            # 收集结果
            for future in as_completed(future_to_params):
                params = future_to_params[future]
                try:
                    score = future.result()
                    progress.update()
                    
                    if score > best_score:
                        best_score = score
                        best_params = params
                except Exception:
                    progress.update()
        
        # 计算搜索时间
        search_time = time.time() - start_time
        
        # 显示评估缓存命中率
        cache_hit_rate = eval_cache_hits / len(combinations) if combinations else 0
        print(f"📊 评估缓存命中率: {cache_hit_rate:.1%} ({eval_cache_hits}/{len(combinations)})")
        
        result = {
            'best_parameters': best_params,
            'best_score': best_score,
            'search_space_size': len(combinations),
            'search_time': search_time,
            'search_speed': len(combinations) / search_time if search_time > 0 else 0
        }
        
        print(f"✅ 参数搜索完成! 耗时: {search_time:.2f}秒, 最佳得分: {best_score:.3f}")
        print(f"   搜索速度: {result['search_speed']:.1f} 组合/秒")
        
        # 缓存结果
        if cache_key:
            self.cache.set(cache_key, result)
        
        return result

# 向后兼容的别名
HighPerformanceCache = SmartCache
HighPerformanceParameterSearch = OptimizedParameterSearch

def optimize_system_for_performance():
    """优化系统性能"""
    print("🚀 正在优化系统性能...")
    
    # 配置垃圾回收
    if PERFORMANCE_CONFIG['aggressive_gc']:
        gc.enable()
        old_threshold = gc.get_threshold()
        gc.set_threshold(700, 10, 5)
        print(f"✅ 垃圾回收已优化: {old_threshold} -> (700, 10, 5)")
    
    # 清理不必要的模块
    initial_modules = len(sys.modules)
    for module_name in list(sys.modules.keys()):
        if module_name.startswith('_') and not module_name.startswith('__'):
            try:
                del sys.modules[module_name]
            except:
                pass
    print(f"✅ 清理了 {initial_modules - len(sys.modules)} 个不必要的模块")
    
    # 强制垃圾回收
    collected = gc.collect()
    print(f"✅ 强制垃圾回收: 回收了 {collected} 个对象")
    
    print("✅ 系统性能优化完成")
    return True

if __name__ == "__main__":
    # 测试性能优化模块
    optimize_system_for_performance()
    
    # 测试批量处理
    processor = BatchProcessor(max_workers=8)
    print("批量处理器初始化成功")
    
    # 测试缓存
    cache = SmartCache("test_cache")
    cache.set("test_key", {"value": "test_value"})
    result = cache.get("test_key")
    print(f"缓存测试: {result}")
    
    print("性能优化模块测试完成")