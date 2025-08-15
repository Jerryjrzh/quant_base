#!/usr/bin/env python3
"""
通过历史数据回测优化补仓位系数
分析不同系数下的补仓效果，找出最优系数
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from portfolio_manager import create_portfolio_manager
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class AddPositionCoefficientOptimizer:
    """补仓系数优化器"""
    
    def __init__(self):
        self.portfolio_manager = create_portfolio_manager()
        
    def analyze_support_calculation(self, stock_code: str) -> dict:
        """分析支撑位计算方法"""
        print(f"📊 分析 {stock_code} 的支撑位计算方法")
        
        # 获取股票数据
        df = self.portfolio_manager.get_stock_data(stock_code)
        if df is None:
            return {'error': '无法获取数据'}
        
        # 计算技术指标
        df = self.portfolio_manager.calculate_technical_indicators(df, stock_code)
        
        # 分析最近60天的数据
        recent_data = df.tail(60)
        current_price = float(df.iloc[-1]['close'])
        
        print(f"   当前价格: ¥{current_price:.2f}")
        print(f"   分析周期: 最近60个交易日")
        
        # 支撑阻力位计算逻辑分析
        resistance_levels = []
        support_levels = []
        
        # 基于历史高低点（5日窗口）
        highs = recent_data['high'].rolling(window=5).max()
        lows = recent_data['low'].rolling(window=5).min()
        
        print(f"   计算方法: 5日滚动窗口寻找局部高低点")
        
        # 找出重要的支撑阻力位
        for i in range(5, len(recent_data)-5):
            if highs.iloc[i] == recent_data['high'].iloc[i]:
                resistance_levels.append(float(recent_data['high'].iloc[i]))
            if lows.iloc[i] == recent_data['low'].iloc[i]:
                support_levels.append(float(recent_data['low'].iloc[i]))
        
        # 去重并排序
        resistance_levels = sorted(list(set(resistance_levels)), reverse=True)
        support_levels = sorted(list(set(support_levels)))
        
        print(f"   发现阻力位: {len(resistance_levels)}个")
        print(f"   发现支撑位: {len(support_levels)}个")
        
        # 找出最近的支撑阻力位
        next_resistance = None
        next_support = None
        
        for level in resistance_levels:
            if level > current_price:
                next_resistance = level
                break
        
        for level in reversed(support_levels):
            if level < current_price:
                next_support = level
                break
        
        support_text = f"¥{next_support:.2f}" if next_support else '无'
        resistance_text = f"¥{next_resistance:.2f}" if next_resistance else '无'
        print(f"   下一支撑位: {support_text}")
        print(f"   下一阻力位: {resistance_text}")
        
        return {
            'current_price': current_price,
            'next_support': next_support,
            'next_resistance': next_resistance,
            'all_support_levels': support_levels,
            'all_resistance_levels': resistance_levels
        }
    
    def backtest_add_position_coefficients(self, stock_code: str, coefficients: list) -> dict:
        """回测不同补仓系数的效果"""
        print(f"\n🔍 回测 {stock_code} 的补仓系数效果")
        
        # 获取股票数据
        df = self.portfolio_manager.get_stock_data(stock_code)
        if df is None:
            return {'error': '无法获取数据'}
        
        # 计算技术指标
        df = self.portfolio_manager.calculate_technical_indicators(df, stock_code)
        
        # 模拟历史补仓场景
        results = {}
        
        for coeff in coefficients:
            print(f"   测试系数: {coeff}")
            success_count = 0
            total_scenarios = 0
            total_return = 0
            
            # 滑动窗口分析历史数据
            for i in range(100, len(df) - 20):  # 留出足够的历史数据和未来数据
                current_data = df.iloc[:i+1]
                future_data = df.iloc[i+1:i+21]  # 未来20天
                
                if len(future_data) < 10:
                    continue
                
                current_price = float(current_data.iloc[-1]['close'])
                
                # 计算当前的支撑位
                price_targets = self.portfolio_manager._calculate_price_targets(current_data, current_price)
                support_level = price_targets.get('next_support')
                
                if not support_level:
                    continue
                
                # 计算补仓价
                add_price = support_level * coeff
                
                # 检查是否触发补仓价
                min_future_price = float(future_data['low'].min())
                if min_future_price <= add_price:
                    total_scenarios += 1
                    
                    # 计算补仓后的收益
                    # 假设在补仓价买入，在未来最高价卖出
                    max_future_price = float(future_data['high'].max())
                    return_pct = (max_future_price - add_price) / add_price * 100
                    
                    if return_pct > 10:
                        success_count += 1
                    
                    total_return += return_pct
            
            if total_scenarios > 0:
                success_rate = success_count / total_scenarios * 100
                avg_return = total_return / total_scenarios
                
                results[coeff] = {
                    'success_rate': success_rate,
                    'avg_return': avg_return,
                    'total_scenarios': total_scenarios,
                    'success_count': success_count
                }
                
                print(f"     场景数: {total_scenarios}, 成功率: {success_rate:.1f}%, 平均收益: {avg_return:.2f}%")
            else:
                results[coeff] = {
                    'success_rate': 0,
                    'avg_return': 0,
                    'total_scenarios': 0,
                    'success_count': 0
                }
                print(f"     场景数: 0, 无有效场景")
        
        return results
    
    def find_optimal_coefficient(self, stock_codes: list, coefficients: list) -> dict:
        """找出最优补仓系数"""
        print(f"\n🎯 寻找最优补仓系数")
        print(f"   测试股票: {len(stock_codes)}只")
        print(f"   测试系数: {coefficients}")
        
        all_results = {}
        coefficient_stats = {coeff: {'total_success': 0, 'total_scenarios': 0, 'total_return': 0} 
                           for coeff in coefficients}
        
        for stock_code in stock_codes:
            print(f"\n--- 分析 {stock_code} ---")
            results = self.backtest_add_position_coefficients(stock_code, coefficients)
            
            if 'error' not in results:
                all_results[stock_code] = results
                
                # 累计统计
                for coeff, stats in results.items():
                    coefficient_stats[coeff]['total_success'] += stats['success_count']
                    coefficient_stats[coeff]['total_scenarios'] += stats['total_scenarios']
                    coefficient_stats[coeff]['total_return'] += stats['avg_return'] * stats['total_scenarios']
        
        # 计算综合统计
        print(f"\n📊 综合统计结果:")
        best_coeff = None
        best_score = -999
        
        for coeff, stats in coefficient_stats.items():
            if stats['total_scenarios'] > 0:
                overall_success_rate = stats['total_success'] / stats['total_scenarios'] * 100
                overall_avg_return = stats['total_return'] / stats['total_scenarios']
                
                # 综合评分：成功率 * 0.6 + 平均收益 * 0.4
                score = overall_success_rate * 0.6 + overall_avg_return * 0.4
                
                print(f"   系数 {coeff}: 成功率 {overall_success_rate:.1f}%, 平均收益 {overall_avg_return:.2f}%, 综合评分 {score:.2f}")
                
                if score > best_score:
                    best_score = score
                    best_coeff = coeff
            else:
                print(f"   系数 {coeff}: 无有效数据")
        
        print(f"\n🏆 最优系数: {best_coeff} (评分: {best_score:.2f})")
        
        return {
            'best_coefficient': best_coeff,
            'best_score': best_score,
            'all_results': all_results,
            'coefficient_stats': coefficient_stats
        }

def main():
    """主函数"""
    print("🧪 补仓系数优化分析")
    print("=" * 60)
    
    optimizer = AddPositionCoefficientOptimizer()
    
    # 1. 分析支撑位计算方法
    print("\n1️⃣ 支撑位计算方法分析")
    portfolio = optimizer.portfolio_manager.load_portfolio()
    if len(portfolio) > 0:
        sample_stock = portfolio[0]['stock_code']
        support_analysis = optimizer.analyze_support_calculation(sample_stock)
        
        if 'error' not in support_analysis:
            print(f"\n📋 支撑位计算说明:")
            print(f"   • 使用最近60个交易日的数据")
            print(f"   • 通过5日滚动窗口寻找局部高低点")
            print(f"   • 局部低点作为支撑位候选")
            print(f"   • 选择距离当前价格最近的下方支撑位")
    
    # 2. 测试不同系数
    print(f"\n2️⃣ 补仓系数回测分析")
    test_coefficients = [0.98, 0.99, 1.00, 1.01, 1.02, 1.03, 1.05]  # 支撑位的98%到105%
    
    # 选择部分持仓进行测试
    test_stocks = [pos['stock_code'] for pos in portfolio[:5]] if len(portfolio) >= 5 else [pos['stock_code'] for pos in portfolio]
    
    if len(test_stocks) > 0:
        optimal_result = optimizer.find_optimal_coefficient(test_stocks, test_coefficients)
        
        print(f"\n📋 系数含义说明:")
        print(f"   • 系数 < 1.0: 在支撑位下方补仓（更保守）")
        print(f"   • 系数 = 1.0: 在支撑位补仓")
        print(f"   • 系数 > 1.0: 在支撑位上方补仓（当前使用1.02）")
        
        print(f"\n💡 建议:")
        if optimal_result['best_coefficient']:
            current_coeff = 1.02
            best_coeff = optimal_result['best_coefficient']
            
            if abs(best_coeff - current_coeff) > 0.01:
                print(f"   建议将补仓系数从 {current_coeff} 调整为 {best_coeff}")
                print(f"   预期可提升补仓成功率和收益")
            else:
                print(f"   当前系数 {current_coeff} 已接近最优值 {best_coeff}")
                print(f"   无需调整")
        else:
            print(f"   数据不足，建议保持当前系数 1.02")
    else:
        print("❌ 没有持仓数据进行测试")
    
    print("\n✅ 补仓系数优化分析完成")

if __name__ == "__main__":
    main()