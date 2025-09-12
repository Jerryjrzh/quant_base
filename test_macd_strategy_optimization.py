#!/usr/bin/env python3
"""
测试MACD零轴启动策略优化效果
根据 test_fix_4.md 的优化建议进行验证
"""

import sys
import os
import pandas as pd
import numpy as np

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

# 添加strategies目录到路径
strategies_dir = os.path.join(backend_dir, 'strategies')
sys.path.insert(0, strategies_dir)

from strategies.macd_zero_axis_strategy import MacdZeroAxisStrategy

def create_dead_cross_scenario():
    """
    创建死叉场景的测试数据
    模拟DIF刚刚下穿DEA的情况
    """
    dates = pd.date_range('2025-08-01', '2025-08-26', freq='D')
    n = len(dates)
    
    # 基础价格数据
    close_prices = 10 + np.random.normal(0, 0.5, n)
    high_prices = close_prices * 1.02
    low_prices = close_prices * 0.98
    
    # 模拟MACD死叉场景
    # DIF从上方下穿DEA
    dif_values = np.array([0.1, 0.08, 0.05, 0.02, -0.01, -0.02, -0.03] + [0.0] * (n-7))
    dea_values = np.array([0.05, 0.04, 0.03, 0.02, 0.01, 0.0, -0.01] + [0.0] * (n-7))
    
    # 确保最后几天是死叉状态
    dif_values[-3:] = [-0.02, -0.03, -0.04]
    dea_values[-3:] = [0.01, 0.0, -0.01]
    
    macd_values = dif_values - dea_values
    
    df = pd.DataFrame({
        'date': dates,
        'close': close_prices,
        'high': high_prices,
        'low': low_prices,
        'dif': dif_values,
        'dea': dea_values,
        'macd': macd_values
    })
    
    return df

def create_golden_cross_scenario():
    """
    创建金叉场景的测试数据
    模拟DIF上穿DEA的情况
    """
    dates = pd.date_range('2025-08-01', '2025-08-26', freq='D')
    n = len(dates)
    
    # 基础价格数据
    close_prices = 10 + np.random.normal(0, 0.5, n)
    high_prices = close_prices * 1.02
    low_prices = close_prices * 0.98
    
    # 模拟MACD金叉场景
    # DIF从下方上穿DEA
    dif_values = np.array([-0.05, -0.03, -0.01, 0.01, 0.02, 0.03, 0.04] + [0.0] * (n-7))
    dea_values = np.array([-0.02, -0.01, 0.0, 0.0, 0.01, 0.01, 0.02] + [0.0] * (n-7))
    
    # 确保最后几天是金叉状态且向上
    dif_values[-3:] = [0.02, 0.03, 0.04]
    dea_values[-3:] = [0.01, 0.01, 0.02]
    
    macd_values = dif_values - dea_values
    
    df = pd.DataFrame({
        'date': dates,
        'close': close_prices,
        'high': high_prices,
        'low': low_prices,
        'dif': dif_values,
        'dea': dea_values,
        'macd': macd_values
    })
    
    return df

def test_dead_cross_prevention():
    """测试死叉后不生成信号的优化"""
    print("🧪 测试死叉后信号防护")
    print("=" * 50)
    
    # 创建死叉场景数据
    df = create_dead_cross_scenario()
    strategy = MacdZeroAxisStrategy()
    
    # 应用策略
    signals, details = strategy.apply_strategy(df)
    
    # 检查最后几天的信号
    last_signals = signals.tail(5)
    signal_count = (last_signals != '').sum()
    
    print(f"📊 死叉场景测试数据（最后3天）:")
    for i in range(-3, 0):
        idx = len(df) + i
        print(f"   第{i+4}天: DIF={df.iloc[idx]['dif']:.3f}, DEA={df.iloc[idx]['dea']:.3f}, 信号='{signals.iloc[idx]}'")
    
    print(f"\n📈 信号生成结果:")
    print(f"   最后5天信号数: {signal_count}")
    print(f"   预期结果: 0 (死叉后不应生成信号)")
    
    # 验证结果
    if signal_count == 0:
        print("✅ 优化成功：死叉后正确阻止信号生成")
        return True
    else:
        print("❌ 优化失败：死叉后仍然生成信号")
        return False

