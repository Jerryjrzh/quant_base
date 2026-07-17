import pandas as pd
from kline_patterns import KlinePatternDetector
import data_loader

class MarketRegimeDetector:
    def __init__(self):
        self.detector = KlinePatternDetector()
    
    def evaluate_regime(self, df_index: pd.DataFrame, eval_date: str, lookback_days: int = 20):
        """股指多周期风险评估（日线 + 小时线 + 15分钟线）"""
        if df_index is None or eval_date not in df_index.index:
            return {"state": "NORMAL", "risk_score": 30, "discount": 1.0, "max_positions": 12}
        
        loc = df_index.index.get_loc(eval_date)
        if loc < lookback_days:
            return {"state": "NORMAL", "risk_score": 30, "discount": 1.0, "max_positions": 12}
        
        # 日线趋势
        close = df_index['close'].iloc[loc]
        ma20 = df_index['close'].iloc[loc-lookback_days:loc].mean()
        daily_drop = (close - df_index['close'].iloc[loc-1]) / df_index['close'].iloc[loc-1]
        
        # 加载60分钟和15分钟形态（短期状态）
        code = df_index.name if hasattr(df_index, 'name') else 'index'
        df_60m = data_loader.get_min_data_in_range(code, '60m', 
                                                   start_date=(pd.to_datetime(eval_date) - pd.Timedelta(days=10)).strftime('%Y-%m-%d'),
                                                   end_date=eval_date)
        df_15m = data_loader.get_min_data_in_range(code, '15m', 
                                                   start_date=(pd.to_datetime(eval_date) - pd.Timedelta(days=5)).strftime('%Y-%m-%d'),
                                                   end_date=eval_date)
        
        short_term_patterns = {}
        if df_60m is not None and len(df_60m) > 10:
            short_term_patterns['60m'] = self.detector.detect_talib_patterns(df_60m)
        if df_15m is not None and len(df_15m) > 10:
            short_term_patterns['15m'] = self.detector.detect_talib_patterns(df_15m)
        
        # 综合判断
        if close < ma20 * 0.96 or daily_drop < -0.025:
            return {"state": "STRONG_BEAR", "risk_score": 85, "discount": 0.92, "max_positions": 4}
        elif close < ma20 or any(p.get('THREE_BLACK_CROWS', 0) < 0 for p in short_term_patterns.values()):
            return {"state": "MILD_BEAR", "risk_score": 65, "discount": 0.96, "max_positions": 7}
        else:
            return {"state": "BULLISH", "risk_score": 25, "discount": 1.0, "max_positions": 15}
