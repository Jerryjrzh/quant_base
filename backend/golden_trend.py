"""
金钻趋势 (Golden Trend) 指标计算模块

公式: GT = (EMA_L - (EMA_H - EMA_L) * K) * offset
双轨: EMA_H (上轨), EMA_L (下轨基准)
自适应参数: 基于历史 ATR/趋势/回撤动态计算 N/K/offset

遵循 indicators.py 的 dataclass config + 函数模式。
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Tuple, Optional, Dict

try:
    from .indicators import IndicatorConfig
except ImportError:
    from indicators import IndicatorConfig


@dataclass
class GoldenTrendConfig(IndicatorConfig):
    n: int = 25
    double_smooth: bool = True
    k: float = 1.0
    offset_coef: float = 1.0
    adaptive: bool = True


def calc_golden_trend(high: pd.Series, low: pd.Series,
                       n: int, double_smooth: bool, k: float,
                       offset_coef: float) -> pd.Series:
    if double_smooth:
        ema_h = high.ewm(span=n, adjust=False).mean().ewm(span=n, adjust=False).mean()
        ema_l = low.ewm(span=n, adjust=False).mean().ewm(span=n, adjust=False).mean()
    else:
        ema_h = high.ewm(span=n, adjust=False).mean()
        ema_l = low.ewm(span=n, adjust=False).mean()
    channel_width = (ema_h - ema_l) * k
    golden = ema_l - channel_width
    if offset_coef != 1.0:
        golden = golden * offset_coef
    return golden


def calc_ema_rails(high: pd.Series, low: pd.Series,
                   n: int, double_smooth: bool
                   ) -> Tuple[pd.Series, pd.Series]:
    if double_smooth:
        ema_h = high.ewm(span=n, adjust=False).mean().ewm(span=n, adjust=False).mean()
        ema_l = low.ewm(span=n, adjust=False).mean().ewm(span=n, adjust=False).mean()
    else:
        ema_h = high.ewm(span=n, adjust=False).mean()
        ema_l = low.ewm(span=n, adjust=False).mean()
    return ema_h, ema_l


def calc_adaptive_n(df: pd.DataFrame) -> int:
    """波动越大→N越大(平滑), 趋势越强→N越小(灵敏)"""
    n_bars = min(20, len(df) - 1)
    if n_bars < 5:
        return 20

    hl = df['high'] - df['low']
    hc = np.abs(df['high'] - df['close'].shift(1))
    lc = np.abs(df['low'] - df['close'].shift(1))
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    atr_pct = float((tr / df['close']).iloc[-n_bars:].mean())

    close_tail = df['close'].iloc[-50:].values if len(df) >= 50 else df['close'].values
    x = np.arange(len(close_tail), dtype=float)
    if len(x) > 2:
        try:
            coeffs = np.polyfit(x, close_tail, 1)
            y_fit = np.polyval(coeffs, x)
            ss_res = np.sum((close_tail - y_fit) ** 2)
            ss_tot = np.sum((close_tail - close_tail.mean()) ** 2)
            trend_r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0
        except Exception:
            trend_r2 = 0
    else:
        trend_r2 = 0

    base_n = 20
    n = int(base_n + atr_pct * 40 - trend_r2 * 10)
    return max(10, min(30, n))


def calc_adaptive_k(df: pd.DataFrame) -> float:
    """振幅大→K大(通道更宽), 振幅小→K小(通道更窄)"""
    if len(df) < 20:
        return 1.0
    avg_range_pct = float(((df['high'] - df['low']) / df['close']).iloc[-60:].mean())
    k = 0.5 + avg_range_pct * 30
    return max(0.3, min(2.0, k))


def calc_adaptive_offset(df: pd.DataFrame) -> float:
    """历史回撤深且恢复弱→系数<1(下轨更低更宽松)"""
    if len(df) < 60:
        return 1.0

    roll_high = df['high'].rolling(60, min_periods=1).max()
    roll_dd = (df['low'] / roll_high - 1).min()
    max_dd = -float(roll_dd)

    if max_dd > 0.25:
        return 0.95
    elif max_dd > 0.15:
        return 0.98
    else:
        return 1.0


def calc_channel_ratio(high: pd.Series, low: pd.Series,
                       n: int, double_smooth: bool) -> float:
    """计算最后一根K线的通道宽度比 (EMA_H - EMA_L) / mid"""
    ema_h, ema_l = calc_ema_rails(high, low, n, double_smooth)
    width = float(ema_h.iloc[-1] - ema_l.iloc[-1])
    mid = float((ema_h.iloc[-1] + ema_l.iloc[-1]) / 2)
    return width / mid if mid > 0 else 0.0


def calculate_golden_trend(df: pd.DataFrame,
                           config: Optional[GoldenTrendConfig] = None,
                           stock_code: str = None
                           ) -> Tuple[pd.Series, pd.Series, pd.Series, Dict]:
    """
    计算金钻趋势指标，返回 (gt_series, ema_h, ema_l, meta_dict)。

    Parameters
    ----------
    df : DataFrame with 'high', 'low', 'close' columns
    config : GoldenTrendConfig (adaptive=True 时使用自适应参数)
    stock_code : 股票代码 (仅用于日志)

    Returns
    -------
    (gt_series, ema_h, ema_l, meta)
        gt_series: GT 下轨 (golden trend 值)
        ema_h: EMA 上轨
        ema_l: EMA 下轨基准 (未减通道)
        meta: 参数和状态字典
    """
    if config is None:
        config = GoldenTrendConfig()

    h = df['high'].reset_index(drop=True)
    l = df['low'].reset_index(drop=True)

    if config.adaptive and len(df) >= 20:
        n = calc_adaptive_n(df)
        k = calc_adaptive_k(df)
        offset = calc_adaptive_offset(df)
        double_smooth = True
    else:
        n = config.n
        k = config.k
        offset = config.offset_coef
        double_smooth = config.double_smooth

    ema_h, ema_l = calc_ema_rails(h, l, n, double_smooth)
    gt = calc_golden_trend(h, l, n, double_smooth, k, offset)

    channel_ratio = calc_channel_ratio(h, l, n, double_smooth)
    rail_overlap = channel_ratio < 0.02

    meta = {
        'n': n,
        'k': round(k, 3),
        'offset': round(offset, 3),
        'double_smooth': double_smooth,
        'channel_ratio': round(channel_ratio, 4),
        'rail_overlap': rail_overlap,
    }

    gt.index = df.index
    ema_h.index = df.index
    ema_l.index = df.index

    return gt, ema_h, ema_l, meta
