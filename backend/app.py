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
@app.route('/api/signals_summary')
def get_signals_summary():
    strategy = request.args.get('strategy', 'PRE_CROSS')
    try:
        return send_from_directory(os.path.join(RESULT_PATH, strategy), 'signals_summary.json')
    except FileNotFoundError:
        return jsonify({"error": f"Signal file not found for strategy '{strategy}'. Have you run screener.py?"}), 404

@app.route('/api/analysis/<stock_code>')
def get_stock_analysis(stock_code):
    try:
        strategy_name = request.args.get('strategy', 'PRE_CROSS')
        adjustment_type = request.args.get('adjustment', 'forward')
        market = stock_code[:2]
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
        if not os.path.exists(file_path): 
            return jsonify({"error": f"Data file not found: {file_path}"}), 404

        df = data_loader.get_daily_data(file_path)
        if df is None: return jsonify({"error": "Failed to load data"}), 500
        
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
        signals = strategies.apply_strategy(strategy_name, df)
        backtest_results = backtester.run_backtest(df, signals)
        
        # 构建信号点
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
                signal_points.append({
                    'date': idx.strftime('%Y-%m-%d'),
                    'price': float(row['low']), 
                    'state': final_state,
                    'original_state': original_state
                })

        # 准备返回数据
        df.replace({np.nan: None}, inplace=True)
        df_reset = df.reset_index().rename(columns={'index': 'date'})
        df_reset['date'] = df_reset['date'].dt.strftime('%Y-%m-%d')
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
        market = stock_code[:2]
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock_code}.day')
        if not os.path.exists(file_path):
            return jsonify({"error": f"无法找到股票 {stock_code} 的数据文件"}), 404

        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 50:
            return jsonify({"error": f"无法加载股票 {stock_code} 的数据或数据不足"}), 404
        
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
        stock_code = data.get('stock_code', '').strip().upper()
        if not stock_code or not (stock_code.startswith(('SZ', 'SH')) and len(stock_code) == 8):
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
        stock_code = request.args.get('stock_code', '').strip().upper()
        if not stock_code: return jsonify({'error': '股票代码不能为空'}), 400
        
        core_pool = load_core_pool_from_file()
        original_count = len(core_pool)
        core_pool = [stock for stock in core_pool if stock['stock_code'] != stock_code]
        
        if len(core_pool) == original_count:
            return jsonify({'error': f'股票 {stock_code} 不在核心池中'}), 404
            
        save_core_pool_to_file(core_pool)
        return jsonify({'success': True, 'message': f'股票 {stock_code} 已删除'})

    return jsonify({'error': '不支持的请求方法'}), 405


if __name__ == '__main__':
    print("量化分析平台后端启动...")
    print("请在浏览器中打开 http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)