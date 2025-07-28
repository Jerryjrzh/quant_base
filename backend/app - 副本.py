import os
import json
import glob
import numpy as np
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import data_loader
import indicators
import strategies
import backtester
import multi_timeframe

backend_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.abspath(os.path.join(backend_dir, '..', 'frontend'))
RESULT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")

app = Flask(__name__, static_folder=frontend_dir, static_url_path='')
CORS(app)

@app.route('/')
def index():
    return send_from_directory(frontend_dir, 'index.html')

@app.route('/api/signals_summary')
def get_signals_summary():
    strategy = request.args.get('strategy', 'PRE_CROSS')
    file_path = os.path.join(RESULT_PATH, strategy, 'signals_summary.json')
    try:
        return send_from_directory(os.path.join(RESULT_PATH, strategy), 'signals_summary.json')
    except FileNotFoundError:
        return jsonify({"error": f"Signal file not found for strategy '{strategy}'. Have you run screener.py?"}), 404

@app.route('/api/deep_scan_results')
def get_deep_scan_results():
    """获取深度扫描结果"""
    try:
        # 查找最新的深度扫描结果
        enhanced_dir = os.path.join(RESULT_PATH, 'ENHANCED_ANALYSIS')
        if not os.path.exists(enhanced_dir):
            return jsonify({"error": "深度扫描结果目录不存在"}), 404
        
        # 获取最新的分析文件
        json_files = glob.glob(os.path.join(enhanced_dir, 'enhanced_analysis_*.json'))
        if not json_files:
            return jsonify({"error": "未找到深度扫描结果"}), 404
        
        latest_file = max(json_files, key=os.path.getctime)
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        # 处理结果，提取关键信息
        processed_results = []
        for stock_code, result in results.items():
            if 'error' not in result:
                processed_result = {
                    'stock_code': stock_code,
                    'score': result.get('overall_score', {}).get('total_score', 0),
                    'grade': result.get('overall_score', {}).get('grade', 'F'),
                    'action': result.get('recommendation', {}).get('action', 'UNKNOWN'),
                    'confidence': result.get('recommendation', {}).get('confidence', 0),
                    'current_price': result.get('basic_analysis', {}).get('current_price', 0),
                    'price_change_30d': result.get('basic_analysis', {}).get('price_change_30d', 0),
                    'volatility': result.get('basic_analysis', {}).get('volatility', 0),
                    'signal_count': result.get('basic_analysis', {}).get('signal_count', 0),
                    'has_price_evaluation': 'price_evaluation' in result,
                    'price_evaluation': result.get('price_evaluation', {})
                }
                processed_results.append(processed_result)
        
        # 按评分排序
        processed_results.sort(key=lambda x: x['score'], reverse=True)
        
        return jsonify({
            'results': processed_results,
            'summary': {
                'total_analyzed': len(processed_results),
                'a_grade_count': len([r for r in processed_results if r['grade'] == 'A']),
                'price_evaluated_count': len([r for r in processed_results if r['has_price_evaluation']]),
                'buy_recommendations': len([r for r in processed_results if r['action'] == 'BUY'])
            },
            'file_path': latest_file,
            'timestamp': os.path.getctime(latest_file)
        })
        
    except Exception as e:
        return jsonify({"error": f"获取深度扫描结果失败: {str(e)}"}), 500

@app.route('/api/trading_advice/<stock_code>')
def get_trading_advice(stock_code):
    """获取股票的交易建议"""
    try:
        strategy = request.args.get('strategy', 'PRE_CROSS')
        
        # 加载股票数据
        stock_data = data_loader.load_stock_data(stock_code)
        if stock_data is None or len(stock_data) < 50:
            return jsonify({"error": f"无法加载股票 {stock_code} 的数据"}), 404
        
        # 计算技术指标
        indicator_data = indicators.calculate_all_indicators(stock_data)
        
        # 获取最新数据
        latest = indicator_data.iloc[-1]
        current_price = latest['close']
        
        # 基于技术指标生成交易建议
        advice = generate_trading_advice(stock_code, latest, indicator_data, strategy)
        
        return jsonify(advice)
        
    except Exception as e:
        return jsonify({"error": f"生成交易建议失败: {str(e)}"}), 500

