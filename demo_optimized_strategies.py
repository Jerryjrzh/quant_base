#!/usr/bin/env python3
"""
演示优化后的策略回测系统
展示智能策略选择和避免长期持有的核心功能
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.append('backend')

def demo_strategy_selection():
    """演示策略选择逻辑"""
    print("🎯 策略选择演示")
    print("=" * 50)
    
    # 模拟不同策略的回测结果
    mock_trades = [
        {"strategy": "智能止盈止损(止盈)", "return_rate": 0.12, "hold_days": 8},
        {"strategy": "动态均线(跌破MA5)", "return_rate": 0.08, "hold_days": 15},
        {"strategy": "技术组合(RSI超买)", "return_rate": 0.15, "hold_days": 5},
        {"strategy": "趋势跟踪(回撤止损)", "return_rate": 0.06, "hold_days": 20},
        {"strategy": "时间退出(7天)", "return_rate": 0.04, "hold_days": 7},
        {"strategy": "买入持有", "return_rate": 0.10, "hold_days": 30},  # 长期持有
    ]
    
    print("📊 模拟策略结果:")
    for i, trade in enumerate(mock_trades, 1):
        print(f"{i}. {trade['strategy']}")
        print(f"   收益率: {trade['return_rate']:.1%}, 持有: {trade['hold_days']}天")
    
    # 应用策略选择逻辑
    print(f"\n🧠 策略评分计算:")
    scored_trades = []
    
    max_days = max(t['hold_days'] for t in mock_trades)
    
    for trade in mock_trades:
        # 收益率评分 (40%)
        return_score = trade['return_rate'] * 0.4
        
        # 时间效率评分 (30%)
        time_score = (1 - trade['hold_days'] / max_days) * 0.3
        
        # 风险调整评分 (30%)
        risk_penalty = 0
        if trade['return_rate'] < -0.1:
            risk_penalty = -0.1
        elif trade['hold_days'] > 20:
            risk_penalty = -0.05
        
        risk_score = 0.3 + risk_penalty
        
        # 综合评分
        total_score = return_score + time_score + risk_score
        
        scored_trades.append((trade, total_score))
        
        print(f"{trade['strategy'][:20]:<20}: "
              f"收益={return_score:.3f} + 时间={time_score:.3f} + 风险={risk_score:.3f} = {total_score:.3f}")
    
    # 选择最优策略
    optimal_trade = max(scored_trades, key=lambda x: x[1])[0]
    
    print(f"\n🏆 最优策略: {optimal_trade['strategy']}")
    print(f"   收益率: {optimal_trade['return_rate']:.1%}")
    print(f"   持有天数: {optimal_trade['hold_days']}天")
    print(f"   ✅ 避免了长期持有风险")

def demo_technical_indicators():
    """演示技术指标计算"""
    print(f"\n📈 技术指标演示")
    print("=" * 50)
    
    # 生成模拟价格数据
    np.random.seed(42)
    dates = pd.date_range(start='2025-07-01', periods=30, freq='D')
    
    # 模拟上升趋势的价格
    base_price = 10.0
    price_changes = np.random.normal(0.01, 0.02, 30)  # 平均1%涨幅，2%波动
    prices = [base_price]
    
    for change in price_changes[1:]:
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, prices[-1] * 0.95))  # 限制单日跌幅
    
    # 创建DataFrame
    df = pd.DataFrame({
        'close': prices,
        'high': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        'low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        'volume': np.random.randint(1000000, 5000000, 30)
    }, index=dates)
    
    # 计算技术指标
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['price_change'] = df['close'].pct_change()
    df['volatility'] = df['price_change'].rolling(window=10).std()
    
    # 模拟RSI
    df['rsi'] = 50 + np.random.normal(0, 15, 30)  # 模拟RSI值
    df['rsi'] = df['rsi'].clip(0, 100)
    
    print("📊 技术指标示例 (最近5天):")
    print(df[['close', 'ma5', 'ma10', 'rsi', 'volatility']].tail().round(3))
    
    # 演示退出信号检测
    print(f"\n🚨 退出信号检测:")
    
    latest = df.iloc[-1]
    signals = []
    
    if latest['rsi'] > 70:
        signals.append("RSI超买 (>70)")
    
    if latest['close'] < latest['ma5'] * 0.98:
        signals.append("跌破MA5")
    
    if latest['volatility'] > 0.03:
        signals.append("高波动率")
    
    if signals:
        print(f"   检测到信号: {', '.join(signals)}")
        print(f"   建议: 考虑退出")
    else:
        print(f"   无退出信号，继续持有")

def demo_risk_management():
    """演示风险管理机制"""
    print(f"\n🛡️  风险管理演示")
    print("=" * 50)
    
    # 模拟交易场景
    entry_price = 10.0
    current_prices = [10.5, 11.2, 10.8, 9.8, 9.5, 9.2]  # 价格变化序列
    atr = 0.3  # 平均真实波幅
    
    print(f"入场价格: ¥{entry_price:.2f}")
    print(f"ATR: {atr:.2f}")
    
    # 计算止损止盈位
    stop_loss = entry_price - 2 * atr
    take_profit = entry_price + 3 * atr
    trailing_stop = stop_loss
    
    print(f"初始止损: ¥{stop_loss:.2f}")
    print(f"目标止盈: ¥{take_profit:.2f}")
    
    print(f"\n📈 价格变化与风险控制:")
    
    for day, price in enumerate(current_prices, 1):
        # 更新移动止损
        if price > entry_price:
            new_trailing_stop = price - 2 * atr
            trailing_stop = max(trailing_stop, new_trailing_stop)
        
        # 检查退出条件
        exit_signal = None
        if price <= trailing_stop:
            exit_signal = f"触发移动止损 (¥{trailing_stop:.2f})"
        elif price >= take_profit:
            exit_signal = f"达到止盈目标 (¥{take_profit:.2f})"
        
        return_rate = (price - entry_price) / entry_price
        
        print(f"第{day}天: ¥{price:.2f} ({return_rate:+.1%}) "
              f"移动止损: ¥{trailing_stop:.2f}")
        
        if exit_signal:
            print(f"   🚨 {exit_signal}")
            print(f"   💰 最终收益: {return_rate:.1%}")
            break
    else:
        print(f"   ✅ 继续持有")

def main():
    """主演示函数"""
    print("🚀 优化策略回测系统演示")
    print("=" * 60)
    
    # 演示策略选择
    demo_strategy_selection()
    
    # 演示技术指标
    demo_technical_indicators()
    
    # 演示风险管理
    demo_risk_management()
    
    print(f"\n🎉 演示完成！")
    print(f"\n📋 系统优化要点:")
    print(f"  🎯 智能策略选择 - 综合收益率、时间效率和风险控制")
    print(f"  ⏱️  避免长期持有 - 多种时间退出机制")
    print(f"  📊 技术指标组合 - RSI、均线、布林带等多重信号")
    print(f"  🛡️  动态风险管理 - ATR止损、移动止损、波动率控制")
    print(f"  🔄 多策略验证 - 6种不同策略同时测试")
    print(f"  📈 收益最大化 - 选择每只股票的最优策略")

if __name__ == "__main__":
    main()