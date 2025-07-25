"""
多周期分析系统配置模块
提供系统配置管理和参数调整功能
"""

import json
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

class MultiTimeframeConfig:
    """多周期分析系统配置管理器"""
    
    def __init__(self, config_file: str = "multi_timeframe_config.json"):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.config = self._load_default_config()
        
        # 如果配置文件存在，加载用户配置
        if self.config_file.exists():
            self._load_config()
        else:
            self._save_config()
    
    def _load_default_config(self) -> Dict[str, Any]:
        """加载默认配置"""
        return {
            "system": {
                "version": "1.0.0",
                "last_updated": datetime.now().isoformat(),
                "debug_mode": False,
                "log_level": "INFO"
            },
            
            "timeframes": {
                "5min": {
                    "enabled": True,
                    "weight": 0.03,
                    "min_data_points": 100,
                    "color": "#FF6B6B",
                    "label": "5min"
                },
                "15min": {
                    "enabled": True,
                    "weight": 0.05,
                    "min_data_points": 100,
                    "color": "#4ECDC4",
                    "label": "15min"
                },
                "30min": {
                    "enabled": True,
                    "weight": 0.12,
                    "min_data_points": 100,
                    "color": "#45B7D1",
                    "label": "30min"
                },
                "1hour": {
                    "enabled": True,
                    "weight": 0.20,
                    "min_data_points": 100,
                    "color": "#96CEB4",
                    "label": "1hour"
                },
                "4hour": {
                    "enabled": True,
                    "weight": 0.25,
                    "min_data_points": 50,
                    "color": "#FFEAA7",
                    "label": "4hour"
                },
                "1day": {
                    "enabled": True,
                    "weight": 0.25,
                    "min_data_points": 30,
                    "color": "#DDA0DD",
                    "label": "1day"
                },
                "1week": {
                    "enabled": True,
                    "weight": 0.40,
                    "min_data_points": 10,
                    "color": "#FF8C00",
                    "label": "1week"
                }
            },
            
            "strategies": {
                "trend_following": {
                    "enabled": True,
                    "weight": 0.30,
                    "parameters": {
                        "ma_short": 10,
                        "ma_long": 30,
                        "trend_threshold": 0.02
                    }
                },
                "reversal_catching": {
                    "enabled": True,
                    "weight": 0.25,
                    "parameters": {
                        "rsi_oversold": 30,
                        "rsi_overbought": 70,
                        "reversal_confirmation": 2
                    }
                },
                "breakout": {
                    "enabled": True,
                    "weight": 0.25,
                    "parameters": {
                        "breakout_threshold": 0.03,
                        "volume_multiplier": 1.5,
                        "confirmation_periods": 3
                    }
                },
                "momentum": {
                    "enabled": True,
                    "weight": 0.20,
                    "parameters": {
                        "momentum_period": 14,
                        "momentum_threshold": 0.05,
                        "acceleration_factor": 0.02
                    }
                }
            },
            
            "signal_processing": {
                "confidence_threshold": 0.6,
                "signal_decay_factor": 0.95,
                "max_signal_age_hours": 24,
                "signal_aggregation_method": "weighted_average",
                "noise_filter_enabled": True,
                "noise_threshold": 0.1
            },
            
            "risk_management": {
                "max_position_size": 0.1,
                "stop_loss_percentage": 0.05,
                "take_profit_percentage": 0.15,
                "risk_free_rate": 0.03,
                "max_drawdown_threshold": 0.15,
                "correlation_threshold": 0.7
            },
            
            "monitoring": {
                "update_interval_seconds": 300,
                "alert_cooldown_minutes": 30,
                "max_alerts_per_hour": 10,
                "alert_types": {
                    "signal_convergence": True,
                    "trend_change": True,
                    "breakout": True,
                    "risk_level_change": True
                }
            },
            
            "backtesting": {
                "initial_capital": 100000,
                "commission_rate": 0.001,
                "slippage_rate": 0.0005,
                "benchmark": "market_index",
                "rebalance_frequency": "daily"
            },
            
            "visualization": {
                "chart_width": 16,
                "chart_height": 10,
                "dpi": 300,
                "color_scheme": "default",
                "show_grid": True,
                "grid_alpha": 0.3
            },
            
            "data_quality": {
                "min_data_completeness": 0.8,
                "outlier_detection_enabled": True,
                "outlier_threshold": 3.0,
                "data_validation_enabled": True
            }
        }
    
    def _load_config(self):
        """从文件加载配置"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
            
            # 递归合并配置
            self.config = self._merge_configs(self.config, user_config)
            
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            print("使用默认配置")
    
    def _save_config(self):
        """保存配置到文件"""
        try:
            # 更新时间戳
            self.config['system']['last_updated'] = datetime.now().isoformat()
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def _merge_configs(self, default: Dict, user: Dict) -> Dict:
        """递归合并配置"""
        result = default.copy()
        
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def get(self, key_path: str, default=None):
        """
        获取配置值
        
        Args:
            key_path: 配置键路径，如 'timeframes.5min.weight'
            default: 默认值
            
        Returns:
            配置值
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key_path: str, value: Any):
        """
        设置配置值
        
        Args:
            key_path: 配置键路径
            value: 配置值
        """
        keys = key_path.split('.')
        config = self.config
        
        # 导航到父级配置
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # 设置值
        config[keys[-1]] = value
        
        # 保存配置
        self._save_config()
    
    def get_enabled_timeframes(self) -> List[str]:
        """获取启用的时间周期列表"""
        enabled_timeframes = []
        
        for timeframe, config in self.config['timeframes'].items():
            if config.get('enabled', True):
                enabled_timeframes.append(timeframe)
        
        return enabled_timeframes
    
    def get_timeframe_weights(self) -> Dict[str, float]:
        """获取时间周期权重"""
        weights = {}
        
        for timeframe, config in self.config['timeframes'].items():
            if config.get('enabled', True):
                weights[timeframe] = config.get('weight', 0.0)
        
        return weights
    
    def get_enabled_strategies(self) -> List[str]:
        """获取启用的策略列表"""
        enabled_strategies = []
        
        for strategy, config in self.config['strategies'].items():
            if config.get('enabled', True):
                enabled_strategies.append(strategy)
        
        return enabled_strategies
    
    def get_strategy_weights(self) -> Dict[str, float]:
        """获取策略权重"""
        weights = {}
        
        for strategy, config in self.config['strategies'].items():
            if config.get('enabled', True):
                weights[strategy] = config.get('weight', 0.0)
        
        return weights
    
    def get_strategy_parameters(self, strategy: str) -> Dict[str, Any]:
        """获取策略参数"""
        return self.config['strategies'].get(strategy, {}).get('parameters', {})
    
    def update_timeframe_weight(self, timeframe: str, weight: float):
        """更新时间周期权重"""
        self.set(f'timeframes.{timeframe}.weight', weight)
    
    def update_strategy_weight(self, strategy: str, weight: float):
        """更新策略权重"""
        self.set(f'strategies.{strategy}.weight', weight)
    
    def enable_timeframe(self, timeframe: str):
        """启用时间周期"""
        self.set(f'timeframes.{timeframe}.enabled', True)
    
    def disable_timeframe(self, timeframe: str):
        """禁用时间周期"""
        self.set(f'timeframes.{timeframe}.enabled', False)
    
    def enable_strategy(self, strategy: str):
        """启用策略"""
        self.set(f'strategies.{strategy}.enabled', True)
    
    def disable_strategy(self, strategy: str):
        """禁用策略"""
        self.set(f'strategies.{strategy}.enabled', False)
    
    def reset_to_defaults(self):
        """重置为默认配置"""
        self.config = self._load_default_config()
        self._save_config()
    
    def export_config(self, export_path: str):
        """导出配置到指定路径"""
        try:
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            print(f"配置已导出到: {export_path}")
        except Exception as e:
            print(f"导出配置失败: {e}")
    
    def import_config(self, import_path: str):
        """从指定路径导入配置"""
        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            self.config = self._merge_configs(self.config, imported_config)
            self._save_config()
            print(f"配置已从 {import_path} 导入")
        except Exception as e:
            print(f"导入配置失败: {e}")
    
    def validate_config(self) -> List[str]:
        """验证配置有效性"""
        errors = []
        
        # 验证时间周期权重总和
        total_timeframe_weight = sum(
            config.get('weight', 0) 
            for config in self.config['timeframes'].values() 
            if config.get('enabled', True)
        )
        
        if abs(total_timeframe_weight - 1.0) > 0.01:
            errors.append(f"时间周期权重总和应为1.0，当前为{total_timeframe_weight:.3f}")
        
        # 验证策略权重总和
        total_strategy_weight = sum(
            config.get('weight', 0) 
            for config in self.config['strategies'].values() 
            if config.get('enabled', True)
        )
        
        if abs(total_strategy_weight - 1.0) > 0.01:
            errors.append(f"策略权重总和应为1.0，当前为{total_strategy_weight:.3f}")
        
        # 验证风险管理参数
        risk_config = self.config.get('risk_management', {})
        max_position = risk_config.get('max_position_size', 0)
        if max_position <= 0 or max_position > 1:
            errors.append("最大仓位大小应在0-1之间")
        
        stop_loss = risk_config.get('stop_loss_percentage', 0)
        if stop_loss <= 0 or stop_loss > 0.5:
            errors.append("止损百分比应在0-0.5之间")
        
        return errors
    
    def get_config_summary(self) -> Dict[str, Any]:
        """获取配置摘要"""
        enabled_timeframes = self.get_enabled_timeframes()
        enabled_strategies = self.get_enabled_strategies()
        
        return {
            "system_version": self.config['system']['version'],
            "last_updated": self.config['system']['last_updated'],
            "enabled_timeframes": len(enabled_timeframes),
            "enabled_strategies": len(enabled_strategies),
            "timeframe_list": enabled_timeframes,
            "strategy_list": enabled_strategies,
            "confidence_threshold": self.config['signal_processing']['confidence_threshold'],
            "max_position_size": self.config['risk_management']['max_position_size'],
            "update_interval": self.config['monitoring']['update_interval_seconds'],
            "config_valid": len(self.validate_config()) == 0
        }

# 全局配置实例
multi_timeframe_config = MultiTimeframeConfig()