def generate_trading_advice(stock_code, latest_data, indicator_data, strategy):
    """生成交易建议"""
    current_price = latest_data['close']
    ma13 = latest_data.get('ma13', current_price)
    ma45 = latest_data.get('ma45', current_price)
    rsi = latest_data.get('rsi6', latest_data.get('rsi', 50))  # 使用rsi6或默认rsi
    macd = (latest_data.get('dif', 0) or 0) - (latest_data.get('dea', 0) or 0)
    
    # 计算支撑阻力位
    recent_data = indicator_data.tail(20)
    resistance_level = recent_data['high'].max()
    support_level = recent_data['low'].min()
    
    # 基础分析逻辑
    analysis_logic = []
    confidence = 0.5
    action = 'WATCH'
    
    # MA趋势分析
    if ma13 > ma45:
        analysis_logic.append("MA13 > MA45，短期趋势向上")
        confidence += 0.1
    else:
        analysis_logic.append("MA13 < MA45，短期趋势向下")
        confidence -= 0.1
    
    # 价格与MA关系
    if current_price > ma13 > ma45:
        analysis_logic.append("价格位于均线之上，多头排列")
        confidence += 0.15
        if action == 'WATCH':
            action = 'BUY'
    elif current_price < ma13 < ma45:
        analysis_logic.append("价格位于均线之下，空头排列")
        confidence -= 0.15
        action = 'AVOID'
    
    # RSI分析
    if rsi < 30:
        analysis_logic.append(f"RSI({rsi:.1f}) 超卖，可能反弹")
        confidence += 0.1
        if action in ['WATCH', 'AVOID']:
            action = 'WATCH'
    elif rsi > 70:
        analysis_logic.append(f"RSI({rsi:.1f}) 超买，注意回调风险")
        confidence -= 0.1
        if action == 'BUY':
            action = 'HOLD'
    else:
        analysis_logic.append(f"RSI({rsi:.1f}) 处于正常区间")
    
    # MACD分析
    if macd > 0:
        analysis_logic.append("MACD金叉，动能向上")
        confidence += 0.1
    else:
        analysis_logic.append("MACD死叉，动能向下")
        confidence -= 0.1
    
    # 策略特定分析
    if strategy == 'PRE_CROSS':
        if abs(ma13 - ma45) / ma45 < 0.02:  # 均线接近
            analysis_logic.append("均线即将交叉，关注突破方向")
            confidence += 0.05
    
    # 限制置信度范围
    confidence = max(0.1, min(0.9, confidence))
    
    # 计算价格位
    if action == 'BUY':
        entry_price = current_price * 0.98  # 稍低于当前价格入场
        target_price = current_price * 1.08  # 8%目标收益
        stop_price = current_price * 0.95   # 5%止损
    elif action == 'HOLD':
        entry_price = current_price
        target_price = current_price * 1.05
        stop_price = current_price * 0.97
    else:
        entry_price = current_price
        target_price = current_price
        stop_price = current_price
    
    return {
        'stock_code': stock_code,
        'action': action,
        'confidence': confidence,
        'current_price': current_price,
        'entry_price': entry_price,
        'target_price': target_price,
        'stop_price': stop_price,
        'resistance_level': resistance_level,
        'support_level': support_level,
        'analysis_logic': analysis_logic,
        'timestamp': indicator_data.index[-1].strftime('%Y-%m-%d %H:%M:%S') if hasattr(indicator_data.index[-1], 'strftime') else str(indicator_data.index[-1])
    }

