"""
【已优化】统一分析服务
实现清晰的单向数据流和数据库缓存机制
"""
import pandas as pd
from typing import Dict, Any, Optional
from datetime import datetime
import json
import numpy as np

from analysis_cache import analysis_cache
from enhanced_advisor import generate_enhanced_advice
import backtester
from data_handler import get_full_data_with_indicators
from stock_pool_manager import StockPoolManager
from portfolio_manager import create_portfolio_manager
from strategy_manager import strategy_manager

# backend/unified_analysis_service.py

def get_or_run_analysis(stock_code: str, strategy_id: str) -> Dict[str, Any]:
    """
    核心函数：实现清晰的单向数据流，并集成数据库缓存。
    """
    try:
        # 1. 尝试从数据库获取今天的结果
        cached_result = analysis_cache.get_cached_analysis(stock_code, strategy_id)
        if cached_result:
            # 缓存命中，组装数据并直接返回
            return _build_success_response(stock_code, cached_result, from_cache=True)

        # 2. 缓存未命中，开始实时计算
        print(f"⏳ 缓存未命中，开始实时计算: {stock_code} @ {strategy_id}")
        
        # 3. 获取数据
        df = get_full_data_with_indicators(stock_code)
        if df is None:
            return {'success': False, 'error': f'无法加载股票数据: {stock_code}'}

        # 4. 运行基础模块
        signals = _apply_strategy(strategy_id, df)
        base_deep_analysis = backtester.get_deep_analysis(stock_code, df.copy())
        enhanced_advice = generate_enhanced_advice(df, stock_code)
        backtest_results = _run_backtest_analysis(df, signals)
        
        # 5. 组合最终的分析结果
        final_analysis_data = {**base_deep_analysis, 'enhanced_trading_advice': enhanced_advice}
        
        # 确保trading_advice字段存在
        if 'trading_advice' not in final_analysis_data:
            final_analysis_data['trading_advice'] = {}
            
        # 将enhanced_advice的关键信息平铺到trading_advice中，保持向后兼容
        if 'reasoning' in enhanced_advice:
            final_analysis_data['trading_advice']['analysis_logic'] = enhanced_advice['reasoning']
        if 'confidence_score' in enhanced_advice:
            final_analysis_data['trading_advice']['confidence'] = enhanced_advice['confidence_score']
        if 'enhanced_action' in enhanced_advice:
            final_analysis_data['trading_advice']['action'] = enhanced_advice['enhanced_action']
        if 'price_targets' in enhanced_advice and enhanced_advice['price_targets']:
            final_analysis_data['trading_advice']['target_price'] = enhanced_advice['price_targets'].get('target_price')
            final_analysis_data['trading_advice']['stop_price'] = enhanced_advice['price_targets'].get('stop_loss_price')
            final_analysis_data['trading_advice']['entry_price'] = enhanced_advice['price_targets'].get('entry_price')
        
        # 6. 准备图表数据
        chart_data = _prepare_chart_data(df, signals, backtest_results)
        
        # 7. 组装待缓存的完整数据包
        data_to_cache = {
            'backtest_results': backtest_results,
            'deep_analysis': final_analysis_data,
            'chart_data': chart_data
        }
        
        # 8. 【FIX】检查错误后再存入缓存
        if 'error' not in final_analysis_data and 'error' not in backtest_results:
            analysis_cache.save_analysis_result(
                stock_code, 
                strategy_id, 
                data_to_cache['backtest_results'],
                data_to_cache['deep_analysis'],
                data_to_cache['chart_data']
            )
        else:
            print(f"⚠️ 分析包含错误，不存入缓存: {stock_code} @ {strategy_id}")
        
        # 9. 组装并返回给前端
        return _build_success_response(stock_code, data_to_cache, from_cache=False)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {'success': False, 'error': f'统一分析失败: {str(e)}'}


