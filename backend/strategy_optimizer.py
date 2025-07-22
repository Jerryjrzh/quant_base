"""
策略优化器 - 针对TRIPLE_CROSS等策略进行胜率筛选和多策略回测
"""
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import data_loader
import strategies
import backtester
import indicators

class StrategyOptimizer:
    def __init__(self, base_strategy='TRIPLE_CROSS'):
        self.base_strategy = base_strategy
        self.backend_dir = os.path.dirname(os.path.abspath(__file__))
        self.result_path = os.path.abspath(os.path.join(self.backend_dir, '..', 'data', 'result'))
        
        # 胜率筛选阈值
        self.min_win_rate = 40.0  # 最低胜率40%
        self.min_signals = 3      # 最少历史信号数
        self.min_avg_profit = 15.0 # 最低平均收益15%
    
    def load_recent_scan_results(self, days_back=10):
        """加载最近N次扫描的结果"""
        strategy_dir = os.path.join(self.result_path, self.base_strategy)
        if not os.path.exists(strategy_dir):
            return []
        
        # 获取所有signals_summary.json文件
        summary_files = []
        for file in os.listdir(strategy_dir):
            if file.startswith('signals_summary') and file.endswith('.json'):
                file_path = os.path.join(strategy_dir, file)
                summary_files.append(file_path)
        
        # 按修改时间排序，取最近的
        summary_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        all_stocks = []
        for file_path in summary_files[:days_back]:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    stocks = json.load(f)
                    if isinstance(stocks, list):
                        all_stocks.extend(stocks)
            except Exception as e:
                print(f"读取文件 {file_path} 失败: {e}")
        
        return all_stocks
    
    def filter_high_win_rate_stocks(self, stocks):
        """筛选高胜率股票"""
        filtered_stocks = []
        
        for stock in stocks:
            try:
                # 解析胜率
                win_rate_str = stock.get('win_rate', '0.0%').replace('%', '')
                win_rate = float(win_rate_str)
                
                # 解析平均收益
                profit_str = stock.get('avg_max_profit', '0.0%').replace('%', '')
                avg_profit = float(profit_str)
                
                # 历史信号数
                total_signals = stock.get('total_signals', 0)
                
                # 筛选条件
                if (win_rate >= self.min_win_rate and 
                    total_signals >= self.min_signals and 
                    avg_profit >= self.min_avg_profit):
                    
                    stock['filter_score'] = win_rate + avg_profit * 0.5  # 综合评分
                    filtered_stocks.append(stock)
                    
            except Exception as e:
                print(f"筛选股票 {stock.get('stock_code', 'unknown')} 时出错: {e}")
                continue
        
        # 按综合评分排序
        filtered_stocks.sort(key=lambda x: x.get('filter_score', 0), reverse=True)
        
        return filtered_stocks
    
    def analyze_signal_phases(self, stock_code):
        """分析信号阶段的触底情况"""
        try:
            # 获取股票数据
            market = stock_code[:2]
            file_path = os.path.join(
                os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc"),
                market, 'lday', f'{stock_code}.day'
            )
            
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 150:
                return None
            
            # 应用策略获取信号
            if self.base_strategy == 'TRIPLE_CROSS':
                signal_series = strategies.apply_triple_cross(df)
            elif self.base_strategy == 'MACD_ZERO_AXIS':
                signal_series = strategies.apply_macd_zero_axis_strategy(df)
            else:
                return None
            
            if signal_series is None:
                return None
            
            # 分析每个信号的阶段特征
            phase_analysis = []
            signal_indices = df.index[signal_series == True] if signal_series.dtype == bool else df.index[signal_series != '']
            
            for idx in signal_indices:
                try:
                    # 分析信号前后的价格行为
                    pre_period = max(0, idx - 10)  # 信号前10天
                    post_period = min(len(df), idx + 20)  # 信号后20天
                    
                    pre_data = df.iloc[pre_period:idx]
                    post_data = df.iloc[idx:post_period]
                    signal_day = df.iloc[idx]
                    
                    # 计算触底特征
                    if len(pre_data) > 0:
                        # 信号前的最低价位置
                        pre_low_idx = pre_data['low'].idxmin()
                        pre_low_position = (pre_low_idx - pre_period) / len(pre_data)  # 0=最早, 1=信号当天
                        
                        # 判断触底阶段
                        if pre_low_position < 0.3:
                            bottom_phase = 'EARLY'  # 早期触底
                        elif pre_low_position < 0.7:
                            bottom_phase = 'MID'    # 中期触底
                        else:
                            bottom_phase = 'LATE'   # 晚期触底（接近信号）
                    else:
                        bottom_phase = 'UNKNOWN'
                    
                    # 计算信号后的表现
                    if len(post_data) > 1:
                        entry_price = signal_day['close']
                        max_profit = (post_data['high'].max() - entry_price) / entry_price
                        max_drawdown = (post_data['low'].min() - entry_price) / entry_price
                        
                        # 找到最高点的天数
                        max_high_idx = post_data['high'].idxmax()
                        days_to_peak = max_high_idx - idx
                    else:
                        max_profit = 0
                        max_drawdown = 0
                        days_to_peak = 0
                    
                    phase_info = {
                        'signal_date': df.iloc[idx]['date'].strftime('%Y-%m-%d'),
                        'bottom_phase': bottom_phase,
                        'max_profit': f"{max_profit:.1%}",
                        'max_drawdown': f"{max_drawdown:.1%}",
                        'days_to_peak': int(days_to_peak),
                        'is_profitable': max_profit > 0.05  # 5%以上认为盈利
                    }
                    
                    phase_analysis.append(phase_info)
                    
                except Exception as e:
                    print(f"分析信号 {idx} 时出错: {e}")
                    continue
            
            return {
                'stock_code': stock_code,
                'total_signals': len(phase_analysis),
                'phase_breakdown': self._summarize_phases(phase_analysis),
                'detailed_signals': phase_analysis
            }
            
        except Exception as e:
            print(f"分析股票 {stock_code} 的信号阶段时出错: {e}")
            return None
    
    def _summarize_phases(self, phase_analysis):
        """汇总阶段分析结果"""
        if not phase_analysis:
            return {}
        
        phase_stats = {}
        for phase in ['EARLY', 'MID', 'LATE']:
            phase_signals = [s for s in phase_analysis if s['bottom_phase'] == phase]
            if phase_signals:
                profitable_count = sum(1 for s in phase_signals if s['is_profitable'])
                win_rate = profitable_count / len(phase_signals)
                
                # 计算平均收益（去掉百分号）
                profits = []
                for s in phase_signals:
                    try:
                        profit_val = float(s['max_profit'].replace('%', ''))
                        profits.append(profit_val)
                    except:
                        pass
                
                avg_profit = np.mean(profits) if profits else 0
                
                phase_stats[phase] = {
                    'count': len(phase_signals),
                    'win_rate': f"{win_rate:.1%}",
                    'avg_profit': f"{avg_profit:.1%}",
                    'best_phase': win_rate >= 0.5 and avg_profit >= 15.0
                }
        
        return phase_stats
    
    def run_multi_strategy_backtest(self, stock_codes, strategies_to_test=None):
        """对股票列表运行多种策略回测"""
        if strategies_to_test is None:
            strategies_to_test = [
                'TRIPLE_CROSS',
                'PRE_CROSS', 
                'MACD_ZERO_AXIS'
            ]
        
        results = {}
        
        for strategy_name in strategies_to_test:
            print(f"正在回测策略: {strategy_name}")
            strategy_results = []
            
            for stock_code in stock_codes:
                try:
                    # 获取股票数据
                    market = stock_code[:2]
                    file_path = os.path.join(
                        os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc"),
                        market, 'lday', f'{stock_code}.day'
                    )
                    
                    df = data_loader.get_daily_data(file_path)
                    if df is None or len(df) < 150:
                        continue
                    
                    # 应用对应策略
                    signal_series = None
                    if strategy_name == 'TRIPLE_CROSS':
                        signal_series = strategies.apply_triple_cross(df)
                    elif strategy_name == 'PRE_CROSS':
                        signal_series = strategies.apply_pre_cross(df)
                    elif strategy_name == 'MACD_ZERO_AXIS':
                        signal_series = strategies.apply_macd_zero_axis_strategy(df)
                    
                    if signal_series is None:
                        continue
                    
                    # 计算技术指标（回测需要）
                    macd_values = indicators.calculate_macd(df)
                    df['dif'], df['dea'] = macd_values[0], macd_values[1]
                    kdj_values = indicators.calculate_kdj(df)
                    df['k'], df['d'], df['j'] = kdj_values[0], kdj_values[1], kdj_values[2]
                    
                    # 执行回测
                    backtest_results = backtester.run_backtest(df, signal_series)
                    
                    if isinstance(backtest_results, dict) and backtest_results.get('total_signals', 0) > 0:
                        result = {
                            'stock_code': stock_code,
                            'strategy': strategy_name,
                            **backtest_results
                        }
                        strategy_results.append(result)
                        
                except Exception as e:
                    print(f"回测 {stock_code} 使用策略 {strategy_name} 时出错: {e}")
                    continue
            
            results[strategy_name] = strategy_results
        
        return results
    
    def generate_optimization_report(self, filtered_stocks, phase_analysis, multi_strategy_results):
        """生成优化报告"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        
        report = {
            'optimization_summary': {
                'timestamp': timestamp,
                'base_strategy': self.base_strategy,
                'filter_criteria': {
                    'min_win_rate': f"{self.min_win_rate}%",
                    'min_signals': self.min_signals,
                    'min_avg_profit': f"{self.min_avg_profit}%"
                },
                'filtered_stocks_count': len(filtered_stocks),
                'phase_analysis_count': len([p for p in phase_analysis if p is not None])
            },
            'high_quality_stocks': filtered_stocks[:20],  # 前20只高质量股票
            'phase_analysis': [p for p in phase_analysis if p is not None],
            'multi_strategy_comparison': self._compare_strategies(multi_strategy_results),
            'recommendations': self._generate_recommendations(filtered_stocks, phase_analysis, multi_strategy_results)
        }
        
        # 保存报告
        output_dir = os.path.join(self.result_path, f'{self.base_strategy}_OPTIMIZED')
        os.makedirs(output_dir, exist_ok=True)
        
        report_file = os.path.join(output_dir, f'optimization_report_{timestamp}.json')
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=4)
        
        # 生成文本报告
        text_file = os.path.join(output_dir, f'optimization_report_{timestamp}.txt')
        self._write_text_report(report, text_file)
        
        return report, report_file, text_file
    
    def _compare_strategies(self, multi_strategy_results):
        """比较不同策略的表现"""
        comparison = {}
        
        for strategy_name, results in multi_strategy_results.items():
            if not results:
                continue
            
            # 计算策略整体表现
            total_signals = sum(r.get('total_signals', 0) for r in results)
            
            win_rates = []
            profit_rates = []
            
            for r in results:
                if r.get('total_signals', 0) > 0:
                    try:
                        win_rate = float(r.get('win_rate', '0%').replace('%', ''))
                        profit_rate = float(r.get('avg_max_profit', '0%').replace('%', ''))
                        win_rates.append(win_rate)
                        profit_rates.append(profit_rate)
                    except:
                        pass
            
            avg_win_rate = np.mean(win_rates) if win_rates else 0
            avg_profit_rate = np.mean(profit_rates) if profit_rates else 0
            
            comparison[strategy_name] = {
                'stocks_tested': len(results),
                'total_signals': total_signals,
                'avg_win_rate': f"{avg_win_rate:.1f}%",
                'avg_profit_rate': f"{avg_profit_rate:.1f}%",
                'strategy_score': avg_win_rate + avg_profit_rate * 0.5  # 综合评分
            }
        
        return comparison
    
    def _generate_recommendations(self, filtered_stocks, phase_analysis, multi_strategy_results):
        """生成投资建议"""
        recommendations = []
        
        # 1. 最佳股票推荐
        if filtered_stocks:
            top_stock = filtered_stocks[0]
            recommendations.append({
                'type': 'TOP_STOCK',
                'content': f"推荐关注 {top_stock['stock_code']}，胜率 {top_stock.get('win_rate', 'N/A')}，平均收益 {top_stock.get('avg_max_profit', 'N/A')}"
            })
        
        # 2. 最佳触底阶段推荐
        best_phases = {}
        for analysis in phase_analysis:
            if analysis and 'phase_breakdown' in analysis:
                for phase, stats in analysis['phase_breakdown'].items():
                    if stats.get('best_phase', False):
                        if phase not in best_phases:
                            best_phases[phase] = []
                        best_phases[phase].append(analysis['stock_code'])
        
        for phase, stocks in best_phases.items():
            recommendations.append({
                'type': 'BEST_PHASE',
                'content': f"{phase}阶段触底表现最佳，相关股票: {', '.join(stocks[:5])}"
            })
        
        # 3. 最佳策略推荐
        if multi_strategy_results:
            strategy_scores = {}
            for strategy, comparison in self._compare_strategies(multi_strategy_results).items():
                strategy_scores[strategy] = comparison.get('strategy_score', 0)
            
            if strategy_scores:
                best_strategy = max(strategy_scores.keys(), key=lambda k: strategy_scores[k])
                recommendations.append({
                    'type': 'BEST_STRATEGY',
                    'content': f"推荐使用 {best_strategy} 策略，综合评分最高: {strategy_scores[best_strategy]:.1f}"
                })
        
        return recommendations
    
    def _write_text_report(self, report, file_path):
        """写入文本格式报告"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("=== 策略优化报告 ===\n")
            f.write(f"生成时间: {report['optimization_summary']['timestamp']}\n")
            f.write(f"基础策略: {report['optimization_summary']['base_strategy']}\n")
            f.write(f"筛选后股票数: {report['optimization_summary']['filtered_stocks_count']}\n\n")
            
            # 筛选条件
            f.write("=== 筛选条件 ===\n")
            criteria = report['optimization_summary']['filter_criteria']
            f.write(f"最低胜率: {criteria['min_win_rate']}\n")
            f.write(f"最少信号数: {criteria['min_signals']}\n")
            f.write(f"最低平均收益: {criteria['min_avg_profit']}\n\n")
            
            # 高质量股票
            f.write("=== 前20只高质量股票 ===\n")
            for i, stock in enumerate(report['high_quality_stocks'], 1):
                f.write(f"{i:2d}. {stock['stock_code']} - 胜率: {stock.get('win_rate', 'N/A')}, "
                       f"收益: {stock.get('avg_max_profit', 'N/A')}, "
                       f"评分: {stock.get('filter_score', 0):.1f}\n")
            
            # 策略比较
            if 'multi_strategy_comparison' in report:
                f.write("\n=== 多策略比较 ===\n")
                for strategy, stats in report['multi_strategy_comparison'].items():
                    f.write(f"{strategy}: 胜率 {stats['avg_win_rate']}, "
                           f"收益 {stats['avg_profit_rate']}, "
                           f"评分 {stats['strategy_score']:.1f}\n")
            
            # 投资建议
            f.write("\n=== 投资建议 ===\n")
            for i, rec in enumerate(report['recommendations'], 1):
                f.write(f"{i}. {rec['content']}\n")

