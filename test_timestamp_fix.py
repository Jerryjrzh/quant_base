#!/usr/bin/env python3
"""
测试时间戳算术修复
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backtester import run_backtest

def test_timestamp_arithmetic_fix():
    """测试时间戳算术修复"""
    print("🔧 测试时间戳算术修复...")
    
    try:
        # 创建测试数据
        dates = pd.date_range(start='2023-06-01', end='2023-07-01', freq='D')
        np.random.seed(42)
        
        test_data = pd.DataFrame({
            'open': 100 + np.random.randn(len(dates)) * 2,
            'high': 102 + np.random.randn(len(dates)) * 2,
            'low': 98 + np.random.randn(len(dates)) * 2,
            'close': 100 + np.random.randn(len(dates)) * 2,
            'volume': np.random.randint(1000000, 10000000, len(dates))
        }, index=dates)
        
        # 确保价格逻辑正确
        for i in range(len(test_data)):
            row = test_data.iloc[i]
            high = max(row['open'], row['close']) + abs(np.random.randn() * 0.5)
            low = min(row['open'], row['close']) - abs(np.random.randn() * 0.5)
            test_data.iloc[i, test_data.columns.get_loc('high')] = high
            test_data.iloc[i, test_data.columns.get_loc('low')] = low
        
        print(f"✅ 创建测试数据: {len(test_data)} 条记录")
        print(f"   日期范围: {test_data.index[0]} 到 {test_data.index[-1]}")
        
        # 创建一些模拟信号
        signal_series = pd.Series(0, index=test_data.index)
        # 在2023-06-09添加信号（这是错误消息中提到的日期）
        if pd.Timestamp('2023-06-09') in signal_series.index:
            signal_series.loc['2023-06-09'] = 1
            print("✅ 在2023-06-09添加测试信号")
        
        # 添加更多信号用于测试
        signal_dates = ['2023-06-15', '2023-06-20', '2023-06-25']
        for date in signal_dates:
            if pd.Timestamp(date) in signal_series.index:
                signal_series.loc[date] = 1
        
        print(f"✅ 总共添加 {signal_series.sum()} 个测试信号")
        
        # 运行回测
        print("\n🚀 运行回测测试...")
        result = run_backtest(test_data, signal_series)
        
        if 'error' in result:
            print(f"❌ 回测失败: {result['error']}")
            return False
        else:
            print("✅ 回测成功完成!")
            print(f"   总信号数: {result.get('total_signals', 0)}")
            print(f"   有效交易: {result.get('total_trades', 0)}")
            print(f"   胜率: {result.get('win_rate', 0):.1%}")
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🎯 时间戳算术修复测试")
    print("=" * 50)
    
    success = test_timestamp_arithmetic_fix()
    
    print("\n" + "=" * 50)
    if success:
        print("✅ 时间戳算术修复测试通过!")
        print("   现在可以正常处理pandas Timestamp对象了")
    else:
        print("❌ 时间戳算术修复测试失败!")
        print("   需要进一步检查和修复")

if __name__ == "__main__":
    main()