@app.route('/api/price_evaluations')
def get_price_evaluations():
    """获取价格评估记录"""
    try:
        eval_dir = os.path.join(RESULT_PATH, 'PRICE_EVALUATION')
        if not os.path.exists(eval_dir):
            return jsonify({"error": "价格评估目录不存在"}), 404
        
        summary_file = os.path.join(eval_dir, 'price_evaluations_summary.jsonl')
        if not os.path.exists(summary_file):
            return jsonify({"evaluations": [], "count": 0})
        
        evaluations = []
        with open(summary_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    evaluations.append(json.loads(line))
        
        # 按时间排序，最新的在前
        evaluations.sort(key=lambda x: x.get('evaluation_time', ''), reverse=True)
        
        return jsonify({
            'evaluations': evaluations,
            'count': len(evaluations)
        })
        
    except Exception as e:
        return jsonify({"error": f"获取价格评估记录失败: {str(e)}"}), 500

@app.route('/api/trigger_deep_scan', methods=['POST'])
def trigger_deep_scan_api():
    """触发深度扫描API"""
    try:
        data = request.get_json()
        stock_codes = data.get('stock_codes', [])
        max_workers = data.get('max_workers', 32)
        
        if not stock_codes:
            return jsonify({"error": "请提供股票代码列表"}), 400
        
        # 导入深度扫描模块
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from run_enhanced_screening import deep_scan_stocks
        
        # 执行深度扫描
        results = deep_scan_stocks(stock_codes, use_optimized_params=True, max_workers=max_workers)
        
        # 统计结果
        valid_results = {k: v for k, v in results.items() if 'error' not in v}
        a_grade_count = len([k for k, v in valid_results.items() if v.get('overall_score', {}).get('grade') == 'A'])
        price_eval_count = len([k for k, v in valid_results.items() if 'price_evaluation' in v])
        
        return jsonify({
            'success': True,
            'message': '深度扫描完成',
            'summary': {
                'total_requested': len(stock_codes),
                'total_analyzed': len(valid_results),
                'a_grade_count': a_grade_count,
                'price_evaluated_count': price_eval_count
            }
        })
        
    except Exception as e:
        return jsonify({"error": f"深度扫描失败: {str(e)}"}), 500

@app.route('/api/run_deep_scan', methods=['POST'])
def run_deep_scan_from_signals():
    """从当前信号列表触发深度扫描"""
    try:
        strategy = request.args.get('strategy', 'PRE_CROSS')
        
        # 读取当前策略的信号列表
        signals_file = os.path.join(RESULT_PATH, strategy, 'signals_summary.json')
        if not os.path.exists(signals_file):
            return jsonify({"error": f"未找到策略 {strategy} 的信号文件"}), 404
        
        with open(signals_file, 'r', encoding='utf-8') as f:
            signals_data = json.load(f)
        
        if not signals_data:
            return jsonify({"error": "当前策略没有信号数据"}), 400
        
        # 提取股票代码
        stock_codes = [signal['stock_code'] for signal in signals_data]
        
        # 导入深度扫描模块
        import sys
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from run_enhanced_screening import deep_scan_stocks
        
        # 执行深度扫描
        results = deep_scan_stocks(stock_codes, use_optimized_params=True, max_workers=32)
        
        # 统计结果
        valid_results = {k: v for k, v in results.items() if 'error' not in v}
        a_grade_count = len([k for k, v in valid_results.items() if v.get('overall_score', {}).get('grade') == 'A'])
        price_eval_count = len([k for k, v in valid_results.items() if 'price_evaluation' in v])
        buy_rec_count = len([k for k, v in valid_results.items() if v.get('recommendation', {}).get('action') == 'BUY'])
        
        return jsonify({
            'success': True,
            'message': f'深度扫描完成，分析了 {len(stock_codes)} 只股票',
            'summary': {
                'total_requested': len(stock_codes),
                'total_analyzed': len(valid_results),
                'a_grade_count': a_grade_count,
                'price_evaluated_count': price_eval_count,
                'buy_recommendations': buy_rec_count
            },
            'strategy': strategy
        })
        
    except Exception as e:
        return jsonify({"error": f"深度扫描失败: {str(e)}"}), 500

@app.route('/api/history_reports')
def get_history_reports():
    """获取历史筛选报告列表"""
    strategy = request.args.get('strategy', 'MACD_ZERO_AXIS')
    strategy_dir = os.path.join(RESULT_PATH, strategy)
    
    if not os.path.exists(strategy_dir):
        return jsonify([])
    
    reports = []
    try:
        # 查找所有汇总报告文件
        summary_files = glob.glob(os.path.join(strategy_dir, 'scan_summary_report*.json'))
        
        for file_path in summary_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                    report_data['id'] = os.path.basename(file_path)
                    reports.append(report_data)
            except Exception as e:
                print(f"Error reading report file {file_path}: {e}")
                continue
        
        # 按时间戳排序（最新的在前）
        reports.sort(key=lambda x: x.get('scan_summary', {}).get('scan_timestamp', ''), reverse=True)
        
        return jsonify(reports)
    except Exception as e:
        return jsonify({"error": f"Failed to load history reports: {str(e)}"}), 500

@app.route('/api/strategy_overview')
def get_strategy_overview():
    """获取策略总体表现概览"""
    strategy = request.args.get('strategy', 'PRE_CROSS')
    strategy_dir = os.path.join(RESULT_PATH, strategy)
    
    if not os.path.exists(strategy_dir):
        return jsonify({"error": "Strategy directory not found"}), 404
    
    try:
        # 读取所有历史报告
        summary_files = glob.glob(os.path.join(strategy_dir, 'scan_summary_report*.json'))
        
        total_scans = len(summary_files)
        total_signals = 0
        win_rates = []
        profit_rates = []
        
        for file_path in summary_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    report_data = json.load(f)
                    scan_summary = report_data.get('scan_summary', {})
                    
                    total_signals += scan_summary.get('total_signals', 0)
                    
                    # 解析胜率和收益率
                    win_rate_str = scan_summary.get('avg_win_rate', '0.0%').replace('%', '')
                    profit_rate_str = scan_summary.get('avg_profit_rate', '0.0%').replace('%', '')
                    
                    try:
                        win_rates.append(float(win_rate_str))
                        profit_rates.append(float(profit_rate_str))
                    except:
                        pass
            except Exception as e:
                print(f"Error processing report {file_path}: {e}")
                continue
        
        # 计算平均值
        avg_win_rate = sum(win_rates) / len(win_rates) if win_rates else 0
        avg_profit_rate = sum(profit_rates) / len(profit_rates) if profit_rates else 0
        
        overview = {
            'total_scans': total_scans,
            'total_signals': total_signals,
            'avg_win_rate': f"{avg_win_rate:.1f}%",
            'avg_profit_rate': f"{avg_profit_rate:.1f}%",
            'strategy': strategy
        }
        
        return jsonify(overview)
    except Exception as e:
        return jsonify({"error": f"Failed to generate overview: {str(e)}"}), 500

@app.route('/api/reliability_analysis')
def get_reliability_analysis():
    """获取数据可靠性分析"""
    strategy = request.args.get('strategy', 'PRE_CROSS')
    strategy_dir = os.path.join(RESULT_PATH, strategy)
    
    if not os.path.exists(strategy_dir):
        return jsonify({"error": "Strategy directory not found"}), 404
    
    try:
        # 读取所有历史信号数据
        signals_files = glob.glob(os.path.join(strategy_dir, 'signals_summary*.json'))
        
        stock_stats = {}
        
        for file_path in signals_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    signals_data = json.load(f)
                    
                    for signal in signals_data:
                        stock_code = signal.get('stock_code', '')
                        if not stock_code:
                            continue
                        
                        if stock_code not in stock_stats:
                            stock_stats[stock_code] = {
                                'stock_code': stock_code,
                                'appearance_count': 0,
                                'win_rates': [],
                                'profits': [],
                                'recent_signals': []
                            }
                        
                        stock_stats[stock_code]['appearance_count'] += 1
                        
                        # 收集胜率和收益数据
                        win_rate_str = signal.get('win_rate', '0.0%').replace('%', '')
                        profit_str = signal.get('avg_max_profit', '0.0%').replace('%', '')
                        
                        try:
                            stock_stats[stock_code]['win_rates'].append(float(win_rate_str))
                            stock_stats[stock_code]['profits'].append(float(profit_str))
                        except:
                            pass
                        
                        # 记录最近的信号
                        stock_stats[stock_code]['recent_signals'].append({
                            'date': signal.get('date', ''),
                            'signal_state': signal.get('signal_state', ''),
                            'scan_timestamp': signal.get('scan_timestamp', '')
                        })
            except Exception as e:
                print(f"Error processing signals file {file_path}: {e}")
                continue
        
        # 计算每个股票的统计数据
        reliability_stocks = []
        for stock_code, stats in stock_stats.items():
            if stats['win_rates'] and stats['profits']:
                avg_win_rate = sum(stats['win_rates']) / len(stats['win_rates'])
                avg_profit = sum(stats['profits']) / len(stats['profits'])
                
                # 获取最近表现
                recent_signals = sorted(stats['recent_signals'], 
                                      key=lambda x: x.get('scan_timestamp', ''), 
                                      reverse=True)[:3]
                
                reliability_stocks.append({
                    'stock_code': stock_code,
                    'appearance_count': stats['appearance_count'],
                    'win_rate': f"{avg_win_rate:.1f}%",
                    'avg_profit': f"{avg_profit:.1f}%",
                    'recent_performance': f"最近{len(recent_signals)}次出现",
                    'recent_signals': recent_signals
                })
        
        # 按出现次数和胜率排序
        reliability_stocks.sort(key=lambda x: (x['appearance_count'], 
                                             float(x['win_rate'].replace('%', ''))), 
                               reverse=True)
        
        return jsonify({'stocks': reliability_stocks})
    except Exception as e:
        return jsonify({"error": f"Failed to analyze reliability: {str(e)}"}), 500

@app.route('/api/performance_tracking')
def get_performance_tracking():
    """获取历史信号表现追踪"""
    strategy = request.args.get('strategy', 'PRE_CROSS')
    strategy_dir = os.path.join(RESULT_PATH, strategy)
    
    if not os.path.exists(strategy_dir):
        return jsonify({"error": "Strategy directory not found"}), 404
    
    try:
        # 这里可以实现更复杂的表现追踪逻辑
        # 目前返回模拟数据作为示例
        tracking_results = []
        
        # 读取最近的信号数据
        signals_file = os.path.join(strategy_dir, 'signals_summary.json')
        if os.path.exists(signals_file):
            with open(signals_file, 'r', encoding='utf-8') as f:
                signals_data = json.load(f)
                
                for signal in signals_data[:10]:  # 只显示前10个
                    tracking_results.append({
                        'scan_date': signal.get('date', ''),
                        'stock_code': signal.get('stock_code', ''),
                        'signal_state': signal.get('signal_state', ''),
                        'expected_profit': signal.get('avg_max_profit', 'N/A'),
                        'actual_profit': 'N/A',  # 需要实际计算
                        'days_to_peak': signal.get('avg_days_to_peak', 'N/A')
                    })
        
        return jsonify({'tracking_results': tracking_results})
    except Exception as e:
        return jsonify({"error": f"Failed to track performance: {str(e)}"}), 500

@app.route('/api/multi_timeframe/<stock_code>')
def get_multi_timeframe_analysis(stock_code):
    """获取多周期分析数据"""
    try:
        strategy_name = request.args.get('strategy', 'MACD_ZERO_AXIS')
        
        # 执行多周期分析
        analysis_result = multi_timeframe.analyze_multi_timeframe_stock(
            stock_code, strategy_name, BASE_PATH
        )
        
        if not analysis_result['success']:
            return jsonify({"error": analysis_result.get('error', 'Multi-timeframe analysis failed')}), 500
        
        return jsonify(analysis_result)
        
    except Exception as e:
        print(f"Error in multi-timeframe analysis: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Multi-timeframe analysis error: {str(e)}"}), 500

