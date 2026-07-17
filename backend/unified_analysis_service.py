"""
【V4.1 - 调度与缓存层】
实现清晰的单向数据流，调用V4.1深度分析服务并缓存结果
"""
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime

from analysis_cache import analysis_cache
from data_handler import get_full_data_with_indicators, calculate_all_indicators
from stock_pool_manager import StockPoolManager
from strategy_manager import strategy_manager
# --- 核心修改：只依赖 backtester 获取所有分析结果 ---
import backtester


# 5分钟线可 resample 的周期映射
_MIN5_RESAMPLE_MAP = {
    '5min':  '5min',
    '10min': '10min',
    '15min': '15min',
    '30min': '30min',
    '60min': '60min',
}

# 日线/周线/月线 resample 规则
_DAILY_RESAMPLE_MAP = {
    'weekly':  'W-FRI',
    'monthly': 'ME',
}


def _load_5min_df(stock_code: str) -> Optional[pd.DataFrame]:
    """加载5分钟原始数据，返回 DatetimeIndex 的 DataFrame"""
    try:
        from data_loader import _build_paths, get_5min_data
        _, _, min5_file = _build_paths(stock_code)
        import os
        if not os.path.exists(min5_file):
            return None
        return get_5min_data(min5_file)
    except Exception as e:
        print(f"[unified] 加载5分钟数据失败 {stock_code}: {e}")
        return None


def _apply_forward_adjustment_to_5min(df_5min: pd.DataFrame, stock_code: str, 
                                       df_daily_adj: pd.DataFrame) -> pd.DataFrame:
    """
    利用日线前复权因子对5分钟数据做前复权。
    计算日线复权前后的收盘价比值，按日期映射到5分钟数据。
    """
    try:
        from data_handler import get_stock_data_simple
        df_raw = get_stock_data_simple(stock_code)
        if df_raw is None or df_raw.empty:
            return df_5min

        df_raw.index = pd.to_datetime(df_raw.index)
        df_daily_adj.index = pd.to_datetime(df_daily_adj.index)

        common_dates = df_raw.index.intersection(df_daily_adj.index)
        if common_dates.empty:
            return df_5min

        factor_series = (df_daily_adj.loc[common_dates, 'close'] /
                         df_raw.loc[common_dates, 'close']).dropna()
        if factor_series.empty:
            return df_5min

        df_out = df_5min.copy()
        df_out.index = pd.to_datetime(df_out.index)
        dates_5min = df_out.index.normalize()

        # 按日期向前填充复权因子
        factor_by_date = factor_series.reindex(dates_5min, method='ffill').fillna(1.0)
        factor_by_date.index = df_out.index

        for col in ['open', 'high', 'low', 'close']:
            if col in df_out.columns:
                df_out[col] = df_out[col] * factor_by_date

        return df_out
    except Exception as e:
        print(f"[unified] 5分钟复权失败: {e}")
        return df_5min


def _resample_to_timeframe(df: pd.DataFrame, timeframe: str, 
                            stock_code: str = None, adjustment_type: str = 'forward') -> Optional[pd.DataFrame]:
    """
    将数据重采样为指定周期。
    - daily: 直接返回
    - weekly/monthly: 从日线 resample
    - 5min/10min/15min/30min/60min: 从 .lc5 文件加载5分钟数据后 resample
    """
    if timeframe == 'daily' or df is None or df.empty:
        return df

    _AGG = {'open': 'first', 'high': 'max', 'low': 'min',
            'close': 'last', 'volume': 'sum', 'amount': 'sum'}

    # 周线/月线：直接从复权日线 resample
    if timeframe in _DAILY_RESAMPLE_MAP:
        rule = _DAILY_RESAMPLE_MAP[timeframe]
        agg_cols = {k: v for k, v in _AGG.items() if k in df.columns}
        return df.resample(rule).agg(agg_cols).dropna(subset=['open', 'close'])

    # 分钟线：从5分钟原始数据加载
    if timeframe in _MIN5_RESAMPLE_MAP and stock_code:
        df_5min = _load_5min_df(stock_code)
        if df_5min is None or df_5min.empty:
            print(f"[unified] 无5分钟数据: {stock_code}，回退到日线")
            return df  # 回退到日线

        # 复权处理：将日线复权因子映射到5分钟数据
        if adjustment_type != 'none':
            df_5min = _apply_forward_adjustment_to_5min(df_5min, stock_code, df)

        # resample 到目标周期
        rule = _MIN5_RESAMPLE_MAP[timeframe]
        agg_cols = {k: v for k, v in _AGG.items() if k in df_5min.columns}
        df_5min.index = pd.to_datetime(df_5min.index)
        
        if timeframe == '5min':
            return df_5min  # 5分钟直接用，不需要 resample
        
        df_resampled = df_5min.resample(rule).agg(agg_cols).dropna(subset=['open', 'close'])
        df_resampled = df_resampled[df_resampled['open'] > 0]
        return df_resampled

    return df


