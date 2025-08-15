#!/usr/bin/env python3
"""
个股参数优化脚本 (多进程改造版)
为指定股票优化交易参数并生成报告
"""

import sys
import os
import threading
# 关键改动: 导入 ProcessPoolExecutor 而不是 ThreadPoolExecutor
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import json
from datetime import datetime
import data_loader
import strategies
import indicators
from parametric_advisor import ParametricTradingAdvisor, TradingParameters

# 打印锁在多进程中不是必须的，因为进程的输出是独立的。但保留它也无害。
print_lock = threading.Lock()

def optimize_stock_parameters(stock_code, optimization_target='win_rate'):
    """优化指定股票的参数 (此函数无需改动)"""
    # 为了清晰，我们可以在输出中指明是哪个进程在工作
    pid = os.getpid()
    print(f"⚙️ [进程 {pid}] 开始优化 {stock_code}...")

    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    if '#' in stock_code:
        market = 'ds'
    else:
        market = stock_code[:2]
    file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')

    if not os.path.exists(file_path):
        print(f"❌ [{stock_code}] 股票数据文件不存在")
        return None

    try:
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 200:
            print(f"❌ [{stock_code}] 股票数据不足 (需要至少200条记录)")
            return None

        df.set_index('date', inplace=True)
        
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        signals = strategies.apply_macd_zero_axis_strategy(df)
        if signals is None or not signals.any():
            print(f"❌ [{stock_code}] 未发现有效信号")
            return None

        advisor = ParametricTradingAdvisor()
        optimization_result = advisor.optimize_parameters_for_stock(df, signals, optimization_target)

        if optimization_result['best_parameters'] is None:
            print(f"❌ [{stock_code}] 参数优化失败")
            return None

        optimized_advisor = ParametricTradingAdvisor(optimization_result['best_parameters'])
        final_backtest = optimized_advisor.backtest_parameters(df, signals, 'moderate')

        # 将保存和打印结果的操作也放在返回值中，由主进程统一处理
        return {
            'stock_code': stock_code,
            'optimization_result': optimization_result,
            'final_backtest': final_backtest
        }
    except Exception as e:
        print(f"❌ [{stock_code} 进程 {pid}] 优化过程出错: {e}")
        return None

def print_optimization_results(stock_code, result):
    # (此函数无需改动)
    print("\n" + "=" * 60)
    print(f"🏆 {stock_code} 参数优化结果")
    # ... (代码与原版相同)
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
    # (此函数无需改动)
    if 'error' in backtest:
        print(f"❌ 回测失败: {backtest['error']}")
        return

    print(f"📊 总交易次数: {backtest['total_trades']}")
    # ... (代码与原版相同)
    print(f"🏆 胜率: {backtest['win_rate']:.1%}")
    print(f"💰 平均收益: {backtest['avg_pnl']:.2%}")
    print(f"📈 平均盈利: {backtest['avg_win']:.2%}")
    print(f"📉 平均亏损: {backtest['avg_loss']:.2%}")
    print(f"🎯 最大盈利: {backtest['max_win']:.2%}")
    print(f"⚠️ 最大亏损: {backtest['max_loss']:.2%}")
    print(f"⏱️ 平均持有天数: {backtest['avg_holding_days']:.1f}天")
    print(f"💎 盈亏比: {backtest['profit_factor']:.2f}")

def compare_default_vs_optimized(stock_code):
    # (此函数无需改动)
    print(f"\n🔄 对比 {stock_code} 的默认参数 vs 优化参数")
    # ... (代码与原版相同)
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


def batch_optimize_stocks(stock_codes, optimization_target='win_rate', max_workers=None):
    """批量优化多只股票 (多进程)"""
    total_jobs = len(stock_codes)
    # 如果未指定进程数，则使用CPU核心数
    if max_workers is None:
        max_workers = os.cpu_count()
    
    print(f"🚀 批量优化 {total_jobs} 只股票 (使用最多 {max_workers} 个进程)")
    print(f"📊 优化目标: {optimization_target}")
    print("=" * 60)

    results = {}
    completed_jobs = 0

    # 关键改动: 使用 ProcessPoolExecutor
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_stock = {executor.submit(optimize_stock_parameters, code, optimization_target): code for code in stock_codes}

        for future in as_completed(future_to_stock):
            stock_code = future_to_stock[future]
            completed_jobs += 1
            try:
                result = future.result()
                if result:
                    results[stock_code] = result
                    # 可以在这里立即处理结果，例如打印和保存
                    print_optimization_results(stock_code, result['optimization_result'])
                    ParametricTradingAdvisor().save_optimized_parameters(stock_code, result['optimization_result'])
                    print(f"✅ [{completed_jobs}/{total_jobs}] {stock_code} 优化完成并已保存。")
                else:
                    print(f"❌ [{completed_jobs}/{total_jobs}] {stock_code} 优化失败。")
            except Exception as exc:
                print(f'❌ {stock_code} 在执行过程中产生异常: {exc}')
            
            # 打印总体进度
            print(f"--- 进度: {completed_jobs}/{total_jobs} ---")

    # 生成最终的批量优化报告
    print("\n" + "=" * 60)
    print("📋 批量优化汇总报告")
    print("=" * 60)
    sorted_results = sorted(results.items())

    for stock_code, result_data in sorted_results:
        backtest = result_data['final_backtest']
        if 'error' not in backtest:
            print(f"{stock_code}: 胜率 {backtest['win_rate']:.1%}, "
                  f"平均收益 {backtest['avg_pnl']:.2%}, "
                  f"交易次数 {backtest['total_trades']}")
        else:
            print(f"{stock_code}: 回测失败 - {backtest['error']}")
    return results

def main():
    """主函数"""
    # ... (帮助信息与原版相同)
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
        stock_codes = [code.lower() for code in sys.argv[2:]]
        if not stock_codes:
            print("❌ 请提供要优化的股票代码")
            return
        optimization_target = 'win_rate'
        batch_optimize_stocks(stock_codes, optimization_target)
    elif len(sys.argv) >= 3 and sys.argv[2] == 'compare':
        stock_code = sys.argv[1].lower()
        compare_default_vs_optimized(stock_code)
    else:
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

# 关键改动: 使用 `if __name__ == '__main__':` 保护
# 这是使用多进程(ProcessPoolExecutor)时的强制要求，尤其是在Windows和macOS上，
# 它可以防止子进程无限递归地重新执行主程序代码。
if __name__ == "__main__":
    main()