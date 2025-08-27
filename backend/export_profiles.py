#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【独立脚本】个股画像数据导出工具

从数据库中查询所有已生成的个股画像，并将其导出为JSON文件。
"""

import argparse
import json
import os
import sys
from datetime import datetime

# 确保 backend 目录在 Python 路径中
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_pool_manager import StockPoolManager

def export_profiles(output_path: str, pretty_print: bool = True):
    """
    执行画像导出任务。
    
    Args:
        output_path (str): JSON文件的输出路径。
        pretty_print (bool): 是否格式化JSON（美化输出）。
    """
    print("初始化数据库管理器...")
    pool_manager = StockPoolManager()

    print("正在从数据库中获取所有已生成的画像...")
    profiles = pool_manager.get_all_profiles()

    if not profiles:
        print("数据库中未找到已生成的画像数据。")
        return

    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    print(f"共找到 {len(profiles)} 条画像数据，正在导出到: {output_path}")

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            indent = 4 if pretty_print else None
            json.dump(profiles, f, ensure_ascii=False, indent=indent)
        
        print(f"✅ 导出成功！")
    except Exception as e:
        print(f"❌ 导出失败: {e}")

def main():
    """主执行函数"""
    parser = argparse.ArgumentParser(
        description="从数据库导出个股画像数据到JSON文件。"
    )
    parser.add_argument(
        '-o', '--output',
        default=f"profiles_export_{datetime.now().strftime('%Y%m%d')}.json",
        help="指定输出的JSON文件名。 (默认: profiles_export_YYYYMMDD.json)"
    )
    parser.add_argument(
        '--raw',
        action='store_true',
        help="导出为紧凑的、未格式化的JSON。"
    )
    args = parser.parse_args()

    export_profiles(output_path=args.output, pretty_print=not args.raw)

if __name__ == "__main__":
    main()