"""
股票复权处理模块

重要说明：
  通达信 .day 文件存储的是【不复权原始价格】。
  gbbq 文件中的除权除息字段单位均为每10股：
    hongli  : 每10股红利（元）
    songgu  : 每10股送股数
    peigu   : 每10股配股数
    peigujia: 配股价（元，单价）

  各种复权模式的实现逻辑：
  - 不复权 (none)    : 直接使用文件原始数据，无需处理
  - 前复权 (forward) : 以最新价格为基准，将历史数据乘以累积因子向下调整
  - 后复权 (backward): 以最早价格为基准，将除权日之后的数据除以因子向上调整

复权因子公式（标准通达信）：
  每股红利 = hongli / 10
  每股送股 = songgu / 10
  每股配股 = peigu / 10
  除权价 = (前收盘 - 每股红利 + 配股价 × 每股配股) / (1 + 每股送股 + 每股配股)
  单次因子 = 除权价 / 前收盘
"""

import os
import pandas as pd
import numpy as np
from typing import Optional, Literal
from dataclasses import dataclass


@dataclass
class AdjustmentConfig:
    """复权配置"""
    adjustment_type: Literal['none', 'forward', 'backward'] = 'forward'
    include_dividends: bool = True   # 是否包含现金分红
    include_splits: bool = True      # 是否包含送股/配股
    cache_enabled: bool = True
    gbbq_path: Optional[str] = None  # 自定义 gbbq 路径


class AdjustmentProcessor:
    """复权处理器"""

    def __init__(self, config: Optional[AdjustmentConfig] = None):
        self.config = config or AdjustmentConfig()
        self._cache: dict = {}
        self._gbbq_df: Optional[pd.DataFrame] = None

    # ── 公开接口 ──────────────────────────────────────────────────────────────

    def process_data(self, df: pd.DataFrame, stock_code: str = None) -> pd.DataFrame:
        """
        对日线 DataFrame 进行复权处理。

        Args:
            df        : 日线数据（TDX 文件读取，原始不复权价格），index 为 DatetimeIndex
            stock_code: 股票代码（如 '600519' 或 'sh600519'）

        Returns:
            按 adjustment_type 处理后的 DataFrame
        """
        if df is None or df.empty:
            return df

        # 不复权：文件本身就是原始价格，直接返回
        if self.config.adjustment_type == 'none':
            return df.copy()

        if not stock_code:
            return df.copy()

        cache_key = f"{stock_code}_{self.config.adjustment_type}_{len(df)}"
        if self.config.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key].copy()

        result = self._apply_adjustment(df.copy(), stock_code)

        if self.config.cache_enabled:
            self._cache[cache_key] = result.copy()
        return result

    def clear_cache(self):
        self._cache.clear()
        self._gbbq_df = None

    # ── 内部实现 ──────────────────────────────────────────────────────────────

    def _get_xdxr(self, stock_code: str) -> pd.DataFrame:
        """获取单只股票的除权除息记录"""
        try:
            from gbbq_reader import get_xdxr_for_stock
            xdxr = get_xdxr_for_stock(stock_code, self.config.gbbq_path)
            if not self.config.include_dividends:
                xdxr = xdxr[xdxr['hongli'] == 0]
            if not self.config.include_splits:
                xdxr = xdxr[(xdxr['songgu'] == 0) & (xdxr['peigu'] == 0)]
            return xdxr
        except Exception as e:
            print(f"[AdjustmentProcessor] 加载除权数据失败 {stock_code}: {e}")
            return pd.DataFrame()

    def _apply_adjustment(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """核心复权逻辑"""
        xdxr = self._get_xdxr(stock_code)
        if xdxr.empty:
            return df

        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)

        from gbbq_reader import calc_adjust_factors
        factors = calc_adjust_factors(xdxr, df['close'])
        if not isinstance(factors.index, pd.DatetimeIndex):
            factors.index = pd.to_datetime(factors.index)

        # 只保留数据范围内的除权日
        factors = factors[
            (factors.index >= df.index.min()) &
            (factors.index <= df.index.max())
        ]
        if factors.empty:
            return df

        price_cols = [c for c in ['open', 'high', 'low', 'close'] if c in df.columns]

        if self.config.adjustment_type == 'forward':
            # 前复权：以最新价格为基准，历史数据乘以累积因子向下调整
            return self._forward_adjust(df, factors, price_cols)
        elif self.config.adjustment_type == 'backward':
            # 后复权：以最早价格为基准，除权日之后的数据除以因子向上调整
            return self._backward_adjust(df, factors, price_cols)

        return df

    def _forward_adjust(self, df: pd.DataFrame, factors: pd.Series,
                        price_cols: list) -> pd.DataFrame:
        """
        前复权（向量化）：计算每行的累积因子，一次性乘到价格列上。
        对每个除权日之前的所有行，累积乘以该因子。
        """
        adj = df.copy()
        n = len(adj)
        cum_factor = np.ones(n, dtype=np.float64)

        for ex_date in sorted(factors.index, reverse=True):
            factor = factors[ex_date]
            if factor <= 0 or factor == 1.0:
                continue
            mask = (adj.index < ex_date)
            cum_factor[mask] *= factor

        for col in price_cols:
            adj[col] = adj[col].values * cum_factor
        if 'volume' in adj.columns:
            # 成交量反向调整：价格缩小则量放大
            with np.errstate(divide='ignore', invalid='ignore'):
                vol_factor = np.where(cum_factor != 0, 1.0 / cum_factor, 1.0)
            adj['volume'] = adj['volume'].astype(np.float64).values * vol_factor
        return adj

    def _backward_adjust(self, df: pd.DataFrame, factors: pd.Series,
                         price_cols: list) -> pd.DataFrame:
        """
        后复权（向量化）：计算每行的累积因子，一次性除到价格列上。
        """
        adj = df.copy()
        n = len(adj)
        cum_factor = np.ones(n, dtype=np.float64)

        for ex_date in sorted(factors.index):
            factor = factors[ex_date]
            if factor <= 0 or factor == 1.0:
                continue
            mask = (adj.index >= ex_date)
            cum_factor[mask] /= factor

        for col in price_cols:
            adj[col] = adj[col].values * cum_factor
        if 'volume' in adj.columns:
            with np.errstate(divide='ignore', invalid='ignore'):
                vol_factor = np.where(cum_factor != 0, 1.0 / cum_factor, 1.0)
            adj['volume'] = adj['volume'].astype(np.float64).values * vol_factor
        return adj

    def get_adjustment_info(self, stock_code: str, df: pd.DataFrame) -> dict:
        """返回复权信息摘要"""
        xdxr = self._get_xdxr(stock_code)
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.copy()
            df.index = pd.to_datetime(df.index)
        in_range = xdxr[
            (xdxr['date'] >= df.index.min()) &
            (xdxr['date'] <= df.index.max())
        ] if not xdxr.empty else pd.DataFrame()
        return {
            'adjustment_type': self.config.adjustment_type,
            'note': 'TDX .day files store forward-adjusted prices natively',
            'xdxr_count': len(in_range),
            'xdxr_dates': in_range['date'].dt.strftime('%Y-%m-%d').tolist() if not in_range.empty else [],
        }


