#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试策略筛选缓存系统
"""

import sys
import os
sys.path.append('backend')

from strategy_screening_cache import strategy_screening_cache
import json

def test_cache_system():
    """测试缓存系统功能"""
    print("=" * 60)
    print("测试策略筛选缓存系统")
    print("=" * 60)
    
    # 测试数据
    test_strategy = "RSI_BOTTOM"
    test_results = [
        {
            'stock_code': 'sz000001',
            'stock_name': '平安银行',
            'date': '2025-08-27',
            'signal_type': 'BUY',
            'price': 12.50
        },
        {
            'stock_code': 'sh600036',
            'stock_name': '招商银行',
            'date': '2025-08-27',
            'signal_type': 'BUY',
            'price': 35.20
        }
    ]
    
    print("1. 测试缓存保存...")
    success = strategy_screening_cache.save_screening_results(test_strategy, test_results)
    print(f"   保存结果: {'✅ 成功' if success else '❌ 失败'}")
    
    print("2. 测试缓存读取...")
    cached_results = strategy_screening_cache.get_cached_screening_results(test_strategy)
    if cached_results:
        print(f"   ✅ 缓存命中，获取到 {len(cached_results)} 条记录")
        print(f"   样本数据: {cached_results[0]}")
    else:
        print("   ❌ 缓存未命中")
    
    print("3. 测试缓存统计...")
    stats = strategy_screening_cache.get_cache_stats()
    print(f"   总记录数: {stats['total_records']}")
    print(f"   今日记录数: {stats['today_records']}")
    print(f"   策略数量: {stats['unique_strategies']}")
    print(f"   今日股票总数: {stats['today_total_stocks']}")
    
    if stats['recent_records']:
        print("   最近记录:")
        for record in stats['recent_records'][:3]:
            print(f"     - {record['strategy_id']}: {record['stock_count']}只股票")
    
    print("4. 测试缓存清理...")
    deleted_count = strategy_screening_cache.invalidate_cache(test_strategy)
    print(f"   清理结果: 删除了 {deleted_count} 条记录")
    
    print("5. 验证清理效果...")
    cached_results_after_clear = strategy_screening_cache.get_cached_screening_results(test_strategy)
    if cached_results_after_clear:
        print("   ❌ 清理失败，仍有缓存数据")
    else:
        print("   ✅ 清理成功，缓存已清空")
    
    print()
    print("=" * 60)
    print("缓存系统测试完成")
    print("=" * 60)
    print()
    print("缓存系统功能:")
    print("✅ 策略筛选结果缓存")
    print("✅ 数据更新检测")
    print("✅ 缓存统计信息")
    print("✅ 缓存清理功能")
    print("✅ 前端缓存管理界面")
    print()
    print("使用方法:")
    print("1. 启动后端服务: python backend/app.py")
    print("2. 打开前端页面: frontend/index.html")
    print("3. 选择策略时会自动使用缓存（如果可用）")
    print("4. 点击'强制刷新'按钮可以强制更新缓存")
    print("5. 点击'缓存管理'按钮可以查看和管理缓存")
    print()
    print("缓存优势:")
    print("- 大幅提升前端响应速度")
    print("- 减少重复计算，节省系统资源")
    print("- 支持数据更新检测，确保数据新鲜度")
    print("- 提供完整的缓存管理功能")

if __name__ == "__main__":
    test_cache_system()