#!/usr/bin/env python3
"""
交易操作顾问演示脚本
展示如何获取具体的买入卖出价格建议
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import json
import glob
from datetime import datetime
import data_loader
import strategies
import indicators
from trading_advisor import TradingAdvisor

def format_trading_report(report):
    """格式化交易报告输出"""
    print("=" * 80)
    print("📊 交易操作建议报告")
    print("=" * 80)
    
    # 基本信息
    if 'stock_info' in report:
        info = report['stock_info']
        print(f"📅 信号日期: {info['signal_date']}")
        print(f"🎯 信号状态: {info['signal_state']}")
        print(f"💰 当前价格: ¥{info['current_price']:.2f}")
        print()
    
    # 入场分析
    if 'entry_analysis' in report and report['entry_analysis']:
        entry = report['entry_analysis']
        print("🚀 入场建议:")
        print("-" * 40)
        
        if 'entry_strategies' in entry:
            for i, strategy in enumerate(entry['entry_strategies'], 1):
                print(f"策略 {i}: {strategy['strategy']}")
                print(f"  目标价位1: ¥{strategy['entry_price_1']}")
                print(f"  目标价位2: ¥{strategy['entry_price_2']}")
                print(f"  仓位配置: {strategy['position_allocation']}")
                print(f"  操作理由: {strategy['rationale']}")
                print()
        
        if 'timing_advice' in entry:
            timing = entry['timing_advice']
            print("⏰ 时机建议:")
            print(f"  最佳时机: {timing.get('best_timing', 'N/A')}")
            print(f"  关注要点: {timing.get('watch_for', 'N/A')}")
            print(f"  避免条件: {timing.get('avoid_if', 'N/A')}")
            print()
        
        if 'risk_management' in entry:
            risk = entry['risk_management']
            print("⚠️ 风险管理:")
            if 'stop_loss_levels' in risk:
                stops = risk['stop_loss_levels']
                print(f"  保守止损: ¥{stops.get('conservative', 'N/A')}")
                print(f"  适中止损: ¥{stops.get('moderate', 'N/A')}")
                print(f"  激进止损: ¥{stops.get('aggressive', 'N/A')}")
                print(f"  技术止损: ¥{stops.get('technical', 'N/A')}")
            print()
    
    # 出场分析
    if 'exit_analysis' in report and report['exit_analysis']:
        exit_data = report['exit_analysis']
        print("🎯 出场建议:")
        print("-" * 40)
        
        if 'current_status' in exit_data:
            status = exit_data['current_status']
            print(f"入场日期: {status['entry_date']}")
            print(f"入场价格: ¥{status['entry_price']:.2f}")
            print(f"当前价格: ¥{status['current_price']:.2f}")
            print(f"当前盈亏: {status['current_pnl']}")
            print(f"持有天数: {status['holding_days']}天")
            print()
        
        if 'price_targets' in exit_data:
            targets = exit_data['price_targets']
            print("🎯 价格目标:")
            print(f"  止损位: ¥{targets.get('stop_loss', 'N/A')}")
            print(f"  目标位1: ¥{targets.get('take_profit_1', 'N/A')}")
            print(f"  目标位2: ¥{targets.get('take_profit_2', 'N/A')}")
            print(f"  目标位3: ¥{targets.get('take_profit_3', 'N/A')}")
            print()
        
        if 'exit_strategies' in exit_data:
            for i, strategy in enumerate(exit_data['exit_strategies'], 1):
                print(f"策略 {i}: {strategy['strategy']}")
                print(f"  操作建议: {strategy['action']}")
                print(f"  目标价位: {strategy['target_price']}")
                print(f"  操作理由: {strategy['rationale']}")
                print()
        
        if 'risk_alerts' in exit_data and exit_data['risk_alerts']:
            print("🚨 风险警报:")
            for alert in exit_data['risk_alerts']:
                severity_icon = "🔴" if alert['severity'] == 'high' else "🟡"
                print(f"  {severity_icon} {alert['type']}: {alert['message']}")
            print()
    
    # 市场环境
    if 'market_context' in report and report['market_context']:
        context = report['market_context']
        print("🌍 市场环境:")
        print("-" * 40)
        print(f"价格趋势: {context.get('price_trend', 'N/A')}")
        print(f"波动水平: {context.get('volatility', 'N/A')}")
        print(f"趋势方向: {context.get('trend_direction', 'N/A')}")
        print(f"市场状态: {context.get('market_state', 'N/A')}")
        print()
    
    # 操作摘要
    if 'action_summary' in report and report['action_summary']:
        print("📋 操作摘要:")
        print("-" * 40)
        for action in report['action_summary']:
            print(f"• {action}")
        print()
    
    print("=" * 80)

def load_sample_stock_data():
    """加载示例股票数据"""
    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    
    # 尝试加载一些常见的股票代码
    sample_codes = ['sh000001', 'sz000001', 'sh600000', 'sz000002', 'sh600036']
    stock_data = {}
    
    for code in sample_codes:
        try:
            market = code[:2]
            file_path = os.path.join(base_path, market, 'lday', f'{code}.day')
            
            if os.path.exists(file_path):
                df = data_loader.get_daily_data(file_path)
                if df is not None and len(df) > 100:  # 确保有足够的数据
                    df.set_index('date', inplace=True)
                    stock_data[code] = df
                    print(f"✅ 加载股票 {code}: {len(df)} 条记录")
                    if len(stock_data) >= 2:  # 只需要几只股票做演示
                        break
        except Exception as e:
            print(f"⚠️ 加载股票 {code} 失败: {e}")
            continue
    
    return stock_data

def demo_trading_advisor():
    """演示交易顾问功能"""
    print("🤖 启动交易操作顾问演示...")
    
    # 初始化组件
    advisor = TradingAdvisor()
    
    # 加载数据
    print("📊 加载股票数据...")
    stock_data = load_sample_stock_data()
    
    if not stock_data:
        print("❌ 无法加载股票数据")
        print("💡 请确保通达信数据路径正确，或者有可用的股票数据文件")
        return
    
    # 选择一只有信号的股票进行演示
    demo_stock = None
    demo_signals = None
    
    for symbol, df in stock_data.items():
        try:
            # 计算技术指标
            macd_values = indicators.calculate_macd(df)
            df['dif'], df['dea'] = macd_values[0], macd_values[1]
            
            # 运行MACD零轴启动策略获取信号
            signals = strategies.apply_macd_zero_axis_strategy(df)
            if signals is not None and signals.any():
                demo_stock = symbol
                demo_signals = signals
                demo_df = df
                break
        except Exception as e:
            print(f"⚠️ 处理股票 {symbol} 失败: {e}")
            continue
    
    if demo_stock is None:
        print("❌ 未找到有效信号的股票")
        return
    
    print(f"🎯 选择演示股票: {demo_stock}")
    
    # 找到最近的信号
    signal_indices = demo_df.index[demo_signals != ''].tolist()
    if not signal_indices:
        print("❌ 未找到有效信号")
        return
    
    # 使用最后一个信号进行演示
    signal_idx = demo_df.index.get_loc(signal_indices[-1])
    signal_state = demo_signals.iloc[signal_idx]
    
    print(f"📍 信号位置: 第{signal_idx}天, 状态: {signal_state}")
    
    # 场景1: 入场建议
    print("\n" + "="*50)
    print("场景1: 获取入场操作建议")
    print("="*50)
    
    entry_report = advisor.get_entry_recommendations(demo_df, signal_idx, signal_state)
    
    if 'error' not in entry_report:
        # 生成完整报告
        full_report = advisor.generate_trading_report(demo_df, signal_idx, signal_state)
        format_trading_report(full_report)
    else:
        print(f"❌ 获取入场建议失败: {entry_report['error']}")
    
    # 场景2: 出场建议（模拟已入场情况）
    print("\n" + "="*50)
    print("场景2: 模拟入场后的出场建议")
    print("="*50)
    
    # 模拟入场价格（使用信号当天收盘价）
    entry_price = demo_df.iloc[signal_idx]['close']
    
    # 模拟当前时间（信号后10天）
    current_idx = min(signal_idx + 10, len(demo_df) - 1)
    
    exit_report = advisor.get_exit_recommendations(demo_df, signal_idx, entry_price, current_idx)
    
    if 'error' not in exit_report:
        # 生成包含出场建议的完整报告
        full_report_with_exit = advisor.generate_trading_report(
            demo_df, signal_idx, signal_state, entry_price, demo_df.iloc[current_idx]['close']
        )
        format_trading_report(full_report_with_exit)
    else:
        print(f"❌ 获取出场建议失败: {exit_report['error']}")
    
    # 场景3: 不同风险等级的建议对比
    print("\n" + "="*50)
    print("场景3: 不同风险等级的出场目标对比")
    print("="*50)
    
    risk_levels = ['conservative', 'moderate', 'aggressive']
    
    for risk_level in risk_levels:
        print(f"\n🎯 {risk_level.upper()} 风险等级:")
        print("-" * 30)
        
        exit_targets = advisor._calculate_exit_targets(demo_df, signal_idx, entry_price, risk_level)
        
        print(f"止损位: ¥{exit_targets['stop_loss']}")
        print(f"目标位1: ¥{exit_targets['take_profit_1']}")
        print(f"目标位2: ¥{exit_targets['take_profit_2']}")
        print(f"目标位3: ¥{exit_targets['take_profit_3']}")
    
    print("\n✅ 交易顾问演示完成!")
    print("\n💡 使用建议:")
    print("1. 战略层面：选择合适的策略信号")
    print("2. 战术层面：根据信号状态制定入场计划")
    print("3. 操作层面：严格执行价格目标和风险控制")
    print("4. 管理层面：持续监控并调整仓位")

if __name__ == "__main__":
    demo_trading_advisor()