def get_or_run_analysis(stock_code: str, strategy_id: str, timeframe: str = 'daily', adjustment_type: str = 'forward') -> Dict[str, Any]:
    """
    核心函数：实现清晰的单向数据流，并集成数据库缓存。
    timeframe: 'daily' | 'weekly' | 'monthly' | '5min' | '10min' | '15min' | '30min' | '60min'
    adjustment_type: 'forward' | 'backward' | 'none'
    """
    try:
        # 只对日线+前复权走缓存，其他组合不缓存
        use_cache = (timeframe == 'daily' and adjustment_type == 'forward')
        cache_key = strategy_id
        if use_cache:
            cached_result = analysis_cache.get_cached_analysis(stock_code, cache_key)
            if cached_result:
                return _build_success_response(stock_code, cached_result, from_cache=True)

        print(f"⏳ 开始计算: {stock_code} @ {strategy_id} [{timeframe}] [{adjustment_type}]")

        # 加载日线数据（含指标，按指定复权类型）
        df = get_full_data_with_indicators(stock_code, adjustment_type=adjustment_type)
        if df is None:
            return {'success': False, 'error': f'无法加载股票数据: {stock_code}'}

        # 非日线周期：先 resample 复权后的 OHLCV，再重新计算指标
        if timeframe != 'daily':
            ohlcv_cols = [c for c in ['open', 'high', 'low', 'close', 'volume', 'amount'] if c in df.columns]
            df_ohlcv = df[ohlcv_cols].copy()
            df_ohlcv.attrs['stock_code'] = stock_code  # 传递给复权函数
            df_raw = _resample_to_timeframe(df_ohlcv, timeframe, 
                                             stock_code=stock_code, 
                                             adjustment_type=adjustment_type)
            if df_raw is None or df_raw.empty:
                return {'success': False, 'error': f'周期转换失败: {timeframe}'}
            df = calculate_all_indicators(df_raw, stock_code, adjustment_type='none')  # 已复权，不再重复处理

        # 深度分析
        deep_analysis_result = backtester.get_deep_analysis(stock_code, df=df)
        if 'error' in deep_analysis_result:
            return {'success': False, 'error': deep_analysis_result['error']}

        # 历史回测
        signals = _apply_strategy(strategy_id, df)
        historical_backtest = backtester.run_backtest(df, signals)

        # 图表数据
        chart_data = _prepare_chart_data(df, signals, historical_backtest)

        data_to_cache = {
            'deep_analysis': deep_analysis_result,
            'historical_backtest': historical_backtest,
            'chart_data': chart_data
        }

        # 只缓存日线
        if timeframe == 'daily':
            analysis_cache.save_analysis_result(
                stock_code,
                cache_key,
                data_to_cache['historical_backtest'],
                data_to_cache['deep_analysis'],
                data_to_cache['chart_data']
            )

        return _build_success_response(stock_code, data_to_cache, from_cache=False)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': f'统一分析失败: {str(e)}'}


