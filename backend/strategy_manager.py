#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略管理器
负责动态加载和管理所有策略
"""

import os
import json
import importlib
import importlib.util
import logging
import pandas as pd
from typing import Dict, List, Any, Optional, Type
from pathlib import Path

from strategies.base_strategy import BaseStrategy
from config_manager import config_manager

logger = logging.getLogger(__name__)


class StrategyManager:
    """策略管理器"""
    
    def __init__(self, strategies_dir: str = None):
        """
        初始化策略管理器
        
        Args:
            strategies_dir: 策略目录路径
        """
        self.strategies_dir = strategies_dir or os.path.join(os.path.dirname(__file__), 'strategies')
        
        # 使用统一配置管理器
        self.config_manager = config_manager
        
        # 已注册的策略
        self.registered_strategies: Dict[str, Type[BaseStrategy]] = {}
        self.strategy_instances: Dict[str, BaseStrategy] = {}
        
        # 自动发现和注册策略
        self.discover_strategies()
        
        #logger.info(f"策略管理器初始化完成，发现 {len(self.registered_strategies)} 个策略")
    
    @property
    def strategy_configs(self):
        """获取策略配置（从统一配置管理器）"""
        return self.config_manager.get_strategies()
    
    def save_strategies_config(self):
        """保存策略配置（通过统一配置管理器）"""
        self.config_manager.save_config()
    
    def discover_strategies(self):
        """自动发现策略目录中的策略"""
        try:
            strategies_path = Path(self.strategies_dir)
            if not strategies_path.exists():
                logger.warning(f"策略目录不存在: {self.strategies_dir}")
                return
            
            # 遍历策略文件
            for strategy_file in strategies_path.glob('*_strategy.py'):
                if strategy_file.name == 'base_strategy.py':
                    continue
                
                try:
                    self._load_strategy_from_file(strategy_file)
                except Exception as e:
                    logger.error(f"加载策略文件失败 {strategy_file}: {e}")
                    
        except Exception as e:
            logger.error(f"策略发现失败: {e}")
    
    def _load_strategy_from_file(self, strategy_file: Path):
        """从文件加载策略"""
        try:
            # 构建模块名（不使用backend前缀避免导入冲突）
            module_name = f"strategies.{strategy_file.stem}"
            
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(module_name, strategy_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 查找策略类
            found_strategy = False
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    hasattr(attr, '__bases__') and
                    any(base.__name__ == 'BaseStrategy' for base in attr.__bases__) and
                    attr.__name__ != 'BaseStrategy'):
                    
                    try:
                        # 创建临时实例获取策略ID
                        temp_instance = attr()
                        # 使用与配置文件一致的ID格式
                        strategy_id = f"{temp_instance.name}_v{temp_instance.version}"
                        
                        # 注册策略
                        self.registered_strategies[strategy_id] = attr
                        
                        #logger.info(f"发现策略: {strategy_id} ({attr.__name__})")
                        found_strategy = True
                        break
                    except Exception as e:
                        logger.error(f"创建策略实例失败 {attr.__name__}: {e}")
            
            if not found_strategy:
                logger.warning(f"在文件 {strategy_file} 中未找到策略类")
                    
        except Exception as e:
            logger.error(f"加载策略文件失败 {strategy_file}: {e}")
    
    def _generate_strategy_id(self, strategy_class: Type[BaseStrategy]) -> str:
        """生成策略ID"""
        try:
            # 创建临时实例获取策略信息
            temp_instance = strategy_class()
            strategy_id = f"{temp_instance.name.replace(' ', '_').lower()}_v{temp_instance.version}"
            return strategy_id
        except Exception as e:
            logger.error(f"生成策略ID失败: {e}")
            return strategy_class.__name__.lower()
    
    def register_strategy(self, strategy_id: str, strategy_class: Type[BaseStrategy], config: Dict[str, Any] = None):
        """手动注册策略"""
        try:
            self.registered_strategies[strategy_id] = strategy_class
            if config:
                self.strategy_configs[strategy_id] = config
            
            logger.info(f"手动注册策略: {strategy_id}")
        except Exception as e:
            logger.error(f"注册策略失败 {strategy_id}: {e}")
    
    def get_strategy_instance(self, strategy_id: str) -> Optional[BaseStrategy]:
        """获取策略实例"""
        try:
            if strategy_id not in self.strategy_instances:
                if strategy_id not in self.registered_strategies:
                    logger.error(f"策略未注册: {strategy_id}")
                    return None
                
                # 创建策略实例
                strategy_class = self.registered_strategies[strategy_id]
                strategy_config = self.config_manager.get_strategy(strategy_id)
                config = strategy_config.get('config', {}) if strategy_config else {}
                
                self.strategy_instances[strategy_id] = strategy_class(config)
                #logger.info(f"创建策略实例: {strategy_id}")
            
            return self.strategy_instances[strategy_id]
            
        except Exception as e:
            logger.error(f"获取策略实例失败 {strategy_id}: {e}")
            return None
    
    def get_available_strategies(self) -> List[Dict[str, Any]]:
        """获取可用策略列表"""
        strategies = []
        
        # 首先从统一配置中获取所有策略
        config_strategies = self.config_manager.get_strategies()
        
        for strategy_id, strategy_config in config_strategies.items():
            try:
                # 如果策略类已注册，获取详细信息
                if strategy_id in self.registered_strategies:
                    strategy_class = self.registered_strategies[strategy_id]
                    temp_instance = strategy_class()
                    
                    strategy_info = {
                        'id': strategy_id,
                        'name': temp_instance.name,
                        'version': temp_instance.version,
                        'description': temp_instance.description,
                        'required_data_length': temp_instance.get_required_data_length(),
                        'config': strategy_config.get('config', {}),
                        'enabled': strategy_config.get('enabled', True),
                        'risk_level': strategy_config.get('risk_level', 'medium'),
                        'expected_signals_per_day': strategy_config.get('expected_signals_per_day', '未知'),
                        'suitable_market': strategy_config.get('suitable_market', []),
                        'tags': strategy_config.get('tags', [])
                    }
                else:
                    # 如果策略类未注册，使用配置中的信息
                    strategy_info = {
                        'id': strategy_id,
                        'name': strategy_config.get('name', '未知策略'),
                        'version': strategy_config.get('version', '1.0'),
                        'description': strategy_config.get('description', ''),
                        'required_data_length': 500,  # 默认值
                        'config': strategy_config.get('config', {}),
                        'enabled': strategy_config.get('enabled', True),
                        'risk_level': strategy_config.get('risk_level', 'medium'),
                        'expected_signals_per_day': strategy_config.get('expected_signals_per_day', '未知'),
                        'suitable_market': strategy_config.get('suitable_market', []),
                        'tags': strategy_config.get('tags', [])
                    }
                
                strategies.append(strategy_info)
                
            except Exception as e:
                logger.error(f"获取策略信息失败 {strategy_id}: {e}")
        
        return strategies
    
    def enable_strategy(self, strategy_id: str):
        """启用策略"""
        self.config_manager.enable_strategy(strategy_id)
        logger.info(f"启用策略: {strategy_id}")
    
    def disable_strategy(self, strategy_id: str):
        """禁用策略"""
        self.config_manager.disable_strategy(strategy_id)
        logger.info(f"禁用策略: {strategy_id}")
    
    def update_strategy_config(self, strategy_id: str, config: Dict[str, Any]):
        """更新策略配置"""
        self.config_manager.update_strategy(strategy_id, config)
        
        # 如果策略实例已存在，需要重新创建
        if strategy_id in self.strategy_instances:
            del self.strategy_instances[strategy_id]
        
        logger.info(f"更新策略配置: {strategy_id}")
    
    def get_enabled_strategies(self) -> List[str]:
        """获取已启用的策略ID列表"""
        return self.config_manager.get_enabled_strategies()
    
    def reload_strategies(self):
        """重新加载所有策略"""
        logger.info("重新加载策略...")
        
        # 清空现有策略
        self.registered_strategies.clear()
        self.strategy_instances.clear()
        
        # 重新发现策略
        self.discover_strategies()
        
        logger.info(f"策略重新加载完成，发现 {len(self.registered_strategies)} 个策略")


# 全局策略管理器实例
strategy_manager = StrategyManager()
