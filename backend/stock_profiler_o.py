#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
个股画像生成器 - 为每只股票找到最优技术指标参数

这个模块负责：
- 使用优化算法为每只股票找到最佳技术指标参数
- 基于历史数据验证参数有效性
- 将优化结果存储到数据库
"""

import json
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from scipy.optimize import minimize, differential_evolution
from concurrent.futures import ProcessPoolExecutor, as_completed
import warnings

from stock_pool_manager import StockPoolManager
import data_handler
import indicators

warnings.filterwarnings('ignore')


def _profiling_worker_process(args):
    """独立的、可被多进程调用的工作函数"""
    stock_code, db_path, method = args
    # 在新进程中，需要重新创建实例
    profiler = StockProfiler(db_path)
    return profiler.create_stock_profile(stock_code, method=method, is_worker=True)


class StockProfiler:
    """个股画像生成器"""
    
    def __init__(self, db_path: str = "stock_pool.db"):
        """初始化画像生成器"""
        self.pool_manager = StockPoolManager(db_path)
        self.logger = logging.getLogger(__name__)
        
        # 优化参数范围
        self.param_bounds = {
            'kdj_n': (5, 20),
            'rsi_period': (5, 30),
            'macd_fast': (5, 20),
            'macd_slow': (20, 50),
            'ma_short': (5, 20),
            'ma_long': (20, 60)
        }
        
        # 默认参数
        self.default_params = {
            'kdj_n': 27,
            'rsi_period': 14,
            'macd_fast': 12,
            'macd_slow': 26,
            'ma_short': 10,
            'ma_long': 30
        }

    def create_stock_profile(self, stock_code: str, method: str = 'differential_evolution', is_worker: bool = False) -> bool:
        """为单只股票创建最优参数画像"""
        if not is_worker:  # 如果是主进程调用，则打印日志
            self.logger.info(f"开始为 {stock_code} 生成参数画像")
        
        try:
            df = data_handler.get_full_data_with_indicators(stock_code)
            if df is None or len(df) < 250:  # 增加数据量要求
                self.logger.warning(f"{stock_code} 数据不足 (少于250天)，无法生成画像")
                return False
            
            recent_df = df.tail(250)
            
            # 运行优化
            optimal_params_dict = self._optimize_with_differential_evolution(recent_df)
            if optimal_params_dict is None or not optimal_params_dict.get('optimization_success'):
                self.logger.error(f"{stock_code} 参数优化失败，使用默认参数回退")
                optimal_params_dict = self.default_params.copy()
                optimal_params_dict['optimization_success'] = False
                optimal_params_dict['optimization_error'] = 1000.0

            # 验证参数
            validation_score = self._validate_parameters(df, optimal_params_dict)
            optimal_params_dict['validation_score'] = validation_score

            profile_data = {
                'optimized_params': json.dumps(optimal_params_dict),
                'optimization_method': method,
                'optimization_date': datetime.now().isoformat()
            }
            
            success = self.pool_manager.update_stock_profile(stock_code, profile_data)
            
            if success and not is_worker:
                self.logger.info(f"成功为 {stock_code} 生成参数画像，验证分数: {validation_score:.3f}")
            return success
                
        except Exception as e:
            self.logger.error(f"为 {stock_code} 生成参数画像时出错: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _optimize_with_differential_evolution(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """使用差分进化算法优化参数"""
        try:
            # 准备参数边界
            bounds = [
                self.param_bounds['kdj_n'],
                self.param_bounds['rsi_period'],
                self.param_bounds['macd_fast'],
                self.param_bounds['macd_slow'],
                self.param_bounds['ma_short'],
                self.param_bounds['ma_long']
            ]
            
            # 运行优化
            result = differential_evolution(
                self._objective_function,
                bounds,
                args=(df,),
                maxiter=50,  # 限制迭代次数以提高速度
                popsize=10,
                seed=42,
                atol=1e-3,
                tol=1e-3
            )
            
            if result.success:
                params = result.x
                return {
                    'kdj_n': int(params[0]),
                    'rsi_period': int(params[1]),
                    'macd_fast': int(params[2]),
                    'macd_slow': int(params[3]),
                    'ma_short': int(params[4]),
                    'ma_long': int(params[5]),
                    'optimization_error': float(result.fun),
                    'optimization_success': True
                }
            else:
                self.logger.warning("差分进化优化失败，使用默认参数")
                return self.default_params.copy()
                
        except Exception as e:
            self.logger.error(f"差分进化优化出错: {e}")
            return None

    def _optimize_with_minimize(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """使用scipy.minimize优化参数"""
        try:
            # 初始猜测
            initial_guess = [
                self.default_params['kdj_n'],
                self.default_params['rsi_period'],
                self.default_params['macd_fast'],
                self.default_params['macd_slow'],
                self.default_params['ma_short'],
                self.default_params['ma_long']
            ]
            
            # 参数边界
            bounds = [
                self.param_bounds['kdj_n'],
                self.param_bounds['rsi_period'],
                self.param_bounds['macd_fast'],
                self.param_bounds['macd_slow'],
                self.param_bounds['ma_short'],
                self.param_bounds['ma_long']
            ]
            
            # 运行优化
            result = minimize(
                self._objective_function,
                initial_guess,
                args=(df,),
                bounds=bounds,
                method='L-BFGS-B'
            )
            
            if result.success:
                params = result.x
                return {
                    'kdj_n': int(params[0]),
                    'rsi_period': int(params[1]),
                    'macd_fast': int(params[2]),
                    'macd_slow': int(params[3]),
                    'ma_short': int(params[4]),
                    'ma_long': int(params[5]),
                    'optimization_error': float(result.fun),
                    'optimization_success': True
                }
            else:
                self.logger.warning("minimize优化失败，使用默认参数")
                return self.default_params.copy()
                
        except Exception as e:
            self.logger.error(f"minimize优化出错: {e}")
            return None

    def _objective_function(self, params: List[float], df: pd.DataFrame) -> float:
        """
        目标函数：双目标优化，同时最小化买入信号与低点、卖出信号与高点的时间差
        """
        try:
            # 解析参数
            kdj_n = int(params[0])
            rsi_period = int(params[1])
            macd_fast = int(params[2])
            macd_slow = int(params[3])
            ma_short = int(params[4])
            ma_long = int(params[5])
            
            # 确保参数合理性
            if macd_fast >= macd_slow or ma_short >= ma_long:
                return 1000.0  # 惩罚不合理的参数
            
            # 计算技术指标
            df_work = df.copy()
            
            # KDJ指标
            kdj_k, kdj_d, kdj_j = indicators.calculate_kdj(df_work, n=kdj_n)
            
            # RSI指标
            rsi = indicators.calculate_rsi(df_work, periods=rsi_period)
            
            # MACD指标
            macd_line, signal_line = indicators.calculate_macd(
                df_work, fast=macd_fast, slow=macd_slow
            )
            histogram = macd_line - signal_line
            
            # 移动平均线
            ma_short_line = df_work['close'].rolling(window=ma_short).mean()
            ma_long_line = df_work['close'].rolling(window=ma_long).mean()
            
            # --- 优化点：同时处理买入和卖出 ---
            # 1. 买入信号与价格低点
            buy_signals = self._generate_buy_signals(
                df_work, kdj_k, kdj_d, rsi, macd_line, signal_line, 
                ma_short_line, ma_long_line
            )
            price_lows = self._find_price_lows(df_work)
            buy_distances = self._calculate_signal_low_distances(buy_signals, price_lows)
            buy_score = np.mean(buy_distances) if buy_distances else 1000.0

            # 2. 卖出信号与价格高点
            sell_signals = self._generate_sell_signals(
                df_work, kdj_k, kdj_d, rsi, macd_line, signal_line, 
                ma_short_line, ma_long_line
            )
            price_highs = self._find_price_highs(df_work)
            sell_distances = self._calculate_signal_high_distances(sell_signals, price_highs)
            sell_score = np.mean(sell_distances) if sell_distances else 1000.0
            
            # 3. 综合评分 (可以设置权重，例如更看重买点)
            final_score = 0.6 * buy_score + 0.4 * sell_score
            
            # 4. 信号数量惩罚
            signal_count_penalty = max(0, len(buy_signals) + len(sell_signals) - 40) * 0.1
            
            return final_score + signal_count_penalty
            
        except Exception:
            return 1000.0

    def _generate_buy_signals(self, df: pd.DataFrame, kdj_k: pd.Series, kdj_d: pd.Series,
                            rsi: pd.Series, macd_line: pd.Series, signal_line: pd.Series,
                            ma_short: pd.Series, ma_long: pd.Series) -> List[int]:
        """生成买入信号"""
        signals = []
        
        for i in range(50, len(df)):  # 从第50个数据点开始，确保指标计算完整
            try:
                # 多重条件买入信号
                conditions = []
                
                # KDJ金叉且在低位
                if (kdj_k.iloc[i] > kdj_d.iloc[i] and 
                    kdj_k.iloc[i-1] <= kdj_d.iloc[i-1] and 
                    kdj_k.iloc[i] < 50):
                    conditions.append(True)
                else:
                    conditions.append(False)
                
                # RSI从超卖区域回升
                if (rsi.iloc[i] > 30 and rsi.iloc[i-1] <= 30):
                    conditions.append(True)
                else:
                    conditions.append(False)
                
                # MACD金叉
                if (macd_line.iloc[i] > signal_line.iloc[i] and 
                    macd_line.iloc[i-1] <= signal_line.iloc[i-1]):
                    conditions.append(True)
                else:
                    conditions.append(False)
                
                # 均线多头排列
                if ma_short.iloc[i] > ma_long.iloc[i]:
                    conditions.append(True)
                else:
                    conditions.append(False)
                
                # 至少满足2个条件才产生信号
                if sum(conditions) >= 2:
                    signals.append(i)
                    
            except (IndexError, KeyError):
                continue
        
        return signals

    def _generate_sell_signals(self, df: pd.DataFrame, kdj_k: pd.Series, kdj_d: pd.Series,
                             rsi: pd.Series, macd_line: pd.Series, signal_line: pd.Series,
                             ma_short: pd.Series, ma_long: pd.Series) -> List[int]:
        """生成卖出信号"""
        signals = []
        for i in range(50, len(df)):
            try:
                conditions = []
                # KDJ死叉且在高位
                if (kdj_k.iloc[i] < kdj_d.iloc[i] and kdj_k.iloc[i-1] >= kdj_d.iloc[i-1] and kdj_k.iloc[i] > 50):
                    conditions.append(True)
                # RSI从超买区回落
                if (rsi.iloc[i] < 70 and rsi.iloc[i-1] >= 70):
                    conditions.append(True)
                # MACD死叉
                if (macd_line.iloc[i] < signal_line.iloc[i] and macd_line.iloc[i-1] >= signal_line.iloc[i-1]):
                    conditions.append(True)
                
                if sum(conditions) >= 2:
                    signals.append(i)
            except (IndexError, KeyError):
                continue
        return signals

    def _find_price_lows(self, df: pd.DataFrame, window: int = 10) -> List[int]:
        """找到价格低点"""
        lows = []
        
        for i in range(window, len(df) - window):
            # 检查是否是局部最低点
            current_low = df['low'].iloc[i]
            is_local_low = True
            
            # 检查前后window个交易日
            for j in range(i - window, i + window + 1):
                if j != i and df['low'].iloc[j] < current_low:
                    is_local_low = False
                    break
            
            if is_local_low:
                lows.append(i)
        
        return list(set(lows))  # 去重

    def _find_price_highs(self, df: pd.DataFrame, window: int = 10) -> List[int]:
        """找到价格高点"""
        highs = []
        for i in range(window, len(df) - window):
            current_high = df['high'].iloc[i]
            if current_high == df['high'].iloc[i - window : i + window + 1].max():
                highs.append(i)
        return list(set(highs))  # 去重

    def _calculate_signal_high_distances(self, signals: List[int], highs: List[int], 
                                       anticipate_days: Tuple[int, int] = (1, 5), 
                                       penalty_factor: float = 3.0) -> List[float]:
        """计算卖出信号与价格高点的时间距离"""
        return self._calculate_signal_low_distances(signals, highs, anticipate_days, penalty_factor)

    def _calculate_signal_low_distances(self, signals: List[int], lows: List[int], 
                                      anticipate_days: Tuple[int, int] = (1, 5), 
                                      penalty_factor: float = 3.0) -> List[float]:
        """
        计算信号与价格低点的时间距离（带提前约束和滞后惩罚）。
        """
        distances = []
        if not lows:  # 如果没有找到任何低点，直接返回惩罚
            return [100.0] * len(signals)

        for signal_idx in signals:
            # 计算所有有向距离 (low_idx - signal_idx)
            # 正数表示信号提前，负数表示信号滞后
            directed_distances = [low_idx - signal_idx for low_idx in lows]
            
            # 找出信号之后最近的低点
            future_low_distances = [d for d in directed_distances if d > 0]
            
            if not future_low_distances:
                # 如果信号之后没有低点，给予一个大的惩罚值
                min_dist = 100.0
            else:
                closest_future_dist = min(future_low_distances)
                # 判断是否在理想的"提前"区间内
                if anticipate_days[0] <= closest_future_dist <= anticipate_days[1]:
                    min_dist = closest_future_dist  # 在奖励区，直接使用天数作为成本
                else:
                    # 不在奖励区，给予惩罚
                    min_dist = closest_future_dist * penalty_factor
            
            distances.append(min_dist)

        return distances

    def _validate_parameters(self, df: pd.DataFrame, params: Dict[str, Any]) -> float:
        """验证参数的有效性，通过模拟交易计算胜率和回报"""
        try:
            # 使用更长的时间窗口进行验证
            df_test = df.tail(250).copy()
            
            # 计算指标
            kdj_k, kdj_d, kdj_j = indicators.calculate_kdj(df_test, n=params['kdj_n'])
            rsi = indicators.calculate_rsi(df_test, periods=params['rsi_period'])
            macd_line, signal_line = indicators.calculate_macd(
                df_test, fast=params['macd_fast'], slow=params['macd_slow']
            )
            histogram = macd_line - signal_line
            ma_short_line = df_test['close'].rolling(window=params['ma_short']).mean()
            ma_long_line = df_test['close'].rolling(window=params['ma_long']).mean()
            
            # 生成买卖信号
            buy_signals = self._generate_buy_signals(
                df_test, kdj_k, kdj_d, rsi, macd_line, signal_line,
                ma_short_line, ma_long_line
            )
            sell_signals = self._generate_sell_signals(
                df_test, kdj_k, kdj_d, rsi, macd_line, signal_line,
                ma_short_line, ma_long_line
            )
            
            if not buy_signals: 
                return 0.0

            # 模拟交易
            trades = []
            holding = False
            entry_price = 0
            entry_index = 0
            
            for i in range(len(df_test)):
                if not holding and i in buy_signals:
                    # 买入
                    holding = True
                    entry_price = df_test['close'].iloc[i]
                    entry_index = i
                elif holding and (i in sell_signals or (i - entry_index > 20)): # 卖出或超时
                    # 卖出
                    exit_price = df_test['close'].iloc[i]
                    if entry_price > 0:
                        trade_return = (exit_price - entry_price) / entry_price
                        trades.append({'return': trade_return, 'entry_index': entry_index})
                    holding = False
            
            if not trades: 
                return 0.0

            # 计算验证指标
            win_rate = len([t for t in trades if t['return'] > 0.02]) / len(trades)  # 胜率要求更高
            avg_return = np.mean([t['return'] for t in trades])
            
            validation_score = win_rate * 0.7 + max(0, avg_return) * 0.3
            return float(validation_score)
                
        except Exception as e:
            self.logger.error(f"验证参数时出错: {e}")
            return 0.0

    def run_profiling_for_pool(self, limit: Optional[int] = None, use_multiprocessing: bool = True) -> Dict[str, int]:
        self.logger.info(f"开始为核心观察池生成参数画像 ({'多进程' if use_multiprocessing else '单进程'}模式)")
        core_pool = self.pool_manager.get_core_pool(limit=limit)
        results = {'success': 0, 'failed': 0, 'total': len(core_pool)}
        stock_codes = [stock['stock_code'] for stock in core_pool]
        
        if use_multiprocessing and len(stock_codes) > 1:
            tasks = [(sc, self.pool_manager.db_path, 'differential_evolution') for sc in stock_codes]
            with ProcessPoolExecutor() as executor:
                futures = {executor.submit(_profiling_worker_process, task): task[0] for task in tasks}
                for i, future in enumerate(as_completed(futures), 1):
                    stock_code = futures[future]
                    self.logger.info(f"处理进度 [{i}/{len(stock_codes)}]: {stock_code}")
                    try:
                        if future.result(): results['success'] += 1
                        else: results['failed'] += 1
                    except Exception as e:
                        self.logger.error(f"处理 {stock_code} 时主进程捕获异常: {e}")
                        results['failed'] += 1
        else:
            for i, stock_code in enumerate(stock_codes, 1):
                self.logger.info(f"处理进度 [{i}/{len(stock_codes)}]: {stock_code}")
                if self.create_stock_profile(stock_code): results['success'] += 1
                else: results['failed'] += 1
        
        self.logger.info(f"参数画像生成完成: 成功 {results['success']}, 失败 {results['failed']}")
        return results

    def get_profiling_summary(self) -> Dict[str, Any]:
        """获取参数画像情况摘要"""
        try:
            core_pool = self.pool_manager.get_core_pool()
            
            summary = {
                'total_stocks': len(core_pool),
                'profiled_stocks': 0,
                'avg_validation_score': 0.0,
                'optimization_methods': {},
                'parameter_distributions': {}
            }
            
            validation_scores = []
            
            for stock in core_pool:
                if stock.get('optimized_params'):
                    summary['profiled_stocks'] += 1
                    
                    # 解析参数
                    if isinstance(stock['optimized_params'], str):
                        params = json.loads(stock['optimized_params'])
                    else:
                        params = stock['optimized_params']
                    
                    # 统计验证分数
                    if 'validation_score' in params:
                        validation_scores.append(params['validation_score'])
                    
                    # 统计优化方法
                    method = params.get('optimization_method', 'unknown')
                    summary['optimization_methods'][method] = summary['optimization_methods'].get(method, 0) + 1
            
            if validation_scores:
                summary['avg_validation_score'] = sum(validation_scores) / len(validation_scores)
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取画像摘要失败: {e}")
            return {}


def main():
    """测试函数"""
    import logging
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 创建画像生成器
    profiler = StockProfiler()
    
    # 测试单只股票画像生成
    test_stock = "sz300290"
    print(f"测试生成股票画像: {test_stock}")
    success = profiler.create_stock_profile(test_stock)
    print(f"画像生成结果: {'成功' if success else '失败'}")
    
    # 获取画像情况摘要
    summary = profiler.get_profiling_summary()
    print(f"画像情况摘要: {summary}")


if __name__ == "__main__":
    main()