"""
策略配置管理模块
支持不同风险等级和市场环境的参数配置
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import json
import os

@dataclass
class MarketEnvironmentConfig:
    """市场环境配置"""
    name: str
    description: str
    volatility_threshold: float  # 波动率阈值
    trend_strength_threshold: float  # 趋势强度阈值
    volume_multiplier: float  # 成交量倍数
    
    # 环境特定的参数调整
    entry_discount_adjustment: float = 0.0  # 入场折扣调整
    stop_loss_adjustment: float = 0.0  # 止损调整
    take_profit_adjustment: float = 0.0  # 止盈调整
    holding_period_adjustment: int = 0  # 持有期调整

@dataclass
class RiskProfileConfig:
    """风险配置文件"""
    name: str
    description: str
    
    # 基础风险参数
    max_position_size: float  # 最大仓位比例
    max_single_loss: float  # 单笔最大亏损
    max_drawdown: float  # 最大回撤
    
    # 入场参数
    pre_entry_discount: float
    mid_entry_premium: float
    post_entry_discount: float
    
    # 出场参数
    stop_loss_pct: float
    take_profit_pct: float
    trailing_stop_pct: float
    
    # 时间参数
    max_holding_days: int
    min_holding_days: int
    
    # 信号过滤参数
    min_signal_strength: float
    require_volume_confirmation: bool

class StrategyConfigManager:
    """策略配置管理器"""
    
    def __init__(self, config_file: str = "backend/strategy_configs.json"):
        self.config_file = config_file
        self.market_environments = {}
        self.risk_profiles = {}
        # 先创建默认配置，再尝试加载
        self._create_default_configs()
        self.load_configs()
    
    def load_configs(self):
        """加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 加载市场环境配置
                for env_data in data.get('market_environments', []):
                    env = MarketEnvironmentConfig(**env_data)
                    self.market_environments[env.name] = env
                
                # 加载风险配置
                for risk_data in data.get('risk_profiles', []):
                    risk = RiskProfileConfig(**risk_data)
                    self.risk_profiles[risk.name] = risk
            else:
                # 创建默认配置
                self._create_default_configs()
                self.save_configs()
                
        except Exception as e:
            print(f"加载配置失败: {e}")
            self._create_default_configs()
    
    def _create_default_configs(self):
        """创建默认配置"""
        # 市场环境配置
        self.market_environments = {
            'bull_market': MarketEnvironmentConfig(
                name='bull_market',
                description='牛市环境 - 趋势向上，波动适中',
                volatility_threshold=0.25,
                trend_strength_threshold=0.1,
                volume_multiplier=1.2,
                entry_discount_adjustment=-0.01,  # 牛市可以少等一点
                stop_loss_adjustment=0.01,  # 止损可以宽松一点
                take_profit_adjustment=0.05,  # 目标可以高一点
                holding_period_adjustment=10  # 可以持有久一点
            ),
            'bear_market': MarketEnvironmentConfig(
                name='bear_market',
                description='熊市环境 - 趋势向下，风险较高',
                volatility_threshold=0.35,
                trend_strength_threshold=-0.1,
                volume_multiplier=0.8,
                entry_discount_adjustment=0.02,  # 熊市要等更大折扣
                stop_loss_adjustment=-0.01,  # 止损要更严格
                take_profit_adjustment=-0.03,  # 目标要保守
                holding_period_adjustment=-10  # 持有期要短
            ),
            'sideways_market': MarketEnvironmentConfig(
                name='sideways_market',
                description='震荡市场 - 无明显趋势',
                volatility_threshold=0.20,
                trend_strength_threshold=0.05,
                volume_multiplier=1.0,
                entry_discount_adjustment=0.0,
                stop_loss_adjustment=0.0,
                take_profit_adjustment=0.0,
                holding_period_adjustment=0
            ),
            'high_volatility': MarketEnvironmentConfig(
                name='high_volatility',
                description='高波动环境 - 价格波动剧烈',
                volatility_threshold=0.40,
                trend_strength_threshold=0.15,
                volume_multiplier=1.5,
                entry_discount_adjustment=0.01,
                stop_loss_adjustment=-0.02,  # 更严格的止损
                take_profit_adjustment=0.03,  # 更高的目标
                holding_period_adjustment=-5  # 更短的持有期
            )
        }
        
        # 风险配置文件
        self.risk_profiles = {
            'conservative': RiskProfileConfig(
                name='conservative',
                description='保守型 - 低风险低收益',
                max_position_size=0.20,
                max_single_loss=0.02,
                max_drawdown=0.05,
                pre_entry_discount=0.03,
                mid_entry_premium=0.005,
                post_entry_discount=0.06,
                stop_loss_pct=0.03,
                take_profit_pct=0.08,
                trailing_stop_pct=0.02,
                max_holding_days=20,
                min_holding_days=3,
                min_signal_strength=0.7,
                require_volume_confirmation=True
            ),
            'moderate': RiskProfileConfig(
                name='moderate',
                description='稳健型 - 平衡风险收益',
                max_position_size=0.40,
                max_single_loss=0.04,
                max_drawdown=0.10,
                pre_entry_discount=0.02,
                mid_entry_premium=0.01,
                post_entry_discount=0.05,
                stop_loss_pct=0.05,
                take_profit_pct=0.12,
                trailing_stop_pct=0.03,
                max_holding_days=30,
                min_holding_days=2,
                min_signal_strength=0.5,
                require_volume_confirmation=True
            ),
            'aggressive': RiskProfileConfig(
                name='aggressive',
                description='激进型 - 高风险高收益',
                max_position_size=0.60,
                max_single_loss=0.08,
                max_drawdown=0.20,
                pre_entry_discount=0.015,
                mid_entry_premium=0.015,
                post_entry_discount=0.04,
                stop_loss_pct=0.08,
                take_profit_pct=0.20,
                trailing_stop_pct=0.05,
                max_holding_days=45,
                min_holding_days=1,
                min_signal_strength=0.3,
                require_volume_confirmation=False
            ),
            'scalping': RiskProfileConfig(
                name='scalping',
                description='短线型 - 快进快出',
                max_position_size=0.30,
                max_single_loss=0.02,
                max_drawdown=0.08,
                pre_entry_discount=0.01,
                mid_entry_premium=0.02,
                post_entry_discount=0.03,
                stop_loss_pct=0.03,
                take_profit_pct=0.06,
                trailing_stop_pct=0.015,
                max_holding_days=5,
                min_holding_days=1,
                min_signal_strength=0.4,
                require_volume_confirmation=True
            )
        }
    
    def save_configs(self):
        """保存配置"""
        try:
            data = {
                'market_environments': [asdict(env) for env in self.market_environments.values()],
                'risk_profiles': [asdict(profile) for profile in self.risk_profiles.values()]
            }
            
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def get_market_environment(self, name: str) -> Optional[MarketEnvironmentConfig]:
        """获取市场环境配置"""
        return self.market_environments.get(name)
    
    def get_risk_profile(self, name: str) -> Optional[RiskProfileConfig]:
        """获取风险配置"""
        return self.risk_profiles.get(name)
    
    def detect_market_environment(self, df, lookback_days: int = 60) -> str:
        """自动检测市场环境"""
        try:
            if len(df) < lookback_days:
                return 'sideways_market'
            
            recent_data = df.tail(lookback_days)
            
            # 计算趋势强度
            price_change = (recent_data['close'].iloc[-1] - recent_data['close'].iloc[0]) / recent_data['close'].iloc[0]
            
            # 计算波动率
            returns = recent_data['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)
            
            # 计算成交量变化（如果有成交量数据）
            volume_ratio = 1.0
            if 'volume' in recent_data.columns:
                recent_volume = recent_data['volume'].tail(10).mean()
                historical_volume = recent_data['volume'].head(lookback_days-10).mean()
                volume_ratio = recent_volume / historical_volume if historical_volume > 0 else 1.0
            
            # 环境判断逻辑
            if volatility > 0.35:
                return 'high_volatility'
            elif price_change > 0.15:
                return 'bull_market'
            elif price_change < -0.15:
                return 'bear_market'
            else:
                return 'sideways_market'
                
        except Exception as e:
            print(f"检测市场环境失败: {e}")
            return 'sideways_market'
    
    def get_adaptive_config(self, df, base_risk_profile: str = 'moderate') -> Dict:
        """获取自适应配置"""
        try:
            # 检测市场环境
            market_env_name = self.detect_market_environment(df)
            market_env = self.get_market_environment(market_env_name)
            
            # 获取基础风险配置
            risk_profile = self.get_risk_profile(base_risk_profile)
            
            if not market_env or not risk_profile:
                return {}
            
            # 根据市场环境调整参数
            adaptive_config = {
                'market_environment': market_env_name,
                'risk_profile': base_risk_profile,
                'parameters': {
                    'pre_entry_discount': max(0.005, risk_profile.pre_entry_discount + market_env.entry_discount_adjustment),
                    'mid_entry_premium': max(0.001, risk_profile.mid_entry_premium),
                    'post_entry_discount': max(0.01, risk_profile.post_entry_discount + market_env.entry_discount_adjustment),
                    'stop_loss_pct': max(0.01, risk_profile.stop_loss_pct + market_env.stop_loss_adjustment),
                    'take_profit_pct': max(0.03, risk_profile.take_profit_pct + market_env.take_profit_adjustment),
                    'max_holding_days': max(1, risk_profile.max_holding_days + market_env.holding_period_adjustment),
                    'max_position_size': risk_profile.max_position_size,
                    'min_signal_strength': risk_profile.min_signal_strength,
                    'require_volume_confirmation': risk_profile.require_volume_confirmation
                }
            }
            
            return adaptive_config
            
        except Exception as e:
            print(f"获取自适应配置失败: {e}")
            return {}
    
    def list_available_configs(self):
        """列出可用配置"""
        print("📋 可用的市场环境配置:")
        for name, env in self.market_environments.items():
            print(f"  {name}: {env.description}")
        
        print("\n📋 可用的风险配置:")
        for name, profile in self.risk_profiles.items():
            print(f"  {name}: {profile.description}")
    
    def create_custom_risk_profile(self, name: str, description: str, **kwargs):
        """创建自定义风险配置"""
        try:
            # 使用moderate作为基础模板
            base_profile = self.risk_profiles['moderate']
            
            # 更新参数
            profile_dict = asdict(base_profile)
            profile_dict['name'] = name
            profile_dict['description'] = description
            profile_dict.update(kwargs)
            
            # 创建新配置
            new_profile = RiskProfileConfig(**profile_dict)
            self.risk_profiles[name] = new_profile
            
            # 保存配置
            self.save_configs()
            
            print(f"✅ 创建自定义风险配置: {name}")
            return new_profile
            
        except Exception as e:
            print(f"创建自定义配置失败: {e}")
            return None

# 导入numpy用于计算
import numpy as np

# 全局配置管理器实例
_config_manager = None

def get_config_manager():
    """获取配置管理器实例"""
    global _config_manager
    if _config_manager is None:
        _config_manager = StrategyConfigManager()
    return _config_manager

def get_strategy_config(strategy_name: str):
    """获取策略配置（兼容性函数）"""
    # 这是一个兼容性函数，用于支持旧的代码
    # 返回一个简单的配置对象
    class DefaultConfig:
        def __init__(self):
            # RSI配置
            class RSIConfig:
                def __init__(self):
                    self.period_short = 6
                    self.period_long = 14
                    self.period_extra = 21
                    self.oversold = 30
                    self.overbought = 70
            
            # MACD配置
            class MACDConfig:
                def __init__(self):
                    self.fast_period = 12
                    self.slow_period = 26
                    self.signal_period = 9
            
            # KDJ配置
            class KDJConfig:
                def __init__(self):
                    self.period = 9
                    self.k_period = 3
                    self.d_period = 3
                    self.oversold = 20
                    self.overbought = 80
            
            self.rsi = RSIConfig()
            self.macd = MACDConfig()
            self.kdj = KDJConfig()
            
            # 策略特定参数
            self.pre_cross_days = 5
            self.post_cross_days = 3
            self.volume_threshold = 1.5
            self.price_change_threshold = 0.02
    
    return DefaultConfig()

def update_strategy_config(strategy_name: str, config_dict: dict):
    """更新策略配置（兼容性函数）"""
    # 这是一个兼容性函数，暂时不实现具体功能
    print(f"更新策略配置: {strategy_name}")
    return True

def validate_strategy_config(config):
    """验证策略配置（兼容性函数）"""
    # 这是一个兼容性函数，暂时返回True
    return True

def list_available_strategies():
    """列出可用策略（兼容性函数）"""
    return ['TRIPLE_CROSS', 'PRE_CROSS', 'MACD_ZERO_AXIS']

# 兼容性变量和函数
config_manager = get_config_manager()

def config_debugger(message: str):
    """配置调试器（兼容性函数）"""
    print(f"[CONFIG DEBUG] {message}")