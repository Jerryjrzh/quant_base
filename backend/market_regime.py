import pandas as pd
from kline_patterns import KlinePatternDetector
import data_loader
import logging

logger = logging.getLogger(__name__)

class MarketRegimeDetector:
    """
    股指多周期风险雷达（日线 + 60分钟 + 15分钟）
    """
    def __init__(self):
        self.detector = KlinePatternDetector()

    def evaluate_regime(self, df_index: pd.DataFrame, eval_date: str, index_code: str = 'sh000852'):
        """核心评估函数"""
        if df_index is None or eval_date not in df_index.index:
            return {"state": "NORMAL", "risk_score": 30, "discount": 1.0, "max_positions": 12}

        try:
            loc = df_index.index.get_loc(eval_date)
            if loc < 30:
                return {"state": "NORMAL", "risk_score": 30, "discount": 1.0, "max_positions": 12}

            close = df_index['close'].iloc[loc]
            ma20 = df_index['close'].iloc[loc-20:loc].mean()
            daily_drop = (close - df_index['close'].iloc[loc-1]) / df_index['close'].iloc[loc-1]

            # 加载短期分钟线（近10天）
            start_60 = (pd.to_datetime(eval_date) - pd.Timedelta(days=12)).strftime('%Y-%m-%d')
            df_60m = data_loader.get_min_data_in_range(index_code, '60m', start_60, eval_date)  # 中证1000

            short_bear = False
            if df_60m is not None and len(df_60m) > 20:
                # 🛡️ 强力防御：大盘分钟线同样强制设定 DatetimeIndex，防止 ndarray 降级
                if 'datetime' in df_60m.columns:
                    df_60m.index = pd.to_datetime(df_60m['datetime'])
                elif not isinstance(df_60m.index, pd.DatetimeIndex):
                    df_60m.index = pd.to_datetime(df_60m.index)
                    
                short_patterns = self.detector.detect_talib_patterns(df_60m)
                if any(v < 0 for v in short_patterns.values()):   # 出现看跌形态
                    short_bear = True

            # 综合判断
            if close < ma20 * 0.955 or daily_drop < -0.035:
                return {"state": "STRONG_BEAR", "risk_score": 88, "discount": 0.91, "max_positions": 3}
            elif close < ma20 or short_bear:
                return {"state": "MILD_BEAR", "risk_score": 65, "discount": 0.96, "max_positions": 7}
            else:
                return {"state": "BULLISH", "risk_score": 25, "discount": 1.0, "max_positions": 15}

        except Exception as e:
            logger.warning(f"股指雷达评估异常: {e}")
            return {"state": "NORMAL", "risk_score": 40, "discount": 0.98, "max_positions": 12}
