#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试MA指标计算
"""

import sys
import os
sys.path.append('backend')

from data_handler import get_full_data_with_indicators
import pandas as pd

def test_ma_calculation():
    """测试MA指标计算"""
    print("=== MA指标计算测试 ===")
    
    # 测试一个常见的股票代码
    test_codes = ['sh600006', 'sz000001', 'sh000001']
    
    for stock_code in test_codes:
        print(f"\n测试股票: {stock_code}")
        
        try:
            df = get_full_data_with_indicators(stock_code)
            if df is None:
                print(f"  ❌ 无法获取数据")
                continue
                
            print(f"  ✅ 数据加载成功，共 {len(df)} 条记录")
            
            # 检查MA指标列
            ma_columns = ['ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240']
            existing_ma_cols = [col for col in ma_columns if col in df.columns]
            missing_ma_cols = [col for col in ma_columns if col not in df.columns]
            
            print(f"  存在的MA列: {existing_ma_cols}")
            if missing_ma_cols:
                print(f"  ❌ 缺失的MA列: {missing_ma_cols}")
            else:
                print(f"  ✅ 所有MA列都存在")
            
            # 检查最新的MA数据
            if existing_ma_cols:
                latest_data = df.iloc[-1]
                print(f"  最新数据 ({latest_data.name}):")
                print(f"    收盘价: {latest_data['close']:.2f}")
                for col in existing_ma_cols:
                    value = latest_data[col]
                    if pd.notna(value):
                        print(f"    {col.upper()}: {value:.2f}")
                    else:
                        print(f"    {col.upper()}: N/A")
            
            # 检查数据完整性
            print(f"  数据完整性检查:")
            for col in existing_ma_cols:
                valid_count = df[col].notna().sum()
                total_count = len(df)
                print(f"    {col.upper()}: {valid_count}/{total_count} ({valid_count/total_count*100:.1f}%)")
            
            return df  # 返回第一个成功的数据用于进一步测试
            
        except Exception as e:
            print(f"  ❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    return None

def test_unified_analysis_api():
    """测试统一分析API"""
    print("\n=== 统一分析API测试 ===")
    
    try:
        from unified_analysis_service import get_or_run_analysis
        
        # 测试一个股票
        stock_code = 'sh600006'
        strategy_id = 'WEEKLY_GOLDEN_CROSS_MA'
        
        print(f"测试: {stock_code} @ {strategy_id}")
        
        result = get_or_run_analysis(stock_code, strategy_id)
        
        if result.get('success'):
            print("  ✅ API调用成功")
            
            chart_data = result['data']['chart_data']
            indicator_data = chart_data['indicator_data']
            
            if indicator_data:
                print(f"  指标数据点数: {len(indicator_data)}")
                
                # 检查第一个数据点
                first_point = indicator_data[0]
                print(f"  第一个数据点的MA字段:")
                ma_fields = ['ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240']
                for field in ma_fields:
                    value = first_point.get(field)
                    print(f"    {field}: {value}")
                
                # 检查最后一个数据点
                last_point = indicator_data[-1]
                print(f"  最后一个数据点的MA字段:")
                for field in ma_fields:
                    value = last_point.get(field)
                    print(f"    {field}: {value}")
            else:
                print("  ❌ 没有指标数据")
        else:
            print(f"  ❌ API调用失败: {result.get('error')}")
            
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # 测试MA计算
    df = test_ma_calculation()
    
    # 测试统一分析API
    test_unified_analysis_api()