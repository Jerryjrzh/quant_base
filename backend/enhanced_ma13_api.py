"""
增强MA13策略API接口

专门为优化后的enhanced_ma13_screener提供API接口
简化导入依赖，专注于增强筛选功能
"""

from flask import Blueprint, request, jsonify
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import traceback
from typing import List, Dict

logger = logging.getLogger(__name__)

# 创建蓝图
enhanced_ma13_bp = Blueprint('enhanced_ma13', __name__, url_prefix='/api/enhanced_ma13')

@enhanced_ma13_bp.route('/analyze', methods=['POST'])
def analyze_stock():
    """
    使用增强MA13筛选器分析股票
    
    POST /api/enhanced_ma13/analyze
    {
        "stock_code": "002021",
        "use_two_stage": false  // 可选，是否使用两阶段架构
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
        use_two_stage = data.get('use_two_stage', False)
        
        logger.info(f"开始增强分析股票 {stock_code} (两阶段: {use_two_stage})")
        
        # 导入增强筛选器
        try:
            from enhanced_ma13_screener import enhanced_ma13_screener
        except ImportError as e:
            logger.error(f"无法导入增强筛选器: {e}")
            return jsonify({
                'success': False,
                'message': '增强筛选器不可用'
            }), 500
        
        if use_two_stage:
            # 两阶段模式：先历史资格审查，再实时择时
            qualified_pool = enhanced_ma13_screener.run_historical_qualification([stock_code])
            if stock_code not in qualified_pool:
                return jsonify({
                    'success': False,
                    'message': f'股票 {stock_code} 未通过历史资格审查',
                    'stage1_qualification': 0,
                    'analysis_mode': 'two_stage_enhanced'
                })
            
            # 第二阶段分析
            screen_result = enhanced_ma13_screener.analyze_single_stock(
                stock_code, 
                stage1_qual=qualified_pool[stock_code]
            )
        else:
            # 单阶段增强模式
            screen_result = enhanced_ma13_screener.analyze_single_stock(stock_code)
        
        if screen_result is None:
            return jsonify({
                'success': False,
                'message': f'无法获取足够的股票数据: {stock_code}'
            }), 404
        
        # 转换为前端兼容格式
        result = _convert_enhanced_result_to_api_format(screen_result, use_two_stage)
        
        logger.info(f"股票 {stock_code} 增强分析完成: {result['success']}")
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"增强分析股票时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'增强分析过程中出错: {str(e)}'
        }), 500

@enhanced_ma13_bp.route('/batch_scan', methods=['POST'])
def batch_scan_stocks():
    """
    使用增强筛选器批量扫描股票
    
    POST /api/enhanced_ma13/batch_scan
    {
        "stock_codes": ["002021", "600618", "300739"],
        "use_two_stage": false
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
        use_two_stage = data.get('use_two_stage', False)
        
        if not isinstance(stock_codes, list) or len(stock_codes) == 0:
            return jsonify({
                'success': False,
                'message': '股票代码列表格式错误'
            }), 400
        
        logger.info(f"开始增强批量扫描 {len(stock_codes)} 只股票")
        
        # 导入增强筛选器
        try:
            from enhanced_ma13_screener import enhanced_ma13_screener
        except ImportError as e:
            logger.error(f"无法导入增强筛选器: {e}")
            return jsonify({
                'success': False,
                'message': '增强筛选器不可用'
            }), 500
        
        # 使用增强筛选器
        screen_results = enhanced_ma13_screener.screen_stocks(stock_codes, use_two_stage=use_two_stage)
        
        # 转换为API格式
        results = []
        qualified_stocks = []
        
        for screen_result in screen_results:
            api_result = _convert_enhanced_result_to_api_format(screen_result, use_two_stage)
            results.append(api_result)
            
            if api_result['success']:
                qualified_stocks.append(screen_result.stock_code)
        
        # 按总分排序
        results.sort(key=lambda x: x.get('enhanced_data', {}).get('total_score', 0), reverse=True)
        
        # 统计信息
        qualified_results = [r for r in results if r['success']]
        
        summary = {
            'total_scanned': len(stock_codes),
            'qualified_count': len(qualified_stocks),
            'qualified_rate': len(qualified_stocks) / len(stock_codes) * 100 if stock_codes else 0,
            'top_candidates': qualified_results[:10],
            'screening_method': 'enhanced_ma13_screener'
        }
        
        logger.info(f"增强批量扫描完成: {len(qualified_stocks)}/{len(stock_codes)} 只股票符合条件")
        
        # 确保summary中的数据是JSON可序列化的
        safe_summary = {
            'total_scanned': int(len(stock_codes)),
            'qualified_count': int(len(qualified_stocks)),
            'qualified_rate': float(len(qualified_stocks) / len(stock_codes) * 100 if stock_codes else 0),
            'top_candidates': qualified_results[:10],  # 这些已经通过_convert_enhanced_result_to_api_format处理过了
            'screening_method': 'enhanced_ma13_screener'
        }
        
        return jsonify({
            'success': True,
            'message': f'增强批量扫描完成，{len(qualified_stocks)}只股票符合条件',
            'summary': safe_summary,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"增强批量扫描时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'增强批量扫描时出错: {str(e)}'
        }), 500

@enhanced_ma13_bp.route('/full_market_scan', methods=['POST'])
def full_market_scan():
    """
    增强全市场扫描
    
    POST /api/enhanced_ma13/full_market_scan
    {
        "max_stocks": 500,
        "use_two_stage": false
    }
    """
    try:
        data = request.get_json() or {}
        max_stocks = data.get('max_stocks', 500)
        use_two_stage = data.get('use_two_stage', False)
        
        logger.info(f"开始增强全市场扫描，最大数量: {max_stocks}，两阶段: {use_two_stage}")
        
        # 获取股票代码列表
        try:
            from data_handler import get_all_stock_codes_from_filesystem
            all_codes = get_all_stock_codes_from_filesystem()
        except ImportError:
            # 使用简单的股票代码列表作为fallback
            all_codes = [
                'sh601388', 'sz002021', 'sz002796', 'sh688291', 'sz000001', 'sh600036',
                'sz000002', 'sh600519', 'sz000858', 'sh600036', 'sz002415', 'sh600276'
            ]
        
        # 过滤和限制数量
        filtered_codes = []
        for code in all_codes:
            if len(filtered_codes) >= max_stocks:
                break
            # 过滤掉一些不适合的股票
            if not any(x in code.upper() for x in ['ST', 'PT', '*']):
                filtered_codes.append(code)
        
        logger.info(f"实际扫描股票数量: {len(filtered_codes)}")
        
        # 导入增强筛选器
        try:
            from enhanced_ma13_screener import enhanced_ma13_screener
        except ImportError as e:
            logger.error(f"无法导入增强筛选器: {e}")
            return jsonify({
                'success': False,
                'message': '增强筛选器不可用'
            }), 500
        
        # 使用增强筛选器
        screen_results = enhanced_ma13_screener.screen_stocks(filtered_codes, use_two_stage=use_two_stage)
        
        # 转换为API格式
        results = []
        qualified_stocks = []
        
        for screen_result in screen_results:
            api_result = _convert_enhanced_result_to_api_format(screen_result, use_two_stage)
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
        
        logger.info(f"增强全市场扫描完成: {len(qualified_stocks)}/{len(filtered_codes)} 只股票符合条件")
        
        # 确保所有数据都是JSON可序列化的
        safe_summary = {}
        if isinstance(summary, dict):
            for k, v in summary.items():
                if isinstance(v, (int, float, str, bool, type(None))):
                    safe_summary[k] = v
                else:
                    safe_summary[k] = str(v)
        
        return jsonify({
            'success': True,
            'message': f'增强全市场扫描完成，{len(qualified_stocks)}只股票符合条件',
            'summary': safe_summary,
            'results': results,
            'scan_stats': {
                'total_stocks': int(len(all_codes)),
                'filtered_stocks': int(len(filtered_codes)),
                'processed_stocks': int(len(filtered_codes)),
                'qualified_stocks': int(len(qualified_stocks)),
                'stage_distribution': dict(stage_stats),
                'model_distribution': dict(model_stats),
                'phase_distribution': dict(phase_stats)
            },
            'enhanced_features': {
                'daily_four_stage_screening': True,
                'hourly_dual_model_scoring': True,
                'market_phase_analysis': True,
                'confluence_scoring': True,
                'two_stage_architecture': bool(use_two_stage)
            }
        })
        
    except Exception as e:
        logger.error(f"增强全市场扫描时出错: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'增强全市场扫描时出错: {str(e)}'
        }), 500

