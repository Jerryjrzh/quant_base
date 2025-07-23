"""
并行参数优化模块 - 多只股票同时进行参数优化
(修改版: 使用 ProcessPoolExecutor 解决 GIL 性能问题)
"""

import os
import json
import time
import threading
from datetime import datetime
# 关键改动: 引入 ProcessPoolExecutor
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing
import itertools
import hashlib
import gc

# 关键改动: 将参数测试逻辑定义为顶层函数
# 这对于 ProcessPoolExecutor 的正常工作至关重要，因为它需要能够 "pickle" (序列化) 这个函数
# 以便发送到子进程中执行。
def _test_combination_worker(df, signals, combination):
    """
    在独立进程中运行的工作函数。
    注意: 这是您原始的 _test_parameter_combination 方法的逻辑。
    """
    try:
        # 在子进程中重新导入必要的模块
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
        # 发生异常时返回一个一致的结构，避免主进程出错
        return (0, None, None)


class ParallelStockOptimizer:
    """并行股票参数优化器 - 同时优化多只股票的参数"""

    def __init__(self, max_workers=None, max_stocks_parallel=8, cache_dir="analysis_cache"):
        """
        初始化并行股票参数优化器

        Args:
            max_workers: 每只股票的参数优化使用的最大进程数 (原为线程数)
            max_stocks_parallel: 同时处理的最大股票数
            cache_dir: 缓存目录
        """
        if max_workers is None:
            cpu_count = multiprocessing.cpu_count()
            # 每只股票使用的进程数 = 总CPU核心数 / 并行股票数
            # 确保至少有1个工作进程
            max_workers = max(1, cpu_count // max_stocks_parallel)

        self.max_workers = max_workers
        self.max_stocks_parallel = max_stocks_parallel
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

        self.optimization_cache = {}
        self.cache_lock = threading.Lock()

        print(f"🚀 并行股票优化器初始化: 同时处理 {max_stocks_parallel} 只股票, 每只股票 {max_workers} 个进程")

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

        # 外层仍然使用线程池，因为每个任务 (_optimize_single_stock) 主要是等待
        # 其内部的进程池完成，这是一种 I/O-bound 行为，适合用线程。
        with ThreadPoolExecutor(max_workers=self.max_stocks_parallel) as executor:
            future_to_stock = {}
            for stock_data in stock_data_list:
                stock_code = stock_data['stock_code']
                df = stock_data['df']
                signals = stock_data['signals']

                cached_result = self._get_cached_result(stock_code)
                if cached_result:
                    print(f"📂 {stock_code}: 使用缓存的优化参数")
                    results[stock_code] = cached_result
                    continue

                future = executor.submit(self._optimize_single_stock, stock_code, df, signals)
                future_to_stock[future] = stock_code

            completed = 0
            # 使用 len(future_to_stock) 来计算总任务数，更准确
            total_tasks = len(future_to_stock)
            if total_tasks == 0:
                print("✅ 所有股票均使用缓存，无需优化。")
                return results

            for future in as_completed(future_to_stock):
                stock_code = future_to_stock[future]
                completed += 1

                try:
                    result = future.result()
                    results[stock_code] = result

                    progress = completed / total_tasks * 100
                    elapsed = time.time() - start_time
                    print(f"✅ [{completed}/{total_tasks}] {stock_code}: 参数优化完成 "
                          f"(进度: {progress:.1f}%, 耗时: {elapsed:.1f}秒)")

                    self._cache_result(stock_code, result)

                except Exception as e:
                    print(f"❌ [{completed}/{total_tasks}] {stock_code}: 参数优化失败 - {e}")
                    results[stock_code] = {'error': f'优化失败: {e}'}

        total_time = time.time() - start_time
        avg_time = total_time / total_stocks if total_stocks > 0 else 0
        print(f"✅ 并行参数优化完成! 总耗时: {total_time:.2f}秒, 平均每只股票: {avg_time:.2f}秒")

        gc.collect()

        return results

    def _optimize_single_stock(self, stock_code, df, signals):
        """优化单只股票的参数 (使用 ProcessPoolExecutor)"""
        try:
            print(f"🔧 {stock_code}: 执行参数优化...")
            start_time = time.time()

            if signals is None or not signals.any():
                return {'error': '无有效信号，无法优化参数'}

            signal_count = len(signals[signals != ''])
            if signal_count < 3:
                return {'error': f'信号数量不足，需要至少3个信号，当前: {signal_count}'}

            param_ranges = {
                'pre_entry_discount': [0.02, 0.03, 0.05],
                'moderate_stop': [0.03, 0.05, 0.08],
                'moderate_profit': [0.10, 0.15, 0.20],
                'max_holding_days': [20, 30]
            }

            combinations = list(itertools.product(*param_ranges.values()))
            total_combinations = len(combinations)

            print(f"⚙️ {stock_code}: 测试 {total_combinations} 种参数组合 (进程数: {self.max_workers})")

            best_params = None
            best_score = -1
            best_result = None

            # 关键改动: 使用 ProcessPoolExecutor 进行 CPU 密集型任务
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_combination = {
                    executor.submit(_test_combination_worker, df, signals, combo): combo
                    for combo in combinations
                }

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

            optimization_result = {
                'best_parameters': best_params.__dict__ if best_params else None,
                'best_score': best_score,
                'best_result': best_result,
                'optimization_target': 'composite_score',
                'combinations_tested': total_combinations,
                'optimization_time': total_time
            }

            self._save_optimization_result(stock_code, optimization_result)

            return optimization_result

        except Exception as e:
            return {'error': f'参数优化失败: {e}'}

    # _test_parameter_combination 方法已被移除，并由顶层函数 _test_combination_worker 替代

    def _get_cached_result(self, stock_code):
        """获取缓存的优化结果"""
        with self.cache_lock:
            if stock_code in self.optimization_cache:
                return self.optimization_cache[stock_code]

        file_path = f"{self.cache_dir}/optimized_parameters_{stock_code}.json"
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

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

# 关键改动: 添加 `if __name__ == '__main__':` 保护
# 这是使用 `multiprocessing` (包括 ProcessPoolExecutor) 时的最佳实践，尤其是在 Windows 和 macOS 上。
# 它可以防止子进程无限递归地重新执行主程序代码。
if __name__ == '__main__':
    print("并行优化器模块已加载。")
    print("要运行优化，请在您的主脚本中导入并调用 optimize_stocks_parallel 函数。")

    # 这是一个示例，展示如何在您的主脚本中使用这个模块：
    #
    # from parallel_optimizer import optimize_stocks_parallel
    # import pandas as pd
    #
    # # 1. 准备您的数据
    # # 这是一个伪造的数据列表，您需要用真实数据替换
    # fake_stock_data = [
    #     {
    #         "stock_code": "STOCK_A",
    #         "df": pd.DataFrame({'close': range(100)}), # 使用您的真实行情 DataFrame
    #         "signals": pd.Series(['buy', '', 'buy', ''] * 25) # 使用您的真实信号 Series
    #     },
    #     {
    #         "stock_code": "STOCK_B",
    #         "df": pd.DataFrame({'close': range(100, 200)}),
    #         "signals": pd.Series(['', 'buy', '', 'buy'] * 25)
    #     }
    # ]
    #
    # # 2. 运行并行优化
    # # 注意: 您需要有一个名为 `parametric_advisor.py` 的文件，其中包含
    # # `TradingParameters` 和 `ParametricTradingAdvisor` 类，否则会引发 ImportError。
    # #
    # # try:
    # #     optimization_results = optimize_stocks_parallel(
    # #         stock_data_list=fake_stock_data,
    # #         max_stocks_parallel=4 # 同时优化4只股票
    # #     )
    # #     print("\n--- 优化结果 ---")
    # #     print(json.dumps(optimization_results, indent=2))
    # # except ImportError:
    # #     print("\n错误: 无法导入 'parametric_advisor'。请确保该文件存在且可访问。")
    # # except Exception as e:
    # #     print(f"\n运行时发生错误: {e}")