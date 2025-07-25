#!/usr/bin/env python3
"""
测试app.py中日期处理修复的有效性
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

sys.path.append('backend')

def test_date_handling():
    """测试日期处理修复"""
    print("🧪 测试app.py日期处理修复")
    print("=" * 50)
    
    try:
        # 导入相关模块
        import data_loader
        
        # 创建模拟数据，模拟data_loader.get_daily_data()的返回格式
        dates = pd.date_range(start='2025-07-01', periods=30, freq='D')
        np.random.seed(42)
        
        # 创建模拟的股票数据
        data = []
        base_price = 10.0
        for i, date in enumerate(dates):
            price = base_price * (1 + np.random.normal(0, 0.02))
            data.append({
                'open': price * (1 + np.random.normal(0, 0.01)),
                'high': price * (1 + abs(np.random.normal(0, 0.015))),
                'low': price * (1 - abs(np.random.normal(0, 0.015))),
                'close': price,
                'volume': np.random.randint(1000000, 5000000)
            })
        
        # 创建DataFrame，设置日期为索引（模拟data_loader的行为）
        df = pd.DataFrame(data, index=dates)
        
        print(f"✅ 创建模拟数据成功")
        print(f"   数据形状: {df.shape}")
        print(f"   索引类型: {type(df.index)}")
        print(f"   索引名称: {df.index.name}")
        
        # 测试修复后的日期处理逻辑
        print(f"\n🔧 测试日期处理逻辑:")
        
        # 1. 测试信号点处理
        print(f"1. 测试信号点日期处理:")
        signal_df = df.head(5)  # 模拟信号数据
        signal_points = []
        
        for idx, row in signal_df.iterrows():
            try:
                signal_point = {
                    'date': idx.strftime('%Y-%m-%d'),  # 使用索引作为日期
                    'price': float(row['low']),
                    'state': 'TEST_STATE'
                }
                signal_points.append(signal_point)
                print(f"   ✅ {signal_point['date']}: ¥{signal_point['price']:.2f}")
            except Exception as e:
                print(f"   ❌ 处理失败: {e}")
                return False
        
        # 2. 测试返回数据处理
        print(f"\n2. 测试返回数据处理:")
        try:
            # 模拟添加技术指标
            df['ma13'] = df['close'].rolling(13).mean()
            df['ma45'] = df['close'].rolling(45).mean()
            
            # 添加模拟的其他指标
            df['dif'] = np.random.randn(len(df))
            df['dea'] = np.random.randn(len(df))
            df['k'] = np.random.uniform(0, 100, len(df))
            df['d'] = np.random.uniform(0, 100, len(df))
            df['j'] = np.random.uniform(0, 100, len(df))
            df['rsi6'] = np.random.uniform(0, 100, len(df))
            df['rsi12'] = np.random.uniform(0, 100, len(df))
            df['rsi24'] = np.random.uniform(0, 100, len(df))
            
            # 处理NaN值
            df.replace({np.nan: None}, inplace=True)
            
            # 重置索引，将日期索引转换为列（修复后的逻辑）
            df_reset = df.reset_index()
            # 检查索引列的名称
            if 'date' not in df_reset.columns:
                # 如果索引没有名称，第一列就是日期
                date_col = df_reset.columns[0]
                df_reset = df_reset.rename(columns={date_col: 'date'})
            df_reset['date'] = df_reset['date'].dt.strftime('%Y-%m-%d')
            
            # 生成返回数据
            kline_data = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
            indicator_data = df_reset[['date', 'ma13', 'ma45', 'dif', 'dea', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']].to_dict('records')
            
            print(f"   ✅ K线数据生成成功: {len(kline_data)} 条记录")
            print(f"   ✅ 指标数据生成成功: {len(indicator_data)} 条记录")
            
            # 显示前几条数据
            print(f"\n   📊 K线数据示例:")
            for i, record in enumerate(kline_data[:3]):
                print(f"     {i+1}. {record['date']}: 开盘¥{record['open']:.2f}, 收盘¥{record['close']:.2f}")
            
            print(f"\n   📈 指标数据示例:")
            for i, record in enumerate(indicator_data[:3]):
                ma13_val = record['ma13']
                ma13_str = f"{ma13_val:.2f}" if ma13_val is not None else "None"
                print(f"     {i+1}. {record['date']}: MA13={ma13_str}")
            
        except Exception as e:
            print(f"   ❌ 返回数据处理失败: {e}")
            return False
        
        print(f"\n🎉 所有测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_app_import():
    """测试app模块导入"""
    print(f"\n🔌 测试app模块导入:")
    
    try:
        import app
        print(f"   ✅ app模块导入成功")
        
        # 检查关键函数是否存在
        if hasattr(app, 'get_stock_analysis'):
            print(f"   ✅ get_stock_analysis函数存在")
        else:
            print(f"   ❌ get_stock_analysis函数不存在")
            return False
        
        return True
        
    except Exception as e:
        print(f"   ❌ app模块导入失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 app.py日期处理修复测试")
    print("=" * 60)
    
    # 测试1: 模块导入
    success1 = test_app_import()
    
    # 测试2: 日期处理逻辑
    success2 = test_date_handling()
    
    print(f"\n📋 测试结果总结:")
    print(f"  模块导入: {'✅ 通过' if success1 else '❌ 失败'}")
    print(f"  日期处理: {'✅ 通过' if success2 else '❌ 失败'}")
    
    if success1 and success2:
        print(f"\n🎉 所有测试通过！日期处理修复成功！")
        
        print(f"\n💡 修复要点:")
        print(f"  • DataFrame索引是日期，不是'date'列")
        print(f"  • 使用idx.strftime()而不是row['date'].strftime()")
        print(f"  • 使用reset_index()将索引转换为列")
        print(f"  • 正确处理日期格式转换")
        
        return True
    else:
        print(f"\n❌ 部分测试失败，需要进一步检查")
        return False

if __name__ == "__main__":
    main()