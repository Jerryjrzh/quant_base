#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据目录管理工具
用于管理和维护data目录下的各种数据文件
"""

import os
import json
import shutil
import glob
from datetime import datetime, timedelta
import argparse

class DataManager:
    """数据目录管理器"""
    
    def __init__(self):
        self.data_root = "data"
        self.backtest_dir = os.path.join(self.data_root, "backtest")
        self.portfolio_dir = os.path.join(self.data_root, "portfolio")
        self.result_dir = os.path.join(self.data_root, "result")
        self.cache_dir = os.path.join(self.data_root, "cache")
        
    def ensure_directories(self):
        """确保所有必要的目录存在"""
        directories = [
            os.path.join(self.backtest_dir, "cache"),
            os.path.join(self.backtest_dir, "reports"),
            self.portfolio_dir,
            self.cache_dir,
            os.path.join(self.data_root, "smart_cache")
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            print(f"✅ 确保目录存在: {directory}")
    
    def clean_old_cache(self, days=30):
        """清理过期的缓存文件"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_count = 0
        
        # 清理回测缓存
        cache_pattern = os.path.join(self.backtest_dir, "cache", "*.json")
        for cache_file in glob.glob(cache_pattern):
            if os.path.getmtime(cache_file) < cutoff_date.timestamp():
                os.remove(cache_file)
                cleaned_count += 1
                print(f"🗑️  删除过期缓存: {os.path.basename(cache_file)}")
        
        # 清理通用缓存
        cache_pattern = os.path.join(self.cache_dir, "*.json")
        for cache_file in glob.glob(cache_pattern):
            if os.path.getmtime(cache_file) < cutoff_date.timestamp():
                os.remove(cache_file)
                cleaned_count += 1
                print(f"🗑️  删除过期缓存: {os.path.basename(cache_file)}")
        
        print(f"✅ 清理完成，共删除 {cleaned_count} 个过期缓存文件")
    
    def clean_old_logs(self, days=7):
        """清理过期的日志文件"""
        cutoff_date = datetime.now() - timedelta(days=days)
        cleaned_count = 0
        
        # 清理筛选日志
        log_pattern = os.path.join(self.result_dir, "*.log")
        for log_file in glob.glob(log_pattern):
            if os.path.getmtime(log_file) < cutoff_date.timestamp():
                os.remove(log_file)
                cleaned_count += 1
                print(f"🗑️  删除过期日志: {os.path.basename(log_file)}")
        
        # 清理子目录中的日志
        for root, dirs, files in os.walk(self.result_dir):
            for file in files:
                if file.endswith('.log'):
                    file_path = os.path.join(root, file)
                    if os.path.getmtime(file_path) < cutoff_date.timestamp():
                        os.remove(file_path)
                        cleaned_count += 1
                        print(f"🗑️  删除过期日志: {file}")
        
        print(f"✅ 清理完成，共删除 {cleaned_count} 个过期日志文件")
    
    def backup_portfolio(self):
        """备份持仓数据"""
        portfolio_file = os.path.join(self.portfolio_dir, "portfolio.json")
        if not os.path.exists(portfolio_file):
            print("⚠️  持仓文件不存在，跳过备份")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = os.path.join(self.portfolio_dir, f"portfolio.json.backup_{timestamp}")
        
        shutil.copy2(portfolio_file, backup_file)
        print(f"✅ 持仓数据已备份: {os.path.basename(backup_file)}")
    
    def get_directory_stats(self):
        """获取目录统计信息"""
        stats = {}
        
        # 回测缓存统计
        cache_files = glob.glob(os.path.join(self.backtest_dir, "cache", "*.json"))
        cache_size = sum(os.path.getsize(f) for f in cache_files)
        stats['backtest_cache'] = {
            'count': len(cache_files),
            'size_mb': round(cache_size / 1024 / 1024, 2)
        }
        
        # 持仓数据统计
        portfolio_files = glob.glob(os.path.join(self.portfolio_dir, "*.json"))
        portfolio_size = sum(os.path.getsize(f) for f in portfolio_files)
        stats['portfolio'] = {
            'count': len(portfolio_files),
            'size_mb': round(portfolio_size / 1024 / 1024, 2)
        }
        
        # 筛选结果统计
        result_dirs = [d for d in os.listdir(self.result_dir) 
                      if os.path.isdir(os.path.join(self.result_dir, d))]
        stats['result_strategies'] = len(result_dirs)
        
        return stats
    
    def print_stats(self):
        """打印目录统计信息"""
        stats = self.get_directory_stats()
        
        print("\n📊 数据目录统计信息")
        print("=" * 50)
        print(f"回测缓存文件: {stats['backtest_cache']['count']} 个")
        print(f"回测缓存大小: {stats['backtest_cache']['size_mb']} MB")
        print(f"持仓相关文件: {stats['portfolio']['count']} 个")
        print(f"持仓数据大小: {stats['portfolio']['size_mb']} MB")
        print(f"策略结果目录: {stats['result_strategies']} 个")
        print("=" * 50)
    
    def migrate_old_files(self):
        """迁移旧的文件到新的目录结构"""
        print("🔄 开始迁移旧文件...")
        
        # 迁移根目录下的回测缓存文件
        old_cache_pattern = os.path.join(self.data_root, "backtest_cache_*.json")
        migrated_count = 0
        
        for old_file in glob.glob(old_cache_pattern):
            new_file = os.path.join(self.backtest_dir, "cache", os.path.basename(old_file))
            if not os.path.exists(new_file):
                shutil.move(old_file, new_file)
                migrated_count += 1
                print(f"📦 迁移缓存文件: {os.path.basename(old_file)}")
        
        # 迁移根目录下的持仓文件
        old_portfolio_files = [
            os.path.join(self.data_root, "portfolio.json"),
            os.path.join(self.data_root, "portfolio_scan_cache.json")
        ]
        
        for old_file in old_portfolio_files:
            if os.path.exists(old_file):
                new_file = os.path.join(self.portfolio_dir, os.path.basename(old_file))
                if not os.path.exists(new_file):
                    shutil.move(old_file, new_file)
                    migrated_count += 1
                    print(f"📦 迁移持仓文件: {os.path.basename(old_file)}")
        
        print(f"✅ 迁移完成，共迁移 {migrated_count} 个文件")

