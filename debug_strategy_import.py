#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试策略导入问题
"""

import sys
import os

# 添加backend目录到路径
sys.path.append('backend')

def test_strategy_import():
    """测试策略导入"""
    print("🔍 测试策略导入")
    print("=" * 50)
    
    # 测试BaseStrategy导入
    try:
        from strategies.base_strategy import BaseStrategy
        print("✅ BaseStrategy 导入成功")
    except Exception as e:
        print(f"❌ BaseStrategy 导入失败: {e}")
        return False
    
    # 测试单个策略文件导入
    strategy_files = [
        'weekly_golden_cross_ma_strategy',
        'macd_zero_axis_strategy',
        'abyss_bottoming_strategy',
        'pre_cross_strategy',
        'triple_cross_strategy'
    ]
    
    for strategy_file in strategy_files:
        try:
            print(f"\n🔍 测试导入: {strategy_file}")
            
            # 添加strategies目录到路径
            strategies_dir = os.path.join('backend', 'strategies')
            if strategies_dir not in sys.path:
                sys.path.insert(0, strategies_dir)
            
            # 导入模块
            module = __import__(strategy_file)
            
            # 查找策略类
            found_classes = []
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    hasattr(attr, '__bases__') and
                    any(base.__name__ == 'BaseStrategy' for base in attr.__bases__)):
                    found_classes.append(attr.__name__)
            
            if found_classes:
                print(f"✅ 找到策略类: {found_classes}")
            else:
                print(f"❌ 未找到策略类")
                
                # 显示模块中的所有类
                all_classes = []
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if isinstance(attr, type):
                        all_classes.append(attr.__name__)
                print(f"   模块中的所有类: {all_classes}")
                
        except Exception as e:
            print(f"❌ 导入失败: {e}")
            import traceback
            traceback.print_exc()
    
    return True

if __name__ == '__main__':
    test_strategy_import()