#!/usr/bin/env python3
"""
测试周线金叉+日线MA策略
验证新策略的功能和信号生成
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

# 导入策略模块
from strategies import (
    apply_weekly_golden_cross_ma_strategy,
    get_strategy_config,
    list_available_strategies,
    get_strategy_description
)
from data_loader import DataLoader

def generate_test_data(days=500):
    """生成测试数据"""
    print("生成测试数据...")
    
    # 生成日期序列
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # 生成价格数据（模拟上升趋势）
    np.random.seed(42)
    base_price = 10.0
    price_trend = np.linspace(0, 0.5, len(dates))  # 上升趋势
    noise = np.random.normal(0, 0.02, len(dates))  # 噪声
    
    close_prices = base_price * (1 + price_trend + noise)
    
    # 生成OHLC数据
    data = []
    for i, (date, close) in enumerate(zip(dates, close_prices)):
        if i == 0:
            open_price = close
        else:
            open_price = close_prices[i-1] * (1 + np.random.normal(0, 0.005))
        
        high = max(open_price, close) * (1 + abs(np.random.normal(0, 0.01)))
        low = min(open_price, close) * (1 - abs(np.random.normal(0, 0.01)))
        volume = np.random.randint(1000000, 5000000)
        
        data.append({
            'date': date,
            'open': open_price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    df = pd.DataFrame(data)
    df.set_index('date', inplace=True)
    
    return df

def test_strategy_basic():
    """基本策略测试"""
    print("\n=== 基本策略测试 ===")
    
    # 生成测试数据
    df = generate_test_data(300)
    print(f"测试数据: {len(df)} 天")
    
    # 获取策略配置
    config = get_strategy_config('WEEKLY_GOLDEN_CROSS_MA')
    print(f"策略配置: {config}")
    
    # 应用策略
    try:
        signals = apply_weekly_golden_cross_ma_strategy(df, config=config)
        print(f"信号生成成功，共 {len(signals)} 个信号")
        
        # 统计信号分布
        signal_counts = signals.value_counts()
        print(f"信号分布: {signal_counts}")
        
        # 显示最近的信号
        recent_signals = signals[signals != ''].tail(10)
        if not recent_signals.empty:
            print("\n最近的信号:")
            for date, signal in recent_signals.items():
                print(f"  {date.strftime('%Y-%m-%d')}: {signal}")
        else:
            print("没有生成信号")
            
        return True
        
    except Exception as e:
        print(f"策略测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_with_real_data():
    """使用真实数据测试"""
    print("\n=== 真实数据测试 ===")
    
    try:
        # 尝试加载真实数据
        data_loader = DataLoader()
        
        # 测试几个股票代码
        test_symbols = ['000001', '000002', '600000', '600036']
        
        for symbol in test_symbols:
            print(f"\n测试股票: {symbol}")
            
            try:
                # 加载数据
                df = data_loader.load_stock_data(symbol, days=365)
                
                if df is None or df.empty:
                    print(f"  无法加载 {symbol} 的数据")
                    continue
                
                print(f"  数据长度: {len(df)} 天")
                
                # 应用策略
                signals = apply_weekly_golden_cross_ma_strategy(df)
                
                # 统计信号
                signal_counts = signals.value_counts()
                print(f"  信号分布: {signal_counts}")
                
                # 显示最近的信号
                recent_signals = signals[signals != ''].tail(5)
                if not recent_signals.empty:
                    print("  最近信号:")
                    for date, signal in recent_signals.items():
                        price = df.loc[date, 'close']
                        print(f"    {date.strftime('%Y-%m-%d')}: {signal} (价格: {price:.2f})")
                
            except Exception as e:
                print(f"  {symbol} 测试失败: {e}")
                continue
                
    except Exception as e:
        print(f"真实数据测试失败: {e}")

def test_strategy_components():
    """测试策略组件"""
    print("\n=== 策略组件测试 ===")
    
    # 生成测试数据
    df = generate_test_data(200)
    
    # 测试周线转换
    from strategies import convert_daily_to_weekly
    weekly_df = convert_daily_to_weekly(df)
    print(f"日线数据: {len(df)} 天")
    print(f"周线数据: {len(weekly_df)} 周")
    
    # 测试MACD零轴策略在周线上的应用
    from strategies import apply_macd_zero_axis_strategy
    weekly_signals = apply_macd_zero_axis_strategy(weekly_df)
    weekly_post_count = (weekly_signals == 'POST').sum()
    print(f"周线POST信号数量: {weekly_post_count}")
    
    # 测试信号映射
    from strategies import map_weekly_to_daily_signals
    weekly_post_signals = weekly_signals == 'POST'
    daily_weekly_signals = map_weekly_to_daily_signals(weekly_post_signals, df.index)
    daily_signal_count = daily_weekly_signals.sum()
    print(f"映射到日线的信号天数: {daily_signal_count}")
    
    # 测试MA计算
    ma_periods = [7, 13, 30, 45, 60, 90, 150, 240]
    mas = {}
    for period in ma_periods:
        mas[f'ma_{period}'] = df['close'].rolling(window=period).mean()
        valid_count = mas[f'ma_{period}'].notna().sum()
        print(f"MA{period}: {valid_count} 个有效值")

def visualize_strategy_signals(symbol='TEST'):
    """可视化策略信号"""
    print(f"\n=== 策略信号可视化 ({symbol}) ===")
    
    try:
        # 生成或加载数据
        if symbol == 'TEST':
            df = generate_test_data(200)
        else:
            data_loader = DataLoader()
            df = data_loader.load_stock_data(symbol, days=200)
            if df is None or df.empty:
                print(f"无法加载 {symbol} 的数据")
                return
        
        # 应用策略
        signals = apply_weekly_golden_cross_ma_strategy(df)
        
        # 计算MA指标用于绘图
        ma13 = df['close'].rolling(window=13).mean()
        ma30 = df['close'].rolling(window=30).mean()
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
        
        # 绘制价格和MA
        ax1.plot(df.index, df['close'], label='Close Price', linewidth=1)
        ax1.plot(df.index, ma13, label='MA13', alpha=0.7)
        ax1.plot(df.index, ma30, label='MA30', alpha=0.7)
        
        # 标记信号点
        buy_signals = signals == 'BUY'
        hold_signals = signals == 'HOLD'
        sell_signals = signals == 'SELL'
        
        if buy_signals.any():
            ax1.scatter(df.index[buy_signals], df['close'][buy_signals], 
                       color='green', marker='^', s=100, label='BUY', zorder=5)
        
        if hold_signals.any():
            ax1.scatter(df.index[hold_signals], df['close'][hold_signals], 
                       color='blue', marker='o', s=50, label='HOLD', alpha=0.6, zorder=4)
        
        if sell_signals.any():
            ax1.scatter(df.index[sell_signals], df['close'][sell_signals], 
                       color='red', marker='v', s=100, label='SELL', zorder=5)
        
        ax1.set_title(f'{symbol} - 周线金叉+日线MA策略信号')
        ax1.set_ylabel('价格')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 绘制信号分布
        signal_counts = signals.value_counts()
        if not signal_counts.empty:
            ax2.bar(signal_counts.index, signal_counts.values, 
                   color=['green' if x=='BUY' else 'blue' if x=='HOLD' else 'red' if x=='SELL' else 'gray' 
                         for x in signal_counts.index])
            ax2.set_title('信号分布')
            ax2.set_ylabel('信号数量')
        
        plt.tight_layout()
        
        # 保存图表
        chart_file = f'charts/weekly_golden_cross_ma_strategy_{symbol}.png'
        os.makedirs('charts', exist_ok=True)
        plt.savefig(chart_file, dpi=300, bbox_inches='tight')
        print(f"图表已保存到: {chart_file}")
        
        plt.show()
        
    except Exception as e:
        print(f"可视化失败: {e}")
        import traceback
        traceback.print_exc()

def main():
    """主测试函数"""
    print("周线金叉+日线MA策略测试")
    print("=" * 50)
    
    # 检查策略是否已注册
    available_strategies = list_available_strategies()
    print(f"可用策略: {available_strategies}")
    
    if 'WEEKLY_GOLDEN_CROSS_MA' in available_strategies:
        description = get_strategy_description('WEEKLY_GOLDEN_CROSS_MA')
        print(f"策略描述: {description}")
    else:
        print("错误: WEEKLY_GOLDEN_CROSS_MA 策略未找到")
        return
    
    # 运行测试
    tests = [
        test_strategy_basic,
        test_strategy_components,
        test_with_real_data
    ]
    
    for test_func in tests:
        try:
            test_func()
        except Exception as e:
            print(f"测试 {test_func.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 可视化测试
    try:
        visualize_strategy_signals('TEST')
    except Exception as e:
        print(f"可视化测试失败: {e}")
    
    print("\n测试完成!")

if __name__ == "__main__":
    main()