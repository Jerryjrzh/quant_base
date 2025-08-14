#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前端策略配置功能测试
测试策略动态加载和配置管理
"""

import os
import sys
import json
import time
import requests
from datetime import datetime

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

def test_strategy_api():
    """测试策略API接口"""
    base_url = "http://localhost:5000"
    
    print("=== 测试策略API接口 ===")
    
    try:
        # 测试获取策略列表
        print("\n1. 测试获取策略列表...")
        response = requests.get(f"{base_url}/api/strategies")
        
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                strategies = data['strategies']
                print(f"✅ 成功获取 {len(strategies)} 个策略")
                
                for strategy in strategies:
                    print(f"   - {strategy['name']} v{strategy['version']} (ID: {strategy['id']})")
                    print(f"     启用状态: {'✅' if strategy.get('enabled', True) else '❌'}")
                    print(f"     描述: {strategy.get('description', 'N/A')}")
                    print()
            else:
                print(f"❌ 获取策略列表失败: {data['error']}")
                return False
        else:
            print(f"❌ API请求失败: {response.status_code}")
            return False
        
        # 测试策略配置管理
        if strategies:
            test_strategy_id = strategies[0]['id']
            print(f"\n2. 测试策略配置管理 (策略: {test_strategy_id})...")
            
            # 获取策略配置
            config_response = requests.get(f"{base_url}/api/strategies/{test_strategy_id}/config")
            if config_response.status_code == 200:
                config_data = config_response.json()
                if config_data['success']:
                    print("✅ 成功获取策略配置")
                    print(f"   配置内容: {json.dumps(config_data['config'], indent=2, ensure_ascii=False)}")
                else:
                    print(f"❌ 获取策略配置失败: {config_data['error']}")
            
            # 测试策略启用/禁用
            print(f"\n3. 测试策略启用/禁用...")
            current_enabled = strategies[0].get('enabled', True)
            new_enabled = not current_enabled
            
            toggle_response = requests.post(
                f"{base_url}/api/strategies/{test_strategy_id}/toggle",
                json={'enabled': new_enabled}
            )
            
            if toggle_response.status_code == 200:
                toggle_data = toggle_response.json()
                if toggle_data['success']:
                    print(f"✅ 成功{'启用' if new_enabled else '禁用'}策略")
                    print(f"   消息: {toggle_data['message']}")
                    
                    # 恢复原状态
                    restore_response = requests.post(
                        f"{base_url}/api/strategies/{test_strategy_id}/toggle",
                        json={'enabled': current_enabled}
                    )
                    if restore_response.status_code == 200:
                        print("✅ 成功恢复策略原状态")
                else:
                    print(f"❌ 切换策略状态失败: {toggle_data['error']}")
            else:
                print(f"❌ 切换策略状态请求失败: {toggle_response.status_code}")
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保后端服务正在运行")
        return False
    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        return False

def test_frontend_compatibility():
    """测试前端兼容性"""
    print("\n=== 测试前端兼容性 ===")
    
    # 测试策略映射
    from frontend.js.strategy_config import (
        STRATEGY_ID_MAPPING, 
        mapOldToNewStrategyId, 
        mapNewToOldStrategyId
    ) if os.path.exists('frontend/js/strategy-config.js') else (None, None, None)
    
    if STRATEGY_ID_MAPPING:
        print("✅ 策略映射配置已加载")
        
        # 测试映射功能
        test_cases = [
            ('PRE_CROSS', '临界金叉_v1.0'),
            ('ABYSS_BOTTOMING', '深渊筑底策略_v2.0')
        ]
        
        for old_id, expected_new_id in test_cases:
            mapped_id = mapOldToNewStrategyId(old_id)
            if mapped_id == expected_new_id:
                print(f"✅ 映射测试通过: {old_id} -> {mapped_id}")
            else:
                print(f"❌ 映射测试失败: {old_id} -> {mapped_id} (期望: {expected_new_id})")
        
        # 测试反向映射
        for old_id, new_id in test_cases:
            reverse_mapped = mapNewToOldStrategyId(new_id)
            if reverse_mapped == old_id:
                print(f"✅ 反向映射测试通过: {new_id} -> {reverse_mapped}")
            else:
                print(f"❌ 反向映射测试失败: {new_id} -> {reverse_mapped} (期望: {old_id})")
    else:
        print("⚠️ 策略映射配置未找到，跳过兼容性测试")

def generate_test_report():
    """生成测试报告"""
    report = {
        'test_time': datetime.now().isoformat(),
        'test_results': {
            'strategy_api': False,
            'frontend_compatibility': False
        },
        'recommendations': []
    }
    
    print("\n=== 生成测试报告 ===")
    
    # 执行测试
    api_result = test_strategy_api()
    compat_result = test_frontend_compatibility()
    
    report['test_results']['strategy_api'] = api_result
    report['test_results']['frontend_compatibility'] = compat_result
    
    # 生成建议
    if not api_result:
        report['recommendations'].append("检查后端服务是否正常运行")
        report['recommendations'].append("验证策略管理器是否正确初始化")
    
    if not compat_result:
        report['recommendations'].append("检查前端策略映射配置")
        report['recommendations'].append("确保JavaScript配置文件正确加载")
    
    if api_result and compat_result:
        report['recommendations'].append("所有测试通过，系统运行正常")
    
    # 保存报告
    report_file = f"frontend_strategy_config_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 测试报告已保存: {report_file}")
    
    # 打印总结
    print(f"\n=== 测试总结 ===")
    print(f"策略API测试: {'✅ 通过' if api_result else '❌ 失败'}")
    print(f"前端兼容性测试: {'✅ 通过' if compat_result else '❌ 失败'}")
    print(f"总体状态: {'✅ 系统正常' if api_result and compat_result else '⚠️ 需要修复'}")
    
    return report

if __name__ == "__main__":
    print("前端策略配置功能测试")
    print("=" * 50)
    
    report = generate_test_report()
    
    # 如果测试失败，提供帮助信息
    if not all(report['test_results'].values()):
        print("\n=== 故障排除建议 ===")
        for rec in report['recommendations']:
            print(f"• {rec}")
        
        print("\n=== 启动后端服务 ===")
        print("如果后端服务未运行，请执行:")
        print("cd backend && python app.py")