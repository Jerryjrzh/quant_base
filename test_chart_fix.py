#!/usr/bin/env python3
"""
测试图表修复效果
"""

import sys
import os
sys.path.append('backend')

import requests
import json

def test_unified_api():
    """测试统一API是否返回正确的图表数据"""
    print("=== 测试统一API图表数据 ===")
    
    # 测试参数
    stock_code = 'sh600036'
    strategy = 'PRE_CROSS'
    
    # 构建API URL
    url = f'http://localhost:5000/api/unified_analysis/{stock_code}'
    params = {'strategy': strategy}
    
    print(f"请求URL: {url}")
    print(f"参数: {params}")
    
    try:
        # 发送请求
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ API请求失败: {response.status_code}")
            print(f"响应内容: {response.text}")
            return False
        
        # 解析响应
        data = response.json()
        
        if not data.get('success'):
            print(f"❌ API返回失败: {data.get('error')}")
            return False
        
        print("✅ API请求成功")
        
        # 检查图表数据
        chart_data = data['data']['chart_data']
        
        print(f"K线数据条数: {len(chart_data['kline_data'])}")
        print(f"指标数据条数: {len(chart_data['indicator_data'])}")
        
        # 检查前几条指标数据
        if chart_data['indicator_data']:
            first_indicator = chart_data['indicator_data'][0]
            print(f"第一条指标数据: {first_indicator}")
            
            # 检查关键指标是否有效
            ma_indicators = ['ma7', 'ma13', 'ma30', 'ma45', 'ma60']
            valid_ma_count = 0
            for ma in ma_indicators:
                if ma in first_indicator and first_indicator[ma] is not None:
                    valid_ma_count += 1
            
            print(f"有效MA指标数量: {valid_ma_count}/{len(ma_indicators)}")
            
            if valid_ma_count == len(ma_indicators):
                print("✅ 所有MA指标都有效，图表应该能正常显示")
                return True
            else:
                print("❌ 部分MA指标无效，图表可能显示异常")
                return False
        else:
            print("❌ 没有指标数据")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求异常: {e}")
        return False
    except Exception as e:
        print(f"❌ 其他异常: {e}")
        return False

def test_multiple_stocks():
    """测试多个股票的图表数据"""
    print("\n=== 测试多个股票 ===")
    
    test_stocks = ['sh600036', 'sz000001', 'sh600519']
    strategy = 'PRE_CROSS'
    
    success_count = 0
    
    for stock_code in test_stocks:
        print(f"\n测试股票: {stock_code}")
        
        url = f'http://localhost:5000/api/unified_analysis/{stock_code}'
        params = {'strategy': strategy}
        
        try:
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    chart_data = data['data']['chart_data']
                    if chart_data['indicator_data']:
                        first_indicator = chart_data['indicator_data'][0]
                        ma_count = sum(1 for ma in ['ma7', 'ma13', 'ma30'] 
                                     if first_indicator.get(ma) is not None)
                        if ma_count >= 2:  # 至少2个MA指标有效
                            print(f"✅ {stock_code} 图表数据正常")
                            success_count += 1
                        else:
                            print(f"❌ {stock_code} MA指标不足")
                    else:
                        print(f"❌ {stock_code} 无指标数据")
                else:
                    print(f"❌ {stock_code} API返回失败")
            else:
                print(f"❌ {stock_code} HTTP错误: {response.status_code}")
                
        except Exception as e:
            print(f"❌ {stock_code} 异常: {e}")
    
    print(f"\n测试结果: {success_count}/{len(test_stocks)} 股票图表数据正常")
    return success_count == len(test_stocks)

if __name__ == '__main__':
    print("开始测试图表修复效果...")
    print("请确保Flask服务器正在运行 (python backend/app.py)")
    
    # 测试单个股票
    single_test_result = test_unified_api()
    
    # 测试多个股票
    multiple_test_result = test_multiple_stocks()
    
    print("\n=== 测试总结 ===")
    if single_test_result and multiple_test_result:
        print("🎉 所有测试通过！图表修复成功！")
        print("前端图表应该能正常显示技术指标了。")
    else:
        print("⚠️ 部分测试失败，可能还需要进一步调试。")