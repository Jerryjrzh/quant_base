"""
测试MA13策略集成效果

验证MA13策略在universal_screener和前端的集成情况
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

def test_universal_screener_integration():
    """测试universal_screener中的MA13策略集成"""
    print("🧪 测试Universal Screener中的MA13策略集成")
    print("=" * 60)
    
    try:
        from universal_screener import UniversalScreener
        
        # 创建测试股票池
        test_stock_pool = [
            {'stock_code': '002021', 'stock_name': '中捷资源'},
            {'stock_code': '600618', 'stock_name': '氯碱化工'},
            {'stock_code': '300739', 'stock_name': '明阳电路'}
        ]
        
        screener = UniversalScreener(stock_pool=test_stock_pool)
        
        # 测试MA13专项筛选
        print("📊 运行MA13专项筛选...")
        results = screener.run_ma13_screening(max_workers=2)
        
        print(f"✅ MA13筛选完成，发现 {len(results)} 个符合条件的股票")
        
        for result in results:
            print(f"   📈 {result.stock_code} ({result.stock_name})")
            print(f"      信号类型: {result.signal_type}")
            print(f"      汇合评分: {result.confluence_score:.1f}")
            print(f"      信心度: {result.confidence:.1%}")
            print(f"      质量等级: {result.quality_grade}")
            print()
        
        # 测试获取MA13候选股票
        print("🎯 获取MA13候选股票详细信息...")
        candidates = screener.get_ma13_candidates(min_confidence=0.5)
        
        print(f"✅ 获取到 {len(candidates)} 个候选股票")
        
        for candidate in candidates:
            print(f"   🔍 {candidate['stock_code']} - {candidate['stock_name']}")
            recommendation = candidate.get('recommendation', {})
            print(f"      操作建议: {recommendation.get('action', 'wait')}")
            print(f"      信心度: {recommendation.get('confidence', 0)}%")
            print(f"      建议仓位: {recommendation.get('position_size', 0):.1%}")
            
            key_levels = candidate.get('key_levels', {})
            print(f"      核心支撑: {key_levels.get('support_1_lower', 0):.2f}")
            print(f"      第一目标: {key_levels.get('target_1', 0):.2f}")
            print()
        
        return True
        
    except Exception as e:
        print(f"❌ Universal Screener集成测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def test_api_integration():
    """测试API集成"""
    print("🌐 测试MA13策略API集成")
    print("=" * 60)
    
    try:
        import requests
        
        base_url = "http://localhost:5000"
        
        # 测试策略信息API
        print("📋 测试策略信息API...")
        response = requests.get(f"{base_url}/api/ma13/strategy_info")
        
        if response.status_code == 200:
            info = response.json()
            print(f"✅ 策略信息获取成功")
            print(f"   策略名称: {info.get('strategy', {}).get('name', 'N/A')}")
            print(f"   版本: {info.get('strategy', {}).get('version', 'N/A')}")
            print(f"   API版本: {info.get('api_version', 'N/A')}")
        else:
            print(f"❌ 策略信息API失败: {response.status_code}")
            return False
        
        # 测试单股分析API
        print("\n🔍 测试单股分析API...")
        test_data = {
            "stock_code": "002021",
            "days": 150
        }
        
        response = requests.post(
            f"{base_url}/api/ma13/analyze",
            json=test_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 单股分析成功")
            print(f"   分析结果: {result.get('success', False)}")
            print(f"   消息: {result.get('message', 'N/A')}")
            
            if result.get('success'):
                recommendation = result.get('recommendation', {})
                print(f"   操作建议: {recommendation.get('action', 'wait')}")
                print(f"   信心度: {recommendation.get('confidence', 0)}%")
        else:
            print(f"❌ 单股分析API失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return False
        
        # 测试批量扫描API
        print("\n📊 测试批量扫描API...")
        batch_data = {
            "stock_codes": ["002021", "600618", "300739"],
            "days": 150
        }
        
        response = requests.post(
            f"{base_url}/api/ma13/batch_scan",
            json=batch_data,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 批量扫描成功")
            print(f"   扫描结果: {result.get('success', False)}")
            
            summary = result.get('summary', {})
            print(f"   总扫描数: {summary.get('total_scanned', 0)}")
            print(f"   符合条件: {summary.get('qualified_count', 0)}")
            print(f"   符合率: {summary.get('qualified_rate', 0):.1f}%")
        else:
            print(f"❌ 批量扫描API失败: {response.status_code}")
            return False
        
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保Flask应用正在运行")
        return False
    except Exception as e:
        print(f"❌ API集成测试失败: {str(e)}")
        return False

def test_frontend_integration():
    """测试前端集成"""
    print("🎨 测试前端集成")
    print("=" * 60)
    
    try:
        # 检查前端文件是否包含MA13相关内容
        
        # 检查index.html
        with open('frontend/index.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        html_checks = [
            ('MA13按钮', 'ma13-strategy-btn' in html_content),
            ('MA13面板', 'ma13-quick-panel' in html_content),
            ('MA13样式', 'ma13-strategy-button' in html_content),
            ('MA13刷新按钮', 'ma13-refresh' in html_content)
        ]
        
        print("📄 检查index.html集成:")
        for check_name, result in html_checks:
            status = "✅" if result else "❌"
            print(f"   {status} {check_name}: {'通过' if result else '失败'}")
        
        # 检查app.js
        with open('frontend/js/app.js', 'r', encoding='utf-8') as f:
            js_content = f.read()
        
        js_checks = [
            ('MA13事件监听', 'ma13-strategy-btn' in js_content),
            ('MA13分析函数', 'runMA13QuickAnalysis' in js_content),
            ('MA13页面打开', 'openMA13StrategyPage' in js_content),
            ('MA13结果显示', 'displayMA13QuickResult' in js_content)
        ]
        
        print("\n📜 检查app.js集成:")
        for check_name, result in js_checks:
            status = "✅" if result else "❌"
            print(f"   {status} {check_name}: {'通过' if result else '失败'}")
        
        # 检查MA13策略页面
        ma13_page_exists = os.path.exists('templates/ma13_strategy.html')
        print(f"\n🎯 MA13策略页面: {'✅ 存在' if ma13_page_exists else '❌ 不存在'}")
        
        all_checks = [result for _, result in html_checks + js_checks] + [ma13_page_exists]
        
        if all(all_checks):
            print("\n🎉 前端集成检查全部通过!")
            return True
        else:
            failed_count = len([r for r in all_checks if not r])
            print(f"\n⚠️ 前端集成检查发现 {failed_count} 个问题")
            return False
        
    except Exception as e:
        print(f"❌ 前端集成测试失败: {str(e)}")
        return False

def generate_integration_report():
    """生成集成报告"""
    print("\n📊 生成MA13策略集成报告")
    print("=" * 60)
    
    # 运行所有测试
    tests = [
        ("Universal Screener集成", test_universal_screener_integration),
        ("前端集成", test_frontend_integration),
        # API测试需要服务器运行，暂时跳过
        # ("API集成", test_api_integration),
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n🔬 运行 {test_name} 测试...")
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {str(e)}")
            results[test_name] = False
    
    # 生成报告
    print("\n" + "=" * 60)
    print("📋 MA13策略集成测试报告")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n📈 总体结果: {passed}/{total} 项测试通过 ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 所有集成测试通过，MA13策略已成功集成到系统中!")
    else:
        print("⚠️ 部分测试失败，请检查相关组件的集成情况")
    
    return passed == total

def main():
    """主函数"""
    print("🚀 MA13策略集成测试")
    print("=" * 60)
    print("测试MA13策略在universal_screener和前端的集成效果")
    print()
    
    success = generate_integration_report()
    
    if success:
        print("\n✨ 集成测试完成，系统准备就绪!")
        print("💡 使用说明:")
        print("   1. 启动Flask应用: python backend/app.py")
        print("   2. 访问主页面: http://localhost:5000")
        print("   3. 点击 '🎯 MA13短线' 按钮访问策略页面")
        print("   4. 在股票分析页面可以看到MA13快速分析面板")
    else:
        print("\n❌ 集成测试发现问题，请检查相关组件")

if __name__ == "__main__":
    main()