"""
MA13短线策略API接口

为MA13短线交易策略提供REST API接口
集成到现有的Flask应用中
"""

from flask import Blueprint, request, jsonify
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import traceback
import sys
import os
from typing import List

# 添加当前目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from strategies.ma13_short_term_strategy import MA13ShortTermStrategy
from short_term_execution_planner import ShortTermExecutionPlanner
from data_handler import DataHandler, get_full_data_with_indicators
import indicators

logger = logging.getLogger(__name__)

# 创建蓝图
ma13_bp = Blueprint('ma13_strategy', __name__, url_prefix='/api/ma13')

# 全局实例
strategy = MA13ShortTermStrategy()
planner = ShortTermExecutionPlanner()
data_handler = DataHandler()

@ma13_bp.route('/analyze', methods=['POST'])
def analyze_stock():
    """
    分析股票是否符合MA13短线策略
    
    POST /api/ma13/analyze
    {
        "stock_code": "002021",
        "days": 150  // 可选，默认150天
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'stock_code' not in data:
            return jsonify({
                'success': False,
                'message': '缺少股票代码参数'
            }), 400
        
        stock_code = data['stock_code']
        days = data.get('days', 150)
        
        logger.info(f"开始分析股票 {stock_code} 的MA13策略")
        
        # 获取股票数据（使用统一接口，已包含所有技术指标）
        df = get_full_data_with_indicators(stock_code)
        
        if df is None or len(df) < 100:
            return jsonify({
                'success': False,
                'message': f'无法获取足够的股票数据: {stock_code}'
            }), 404
        
        # 如果需要限制天数，截取最近的数据
        if days < len(df):
            df = df.tail(days).copy()
        
        # 运行策略分析
        result = strategy.analyze_stock(df, stock_code)
        
        # 添加额外信息
        if result['success']:
            latest = df.iloc[-1]
            result['current_data'] = {
                'date': latest['date'],
                'price': latest['close'],
                'ma13': latest.get('ma13', 0),
                'ma30': latest.get('ma30', 0),
                'rsi6': latest.get('rsi6', 0),
                'kdj_j': latest.get('j', 0),
                'volume': latest['volume']
            }
        
        logger.info(f"股票 {stock_code} 分析完成: {result['success']}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"分析股票时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'分析过程中出错: {str(e)}'
        }), 500

@ma13_bp.route('/execution_plan', methods=['POST'])
def generate_execution_plan():
    """
    生成执行计划
    
    POST /api/ma13/execution_plan
    {
        "stock_code": "002021",
        "days": 150  // 可选，默认150天
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'stock_code' not in data:
            return jsonify({
                'success': False,
                'message': '缺少股票代码参数'
            }), 400
        
        stock_code = data['stock_code']
        days = data.get('days', 150)
        
        logger.info(f"开始生成股票 {stock_code} 的执行计划")
        
        # 获取股票数据（使用统一接口，已包含所有技术指标）
        df = get_full_data_with_indicators(stock_code)
        
        if df is None or len(df) < 100:
            return jsonify({
                'success': False,
                'message': f'无法获取足够的股票数据: {stock_code}'
            }), 404
        
        # 如果需要限制天数，截取最近的数据
        if days < len(df):
            df = df.tail(days).copy()
        
        # 先运行策略分析
        strategy_result = strategy.analyze_stock(df, stock_code)
        
        if not strategy_result['success']:
            return jsonify({
                'success': False,
                'message': f'策略分析未通过: {strategy_result["message"]}'
            }), 400
        
        # 生成执行计划
        plan_result = planner.generate_execution_plan(df, strategy_result, stock_code)
        
        logger.info(f"股票 {stock_code} 执行计划生成完成: {plan_result['success']}")
        return jsonify(plan_result)
        
    except Exception as e:
        logger.error(f"生成执行计划时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'生成执行计划时出错: {str(e)}'
        }), 500

