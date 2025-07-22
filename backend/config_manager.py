"""
配置管理工具 - 用于调试和验证策略参数
提供命令行界面和API接口来管理策略配置
"""
import json
import os
import argparse
from typing import Dict, Any, List, Optional
from datetime import datetime
import pandas as pd

from strategy_config import (
    config_manager, config_debugger, 
    get_strategy_config, update_strategy_config,
    validate_strategy_config, list_available_strategies
)
import data_loader
import strategies
import backtester

class ConfigTester:
    """配置测试器 - 用于验证配置参数的效果"""
    
    def __init__(self):
        self.base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        self.test_stocks = [
            'sh600036',  # 招商银行
            'sz000002',  # 万科A
            'sz000858',  # 五粮液
            'sh600519',  # 贵州茅台
            'sz002415'   # 海康威视
        ]
    
    def test_config_on_stocks(self, strategy_name: str, config_updates: Dict[str, Any] = None) -> Dict[str, Any]:
        """在测试股票上验证配置效果"""
        print(f"\n=== 测试 {strategy_name} 策略配置 ===")
        
        # 备份原配置
        original_config = config_manager.get_config(strategy_name)
        
        # 应用新配置
        if config_updates:
            print(f"应用配置更新: {config_updates}")
            config_manager.update_config(strategy_name, config_updates)
        
        results = {}
        strategy_func = strategies.get_strategy_function(strategy_name)
        
        if not strategy_func:
            print(f"未找到策略函数: {strategy_name}")
            return results
        
        for stock_code in self.test_stocks:
            try:
                print(f"测试股票: {stock_code}")
                
                # 加载数据
                df = self._load_stock_data(stock_code)
                if df is None:
                    continue
                
                # 应用策略
                signal_series = strategy_func(df)
                if signal_series is None:
                    continue
                
                # 执行回测
                backtest_result = backtester.run_backtest(df, signal_series)
                
                if isinstance(backtest_result, dict) and backtest_result.get('total_signals', 0) > 0:
                    results[stock_code] = {
                        'total_signals': backtest_result.get('total_signals', 0),
                        'win_rate': backtest_result.get('win_rate', '0%'),
                        'avg_profit': backtest_result.get('avg_max_profit', '0%'),
                        'avg_days': backtest_result.get('avg_days_to_peak', '0 天')
                    }
                    print(f"  信号数: {results[stock_code]['total_signals']}, "
                          f"胜率: {results[stock_code]['win_rate']}, "
                          f"收益: {results[stock_code]['avg_profit']}")
                else:
                    print(f"  无有效信号")
                    
            except Exception as e:
                print(f"  测试失败: {e}")
        
        # 恢复原配置
        if config_updates and original_config:
            config_manager.configs[strategy_name] = original_config
            config_manager.save_configs()
        
        return results
    
    def _load_stock_data(self, stock_code: str) -> Optional[pd.DataFrame]:
        """加载股票数据"""
        try:
            if stock_code.startswith('sh'):
                market = 'sh'
            elif stock_code.startswith('sz'):
                market = 'sz'
            else:
                return None
            
            file_path = os.path.join(self.base_path, market, 'lday', f'{stock_code}.day')
            return data_loader.get_daily_data(file_path)
        except Exception as e:
            print(f"加载{stock_code}数据失败: {e}")
            return None
    
    def compare_configs(self, strategy_name: str, config_variants: List[Dict[str, Any]]) -> Dict[str, Any]:
        """比较不同配置的效果"""
        print(f"\n=== 比较 {strategy_name} 不同配置效果 ===")
        
        comparison_results = {}
        
        for i, config_variant in enumerate(config_variants):
            variant_name = f"配置{i+1}"
            print(f"\n测试 {variant_name}: {config_variant}")
            
            results = self.test_config_on_stocks(strategy_name, config_variant)
            comparison_results[variant_name] = {
                'config': config_variant,
                'results': results,
                'summary': self._summarize_results(results)
            }
        
        # 生成对比报告
        self._print_comparison_report(comparison_results)
        
        return comparison_results
    
    def _summarize_results(self, results: Dict[str, Any]) -> Dict[str, float]:
        """汇总测试结果"""
        if not results:
            return {'avg_win_rate': 0, 'avg_profit': 0, 'total_signals': 0}
        
        win_rates = []
        profits = []
        total_signals = 0
        
        for stock_result in results.values():
            try:
                win_rate = float(stock_result['win_rate'].replace('%', ''))
                profit = float(stock_result['avg_profit'].replace('%', ''))
                win_rates.append(win_rate)
                profits.append(profit)
                total_signals += stock_result['total_signals']
            except:
                continue
        
        return {
            'avg_win_rate': sum(win_rates) / len(win_rates) if win_rates else 0,
            'avg_profit': sum(profits) / len(profits) if profits else 0,
            'total_signals': total_signals
        }
    
    def _print_comparison_report(self, comparison_results: Dict[str, Any]):
        """打印对比报告"""
        print(f"\n=== 配置对比报告 ===")
        print(f"{'配置':<10} {'平均胜率':<10} {'平均收益':<10} {'总信号数':<10}")
        print("-" * 50)
        
        for variant_name, data in comparison_results.items():
            summary = data['summary']
            print(f"{variant_name:<10} {summary['avg_win_rate']:<9.1f}% "
                  f"{summary['avg_profit']:<9.1f}% {summary['total_signals']:<10}")

