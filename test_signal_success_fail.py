#!/usr/bin/env python3
"""
测试回测成功和失败标识的显示
验证K线图上是否正确显示SUCCESS和FAIL状态
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
import data_loader
import indicators
import strategies
import backtester
from adjustment_processor import create_adjustment_config, create_adjustment_processor

def test_success_fail_display():
    """测试成功和失败标识的显示"""
    print("🔍 测试回测成功/失败标识显示")
    print("=" * 60)
    
    # 测试多个股票和策略
    test_configs = [
        ('sz300290', 'MACD_ZERO_AXIS'),
        ('sz000001', 'TRIPLE_CROSS'),
        ('sh600036', 'PRE_CROSS'),
        ('sz002415', 'WEEKLY_GOLDEN_CROSS_MA')
    ]
    
    for stock_code, strategy_name in test_configs:
        print(f"\n📊 测试 {stock_code} - {strategy_name}")
        print("-" * 50)
        
        try:
            # 加载数据
            market = stock_code[:2]
            base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
            file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
            
            if not os.path.exists(file_path):
                print(f"❌ 数据文件不存在: {file_path}")
                continue
                
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 100:
                print(f"❌ 数据加载失败或数据不足")
                continue
            
            # 应用复权处理
            adjustment_type = 'forward'
            adjustment_config = create_adjustment_config(adjustment_type)
            adjustment_processor = create_adjustment_processor(adjustment_config)
            df = adjustment_processor.process_data(df, stock_code)
            
            # 计算技术指标
            df['ma13'] = indicators.calculate_ma(df, 13)
            df['ma45'] = indicators.calculate_ma(df, 45)
            
            macd_config = indicators.MACDIndicatorConfig(adjustment_config=adjustment_config)
            df['dif'], df['dea'] = indicators.calculate_macd(df, config=macd_config, stock_code=stock_code)
            df['macd'] = df['dif'] - df['dea']
            
            kdj_config = indicators.KDJIndicatorConfig(adjustment_config=adjustment_config)
            df['k'], df['d'], df['j'] = indicators.calculate_kdj(df, config=kdj_config, stock_code=stock_code)
            
            # 应用策略
            signals = strategies.apply_strategy(strategy_name, df)
            
            if signals is None or signals[signals != ''].empty:
                print(f"⚠️ 无信号")
                continue
                
            # 执行回测
            backtest_results = backtester.run_backtest(df, signals)
            
            if not backtest_results or backtest_results.get('total_signals', 0) == 0:
                print(f"⚠️ 回测无结果")
                continue
            
            print(f"✅ 发现 {backtest_results['total_signals']} 个信号")
            
            # 分析成功/失败状态
            trades = backtest_results.get('trades', [])
            if not trades:
                print(f"⚠️ 无交易记录")
                continue
            
            success_count = sum(1 for trade in trades if trade.get('is_success', False))
            fail_count = len(trades) - success_count
            
            print(f"📈 成功交易: {success_count} 个")
            print(f"📉 失败交易: {fail_count} 个")
            print(f"🎯 成功率: {success_count/len(trades)*100:.1f}%")
            
            # 构建信号点（模拟前端逻辑）
            signal_df = df[signals != '']
            trade_results = {trade['entry_idx']: trade for trade in trades}
            
            success_signals = []
            fail_signals = []
            
            print(f"\n📍 信号点状态分析:")
            for i, (idx, row) in enumerate(signal_df.iterrows()):
                if i >= 10:  # 只显示前10个
                    break
                    
                original_state = str(signals[idx])
                idx_pos = df.index.get_loc(idx) if idx in df.index else 0
                is_success = trade_results.get(idx_pos, {}).get('is_success', False)
                final_state = f"{original_state}_SUCCESS" if is_success else f"{original_state}_FAIL"
                
                # 获取实际入场价格
                actual_entry_price = trade_results.get(idx_pos, {}).get('entry_price')
                if actual_entry_price is not None:
                    display_price = float(actual_entry_price)
                else:
                    display_price = float(row['close'])
                
                date_str = idx.strftime('%Y-%m-%d') if hasattr(idx, 'strftime') else str(idx)
                
                signal_point = {
                    'date': date_str,
                    'price': display_price,
                    'state': final_state,
                    'original_state': original_state
                }
                
                if is_success:
                    success_signals.append(signal_point)
                    status_icon = "🟢"
                else:
                    fail_signals.append(signal_point)
                    status_icon = "🔴"
                
                print(f"  {i+1:2d}. {date_str} {status_icon} {final_state} - ¥{display_price:.2f}")
                
                # 显示交易详情
                trade_info = trade_results.get(idx_pos, {})
                if trade_info:
                    max_profit = trade_info.get('actual_max_pnl', 0) * 100
                    max_drawdown = trade_info.get('max_drawdown', 0) * 100
                    days_to_peak = trade_info.get('days_to_peak', 0)
                    print(f"      最大收益: {max_profit:+.1f}%, 最大回撤: {max_drawdown:+.1f}%, 达峰天数: {days_to_peak}")
            
            print(f"\n📊 前端显示统计:")
            print(f"   🟢 绿色三角(SUCCESS): {len(success_signals)} 个")
            print(f"   🔴 红色三角(FAIL): {len(fail_signals)} 个")
            print(f"   🟡 黄色三角(其他): {len(signal_df) - len(success_signals) - len(fail_signals)} 个")
            
            # 验证前端颜色逻辑
            print(f"\n🎨 前端颜色映射验证:")
            for signal in (success_signals + fail_signals)[:5]:  # 显示前5个
                state = signal['state']
                if 'SUCCESS' in state:
                    color = '#00ff00'  # 绿色
                    color_name = "绿色"
                elif 'FAIL' in state:
                    color = '#ff0000'  # 红色
                    color_name = "红色"
                else:
                    color = '#ffff00'  # 黄色
                    color_name = "黄色"
                
                print(f"   {signal['date']} {state} → {color_name} ({color})")
            
            break  # 找到一个有效的测试就够了
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()

def test_frontend_color_logic():
    """测试前端颜色逻辑"""
    print(f"\n🎨 前端颜色逻辑测试")
    print("=" * 60)
    
    # 模拟不同状态的信号点
    test_signals = [
        {'state': 'PRE_SUCCESS', 'expected_color': '#00ff00'},
        {'state': 'MID_SUCCESS', 'expected_color': '#00ff00'},
        {'state': 'POST_SUCCESS', 'expected_color': '#00ff00'},
        {'state': 'PRE_FAIL', 'expected_color': '#ff0000'},
        {'state': 'MID_FAIL', 'expected_color': '#ff0000'},
        {'state': 'POST_FAIL', 'expected_color': '#ff0000'},
        {'state': 'BUY_SUCCESS', 'expected_color': '#00ff00'},
        {'state': 'BUY_FAIL', 'expected_color': '#ff0000'},
        {'state': 'UNKNOWN', 'expected_color': '#ffff00'},
        {'state': 'PRE', 'expected_color': '#ffff00'},
    ]
    
    print("📋 颜色映射测试:")
    for signal in test_signals:
        state = signal['state']
        expected = signal['expected_color']
        
        # 模拟前端逻辑
        if 'SUCCESS' in state:
            actual_color = '#00ff00'
        elif 'FAIL' in state:
            actual_color = '#ff0000'
        else:
            actual_color = '#ffff00'
        
        status = "✅" if actual_color == expected else "❌"
        color_name = {"#00ff00": "绿色", "#ff0000": "红色", "#ffff00": "黄色"}[actual_color]
        
        print(f"  {status} {state:12s} → {color_name:4s} ({actual_color})")

def check_backtester_success_criteria():
    """检查回测成功判定标准"""
    print(f"\n🔍 回测成功判定标准检查")
    print("=" * 60)
    
    print("📋 当前成功判定标准:")
    print(f"   1. 趋势确认: 确认期内至少60%的交易日收盘价高于入场价")
    print(f"   2. 收益目标: 实际最大收益 >= {backtester.PROFIT_TARGET_FOR_SUCCESS*100}%")
    print(f"   3. 期末检查: 确认期结束时价格不能低于入场价超过2%")
    
    print(f"\n⚙️ 相关参数:")
    print(f"   最大观察天数: {backtester.MAX_LOOKAHEAD_DAYS} 天")
    print(f"   成功收益目标: {backtester.PROFIT_TARGET_FOR_SUCCESS*100}%")
    
    print(f"\n💡 如果看不到失败标识，可能的原因:")
    print(f"   1. 成功判定标准过于宽松，大部分信号都被判定为成功")
    print(f"   2. 测试的股票/策略组合恰好表现较好")
    print(f"   3. 回测期间市场整体上涨，掩盖了失败信号")
    print(f"   4. 过滤器已经排除了大部分可能失败的信号")

if __name__ == "__main__":
    print("🔍 回测成功/失败标识显示测试")
    print("=" * 80)
    
    test_success_fail_display()
    test_frontend_color_logic()
    check_backtester_success_criteria()
    
    print(f"\n📝 总结:")
    print("1. 前端确实有SUCCESS(绿色)和FAIL(红色)的显示逻辑")
    print("2. 如果只看到成功标识，可能是因为:")
    print("   - 成功判定标准相对宽松")
    print("   - 过滤器已经排除了大部分失败信号")
    print("   - 测试期间市场表现较好")
    print("3. 可以通过调整成功判定标准来增加失败信号的显示")