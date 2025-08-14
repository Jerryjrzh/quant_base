#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动统一配置测试服务器
"""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

from flask import Flask, send_from_directory
from flask_cors import CORS
from config_manager import config_manager

# 创建测试应用
app = Flask(__name__)
CORS(app)

# 静态文件目录
frontend_dir = os.path.dirname(__file__)

@app.route('/')
def index():
    """主页"""
    return send_from_directory(frontend_dir, 'test_frontend_unified_config.html')

@app.route('/frontend/<path:filename>')
def frontend_files(filename):
    """前端文件"""
    return send_from_directory(os.path.join(frontend_dir, 'frontend'), filename)

@app.route('/api/config/unified')
def get_unified_config():
    """获取统一配置API"""
    try:
        return {
            'success': True,
            'data': config_manager.config
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }, 500

def open_browser():
    """延迟打开浏览器"""
    time.sleep(2)
    webbrowser.open('http://localhost:5001')

def main():
    """主函数"""
    print("🚀 启动统一配置测试服务器")
    print("📡 测试地址: http://localhost:5001")
    print("🔧 配置文件:", config_manager.config_path)
    print("📊 策略数量:", len(config_manager.get_strategies()))
    print()
    
    # 在后台线程中打开浏览器
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True
    browser_thread.start()
    
    # 启动服务器
    try:
        app.run(host='0.0.0.0', port=5001, debug=False)
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")

if __name__ == '__main__':
    main()