@app.route('/api/timeframe_data/<stock_code>')
def get_timeframe_data(stock_code):
    """获取指定周期的原始数据"""
    try:
        timeframe = request.args.get('timeframe', 'daily')  # daily, 5min, 15min, 30min, 60min
        limit = int(request.args.get('limit', 200))  # 返回数据条数限制
        
        # 获取多周期数据
        multi_data = data_loader.get_multi_timeframe_data(stock_code, BASE_PATH)
        
        if timeframe == 'daily':
            df = multi_data['daily_data']
        elif timeframe == '5min':
            df = multi_data['min5_data']
        else:
            # 需要从5分钟数据重采样
            if multi_data['min5_data'] is None:
                return jsonify({"error": f"5-minute data not available for {stock_code}"}), 404
            
            resampled = data_loader.resample_5min_to_other_timeframes(multi_data['min5_data'])
            df = resampled.get(timeframe)
        
        if df is None or df.empty:
            return jsonify({"error": f"No data available for timeframe {timeframe}"}), 404
        
        # 限制返回数据量
        if len(df) > limit:
            df = df.tail(limit)
        
        # 转换为JSON格式
        df_copy = df.copy()
        if 'datetime' in df_copy.columns:
            df_copy['datetime'] = df_copy['datetime'].dt.strftime('%Y-%m-%d %H:%M:%S')
        if 'date' in df_copy.columns and hasattr(df_copy['date'].iloc[0], 'strftime'):
            df_copy['date'] = df_copy['date'].dt.strftime('%Y-%m-%d')
        
        # 替换NaN值
        df_copy = df_copy.replace({np.nan: None})
        
        return jsonify({
            'stock_code': stock_code,
            'timeframe': timeframe,
            'data_count': len(df_copy),
            'data': df_copy.to_dict('records')
        })
        
    except Exception as e:
        print(f"Error getting timeframe data: {e}")
        return jsonify({"error": f"Failed to get timeframe data: {str(e)}"}), 500

