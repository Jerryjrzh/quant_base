#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用股票筛选器框架
支持动态加载多种策略，前后端解耦
"""

import os
import glob
import json
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging
import warnings
import struct
from typing import List, Dict, Any, Optional
from pathlib import Path

import pandas as pd


class NumpyEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理numpy数据类型"""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, pd.Timestamp):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(obj, pd.Series):
            return obj.tolist()
        elif hasattr(obj, 'item'):  # numpy scalar
            return obj.item()
        return super(NumpyEncoder, self).default(obj)

# 修复导入路径
import sys
import os
sys.path.append(os.path.dirname(__file__))

# 导入策略相关模块
from strategies.base_strategy import StrategyResult
import backtester
from win_rate_filter import WinRateFilter, AdvancedTripleCrossFilter
import indicators

warnings.filterwarnings('ignore')

# --- 配置 ---
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
#MARKETS = ['sh', 'sz', 'bj', 'ds']
MARKETS = ['sh', 'sz', 'bj', 'ds']

# --- 路径定义 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))

# --- 初始化日志 ---
DATE = datetime.now().strftime("%Y%m%d_%H%M")
LOG_FILE = os.path.join(OUTPUT_PATH, f'universal_screener_{DATE}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, 'a', 'utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('universal_screener')


def process_single_stock_worker(args):
    """
    多进程工作函数 - 处理单只股票
    这个函数必须在模块级别定义以支持multiprocessing pickle
    """
    file_path, market, enabled_strategies, config_data = args
    
    # 在工作进程中重新导入必要的模块
    from strategy_manager import StrategyManager
    from strategies.base_strategy import StrategyResult
    # 【重要】导入新的数据处理器
    from data_handler import get_full_data_with_indicators
    
    stock_code_full = os.path.basename(file_path).split('.')[0]
    
    # 检查股票代码有效性
    valid_prefixes = {
        'sh': ['600', '601', '603', '605', '688'],
        'sz': ['000', '001', '002', '003', '300'],
        'bj': ['430', '831', '832', '833', '834', '835', '836', '837', '838', '839'],
 #       'ds': ['31#']
    }
    
    market_prefixes = valid_prefixes.get(market, [])
    stock_code_no_prefix = stock_code_full.replace(market, '')
    is_valid = any(stock_code_no_prefix.startswith(prefix) for prefix in market_prefixes)
    
    if not is_valid:
        return []
    
    try:
        # 【优化】一次性获取包含所有指标的数据
        # 注意：这里不再需要手动复权和计算指标
        df = get_full_data_with_indicators(stock_code_full)
        if df is None:
            return []
        
        # 在工作进程中创建策略管理器
        strategy_manager = StrategyManager()
        
        results = []
        
        # 对每个启用的策略进行筛选
        for strategy_id in enabled_strategies:
            try:
                # 处理所有策略通过统一的策略管理器
                strategy = strategy_manager.get_strategy_instance(strategy_id)
                if strategy is None:
                    continue
                
                # 检查数据长度是否足够
                if len(df) < strategy.get_required_data_length():
                    continue
                
                # 应用策略
                signal_series, details = strategy.apply_strategy(df)
                
                if signal_series is not None and details is not None:
                    # 检查最新一天是否有信号
                    latest_signal = signal_series.iloc[-1]
                    # 处理布尔信号和字符串信号
                    has_signal = False
                    if isinstance(latest_signal, bool):
                        has_signal = latest_signal
                        signal_type = 'BUY' if latest_signal else 'HOLD'
                    elif isinstance(latest_signal, str):
                        has_signal = latest_signal in ['POTENTIAL_BUY', 'BUY', 'STRONG_BUY']
                        signal_type = latest_signal
                    else:
                        continue
                    
                    if has_signal:
                        # 创建策略结果
                        result = StrategyResult(
                            stock_code=stock_code_full,
                            strategy_name=strategy.name,
                            signal_type=signal_type,
                            signal_strength=details.get('signal_strength', details.get('stage_passed', 1)),
                            date=df.index[-1].strftime('%Y-%m-%d'),
                            current_price=float(df['close'].iloc[-1]),
                            signal_details=details
                        )
                        
                        results.append(result)
            
            except Exception as e:
                # 在工作进程中记录错误但不中断处理
                continue
        
        return results
        
    except Exception as e:
        return []


def check_macd_zero_axis_pre_filter(df, signal_idx, signal_state, lookback_days=5):
    """
    MACD零轴启动策略的预筛选过滤器：排除五日内价格上涨超过5%的情况
    工作进程中可用的独立函数
    """
    try:
        # 只对MACD零轴启动策略进行过滤
        if signal_state not in ['PRE', 'MID', 'POST']:
            return False, ""
        
        # 获取信号前5天的数据
        start_idx = max(0, signal_idx - lookback_days)
        end_idx = signal_idx
        
        if start_idx >= end_idx:
            return False, ""
        
        # 计算5日内的最大涨幅
        lookback_data = df.iloc[start_idx:end_idx + 1]
        if len(lookback_data) < 2:
            return False, ""
        
        # 获取5日前的收盘价和信号当天的最高价
        base_price = lookback_data.iloc[0]['close']  # 5日前收盘价
        current_high = df.iloc[signal_idx]['high']    # 信号当天最高价
        
        # 计算涨幅
        price_increase = (current_high - base_price) / base_price
        
        # 如果5日内涨幅超过5%，则排除
        if price_increase > 0.25 or price_increase < 0.05:
            return True, f"五日内涨幅{price_increase:.1%}超过25%或者低于5%，排除不活跃风险"
        
        return False, ""
        
    except Exception as e:
        return False, ""

def check_weekly_golden_cross_ma_filter(df, signal_idx, signal_state, stock_code):
    """
    周线金叉+日线MA策略的过滤器
    工作进程中可用的独立函数
    """
    try:
        # 只对BUY信号进行严格过滤
        if signal_state != 'BUY':
            return False, ""
        
        # 1. 检查数据长度是否足够
        if len(df) < 240:  # 需要足够的数据计算MA240
            return True, "数据长度不足，无法计算长期MA"
        
        # 2. 检查价格是否过度上涨（防止追高）
        current_price = df.iloc[signal_idx]['close']
        ma13 = df['close'].rolling(window=13).mean().iloc[signal_idx]
        
        if pd.isna(ma13):
            return True, "MA13计算失败"
        
        # 价格距离MA13超过5%则排除
        price_distance = (current_price - ma13) / ma13
        if price_distance > 0.05:
            return True, f"价格距离MA13过远({price_distance:.1%})，排除追高风险"
        
        return False, ""
        
    except Exception as e:
        return True, f"过滤器执行失败: {e}"

def check_triple_cross_enhanced_filter(df, signal_idx, stock_code):
    """
    TRIPLE_CROSS策略的增强过滤器
    工作进程中可用的独立函数
    """
    try:
        # 简化版本，只进行基本检查
        quality_score = 0.5  # 默认中等质量
        cross_stage = 'UNKNOWN'
        
        # 这里可以添加更复杂的过滤逻辑
        # 目前返回默认通过
        
        return False, "通过增强筛选", {
            'quality_score': quality_score,
            'cross_stage': cross_stage,
            'filter_type': 'passed'
        }
        
    except Exception as e:
        return True, f"增强过滤器执行失败: {e}", {
            'quality_score': 0,
            'cross_stage': 'UNKNOWN',
            'filter_type': 'error'
        }



class UniversalScreener:
    """通用股票筛选器"""
    
    def __init__(self, config_file: Optional[str] = None):
        """
        初始化筛选器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file or os.path.join(backend_dir, 'strategies_config.json')
        self.config = self.load_config()
        
        # 初始化策略管理器
        from strategy_manager import StrategyManager
        self.strategy_manager = StrategyManager()
        
        # 筛选结果
        self.results: List[StrategyResult] = []
        
        logger.info("通用筛选器初始化完成")
    
    def load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"加载配置文件: {self.config_file}")
                return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "global_settings": {
                "max_concurrent_strategies": 5,
                "default_data_length": 500,
                "enable_parallel_processing": True,
                "log_level": "INFO"
            },
            "market_filters": {
                "valid_prefixes": {
                    "sh": ["600", "601", "603", "605", "688"],
                    "sz": ["000", "001", "002", "003", "300"],
                    "bj": ["430", "831", "832", "833", "834", "835", "836", "837", "838", "839"],
                    #"ds": ["31#", "43#", "48#"]
                },
                "exclude_st": True,
                "exclude_delisted": True,
                "min_market_cap": 500000000,
                "min_daily_volume": 10000000
            },
            "output_settings": {
                "save_detailed_analysis": True,
                "generate_charts": False,
                "export_formats": ["json", "txt", "csv"],
                "max_signals_per_strategy": 50
            }
        }
    
    def read_day_file(self, file_path: str) -> Optional[pd.DataFrame]:
        """读取通达信.day文件 - 使用统一数据处理模块"""
        from data_handler import read_day_file
        return read_day_file(file_path)
    
    def is_valid_stock_code(self, stock_code: str, market: str) -> bool:
        """检查股票代码是否有效"""
        try:
            valid_prefixes = self.config.get('market_filters', {}).get('valid_prefixes', {})
            market_prefixes = valid_prefixes.get(market, [])
            
            if not market_prefixes:
                # 默认前缀
                if market == 'sh':
                    market_prefixes = ['600', '601', '603', '605', '688']
                elif market == 'sz':
                    market_prefixes = ['000', '001', '002', '003', '300']
                elif market == 'bj':
                    market_prefixes = ['430', '831', '832', '833', '834', '835', '836', '837', '838', '839']
                elif market == 'ds':
                    market_prefixes = ['31#', '43#', '48#']
            
            stock_code_no_prefix = stock_code.replace(market, '')
            return any(stock_code_no_prefix.startswith(prefix) for prefix in market_prefixes)
            
        except Exception as e:
            logger.error(f"检查股票代码失败 {stock_code}: {e}")
            return False
    
    def process_single_stock(self, args) -> List[StrategyResult]:
        """处理单只股票"""
        file_path, market = args
        stock_code_full = os.path.basename(file_path).split('.')[0]
        
        # 检查股票代码有效性
        if not self.is_valid_stock_code(stock_code_full, market):
            return []
        
        try:
            # 读取股票数据
            df = self.read_day_file(file_path)
            if df is None:
                return []
            
            # 获取启用的策略
            enabled_strategies = self.strategy_manager.get_enabled_strategies()
            if not enabled_strategies:
                logger.warning("没有启用的策略")
                return []
            
            results = []
            
            # 对每个启用的策略进行筛选
            for strategy_id in enabled_strategies:
                try:
                    strategy = self.strategy_manager.get_strategy_instance(strategy_id)
                    if strategy is None:
                        continue
                    
                    # 检查数据长度是否足够
                    if len(df) < strategy.get_required_data_length():
                        continue
                    
                    # 应用策略
                    signal_series, details = strategy.apply_strategy(df)
                    
                    if signal_series is not None and details is not None:
                        # 检查最新一天是否有信号
                        latest_signal = signal_series.iloc[-1]
                        if latest_signal in ['POTENTIAL_BUY', 'BUY', 'STRONG_BUY']:
                            # 【新增】应用策略专用过滤器
                            should_exclude = False
                            exclude_reason = ""
                            
                            # 根据策略类型应用相应的过滤器
                            if 'MACD' in strategy.name and 'ZERO' in strategy.name:
                                # MACD零轴策略过滤
                                should_exclude, exclude_reason = check_macd_zero_axis_pre_filter(
                                    df, len(df) - 1, latest_signal
                                )
                            elif 'TRIPLE_CROSS' in strategy.name:
                                # 三重交叉策略过滤
                                should_exclude, exclude_reason, filter_details = check_triple_cross_enhanced_filter(
                                    df, len(df) - 1, stock_code_full
                                )
                                if not should_exclude:
                                    details.update(filter_details)
                            elif 'WEEKLY' in strategy.name and 'GOLDEN' in strategy.name:
                                # 周线金叉策略过滤
                                should_exclude, exclude_reason = check_weekly_golden_cross_ma_filter(
                                    df, len(df) - 1, latest_signal, stock_code_full
                                )
                            
                            # 如果被过滤器排除，跳过该结果
                            if should_exclude:
                                continue
                            
                            # 创建策略结果
                            result = StrategyResult(
                                stock_code=stock_code_full,
                                strategy_name=strategy.name,
                                signal_type=latest_signal,
                                signal_strength=details.get('stage_passed', 1),
                                date=df.index[-1].strftime('%Y-%m-%d'),
                                current_price=float(df['close'].iloc[-1]),
                                signal_details=details
                            )
                            
                            results.append(result)
                            logger.info(f"发现信号: {stock_code_full} - {strategy.name} - {latest_signal}")
                
                except Exception as e:
                    logger.error(f"策略 {strategy_id} 处理股票 {stock_code_full} 失败: {e}")
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"处理股票 {stock_code_full} 失败: {e}")
            return []
    
    def collect_stock_files(self) -> List[tuple]:
        """收集所有股票文件"""
        all_files = []
        
        for market in MARKETS:
            path = os.path.join(BASE_PATH, market, 'lday', '*.day')
            files = glob.glob(path)
            if not files:
                logger.warning(f"在路径 {path} 未找到任何文件")
            all_files.extend([(f, market) for f in files])
        
        return all_files
    
    def run_screening(self, selected_strategies: Optional[List[str]] = None) -> List[StrategyResult]:
        """
        运行筛选
        
        Args:
            selected_strategies: 指定要运行的策略ID列表，None表示运行所有启用的策略
            
        Returns:
            筛选结果列表
        """
        start_time = datetime.now()
        logger.info("===== 开始执行通用股票筛选 =====")
        
        # 如果指定了策略，临时启用这些策略
        original_enabled = []
        if selected_strategies:
            original_enabled = self.strategy_manager.get_enabled_strategies()
            for strategy_id in selected_strategies:
                self.strategy_manager.enable_strategy(strategy_id)
        
        try:
            # 收集股票文件
            all_files = self.collect_stock_files()
            if not all_files:
                logger.error("未找到任何股票数据文件")
                return []
            
            logger.info(f"共找到 {len(all_files)} 个股票文件")
            
            # 获取启用的策略
            enabled_strategies = self.strategy_manager.get_enabled_strategies()
            logger.info(f"启用的策略: {enabled_strategies}")
            
            if not enabled_strategies:
                logger.error("没有启用的策略")
                return []
            
            # 多进程处理
            enable_parallel = self.config.get('global_settings', {}).get('enable_parallel_processing', True)
            
            if enable_parallel:
                try:
                    max_workers = min(cpu_count(), 32)
                    # 准备多进程参数
                    process_args = [(file_path, market, enabled_strategies, self.config) for file_path, market in all_files]
                    
                    with Pool(processes=max_workers) as pool:
                        results_list = pool.map(process_single_stock_worker, process_args)
                except Exception as e:
                    logger.error(f"多进程处理失败: {e}")
                    # 降级到单进程
                    results_list = list(map(self.process_single_stock, all_files))
            else:
                results_list = list(map(self.process_single_stock, all_files))
            
            # 合并结果
            all_results = []
            for results in results_list:
                all_results.extend(results)

            # 【新增】对筛选结果进行回测分析
            run_backtest = self.config.get('global_settings', {}).get('run_backtest_after_scan', True)
            if run_backtest and all_results:
                logger.info(f"对 {len(all_results)} 个信号结果进行回测摘要分析...")
                all_results = self._run_backtest_on_results(all_results)
            
            # 【新增】自动触发深度扫描
            deep_scan_enabled = self.config.get('global_settings', {}).get('enable_deep_scan', False)
            if deep_scan_enabled and all_results and len(all_results) > 0:
                logger.info(f"\n启动深度扫描阶段...")
                deep_scan_results = self.trigger_deep_scan(all_results)
                
                if deep_scan_results:
                    # 统计深度扫描结果
                    valid_deep_results = {k: v for k, v in deep_scan_results.items() if 'error' not in v}
                    a_grade_stocks = [k for k, v in valid_deep_results.items() if v.get('overall_score', {}).get('grade') == 'A']
                    buy_recommendations = [k for k, v in valid_deep_results.items() if v.get('recommendation', {}).get('action') == 'BUY']
                    
                    logger.info(f"深度扫描结果: {len(valid_deep_results)}/{len(all_results)} 成功, A级: {len(a_grade_stocks)}, 买入推荐: {len(buy_recommendations)}")
                    
                    # 将深度扫描结果附加到筛选结果
                    for result in all_results:
                        if result.stock_code in valid_deep_results:
                            result.signal_details['deep_scan_result'] = valid_deep_results[result.stock_code]
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            logger.info(f"筛选完成，发现 {len(all_results)} 个信号，耗时 {processing_time:.2f} 秒")
            
            self.results = all_results
            return all_results
            
        finally:
            # 恢复原始策略启用状态
            if selected_strategies and original_enabled:
                # 禁用所有策略
                for strategy_id in self.strategy_manager.registered_strategies.keys():
                    self.strategy_manager.disable_strategy(strategy_id)
                # 重新启用原始策略
                for strategy_id in original_enabled:
                    self.strategy_manager.enable_strategy(strategy_id)
    
    def save_results(self, results: List[StrategyResult], output_dir: Optional[str] = None) -> Dict[str, str]:
        """
        保存筛选结果
        
        Args:
            results: 筛选结果
            output_dir: 输出目录
            
        Returns:
            保存的文件路径字典
        """
        if output_dir is None:
            output_dir = os.path.join(OUTPUT_PATH, 'UNIVERSAL_SCREENING')
        
        os.makedirs(output_dir, exist_ok=True)
        
        saved_files = {}
        
        try:
            # 转换结果为字典格式
            results_dict = [result.to_dict() for result in results]
            
            # 保存详细结果 (JSON)
            json_file = os.path.join(output_dir, f'screening_results_{DATE}.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(results_dict, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)
            saved_files['json'] = json_file
            
            # 生成汇总报告
            summary = self.generate_summary_report(results)
            summary_file = os.path.join(output_dir, f'screening_summary_{DATE}.json')
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2, cls=NumpyEncoder)
            saved_files['summary'] = summary_file
            
            # 生成文本报告
            text_file = os.path.join(output_dir, f'screening_report_{DATE}.txt')
            self.generate_text_report(results, text_file)
            saved_files['text'] = text_file
            
            # 生成CSV报告（如果配置启用）
            export_formats = self.config.get('output_settings', {}).get('export_formats', [])
            if 'csv' in export_formats:
                csv_file = os.path.join(output_dir, f'screening_results_{DATE}.csv')
                self.generate_csv_report(results, csv_file)
                saved_files['csv'] = csv_file
            
            logger.info(f"结果已保存至: {output_dir}")
            return saved_files
            
        except Exception as e:
            logger.error(f"保存结果失败: {e}")
            return {}
    
    def generate_summary_report(self, results: List[StrategyResult]) -> Dict[str, Any]:
        """生成汇总报告"""
        if not results:
            return {
                'scan_summary': {
                    'total_signals': 0,
                    'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'enabled_strategies': self.strategy_manager.get_enabled_strategies(),
                    'total_historical_signals': 0,
                    'avg_win_rate': '0.0%',
                    'avg_profit_rate': '0.0%',
                    'avg_days_to_peak': '0.0 天'
                },
                'signal_breakdown': {},
                'top_performers': [],
                'results': []
            }
        
        # 按策略分组统计
        strategy_stats = {}
        signal_type_stats = {}
        
        # 计算整体统计
        total_signals = len(results)
        backtest_results = []
        
        for result in results:
            # 策略统计
            strategy_name = result.strategy_name
            if strategy_name not in strategy_stats:
                strategy_stats[strategy_name] = 0
            strategy_stats[strategy_name] += 1
            
            # 信号类型统计
            signal_type = result.signal_type
            if signal_type not in signal_type_stats:
                signal_type_stats[signal_type] = 0
            signal_type_stats[signal_type] += 1
            
            # 收集回测统计信息
            signal_details = result.signal_details if hasattr(result, 'signal_details') else {}
            if 'backtest_win_rate' in signal_details:
                backtest_results.append({
                    'win_rate': signal_details['backtest_win_rate'],
                    'avg_profit': signal_details['backtest_avg_profit'],
                    'stock_code': result.stock_code
                })
        
        # 计算平均回测指标
        total_historical_signals = len(backtest_results)
        
        # 解析胜率和收益率（去掉百分号）
        win_rates = []
        profit_rates = []
        
        for backtest in backtest_results:
            # 解析胜率
            win_rate_str = str(backtest.get('win_rate', '0.0%')).replace('%', '')
            try:
                win_rates.append(float(win_rate_str))
            except:
                pass
            
            # 解析收益率
            profit_str = str(backtest.get('avg_profit', '0.0%')).replace('%', '')
            try:
                profit_rates.append(float(profit_str))
            except:
                pass
        
        # 计算平均值
        avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
        avg_profit_rate = sum(profit_rates) / len(profit_rates) if profit_rates else 0
        
        # 按信号强度分组
        signal_strength_breakdown = {}
        for result in results:
            strength = result.signal_strength
            if strength not in signal_strength_breakdown:
                signal_strength_breakdown[strength] = []
            signal_strength_breakdown[strength].append(result)
        
        # 最佳表现者（按回测收益排序）
        top_performers = []
        if backtest_results:
            # 按收益率排序
            sorted_results = sorted(
                [(r, next((b for b in backtest_results if b['stock_code'] == r.stock_code), None)) 
                 for r in results],
                key=lambda x: float(str(x[1]['avg_profit'] if x[1] else '0%').replace('%', '')) if x[1] else 0,
                reverse=True
            )[:10]  # 前10名
            
            for result, backtest in sorted_results:
                if backtest:
                    top_performers.append({
                        'stock_code': result.stock_code,
                        'strategy': result.strategy_name,
                        'signal_type': result.signal_type,
                        'win_rate': backtest['win_rate'],
                        'avg_profit': backtest['avg_profit'],
                        'current_price': result.current_price
                    })
        
        summary = {
            'scan_summary': {
                'total_signals': total_signals,
                'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'enabled_strategies': self.strategy_manager.get_enabled_strategies(),
                'strategy_distribution': strategy_stats,
                'signal_type_distribution': signal_type_stats,
                'signal_strength_breakdown': {k: len(v) for k, v in signal_strength_breakdown.items()},
                'total_historical_signals': total_historical_signals,
                'avg_win_rate': f"{avg_win_rate:.1f}%",
                'avg_profit_rate': f"{avg_profit_rate:.1f}%"
            },
            'signal_breakdown': {k: [result.to_dict() for result in v] for k, v in signal_strength_breakdown.items()},
            'top_performers': top_performers,
            'results': [result.to_dict() for result in results]
        }
        
        return summary
    
    def generate_text_report(self, results: List[StrategyResult], output_file: str):
        """生成文本报告"""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write("通用股票筛选报告\n")
                f.write("=" * 80 + "\n")
                f.write(f"扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"发现信号数: {len(results)}\n")
                f.write(f"启用策略: {', '.join(self.strategy_manager.get_enabled_strategies())}\n\n")
                
                if results:
                    # 生成汇总报告
                    summary = self.generate_summary_report(results)
                    scan_summary = summary['scan_summary']
                    
                    f.write("=== 扫描统计概览 ===\n")
                    f.write(f"总信号数: {scan_summary['total_signals']}\n")
                    f.write(f"历史信号数: {scan_summary['total_historical_signals']}\n")
                    f.write(f"平均胜率: {scan_summary['avg_win_rate']}\n")
                    f.write(f"平均收益: {scan_summary['avg_profit_rate']}\n\n")
                    
                    # 策略分布
                    if 'strategy_distribution' in scan_summary:
                        f.write("=== 策略分布 ===\n")
                        for strategy, count in scan_summary['strategy_distribution'].items():
                            f.write(f"{strategy}: {count} 个\n")
                        f.write("\n")
                    
                    # 信号类型分布
                    if 'signal_type_distribution' in scan_summary:
                        f.write("=== 信号类型分布 ===\n")
                        for signal_type, count in scan_summary['signal_type_distribution'].items():
                            f.write(f"{signal_type}: {count} 个\n")
                        f.write("\n")
                    
                    # 信号强度分布
                    if 'signal_strength_breakdown' in scan_summary:
                        f.write("=== 信号强度分布 ===\n")
                        for strength, count in scan_summary['signal_strength_breakdown'].items():
                            f.write(f"强度 {strength}: {count} 个\n")
                        f.write("\n")
                    
                    # 最佳表现者
                    if summary.get('top_performers'):
                        f.write("=== 前10名表现最佳股票 ===\n")
                        for i, stock in enumerate(summary['top_performers'], 1):
                            f.write(f"{i:2d}. {stock['stock_code']} - {stock['strategy']}\n")
                            f.write(f"    信号: {stock['signal_type']}, 价格: {stock['current_price']:.2f}\n")
                            f.write(f"    胜率: {stock.get('win_rate', 'N/A')}, 收益: {stock.get('avg_profit', 'N/A')}\n\n")
                    
                    # 按策略分组
                    strategy_groups = {}
                    for result in results:
                        strategy_name = result.strategy_name
                        if strategy_name not in strategy_groups:
                            strategy_groups[strategy_name] = []
                        strategy_groups[strategy_name].append(result)
                    
                    for strategy_name, strategy_results in strategy_groups.items():
                        f.write(f"\n{strategy_name} ({len(strategy_results)} 个信号)\n")
                        f.write("-" * 60 + "\n")
                        
                        for i, result in enumerate(strategy_results, 1):
                            f.write(f"{i:2d}. {result.stock_code} - {result.signal_type}\n")
                            f.write(f"    日期: {result.date}\n")
                            f.write(f"    价格: {result.current_price:.2f}\n")
                            f.write(f"    强度: {result.signal_strength}\n")
                            
                            # 添加策略特定信息
                            if hasattr(result, 'signal_details') and result.signal_details:
                                signal_details = result.signal_details
                                stage_passed = signal_details.get('stage_passed', 0)
                                f.write(f"    阶段: {stage_passed}\n")
                                
                                # 回测信息
                                if 'backtest_win_rate' in signal_details:
                                    f.write(f"    回测胜率: {signal_details['backtest_win_rate']}\n")
                                    f.write(f"    回测收益: {signal_details['backtest_avg_profit']}\n")
                                
                                # 深度扫描结果
                                if 'deep_scan_result' in signal_details:
                                    deep_result = signal_details['deep_scan_result']
                                    if 'overall_score' in deep_result:
                                        score = deep_result['overall_score'].get('total_score', 0)
                                        grade = deep_result['overall_score'].get('grade', 'N/A')
                                        f.write(f"    深度评分: {score:.1f} ({grade}级)\n")
                                    if 'recommendation' in deep_result:
                                        action = deep_result['recommendation'].get('action', 'N/A')
                                        confidence = deep_result['recommendation'].get('confidence', 0)
                                        f.write(f"    推荐操作: {action} (信心度: {confidence:.1%})\n")
                            
                            f.write("\n")
                
        except Exception as e:
            logger.error(f"生成文本报告失败: {e}")
    
    def generate_csv_report(self, results: List[StrategyResult], output_file: str):
        """生成CSV报告"""
        try:
            if not results:
                return
            
            # 转换为DataFrame
            data = []
            for result in results:
                row = {
                    'stock_code': result.stock_code,
                    'strategy': result.strategy_name,
                    'signal_type': result.signal_type,
                    'signal_strength': result.signal_strength,
                    'date': result.date,
                    'current_price': result.current_price,
                    'scan_timestamp': result.scan_timestamp
                }
                data.append(row)
            
            df = pd.DataFrame(data)
            df.to_csv(output_file, index=False, encoding='utf-8-sig')
            
        except Exception as e:
            logger.error(f"生成CSV报告失败: {e}")
    
    def _run_backtest_on_results(self, results: List[StrategyResult]) -> List[StrategyResult]:
        """
        【新增函数】
        为筛选出的结果列表中的每个股票运行一次简化的回测。
        """
        # 按股票代码分组，避免重复加载数据和回测
        stocks_to_backtest = {res.stock_code for res in results}
        backtest_summaries = {}

        for i, stock_code in enumerate(stocks_to_backtest, 1):
            logger.info(f"回测分析 [{i}/{len(stocks_to_backtest)}]: {stock_code}")
            if '#' in stock_code:
                market = 'ds'
            else:
                market = stock_code[:2]  # 前两位是市场代码
            try:
                # 使用与 portfolio_manager 相同的方式获取数据
                df = self.read_day_file(os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day'))
                if df is None or len(df) < 100: continue

                # 生成信号Series用于回测
                signals_for_stock = [res for res in results if res.stock_code == stock_code]
                strategy_name = signals_for_stock[0].strategy_name
                strategy = self.strategy_manager.get_strategy_instance(strategy_name)
                if not strategy: continue
                
                signal_series, _ = strategy.apply_strategy(df)
                
                # 调用标准回测函数
                backtest_result = backtester.run_backtest(df, signal_series)
                backtest_summaries[stock_code] = backtest_result
            except Exception as e:
                logger.error(f"为 {stock_code} 生成回测摘要失败: {e}")
                continue

        # 将回测结果附加到原始结果中
        for res in results:
            summary = backtest_summaries.get(res.stock_code)
            if summary and 'win_rate' in summary:
                res.signal_details['backtest_win_rate'] = summary['win_rate']
                res.signal_details['backtest_avg_profit'] = summary['avg_max_profit']
        
        return results
    
    def check_macd_zero_axis_pre_filter(self, df: pd.DataFrame, signal_idx: int, signal_state: str, lookback_days: int = 5) -> tuple:
        """
        MACD零轴启动策略的预筛选过滤器：排除五日内价格上涨超过5%的情况
        
        Args:
            df: 股票数据DataFrame
            signal_idx: 信号出现的索引
            signal_state: 信号状态
            lookback_days: 回看天数
        
        Returns:
            tuple: (是否应该排除, 排除原因)
        """
        try:
            # 只对MACD零轴启动策略进行过滤
            if signal_state not in ['PRE', 'MID', 'POST']:
                return False, ""
            
            # 获取信号前5天的数据
            start_idx = max(0, signal_idx - lookback_days)
            end_idx = signal_idx
            
            if start_idx >= end_idx:
                return False, ""
            
            # 计算5日内的最大涨幅
            lookback_data = df.iloc[start_idx:end_idx + 1]
            if len(lookback_data) < 2:
                return False, ""
            
            # 获取5日前的收盘价和信号当天的最高价
            base_price = lookback_data.iloc[0]['close']  # 5日前收盘价
            current_high = df.iloc[signal_idx]['high']    # 信号当天最高价
            
            # 计算涨幅
            price_increase = (current_high - base_price) / base_price
            
            # 如果5日内涨幅超过5%，则排除
            if price_increase > 0.25 or price_increase < 0.05:
                return True, f"五日内涨幅{price_increase:.1%}超过25%或者低于5%，排除不活跃风险"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"MACD零轴预筛选过滤器检查失败: {e}")
            return False, ""
    
    def check_weekly_golden_cross_ma_filter(self, df: pd.DataFrame, signal_idx: int, signal_state: str, stock_code: str) -> tuple:
        """
        周线金叉+日线MA策略的过滤器
        
        Args:
            df: 股票数据DataFrame
            signal_idx: 信号出现的索引
            signal_state: 信号状态 ('BUY', 'HOLD', 'SELL')
            stock_code: 股票代码
        
        Returns:
            tuple: (是否应该排除, 排除原因)
        """
        try:
            # 只对BUY信号进行严格过滤
            if signal_state != 'BUY':
                return False, ""
            
            # 1. 检查数据长度是否足够
            if len(df) < 240:  # 需要足够的数据计算MA240
                return True, "数据长度不足，无法计算长期MA"
            
            # 2. 检查价格是否过度上涨（防止追高）
            current_price = df.iloc[signal_idx]['close']
            ma13 = df['close'].rolling(window=13).mean().iloc[signal_idx]
            
            if pd.isna(ma13):
                return True, "MA13计算失败"
            
            # 价格距离MA13超过5%则排除
            price_distance = (current_price - ma13) / ma13
            if price_distance > 0.05:
                return True, f"价格距离MA13过远({price_distance:.1%})，排除追高风险"
            
            # 3. 检查成交量是否异常
            if 'volume' in df.columns:
                current_volume = df.iloc[signal_idx]['volume']
                avg_volume = df['volume'].rolling(window=20).mean().iloc[signal_idx]
                
                if not pd.isna(avg_volume) and avg_volume > 0:
                    volume_ratio = current_volume / avg_volume
                    # 成交量过度放大（超过5倍）可能是异常
                    if volume_ratio > 5.0:
                        return True, f"成交量异常放大({volume_ratio:.1f}倍)，可能存在风险"
            
            # 4. 检查短期涨幅（5日内涨幅超过15%排除）
            if signal_idx >= 5:
                price_5_days_ago = df.iloc[signal_idx - 5]['close']
                short_term_gain = (current_price - price_5_days_ago) / price_5_days_ago
                if short_term_gain > 0.15:
                    return True, f"短期涨幅过大({short_term_gain:.1%})，排除追高风险"
            
            return False, ""
            
        except Exception as e:
            logger.error(f"周线金叉+日线MA过滤器检查失败 {stock_code}: {e}")
            return True, f"过滤器执行失败: {e}"
    
    def analyze_ma_trend(self, df: pd.DataFrame) -> Dict[str, float]:
        """
        分析MA趋势强度和相关指标
        
        Args:
            df: 股票数据DataFrame
        
        Returns:
            dict: 包含趋势分析结果的字典
        """
        try:
            # 计算各种MA
            ma_periods = [7, 13, 30, 45]
            mas = {}
            for period in ma_periods:
                mas[f'ma_{period}'] = df['close'].rolling(window=period).mean()
            
            current_price = df['close'].iloc[-1]
            ma13_current = mas['ma_13'].iloc[-1]
            
            # 1. 计算趋势强度（MA排列程度）
            trend_strength = 0
            if not pd.isna(ma13_current):
                # 检查MA排列：7>13>30>45
                if (mas['ma_7'].iloc[-1] > mas['ma_13'].iloc[-1] and
                    mas['ma_13'].iloc[-1] > mas['ma_30'].iloc[-1] and
                    mas['ma_30'].iloc[-1] > mas['ma_45'].iloc[-1]):
                    trend_strength = 1.0
                elif (mas['ma_7'].iloc[-1] > mas['ma_13'].iloc[-1] and
                      mas['ma_13'].iloc[-1] > mas['ma_30'].iloc[-1]):
                    trend_strength = 0.7
                elif mas['ma_7'].iloc[-1] > mas['ma_13'].iloc[-1]:
                    trend_strength = 0.4
                else:
                    trend_strength = 0.0
            
            # 2. 计算价格距离MA13的百分比
            ma13_distance = 0
            if not pd.isna(ma13_current) and ma13_current > 0:
                ma13_distance = (current_price - ma13_current) / ma13_current
            
            # 3. 计算成交量放大比例
            volume_surge_ratio = 1.0
            if 'volume' in df.columns and len(df) >= 20:
                current_volume = df['volume'].iloc[-1]
                avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]
                if not pd.isna(avg_volume) and avg_volume > 0:
                    volume_surge_ratio = current_volume / avg_volume
            
            return {
                'trend_strength': trend_strength,
                'ma13_distance': ma13_distance,
                'volume_surge_ratio': volume_surge_ratio
            }
            
        except Exception as e:
            logger.error(f"MA趋势分析失败: {e}")
            return {
                'trend_strength': 0,
                'ma13_distance': 0,
                'volume_surge_ratio': 1.0
            }
    
    def check_triple_cross_enhanced_filter(self, df: pd.DataFrame, signal_idx: int, stock_code: str) -> tuple:
        """
        TRIPLE_CROSS策略的增强过滤器：结合胜率筛选和交叉阶段分析
        
        Args:
            df: 股票数据DataFrame
            signal_idx: 信号出现的索引
            stock_code: 股票代码
        
        Returns:
            tuple: (是否应该排除, 排除原因, 详细信息)
        """
        try:
            # 1. 使用增强版过滤器
            advanced_filter = AdvancedTripleCrossFilter()
            should_exclude, exclude_reason, quality_score, cross_stage = advanced_filter.enhanced_triple_cross_filter(df, signal_idx)
            
            if should_exclude:
                return True, exclude_reason, {
                    'quality_score': quality_score,
                    'cross_stage': cross_stage,
                    'filter_type': 'advanced_quality'
                }
            
            # 2. 胜率过滤器检查
            try:
                # 假设有apply_triple_cross函数
                import strategies
                signal_series = strategies.apply_triple_cross(df)
                if signal_series is not None:
                    win_rate_filter = WinRateFilter(min_win_rate=0.4, min_signals=3, min_avg_profit=0.08)
                    should_exclude_wr, exclude_reason_wr, backtest_stats = win_rate_filter.should_exclude_stock(df, signal_series, stock_code)
                    
                    if should_exclude_wr:
                        return True, f"胜率筛选: {exclude_reason_wr}", {
                            'quality_score': quality_score,
                            'cross_stage': cross_stage,
                            'filter_type': 'win_rate',
                            'backtest_stats': backtest_stats
                        }
            except ImportError:
                logger.warning("strategies模块不可用，跳过胜率过滤")
                pass
            
            # 3. 通过所有筛选
            backtest_stats = {}  # 初始化默认空值
            return False, "通过增强筛选", {
                'quality_score': quality_score,
                'cross_stage': cross_stage,
                'filter_type': 'passed',
                'backtest_stats': backtest_stats
            }
            
        except Exception as e:
            return True, f"增强过滤器执行失败: {e}", {
                'quality_score': 0,
                'cross_stage': 'UNKNOWN',
                'filter_type': 'error'
            }
    
    def calculate_backtest_stats(self, df: pd.DataFrame, signal_series: pd.Series) -> Dict[str, Any]:
        """计算细化的回测统计信息"""
        try:
            # 计算技术指标（回测需要）
            if 'dif' not in df.columns or 'dea' not in df.columns:
                macd_values = indicators.calculate_macd(df)
                df['dif'], df['dea'] = macd_values[0], macd_values[1]
                
            if 'k' not in df.columns or 'd' not in df.columns:
                kdj_values = indicators.calculate_kdj(df)
                df['k'], df['d'], df['j'] = kdj_values[0], kdj_values[1], kdj_values[2]
            
            # 执行细化回测
            backtest_results = backtester.run_backtest(df, signal_series)
            
            if isinstance(backtest_results, dict) and backtest_results.get('total_signals', 0) > 0:
                stats = {
                    'total_signals': backtest_results.get('total_signals', 0),
                    'win_rate': backtest_results.get('win_rate', '0.0%'),
                    'avg_max_profit': backtest_results.get('avg_max_profit', '0.0%'),
                    'avg_max_drawdown': backtest_results.get('avg_max_drawdown', '0.0%'),
                    'avg_days_to_peak': backtest_results.get('avg_days_to_peak', '0.0 天')
                }
                
                # 添加各状态统计信息
                if 'state_statistics' in backtest_results:
                    stats['state_statistics'] = backtest_results['state_statistics']
                
                # 添加详细交易信息（用于进一步分析）
                if 'trades' in backtest_results:
                    # 计算一些额外的统计指标
                    trades = backtest_results['trades']
                    if trades:
                        # 最佳表现交易
                        best_trade = max(trades, key=lambda x: x['actual_max_pnl'])
                        worst_trade = min(trades, key=lambda x: x['actual_max_pnl'])
                        
                        stats.update({
                            'best_trade_profit': f"{best_trade['actual_max_pnl']:.1%}",
                            'worst_trade_profit': f"{worst_trade['actual_max_pnl']:.1%}",
                            'avg_entry_strategy': self.get_most_common_entry_strategy(trades)
                        })
                
                return stats
            else:
                return {
                    'total_signals': 0,
                    'win_rate': '0.0%',
                    'avg_max_profit': '0.0%',
                    'avg_max_drawdown': '0.0%',
                    'avg_days_to_peak': '0.0 天'
                }
        except Exception as e:
            logger.error(f"回测计算失败: {e}")
            return {
                'total_signals': 0,
                'win_rate': '0.0%',
                'avg_max_profit': '0.0%',
                'avg_max_drawdown': '0.0%',
                'avg_days_to_peak': '0.0 天'
            }
    
    def get_most_common_entry_strategy(self, trades: List[Dict]) -> str:
        """获取最常用的入场策略"""
        try:
            from collections import Counter
            strategies = [trade.get('entry_strategy', '未知') for trade in trades]
            most_common = Counter(strategies).most_common(1)
            return most_common[0][0] if most_common else '未知'
        except:
            return '未知'
    
    def trigger_deep_scan(self, passed_stocks: List[StrategyResult]) -> Optional[Dict[str, Any]]:
        """触发深度扫描"""
        if not passed_stocks:
            logger.info("没有通过筛选的股票，跳过深度扫描")
            return None
        
        logger.info(f"触发深度扫描，处理 {len(passed_stocks)} 只股票")
        
        # 提取股票代码
        stock_codes = [stock.stock_code for stock in passed_stocks]
        
        try:
            # 导入深度扫描模块
            from run_enhanced_screening import analyze_multiple_stocks
            
            # 执行深度扫描
            deep_scan_results = analyze_multiple_stocks(stock_codes, use_optimized_params=True, max_workers=32)
            
            logger.info("深度扫描完成")
            return deep_scan_results
            
        except ImportError:
            logger.warning("深度扫描模块不可用")
            return None
        except Exception as e:
            logger.error(f"深度扫描失败: {e}")
            return None

    def get_available_strategies(self) -> List[Dict[str, Any]]:
        """获取可用策略列表"""
        return self.strategy_manager.get_available_strategies()


def main():
    """主函数"""
    print("🚀 通用股票筛选器")
    print("=" * 50)
    
    # 创建筛选器实例
    screener = UniversalScreener()
    
    # 显示可用策略
    available_strategies = screener.get_available_strategies()
    print(f"📋 可用策略 ({len(available_strategies)} 个):")
    for strategy in available_strategies:
        status = "✅ 启用" if strategy['enabled'] else "❌ 禁用"
        print(f"  - {strategy['name']} v{strategy['version']} {status}")
        print(f"    {strategy['description']}")
    
    print("\n🔍 开始筛选...")
    
    # 运行筛选
    results = screener.run_screening()
    
    # 保存结果
    if results:
        saved_files = screener.save_results(results)
        
        print(f"\n📊 筛选完成！")
        print(f"🎯 发现信号: {len(results)} 个")
        print(f"📄 结果文件:")
        for file_type, file_path in saved_files.items():
            print(f"  - {file_type.upper()}: {file_path}")
    else:
        print("\n📊 筛选完成，未发现符合条件的信号")


if __name__ == '__main__':
    main()
