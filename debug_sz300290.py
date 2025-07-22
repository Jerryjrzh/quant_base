#!/usr/bin/env python3
"""
专门验证sz300290的5分钟线数据解析
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
from datetime import datetime
import data_loader

def debug_sz300290_data():
    """调试sz300290的数据解析"""
    print("🔍 调试sz300290数据解析")
    print("=" * 60)
    
    stock_code = 'sz300290'
    
    try:
        # 获取多周期数据
        print(f"📊 加载 {stock_code} 的多周期数据...")
        multi_data = data_loader.get_multi_timeframe_data(stock_code)
        
        print(f"股票代码: {multi_data['stock_code']}")
        print(f"日线数据可用: {multi_data['data_status']['daily_available']}")
        print(f"5分钟数据可用: {multi_data['data_status']['min5_available']}")
        
        # 详细检查日线数据
        if multi_data['daily_data'] is not None:
            daily_df = multi_data['daily_data']
            print(f"\n📈 日线数据详情:")
            print(f"  数据量: {len(daily_df)} 条")
            print(f"  数据列: {list(daily_df.columns)}")
            print(f"  数据类型: {daily_df.dtypes.to_dict()}")
            
            if len(daily_df) > 0:
                print(f"  日期范围: {daily_df['date'].min()} 到 {daily_df['date'].max()}")
                print(f"  价格范围: {daily_df['close'].min():.2f} - {daily_df['close'].max():.2f}")
                
                # 显示最近10天的数据
                print(f"\n  最近10天日线数据:")
                recent_daily = daily_df.tail(10)[['date', 'open', 'high', 'low', 'close', 'volume']]
                for idx, row in recent_daily.iterrows():
                    print(f"    {row['date']}: O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f} V:{row['volume']}")
        
        # 详细检查5分钟数据
        if multi_data['min5_data'] is not None:
            min5_df = multi_data['min5_data']
            print(f"\n🕐 5分钟数据详情:")
            print(f"  数据量: {len(min5_df)} 条")
            print(f"  数据列: {list(min5_df.columns)}")
            print(f"  数据类型: {min5_df.dtypes.to_dict()}")
            
            if len(min5_df) > 0:
                print(f"  时间范围: {min5_df['datetime'].min()} 到 {min5_df['datetime'].max()}")
                print(f"  价格范围: {min5_df['close'].min():.2f} - {min5_df['close'].max():.2f}")
                
                # 检查数据异常
                print(f"\n  数据质量检查:")
                print(f"    价格为0的记录: {(min5_df['close'] <= 0).sum()}")
                print(f"    价格异常高的记录 (>1000): {(min5_df['close'] > 1000).sum()}")
                print(f"    价格异常低的记录 (<1): {(min5_df['close'] < 1).sum()}")
                print(f"    成交量为0的记录: {(min5_df['volume'] <= 0).sum()}")
                
                # 显示最近20条5分钟数据
                print(f"\n  最近20条5分钟数据:")
                recent_min5 = min5_df.tail(20)[['datetime', 'open', 'high', 'low', 'close', 'volume']]
                for idx, row in recent_min5.iterrows():
                    print(f"    {row['datetime']}: O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f} V:{row['volume']}")
                
                # 检查价格连续性
                print(f"\n  价格连续性检查:")
                price_changes = min5_df['close'].pct_change().dropna()
                large_changes = price_changes[abs(price_changes) > 0.1]  # 超过10%的变化
                print(f"    超过10%变化的记录数: {len(large_changes)}")
                if len(large_changes) > 0:
                    print(f"    最大涨幅: {price_changes.max():.2%}")
                    print(f"    最大跌幅: {price_changes.min():.2%}")
        
        # 检查数据文件是否存在
        base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        market = stock_code[:2]
        daily_file = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
        min5_file = os.path.join(base_path, market, 'fzline', f'{stock_code}.lc5')
        
        print(f"\n📁 数据文件检查:")
        print(f"  日线文件: {daily_file}")
        print(f"  文件存在: {os.path.exists(daily_file)}")
        if os.path.exists(daily_file):
            print(f"  文件大小: {os.path.getsize(daily_file)} 字节")
        
        print(f"  5分钟文件: {min5_file}")
        print(f"  文件存在: {os.path.exists(min5_file)}")
        if os.path.exists(min5_file):
            print(f"  文件大小: {os.path.getsize(min5_file)} 字节")
        
        return multi_data
        
    except Exception as e:
        print(f"❌ 数据加载失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_sz300290_price_calculation():
    """测试sz300290的价格计算逻辑"""
    print("\n💰 测试sz300290价格计算逻辑")
    print("=" * 60)
    
    try:
        # 直接加载日线数据
        base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        market = 'sz'
        file_path = os.path.join(base_path, market, 'lday', 'sz300290.day')
        
        if not os.path.exists(file_path):
            print(f"❌ 日线数据文件不存在: {file_path}")
            return
        
        df = data_loader.get_daily_data(file_path)
        if df is None:
            print("❌ 无法加载日线数据")
            return
        
        df.set_index('date', inplace=True)
        
        print(f"📊 日线数据加载成功: {len(df)} 条记录")
        print(f"价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
        
        # 显示最近的价格数据
        print(f"\n最近10天价格数据:")
        recent_data = df.tail(10)[['open', 'high', 'low', 'close', 'volume']]
        for date, row in recent_data.iterrows():
            print(f"  {date}: O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f}")
        
        # 测试交易建议的价格计算
        print(f"\n🎯 测试交易建议价格计算:")
        from trading_advisor import TradingAdvisor
        import strategies
        import indicators
        
        # 计算技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        # 生成信号
        signals = strategies.apply_macd_zero_axis_strategy(df)
        
        # 找到最近的信号
        recent_signals = signals[signals != ''].tail(5)
        if not recent_signals.empty:
            latest_signal_date = recent_signals.index[-1]
            latest_signal_idx = df.index.get_loc(latest_signal_date)
            latest_signal_state = recent_signals.iloc[-1]
            current_price = df.iloc[latest_signal_idx]['close']
            
            print(f"最新信号: {latest_signal_date}, 状态: {latest_signal_state}")
            print(f"信号当天价格: ¥{current_price:.2f}")
            
            # 获取交易建议
            advisor = TradingAdvisor()
            advice = advisor.get_entry_recommendations(df, latest_signal_idx, latest_signal_state, current_price)
            
            if 'error' not in advice and 'entry_strategies' in advice:
                print(f"\n入场策略计算:")
                for i, strategy in enumerate(advice['entry_strategies'], 1):
                    print(f"  策略{i}: {strategy['strategy']}")
                    print(f"    当前价格: ¥{current_price:.2f}")
                    print(f"    目标价位1: ¥{strategy['entry_price_1']}")
                    print(f"    目标价位2: ¥{strategy['entry_price_2']}")
                    print(f"    价位1折扣: {(current_price - strategy['entry_price_1']) / current_price:.1%}")
                    print(f"    价位2折扣: {(current_price - strategy['entry_price_2']) / current_price:.1%}")
            
            if 'risk_management' in advice and 'stop_loss_levels' in advice['risk_management']:
                stops = advice['risk_management']['stop_loss_levels']
                print(f"\n止损位计算:")
                print(f"  当前价格: ¥{current_price:.2f}")
                print(f"  保守止损: ¥{stops.get('conservative', 'N/A')} ({(stops.get('conservative', current_price) - current_price) / current_price:.1%})")
                print(f"  适中止损: ¥{stops.get('moderate', 'N/A')} ({(stops.get('moderate', current_price) - current_price) / current_price:.1%})")
                print(f"  激进止损: ¥{stops.get('aggressive', 'N/A')} ({(stops.get('aggressive', current_price) - current_price) / current_price:.1%})")
                print(f"  技术止损: ¥{stops.get('technical', 'N/A')} ({(stops.get('technical', current_price) - current_price) / current_price:.1%})")
        
    except Exception as e:
        print(f"❌ 价格计算测试失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主函数"""
    print("🔍 sz300290 数据解析调试")
    print("=" * 80)
    
    # 调试数据解析
    multi_data = debug_sz300290_data()
    
    # 测试价格计算
    test_sz300290_price_calculation()
    
    print("\n" + "=" * 80)
    print("🎯 调试总结:")
    if multi_data:
        print("✅ 数据加载成功")
        if multi_data['data_status']['daily_available']:
            print("✅ 日线数据可用")
        if multi_data['data_status']['min5_available']:
            print("✅ 5分钟数据可用")
    else:
        print("❌ 数据加载失败")

if __name__ == "__main__":
    main()