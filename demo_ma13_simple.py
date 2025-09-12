"""
MA13短线交易策略简化演示

不依赖复杂的数据加载，使用模拟数据演示策略功能
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# 简化的技术指标计算类
class SimpleIndicators:
    """简化的技术指标计算"""
    
    def calculate_ma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """计算移动平均线"""
        return df['close'].rolling(window=period).mean()
    
    def calculate_macd(self, df: pd.DataFrame, fast=12, slow=26, signal=9):
        """计算MACD指标"""
        ema_fast = df['close'].ewm(span=fast).mean()
        ema_slow = df['close'].ewm(span=slow).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal).mean()
        return dif, dea
    
    def calculate_kdj(self, df: pd.DataFrame, n=27, k=3, d=3):
        """计算KDJ指标"""
        low_n = df['low'].rolling(window=n).min()
        high_n = df['high'].rolling(window=n).max()
        rsv = (df['close'] - low_n) / (high_n - low_n) * 100
        
        k_values = []
        d_values = []
        j_values = []
        
        k_val = 50  # 初始值
        d_val = 50  # 初始值
        
        for rsv_val in rsv:
            if pd.notna(rsv_val):
                k_val = (2/3) * k_val + (1/3) * rsv_val
                d_val = (2/3) * d_val + (1/3) * k_val
                j_val = 3 * k_val - 2 * d_val
            else:
                j_val = np.nan
            
            k_values.append(k_val)
            d_values.append(d_val)
            j_values.append(j_val)
        
        return pd.Series(k_values, index=df.index), pd.Series(d_values, index=df.index), pd.Series(j_values, index=df.index)
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算RSI指标"""
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

# 简化的数据处理类
class SimpleDataHandler:
    """简化的数据处理"""
    
    def get_stock_data(self, stock_code: str, days: int = 150) -> pd.DataFrame:
        """生成模拟股票数据"""
        return create_sample_data(stock_code, days)

