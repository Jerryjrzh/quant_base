#!/usr/bin/env python3
"""
测试周线功能
验证多周期系统中周线数据的获取、处理和分析功能
"""

import sys
import os
sys.path.append('backend')

from multi_timeframe_data_manager import MultiTimeframeDataManager
from multi_timeframe_signal_generator import MultiTimeframeSignalGenerator
from multi_timeframe_visualizer import MultiTimeframeVisualizer
from multi_timeframe_config import MultiTimeframeConfig
import json
from datetime import datetime

def test_weekly_data_manager():
    """测试周线数据管理器"""
    print("🔍 测试周线数据管理器")
    print("=" * 50)
    
    manager = MultiTimeframeDataManager()
    
    # 测试股票
    test_stock = 'sz300290'
    
    # 包含周线的时间周期列表
    timeframes = ['5min', '15min', '30min', '1hour', '4hour', '1day', '1week']
    
    print(f"📊 测试股票: {test_stock}")
    print(f"📈 测试周期: {timeframes}")
    
    # 获取多周期数据
    sync_data = manager.get_synchronized_data(test_stock, timeframes)
    
    if 'error' in sync_data:
        print(f"❌ 数据获取失败: {sync_data['error']}")
        return False
    
    print(f"\n✅ 成功获取 {len(sync_data['timeframes'])} 个时间周期的数据")
    
    # 检查周线数据
    for timeframe in timeframes:
        if timeframe in sync_data['timeframes']:
            df = sync_data['timeframes'][timeframe]
            quality = sync_data['data_quality'][timeframe]
            print(f"  {timeframe:>6}: {len(df):>4} 条数据, 质量评分: {quality['quality_score']:.3f}")
            
            # 特别检查周线数据
            if timeframe == '1week' and not df.empty:
                print(f"    📅 周线数据时间范围: {df.index[0]} 到 {df.index[-1]}")
                print(f"    💰 最新收盘价: {df['close'].iloc[-1]:.2f}")
                print(f"    📊 最新成交量: {df['volume'].iloc[-1]:,.0f}")
        else:
            print(f"  {timeframe:>6}: ❌ 无数据")
    
    # 测试跨周期分析
    if 'alignment_info' in sync_data:
        alignment = sync_data['alignment_info']
        print(f"\n🔗 时间轴对齐信息:")
        if alignment.get('common_start_time'):
            print(f"  共同开始时间: {alignment['common_start_time']}")
            print(f"  共同结束时间: {alignment['common_end_time']}")
    
    return True

def test_weekly_indicators():
    """测试周线技术指标计算"""
    print("\n🔍 测试周线技术指标计算")
    print("=" * 50)
    
    manager = MultiTimeframeDataManager()
    test_stock = 'sz300290'
    
    # 计算包含周线的多周期指标
    timeframes = ['1day', '1week']
    indicators_result = manager.calculate_multi_timeframe_indicators(test_stock, timeframes)
    
    if 'error' in indicators_result:
        print(f"❌ 指标计算失败: {indicators_result['error']}")
        return False
    
    print(f"✅ 成功计算 {len(indicators_result['timeframes'])} 个时间周期的指标")
    
    # 检查周线指标
    if '1week' in indicators_result['timeframes']:
        weekly_indicators = indicators_result['timeframes']['1week']
        print(f"\n📊 周线技术指标:")
        print(f"  数据点数: {weekly_indicators['data_points']}")
        
        # 显示主要指标的最新值
        indicators_dict = weekly_indicators.get('indicators', {})
        
        if 'ma' in indicators_dict:
            ma_data = indicators_dict['ma']
            if ma_data.get('ma_20'):
                print(f"  MA20: {ma_data['ma_20'][-1]:.2f}")
        
        if 'rsi' in indicators_dict:
            rsi_data = indicators_dict['rsi']
            if rsi_data.get('rsi_14'):
                print(f"  RSI14: {rsi_data['rsi_14'][-1]:.2f}")
        
        if 'macd' in indicators_dict:
            macd_data = indicators_dict['macd']
            if macd_data.get('dif') and macd_data.get('dea'):
                print(f"  MACD DIF: {macd_data['dif'][-1]:.4f}")
                print(f"  MACD DEA: {macd_data['dea'][-1]:.4f}")
        
        # 趋势分析
        trend_analysis = weekly_indicators.get('trend_analysis', {})
        if trend_analysis:
            print(f"  价格趋势: {trend_analysis.get('price_trend', 'unknown')}")
            print(f"  成交量趋势: {trend_analysis.get('volume_trend', 'unknown')}")
            print(f"  波动率: {trend_analysis.get('volatility', 0):.4f}")
    
    # 跨周期分析
    cross_analysis = indicators_result.get('cross_timeframe_analysis', {})
    if cross_analysis:
        print(f"\n🔗 跨周期分析:")
        recommendation = cross_analysis.get('recommendation', 'neutral')
        print(f"  综合建议: {recommendation}")
        
        trend_alignment = cross_analysis.get('trend_alignment', {})
        if trend_alignment:
            alignment_strength = trend_alignment.get('alignment_strength', 0)
            print(f"  趋势一致性: {alignment_strength:.3f}")
    
    return True

