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
        
        # 注册配置文件中的策略
        self._register_config_strategies()
    
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
            
            # 注册完成后，确保配置文件中的策略都有对应的实现
            self._ensure_config_strategy_mapping()
                    
        except Exception as e:
            logger.error(f"策略发现失败: {e}")
    
    def _ensure_config_strategy_mapping(self):
        """确保配置文件中的策略都有对应的注册策略"""
        config_strategies = self.config_manager.get_strategies()
        
        for config_id in config_strategies.keys():
            if config_id not in self.registered_strategies:
                # 尝试找到匹配的注册策略
                matched_id = None
                config_name = config_strategies[config_id].get('name', '')
                
                for registered_id, strategy_class in self.registered_strategies.items():
                    try:
                        temp_instance = strategy_class()
                        if temp_instance.name == config_name:
                            matched_id = registered_id
                            break
                    except:
                        continue
                
                if matched_id:
                    # 创建别名映射
                    self.registered_strategies[config_id] = self.registered_strategies[matched_id]
                    logger.info(f"创建策略别名映射: {config_id} -> {matched_id}")
                else:
                    logger.warning(f"配置中的策略未找到对应实现: {config_id}")
    
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
                        
                        # 同时注册英文名称作为别名（向后兼容）
                        english_name = self._get_english_name(temp_instance.name)
                        if english_name != temp_instance.name:
                            english_id = f"{english_name}_v{temp_instance.version}"
                            self.registered_strategies[english_id] = attr
                        
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
    
    def _get_english_name(self, chinese_name: str) -> str:
        """获取策略的英文名称（用于向后兼容）"""
        name_mapping = {
            "深渊筑底策略": "ABYSS_BOTTOMING",
            "临界金叉": "PRE_CROSS", 
            "三重金叉": "TRIPLE_CROSS",
            "MACD零轴启动": "MACD_ZERO_AXIS",
            "周线金叉+日线MA": "WEEKLY_GOLDEN_CROSS_MA"
        }
        return name_mapping.get(chinese_name, chinese_name)
    
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
                    # 尝试查找别名或相似的策略ID
                    alternative_id = self._find_alternative_strategy_id(strategy_id)
                    if alternative_id:
                        #logger.warning(f"策略ID {strategy_id} 未找到，使用替代ID: {alternative_id}")
                        strategy_id = alternative_id
                    else:
                        logger.error(f"策略未注册: {strategy_id}")
                        logger.error(f"可用策略: {list(self.registered_strategies.keys())}")
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
    
    def _find_alternative_strategy_id(self, strategy_id: str) -> Optional[str]:
        """查找替代的策略ID"""
        # 检查是否有完全匹配的策略
        for registered_id in self.registered_strategies.keys():
            if registered_id == strategy_id:
                return registered_id
        
        # 检查是否有部分匹配的策略
        for registered_id in self.registered_strategies.keys():
            if strategy_id in registered_id or registered_id in strategy_id:
                return registered_id
        
        # 检查英文名称映射
        name_mapping = {
            "深渊筑底策略": "ABYSS_BOTTOMING",
            "临界金叉": "PRE_CROSS", 
            "三重金叉": "TRIPLE_CROSS",
            "MACD零轴启动": "MACD_ZERO_AXIS",
            "周线金叉+日线MA": "WEEKLY_GOLDEN_CROSS_MA"
        }
        
        for chinese_name, english_name in name_mapping.items():
            if chinese_name in strategy_id:
                # 尝试查找对应的英文策略ID
                for registered_id in self.registered_strategies.keys():
                    if english_name in registered_id:
                        return registered_id
        
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



    def _register_config_strategies(self):
        """注册配置文件中的策略"""
        try:
            config_strategies = self.config_manager.get_strategies()
            
            for config_id, config_data in config_strategies.items():
                if config_id not in self.registered_strategies:
                    # 尝试根据名称找到对应的策略类
                    strategy_name = config_data.get('name', '')
                    
                    # 查找匹配的策略类
                    for registered_id, strategy_class in list(self.registered_strategies.items()):
                        try:
                            temp_instance = strategy_class()
                            if temp_instance.name == strategy_name:
                                # 注册配置ID作为别名
                                self.registered_strategies[config_id] = strategy_class
                                logger.info(f"注册策略别名: {config_id} -> {registered_id}")
                                break
                        except Exception as e:
                            continue
                            
        except Exception as e:
            logger.error(f"注册配置策略失败: {e}")

# 全局策略管理器实例
strategy_manager = StrategyManager()
