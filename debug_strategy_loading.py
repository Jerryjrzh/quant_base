#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试策略加载问题
"""

import sys
import os

# 添加backend目录到路径
sys.path.append('backend')

def debug_strategy_loading():
    """调试策略加载"""
    print("🔍 调试策略加载问题")
    print("=" * 50)
    
    try:
        from strategy_manager import StrategyManager
        
        # 创建策略管理器
        manager = StrategyManager()
        
        print(f"📁 策略目录: {manager.strategies_dir}")
        print(f"📋 注册的策略数量: {len(manager.registered_strategies)}")
        print(f"📋 注册的策略: {list(manager.registered_strategies.keys())}")
        
        # 检查策略目录
        import glob
        strategy_files = glob.glob(os.path.join(manager.strategies_dir, '*_strategy.py'))
        print(f"📄 发现的策略文件: {len(strategy_files)}")
        for file in strategy_files:
            print(f"  - {os.path.basename(file)}")
        
        # 手动测试策略发现
        print("\n🔍 手动测试策略发现...")
        manager.discover_strategies()
        
        print(f"📋 发现后注册的策略数量: {len(manager.registered_strategies)}")
        print(f"📋 发现后注册的策略: {list(manager.registered_strategies.keys())}")
        
        # 测试单个策略文件加载
        print("\n🔍 测试单个策略文件加载...")
        from pathlib import Path
        
        test_file = Path(manager.strategies_dir) / "weekly_golden_cross_ma_strategy.py"
        if test_file.exists():
            print(f"📄 测试文件: {test_file}")
            try:
                manager._load_strategy_from_file(test_file)
                print("✅ 单个文件加载成功")
            except Exception as e:
                print(f"❌ 单个文件加载失败: {e}")
                import traceback
                traceback.print_exc()
        
        return True
        
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    debug_strategy_loading()