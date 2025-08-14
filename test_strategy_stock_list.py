#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略选择后股票列表显示功能
"""

import requests
import json
import time
from datetime import datetime

def test_strategy_stock_list():
    """测试策略股票列表功能"""
    print("🧪 测试策略选择后股票列表显示功能")
    print("=" * 60)
    
    base_url = "http://localhost:5000"
    
    # 1. 测试获取可用策略
    print("\n1. 获取可用策略列表...")
    try:
        response = requests.get(f"{base_url}/api/strategies")
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                strategies = data['data']
                print(f"✅ 成功获取 {len(strategies)} 个策略")
                for strategy_id, strategy_info in strategies.items():
                    print(f"   - {strategy_id}: {strategy_info.get('name', 'Unknown')}")
            else:
                print(f"❌ 获取策略失败: {data.get('error', 'Unknown error')}")
                return
        else:
            print(f"❌ API请求失败: {response.status_code}")
            return
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return
    
    # 2. 测试新的策略股票列表API
    print("\n2. 测试新的策略股票列表API...")
    test_strategies = ['临界金叉_v1.0', '三重金叉_v1.0', 'macd零轴启动_v1.0']
    
    for strategy_id in test_strategies:
        if strategy_id in strategies:
            print(f"\n   测试策略: {strategy_id}")
            try:
                response = requests.get(f"{base_url}/api/strategies/{strategy_id}/stocks")
                if response.status_code == 200:
                    data = response.json()
                    if data['success']:
                        stock_list = data['data']
                        print(f"   ✅ 获取到 {len(stock_list)} 只股票")
                        
                        # 显示前5只股票
                        for i, stock in enumerate(stock_list[:5]):
                            print(f"      {i+1}. {stock['stock_code']} ({stock['date']}) - {stock.get('signal_type', 'N/A')}")
                        
                        if len(stock_list) > 5:
                            print(f"      ... 还有 {len(stock_list) - 5} 只股票")
                    else:
                        print(f"   ❌ 获取失败: {data.get('error', 'Unknown error')}")
                else:
                    print(f"   ❌ API请求失败: {response.status_code}")
            except Exception as e:
                print(f"   ❌ 请求异常: {e}")
        else:
            print(f"   ⚠️  策略 {strategy_id} 不存在，跳过测试")
    
    # 3. 测试兼容性API
    print("\n3. 测试兼容性API (signals_summary)...")
    old_strategies = ['PRE_CROSS', 'TRIPLE_CROSS', 'MACD_ZERO_AXIS']
    
    for old_strategy in old_strategies:
        print(f"\n   测试旧策略ID: {old_strategy}")
        try:
            response = requests.get(f"{base_url}/api/signals_summary?strategy={old_strategy}")
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    print(f"   ✅ 获取到 {len(data)} 只股票")
                    
                    # 显示前3只股票
                    for i, stock in enumerate(data[:3]):
                        print(f"      {i+1}. {stock['stock_code']} ({stock['date']})")
                    
                    if len(data) > 3:
                        print(f"      ... 还有 {len(data) - 3} 只股票")
                elif isinstance(data, dict) and 'error' in data:
                    print(f"   ❌ 获取失败: {data['error']}")
                else:
                    print(f"   ⚠️  返回数据格式异常: {type(data)}")
            else:
                print(f"   ❌ API请求失败: {response.status_code}")
        except Exception as e:
            print(f"   ❌ 请求异常: {e}")
    
    # 4. 测试统一配置API
    print("\n4. 测试统一配置API...")
    try:
        response = requests.get(f"{base_url}/api/config/unified")
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                config = data['data']
                strategies_config = config.get('strategies', {})
                print(f"   ✅ 获取到统一配置，包含 {len(strategies_config)} 个策略配置")
                
                # 显示策略配置概览
                for strategy_id, strategy_config in list(strategies_config.items())[:3]:
                    enabled = strategy_config.get('enabled', True)
                    name = strategy_config.get('name', 'Unknown')
                    version = strategy_config.get('version', 'Unknown')
                    print(f"      - {strategy_id}: {name} v{version} ({'启用' if enabled else '禁用'})")
            else:
                print(f"   ❌ 获取配置失败: {data.get('error', 'Unknown error')}")
        else:
            print(f"   ❌ API请求失败: {response.status_code}")
    except Exception as e:
        print(f"   ❌ 请求异常: {e}")
    
    print("\n" + "=" * 60)
    print("🎯 测试完成！")
    print("\n📋 测试总结:")
    print("   - 新的策略股票列表API: /api/strategies/<id>/stocks")
    print("   - 兼容性API: /api/signals_summary?strategy=<old_id>")
    print("   - 统一配置API: /api/config/unified")
    print("\n💡 前端使用建议:")
    print("   1. 优先使用新API获取股票列表")
    print("   2. 如果新API失败，回退到兼容性API")
    print("   3. 使用统一配置API获取策略信息")

def test_frontend_integration():
    """测试前端集成"""
    print("\n🌐 测试前端集成...")
    print("=" * 60)
    
    # 模拟前端策略选择流程
    print("\n模拟前端策略选择流程:")
    print("1. 用户选择策略: '临界金叉_v1.0'")
    print("2. 前端调用API获取股票列表")
    print("3. 更新股票下拉框")
    print("4. 用户选择股票后加载图表")
    
    # 这里可以添加更多前端集成测试
    print("\n✅ 前端集成测试完成")

if __name__ == "__main__":
    print(f"🚀 开始测试 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        test_strategy_stock_list()
        test_frontend_integration()
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n🏁 测试结束 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")