def create_sample_data(stock_code="002021", days=150):
    """创建符合MA13策略的示例数据"""
    print(f"📊 创建 {stock_code} 的示例数据 ({days}天)...")
    
    # 生成日期序列
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days*1.5)  # 多生成一些，然后筛选工作日
    
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    dates = [d for d in dates if d.weekday() < 5][:days]  # 只保留工作日
    
    np.random.seed(42)  # 固定随机种子
    
    # 第一阶段：底部箱体震荡 (前60%)
    box_days = int(days * 0.6)
    base_price = 2.20
    box_data = []
    
    for i in range(box_days):
        # 箱体震荡，波动范围2.15-2.40
        noise = np.random.normal(0, 0.02)
        price = base_price + 0.10 * np.sin(i * 0.1) + noise
        price = max(2.15, min(2.40, price))  # 限制在箱体内
        
        open_price = price * (1 + np.random.normal(0, 0.01))
        high_price = price * (1 + abs(np.random.normal(0, 0.015)))
        low_price = price * (1 - abs(np.random.normal(0, 0.015)))
        volume = np.random.normal(1.2e8, 0.2e8)  # 基础成交量 (降低以确保突破时放大明显)
        
        box_data.append({
            'date': dates[i].strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(price, 2),
            'volume': int(max(volume, 0.5e8))
        })
    
    # 第二阶段：突破上涨 (15%)
    breakout_days = int(days * 0.15)
    start_price = 2.40
    
    for i in range(breakout_days):
        # 放量突破，涨幅约30%
        progress = i / (breakout_days - 1) if breakout_days > 1 else 1
        price = start_price * (1 + 0.30 * progress)  # 涨到3.12
        
        # 添加一些波动
        noise = np.random.normal(0, 0.01)
        price = price * (1 + noise)
        
        open_price = price * (1 + np.random.normal(0, 0.008))
        high_price = price * (1 + abs(np.random.normal(0, 0.012)))
        low_price = price * (1 - abs(np.random.normal(0, 0.012)))
        
        # 突破期间成交量放大 (确保放大倍数足够)
        volume = np.random.normal(3.0e8, 0.5e8)  # 增加基础成交量
        
        box_data.append({
            'date': dates[box_days + i].strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high_price, 2),
            'low': round(low_price, 2),
            'close': round(price, 2),
            'volume': int(max(volume, 1.0e8))
        })
    
    # 第三阶段：回调至MA13 (15%)
    pullback_days = int(days * 0.15)
    high_price = 3.09
    
    for i in range(pullback_days):
        # 回调到MA13附近
        progress = i / (pullback_days - 1) if pullback_days > 1 else 1
        price = high_price * (1 - 0.10 * progress)  # 回调10%到2.78
        
        noise = np.random.normal(0, 0.008)
        price = price * (1 + noise)
        
        open_price = price * (1 + np.random.normal(0, 0.006))
        high_price_day = price * (1 + abs(np.random.normal(0, 0.010)))
        low_price_day = price * (1 - abs(np.random.normal(0, 0.010)))
        
        # 回调期间成交量缩小
        volume = np.random.normal(1.8e8, 0.4e8)
        
        box_data.append({
            'date': dates[box_days + breakout_days + i].strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high_price_day, 2),
            'low': round(low_price_day, 2),
            'close': round(price, 2),
            'volume': int(max(volume, 0.8e8))
        })
    
    # 第四阶段：当前反弹确认 (剩余10%)
    current_days = days - box_days - breakout_days - pullback_days
    start_price = 2.78
    
    for i in range(current_days):
        # 从MA13支撑反弹
        if i < current_days // 2:
            # 前半段在支撑位震荡
            price = start_price * (1 + np.random.normal(0, 0.01))
        else:
            # 后半段开始反弹
            progress = (i - current_days // 2) / (current_days // 2) if current_days > 2 else 1
            price = start_price * (1 + 0.08 * progress)  # 反弹8%
        
        noise = np.random.normal(0, 0.008)
        price = price * (1 + noise)
        
        open_price = price * (1 + np.random.normal(0, 0.006))
        high_price_day = price * (1 + abs(np.random.normal(0, 0.012)))
        low_price_day = price * (1 - abs(np.random.normal(0, 0.008)))
        
        # 反弹期间成交量逐步放大
        base_vol = 1.5e8 + (i / current_days) * 1.0e8 if current_days > 0 else 1.5e8
        volume = np.random.normal(base_vol, 0.3e8)
        
        box_data.append({
            'date': dates[box_days + breakout_days + pullback_days + i].strftime('%Y-%m-%d'),
            'open': round(open_price, 2),
            'high': round(high_price_day, 2),
            'low': round(low_price_day, 2),
            'close': round(price, 2),
            'volume': int(max(volume, 0.8e8))
        })
    
    df = pd.DataFrame(box_data)
    print(f"✅ 生成了{len(df)}天的股票数据")
    
    return df

def calculate_technical_indicators(df):
    """计算技术指标"""
    print("📈 计算技术指标...")
    
    indicators = SimpleIndicators()
    
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

def test_ma13_strategy_simple():
    """简化的MA13策略测试"""
    print("🚀 MA13短线交易策略简化演示")
    print("=" * 50)
    
    try:
        # 导入策略类
        from strategies.ma13_short_term_strategy import MA13ShortTermStrategy
        from short_term_execution_planner import ShortTermExecutionPlanner
        
        # 1. 创建示例数据
        df = create_sample_data("002021", 150)
        
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
        print(f"\n🔍 使用MA13短线策略分析...")
        
        strategy = MA13ShortTermStrategy()
        result = strategy.analyze_stock(df, "002021")
        
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
            
            # 5. 生成执行计划
            if result['success']:
                print(f"\n📋 生成执行计划...")
                
                planner = ShortTermExecutionPlanner()
                plan_result = planner.generate_execution_plan(df, result, "002021")
                
                if plan_result['success']:
                    print(f"✅ 执行计划生成成功")
                    
                    # 显示支撑位分析
                    support_analysis = plan_result.get('support_analysis', {})
                    print(f"\n🛡️ 支撑位分析:")
                    
                    core_support = support_analysis.get('core_support_zone', {})
                    print(f"   {core_support.get('description', '')}")
                    
                    final_support = support_analysis.get('final_support_zone', {})
                    print(f"   {final_support.get('description', '')}")
                    
                    print(f"   当前位置: {support_analysis.get('current_position', '')}")
                    
                    # 显示目标位分析
                    target_analysis = plan_result.get('target_analysis', {})
                    print(f"\n🎯 目标位分析:")
                    
                    for target_key in ['target_1', 'target_2']:
                        target = target_analysis.get(target_key, {})
                        if target:
                            print(f"   {target.get('description', '')}")
                    
                    # 显示时间窗口
                    time_window = plan_result.get('time_window', {})
                    print(f"\n⏰ 时间窗口:")
                    print(f"   {time_window.get('window_description', '')}")
                    print(f"   预期交易日: {time_window.get('expected_trading_days', 0)}天")
                    
                    # 显示风险控制
                    risk_control = plan_result.get('risk_control', {})
                    print(f"\n⚠️ 风险控制:")
                    print(f"   风险收益比: {risk_control.get('risk_reward_ratio', 0):.2f}")
                    print(f"   最大亏损: {risk_control.get('max_loss_pct', 0):.1f}%")
                    print(f"   预期收益: {risk_control.get('expected_gain_pct', 0):.1f}%")
                    
                    print(f"\n🎉 MA13短线策略演示完成!")
                    print(f"   策略匹配: ✅")
                    print(f"   执行计划: ✅")
                    print(f"   建议操作: {recommendation.get('action', 'wait')}")
                    print(f"   信心度: {recommendation.get('confidence', 0)}%")
                else:
                    print(f"❌ 执行计划生成失败: {plan_result.get('message', '')}")
        else:
            print(f"\n❌ 策略分析未通过")
    
    except Exception as e:
        print(f"\n❌ 演示过程中出错: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ma13_strategy_simple()