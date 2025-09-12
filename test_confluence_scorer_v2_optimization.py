#!/usr/bin/env python3
"""
测试融合评分器V2优化效果
根据 test_fix_5.md 的优化建议进行验证
"""

import sys
import os
import pandas as pd
import numpy as np

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

from confluence_scorer import ConfluenceScorer

def create_sh600702_scenario():
    """
    创建模拟 sh600702 2025-08-14 的测试数据
    根据文档描述：价格位置好，MACD持续金叉，RSI在健康区间
    """
    dates = pd.date_range('2025-07-01', '2025-08-14', freq='D')
    n = len(dates)
    
    # 模拟价格数据：处于相对低位
    base_price = 20.0
    price_trend = np.linspace(0, 2.0, n)  # 缓慢上涨
    
    # 添加随机波动
    np.random.seed(42)
    noise = np.random.normal(0, 0.3, n)
    close_prices = base_price + price_trend + noise
    
    # 生成高低价
    high_prices = close_prices * (1 + np.random.uniform(0.01, 0.03, n))
    low_prices = close_prices * (1 - np.random.uniform(0.01, 0.03, n))
    
    # 确保价格在相对低位（约40%位置）
    max_high = high_prices.max()
    current_price = close_prices[-1]
    target_ratio = 0.4  # 40%位置
    adjustment = (max_high * target_ratio) / current_price
    close_prices *= adjustment
    high_prices *= adjustment
    low_prices *= adjustment
    
    # 模拟MACD数据：持续金叉状态
    diff_values = np.array([0.1] * n)  # DIF持续在DEA上方
    dea_values = np.array([0.05] * n)  # DEA稳定
    macd_values = diff_values - dea_values  # MACD柱状线为正
    
    # 最后一天保持金叉但柱状线没有翻红（测试持续状态奖励）
    macd_values[-1] = 0.05  # 正值但不是刚翻红
    
    # 模拟KDJ数据：向上趋势
    k_values = np.linspace(30, 45, n)  # 从低位向上
    d_values = k_values - 5
    j_values = 3 * k_values - 2 * d_values
    
    # 模拟RSI数据：在健康看涨区间（50-75）
    rsi_values = np.array([60] * n)  # 稳定在看涨区间
    rsi_values[-1] = 62  # 最后一天略有上升
    rsi_values[-2] = 61  # 前一天
    
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

def test_macd_v2_optimization():
    """测试MACD V2优化：奖励持续的健康状态"""
    print("🧪 测试MACD V2优化")
    print("=" * 50)
    
    # 创建测试数据
    df = create_sh600702_scenario()
    scorer = ConfluenceScorer()
    
    # 测试最后一天
    test_index = len(df) - 1
    
    # 计算MACD评分
    macd_score = scorer.calculate_macd_state_score(df, test_index)
    
    print(f"📊 测试数据（最后一天）:")
    print(f"   DIFF值: {df.iloc[test_index]['diff']:.3f}")
    print(f"   DEA值: {df.iloc[test_index]['dea']:.3f}")
    print(f"   MACD值: {df.iloc[test_index]['macd']:.3f}")
    print(f"   前一天MACD: {df.iloc[test_index-1]['macd']:.3f}")
    print(f"   是否金叉: {'是' if df.iloc[test_index]['diff'] > df.iloc[test_index]['dea'] else '否'}")
    print(f"   MACD是否为正: {'是' if df.iloc[test_index]['macd'] > 0 else '否'}")
    
    print(f"\n📈 MACD评分结果:")
    print(f"   V2优化后评分: {macd_score:.2f}")
    print(f"   权重上限: {scorer.weights['macd_state']}")
    print(f"   预期结果: 15-25分 (持续金叉状态)")
    
    # 验证结果
    expected_min = 15
    expected_max = 25
    if expected_min <= macd_score <= expected_max:
        print("✅ MACD V2优化成功：正确奖励持续金叉状态")
        return True
    else:
        print("❌ MACD V2优化失败：评分不在预期范围")
        return False

def test_rsi_v2_optimization():
    """测试RSI V2优化：奖励健康看涨区间"""
    print("\n🧪 测试RSI V2优化")
    print("=" * 50)
    
    df = create_sh600702_scenario()
    scorer = ConfluenceScorer()
    
    test_index = len(df) - 1
    
    # 计算RSI评分
    rsi_score = scorer.calculate_rsi_state_score(df, test_index)
    
    print(f"📊 测试数据（最后一天）:")
    print(f"   RSI值: {df.iloc[test_index]['rsi6']:.1f}")
    print(f"   前一天RSI: {df.iloc[test_index-1]['rsi6']:.1f}")
    print(f"   RSI趋势: {'向上' if df.iloc[test_index]['rsi6'] > df.iloc[test_index-1]['rsi6'] else '向下'}")
    print(f"   看涨区间: {scorer.thresholds.get('rsi_bullish_low', 50)}-{scorer.thresholds.get('rsi_bullish_high', 75)}")
    print(f"   是否在看涨区间: {'是' if 50 <= df.iloc[test_index]['rsi6'] <= 75 else '否'}")
    
    print(f"\n📈 RSI评分结果:")
    print(f"   V2优化后评分: {rsi_score:.2f}")
    print(f"   权重上限: {scorer.weights['rsi_state']}")
    print(f"   预期结果: 5-8分 (健康看涨区间)")
    
    # 验证结果
    expected_min = 5
    expected_max = 8
    if expected_min <= rsi_score <= expected_max:
        print("✅ RSI V2优化成功：正确奖励健康看涨区间")
        return True
    else:
        print("❌ RSI V2优化失败：评分不在预期范围")
        return False

