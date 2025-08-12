#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
修复持仓数据中的股票代码大小写不一致问题
将所有股票代码统一转换为小写格式
"""

import json
import os
from datetime import datetime

def fix_portfolio_case():
    """修复持仓数据中的股票代码大小写"""
    portfolio_file = os.path.join('data', 'portfolio.json')
    
    if not os.path.exists(portfolio_file):
        print("持仓文件不存在")
        return
    
    # 备份原文件
    backup_file = f"{portfolio_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    try:
        # 读取原数据
        with open(portfolio_file, 'r', encoding='utf-8') as f:
            portfolio = json.load(f)
        
        # 备份原文件
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(portfolio, f, ensure_ascii=False, indent=2)
        print(f"原文件已备份到: {backup_file}")
        
        # 修复大小写
        fixed_count = 0
        for position in portfolio:
            original_code = position['stock_code']
            fixed_code = original_code.lower()
            
            if original_code != fixed_code:
                position['stock_code'] = fixed_code
                position['updated_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                fixed_count += 1
                print(f"修复: {original_code} -> {fixed_code}")
        
        # 保存修复后的数据
        with open(portfolio_file, 'w', encoding='utf-8') as f:
            json.dump(portfolio, f, ensure_ascii=False, indent=2)
        
        print(f"\n修复完成！")
        print(f"总持仓数: {len(portfolio)}")
        print(f"修复数量: {fixed_count}")
        print(f"未修复数量: {len(portfolio) - fixed_count}")
        
    except Exception as e:
        print(f"修复失败: {e}")
        if os.path.exists(backup_file):
            print(f"可以从备份文件恢复: {backup_file}")

if __name__ == '__main__':
    fix_portfolio_case()