@app.route('/api/consensus_analysis')
def get_consensus_analysis():
    """获取多股票多周期共振分析"""
    try:
        strategy = request.args.get('strategy', 'MACD_ZERO_AXIS')
        
        # 读取当前策略的信号列表
        strategy_dir = os.path.join(RESULT_PATH, strategy)
        signals_file = os.path.join(strategy_dir, 'signals_summary.json')
        
        if not os.path.exists(signals_file):
            return jsonify({"error": f"No signals found for strategy {strategy}"}), 404
        
        with open(signals_file, 'r', encoding='utf-8') as f:
            signals_data = json.load(f)
        
        consensus_results = []
        
        # 对每个信号股票进行多周期分析
        for signal in signals_data[:10]:  # 限制分析前10个股票
            stock_code = signal.get('stock_code', '')
            if not stock_code:
                continue
            
            try:
                analysis_result = multi_timeframe.analyze_multi_timeframe_stock(
                    stock_code, strategy, BASE_PATH
                )
                
                if analysis_result['success']:
                    consensus_info = analysis_result['consensus_analysis']
                    consensus_info['daily_signal_info'] = {
                        'date': signal.get('date', ''),
                        'signal_state': signal.get('signal_state', ''),
                        'win_rate': signal.get('win_rate', 'N/A'),
                        'avg_profit': signal.get('avg_max_profit', 'N/A')
                    }
                    consensus_results.append(consensus_info)
                    
            except Exception as e:
                print(f"Error analyzing {stock_code}: {e}")
                continue
        
        # 按共振得分排序
        consensus_results.sort(key=lambda x: x.get('consensus_score', 0), reverse=True)
        
        return jsonify({
            'strategy': strategy,
            'analysis_count': len(consensus_results),
            'consensus_results': consensus_results
        })
        
    except Exception as e:
        print(f"Error in consensus analysis: {e}")
        return jsonify({"error": f"Consensus analysis failed: {str(e)}"}), 500

@app.route('/api/core_pool', methods=['GET', 'POST', 'DELETE'])
def manage_core_pool():
    """核心池管理API"""
    core_pool_file = os.path.join(RESULT_PATH, 'core_pool.json')
    
    if request.method == 'GET':
        # 获取核心池数据
        try:
            if os.path.exists(core_pool_file):
                with open(core_pool_file, 'r', encoding='utf-8') as f:
                    core_pool = json.load(f)
            else:
                core_pool = []
            
            return jsonify({
                'success': True,
                'core_pool': core_pool,
                'count': len(core_pool)
            })
        except Exception as e:
            return jsonify({'error': f'获取核心池数据失败: {str(e)}'}), 500
    
    elif request.method == 'POST':
        # 添加股票到核心池
        try:
            data = request.get_json()
            stock_code = data.get('stock_code', '').strip().upper()
            
            if not stock_code:
                return jsonify({'error': '股票代码不能为空'}), 400
            
            # 验证股票代码格式
            if not (stock_code.startswith(('SZ', 'SH')) and len(stock_code) == 8):
                return jsonify({'error': '股票代码格式不正确，应为SZ000001或SH600000格式'}), 400
            
            # 读取现有核心池
            if os.path.exists(core_pool_file):
                with open(core_pool_file, 'r', encoding='utf-8') as f:
                    core_pool = json.load(f)
            else:
                core_pool = []
            
            # 检查是否已存在
            if any(stock['stock_code'] == stock_code for stock in core_pool):
                return jsonify({'error': f'股票 {stock_code} 已在核心池中'}), 400
            
            # 添加新股票
            new_stock = {
                'stock_code': stock_code,
                'added_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'note': data.get('note', '')
            }
            core_pool.append(new_stock)
            
            # 保存核心池
            os.makedirs(os.path.dirname(core_pool_file), exist_ok=True)
            with open(core_pool_file, 'w', encoding='utf-8') as f:
                json.dump(core_pool, f, ensure_ascii=False, indent=2)
            
            return jsonify({
                'success': True,
                'message': f'股票 {stock_code} 已添加到核心池',
                'stock': new_stock
            })
            
        except Exception as e:
            return jsonify({'error': f'添加股票失败: {str(e)}'}), 500
    
    elif request.method == 'DELETE':
        # 从核心池删除股票
        try:
            stock_code = request.args.get('stock_code', '').strip().upper()
            
            if not stock_code:
                return jsonify({'error': '股票代码不能为空'}), 400
            
            if not os.path.exists(core_pool_file):
                return jsonify({'error': '核心池文件不存在'}), 404
            
            with open(core_pool_file, 'r', encoding='utf-8') as f:
                core_pool = json.load(f)
            
            # 查找并删除股票
            original_count = len(core_pool)
            core_pool = [stock for stock in core_pool if stock['stock_code'] != stock_code]
            
            if len(core_pool) == original_count:
                return jsonify({'error': f'股票 {stock_code} 不在核心池中'}), 404
            
            # 保存更新后的核心池
            with open(core_pool_file, 'w', encoding='utf-8') as f:
                json.dump(core_pool, f, ensure_ascii=False, indent=2)
            
            return jsonify({
                'success': True,
                'message': f'股票 {stock_code} 已从核心池删除'
            })
            
        except Exception as e:
            return jsonify({'error': f'删除股票失败: {str(e)}'}), 500

