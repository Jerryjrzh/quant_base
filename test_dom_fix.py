#!/usr/bin/env python3
"""
测试DOM元素修复效果的脚本
"""
import os
import webbrowser
import time

def test_dom_fix():
    """测试DOM元素修复效果"""
    print("=== DOM元素修复测试 ===\n")
    
    print("🔧 修复内容:")
    print("  ✅ 添加了缺失的 avg-days-to-peak 元素")
    print("  ✅ 在 renderBacktestResults 函数中添加了安全检查")
    print("  ✅ 在 updateAdvicePanel 函数中添加了安全检查")
    print("  ✅ 添加了元素不存在时的警告日志")
    print()
    
    # 检查修复的文件
    files_to_check = [
        'frontend/index.html',
        'frontend/js/app.js',
        'debug_dom_elements.html'
    ]
    
    missing_files = []
    for file_path in files_to_check:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ 缺少必要文件:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        return
    
    print("✅ 所有文件检查通过")
    print()
    
    # 打开调试页面
    debug_page = os.path.abspath('debug_dom_elements.html')
    
    print("🌐 打开DOM元素调试页面...")
    print(f"📁 文件路径: {debug_page}")
    print()
    
    try:
        webbrowser.open(f'file://{debug_page}')
        print("✅ 调试页面已在浏览器中打开")
        print()
        
        print("🔍 请在浏览器中检查以下内容:")
        print("  1. 所有必需的DOM元素是否都存在")
        print("  2. 模拟app.js错误是否正常工作")
        print("  3. 控制台是否有错误信息")
        print()
        
        print("📋 修复前后对比:")
        print("  修复前: TypeError: can't access property 'textContent', document.getElementById(...) is null")
        print("  修复后: 添加了安全检查，避免访问null元素")
        print()
        
        print("💡 如果调试页面显示所有元素都找到，说明修复成功")
        
    except Exception as e:
        print(f"❌ 无法打开调试页面: {e}")
        print(f"请手动打开: {debug_page}")

def check_html_elements():
    """检查HTML文件中的元素"""
    print("\n=== HTML元素检查 ===\n")
    
    html_file = 'frontend/index.html'
    if not os.path.exists(html_file):
        print("❌ HTML文件不存在")
        return
    
    with open(html_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查关键元素
    key_elements = [
        'total-signals',
        'win-rate', 
        'avg-max-profit',
        'avg-max-drawdown',
        'avg-days-to-peak',
        'state-stats-content',
        'action-recommendation',
        'analysis-logic'
    ]
    
    print("关键元素检查结果:")
    for element_id in key_elements:
        if f'id="{element_id}"' in content:
            print(f"  ✅ {element_id} - 存在")
        else:
            print(f"  ❌ {element_id} - 缺失")
    
    print()

def check_js_safety():
    """检查JavaScript安全性"""
    print("=== JavaScript安全性检查 ===\n")
    
    js_file = 'frontend/js/app.js'
    if not os.path.exists(js_file):
        print("❌ JavaScript文件不存在")
        return
    
    with open(js_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查安全性改进
    safety_checks = [
        ('getElementById安全检查', 'if (totalSignalsEl)'),
        ('价格元素安全检查', 'if (el) {'),
        ('警告日志', 'console.warn'),
        ('元素存在性检查', 'Element with id')
    ]
    
    print("安全性改进检查结果:")
    for check_name, pattern in safety_checks:
        if pattern in content:
            print(f"  ✅ {check_name} - 已添加")
        else:
            print(f"  ❌ {check_name} - 未找到")
    
    print()

if __name__ == "__main__":
    test_dom_fix()
    check_html_elements()
    check_js_safety()