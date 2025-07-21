import os
import json
import numpy as np
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import data_loader
import indicators
import strategies
import backtester

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
