"""
【V4.1 - 调度与缓存层】
实现清晰的单向数据流，调用V4.1深度分析服务并缓存结果
"""
import pandas as pd
from typing import Dict, Any
from datetime import datetime

from analysis_cache import analysis_cache
from data_handler import get_full_data_with_indicators
from stock_pool_manager import StockPoolManager
from strategy_manager import strategy_manager
# --- 核心修改：只依赖 backtester 获取所有分析结果 ---
import backtester

def get_or_run_analysis(stock_code: str, strategy_id: str) -> Dict[str, Any]:
    """
    核心函数：实现清晰的单向数据流，并集成数据库缓存。
    """
    try:
        cached_result = analysis_cache.get_cached_analysis(stock_code, strategy_id)
        if cached_result:
            return _build_success_response(stock_code, cached_result, from_cache=True)

        print(f"⏳ 缓存未命中，开始V4.1实时计算: {stock_code} @ {strategy_id}")
        
        df = get_full_data_with_indicators(stock_code)
        if df is None:
            return {'success': False, 'error': f'无法加载股票数据: {stock_code}'}

        # --- 核心数据流改变 ---
        # 1. 运行V4.1深度分析，获取包含所有信息的综合结果
        deep_analysis_result = backtester.get_deep_analysis(stock_code, df)
        
        if 'error' in deep_analysis_result:
             return {'success': False, 'error': deep_analysis_result['error']}

        # 2. 运行历史回测（可选，作为补充信息）
        signals = _apply_strategy(strategy_id, df)
        historical_backtest = backtester.run_backtest(df, signals)
        
        # 3. 准备图表数据
        chart_data = _prepare_chart_data(df, signals, historical_backtest)
        
        # 4. 组装待缓存的完整数据包
        data_to_cache = {
            'deep_analysis': deep_analysis_result,
            'historical_backtest': historical_backtest,
            'chart_data': chart_data
        }
        
        analysis_cache.save_analysis_result(
            stock_code, 
            strategy_id, 
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
    stock_info = StockPoolManager().get_stock_by_code(stock_code)
    stock_name = stock_info.get('stock_name', stock_code) if stock_info else stock_code

    # V4.1 响应结构 - 修复交易建议数据结构
    deep_analysis = result_data['deep_analysis']
    
    unified_result = {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'sector': stock_info.get('sector', '未知') if stock_info else '未知',
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
        df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d')
        
        # K线数据
        kline = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        
        # 指标数据 - 包含完整的MA系列
        indicator_cols = ['date', 'ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12']
        for col in indicator_cols:
            if col not in df_reset.columns:
                df_reset[col] = None
        
        # 填充NaN值 - 包含完整的MA系列
        for col in ['ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(df_reset['close'])
        
        for col in ['k', 'd', 'j', 'rsi6', 'rsi12']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(50.0)
        
        for col in ['dif', 'dea', 'macd']:
            if col in df_reset.columns:
                df_reset[col] = df_reset[col].fillna(0.0)
        
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
        
        return {'kline_data': kline, 'indicator_data': indicator_data, 'signal_points': signal_points}
    
    except Exception as e:
        print(f"准备图表数据失败: {e}")
        return {'kline_data': [], 'indicator_data': [], 'signal_points': []}
