#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试缓存失效机制
验证数据更新后缓存是否能正确失效
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from strategy_screening_cache import strategy_screening_cache
import time

def test_cache_invalidation():
    """测试缓存失效机制"""
    
    print("🧪 开始测试缓存失效机制...")
    
    # 1. 检查当前数据新鲜度
    print("\n1. 检查数据新鲜度:")
    freshness = strategy_screening_cache.check_data_freshness()
    print(f"   需要更新: {freshness['needs_update']}")
    print(f"   原因: {freshness['reason']}")
    print(f"   当前哈希: {freshness['current_hash'][:16]}...")
    print(f"   缓存哈希: {freshness.get('cached_hash', 'None')}")
    
    # 2. 获取缓存统计
    print("\n2. 当前缓存统计:")
    stats = strategy_screening_cache.get_cache_stats()
    print(f"   总记录数: {stats['total_records']}")
    print(f"   今日记录数: {stats['today_records']}")
    print(f"   策略数量: {stats['unique_strategies']}")
    print(f"   今日总股票数: {stats['today_total_stocks']}")
    
    # 3. 模拟保存一些缓存数据
    print("\n3. 模拟保存缓存数据:")
    test_results = [
        {
            'stock_code': 'sh600000',
            'stock_name': '浦发银行',
            'date': '2025-01-15',
            'signal_type': '买入信号',
            'price': 10.50,
            'confluence_score': 85,
            'confidence': 0.8,
            'market_phase': 'uptrend'
        },
        {
            'stock_code': 'sz000001',
            'stock_name': '平安银行',
            'date': '2025-01-15',
            'signal_type': '买入信号',
            'price': 15.20,
            'confluence_score': 78,
            'confidence': 0.7,
            'market_phase': 'consolidation'
        }
    ]
    
    test_strategy = 'test_strategy_cache'
    success = strategy_screening_cache.save_screening_results(test_strategy, test_results)
    print(f"   保存结果: {'成功' if success else '失败'}")
    
    # 4. 尝试获取缓存
    print("\n4. 尝试获取缓存:")
    cached_results = strategy_screening_cache.get_cached_screening_results(test_strategy)
    if cached_results:
        print(f"   缓存命中: 获取到 {len(cached_results)} 条记录")
        for result in cached_results[:2]:  # 只显示前2条
            print(f"   - {result['stock_code']} ({result['stock_name']}): {result['signal_type']}")
    else:
        print("   缓存未命中")
    
    # 5. 更新数据跟踪
    print("\n5. 更新数据跟踪:")
    strategy_screening_cache.update_data_tracking('stock_data')
    
    # 6. 再次检查数据新鲜度
    print("\n6. 更新后的数据新鲜度:")
    freshness_after = strategy_screening_cache.check_data_freshness()
    print(f"   需要更新: {freshness_after['needs_update']}")
    print(f"   原因: {freshness_after['reason']}")
    
    # 7. 测试强制失效
    print("\n7. 测试强制失效所有缓存:")
    deleted_count = strategy_screening_cache.force_invalidate_all_cache()
    print(f"   删除记录数: {deleted_count}")
    
    # 8. 验证缓存已清空
    print("\n8. 验证缓存已清空:")
    cached_results_after = strategy_screening_cache.get_cached_screening_results(test_strategy)
    print(f"   缓存状态: {'已清空' if not cached_results_after else '仍有数据'}")
    
    # 9. 最终统计
    print("\n9. 最终缓存统计:")
    final_stats = strategy_screening_cache.get_cache_stats()
    print(f"   总记录数: {final_stats['total_records']}")
    print(f"   今日记录数: {final_stats['today_records']}")
    
    print("\n✅ 缓存失效机制测试完成!")

if __name__ == "__main__":
    test_cache_invalidation()