def test_overall_score_improvement():
    """测试整体评分改善"""
    print("\n🧪 测试整体评分改善")
    print("=" * 50)
    
    df = create_sh600702_scenario()
    scorer = ConfluenceScorer()
    
    test_index = len(df) - 1
    
    # 计算融合评分
    result = scorer.calculate_confluence_score(df, test_index)
    
    print(f"📊 融合评分详情:")
    print(f"   总分: {result['total_score']:.2f}")
    print(f"   置信度: {result['confidence']:.1%}")
    print(f"   评分阈值: {scorer.scoring.get('min_confluence_score', 70)}")
    print(f"   是否高质量: {result['is_high_quality']}")
    
    print(f"\n📈 分项评分:")
    breakdown = result.get('breakdown', {})
    for key, value in breakdown.items():
        print(f"   {key}: {value:.2f}")
    
    # 验证结果
    expected_min_score = 70  # 应该超过阈值
    if result['total_score'] >= expected_min_score and result['is_high_quality']:
        print("✅ 整体评分改善成功：sh600702类型股票现在能通过评分阈值")
        return True
    else:
        print("❌ 整体评分改善失败：仍未达到预期效果")
        return False

def test_comparison_with_old_logic():
    """对比V1和V2逻辑的差异"""
    print("\n🧪 对比V1和V2逻辑差异")
    print("=" * 50)
    
    df = create_sh600702_scenario()
    scorer = ConfluenceScorer()
    
    test_index = len(df) - 1
    
    # V2评分
    v2_macd = scorer.calculate_macd_state_score(df, test_index)
    v2_rsi = scorer.calculate_rsi_state_score(df, test_index)
    v2_total = scorer.calculate_confluence_score(df, test_index)['total_score']
    
    print(f"📊 V2优化后评分:")
    print(f"   MACD评分: {v2_macd:.2f}")
    print(f"   RSI评分: {v2_rsi:.2f}")
    print(f"   总评分: {v2_total:.2f}")
    
    # 模拟V1逻辑的预期结果（基于文档描述）
    v1_macd_expected = 3.0  # 文档中提到的低分
    v1_rsi_expected = 0.0   # 文档中提到的零分
    v1_total_expected = 67.0  # 文档中提到的总分
    
    print(f"\n📊 V1逻辑预期结果（基于文档）:")
    print(f"   MACD评分: {v1_macd_expected:.2f}")
    print(f"   RSI评分: {v1_rsi_expected:.2f}")
    print(f"   总评分: {v1_total_expected:.2f}")
    
    print(f"\n📈 改善效果:")
    macd_improvement = v2_macd - v1_macd_expected
    rsi_improvement = v2_rsi - v1_rsi_expected
    total_improvement = v2_total - v1_total_expected
    
    print(f"   MACD评分提升: +{macd_improvement:.2f}")
    print(f"   RSI评分提升: +{rsi_improvement:.2f}")
    print(f"   总评分提升: +{total_improvement:.2f}")
    
    # 验证改善效果
    if macd_improvement >= 12 and rsi_improvement >= 5 and total_improvement >= 3:
        print("✅ V2优化显著改善了评分逻辑")
        return True
    else:
        print("❌ V2优化效果不够显著")
        return False

def main():
    """主测试函数"""
    print("🚀 融合评分器V2优化测试")
    print("根据 doc/test_fix_5.md 的优化建议进行验证")
    print("=" * 60)
    
    test_results = []
    
    # 执行各项测试
    test_results.append(test_macd_v2_optimization())
    test_results.append(test_rsi_v2_optimization())
    test_results.append(test_overall_score_improvement())
    test_results.append(test_comparison_with_old_logic())
    
    # 总结
    print("\n" + "=" * 60)
    print("📋 测试总结:")
    passed_tests = sum(test_results)
    total_tests = len(test_results)
    
    print(f"   通过测试: {passed_tests}/{total_tests}")
    
    if passed_tests == total_tests:
        print("🎉 所有V2优化测试通过！")
        print("\n💡 验证命令:")
        print("   # 验证sh600702在2025-08-14的表现")
        print("   python backend/validation_suite.py --stock-code sh600702 --strategy 深渊筑底策略_v2.0 --date 2025-08-14")
        print("   # 预期结果：MACD评分15-25分，RSI评分5-8分，总分超过70分")
    else:
        print("⚠️ 部分测试失败，需要进一步调试")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    main()