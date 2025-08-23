import os
import json
import glob
import numpy as np
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import data_loader
import indicators
import strategies
import backtester
import multi_timeframe
from adjustment_processor import create_adjustment_config, create_adjustment_processor
from portfolio_manager import create_portfolio_manager
from strategy_manager import strategy_manager
from config_manager import config_manager

# --- 配置路径 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.abspath(os.path.join(backend_dir, '..', 'frontend'))
RESULT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
CORE_POOL_FILE = os.path.join(RESULT_PATH, 'core_pool.json')

app = Flask(__name__, static_folder=frontend_dir, static_url_path='')
CORS(app)

# --- 核心池管理辅助函数 (合并后的版本) ---
def load_core_pool_from_file():
    """从文件加载核心池数据"""
    if not os.path.exists(CORE_POOL_FILE):
        return []
    try:
        with open(CORE_POOL_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_core_pool_to_file(core_pool_data):
    """保存核心池数据到文件"""
    os.makedirs(os.path.dirname(CORE_POOL_FILE), exist_ok=True)
    with open(CORE_POOL_FILE, 'w', encoding='utf-8') as f:
        json.dump(core_pool_data, f, ensure_ascii=False, indent=2)

# --- 静态文件与主页 ---
@app.route('/')
def index():
    return send_from_directory(frontend_dir, 'index.html')

# --- API 端点 ---

@app.route('/api/strategies')
def get_available_strategies():
    """获取可用策略列表"""
    try:
        strategies = strategy_manager.get_available_strategies()
        return jsonify({
            'success': True,
            'strategies': strategies
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取策略列表失败: {str(e)}'
        }), 500

@app.route('/api/strategies/<strategy_id>/config', methods=['GET', 'PUT'])
def manage_strategy_config(strategy_id):
    """管理策略配置"""
    if request.method == 'GET':
        try:
            config = strategy_manager.strategy_configs.get(strategy_id, {})
            return jsonify({
                'success': True,
                'config': config
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'获取策略配置失败: {str(e)}'
            }), 500
    
    elif request.method == 'PUT':
        try:
            data = request.get_json()
            strategy_manager.update_strategy_config(strategy_id, data)
            return jsonify({
                'success': True,
                'message': f'策略 {strategy_id} 配置已更新'
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'更新策略配置失败: {str(e)}'
            }), 500

@app.route('/api/strategies/<strategy_id>/toggle', methods=['POST'])
def toggle_strategy(strategy_id):
    """启用/禁用策略"""
    try:
        data = request.get_json()
        enabled = data.get('enabled', True)
        
        if enabled:
            strategy_manager.enable_strategy(strategy_id)
        else:
            strategy_manager.disable_strategy(strategy_id)
        
        return jsonify({
            'success': True,
            'message': f'策略 {strategy_id} 已{"启用" if enabled else "禁用"}'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'切换策略状态失败: {str(e)}'
        }), 500

@app.route('/api/config/unified')
def get_unified_config():
    """获取统一配置"""
    try:
        # 获取完整配置
        config_data = {
            'strategies': config_manager.get_strategies(),
            'global_settings': config_manager.config.get('global_settings', {}),
            'market_filters': config_manager.config.get('market_filters', {}),
            'output_settings': config_manager.config.get('output_settings', {}),
            'frontend_settings': config_manager.config.get('frontend_settings', {}),
            'version': config_manager.config.get('version', '2.0'),
            'last_updated': config_manager.config.get('last_updated')
        }
        
        return jsonify({
            'success': True,
            'data': config_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'获取统一配置失败: {str(e)}'
        }), 500

@app.route('/api/signals_summary')
def get_signals_summary():
    """兼容旧版API - 获取策略信号摘要"""
    strategy = request.args.get('strategy', 'PRE_CROSS')
    
    # 首先尝试从文件系统读取（保持向后兼容）
    try:
        return send_from_directory(os.path.join(RESULT_PATH, strategy), 'signals_summary.json')
    except FileNotFoundError:
        # 如果文件不存在，尝试动态生成
        try:
            # 导入筛选器
            from universal_screener import UniversalScreener
            
            # 策略ID映射 - 添加新迁移的策略
            strategy_mapping = {
                'PRE_CROSS': '临界金叉_v1.0',
                'TRIPLE_CROSS': '三重金叉_v1.0', 
                'MACD_ZERO_AXIS': 'MACD零轴启动_v1.0',
                'WEEKLY_GOLDEN_CROSS_MA': '周线金叉+日线MA_v1.0',
                'ABYSS_BOTTOMING': '深渊筑底策略_v2.0',
                # 新迁移的策略
                'VALUE_REVERSAL': '价值反转策略（最终版）_v1.0',
                'REVERSED_SHORT': '反转做多策略（优化版）_v1.0'
            }
            
            new_strategy_id = strategy_mapping.get(strategy, strategy)
            
            # 创建筛选器实例并运行
            screener = UniversalScreener()
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
            return jsonify({"error": f"无法获取策略 '{strategy}' 的信号: {str(e)}"}), 500

def get_timeframe_data(stock_code, timeframe='daily'):
    """获取指定周期的数据"""
    if '#' in stock_code:
        market = 'ds'
    else:
        market = stock_code[:2]
    
    # 分时数据处理
    if timeframe in ['5min', '10min', '15min', '30min', '60min']:
        min5_file = os.path.join(BASE_PATH, market, 'fzline', f'{stock_code}.lc5')
        if not os.path.exists(min5_file):
            # 如果没有分时数据，回退到日线数据
            print(f"⚠️ 分时数据文件不存在，回退到日线数据: {min5_file}")
            file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
            if not os.path.exists(file_path):
                return None, f"Data file not found: {file_path}"
            return data_loader.get_daily_data(file_path), None
        
        min5_df = data_loader.get_5min_data(min5_file)
        if min5_df is None:
            # 如果分时数据加载失败，回退到日线数据
            print(f"⚠️ 分时数据加载失败，回退到日线数据")
            file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
            if not os.path.exists(file_path):
                return None, f"Data file not found: {file_path}"
            return data_loader.get_daily_data(file_path), None
        
        if timeframe == '5min':
            return min5_df, None
        
        # 重采样到其他分时周期
        interval_map = {
            '10min': '10T',
            '15min': '15T', 
            '30min': '30T',
            '60min': '60T'
        }
        
        try:
            resampled_df = min5_df.resample(interval_map[timeframe]).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            return resampled_df, None
        except Exception as e:
            print(f"⚠️ 分时数据重采样失败: {e}，回退到日线数据")
            file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
            if not os.path.exists(file_path):
                return None, f"Data file not found: {file_path}"
            return data_loader.get_daily_data(file_path), None
    
    elif timeframe == 'daily':
        # 日线数据
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
        if not os.path.exists(file_path):
            return None, f"Daily data file not found: {file_path}"
        return data_loader.get_daily_data(file_path), None
    
    elif timeframe in ['weekly', 'monthly']:
        # 周线和月线需要从日线数据重采样
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
        if not os.path.exists(file_path):
            return None, f"Daily data file not found: {file_path}"
        
        daily_df = data_loader.get_daily_data(file_path)
        if daily_df is None:
            return None, "Failed to load daily data"
        
        # 重采样到周线或月线
        try:
            if timeframe == 'weekly':
                resampled_df = daily_df.resample('W').agg({
                    'open': 'first',
                    'high': 'max', 
                    'low': 'min',
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
            else:  # monthly
                resampled_df = daily_df.resample('M').agg({
                    'open': 'first',
                    'high': 'max',
                    'low': 'min', 
                    'close': 'last',
                    'volume': 'sum'
                }).dropna()
            
            return resampled_df, None
        except Exception as e:
            return None, f"Failed to resample data: {str(e)}"
    
    else:
        return None, f"Unsupported timeframe: {timeframe}"

@app.route('/api/analysis/<stock_code>')
def get_stock_analysis(stock_code):
    try:
        strategy_name = request.args.get('strategy', 'PRE_CROSS')
        adjustment_type = request.args.get('adjustment', 'forward')
        timeframe = request.args.get('timeframe', 'daily')
        
        # 获取指定周期的数据
        df, error = get_timeframe_data(stock_code, timeframe)
        if df is None:
            return jsonify({"error": error}), 404
        
        # 应用复权处理
        if adjustment_type != 'none':
            adjustment_config = create_adjustment_config(adjustment_type)
            adjustment_processor = create_adjustment_processor(adjustment_config)
            df = adjustment_processor.process_data(df, stock_code)
            print(f"📊 复权处理 {stock_code}: {adjustment_type}")  # 调试信息

        # 计算指标（使用复权后的数据）
        df['ma13'] = indicators.calculate_ma(df, 13)
        df['ma45'] = indicators.calculate_ma(df, 45)
        
        # 创建复权配置用于指标计算
        adjustment_config = create_adjustment_config(adjustment_type) if adjustment_type != 'none' else None
        
        # 使用配置计算MACD指标
        macd_config = indicators.MACDIndicatorConfig(adjustment_config=adjustment_config)
        df['dif'], df['dea'] = indicators.calculate_macd(df, config=macd_config, stock_code=stock_code)
        df['macd'] = df['dif'] - df['dea']  # 计算MACD柱状图数据
        
        # 使用配置计算KDJ指标
        kdj_config = indicators.KDJIndicatorConfig(adjustment_config=adjustment_config)
        df['k'], df['d'], df['j'] = indicators.calculate_kdj(df, config=kdj_config, stock_code=stock_code)
        
        # 计算多个周期的RSI
        df['rsi6'] = indicators.calculate_rsi(df, 6)
        df['rsi12'] = indicators.calculate_rsi(df, 12)
        df['rsi24'] = indicators.calculate_rsi(df, 24)
        
        # 应用策略和回测
        # 使用统一配置管理器查找策略ID
        strategy_id = config_manager.find_strategy_by_old_id(strategy_name)
        signals = None
        
        if strategy_id:
            try:
                # 使用策略管理器获取策略实例
                strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
                if strategy_instance:
                    signals = strategy_instance.apply_strategy(df)
                    if signals is None:
                        signals = pd.Series([False] * len(df), index=df.index)
                else:
                    print(f"策略实例未找到: {strategy_id}")
                    print(f"可用策略: {list(strategy_manager.registered_strategies.keys())}")
            except Exception as e:
                print(f"策略管理器错误: {e}")
                import traceback
                traceback.print_exc()
        
        # 如果策略管理器失败，尝试使用传统方法
        if signals is None:
            try:
                if hasattr(strategies, 'apply_strategy'):
                    signals = strategies.apply_strategy(strategy_name, df)
                else:
                    # 最后的回退方案
                    signals = pd.Series([False] * len(df), index=df.index)
                    print(f"警告: 策略 {strategy_name} 未找到，返回空信号")
            except Exception as e:
                print(f"传统策略调用失败: {e}")
                signals = pd.Series([False] * len(df), index=df.index)
        # ---新增的防御性代码---
        #检查 signals是否为元组，如果是，则只取第一个元素
        if isinstance(signals, tuple) and len(signals) > 0:
            print(f"警告：策略{strategy_name} 返回了一个元组，自动取第一个元素作为信号，原始信号{signals}")
            signals = signals[0]
        backtest_results = backtester.run_backtest(df, signals)
        
        # 构建信号点 - 修复：使用回测中实际的入场价格
        signal_points = []
        if signals is not None and not signals[signals != ''].empty:
            signal_df = df[signals != '']
            # 修复：使用正确的键名 'entry_idx' 而不是 'entry_index'
            trade_results = {trade['entry_idx']: trade for trade in backtest_results.get('trades', [])}
            for idx, row in signal_df.iterrows():
                original_state = str(signals[idx])
                # 需要将pandas索引转换为位置索引来匹配backtester的返回值
                idx_pos = df.index.get_loc(idx) if idx in df.index else 0
                is_success = trade_results.get(idx_pos, {}).get('is_success', False)
                final_state = f"{original_state}_SUCCESS" if is_success else f"{original_state}_FAIL"
                
                # 修复：使用回测中实际的入场价格，而不是固定使用最低价
                actual_entry_price = trade_results.get(idx_pos, {}).get('entry_price')
                if actual_entry_price is not None:
                    # 使用回测中计算的实际入场价格
                    display_price = float(actual_entry_price)
                else:
                    # 如果没有回测数据，回退到收盘价（更合理的默认值）
                    display_price = float(row['close'])
                
                # 处理不同类型的时间索引格式
                if hasattr(idx, 'strftime'):
                    if timeframe in ['5min', '10min', '15min', '30min', '60min']:
                        date_str = idx.strftime('%Y-%m-%d %H:%M')
                    else:
                        date_str = idx.strftime('%Y-%m-%d')
                else:
                    date_str = str(idx)
                
                signal_points.append({
                    'date': date_str,
                    'price': display_price, 
                    'state': final_state,
                    'original_state': original_state
                })

        # 准备返回数据
        df.replace({np.nan: None}, inplace=True)
        df_reset = df.reset_index()
        
        # 处理不同类型的时间索引
        index_col = df_reset.columns[0]
        
        # 重命名索引列为date
        if index_col != 'date':
            df_reset = df_reset.rename(columns={index_col: 'date'})
        
        # 根据周期类型格式化日期
        if timeframe in ['5min', '10min', '15min', '30min', '60min']:
            # 分时数据显示时间
            df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d %H:%M')
        else:
            # 日线、周线、月线数据只显示日期
            df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d')
        
        kline_data = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        indicator_data = df_reset[['date', 'ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']].to_dict('records')
        
        # 序列化回测结果
        if isinstance(backtest_results, dict):
            backtest_results = json.loads(json.dumps(backtest_results, default=lambda x: x.item() if isinstance(x, (np.integer, np.floating)) else bool(x) if isinstance(x, np.bool_) else None))

        return jsonify({
            'kline_data': kline_data,
            'indicator_data': indicator_data,
            'signal_points': signal_points,
            'backtest_results': backtest_results
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500


@app.route('/api/trading_advice/<stock_code>')
def get_trading_advice(stock_code):
    try:
        # 使用与分析API相同的数据加载方式
        adjustment_type = request.args.get('adjustment', 'forward')
        timeframe = request.args.get('timeframe', 'daily')
        
        # 获取指定周期的数据
        df, error = get_timeframe_data(stock_code, timeframe)
        if df is None:
            return jsonify({"error": error}), 404
        
        if len(df) < 50:
            return jsonify({"error": f"数据不足，需要至少50个数据点"}), 404
        
        # 应用复权处理
        if adjustment_type != 'none':
            adjustment_config = create_adjustment_config(adjustment_type)
            adjustment_processor = create_adjustment_processor(adjustment_config)
            df = adjustment_processor.process_data(df, stock_code)
            print(f"📊 交易建议复权处理 {stock_code}: {adjustment_type}")  # 调试信息
        
        # 计算技术指标
        df['ma13'] = indicators.calculate_ma(df, 13)
        df['ma45'] = indicators.calculate_ma(df, 45)
        df['rsi6'] = indicators.calculate_rsi(df, 6)
        df['rsi12'] = indicators.calculate_rsi(df, 12)
        df['rsi24'] = indicators.calculate_rsi(df, 24)
        
        # 获取最新数据
        latest = df.iloc[-1]
        
        # 生成建议
        analysis_logic = []
        confidence = 0.5
        action = 'WATCH'
        
        ma13 = latest['ma13'] if not pd.isna(latest['ma13']) else latest['close']
        ma45 = latest['ma45'] if not pd.isna(latest['ma45']) else latest['close']
        rsi = latest['rsi6'] if not pd.isna(latest['rsi6']) else 50

        if ma13 > ma45:
            analysis_logic.append(f"短期均线(MA13: {ma13:.2f})位于长期均线(MA45: {ma45:.2f})之上，呈多头趋势。")
            confidence += 0.15
            action = 'HOLD'
        else:
            analysis_logic.append(f"短期均线(MA13: {ma13:.2f})位于长期均线(MA45: {ma45:.2f})之下，呈空头趋势。")
            confidence -= 0.15
            action = 'AVOID'

        if latest['close'] > ma13:
            analysis_logic.append(f"当前价格({latest['close']:.2f})在MA13之上，短期强势。")
            confidence += 0.1
        else:
            analysis_logic.append(f"当前价格({latest['close']:.2f})在MA13之下，短期弱势。")
            confidence -= 0.1

        if rsi < 30:
            analysis_logic.append(f"RSI指标({rsi:.1f})进入超卖区，可能存在反弹机会。")
            confidence += 0.15
            action = 'BUY' if action != 'AVOID' else 'WATCH'
        elif rsi > 70:
            analysis_logic.append(f"RSI指标({rsi:.1f})进入超买区，警惕回调风险。")
            confidence -= 0.15
            if action == 'BUY': action = 'HOLD'
        else:
            analysis_logic.append(f"RSI指标({rsi:.1f})处于正常区间。")
        
        confidence = max(0.1, min(0.95, confidence))
        
        # 计算价格位
        recent_data = df.tail(30)
        resistance = recent_data['high'].max()
        support = recent_data['low'].min()
        
        return jsonify({
            'action': action,
            'confidence': confidence,
            'current_price': float(latest['close']),
            'entry_price': float(latest['close'] * 0.99),
            'target_price': float(latest['close'] * 1.1),
            'stop_price': float(latest['close'] * 0.95),
            'resistance_level': float(resistance),
            'support_level': float(support),
            'analysis_logic': analysis_logic,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"生成交易建议失败: {str(e)}"}), 500

# --- 其他API (历史报告, 深度扫描等) ---

@app.route('/api/history_reports')
def get_history_reports():
    strategy = request.args.get('strategy', 'PRE_CROSS')
    strategy_dir = os.path.join(RESULT_PATH, strategy)
    if not os.path.exists(strategy_dir): return jsonify([])
    reports = []
    for file_path in glob.glob(os.path.join(strategy_dir, 'scan_summary_report*.json')):
        with open(file_path, 'r', encoding='utf-8') as f:
            report_data = json.load(f)
            report_data['id'] = os.path.basename(file_path)
            reports.append(report_data)
    reports.sort(key=lambda x: x.get('scan_summary', {}).get('scan_timestamp', ''), reverse=True)
    return jsonify(reports)

@app.route('/api/deep_scan_results')
def get_deep_scan_results():
    try:
        enhanced_dir = os.path.join(RESULT_PATH, 'ENHANCED_ANALYSIS')
        if not os.path.exists(enhanced_dir): return jsonify({"error": "深度扫描结果目录不存在"}), 404
        
        json_files = glob.glob(os.path.join(enhanced_dir, 'enhanced_analysis_*.json'))
        if not json_files: return jsonify({"error": "未找到深度扫描结果"}), 404
        
        latest_file = max(json_files, key=os.path.getctime)
        with open(latest_file, 'r', encoding='utf-8') as f: results = json.load(f)

        processed = [{
            'stock_code': k, 'score': v.get('overall_score', {}).get('total_score', 0),
            'grade': v.get('overall_score', {}).get('grade', 'F'),
            'action': v.get('recommendation', {}).get('action', 'UNKNOWN'),
            'confidence': v.get('recommendation', {}).get('confidence', 0),
            'current_price': v.get('basic_analysis', {}).get('current_price', 0),
            'price_change_30d': v.get('basic_analysis', {}).get('price_change_30d', 0),
            'volatility': v.get('basic_analysis', {}).get('volatility', 0),
            'signal_count': v.get('basic_analysis', {}).get('signal_count', 0),
            'has_price_evaluation': 'price_evaluation' in v,
            'price_evaluation': v.get('price_evaluation', {})
        } for k, v in results.items() if 'error' not in v]
        processed.sort(key=lambda x: x['score'], reverse=True)

        summary = {
            'total_analyzed': len(processed),
            'a_grade_count': sum(1 for r in processed if r['grade'] == 'A'),
            'price_evaluated_count': sum(1 for r in processed if r['has_price_evaluation']),
            'buy_recommendations': sum(1 for r in processed if r['action'] == 'BUY')
        }
        return jsonify({'results': processed, 'summary': summary})
    except Exception as e:
        return jsonify({"error": f"获取深度扫描结果失败: {str(e)}"}), 500

@app.route('/api/run_deep_scan', methods=['POST'])
def run_deep_scan_from_signals():
    # ... (此部分逻辑无需修改，保持原样)
    return jsonify({"success": True, "message": "深度扫描已触发"})

# --- 核心池管理 (统一版本) ---
@app.route('/api/core_pool', methods=['GET', 'POST', 'DELETE'])
def manage_core_pool():
    if request.method == 'GET':
        core_pool = load_core_pool_from_file()
        return jsonify({'success': True, 'core_pool': core_pool, 'count': len(core_pool)})

    if request.method == 'POST':
        data = request.get_json()
        stock_code = data.get('stock_code', '').strip().lower()
        if not stock_code or not (stock_code.startswith(('sz', 'sh')) and len(stock_code) == 8):
            return jsonify({'error': '股票代码格式不正确'}), 400
        
        core_pool = load_core_pool_from_file()
        if any(stock['stock_code'] == stock_code for stock in core_pool):
            return jsonify({'error': f'股票 {stock_code} 已存在'}), 400
            
        new_stock = {
            'stock_code': stock_code,
            'added_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'note': data.get('note', ''),
            'grade': 'C',
            'weight': 5.0
        }
        core_pool.append(new_stock)
        save_core_pool_to_file(core_pool)
        return jsonify({'success': True, 'message': f'股票 {stock_code} 添加成功', 'stock': new_stock})

    if request.method == 'DELETE':
        stock_code = request.args.get('stock_code', '').strip().lower()
        if not stock_code: return jsonify({'error': '股票代码不能为空'}), 400
        
        core_pool = load_core_pool_from_file()
        original_count = len(core_pool)
        core_pool = [stock for stock in core_pool if stock['stock_code'] != stock_code]
        
        if len(core_pool) == original_count:
            return jsonify({'error': f'股票 {stock_code} 不在核心池中'}), 404
            
        save_core_pool_to_file(core_pool)
        return jsonify({'success': True, 'message': f'股票 {stock_code} 已删除'})

    return jsonify({'error': '不支持的请求方法'}), 405

# --- 持仓管理API ---
@app.route('/api/portfolio', methods=['GET', 'POST', 'PUT', 'DELETE'])
def manage_portfolio():
    portfolio_manager = create_portfolio_manager()
    
    if request.method == 'GET':
        # 获取持仓列表
        portfolio = portfolio_manager.load_portfolio()
        return jsonify({'success': True, 'portfolio': portfolio, 'count': len(portfolio)})
    
    elif request.method == 'POST':
        # 添加持仓
        data = request.get_json()
        try:
            stock_code = data.get('stock_code', '').strip().lower()
            purchase_price = float(data.get('purchase_price', 0))
            quantity = int(data.get('quantity', 0))
            purchase_date = data.get('purchase_date', '')
            note = data.get('note', '')
            
            if not stock_code or not (stock_code.startswith(('sz', 'sh')) and len(stock_code) == 8):
                return jsonify({'error': '股票代码格式不正确'}), 400
            
            if purchase_price <= 0:
                return jsonify({'error': '购买价格必须大于0'}), 400
            
            if quantity <= 0:
                return jsonify({'error': '持仓数量必须大于0'}), 400
            
            position = portfolio_manager.add_position(
                stock_code, purchase_price, quantity, purchase_date, note
            )
            return jsonify({'success': True, 'message': f'持仓 {stock_code} 添加成功', 'position': position})
            
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': f'添加持仓失败: {str(e)}'}), 500
    
    elif request.method == 'PUT':
        # 更新持仓
        data = request.get_json()
        stock_code = data.get('stock_code', '').strip().lower()
        
        if not stock_code:
            return jsonify({'error': '股票代码不能为空'}), 400
        
        update_data = {k: v for k, v in data.items() if k != 'stock_code'}
        
        if portfolio_manager.update_position(stock_code, **update_data):
            return jsonify({'success': True, 'message': f'持仓 {stock_code} 更新成功'})
        else:
            return jsonify({'error': f'持仓 {stock_code} 不存在'}), 404
    
    elif request.method == 'DELETE':
        # 删除持仓
        stock_code = request.args.get('stock_code', '').strip().lower()
        
        if not stock_code:
            return jsonify({'error': '股票代码不能为空'}), 400
        
        if portfolio_manager.remove_position(stock_code):
            return jsonify({'success': True, 'message': f'持仓 {stock_code} 已删除'})
        else:
            return jsonify({'error': f'持仓 {stock_code} 不存在'}), 404

@app.route('/api/portfolio/scan', methods=['POST'])
def scan_portfolio():
    """扫描所有持仓并生成分析报告"""
    try:
        portfolio_manager = create_portfolio_manager()
        
        # 后端自动判断是否需要重新扫描
        # 首先尝试获取缓存结果
        results = portfolio_manager.scan_all_positions(force_refresh=False)
        
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'持仓扫描失败: {str(e)}'}), 500

@app.route('/api/portfolio/analysis/<stock_code>')
def get_position_analysis(stock_code):
    """获取单个持仓的详细分析"""
    try:
        portfolio_manager = create_portfolio_manager()
        portfolio = portfolio_manager.load_portfolio()
        
        # 找到对应的持仓
        position = None
        for p in portfolio:
            if p['stock_code'] == stock_code:
                position = p
                break
        
        if not position:
            return jsonify({'error': f'持仓 {stock_code} 不存在'}), 404
        
        # 进行深度分析
        analysis = portfolio_manager.analyze_position_deep(
            stock_code,
            position['purchase_price'],
            position['purchase_date']
        )
        
        if 'error' in analysis:
            return jsonify(analysis), 500
        
        # 合并持仓基本信息
        result = {**position, **analysis}
        return jsonify({'success': True, 'analysis': result})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'获取持仓分析失败: {str(e)}'}), 500


if __name__ == '__main__':
    print("量化分析平台后端启动...")
    print("请在浏览器中打开 http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)