#!/usr/bin/env python3
"""
精确季度策略分析器
分析精确季度回测结果，生成详细的操作建议
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import matplotlib.pyplot as plt
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'Noto Sans CJK SC', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

class PreciseStrategyAnalyzer:
    """精确策略分析器"""
    
    def __init__(self, result_files: List[str]):
        """
        初始化分析器
        
        Args:
            result_files: 结果文件路径列表
        """
        self.result_files = result_files
        self.results = self._load_results()
    
    def _load_results(self) -> List[Dict]:
        """加载所有结果文件"""
        results = []
        for file_path in self.result_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    result = json.load(f)
                    results.append(result)
            except Exception as e:
                print(f"加载文件失败 {file_path}: {e}")
        return results
    
    def generate_operation_guide(self) -> str:
        """生成操作指南"""
        guide = []
        guide.append("=" * 80)
        guide.append("📋 精确季度操作策略指南")
        guide.append("=" * 80)
        
        for result in self.results:
            config = result['config']
            strategy = result['strategy']
            
            guide.append(f"\n🗓️ {config['current_quarter']} 季度策略")
            guide.append("-" * 60)
            
            # 时间窗口
            guide.append(f"📅 关键时间节点:")
            guide.append(f"  • 季度开始: {config['quarter_start']}")
            guide.append(f"  • 选股截止: {config['selection_end']} (第三周结束)")
            guide.append(f"  • 回测开始: {config['backtest_start']}")
            guide.append(f"  • 回测结束: {config['backtest_end']}")
            
            # 选股条件
            guide.append(f"\n🎯 选股条件:")
            guide.append(f"  • 周线金叉确认: {'是' if config['require_weekly_golden_cross'] else '否'}")
            guide.append(f"  • 单日最小涨幅: {config['min_daily_gain']:.0%}")
            guide.append(f"  • 价格范围: ¥{config['min_price']:.1f} - ¥{config['max_price']:.1f}")
            guide.append(f"  • 最小成交量: {config['min_volume']:,}")
            
            # 核心股票池
            core_pool = strategy['core_pool']
            guide.append(f"\n🏆 核心股票池 ({len(core_pool)} 只):")
            
            if core_pool:
                # 按最大涨幅排序显示
                sorted_pool = sorted(core_pool, key=lambda x: x['max_gain'], reverse=True)
                for i, stock in enumerate(sorted_pool, 1):
                    guide.append(f"  {i}. {stock['symbol']} ⭐强势度: {stock['max_gain']:.1%}")
                    guide.append(f"     选入价格: ¥{stock['selection_price']:.2f}")
                    guide.append(f"     最大涨幅: {stock['max_gain']:.1%} ({stock['max_gain_date']})")
                    guide.append(f"     周线状态: {'✓金叉' if stock['weekly_cross_confirmed'] else '✗'}")
            else:
                guide.append("  暂无符合条件的股票")
            
            # 深度回测结果 - 按收益率排序
            trades = strategy['recommended_trades']
            guide.append(f"\n🚀 深度回测结果 ({len(trades)} 种策略组合，按收益率排序):")
            
            if trades:
                # 按收益率排序（已在回测中排序）
                for i, trade in enumerate(trades[:10], 1):  # 只显示前10个最佳结果
                    profit_icon = "🟢" if trade['return_rate'] > 0 else "🔴"
                    guide.append(f"  {i:2d}. {profit_icon} {trade['symbol']} - {trade['strategy']}")
                    guide.append(f"      💰 收益率: {trade['return_rate']:.2%}")
                    guide.append(f"      📅 买入: {trade['entry_date']} ¥{trade['entry_price']:.2f}")
                    guide.append(f"      📅 卖出: {trade['exit_date']} ¥{trade['exit_price']:.2f}")
                    guide.append(f"      ⏱️  持有: {trade['hold_days']} 天")
                    guide.append("")
                
                if len(trades) > 10:
                    guide.append(f"  ... 还有 {len(trades) - 10} 个策略组合")
            else:
                guide.append("  暂无交易建议")
            
            # 最佳操作策略推荐
            if trades:
                best_trade = trades[0]  # 收益率最高的策略
                guide.append(f"\n⭐ 最佳操作策略推荐:")
                guide.append(f"  🎯 推荐股票: {best_trade['symbol']}")
                guide.append(f"  📈 推荐策略: {best_trade['strategy']}")
                guide.append(f"  💎 预期收益: {best_trade['return_rate']:.2%}")
                guide.append(f"  📊 操作详情:")
                guide.append(f"    • 买入时机: {best_trade['entry_date']}")
                guide.append(f"    • 买入价格: ¥{best_trade['entry_price']:.2f}")
                guide.append(f"    • 卖出时机: {best_trade['exit_date']}")
                guide.append(f"    • 卖出价格: ¥{best_trade['exit_price']:.2f}")
                guide.append(f"    • 持有周期: {best_trade['hold_days']} 天")
                
                # 策略分析
                guide.append(f"\n📋 策略分析:")
                if "买入持有" in best_trade['strategy']:
                    guide.append(f"  • 策略类型: 长期持有策略")
                    guide.append(f"  • 适合投资者: 风险承受能力较强，看好长期趋势")
                    guide.append(f"  • 操作难度: ⭐⭐ (简单)")
                elif "高点止盈" in best_trade['strategy']:
                    guide.append(f"  • 策略类型: 目标收益策略")
                    guide.append(f"  • 适合投资者: 追求稳定收益，及时止盈")
                    guide.append(f"  • 操作难度: ⭐⭐⭐ (中等)")
                elif "移动止损" in best_trade['strategy']:
                    guide.append(f"  • 策略类型: 趋势跟踪策略")
                    guide.append(f"  • 适合投资者: 注重风险控制，灵活操作")
                    guide.append(f"  • 操作难度: ⭐⭐⭐⭐ (较难)")
                elif "波段操作" in best_trade['strategy']:
                    guide.append(f"  • 策略类型: 短线波段策略")
                    guide.append(f"  • 适合投资者: 经验丰富，时间充裕")
                    guide.append(f"  • 操作难度: ⭐⭐⭐⭐⭐ (困难)")
                elif "RSI" in best_trade['strategy']:
                    guide.append(f"  • 策略类型: 技术指标策略")
                    guide.append(f"  • 适合投资者: 熟悉技术分析，理性操作")
                    guide.append(f"  • 操作难度: ⭐⭐⭐⭐ (较难)")
            
            # 策略表现统计
            summary = strategy['strategy_summary']
            guide.append(f"\n📊 整体策略表现:")
            guide.append(f"  • 核心池股票: {summary['total_stocks']} 只")
            guide.append(f"  • 策略组合数: {summary['traded_stocks']} 个")
            guide.append(f"  • 平均收益率: {summary['avg_return']:.2%}")
            guide.append(f"  • 盈利策略比例: {summary['win_rate']:.1%}")
            guide.append(f"  • 总体收益率: {summary['total_return']:.2%}")
            
            if summary['best_trade']:
                guide.append(f"  • 最佳表现: {summary['best_trade']['symbol']} ({summary['best_trade']['return']:.2%})")
            if summary['worst_trade']:
                guide.append(f"  • 最差表现: {summary['worst_trade']['symbol']} ({summary['worst_trade']['return']:.2%})")
            
            # 风险提示
            guide.append(f"\n⚠️ 风险控制建议:")
            guide.append(f"  • 单股最大仓位: {config['max_position_size']:.0%}")
            guide.append(f"  • 交易手续费: {config['commission_rate']:.1%}")
            guide.append(f"  • 建议止损位: -8% 到 -10%")
            guide.append(f"  • 建议止盈位: +15% 到 +25%")
            guide.append(f"  • 回测基于历史数据，实际交易需考虑市场变化")
            guide.append(f"  • 建议分批建仓，控制整体风险")
        
        # 综合建议
        guide.append(f"\n" + "=" * 80)
        guide.append(f"🎯 综合操作建议")
        guide.append("=" * 80)
        
        # 分析所有季度的表现
        all_returns = []
        all_win_rates = []
        total_trades = 0
        
        for result in self.results:
            summary = result['strategy']['strategy_summary']
            if summary['traded_stocks'] > 0:
                all_returns.append(summary['avg_return'])
                all_win_rates.append(summary['win_rate'])
                total_trades += summary['traded_stocks']
        
        if all_returns:
            avg_return = np.mean(all_returns)
            avg_win_rate = np.mean(all_win_rates)
            
            guide.append(f"📈 历史表现统计:")
            guide.append(f"  • 平均季度收益率: {avg_return:.2%}")
            guide.append(f"  • 平均胜率: {avg_win_rate:.1%}")
            guide.append(f"  • 总交易次数: {total_trades}")
            
            guide.append(f"\n💰 资金管理建议:")
            guide.append(f"  • 建议单股仓位: 10-20%")
            guide.append(f"  • 建议总仓位: 不超过80%")
            guide.append(f"  • 止损设置: -8% 到 -10%")
            guide.append(f"  • 止盈设置: +15% 到 +25%")
            
            guide.append(f"\n⏰ 操作时机建议:")
            guide.append(f"  • 选股时机: 季度第三周结束前完成筛选")
            guide.append(f"  • 买入时机: 季度第四周开始，选择回调机会")
            guide.append(f"  • 卖出时机: 根据技术指标和基本面变化")
            guide.append(f"  • 复盘时机: 每季度结束后进行策略复盘")
        
        guide.append(f"\n🔄 下季度准备:")
        guide.append(f"  1. 关注市场整体趋势变化")
        guide.append(f"  2. 调整选股条件和参数")
        guide.append(f"  3. 优化买卖时机判断")
        guide.append(f"  4. 完善风险控制措施")
        
        return "\n".join(guide)
    
    def generate_comparison_analysis(self) -> str:
        """生成对比分析"""
        if len(self.results) < 2:
            return "需要至少2个季度的数据进行对比分析"
        
        analysis = []
        analysis.append("=" * 80)
        analysis.append("📊 季度对比分析")
        analysis.append("=" * 80)
        
        # 创建对比表格
        quarters = []
        stock_counts = []
        trade_counts = []
        avg_returns = []
        win_rates = []
        
        for result in self.results:
            config = result['config']
            strategy = result['strategy']
            summary = strategy['strategy_summary']
            
            quarters.append(config['current_quarter'])
            stock_counts.append(summary['total_stocks'])
            trade_counts.append(summary['traded_stocks'])
            avg_returns.append(summary['avg_return'])
            win_rates.append(summary['win_rate'])
        
        # 生成对比表格
        analysis.append(f"\n📋 季度表现对比:")
        analysis.append("-" * 80)
        analysis.append(f"{'季度':<10} {'选股数':<8} {'交易数':<8} {'平均收益率':<12} {'胜率':<8}")
        analysis.append("-" * 80)
        
        for i in range(len(quarters)):
            analysis.append(f"{quarters[i]:<10} {stock_counts[i]:<8} {trade_counts[i]:<8} "
                          f"{avg_returns[i]:<12.2%} {win_rates[i]:<8.1%}")
        
        # 趋势分析
        analysis.append(f"\n📈 趋势分析:")
        analysis.append("-" * 40)
        
        if len(avg_returns) >= 2:
            return_trend = "上升" if avg_returns[-1] > avg_returns[-2] else "下降"
            win_rate_trend = "上升" if win_rates[-1] > win_rates[-2] else "下降"
            
            analysis.append(f"收益率趋势: {return_trend}")
            analysis.append(f"胜率趋势: {win_rate_trend}")
        
        # 最佳季度
        if avg_returns:
            best_quarter_idx = np.argmax(avg_returns)
            worst_quarter_idx = np.argmin(avg_returns)
            
            analysis.append(f"\n🏆 最佳季度: {quarters[best_quarter_idx]} (收益率: {avg_returns[best_quarter_idx]:.2%})")
            analysis.append(f"📉 最差季度: {quarters[worst_quarter_idx]} (收益率: {avg_returns[worst_quarter_idx]:.2%})")
        
        return "\n".join(analysis)
    
    def plot_performance_chart(self, save_path: str = None):
        """绘制表现图表"""
        if len(self.results) < 2:
            print("需要至少2个季度的数据才能绘制图表")
            return
        
        # 提取数据
        quarters = []
        returns = []
        win_rates = []
        stock_counts = []
        
        for result in self.results:
            config = result['config']
            strategy = result['strategy']
            summary = strategy['strategy_summary']
            
            quarters.append(config['current_quarter'])
            returns.append(summary['avg_return'] * 100)  # 转换为百分比
            win_rates.append(summary['win_rate'] * 100)
            stock_counts.append(summary['total_stocks'])
        
        # 创建图表
        fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
        
        # 1. 收益率趋势
        ax1.plot(quarters, returns, marker='o', linewidth=2, markersize=8, color='green')
        ax1.set_title('季度平均收益率趋势', fontsize=14, fontweight='bold')
        ax1.set_ylabel('收益率 (%)')
        ax1.grid(True, alpha=0.3)
        ax1.axhline(y=0, color='red', linestyle='--', alpha=0.5)
        
        # 添加数值标签
        for i, v in enumerate(returns):
            ax1.text(i, v + max(returns) * 0.02, f'{v:.1f}%', ha='center', va='bottom')
        
        # 2. 胜率趋势
        ax2.plot(quarters, win_rates, marker='s', linewidth=2, markersize=8, color='blue')
        ax2.set_title('季度胜率趋势', fontsize=14, fontweight='bold')
        ax2.set_ylabel('胜率 (%)')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, 100)
        
        for i, v in enumerate(win_rates):
            ax2.text(i, v + 2, f'{v:.0f}%', ha='center', va='bottom')
        
        # 3. 选股数量
        bars = ax3.bar(quarters, stock_counts, alpha=0.7, color='orange')
        ax3.set_title('季度选股数量', fontsize=14, fontweight='bold')
        ax3.set_ylabel('股票数量')
        
        for bar in bars:
            height = bar.get_height()
            ax3.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}', ha='center', va='bottom')
        
        # 4. 收益率vs胜率散点图
        ax4.scatter(win_rates, returns, s=np.array(stock_counts)*20, alpha=0.7, color='purple')
        ax4.set_xlabel('胜率 (%)')
        ax4.set_ylabel('收益率 (%)')
        ax4.set_title('收益率 vs 胜率 (气泡大小=选股数量)', fontsize=14, fontweight='bold')
        ax4.grid(True, alpha=0.3)
        
        # 添加季度标签
        for i, quarter in enumerate(quarters):
            ax4.annotate(quarter, (win_rates[i], returns[i]), 
                        xytext=(5, 5), textcoords='offset points', fontsize=10)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"图表已保存到: {save_path}")
        
        plt.show()
    
    def save_analysis_report(self, filename: str = None):
        """保存分析报告"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'precise_strategy_analysis_{timestamp}.txt'
        
        # 生成完整报告
        report = []
        report.append(self.generate_operation_guide())
        report.append("\n\n")
        report.append(self.generate_comparison_analysis())
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("\n".join(report))
        
        print(f"分析报告已保存到: {filename}")
        return filename

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='精确季度策略分析器')
    parser.add_argument('result_files', nargs='+', help='结果文件路径')
    parser.add_argument('--chart', action='store_true', help='生成图表')
    parser.add_argument('--report', action='store_true', help='保存分析报告')
    
    args = parser.parse_args()
    
    # 检查文件存在性
    for file_path in args.result_files:
        if not os.path.exists(file_path):
            print(f"错误: 文件 {file_path} 不存在")
            return
    
    try:
        analyzer = PreciseStrategyAnalyzer(args.result_files)
        
        # 显示操作指南
        print(analyzer.generate_operation_guide())
        
        # 显示对比分析
        if len(args.result_files) > 1:
            print("\n")
            print(analyzer.generate_comparison_analysis())
        
        # 生成图表
        if args.chart:
            print("\n生成图表中...")
            analyzer.plot_performance_chart('charts/precise_strategy_performance.png')
        
        # 保存报告
        if args.report:
            print("\n生成分析报告中...")
            analyzer.save_analysis_report()
        
    except Exception as e:
        print(f"分析失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()