#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试可配置的港股数据加载功能
"""

import sys
import os
sys.path.append('backend')

from data_handler import (
    get_data_handler_config,
    get_hk_stock_codes,
    get_all_stock_codes_from_filesystem,
    filter_stocks_by_market,
    set_hk_stocks_enabled,
    get_full_data_with_indicators,
    get_stock_market_info
)

def test_configuration_toggle():
    """测试港股功能开关"""
    print("=== 港股功能开关测试 ===")
    
    # 显示初始配置
    config = get_data_handler_config()
    print(f"初始配置: {config}")
    
    # 测试禁用港股
    print("\n--- 禁用港股功能 ---")
    set_hk_stocks_enabled(False)
    hk_codes_disabled = get_hk_stock_codes()
    print(f"禁用后港股数量: {len(hk_codes_disabled)}")
    
    # 测试启用港股
    print("\n--- 启用港股功能 ---")
    set_hk_stocks_enabled(True)
    hk_codes_enabled = get_hk_stock_codes()
    print(f"启用后港股数量: {len(hk_codes_enabled)}")
    
    return hk_codes_enabled

def test_data_loading_with_config(hk_codes):
    """测试不同配置下的数据加载"""
    print("\n=== 数据加载配置测试 ===")
    
    if not hk_codes:
        print("没有港股数据可测试")
        return
    
    # 选择一只港股进行测试
    test_hk_code = hk_codes[0]
    print(f"测试港股: {test_hk_code}")
    
    # 获取市场信息
    market_info = get_stock_market_info(test_hk_code)
    print(f"市场信息: {market_info}")
    
    # 测试启用港股时的数据加载
    print("\n--- 港股功能启用时 ---")
    set_hk_stocks_enabled(True)
    df_enabled = get_full_data_with_indicators(test_hk_code)
    if df_enabled is not None:
        print(f"成功加载数据，行数: {len(df_enabled)}")
        print(f"最新价格: {df_enabled['close'].iloc[-1]:.3f}")
    else:
        print("数据加载失败")
    
    # 测试禁用港股时的数据加载
    print("\n--- 港股功能禁用时 ---")
    set_hk_stocks_enabled(False)
    df_disabled = get_full_data_with_indicators(test_hk_code)
    if df_disabled is not None:
        print(f"意外成功加载数据，行数: {len(df_disabled)}")
    else:
        print("按预期无法加载港股数据")

def test_stock_filtering():
    """测试股票过滤功能"""
    print("\n=== 股票过滤功能测试 ===")
    
    # 创建混合股票代码列表
    mixed_codes = ['sh600000', '31#00700', 'sz000001', '43#09988', 'sh600036']
    print(f"原始股票列表: {mixed_codes}")
    
    # 测试不同过滤配置
    filtered_no_hk = filter_stocks_by_market(mixed_codes, include_hk=False)
    filtered_with_hk = filter_stocks_by_market(mixed_codes, include_hk=True)
    
    print(f"不包含港股: {filtered_no_hk}")
    print(f"包含港股: {filtered_with_hk}")
    
    # 测试使用全局配置
    set_hk_stocks_enabled(True)
    filtered_global_enabled = filter_stocks_by_market(mixed_codes)
    
    set_hk_stocks_enabled(False)
    filtered_global_disabled = filter_stocks_by_market(mixed_codes)
    
    print(f"全局启用港股时: {filtered_global_enabled}")
    print(f"全局禁用港股时: {filtered_global_disabled}")

def main():
    """主测试函数"""
    print("港股可配置数据加载功能测试")
    print("=" * 50)
    
    try:
        # 测试配置开关
        hk_codes = test_configuration_toggle()
        
        # 测试数据加载
        test_data_loading_with_config(hk_codes)
        
        # 测试股票过滤
        test_stock_filtering()
        
        print("\n=== 测试完成 ===")
        
        # 恢复港股功能
        set_hk_stocks_enabled(True)
        final_config = get_data_handler_config()
        print(f"最终配置: {final_config}")
        
    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()