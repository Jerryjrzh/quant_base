#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速生成股票画像脚本

这个脚本提供最简单的方式来生成股票画像：
- 自动为核心观察池生成画像
- 使用多进程加速
- 提供简洁的进度显示
"""

import os
import sys
import time
from datetime import datetime

# 添加backend目录到路径
sys.path.append('backend')

try:
    from stock_profiler import StockProfiler
    from stock_pool_manager import StockPoolManager
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)


def main():
    """主函数"""
    print("🚀 快速生成股票画像")
    print("=" * 50)
    
    try:
        # 创建画像生成器
        profiler = StockProfiler()
        pool_manager = StockPoolManager()
        
        # 获取当前状态
        core_pool = pool_manager.get_core_pool()
        print(f"📊 核心观察池股票数量: {len(core_pool)}")
        
        # 检查已有画像
        existing_profiles = 0
        for stock in core_pool:
            if stock.get('optimized_params'):
                existing_profiles += 1
        
        print(f"📈 已有画像股票: {existing_profiles}")
        print(f"🎯 待生成画像股票: {len(core_pool) - existing_profiles}")
        
        if existing_profiles == len(core_pool):
            print("✅ 所有核心池股票都已有画像！")
            
            # 显示画像摘要
            summary = profiler.get_profiling_summary()
            if summary.get('avg_validation_score'):
                print(f"📊 平均验证分数: {summary['avg_validation_score']:.3f}")
            
            return
        
        print("\n🔄 开始生成画像...")
        print("💡 使用多进程模式以提高速度")
        
        # 记录开始时间
        start_time = time.time()
        
        # 生成画像
        results = profiler.run_profiling_for_pool(use_multiprocessing=True)
        
        # 记录结束时间
        end_time = time.time()
        duration = end_time - start_time
        
        # 显示结果
        print("\n" + "=" * 50)
        print("✅ 画像生成完成！")
        print(f"⏱️  总耗时: {duration:.2f} 秒")
        print(f"📊 成功: {results['success']} 只")
        print(f"❌ 失败: {results['failed']} 只")
        print(f"📈 成功率: {results['success'] / results['total'] * 100:.1f}%")
        
        # 显示最终摘要
        final_summary = profiler.get_profiling_summary()
        if final_summary.get('avg_validation_score'):
            print(f"🎯 平均验证分数: {final_summary['avg_validation_score']:.3f}")
        
        print("\n🎉 现在可以使用通用筛选器进行更精准的股票筛选了！")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断操作")
    except Exception as e:
        print(f"\n❌ 生成过程中出错: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()