# ── 工厂函数 ──────────────────────────────────────────────────────────────────

def create_adjustment_config(adjustment_type: str = 'forward',
                             include_dividends: bool = True,
                             include_splits: bool = True,
                             cache_enabled: bool = True,
                             gbbq_path: str = None) -> AdjustmentConfig:
    return AdjustmentConfig(
        adjustment_type=adjustment_type,
        include_dividends=include_dividends,
        include_splits=include_splits,
        cache_enabled=cache_enabled,
        gbbq_path=gbbq_path,
    )


def create_adjustment_processor(config: Optional[AdjustmentConfig] = None) -> AdjustmentProcessor:
    return AdjustmentProcessor(config)


# ── 便捷函数 ──────────────────────────────────────────────────────────────────

def apply_forward_adjustment(df: pd.DataFrame, stock_code: str = None,
                             gbbq_path: str = None) -> pd.DataFrame:
    """前复权（以最新价格为基准，历史价格向下调整）"""
    return AdjustmentProcessor(
        AdjustmentConfig('forward', gbbq_path=gbbq_path)
    ).process_data(df, stock_code)


def apply_no_adjustment(df: pd.DataFrame, stock_code: str = None,
                        gbbq_path: str = None) -> pd.DataFrame:
    """不复权（TDX文件原始价格，直接返回）"""
    return df.copy() if df is not None else df


def apply_backward_adjustment(df: pd.DataFrame, stock_code: str = None,
                              gbbq_path: str = None) -> pd.DataFrame:
    """后复权（收益率计算用）"""
    return AdjustmentProcessor(
        AdjustmentConfig('backward', gbbq_path=gbbq_path)
    ).process_data(df, stock_code)
