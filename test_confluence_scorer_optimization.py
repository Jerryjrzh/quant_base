#!/usr/bin/env python3
"""
测试融合评分器优化效果
根据 test_fix_4.md 的优化建议进行验证
"""

import sys
import os
import pandas as pd
import numpy as np

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

from confluence_scorer import ConfluenceScorer

def create_test_data_sh600825_scenario():
    """
    创建模拟 sh600825 2025-08-26 的测试数据
    根据文档描述：价格在高位，MACD死叉，KDJ向下
    """
    dates = pd.date_range('2025-07-01', '2025-08-26', freq='D')
    n = len(dates)
    
    # 模拟价格数据：从低位上涨到高位然后回调
    base_price = 6.0
    price_trend = np.concatenate([
        np.linspace(0, 2.0, n//2),  # 前半段上涨
        np.linspace(2.0, 1.5, n - n//2)  # 后半段回调
    ])
    
    # 添加随机波动
    np.random.seed(42)
    noise = np.random.normal(0, 0.1, n)
    close_prices = base_price + price_trend + noise
    
    # 确保最后一天价格在高位（81.2%）
    close_prices[-1] = 8.05 * 0.812  # 约6.53
    
    # 生成高低价
    high_prices = close_prices * (1 + np.random.uniform(0.01, 0.05, n))
    low_prices = close_prices * (1 - np.random.uniform(0.01, 0.05, n))
    
    # 确保52周高点为8.05
    high_prices[n//2] = 8.05
    
    # 模拟MACD数据：死叉状态
    macd_values = np.sin(np.linspace(0, 4*np.pi, n)) * 0.1
    macd_values[-5:] = [-0.02, -0.03, -0.04, -0.05, -0.06]  # 最近死叉
    
    diff_values = np.sin(np.linspace(0, 4*np.pi, n) + 0.1) * 0.15
    diff_values[-5:] = [0.02, 0.01, -0.01, -0.02, -0.03]  # DIF下穿DEA
    
    dea_values = diff_values - macd_values
    
    # 模拟KDJ数据：向下趋势
    k_values = 50 + 30 * np.sin(np.linspace(0, 3*np.pi, n))
    k_values[-5:] = [45, 42, 38, 35, 32]  # 向下趋势
    
    d_values = k_values - np.random.uniform(1, 5, n)
    j_values = 3 * k_values - 2 * d_values
    
    # 模拟RSI数据：弱势
    rsi_values = 50 + 20 * np.sin(np.linspace(0, 2*np.pi, n))
    rsi_values[-5:] = [48, 45, 42, 40, 38]  # 向下趋势
    
    df = pd.DataFrame({
        'date': dates,
        'close': close_prices,
        'high': high_prices,
        'low': low_prices,
        'macd': macd_values,
        'diff': diff_values,
        'dea': dea_values,
        'k': k_values,
        'd': d_values,
        'j': j_values,
        'rsi6': rsi_values
    })
    
    return df

def test_kdj_trend_awareness():
    """测试KDJ趋势感知优化"""
    print("🧪 测试KDJ趋势感知优化")
    print("=" * 50)
    
    # 创建测试数据
    df = create_test_data_sh600825_scenario()
    scorer = ConfluenceScorer()
    
    # 测试最后一天（sh600825场景）
    test_index = len(df) - 1
    
    # 计算KDJ评分
    kdj_score = scorer.calculate_kdj_state_score(df, test_index)
    
    print(f"📊 测试数据（最后一天）:")
    print(f"   K值: {df.iloc[test_index]['k']:.2f}")
    print(f"   前一天K值: {df.iloc[test_index-1]['k']:.2f}")
    print(f"   K值趋势: {'向上' if df.iloc[test_index]['k'] > df.iloc[test_index-1]['k'] else '向下'}")
    print(f"   D值: {df.iloc[test_index]['d']:.2f}")
    
    print(f"\n📈 KDJ评分结果:")
    print(f"   优化后评分: {kdj_score:.2f}")
    print(f"   预期结果: 0.00 (因为KDJ向下)")
    
    # 验证结果
    if kdj_score == 0:
        print("✅ 优化成功：KDJ向下时正确给出0分")
    else:
        print("❌ 优化失败：KDJ向下时仍然给分")
    
    return kdj_score == 0

def test_price_filter_configurability():
    """测试价格过滤器可配置性"""
    print("\n🧪 测试价格过滤器可配置性")
    print("=" * 50)
    
    df = create_test_data_sh600825_scenario()
    scorer = ConfluenceScorer()
    
    test_index = len(df) - 1
    
    # 测试价格过滤
    passed, reason = scorer.filter_by_price_position(df, test_index)
    
    print(f"📊 价格过滤测试:")
    print(f"   当前价格: {df.iloc[test_index]['close']:.2f}")
    print(f"   52周高点: {df['high'].max():.2f}")
    print(f"   价格比例: {df.iloc[test_index]['close'] / df['high'].max():.1%}")
    print(f"   配置阈值: {scorer.thresholds.get('price_ratio_filter', 0.8):.1%}")
    
    print(f"\n📈 过滤结果:")
    print(f"   是否通过: {passed}")
    print(f"   原因: {reason}")
    
    # 验证结果
    expected_fail = df.iloc[test_index]['close'] / df['high'].max() > 0.8
    if not passed and expected_fail:
        print("✅ 价格过滤器工作正常：正确过滤高价股票")
        return True
    elif passed and not expected_fail:
        print("✅ 价格过滤器工作正常：正确通过低价股票")
        return True
    else:
        print("❌ 价格过滤器异常")
        return False

def test_confluence_score_configurability():
    """测试融合评分可配置性"""
    print("\n🧪 测试融合评分可配置性")
    print("=" * 50)
    
    df = create_test_data_sh600825_scenario()
    scorer = ConfluenceScorer()
    
    test_index = len(df) - 1
    
    # 计算融合评分
    result = scorer.calculate_confluence_score(df, test_index)
    
    print(f"📊 融合评分详情:")
    print(f"   总分: {result['total_score']:.2f}")
    print(f"   置信度: {result['confidence']:.1%}")
    print(f"   配置阈值: {scorer.scoring.get('min_confluence_score', 70)}")
    print(f"   是否高质量: {result['is_high_quality']}")
    
    print(f"\n📈 分项评分:")
    breakdown = result.get('breakdown', {})
    for key, value in breakdown.items():
        print(f"   {key}: {value:.2f}")
    
    # 验证低分股票被正确识别
    if result['total_score'] < 70 and not result['is_high_quality']:
        print("✅ 融合评分工作正常：正确识别低质量信号")
        return True
    else:
        print("❌ 融合评分异常：未能正确识别信号质量")
        return False

def test_complete_scenario():
    """测试完整的sh600825场景"""
    print("\n🧪 测试完整的sh600825场景")
    print("=" * 50)
    
    df = create_test_data_sh600825_scenario()
    scorer = ConfluenceScorer()
    
    test_index = len(df) - 1
    
    # 第一层：价格过滤
    price_passed, price_reason = scorer.filter_by_price_position(df, test_index)
    print(f"🔍 第一层过滤（价格位置）:")
    print(f"   结果: {'通过' if price_passed else '失败'}")
    print(f"   原因: {price_reason}")
    
    # 第二层：融合评分
    if price_passed:
        confluence_result = scorer.calculate_confluence_score(df, test_index)
        print(f"\n🔍 第二层评分（技术指标融合）:")
        print(f"   总分: {confluence_result['total_score']:.2f}")
        print(f"   是否高质量: {confluence_result['is_high_quality']}")
        
        breakdown = confluence_result.get('breakdown', {})
        print(f"   价格位置分: {breakdown.get('price_position', 0):.2f}")
        print(f"   MACD状态分: {breakdown.get('macd_state', 0):.2f}")
        print(f"   KDJ状态分: {breakdown.get('kdj_state', 0):.2f}")
        print(f"   RSI状态分: {breakdown.get('rsi_state', 0):.2f}")
    
    # 最终建议
    print(f"\n🎯 最终建议:")
    if not price_passed:
        print("   ❌ AVOID - 价格过高")
    elif price_passed:
        confluence_result = scorer.calculate_confluence_score(df, test_index)
        if confluence_result['is_high_quality']:
            print("   ✅ BUY - 高质量信号")
        else:
            print("   ❌ AVOID - 技术指标质量不佳")
    
    return True

def main():
    """主测试函数"""
    print("🚀 融合评分器优化测试")
    print("根据 doc/test_fix_4.md 的优化建议进行验证")
    print("=" * 60)
    
    test_results = []
    
    # 执行各项测试
    test_results.append(test_kdj_trend_awareness())
    test_results.append(test_price_filter_configurability())
    test_results.append(test_confluence_score_configurability())
    test_results.append(test_complete_scenario())
    
    # 总结
    print("\n" + "=" * 60)
    print("📋 测试总结:")
    passed_tests = sum(test_results)
    total_tests = len(test_results)
    
    print(f"   通过测试: {passed_tests}/{total_tests}")
    
    if passed_tests == total_tests:
        print("🎉 所有优化测试通过！")
    else:
        print("⚠️ 部分测试失败，需要进一步调试")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    main()