def _convert_enhanced_result_to_api_format(screen_result, use_two_stage=False):
    """
    将增强筛选器结果转换为前端兼容的API格式
    
    Args:
        screen_result: EnhancedMA13Screener的结果
        use_two_stage: 是否使用两阶段模式
        
    Returns:
        前端兼容的结果格式
    """
    try:
        # 安全获取属性，避免AttributeError
        def safe_get_attr(obj, attr, default=None):
            try:
                return getattr(obj, attr, default)
            except:
                return default
        
        def safe_get_dict(d, key, default=None):
            try:
                return d.get(key, default) if isinstance(d, dict) else default
            except:
                return default
        
        # 基础成功判断
        daily_qualified = safe_get_attr(screen_result, 'daily_qualified', False)
        total_score = safe_get_attr(screen_result, 'total_score', 0)
        success = bool(daily_qualified and total_score >= 60)
        
        # 安全获取各种属性
        stock_code = safe_get_attr(screen_result, 'stock_code', '')
        daily_score = safe_get_attr(screen_result, 'daily_score', 0)
        hourly_score = safe_get_attr(screen_result, 'hourly_score', 0)
        daily_stage = safe_get_attr(screen_result, 'daily_stage', '')
        hourly_model = safe_get_attr(screen_result, 'hourly_model', '')
        market_phase = safe_get_attr(screen_result, 'market_phase', '')
        confidence = safe_get_attr(screen_result, 'confidence', 0)
        recommendation = safe_get_attr(screen_result, 'recommendation', {})
        key_levels = safe_get_attr(screen_result, 'key_levels', {})
        hourly_signals = safe_get_attr(screen_result, 'hourly_signals', [])
        
        # 确保所有数值都是JSON可序列化的
        daily_score = float(daily_score) if daily_score is not None else 0.0
        hourly_score = float(hourly_score) if hourly_score is not None else 0.0
        total_score = float(total_score) if total_score is not None else 0.0
        confidence = float(confidence) if confidence is not None else 0.0
        
        # 构建前端兼容的结果
        result = {
            'success': bool(success),
            'stock_code': str(stock_code),
            'analysis_mode': 'two_stage_enhanced' if use_two_stage else 'single_stage_enhanced',
            'message': f'总分 {total_score:.1f}，{"符合" if success else "不符合"}条件',
            
            # 阶段分析（前端兼容格式）
            'stage_1': {
                'qualified': bool(daily_score >= 30),
                'score': daily_score,
                'stage': str(daily_stage),
                'description': '底部稳定分析'
            },
            'stage_2': {
                'qualified': bool(hourly_score >= 25),
                'score': hourly_score,
                'model': str(hourly_model),
                'description': '小时线模型确认'
            },
            'stage_3': {
                'qualified': bool(success),
                'score': total_score,
                'phase': str(market_phase),
                'description': '综合评分'
            },
            
            # 信号分析
            'signals': {
                'signal_strength': min(float(total_score), 100.0),
                'oversold_model': bool(hourly_model == 'oversold_rebound'),
                'continuation_model': bool(hourly_model == 'continuation_confirm'),
                'hourly_signals': list(hourly_signals) if hourly_signals else [],
                'market_phase': str(market_phase)
            },
            
            # 操作建议
            'recommendation': {
                'action': str(safe_get_dict(recommendation, 'action', 'wait')),
                'position_size': float(safe_get_dict(recommendation, 'position_size', 0)),
                'confidence': float(confidence * 100),
                'entry_timing': str(hourly_model or 'wait'),
                'hold_days': str(safe_get_dict(recommendation, 'hold_days', '3-8天')),
                'risk_reward_ratio': float(safe_get_dict(recommendation, 'risk_reward_ratio', 0))
            },
            
            # 关键价位
            'key_levels': dict(key_levels) if key_levels else {},
            
            # 当前数据
            'current_data': {
                'date': datetime.now().strftime('%Y-%m-%d'),
                'price': float(safe_get_dict(key_levels, 'current_price', 0)),
                'ma13': float(safe_get_dict(key_levels, 'support_1_upper', 0)),
                'ma30': float(safe_get_dict(key_levels, 'support_2_upper', 0)),
                'volume': 0.0  # 需要从原始数据获取
            },
            
            # 增强数据（新增）
            'enhanced_data': {
                'daily_stage': str(daily_stage),
                'daily_score': daily_score,
                'hourly_model': str(hourly_model),
                'hourly_score': hourly_score,
                'market_phase': str(market_phase),
                'total_score': total_score,
                'confidence': confidence,
                'stage1_qualification': float(safe_get_attr(screen_result, 'stage1_qualification', 0)) if safe_get_attr(screen_result, 'stage1_qualification') is not None else None
            }
        }
        
        return result
        
    except Exception as e:
        logger.error(f"数据转换出错: {str(e)}")
        # 返回一个安全的默认结果
        return {
            'success': False,
            'stock_code': str(getattr(screen_result, 'stock_code', '')),
            'analysis_mode': 'error',
            'message': f'数据转换失败: {str(e)}',
            'stage_1': {'qualified': False, 'score': 0, 'stage': '', 'description': '底部稳定分析'},
            'stage_2': {'qualified': False, 'score': 0, 'model': '', 'description': '小时线模型确认'},
            'stage_3': {'qualified': False, 'score': 0, 'phase': '', 'description': '综合评分'},
            'signals': {'signal_strength': 0, 'oversold_model': False, 'continuation_model': False, 'hourly_signals': [], 'market_phase': ''},
            'recommendation': {'action': 'wait', 'position_size': 0, 'confidence': 0, 'entry_timing': 'wait', 'hold_days': '3-8天', 'risk_reward_ratio': 0},
            'key_levels': {},
            'current_data': {'date': datetime.now().strftime('%Y-%m-%d'), 'price': 0, 'ma13': 0, 'ma30': 0, 'volume': 0},
            'enhanced_data': {'daily_stage': '', 'daily_score': 0, 'hourly_model': '', 'hourly_score': 0, 'market_phase': '', 'total_score': 0, 'confidence': 0, 'stage1_qualification': None}
        }

# 注册错误处理器
@enhanced_ma13_bp.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'message': '接口不存在'
    }), 404

@enhanced_ma13_bp.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'message': '服务器内部错误'
    }), 500