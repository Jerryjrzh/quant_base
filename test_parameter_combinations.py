#!/usr/bin/env python3
"""
测试参数组合的效果
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
from datetime import datetime
from parametric_advisor import ParametricTradingAdvisor, TradingParameters

def test_parameter_combinations():
    """测试不同参数组合"""
    print("🧪 测试参数组合效果")
    print("=" * 50)
    
    # 创建测试数据
    dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
    np.random.seed(42)
    
    # 模拟有趋势的价格数据
    trend = np.linspace(0, 0.2, len(dates))  # 20%的年度趋势
    noise = np.random.normal(0, 0.02, len(dates))
    returns = trend/len(dates) + noise
    prices = 100 * np.cumprod(1 + returns)
    
    df = pd.DataFrame({
        'close': prices,
        'high': prices * (1 + np.random.uniform(0, 0.02, len(dates))),
        'low': prices * (1 - np.random.uniform(0, 0.02, len(dates))),
        'open': prices * (1 + np.random.uniform(-0.01, 0.01, len(dates))),
        'volume': np.random.randint(1000000, 10000000, len(dates))
    }, index=dates)
    
    # 创建模拟信号
    signal_dates = pd.date_range(start='2023-02-01', end='2023-11-01', freq='30D')
    signals = pd.Series('', index=df.index)
    
    for i, date in enumerate(signal_dates):
        if date in df.index:
            state = ['PRE', 'MID', 'POST'][i % 3]
            signals.loc[date] = state
    
    print(f"📊 测试数据: {len(df)} 天，{len(signals[signals != ''])} 个信号")
    
    # 测试不同参数组合
    parameter_sets = [
        {
            'name': '保守型',
            'pre_entry_discount': 0.03,
            'moderate_stop': 0.03,
            'moderate_profit': 0.08,
            'max_holding_days': 20
        },
        {
            'name': '适中型',
            'pre_entry_discount': 0.02,
            'moderate_stop': 0.05,
            'moderate_profit': 0.12,
            'max_holding_days': 30
        },
        {
            'name': '激进型',
            'pre_entry_discount': 0.015,
            'moderate_stop': 0.08,
            'moderate_profit': 0.20,
            'max_holding_days': 45
        }
    ]
    
    results = []
    
    for param_set in parameter_sets:
        print(f"\n🔧 测试 {param_set['name']} 参数...")
        
        # 创建参数对象
        params = TradingParameters()
        params.pre_entry_discount = param_set['pre_entry_discount']
        params.moderate_stop = param_set['moderate_stop']
        params.moderate_profit = param_set['moderate_profit']
        params.max_holding_days = param_set['max_holding_days']
        
        # 创建顾问
        advisor = ParametricTradingAdvisor(params)
        
        # 执行回测
        backtest_result = advisor.backtest_parameters(df, signals, 'moderate')
        
        if 'error' not in backtest_result:
            result = {
                'name': param_set['name'],
                'total_trades': backtest_result['total_trades'],
                'win_rate': backtest_result['win_rate'],
                'avg_pnl': backtest_result['avg_pnl'],
                'max_win': backtest_result['max_win'],
                'max_loss': backtest_result['max_loss'],
                'profit_factor': backtest_result['profit_factor']
            }
            results.append(result)
            
            print(f"  交易次数: {result['total_trades']}")
            print(f"  胜率: {result['win_rate']:.1%}")
            print(f"  平均收益: {result['avg_pnl']:+.2%}")
            print(f"  盈亏比: {result['profit_factor']:.2f}")
        else:
            print(f"  ❌ 回测失败: {backtest_result['error']}")
    
    # 对比结果
    if results:
        print("\n📊 参数组合对比:")
        print("=" * 70)
        print(f"{'参数组合':<10} {'交易次数':<8} {'胜率':<8} {'平均收益':<10} {'盈亏比':<8}")
        print("-" * 70)
        
        for result in results:
            print(f"{result['name']:<10} {result['total_trades']:<8} "
                  f"{result['win_rate']:<7.1%} {result['avg_pnl']:<9.2%} "
                  f"{result['profit_factor']:<8.2f}")
        
        # 找出最佳参数
        best_result = max(results, key=lambda x: x['win_rate'] * 0.6 + max(0, x['avg_pnl']) * 0.4)
        print(f"\n🏆 最佳参数组合: {best_result['name']}")
        print(f"   综合得分: {best_result['win_rate'] * 0.6 + max(0, best_result['avg_pnl']) * 0.4:.3f}")
    
    print("\n✅ 参数组合测试完成！")

def test_entry_strategies():
    """测试入场策略"""
    print("\n🎯 测试入场策略...")
    
    # 创建简单测试数据
    dates = pd.date_range(start='2023-06-01', end='2023-06-30', freq='D')
    prices = [100, 101, 99, 102, 98, 103, 97, 104, 96, 105] * 3  # 重复模式
    
    df = pd.DataFrame({
        'close': prices[:len(dates)],
        'high': [p * 1.02 for p in prices[:len(dates)]],
        'low': [p * 0.98 for p in prices[:len(dates)]],
        'open': prices[:len(dates)],
        'volume': [1000000] * len(dates)
    }, index=dates)
    
    # 测试不同信号状态的入场策略
    advisor = ParametricTradingAdvisor()
    
    test_cases = [
        ('PRE', 10, 100.0),
        ('MID', 15, 102.0),
        ('POST', 20, 98.0)
    ]
    
    for signal_state, signal_idx, current_price in test_cases:
        print(f"\n测试 {signal_state} 状态入场策略:")
        
        advice = advisor.get_parametric_entry_recommendations(
            df, signal_idx, signal_state, current_price
        )
        
        if 'error' not in advice and 'entry_strategies' in advice:
            for i, strategy in enumerate(advice['entry_strategies'], 1):
                print(f"  策略{i}: {strategy['strategy']}")
                print(f"    价位1: ¥{strategy['entry_price_1']}")
                print(f"    价位2: ¥{strategy['entry_price_2']}")
                print(f"    仓位: {strategy['position_allocation']}")
        else:
            print(f"  ❌ 获取策略失败")
    
    print("\n✅ 入场策略测试完成！")

def main():
    """主函数"""
    print("🚀 开始参数组合测试")
    print("=" * 60)
    
    try:
        test_parameter_combinations()
        test_entry_strategies()
        
        print("\n🎉 所有测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()