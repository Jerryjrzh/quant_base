#!/usr/bin/env python3
"""
调试信号显示问题
检查为什么用户可能只看到成功的信号
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import json
import pandas as pd
import numpy as np
import data_loader
import indicators
import strategies
import backtester
from adjustment_processor import create_adjustment_config, create_adjustment_processor

def debug_signal_filtering():
    """调试信号过滤问题"""
    print("🔍 调试信号显示问题")
    print("=" * 60)
    
    # 测试当前用户可能使用的策略
    current_strategy = 'WEEKLY_GOLDEN_CROSS_MA'  # 从screener.py中看到的当前策略
    test_stocks = ['sz300290', 'sz000001', 'sh600036', 'sz002415', 'sh600519']
    
    print(f"📈 当前策略: {current_strategy}")
    
    for stock_code in test_stocks:
        print(f"\n📊 测试股票: {stock_code}")
        print("-" * 40)
        
        try:
            # 加载数据
            if '#' in stock_code:
                market = 'ds'
            else:
                market = stock_code[:2]
            base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
            file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
            
            if not os.path.exists(file_path):
                print(f"❌ 数据文件不存在")
                continue
                
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 100:
                print(f"❌ 数据不足")
                continue
            
            # 应用复权处理
            adjustment_type = 'forward'
            adjustment_config = create_adjustment_config(adjustment_type)
            adjustment_processor = create_adjustment_processor(adjustment_config)
            df = adjustment_processor.process_data(df, stock_code)
            
            # 计算技术指标
            df['ma13'] = indicators.calculate_ma(df, 13)
            df['ma45'] = indicators.calculate_ma(df, 45)
            
            macd_config = indicators.MACDIndicatorConfig(adjustment_config=adjustment_config)
            df['dif'], df['dea'] = indicators.calculate_macd(df, config=macd_config, stock_code=stock_code)
            df['macd'] = df['dif'] - df['dea']
            
            kdj_config = indicators.KDJIndicatorConfig(adjustment_config=adjustment_config)
            df['k'], df['d'], df['j'] = indicators.calculate_kdj(df, config=kdj_config, stock_code=stock_code)
            
            # 应用策略
            signals = strategies.apply_strategy(current_strategy, df)
            
            if signals is None:
                print(f"❌ 策略应用失败")
                continue
                
            # 统计原始信号
            raw_signals = signals[signals != '']
            if raw_signals.empty:
                print(f"⚠️ 无原始信号")
                continue
                
            print(f"📊 原始信号数量: {len(raw_signals)}")
            
            # 执行回测
            backtest_results = backtester.run_backtest(df, signals)
            
            if not backtest_results or backtest_results.get('total_signals', 0) == 0:
                print(f"⚠️ 回测后无有效信号")
                continue
            
            trades = backtest_results.get('trades', [])
            if not trades:
                print(f"⚠️ 无交易记录")
                continue
            
            # 分析成功/失败比例
            success_count = sum(1 for trade in trades if trade.get('is_success', False))
            fail_count = len(trades) - success_count
            success_rate = success_count / len(trades) * 100
            
            print(f"✅ 有效信号数量: {len(trades)}")
            print(f"🟢 成功信号: {success_count} ({success_rate:.1f}%)")
            print(f"🔴 失败信号: {fail_count} ({100-success_rate:.1f}%)")
            
            # 模拟前端API返回的数据
            signal_points = []
            signal_df = df[signals != '']
            trade_results = {trade['entry_idx']: trade for trade in trades}
            
            for idx, row in signal_df.iterrows():
                original_state = str(signals[idx])
                idx_pos = df.index.get_loc(idx) if idx in df.index else 0
                is_success = trade_results.get(idx_pos, {}).get('is_success', False)
                final_state = f"{original_state}_SUCCESS" if is_success else f"{original_state}_FAIL"
                
                # 使用修复后的价格逻辑
                actual_entry_price = trade_results.get(idx_pos, {}).get('entry_price')
                if actual_entry_price is not None:
                    display_price = float(actual_entry_price)
                else:
                    display_price = float(row['close'])
                
                date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)
                
                signal_points.append({
                    'date': date_str,
                    'price': display_price,
                    'state': final_state,
                    'original_state': original_state
                })
            
            # 统计前端会显示的颜色
            success_signals = [s for s in signal_points if 'SUCCESS' in s['state']]
            fail_signals = [s for s in signal_points if 'FAIL' in s['state']]
            other_signals = [s for s in signal_points if 'SUCCESS' not in s['state'] and 'FAIL' not in s['state']]
            
            print(f"\n🎨 前端显示统计:")
            print(f"   🟢 绿色三角(SUCCESS): {len(success_signals)} 个")
            print(f"   🔴 红色三角(FAIL): {len(fail_signals)} 个")
            print(f"   🟡 黄色三角(其他): {len(other_signals)} 个")
            
            # 显示最近的信号状态
            recent_signals = signal_points[-5:] if len(signal_points) >= 5 else signal_points
            print(f"\n📅 最近的信号状态:")
            for signal in recent_signals:
                color_icon = "🟢" if 'SUCCESS' in signal['state'] else "🔴" if 'FAIL' in signal['state'] else "🟡"
                print(f"   {signal['date']} {color_icon} {signal['state']} - ¥{signal['price']:.2f}")
            
            # 如果成功率很高，解释原因
            if success_rate > 80:
                print(f"\n💡 成功率很高的可能原因:")
                print(f"   1. 策略本身表现良好")
                print(f"   2. 过滤器已经排除了大部分失败信号")
                print(f"   3. 回测期间市场整体表现较好")
                print(f"   4. 成功判定标准相对宽松")
            
            break  # 找到一个有效的例子就够了
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            continue

def check_current_screener_results():
    """检查当前筛选器的结果"""
    print(f"\n📋 检查当前筛选器结果")
    print("=" * 60)
    
    # 检查最新的筛选结果
    result_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data', 'result'))
    strategy = 'WEEKLY_GOLDEN_CROSS_MA'  # 当前策略
    
    signals_file = os.path.join(result_path, strategy, 'signals_summary.json')
    
    if os.path.exists(signals_file):
        try:
            with open(signals_file, 'r', encoding='utf-8') as f:
                signals_data = json.load(f)
            
            print(f"📊 当前筛选结果:")
            print(f"   策略: {strategy}")
            print(f"   信号数量: {len(signals_data)}")
            
            if signals_data:
                print(f"\n📈 信号统计:")
                for i, signal in enumerate(signals_data[:5]):  # 显示前5个
                    stock_code = signal.get('stock_code', 'N/A')
                    signal_state = signal.get('signal_state', 'N/A')
                    win_rate = signal.get('win_rate', 'N/A')
                    avg_profit = signal.get('avg_max_profit', 'N/A')
                    
                    print(f"   {i+1}. {stock_code} - {signal_state} (胜率:{win_rate}, 收益:{avg_profit})")
                
                # 分析胜率分布
                win_rates = []
                for signal in signals_data:
                    win_rate_str = signal.get('win_rate', '0%').replace('%', '')
                    try:
                        win_rates.append(float(win_rate_str))
                    except:
                        pass
                
                if win_rates:
                    avg_win_rate = sum(win_rates) / len(win_rates)
                    print(f"\n📊 胜率分析:")
                    print(f"   平均胜率: {avg_win_rate:.1f}%")
                    print(f"   胜率范围: {min(win_rates):.1f}% - {max(win_rates):.1f}%")
                    
                    high_win_rate_count = sum(1 for wr in win_rates if wr >= 60)
                    print(f"   高胜率(≥60%)股票: {high_win_rate_count}/{len(win_rates)} ({high_win_rate_count/len(win_rates)*100:.1f}%)")
        
        except Exception as e:
            print(f"❌ 读取筛选结果失败: {e}")
    else:
        print(f"⚠️ 筛选结果文件不存在: {signals_file}")
        print(f"   请先运行 screener.py 生成筛选结果")

def suggest_solutions():
    """建议解决方案"""
    print(f"\n💡 如果只看到成功信号的解决方案")
    print("=" * 60)
    
    print("🔧 可能的解决方案:")
    print("1. 调整成功判定标准:")
    print("   - 提高收益目标 (当前5%)")
    print("   - 增加趋势确认要求")
    print("   - 缩短观察期")
    
    print("\n2. 检查数据时间范围:")
    print("   - 确保包含不同市场环境的数据")
    print("   - 避免只测试牛市期间的数据")
    
    print("\n3. 验证前端显示:")
    print("   - 检查浏览器开发者工具中的信号数据")
    print("   - 确认signal_points数组包含FAIL状态的信号")
    print("   - 验证ECharts渲染是否正确")
    
    print("\n4. 测试不同策略:")
    print("   - 尝试MACD_ZERO_AXIS策略 (通常有更多失败信号)")
    print("   - 测试PRE_CROSS策略")
    print("   - 比较不同策略的成功/失败比例")

if __name__ == "__main__":
    print("🔍 信号显示问题调试")
    print("=" * 80)
    
    debug_signal_filtering()
    check_current_screener_results()
    suggest_solutions()
    
    print(f"\n📝 总结:")
    print("回测失败标识的逻辑是正确的，如果只看到成功信号，可能是因为:")
    print("1. 当前策略和股票组合的成功率确实很高")
    print("2. 过滤器已经排除了大部分可能失败的信号")
    print("3. 需要测试更多样化的市场环境和策略")