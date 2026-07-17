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
from golden_trend import calculate_golden_trend, GoldenTrendConfig
from adjustment_processor import create_adjustment_config, create_adjustment_processor, AdjustmentProcessor, AdjustmentConfig
from portfolio_manager import create_portfolio_manager
from strategy_manager import strategy_manager
from config_manager import config_manager
# 尝试导入MA13策略API
try:
    from ma13_strategy_api import ma13_bp
    ma13_available = True
except ImportError as e:
    print(f"警告: 无法导入ma13_strategy_api: {e}")
    ma13_bp = None
    ma13_available = False

# 导入增强MA13 API
try:
    from enhanced_ma13_api import enhanced_ma13_bp
    enhanced_ma13_available = True
except ImportError as e:
    print(f"警告: 无法导入enhanced_ma13_api: {e}")
    enhanced_ma13_bp = None
    enhanced_ma13_available = False

# --- 配置路径 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
frontend_dir = os.path.abspath(os.path.join(backend_dir, '..', 'frontend'))
RESULT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
CORE_POOL_FILE = os.path.join(RESULT_PATH, 'core_pool.json')

app = Flask(__name__, static_folder=frontend_dir, static_url_path='')
CORS(app)

# --- 复权处理器单例（按类型缓存，避免每次请求重建）---
_adj_processors: dict = {}

def get_adj_processor(adjustment_type: str) -> AdjustmentProcessor:
    # 等待后台预热完成（最多等 60s，正常 10s 内完成）
    _gbbq_ready.wait(timeout=60)
    if adjustment_type not in _adj_processors:
        _adj_processors[adjustment_type] = AdjustmentProcessor(
            AdjustmentConfig(adjustment_type=adjustment_type)
        )
    return _adj_processors[adjustment_type]

# --- gbbq 后台预热：模块导入时立即在后台线程加载，不 block 启动也不 block 请求 ---
import threading as _threading

_gbbq_ready = _threading.Event()

def _preload_gbbq():
    try:
        from gbbq_reader import read_gbbq
        read_gbbq()
        print("✅ 复权数据加载完成（后台）")
    except Exception as e:
        print(f"⚠️ 复权数据预加载失败: {e}")
    finally:
        _gbbq_ready.set()

_threading.Thread(target=_preload_gbbq, daemon=True, name='gbbq-preload').start()

# 注册MA13策略蓝图
if ma13_available and ma13_bp:
    app.register_blueprint(ma13_bp)
    print("已注册原版MA13策略API")

# 注册增强MA13策略蓝图
if enhanced_ma13_available and enhanced_ma13_bp:
    app.register_blueprint(enhanced_ma13_bp)
    print("已注册增强MA13策略API")

# --- JSON序列化修复函数 ---
def safe_jsonify(data):
    """
    【修复】安全的Flask JSON响应，处理numpy类型和Timestamp
    """
    def convert_types(item):
        if isinstance(item, dict):
            return {k: convert_types(v) for k, v in item.items()}
        if isinstance(item, list):
            return [convert_types(i) for i in item]
        # --- [核心修复逻辑] ---
        if isinstance(item, (datetime, pd.Timestamp)):
            return item.isoformat()
        # --- [numpy 类型处理] ---
        if hasattr(item, 'item'): 
            return item.item()
        if isinstance(item, (np.bool_, bool)): 
            return bool(item)
        if isinstance(item, (np.integer)): 
            return int(item)
        if isinstance(item, (np.floating)): 
            return float(item)
        return item
    
    try:
        converted_data = convert_types(data)
        return jsonify(converted_data)
    except Exception as e:
        app.logger.error(f"JSON序列化失败: {e}")
        return jsonify({'success': False, 'error': f'数据序列化失败: {str(e)}'})

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

@app.route('/ma13_strategy')
def ma13_strategy_page():
    """MA13短线策略页面"""
    return send_from_directory(os.path.join(backend_dir, '..', 'templates'), 'ma13_strategy.html')