def main():
    """主函数 - 运行策略优化"""
    print("开始策略优化分析...")
    
    optimizer = StrategyOptimizer('TRIPLE_CROSS')
    
    # 1. 加载最近的扫描结果
    print("加载最近10次扫描结果...")
    recent_stocks = optimizer.load_recent_scan_results(10)
    print(f"加载了 {len(recent_stocks)} 个股票记录")
    
    # 2. 筛选高胜率股票
    print("筛选高胜率股票...")
    filtered_stocks = optimizer.filter_high_win_rate_stocks(recent_stocks)
    print(f"筛选出 {len(filtered_stocks)} 只高质量股票")
    
    # 3. 分析信号阶段
    print("分析信号阶段特征...")
    phase_analysis = []
    for stock in filtered_stocks[:30]:  # 分析前30只
        analysis = optimizer.analyze_signal_phases(stock['stock_code'])
        phase_analysis.append(analysis)
        if analysis:
            print(f"  {stock['stock_code']}: {len(analysis.get('detailed_signals', []))} 个信号")
    
    # 4. 多策略回测
    print("执行多策略回测...")
    stock_codes = [s['stock_code'] for s in filtered_stocks[:20]]  # 回测前20只
    multi_strategy_results = optimizer.run_multi_strategy_backtest(stock_codes)
    
    for strategy, results in multi_strategy_results.items():
        print(f"  {strategy}: {len(results)} 只股票有效")
    
    # 5. 生成报告
    print("生成优化报告...")
    report, json_file, text_file = optimizer.generate_optimization_report(
        filtered_stocks, phase_analysis, multi_strategy_results
    )
    
    print(f"\n优化完成！")
    print(f"JSON报告: {json_file}")
    print(f"文本报告: {text_file}")
    
    # 显示关键结果
    print(f"\n=== 关键发现 ===")
    print(f"高质量股票数: {len(filtered_stocks)}")
    if filtered_stocks:
        top_stock = filtered_stocks[0]
        print(f"最佳股票: {top_stock['stock_code']} (胜率: {top_stock.get('win_rate', 'N/A')})")
    
    if 'multi_strategy_comparison' in report:
        best_strategy = max(
            report['multi_strategy_comparison'].items(),
            key=lambda x: x[1].get('strategy_score', 0)
        )
        print(f"最佳策略: {best_strategy[0]} (评分: {best_strategy[1].get('strategy_score', 0):.1f})")

if __name__ == '__main__':
    main()