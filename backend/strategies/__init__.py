# 策略模块初始化文件
"""
策略模块初始化文件
导入所有策略函数以保持向后兼容性
"""

import sys
import os
import importlib.util

# 直接导入strategies.py文件，避免循环导入
backend_dir = os.path.dirname(os.path.dirname(__file__))
strategies_file = os.path.join(backend_dir, 'strategies.py')

if os.path.exists(strategies_file):
    # 使用importlib直接加载strategies.py文件
    spec = importlib.util.spec_from_file_location("strategies_module", strategies_file)
    strategies_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(strategies_module)
    
    # 导入所有策略函数
    apply_triple_cross = strategies_module.apply_triple_cross
    apply_pre_cross = strategies_module.apply_pre_cross
    apply_macd_zero_axis_strategy = strategies_module.apply_macd_zero_axis_strategy
    apply_weekly_golden_cross_ma_strategy = strategies_module.apply_weekly_golden_cross_ma_strategy
    apply_triple_cross_legacy = strategies_module.apply_triple_cross_legacy
    apply_pre_cross_legacy = strategies_module.apply_pre_cross_legacy
    apply_macd_zero_axis_strategy_legacy = strategies_module.apply_macd_zero_axis_strategy_legacy
    apply_strategy = strategies_module.apply_strategy
    get_strategy_function = strategies_module.get_strategy_function
    get_strategy_description = strategies_module.get_strategy_description
    list_available_strategies = strategies_module.list_available_strategies
    validate_strategy_config = strategies_module.validate_strategy_config
    
    # 导出所有函数
    __all__ = [
        'apply_triple_cross',
        'apply_pre_cross', 
        'apply_macd_zero_axis_strategy',
        'apply_weekly_golden_cross_ma_strategy',
        'apply_triple_cross_legacy',
        'apply_pre_cross_legacy',
        'apply_macd_zero_axis_strategy_legacy',
        'apply_strategy',
        'get_strategy_function',
        'get_strategy_description',
        'list_available_strategies',
        'validate_strategy_config'
    ]
    
else:
    # 如果strategies.py文件不存在，提供错误函数
    def apply_macd_zero_axis_strategy(*args, **kwargs):
        raise ImportError("strategies.py file not found")
    
    def apply_triple_cross(*args, **kwargs):
        raise ImportError("strategies.py file not found")
    
    def apply_pre_cross(*args, **kwargs):
        raise ImportError("strategies.py file not found")
    
    def apply_weekly_golden_cross_ma_strategy(*args, **kwargs):
        raise ImportError("strategies.py file not found")