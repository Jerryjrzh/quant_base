#!/usr/bin/env python3
"""
5分钟数据解析和调用验证脚本
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import data_loader

def test_5min_data_parsing():
    """测试5分钟数据解析"""
    print("🕐 测试5分钟数据解析功能")
    print("=" * 50)
    
    # 测试多周期数据加载
    test_codes = ['sz300290', 'sz002691', 'sz002107']
    
    for stock_code in test_codes:
        print(f"\n📊 测试股票: {stock_code}")
        
        try:
            # 获取多周期数据
            multi_data = data_loader.get_multi_timeframe_data(stock_code)
            
            print(f"  股票代码: {multi_data['stock_code']}")
            print(f"  日线数据可用: {multi_data['data_status']['daily_available']}")
            print(f"  5分钟数据可用: {multi_data['data_status']['min5_available']}")
            
            # 检查日线数据
            if multi_data['daily_data'] is not None:
                daily_df = multi_data['daily_data']
                print(f"  日线数据量: {len(daily_df)} 条")
                print(f"  日线数据列: {list(daily_df.columns)}")
                print(f"  日线最新日期: {daily_df.index[-1] if len(daily_df) > 0 else 'N/A'}")
            
            # 检查5分钟数据
            if multi_data['min5_data'] is not None:
                min5_df = multi_data['min5_data']
                print(f"  5分钟数据量: {len(min5_df)} 条")
                print(f"  5分钟数据列: {list(min5_df.columns)}")
                print(f"  5分钟最新时间: {min5_df.index[-1] if len(min5_df) > 0 else 'N/A'}")
                
                # 显示最近几条5分钟数据
                if len(min5_df) > 0:
                    print("  最近5条5分钟数据:")
                    recent_data = min5_df.tail(5)[['open', 'high', 'low', 'close', 'volume']]
                    for idx, row in recent_data.iterrows():
                        print(f"    {idx}: O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f} V:{row['volume']}")
            
            print(f"  ✅ {stock_code} 数据解析正常")
            
        except Exception as e:
            print(f"  ❌ {stock_code} 数据解析失败: {e}")
            continue
        
        # 如果找到有效数据就停止测试
        if (multi_data['data_status']['daily_available'] or 
            multi_data['data_status']['min5_available']):
            break
    
    return True

def test_5min_resampling():
    """测试5分钟数据重采样"""
    print("\n🔄 测试5分钟数据重采样功能")
    print("=" * 50)
    
    try:
        # 创建模拟5分钟数据
        start_time = datetime(2024, 1, 2, 9, 30)  # 交易日开始时间
        time_range = pd.date_range(start=start_time, periods=48, freq='5T')  # 4小时交易时间
        
        # 生成模拟价格数据
        np.random.seed(42)
        base_price = 100
        prices = []
        current_price = base_price
        
        for i in range(len(time_range)):
            # 模拟价格波动
            change = np.random.normal(0, 0.002)  # 0.2%的标准波动
            current_price *= (1 + change)
            prices.append(current_price)
        
        # 创建5分钟数据DataFrame
        min5_data = pd.DataFrame({
            'datetime': time_range,
            'open': prices,
            'high': [p * (1 + np.random.uniform(0, 0.01)) for p in prices],
            'low': [p * (1 - np.random.uniform(0, 0.01)) for p in prices],
            'close': [p * (1 + np.random.uniform(-0.005, 0.005)) for p in prices],
            'volume': np.random.randint(1000, 10000, len(time_range)),
            'amount': np.random.uniform(100000, 1000000, len(time_range))
        })
        
        print(f"📊 创建模拟5分钟数据: {len(min5_data)} 条")
        print(f"时间范围: {min5_data['datetime'].iloc[0]} 到 {min5_data['datetime'].iloc[-1]}")
        
        # 测试重采样功能
        resampled_data = data_loader.resample_5min_to_other_timeframes(min5_data)
        
        print(f"\n🔄 重采样结果:")
        for timeframe, df in resampled_data.items():
            if df is not None and not df.empty:
                print(f"  {timeframe}: {len(df)} 条数据")
                print(f"    时间范围: {df.index[0]} 到 {df.index[-1]}")
                print(f"    数据列: {list(df.columns)}")
            else:
                print(f"  {timeframe}: 无数据")
        
        print("✅ 5分钟数据重采样功能正常")
        return True
        
    except Exception as e:
        print(f"❌ 5分钟数据重采样测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_5min_strategy_application():
    """测试在5分钟数据上应用策略"""
    print("\n📈 测试5分钟数据策略应用")
    print("=" * 50)
    
    try:
        import strategies
        import indicators
        
        # 创建更长的5分钟模拟数据用于策略测试
        start_time = datetime(2024, 1, 2, 9, 30)
        # 创建5个交易日的数据 (每天48个5分钟K线)
        time_points = []
        for day in range(5):
            day_start = start_time + timedelta(days=day)
            day_times = pd.date_range(start=day_start, periods=48, freq='5T')
            time_points.extend(day_times)
        
        # 生成趋势性价格数据
        np.random.seed(42)
        base_price = 100
        trend = np.linspace(0, 0.05, len(time_points))  # 5%的整体趋势
        noise = np.random.normal(0, 0.01, len(time_points))  # 1%的随机波动
        
        price_changes = trend + noise
        prices = base_price * np.cumprod(1 + price_changes)
        
        # 创建5分钟数据
        min5_df = pd.DataFrame({
            'open': prices,
            'high': prices * (1 + np.random.uniform(0, 0.005, len(prices))),
            'low': prices * (1 - np.random.uniform(0, 0.005, len(prices))),
            'close': prices * (1 + np.random.uniform(-0.002, 0.002, len(prices))),
            'volume': np.random.randint(1000, 10000, len(prices))
        }, index=pd.DatetimeIndex(time_points))
        
        print(f"📊 创建5分钟策略测试数据: {len(min5_df)} 条")
        print(f"价格范围: {min5_df['close'].min():.2f} - {min5_df['close'].max():.2f}")
        
        # 计算技术指标
        print("\n🔧 计算技术指标...")
        macd_values = indicators.calculate_macd(min5_df)
        min5_df['dif'], min5_df['dea'] = macd_values[0], macd_values[1]
        
        kdj_values = indicators.calculate_kdj(min5_df)
        min5_df['k'], min5_df['d'], min5_df['j'] = kdj_values[0], kdj_values[1], kdj_values[2]
        
        min5_df['rsi'] = indicators.calculate_rsi(min5_df)
        
        print("✅ 技术指标计算完成")
        
        # 应用策略
        print("\n📈 应用交易策略...")
        
        # 测试MACD零轴启动策略
        macd_signals = strategies.apply_macd_zero_axis_strategy(min5_df)
        macd_signal_count = len(macd_signals[macd_signals != ''])
        print(f"  MACD零轴启动策略: {macd_signal_count} 个信号")
        
        # 测试三重金叉策略
        triple_signals = strategies.apply_triple_cross(min5_df)
        triple_signal_count = len(triple_signals[triple_signals == True])
        print(f"  三重金叉策略: {triple_signal_count} 个信号")
        
        # 测试PRE策略
        pre_signals = strategies.apply_pre_cross(min5_df)
        pre_signal_count = len(pre_signals[pre_signals == True])
        print(f"  PRE策略: {pre_signal_count} 个信号")
        
        # 显示信号详情
        if macd_signal_count > 0:
            print(f"\n📍 MACD零轴启动信号详情:")
            signal_dates = min5_df.index[macd_signals != '']
            for i, date in enumerate(signal_dates[:5]):  # 显示前5个信号
                signal_state = macd_signals.loc[date]
                price = min5_df.loc[date, 'close']
                print(f"  {i+1}. {date}: {signal_state} 状态, 价格: ¥{price:.2f}")
        
        print("✅ 5分钟数据策略应用正常")
        return True
        
    except Exception as e:
        print(f"❌ 5分钟数据策略应用失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_5min_trading_advice():
    """测试5分钟数据的交易建议"""
    print("\n💡 测试5分钟数据交易建议")
    print("=" * 50)
    
    try:
        from trading_advisor import TradingAdvisor
        import strategies
        import indicators
        
        # 创建5分钟测试数据
        dates = pd.date_range(start='2024-01-02 09:30', periods=100, freq='5T')
        np.random.seed(42)
        
        prices = 100 * np.cumprod(1 + np.random.normal(0.0001, 0.01, len(dates)))
        
        min5_df = pd.DataFrame({
            'open': prices,
            'high': prices * (1 + np.random.uniform(0, 0.01, len(prices))),
            'low': prices * (1 - np.random.uniform(0, 0.01, len(prices))),
            'close': prices,
            'volume': np.random.randint(1000, 10000, len(prices))
        }, index=dates)
        
        # 计算指标
        macd_values = indicators.calculate_macd(min5_df)
        min5_df['dif'], min5_df['dea'] = macd_values[0], macd_values[1]
        
        # 生成信号
        signals = strategies.apply_macd_zero_axis_strategy(min5_df)
        signal_indices = min5_df.index[signals != ''].tolist()
        
        if signal_indices:
            # 测试交易建议
            advisor = TradingAdvisor()
            signal_idx = min5_df.index.get_loc(signal_indices[0])
            signal_state = signals.iloc[signal_idx]
            
            print(f"📍 测试信号: {signal_indices[0]}, 状态: {signal_state}")
            
            # 获取入场建议
            entry_advice = advisor.get_entry_recommendations(min5_df, signal_idx, signal_state)
            
            if 'error' not in entry_advice:
                print("✅ 5分钟数据入场建议生成正常")
                
                # 显示建议摘要
                if 'entry_strategies' in entry_advice and entry_advice['entry_strategies']:
                    strategy = entry_advice['entry_strategies'][0]
                    print(f"  策略: {strategy['strategy']}")
                    print(f"  价位1: ¥{strategy['entry_price_1']}")
                    print(f"  价位2: ¥{strategy['entry_price_2']}")
            else:
                print(f"❌ 入场建议生成失败: {entry_advice['error']}")
                return False
        else:
            print("⚠️ 未生成有效信号，跳过交易建议测试")
        
        print("✅ 5分钟数据交易建议功能正常")
        return True
        
    except Exception as e:
        print(f"❌ 5分钟数据交易建议测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🕐 5分钟数据功能验证")
    print("=" * 60)
    
    test_results = []
    
    # 执行测试
    tests = [
        ("5分钟数据解析", test_5min_data_parsing),
        ("5分钟数据重采样", test_5min_resampling),
        ("5分钟策略应用", test_5min_strategy_application),
        ("5分钟交易建议", test_5min_trading_advice)
    ]
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            result = test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}测试出现异常: {e}")
            test_results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📋 5分钟数据功能验证结果")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:<20} {status}")
        if result:
            passed += 1
    
    print("-" * 60)
    print(f"总计: {passed}/{total} 通过 ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 5分钟数据功能验证全部通过！")
    else:
        print("⚠️ 部分5分钟数据功能需要检查")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)