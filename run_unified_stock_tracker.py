#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一股票跟踪器运行脚本
使用配置化的分级标准运行股票跟踪分析
"""

import sys
import os
import argparse
from datetime import datetime

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from unified_stock_tracker import UnifiedStockTracker
from config_loader import ConfigLoader

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='统一股票跟踪器')
    parser.add_argument('--grade', '-g', type=str, default='A', 
                       help='股票等级 (默认: A)')
    parser.add_argument('--config', '-c', type=str, 
                       help='配置文件路径 (默认: config/stock_grading_criteria.yaml)')
    parser.add_argument('--list-grades', '-l', action='store_true',
                       help='列出所有可用的等级')
    parser.add_argument('--validate-config', '-v', action='store_true',
                       help='验证配置文件')
    parser.add_argument('--all-grades', '-a', action='store_true',
                       help='运行所有等级的分析')
    
    args = parser.parse_args()
    
    # 初始化配置加载器
    config_loader = ConfigLoader(args.config)
    
    # 验证配置文件
    if args.validate_config:
        if config_loader.validate_config():
            print("✅ 配置文件验证通过")
            return 0
        else:
            print("❌ 配置文件验证失败")
            return 1
    
    # 列出可用等级
    if args.list_grades:
        try:
            grades = config_loader.list_available_grades()
            print("📋 可用的股票等级:")
            for grade in grades:
                criteria = config_loader.get_grade_criteria(grade)
                print(f"  {grade}: {criteria.get('name', f'{grade}级股票')}")
            return 0
        except Exception as e:
            print(f"❌ 获取等级列表失败: {e}")
            return 1
    
    # 运行分析
    try:
        if args.all_grades:
            # 运行所有等级的分析
            grades = config_loader.list_available_grades()
            results = {}
            
            print(f"🚀 开始运行所有等级的股票跟踪分析...")
            print(f"📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            
            for grade in grades:
                print(f"\n🔍 正在分析{grade}级股票...")
                try:
                    criteria = config_loader.get_grade_criteria(grade)
                    tracker = UnifiedStockTracker(grade, criteria)
                    result = tracker.run_full_analysis()
                    results[grade] = result
                    print(f"✅ {grade}级分析完成: 发现{result['total_stocks']}只股票")
                except Exception as e:
                    print(f"❌ {grade}级分析失败: {e}")
                    results[grade] = {'error': str(e)}
            
            # 汇总结果
            print("\n" + "=" * 80)
            print("📊 分析结果汇总:")
            total_stocks = 0
            for grade, result in results.items():
                if 'error' in result:
                    print(f"  {grade}级: 分析失败 - {result['error']}")
                else:
                    stock_count = result['total_stocks']
                    total_stocks += stock_count
                    print(f"  {grade}级: {stock_count}只股票")
                    if result.get('report_path'):
                        print(f"    📄 报告: {result['report_path']}")
                    if result.get('excel_path'):
                        print(f"    📊 Excel: {result['excel_path']}")
            
            print(f"\n🎯 总计发现: {total_stocks}只分级股票")
            
        else:
            # 运行单个等级的分析
            grade = args.grade.upper()
            
            print(f"🚀 开始{grade}级股票跟踪分析...")
            print(f"📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)
            
            # 获取分级标准
            criteria = config_loader.get_grade_criteria(grade)
            print(f"📋 使用{grade}级标准: {criteria.get('name', f'{grade}级股票')}")
            
            # 创建跟踪器并运行分析
            tracker = UnifiedStockTracker(grade, criteria)
            result = tracker.run_full_analysis()
            
            print("\n" + "=" * 80)
            print("📊 分析完成!")
            print(f"🎯 发现{grade}级股票: {result['total_stocks']}只")
            if result.get('report_path'):
                print(f"📄 报告文件: {result['report_path']}")
            if result.get('excel_path'):
                print(f"📊 Excel文件: {result['excel_path']}")
        
        return 0
        
    except KeyError as e:
        print(f"❌ 未找到等级 '{args.grade}' 的配置")
        print("💡 使用 --list-grades 查看可用等级")
        return 1
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)