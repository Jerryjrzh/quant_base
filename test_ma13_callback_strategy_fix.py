#!/usr/bin/env python3
"""
MA13强势回调策略修复测试
测试新实现的MA13策略是否能正确识别强势股的回调买点

测试目标：
1. 验证数据接口正常工作（5分钟->小时线聚合）
2. 验证指标位置判断逻辑
3. 验证双模型识别逻辑
4. 对比修复前后的结果差异

作者：基于Grok和Gemini评估优化
日期：2025-09-17
"""

import sys
import os
import pandas as pd
import json
from datetime import datetime

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from backend.strategies.ma13_callback_strategy import MA13CallbackStrategy
    from backend.data_loader import get_multi_timeframe_data, fetch_hourly_kline
    from backend.indicators import get_indicator_position, calculate_macd, calculate_kdj, calculate_rsi
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保在项目根目录下运行此脚本")
    sys.exit(1)

def test_data_interfaces():
    """测试数据接口功能"""
    print("=== 测试数据接口 ===")
    
    test_stocks = ['sz002021', 'sh600618', 'sz300739']
    
    for stock_code in test_stocks:
        print(f"\n--- 测试股票: {stock_code} ---")
        
        # 测试多时间框架数据获取
        multi_data = get_multi_timeframe_data(stock_code)
        print(f"日线数据可用: {multi_data['data_status']['daily_available']}")
        print(f"5分钟数据可用: {multi_data['data_status']['min5_available']}")
        
        if multi_data['data_status']['daily_available']:
            daily_df = multi_data['daily_data']
            print(f"日线数据量: {len(daily_df)} 条")
            print(f"日线数据范围: {daily_df.index[0]} 到 {daily_df.index[-1]}")
        
        # 测试小时线数据聚合
        try:
            hourly_df = fetch_hourly_kline(stock_code, '2025-09-01', '2025-09-11')
            if not hourly_df.empty:
                print(f"小时线数据量: {len(hourly_df)} 条")
                print(f"小时线数据范围: {hourly_df['date'].iloc[0]} 到 {hourly_df['date'].iloc[-1]}")
            else:
                print("小时线数据为空")
        except Exception as e:
            print(f"小时线数据获取失败: {e}")

def test_indicator_positions():
    """测试指标位置判断逻辑"""
    print("\n=== 测试指标位置判断 ===")
    
    # 测试KDJ J值位置判断
    test_kdj_values = [25, 45, 75, 95]
    for j_value in test_kdj_values:
        position = get_indicator_position(j_value, 'kdj_j')
        print(f"KDJ J={j_value} -> 位置: {position}")
    
    # 测试RSI位置判断
    test_rsi_values = [25, 45, 65, 85]
    for rsi_value in test_rsi_values:
        position = get_indicator_position(rsi_value, 'rsi_6')
        print(f"RSI={rsi_value} -> 位置: {position}")
    
    # 测试MACD DIF位置判断
    test_dif_values = [-0.5, -0.1, 0.1, 0.5]
    for dif_value in test_dif_values:
        position = get_indicator_position(dif_value, 'macd_dif')
        print(f"MACD DIF={dif_value} -> 位置: {position}")

def test_strategy_application():
    """测试策略应用"""
    print("\n=== 测试策略应用 ===")
    
    # 策略配置
    config = {
        'callback_range': [3, 15],
        'vol_multiplier': 1.1,
        'kdj_relay_range': [40, 90],
        'ma13_tolerance': 0.02,
        'min_rise_pct': 15,
        'lookback_days': 60,
        'hourly_lookback_days': 10
    }
    
    strategy = MA13CallbackStrategy(config)
    
    # 测试股票
    test_stocks = ['sz002021', 'sh600618', 'sz300739']
    results = {}
    
    for stock_code in test_stocks:
        print(f"\n--- 应用策略到股票: {stock_code} ---")
        
        try:
            # 获取日线数据
            multi_data = get_multi_timeframe_data(stock_code)
            
            if not multi_data['data_status']['daily_available']:
                print(f"跳过 {stock_code}：无日线数据")
                continue
            
            daily_df = multi_data['daily_data']
            
            # 应用策略
            result = strategy.apply_strategy(stock_code, daily_df)
            results[stock_code] = result
            
            # 输出结果
            print(f"信号: {result['signal']}")
            print(f"强度: {result['strength']}")
            print(f"模型: {result['model']}")
            
            if result['details']:
                daily_details = result['details'].get('daily', {})
                if daily_details:
                    print(f"日线检查通过: {daily_details.get('passed', False)}")
                    if 'details' in daily_details:
                        details = daily_details['details']
                        print(f"  当前价格: {details.get('current_price', 'N/A'):.2f}")
                        print(f"  MA13距离: {details.get('ma13_distance', 'N/A'):.3f}")
                        print(f"  回调幅度: {details.get('callback_pct', 'N/A'):.2f}%")
                
                hourly_details = result['details'].get('hourly', {})
                if hourly_details and 'details' in hourly_details:
                    h_details = hourly_details['details']
                    print(f"小时线详情:")
                    print(f"  KDJ J: {h_details.get('kdj_j', 'N/A'):.2f}")
                    print(f"  RSI: {h_details.get('rsi', 'N/A'):.2f}")
                    print(f"  成交量放大: {h_details.get('vol_amplified', 'N/A')}")
            
        except Exception as e:
            print(f"测试 {stock_code} 时出错: {e}")
            results[stock_code] = {'error': str(e)}
    
    return results

