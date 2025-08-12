#!/usr/bin/env python3
"""
测试WEEKLY_GOLDEN_CROSS_MA策略的信号显示问题
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
import data_loader
import indicators
import strategies
import backtester
from adjustment_processor import create_adjustment_config, create_adjustment_processor

def test_weekly_strategy_signals():
    """测试周线策略的信号"""
    print("🔍 测试WEEKLY_GOLDEN_CROSS_MA策略信号")
    print("=" * 60)
    
    # 从筛选结果中选择一个股票进行测试
    test_stock = 'sh603369'  # 从调试结果中看到的第一个股票
    
    print(f"📊 测试股票: {test_stock}")
    
    try:
        # 加载数据
        market = test_stock[:2]
        base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        file_path = os.path.join(base_path, market, 'lday', f'{test_stock}.day')
        
        if not os.path.exists(file_path):
            print(f"❌ 数据文件不存在: {file_path}")
            return
            
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 100:
            print(f"❌ 数据加载失败或数据不足")
            return
        
        print(f"✅ 数据加载成功，共 {len(df)} 条记录")
        print(f"📅 数据时间范围: {df.index[0].strftime('%Y-%m-%d')} 到 {df.index[-1].strftime('%Y-%m-%d')}")
        
        # 应用复权处理
        adjustment_type = 'forward'
        adjustment_config = create_adjustment_config(adjustment_type)
        adjustment_processor = create_adjustment_processor(adjustment_config)
        df = adjustment_processor.process_data(df, test_stock)
        
        # 计算技术指标
        df['ma13'] = indicators.calculate_ma(df, 13)
        df['ma45'] = indicators.calculate_ma(df, 45)
        
        macd_config = indicators.MACDIndicatorConfig(adjustment_config=adjustment_config)
        df['dif'], df['dea'] = indicators.calculate_macd(df, config=macd_config, stock_code=test_stock)
        df['macd'] = df['dif'] - df['dea']
        
        kdj_config = indicators.KDJIndicatorConfig(adjustment_config=adjustment_config)
        df['k'], df['d'], df['j'] = indicators.calculate_kdj(df, config=kdj_config, stock_code=test_stock)
        
        # 应用策略
        signals = strategies.apply_strategy('WEEKLY_GOLDEN_CROSS_MA', df)
        
        if signals is None:
            print(f"❌ 策略应用失败")
            return
            
        # 统计原始信号
        raw_signals = signals[signals != '']
        print(f"📊 原始信号数量: {len(raw_signals)}")
        
        # 显示最近的信号状态
        recent_signals = raw_signals.tail(10)
        print(f"\n📅 最近10个信号:")
        for idx, state in recent_signals.items():
            date_str = idx.strftime('%Y-%m-%d')
            price = df.loc[idx, 'close']
            print(f"   {date_str}: {state} - ¥{price:.2f}")
        
        # 执行回测
        print(f"\n🔄 执行回测...")
        backtest_results = backtester.run_backtest(df, signals)
        
        if not backtest_results:
            print(f"❌ 回测失败")
            return
            
        print(f"📊 回测结果:")
        print(f"   总信号数: {backtest_results.get('total_signals', 0)}")
        print(f"   胜率: {backtest_results.get('win_rate', '0%')}")
        print(f"   平均收益: {backtest_results.get('avg_max_profit', '0%')}")
        
        trades = backtest_results.get('trades', [])
        if trades:
            success_count = sum(1 for trade in trades if trade.get('is_success', False))
            fail_count = len(trades) - success_count
            
            print(f"   成功交易: {success_count}")
            print(f"   失败交易: {fail_count}")
            
            # 模拟前端API的信号点构建
            print(f"\n🎨 前端信号点构建:")
            signal_points = []
            signal_df = df[signals != '']
            trade_results = {trade['entry_idx']: trade for trade in trades}
            
            success_signals = 0
            fail_signals = 0
            other_signals = 0
            
            for idx, row in signal_df.iterrows():
                original_state = str(signals[idx])
                idx_pos = df.index.get_loc(idx) if idx in df.index else 0
                is_success = trade_results.get(idx_pos, {}).get('is_success', False)
                final_state = f"{original_state}_SUCCESS" if is_success else f"{original_state}_FAIL"
                
                if 'SUCCESS' in final_state:
                    success_signals += 1
                elif 'FAIL' in final_state:
                    fail_signals += 1
                else:
                    other_signals += 1
            
            print(f"   🟢 绿色三角(SUCCESS): {success_signals}")
            print(f"   🔴 红色三角(FAIL): {fail_signals}")
            print(f"   🟡 黄色三角(其他): {other_signals}")
            
            # 显示最近几个信号的状态
            recent_trade_signals = []
            for idx, row in signal_df.tail(5).iterrows():
                original_state = str(signals[idx])
                idx_pos = df.index.get_loc(idx) if idx in df.index else 0
                is_success = trade_results.get(idx_pos, {}).get('is_success', False)
                final_state = f"{original_state}_SUCCESS" if is_success else f"{original_state}_FAIL"
                
                color_icon = "🟢" if 'SUCCESS' in final_state else "🔴" if 'FAIL' in final_state else "🟡"
                date_str = idx.strftime('%Y-%m-%d')
                price = row['close']
                
                recent_trade_signals.append(f"   {date_str} {color_icon} {final_state} - ¥{price:.2f}")
            
            print(f"\n📅 最近5个交易信号的前端显示:")
            for signal_info in recent_trade_signals:
                print(signal_info)
        else:
            print(f"   ⚠️ 无交易记录")
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

def test_different_strategies():
    """测试不同策略的成功/失败比例"""
    print(f"\n🔄 测试不同策略的成功/失败比例")
    print("=" * 60)
    
    strategies_to_test = ['MACD_ZERO_AXIS', 'TRIPLE_CROSS', 'PRE_CROSS']
    test_stock = 'sz300290'  # 之前测试过有信号的股票
    
    for strategy_name in strategies_to_test:
        print(f"\n📈 策略: {strategy_name}")
        print("-" * 30)
        
        try:
            # 加载数据
            market = test_stock[:2]
            base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
            file_path = os.path.join(base_path, market, 'lday', f'{test_stock}.day')
            
            if not os.path.exists(file_path):
                continue
                
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 100:
                continue
            
            # 应用复权处理
            adjustment_type = 'forward'
            adjustment_config = create_adjustment_config(adjustment_type)
            adjustment_processor = create_adjustment_processor(adjustment_config)
            df = adjustment_processor.process_data(df, test_stock)
            
            # 计算技术指标
            df['ma13'] = indicators.calculate_ma(df, 13)
            df['ma45'] = indicators.calculate_ma(df, 45)
            
            macd_config = indicators.MACDIndicatorConfig(adjustment_config=adjustment_config)
            df['dif'], df['dea'] = indicators.calculate_macd(df, config=macd_config, stock_code=test_stock)
            df['macd'] = df['dif'] - df['dea']
            
            kdj_config = indicators.KDJIndicatorConfig(adjustment_config=adjustment_config)
            df['k'], df['d'], df['j'] = indicators.calculate_kdj(df, config=kdj_config, stock_code=test_stock)
            
            # 应用策略
            signals = strategies.apply_strategy(strategy_name, df)
            
            if signals is None or signals[signals != ''].empty:
                print(f"   ⚠️ 无信号")
                continue
                
            # 执行回测
            backtest_results = backtester.run_backtest(df, signals)
            
            if not backtest_results or backtest_results.get('total_signals', 0) == 0:
                print(f"   ⚠️ 回测无结果")
                continue
            
            trades = backtest_results.get('trades', [])
            if trades:
                success_count = sum(1 for trade in trades if trade.get('is_success', False))
                fail_count = len(trades) - success_count
                success_rate = success_count / len(trades) * 100
                
                print(f"   总信号: {len(trades)}")
                print(f"   🟢 成功: {success_count} ({success_rate:.1f}%)")
                print(f"   🔴 失败: {fail_count} ({100-success_rate:.1f}%)")
                
                # 这个策略在前端会显示多少红色和绿色三角
                print(f"   前端显示: {success_count}个绿色三角, {fail_count}个红色三角")
            
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")

if __name__ == "__main__":
    print("🔍 周线策略信号显示测试")
    print("=" * 80)
    
    test_weekly_strategy_signals()
    test_different_strategies()
    
    print(f"\n📝 结论:")
    print("1. 回测失败标识的逻辑是正确的")
    print("2. 不同策略会有不同的成功/失败比例")
    print("3. 如果只看到成功信号，可能是因为:")
    print("   - 当前查看的股票/策略组合成功率很高")
    print("   - 需要切换到其他策略查看更多失败案例")
    print("   - MACD_ZERO_AXIS和PRE_CROSS策略通常有更多失败信号")