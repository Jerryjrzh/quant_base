#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试API路由
验证策略股票列表API是否正常工作
"""

import requests
import json
import time
from urllib.parse import quote, unquote

def test_api_routes():
    """测试API路由"""
    base_url = "http://localhost:5000"
    
    print("🧪 测试API路由")
    print("=" * 50)
    
    # 1. 测试策略列表API
    print("\n1. 测试策略列表API...")
    try:
        response = requests.get(f"{base_url}/api/strategies", timeout=10)
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                strategies = data.get('data', {})
                print(f"   ✅ 获取到 {len(strategies)} 个策略")
                
                # 显示策略列表
                for strategy_id, strategy_info in list(strategies.items())[:3]:
                    name = strategy_info.get('name', 'Unknown')
                    print(f"      - {strategy_id}: {name}")
                
                return list(strategies.keys())[:2]  # 返回前2个策略用于测试
            else:
                print(f"   ❌ API返回错误: {data.get('error')}")
        else:
            print(f"   ❌ HTTP错误: {response.status_code}")
            print(f"   响应内容: {response.text}")
    except Exception as e:
        print(f"   ❌ 请求异常: {e}")
    
    return []

def test_strategy_stocks_api(strategy_ids):
    """测试策略股票列表API"""
    base_url = "http://localhost:5000"
    
    print("\n2. 测试策略股票列表API...")
    
    for strategy_id in strategy_ids:
        print(f"\n   测试策略: {strategy_id}")
        
        # 测试不同的URL编码方式
        encodings = [
            ("直接使用", strategy_id),
            ("URL编码", quote(strategy_id, safe='')),
            ("UTF-8编码", quote(strategy_id.encode('utf-8'), safe=''))
        ]
        
        for encoding_name, encoded_id in encodings:
            print(f"     {encoding_name}: {encoded_id}")
            
            try:
                url = f"{base_url}/api/strategies/{encoded_id}/stocks"
                response = requests.get(url, timeout=10)
                print(f"       状态码: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get('success'):
                        stock_count = len(data.get('data', []))
                        print(f"       ✅ 成功获取 {stock_count} 只股票")
                        
                        # 显示前3只股票
                        stocks = data.get('data', [])[:3]
                        for stock in stocks:
                            print(f"         - {stock.get('stock_code')} ({stock.get('date')})")
                        
                        break  # 成功了就不用测试其他编码方式
                    else:
                        print(f"       ❌ API返回错误: {data.get('error')}")
                elif response.status_code == 404:
                    print(f"       ❌ 路由未找到 (404)")
                else:
                    print(f"       ❌ HTTP错误: {response.status_code}")
                    print(f"       响应: {response.text[:200]}")
            except Exception as e:
                print(f"       ❌ 请求异常: {e}")

def test_compatibility_api():
    """测试兼容性API"""
    base_url = "http://localhost:5000"
    
    print("\n3. 测试兼容性API...")
    
    old_strategies = ['PRE_CROSS', 'TRIPLE_CROSS', 'MACD_ZERO_AXIS']
    
    for old_strategy in old_strategies:
        print(f"\n   测试旧策略ID: {old_strategy}")
        
        try:
            url = f"{base_url}/api/signals_summary?strategy={old_strategy}"
            response = requests.get(url, timeout=10)
            print(f"     状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    print(f"     ✅ 成功获取 {len(data)} 只股票")
                    
                    # 显示前2只股票
                    for stock in data[:2]:
                        print(f"       - {stock.get('stock_code')} ({stock.get('date')})")
                elif isinstance(data, dict) and 'error' in data:
                    print(f"     ❌ API返回错误: {data['error']}")
                else:
                    print(f"     ⚠️  返回格式异常: {type(data)}")
            else:
                print(f"     ❌ HTTP错误: {response.status_code}")
                print(f"     响应: {response.text[:200]}")
        except Exception as e:
            print(f"     ❌ 请求异常: {e}")

def test_server_status():
    """测试服务器状态"""
    base_url = "http://localhost:5000"
    
    print("\n0. 测试服务器状态...")
    
    try:
        response = requests.get(f"{base_url}/api/system/info", timeout=5)
        print(f"   状态码: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                info = data.get('data', {})
                print(f"   ✅ 服务器正常运行")
                print(f"     版本: {info.get('version')}")
                print(f"     策略数: {info.get('total_strategies')}")
                print(f"     启用策略: {info.get('enabled_strategies')}")
                return True
            else:
                print(f"   ❌ 系统信息API错误: {data.get('error')}")
        else:
            print(f"   ❌ 系统信息API HTTP错误: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("   ❌ 无法连接到服务器，请确保API服务正在运行")
        print("   💡 运行: python start_strategy_stock_api.py")
        return False
    except Exception as e:
        print(f"   ❌ 请求异常: {e}")
    
    return False

def main():
    """主函数"""
    print("🎯 API路由测试工具")
    print("=" * 50)
    
    # 检查服务器状态
    if not test_server_status():
        return
    
    # 测试策略列表API
    strategy_ids = test_api_routes()
    
    if strategy_ids:
        # 测试策略股票列表API
        test_strategy_stocks_api(strategy_ids)
    else:
        print("\n⚠️  没有可用的策略ID，跳过股票列表API测试")
    
    # 测试兼容性API
    test_compatibility_api()
    
    print("\n" + "=" * 50)
    print("🎯 测试完成！")
    
    print("\n💡 如果遇到404错误，可能的原因:")
    print("   1. API服务未启动或端口不正确")
    print("   2. 路由定义有问题")
    print("   3. 中文字符URL编码问题")
    print("   4. Flask应用配置问题")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()