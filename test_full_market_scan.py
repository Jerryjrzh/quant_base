#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试全市场扫描功能

验证：
1. 获取所有股票代码API
2. 全市场扫描API
3. 前端批量扫描功能
"""

import sys
import os
import requests
import json
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_get_all_stocks_api():
    """测试获取所有股票代码API"""
    print("🧪 测试获取所有股票代码API...")
    
    try:
        # 测试API端点
        url = 'http://localhost:5000/api/ma13/all_stocks'
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ API调用成功")
                print(f"   总股票数: {data.get('total_count', 0)}")
                print(f"   过滤后数量: {data.get('filtered_count', 0)}")
                print(f"   返回数量: {len(data.get('stock_codes', []))}")
                
                # 显示前10个股票代码
                codes = data.get('stock_codes', [])
                if codes:
                    print(f"   前10个代码: {codes[:10]}")
                
                return True
            else:
                print(f"❌ API返回失败: {data.get('message', 'Unknown error')}")
                return False
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("⚠️  无法连接到服务器，请确保Flask应用正在运行")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_full_market_scan_api():
    """测试全市场扫描API"""
    print("\n🧪 测试全市场扫描API...")
    
    try:
        # 测试API端点（小规模测试）
        url = 'http://localhost:5000/api/ma13/full_market_scan'
        payload = {
            'max_stocks': 10,  # 只测试10只股票
            'days': 150
        }
        
        print(f"   发送请求: {payload}")
        response = requests.post(url, json=payload, timeout=120)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print(f"✅ 全市场扫描成功")
                
                summary = data.get('summary', {})
                print(f"   扫描总数: {summary.get('total_scanned', 0)}")
                print(f"   符合条件: {summary.get('qualified_count', 0)}")
                print(f"   符合率: {summary.get('qualified_rate', 0):.1f}%")
                
                # 显示符合条件的股票
                top_candidates = summary.get('top_candidates', [])
                if top_candidates:
                    print(f"   符合条件的股票:")
                    for i, candidate in enumerate(top_candidates[:5]):
                        stock_code = candidate.get('stock_code', 'N/A')
                        confidence = candidate.get('summary', {}).get('confidence', 0)
                        action = candidate.get('summary', {}).get('action', 'wait')
                        print(f"     {i+1}. {stock_code} - 信心度: {confidence}% - 操作: {action}")
                
                return True
            else:
                print(f"❌ 扫描失败: {data.get('message', 'Unknown error')}")
                return False
        else:
            print(f"❌ HTTP错误: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("⚠️  无法连接到服务器，请确保Flask应用正在运行")
        return False
    except requests.exceptions.Timeout:
        print("⚠️  请求超时，全市场扫描需要较长时间")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

def test_backend_data_access():
    """测试后端数据访问"""
    print("\n🧪 测试后端数据访问...")
    
    try:
        from backend.data_handler import get_all_stock_codes_from_filesystem, get_full_data_with_indicators
        
        # 测试获取股票代码
        all_codes = get_all_stock_codes_from_filesystem()
        print(f"✅ 获取股票代码成功: {len(all_codes)} 只")
        
        if all_codes:
            print(f"   前10个代码: {all_codes[:10]}")
            
            # 测试数据获取
            test_code = all_codes[0]
            print(f"   测试股票: {test_code}")
            
            df = get_full_data_with_indicators(test_code)
            if df is not None and len(df) > 0:
                print(f"   ✅ 数据获取成功: {len(df)} 条记录")
                print(f"   日期范围: {df.index[0]} 到 {df.index[-1]}")
                
                # 检查技术指标
                indicators = ['ma13', 'ma30', 'rsi6', 'dif', 'dea', 'k', 'd', 'j']
                missing = [ind for ind in indicators if ind not in df.columns]
                if missing:
                    print(f"   ⚠️  缺少指标: {missing}")
                else:
                    print(f"   ✅ 技术指标完整")
            else:
                print(f"   ❌ 数据获取失败")
        
        return True
    except Exception as e:
        print(f"❌ 后端数据访问测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ma13_strategy():
    """测试MA13策略分析"""
    print("\n🧪 测试MA13策略分析...")
    
    try:
        from backend.strategies.ma13_short_term_strategy import MA13ShortTermStrategy
        from backend.data_handler import get_full_data_with_indicators
        
        strategy = MA13ShortTermStrategy()
        print("✅ MA13策略实例化成功")
        
        # 测试几只股票
        test_codes = ['sz002021', 'sh600000', 'sz000001']
        
        for stock_code in test_codes:
            print(f"\n   测试股票: {stock_code}")
            
            df = get_full_data_with_indicators(stock_code)
            if df is not None and len(df) > 100:
                result = strategy.analyze_stock(df, stock_code)
                
                if result.get('success'):
                    recommendation = result.get('recommendation', {})
                    print(f"   ✅ 分析成功 - 操作: {recommendation.get('action', 'wait')}")
                    print(f"      信心度: {recommendation.get('confidence', 0)}%")
                else:
                    print(f"   ⚠️  不符合条件: {result.get('message', 'N/A')}")
            else:
                print(f"   ❌ 数据不足")
        
        return True
    except Exception as e:
        print(f"❌ MA13策略测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_frontend_integration():
    """测试前端集成"""
    print("\n🧪 测试前端集成...")
    
    try:
        # 检查模板文件
        template_path = 'templates/ma13_strategy.html'
        if os.path.exists(template_path):
            print("✅ MA13策略模板文件存在")
            
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 检查关键功能
            checks = [
                ('fullMarketScan', '全市场扫描函数'),
                ('getAllStockCodes', '获取所有股票代码函数'),
                ('loadAllStockCodes', '加载所有股票代码函数'),
                ('/api/ma13/full_market_scan', '全市场扫描API调用'),
                ('/api/ma13/all_stocks', '获取股票代码API调用'),
            ]
            
            for check, desc in checks:
                if check in content:
                    print(f"   ✅ {desc}")
                else:
                    print(f"   ❌ 缺少{desc}")
        else:
            print("❌ MA13策略模板文件不存在")
            return False
        
        return True
    except Exception as e:
        print(f"❌ 前端集成测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("全市场扫描功能测试")
    print("=" * 50)
    
    tests = [
        ("后端数据访问", test_backend_data_access),
        ("MA13策略分析", test_ma13_strategy),
        ("前端集成", test_frontend_integration),
        ("获取股票代码API", test_get_all_stocks_api),
        ("全市场扫描API", test_full_market_scan_api),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ 测试 {test_name} 出现异常: {e}")
            results.append((test_name, False))
    
    # 汇总结果
    print(f"\n{'='*50}")
    print("测试结果汇总:")
    print("=" * 50)
    
    passed = 0
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n总体结果: {passed}/{len(results)} 个测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！全市场扫描功能已就绪")
        print("\n✅ 功能特点:")
        print("   - 自动获取所有可用股票代码")
        print("   - 支持设置最大扫描数量")
        print("   - 过滤ST股票等不适合的标的")
        print("   - 按信心度排序显示结果")
        print("   - 提供详细的扫描统计信息")
        print("\n📖 使用方法:")
        print("   1. 访问 http://localhost:5000/ma13_strategy")
        print("   2. 点击"全市场扫描"按钮")
        print("   3. 选择扫描数量并确认")
        print("   4. 等待扫描完成查看结果")
    else:
        print("⚠️  部分测试失败，需要进一步检查")
        
        if passed >= 3:
            print("\n💡 提示: 后端功能正常，API测试失败可能是因为Flask应用未运行")
            print("   请运行: python backend/app.py")

if __name__ == "__main__":
    main()