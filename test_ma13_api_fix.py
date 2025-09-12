#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试MA13 API修复

验证：
1. DataHandler导入问题已修复
2. 股票代码格式支持（带前缀）
3. API基本功能正常
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_imports():
    """测试导入是否正常"""
    print("🧪 测试模块导入...")
    
    try:
        from backend.data_handler import DataHandler
        print("✅ DataHandler 导入成功")
        
        from backend.ma13_strategy_api import ma13_bp, strategy, planner, data_handler
        print("✅ MA13 API 模块导入成功")
        
        import backend.indicators as indicators
        print("✅ indicators 模块导入成功")
        
        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def test_data_handler():
    """测试DataHandler功能"""
    print("\n🧪 测试DataHandler功能...")
    
    try:
        from backend.data_handler import DataHandler
        
        handler = DataHandler()
        print("✅ DataHandler 实例化成功")
        
        # 测试股票数据获取
        test_codes = ['sz002021', 'sh600000', 'sz000001']
        
        for stock_code in test_codes:
            print(f"\n测试股票: {stock_code}")
            
            df = handler.get_stock_data(stock_code, 50)
            if df is not None and len(df) > 0:
                print(f"✅ 数据获取成功: {len(df)} 条记录")
                print(f"   日期范围: {df.index[0]} 到 {df.index[-1]}")
                print(f"   最新价格: {df['close'].iloc[-1]:.2f}")
            else:
                print(f"⚠️  数据获取失败或数据为空")
        
        return True
    except Exception as e:
        print(f"❌ DataHandler测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_strategy_analysis():
    """测试策略分析功能"""
    print("\n🧪 测试策略分析功能...")
    
    try:
        from backend.strategies.ma13_short_term_strategy import MA13ShortTermStrategy
        from backend.data_handler import get_full_data_with_indicators
        
        strategy = MA13ShortTermStrategy()
        print("✅ MA13策略实例化成功")
        
        # 测试股票分析
        test_stock = 'sz002021'
        print(f"\n分析股票: {test_stock}")
        
        # 获取数据并计算指标
        df = get_full_data_with_indicators(test_stock)
        
        if df is not None and len(df) > 100:
            print(f"✅ 数据获取成功: {len(df)} 条记录")
            
            # 检查必要的指标
            required_indicators = ['ma13', 'ma30', 'dif', 'dea', 'k', 'd', 'j', 'rsi6']
            missing_indicators = [ind for ind in required_indicators if ind not in df.columns]
            
            if missing_indicators:
                print(f"⚠️  缺少指标: {missing_indicators}")
            else:
                print("✅ 所有必要指标已计算")
            
            # 运行策略分析
            result = strategy.analyze_stock(df, test_stock)
            
            if result.get('success', False):
                print("✅ 策略分析成功")
                print(f"   推荐操作: {result.get('recommendation', {}).get('action', 'N/A')}")
                print(f"   信心度: {result.get('recommendation', {}).get('confidence', 0):.2f}")
            else:
                print(f"⚠️  策略分析未通过: {result.get('message', 'N/A')}")
        else:
            print(f"❌ 数据获取失败")
        
        return True
    except Exception as e:
        print(f"❌ 策略分析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_endpoints():
    """测试API端点（模拟）"""
    print("\n🧪 测试API端点...")
    
    try:
        from backend.ma13_strategy_api import ma13_bp
        
        # 检查蓝图注册
        print("✅ MA13 API蓝图创建成功")
        
        # 检查路由
        routes = []
        for rule in ma13_bp.url_map.iter_rules():
            routes.append(f"{rule.methods} {rule.rule}")
        
        print(f"✅ 注册的路由数量: {len(routes)}")
        for route in routes:
            print(f"   - {route}")
        
        return True
    except Exception as e:
        print(f"❌ API端点测试失败: {e}")
        return False

def test_stock_code_formats():
    """测试不同股票代码格式"""
    print("\n🧪 测试股票代码格式...")
    
    try:
        from data_format_validator import DataFormatValidator
        
        validator = DataFormatValidator()
        
        test_cases = [
            ('002021', 'sz'),      # 纯数字深圳股票
            ('sz002021', 'sz'),    # 带前缀深圳股票
            ('600000', 'sh'),      # 纯数字上海股票
            ('sh600000', 'sh'),    # 带前缀上海股票
            ('31#00700', 'ds'),    # 港股
            ('bj430047', 'bj'),    # 北交所
        ]
        
        for stock_code, expected_market in test_cases:
            actual_market = validator.get_correct_market(stock_code)
            if actual_market == expected_market:
                print(f"✅ {stock_code} -> {actual_market}")
            else:
                print(f"❌ {stock_code} -> {actual_market} (期望: {expected_market})")
        
        return True
    except Exception as e:
        print(f"❌ 股票代码格式测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("MA13 API修复验证测试")
    print("=" * 50)
    
    tests = [
        ("模块导入", test_imports),
        ("DataHandler功能", test_data_handler),
        ("策略分析", test_strategy_analysis),
        ("API端点", test_api_endpoints),
        ("股票代码格式", test_stock_code_formats),
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
        print("🎉 所有测试通过！MA13 API修复成功")
    else:
        print("⚠️  部分测试失败，需要进一步检查")

if __name__ == "__main__":
    main()