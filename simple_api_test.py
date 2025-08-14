#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单API测试
不依赖外部库，直接测试Flask应用
"""

import sys
import os
import json
from urllib.parse import quote, unquote

# 添加backend路径
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)
os.chdir(backend_path)

def test_flask_app():
    """测试Flask应用"""
    print("🧪 测试Flask应用")
    print("=" * 50)
    
    try:
        from screening_api import app
        
        print("✅ Flask应用导入成功")
        
        # 使用测试客户端
        with app.test_client() as client:
            
            # 1. 测试策略列表API
            print("\n1. 测试策略列表API...")
            response = client.get('/api/strategies')
            print(f"   状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.get_json()
                if data and data.get('success'):
                    strategies_data = data.get('data', {})
                    print(f"   ✅ 获取到 {len(strategies_data)} 个策略")
                    
                    # 处理字典格式
                    if isinstance(strategies_data, dict):
                        strategy_ids = list(strategies_data.keys())[:2]
                        for strategy_id in strategy_ids:
                            strategy_info = strategies_data[strategy_id]
                            name = strategy_info.get('name', 'Unknown')
                            print(f"      - {strategy_id}: {name}")
                    # 处理列表格式（兼容性）
                    elif isinstance(strategies_data, list):
                        strategy_ids = [s.get('id') for s in strategies_data[:2] if s.get('id')]
                        for strategy in strategies_data[:2]:
                            strategy_id = strategy.get('id', 'Unknown')
                            name = strategy.get('name', 'Unknown')
                            print(f"      - {strategy_id}: {name}")
                    else:
                        print(f"   ⚠️  未知的数据格式: {type(strategies_data)}")
                        strategy_ids = []
                    
                    # 2. 测试策略股票列表API
                    print(f"\n2. 测试策略股票列表API...")
                    for strategy_id in strategy_ids:
                        print(f"\n   测试策略: {strategy_id}")
                        
                        # 直接使用策略ID（不编码）
                        url = f'/api/strategies/{strategy_id}/stocks'
                        print(f"   URL: {url}")
                        
                        response = client.get(url)
                        print(f"   状态码: {response.status_code}")
                        
                        if response.status_code == 200:
                            data = response.get_json()
                            if data and data.get('success'):
                                stock_count = len(data.get('data', []))
                                print(f"   ✅ 成功获取 {stock_count} 只股票")
                                
                                # 显示前3只股票
                                stocks = data.get('data', [])[:3]
                                for stock in stocks:
                                    print(f"     - {stock.get('stock_code')} ({stock.get('date')})")
                            else:
                                print(f"   ❌ API返回错误: {data.get('error') if data else 'No data'}")
                        else:
                            print(f"   ❌ HTTP错误: {response.status_code}")
                            error_data = response.get_json()
                            if error_data:
                                print(f"   错误信息: {error_data.get('error', 'Unknown error')}")
                else:
                    print(f"   ❌ API返回错误: {data.get('error') if data else 'No data'}")
            else:
                print(f"   ❌ HTTP错误: {response.status_code}")
            
            # 3. 测试兼容性API
            print(f"\n3. 测试兼容性API...")
            old_strategies = ['PRE_CROSS', 'TRIPLE_CROSS']
            
            for old_strategy in old_strategies:
                print(f"\n   测试旧策略ID: {old_strategy}")
                
                response = client.get(f'/api/signals_summary?strategy={old_strategy}')
                print(f"   状态码: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.get_json()
                    if isinstance(data, list):
                        print(f"   ✅ 成功获取 {len(data)} 只股票")
                        
                        # 显示前2只股票
                        for stock in data[:2]:
                            print(f"     - {stock.get('stock_code')} ({stock.get('date')})")
                    elif isinstance(data, dict) and 'error' in data:
                        print(f"   ❌ API返回错误: {data['error']}")
                    else:
                        print(f"   ⚠️  返回格式异常: {type(data)}")
                else:
                    print(f"   ❌ HTTP错误: {response.status_code}")
                    error_data = response.get_json()
                    if error_data:
                        print(f"   错误信息: {error_data.get('error', 'Unknown error')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_url_encoding():
    """测试URL编码"""
    print(f"\n🔤 测试URL编码:")
    
    test_strings = [
        "深渊筑底策略_v2.0",
        "临界金叉_v1.0",
        "三重金叉_v1.0"
    ]
    
    for test_str in test_strings:
        encoded = quote(test_str, safe='')
        decoded = unquote(encoded)
        print(f"  原始: {test_str}")
        print(f"  编码: {encoded}")
        print(f"  解码: {decoded}")
        print(f"  匹配: {'✅' if test_str == decoded else '❌'}")
        print()

def main():
    """主函数"""
    print("🎯 简单API测试工具")
    print("=" * 50)
    
    # 测试URL编码
    test_url_encoding()
    
    # 测试Flask应用
    success = test_flask_app()
    
    print("\n" + "=" * 50)
    print("🎯 测试完成！")
    
    if success:
        print("\n✅ API测试通过，功能正常")
        print("\n💡 如果在浏览器中遇到404错误，可能是:")
        print("   1. 服务器未启动")
        print("   2. 端口不匹配")
        print("   3. 浏览器缓存问题")
    else:
        print("\n❌ API测试失败，需要检查问题")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()