def _build_success_response(stock_code, result_data, from_cache):
    """构建统一的成功响应结构"""
    from stock_name_reader import get_stock_name
    stock_name = get_stock_name(stock_code)

    # V4.1 响应结构 - 修复交易建议数据结构
    deep_analysis = result_data['deep_analysis']
    
    unified_result = {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'sector': '未知',
        'chart_data': result_data['chart_data'],
        'analysis': {
            'deep_analysis': deep_analysis,
            'historical_backtest': result_data.get('historical_backtest', {}),
            # 【修复】确保前端能访问到trading_advice
            'trading_advice': deep_analysis.get('trading_advice', {})
        },
        'from_cache': from_cache,
        'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    return {'success': True, 'data': unified_result}

# ... (_apply_strategy, _prepare_chart_data 等辅助函数保持不变) ...
def _apply_strategy(strategy_id: str, df: pd.DataFrame) -> pd.Series:
    """应用策略并确保返回pandas Series格式"""
    try:
        strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
        if not strategy_instance: return pd.Series(index=df.index, dtype=object).fillna('')
        signals = strategy_instance.apply_strategy(df)
        if isinstance(signals, tuple): signals = signals[0]
        return signals if isinstance(signals, pd.Series) else pd.Series(index=df.index, dtype=object).fillna('')
    except Exception as e:
        print(f"策略应用失败: {strategy_id}, 错误: {e}")
        return pd.Series(index=df.index, dtype=object).fillna('')

def _prepare_chart_data(df: pd.DataFrame, signals: pd.Series, backtest_results: Dict) -> Dict:
    """准备图表数据，处理NaN值确保前端正常显示"""
    try:
        df_reset = df.reset_index()
        # 兼容日线（index名为date）和分钟线（index名为datetime）
        date_col = 'datetime' if 'datetime' in df_reset.columns else 'date'
        if date_col not in df_reset.columns:
            df_reset.rename(columns={df_reset.columns[0]: 'date'}, inplace=True)
            date_col = 'date'
        
        # 分钟线保留时间，日线只保留日期
        dt_series = pd.to_datetime(df_reset[date_col])
        if dt_series.dt.time.nunique() > 1:  # 有多个不同时间 -> 分钟线
            df_reset['date'] = dt_series.dt.strftime('%Y-%m-%d %H:%M')
        else:
            df_reset['date'] = dt_series.dt.strftime('%Y-%m-%d')
        
        # K线数据
        kline = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        
        # 指标数据 - 包含完整的MA系列
        indicator_cols = ['date', 'ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24', 'gt_upper', 'gt_lower', 'gt_mid', 'mtl', 'mtl_rising', 'ema5', 'ema10', 'ema20', 'candle_color', 'trend_buy', 'trend_sell']
        for col in indicator_cols:
            if col not in df_reset.columns:
                df_reset[col] = None
        
        # 填充NaN值 - 包含完整的MA系列
        for col in ['ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(df_reset['close'])

        for col in ['gt_upper', 'gt_lower', 'gt_mid']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(df_reset['close'])
        
        for col in ['k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(50.0)
        
        for col in ['dif', 'dea', 'macd']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(0.0)

        for col in ['mtl', 'ema5', 'ema10', 'ema20']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(df_reset['close'])

        for col in ['mtl_rising', 'candle_color', 'trend_buy', 'trend_sell']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(0)
        
        indicator_data = df_reset[indicator_cols].to_dict('records')
        
        # 处理剩余NaN值
        for record in indicator_data:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
        
        # 信号点数据
        signal_points = []
        if signals is not None and isinstance(signals, pd.Series) and signals.any():
            try:
                signal_mask = signals.reindex(df_reset.index, fill_value=False)
                signal_dates = df_reset[signal_mask]['date'].tolist()
                signal_prices = df_reset[signal_mask]['close'].tolist()
                
                for date, price in zip(signal_dates, signal_prices):
                    signal_points.append({
                        'date': date,
                        'price': float(price),
                        'state': 'PENDING'
                    })
            except Exception as e:
                print(f"处理信号点数据时出错: {e}")
        
        # GT 元数据
        gt_meta = df.attrs.get('golden_trend_meta', {}) if hasattr(df, 'attrs') else {}

        return {
            'kline_data': kline,
            'indicator_data': indicator_data,
            'signal_points': signal_points,
            'golden_trend_meta': gt_meta,
        }

    except Exception as e:
        print(f"准备图表数据失败: {e}")
        return {'kline_data': [], 'indicator_data': [], 'signal_points': [], 'golden_trend_meta': {}}
