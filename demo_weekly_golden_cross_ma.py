#!/usr/bin/env python3
"""
周线金叉+日线MA策略演示脚本
展示如何使用新的策略进行股票分析
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def demo_strategy_usage():
    """演示策略使用方法"""
    print("=== 周线金叉+日线MA策略使用演示 ===")
    
    # 1. 导入必要模块
    from strategies import (
        apply_weekly_golden_cross_ma_strategy,
        get_strategy_config,
        get_strategy_description
    )
    
    print("1. 策略信息:")
    description = get_strategy_description('WEEKLY_GOLDEN_CROSS_MA')
    print(f"   描述: {description}")
    
    # 2. 获取策略配置
    config = get_strategy_config('WEEKLY_GOLDEN_CROSS_MA')
    print(f"\n2. 策略配置:")
    print(f"   MA13容忍度: {config.weekly_golden_cross_ma.ma13_tolerance}")
    print(f"   成交量阈值: {config.weekly_golden_cross_ma.volume_surge_threshold}")
    print(f"   卖出阈值: {config.weekly_golden_cross_ma.sell_threshold}")
    
    # 3. 策略逻辑说明
    print(f"\n3. 策略逻辑:")
    print("   第一步: 通过周线MACD零轴策略判断POST状态")
    print("   第二步: 计算日线MA指标 [7, 13, 30, 45, 60, 90, 150, 240]")
    print("   第三步: 判断价格是否在MA13附近（±2%）")
    print("   第四步: 确认多重MA排列趋势（7>13>30>45）")
    print("   第五步: 成交量确认（放大20%）")
    print("   第六步: 生成BUY/HOLD/SELL信号")
    
    # 4. 信号含义
    print(f"\n4. 信号含义:")
    print("   BUY:  周线POST + 价格接近MA13 + 趋势向上 + 成交量放大")
    print("   HOLD: 周线POST + 价格在MA13上方 + 趋势向上")
    print("   SELL: 价格跌破MA13的95% 或 趋势转弱")
    
    return True

def demo_integration_with_existing_system():
    """演示与现有系统的集成"""
    print("\n=== 与现有系统集成演示 ===")
    
    # 1. 与筛选器集成
    print("1. 与筛选器集成:")
    print("   可以在 backend/screener.py 中添加此策略")
    print("   用于筛选符合周线金叉+日线MA条件的股票")
    
    # 2. 与回测系统集成
    print("\n2. 与回测系统集成:")
    print("   可以在 backend/backtester.py 中使用此策略")
    print("   评估策略的历史表现")
    
    # 3. 与多时间框架系统集成
    print("\n3. 与多时间框架系统集成:")
    print("   策略天然支持多时间框架（周线+日线）")
    print("   可以与 backend/multi_timeframe.py 系统结合")
    
    # 4. 与交易顾问集成
    print("\n4. 与交易顾问集成:")
    print("   可以在 backend/trading_advisor.py 中使用")
    print("   提供基于此策略的交易建议")
    
    return True

def demo_configuration_options():
    """演示配置选项"""
    print("\n=== 配置选项演示 ===")
    
    # 显示配置文件内容
    import json
    
    try:
        with open('backend/strategy_configs.json', 'r', encoding='utf-8') as f:
            configs = json.load(f)
        
        wgc_config = configs.get('WEEKLY_GOLDEN_CROSS_MA', {})
        
        print("1. MACD配置:")
        macd_config = wgc_config.get('macd', {})
        for key, value in macd_config.items():
            print(f"   {key}: {value}")
        
        print("\n2. MA配置:")
        ma_config = wgc_config.get('ma', {})
        for key, value in ma_config.items():
            print(f"   {key}: {value}")
        
        print("\n3. 成交量配置:")
        volume_config = wgc_config.get('volume', {})
        for key, value in volume_config.items():
            print(f"   {key}: {value}")
        
        print("\n4. 风险管理配置:")
        risk_config = wgc_config.get('risk', {})
        for key, value in risk_config.items():
            print(f"   {key}: {value}")
        
        print("\n5. 过滤器配置:")
        filter_config = wgc_config.get('filter', {})
        for key, value in filter_config.items():
            print(f"   {key}: {value}")
        
    except Exception as e:
        print(f"读取配置失败: {e}")
    
    return True

def demo_usage_examples():
    """演示使用示例"""
    print("\n=== 使用示例演示 ===")
    
    print("1. 基本使用:")
    print("""
    from strategies import apply_weekly_golden_cross_ma_strategy
    
    # 假设有日线数据 df
    signals = apply_weekly_golden_cross_ma_strategy(df)
    
    # 获取买入信号
    buy_signals = signals == 'BUY'
    buy_dates = df.index[buy_signals]
    """)
    
    print("2. 带周线数据使用:")
    print("""
    # 如果有独立的周线数据
    weekly_df = load_weekly_data(symbol)
    signals = apply_weekly_golden_cross_ma_strategy(df, weekly_df=weekly_df)
    """)
    
    print("3. 自定义配置使用:")
    print("""
    # 使用自定义配置
    config = get_strategy_config('WEEKLY_GOLDEN_CROSS_MA')
    config.weekly_golden_cross_ma.ma13_tolerance = 0.03  # 调整容忍度
    signals = apply_weekly_golden_cross_ma_strategy(df, config=config)
    """)
    
    print("4. 批量处理:")
    print("""
    # 批量处理多个股票
    symbols = ['000001', '000002', '600000']
    results = {}
    
    for symbol in symbols:
        df = load_stock_data(symbol)
        signals = apply_weekly_golden_cross_ma_strategy(df)
        results[symbol] = signals
    """)
    
    return True

def demo_performance_considerations():
    """演示性能考虑"""
    print("\n=== 性能考虑演示 ===")
    
    print("1. 数据要求:")
    print("   - 建议至少300天的日线数据")
    print("   - 需要OHLCV完整数据")
    print("   - 周线数据可以从日线自动生成")
    
    print("\n2. 计算复杂度:")
    print("   - MA计算: O(n)")
    print("   - MACD计算: O(n)")
    print("   - 信号映射: O(n)")
    print("   - 总体复杂度: O(n)")
    
    print("\n3. 优化建议:")
    print("   - 缓存周线数据转换结果")
    print("   - 批量计算多个股票时复用配置")
    print("   - 使用向量化操作提高效率")
    
    print("\n4. 内存使用:")
    print("   - 主要消耗在MA指标计算")
    print("   - 8个MA指标 × 数据长度")
    print("   - 建议分批处理大量股票")
    
    return True

def main():
    """主演示函数"""
    print("周线金叉+日线MA策略完整演示")
    print("=" * 60)
    
    demos = [
        demo_strategy_usage,
        demo_integration_with_existing_system,
        demo_configuration_options,
        demo_usage_examples,
        demo_performance_considerations
    ]
    
    for demo_func in demos:
        try:
            demo_func()
        except Exception as e:
            print(f"演示 {demo_func.__name__} 失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("\n下一步建议:")
    print("1. 使用真实数据测试策略效果")
    print("2. 调整配置参数优化策略表现")
    print("3. 集成到现有的交易系统中")
    print("4. 进行回测验证策略有效性")

if __name__ == "__main__":
    main()