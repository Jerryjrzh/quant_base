#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略加载修复
验证前端策略选择是否正常工作
"""

import os
import sys
import json
import logging
import threading
import time
import webbrowser
from pathlib import Path

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS
from config_manager import config_manager
from strategy_manager import strategy_manager

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 创建测试应用
app = Flask(__name__)
CORS(app)

# 静态文件目录
frontend_dir = os.path.join(os.path.dirname(__file__), 'frontend')

@app.route('/')
def index():
    """主页"""
    return send_from_directory(frontend_dir, 'index.html')

@app.route('/<path:filename>')
def static_files(filename):
    """静态文件"""
    if filename.startswith('js/') or filename.startswith('css/'):
        return send_from_directory(frontend_dir, filename)
    return send_from_directory(os.path.dirname(__file__), filename)

@app.route('/api/strategies')
def get_available_strategies():
    """获取可用策略列表"""
    try:
        logger.info("收到策略列表请求")
        strategies = strategy_manager.get_available_strategies()
        logger.info(f"返回策略数量: {len(strategies)}")
        
        response = {
            'success': True,
            'strategies': strategies
        }
        
        logger.info(f"策略列表: {[s['id'] for s in strategies]}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"获取策略列表失败: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'获取策略列表失败: {str(e)}'
        }), 500

@app.route('/api/config/unified')
def get_unified_config():
    """获取统一配置API"""
    try:
        logger.info("收到统一配置请求")
        response = {
            'success': True,
            'data': config_manager.config
        }
        logger.info(f"返回配置版本: {config_manager.config.get('version', 'unknown')}")
        return jsonify(response)
    except Exception as e:
        logger.error(f"获取统一配置失败: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/test/debug')
def debug_info():
    """调试信息"""
    try:
        debug_data = {
            'config_loaded': config_manager.config is not None,
            'config_version': config_manager.config.get('version', 'unknown'),
            'strategies_count': len(config_manager.get_strategies()),
            'registered_strategies': list(strategy_manager.registered_strategies.keys()),
            'enabled_strategies': config_manager.get_enabled_strategies(),
            'strategy_manager_available': len(strategy_manager.get_available_strategies())
        }
        
        return jsonify({
            'success': True,
            'debug': debug_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def open_browser():
    """延迟打开浏览器"""
    time.sleep(2)
    webbrowser.open('http://localhost:5002')

def main():
    """主函数"""
    print("🚀 启动策略加载测试服务器")
    print("📡 测试地址: http://localhost:5002")
    print("🔧 配置文件:", config_manager.config_path)
    print("📊 配置中的策略数量:", len(config_manager.get_strategies()))
    print("🎯 注册的策略数量:", len(strategy_manager.registered_strategies))
    print("✅ 可用策略数量:", len(strategy_manager.get_available_strategies()))
    print()
    
    # 打印调试信息
    print("=== 调试信息 ===")
    print("配置中的策略:")
    for strategy_id, strategy in config_manager.get_strategies().items():
        print(f"  - {strategy_id}: {strategy.get('name', 'unknown')} (启用: {strategy.get('enabled', True)})")
    
    print("\n注册的策略类:")
    for strategy_id in strategy_manager.registered_strategies.keys():
        print(f"  - {strategy_id}")
    
    print("\n可用策略:")
    available = strategy_manager.get_available_strategies()
    for strategy in available:
        print(f"  - {strategy['id']}: {strategy['name']} v{strategy['version']} (启用: {strategy['enabled']})")
    
    print("\n=== 启动服务器 ===")
    
    # 在后台线程中打开浏览器
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    # 启动服务器
    try:
        app.run(host='0.0.0.0', port=5002, debug=False)
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")

if __name__ == '__main__':
    main()