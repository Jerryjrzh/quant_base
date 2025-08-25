#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试股票信息修复
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from stock_info_crawler import get_multiple_stock_info

def test_stock_info_fix():
    """测试股票信息获取和处理"""
    print("测试股票信息获取修复...")
    
    # 测试股票代码
    test_codes = ["000001", "600000", "300001"]
    
    try:
        # 获取股票信息
        stock_info_map = get_multiple_stock_info(test_codes, use_cache=True)
        print(f"成功获取 {len(stock_info_map)} 个股票信息")
        
        # 模拟原来的错误用法和修复后的正确用法
        for code, stock_info in stock_info_map.items():
            print(f"\n股票代码: {code}")
            print(f"股票信息类型: {type(stock_info)}")
            print(f"股票名称: {stock_info.name}")
            
            # 测试正确的用法
            stock_data = {'stock_code': code}
            
            # 正确的方式：使用属性构建字典
            stock_data.update({
                'name': stock_info.name,
                'sector': stock_info.sector,
                'industry': stock_info.industry,
                'market': stock_info.market
            })
            
            print(f"更新后的股票数据: {stock_data}")
            
            # 测试 to_dict 方法
            stock_dict = stock_info.to_dict()
            print(f"to_dict() 结果: {stock_dict}")
            
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_stock_info_fix()