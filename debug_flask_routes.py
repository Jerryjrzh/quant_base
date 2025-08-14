#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试Flask路由
检查所有注册的路由
"""

import sys
import os

# 添加backend路径
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)
os.chdir(backend_path)

def debug_flask_routes():
    """调试Flask路由"""
    print("🔍 调试Flask路由")
    print("=" * 50)
    
    try:
        from screening_api import app
        
        print("✅ Flask应用导入成功")
        
        # 显示所有注册的路由
        print("\n📋 注册的路由:")
        for rule in app.url_map.iter_rules():
            methods = ', '.join(rule.methods - {'HEAD', 'OPTIONS'})
            print(f"  {rule.rule:<50} [{methods}] -> {rule.endpoint}")
        
        # 检查特定路由
        target_routes = [
            '/api/strategies',
            '/api/strategies/<path:strategy_id>/stocks',
            '/api/signals_summary',
            '/api/config/unified',
            '/api/system/info'
        ]
        
        print(f"\n🎯 检查目标路由:")
        registered_rules = [rule.rule for rule in app.url_map.iter_rules()]
        
        for target in target_routes:
            if any(target in rule or rule in target for rule in registered_rules):
                print(f"  ✅ {target}")
            else:
                print(f"  ❌ {target} (未找到)")
        
        # 测试路由匹配
        print(f"\n🧪 测试路由匹配:")
        test_urls = [
            '/api/strategies',
            '/api/strategies/深渊筑底策略_v2.0/stocks',
            '/api/strategies/临界金叉_v1.0/stocks',
            '/api/signals_summary'
        ]
        
        with app.test_client() as client:
            for url in test_urls:
                try:
                    # 只测试路由匹配，不实际执行
                    with app.test_request_context(url):
                        endpoint, values = app.url_map.bind('localhost').match(url)
                        print(f"  ✅ {url} -> {endpoint}")
                except Exception as e:
                    print(f"  ❌ {url} -> {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Flask应用导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_strategy_manager():
    """测试策略管理器"""
    print(f"\n🧪 测试策略管理器:")
    
    try:
        from strategy_manager import strategy_manager
        
        strategies = strategy_manager.get_available_strategies()
        print(f"  ✅ 获取到 {len(strategies)} 个策略")
        
        for strategy in strategies[:3]:
            strategy_id = strategy.get('id', 'Unknown')
            name = strategy.get('name', 'Unknown')
            print(f"    - {strategy_id}: {name}")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 策略管理器测试失败: {e}")
        return False

def test_screener():
    """测试筛选器"""
    print(f"\n🧪 测试筛选器:")
    
    try:
        from universal_screener import UniversalScreener
        
        screener = UniversalScreener()
        print(f"  ✅ 筛选器初始化成功")
        
        return True
        
    except Exception as e:
        print(f"  ❌ 筛选器测试失败: {e}")
        return False

def main():
    """主函数"""
    print("🎯 Flask路由调试工具")
    print("=" * 50)
    
    # 1. 调试Flask路由
    flask_ok = debug_flask_routes()
    
    # 2. 测试策略管理器
    strategy_ok = test_strategy_manager()
    
    # 3. 测试筛选器
    screener_ok = test_screener()
    
    print("\n" + "=" * 50)
    print("🎯 调试完成！")
    
    if flask_ok and strategy_ok and screener_ok:
        print("\n✅ 所有组件正常，API应该可以正常工作")
        print("\n📋 下一步:")
        print("  1. 启动API服务: python start_strategy_stock_api.py")
        print("  2. 测试路由: python test_api_routes.py")
    else:
        print("\n❌ 部分组件有问题，需要修复")
        
        if not flask_ok:
            print("  - Flask应用有问题")
        if not strategy_ok:
            print("  - 策略管理器有问题")
        if not screener_ok:
            print("  - 筛选器有问题")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  调试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 调试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()