def main():
    parser = argparse.ArgumentParser(description="数据目录管理工具")
    parser.add_argument("--init", action="store_true", help="初始化目录结构")
    parser.add_argument("--clean-cache", type=int, default=30, help="清理N天前的缓存文件")
    parser.add_argument("--clean-logs", type=int, default=7, help="清理N天前的日志文件")
    parser.add_argument("--backup", action="store_true", help="备份持仓数据")
    parser.add_argument("--stats", action="store_true", help="显示目录统计信息")
    parser.add_argument("--migrate", action="store_true", help="迁移旧文件到新目录结构")
    
    args = parser.parse_args()
    
    manager = DataManager()
    
    if args.init:
        manager.ensure_directories()
    
    if args.migrate:
        manager.migrate_old_files()
    
    if args.backup:
        manager.backup_portfolio()
    
    if args.clean_cache:
        manager.clean_old_cache(args.clean_cache)
    
    if args.clean_logs:
        manager.clean_old_logs(args.clean_logs)
    
    if args.stats:
        manager.print_stats()
    
    # 如果没有指定任何参数，显示帮助信息
    if not any(vars(args).values()):
        parser.print_help()
        print("\n📋 常用命令示例:")
        print("python data_manager.py --init                    # 初始化目录结构")
        print("python data_manager.py --migrate                 # 迁移旧文件")
        print("python data_manager.py --stats                   # 查看统计信息")
        print("python data_manager.py --backup                  # 备份持仓数据")
        print("python data_manager.py --clean-cache 30          # 清理30天前的缓存")
        print("python data_manager.py --clean-logs 7            # 清理7天前的日志")

if __name__ == "__main__":
    main()