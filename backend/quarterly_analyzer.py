#!/usr/bin/env python3
"""
季度回测结果分析器
分析季度回测结果，生成详细的分析报告和可视化图表
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.font_manager import FontProperties

# 可选导入seaborn
try:
    import seaborn as sns
    HAS_SEABORN = True
except ImportError:
    HAS_SEABORN = False

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'Noto Sans CJK SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class QuarterlyAnalyzer:
    """季度回测结果分析器"""
    
    def __init__(self, results_file: str):
        """
        初始化分析器
        
        Args:
            results_file: 回测结果文件路径
        """
        self.results_file = results_file
        self.results = self._load_results()
        
    def _load_results(self) -> Dict:
        """加载回测结果"""
        try:
            with open(self.results_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            raise ValueError(f"无法加载回测结果文件: {e}")
    
    def analyze_strategy_performance(self) -> pd.DataFrame:
        """分析策略表现"""
        strategy_data = []
        
        for strategy_name, perf in self.results['strategy_performance'].items():
            strategy_data.append({
                'strategy': strategy_name,
                'quarters_used': perf['quarters_used'],
                'avg_return': perf['avg_return'],
                'avg_win_rate': perf['avg_win_rate'],
                'total_trades': perf['total_trades'],
                'total_return': perf['total_return']
            })
        
        return pd.DataFrame(strategy_data)
    
    def analyze_quarterly_trends(self) -> pd.DataFrame:
        """分析季度趋势"""
        quarterly_data = []
        
        for quarter_info in self.results['quarterly_analysis']:
            quarterly_data.append({
                'quarter': quarter_info['quarter'],
                'pool_size': quarter_info['pool_size'],
                'best_strategy': quarter_info['best_strategy'],
                'best_return': quarter_info['best_return'],
                'win_rate': quarter_info['win_rate'],
                'total_trades': quarter_info['total_trades']
            })
        
        df = pd.DataFrame(quarterly_data)
        df['quarter_date'] = pd.to_datetime(df['quarter'].str.replace('Q', '-Q'), format='%Y-Q%q')
        return df.sort_values('quarter_date')
    
    def plot_strategy_comparison(self, save_path: str = None):
        """绘制策略对比图"""
        strategy_df = self.analyze_strategy_performance()
        
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # 1. 平均收益率对比
        bars1 = ax1.bar(strategy_df['strategy'], strategy_df['avg_return'] * 100)
        ax1.set_title('策略平均收益率对比', fontsize=14, fontweight='bold')
        ax1.set_ylabel('平均收益率 (%)')
        ax1.tick_params(axis='x', rotation=45)
        
        # 添加数值标签
        for bar in bars1:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom')
        
        # 2. 胜率对比
        bars2 = ax2.bar(strategy_df['strategy'], strategy_df['avg_win_rate'] * 100, color='green', alpha=0.7)
        ax2.set_title('策略平均胜率对比', fontsize=14, fontweight='bold')
        ax2.set_ylabel('平均胜率 (%)')
        ax2.tick_params(axis='x', rotation=45)
        
        for bar in bars2:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom')
        
        # 3. 交易次数对比
        bars3 = ax3.bar(strategy_df['strategy'], strategy_df['total_trades'], color='orange', alpha=0.7)
        ax3.set_title('策略总交易次数对比', fontsize=14, fontweight='bold')
        ax3.set_ylabel('总交易次数')
        ax3.tick_params(axis='x', rotation=45)
        
        for bar in bars3:
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}', ha='center', va='bottom')
        
        # 4. 收益率vs胜率散点图
        ax4.scatter(strategy_df['avg_win_rate'] * 100, strategy_df['avg_return'] * 100, 
                   s=strategy_df['total_trades']/10, alpha=0.7)
        
        for i, strategy in enumerate(strategy_df['strategy']):
            ax4.annotate(strategy, 
                        (strategy_df['avg_win_rate'].iloc[i] * 100, 
                         strategy_df['avg_return'].iloc[i] * 100),
                        xytext=(5, 5), textcoords='offset points', fontsize=9)
        
        ax4.set_xlabel('平均胜率 (%)')
        ax4.set_ylabel('平均收益率 (%)')
        ax4.set_title('收益率 vs 胜率 (气泡大小=交易次数)', fontsize=14, fontweight='bold')
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"策略对比图已保存到: {save_path}")
        
        plt.show()
    
    def plot_quarterly_trends(self, save_path: str = None):
        """绘制季度趋势图"""
        quarterly_df = self.analyze_quarterly_trends()
        
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # 1. 季度收益率趋势
        ax1.plot(quarterly_df['quarter'], quarterly_df['best_return'] * 100, 
                marker='o', linewidth=2, markersize=8)
        ax1.set_title('季度最佳策略收益率趋势', fontsize=14, fontweight='bold')
        ax1.set_ylabel('收益率 (%)')
        ax1.tick_params(axis='x', rotation=45)
        ax1.grid(True, alpha=0.3)
        
        # 添加零线
        ax1.axhline(y=0, color='red', linestyle='--', alpha=0.5)
        
        # 2. 季度胜率趋势
        ax2.plot(quarterly_df['quarter'], quarterly_df['win_rate'] * 100, 
                marker='s', color='green', linewidth=2, markersize=8)
        ax2.set_title('季度胜率趋势', fontsize=14, fontweight='bold')
        ax2.set_ylabel('胜率 (%)')
        ax2.tick_params(axis='x', rotation=45)
        ax2.grid(True, alpha=0.3)
        
        # 3. 股票池大小趋势
        ax3.bar(quarterly_df['quarter'], quarterly_df['pool_size'], alpha=0.7, color='orange')
        ax3.set_title('季度股票池大小趋势', fontsize=14, fontweight='bold')
        ax3.set_ylabel('股票池大小')
        ax3.tick_params(axis='x', rotation=45)
        
        # 4. 最佳策略分布
        strategy_counts = quarterly_df['best_strategy'].value_counts()
        colors = plt.cm.Set3(np.linspace(0, 1, len(strategy_counts)))
        wedges, texts, autotexts = ax4.pie(strategy_counts.values, labels=strategy_counts.index, 
                                          autopct='%1.1f%%', colors=colors)
        ax4.set_title('各季度最佳策略分布', fontsize=14, fontweight='bold')
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"季度趋势图已保存到: {save_path}")
        
        plt.show()
    
    def plot_detailed_analysis(self, save_path: str = None):
        """绘制详细分析图"""
        # 提取详细交易数据
        all_trades = []
        for quarter_result in self.results['detailed_results']:
            quarter = quarter_result['quarter']
            for strategy_name, strategy_result in quarter_result['strategy_results'].items():
                for trade in strategy_result.get('trades', []):
                    trade_info = trade.copy()
                    trade_info['quarter'] = quarter
                    trade_info['strategy'] = strategy_name
                    all_trades.append(trade_info)
        
        if not all_trades:
            print("没有详细交易数据可供分析")
            return
        
        trades_df = pd.DataFrame(all_trades)
        
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))
        
        # 1. 收益率分布直方图
        ax1.hist(trades_df['final_return'] * 100, bins=30, alpha=0.7, edgecolor='black')
        ax1.set_title('交易收益率分布', fontsize=14, fontweight='bold')
        ax1.set_xlabel('收益率 (%)')
        ax1.set_ylabel('交易次数')
        ax1.axvline(x=0, color='red', linestyle='--', alpha=0.7, label='盈亏平衡线')
        ax1.axvline(x=trades_df['final_return'].mean() * 100, color='green', 
                   linestyle='-', alpha=0.7, label=f'平均收益率: {trades_df["final_return"].mean()*100:.1f}%')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 2. 持有天数vs收益率散点图
        colors = ['red' if x < 0 else 'green' for x in trades_df['final_return']]
        ax2.scatter(trades_df['hold_days'], trades_df['final_return'] * 100, 
                   c=colors, alpha=0.6)
        ax2.set_title('持有天数 vs 收益率', fontsize=14, fontweight='bold')
        ax2.set_xlabel('持有天数')
        ax2.set_ylabel('收益率 (%)')
        ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax2.grid(True, alpha=0.3)
        
        # 3. 各策略收益率箱线图
        strategy_returns = []
        strategy_names = []
        for strategy in trades_df['strategy'].unique():
            strategy_data = trades_df[trades_df['strategy'] == strategy]['final_return'] * 100
            if len(strategy_data) > 0:
                strategy_returns.append(strategy_data.values)
                strategy_names.append(strategy)
        
        if strategy_returns:
            ax3.boxplot(strategy_returns, labels=strategy_names)
            ax3.set_title('各策略收益率分布', fontsize=14, fontweight='bold')
            ax3.set_ylabel('收益率 (%)')
            ax3.tick_params(axis='x', rotation=45)
            ax3.axhline(y=0, color='red', linestyle='--', alpha=0.5)
            ax3.grid(True, alpha=0.3)
        
        # 4. 成功率vs最大收益率
        success_analysis = trades_df.groupby('strategy').agg({
            'success': 'mean',
            'max_return': 'mean',
            'final_return': 'count'
        }).reset_index()
        success_analysis.columns = ['strategy', 'success_rate', 'avg_max_return', 'trade_count']
        
        ax4.scatter(success_analysis['success_rate'] * 100, 
                   success_analysis['avg_max_return'] * 100,
                   s=success_analysis['trade_count']/2, alpha=0.7)
        
        for i, strategy in enumerate(success_analysis['strategy']):
            ax4.annotate(strategy, 
                        (success_analysis['success_rate'].iloc[i] * 100, 
                         success_analysis['avg_max_return'].iloc[i] * 100),
                        xytext=(5, 5), textcoords='offset points', fontsize=9)
        
        ax4.set_xlabel('成功率 (%)')
        ax4.set_ylabel('平均最大收益率 (%)')
        ax4.set_title('成功率 vs 平均最大收益率', fontsize=14, fontweight='bold')
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"详细分析图已保存到: {save_path}")
        
        plt.show()
    
    def generate_text_report(self) -> str:
        """生成文本分析报告"""
        report = []
        report.append("=" * 60)
        report.append("季度回测分析报告")
        report.append("=" * 60)
        
        # 基本信息
        summary = self.results['summary']
        report.append(f"\n📊 基本信息:")
        report.append(f"  • 回测季度数: {summary['total_quarters']}")
        report.append(f"  • 最佳整体策略: {summary['best_overall_strategy']}")
        report.append(f"  • 平均季度收益率: {summary['avg_quarterly_return']:.2%}")
        report.append(f"  • 平均胜率: {summary['avg_win_rate']:.1%}")
        report.append(f"  • 总交易次数: {summary['total_trades']}")
        
        # 策略表现分析
        report.append(f"\n🎯 策略表现分析:")
        strategy_df = self.analyze_strategy_performance()
        strategy_df_sorted = strategy_df.sort_values('avg_return', ascending=False)
        
        for _, row in strategy_df_sorted.iterrows():
            report.append(f"  • {row['strategy']}:")
            report.append(f"    - 平均收益率: {row['avg_return']:.2%}")
            report.append(f"    - 平均胜率: {row['avg_win_rate']:.1%}")
            report.append(f"    - 使用季度数: {row['quarters_used']}")
            report.append(f"    - 总交易次数: {row['total_trades']}")
        
        # 季度趋势分析
        report.append(f"\n📈 季度趋势分析:")
        quarterly_df = self.analyze_quarterly_trends()
        
        best_quarter = quarterly_df.loc[quarterly_df['best_return'].idxmax()]
        worst_quarter = quarterly_df.loc[quarterly_df['best_return'].idxmin()]
        
        report.append(f"  • 最佳季度: {best_quarter['quarter']} (收益率: {best_quarter['best_return']:.2%})")
        report.append(f"  • 最差季度: {worst_quarter['quarter']} (收益率: {worst_quarter['best_return']:.2%})")
        report.append(f"  • 平均股票池大小: {quarterly_df['pool_size'].mean():.1f}")
        report.append(f"  • 股票池大小范围: {quarterly_df['pool_size'].min()} - {quarterly_df['pool_size'].max()}")
        
        # 优化建议
        report.append(f"\n💡 优化建议:")
        for i, suggestion in enumerate(self.results['optimization_suggestions'], 1):
            priority_icon = "🔴" if suggestion['priority'] == 'high' else "🟡"
            report.append(f"  {i}. {priority_icon} {suggestion['suggestion']}")
        
        # 详细季度表现
        report.append(f"\n📋 详细季度表现:")
        for _, row in quarterly_df.iterrows():
            report.append(f"  • {row['quarter']}:")
            report.append(f"    - 股票池大小: {row['pool_size']}")
            report.append(f"    - 最佳策略: {row['best_strategy']}")
            report.append(f"    - 收益率: {row['best_return']:.2%}")
            report.append(f"    - 胜率: {row['win_rate']:.1%}")
            report.append(f"    - 交易次数: {row['total_trades']}")
        
        return "\n".join(report)
    
    def save_analysis_report(self, filename: str = None):
        """保存分析报告"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'quarterly_analysis_report_{timestamp}.txt'
        
        report = self.generate_text_report()
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"分析报告已保存到: {filename}")
        return filename
    
    def generate_all_charts(self, output_dir: str = "charts"):
        """生成所有图表"""
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 生成各种图表
        self.plot_strategy_comparison(
            os.path.join(output_dir, f'strategy_comparison_{timestamp}.png')
        )
        
        self.plot_quarterly_trends(
            os.path.join(output_dir, f'quarterly_trends_{timestamp}.png')
        )
        
        self.plot_detailed_analysis(
            os.path.join(output_dir, f'detailed_analysis_{timestamp}.png')
        )
        
        print(f"所有图表已保存到目录: {output_dir}")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='季度回测结果分析器')
    parser.add_argument('results_file', help='回测结果JSON文件路径')
    parser.add_argument('--charts', action='store_true', help='生成图表')
    parser.add_argument('--report', action='store_true', help='生成文本报告')
    parser.add_argument('--output-dir', default='charts', help='图表输出目录')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.results_file):
        print(f"错误: 结果文件 {args.results_file} 不存在")
        return
    
    try:
        analyzer = QuarterlyAnalyzer(args.results_file)
        
        # 显示基本信息
        print("季度回测结果分析")
        print("=" * 50)
        print(f"结果文件: {args.results_file}")
        print(f"总季度数: {analyzer.results['summary']['total_quarters']}")
        print(f"最佳策略: {analyzer.results['summary']['best_overall_strategy']}")
        print(f"平均收益率: {analyzer.results['summary']['avg_quarterly_return']:.2%}")
        
        if args.charts:
            print("\n生成图表中...")
            analyzer.generate_all_charts(args.output_dir)
        
        if args.report:
            print("\n生成文本报告中...")
            report_file = analyzer.save_analysis_report()
            print(f"报告已保存: {report_file}")
        
        if not args.charts and not args.report:
            # 默认显示文本报告
            print("\n" + analyzer.generate_text_report())
        
    except Exception as e:
        print(f"分析失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()