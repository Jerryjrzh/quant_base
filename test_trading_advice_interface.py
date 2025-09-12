#!/usr/bin/env python3
"""
测试交易建议接口 - 验证前后端数据结构一致性
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_unified_analysis_response_structure():
    """测试统一分析接口返回的数据结构"""
    print("🧪 测试统一分析接口数据结构...")
    
    try:
        from backend.unified_analysis_service import get_or_run_analysis
        
        test_stock = 'sh600006'
        test_strategy = 'MACD零轴启动_v1.0'
        
        # 调用统一分析服务
        result = get_or_run_analysis(test_stock, test_strategy)
        
        if not result.get('success'):
            print(f"❌ 统一分析失败: {result.get('error')}")
            return False
        
        print(f"✅ 统一分析成功: {test_stock}")
        
        # 检查数据结构
        data = result.get('data', {})
        analysis = data.get('analysis', {})
        
        print(f"📊 数据结构检查:")
        print(f"   - data.analysis 存在: {'✅' if analysis else '❌'}")
        print(f"   - data.analysis.trading_advice 存在: {'✅' if analysis.get('trading_advice') else '❌'}")
        print(f"   - data.analysis.deep_analysis 存在: {'✅' if analysis.get('deep_analysis') else '❌'}")
        
        # 检查trading_advice的具体内容
        trading_advice = analysis.get('trading_advice', {})
        if trading_advice:
            print(f"📋 交易建议内容:")
            print(f"   - action: {trading_advice.get('action', 'N/A')}")
            print(f"   - confidence: {trading_advice.get('confidence', 'N/A')}")
            print(f"   - current_price: {trading_advice.get('current_price', 'N/A')}")
            print(f"   - entry_price: {trading_advice.get('entry_price', 'N/A')}")
            print(f"   - target_price: {trading_advice.get('target_price', 'N/A')}")
            print(f"   - analysis_logic: {len(trading_advice.get('analysis_logic', []))} 条")
            
            # 检查前端期望的字段
            required_fields = ['action', 'confidence', 'current_price', 'entry_price', 'target_price', 'analysis_logic']
            missing_fields = [field for field in required_fields if field not in trading_advice]
            
            if missing_fields:
                print(f"⚠️  缺少前端期望的字段: {missing_fields}")
            else:
                print("✅ 包含所有前端期望的字段")
        else:
            print("❌ trading_advice 为空")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_deep_analysis_structure():
    """测试深度分析返回的数据结构"""
    print("\n🧪 测试深度分析数据结构...")
    
    try:
        from backend.backtester import get_deep_analysis
        
        test_stock = 'sh600006'
        
        # 调用深度分析
        result = get_deep_analysis(test_stock)
        
        if 'error' in result:
            print(f"❌ 深度分析失败: {result['error']}")
            return False
        
        print(f"✅ 深度分析成功: {test_stock}")
        
        # 检查数据结构
        trading_advice = result.get('trading_advice', {})
        
        print(f"📊 深度分析结构检查:")
        print(f"   - trading_advice 存在: {'✅' if trading_advice else '❌'}")
        
        if trading_advice:
            print(f"📋 交易建议详情:")
            for key, value in trading_advice.items():
                if key == 'analysis_logic' and isinstance(value, list):
                    print(f"   - {key}: {len(value)} 条逻辑")
                else:
                    print(f"   - {key}: {value}")
        
        return True
        
    except Exception as e:
        print(f"❌ 深度分析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_frontend_compatibility():
    """测试前端兼容性"""
    print("\n🧪 测试前端兼容性...")
    
    try:
        from backend.unified_analysis_service import get_or_run_analysis
        
        test_stock = 'sh600006'
        test_strategy = 'MACD零轴启动_v1.0'
        
        result = get_or_run_analysis(test_stock, test_strategy)
        
        if not result.get('success'):
            print(f"❌ 获取数据失败")
            return False
        
        # 模拟前端代码的数据访问路径
        unifiedData = result.get('data', {})
        
        # 前端代码: unifiedData.analysis.trading_advice
        tradingAdvice = None
        if unifiedData.get('analysis'):
            tradingAdvice = unifiedData['analysis'].get('enhanced_trading_advice') or unifiedData['analysis'].get('trading_advice')
        
        print(f"🎯 前端数据访问测试:")
        print(f"   - unifiedData.analysis 存在: {'✅' if unifiedData.get('analysis') else '❌'}")
        print(f"   - tradingAdvice 获取成功: {'✅' if tradingAdvice else '❌'}")
        
        if tradingAdvice:
            # 检查前端updateAdvicePanel函数期望的字段
            frontend_fields = {
                'action': tradingAdvice.get('action'),
                'confidence': tradingAdvice.get('confidence'),
                'entry_price': tradingAdvice.get('entry_price'),
                'target_price': tradingAdvice.get('target_price'),
                'stop_price': tradingAdvice.get('stop_price'),
                'current_price': tradingAdvice.get('current_price'),
                'resistance_level': tradingAdvice.get('resistance_level'),
                'support_level': tradingAdvice.get('support_level'),
                'analysis_logic': tradingAdvice.get('analysis_logic')
            }
            
            print(f"📋 前端字段检查:")
            for field, value in frontend_fields.items():
                status = "✅" if value is not None else "❌"
                print(f"   - {field}: {status} ({value})")
            
            missing_critical = [field for field in ['action', 'analysis_logic'] if frontend_fields[field] is None]
            if missing_critical:
                print(f"⚠️  缺少关键字段: {missing_critical}")
                return False
            else:
                print("✅ 前端兼容性测试通过")
                return True
        else:
            print("❌ 无法获取交易建议数据")
            return False
        
    except Exception as e:
        print(f"❌ 前端兼容性测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("🚀 开始交易建议接口测试\n")
    
    tests = [
        test_deep_analysis_structure,
        test_unified_analysis_response_structure,
        test_frontend_compatibility
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print(f"📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！交易建议接口修复成功。")
    else:
        print("⚠️  部分测试失败，需要进一步检查。")
    
    return passed == total

if __name__ == "__main__":
    main()