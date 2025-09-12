"""
MA13短线交易策略演示

演示如何使用MA13强势回调短线交易策略系统
包含策略分析、执行计划生成和结果展示
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# 修复导入路径
try:
    from backend.strategies.ma13_short_term_strategy import MA13ShortTermStrategy
    from backend.short_term_execution_planner import ShortTermExecutionPlanner
    from backend.data_handler import DataHandler
    from backend.indicators import TechnicalIndicators
except ImportError:
    # 如果上面的导入失败，尝试直接导入
    sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
    from strategies.ma13_short_term_strategy import MA13ShortTermStrategy
    from short_term_execution_planner import ShortTermExecutionPlanner
    from data_handler import DataHandler
    from indicators import TechnicalIndicators

def create_sample_data():
    """创建符合MA13策略的示例数据"""
    print("📊 创建示例股票数据...")
    
    # 生成150天的数据
    dates = pd.date_range(start='2025-03-01', end='2025-09-12', freq='D')
    dates = [d for d in dates if d.weekday() < 5]  # 只保留工作日
    
    np.random.seed(42)  # 固定随机种子
    
    # 第一阶段：底部箱体震荡 (前90天)
    base_price = 2.20
    box_data = []
    
    for i in range(90):
        # 箱体震荡，波动范围2.15-2.40
        noise = np.random.normal(0, 0.02)
        price = base_price + 0.10 * np.sin(i * 0.1) + noise
        price = max(2.15, min(2.40, price))  # 限制在箱体内
        
        open_price = price * (1 + np.random.normal(0, 0.01))
        high_price = price * (1 + abs(np.random.normal(0, 0.015)))
        low_price = price * (1 - abs(np.random.normal(0, 0.015)))
        volume = np.random.normal(1.5e8, 0.3e8)  # 基础成交量
        
        box_data.append({
            'date': dates[i].strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(price, 2),
            'volume': int(max(volume, 0.5e8))
        })
    
    # 第二阶段：突破上涨 (90-110天)
    breakout_data = []
    start_price = 2.40
    
    for i in range(20):
        # 放量突破，涨幅约30%
        progress = i / 19
        price = start_price * (1 + 0.30 * progress)  # 涨到3.12
        
        # 添加一些波动
        noise = np.random.normal(0, 0.01)
        price = price * (1 + noise)
        
        open_price = price * (1 + np.random.normal(0, 0.008))
        high_price = price * (1 + abs(np.random.normal(0, 0.012)))
        low_price = price * (1 - abs(np.random.normal(0, 0.012)))
        
        # 突破期间成交量放大
        volume = np.random.normal(2.5e8, 0.5e8)
        
        breakout_data.append({
            'date': dates[90 + i].strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(price, 2),
            'volume': int(max(volume, 1.0e8))
        })
    
    # 第三阶段：回调至MA13 (110-125天)
    pullback_data = []
    high_price = 3.09
    
    for i in range(15):
        # 回调到MA13附近
        progress = i / 14
        price = high_price * (1 - 0.10 * progress)  # 回调10%到2.78
        
        noise = np.random.normal(0, 0.008)
        price = price * (1 + noise)
        
        open_price = price * (1 + np.random.normal(0, 0.006))
        high_price_day = price * (1 + abs(np.random.normal(0, 0.010)))
        low_price_day = price * (1 - abs(np.random.normal(0, 0.010)))
        
        # 回调期间成交量缩小
        volume = np.random.normal(1.8e8, 0.4e8)
        
        pullback_data.append({
            'date': dates[110 + i].strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high_price_day, 2),
            'low': round(low_price_day, 2),
            'close': round(price, 2),
            'volume': int(max(volume, 0.8e8))
        })
    
    # 第四阶段：当前反弹确认 (125-150天)
    current_data = []
    start_price = 2.78
    
    for i in range(25):
        # 从MA13支撑反弹
        if i < 5:
            # 前5天在支撑位震荡
            price = start_price * (1 + np.random.normal(0, 0.01))
        else:
            # 后续开始反弹
            progress = (i - 5) / 19
            price = start_price * (1 + 0.08 * progress)  # 反弹8%
        
        noise = np.random.normal(0, 0.008)
        price = price * (1 + noise)
        
        open_price = price * (1 + np.random.normal(0, 0.006))
        high_price_day = price * (1 + abs(np.random.normal(0, 0.012)))
        low_price_day = price * (1 - abs(np.random.normal(0, 0.008)))
        
        # 反弹期间成交量逐步放大
        base_vol = 1.5e8 + (i / 24) * 1.0e8
        volume = np.random.normal(base_vol, 0.3e8)
        
        current_data.append({
            'date': dates[125 + i].strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high_price_day, 2),
            'low': round(low_price_day, 2),
            'close': round(price, 2),
            'volume': int(max(volume, 0.8e8))
        })
    
    # 合并所有数据
    all_data = box_data + breakout_data + pullback_data + current_data
    df = pd.DataFrame(all_data)
    
    print(f"✅ 生成了{len(df)}天的股票数据")
    print(f"   箱体期间: {df.iloc[0]['date']} - {df.iloc[89]['date']}")
    print(f"   突破期间: {df.iloc[90]['date']} - {df.iloc[109]['date']}")
    print(f"   回调期间: {df.iloc[110]['date']} - {df.iloc[124]['date']}")
    print(f"   当前阶段: {df.iloc[125]['date']} - {df.iloc[-1]['date']}")
    
    return df

def calculate_technical_indicators(df):
    """计算技术指标"""
    print("📈 计算技术指标...")
    
    indicators = TechnicalIndicators()
    
    # 计算移动平均线
    df['ma7'] = indicators.calculate_ma(df, 7)
    df['ma13'] = indicators.calculate_ma(df, 13)
    df['ma30'] = indicators.calculate_ma(df, 30)
    df['ma60'] = indicators.calculate_ma(df, 60)
    
    # 计算MACD
    df['dif'], df['dea'] = indicators.calculate_macd(df)
    
    # 计算KDJ
    df['k'], df['d'], df['j'] = indicators.calculate_kdj(df)
    
    # 计算RSI
    df['rsi6'] = indicators.calculate_rsi(df, 6)
    df['rsi12'] = indicators.calculate_rsi(df, 12)
    df['rsi24'] = indicators.calculate_rsi(df, 24)
    
    print("✅ 技术指标计算完成")
    return df

def analyze_with_ma13_strategy(df, stock_code="002021"):
    """使用MA13策略分析股票"""
    print(f"\n🔍 使用MA13短线策略分析 {stock_code}...")
    
    strategy = MA13ShortTermStrategy()
    result = strategy.analyze_stock(df, stock_code)
    
    print(f"\n📊 策略分析结果:")
    print(f"   成功: {result['success']}")
    print(f"   消息: {result['message']}")
    
    if result['success']:
        # 显示各阶段结果
        stages = ['stage_1', 'stage_2', 'stage_3']
        stage_names = ['海选-底部稳定', '精选-日线爆发', '择时-MA13回调']
        
        for stage, name in zip(stages, stage_names):
            stage_result = result.get(stage, {})
            print(f"\n   {name}:")
            print(f"     通过: {stage_result.get('qualified', False)}")
            if stage_result.get('qualified'):
                if stage == 'stage_1':
                    print(f"     箱体波动率: {stage_result.get('box_volatility', 0):.2%}")
                    print(f"     箱体区间: {stage_result.get('box_low', 0):.2f} - {stage_result.get('box_high', 0):.2f}")
                elif stage == 'stage_2':
                    print(f"     突破涨幅: {stage_result.get('breakout_gain', 0):.2%}")
                    print(f"     成交量放大: {stage_result.get('volume_ratio', 0):.2f}倍")
                elif stage == 'stage_3':
                    print(f"     回调幅度: {stage_result.get('pullback_pct', 0):.2%}")
                    print(f"     MA13支撑: {stage_result.get('current_ma13', 0):.2f}")
        
        # 显示信号分析
        signals = result.get('signals', {})
        print(f"\n   小时线信号:")
        print(f"     超跌模型: {signals.get('oversold_model', False)}")
        print(f"     中继模型: {signals.get('continuation_model', False)}")
        print(f"     信号强度: {signals.get('signal_strength', 0)}")
        print(f"     入场时机: {signals.get('entry_timing', 'wait')}")
        
        # 显示关键价位
        key_levels = result.get('key_levels', {})
        print(f"\n   关键价位:")
        print(f"     核心支撑: {key_levels.get('support_1_lower', 0):.2f}")
        print(f"     最终止损: {key_levels.get('stop_loss', 0):.2f}")
        print(f"     第一目标: {key_levels.get('target_1', 0):.2f}")
        print(f"     第二目标: {key_levels.get('target_2', 0):.2f}")
        
        # 显示交易建议
        recommendation = result.get('recommendation', {})
        print(f"\n   交易建议:")
        print(f"     操作: {recommendation.get('action', 'wait')}")
        print(f"     建议仓位: {recommendation.get('position_size', 0):.1%}")
        print(f"     信心度: {recommendation.get('confidence', 0)}%")
        print(f"     风险收益比: {recommendation.get('risk_reward_ratio', 0):.2f}")
    
    return result

def generate_execution_plan(df, strategy_result, stock_code="002021"):
    """生成执行计划"""
    print(f"\n📋 生成执行计划...")
    
    planner = ShortTermExecutionPlanner()
    plan_result = planner.generate_execution_plan(df, strategy_result, stock_code)
    
    if not plan_result['success']:
        print(f"❌ 执行计划生成失败: {plan_result['message']}")
        return plan_result
    
    print(f"✅ 执行计划生成成功")
    
    # 显示支撑位分析
    support_analysis = plan_result.get('support_analysis', {})
    print(f"\n🛡️ 支撑位分析:")
    
    core_support = support_analysis.get('core_support_zone', {})
    print(f"   {core_support.get('description', '')}")
    print(f"   {core_support.get('tactical_meaning', '')}")
    
    final_support = support_analysis.get('final_support_zone', {})
    print(f"   {final_support.get('description', '')}")
    print(f"   {final_support.get('tactical_meaning', '')}")
    
    print(f"   当前位置: {support_analysis.get('current_position', '')}")
    print(f"   支撑强度: {support_analysis.get('support_strength', {}).get('strength_level', '')}")
    
    # 显示目标位分析
    target_analysis = plan_result.get('target_analysis', {})
    print(f"\n🎯 目标位分析:")
    
    for target_key in ['target_1', 'target_2', 'target_3']:
        target = target_analysis.get(target_key, {})
        if target:
            print(f"   {target.get('description', '')}")
            print(f"     依据: {target.get('basis', '')}")
            print(f"     操作: {target.get('operation', '')}")
            print(f"     概率: {target.get('probability', 0)}%")
    
    # 显示时间窗口
    time_window = plan_result.get('time_window', {})
    print(f"\n⏰ 时间窗口:")
    print(f"   {time_window.get('window_description', '')}")
    print(f"   {time_window.get('golden_period', '')}")
    print(f"   预期交易日: {time_window.get('expected_trading_days', 0)}天")
    
    # 显示仓位管理
    position_plan = plan_result.get('position_plan', {})
    print(f"\n💰 仓位管理:")
    
    initial_entry = position_plan.get('initial_entry', {})
    print(f"   {initial_entry.get('description', '')}")
    print(f"   触发条件: {initial_entry.get('trigger', '')}")
    
    add_position = position_plan.get('add_position', {})
    print(f"   {add_position.get('description', '')}")
    print(f"   触发条件: {add_position.get('trigger', '')}")
    
    # 显示风险控制
    risk_control = plan_result.get('risk_control', {})
    print(f"\n⚠️ 风险控制:")
    
    stop_loss = risk_control.get('stop_loss', {})
    print(f"   {stop_loss.get('description', '')}")
    print(f"   触发条件: {stop_loss.get('trigger', '')}")
    
    print(f"   风险收益比: {risk_control.get('risk_reward_ratio', 0):.2f}")
    print(f"   最大亏损: {risk_control.get('max_loss_pct', 0):.1f}%")
    print(f"   预期收益: {risk_control.get('expected_gain_pct', 0):.1f}%")
    print(f"   风险评估: {risk_control.get('risk_assessment', '')}")
    
    # 显示执行总结
    execution_summary = plan_result.get('execution_summary', {})
    print(f"\n📊 执行总结表:")
    
    summary_table = execution_summary.get('summary_table', [])
    for item in summary_table:
        print(f"   {item.get('item', '')}: {item.get('key_level', '')} - {item.get('tactical_response', '')}")
    
    # 显示关键指标
    key_metrics = execution_summary.get('key_metrics', {})
    print(f"\n📈 关键指标:")
    print(f"   当前价格: {key_metrics.get('current_price', 0):.2f}元")
    print(f"   距离支撑: {key_metrics.get('support_distance', 0):.1f}%")
    print(f"   距离目标: {key_metrics.get('target_distance', 0):.1f}%")
    print(f"   风险收益比: {key_metrics.get('risk_reward_ratio', 0):.2f}")
    print(f"   最大仓位: {key_metrics.get('max_position', 0):.0f}%")
    
    return plan_result

def save_results(strategy_result, plan_result, stock_code="002021"):
    """保存分析结果"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    # 保存策略分析结果
    strategy_file = f"ma13_strategy_analysis_{stock_code}_{timestamp}.json"
    with open(strategy_file, 'w', encoding='utf-8') as f:
        json.dump(strategy_result, f, ensure_ascii=False, indent=2, default=str)
    
    # 保存执行计划
    plan_file = f"ma13_execution_plan_{stock_code}_{timestamp}.json"
    with open(plan_file, 'w', encoding='utf-8') as f:
        json.dump(plan_result, f, ensure_ascii=False, indent=2, default=str)
    
    print(f"\n💾 结果已保存:")
    print(f"   策略分析: {strategy_file}")
    print(f"   执行计划: {plan_file}")

