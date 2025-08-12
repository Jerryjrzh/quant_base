#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持仓管理功能简化测试
验证核心功能是否正常工作
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://127.0.0.1:5000"

def test_basic_functions():
    """测试基本功能"""
    print("🧪 持仓管理功能测试")
    print("=" * 50)
    
    # 1. 测试添加持仓
    print("\n1️⃣ 测试添加持仓")
    test_positions = [
        {
            'stock_code': 'TEST001',
            'purchase_price': 10.00,
            'quantity': 1000,
            'purchase_date': '2024-01-01',
            'note': '测试股票1'
        },
        {
            'stock_code': 'TEST002', 
            'purchase_price': 20.00,
            'quantity': 500,
            'purchase_date': '2024-02-01',
            'note': '测试股票2'
        }
    ]
    
    for position in test_positions:
        try:
            response = requests.post(
                f"{BASE_URL}/api/portfolio",
                headers={'Content-Type': 'application/json'},
                data=json.dumps(position)
            )
            data = response.json()
            if response.status_code == 200:
                print(f"✅ {position['stock_code']}: 添加成功")
            else:
                print(f"⚠️  {position['stock_code']}: {data.get('error', '添加失败')}")
        except Exception as e:
            print(f"❌ {position['stock_code']}: 请求异常 - {e}")
    
    # 2. 测试获取持仓列表
    print("\n2️⃣ 测试获取持仓列表")
    try:
        response = requests.get(f"{BASE_URL}/api/portfolio")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 获取成功: 共 {data['count']} 个持仓")
            
            print("\n📋 持仓列表:")
            print(f"{'代码':<10} {'价格':<8} {'数量':<6} {'日期':<12} {'备注':<15}")
            print("-" * 55)
            
            for position in data['portfolio']:
                print(f"{position['stock_code']:<10} "
                      f"¥{position['purchase_price']:<7.2f} "
                      f"{position['quantity']:<6} "
                      f"{position['purchase_date']:<12} "
                      f"{position['note'][:12]:<15}")
        else:
            print(f"❌ 获取失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 请求异常: {e}")
    
    # 3. 测试更新持仓
    print("\n3️⃣ 测试更新持仓")
    try:
        update_data = {
            'stock_code': 'TEST001',
            'note': '测试股票1 - 已更新'
        }
        response = requests.put(
            f"{BASE_URL}/api/portfolio",
            headers={'Content-Type': 'application/json'},
            data=json.dumps(update_data)
        )
        data = response.json()
        if response.status_code == 200:
            print(f"✅ 更新成功: {data['message']}")
        else:
            print(f"❌ 更新失败: {data.get('error', '未知错误')}")
    except Exception as e:
        print(f"❌ 请求异常: {e}")
    
    # 4. 测试持仓扫描（简化版）
    print("\n4️⃣ 测试持仓扫描")
    try:
        response = requests.post(f"{BASE_URL}/api/portfolio/scan")
        if response.status_code == 200:
            data = response.json()
            if data['success']:
                results = data['results']
                print(f"✅ 扫描完成:")
                print(f"   📊 总持仓: {results['total_positions']}")
                print(f"   📈 盈利: {results['summary']['profitable_count']}")
                print(f"   📉 亏损: {results['summary']['loss_count']}")
                print(f"   ⚠️  高风险: {results['summary']['high_risk_count']}")
                print(f"   🎯 需操作: {results['summary']['action_required_count']}")
            else:
                print(f"❌ 扫描失败: {data.get('error', '未知错误')}")
        else:
            print(f"❌ 扫描请求失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 请求异常: {e}")
    
    # 5. 清理测试数据
    print("\n5️⃣ 清理测试数据")
    for stock_code in ['TEST001', 'TEST002']:
        try:
            response = requests.delete(f"{BASE_URL}/api/portfolio?stock_code={stock_code}")
            data = response.json()
            if response.status_code == 200:
                print(f"✅ {stock_code}: 删除成功")
            else:
                print(f"⚠️  {stock_code}: {data.get('error', '删除失败')}")
        except Exception as e:
            print(f"❌ {stock_code}: 请求异常 - {e}")

def test_frontend_integration():
    """测试前端集成"""
    print("\n🌐 前端集成测试")
    print("=" * 50)
    
    try:
        # 测试主页面
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            content = response.text
            if '持仓管理' in content:
                print("✅ 前端页面包含持仓管理按钮")
            else:
                print("⚠️  前端页面未找到持仓管理按钮")
            
            if 'portfolio-btn' in content:
                print("✅ 持仓管理按钮ID正确")
            else:
                print("⚠️  持仓管理按钮ID未找到")
                
            print(f"📄 页面大小: {len(content)} 字符")
        else:
            print(f"❌ 前端页面访问失败: {response.status_code}")
    except Exception as e:
        print(f"❌ 前端访问异常: {e}")

def main():
    """主测试函数"""
    print("🚀 开始持仓管理功能验证")
    print(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔗 服务地址: {BASE_URL}")
    
    # 测试服务连接
    try:
        response = requests.get(f"{BASE_URL}/api/portfolio", timeout=5)
        print("✅ 后端服务连接正常")
    except Exception as e:
        print(f"❌ 后端服务连接失败: {e}")
        print("请确保后端服务正在运行: python backend/app.py")
        return
    
    # 执行测试
    test_basic_functions()
    test_frontend_integration()
    
    print("\n" + "=" * 50)
    print("🎉 验证完成!")
    print("\n📖 使用指南:")
    print("1. 后端服务: python backend/app.py")
    print("2. 浏览器访问: http://127.0.0.1:5000")
    print("3. 点击 '💼 持仓管理' 开始使用")
    print("\n✨ 主要功能:")
    print("• 添加/删除/编辑持仓")
    print("• 深度扫描分析")
    print("• 操作建议生成")
    print("• 风险评估")
    print("• 价格目标计算")
    print("• 时间周期分析")

if __name__ == "__main__":
    main()