#!/usr/bin/env python3
"""
调试筛选器问题
"""
import os
import glob
import sys
sys.path.append('backend')

import data_loader
import strategies
import indicators

# 配置
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz', 'bj']

def test_single_stock():
    """测试单只股票的处理流程"""
    print("🔍 开始调试筛选器...")
    
    # 找到一些测试文件
    all_files = []
    for market in MARKETS:
        path = os.path.join(BASE_PATH, market, 'lday', '*.day')
        files = glob.glob(path)
        if files:
            all_files.extend(files[:5])  # 只取前5个文件测试
            break
    
    if not all_files:
        print("❌ 未找到任何日线文件")
        return
    
    print(f"📊 找到 {len(all_files)} 个测试文件")
    
    for file_path in all_files:
        stock_code = os.path.basename(file_path).split('.')[0]
        print(f"\n🔍 测试股票: {stock_code}")
        
        try:
            # 1. 测试数据加载
            df = data_loader.get_daily_data(file_path)
            if df is None:
                print(f"  ❌ 数据加载失败")
                continue
            
            print(f"  ✅ 数据加载成功: {len(df)} 条记录")
            print(f"  📅 数据范围: {df.index[0].strftime('%Y-%m-%d')} 到 {df.index[-1].strftime('%Y-%m-%d')}")
            
            # 2. 测试技术指标计算
            try:
                macd_values = indicators.calculate_macd(df)
                df['dif'], df['dea'] = macd_values[0], macd_values[1]
                print(f"  ✅ MACD计算成功")
            except Exception as e:
                print(f"  ❌ MACD计算失败: {e}")
                continue
            
            # 3. 测试策略应用
            try:
                signal_series = strategies.apply_macd_zero_axis_strategy(df)
                if signal_series is not None:
                    # 统计信号
                    pre_signals = (signal_series == 'PRE').sum()
                    mid_signals = (signal_series == 'MID').sum()
                    post_signals = (signal_series == 'POST').sum()
                    total_signals = pre_signals + mid_signals + post_signals
                    
                    print(f"  ✅ 策略应用成功")
                    print(f"    📊 PRE信号: {pre_signals}")
                    print(f"    📊 MID信号: {mid_signals}")
                    print(f"    📊 POST信号: {post_signals}")
                    print(f"    📊 总信号数: {total_signals}")
                    
                    # 检查最新信号
                    latest_signal = signal_series.iloc[-1]
                    if latest_signal in ['PRE', 'MID', 'POST']:
                        print(f"  🎯 最新信号: {latest_signal} ✅")
                    else:
                        print(f"  ⚪ 最新信号: 无")
                        
                else:
                    print(f"  ❌ 策略返回None")
                    
            except Exception as e:
                print(f"  ❌ 策略应用失败: {e}")
                import traceback
                traceback.print_exc()
                continue
                
        except Exception as e:
            print(f"  ❌ 处理失败: {e}")
            continue

if __name__ == '__main__':
    test_single_stock()