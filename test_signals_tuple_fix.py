#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试信号元组格式修复
"""

import sys
import os
sys.path.append('backend')

from unified_analysis_service import get_or_run_analysis, _apply_strategy
from data_handler import get_full_data_with_indicators
from strategy_manager import strategy_manager

def test_signals_fix():
    """测试信号格式修复"""
    print("=" * 60)
    print("测试信号元组格式修复")
    print("=" * 60)
    
    # 测试股票和策略
    test_stock = "sh600833"
    test_strategy = "MACD零轴启动_v1.0"
    
    print(f"1. 测试股票: {test_stock}")
    print(f"2. 测试策略: {test_strategy}")
    print()
    
    # 获取数据
    print("3. 获取股票数据...")
    df = get_full_data_with_indicators(test_stock)
    if df is None:
        print("   ❌ 无法获取股票数据")
        return
    print(f"   ✅ 获取到 {len(df)} 条数据")
    
    # 测试策略应用
    print("4. 测试策略应用...")
    try:
        strategy_instance = strategy_manager.get_strategy_instance(test_strategy)
        if strategy_instance:
            raw_signals = strategy_instance.apply_strategy(df)
            print(f"   原始信号类型: {type(raw_signals)}")
            if isinstance(raw_signals, tuple):
                print(f"   元组长度: {len(raw_signals)}")
                print(f"   元组内容类型: {[type(x) for x in raw_signals]}")
        else:
            print("   ❌ 无法获取策略实例")
            return
    except Exception as e:
        print(f"   ❌ 策略应用失败: {e}")
        return
    
    # 测试修复后的策略应用
    print("5. 测试修复后的策略应用...")
    try:
        fixed_signals = _apply_strategy(test_strategy, df)
        print(f"   修复后信号类型: {type(fixed_signals)}")
        print(f"   信号数量: {len(fixed_signals)}")
        print(f"   有效信号数: {fixed_signals.sum() if hasattr(fixed_signals, 'sum') else 'N/A'}")
    except Exception as e:
        print(f"   ❌ 修复后策略应用失败: {e}")
        return
    
    # 测试完整的统一分析
    print("6. 测试完整的统一分析...")
    try:
        result = get_or_run_analysis(test_stock, test_strategy)
        if result['success']:
            print("   ✅ 统一分析成功")
            
            # 检查数据结构
            data = result['data']
            print(f"   图表数据: K线{len(data['chart_data']['kline_data'])}点, 指标{len(data['chart_data']['indicator_data'])}点, 信号{len(data['chart_data']['signal_points'])}点")
            
            # 检查回测结果
            backtest = data['analysis'].get('backtest_results', {})
            if 'error' not in backtest:
                print(f"   回测结果: 总信号{backtest.get('total_signals', 0)}, 胜率{backtest.get('win_rate', 'N/A')}")
            else:
                print(f"   回测错误: {backtest['error']}")
                
        else:
            print(f"   ❌ 统一分析失败: {result.get('error', '未知错误')}")
    except Exception as e:
        print(f"   ❌ 统一分析异常: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)
    print()
    print("修复内容:")
    print("✅ 修复了策略返回tuple格式时的处理")
    print("✅ 增强了信号格式检查和转换")
    print("✅ 改进了错误处理和调试信息")
    print("✅ 确保回测和图表数据生成的稳定性")

if __name__ == "__main__":
    test_signals_fix()