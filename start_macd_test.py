#!/usr/bin/env python3
"""
启动MACD显示测试的脚本
"""
import os
import sys
import subprocess
import webbrowser
import time
from threading import Thread

def start_backend_server():
    """启动后端服务器"""
    print("🚀 启动后端服务器...")
    backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
    
    try:
        # 切换到backend目录并启动Flask应用
        os.chdir(backend_dir)
        subprocess.run([sys.executable, 'app.py'], check=True)
    except KeyboardInterrupt:
        print("\n⏹️ 后端服务器已停止")
    except Exception as e:
        print(f"❌ 后端服务器启动失败: {e}")

def open_test_page():
    """打开测试页面"""
    time.sleep(3)  # 等待服务器启动
    
    test_page = os.path.join(os.path.dirname(__file__), 'test_macd_complete_display.html')
    
    if os.path.exists(test_page):
        print("🌐 打开MACD显示测试页面...")
        webbrowser.open(f'file://{os.path.abspath(test_page)}')
    else:
        print("❌ 测试页面文件不存在")

def main():
    print("=== MACD显示修复测试启动器 ===\n")
    
    print("📋 测试内容:")
    print("  ✅ 完整MACD指标显示（DIF、DEA、MACD柱状图）")
    print("  ✅ 柱状图颜色区分（红色正值，青色负值）")
    print("  ✅ 后端API数据完整性")
    print("  ✅ 前端图表渲染效果")
    print()
    
    # 检查必要文件
    required_files = [
        'backend/app.py',
        'test_macd_complete_display.html',
        'test_complete_macd_api_response.json'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ 缺少必要文件:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        print("\n请确保所有文件都存在后重新运行。")
        return
    
    print("✅ 所有必要文件检查通过")
    print()
    
    # 启动测试
    print("🎯 启动测试...")
    print("  1. 后端服务器将在 http://localhost:5000 启动")
    print("  2. 测试页面将自动在浏览器中打开")
    print("  3. 按 Ctrl+C 停止测试")
    print()
    
    # 在后台线程中打开测试页面
    Thread(target=open_test_page, daemon=True).start()
    
    # 启动后端服务器（阻塞主线程）
    start_backend_server()

if __name__ == "__main__":
    main()