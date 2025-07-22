#!/usr/bin/env python3
"""
快速获取交易建议的工具
使用方法: python get_trading_advice.py [股票代码] [信号状态]
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
from datetime import datetime
import data_loader
import strategies
import indicators
from trading_advisor import TradingAdvisor

def get_stock_advice(stock_code, signal_state=None, entry_price=None):
    """获取指定股票的交易建议"""
    
    # 加载股票数据
    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    market = stock_code[:2]
    file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
    
    if not os.path.exists(file_path):
        return f"❌ 股票数据文件不存在: {stock_code}"
    
    try:
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 50:
            return f"❌ 股票数据不足: {stock_code}"
        
        df.set_index('date', inplace=True)
        
        # 计算技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        # 如果没有指定信号状态，自动检测最新信号
        if signal_state is None:
            signals = strategies.apply_macd_zero_axis_strategy(df)
            if signals is not None and signals.any():
                # 找到最近的信号
                recent_signals = signals[signals != ''].tail(5)
                if not recent_signals.empty:
                    signal_idx = df.index.get_loc(recent_signals.index[-1])
                    signal_state = recent_signals.iloc[-1]
                else:
                    return f"❌ 未发现有效信号: {stock_code}"
            else:
                return f"❌ 未发现有效信号: {stock_code}"
        else:
            # 使用最新数据点作为信号位置
            signal_idx = len(df) - 1
        
        # 初始化交易顾问
        advisor = TradingAdvisor()
        
        # 生成交易报告
        current_price = df.iloc[-1]['close']
        report = advisor.generate_trading_report(
            df, signal_idx, signal_state, entry_price, current_price
        )
        
        return format_simple_advice(stock_code, report)
        
    except Exception as e:
        return f"❌ 处理股票 {stock_code} 失败: {e}"

def format_simple_advice(stock_code, report):
    """格式化简洁的建议输出"""
    if 'error' in report:
        return f"❌ {report['error']}"
    
    output = []
    output.append(f"📊 {stock_code} 交易建议")
    output.append("=" * 40)
    
    # 基本信息
    if 'stock_info' in report:
        info = report['stock_info']
        output.append(f"📅 日期: {info['signal_date']}")
        output.append(f"🎯 信号: {info['signal_state']}")
        output.append(f"💰 价格: ¥{info['current_price']:.2f}")
        output.append("")
    
    # 入场建议
    if 'entry_analysis' in report and report['entry_analysis']:
        entry = report['entry_analysis']
        if 'entry_strategies' in entry and entry['entry_strategies']:
            strategy = entry['entry_strategies'][0]  # 取第一个策略
            output.append("🚀 入场建议:")
            output.append(f"  策略: {strategy['strategy']}")
            output.append(f"  价位1: ¥{strategy['entry_price_1']}")
            output.append(f"  价位2: ¥{strategy['entry_price_2']}")
            output.append(f"  仓位: {strategy['position_allocation']}")
            output.append("")
        
        if 'risk_management' in entry and 'stop_loss_levels' in entry['risk_management']:
            stops = entry['risk_management']['stop_loss_levels']
            output.append("⚠️ 止损建议:")
            output.append(f"  适中止损: ¥{stops.get('moderate', 'N/A')}")
            output.append(f"  技术止损: ¥{stops.get('technical', 'N/A')}")
            output.append("")
    
    # 出场建议
    if 'exit_analysis' in report and report['exit_analysis']:
        exit_data = report['exit_analysis']
        if 'current_status' in exit_data:
            status = exit_data['current_status']
            output.append("📈 持仓状态:")
            output.append(f"  当前盈亏: {status['current_pnl']}")
            output.append(f"  持有天数: {status['holding_days']}天")
            output.append("")
        
        if 'price_targets' in exit_data:
            targets = exit_data['price_targets']
            output.append("🎯 价格目标:")
            output.append(f"  止损位: ¥{targets.get('stop_loss', 'N/A')}")
            output.append(f"  目标位: ¥{targets.get('take_profit_1', 'N/A')}")
            output.append("")
        
        if 'exit_strategies' in exit_data and exit_data['exit_strategies']:
            strategy = exit_data['exit_strategies'][0]
            output.append("💡 当前建议:")
            output.append(f"  {strategy['action']}")
            output.append("")
    
    # 操作摘要
    if 'action_summary' in report and report['action_summary']:
        output.append("📋 操作要点:")
        for action in report['action_summary'][:2]:  # 只显示前两个要点
            output.append(f"  • {action}")
        output.append("")
    
    return "\n".join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python get_trading_advice.py <股票代码> [信号状态] [入场价格]")
        print("")
        print("示例:")
        print("  python get_trading_advice.py sh000001")
        print("  python get_trading_advice.py sz000001 PRE")
        print("  python get_trading_advice.py sh600000 MID 12.50")
        print("")
        print("信号状态: PRE(预备), MID(进行中), POST(已突破)")
        return
    
    stock_code = sys.argv[1].lower()
    signal_state = sys.argv[2] if len(sys.argv) > 2 else None
    entry_price = float(sys.argv[3]) if len(sys.argv) > 3 else None
    
    print("🤖 正在分析股票交易机会...")
    result = get_stock_advice(stock_code, signal_state, entry_price)
    print(result)

if __name__ == "__main__":
    main()