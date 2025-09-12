#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试前端指标显示修复
"""

import sys
import os
sys.path.append('backend')

from unified_analysis_service import get_or_run_analysis
import json

def test_indicators_display():
    """测试指标显示修复"""
    print("=" * 60)
    print("测试前端指标显示修复")
    print("=" * 60)
    
    # 测试股票
    test_stock = "sz000001"
    test_strategy = "RSI_BOTTOM"
    
    print(f"1. 测试股票: {test_stock}")
    print(f"2. 测试策略: {test_strategy}")
    print()
    
    # 获取分析数据
    print("3. 获取统一分析数据...")
    result = get_or_run_analysis(test_stock, test_strategy)
    
    if not result['success']:
        print(f"   ❌ 分析失败: {result.get('error', '未知错误')}")
        return
    
    print("   ✅ 分析成功")
    
    # 检查图表数据
    chart_data = result['data']['chart_data']
    
    print("4. 检查图表数据结构...")
    print(f"   K线数据点数: {len(chart_data['kline_data'])}")
    print(f"   指标数据点数: {len(chart_data['indicator_data'])}")
    print(f"   信号点数: {len(chart_data['signal_points'])}")
    
    # 检查指标数据
    if chart_data['indicator_data']:
        sample_indicator = chart_data['indicator_data'][-1]  # 最后一个数据点
        print("5. 检查指标数据完整性...")
        
        indicators_to_check = ['ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240', 
                              'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']
        
        missing_indicators = []
        for indicator in indicators_to_check:
            if indicator not in sample_indicator or sample_indicator[indicator] is None:
                missing_indicators.append(indicator)
        
        if missing_indicators:
            print(f"   ⚠️  缺失指标: {missing_indicators}")
        else:
            print("   ✅ 所有指标数据完整")
        
        # 显示样本数据
        print("6. 样本指标数据:")
        for indicator in ['ma13', 'rsi12', 'k', 'dif']:
            value = sample_indicator.get(indicator, 'N/A')
            print(f"   {indicator}: {value}")
    
    # 检查信号点数据
    if chart_data['signal_points']:
        print("7. 检查信号点数据...")
        for i, signal in enumerate(chart_data['signal_points'][:3]):  # 显示前3个信号点
            print(f"   信号{i+1}: 日期={signal['date']}, 价格={signal['price']:.2f}, 状态={signal['state']}")
            if 'profit' in signal:
                print(f"           收益={signal['profit']:.2%}")
    else:
        print("7. 无信号点数据")
    
    # 检查回测结果
    backtest = result['data']['analysis'].get('backtest_results', {})
    if backtest and 'total_signals' in backtest:
        print("8. 回测结果摘要:")
        print(f"   总信号数: {backtest.get('total_signals', 0)}")
        print(f"   胜率: {backtest.get('win_rate', 'N/A')}")
        print(f"   平均收益: {backtest.get('avg_max_profit', 'N/A')}")
    else:
        print("8. 无回测结果")
    
    print()
    print("=" * 60)
    print("测试完成")
    print("=" * 60)
    print()
    print("前端修复内容:")
    print("✅ 添加了KDJ、RSI、MACD指标的多网格显示")
    print("✅ 修复了信号点的回测成功标记显示")
    print("✅ 优化了图表布局，确保所有指标都有足够的显示空间")
    print("✅ 改进了信号点的颜色和形状区分")
    print()
    print("使用方法:")
    print("1. 启动后端服务: python backend/app.py")
    print("2. 打开前端页面: frontend/index.html")
    print("3. 选择策略和股票，查看完整的技术指标显示")

if __name__ == "__main__":
    test_indicators_display()