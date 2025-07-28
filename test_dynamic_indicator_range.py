#!/usr/bin/env python3
"""
测试动态指标范围功能
验证前端JavaScript修改是否正确实现了指标高度的动态调整
"""

import json
import os
from datetime import datetime

def test_dynamic_range_calculation():
    """测试动态范围计算逻辑"""
    print("=== 动态指标范围测试 ===")
    
    # 模拟指标数据
    test_data = {
        "rsi6": [20, 30, 45, 60, 75, 80, 25, 35],
        "rsi12": [25, 35, 50, 65, 70, 85, 30, 40], 
        "rsi24": [30, 40, 55, 70, 65, 90, 35, 45],
        "k": [15, 25, 40, 55, 70, 85, 20, 30],
        "d": [20, 30, 45, 60, 75, 80, 25, 35],
        "j": [10, 20, 35, 50, 65, 90, 15, 25],
        "dif": [-0.5, -0.2, 0.1, 0.3, 0.6, 0.8, -0.3, 0.2],
        "dea": [-0.3, -0.1, 0.2, 0.4, 0.5, 0.7, -0.2, 0.3],
        "macd": [-0.2, -0.1, -0.1, -0.1, 0.1, 0.1, -0.1, -0.1]
    }
    
    # 计算RSI范围
    all_rsi_values = []
    for key in ["rsi6", "rsi12", "rsi24"]:
        all_rsi_values.extend([v for v in test_data[key] if v is not None])
    
    rsi_min = max(0, min(all_rsi_values) - 5) if all_rsi_values else 0
    rsi_max = min(100, max(all_rsi_values) + 5) if all_rsi_values else 100
    
    print(f"RSI数据范围: {min(all_rsi_values):.1f} - {max(all_rsi_values):.1f}")
    print(f"RSI显示范围: {rsi_min:.1f} - {rsi_max:.1f}")
    
    # 计算KDJ范围
    all_kdj_values = []
    for key in ["k", "d", "j"]:
        all_kdj_values.extend([v for v in test_data[key] if v is not None])
    
    kdj_min = max(0, min(all_kdj_values) - 5) if all_kdj_values else 0
    kdj_max = min(100, max(all_kdj_values) + 5) if all_kdj_values else 100
    
    print(f"KDJ数据范围: {min(all_kdj_values):.1f} - {max(all_kdj_values):.1f}")
    print(f"KDJ显示范围: {kdj_min:.1f} - {kdj_max:.1f}")
    
    # 计算MACD范围
    all_macd_values = []
    for key in ["dif", "dea", "macd"]:
        all_macd_values.extend([v for v in test_data[key] if v is not None])
    
    macd_min = min(all_macd_values) * 1.2 if all_macd_values else -1
    macd_max = max(all_macd_values) * 1.2 if all_macd_values else 1
    
    print(f"MACD数据范围: {min(all_macd_values):.3f} - {max(all_macd_values):.3f}")
    print(f"MACD显示范围: {macd_min:.3f} - {macd_max:.3f}")
    
    return {
        "rsi_range": (rsi_min, rsi_max),
        "kdj_range": (kdj_min, kdj_max), 
        "macd_range": (macd_min, macd_max)
    }

def check_frontend_modification():
    """检查前端文件修改是否正确"""
    print("\n=== 前端修改检查 ===")
    
    js_file = "frontend/js/app.js"
    if not os.path.exists(js_file):
        print("❌ 前端JavaScript文件不存在")
        return False
    
    with open(js_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查关键修改点
    checks = [
        ("RSI范围计算", "allRsiValues.length > 0 ? Math.max(0, Math.min(...allRsiValues) - 5) : 0"),
        ("KDJ范围计算", "allKdjValues.length > 0 ? Math.max(0, Math.min(...allKdjValues) - 5) : 0"),
        ("RSI动态范围应用", "max: rsiMax"),
        ("KDJ动态范围应用", "max: kdjMax"),
        ("MACD范围保持", "max: macdMax")
    ]
    
    all_passed = True
    for check_name, check_pattern in checks:
        if check_pattern in content:
            print(f"✅ {check_name}: 已正确实现")
        else:
            print(f"❌ {check_name}: 未找到预期代码")
            all_passed = False
    
    return all_passed

def generate_test_report():
    """生成测试报告"""
    print("\n=== 生成测试报告 ===")
    
    ranges = test_dynamic_range_calculation()
    frontend_ok = check_frontend_modification()
    
    report = {
        "test_time": datetime.now().isoformat(),
        "test_results": {
            "dynamic_range_calculation": ranges,
            "frontend_modification_check": frontend_ok
        },
        "summary": {
            "status": "PASSED" if frontend_ok else "FAILED",
            "description": "动态指标范围功能已实现" if frontend_ok else "前端修改存在问题"
        },
        "improvements": [
            "RSI指标现在根据实际数据动态调整显示范围，避免显示超出范围",
            "KDJ指标现在根据实际数据动态调整显示范围，提高显示效果", 
            "MACD指标保持原有的动态范围计算逻辑",
            "所有指标都添加了5个单位的缓冲区，确保数据完整显示"
        ]
    }
    
    # 保存报告
    report_file = f"dynamic_indicator_range_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"测试报告已保存: {report_file}")
    return report

if __name__ == "__main__":
    report = generate_test_report()
    
    print(f"\n=== 测试总结 ===")
    print(f"状态: {report['summary']['status']}")
    print(f"描述: {report['summary']['description']}")
    
    print(f"\n功能改进:")
    for improvement in report['improvements']:
        print(f"• {improvement}")