@app.route('/api/analysis/<stock_code>')
def get_stock_analysis(stock_code):
    try:
        strategy_name = request.args.get('strategy', 'PRE_CROSS')
        market = stock_code[:2]
        
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
        if not os.path.exists(file_path): 
            return jsonify({"error": f"Data file not found: {file_path}"}), 404

        df = data_loader.get_daily_data(file_path)
        if df is None: 
            return jsonify({"error": "Failed to load data"}), 500

        # 计算技术指标
        df['ma13'] = df['close'].rolling(13).mean()
        df['ma45'] = df['close'].rolling(45).mean()
        macd_values = indicators.calculate_macd(df)
        df['dif'], df['dea'] = macd_values[0], macd_values[1]
        kdj_values = indicators.calculate_kdj(df)
        df['k'], df['d'], df['j'] = kdj_values[0], kdj_values[1], kdj_values[2]
        # 使用配置系统中的RSI参数
        from strategy_config import get_strategy_config
        config = get_strategy_config('TRIPLE_CROSS')
        rsi_periods = [config.rsi.period_short, config.rsi.period_long, config.rsi.period_extra]
        rsi_values = [indicators.calculate_rsi(df, p) for p in rsi_periods]
        df['rsi6'], df['rsi12'], df['rsi24'] = rsi_values[0], rsi_values[1], rsi_values[2]
        
        # 应用策略
        signals = None
        if strategy_name == 'PRE_CROSS': 
            signals = strategies.apply_pre_cross(df)
        elif strategy_name == 'TRIPLE_CROSS': 
            signals = strategies.apply_triple_cross(df)
        elif strategy_name == 'MACD_ZERO_AXIS': 
            signals = strategies.apply_macd_zero_axis_strategy(df)
        
        # 执行回测
        backtest_results = backtester.run_backtest(df, signals)
        
        # 构建信号点数据
        signal_points = []
        if signals is not None and hasattr(signals, 'empty') and not signals.empty:
            try:
                if signals.dtype == bool:
                    signal_df = df[signals]
                else:
                    signal_df = df[signals != '']
                
                # 获取每个信号点的回测结果
                trade_results = {}
                if isinstance(backtest_results, dict) and 'trades' in backtest_results and 'entry_indices' in backtest_results:
                    for i, entry_idx in enumerate(backtest_results['entry_indices']):
                        if i < len(backtest_results['trades']):
                            trade_results[entry_idx] = backtest_results['trades'][i]
                
                # 构建信号点数据，包含成功/失败状态
                for idx, row in signal_df.iterrows():
                    try:
                        original_state = 'MID' if signals.dtype == bool else str(signals[idx])
                        
                        # 根据回测结果确定最终状态
                        if idx in trade_results:
                            is_success = trade_results[idx].get('is_success', False)
                            final_state = f"{original_state}_SUCCESS" if is_success else f"{original_state}_FAIL"
                        else:
                            final_state = original_state
                            
                        signal_points.append({
                            'date': idx.strftime('%Y-%m-%d'),  # idx是日期索引
                            'price': float(row['low']), 
                            'state': final_state,
                            'original_state': original_state
                        })
                    except Exception as e:
                        print(f"Error processing signal point at index {idx}: {e}")
                        continue
                        
            except Exception as e:
                print(f"Error processing signals: {e}")
                # 如果信号处理失败，返回空的信号点列表
                signal_points = []

        # 准备返回数据
        df.replace({np.nan: None}, inplace=True)
        # 重置索引，将日期索引转换为列
        df_reset = df.reset_index()
        # 确保日期列存在并格式化
        if 'date' in df_reset.columns:
            df_reset['date'] = df_reset['date'].dt.strftime('%Y-%m-%d')
        else:
            # 如果索引没有名称，第一列就是日期
            date_col = df_reset.columns[0]
            df_reset = df_reset.rename(columns={date_col: 'date'})
            df_reset['date'] = df_reset['date'].dt.strftime('%Y-%m-%d')
        
        kline_data = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        indicator_data = df_reset[['date', 'ma13', 'ma45', 'dif', 'dea', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']].to_dict('records')

        # 确保回测结果可以被JSON序列化
        if isinstance(backtest_results, dict):
            # 处理trades列表中的numpy类型
            if 'trades' in backtest_results:
                for trade in backtest_results['trades']:
                    for key, value in trade.items():
                        if hasattr(value, 'item'):  # numpy类型
                            trade[key] = value.item()
                        elif isinstance(value, (np.bool_, bool)):
                            trade[key] = bool(value)
                        elif isinstance(value, (np.integer, np.floating)):
                            trade[key] = float(value)
            
            # 处理entry_indices列表
            if 'entry_indices' in backtest_results:
                backtest_results['entry_indices'] = [int(idx) for idx in backtest_results['entry_indices']]

        return jsonify({
            'kline_data': kline_data,
            'indicator_data': indicator_data,
            'signal_points': signal_points,
            'backtest_results': backtest_results
        })
        
    except Exception as e:
        print(f"Error in get_stock_analysis: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

if __name__ == '__main__':
    print("量化分析平台后端启动...")
    print("请在浏览器中打开 http://127.0.0.1:5000")
    app.run(host='0.0.0.0', debug=True)
# 核心池管理API
@app.route('/api/core_pool')
def get_core_pool():
    """获取核心池数据"""
    try:
        # 这里应该从数据库或文件中读取核心池数据
        # 暂时返回模拟数据
        core_pool_data = load_core_pool_data()
        
        return jsonify({
            'stocks': core_pool_data['stocks'],
            'stats': core_pool_data['stats']
        })
        
    except Exception as e:
        return jsonify({"error": f"获取核心池数据失败: {str(e)}"}), 500

@app.route('/api/core_pool/add', methods=['POST'])
def add_to_core_pool():
    """添加股票到核心池"""
    try:
        data = request.get_json()
        stock_code = data.get('stock_code')
        
        if not stock_code:
            return jsonify({"error": "股票代码不能为空"}), 400
        
        # 验证股票代码是否有效
        stock_data = data_loader.load_stock_data(stock_code)
        if stock_data is None or len(stock_data) < 10:
            return jsonify({"error": f"无法加载股票 {stock_code} 的数据"}), 404
        
        # 添加到核心池
        success = add_stock_to_core_pool(stock_code)
        
        if success:
            return jsonify({"success": True, "message": f"股票 {stock_code} 已添加到核心池"})
        else:
            return jsonify({"error": "添加失败，股票可能已存在于核心池中"}), 400
        
    except Exception as e:
        return jsonify({"error": f"添加股票失败: {str(e)}"}), 500

@app.route('/api/core_pool/remove', methods=['POST'])
def remove_from_core_pool():
    """从核心池移除股票"""
    try:
        data = request.get_json()
        stock_code = data.get('stock_code')
        
        if not stock_code:
            return jsonify({"error": "股票代码不能为空"}), 400
        
        success = remove_stock_from_core_pool(stock_code)
        
        if success:
            return jsonify({"success": True, "message": f"股票 {stock_code} 已从核心池移除"})
        else:
            return jsonify({"error": "移除失败，股票不在核心池中"}), 400
        
    except Exception as e:
        return jsonify({"error": f"移除股票失败: {str(e)}"}), 500

@app.route('/api/core_pool/weight', methods=['POST'])
def update_stock_weight():
    """更新股票权重"""
    try:
        data = request.get_json()
        stock_code = data.get('stock_code')
        weight = data.get('weight')
        
        if not stock_code or weight is None:
            return jsonify({"error": "股票代码和权重不能为空"}), 400
        
        if not (0 <= weight <= 50):
            return jsonify({"error": "权重必须在0-50%之间"}), 400
        
        success = update_stock_weight_in_pool(stock_code, weight)
        
        if success:
            return jsonify({"success": True, "message": f"股票 {stock_code} 权重已更新为 {weight}%"})
        else:
            return jsonify({"error": "更新失败，股票不在核心池中"}), 400
        
    except Exception as e:
        return jsonify({"error": f"更新权重失败: {str(e)}"}), 500

@app.route('/api/core_pool/grade', methods=['POST'])
def update_stock_grade():
    """更新股票等级"""
    try:
        data = request.get_json()
        stock_code = data.get('stock_code')
        grade = data.get('grade')
        
        if not stock_code or not grade:
            return jsonify({"error": "股票代码和等级不能为空"}), 400
        
        if grade not in ['A', 'B', 'C', 'D', 'F']:
            return jsonify({"error": "等级必须是A、B、C、D、F之一"}), 400
        
        success = update_stock_grade_in_pool(stock_code, grade)
        
        if success:
            return jsonify({"success": True, "message": f"股票 {stock_code} 等级已更新为 {grade}"})
        else:
            return jsonify({"error": "更新失败，股票不在核心池中"}), 400
        
    except Exception as e:
        return jsonify({"error": f"更新等级失败: {str(e)}"}), 500

@app.route('/api/core_pool/demote', methods=['POST'])
def demote_stock():
    """降级股票"""
    try:
        data = request.get_json()
        stock_code = data.get('stock_code')
        
        if not stock_code:
            return jsonify({"error": "股票代码不能为空"}), 400
        
        success = demote_stock_in_pool(stock_code)
        
        if success:
            return jsonify({"success": True, "message": f"股票 {stock_code} 已降级"})
        else:
            return jsonify({"error": "降级失败，股票不在核心池中或已是最低等级"}), 400
        
    except Exception as e:
        return jsonify({"error": f"降级股票失败: {str(e)}"}), 500

# 核心池管理辅助函数
def load_core_pool_data():
    """加载核心池数据"""
    core_pool_file = os.path.join(RESULT_PATH, 'core_pool.json')
    
    if not os.path.exists(core_pool_file):
        # 创建默认核心池文件
        default_data = {
            'stocks': [],
            'created_at': '2025-01-28',
            'last_updated': '2025-01-28'
        }
        with open(core_pool_file, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
        return {'stocks': [], 'stats': get_core_pool_stats([])}
    
    try:
        with open(core_pool_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stocks = data.get('stocks', [])
        
        # 更新股票的实时数据
        updated_stocks = []
        for stock in stocks:
            try:
                stock_data = data_loader.load_stock_data(stock['stock_code'])
                if stock_data is not None and len(stock_data) > 0:
                    latest = stock_data.iloc[-1]
                    stock['current_price'] = latest['close']
                    
                    # 计算30天价格变化
                    if len(stock_data) >= 30:
                        price_30d_ago = stock_data.iloc[-30]['close']
                        stock['price_change'] = (latest['close'] - price_30d_ago) / price_30d_ago
                    else:
                        stock['price_change'] = 0
                    
                    updated_stocks.append(stock)
            except Exception as e:
                print(f"Error updating stock {stock['stock_code']}: {e}")
                # 保留原数据，但标记为无法更新
                stock['current_price'] = stock.get('current_price', 0)
                stock['price_change'] = stock.get('price_change', 0)
                updated_stocks.append(stock)
        
        return {
            'stocks': updated_stocks,
            'stats': get_core_pool_stats(updated_stocks)
        }
        
    except Exception as e:
        print(f"Error loading core pool data: {e}")
        return {'stocks': [], 'stats': get_core_pool_stats([])}

def get_core_pool_stats(stocks):
    """计算核心池统计数据"""
    if not stocks:
        return {
            'total_stocks': 0,
            'a_grade_stocks': 0,
            'avg_weight': 0,
            'total_weight': 0
        }
    
    total_stocks = len(stocks)
    a_grade_stocks = len([s for s in stocks if s.get('grade') == 'A'])
    total_weight = sum(s.get('weight', 0) for s in stocks)
    avg_weight = total_weight / total_stocks if total_stocks > 0 else 0
    
    return {
        'total_stocks': total_stocks,
        'a_grade_stocks': a_grade_stocks,
        'avg_weight': avg_weight,
        'total_weight': total_weight
    }

def save_core_pool_data(data):
    """保存核心池数据"""
    core_pool_file = os.path.join(RESULT_PATH, 'core_pool.json')
    data['last_updated'] = '2025-01-28'
    
    with open(core_pool_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_stock_to_core_pool(stock_code):
    """添加股票到核心池"""
    data = load_core_pool_data()
    stocks = data['stocks']
    
    # 检查是否已存在
    for stock in stocks:
        if stock['stock_code'] == stock_code:
            return False
    
    # 添加新股票
    new_stock = {
        'stock_code': stock_code,
        'grade': 'C',  # 默认等级
        'weight': 5.0,  # 默认权重
        'score': 0,
        'current_price': 0,
        'price_change': 0,
        'added_at': '2025-01-28'
    }
    
    stocks.append(new_stock)
    save_core_pool_data({'stocks': stocks})
    return True

def remove_stock_from_core_pool(stock_code):
    """从核心池移除股票"""
    data = load_core_pool_data()
    stocks = data['stocks']
    
    original_length = len(stocks)
    stocks = [s for s in stocks if s['stock_code'] != stock_code]
    
    if len(stocks) < original_length:
        save_core_pool_data({'stocks': stocks})
        return True
    return False

def update_stock_weight_in_pool(stock_code, weight):
    """更新股票权重"""
    data = load_core_pool_data()
    stocks = data['stocks']
    
    for stock in stocks:
        if stock['stock_code'] == stock_code:
            stock['weight'] = weight
            save_core_pool_data({'stocks': stocks})
            return True
    return False

def update_stock_grade_in_pool(stock_code, grade):
    """更新股票等级"""
    data = load_core_pool_data()
    stocks = data['stocks']
    
    for stock in stocks:
        if stock['stock_code'] == stock_code:
            stock['grade'] = grade
            save_core_pool_data({'stocks': stocks})
            return True
    return False

def demote_stock_in_pool(stock_code):
    """降级股票"""
    data = load_core_pool_data()
    stocks = data['stocks']
    
    grade_order = ['A', 'B', 'C', 'D', 'F']
    
    for stock in stocks:
        if stock['stock_code'] == stock_code:
            current_grade = stock.get('grade', 'C')
            if current_grade in grade_order:
                current_index = grade_order.index(current_grade)
                if current_index < len(grade_order) - 1:
                    stock['grade'] = grade_order[current_index + 1]
                    save_core_pool_data({'stocks': stocks})
                    return True
    return False