class ConfigOptimizer:
    """配置优化器 - 自动寻找最佳参数组合"""
    
    def __init__(self):
        self.tester = ConfigTester()
    
    def optimize_macd_params(self, strategy_name: str) -> Dict[str, Any]:
        """优化MACD参数"""
        print(f"\n=== 优化 {strategy_name} 的MACD参数 ===")
        
        # 定义参数搜索空间
        fast_periods = [8, 10, 12, 14]
        slow_periods = [20, 24, 26, 30]
        signal_periods = [6, 8, 9, 12]
        
        best_config = None
        best_score = 0
        
        total_combinations = len(fast_periods) * len(slow_periods) * len(signal_periods)
        current_combination = 0
        
        for fast in fast_periods:
            for slow in slow_periods:
                if fast >= slow:  # 快线必须小于慢线
                    continue
                    
                for signal in signal_periods:
                    current_combination += 1
                    print(f"测试组合 {current_combination}/{total_combinations}: "
                          f"MACD({fast},{slow},{signal})")
                    
                    config_update = {
                        'macd': {
                            'fast_period': fast,
                            'slow_period': slow,
                            'signal_period': signal
                        }
                    }
                    
                    results = self.tester.test_config_on_stocks(strategy_name, config_update)
                    summary = self.tester._summarize_results(results)
                    
                    # 综合评分：胜率权重60%，收益权重40%
                    score = summary['avg_win_rate'] * 0.6 + summary['avg_profit'] * 0.4
                    
                    if score > best_score:
                        best_score = score
                        best_config = config_update.copy()
                        print(f"  ★ 新的最佳配置！评分: {score:.2f}")
                    else:
                        print(f"  评分: {score:.2f}")
        
        print(f"\n=== MACD参数优化结果 ===")
        print(f"最佳配置: {best_config}")
        print(f"最佳评分: {best_score:.2f}")
        
        return best_config
    
    def optimize_kdj_params(self, strategy_name: str) -> Dict[str, Any]:
        """优化KDJ参数"""
        print(f"\n=== 优化 {strategy_name} 的KDJ参数 ===")
        
        # 定义参数搜索空间
        n_periods = [7, 9, 14, 21, 27]
        k_periods = [1, 3, 5]
        d_periods = [1, 3, 5]
        
        best_config = None
        best_score = 0
        
        for n in n_periods:
            for k in k_periods:
                for d in d_periods:
                    print(f"测试KDJ({n},{k},{d})")
                    
                    config_update = {
                        'kdj': {
                            'n_period': n,
                            'k_period': k,
                            'd_period': d
                        }
                    }
                    
                    results = self.tester.test_config_on_stocks(strategy_name, config_update)
                    summary = self.tester._summarize_results(results)
                    
                    score = summary['avg_win_rate'] * 0.6 + summary['avg_profit'] * 0.4
                    
                    if score > best_score:
                        best_score = score
                        best_config = config_update.copy()
                        print(f"  ★ 新的最佳配置！评分: {score:.2f}")
                    else:
                        print(f"  评分: {score:.2f}")
        
        print(f"\n=== KDJ参数优化结果 ===")
        print(f"最佳配置: {best_config}")
        print(f"最佳评分: {best_score:.2f}")
        
        return best_config

