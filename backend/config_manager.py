#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一配置管理器
前后端共享的配置加载和管理系统
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class ConfigManager:
    """统一配置管理器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        if config_path is None:
            # 默认配置文件路径
            self.config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                'config', 
                'unified_strategy_config.json'
            )
        else:
            self.config_path = config_path
        
        self.config: Dict[str, Any] = {}
        self.load_config()
        
        logger.info(f"配置管理器初始化完成，配置文件: {self.config_path}")
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                logger.info(f"配置加载成功: {len(self.config.get('strategies', {}))} 个策略")
            else:
                logger.warning(f"配置文件不存在: {self.config_path}")
                self.config = self._get_default_config()
                self.save_config()
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            self.config = self._get_default_config()
    
    def save_config(self):
        """保存配置文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            # 更新时间戳
            self.config['last_updated'] = datetime.now().isoformat()
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            logger.info("配置保存成功")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "version": "2.0",
            "last_updated": datetime.now().isoformat(),
            "strategies": {},
            "global_settings": {
                "max_concurrent_strategies": 5,
                "default_data_length": 500,
                "enable_parallel_processing": True,
                "log_level": "INFO"
            },
            "market_filters": {
                "valid_prefixes": {
                    "sh": ["600", "601", "603", "605", "688"],
                    "sz": ["000", "001", "002", "003", "300"]
                },
                "exclude_st": True,
                "exclude_delisted": True,
                "min_market_cap": 500000000,
                "min_daily_volume": 10000000
            },
            "output_settings": {
                "save_detailed_analysis": True,
                "generate_charts": False,
                "export_formats": ["json", "txt", "csv"],
                "max_signals_per_strategy": 50
            },
            "frontend_settings": {
                "default_timeframe": "daily",
                "default_adjustment": "forward",
                "chart_data_points": 60,
                "auto_refresh_interval": 300000,
                "enable_real_time": False
            }
        }
    
    def get_strategies(self) -> Dict[str, Any]:
        """获取所有策略配置"""
        return self.config.get('strategies', {})
    
    def get_strategy(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """获取单个策略配置"""
        return self.config.get('strategies', {}).get(strategy_id)
    
    def add_strategy(self, strategy_id: str, strategy_config: Dict[str, Any]):
        """添加策略配置"""
        if 'strategies' not in self.config:
            self.config['strategies'] = {}
        
        self.config['strategies'][strategy_id] = strategy_config
        self.save_config()
        logger.info(f"添加策略配置: {strategy_id}")
    
    def update_strategy(self, strategy_id: str, strategy_config: Dict[str, Any]):
        """更新策略配置"""
        if 'strategies' not in self.config:
            self.config['strategies'] = {}
        
        if strategy_id in self.config['strategies']:
            self.config['strategies'][strategy_id].update(strategy_config)
        else:
            self.config['strategies'][strategy_id] = strategy_config
        
        self.save_config()
        logger.info(f"更新策略配置: {strategy_id}")
    
    def remove_strategy(self, strategy_id: str):
        """删除策略配置"""
        if strategy_id in self.config.get('strategies', {}):
            del self.config['strategies'][strategy_id]
            self.save_config()
            logger.info(f"删除策略配置: {strategy_id}")
    
    def enable_strategy(self, strategy_id: str):
        """启用策略"""
        strategy = self.get_strategy(strategy_id)
        if strategy:
            strategy['enabled'] = True
            self.save_config()
            logger.info(f"启用策略: {strategy_id}")
    
    def disable_strategy(self, strategy_id: str):
        """禁用策略"""
        strategy = self.get_strategy(strategy_id)
        if strategy:
            strategy['enabled'] = False
            self.save_config()
            logger.info(f"禁用策略: {strategy_id}")
    
    def get_enabled_strategies(self) -> List[str]:
        """获取已启用的策略ID列表"""
        enabled = []
        for strategy_id, strategy in self.get_strategies().items():
            if strategy.get('enabled', True):
                enabled.append(strategy_id)
        return enabled
    
    def get_global_settings(self) -> Dict[str, Any]:
        """获取全局设置"""
        return self.config.get('global_settings', {})
    
    def update_global_settings(self, settings: Dict[str, Any]):
        """更新全局设置"""
        if 'global_settings' not in self.config:
            self.config['global_settings'] = {}
        
        self.config['global_settings'].update(settings)
        self.save_config()
        logger.info("更新全局设置")
    
    def get_market_filters(self) -> Dict[str, Any]:
        """获取市场过滤器"""
        return self.config.get('market_filters', {})
    
    def get_output_settings(self) -> Dict[str, Any]:
        """获取输出设置"""
        return self.config.get('output_settings', {})
    
    def get_frontend_settings(self) -> Dict[str, Any]:
        """获取前端设置"""
        return self.config.get('frontend_settings', {})
    
    def get_legacy_mapping(self, strategy_id: str) -> Optional[Dict[str, str]]:
        """获取策略的兼容性映射"""
        strategy = self.get_strategy(strategy_id)
        if strategy:
            return strategy.get('legacy_mapping', {})
        return None
    
    def find_strategy_by_old_id(self, old_id: str) -> Optional[str]:
        """通过旧ID查找新策略ID"""
        for strategy_id, strategy in self.get_strategies().items():
            legacy_mapping = strategy.get('legacy_mapping', {})
            if legacy_mapping.get('old_id') == old_id or legacy_mapping.get('api_id') == old_id:
                return strategy_id
        return None
    
    def get_strategy_display_info(self, strategy_id: str) -> Dict[str, Any]:
        """获取策略显示信息"""
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            return {}
        
        return {
            'id': strategy_id,
            'name': strategy.get('name', '未知策略'),
            'version': strategy.get('version', '1.0'),
            'description': strategy.get('description', ''),
            'enabled': strategy.get('enabled', True),
            'risk_level': strategy.get('risk_level', 'medium'),
            'expected_signals_per_day': strategy.get('expected_signals_per_day', '未知'),
            'suitable_market': strategy.get('suitable_market', []),
            'tags': strategy.get('tags', [])
        }
    
    def export_config(self, export_path: str = None) -> str:
        """导出配置文件"""
        if export_path is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            export_path = f"config_backup_{timestamp}.json"
        
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            
            logger.info(f"配置导出成功: {export_path}")
            return export_path
        except Exception as e:
            logger.error(f"配置导出失败: {e}")
            raise
    
    def import_config(self, import_path: str, merge: bool = True):
        """导入配置文件"""
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            if merge:
                # 合并配置
                self._merge_config(imported_config)
            else:
                # 完全替换
                self.config = imported_config
            
            self.save_config()
            logger.info(f"配置导入成功: {import_path}")
        except Exception as e:
            logger.error(f"配置导入失败: {e}")
            raise
    
    def _merge_config(self, imported_config: Dict[str, Any]):
        """合并配置"""
        # 合并策略
        if 'strategies' in imported_config:
            if 'strategies' not in self.config:
                self.config['strategies'] = {}
            self.config['strategies'].update(imported_config['strategies'])
        
        # 合并其他设置
        for key in ['global_settings', 'market_filters', 'output_settings', 'frontend_settings']:
            if key in imported_config:
                if key not in self.config:
                    self.config[key] = {}
                self.config[key].update(imported_config[key])
    
    def validate_config(self) -> List[str]:
        """验证配置文件"""
        errors = []
        
        # 检查必需字段
        required_fields = ['version', 'strategies', 'global_settings']
        for field in required_fields:
            if field not in self.config:
                errors.append(f"缺少必需字段: {field}")
        
        # 检查策略配置
        strategies = self.get_strategies()
        for strategy_id, strategy in strategies.items():
            if not isinstance(strategy, dict):
                errors.append(f"策略配置格式错误: {strategy_id}")
                continue
            
            # 检查策略必需字段
            strategy_required = ['name', 'version', 'config']
            for field in strategy_required:
                if field not in strategy:
                    errors.append(f"策略 {strategy_id} 缺少必需字段: {field}")
        
        return errors
    
    def reload_config(self):
        """重新加载配置"""
        logger.info("重新加载配置...")
        self.load_config()


# 全局配置管理器实例
config_manager = ConfigManager()