def test_golden_cross_signal_generation():
    """测试金叉时正常生成信号"""
    print("\n🧪 测试金叉信号正常生成")
    print("=" * 50)
    
    # 创建金叉场景数据
    df = create_golden_cross_scenario()
    strategy = MacdZeroAxisStrategy()
    
    # 应用策略
    signals, details = strategy.apply_strategy(df)
    
    # 检查信号生成情况
    total_signals = (signals != '').sum()
    mid_signals = (signals == 'MID').sum()
    
    print(f"📊 金叉场景测试数据（最后3天）:")
    for i in range(-3, 0):
        idx = len(df) + i
        print(f"   第{i+4}天: DIF={df.iloc[idx]['dif']:.3f}, DEA={df.iloc[idx]['dea']:.3f}, 信号='{signals.iloc[idx]}'")
    
    print(f"\n📈 信号生成结果:")
    print(f"   总信号数: {total_signals}")
    print(f"   MID信号数: {mid_signals}")
    print(f"   预期结果: >0 (金叉时应生成信号)")
    
    # 验证结果
    if total_signals > 0:
        print("✅ 正常工作：金叉时正确生成信号")
        return True
    else:
        print("❌ 异常：金叉时未能生成信号")
        return False

def test_dif_trend_requirement():
    """测试DIF向上趋势要求"""
    print("\n🧪 测试DIF向上趋势要求")
    print("=" * 50)
    
    # 创建DIF向下但接近DEA的场景
    dates = pd.date_range('2025-08-20', '2025-08-26', freq='D')
    n = len(dates)
    
    close_prices = np.full(n, 10.0)
    high_prices = close_prices * 1.02
    low_prices = close_prices * 0.98
    
    # DIF向下接近DEA但不满足向上趋势
    dif_values = np.array([0.05, 0.03, 0.01, -0.01, -0.02, -0.03, -0.04])
    dea_values = np.array([0.02, 0.01, 0.0, -0.01, -0.02, -0.03, -0.04])
    macd_values = dif_values - dea_values
    
    df = pd.DataFrame({
        'date': dates,
        'close': close_prices,
        'high': high_prices,
        'low': low_prices,
        'dif': dif_values,
        'dea': dea_values,
        'macd': macd_values
    })
    
    strategy = MacdZeroAxisStrategy()
    signals, details = strategy.apply_strategy(df)
    
    # 检查最后几天的信号
    last_signals = signals.tail(3)
    signal_count = (last_signals != '').sum()
    
    print(f"📊 DIF向下场景测试数据（最后3天）:")
    for i in range(-3, 0):
        idx = len(df) + i
        dif_trend = "向上" if df.iloc[idx]['dif'] > df.iloc[idx-1]['dif'] else "向下"
        print(f"   第{i+4}天: DIF={df.iloc[idx]['dif']:.3f} ({dif_trend}), DEA={df.iloc[idx]['dea']:.3f}, 信号='{signals.iloc[idx]}'")
    
    print(f"\n📈 信号生成结果:")
    print(f"   最后3天信号数: {signal_count}")
    print(f"   预期结果: 0 (DIF向下时不应生成信号)")
    
    # 验证结果
    if signal_count == 0:
        print("✅ 优化成功：DIF向下时正确阻止信号生成")
        return True
    else:
        print("❌ 优化失败：DIF向下时仍然生成信号")
        return False

def test_strategy_optimization_info():
    """测试策略优化信息"""
    print("\n🧪 测试策略优化信息")
    print("=" * 50)
    
    strategy = MacdZeroAxisStrategy()
    df = create_golden_cross_scenario()
    
    signals, details = strategy.apply_strategy(df)
    
    print(f"📊 策略详情:")
    print(f"   策略名称: {details.get('strategy', 'N/A')}")
    print(f"   版本: {details.get('version', 'N/A')}")
    print(f"   信号数量: {details.get('signal_count', 0)}")
    print(f"   优化说明: {details.get('optimization_note', 'N/A')}")
    
    # 验证优化说明存在
    has_optimization_note = 'optimization_note' in details
    
    if has_optimization_note:
        print("✅ 策略包含优化说明")
        return True
    else:
        print("❌ 策略缺少优化说明")
        return False

def main():
    """主测试函数"""
    print("🚀 MACD零轴启动策略优化测试")
    print("根据 doc/test_fix_4.md 的优化建议进行验证")
    print("=" * 60)
    
    test_results = []
    
    # 执行各项测试
    test_results.append(test_dead_cross_prevention())
    test_results.append(test_golden_cross_signal_generation())
    test_results.append(test_dif_trend_requirement())
    test_results.append(test_strategy_optimization_info())
    
    # 总结
    print("\n" + "=" * 60)
    print("📋 测试总结:")
    passed_tests = sum(test_results)
    total_tests = len(test_results)
    
    print(f"   通过测试: {passed_tests}/{total_tests}")
    
    if passed_tests == total_tests:
        print("🎉 所有MACD策略优化测试通过！")
    else:
        print("⚠️ 部分测试失败，需要进一步调试")
    
    return passed_tests == total_tests

if __name__ == "__main__":
    main()