# --- API 端点 ---


@app.route("/api/stock_search")
def search_stocks_api():
    """按代码、名称、拼音首字母或全拼搜索股票"""
    from stock_name_reader import search_stocks
    query = request.args.get("q", "").strip()
    limit = min(int(request.args.get("limit", 20)), 50)
    if not query:
        return jsonify({"success": True, "results": []})
    try:
        results = search_stocks(query, limit=limit)
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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
            
            # 策略配置更新后，清理相关缓存
            from analysis_cache import analysis_cache
            analysis_cache.invalidate_cache(strategy_id=strategy_id)
            app.logger.info(f"策略 {strategy_id} 配置已更新，相关缓存已清理")
            
            return jsonify({
                'success': True,
                'message': f'策略 {strategy_id} 配置已更新'
            })
        except Exception as e:
            app.logger.error(f'更新策略配置失败: {str(e)}')
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
            
            # 策略ID映射
            strategy_mapping = {
                'PRE_CROSS': '临界金叉_v1.0',
                'TRIPLE_CROSS': '三重金叉_v1.0', 
                'MACD_ZERO_AXIS': 'macd零轴启动_v1.0',
                'WEEKLY_GOLDEN_CROSS_MA': '周线金叉+日线ma_v1.0',
                'ABYSS_BOTTOMING': '深渊筑底策略_v2.0'
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

@app.route('/api/strategies/<strategy_id>/stocks')
def get_stocks_for_strategy(strategy_id):
    """
    【缓存优化版】获取策略的信号股票列表。
    优先从策略筛选缓存读取，若无缓存或数据已更新则重新筛选。
    """
    try:
        from strategy_screening_cache import strategy_screening_cache
        from stock_pool_manager import StockPoolManager
        
        # 1. 优先从策略筛选缓存中获取结果
        cached_results = strategy_screening_cache.get_cached_screening_results(strategy_id)
        
        if cached_results:
            print(f"⚡️ 策略筛选缓存命中: 直接返回策略 '{strategy_id}' 的 {len(cached_results)} 个结果。")
            return safe_jsonify({'success': True, 'data': cached_results, 'from_cache': True})

        # 2. 如果缓存未命中，则启动筛选
        print(f"⏳ 策略筛选缓存未命中: 为策略 '{strategy_id}' 启动筛选...")
        from universal_screener import UniversalScreener
        
        screener = UniversalScreener()
        results = screener.run_screening([strategy_id])
        
        # 3. 构建返回数据
        from stock_name_reader import get_stock_name
        stock_list = []
        for result in results:
            stock_data = {
                'stock_code': result.stock_code,
                'stock_name': get_stock_name(result.stock_code),
                'date': str(result.date),
                'signal_type': result.signal_type,
                'price': result.current_price
            }
            stock_list.append(stock_data)
        
        # 4. 保存到缓存
        strategy_screening_cache.save_screening_results(strategy_id, stock_list)
        
        return safe_jsonify({'success': True, 'data': stock_list, 'from_cache': False})
        
    except Exception as e:
        app.logger.error(f"为策略 {strategy_id} 获取股票列表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"无法获取策略 '{strategy_id}' 的股票列表: {str(e)}"}), 500

@app.route('/api/cache/strategy_screening/stats')
def get_strategy_screening_cache_stats():
    """获取策略筛选缓存统计信息"""
    try:
        from strategy_screening_cache import strategy_screening_cache
        stats = strategy_screening_cache.get_cache_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cache/strategy_screening/clear', methods=['POST'])
def clear_strategy_screening_cache():
    """清理策略筛选缓存"""
    try:
        from strategy_screening_cache import strategy_screening_cache
        data = request.get_json() or {}
        
        strategy_id = data.get('strategy_id')
        older_than_days = data.get('older_than_days')
        
        deleted_count = strategy_screening_cache.invalidate_cache(
            strategy_id=strategy_id,
            older_than_days=older_than_days
        )
        
        return jsonify({
            'success': True,
            'message': f'已清理 {deleted_count} 条缓存记录',
            'deleted_count': deleted_count
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cache/strategy_screening/refresh/<strategy_id>', methods=['POST'])
def refresh_strategy_screening_cache(strategy_id):
    """强制刷新指定策略的筛选缓存"""
    try:
        from strategy_screening_cache import strategy_screening_cache
        from universal_screener import UniversalScreener
        from stock_pool_manager import StockPoolManager
        
        # 清理旧缓存
        strategy_screening_cache.invalidate_cache(strategy_id)
        
        # 重新筛选
        screener = UniversalScreener()
        results = screener.run_screening([strategy_id])
        
        # 构建数据并保存到缓存
        from stock_name_reader import get_stock_name
        stock_list = []
        for result in results:
            stock_data = {
                'stock_code': result.stock_code,
                'stock_name': get_stock_name(result.stock_code),
                'date': str(result.date),
                'signal_type': result.signal_type,
                'price': result.current_price
            }
            stock_list.append(stock_data)
        
        strategy_screening_cache.save_screening_results(strategy_id, stock_list)
        
        return jsonify({
            'success': True,
            'message': f'策略 {strategy_id} 的缓存已刷新',
            'stock_count': len(stock_list),
            'data': stock_list
        })
        
    except Exception as e:
        app.logger.error(f"刷新策略 {strategy_id} 缓存失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
            df = get_adj_processor(adjustment_type).process_data(df, stock_code)

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
        
        # 计算多个周期的RSI（使用复权配置，与MACD/KDJ保持一致）
        rsi6_config = indicators.RSIIndicatorConfig(period=6, adjustment_config=adjustment_config)
        rsi12_config = indicators.RSIIndicatorConfig(period=12, adjustment_config=adjustment_config)
        rsi24_config = indicators.RSIIndicatorConfig(period=24, adjustment_config=adjustment_config)
        df['rsi6'] = indicators.calculate_rsi(df, config=rsi6_config, stock_code=stock_code)
        df['rsi12'] = indicators.calculate_rsi(df, config=rsi12_config, stock_code=stock_code)
        df['rsi24'] = indicators.calculate_rsi(df, config=rsi24_config, stock_code=stock_code)

        # 金钻趋势双轨 (自适应参数)
        gt_config = GoldenTrendConfig(adaptive=True)
        gt_series, ema_h, ema_l, gt_meta = calculate_golden_trend(df, config=gt_config, stock_code=stock_code)
        df['gt_upper'] = ema_h
        df['gt_lower'] = gt_series
        df['gt_mid'] = (ema_h + ema_l) / 2

        # 趋势EMA指标 (通达信双EMA策略)
        close = df['close'].astype(float)
        ema13 = close.ewm(span=13, adjust=False).mean()
        df['mtl'] = ema13.ewm(span=13, adjust=False).mean()
        df['mtl_rising'] = (df['mtl'] > df['mtl'].shift(1)).astype(int)

        df['ema5'] = close.ewm(span=5, adjust=False).mean()
        df['ema10'] = close.ewm(span=10, adjust=False).mean()
        df['ema20'] = close.ewm(span=20, adjust=False).mean()

        aa = df['ema5'] > df['ema20']
        bb = df['ema5'] < df['ema20']
        cc = df['ema5'] > df['ema10']
        cc1 = df['ema5'] < df['ema10']

        candle_color = pd.Series(0, index=df.index)
        candle_color[aa] = 1
        candle_color[bb] = -1
        candle_color[bb & cc] = 0
        candle_color[aa & cc1] = 0
        df['candle_color'] = candle_color

        buy_sig = (
            (close > df['mtl']) &
            (close.shift(1) <= df['mtl'].shift(1)) &
            (df['mtl_rising'] == 1)
        )
        sell_cond = (candle_color == -1) & (close < df['low'].shift(1))
        sell_sig = sell_cond & ~sell_cond.shift(1).fillna(False)
        df['trend_buy'] = buy_sig.astype(int)
        df['trend_sell'] = sell_sig.astype(int)

        # 应用策略和回测
        signals = None
        
        # --- 新增的保护性代码 ---
        if strategy_name:
            # 使用统一配置管理器查找策略ID
            strategy_id = config_manager.find_strategy_by_old_id(strategy_name)
            
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
        else:
            # 如果策略名为空，直接创建一个空的信号序列
            print(f"警告: 未提供策略名称，将不应用任何信号。")
            signals = pd.Series([''] * len(df), index=df.index)
        # --- 保护性代码结束 ---
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
        indicator_data = df_reset[['date', 'ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24', 'gt_upper', 'gt_lower', 'gt_mid', 'mtl', 'mtl_rising', 'ema5', 'ema10', 'ema20', 'candle_color', 'trend_buy', 'trend_sell']].to_dict('records')
        
        # 序列化回测结果
        if isinstance(backtest_results, dict):
            backtest_results = json.loads(json.dumps(backtest_results, default=lambda x: x.item() if isinstance(x, (np.integer, np.floating)) else bool(x) if isinstance(x, np.bool_) else None))

        return safe_jsonify({
            'kline_data': kline_data,
            'indicator_data': indicator_data,
            'signal_points': signal_points,
            'backtest_results': backtest_results,
            'golden_trend_meta': gt_meta,
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
            df = get_adj_processor(adjustment_type).process_data(df, stock_code)
        
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
        
        return safe_jsonify({
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

        # 批量获取股票名称
        from stock_name_reader import get_stock_name

        processed = [{
            'stock_code': k,
            'stock_name': get_stock_name(k),
            'score': v.get('overall_score', {}).get('total_score', 0),
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
    """运行深度扫描"""
    try:
        import threading
        from universal_screener import UniversalScreener
        
        def run_screening_task():
            """后台运行筛选任务"""
            try:
                screener = UniversalScreener()
                # 使用多个策略进行筛选
                strategy_ids = ['PRE_CROSS', 'MACD_ZERO_AXIS', 'RSI_BOTTOM']
                results = screener.run_screening(strategy_ids, max_workers=16)
                app.logger.info(f"深度扫描完成，发现 {len(results)} 个高质量信号")
            except Exception as e:
                app.logger.error(f"深度扫描任务失败: {e}")
        
        # 在后台线程中运行筛选
        thread = threading.Thread(target=run_screening_task)
        thread.daemon = True
        thread.start()
        
        return jsonify({"success": True, "message": "深度扫描已启动，正在后台处理中..."})
        
    except Exception as e:
        app.logger.error(f"启动深度扫描失败: {e}")
        return jsonify({"success": False, "error": f"启动深度扫描失败: {str(e)}"}), 500

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

@app.route('/api/core_pool/analysis')
def get_core_pool_analysis():
    """
    【新增API】获取核心池股票的完整分析列表
    """
    try:
        core_pool_stocks = load_core_pool_from_file()
        
        analysis_results = []
        for stock_info in core_pool_stocks:
            stock_code = stock_info['stock_code']
            
            # 为每只股票调用深度分析
            # 注意：这里为了性能，应该利用缓存
            # _get_or_generate_backtest_analysis 内部有缓存机制
            pm = create_portfolio_manager()
            df = pm.get_stock_data(stock_code)
            if df is None:
                analysis = {'error': '数据加载失败'}
            else:
                df = pm.calculate_technical_indicators(df, stock_code)
                analysis = pm._get_or_generate_backtest_analysis(stock_code, df)

            # 合并基础信息和分析结果
            merged_info = {**stock_info, **analysis}
            analysis_results.append(merged_info)
        
        return jsonify({'success': True, 'core_pool': analysis_results})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'核心池分析失败: {str(e)}'}), 500

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

@app.route('/api/unified_analysis/<stock_code>')
def get_unified_stock_analysis(stock_code):
    """
    【统一分析接口 - 数据库缓存版】
    整合所有分析功能并实现数据库缓存机制，避免重复计算
    包含增强版交易建议功能
    """
    try:
        from unified_analysis_service import get_or_run_analysis
        
        # 获取请求参数
        strategy_name = request.args.get('strategy', 'PRE_CROSS')
        timeframe = request.args.get('timeframe', 'daily')
        adjustment_type = request.args.get('adjustment', 'forward')
        app.logger.info(f"统一分析请求: {stock_code}, 策略: {strategy_name}, 周期: {timeframe}, 复权: {adjustment_type}")
        
        # 使用统一配置管理器查找策略ID
        strategy_id = config_manager.find_strategy_by_old_id(strategy_name)
        if not strategy_id:
            app.logger.warning(f"策略映射失败，使用原名: {strategy_name}")
            strategy_id = strategy_name
        else:
            app.logger.info(f"策略映射成功: {strategy_name} -> {strategy_id}")
        
        # 调用统一分析服务（包含缓存机制）
        result = get_or_run_analysis(stock_code, strategy_id, timeframe=timeframe, adjustment_type=adjustment_type)
        
        if result['success']:
            app.logger.info(f"统一分析成功: {stock_code}, 缓存状态: {result['data'].get('from_cache', False)}")
            return safe_jsonify(result)
        else:
            app.logger.error(f"统一分析失败: {stock_code}, 错误: {result.get('error', '未知错误')}")
            return safe_jsonify(result), 500

    except Exception as e:
        import traceback
        app.logger.error(f"统一分析接口异常: {stock_code}, 错误: {str(e)}")
        traceback.print_exc()
        return safe_jsonify({
            'success': False, 
            'error': f'统一分析接口错误: {str(e)}'
        }), 500


# --- 缓存管理API ---


@app.route('/api/cache/clear_expired', methods=['POST'])
def clear_expired_cache_api():
    """清理过期的缓存（例如，7天前的数据）"""
    try:
        # This function is no longer defined in the service, call the cache directly
        from analysis_cache import analysis_cache
        data = request.get_json() or {}
        days_old = data.get('days_old', 7)
        
        deleted_count = analysis_cache.clear_old_cache(days_old)
        
        return jsonify({
            'success': True,
            'message': f'Expired cache cleared, {deleted_count} records deleted.',
            'deleted_count': deleted_count
        })
    except Exception as e:
        app.logger.error(f'清理过期缓存失败: {str(e)}')
        return jsonify({
            'success': False,
            'error': f'清理过期缓存失败: {str(e)}'
        }), 500

# --- 缓存管理API ---
@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """清理缓存"""
    try:
        data = request.get_json() or {}
        stock_code = data.get('stock_code')
        strategy_id = data.get('strategy_id')
        
        from analysis_cache import analysis_cache
        deleted_count = analysis_cache.invalidate_cache(stock_code=stock_code, strategy_id=strategy_id)
        
        app.logger.info(f"缓存清理完成，删除 {deleted_count} 条记录")
        
        return jsonify({
            'success': True,
            'message': f'缓存清理完成，删除 {deleted_count} 条记录',
            'deleted_count': deleted_count
        })
    except Exception as e:
        app.logger.error(f'缓存清理失败: {str(e)}')
        return jsonify({
            'success': False,
            'error': f'缓存清理失败: {str(e)}'
        }), 500

@app.route('/api/cache/stats', methods=['GET'])
def get_cache_stats():
    """获取缓存统计信息"""
    try:
        from analysis_cache import analysis_cache
        stats = analysis_cache.get_cache_stats()
        
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        app.logger.error(f'获取缓存统计失败: {str(e)}')
        return jsonify({
            'success': False,
            'error': f'获取缓存统计失败: {str(e)}'
        }), 500

# ── 板块数据 API ──────────────────────────────────────────────────────────────

@app.route('/api/stock/<stock_code>/blocks')
def get_stock_block_info(stock_code):
    """获取个股所属板块信息"""
    try:
        from block_reader import get_stock_all_blocks
        blocks = get_stock_all_blocks(stock_code)
        # 合并 concept + special，去重
        concept = blocks.get('concept', [])
        special = blocks.get('special', [])
        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'concept_blocks': concept,
            'special_blocks': special,
            'all_blocks': concept + [b for b in special if b not in concept],
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/blocks/list')
def get_blocks_list():
    """获取所有板块列表"""
    try:
        from block_reader import list_all_blocks
        block_type = request.args.get('type', 'concept')
        df = list_all_blocks(block_type)
        return jsonify({
            'success': True,
            'block_type': block_type,
            'blocks': df.to_dict('records'),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/blocks/<block_name>/stocks')
def get_block_stock_list(block_name):
    """获取板块内所有股票"""
    try:
        from block_reader import get_block_stocks
        block_type = request.args.get('type', 'concept')
        codes = get_block_stocks(block_name, block_type)
        return jsonify({
            'success': True,
            'block_name': block_name,
            'stock_count': len(codes),
            'stocks': codes,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/blocks/<block_name>/screen')
def screen_block_stocks(block_name):
    """对板块内股票运行策略筛选，按评分排列返回"""
    try:
        from block_reader import get_block_stocks
        from stock_name_reader import get_stock_name
        import data_loader as _dl
        import strategies as _strat
        import indicators as _ind
        import backtester as _bt
        from adjustment_processor import AdjustmentProcessor, AdjustmentConfig

        block_type = request.args.get('type', 'concept')
        strategy_id = request.args.get('strategy', 'PRE_CROSS').upper()

        codes = get_block_stocks(block_name, block_type)
        if not codes:
            return jsonify({'success': True, 'block_name': block_name,
                            'strategy': strategy_id, 'results': [], 'total': 0})

        adj_processor = AdjustmentProcessor(AdjustmentConfig(adjustment_type='forward'))
        _gbbq_ready.wait(timeout=30)

        valid_prefixes = ('600', '601', '603', '000', '001', '002', '003', '300', '688')
        results = []

        for code in codes:
            try:
                if code.startswith('sh'):
                    market, pure = 'sh', code[2:]
                elif code.startswith('sz'):
                    market, pure = 'sz', code[2:]
                elif code.startswith('bj'):
                    market, pure = 'bj', code[2:]
                else:
                    continue

                if not pure.startswith(valid_prefixes):
                    continue

                file_path = os.path.join(BASE_PATH, market, 'lday', f'{code}.day')
                if not os.path.exists(file_path):
                    continue

                df = _dl.get_daily_data(file_path)
                if df is None or len(df) < 150:
                    continue

                df = adj_processor.process_data(df, pure)

                signal_series = None
                signal_state = None

                if strategy_id == 'PRE_CROSS':
                    signal_series = _strat.apply_pre_cross(df)
                    if signal_series is None or not signal_series.iloc[-1]:
                        continue
                elif strategy_id == 'TRIPLE_CROSS':
                    signal_series = _strat.apply_triple_cross(df)
                    if signal_series is None or not signal_series.iloc[-1]:
                        continue
                elif strategy_id == 'MACD_ZERO_AXIS':
                    signal_series = _strat.apply_macd_zero_axis_strategy(df)
                    signal_state = signal_series.iloc[-1] if signal_series is not None else None
                    if signal_state not in ['PRE', 'MID', 'POST']:
                        continue
                elif strategy_id == 'WEEKLY_GOLDEN_CROSS_MA':
                    signal_series = _strat.apply_weekly_golden_cross_ma_strategy(df)
                    signal_state = signal_series.iloc[-1] if signal_series is not None else None
                    if signal_state not in ['BUY', 'HOLD', 'SELL']:
                        continue
                else:
                    continue

                if 'dif' not in df.columns:
                    mv = _ind.calculate_macd(df)
                    df['dif'], df['dea'] = mv[0], mv[1]
                if 'k' not in df.columns:
                    kv = _ind.calculate_kdj(df)
                    df['k'], df['d'], df['j'] = kv[0], kv[1], kv[2]

                bt = _bt.run_backtest(df, signal_series)
                win_rate_str = bt.get('win_rate', '0.0%') if isinstance(bt, dict) else '0.0%'
                profit_str = bt.get('avg_max_profit', '0.0%') if isinstance(bt, dict) else '0.0%'
                total_signals = bt.get('total_signals', 0) if isinstance(bt, dict) else 0

                try:
                    profit_val = float(profit_str.replace('%', ''))
                except Exception:
                    profit_val = 0.0
                try:
                    win_val = float(win_rate_str.replace('%', ''))
                except Exception:
                    win_val = 0.0

                results.append({
                    'stock_code': code,
                    'stock_name': get_stock_name(code),
                    'signal_state': signal_state or 'BUY',
                    'total_signals': total_signals,
                    'win_rate': win_rate_str,
                    'avg_max_profit': profit_str,
                    'avg_max_drawdown': bt.get('avg_max_drawdown', '0.0%') if isinstance(bt, dict) else '0.0%',
                    'avg_days_to_peak': bt.get('avg_days_to_peak', '0.0 天') if isinstance(bt, dict) else '0.0 天',
                    '_profit_val': profit_val,
                    '_win_val': win_val,
                })
            except Exception:
                continue

        results.sort(key=lambda x: (x['_profit_val'], x['_win_val']), reverse=True)
        for r in results:
            r.pop('_profit_val', None)
            r.pop('_win_val', None)

        return safe_jsonify({
            'success': True,
            'block_name': block_name,
            'strategy': strategy_id,
            'total': len(results),
            'results': results,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500



# ── 个股公告/快讯 API ─────────────────────────────────────────────────────────

@app.route('/api/stock/<stock_code>/announcements')
def get_stock_announcements(stock_code):
    """获取个股最新公告（东方财富）"""
    try:
        import requests as req
        # 提取纯数字代码
        pure_code = stock_code.replace('sh', '').replace('sz', '').replace('bj', '')
        page_size = int(request.args.get('page_size', 10))
        ann_type = request.args.get('ann_type', 'A')  # A=全部

        url = 'https://np-anotice-stock.eastmoney.com/api/security/ann'
        params = {
            'sr': -1,
            'page_size': page_size,
            'page_index': 1,
            'ann_type': ann_type,
            'client_source': 'web',
            'stock_list': pure_code,
        }
        r = req.get(url, params=params, timeout=8)
        data = r.json()

        if not data.get('success', False) and data.get('error'):
            return jsonify({'success': False, 'error': data['error']}), 500

        items = data.get('data', {}).get('list', [])
        announcements = []
        for item in items:
            announcements.append({
                'title': item.get('title', ''),
                'date': item.get('notice_date', '')[:10],
                'art_code': item.get('art_code', ''),
                'url': f"https://data.eastmoney.com/notices/detail/{item.get('art_code', '')}.html",
            })

        return jsonify({
            'success': True,
            'stock_code': stock_code,
            'total': len(announcements),
            'announcements': announcements,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stock_names', methods=['POST'])
def get_stock_names_batch():
    """批量获取股票名称，body: {"codes": ["sh600519", ...]}"""
    try:
        from stock_name_reader import get_stock_names
        codes = (request.get_json() or {}).get('codes', [])
        return jsonify({'success': True, 'names': get_stock_names(codes)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("量化分析平台后端启动...")
    print("🚀 新功能：数据库缓存系统已启用")
    print("📊 增强版交易建议已集成")
    print("⏳ 复权数据正在后台加载中...")
    print("请在浏览器中打开 http://127.0.0.1:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)