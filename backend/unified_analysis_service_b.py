"""
统一分析服务
实现数据库缓存机制的核心分析服务
"""

import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime
import json

# 导入必要的模块
from analysis_cache import analysis_cache
from enhanced_advisor import generate_enhanced_advice
import backtester
import data_loader
import indicators
from data_handler import get_full_data_with_indicators
from stock_pool_manager import StockPoolManager
from portfolio_manager import create_portfolio_manager
from config_manager import config_manager
from strategy_manager import strategy_manager

def get_or_run_analysis(stock_code: str, strategy_id: str) -> Dict[str, Any]:
    """
    核心函数：从数据库获取分析结果，如果不存在或已过期，则重新运行并存入数据库。
    
    Args:
        stock_code: 股票代码
        strategy_id: 策略ID
        
    Returns:
        完整的分析结果字典
    """
    try:
        # 1. 尝试从数据库获取今天的结果
        cached_result = analysis_cache.get_cached_analysis(stock_code, strategy_id)
        
        if cached_result:
            # 缓存命中，直接返回
            return {
                'success': True,
                'data': {
                    'stock_code': stock_code,
                    'stock_name': _get_stock_name(stock_code),
                    'chart_data': cached_result['chart_data'],
                    'analysis': {
                        'backtest_results': cached_result['backtest_results'],
                        **cached_result['deep_analysis']
                    },
                    'from_cache': True,
                    'cache_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
            }
        
        # 2. 缓存未命中，开始实时计算
        print(f"⏳ 缓存未命中，开始实时计算: {stock_code} @ {strategy_id}")
        
        # 3. 获取完整的股票数据和指标
        df = get_full_data_with_indicators(stock_code)
        if df is None:
            return {
                'success': False,
                'error': f'无法加载股票数据: {stock_code}'
            }
        
        # 4. 处理策略信号
        signals = _apply_strategy(strategy_id, df)
        
        # 5. 运行深度分析（包含增强版建议）
        deep_analysis = _run_enhanced_deep_analysis(stock_code, df)
        
        # 6. 运行回测分析
        backtest_results = _run_backtest_analysis(df, signals)
        
        # 7. 准备图表数据
        chart_data = _prepare_chart_data(df, signals, backtest_results)
        
        # 8. 获取股票基础信息
        stock_info = _get_stock_profile(stock_code)
        
        # 9. 将新结果存入数据库
        analysis_cache.save_analysis_result(
            stock_code, 
            strategy_id, 
            backtest_results, 
            deep_analysis, 
            chart_data
        )
        
        # 10. 更新股票基础信息
        if stock_info:
            analysis_cache.update_stock_info(
                stock_code,
                stock_info.get('stock_name'),
                stock_info.get('sector')
            )
        
        # 11. 组装最终结果
        unified_result = {
            'stock_code': stock_code,
            'stock_name': stock_info.get('stock_name', stock_code) if stock_info else stock_code,
            'sector': stock_info.get('sector', '未知') if stock_info else '未知',
            'chart_data': chart_data,
            'analysis': {
                'backtest_results': backtest_results,
                **deep_analysis
            },
            'profile': stock_info or {},
            'portfolio_info': _get_portfolio_info(stock_code),
            'from_cache': False,
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return {
            'success': True,
            'data': unified_result
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': f'统一分析失败: {str(e)}'
        }

def _apply_strategy(strategy_id: str, df: pd.DataFrame) -> pd.Series:
    """
    应用策略获取信号
    """
    try:
        # 使用策略管理器获取策略实例
        strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
        if strategy_instance:
            signals = strategy_instance.apply_strategy(df)
            if signals is not None:
                return signals
        
        # 如果策略管理器失败，尝试传统方法
        import strategies
        if hasattr(strategies, 'apply_strategy'):
            signals = strategies.apply_strategy(strategy_id, df)
            if signals is not None:
                return signals
        
        # 返回空信号
        return pd.Series([False] * len(df), index=df.index)
        
    except Exception as e:
        print(f"策略应用失败: {e}")
        return pd.Series([False] * len(df), index=df.index)

def _run_enhanced_deep_analysis(stock_code: str, df: pd.DataFrame) -> Dict[str, Any]:
    """
    运行增强版深度分析
    """
    try:
        # 1. 运行基础深度分析
        base_analysis = backtester.get_deep_analysis(stock_code, df.copy())
        
        if 'error' in base_analysis:
            return base_analysis
        
        # 2. 运行增强版建议分析
        enhanced_advice = generate_enhanced_advice(df, stock_code)
        
        # 3. 合并结果
        base_analysis['enhanced_trading_advice'] = enhanced_advice
        
        return base_analysis
        
    except Exception as e:
        print(f"增强版深度分析失败: {e}")
        return {'error': f'增强版深度分析失败: {str(e)}'}

def _run_backtest_analysis(df: pd.DataFrame, signals: pd.Series) -> Dict[str, Any]:
    """
    运行回测分析
    """
    try:
        if signals is None or len(signals) == 0:
            return {'error': '无有效信号进行回测'}
        
        # 检查信号格式
        if isinstance(signals, tuple) and len(signals) > 0:
            signals = signals[0]
        
        # 运行回测
        backtest_results = backtester.run_backtest(df, signals)
        
        # 序列化结果
        if isinstance(backtest_results, dict):
            import numpy as np
            backtest_results = json.loads(json.dumps(
                backtest_results, 
                default=lambda x: x.item() if isinstance(x, (np.integer, np.floating)) 
                else bool(x) if isinstance(x, np.bool_) else None
            ))
        
        return backtest_results
        
    except Exception as e:
        print(f"回测分析失败: {e}")
        return {'error': f'回测分析失败: {str(e)}'}

def _prepare_chart_data(df: pd.DataFrame, signals: pd.Series, 
                       backtest_results: Dict) -> Dict[str, Any]:
    """
    准备图表数据
    """
    try:
        # 重置索引并格式化日期
        df_reset = df.reset_index()
        df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d')
        
        # K线数据
        kline_data = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        
        # 指标数据
        indicator_columns = ['date', 'ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']
        available_columns = [col for col in indicator_columns if col in df_reset.columns]
        indicator_data = df_reset[available_columns].to_dict('records')
        
        # 信号点数据
        signal_points = _extract_signal_points(df_reset, signals, backtest_results)
        
        return {
            'kline_data': kline_data,
            'indicator_data': indicator_data,
            'signal_points': signal_points
        }
        
    except Exception as e:
        print(f"图表数据准备失败: {e}")
        return {
            'kline_data': [],
            'indicator_data': [],
            'signal_points': []
        }

def _extract_signal_points(df_reset: pd.DataFrame, signals: pd.Series, 
                          backtest_results: Dict) -> list:
    """
    提取信号点数据
    """
    signal_points = []
    
    try:
        if signals is None or len(signals) == 0:
            return signal_points
        
        # 获取交易结果映射
        trade_results = {}
        if 'trades' in backtest_results:
            trade_results = {
                trade['entry_idx']: trade 
                for trade in backtest_results['trades']
            }
        
        # 处理信号
        df_with_signals = df_reset.copy()
        df_with_signals['signal'] = signals.values if len(signals) == len(df_reset) else [False] * len(df_reset)
        
        # 提取有效信号点
        valid_signals = df_with_signals[df_with_signals['signal'] != False]
        
        for idx, row in valid_signals.iterrows():
            original_state = str(row['signal'])
            
            # 判断成功失败
            is_success = trade_results.get(idx, {}).get('is_success', False)
            final_state = f"{original_state}_SUCCESS" if is_success else f"{original_state}_FAIL"
            
            # 获取实际入场价格
            actual_entry_price = trade_results.get(idx, {}).get('entry_price')
            display_price = float(actual_entry_price) if actual_entry_price else float(row['close'])
            
            signal_points.append({
                'date': row['date'],
                'price': display_price,
                'state': final_state,
                'original_state': original_state
            })
    
    except Exception as e:
        print(f"信号点提取失败: {e}")
    
    return signal_points

def _get_stock_name(stock_code: str) -> str:
    """
    获取股票名称
    """
    try:
        # 首先尝试从缓存获取
        stock_info = analysis_cache.get_stock_info(stock_code)
        if stock_info and stock_info.get('stock_name'):
            return stock_info['stock_name']
        
        # 尝试从股票池管理器获取
        pool_manager = StockPoolManager()
        stock_profile = pool_manager.get_stock_by_code(stock_code)
        if stock_profile and stock_profile.get('stock_name'):
            return stock_profile['stock_name']
        
        return stock_code
        
    except Exception:
        return stock_code

def _get_stock_profile(stock_code: str) -> Optional[Dict]:
    """
    获取股票档案信息
    """
    try:
        pool_manager = StockPoolManager()
        return pool_manager.get_stock_by_code(stock_code)
    except Exception:
        return None

def _get_portfolio_info(stock_code: str) -> Optional[Dict]:
    """
    获取持仓信息
    """
    try:
        portfolio_manager = create_portfolio_manager()
        portfolio = portfolio_manager.load_portfolio()
        return next((p for p in portfolio if p['stock_code'] == stock_code), None)
    except Exception:
        return None

def get_cache_statistics() -> Dict[str, Any]:
    """
    获取缓存统计信息
    """
    try:
        stats = analysis_cache.get_cache_stats()
        return {
            'success': True,
            'stats': stats
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'获取缓存统计失败: {str(e)}'
        }

def clear_expired_cache(days_old: int = 7) -> Dict[str, Any]:
    """
    清理过期缓存
    """
    try:
        deleted_count = analysis_cache.clear_old_cache(days_old)
        return {
            'success': True,
            'deleted_count': deleted_count,
            'message': f'已清理 {deleted_count} 条过期缓存记录'
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'清理缓存失败: {str(e)}'
        }