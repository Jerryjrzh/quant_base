#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单测试通用筛选器运行
"""

import sys
import os

# 添加backend目录到路径
sys.path.append('backend')

def main():
    """主函数"""
    print("🚀 通用筛选器简单运行测试")
    print("=" * 50)
    
    try:
        import universal_screener
        
        # 创建筛选器实例
        screener = universal_screener.UniversalScreener()
        
        # 显示可用策略
        available_strategies = screener.get_available_strategies()
        print(f"📋 可用策略 ({len(available_strategies)} 个):")
        for strategy in available_strategies:
            status = "✅ 启用" if strategy['enabled'] else "❌ 禁用"
            print(f"  - {strategy['name']} v{strategy['version']} {status}")
        
        print("\n✅ 筛选器初始化和配置测试成功！")
        print("📝 注意：由于没有股票数据文件，跳过实际筛选测试")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = main()
    if success:
        print("\n🎉 测试通过！")
    else:
        print("\n❌ 测试失败！")