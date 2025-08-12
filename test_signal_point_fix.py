#!/usr/bin/env python3
"""
测试信号点位置修复
验证K线图上的三角符号是否显示在正确的价格位置
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

def test_signal_point_positioning():
    """测试信号点定位修复"""
    print("🔧 测试信号点位置修复")
    print("=" * 60)
    
    # 测试股票代码
    test_stocks = ['sz300290', 'sz000001', 'sh600036']
    
    for stock_code in test_stocks:
        print(f"\n📊 测试股票: {stock_code}")
        print("-" * 40)
        
        try:
            # 加载数据
            market = stock_code[:2]
            base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
            file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
            
            if not os.path.exists(file_path):
                print(f"❌ 数据文件不存在: {file_path}")
                continue
                
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 100:
                print(f"❌ 数据加载失败或数据不足")
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
            strategy_name = 'WEEKLY_GOLDEN_CROSS_MA'
            signals = strategies.apply_strategy(strategy_name, df)
            
            if signals is None:
                print(f"❌ 策略应用失败")
                continue
                
            # 执行回测
            backtest_results = backtester.run_backtest(df, signals)
            
            if not backtest_results or backtest_results.get('total_signals', 0) == 0:
                print(f"⚠️ 无有效信号")
                continue
            
            # 分析信号点
            print(f"✅ 发现 {backtest_results['total_signals']} 个信号")
            
            # 构建信号点（使用修复后的逻辑）
            signal_points = []
            if signals is not None and not signals[signals != ''].empty:
                signal_df = df[signals != '']
                trade_results = {trade['entry_idx']: trade for trade in backtest_results.get('trades', [])}
                
                print(f"\n📍 信号点分析:")
                for i, (idx, row) in enumerate(signal_df.iterrows()):
                    if i >= 5:  # 只显示前5个信号
                        break
                        
                    original_state = str(signals[idx])
                    idx_pos = df.index.get_loc(idx) if idx in df.index else 0
                    is_success = trade_results.get(idx_pos, {}).get('is_success', False)
                    final_state = f"{original_state}_SUCCESS" if is_success else f"{original_state}_FAIL"
                    
                    # 修复后的价格逻辑
                    actual_entry_price = trade_results.get(idx_pos, {}).get('entry_price')
                    if actual_entry_price is not None:
                        display_price = float(actual_entry_price)
                        price_source = "回测入场价"
                    else:
                        display_price = float(row['close'])
                        price_source = "收盘价(备选)"
                    
                    # 对比修复前后的价格差异
                    old_price = float(row['low'])  # 修复前使用的价格
                    price_diff = display_price - old_price
                    price_diff_pct = (price_diff / old_price) * 100
                    
                    date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)
                    
                    print(f"  {i+1}. {date_str} - {final_state}")
                    print(f"     修复前价格(最低价): ¥{old_price:.2f}")
                    print(f"     修复后价格({price_source}): ¥{display_price:.2f}")
                    print(f"     价格差异: ¥{price_diff:+.2f} ({price_diff_pct:+.1f}%)")
                    print(f"     当日价格区间: ¥{row['low']:.2f} - ¥{row['high']:.2f}")
                    
                    if actual_entry_price is not None:
                        entry_strategy = trade_results.get(idx_pos, {}).get('entry_strategy', '未知')
                        print(f"     入场策略: {entry_strategy}")
                    
                    print()
            
            print(f"📈 回测统计:")
            print(f"   胜率: {backtest_results.get('win_rate', '0%')}")
            print(f"   平均收益: {backtest_results.get('avg_max_profit', '0%')}")
            print(f"   平均回撤: {backtest_results.get('avg_max_drawdown', '0%')}")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()

def test_price_positioning_accuracy():
    """测试价格定位准确性"""
    print(f"\n🎯 价格定位准确性测试")
    print("=" * 60)
    
    # 创建模拟数据进行精确测试
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)  # 固定随机种子确保可重复
    
    # 生成模拟价格数据
    base_price = 10.0
    prices = []
    for i in range(100):
        # 模拟价格波动
        change = np.random.normal(0, 0.02)  # 2%的日波动
        base_price *= (1 + change)
        
        # 生成OHLC数据
        high = base_price * (1 + abs(np.random.normal(0, 0.01)))
        low = base_price * (1 - abs(np.random.normal(0, 0.01)))
        open_price = base_price * (1 + np.random.normal(0, 0.005))
        close = base_price
        
        prices.append({
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': np.random.randint(1000000, 10000000)
        })
    
    df = pd.DataFrame(prices, index=dates)
    
    # 计算指标
    df['ma13'] = indicators.calculate_ma(df, 13)
    df['ma45'] = indicators.calculate_ma(df, 45)
    df['dif'], df['dea'] = indicators.calculate_macd(df)
    df['k'], df['d'], df['j'] = indicators.calculate_kdj(df)
    
    # 创建模拟信号（在特定位置）
    signals = pd.Series('', index=df.index)
    signal_dates = [dates[20], dates[40], dates[60], dates[80]]
    signal_states = ['PRE', 'MID', 'POST', 'MID']
    
    for date, state in zip(signal_dates, signal_states):
        signals[date] = state
    
    # 执行回测
    backtest_results = backtester.run_backtest(df, signals)
    
    print(f"📊 模拟数据测试结果:")
    print(f"   信号数量: {backtest_results.get('total_signals', 0)}")
    
    if backtest_results.get('trades'):
        print(f"\n📍 入场价格分析:")
        for i, trade in enumerate(backtest_results['trades'][:3]):  # 显示前3个交易
            entry_idx = trade['entry_idx']
            signal_state = trade['signal_state']
            entry_price = trade['entry_price']
            entry_strategy = trade['entry_strategy']
            
            # 获取对应日期的价格数据
            row = df.iloc[entry_idx]
            date_str = df.index[entry_idx].strftime('%Y-%m-%d')
            
            print(f"  {i+1}. {date_str} - {signal_state}状态")
            print(f"     入场价格: ¥{entry_price:.2f}")
            print(f"     入场策略: {entry_strategy}")
            print(f"     当日OHLC: 开¥{row['open']:.2f} 高¥{row['high']:.2f} 低¥{row['low']:.2f} 收¥{row['close']:.2f}")
            
            # 验证入场价格的合理性
            if row['low'] <= entry_price <= row['high']:
                print(f"     ✅ 入场价格在合理区间内")
            else:
                print(f"     ❌ 入场价格超出当日价格区间！")
            
            print()

if __name__ == "__main__":
    print("🔧 信号点位置修复测试")
    print("=" * 80)
    
    test_signal_point_positioning()
    test_price_positioning_accuracy()
    
    print("\n✅ 测试完成！")
    print("\n📝 修复说明:")
    print("1. 修复前：信号点固定显示在K线最低价位置")
    print("2. 修复后：信号点显示在回测实际使用的入场价格位置")
    print("3. 这样可以确保前端显示与回测逻辑一致")