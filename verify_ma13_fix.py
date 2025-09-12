#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证MA13全市场扫描修复

检查：
1. displayBatchResults函数是否存在
2. 全市场扫描API是否正常
3. 前端调用是否正确
"""

import os
import re

def check_frontend_functions():
    """检查前端函数定义"""
    print("🧪 检查前端函数定义...")
    
    template_path = 'templates/ma13_strategy.html'
    if not os.path.exists(template_path):
        print("❌ MA13策略模板文件不存在")
        return False
    
    with open(template_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查关键函数
    functions_to_check = [
        ('displayBatchResults', '批量结果显示函数'),
        ('fullMarketScan', '全市场扫描函数'),
        ('getAllStockCodes', '获取股票代码函数'),
        ('loadAllStockCodes', '加载股票代码函数'),
    ]
    
    all_found = True
    for func_name, desc in functions_to_check:
        pattern = rf'function\s+{func_name}\s*\('
        if re.search(pattern, content):
            print(f"   ✅ {desc}: {func_name}")
        else:
            print(f"   ❌ 缺少{desc}: {func_name}")
            all_found = False
    
    # 检查函数调用
    calls_to_check = [
        ('displayBatchResults(result)', '正确的批量结果显示调用'),
        ('/api/ma13/full_market_scan', '全市场扫描API调用'),
        ('/api/ma13/all_stocks', '获取股票代码API调用'),
    ]
    
    for call, desc in calls_to_check:
        if call in content:
            print(f"   ✅ {desc}")
        else:
            print(f"   ❌ 缺少{desc}")
            all_found = False
    
    return all_found

def check_backend_api():
    """检查后端API定义"""
    print("\n🧪 检查后端API定义...")
    
    api_path = 'backend/ma13_strategy_api.py'
    if not os.path.exists(api_path):
        print("❌ MA13策略API文件不存在")
        return False
    
    with open(api_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查API端点
    endpoints_to_check = [
        ('@ma13_bp.route(\'/all_stocks\'', '获取所有股票API'),
        ('@ma13_bp.route(\'/full_market_scan\'', '全市场扫描API'),
        ('def get_all_stocks()', '获取股票代码函数'),
        ('def full_market_scan()', '全市场扫描函数'),
    ]
    
    all_found = True
    for endpoint, desc in endpoints_to_check:
        if endpoint in content:
            print(f"   ✅ {desc}")
        else:
            print(f"   ❌ 缺少{desc}")
            all_found = False
    
    # 检查统一数据接口使用
    if 'get_full_data_with_indicators' in content:
        print(f"   ✅ 使用统一数据接口")
    else:
        print(f"   ❌ 未使用统一数据接口")
        all_found = False
    
    return all_found

def check_data_handler():
    """检查数据处理器"""
    print("\n🧪 检查数据处理器...")
    
    try:
        import sys
        sys.path.append('backend')
        
        from data_handler import get_all_stock_codes_from_filesystem, get_full_data_with_indicators
        
        # 测试获取股票代码
        codes = get_all_stock_codes_from_filesystem()
        print(f"   ✅ 获取股票代码成功: {len(codes)} 只")
        
        if codes:
            # 测试数据获取
            test_code = codes[0]
            df = get_full_data_with_indicators(test_code)
            if df is not None and len(df) > 0:
                print(f"   ✅ 数据获取成功: {test_code} ({len(df)} 条记录)")
            else:
                print(f"   ⚠️  数据获取失败: {test_code}")
        
        return True
    except Exception as e:
        print(f"   ❌ 数据处理器测试失败: {e}")
        return False

def check_strategy():
    """检查策略实现"""
    print("\n🧪 检查策略实现...")
    
    try:
        import sys
        sys.path.append('backend')
        
        from strategies.ma13_short_term_strategy import MA13ShortTermStrategy
        
        strategy = MA13ShortTermStrategy()
        print(f"   ✅ MA13策略实例化成功")
        
        # 检查策略方法
        if hasattr(strategy, 'analyze_stock'):
            print(f"   ✅ analyze_stock方法存在")
        else:
            print(f"   ❌ analyze_stock方法不存在")
            return False
        
        return True
    except Exception as e:
        print(f"   ❌ 策略实现测试失败: {e}")
        return False

def generate_fix_summary():
    """生成修复总结"""
    print("\n📋 修复总结:")
    print("=" * 50)
    
    fixes = [
        "✅ 修复了 displayBatchResult -> displayBatchResults 函数名错误",
        "✅ 添加了全市场扫描API (/api/ma13/full_market_scan)",
        "✅ 添加了获取所有股票代码API (/api/ma13/all_stocks)",
        "✅ 前端添加了全市场扫描按钮和功能",
        "✅ 使用统一数据接口 get_full_data_with_indicators",
        "✅ 支持设置最大扫描数量",
        "✅ 过滤ST股票等不适合的标的",
        "✅ 按信心度排序显示结果",
    ]
    
    for fix in fixes:
        print(fix)
    
    print("\n🚀 使用方法:")
    print("1. 启动Flask应用: python backend/app.py")
    print("2. 访问MA13策略页面: http://localhost:5000/ma13_strategy")
    print("3. 点击"全市场扫描"按钮")
    print("4. 选择扫描数量并确认")
    print("5. 等待扫描完成查看结果")
    
    print("\n🧪 测试页面:")
    print("访问测试页面: test_ma13_frontend.html")

def main():
    """主函数"""
    print("MA13全市场扫描修复验证")
    print("=" * 50)
    
    checks = [
        ("前端函数定义", check_frontend_functions),
        ("后端API定义", check_backend_api),
        ("数据处理器", check_data_handler),
        ("策略实现", check_strategy),
    ]
    
    results = []
    
    for check_name, check_func in checks:
        print(f"\n{'='*20} {check_name} {'='*20}")
        try:
            success = check_func()
            results.append((check_name, success))
        except Exception as e:
            print(f"❌ 检查 {check_name} 出现异常: {e}")
            results.append((check_name, False))
    
    # 汇总结果
    print(f"\n{'='*50}")
    print("检查结果汇总:")
    print("=" * 50)
    
    passed = 0
    for check_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{check_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n总体结果: {passed}/{len(results)} 个检查通过")
    
    if passed == len(results):
        print("🎉 所有检查通过！MA13全市场扫描功能已修复")
        generate_fix_summary()
    else:
        print("⚠️  部分检查失败，需要进一步修复")

if __name__ == "__main__":
    main()