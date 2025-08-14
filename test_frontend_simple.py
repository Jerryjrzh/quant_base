#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的前端功能测试
"""

import os
import sys
import json

def test_strategy_config_file():
    """测试策略配置文件"""
    print("=== 测试策略配置文件 ===")
    
    config_file = "frontend/js/strategy-config.js"
    if not os.path.exists(config_file):
        print("❌ 策略配置文件不存在")
        return False
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查关键内容
        required_items = [
            'STRATEGY_ID_MAPPING',
            'mapOldToNewStrategyId',
            'mapNewToOldStrategyId',
            'PRE_CROSS',
            'ABYSS_BOTTOMING'
        ]
        
        for item in required_items:
            if item in content:
                print(f"✅ 找到必需项: {item}")
            else:
                print(f"❌ 缺少必需项: {item}")
                return False
        
        print("✅ 策略配置文件检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 读取策略配置文件失败: {e}")
        return False

def test_backend_integration():
    """测试后端集成"""
    print("\n=== 测试后端集成 ===")
    
    try:
        # 添加backend目录到路径
        sys.path.insert(0, 'backend')
        
        # 测试策略管理器
        from strategy_manager import strategy_manager
        
        print(f"✅ 策略管理器加载成功")
        print(f"   已注册策略数量: {len(strategy_manager.registered_strategies)}")
        
        # 获取策略列表
        strategies = strategy_manager.get_available_strategies()
        print(f"   可用策略数量: {len(strategies)}")
        
        for strategy in strategies:
            print(f"   - {strategy['name']} v{strategy['version']}")
            print(f"     ID: {strategy['id']}")
            print(f"     启用: {strategy.get('enabled', True)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 后端集成测试失败: {e}")
        return False

def test_html_structure():
    """测试HTML结构"""
    print("\n=== 测试HTML结构 ===")
    
    html_file = "frontend/index.html"
    if not os.path.exists(html_file):
        print("❌ HTML文件不存在")
        return False
    
    try:
        with open(html_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查关键元素
        required_elements = [
            'strategy-select',
            'strategy-config-btn',
            'strategy-config-modal',
            'strategy-config.js',
            'app.js'
        ]
        
        for element in required_elements:
            if element in content:
                print(f"✅ 找到必需元素: {element}")
            else:
                print(f"❌ 缺少必需元素: {element}")
                return False
        
        print("✅ HTML结构检查通过")
        return True
        
    except Exception as e:
        print(f"❌ 读取HTML文件失败: {e}")
        return False

def main():
    """主测试函数"""
    print("前端策略解耦功能简单测试")
    print("=" * 50)
    
    results = []
    
    # 执行测试
    results.append(("策略配置文件", test_strategy_config_file()))
    results.append(("后端集成", test_backend_integration()))
    results.append(("HTML结构", test_html_structure()))
    
    # 输出结果
    print("\n=== 测试结果汇总 ===")
    all_passed = True
    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name}: {status}")
        if not result:
            all_passed = False
    
    print(f"\n总体状态: {'✅ 所有测试通过' if all_passed else '⚠️ 部分测试失败'}")
    
    if all_passed:
        print("\n🎉 前端策略解耦功能实现成功！")
        print("\n下一步操作:")
        print("1. 启动后端服务: cd backend && python app.py")
        print("2. 访问前端界面: http://localhost:5000")
        print("3. 点击 '⚙️ 策略配置' 测试功能")
    else:
        print("\n⚠️ 请检查失败的测试项并修复相关问题")
    
    return all_passed

if __name__ == "__main__":
    main()