@ma13_bp.route('/batch_scan', methods=['POST'])
def batch_scan_stocks():
    """
    批量扫描股票
    
    POST /api/ma13/batch_scan
    {
        "stock_codes": ["002021", "600618", "300739"],
        "days": 150  // 可选，默认150天
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'stock_codes' not in data:
            return jsonify({
                'success': False,
                'message': '缺少股票代码列表参数'
            }), 400
        
        stock_codes = data['stock_codes']
        days = data.get('days', 150)
        
        if not isinstance(stock_codes, list) or len(stock_codes) == 0:
            return jsonify({
                'success': False,
                'message': '股票代码列表格式错误'
            }), 400
        
        logger.info(f"开始批量扫描 {len(stock_codes)} 只股票")
        
        results = []
        qualified_stocks = []
        
        for stock_code in stock_codes:
            try:
                # 获取股票数据（使用统一接口，已包含所有技术指标）
                df = get_full_data_with_indicators(stock_code)
                
                if df is None or len(df) < 100:
                    results.append({
                        'stock_code': stock_code,
                        'success': False,
                        'message': '数据不足'
                    })
                    continue
                
                # 如果需要限制天数，截取最近的数据
                if days < len(df):
                    df = df.tail(days).copy()
                
                # 运行策略分析
                result = strategy.analyze_stock(df, stock_code)
                
                # 添加当前价格信息
                if result['success']:
                    latest = df.iloc[-1]
                    result['current_price'] = latest['close']
                    result['current_date'] = latest['date']
                    
                    # 计算关键指标
                    recommendation = result.get('recommendation', {})
                    result['summary'] = {
                        'action': recommendation.get('action', 'wait'),
                        'confidence': recommendation.get('confidence', 0),
                        'position_size': recommendation.get('position_size', 0),
                        'signal_strength': result.get('signals', {}).get('signal_strength', 0)
                    }
                    
                    qualified_stocks.append(stock_code)
                
                results.append(result)
                
            except Exception as e:
                logger.error(f"扫描股票 {stock_code} 时出错: {str(e)}")
                results.append({
                    'stock_code': stock_code,
                    'success': False,
                    'message': f'分析出错: {str(e)}'
                })
        
        # 按信心度排序
        qualified_results = [r for r in results if r.get('success', False)]
        qualified_results.sort(
            key=lambda x: x.get('summary', {}).get('confidence', 0), 
            reverse=True
        )
        
        summary = {
            'total_scanned': len(stock_codes),
            'qualified_count': len(qualified_stocks),
            'qualified_rate': len(qualified_stocks) / len(stock_codes) * 100,
            'top_candidates': qualified_results[:5]  # 前5名候选
        }
        
        logger.info(f"批量扫描完成: {len(qualified_stocks)}/{len(stock_codes)} 只股票符合条件")
        
        return jsonify({
            'success': True,
            'message': f'批量扫描完成，{len(qualified_stocks)}只股票符合条件',
            'summary': summary,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"批量扫描时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'批量扫描时出错: {str(e)}'
        }), 500

@ma13_bp.route('/strategy_info', methods=['GET'])
def get_strategy_info():
    """
    获取策略信息
    
    GET /api/ma13/strategy_info
    """
    try:
        strategy_info = strategy.get_strategy_info()
        planner_info = {
            'name': planner.name,
            'version': planner.version,
            'parameters': planner.params
        }
        
        return jsonify({
            'success': True,
            'strategy': strategy_info,
            'planner': planner_info,
            'api_version': '1.0',
            'last_updated': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"获取策略信息时出错: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取策略信息时出错: {str(e)}'
        }), 500

@ma13_bp.route('/all_stocks', methods=['GET'])
def get_all_stocks():
    """
    获取所有可用的股票代码
    
    GET /api/ma13/all_stocks
    """
    try:
        from data_handler import get_all_stock_codes_from_filesystem
        
        # 获取所有股票代码
        all_codes = get_all_stock_codes_from_filesystem()
        
        # 过滤掉一些不适合的股票（可选）
        filtered_codes = []
        for code in all_codes:
            # 过滤掉ST股票、退市股票等
            if not any(x in code.upper() for x in ['ST', 'PT', '*']):
                filtered_codes.append(code)
        
        logger.info(f"获取股票代码列表: 总数 {len(all_codes)}, 过滤后 {len(filtered_codes)}")
        
        return jsonify({
            'success': True,
            'total_count': len(all_codes),
            'filtered_count': len(filtered_codes),
            'stock_codes': filtered_codes[:1000],  # 限制返回数量，避免响应过大
            'message': f'成功获取 {len(filtered_codes)} 只股票代码'
        })
        
    except Exception as e:
        logger.error(f"获取股票代码列表时出错: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取股票代码列表时出错: {str(e)}'
        }), 500

@ma13_bp.route('/full_market_scan', methods=['POST'])
def full_market_scan():
    """
    全市场扫描 - 使用增强版MA13筛选器
    
    POST /api/ma13/full_market_scan
    {
        "max_stocks": 500,  // 可选，最大扫描数量
        "days": 150,  // 可选，分析天数
        "use_enhanced_screener": true  // 可选，是否使用增强筛选器
    }
    """
    try:
        data = request.get_json() or {}
        max_stocks = data.get('max_stocks', 500)
        days = data.get('days', 150)
        use_enhanced = data.get('use_enhanced_screener', True)
        
        logger.info(f"开始全市场扫描，最大数量: {max_stocks}，增强模式: {use_enhanced}")
        
        from data_handler import get_all_stock_codes_from_filesystem
        
        # 获取所有股票代码
        all_codes = get_all_stock_codes_from_filesystem()
        
        # 过滤和限制数量
        filtered_codes = []
        for code in all_codes:
            if len(filtered_codes) >= max_stocks:
                break
            # 过滤掉一些不适合的股票
            if not any(x in code.upper() for x in ['ST', 'PT', '*']):
                filtered_codes.append(code)
        
        logger.info(f"实际扫描股票数量: {len(filtered_codes)}")
        
        if use_enhanced:
            # 使用增强版筛选器
            return _enhanced_market_scan(filtered_codes, all_codes)
        else:
            # 使用原版筛选逻辑
            return _legacy_market_scan(filtered_codes, all_codes, days)
        
    except Exception as e:
        logger.error(f"全市场扫描时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'全市场扫描时出错: {str(e)}'
        }), 500

def _enhanced_market_scan(filtered_codes: List[str], all_codes: List[str]) -> dict:
    """
    增强版市场扫描
    
    Args:
        filtered_codes: 过滤后的股票代码列表
        all_codes: 所有股票代码列表
        
    Returns:
        扫描结果
    """
    from enhanced_ma13_screener import enhanced_ma13_screener
    
    logger.info("使用增强版MA13筛选器进行扫描")
    
    # 使用增强筛选器
    screen_results = enhanced_ma13_screener.screen_stocks(filtered_codes)
    
    # 转换为API格式
    results = []
    qualified_stocks = []
    
    for screen_result in screen_results:
        api_result = {
            'stock_code': screen_result.stock_code,
            'success': screen_result.total_score >= 70,
            'current_price': screen_result.key_levels.get('current_price', 0),
            'current_date': datetime.now().strftime('%Y-%m-%d'),
            'summary': {
                'action': screen_result.recommendation.get('action', 'wait'),
                'confidence': screen_result.confidence * 100,
                'position_size': screen_result.recommendation.get('position_size', 0),
                'signal_strength': screen_result.total_score
            },
            'enhanced_data': {
                'daily_stage': screen_result.daily_stage,
                'daily_score': screen_result.daily_score,
                'hourly_model': screen_result.hourly_model,
                'hourly_score': screen_result.hourly_score,
                'market_phase': screen_result.market_phase,
                'total_score': screen_result.total_score,
                'key_levels': screen_result.key_levels,
                'hourly_signals': screen_result.hourly_signals
            }
        }
        
        results.append(api_result)
        
        if api_result['success']:
            qualified_stocks.append(screen_result.stock_code)
    
    # 按总分排序
    results.sort(key=lambda x: x.get('enhanced_data', {}).get('total_score', 0), reverse=True)
    
    # 统计信息
    qualified_results = [r for r in results if r['success']]
    
    summary = {
        'total_scanned': len(filtered_codes),
        'qualified_count': len(qualified_stocks),
        'qualified_rate': len(qualified_stocks) / len(filtered_codes) * 100 if filtered_codes else 0,
        'top_candidates': qualified_results[:10],
        'screening_method': 'enhanced_ma13_screener'
    }
    
    # 增强统计信息
    stage_stats = {}
    model_stats = {}
    phase_stats = {}
    
    for result in results:
        enhanced = result.get('enhanced_data', {})
        
        # 日线阶段统计
        stage = enhanced.get('daily_stage', 'unknown')
        stage_stats[stage] = stage_stats.get(stage, 0) + 1
        
        # 小时线模型统计
        model = enhanced.get('hourly_model', 'unknown')
        model_stats[model] = model_stats.get(model, 0) + 1
        
        # 市场阶段统计
        phase = enhanced.get('market_phase', 'unknown')
        phase_stats[phase] = phase_stats.get(phase, 0) + 1
    
    logger.info(f"增强扫描完成: {len(qualified_stocks)}/{len(filtered_codes)} 只股票符合条件")
    
    return jsonify({
        'success': True,
        'message': f'增强扫描完成，{len(qualified_stocks)}只股票符合条件',
        'summary': summary,
        'results': results,
        'scan_stats': {
            'total_stocks': len(all_codes),
            'filtered_stocks': len(filtered_codes),
            'processed_stocks': len(filtered_codes),
            'qualified_stocks': len(qualified_stocks),
            'stage_distribution': stage_stats,
            'model_distribution': model_stats,
            'phase_distribution': phase_stats
        },
        'enhanced_features': {
            'daily_four_stage_screening': True,
            'hourly_dual_model_scoring': True,
            'market_phase_analysis': True,
            'confluence_scoring': True
        }
    })

def _legacy_market_scan(filtered_codes: List[str], all_codes: List[str], days: int) -> dict:
    """
    原版市场扫描（保持向后兼容）
    
    Args:
        filtered_codes: 过滤后的股票代码列表
        all_codes: 所有股票代码列表
        days: 分析天数
        
    Returns:
        扫描结果
    """
    logger.info("使用原版MA13策略进行扫描")
    
    # 调用批量扫描逻辑
    results = []
    qualified_stocks = []
    processed_count = 0
    
    for stock_code in filtered_codes:
        try:
            processed_count += 1
            
            # 每处理50只股票记录一次进度
            if processed_count % 50 == 0:
                logger.info(f"扫描进度: {processed_count}/{len(filtered_codes)}")
            
            # 获取股票数据（使用统一接口，已包含所有技术指标）
            df = get_full_data_with_indicators(stock_code)
            
            if df is None or len(df) < 100:
                results.append({
                    'stock_code': stock_code,
                    'success': False,
                    'message': '数据不足'
                })
                continue
            
            # 如果需要限制天数，截取最近的数据
            if days < len(df):
                df = df.tail(days).copy()
            
            # 运行策略分析
            result = strategy.analyze_stock(df, stock_code)
            
            # 添加当前价格信息
            if result['success']:
                latest = df.iloc[-1]
                result['current_price'] = latest['close']
                result['current_date'] = latest.name.strftime('%Y-%m-%d') if hasattr(latest.name, 'strftime') else str(latest.name)
                
                # 计算关键指标
                recommendation = result.get('recommendation', {})
                result['summary'] = {
                    'action': recommendation.get('action', 'wait'),
                    'confidence': recommendation.get('confidence', 0),
                    'position_size': recommendation.get('position_size', 0),
                    'signal_strength': result.get('signals', {}).get('signal_strength', 0)
                }
                
                qualified_stocks.append(stock_code)
            
            results.append(result)
            
        except Exception as e:
            logger.error(f"扫描股票 {stock_code} 时出错: {str(e)}")
            results.append({
                'stock_code': stock_code,
                'success': False,
                'message': f'分析出错: {str(e)}'
            })
    
    # 按信心度排序
    qualified_results = [r for r in results if r.get('success', False)]
    qualified_results.sort(
        key=lambda x: x.get('summary', {}).get('confidence', 0), 
        reverse=True
    )
    
    summary = {
        'total_scanned': len(filtered_codes),
        'qualified_count': len(qualified_stocks),
        'qualified_rate': len(qualified_stocks) / len(filtered_codes) * 100 if filtered_codes else 0,
        'top_candidates': qualified_results[:10],
        'screening_method': 'legacy_ma13_strategy'
    }
    
    logger.info(f"原版扫描完成: {len(qualified_stocks)}/{len(filtered_codes)} 只股票符合条件")
    
    return jsonify({
        'success': True,
        'message': f'全市场扫描完成，{len(qualified_stocks)}只股票符合条件',
        'summary': summary,
        'results': results,
        'scan_stats': {
            'total_stocks': len(all_codes),
            'filtered_stocks': len(filtered_codes),
            'processed_stocks': processed_count,
            'qualified_stocks': len(qualified_stocks)
        }
    })

@ma13_bp.route('/backtest', methods=['POST'])
def run_backtest():
    """
    运行回测
    
    POST /api/ma13/backtest
    {
        "stock_code": "002021",
        "start_date": "2025-01-01",
        "end_date": "2025-09-12",
        "initial_capital": 100000
    }
    """
    try:
        data = request.get_json()
        
        if not data or 'stock_code' not in data:
            return jsonify({
                'success': False,
                'message': '缺少股票代码参数'
            }), 400
        
        stock_code = data['stock_code']
        start_date = data.get('start_date', '2025-01-01')
        end_date = data.get('end_date', datetime.now().strftime('%Y-%m-%d'))
        initial_capital = data.get('initial_capital', 100000)
        
        logger.info(f"开始回测股票 {stock_code}: {start_date} - {end_date}")
        
        # 获取历史数据（使用统一接口，已包含所有技术指标）
        df = get_full_data_with_indicators(stock_code)
        
        if df is None or len(df) < 50:
            return jsonify({
                'success': False,
                'message': f'回测数据不足: {stock_code}'
            }), 404
        
        # 根据日期范围筛选数据
        df = df[(df.index >= start_date) & (df.index <= end_date)]
        
        if len(df) < 50:
            return jsonify({
                'success': False,
                'message': f'指定日期范围内数据不足: {stock_code}'
            }), 404
        
        # 运行回测
        backtest_result = _run_ma13_backtest(df, stock_code, initial_capital)
        
        logger.info(f"股票 {stock_code} 回测完成")
        return jsonify(backtest_result)
        
    except Exception as e:
        logger.error(f"回测时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'回测时出错: {str(e)}'
        }), 500

# 注意：_calculate_all_indicators 函数已移除
# 因为 get_full_data_with_indicators 统一接口已包含所有技术指标计算

def _run_ma13_backtest(df, stock_code, initial_capital):
    """运行MA13策略回测"""
    try:
        trades = []
        positions = []
        current_position = None
        capital = initial_capital
        
        # 滑动窗口分析
        window_size = 150
        
        for i in range(window_size, len(df)):
            window_df = df.iloc[i-window_size:i+1].copy().reset_index(drop=True)
            current_date = window_df.iloc[-1]['date']
            current_price = window_df.iloc[-1]['close']
            
            # 运行策略分析
            result = strategy.analyze_stock(window_df, stock_code)
            
            if result['success']:
                recommendation = result.get('recommendation', {})
                action = recommendation.get('action', 'wait')
                confidence = recommendation.get('confidence', 0)
                
                # 买入信号
                if action in ['buy_light', 'buy_heavy'] and current_position is None:
                    position_size = recommendation.get('position_size', 0.3)
                    shares = int(capital * position_size / current_price)
                    
                    if shares > 0:
                        cost = shares * current_price
                        capital -= cost
                        
                        current_position = {
                            'entry_date': current_date,
                            'entry_price': current_price,
                            'shares': shares,
                            'cost': cost,
                            'stop_loss': result.get('key_levels', {}).get('stop_loss', current_price * 0.95),
                            'target_1': result.get('key_levels', {}).get('target_1', current_price * 1.1),
                            'target_2': result.get('key_levels', {}).get('target_2', current_price * 1.2),
                            'max_hold_days': 10,
                            'entry_day': i
                        }
                        
                        positions.append(current_position.copy())
            
            # 卖出信号检查
            if current_position is not None:
                hold_days = i - current_position['entry_day']
                
                # 止损
                if current_price <= current_position['stop_loss']:
                    sell_reason = 'stop_loss'
                # 止盈
                elif current_price >= current_position['target_2']:
                    sell_reason = 'take_profit_2'
                elif current_price >= current_position['target_1'] and hold_days >= 3:
                    sell_reason = 'take_profit_1'
                # 超时
                elif hold_days >= current_position['max_hold_days']:
                    sell_reason = 'timeout'
                else:
                    sell_reason = None
                
                if sell_reason:
                    # 执行卖出
                    sell_value = current_position['shares'] * current_price
                    capital += sell_value
                    
                    profit = sell_value - current_position['cost']
                    profit_pct = profit / current_position['cost']
                    
                    trade = {
                        'entry_date': current_position['entry_date'],
                        'exit_date': current_date,
                        'entry_price': current_position['entry_price'],
                        'exit_price': current_price,
                        'shares': current_position['shares'],
                        'cost': current_position['cost'],
                        'sell_value': sell_value,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'hold_days': hold_days,
                        'sell_reason': sell_reason
                    }
                    
                    trades.append(trade)
                    current_position = None
        
        # 计算回测统计
        if trades:
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t['profit'] > 0])
            win_rate = winning_trades / total_trades
            
            total_profit = sum(t['profit'] for t in trades)
            total_return = total_profit / initial_capital
            
            avg_profit_pct = np.mean([t['profit_pct'] for t in trades])
            avg_hold_days = np.mean([t['hold_days'] for t in trades])
            
            max_profit = max(t['profit'] for t in trades)
            max_loss = min(t['profit'] for t in trades)
            
            final_capital = capital
            if current_position:  # 如果还有持仓
                final_price = df.iloc[-1]['close']
                final_capital += current_position['shares'] * final_price
        else:
            total_trades = 0
            win_rate = 0
            total_return = 0
            avg_profit_pct = 0
            avg_hold_days = 0
            max_profit = 0
            max_loss = 0
            final_capital = capital
        
        return {
            'success': True,
            'stock_code': stock_code,
            'backtest_period': f"{df.iloc[0]['date']} - {df.iloc[-1]['date']}",
            'initial_capital': initial_capital,
            'final_capital': final_capital,
            'total_return': total_return,
            'total_return_pct': total_return * 100,
            'statistics': {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'win_rate': win_rate * 100,
                'avg_profit_pct': avg_profit_pct * 100,
                'avg_hold_days': avg_hold_days,
                'max_profit': max_profit,
                'max_loss': max_loss
            },
            'trades': trades[-10:] if trades else [],  # 最近10笔交易
            'all_trades_count': len(trades)
        }
        
    except Exception as e:
        logger.error(f"回测执行出错: {str(e)}")
        return {
            'success': False,
            'message': f'回测执行出错: {str(e)}'
        }

# 注册错误处理器
@ma13_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': '接口不存在'
    }), 404

@ma13_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': '服务器内部错误'
    }), 500