def test_weekly_signals():
    """测试周线信号生成"""
    print("\n🔍 测试周线信号生成")
    print("=" * 50)
    
    data_manager = MultiTimeframeDataManager()
    signal_generator = MultiTimeframeSignalGenerator(data_manager)
    
    test_stock = 'sz300290'
    
    # 生成包含周线的复合信号
    signal_result = signal_generator.generate_composite_signals(test_stock)
    
    if 'error' in signal_result:
        print(f"❌ 信号生成失败: {signal_result['error']}")
        return False
    
    print(f"✅ 成功生成复合信号")
    
    # 检查各周期信号
    timeframe_signals = signal_result.get('timeframe_signals', {})
    print(f"\n📈 各周期信号强度:")
    
    for timeframe, signals in timeframe_signals.items():
        composite_score = signals.get('composite_score', 0)
        signal_strength = signals.get('signal_strength', 'neutral')
        print(f"  {timeframe:>6}: {composite_score:>7.3f} ({signal_strength})")
    
    # 检查周线特定信号
    if '1week' in timeframe_signals:
        weekly_signals = timeframe_signals['1week']
        print(f"\n📊 周线详细信号:")
        print(f"  趋势信号: {weekly_signals.get('trend_signal', 0):.3f}")
        print(f"  动量信号: {weekly_signals.get('momentum_signal', 0):.3f}")
        print(f"  反转信号: {weekly_signals.get('reversal_signal', 0):.3f}")
        print(f"  突破信号: {weekly_signals.get('breakout_signal', 0):.3f}")
    
    # 复合信号
    composite_signal = signal_result.get('composite_signal', {})
    if composite_signal:
        print(f"\n🎯 复合信号:")
        print(f"  最终评分: {composite_signal.get('final_score', 0):.3f}")
        print(f"  信号强度: {composite_signal.get('signal_strength', 'neutral')}")
        print(f"  置信度: {composite_signal.get('confidence_level', 0):.3f}")
    
    return True

def test_weekly_config():
    """测试周线配置"""
    print("\n🔍 测试周线配置")
    print("=" * 50)
    
    config = MultiTimeframeConfig()
    
    # 检查周线配置
    weekly_config = config.get('timeframes.1week')
    if weekly_config:
        print(f"✅ 周线配置存在:")
        print(f"  启用状态: {weekly_config.get('enabled', False)}")
        print(f"  权重: {weekly_config.get('weight', 0):.3f}")
        print(f"  最小数据点: {weekly_config.get('min_data_points', 0)}")
        print(f"  颜色: {weekly_config.get('color', 'N/A')}")
        print(f"  标签: {weekly_config.get('label', 'N/A')}")
    else:
        print(f"❌ 周线配置不存在")
        return False
    
    # 检查权重分布
    print(f"\n⚖️ 时间周期权重分布:")
    timeframes = config.config['timeframes']
    total_weight = 0
    
    for timeframe, tf_config in timeframes.items():
        weight = tf_config.get('weight', 0)
        total_weight += weight
        print(f"  {timeframe:>6}: {weight:.3f}")
    
    print(f"  总权重: {total_weight:.3f}")
    
    if abs(total_weight - 1.0) > 0.01:
        print(f"⚠️  权重总和不等于1.0，可能需要调整")
    
    return True

def test_weekly_visualization():
    """测试周线可视化"""
    print("\n🔍 测试周线可视化")
    print("=" * 50)
    
    try:
        visualizer = MultiTimeframeVisualizer()
        
        # 检查周线配置
        if '1week' in visualizer.timeframe_config:
            weekly_viz_config = visualizer.timeframe_config['1week']
            print(f"✅ 周线可视化配置:")
            print(f"  标签: {weekly_viz_config['label']}")
            print(f"  颜色: {weekly_viz_config['color']}")
            print(f"  权重: {weekly_viz_config['weight']:.3f}")
        else:
            print(f"❌ 周线可视化配置缺失")
            return False
        
        print(f"✅ 可视化器支持周线显示")
        return True
        
    except Exception as e:
        print(f"❌ 可视化测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🧪 周线功能完整性测试")
    print("=" * 60)
    
    test_results = []
    
    # 执行各项测试
    tests = [
        ("周线数据管理器", test_weekly_data_manager),
        ("周线技术指标", test_weekly_indicators),
        ("周线信号生成", test_weekly_signals),
        ("周线配置管理", test_weekly_config),
        ("周线可视化", test_weekly_visualization)
    ]
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*20} {test_name} {'='*20}")
            result = test_func()
            test_results.append((test_name, result))
            
            if result:
                print(f"✅ {test_name} 测试通过")
            else:
                print(f"❌ {test_name} 测试失败")
                
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
            test_results.append((test_name, False))
    
    # 测试结果汇总
    print(f"\n{'='*60}")
    print("📋 测试结果汇总")
    print("=" * 60)
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {test_name:<20}: {status}")
        if result:
            passed += 1
    
    print(f"\n📊 总体结果: {passed}/{total} 项测试通过")
    
    if passed == total:
        print("🎉 所有周线功能测试通过！周线已成功集成到多周期系统中。")
    else:
        print("⚠️  部分测试失败，请检查相关功能。")
    
    # 保存测试报告
    test_report = {
        'test_time': datetime.now().isoformat(),
        'total_tests': total,
        'passed_tests': passed,
        'test_results': [
            {'test_name': name, 'result': result} 
            for name, result in test_results
        ],
        'success_rate': passed / total if total > 0 else 0
    }
    
    with open('weekly_test_report.json', 'w', encoding='utf-8') as f:
        json.dump(test_report, f, ensure_ascii=False, indent=2)
    
    print(f"\n📄 测试报告已保存到: weekly_test_report.json")

if __name__ == "__main__":
    main()