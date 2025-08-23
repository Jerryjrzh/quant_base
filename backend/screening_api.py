#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
筛选API接口
为前端提供策略管理和筛选功能的REST API
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Any

from universal_screener import UniversalScreener
from strategy_manager import strategy_manager
from config_manager import config_manager
from stock_info_crawler import get_multiple_stock_info

# 创建Flask应用
app = Flask(__name__)
CORS(app)  # 启用跨域支持

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局筛选器实例
screener = UniversalScreener()


@app.route('/api/strategies', methods=['GET'])
def get_strategies():
    """获取所有可用策略"""
    try:
        strategies_list = screener.get_available_strategies()
        
        # 转换为字典格式，以策略ID为键
        strategies_dict = {}
        for strategy in strategies_list:
            strategy_id = strategy.get('id')
            if strategy_id:
                strategies_dict[strategy_id] = strategy
        
        return jsonify({
            'success': True,
            'data': strategies_dict,
            'total': len(strategies_dict)
        })
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/strategies/<strategy_id>', methods=['GET'])
def get_strategy_detail(strategy_id):
    """获取策略详细信息"""
    try:
        strategy = strategy_manager.get_strategy_instance(strategy_id)
        if strategy is None:
            return jsonify({
                'success': False,
                'error': f'策略不存在: {strategy_id}'
            }), 404
        
        strategy_info = strategy.get_strategy_info()
        return jsonify({
            'success': True,
            'data': strategy_info
        })
    except Exception as e:
        logger.error(f"获取策略详情失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/strategies/<strategy_id>/enable', methods=['POST'])
def enable_strategy(strategy_id):
    """启用策略"""
    try:
        strategy_manager.enable_strategy(strategy_id)
        return jsonify({
            'success': True,
            'message': f'策略已启用: {strategy_id}'
        })
    except Exception as e:
        logger.error(f"启用策略失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/strategies/<strategy_id>/disable', methods=['POST'])
def disable_strategy(strategy_id):
    """禁用策略"""
    try:
        strategy_manager.disable_strategy(strategy_id)
        return jsonify({
            'success': True,
            'message': f'策略已禁用: {strategy_id}'
        })
    except Exception as e:
        logger.error(f"禁用策略失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/strategies/<strategy_id>/config', methods=['GET'])
def get_strategy_config(strategy_id):
    """获取策略配置"""
    try:
        config = strategy_manager.strategy_configs.get(strategy_id, {})
        return jsonify({
            'success': True,
            'data': config
        })
    except Exception as e:
        logger.error(f"获取策略配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/strategies/<strategy_id>/config', methods=['PUT'])
def update_strategy_config(strategy_id):
    """更新策略配置"""
    try:
        config = request.get_json()
        if not config:
            return jsonify({
                'success': False,
                'error': '配置数据不能为空'
            }), 400
        
        strategy_manager.update_strategy_config(strategy_id, config)
        return jsonify({
            'success': True,
            'message': f'策略配置已更新: {strategy_id}'
        })
    except Exception as e:
        logger.error(f"更新策略配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/screening/start', methods=['POST'])
def start_screening():
    """开始筛选"""
    try:
        data = request.get_json() or {}
        selected_strategies = data.get('strategies', None)
        
        # 运行筛选
        results = screener.run_screening(selected_strategies)
        
        # 保存结果
        saved_files = screener.save_results(results)
        
        return jsonify({
            'success': True,
            'data': {
                'total_signals': len(results),
                'results': [result.to_dict() for result in results[:50]],  # 限制返回数量
                'saved_files': saved_files,
                'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        logger.error(f"筛选失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/screening/status', methods=['GET'])
def get_screening_status():
    """获取筛选状态"""
    try:
        # 这里可以实现筛选进度跟踪
        return jsonify({
            'success': True,
            'data': {
                'status': 'idle',  # idle, running, completed, error
                'progress': 0,
                'message': '就绪'
            }
        })
    except Exception as e:
        logger.error(f"获取筛选状态失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/screening/results', methods=['GET'])
def get_screening_results():
    """获取筛选结果"""
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('page_size', 20))
        strategy_filter = request.args.get('strategy', None)
        signal_type_filter = request.args.get('signal_type', None)
        
        # 过滤结果
        filtered_results = screener.results
        
        if strategy_filter:
            filtered_results = [r for r in filtered_results if r.strategy_name == strategy_filter]
        
        if signal_type_filter:
            filtered_results = [r for r in filtered_results if r.signal_type == signal_type_filter]
        
        # 分页
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_results = filtered_results[start_idx:end_idx]
        
        return jsonify({
            'success': True,
            'data': {
                'results': [result.to_dict() for result in page_results],
                'pagination': {
                    'page': page,
                    'page_size': page_size,
                    'total': len(filtered_results),
                    'total_pages': (len(filtered_results) + page_size - 1) // page_size
                }
            }
        })
    except Exception as e:
        logger.error(f"获取筛选结果失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/strategies/<path:strategy_id>/stocks', methods=['GET'])
def get_strategy_stocks(strategy_id):
    """获取指定策略的股票列表"""
    try:
        # URL解码策略ID（处理中文字符）
        from urllib.parse import unquote
        strategy_id = unquote(strategy_id)
        
        logger.info(f"获取策略股票列表: {strategy_id}")
        
        # 验证策略是否存在
        available_strategies = strategy_manager.get_available_strategies()
        strategy_ids = [s.get('id') for s in available_strategies]
        
        if strategy_id not in strategy_ids:
            logger.warning(f"策略不存在: {strategy_id}, 可用策略: {strategy_ids}")
            return jsonify({
                'success': False,
                'error': f'策略不存在: {strategy_id}',
                'available_strategies': strategy_ids
            }), 404
        
        # 运行单个策略的筛选
        logger.info(f"开始运行策略筛选: {strategy_id}")
        results = screener.run_screening([strategy_id])
        logger.info(f"筛选完成，获得 {len(results)} 个结果")
        
        # 转换为前端需要的格式
        stock_list = []
        stock_codes = []
        
        for result in results:
            try:
                stock_list.append({
                    'stock_code': result.stock_code,
                    'date': str(result.date),  # 使用正确的字段名
                    'signal_type': result.signal_type,
                    'price': result.current_price,  # 使用正确的字段名
                    'strategy_name': result.strategy_name
                })
                stock_codes.append(result.stock_code)
            except Exception as result_error:
                logger.warning(f"处理结果时出错: {result_error}, 跳过该结果")
                continue
        
        # 批量获取股票基本信息（名称、板块等）
        stock_info_map = {}
        if stock_codes:
            try:
                logger.info(f"正在获取 {len(stock_codes)} 个股票的基本信息...")
                stock_info_map = get_multiple_stock_info(stock_codes, use_cache=True)
                logger.info(f"成功获取 {len(stock_info_map)} 个股票的基本信息")
            except Exception as info_error:
                logger.warning(f"获取股票基本信息失败: {info_error}，将使用默认信息")
        
        # 将股票基本信息合并到结果中
        enhanced_stock_list = []
        for stock_data in stock_list:
            stock_code = stock_data['stock_code']
            stock_info = stock_info_map.get(stock_code)
            
            enhanced_data = stock_data.copy()
            if stock_info:
                enhanced_data.update({
                    'name': stock_info.name,
                    'sector': stock_info.sector,
                    'industry': stock_info.industry,
                    'market': stock_info.market
                })
            else:
                # 提供默认信息
                enhanced_data.update({
                    'name': f'股票{stock_code}',
                    'sector': '未知板块',
                    'industry': '未知行业', 
                    'market': 'A股'
                })
            
            enhanced_stock_list.append(enhanced_data)
        
        return jsonify({
            'success': True,
            'data': enhanced_stock_list,
            'total': len(enhanced_stock_list),
            'strategy_id': strategy_id,
            'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        logger.error(f"获取策略股票列表失败: {strategy_id} - {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'strategy_id': strategy_id
        }), 500


@app.route('/api/signals_summary', methods=['GET'])
def get_signals_summary():
    """兼容旧版API - 获取策略信号摘要"""
    try:
        strategy = request.args.get('strategy', 'PRE_CROSS')
        
        # 将旧策略ID映射为新策略ID
        strategy_mapping = {
            'PRE_CROSS': '临界金叉_v1.0',
            'TRIPLE_CROSS': '三重金叉_v1.0', 
            'MACD_ZERO_AXIS': 'macd零轴启动_v1.0',
            'WEEKLY_GOLDEN_CROSS_MA': '周线金叉+日线ma_v1.0',
            'ABYSS_BOTTOMING': '深渊筑底策略_v2.0'
        }
        
        new_strategy_id = strategy_mapping.get(strategy, strategy)
        
        # 运行筛选获取最新结果
        results = screener.run_screening([new_strategy_id])
        
        # 转换为旧版API格式
        stock_list = []
        for result in results:
            stock_list.append({
                'stock_code': result.stock_code,
                'date': str(result.date),  # 使用正确的字段名
                'signal_type': result.signal_type,
                'price': result.current_price  # 使用正确的字段名
            })
        
        return jsonify(stock_list)
        
    except Exception as e:
        logger.error(f"获取信号摘要失败: {e}")
        return jsonify({
            'error': f"获取策略 {strategy} 的信号失败: {str(e)}"
        }), 500


@app.route('/api/screening/export/<file_type>', methods=['GET'])
def export_results(file_type):
    """导出筛选结果"""
    try:
        if not screener.results:
            return jsonify({
                'success': False,
                'error': '没有可导出的结果'
            }), 400
        
        # 保存结果并获取文件路径
        saved_files = screener.save_results(screener.results)
        
        if file_type not in saved_files:
            return jsonify({
                'success': False,
                'error': f'不支持的文件类型: {file_type}'
            }), 400
        
        file_path = saved_files[file_type]
        
        if not os.path.exists(file_path):
            return jsonify({
                'success': False,
                'error': '文件不存在'
            }), 404
        
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        logger.error(f"导出结果失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/config', methods=['GET'])
def get_global_config():
    """获取全局配置"""
    try:
        return jsonify({
            'success': True,
            'data': screener.config
        })
    except Exception as e:
        logger.error(f"获取全局配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/config/unified', methods=['GET'])
def get_unified_config():
    """获取统一配置"""
    try:
        return jsonify({
            'success': True,
            'data': config_manager.config
        })
    except Exception as e:
        logger.error(f"获取统一配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/config', methods=['PUT'])
def update_global_config():
    """更新全局配置"""
    try:
        config = request.get_json()
        if not config:
            return jsonify({
                'success': False,
                'error': '配置数据不能为空'
            }), 400
        
        # 更新配置
        screener.config.update(config)
        
        # 保存配置文件
        with open(screener.config_file, 'w', encoding='utf-8') as f:
            json.dump(screener.config, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'message': '全局配置已更新'
        })
    except Exception as e:
        logger.error(f"更新全局配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/system/info', methods=['GET'])
def get_system_info():
    """获取系统信息"""
    try:
        return jsonify({
            'success': True,
            'data': {
                'version': '2.0',
                'total_strategies': len(strategy_manager.registered_strategies),
                'enabled_strategies': len(strategy_manager.get_enabled_strategies()),
                'last_scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'total_results': len(screener.results)
            }
        })
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'success': False,
        'error': 'API接口不存在'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'success': False,
        'error': '服务器内部错误'
    }), 500


if __name__ == '__main__':
    print("🚀 启动筛选API服务器")
    print("📡 API文档:")
    print("  GET  /api/strategies - 获取策略列表")
    print("  POST /api/strategies/<id>/enable - 启用策略")
    print("  POST /api/strategies/<id>/disable - 禁用策略")
    print("  POST /api/screening/start - 开始筛选")
    print("  GET  /api/screening/results - 获取结果")
    print("  GET  /api/screening/export/<type> - 导出结果")
    print("\n🌐 服务地址: http://localhost:5000")
    
    app.run(host='0.0.0.0', port=5000, debug=True)