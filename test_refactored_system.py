#!/usr/bin/env python3
"""
测试重构后的系统
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_data_handler():
    """测试统一数据处理模块"""
    print("🔍 测试统一数据处理模块...")
    try:
        from data_handler import get_full_data_with_indicators, get_stock_data_simple
        
        # 测试获取完整数据
        df = get_full_data_with_indicators('sh600006')
        if df is not None:
            print(f"✅ 成功获取 sh600006 数据，共 {len(df)} 条记录")
            print(f"   包含指标: {[col for col in df.columns if col in ['ma5', 'ma60', 'rsi6', 'macd']]}")
        else:
            print("❌ 获取数据失败")
            
        return df is not None
    except Exception as e:
        print(f"❌ 数据处理模块测试失败: {e}")
        return False

def test_backtester():
    """测试回测模块"""
    print("\n🔍 测试回测模块...")
    try:
        from backtester import get_deep_analysis
        
        result = get_deep_analysis('sh600006')
        if 'error' not in result:
            print("✅ 回测分析成功")
            print(f"   股票代码: {result.get('stock_code')}")
            print(f"   当前价格: {result.get('current_price')}")
            print(f"   分析时间: {result.get('analysis_time')}")
            
            # 检查关键字段
            if 'backtest_analysis' in result and 'trading_advice' in result:
                print("✅ 包含必要的分析结果")
                return True
            else:
                print("❌ 缺少关键分析结果")
                return False
        else:
            print(f"❌ 回测分析失败: {result['error']}")
            return False
    except Exception as e:
        print(f"❌ 回测模块测试失败: {e}")
        return False

def test_portfolio_manager():
    """测试持仓管理器"""
    print("\n🔍 测试持仓管理器...")
    try:
        from portfolio_manager import PortfolioManager
        
        pm = PortfolioManager()
        
        # 测试数据获取
        df = pm.get_stock_data('sh600006')
        if df is not None:
            print(f"✅ 持仓管理器数据获取成功，共 {len(df)} 条记录")
        else:
            print("❌ 持仓管理器数据获取失败")
            return False
            
        # 测试深度分析
        analysis = pm.analyze_position_deep('sh600006', 10.0, '2024-01-01')
        if 'error' not in analysis:
            print("✅ 持仓深度分析成功")
            print(f"   当前价格: {analysis.get('current_price')}")
            print(f"   盈亏比例: {analysis.get('profit_loss_pct', 0):.2f}%")
            return True
        else:
            print(f"❌ 持仓深度分析失败: {analysis['error']}")
            return False
    except Exception as e:
        print(f"❌ 持仓管理器测试失败: {e}")
        return False

def test_get_trading_advice():
    """测试交易建议脚本"""
    print("\n🔍 测试交易建议脚本...")
    try:
        from get_trading_advice import format_advice
        from backtester import get_deep_analysis
        
        # 获取分析结果
        analysis = get_deep_analysis('sh600006')
        if 'error' not in analysis:
            # 格式化输出
            advice_text = format_advice(analysis)
            if advice_text and not advice_text.startswith('❌'):
                print("✅ 交易建议格式化成功")
                print("   建议内容预览:")
                lines = advice_text.split('\n')[:5]
                for line in lines:
                    print(f"   {line}")
                return True
            else:
                print("❌ 交易建议格式化失败")
                return False
        else:
            print(f"❌ 无法获取分析结果: {analysis['error']}")
            return False
    except Exception as e:
        print(f"❌ 交易建议脚本测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 开始测试重构后的系统")
    print("=" * 50)
    
    tests = [
        ("数据处理模块", test_data_handler),
        ("回测模块", test_backtester),
        ("持仓管理器", test_portfolio_manager),
        ("交易建议脚本", test_get_trading_advice),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！重构成功！")
    else:
        print("⚠️  部分测试失败，需要进一步调试")
    
    return passed == total

if __name__ == "__main__":
    main()