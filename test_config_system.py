#!/usr/bin/env python3
"""
测试配置系统
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from strategy_config import StrategyConfigManager

def test_config_system():
    """测试配置系统"""
    print("🧪 测试策略配置系统")
    print("=" * 40)
    
    # 创建配置管理器
    config_manager = StrategyConfigManager()
    
    # 显示配置
    print("📋 市场环境配置:")
    for name, env in config_manager.market_environments.items():
        print(f"  {name}: {env.description}")
    
    print("\n📋 风险配置:")
    for name, profile in config_manager.risk_profiles.items():
        print(f"  {name}: {profile.description}")
        print(f"    最大仓位: {profile.max_position_size:.0%}")
        print(f"    止损比例: {profile.stop_loss_pct:.1%}")
        print(f"    止盈比例: {profile.take_profit_pct:.1%}")
        print(f"    最大持有天数: {profile.max_holding_days}")
        print()
    
    # 测试自适应配置
    print("🔧 测试自适应配置...")
    
    # 创建模拟数据
    import pandas as pd
    import numpy as np
    from datetime import datetime, timedelta
    
    # 生成模拟股价数据
    dates = pd.date_range(start='2023-01-01', end='2024-01-01', freq='D')
    np.random.seed(42)
    prices = 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, len(dates)))
    
    df = pd.DataFrame({
        'date': dates,
        'close': prices,
        'high': prices * (1 + np.random.uniform(0, 0.02, len(dates))),
        'low': prices * (1 - np.random.uniform(0, 0.02, len(dates))),
        'open': prices,
        'volume': np.random.randint(1000000, 10000000, len(dates))
    })
    df.set_index('date', inplace=True)
    
    # 测试市场环境检测
    detected_env = config_manager.detect_market_environment(df)
    print(f"检测到的市场环境: {detected_env}")
    
    # 获取自适应配置
    adaptive_config = config_manager.get_adaptive_config(df, 'moderate')
    if adaptive_config:
        print(f"自适应配置:")
        print(f"  市场环境: {adaptive_config['market_environment']}")
        print(f"  风险配置: {adaptive_config['risk_profile']}")
        print(f"  参数:")
        for key, value in adaptive_config['parameters'].items():
            if isinstance(value, float) and key.endswith(('_pct', '_discount', '_premium')):
                print(f"    {key}: {value:.1%}")
            else:
                print(f"    {key}: {value}")
    
    print("\n✅ 配置系统测试完成！")

if __name__ == "__main__":
    test_config_system()