def main():
    """主函数"""
    print("🚀 MA13短线交易策略演示")
    print("=" * 50)
    
    try:
        # 1. 创建示例数据
        df = create_sample_data()
        
        # 2. 计算技术指标
        df = calculate_technical_indicators(df)
        
        # 3. 显示最新数据
        latest = df.iloc[-1]
        print(f"\n📊 最新数据 ({latest['date']}):")
        print(f"   收盘价: {latest['close']:.2f}元")
        print(f"   MA13: {latest['ma13']:.2f}元")
        print(f"   MA30: {latest['ma30']:.2f}元")
        print(f"   RSI6: {latest['rsi6']:.1f}")
        print(f"   KDJ J: {latest['j']:.1f}")
        print(f"   成交量: {latest['volume']:,.0f}")
        
        # 4. 策略分析
        strategy_result = analyze_with_ma13_strategy(df, "002021")
        
        if strategy_result['success']:
            # 5. 生成执行计划
            plan_result = generate_execution_plan(df, strategy_result, "002021")
            
            if plan_result['success']:
                # 6. 保存结果
                save_results(strategy_result, plan_result, "002021")
                
                print(f"\n🎉 MA13短线策略演示完成!")
                print(f"   策略匹配: ✅")
                print(f"   执行计划: ✅")
                print(f"   建议操作: {strategy_result.get('recommendation', {}).get('action', 'wait')}")
                print(f"   信心度: {strategy_result.get('recommendation', {}).get('confidence', 0)}%")
            else:
                print(f"\n❌ 执行计划生成失败")
        else:
            print(f"\n❌ 策略分析未通过")
    
    except Exception as e:
        print(f"\n❌ 演示过程中出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()