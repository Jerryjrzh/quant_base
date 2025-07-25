#!/usr/bin/env python3
"""
周线分析演示脚本
展示多周期系统中周线功能的完整使用流程
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

def demo_weekly_analysis():
    """演示周线分析完整流程"""
    print("🚀 多周期系统周线分析演示")
    print("=" * 60)
    
    # 测试股票列表
    test_stocks = ['sz300290', 'sz002691', 'sh600690']
    
    # 初始化组件
    print("🔧 初始化系统组件...")
    data_manager = MultiTimeframeDataManager()
    signal_generator = MultiTimeframeSignalGenerator(data_manager)
    config = MultiTimeframeConfig()
    
    # 显示系统配置
    print("\n📊 系统配置信息:")
    timeframes = config.config['timeframes']
    print(f"支持的时间周期: {list(timeframes.keys())}")
    
    # 显示权重分布
    print("\n⚖️ 时间周期权重分布:")
    total_weight = 0
    for timeframe, tf_config in timeframes.items():
        weight = tf_config.get('weight', 0)
        total_weight += weight
        enabled = "✅" if tf_config.get('enabled', False) else "❌"
        print(f"  {timeframe:>6}: {weight:>6.3f} {enabled}")
    print(f"  总权重: {total_weight:.3f}")
    
    # 分析每只股票
    for i, stock_code in enumerate(test_stocks, 1):
        print(f"\n{'='*20} 股票 {i}: {stock_code} {'='*20}")
        
        try:
            # 1. 获取多周期数据（包含周线）
            print("📈 获取多周期数据...")
            timeframes_list = ['5min', '15min', '30min', '1hour', '4hour', '1day', '1week']
            sync_data = data_manager.get_synchronized_data(stock_code, timeframes_list)
            
            if 'error' in sync_data:
                print(f"❌ 数据获取失败: {sync_data['error']}")
                continue
            
            print(f"✅ 获取到 {len(sync_data['timeframes'])} 个时间周期的数据")
            
            # 显示各周期数据概况
            for timeframe in timeframes_list:
                if timeframe in sync_data['timeframes']:
                    df = sync_data['timeframes'][timeframe]
                    quality = sync_data['data_quality'][timeframe]
                    print(f"  {timeframe:>6}: {len(df):>4} 条数据, 质量: {quality['quality_score']:.3f}")
                    
                    # 特别显示周线信息
                    if timeframe == '1week' and not df.empty:
                        latest_price = df['close'].iloc[-1]
                        price_change = (df['close'].iloc[-1] / df['close'].iloc[-2] - 1) * 100 if len(df) > 1 else 0
                        volume = df['volume'].iloc[-1]
                        print(f"    📊 周线最新: 价格 {latest_price:.2f} ({price_change:+.2f}%), 成交量 {volume:,.0f}")
            
            # 2. 计算多周期技术指标
            print("\n🔍 计算多周期技术指标...")
            indicators_result = data_manager.calculate_multi_timeframe_indicators(stock_code)
            
            if 'error' in indicators_result:
                print(f"❌ 指标计算失败: {indicators_result['error']}")
                continue
            
            # 显示周线技术指标
            if '1week' in indicators_result['timeframes']:
                weekly_indicators = indicators_result['timeframes']['1week']
                print("📊 周线技术指标:")
                
                indicators_dict = weekly_indicators.get('indicators', {})
                
                # MA指标
                if 'ma' in indicators_dict:
                    ma_data = indicators_dict['ma']
                    if ma_data.get('ma_5') and ma_data.get('ma_20'):
                        ma5 = ma_data['ma_5'][-1]
                        ma20 = ma_data['ma_20'][-1]
                        ma_trend = "上升" if ma5 > ma20 else "下降"
                        print(f"  MA5: {ma5:.2f}, MA20: {ma20:.2f} ({ma_trend})")
                
                # RSI指标
                if 'rsi' in indicators_dict:
                    rsi_data = indicators_dict['rsi']
                    if rsi_data.get('rsi_14'):
                        rsi14 = rsi_data['rsi_14'][-1]
                        rsi_status = "超买" if rsi14 > 70 else "超卖" if rsi14 < 30 else "正常"
                        print(f"  RSI14: {rsi14:.2f} ({rsi_status})")
                
                # MACD指标
                if 'macd' in indicators_dict:
                    macd_data = indicators_dict['macd']
                    if macd_data.get('dif') and macd_data.get('dea'):
                        dif = macd_data['dif'][-1]
                        dea = macd_data['dea'][-1]
                        macd_signal = "金叉" if dif > dea else "死叉"
                        print(f"  MACD: DIF {dif:.4f}, DEA {dea:.4f} ({macd_signal})")
                
                # 趋势分析
                trend_analysis = weekly_indicators.get('trend_analysis', {})
                if trend_analysis:
                    price_trend = trend_analysis.get('price_trend', 'unknown')
                    volume_trend = trend_analysis.get('volume_trend', 'unknown')
                    volatility = trend_analysis.get('volatility', 0)
                    print(f"  趋势: 价格{price_trend}, 成交量{volume_trend}, 波动率{volatility:.4f}")
            
            # 3. 生成多周期信号
            print("\n🎯 生成多周期信号...")
            signal_result = signal_generator.generate_composite_signals(stock_code)
            
            if 'error' in signal_result:
                print(f"❌ 信号生成失败: {signal_result['error']}")
                continue
            
            # 显示各周期信号强度
            timeframe_signals = signal_result.get('timeframe_signals', {})
            print("📈 各周期信号强度:")
            
            for timeframe in timeframes_list:
                if timeframe in timeframe_signals:
                    signals = timeframe_signals[timeframe]
                    composite_score = signals.get('composite_score', 0)
                    signal_strength = signals.get('signal_strength', 'neutral')
                    
                    # 为周线添加特殊标记
                    marker = " 🔥" if timeframe == '1week' else ""
                    print(f"  {timeframe:>6}: {composite_score:>7.3f} ({signal_strength}){marker}")
            
            # 特别显示周线信号详情
            if '1week' in timeframe_signals:
                weekly_signals = timeframe_signals['1week']
                print("\n📊 周线信号详细分析:")
                print(f"  趋势信号: {weekly_signals.get('trend_signal', 0):>7.3f}")
                print(f"  动量信号: {weekly_signals.get('momentum_signal', 0):>7.3f}")
                print(f"  反转信号: {weekly_signals.get('reversal_signal', 0):>7.3f}")
                print(f"  突破信号: {weekly_signals.get('breakout_signal', 0):>7.3f}")
                
                supporting_indicators = weekly_signals.get('supporting_indicators', [])
                if supporting_indicators:
                    print(f"  支持指标: {', '.join(supporting_indicators)}")
            
            # 4. 复合信号分析
            composite_signal = signal_result.get('composite_signal', {})
            if composite_signal:
                print("\n🎯 复合信号分析:")
                final_score = composite_signal.get('final_score', 0)
                signal_strength = composite_signal.get('signal_strength', 'neutral')
                confidence_level = composite_signal.get('confidence_level', 0)
                
                print(f"  最终评分: {final_score:>7.3f}")
                print(f"  信号强度: {signal_strength}")
                print(f"  置信度: {confidence_level:>7.3f}")
                
                # 根据信号强度给出建议
                if signal_strength in ['strong_buy', 'buy']:
                    recommendation = "🟢 建议关注买入机会"
                elif signal_strength in ['strong_sell', 'sell']:
                    recommendation = "🔴 建议关注卖出机会"
                else:
                    recommendation = "🟡 建议继续观望"
                
                print(f"  投资建议: {recommendation}")
            
            # 5. 跨周期分析
            cross_analysis = indicators_result.get('cross_timeframe_analysis', {})
            if cross_analysis:
                print("\n🔗 跨周期分析:")
                
                trend_alignment = cross_analysis.get('trend_alignment', {})
                if trend_alignment:
                    alignment_strength = trend_alignment.get('alignment_strength', 0)
                    uptrend_ratio = trend_alignment.get('uptrend_ratio', 0)
                    downtrend_ratio = trend_alignment.get('downtrend_ratio', 0)
                    
                    print(f"  趋势一致性: {alignment_strength:.3f}")
                    print(f"  上升趋势比例: {uptrend_ratio:.3f}")
                    print(f"  下降趋势比例: {downtrend_ratio:.3f}")
                
                signal_convergence = cross_analysis.get('signal_convergence', {})
                if signal_convergence:
                    convergence_strength = signal_convergence.get('convergence_strength', 0)
                    print(f"  信号收敛强度: {convergence_strength:.3f}")
                
                recommendation = cross_analysis.get('recommendation', 'neutral')
                print(f"  跨周期建议: {recommendation}")
            
            print(f"✅ {stock_code} 分析完成")
            
        except Exception as e:
            print(f"❌ {stock_code} 分析失败: {e}")
            continue
    
    # 总结
    print(f"\n{'='*60}")
    print("📋 周线分析演示总结")
    print("=" * 60)
    print("✅ 周线数据获取: 支持从日线数据重采样生成周线数据")
    print("✅ 周线技术指标: 支持MA、RSI、MACD、KDJ、布林带等指标计算")
    print("✅ 周线信号生成: 支持趋势、动量、反转、突破等信号类型")
    print("✅ 跨周期分析: 周线作为长期趋势参考，权重最高(40%)")
    print("✅ 信号融合: 周线信号与其他周期信号有效融合")
    
    print("\n🎯 周线分析的优势:")
    print("• 长期趋势识别: 周线能更好地识别主要趋势方向")
    print("• 噪音过滤: 周线数据过滤了短期市场噪音")
    print("• 支撑阻力: 周线级别的支撑阻力更加可靠")
    print("• 趋势确认: 为短期信号提供长期趋势确认")
    
    print("\n📈 使用建议:")
    print("• 周线信号适合中长期投资决策")
    print("• 结合日线和小时线信号确定具体入场时机")
    print("• 周线趋势变化通常预示着重要的市场转折")
    print("• 建议定期关注周线技术指标的变化")

def main():
    """主函数"""
    try:
        demo_weekly_analysis()
    except KeyboardInterrupt:
        print("\n\n⏹️  演示被用户中断")
    except Exception as e:
        print(f"\n❌ 演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()