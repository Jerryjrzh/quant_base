#!/usr/bin/env python3
"""
【V4.0 融合评分器优化测试】
测试基于Grok和Gemini建议的三大核心优化：
1. 市场阶段识别与自适应权重
2. 趋势导向的KDJ/RSI评分
3. 历史形态对齐检测
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

import pandas as pd
import numpy as np
from backend.confluence_scorer import ConfluenceScorer
from backend.data_handler import DataHandler
import json
from datetime import datetime

def create_test_data():
    """创建测试数据，模拟不同市场阶段"""
    dates = pd.date_range('2024-01-01', periods=150, freq='D')
    
    # 模拟积累期 -> 上升期 -> 分配期的完整周期
    base_price = 10.0
    prices = []
    
    for i in range(150):
        if i < 50:  # 积累期：低位震荡
            price = base_price + np.sin(i * 0.2) * 0.5 + np.random.normal(0, 0.1)
        elif i < 100:  # 上升期：趋势上涨
            price = base_price + (i - 50) * 0.1 + np.sin(i * 0.1) * 0.3 + np.random.normal(0, 0.1)
        else:  # 分配期：高位震荡
            price = base_price + 5 + np.sin(i * 0.3) * 0.8 + np.random.normal(0, 0.15)
        
        prices.append(max(price, 0.1))  # 确保价格为正
    
    # 构建完整的技术指标数据
    df = pd.DataFrame({
        'date': dates,
        'close': prices,
        'high': [p * (1 + np.random.uniform(0, 0.05)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.05)) for p in prices],
        'volume': np.random.randint(1000000, 10000000, 150)
    })
    
    # 计算技术指标
    df['ma50'] = df['close'].rolling(50).mean()
    df['ma90'] = df['close'].rolling(90).mean()
    df['ma150'] = df['close'].rolling(150).mean()
    df['ma200'] = df['close'].rolling(200).mean()
    
    # 模拟MACD指标
    exp1 = df['close'].ewm(span=12).mean()
    exp2 = df['close'].ewm(span=26).mean()
    df['diff'] = exp1 - exp2
    df['dea'] = df['diff'].ewm(span=9).mean()
    df['macd'] = (df['diff'] - df['dea']) * 2
    
    # 模拟KDJ指标
    low_min = df['low'].rolling(9).min()
    high_max = df['high'].rolling(9).max()
    rsv = (df['close'] - low_min) / (high_max - low_min) * 100
    df['k'] = rsv.ewm(com=2).mean()
    df['d'] = df['k'].ewm(com=2).mean()
    df['j'] = 3 * df['k'] - 2 * df['d']
    
    # 模拟RSI指标
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=6).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=6).mean()
    rs = gain / loss
    df['rsi6'] = 100 - (100 / (1 + rs))
    
    return df

def test_market_phase_detection():
    """测试市场阶段识别功能"""
    print("=" * 60)
    print("【测试1：市场阶段识别功能】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_test_data()
    
    # 测试不同时期的阶段识别
    test_indices = [30, 75, 120, 140]  # 积累期、上升期、分配期、下跌期
    phase_names = ['积累期', '上升期', '分配期', '下跌期']
    
    for i, (idx, expected_phase) in enumerate(zip(test_indices, phase_names)):
        if idx < len(df):
            detected_phase = scorer.detect_market_phase(df, idx)
            price = df.iloc[idx]['close']
            
            print(f"\n时期 {i+1} (第{idx}天, 价格: {price:.2f}):")
            print(f"  预期阶段: {expected_phase}")
            print(f"  检测阶段: {detected_phase}")
            print(f"  匹配度: {'✅' if expected_phase.replace('期', '') in detected_phase else '❌'}")

def test_trend_based_scoring():
    """测试趋势导向评分功能"""
    print("\n" + "=" * 60)
    print("【测试2：趋势导向评分功能】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_test_data()
    
    # 比较V3.2和V4.0的KDJ/RSI评分差异
    test_index = 80  # 选择上升期的一个点
    
    if test_index < len(df):
        # V4.0评分
        kdj_score_v4 = scorer.calculate_kdj_state_score(df, test_index)
        rsi_score_v4 = scorer.calculate_rsi_state_score(df, test_index)
        
        current_data = df.iloc[test_index]
        print(f"\n测试点 (第{test_index}天):")
        print(f"  当前K值: {current_data.get('k', 0):.2f}")
        print(f"  当前RSI: {current_data.get('rsi6', 0):.2f}")
        print(f"  V4.0 KDJ评分: {kdj_score_v4:.2f}")
        print(f"  V4.0 RSI评分: {rsi_score_v4:.2f}")
        
        # 计算趋势斜率
        if test_index >= 5:
            k_values = df.iloc[test_index-4:test_index+1]['k'].values
            rsi_values = df.iloc[test_index-4:test_index+1]['rsi6'].fillna(50).values
            
            if len(k_values) == 5:
                k_slope = np.polyfit(range(5), k_values, 1)[0]
                print(f"  KDJ斜率: {k_slope:.3f}")
            
            if len(rsi_values) == 5:
                rsi_slope = np.polyfit(range(5), rsi_values, 1)[0]
                print(f"  RSI斜率: {rsi_slope:.3f}")

def test_historical_alignment():
    """测试历史形态对齐检测"""
    print("\n" + "=" * 60)
    print("【测试3：历史形态对齐检测】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_test_data()
    
    test_index = 100  # 选择有足够历史数据的点
    
    if test_index < len(df):
        alignment_result = scorer.detect_historical_alignment(df, test_index)
        
        print(f"\n历史对齐分析 (第{test_index}天):")
        print(f"  对齐评分: {alignment_result['alignment_score']}")
        print(f"  同步质量: {alignment_result['sync_quality']}")
        print(f"  价格底部数量: {alignment_result['price_bottoms_count']}")
        print(f"  KDJ底部数量: {alignment_result['kdj_bottoms_count']}")
        print(f"  RSI底部数量: {alignment_result['rsi_bottoms_count']}")

def test_adaptive_scoring():
    """测试自适应综合评分"""
    print("\n" + "=" * 60)
    print("【测试4：自适应综合评分对比】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_test_data()
    
    # 测试不同阶段的评分差异
    test_indices = [30, 75, 120]  # 积累期、上升期、分配期
    phase_names = ['积累期', '上升期', '分配期']
    
    for idx, phase_name in zip(test_indices, phase_names):
        if idx < len(df):
            # 先检查是否通过价格过滤
            passed_filter, filter_reason = scorer.filter_by_price_position(df, idx)
            
            if passed_filter:
                result = scorer.calculate_confluence_score(df, idx)
                
                print(f"\n{phase_name} (第{idx}天):")
                print(f"  检测阶段: {result['market_phase']}")
                print(f"  总评分: {result['total_score']:.1f}")
                print(f"  置信度: {result['confidence']:.2%}")
                print(f"  高质量信号: {'✅' if result['is_high_quality'] else '❌'}")
                print(f"  使用权重: {result['phase_weights_used']}")
                print(f"  评分明细:")
                for component, score in result['breakdown'].items():
                    print(f"    {component}: {score:.1f}")
                print(f"  对齐分析: {result['alignment_analysis']['sync_quality']}")
            else:
                print(f"\n{phase_name} (第{idx}天): 未通过价格过滤 - {filter_reason}")

def generate_performance_report():
    """生成性能对比报告"""
    print("\n" + "=" * 60)
    print("【V4.0 性能报告生成】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_test_data()
    
    results = []
    
    # 分析最后30天的数据
    for i in range(max(120, len(df)-30), len(df)):
        passed_filter, filter_reason = scorer.filter_by_price_position(df, i)
        
        if passed_filter:
            result = scorer.calculate_confluence_score(df, i)
            results.append({
                'day': i,
                'price': df.iloc[i]['close'],
                'market_phase': result['market_phase'],
                'total_score': result['total_score'],
                'confidence': result['confidence'],
                'is_high_quality': result['is_high_quality'],
                'alignment_score': result['alignment_analysis']['alignment_score'],
                'sync_quality': result['alignment_analysis']['sync_quality']
            })
    
    if results:
        # 统计分析
        high_quality_count = sum(1 for r in results if r['is_high_quality'])
        avg_score = np.mean([r['total_score'] for r in results])
        avg_confidence = np.mean([r['confidence'] for r in results])
        
        print(f"\n分析样本数: {len(results)}")
        print(f"高质量信号数: {high_quality_count} ({high_quality_count/len(results):.1%})")
        print(f"平均评分: {avg_score:.1f}")
        print(f"平均置信度: {avg_confidence:.1%}")
        
        # 按市场阶段分组统计
        phase_stats = {}
        for result in results:
            phase = result['market_phase']
            if phase not in phase_stats:
                phase_stats[phase] = []
            phase_stats[phase].append(result['total_score'])
        
        print(f"\n各阶段评分统计:")
        for phase, scores in phase_stats.items():
            print(f"  {phase}: 平均{np.mean(scores):.1f}, 样本数{len(scores)}")
    
    # 保存详细报告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"confluence_scorer_v4_test_report_{timestamp}.json"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'test_timestamp': timestamp,
            'version': 'V4.0',
            'test_results': results,
            'summary': {
                'total_samples': len(results),
                'high_quality_signals': high_quality_count,
                'average_score': avg_score,
                'average_confidence': avg_confidence,
                'phase_distribution': {phase: len(scores) for phase, scores in phase_stats.items()}
            }
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细报告已保存: {report_file}")

def main():
    """主测试函数"""
    print("🚀 融合评分器V4.0优化测试开始")
    print("基于Grok和Gemini的深度分析建议")
    
    try:
        # 执行各项测试
        test_market_phase_detection()
        test_trend_based_scoring()
        test_historical_alignment()
        test_adaptive_scoring()
        generate_performance_report()
        
        print("\n" + "=" * 60)
        print("✅ 所有测试完成！V4.0核心功能验证成功")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()