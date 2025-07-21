import os
import json
import glob
import numpy as np
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

@app.route('/api/history_reports')
def get_history_reports():
    """获取历史筛选报告列表"""
    strategy = request.args.get('strategy', 'PRE_CROSS')
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
        df['dif'], df['dea'] = indicators.calculate_macd(df)
        df['k'], df['d'], df['j'] = indicators.calculate_kdj(df)
        df['rsi6'], df['rsi12'], df['rsi24'] = [indicators.calculate_rsi(df, p) for p in [6, 12, 24]]
        
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
                            'date': row['date'].strftime('%Y-%m-%d'), 
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
        df['date'] = df['date'].dt.strftime('%Y-%m-%d')
        kline_data = df[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        indicator_data = df[['date', 'ma13', 'ma45', 'dif', 'dea', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']].to_dict('records')

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
