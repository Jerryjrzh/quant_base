#!/usr/bin/env python3
"""
个股参数优化脚本
为指定股票优化交易参数并生成报告
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import json
from datetime import datetime
import data_loader
import strategies
import indicators
from parametric_advisor import ParametricTradingAdvisor, TradingParameters

def optimize_stock_parameters(stock_code, optimization_target='win_rate'):
    """优化指定股票的参数"""
    print(f"🎯 开始优化股票 {stock_code} 的交易参数")
    print(f"📊 优化目标: {optimization_target}")
    print("=" * 60)
    
    # 加载股票数据
    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    if '#' in stock_code:
        market = 'ds'
    else:
        market = stock_code[:2]
    file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
    
    if not os.path.exists(file_path):
        print(f"❌ 股票数据文件不存在: {stock_code}")
        return None
    
    try:
        # 加载和预处理数据
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 200:
            print(f"❌ 股票数据不足: {stock_code} (需要至少200条记录)")
            return None
        
        df.set_index('date', inplace=True)
        print(f"✅ 加载股票数据: {len(df)} 条记录")
        
        # 计算技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        # 生成交易信号
        signals = strategies.apply_macd_zero_axis_strategy(df)
        if signals is None or not signals.any():
            print(f"❌ 未发现有效信号: {stock_code}")
            return None
        
        signal_count = len(signals[signals != ''])
        print(f"📈 发现 {signal_count} 个交易信号")
        
        if signal_count < 5:
            print(f"⚠️ 信号数量较少，优化结果可能不够可靠")
        
        # 执行参数优化
        advisor = ParametricTradingAdvisor()
        optimization_result = advisor.optimize_parameters_for_stock(
            df, signals, optimization_target
        )
        
        if optimization_result['best_parameters'] is None:
            print(f"❌ 参数优化失败")
            return None
        
        # 显示优化结果
        print_optimization_results(stock_code, optimization_result)
        
        # 保存优化结果
        advisor.save_optimized_parameters(stock_code, optimization_result)
        
        # 使用优化参数进行最终回测
        optimized_advisor = ParametricTradingAdvisor(optimization_result['best_parameters'])
        final_backtest = optimized_advisor.backtest_parameters(df, signals, 'moderate')
        
        print("\n" + "=" * 60)
        print("📊 优化参数最终回测结果:")
        print("=" * 60)
        print_backtest_results(final_backtest)
        
        return {
            'stock_code': stock_code,
            'optimization_result': optimization_result,
            'final_backtest': final_backtest,
            'optimized_advisor': optimized_advisor
        }
        
    except Exception as e:
        print(f"❌ 优化过程出错: {e}")
        return None

def print_optimization_results(stock_code, result):
    """打印优化结果"""
    print("\n" + "=" * 60)
    print(f"🏆 {stock_code} 参数优化结果")
    print("=" * 60)
    
    best_params = result['best_parameters']
    best_score = result['best_score']
    target = result['optimization_target']
    
    print(f"🎯 优化目标: {target}")
    print(f"🏅 最佳得分: {best_score:.4f}")
    print()
    
    print("📋 最优参数:")
    print(f"  PRE入场折扣: {best_params.pre_entry_discount:.1%}")
    print(f"  适中止损: {best_params.moderate_stop:.1%}")
    print(f"  适中止盈: {best_params.moderate_profit:.1%}")
    print(f"  最大持有天数: {best_params.max_holding_days}天")
    print()
    
    print("📈 前5名参数组合:")
    for i, res in enumerate(result['optimization_results'][:5], 1):
        params = res['parameters']
        score = res['score']
        stats = res['stats']
        print(f"  {i}. 得分: {score:.4f} | 胜率: {stats['win_rate']:.1%} | "
              f"平均收益: {stats['avg_pnl']:.2%} | 交易次数: {stats['total_trades']}")

def print_backtest_results(backtest):
    """打印回测结果"""
    if 'error' in backtest:
        print(f"❌ 回测失败: {backtest['error']}")
        return
    
    print(f"📊 总交易次数: {backtest['total_trades']}")
    print(f"🏆 胜率: {backtest['win_rate']:.1%}")
    print(f"💰 平均收益: {backtest['avg_pnl']:.2%}")
    print(f"📈 平均盈利: {backtest['avg_win']:.2%}")
    print(f"📉 平均亏损: {backtest['avg_loss']:.2%}")
    print(f"🎯 最大盈利: {backtest['max_win']:.2%}")
    print(f"⚠️ 最大亏损: {backtest['max_loss']:.2%}")
    print(f"⏱️ 平均持有天数: {backtest['avg_holding_days']:.1f}天")
    print(f"💎 盈亏比: {backtest['profit_factor']:.2f}")

def compare_default_vs_optimized(stock_code):
    """对比默认参数和优化参数的效果"""
    print(f"\n🔄 对比 {stock_code} 的默认参数 vs 优化参数")
    print("=" * 60)
    
    # 加载数据
    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    if '#' in stock_code:
        market = 'ds'
    else:
        market = stock_code[:2]
    file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
    
    df = data_loader.get_daily_data(file_path)
    df.set_index('date', inplace=True)
    
    macd_values = indicators.calculate_macd(df)
    df['dif'], df['dea'] = macd_values[0], macd_values[1]
    signals = strategies.apply_macd_zero_axis_strategy(df)
    
    # 默认参数回测
    default_advisor = ParametricTradingAdvisor()
    default_result = default_advisor.backtest_parameters(df, signals, 'moderate')
    
    # 优化参数回测
    optimized_params = default_advisor.load_optimized_parameters(stock_code)
    if optimized_params is None:
        print("❌ 未找到优化参数，请先运行参数优化")
        return
    
    optimized_advisor = ParametricTradingAdvisor(optimized_params)
    optimized_result = optimized_advisor.backtest_parameters(df, signals, 'moderate')
    
    # 对比结果
    print("📊 默认参数结果:")
    print_backtest_results(default_result)
    
    print("\n📊 优化参数结果:")
    print_backtest_results(optimized_result)
    
    # 计算改进幅度
    if 'error' not in default_result and 'error' not in optimized_result:
        print("\n📈 改进幅度:")
        win_rate_improvement = optimized_result['win_rate'] - default_result['win_rate']
        pnl_improvement = optimized_result['avg_pnl'] - default_result['avg_pnl']
        
        print(f"  胜率改进: {win_rate_improvement:+.1%}")
        print(f"  平均收益改进: {pnl_improvement:+.2%}")
        
        if win_rate_improvement > 0 or pnl_improvement > 0:
            print("✅ 参数优化有效！")
        else:
            print("⚠️ 参数优化效果不明显")

def batch_optimize_stocks(stock_codes, optimization_target='win_rate'):
    """批量优化多只股票"""
    print(f"🚀 批量优化 {len(stock_codes)} 只股票")
    print(f"📊 优化目标: {optimization_target}")
    print("=" * 60)
    
    results = {}
    
    for i, stock_code in enumerate(stock_codes, 1):
        print(f"\n[{i}/{len(stock_codes)}] 正在优化 {stock_code}...")
        
        result = optimize_stock_parameters(stock_code, optimization_target)
        if result:
            results[stock_code] = result
            print(f"✅ {stock_code} 优化完成")
        else:
            print(f"❌ {stock_code} 优化失败")
    
    # 生成批量优化报告
    print("\n" + "=" * 60)
    print("📋 批量优化汇总报告")
    print("=" * 60)
    
    for stock_code, result in results.items():
        backtest = result['final_backtest']
        if 'error' not in backtest:
            print(f"{stock_code}: 胜率 {backtest['win_rate']:.1%}, "
                  f"平均收益 {backtest['avg_pnl']:.2%}, "
                  f"交易次数 {backtest['total_trades']}")
    
    return results

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python run_optimization.py <股票代码> [优化目标]")
        print("  python run_optimization.py <股票代码> compare  # 对比默认vs优化参数")
        print("  python run_optimization.py batch <股票代码1> <股票代码2> ...  # 批量优化")
        print("")
        print("优化目标选项:")
        print("  win_rate     - 胜率 (默认)")
        print("  avg_pnl      - 平均收益")
        print("  profit_factor - 盈亏比")
        print("")
        print("示例:")
        print("  python run_optimization.py sh000001")
        print("  python run_optimization.py sz000001 avg_pnl")
        print("  python run_optimization.py sh000001 compare")
        print("  python run_optimization.py batch sh000001 sz000001 sh600000")
        return
    
    if sys.argv[1] == 'batch':
        # 批量优化
        stock_codes = [code.lower() for code in sys.argv[2:]]
        if not stock_codes:
            print("❌ 请提供要优化的股票代码")
            return
        
        optimization_target = 'win_rate'
        batch_optimize_stocks(stock_codes, optimization_target)
        
    elif len(sys.argv) >= 3 and sys.argv[2] == 'compare':
        # 对比模式
        stock_code = sys.argv[1].lower()
        compare_default_vs_optimized(stock_code)
        
    else:
        # 单只股票优化
        stock_code = sys.argv[1].lower()
        optimization_target = sys.argv[2] if len(sys.argv) > 2 else 'win_rate'
        
        if optimization_target not in ['win_rate', 'avg_pnl', 'profit_factor']:
            print(f"❌ 不支持的优化目标: {optimization_target}")
            return
        
        result = optimize_stock_parameters(stock_code, optimization_target)
        
        if result:
            print(f"\n🎉 {stock_code} 参数优化完成！")
            print("💡 使用以下命令对比效果:")
            print(f"   python run_optimization.py {stock_code} compare")

if __name__ == "__main__":
    main()