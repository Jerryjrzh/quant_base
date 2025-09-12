#!/usr/bin/env python3
"""
调试前端图表空白问题
检查unified_analysis_service中的数据处理是否正确
"""

import sys
import os
sys.path.append('backend')

import pandas as pd
import numpy as np
import json
from data_handler import get_full_data_with_indicators
from unified_analysis_service import get_or_run_analysis

def test_chart_data_processing():
    """测试图表数据处理是否正确"""
    print("=== 调试前端图表空白问题 ===")
    
    # 测试股票代码
    test_stock = 'sh600036'  # 招商银行
    test_strategy = 'PRE_CROSS'
    
    print(f"测试股票: {test_stock}")
    print(f"测试策略: {test_strategy}")
    
    # 1. 直接获取原始数据
    print("\n1. 获取原始数据...")
    df = get_full_data_with_indicators(test_stock)
    if df is None:
        print("❌ 无法获取原始数据")
        return
    
    print(f"✅ 原始数据获取成功，形状: {df.shape}")
    print(f"   列名: {list(df.columns)}")
    print(f"   前5行数据:")
    print(df.head())
    
    # 检查NaN值
    nan_counts = df.isnull().sum()
    print(f"\n   NaN值统计:")
    for col, count in nan_counts.items():
        if count > 0:
            print(f"   {col}: {count} 个NaN")
    
    # 2. 测试统一分析服务
    print("\n2. 测试统一分析服务...")
    result = get_or_run_analysis(test_stock, test_strategy)
    
    if not result['success']:
        print(f"❌ 统一分析失败: {result.get('error')}")
        return
    
    print("✅ 统一分析成功")
    
    # 3. 检查图表数据
    print("\n3. 检查图表数据...")
    chart_data = result['data']['chart_data']
    
    print(f"   K线数据条数: {len(chart_data['kline_data'])}")
    print(f"   指标数据条数: {len(chart_data['indicator_data'])}")
    
    # 检查前几条数据
    if chart_data['kline_data']:
        print(f"   K线数据示例:")
        for i, item in enumerate(chart_data['kline_data'][:3]):
            print(f"     [{i}] {item}")
    
    if chart_data['indicator_data']:
        print(f"   指标数据示例:")
        for i, item in enumerate(chart_data['indicator_data'][:3]):
            print(f"     [{i}] {item}")
    
    # 4. 检查数据中的None值
    print("\n4. 检查数据中的None值...")
    kline_none_count = 0
    indicator_none_count = 0
    
    for item in chart_data['kline_data']:
        for key, value in item.items():
            if value is None:
                kline_none_count += 1
    
    for item in chart_data['indicator_data']:
        for key, value in item.items():
            if value is None:
                indicator_none_count += 1
    
    print(f"   K线数据中的None值: {kline_none_count}")
    print(f"   指标数据中的None值: {indicator_none_count}")
    
    # 5. 测试JSON序列化
    print("\n5. 测试JSON序列化...")
    try:
        json_str = json.dumps(chart_data, ensure_ascii=False, indent=2)
        print("✅ JSON序列化成功")
        print(f"   JSON长度: {len(json_str)} 字符")
    except Exception as e:
        print(f"❌ JSON序列化失败: {e}")
    
    # 6. 检查关键指标是否有效
    print("\n6. 检查关键指标...")
    if chart_data['indicator_data']:
        first_indicator = chart_data['indicator_data'][0]
        print(f"   第一条指标数据: {first_indicator}")
        
        # 检查MA指标
        ma_indicators = ['ma7', 'ma13', 'ma30', 'ma45', 'ma60']
        valid_ma_count = 0
        for ma in ma_indicators:
            if ma in first_indicator and first_indicator[ma] is not None:
                valid_ma_count += 1
        
        print(f"   有效MA指标数量: {valid_ma_count}/{len(ma_indicators)}")
        
        # 检查MACD指标
        macd_indicators = ['dif', 'dea', 'macd']
        valid_macd_count = 0
        for macd in macd_indicators:
            if macd in first_indicator and first_indicator[macd] is not None:
                valid_macd_count += 1
        
        print(f"   有效MACD指标数量: {valid_macd_count}/{len(macd_indicators)}")
    
    print("\n=== 调试完成 ===")

def test_nan_replacement_issue():
    """测试NaN替换是否导致问题"""
    print("\n=== 测试NaN替换问题 ===")
    
    # 创建测试数据
    test_data = pd.DataFrame({
        'date': pd.date_range('2024-01-01', periods=5),
        'open': [10.0, 11.0, np.nan, 12.0, 13.0],
        'close': [10.5, 11.5, 11.8, 12.5, 13.5],
        'ma7': [10.2, 11.2, np.nan, 12.2, 13.2],
        'volume': [1000, 1100, 1200, np.nan, 1400]
    })
    
    print("原始测试数据:")
    print(test_data)
    print(f"NaN值统计: {test_data.isnull().sum().sum()}")
    
    # 应用当前的修复方法
    test_data_fixed = test_data.copy()
    test_data_fixed.replace({np.nan: None, pd.NaT: None}, inplace=True)
    
    print("\n应用NaN->None替换后:")
    print(test_data_fixed)
    
    # 测试JSON序列化
    try:
        json_str = json.dumps(test_data_fixed.to_dict('records'), ensure_ascii=False)
        print("✅ JSON序列化成功")
    except Exception as e:
        print(f"❌ JSON序列化失败: {e}")
    
    # 测试更好的处理方法
    print("\n测试更好的处理方法:")
    test_data_better = test_data.copy()
    
    # 方法1: 使用fillna填充数值列
    numeric_cols = test_data_better.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        if col != 'volume':  # volume可以为0
            test_data_better[col] = test_data_better[col].fillna(method='ffill')  # 前向填充
    
    # volume用0填充
    if 'volume' in test_data_better.columns:
        test_data_better['volume'] = test_data_better['volume'].fillna(0)
    
    print("使用前向填充后:")
    print(test_data_better)
    
    # 转换为字典并处理剩余的NaN
    records = test_data_better.to_dict('records')
    for record in records:
        for key, value in record.items():
            if pd.isna(value):
                record[key] = None
    
    try:
        json_str = json.dumps(records, ensure_ascii=False, default=str)
        print("✅ 改进方法JSON序列化成功")
    except Exception as e:
        print(f"❌ 改进方法JSON序列化失败: {e}")

if __name__ == '__main__':
    test_chart_data_processing()
    test_nan_replacement_issue()