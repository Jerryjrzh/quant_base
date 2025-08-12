#!/usr/bin/env python3
"""
测试多周期指标显示功能
"""

import requests
import json
import time
from datetime import datetime

# 测试配置
BASE_URL = "http://localhost:5000"
TEST_STOCK_CODE = "sz000001"
TEST_STRATEGY = "PRE_CROSS"

def test_api_endpoint(endpoint, params=None):
    """测试API端点"""
    try:
        url = f"{BASE_URL}{endpoint}"
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return True, data
        else:
            print(f"❌ API错误 {response.status_code}: {response.text}")
            return False, None
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False, None

def test_timeframe_analysis():
    """测试不同周期的分析功能"""
    print("🔍 测试多周期分析功能...")
    
    timeframes = [
        ('daily', '5min', '日线'),
        ('weekly', '5min', '周线'),
        ('monthly', '5min', '月线')
    ]
    
    intervals = [
        ('daily', '5min', '5分钟'),
        ('daily', '10min', '10分钟'),
        ('daily', '15min', '15分钟'),
        ('daily', '30min', '30分钟'),
        ('daily', '60min', '60分钟')
    ]
    
    # 测试不同周期
    for timeframe, interval, name in timeframes:
        print(f"\n📊 测试{name}数据...")
        params = {
            'strategy': TEST_STRATEGY,
            'adjustment': 'forward',
            'timeframe': timeframe,
            'interval': interval
        }
        
        success, data = test_api_endpoint(f"/api/analysis/{TEST_STOCK_CODE}", params)
        if success:
            print(f"✅ {name}数据加载成功")
            print(f"   - K线数据点数: {len(data.get('kline_data', []))}")
            print(f"   - 指标数据点数: {len(data.get('indicator_data', []))}")
            print(f"   - 信号点数: {len(data.get('signal_points', []))}")
            
            # 检查数据格式
            if data.get('kline_data'):
                sample_kline = data['kline_data'][0]
                print(f"   - 样本K线数据: {sample_kline}")
            
            if data.get('indicator_data'):
                sample_indicator = data['indicator_data'][0]
                print(f"   - 样本指标数据: {sample_indicator}")
        else:
            print(f"❌ {name}数据加载失败")
    
    # 测试不同分时
    print(f"\n📈 测试分时数据...")
    for timeframe, interval, name in intervals:
        print(f"\n⏰ 测试{name}数据...")
        params = {
            'strategy': TEST_STRATEGY,
            'adjustment': 'forward',
            'timeframe': timeframe,
            'interval': interval
        }
        
        success, data = test_api_endpoint(f"/api/analysis/{TEST_STOCK_CODE}", params)
        if success:
            print(f"✅ {name}数据加载成功")
            print(f"   - K线数据点数: {len(data.get('kline_data', []))}")
            
            # 检查时间格式
            if data.get('kline_data'):
                sample_date = data['kline_data'][0]['date']
                print(f"   - 时间格式: {sample_date}")
        else:
            print(f"❌ {name}数据加载失败")

def test_trading_advice_with_timeframes():
    """测试不同周期的交易建议"""
    print("\n💡 测试多周期交易建议...")
    
    test_cases = [
        ('daily', '5min', '日线'),
        ('weekly', '5min', '周线'),
        ('daily', '15min', '15分钟')
    ]
    
    for timeframe, interval, name in test_cases:
        print(f"\n📋 测试{name}交易建议...")
        params = {
            'strategy': TEST_STRATEGY,
            'adjustment': 'forward',
            'timeframe': timeframe,
            'interval': interval
        }
        
        success, data = test_api_endpoint(f"/api/trading_advice/{TEST_STOCK_CODE}", params)
        if success:
            print(f"✅ {name}交易建议生成成功")
            print(f"   - 建议操作: {data.get('action', 'N/A')}")
            print(f"   - 置信度: {data.get('confidence', 'N/A')}")
            print(f"   - 当前价格: {data.get('current_price', 'N/A')}")
            print(f"   - 分析逻辑条数: {len(data.get('analysis_logic', []))}")
        else:
            print(f"❌ {name}交易建议生成失败")

def test_indicator_parameters():
    """测试指标参数显示"""
    print("\n🔧 测试指标参数配置...")
    
    # 这里主要测试前端显示，后端数据结构应该包含指标参数信息
    params = {
        'strategy': TEST_STRATEGY,
        'adjustment': 'forward',
        'timeframe': 'daily',
        'interval': '5min'
    }
    
    success, data = test_api_endpoint(f"/api/analysis/{TEST_STOCK_CODE}", params)
    if success:
        print("✅ 指标数据获取成功")
        
        # 检查指标数据是否包含预期的字段
        if data.get('indicator_data'):
            sample = data['indicator_data'][0]
            expected_indicators = ['ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']
            
            print("   指标字段检查:")
            for indicator in expected_indicators:
                if indicator in sample:
                    print(f"   ✅ {indicator}: {sample[indicator]}")
                else:
                    print(f"   ❌ 缺少指标: {indicator}")
        else:
            print("❌ 未找到指标数据")
    else:
        print("❌ 指标数据获取失败")

def generate_test_report():
    """生成测试报告"""
    print("\n" + "="*60)
    print("📊 多周期指标显示功能测试报告")
    print("="*60)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"测试股票: {TEST_STOCK_CODE}")
    print(f"测试策略: {TEST_STRATEGY}")
    print("-"*60)
    
    # 执行所有测试
    test_timeframe_analysis()
    test_trading_advice_with_timeframes()
    test_indicator_parameters()
    
    print("\n" + "="*60)
    print("✅ 测试完成")
    print("="*60)

if __name__ == "__main__":
    print("🚀 启动多周期指标显示功能测试...")
    generate_test_report()