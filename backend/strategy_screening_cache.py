#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略筛选结果缓存系统
实现策略筛选结果的缓存机制，避免重复筛选，提升前端响应速度
"""

import sqlite3
import json
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any
import hashlib

# 数据库路径
DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'strategy_screening_cache.db')

class StrategyScreeningCache:
    """策略筛选结果缓存管理器"""
    
    def __init__(self):
        self.db_path = DATABASE_PATH
        self._ensure_database_exists()
    
    def _ensure_database_exists(self):
        """确保数据库和表结构存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建策略筛选结果缓存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS strategy_screening_results (
                strategy_id TEXT,
                screening_date TEXT,
                data_hash TEXT,
                results_json TEXT,
                stock_count INTEGER,
                created_at TEXT,
                PRIMARY KEY (strategy_id, screening_date)
            )
        ''')
        
        # 创建数据更新跟踪表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS data_update_tracking (
                data_type TEXT PRIMARY KEY,
                last_update_date TEXT,
                update_hash TEXT
            )
        ''')
        
        # 创建索引
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_screening_date 
            ON strategy_screening_results(screening_date)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at 
            ON strategy_screening_results(created_at)
        ''')
        
        conn.commit()
        conn.close()
    
    def _calculate_data_hash(self) -> str:
        """计算当前数据的哈希值，用于检测数据是否更新"""
        try:
            # 这里可以根据实际情况计算数据哈希
            # 例如：检查股票数据文件的最后修改时间
            import data_handler
            
            # 简单的实现：使用当前日期作为哈希
            # 在实际应用中，可以检查数据文件的修改时间或内容哈希
            today = date.today().strftime('%Y-%m-%d')
            return hashlib.md5(today.encode()).hexdigest()
        except Exception:
            return hashlib.md5(str(datetime.now()).encode()).hexdigest()
    
    def get_cached_screening_results(self, strategy_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        获取缓存的策略筛选结果
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            缓存的筛选结果，如果不存在或数据已更新则返回None
        """
        today_str = date.today().strftime('%Y-%m-%d')
        current_hash = self._calculate_data_hash()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT results_json, data_hash, stock_count, created_at
            FROM strategy_screening_results 
            WHERE strategy_id=? AND screening_date=?
        ''', (strategy_id, today_str))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            cached_hash = result[1]
            if cached_hash == current_hash:
                print(f"✅ 策略筛选缓存命中: {strategy_id} (股票数: {result[2]})")
                try:
                    return json.loads(result[0])
                except json.JSONDecodeError:
                    print(f"⚠️ 缓存数据解析失败: {strategy_id}")
                    return None
            else:
                print(f"🔄 数据已更新，缓存失效: {strategy_id}")
                # 删除过期缓存
                self.invalidate_cache(strategy_id)
                return None
        
        print(f"❌ 策略筛选缓存未命中: {strategy_id}")
        return None
    
    def save_screening_results(self, strategy_id: str, results: List[Dict[str, Any]]) -> bool:
        """
        保存策略筛选结果到缓存
        
        Args:
            strategy_id: 策略ID
            results: 筛选结果列表
            
        Returns:
            是否保存成功
        """
        try:
            today_str = date.today().strftime('%Y-%m-%d')
            current_hash = self._calculate_data_hash()
            results_json = json.dumps(results, ensure_ascii=False)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO strategy_screening_results 
                (strategy_id, screening_date, data_hash, results_json, stock_count, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                strategy_id,
                today_str,
                current_hash,
                results_json,
                len(results),
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
            print(f"💾 策略筛选结果已缓存: {strategy_id} (股票数: {len(results)})")
            return True
            
        except Exception as e:
            print(f"❌ 保存策略筛选缓存失败: {strategy_id}, 错误: {e}")
            return False
    
    def invalidate_cache(self, strategy_id: str = None, older_than_days: int = None):
        """
        清理缓存
        
        Args:
            strategy_id: 指定策略ID，为None时清理所有策略
            older_than_days: 清理多少天前的缓存，为None时清理所有
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if strategy_id and older_than_days:
            cutoff_date = (date.today() - timedelta(days=older_than_days)).strftime('%Y-%m-%d')
            cursor.execute('''
                DELETE FROM strategy_screening_results 
                WHERE strategy_id=? AND screening_date<?
            ''', (strategy_id, cutoff_date))
            print(f"🗑️ 已清理策略 {strategy_id} {older_than_days}天前的缓存")
        elif strategy_id:
            cursor.execute('DELETE FROM strategy_screening_results WHERE strategy_id=?', (strategy_id,))
            print(f"🗑️ 已清理策略缓存: {strategy_id}")
        elif older_than_days:
            cutoff_date = (date.today() - timedelta(days=older_than_days)).strftime('%Y-%m-%d')
            cursor.execute('DELETE FROM strategy_screening_results WHERE screening_date<?', (cutoff_date,))
            print(f"🗑️ 已清理 {older_than_days}天前的所有缓存")
        else:
            cursor.execute('DELETE FROM strategy_screening_results')
            print("🗑️ 已清理所有策略筛选缓存")
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总记录数
        cursor.execute('SELECT COUNT(*) FROM strategy_screening_results')
        total_records = cursor.fetchone()[0]
        
        # 今日记录数
        today_str = date.today().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM strategy_screening_results WHERE screening_date=?', (today_str,))
        today_records = cursor.fetchone()[0]
        
        # 策略数量
        cursor.execute('SELECT COUNT(DISTINCT strategy_id) FROM strategy_screening_results')
        unique_strategies = cursor.fetchone()[0]
        
        # 今日总股票数
        cursor.execute('SELECT SUM(stock_count) FROM strategy_screening_results WHERE screening_date=?', (today_str,))
        today_total_stocks = cursor.fetchone()[0] or 0
        
        # 最近的缓存记录
        cursor.execute('''
            SELECT strategy_id, stock_count, created_at 
            FROM strategy_screening_results 
            WHERE screening_date=? 
            ORDER BY created_at DESC 
            LIMIT 5
        ''', (today_str,))
        
        recent_records = []
        for row in cursor.fetchall():
            recent_records.append({
                'strategy_id': row[0],
                'stock_count': row[1],
                'created_at': row[2]
            })
        
        conn.close()
        
        return {
            'total_records': total_records,
            'today_records': today_records,
            'unique_strategies': unique_strategies,
            'today_total_stocks': today_total_stocks,
            'recent_records': recent_records
        }
    
    def update_data_tracking(self, data_type: str):
        """
        更新数据跟踪信息
        
        Args:
            data_type: 数据类型（如 'stock_data', 'market_data'）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today_str = date.today().strftime('%Y-%m-%d')
        current_hash = self._calculate_data_hash()
        
        cursor.execute('''
            INSERT OR REPLACE INTO data_update_tracking 
            (data_type, last_update_date, update_hash)
            VALUES (?, ?, ?)
        ''', (data_type, today_str, current_hash))
        
        conn.commit()
        conn.close()
        
        print(f"📊 数据跟踪已更新: {data_type}")

# 创建全局实例
strategy_screening_cache = StrategyScreeningCache()