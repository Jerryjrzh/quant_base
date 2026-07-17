# backend/kline_patterns.py
import pandas as pd
import numpy as np
import talib
from typing import Dict, Tuple, Optional


class KlinePatternDetector:
    """
    多周期 K 线形态识别器（日线 / 周线 / 60分钟线）
    支持 TA-Lib 标准形态 + 自定义复合形态（深踩反转、金牛金钻等）
    """

    def __init__(self):
        self.patterns = {}

    def resample_to_period(self, df: pd.DataFrame, period: str = 'W') -> pd.DataFrame:
        """重采样到指定周期（W=周线, 60T=60分钟等）"""
        if period == 'W':
            return df.resample('W').agg({
                'open': 'first', 'high': 'max', 'low': 'min',
                'close': 'last', 'volume': 'sum'
            }).dropna()
        elif period == '60T':
            return df.resample('60T').agg({
                'open': 'first', 'high': 'max', 'low': 'min',
                'close': 'last', 'volume': 'sum'
            }).dropna()
        return df  # 默认日线

    def detect_talib_patterns(self, df: pd.DataFrame) -> Dict[str, int]:
        """使用 TA-Lib 检测标准 K 线形态"""
        o, h, l, c = df['open'], df['high'], df['low'], df['close']
        
        patterns = {
            'DOJI': talib.CDLDOJI(o, h, l, c).iloc[-1],
            'HAMMER': talib.CDLHAMMER(o, h, l, c).iloc[-1],
            'INVERTED_HAMMER': talib.CDLINVERTEDHAMMER(o, h, l, c).iloc[-1],
            'ENGULFING': talib.CDLENGULFING(o, h, l, c).iloc[-1],
            'MORNING_STAR': talib.CDLMORNINGSTAR(o, h, l, c).iloc[-1],
            'EVENING_STAR': talib.CDLEVENINGSTAR(o, h, l, c).iloc[-1],
            'THREE_WHITE_SOLDIERS': talib.CDL3WHITESOLDIERS(o, h, l, c).iloc[-1],
            'THREE_BLACK_CROWS': talib.CDL3BLACKCROWS(o, h, l, c).iloc[-1],
            'PIERCING': talib.CDLPIERCING(o, h, l, c).iloc[-1],
            'DARK_CLOUD_COVER': talib.CDLDARKCLOUDCOVER(o, h, l, c).iloc[-1],
        }
        return {k: int(v) for k, v in patterns.items() if v != 0}

    def detect_deep_step_reversal(self, df: pd.DataFrame, ma_period: int = 60) -> Dict:
        """自定义：深踩专属均线后的反转形态"""
        ma = talib.MA(df['close'], timeperiod=ma_period)
        dist = (df['close'] - ma) / ma
        
        result = {
            'near_support': abs(dist.iloc[-1]) <= 0.028,           # 当前靠近均线
            'deep_step': (dist.iloc[-5:] < -0.015).sum() >= 2,    # 近期有深踩
            'reversal_signal': (df['close'].iloc[-1] > df['close'].iloc[-2]) and 
                              (df['volume'].iloc[-1] > df['volume'].iloc[-2] * 1.2),
            'ma_uptrend': ma.iloc[-1] > ma.iloc[-10]
        }
        return result

    def analyze_multi_timeframe(self, df_daily: pd.DataFrame) -> Dict:
        """
        多周期综合分析
        """
        results = {
            'daily': self.detect_talib_patterns(df_daily),
            'weekly': self.detect_talib_patterns(self.resample_to_period(df_daily, 'W')),
            'deep_step': self.detect_deep_step_reversal(df_daily, ma_period=60)
        }
        return results


# ====================== 便捷调用函数 ======================
def detect_patterns(df: pd.DataFrame, include_weekly: bool = True) -> Dict:
    """对外便捷接口"""
    detector = KlinePatternDetector()
    return detector.analyze_multi_timeframe(df)