def test_hourly_indicators():
    """测试小时线指标计算"""
    print("\n=== 测试小时线指标计算 ===")
    
    stock_code = 'sz002021'  # 使用一个测试股票
    
    try:
        # 获取小时线数据
        hourly_df = fetch_hourly_kline(stock_code, '2025-09-01', '2025-09-17')
        
        if hourly_df.empty:
            print(f"无法获取 {stock_code} 的小时线数据")
            return
        
        print(f"小时线数据量: {len(hourly_df)} 条")
        
        # 计算指标
        dif, dea = calculate_macd(hourly_df, fast=8, slow=21, signal=6)
        k, d, j = calculate_kdj(hourly_df, n=27, k_period=3, d_period=3)
        rsi = calculate_rsi(hourly_df, periods=6)
        
        # 显示最近几个数据点
        print("\n最近5个小时的指标数据:")
        for i in range(-5, 0):
            if abs(i) <= len(hourly_df):
                print(f"时间: {hourly_df['date'].iloc[i]}")
                print(f"  MACD DIF: {dif.iloc[i]:.4f}, DEA: {dea.iloc[i]:.4f}")
                print(f"  KDJ J: {j.iloc[i]:.2f}, K: {k.iloc[i]:.2f}, D: {d.iloc[i]:.2f}")
                print(f"  RSI: {rsi.iloc[i]:.2f}")
                print(f"  成交量: {hourly_df['volume'].iloc[i]:,.0f}")
                print()
        
    except Exception as e:
        print(f"测试小时线指标时出错: {e}")

def generate_test_report(results):
    """生成测试报告"""
    print("\n=== 测试报告 ===")
    
    # 清理结果数据，确保JSON可序列化
    clean_results = {}
    for stock, result in results.items():
        clean_result = {}
        for key, value in result.items():
            if isinstance(value, (dict, list)):
                # 递归清理嵌套结构
                clean_result[key] = clean_nested_data(value)
            else:
                clean_result[key] = value
        clean_results[stock] = clean_result
    
    report = {
        'test_time': datetime.now().isoformat(),
        'test_results': clean_results,
        'summary': {
            'total_stocks': len(results),
            'successful_tests': len([r for r in results.values() if 'error' not in r]),
            'signals_generated': len([r for r in results.values() if r.get('signal')]),
            'super_fall_signals': len([r for r in results.values() if r.get('signal') == 'buy_super_fall']),
            'relay_signals': len([r for r in results.values() if r.get('signal') == 'buy_relay'])
        }
    }
    
    # 保存报告
    report_file = f'ma13_strategy_test_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        print(f"测试报告已保存到: {report_file}")
    except Exception as e:
        print(f"保存报告失败: {e}")
    
    # 打印摘要
    summary = report['summary']
    print(f"测试股票总数: {summary['total_stocks']}")
    print(f"成功测试数: {summary['successful_tests']}")
    print(f"产生信号数: {summary['signals_generated']}")
    print(f"超跌反弹信号: {summary['super_fall_signals']}")
    print(f"中继确认信号: {summary['relay_signals']}")
    
    return report

def clean_nested_data(data):
    """清理嵌套数据，确保JSON可序列化"""
    if isinstance(data, dict):
        return {k: clean_nested_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_nested_data(item) for item in data]
    elif isinstance(data, (bool, int, float, str)) or data is None:
        return data
    else:
        return str(data)

def main():
    """主测试函数"""
    print("MA13强势回调策略修复测试")
    print("=" * 50)
    
    # 1. 测试数据接口
    test_data_interfaces()
    
    # 2. 测试指标位置判断
    test_indicator_positions()
    
    # 3. 测试小时线指标计算
    test_hourly_indicators()
    
    # 4. 测试策略应用
    results = test_strategy_application()
    
    # 5. 生成测试报告
    report = generate_test_report(results)
    
    print("\n测试完成！")
    print("请检查测试报告以了解详细结果。")

if __name__ == "__main__":
    main()