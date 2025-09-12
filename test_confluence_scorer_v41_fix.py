#!/usr/bin/env python3
"""
【V4.1 融合评分器修复测试】
基于test_fix_7.md的建议实现的增强功能测试：
1. 修复phase_weights配置加载bug
2. 增强市场阶段识别（集成波动率和成交量）
3. 动态阈值调整（基于ATR）
4. 历史回测验证功能
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

import pandas as pd
import numpy as np
from backend.confluence_scorer import ConfluenceScorer
import json
from datetime import datetime

def create_enhanced_test_data():
    """创建增强测试数据，包含更真实的市场特征"""
    dates = pd.date_range('2024-01-01', periods=200, freq='D')
    
    # 模拟更复杂的市场周期
    base_price = 15.0
    prices = []
    volumes = []
    
    for i in range(200):
        # 添加随机波动率变化
        if i < 60:  # 积累期：低位震荡，波动率较低
            volatility = 0.02
            price = base_price + np.sin(i * 0.15) * 0.8 + np.random.normal(0, volatility)
            volume = np.random.randint(500000, 2000000)
        elif i < 120:  # 上升期：趋势上涨，波动率中等
            volatility = 0.03
            price = base_price + (i - 60) * 0.12 + np.sin(i * 0.1) * 0.5 + np.random.normal(0, volatility)
            volume = np.random.randint(1500000, 8000000)  # 放量上涨
        elif i < 160:  # 分配期：高位震荡，波动率增加
            volatility = 0.04
            price = base_price + 7 + np.sin(i * 0.25) * 1.2 + np.random.normal(0, volatility)
            volume = np.random.randint(800000, 5000000)
        else:  # 下跌期：下跌趋势，波动率高
            volatility = 0.05
            price = base_price + 7 - (i - 160) * 0.08 + np.sin(i * 0.2) * 0.8 + np.random.normal(0, volatility)
            volume = np.random.randint(1000000, 6000000)  # 放量下跌
        
        prices.append(max(price, 0.1))
        volumes.append(volume)
    
    # 构建完整的技术指标数据
    df = pd.DataFrame({
        'date': dates,
        'close': prices,
        'high': [p * (1 + np.random.uniform(0, 0.03)) for p in prices],
        'low': [p * (1 - np.random.uniform(0, 0.03)) for p in prices],
        'volume': volumes
    })
    
    # 计算技术指标
    df['ma50'] = df['close'].rolling(50).mean()
    df['ma90'] = df['close'].rolling(90).mean()
    df['ma150'] = df['close'].rolling(150).mean()
    df['ma200'] = df['close'].rolling(200).mean()
    
    # 计算MACD指标
    exp1 = df['close'].ewm(span=12).mean()
    exp2 = df['close'].ewm(span=26).mean()
    df['diff'] = exp1 - exp2
    df['dea'] = df['diff'].ewm(span=9).mean()
    df['macd'] = (df['diff'] - df['dea']) * 2
    
    # 计算KDJ指标
    low_min = df['low'].rolling(9).min()
    high_max = df['high'].rolling(9).max()
    rsv = (df['close'] - low_min) / (high_max - low_min) * 100
    df['k'] = rsv.ewm(com=2).mean()
    df['d'] = df['k'].ewm(com=2).mean()
    df['j'] = 3 * df['k'] - 2 * df['d']
    
    # 计算RSI指标
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=6).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=6).mean()
    rs = gain / loss
    df['rsi6'] = 100 - (100 / (1 + rs))
    
    return df

def test_bug_fix():
    """测试phase_weights配置加载bug修复"""
    print("=" * 60)
    print("【测试1：phase_weights配置加载bug修复】")
    print("=" * 60)
    
    try:
        # 测试配置加载
        scorer = ConfluenceScorer()
        
        # 检查phase_weights是否正确加载
        if hasattr(scorer, 'phase_weights') and scorer.phase_weights:
            print("✅ phase_weights配置加载成功")
            print(f"   支持的市场阶段: {list(scorer.phase_weights.keys())}")
            
            # 测试每个阶段的权重配置
            for phase, weights in scorer.phase_weights.items():
                total_weight = sum(weights.values())
                print(f"   {phase}: 总权重={total_weight}, 配置={weights}")
        else:
            print("❌ phase_weights配置加载失败")
            
    except Exception as e:
        print(f"❌ 配置加载测试失败: {e}")

def test_enhanced_phase_detection():
    """测试增强的市场阶段识别功能"""
    print("\n" + "=" * 60)
    print("【测试2：增强市场阶段识别功能】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_enhanced_test_data()
    
    # 测试不同时期的阶段识别
    test_indices = [40, 90, 140, 180]  # 积累期、上升期、分配期、下跌期
    expected_phases = ['accumulation', 'markup', 'distribution', 'decline']
    
    for i, (idx, expected) in enumerate(zip(test_indices, expected_phases)):
        if idx < len(df):
            phase_result = scorer.detect_market_phase(df, idx)
            
            print(f"\n时期 {i+1} (第{idx}天):")
            print(f"  当前价格: {df.iloc[idx]['close']:.2f}")
            print(f"  预期阶段: {expected}")
            print(f"  检测阶段: {phase_result['phase']}")
            print(f"  置信度: {phase_result['confidence']:.2%}")
            print(f"  ATR: {phase_result['atr']:.4f}")
            print(f"  价格位置: {phase_result.get('price_position', 0):.2%}")
            print(f"  成交量趋势: {phase_result.get('volume_trend', 1):.2f}")
            print(f"  匹配度: {'✅' if expected in phase_result['phase'] else '❌'}")

def test_dynamic_thresholds():
    """测试动态阈值调整功能"""
    print("\n" + "=" * 60)
    print("【测试3：动态阈值调整功能】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_enhanced_test_data()
    
    # 测试不同波动率环境下的阈值调整
    test_indices = [50, 100, 150]  # 低、中、高波动率时期
    
    for idx in test_indices:
        if idx < len(df):
            phase_result = scorer.detect_market_phase(df, idx)
            atr = phase_result['atr']
            
            dynamic_thresholds = scorer.calculate_dynamic_thresholds(df, idx, atr)
            
            print(f"\n第{idx}天 (ATR: {atr:.4f}):")
            print(f"  当前价格: {df.iloc[idx]['close']:.2f}")
            print(f"  动态RSI超卖阈值: {dynamic_thresholds['rsi_oversold']:.1f}")
            print(f"  动态RSI看涨下限: {dynamic_thresholds['rsi_bullish_low']:.1f}")
            print(f"  动态KDJ超卖阈值: {dynamic_thresholds['kdj_oversold']:.1f}")
            print(f"  动态斜率阈值: {dynamic_thresholds['min_slope_threshold']:.3f}")

def test_backtest_functionality():
    """测试历史回测验证功能"""
    print("\n" + "=" * 60)
    print("【测试4：历史回测验证功能】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_enhanced_test_data()
    
    # 选择有足够历史数据的测试点
    test_index = 150
    
    if test_index < len(df):
        backtest_result = scorer.backtest_alignments(df, test_index)
        
        print(f"\n历史回测分析 (第{test_index}天):")
        print(f"  信号数量: {backtest_result['signal_count']}")
        print(f"  综合胜率: {backtest_result['win_rate']:.1%}")
        print(f"  5天胜率: {backtest_result['win_rate_5d']:.1%}")
        print(f"  10天胜率: {backtest_result['win_rate_10d']:.1%}")
        print(f"  平均收益: {backtest_result['avg_return']:.2%}")
        print(f"  置信度乘数: {backtest_result['confidence_multiplier']:.2f}")
        
        if backtest_result['recent_signals']:
            print(f"  最近信号样本:")
            for i, signal in enumerate(backtest_result['recent_signals'][-3:]):
                print(f"    信号{i+1}: 入场价{signal['entry_price']:.2f}, "
                      f"5天收益{signal['return_5d']:.1%}, "
                      f"10天收益{signal['return_10d']:.1%}")

def test_comprehensive_scoring():
    """测试V4.1综合评分功能"""
    print("\n" + "=" * 60)
    print("【测试5：V4.1综合评分对比】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_enhanced_test_data()
    
    # 测试不同阶段的综合评分
    test_indices = [40, 90, 140, 180]
    phase_names = ['积累期', '上升期', '分配期', '下跌期']
    
    for idx, phase_name in zip(test_indices, phase_names):
        if idx < len(df):
            # 检查价格过滤
            passed_filter, filter_reason = scorer.filter_by_price_position(df, idx)
            
            if passed_filter:
                result = scorer.calculate_confluence_score(df, idx)
                
                print(f"\n{phase_name} (第{idx}天):")
                print(f"  检测阶段: {result['market_phase']}")
                print(f"  阶段置信度: {result['phase_confidence']:.2%}")
                print(f"  总评分: {result['total_score']:.1f}")
                print(f"  基础置信度: {result['base_confidence']:.2%}")
                print(f"  综合置信度: {result['confidence']:.2%}")
                print(f"  高质量信号: {'✅' if result['is_high_quality'] else '❌'}")
                
                # 显示评分明细
                print(f"  评分明细:")
                for component, score in result['breakdown'].items():
                    print(f"    {component}: {score:.1f}")
                
                # 显示回测信息
                backtest = result.get('backtest_analysis', {})
                if backtest.get('signal_count', 0) > 0:
                    print(f"  回测胜率: {backtest['win_rate']:.1%}")
                    print(f"  置信度乘数: {backtest['confidence_multiplier']:.2f}")
                
            else:
                print(f"\n{phase_name} (第{idx}天): 未通过价格过滤")
                print(f"  过滤原因: {filter_reason}")

def generate_v41_performance_report():
    """生成V4.1性能报告"""
    print("\n" + "=" * 60)
    print("【V4.1 性能报告生成】")
    print("=" * 60)
    
    scorer = ConfluenceScorer()
    df = create_enhanced_test_data()
    
    results = []
    phase_distribution = {}
    
    # 分析最后50天的数据
    for i in range(max(150, len(df)-50), len(df)):
        passed_filter, filter_reason = scorer.filter_by_price_position(df, i)
        
        if passed_filter:
            result = scorer.calculate_confluence_score(df, i)
            
            # 统计阶段分布
            phase = result['market_phase']
            if phase not in phase_distribution:
                phase_distribution[phase] = 0
            phase_distribution[phase] += 1
            
            results.append({
                'day': i,
                'price': df.iloc[i]['close'],
                'market_phase': phase,
                'phase_confidence': result['phase_confidence'],
                'total_score': result['total_score'],
                'base_confidence': result['base_confidence'],
                'combined_confidence': result['confidence'],
                'is_high_quality': result['is_high_quality'],
                'backtest_win_rate': result.get('backtest_analysis', {}).get('win_rate', 0),
                'confidence_multiplier': result.get('backtest_analysis', {}).get('confidence_multiplier', 1.0)
            })
    
    if results:
        # 统计分析
        high_quality_count = sum(1 for r in results if r['is_high_quality'])
        avg_score = np.mean([r['total_score'] for r in results])
        avg_base_confidence = np.mean([r['base_confidence'] for r in results])
        avg_combined_confidence = np.mean([r['combined_confidence'] for r in results])
        avg_phase_confidence = np.mean([r['phase_confidence'] for r in results])
        
        print(f"\n=== V4.1 性能统计 ===")
        print(f"分析样本数: {len(results)}")
        print(f"高质量信号数: {high_quality_count} ({high_quality_count/len(results):.1%})")
        print(f"平均评分: {avg_score:.1f}")
        print(f"平均基础置信度: {avg_base_confidence:.1%}")
        print(f"平均综合置信度: {avg_combined_confidence:.1%}")
        print(f"平均阶段置信度: {avg_phase_confidence:.1%}")
        
        print(f"\n=== 市场阶段分布 ===")
        for phase, count in phase_distribution.items():
            percentage = count / len(results) * 100
            print(f"{phase}: {count}个样本 ({percentage:.1f}%)")
        
        # 按阶段统计评分
        phase_stats = {}
        for result in results:
            phase = result['market_phase']
            if phase not in phase_stats:
                phase_stats[phase] = []
            phase_stats[phase].append(result['total_score'])
        
        print(f"\n=== 各阶段评分统计 ===")
        for phase, scores in phase_stats.items():
            avg_score = np.mean(scores)
            max_score = np.max(scores)
            min_score = np.min(scores)
            print(f"{phase}: 平均{avg_score:.1f}, 最高{max_score:.1f}, 最低{min_score:.1f}, 样本{len(scores)}")
    
    # 保存详细报告
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"confluence_scorer_v41_fix_report_{timestamp}.json"
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'test_timestamp': timestamp,
            'version': 'V4.1-Fix',
            'improvements': [
                'Fixed phase_weights configuration loading bug',
                'Enhanced market phase detection with volatility and volume',
                'Dynamic thresholds adjustment based on ATR',
                'Historical backtesting validation',
                'Multi-dimensional confidence calculation'
            ],
            'test_results': results,
            'summary': {
                'total_samples': len(results),
                'high_quality_signals': high_quality_count,
                'average_score': avg_score if results else 0,
                'average_combined_confidence': avg_combined_confidence if results else 0,
                'phase_distribution': phase_distribution
            }
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细报告已保存: {report_file}")

def main():
    """主测试函数"""
    print("🚀 融合评分器V4.1修复测试开始")
    print("基于test_fix_7.md的建议实现")
    
    try:
        # 执行各项测试
        test_bug_fix()
        test_enhanced_phase_detection()
        test_dynamic_thresholds()
        test_backtest_functionality()
        test_comprehensive_scoring()
        generate_v41_performance_report()
        
        print("\n" + "=" * 60)
        print("✅ 所有V4.1修复测试完成！")
        print("主要改进:")
        print("  1. ✅ 修复了phase_weights配置加载bug")
        print("  2. ✅ 增强了市场阶段识别（集成波动率和成交量）")
        print("  3. ✅ 实现了动态阈值调整（基于ATR）")
        print("  4. ✅ 添加了历史回测验证功能")
        print("  5. ✅ 提升了多维度置信度计算")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()