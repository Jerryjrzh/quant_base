"""
股票复权处理模块
支持前复权、后复权和不复权的数据处理
"""

import pandas as pd
import numpy as np
from typing import Optional, Literal, Tuple
from dataclasses import dataclass
from datetime import datetime
import os

@dataclass
class AdjustmentConfig:
    """复权配置"""
    adjustment_type: Literal['none', 'forward', 'backward'] = 'forward'  # 不复权、前复权、后复权
    include_dividends: bool = True  # 是否包含分红调整
    include_splits: bool = True     # 是否包含拆股调整
    cache_enabled: bool = True      # 是否启用缓存
    
class AdjustmentProcessor:
    """复权处理器"""
    
    def __init__(self, config: Optional[AdjustmentConfig] = None):
        self.config = config or AdjustmentConfig()
        self.adjustment_cache = {}
        
    def process_data(self, df: pd.DataFrame, stock_code: str = None) -> pd.DataFrame:
        """
        处理股票数据的复权
        
        Args:
            df: 原始股票数据DataFrame，包含OHLCV列
            stock_code: 股票代码，用于缓存和日志
            
        Returns:
            复权处理后的DataFrame
        """
        if self.config.adjustment_type == 'none':
            return df.copy()
        
        # 检查缓存
        cache_key = f"{stock_code}_{self.config.adjustment_type}" if stock_code else None
        if cache_key and self.config.cache_enabled and cache_key in self.adjustment_cache:
            cached_data = self.adjustment_cache[cache_key]
            if len(cached_data) == len(df):  # 简单的缓存有效性检查
                return cached_data.copy()
        
        # 执行复权处理
        adjusted_df = self._apply_adjustment(df.copy(), stock_code)
        
        # 缓存结果
        if cache_key and self.config.cache_enabled:
            self.adjustment_cache[cache_key] = adjusted_df.copy()
        
        return adjusted_df
    
    def _apply_adjustment(self, df: pd.DataFrame, stock_code: str = None) -> pd.DataFrame:
        """应用复权调整"""
        
        # 尝试加载复权因子数据
        adjustment_factors = self._load_adjustment_factors(stock_code)
        
        if adjustment_factors is None or adjustment_factors.empty:
            # 如果没有复权因子数据，使用简化的复权处理
            return self._apply_simple_adjustment(df)
        
        # 使用复权因子进行精确调整
        return self._apply_factor_adjustment(df, adjustment_factors)
    
    def _load_adjustment_factors(self, stock_code: str) -> Optional[pd.DataFrame]:
        """
        加载复权因子数据
        
        在实际应用中，这里应该从数据源加载真实的复权因子
        目前返回None，使用简化处理
        """
        # TODO: 实现从数据源加载复权因子
        # 复权因子数据格式应该包含：
        # - date: 除权除息日期
        # - split_ratio: 拆股比例
        # - dividend: 分红金额
        # - bonus_ratio: 送股比例
        
        return None
    
    def _apply_simple_adjustment(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        应用简化的复权处理
        
        当没有精确的复权因子数据时，使用价格跳跃检测进行近似复权
        """
        if len(df) < 2:
            return df
        
        # 检测价格跳跃（可能的除权点）
        price_changes = df['close'].pct_change().abs()
        
        # 设定跳跃阈值（超过15%的价格变化可能是除权）
        jump_threshold = 0.15
        jump_points = price_changes > jump_threshold
        
        if not jump_points.any():
            return df  # 没有检测到跳跃，返回原数据
        
        # 应用复权调整
        adjusted_df = df.copy()
        
        if self.config.adjustment_type == 'forward':
            # 前复权：调整除权日之前的数据
            adjusted_df = self._apply_forward_adjustment(adjusted_df, jump_points)
        elif self.config.adjustment_type == 'backward':
            # 后复权：调整除权日之后的数据
            adjusted_df = self._apply_backward_adjustment(adjusted_df, jump_points)
        
        return adjusted_df
    
    def _apply_forward_adjustment(self, df: pd.DataFrame, jump_points: pd.Series) -> pd.DataFrame:
        """应用前复权调整"""
        adjusted_df = df.copy()
        
        # 从最后一个跳跃点开始，向前调整
        jump_indices = jump_points[jump_points].index
        
        for jump_idx in reversed(jump_indices):
            jump_pos = df.index.get_loc(jump_idx)
            if jump_pos == 0:
                continue
                
            # 计算调整因子
            before_price = df.iloc[jump_pos - 1]['close']
            after_price = df.iloc[jump_pos]['close']
            
            if before_price > 0 and after_price > 0:
                adjustment_factor = after_price / before_price
                
                # 调整跳跃点之前的所有数据
                price_columns = ['open', 'high', 'low', 'close']
                for col in price_columns:
                    if col in adjusted_df.columns:
                        adjusted_df.iloc[:jump_pos, adjusted_df.columns.get_loc(col)] *= adjustment_factor
                
                # 调整成交量（反向调整）
                if 'volume' in adjusted_df.columns:
                    volume_col = adjusted_df.columns.get_loc('volume')
                    adjusted_df.iloc[:jump_pos, volume_col] = (
                        adjusted_df.iloc[:jump_pos, volume_col].astype(float) / adjustment_factor
                    ).astype(adjusted_df.dtypes['volume'])
        
        return adjusted_df
    
    def _apply_backward_adjustment(self, df: pd.DataFrame, jump_points: pd.Series) -> pd.DataFrame:
        """应用后复权调整"""
        adjusted_df = df.copy()
        
        # 从第一个跳跃点开始，向后调整
        jump_indices = jump_points[jump_points].index
        
        for jump_idx in jump_indices:
            jump_pos = df.index.get_loc(jump_idx)
            if jump_pos >= len(df) - 1:
                continue
                
            # 计算调整因子
            before_price = df.iloc[jump_pos - 1]['close']
            after_price = df.iloc[jump_pos]['close']
            
            if before_price > 0 and after_price > 0:
                adjustment_factor = before_price / after_price
                
                # 调整跳跃点之后的所有数据
                price_columns = ['open', 'high', 'low', 'close']
                for col in price_columns:
                    if col in adjusted_df.columns:
                        adjusted_df.iloc[jump_pos:, adjusted_df.columns.get_loc(col)] *= adjustment_factor
                
                # 调整成交量（反向调整）
                if 'volume' in adjusted_df.columns:
                    volume_col = adjusted_df.columns.get_loc('volume')
                    adjusted_df.iloc[jump_pos:, volume_col] = (
                        adjusted_df.iloc[jump_pos:, volume_col].astype(float) / adjustment_factor
                    ).astype(adjusted_df.dtypes['volume'])
        
        return adjusted_df
    
    def _apply_factor_adjustment(self, df: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
        """使用精确的复权因子进行调整"""
        # TODO: 实现精确的复权因子调整
        # 这里应该根据复权因子数据进行精确计算
        return df
    
    def get_adjustment_info(self, df_original: pd.DataFrame, df_adjusted: pd.DataFrame) -> dict:
        """获取复权调整信息"""
        if self.config.adjustment_type == 'none':
            return {
                'adjustment_type': 'none',
                'adjustments_applied': 0,
                'price_change_ratio': 1.0,
                'volume_change_ratio': 1.0
            }
        
        # 计算调整统计信息
        original_close = df_original['close'].iloc[-1] if len(df_original) > 0 else 0
        adjusted_close = df_adjusted['close'].iloc[-1] if len(df_adjusted) > 0 else 0
        
        price_ratio = adjusted_close / original_close if original_close > 0 else 1.0
        
        original_volume = df_original['volume'].mean() if 'volume' in df_original.columns else 0
        adjusted_volume = df_adjusted['volume'].mean() if 'volume' in df_adjusted.columns else 0
        
        volume_ratio = adjusted_volume / original_volume if original_volume > 0 else 1.0
        
        return {
            'adjustment_type': self.config.adjustment_type,
            'adjustments_applied': self._count_adjustments(df_original),
            'price_change_ratio': price_ratio,
            'volume_change_ratio': volume_ratio,
            'original_price_range': (df_original['close'].min(), df_original['close'].max()),
            'adjusted_price_range': (df_adjusted['close'].min(), df_adjusted['close'].max())
        }
    
    def _count_adjustments(self, df: pd.DataFrame) -> int:
        """统计可能的调整次数"""
        if len(df) < 2:
            return 0
        
        price_changes = df['close'].pct_change().abs()
        jump_threshold = 0.15
        return (price_changes > jump_threshold).sum()

# 工厂函数
def create_adjustment_config(adjustment_type: str = 'forward', 
                           include_dividends: bool = True,
                           include_splits: bool = True,
                           cache_enabled: bool = True) -> AdjustmentConfig:
    """创建复权配置"""
    return AdjustmentConfig(
        adjustment_type=adjustment_type,
        include_dividends=include_dividends,
        include_splits=include_splits,
        cache_enabled=cache_enabled
    )

def create_adjustment_processor(config: Optional[AdjustmentConfig] = None) -> AdjustmentProcessor:
    """创建复权处理器"""
    return AdjustmentProcessor(config)

# 便捷函数
def apply_forward_adjustment(df: pd.DataFrame, stock_code: str = None) -> pd.DataFrame:
    """应用前复权"""
    config = create_adjustment_config('forward')
    processor = create_adjustment_processor(config)
    return processor.process_data(df, stock_code)

def apply_backward_adjustment(df: pd.DataFrame, stock_code: str = None) -> pd.DataFrame:
    """应用后复权"""
    config = create_adjustment_config('backward')
    processor = create_adjustment_processor(config)
    return processor.process_data(df, stock_code)

def apply_no_adjustment(df: pd.DataFrame, stock_code: str = None) -> pd.DataFrame:
    """不复权处理"""
    config = create_adjustment_config('none')
    processor = create_adjustment_processor(config)
    return processor.process_data(df, stock_code)