#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
60分钟K线特征提取模块 (路径分类器输入)

对每个信号提取 T0 日及之前 ~20 个交易日的 60m K 线特征 (~15 维)。
所有特征仅使用 T0 及之前数据，无未来泄露。
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Any

import data_loader


def extract_hourly_features(stock_code: str,
                            t0_date: pd.Timestamp,
                            lookback_calendar_days: int = 35) -> Optional[Dict[str, float]]:
    """
    提取 T0 及之前 ~20 个交易日的 60m K 线特征。

    返回: dict of feature name -> scalar, or None if data insufficient
    """
    t0 = pd.to_datetime(t0_date)
    start = (t0 - pd.Timedelta(days=lookback_calendar_days)).strftime('%Y-%m-%d')
    # 截止 t0 当日收盘 (包含 t0 当日 bar)
    end = (t0 + pd.Timedelta(days=1)).strftime('%Y-%m-%d')

    try:
        df = data_loader.get_min_data_in_range(stock_code, '60m', start, end)
    except Exception:
        return None

    if df is None or df.empty:
        return None

    # 确保 index 是 DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns:
            df = df.set_index(pd.to_datetime(df['datetime']))
        elif 'date' in df.columns:
            df = df.set_index(pd.to_datetime(df['date']))
        else:
            df = df.copy()
            df.index = pd.to_datetime(df.index, errors='coerce')

    # 截取 t0 当日及之前
    df = df[df.index <= t0.normalize() + pd.Timedelta(days=1)]
    if len(df) < 80:  # 至少 ~20 根 60m (5 交易日)
        return None

    # 取最近 400 根 (≈100 交易日)，控制特征计算稳定
    df = df.tail(400).copy()

    df['hourly_return'] = df['close'].pct_change()
    df['range'] = df['high'] - df['low']

    # 趋势结构
    ma20 = df['close'].rolling(20, min_periods=10).mean()
    ma60 = df['close'].rolling(60, min_periods=30).mean()
    ma20_slope = (ma20.iloc[-1] - ma20.iloc[-20]) / 20 if len(ma20) >= 20 else 0
    close_ma20_ratio = df['close'].iloc[-1] / ma20.iloc[-1] - 1 if ma20.iloc[-1] > 0 else 0
    close_ma60_ratio = (df['close'].iloc[-1] / ma60.iloc[-1] - 1
                        if not np.isnan(ma60.iloc[-1]) and ma60.iloc[-1] > 0 else 0)

    # 波动特征
    vol_20 = df['hourly_return'].rolling(20, min_periods=10).std().iloc[-1]
    avg_amplitude = (df['range'] / df['open']).mean()
    prev_close = df['close'].shift(1)
    gap_mask = prev_close > 0
    gap_freq = ((abs(df['open'] - prev_close) / prev_close) > 0.01).where(gap_mask).mean()

    # 量价关系
    up_mask = df['close'] > df['open']
    down_mask = df['close'] < df['open']
    up_vol = df.loc[up_mask, 'volume'].mean() if up_mask.any() else 0
    down_vol = df.loc[down_mask, 'volume'].mean() if down_mask.any() else 1e-6
    up_down_vol_ratio = up_vol / (down_vol + 1e-6)

    vol_ma20 = df['volume'].rolling(20, min_periods=10).mean()
    volume_trend = (vol_ma20.iloc[-1] / vol_ma20.iloc[-20]
                    if len(vol_ma20) >= 20 and vol_ma20.iloc[-20] > 0 else 1.0)

    # 回调形态 (近20交易日 ≈ 80根 60m)
    recent = df.tail(80)
    recent_high = recent['high'].max()
    recent_low = recent['low'].min()
    drawdown_depth = ((recent_high - recent_low) / recent_high
                     if recent_high > 0 else 0)
    span = recent_high - recent_low
    rebound_ratio = ((df['close'].iloc[-1] - recent_low) / span
                     if span > 0 else 0.5)

    # 路径特征
    rolling_high = df['high'].expanding(min_periods=1).max()
    new_high_count = int((df['high'] >= rolling_high * 0.999).sum())
    touch_ma20 = int((df['low'] <= ma20).sum()) if ma20.notna().any() else 0

    # 近20根K线动能
    last20 = df.tail(20)
    momentum_20 = (last20['close'].iloc[-1] / last20['close'].iloc[0] - 1
                   if last20['close'].iloc[0] > 0 else 0)

    # 近5根vs近20根量能
    vol5 = df['volume'].tail(5).mean()
    vol20 = df['volume'].tail(20).mean()
    vol_5_20_ratio = vol5 / vol20 if vol20 > 0 else 1.0

    # v4.1 新增特征
    last20_close = last20['close'].values.astype(float)
    if len(last20_close) >= 10 and last20_close.min() > 0:
        x = np.arange(len(last20_close), dtype=float)
        y = np.log(last20_close)
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        trend_stability = max(1 - ss_res / ss_tot, 0.0) if ss_tot > 0 else 0.0
    else:
        trend_stability = 0.0

    hourly_dd_series = df['hourly_return'].rolling(4, min_periods=2).min()
    avg_intraday_dd = float(hourly_dd_series.tail(80).mean()) if len(hourly_dd_series.tail(80).dropna()) > 0 else 0.0

    r80_high = recent['high'].max()
    r80_low = recent['low'].min()
    price_compactness = (r80_high / r80_low - 1) if r80_low > 0 else 0.0

    features = {
        'n_bars': len(df),
        'ma20_slope': float(ma20_slope) if not np.isnan(ma20_slope) else 0.0,
        'close_ma20_ratio': float(close_ma20_ratio),
        'close_ma60_ratio': float(close_ma60_ratio),
        'volatility_20': float(vol_20) if not np.isnan(vol_20) else 0.0,
        'avg_amplitude': float(avg_amplitude),
        'gap_freq': float(gap_freq) if not np.isnan(gap_freq) else 0.0,
        'up_down_vol_ratio': float(up_down_vol_ratio),
        'volume_trend': float(volume_trend),
        'drawdown_depth_80': float(drawdown_depth),
        'rebound_ratio_80': float(rebound_ratio),
        'new_high_freq': new_high_count / len(df),
        'ma20_touch_freq': touch_ma20 / len(df),
        'momentum_20': float(momentum_20),
        'vol_5_20_ratio': float(vol_5_20_ratio),
        'trend_stability': float(trend_stability),
        'avg_intraday_dd': float(avg_intraday_dd) if not np.isnan(avg_intraday_dd) else 0.0,
        'price_compactness': float(price_compactness),
    }
    return features