def create_config_cli():
    """创建命令行界面"""
    parser = argparse.ArgumentParser(description='策略配置管理工具')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 显示配置
    show_parser = subparsers.add_parser('show', help='显示策略配置')
    show_parser.add_argument('strategy', help='策略名称')
    
    # 更新配置
    update_parser = subparsers.add_parser('update', help='更新策略配置')
    update_parser.add_argument('strategy', help='策略名称')
    update_parser.add_argument('--config', help='配置JSON字符串')
    update_parser.add_argument('--file', help='配置文件路径')
    
    # 验证配置
    validate_parser = subparsers.add_parser('validate', help='验证策略配置')
    validate_parser.add_argument('strategy', help='策略名称')
    
    # 测试配置
    test_parser = subparsers.add_parser('test', help='测试策略配置')
    test_parser.add_argument('strategy', help='策略名称')
    test_parser.add_argument('--config', help='测试配置JSON字符串')
    
    # 比较配置
    compare_parser = subparsers.add_parser('compare', help='比较不同配置')
    compare_parser.add_argument('strategy1', help='策略1名称')
    compare_parser.add_argument('strategy2', help='策略2名称')
    
    # 优化参数
    optimize_parser = subparsers.add_parser('optimize', help='优化策略参数')
    optimize_parser.add_argument('strategy', help='策略名称')
    optimize_parser.add_argument('--indicator', choices=['macd', 'kdj', 'rsi'], help='要优化的指标')
    
    # 列出策略
    subparsers.add_parser('list', help='列出所有可用策略')
    
    # 重置配置
    reset_parser = subparsers.add_parser('reset', help='重置策略配置为默认值')
    reset_parser.add_argument('strategy', help='策略名称')
    
    return parser

def main():
    """主函数"""
    parser = create_config_cli()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'show':
            config_debugger.print_config(args.strategy)
            
        elif args.command == 'update':
            if args.config:
                config_updates = json.loads(args.config)
                update_strategy_config(args.strategy, config_updates)
                print(f"已更新 {args.strategy} 配置")
            elif args.file:
                config_manager.import_config(args.strategy, args.file)
                print(f"已从文件导入 {args.strategy} 配置")
            else:
                print("请提供 --config 或 --file 参数")
                
        elif args.command == 'validate':
            is_valid, errors = validate_strategy_config(args.strategy)
            if is_valid:
                print(f"✅ {args.strategy} 配置有效")
            else:
                print(f"❌ {args.strategy} 配置无效:")
                for error in errors:
                    print(f"  - {error}")
                    
        elif args.command == 'test':
            tester = ConfigTester()
            config_updates = json.loads(args.config) if args.config else None
            results = tester.test_config_on_stocks(args.strategy, config_updates)
            
            if results:
                summary = tester._summarize_results(results)
                print(f"\n测试结果汇总:")
                print(f"平均胜率: {summary['avg_win_rate']:.1f}%")
                print(f"平均收益: {summary['avg_profit']:.1f}%")
                print(f"总信号数: {summary['total_signals']}")
            else:
                print("测试未产生有效结果")
                
        elif args.command == 'compare':
            config_debugger.compare_configs(args.strategy1, args.strategy2)
            
        elif args.command == 'optimize':
            optimizer = ConfigOptimizer()
            if args.indicator == 'macd':
                best_config = optimizer.optimize_macd_params(args.strategy)
            elif args.indicator == 'kdj':
                best_config = optimizer.optimize_kdj_params(args.strategy)
            else:
                print("请指定要优化的指标: --indicator macd|kdj|rsi")
                return
            
            if best_config:
                print(f"\n是否应用最佳配置到 {args.strategy}? (y/n): ", end='')
                if input().lower() == 'y':
                    update_strategy_config(args.strategy, best_config)
                    print("配置已应用")
                    
        elif args.command == 'list':
            strategy_list = list_available_strategies()
            print("可用策略:")
            for strategy in strategy_list:
                description = strategies.get_strategy_description(strategy)
                print(f"  - {strategy}: {description}")
                
        elif args.command == 'reset':
            backup = config_manager.reset_to_default(args.strategy)
            if backup:
                print(f"已重置 {args.strategy} 配置为默认值")
                print("原配置已备份")
            else:
                print(f"策略 {args.strategy} 不存在")
                
    except Exception as e:
        print(f"执行命令时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()