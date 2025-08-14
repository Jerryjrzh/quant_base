#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
启动策略股票列表API服务
用于测试前端策略选择后股票列表显示功能
"""

import os
import sys
import time
import threading
from datetime import datetime

# 添加backend路径
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

def start_screening_api():
    """启动筛选API服务"""
    print("🚀 启动筛选API服务...")
    os.chdir(backend_path)
    
    try:
        from screening_api import app
        print("📡 筛选API服务启动成功")
        print("🌐 服务地址: http://localhost:5000")
        print("📋 可用接口:")
        print("  GET  /api/strategies - 获取策略列表")
        print("  GET  /api/strategies/{id}/stocks - 获取策略股票列表")
        print("  GET  /api/signals_summary?strategy={old_id} - 兼容接口")
        print("  GET  /api/config/unified - 获取统一配置")
        print("\n⚡ 按 Ctrl+C 停止服务")
        
        app.run(host='0.0.0.0', port=5000, debug=False)
        
    except Exception as e:
        print(f"❌ 启动筛选API服务失败: {e}")
        import traceback
        traceback.print_exc()

def test_api_endpoints():
    """测试API端点"""
    import requests
    import json
    
    print("\n🧪 等待服务启动...")
    time.sleep(3)
    
    base_url = "http://localhost:5000"
    
    # 测试端点
    endpoints = [
        ("/api/strategies", "策略列表"),
        ("/api/config/unified", "统一配置"),
        ("/api/system/info", "系统信息")
    ]
    
    print("\n📊 测试API端点:")
    for endpoint, name in endpoints:
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and data.get('success'):
                    print(f"  ✅ {name}: 正常")
                else:
                    print(f"  ⚠️  {name}: 响应格式异常")
            else:
                print(f"  ❌ {name}: HTTP {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"  ❌ {name}: 连接失败 - {e}")
        except Exception as e:
            print(f"  ❌ {name}: 异常 - {e}")

def main():
    """主函数"""
    print("=" * 60)
    print("🎯 策略股票列表API服务启动器")
    print(f"⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 检查环境
    print("\n🔍 环境检查:")
    
    # 检查backend目录
    if os.path.exists(backend_path):
        print(f"  ✅ Backend目录: {backend_path}")
    else:
        print(f"  ❌ Backend目录不存在: {backend_path}")
        return
    
    # 检查关键文件
    key_files = [
        'screening_api.py',
        'universal_screener.py', 
        'strategy_manager.py',
        'config_manager.py'
    ]
    
    for file in key_files:
        file_path = os.path.join(backend_path, file)
        if os.path.exists(file_path):
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} 不存在")
    
    # 启动API测试线程
    test_thread = threading.Thread(target=test_api_endpoints, daemon=True)
    test_thread.start()
    
    # 启动API服务
    try:
        start_screening_api()
    except KeyboardInterrupt:
        print("\n\n⚠️  服务被用户中断")
    except Exception as e:
        print(f"\n\n❌ 服务异常: {e}")
    finally:
        print("\n🏁 服务已停止")

if __name__ == "__main__":
    main()