def _build_success_response(stock_code, result_data, from_cache):
    """构建统一的成功响应结构"""
    stock_info = _get_stock_profile(stock_code)
    stock_name = stock_info.get('stock_name', stock_code) if stock_info else stock_code
    
    # 更新数据库中的股票基础信息
    if stock_info and not from_cache:
        analysis_cache.update_stock_info(stock_code, stock_name, stock_info.get('sector'))
    
    unified_result = {
        'stock_code': stock_code,
        'stock_name': stock_name,
        'sector': stock_info.get('sector', '未知') if stock_info else '未知',
        'chart_data': result_data['chart_data'],
        'analysis': {
            'backtest_results': result_data['backtest_results'],
            **result_data['deep_analysis'] 
        },
        'profile': stock_info or {},
        'portfolio_info': _get_portfolio_info(stock_code),
        'from_cache': from_cache,
        'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    return {'success': True, 'data': unified_result}

# --- 辅助函数 (基本保持不变) ---

def _apply_strategy(strategy_id: str, df: pd.DataFrame) -> pd.Series:
    """应用策略并确保返回pandas Series格式"""
    try:
        strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
        if strategy_instance:
            signals = strategy_instance.apply_strategy(df)
            
            # 处理不同的返回格式
            if signals is None:
                return pd.Series([False] * len(df), index=df.index)
            elif isinstance(signals, tuple):
                # 如果返回的是元组，取第一个元素（通常是信号Series）
                signals = signals[0] if len(signals) > 0 else pd.Series([False] * len(df), index=df.index)
            elif not isinstance(signals, pd.Series):
                # 如果不是Series，尝试转换
                signals = pd.Series(signals, index=df.index) if hasattr(signals, '__len__') else pd.Series([False] * len(df), index=df.index)
            
            return signals
        return pd.Series([False] * len(df), index=df.index)
    except Exception as e:
        print(f"策略应用失败: {strategy_id}, 错误: {e}")
        return pd.Series([False] * len(df), index=df.index)

def _run_backtest_analysis(df: pd.DataFrame, signals: pd.Series) -> Dict[str, Any]:
    """运行回测分析，处理不同格式的signals"""
    try:
        # 处理不同格式的signals
        if signals is None:
            return {'error': '无信号'}
        
        if isinstance(signals, tuple):
            signals = signals[0] if len(signals) > 0 else None
            
        if signals is None or (hasattr(signals, 'empty') and signals.empty):
            return {'error': '无信号'}
            
        if not isinstance(signals, pd.Series):
            # 尝试转换为Series
            if hasattr(signals, '__len__'):
                signals = pd.Series(signals, index=df.index)
            else:
                return {'error': '信号格式错误'}
        
        # 检查是否有有效信号
        if not signals.any():
            return {'error': '无有效信号'}
            
        results = backtester.run_backtest(df, signals)
        return json.loads(json.dumps(results, default=lambda x: x.item() if isinstance(x, (np.integer, np.floating)) else bool(x) if isinstance(x, np.bool_) else None))
    except Exception as e:
        print(f"回测分析失败: {e}")
        return {'error': f'回测失败: {str(e)}'}

def _prepare_chart_data(df: pd.DataFrame, signals: pd.Series, backtest_results: Dict) -> Dict:
    """【修复图表空白问题】准备图表专用数据，智能处理NaN值以确保图表正常显示，并添加信号点数据"""
    
    df_reset = df.reset_index()
    df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d')
    
    # K线数据处理（K线数据通常不会有NaN）
    kline = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
    
    # 确保所有指标列都存在
    indicator_cols = ['date', 'ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']
    for col in indicator_cols:
        if col not in df_reset.columns:
            df_reset[col] = None
    
    # --- [关键修复] 智能处理技术指标的NaN值 ---
    # 对于移动平均线，使用前向填充，如果前面没有数据则使用当前收盘价
    ma_cols = ['ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240']
    for ma_col in ma_cols:
        if ma_col in df_reset.columns:
            # 先尝试前向填充（使用新的pandas方法）
            df_reset[ma_col] = df_reset[ma_col].ffill()
            # 如果还有NaN（开头部分），用收盘价填充
            df_reset[ma_col] = df_reset[ma_col].fillna(df_reset['close'])
    
    # 对于KDJ指标，使用合理的默认值
    kdj_cols = ['k', 'd', 'j']
    for kdj_col in kdj_cols:
        if kdj_col in df_reset.columns:
            # KDJ的合理默认值是50（中性位置）
            df_reset[kdj_col] = df_reset[kdj_col].fillna(50.0)
    
    # 对于RSI指标，使用合理的默认值
    rsi_cols = ['rsi6', 'rsi12', 'rsi24']
    for rsi_col in rsi_cols:
        if rsi_col in df_reset.columns:
            # RSI的合理默认值是50（中性位置）
            df_reset[rsi_col] = df_reset[rsi_col].fillna(50.0)
    
    # 对于MACD指标，使用0作为默认值
    macd_cols = ['dif', 'dea', 'macd']
    for macd_col in macd_cols:
        if macd_col in df_reset.columns:
            df_reset[macd_col] = df_reset[macd_col].fillna(0.0)
    
    # 转换为字典并处理剩余的NaN值
    indicator_data = df_reset[indicator_cols].to_dict('records')
    
    # 最后的安全检查：将任何剩余的NaN转换为None
    for record in indicator_data:
        for key, value in record.items():
            if pd.isna(value):
                record[key] = None
    
    # 生成信号点数据，包含回测结果
    signal_points = []
    
    # 确保signals是正确的格式
    if signals is not None:
        # 处理tuple格式的signals
        if isinstance(signals, tuple):
            signals = signals[0] if len(signals) > 0 else pd.Series([False] * len(df_reset), index=df_reset.index)
        
        # 确保signals是pandas Series且不为空
        if isinstance(signals, pd.Series) and not signals.empty and signals.any():
            try:
                signal_mask = signals.reindex(df_reset.index, fill_value=False)
                signal_dates = df_reset[signal_mask]['date'].tolist()
                signal_prices = df_reset[signal_mask]['close'].tolist()
        
                # 从回测结果中获取每个信号的状态
                signal_states = []
                if 'signal_details' in backtest_results:
                    for detail in backtest_results['signal_details']:
                        if detail.get('max_profit', 0) > 0.02:  # 收益超过2%认为成功
                            signal_states.append('SUCCESS')
                        elif detail.get('max_drawdown', 0) < -0.05:  # 回撤超过5%认为失败
                            signal_states.append('FAIL')
                        else:
                            signal_states.append('PENDING')
                
                # 确保状态数量与信号数量匹配
                while len(signal_states) < len(signal_dates):
                    signal_states.append('PENDING')
                
                for i, (date, price) in enumerate(zip(signal_dates, signal_prices)):
                    signal_point = {
                        'date': date,
                        'price': float(price),
                        'state': signal_states[i] if i < len(signal_states) else 'PENDING'
                    }
                    
                    # 添加收益信息
                    if 'signal_details' in backtest_results and i < len(backtest_results['signal_details']):
                        detail = backtest_results['signal_details'][i]
                        signal_point['profit'] = detail.get('max_profit', 0)
                        signal_point['drawdown'] = detail.get('max_drawdown', 0)
                    
                    signal_points.append(signal_point)
            except Exception as e:
                print(f"处理信号点数据时出错: {e}")
                # 如果处理失败，至少返回空的信号点列表
    
    return {'kline_data': kline, 'indicator_data': indicator_data, 'signal_points': signal_points}

def _get_stock_profile(stock_code: str) -> Optional[Dict]:
    # ... (此函数无需修改)
    try:
        return StockPoolManager().get_stock_by_code(stock_code)
    except Exception: return None

def _get_portfolio_info(stock_code: str) -> Optional[Dict]:
    # ... (此函数无需修改)
    try:
        pm = create_portfolio_manager()
        return next((p for p in pm.load_portfolio() if p['stock_code'] == stock_code), None)
    except Exception: return None
