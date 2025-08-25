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
                    if latest_signal in ['POTENTIAL_BUY', 'BUY', 'STRONG_BUY']:
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
            
            except Exception as e:
                # 在工作进程中记录错误但不中断处理
                continue
        
        return results
        
    except Exception as e:
        return []


# 【注意】read_day_file_worker 函数已删除，因为不再被使用


class UniversalScreener:
    """通用股票筛选器"""
    
    def __init__(self, config_file: str = None):
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
    
    def run_screening(self, selected_strategies: List[str] = None) -> List[StrategyResult]:
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
            
            end_time = datetime.now()
            processing_time = (end_time - start_time).total_seconds()
            
            logger.info(f"筛选完成，发现 {len(all_results)} 个信号，耗时 {processing_time:.2f} 秒")
            
            self.results = all_results
            return all_results
            
        finally:
            # 恢复原始策略启用状态
            if selected_strategies:
                # 禁用所有策略
                for strategy_id in self.strategy_manager.registered_strategies.keys():
                    self.strategy_manager.disable_strategy(strategy_id)
                # 重新启用原始策略
                for strategy_id in original_enabled:
                    self.strategy_manager.enable_strategy(strategy_id)
    
    def save_results(self, results: List[StrategyResult], output_dir: str = None) -> Dict[str, str]:
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
                    'enabled_strategies': self.strategy_manager.get_enabled_strategies()
                },
                'results': []
            }
        
        # 按策略分组统计
        strategy_stats = {}
        signal_type_stats = {}
        
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
        
        summary = {
            'scan_summary': {
                'total_signals': len(results),
                'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'enabled_strategies': self.strategy_manager.get_enabled_strategies(),
                'strategy_distribution': strategy_stats,
                'signal_type_distribution': signal_type_stats
            },
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
                            if hasattr(result.signal_details, 'get'):
                                stage_passed = result.signal_details.get('stage_passed', 0)
                                f.write(f"    阶段: {stage_passed}/4\n")
                            
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
