#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
测试持仓股票代码大小写修复
验证前端和后端的一致性
"""

import json
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from portfolio_manager import create_portfolio_manager

def test_portfolio_case_consistency():
    """测试持仓数据的大小写一致性"""
    print("=== 持仓股票代码大小写一致性测试 ===\n")
    
    # 1. 检查现有持仓数据
    portfolio_file = os.path.join('data', 'portfolio', 'portfolio.json')
    if os.path.exists(portfolio_file):
        with open(portfolio_file, 'r', encoding='utf-8') as f:
            portfolio = json.load(f)
        
        print(f"1. 现有持仓数据检查 (共{len(portfolio)}条):")
        uppercase_count = 0
        lowercase_count = 0
        
        for position in portfolio:
            stock_code = position['stock_code']
            if stock_code.isupper():
                uppercase_count += 1
                print(f"   ❌ 大写: {stock_code}")
            elif stock_code.islower():
                lowercase_count += 1
                print(f"   ✅ 小写: {stock_code}")
            else:
                print(f"   ⚠️  混合: {stock_code}")
        
        print(f"   小写数量: {lowercase_count}")
        print(f"   大写数量: {uppercase_count}")
        print(f"   一致性: {'✅ 通过' if uppercase_count == 0 else '❌ 失败'}\n")
    
    # 2. 测试持仓管理器
    print("2. 持仓管理器测试:")
    try:
        portfolio_manager = create_portfolio_manager()
        portfolio = portfolio_manager.load_portfolio()
        print(f"   ✅ 成功加载 {len(portfolio)} 条持仓记录")
        
        # 测试数据加载
        test_codes = ['sz300741', 'sh600618', 'sz002021']  # 使用小写
        success_count = 0
        
        for code in test_codes:
            # 查找该股票是否在持仓中
            position = next((p for p in portfolio if p['stock_code'] == code), None)
            if position:
                print(f"   ✅ 找到持仓: {code}")
                
                # 测试数据加载
                df = portfolio_manager.get_stock_data(code)
                if df is not None and len(df) > 0:
                    print(f"   ✅ 数据加载成功: {code} ({len(df)}条记录)")
                    success_count += 1
                else:
                    print(f"   ❌ 数据加载失败: {code}")
            else:
                print(f"   ⚠️  持仓中未找到: {code}")
        
        print(f"   数据加载成功率: {success_count}/{len(test_codes)}\n")
        
    except Exception as e:
        print(f"   ❌ 持仓管理器测试失败: {e}\n")
    
    # 3. 测试股票代码格式验证
    print("3. 股票代码格式验证测试:")
    test_cases = [
        ('sz000001', True, '深圳主板小写'),
        ('sh600000', True, '上海主板小写'),
        ('SZ000001', False, '深圳主板大写'),
        ('SH600000', False, '上海主板大写'),
        ('sz30001', False, '代码长度不足'),
        ('sz0000001', False, '代码长度过长'),
        ('bj000001', False, '不支持的市场'),
    ]
    
    for code, should_pass, description in test_cases:
        # 模拟验证逻辑
        is_valid = code and code.startswith(('sz', 'sh')) and len(code) == 8
        result = '✅ 通过' if is_valid == should_pass else '❌ 失败'
        print(f"   {result} {description}: {code} -> {is_valid}")
    
    print("\n=== 测试完成 ===")

if __name__ == '__main__':
    test_portfolio_case_consistency()