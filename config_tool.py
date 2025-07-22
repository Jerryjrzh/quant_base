#!/usr/bin/env python3
"""
策略配置管理工具
用于管理和测试不同的交易参数配置
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import json
from datetime import datetime
import data_loader
import strategies
import indicators
from strategy_config import StrategyConfigManager
from parametric_advisor import ParametricTradingAdvisor, TradingParameters

def show_available_configs():
    """显示可用配置"""
    print("📋 策略配置管理工具")
    print("=" * 50)
    
    config_manager = StrategyConfigManager()
    config_manager.list_available_configs()

def test_config_on_stock(stock_code, risk_profile='moderate', market_env=None):
    """在指定股票上测试配置"""
    print(f"🧪 测试配置在股票 {stock_code} 上的效果")
    print(f"📊 风险配置: {risk_profile}")
    if market_env:
        print(f"🌍 市场环境: {market_env}")
    print("=" * 50)
    
    # 加载数据
    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    market = stock_code[:2]
    file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
    
    if not os.path.exists(file_path):
        print(f"❌ 股票数据文件不存在: {stock_code}")
        return
    
    try:
        # 加载和预处理数据
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 100:
            print(f"❌ 股票数据不足: {stock_code}")
            return
        
        df.set_index('date', inplace=True)
        
        # 计算技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        # 生成信号
        signals = strategies.apply_macd_zero_axis_strategy(df)
        if signals is None or not signals.any():
            print(f"❌ 未发现有效信号: {stock_code}")
            return
        
        # 获取配置
        config_manager = StrategyConfigManager()
        
        if market_env is None:
            # 自动检测市场环境
            adaptive_config = config_manager.get_adaptive_config(df, risk_profile)
            if adaptive_config:
                market_env = adaptive_config['market_environment']
                params = adaptive_config['parameters']
                print(f"🔍 自动检测市场环境: {market_env}")
            else:
                print("❌ 无法获取自适应配置，使用默认参数")
                return
        else:
            # 使用指定的市场环境
            risk_config = config_manager.get_risk_profile(risk_profile)
            market_config = config_manager.get_market_environment(market_env)
            
            if not risk_config or not market_config:
                print(f"❌ 配置不存在: {risk_profile} 或 {market_env}")
                return
            
            # 手动组合参数
            params = {
                'pre_entry_discount': max(0.005, risk_config.pre_entry_discount + market_config.entry_discount_adjustment),
                'stop_loss_pct': max(0.01, risk_config.stop_loss_pct + market_config.stop_loss_adjustment),
                'take_profit_pct': max(0.03, risk_config.take_profit_pct + market_config.take_profit_adjustment),
                'max_holding_days': max(1, risk_config.max_holding_days + market_config.holding_period_adjustment),
                'max_position_size': risk_config.max_position_size
            }
        
        # 创建参数化顾问
        trading_params = TradingParameters()
        trading_params.pre_entry_discount = params['pre_entry_discount']
        trading_params.moderate_stop = params['stop_loss_pct']
        trading_params.moderate_profit = params['take_profit_pct']
        trading_params.max_holding_days = params['max_holding_days']
        
        advisor = ParametricTradingAdvisor(trading_params)
        
        # 执行回测
        backtest_result = advisor.backtest_parameters(df, signals, 'moderate')
        
        # 显示结果
        print("\n📊 配置测试结果:")
        print("-" * 30)
        print(f"市场环境: {market_env}")
        print(f"风险配置: {risk_profile}")
        print()
        
        print("📋 使用的参数:")
        print(f"  入场折扣: {params['pre_entry_discount']:.1%}")
        print(f"  止损比例: {params['stop_loss_pct']:.1%}")
        print(f"  止盈比例: {params['take_profit_pct']:.1%}")
        print(f"  最大持有天数: {params['max_holding_days']}")
        print(f"  最大仓位: {params.get('max_position_size', 0.5):.0%}")
        print()
        
        if 'error' not in backtest_result:
            print("📈 回测结果:")
            print(f"  总交易次数: {backtest_result['total_trades']}")
            print(f"  胜率: {backtest_result['win_rate']:.1%}")
            print(f"  平均收益: {backtest_result['avg_pnl']:+.2%}")
            print(f"  最大盈利: {backtest_result['max_win']:+.2%}")
            print(f"  最大亏损: {backtest_result['max_loss']:+.2%}")
            print(f"  平均持有天数: {backtest_result['avg_holding_days']:.1f}")
            print(f"  盈亏比: {backtest_result['profit_factor']:.2f}")
        else:
            print(f"❌ 回测失败: {backtest_result['error']}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")

def compare_configs_on_stock(stock_code, risk_profiles=None):
    """在指定股票上对比不同配置"""
    if risk_profiles is None:
        risk_profiles = ['conservative', 'moderate', 'aggressive']
    
    print(f"🔄 对比不同配置在股票 {stock_code} 上的效果")
    print("=" * 60)
    
    results = {}
    
    for risk_profile in risk_profiles:
        print(f"\n测试配置: {risk_profile}")
        print("-" * 30)
        
        # 这里我们需要修改test_config_on_stock来返回结果而不是打印
        result = test_config_silently(stock_code, risk_profile)
        if result:
            results[risk_profile] = result
    
    # 显示对比结果
    print("\n📊 配置对比结果:")
    print("=" * 60)
    print(f"{'配置':<12} {'胜率':<8} {'平均收益':<10} {'最大盈利':<10} {'盈亏比':<8}")
    print("-" * 60)
    
    for config, result in results.items():
        if 'error' not in result:
            print(f"{config:<12} {result['win_rate']:<7.1%} {result['avg_pnl']:<9.2%} "
                  f"{result['max_win']:<9.2%} {result['profit_factor']:<8.2f}")
    
    # 找出最佳配置
    if results:
        best_config = max(results.items(), 
                         key=lambda x: x[1]['win_rate'] * 0.6 + max(0, x[1]['avg_pnl']) * 0.4 
                         if 'error' not in x[1] else 0)
        
        print(f"\n🏆 最佳配置: {best_config[0]}")
        print(f"   综合得分: {best_config[1]['win_rate'] * 0.6 + max(0, best_config[1]['avg_pnl']) * 0.4:.3f}")

def test_config_silently(stock_code, risk_profile):
    """静默测试配置（返回结果而不打印）"""
    try:
        # 加载数据
        base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        market = stock_code[:2]
        file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
        
        if not os.path.exists(file_path):
            return {'error': '数据文件不存在'}
        
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 100:
            return {'error': '数据不足'}
        
        df.set_index('date', inplace=True)
        
        # 计算技术指标
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        
        # 生成信号
        signals = strategies.apply_macd_zero_axis_strategy(df)
        if signals is None or not signals.any():
            return {'error': '无有效信号'}
        
        # 获取配置
        config_manager = StrategyConfigManager()
        adaptive_config = config_manager.get_adaptive_config(df, risk_profile)
        
        if not adaptive_config:
            return {'error': '无法获取配置'}
        
        params = adaptive_config['parameters']
        
        # 创建参数化顾问
        trading_params = TradingParameters()
        trading_params.pre_entry_discount = params['pre_entry_discount']
        trading_params.moderate_stop = params['stop_loss_pct']
        trading_params.moderate_profit = params['take_profit_pct']
        trading_params.max_holding_days = params['max_holding_days']
        
        advisor = ParametricTradingAdvisor(trading_params)
        
        # 执行回测
        return advisor.backtest_parameters(df, signals, 'moderate')
        
    except Exception as e:
        return {'error': str(e)}

def create_custom_config():
    """创建自定义配置"""
    print("🛠️ 创建自定义风险配置")
    print("=" * 30)
    
    config_manager = StrategyConfigManager()
    
    # 获取用户输入
    name = input("配置名称: ").strip()
    if not name:
        print("❌ 配置名称不能为空")
        return
    
    description = input("配置描述: ").strip()
    if not description:
        description = f"自定义配置 - {name}"
    
    print("\n请输入参数 (直接回车使用默认值):")
    
    try:
        # 获取参数输入
        max_position_size = input("最大仓位比例 (0.4): ").strip()
        max_position_size = float(max_position_size) if max_position_size else 0.4
        
        stop_loss_pct = input("止损比例 (0.05): ").strip()
        stop_loss_pct = float(stop_loss_pct) if stop_loss_pct else 0.05
        
        take_profit_pct = input("止盈比例 (0.12): ").strip()
        take_profit_pct = float(take_profit_pct) if take_profit_pct else 0.12
        
        max_holding_days = input("最大持有天数 (30): ").strip()
        max_holding_days = int(max_holding_days) if max_holding_days else 30
        
        # 创建配置
        custom_config = config_manager.create_custom_risk_profile(
            name=name,
            description=description,
            max_position_size=max_position_size,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            max_holding_days=max_holding_days
        )
        
        if custom_config:
            print(f"✅ 自定义配置 '{name}' 创建成功！")
            print("💡 现在可以使用以下命令测试:")
            print(f"   python config_tool.py test <股票代码> {name}")
        
    except ValueError as e:
        print(f"❌ 参数输入错误: {e}")
    except Exception as e:
        print(f"❌ 创建配置失败: {e}")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("策略配置管理工具")
        print("=" * 30)
        print("使用方法:")
        print("  python config_tool.py list                              # 显示可用配置")
        print("  python config_tool.py test <股票代码> [风险配置] [市场环境]  # 测试配置")
        print("  python config_tool.py compare <股票代码>                 # 对比配置")
        print("  python config_tool.py create                           # 创建自定义配置")
        print("")
        print("示例:")
        print("  python config_tool.py list")
        print("  python config_tool.py test sh000001 moderate")
        print("  python config_tool.py test sz000001 aggressive bull_market")
        print("  python config_tool.py compare sh000001")
        print("  python config_tool.py create")
        return
    
    command = sys.argv[1].lower()
    
    if command == 'list':
        show_available_configs()
        
    elif command == 'test':
        if len(sys.argv) < 3:
            print("❌ 请提供股票代码")
            return
        
        stock_code = sys.argv[2].lower()
        risk_profile = sys.argv[3] if len(sys.argv) > 3 else 'moderate'
        market_env = sys.argv[4] if len(sys.argv) > 4 else None
        
        test_config_on_stock(stock_code, risk_profile, market_env)
        
    elif command == 'compare':
        if len(sys.argv) < 3:
            print("❌ 请提供股票代码")
            return
        
        stock_code = sys.argv[2].lower()
        compare_configs_on_stock(stock_code)
        
    elif command == 'create':
        create_custom_config()
        
    else:
        print(f"❌ 未知命令: {command}")

if __name__ == "__main__":
    main()