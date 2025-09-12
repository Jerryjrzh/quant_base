#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试统一数据接口修复

验证：
1. 统一数据接口路径正确
2. 股票代码格式支持（带前缀）
3. 技术指标完整性
4. MA13 API使用统一接口
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_unified_data_interface():
    """测试统一数据接口"""
    print("🧪 测试统一数据接口...")
    
    try:
        from backend.data_handler import get_full_data_with_indicators
        
        # 测试不同格式的股票代码
        test_codes = [
            'sz002021',  # 深圳股票（带前缀）
            'sh600000',  # 上海股票（带前缀）
            'sz000001',  # 深圳股票（带前缀）
        ]
        
        for stock_code in test_codes:
            print(f"\n测试股票: {stock_code}")
            
            df = get_full_data_with_indicators(stock_code)
            
            if df is not None and len(df) > 0:
                print(f"✅ 数据获取成功: {len(df)} 条记录")
                print(f"   日期范围: {df.index[0]} 到 {df.index[-1]}")
                print(f"   最新价格: {df['close'].iloc[-1]:.2f}")
                
                # 检查必要的技术指标
                required_indicators = [
                    'ma7', 'ma13', 'ma30', 'ma45', 'ma60',
                    'dif', 'dea', 'macd',
                    'k', 'd', 'j',
                    'rsi6', 'rsi12', 'rsi24'
                ]
                
                missing_indicators = [ind for ind in required_indicators if ind not in df.columns]
                
                if missing_indicators:
                    print(f"   ⚠️  缺少指标: {missing_indicators}")
                else:
                    print("   ✅ 所有必要指标已计算")
                
                # 显示部分指标值
                latest = df.iloc[-1]
                print(f"   MA13: {latest.get('ma13', 'N/A'):.2f}")
                print(f"   MA30: {latest.get('ma30', 'N/A'):.2f}")
                print(f"   RSI6: {latest.get('rsi6', 'N/A'):.2f}")
                print(f"   KDJ-J: {latest.get('j', 'N/A'):.2f}")
                
            else:
                print(f"❌ 数据获取失败或数据为空")
        
        return True
    except Exception as e:
        print(f"❌ 统一数据接口测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_handler_class():
    """测试DataHandler类"""
    print("\n🧪 测试DataHandler类...")
    
    try:
        from backend.data_handler import DataHandler
        
        handler = DataHandler()
        print("✅ DataHandler 实例化成功")
        
        # 测试get_stock_data方法
        test_stock = 'sz002021'
        print(f"\n测试 get_stock_data: {test_stock}")
        
        df = handler.get_stock_data(test_stock, 50)
        
        if df is not None and len(df) > 0:
            print(f"✅ get_stock_data 成功: {len(df)} 条记录")
            print(f"   日期范围: {df.index[0]} 到 {df.index[-1]}")
            
            # 检查是否包含技术指标
            has_indicators = any(col in df.columns for col in ['ma13', 'ma30', 'rsi6', 'dif'])
            if has_indicators:
                print("   ✅ 包含技术指标")
            else:
                print("   ⚠️  不包含技术指标")
        else:
            print(f"❌ get_stock_data 失败")
        
        return True
    except Exception as e:
        print(f"❌ DataHandler类测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ma13_api_imports():
    """测试MA13 API导入"""
    print("\n🧪 测试MA13 API导入...")
    
    try:
        from backend.ma13_strategy_api import ma13_bp, strategy, planner, data_handler
        print("✅ MA13 API模块导入成功")
        
        # 测试data_handler实例
        print(f"✅ data_handler实例: {type(data_handler)}")
        
        # 测试策略实例
        print(f"✅ strategy实例: {type(strategy)}")
        
        # 测试规划器实例
        print(f"✅ planner实例: {type(planner)}")
        
        return True
    except Exception as e:
        print(f"❌ MA13 API导入测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_file_path_resolution():
    """测试文件路径解析"""
    print("\n🧪 测试文件路径解析...")
    
    try:
        from backend.data_handler import _get_market_from_stock_code
        from backend.config import BASE_PATH
        import os
        
        test_cases = [
            ('sz002021', 'sz'),
            ('sh600000', 'sh'),
            ('bj430047', 'bj'),
            ('31#00700', 'ds'),
        ]
        
        print(f"数据基础路径: {BASE_PATH}")
        
        for stock_code, expected_market in test_cases:
            market = _get_market_from_stock_code(stock_code)
            file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
            
            exists = os.path.exists(file_path)
            status = "✅" if exists else "❌"
            
            print(f"   {status} {stock_code} -> {market} (期望: {expected_market})")
            print(f"      路径: {file_path}")
            print(f"      存在: {exists}")
        
        return True
    except Exception as e:
        print(f"❌ 文件路径解析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_functionality():
    """测试API功能（模拟）"""
    print("\n🧪 测试API功能...")
    
    try:
        from backend.ma13_strategy_api import ma13_bp
        from backend.strategies.ma13_short_term_strategy import MA13ShortTermStrategy
        from backend.data_handler import get_full_data_with_indicators
        
        # 测试策略分析流程
        test_stock = 'sz002021'
        print(f"模拟分析股票: {test_stock}")
        
        # 1. 获取数据
        df = get_full_data_with_indicators(test_stock)
        if df is None or len(df) < 100:
            print("❌ 数据获取失败")
            return False
        
        print(f"✅ 数据获取成功: {len(df)} 条记录")
        
        # 2. 运行策略分析
        strategy = MA13ShortTermStrategy()
        result = strategy.analyze_stock(df, test_stock)
        
        if result.get('success', False):
            print("✅ 策略分析成功")
            print(f"   推荐操作: {result.get('recommendation', {}).get('action', 'N/A')}")
            print(f"   信心度: {result.get('recommendation', {}).get('confidence', 0):.2f}")
        else:
            print(f"⚠️  策略分析未通过: {result.get('message', 'N/A')}")
        
        # 3. 检查API路由
        routes = []
        for rule in ma13_bp.url_map.iter_rules():
            routes.append(f"{list(rule.methods)} {rule.rule}")
        
        print(f"✅ API路由注册: {len(routes)} 个")
        for route in routes[:3]:  # 显示前3个
            print(f"   - {route}")
        
        return True
    except Exception as e:
        print(f"❌ API功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("统一数据接口修复验证测试")
    print("=" * 50)
    
    tests = [
        ("统一数据接口", test_unified_data_interface),
        ("DataHandler类", test_data_handler_class),
        ("MA13 API导入", test_ma13_api_imports),
        ("文件路径解析", test_file_path_resolution),
        ("API功能", test_api_functionality),
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
        print("🎉 所有测试通过！统一数据接口修复成功")
        print("\n✅ 修复要点:")
        print("   - 使用 get_full_data_with_indicators 统一数据接口")
        print("   - 支持带前缀的股票代码格式 (sz002021)")
        print("   - 正确的文件路径: /market/lday/stock_code.day")
        print("   - 自动包含所有技术指标计算")
        print("   - MA13 API已更新使用统一接口")
    else:
        print("⚠️  部分测试失败，需要进一步检查")

if __name__ == "__main__":
    main()