"""
分析结果缓存系统
实现数据库缓存机制，避免重复计算，提升系统性能
"""

import sqlite3
import json
import os
from datetime import date, datetime
from typing import Dict, Optional, Any
import pandas as pd
import numpy as np

# 数据库路径
DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'quant_analysis.db')

class AnalysisCache:
    """分析结果缓存管理器"""
    
    def __init__(self):
        self.db_path = DATABASE_PATH
        self._ensure_database_exists()
    
    def _ensure_database_exists(self):
        """确保数据库和表结构存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 创建股票基础信息表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_basic_info (
                stock_code TEXT PRIMARY KEY,
                stock_name TEXT,
                sector TEXT,
                last_updated TEXT
            )
        ''')
        
        # 创建分析结果缓存表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_results (
                stock_code TEXT,
                strategy_id TEXT,
                analysis_date TEXT,
                backtest_result TEXT,
                deep_analysis_result TEXT,
                chart_data TEXT,
                created_at TEXT,
                PRIMARY KEY (stock_code, strategy_id, analysis_date)
            )
        ''')
        
        # 创建索引以提升查询性能
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_analysis_date 
            ON analysis_results(analysis_date)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at 
            ON analysis_results(created_at)
        ''')
        
        conn.commit()
        conn.close()
    
    def get_cached_analysis(self, stock_code: str, strategy_id: str) -> Optional[Dict[str, Any]]:
        """
        从数据库获取缓存的分析结果
        
        Args:
            stock_code: 股票代码
            strategy_id: 策略ID
            
        Returns:
            缓存的分析结果，如果不存在或已过期则返回None
        """
        today_str = date.today().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT backtest_result, deep_analysis_result, chart_data 
            FROM analysis_results 
            WHERE stock_code=? AND strategy_id=? AND analysis_date=?
        ''', (stock_code, strategy_id, today_str))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            print(f"✅ 从数据库缓存命中: {stock_code} @ {strategy_id}")
            try:
                backtest_data = json.loads(result[0]) if result[0] else {}
                deep_analysis_data = json.loads(result[1]) if result[1] else {}
                chart_data = json.loads(result[2]) if result[2] else {}
                
                return {
                    'backtest_results': backtest_data,
                    'deep_analysis': deep_analysis_data,
                    'chart_data': chart_data
                }
            except json.JSONDecodeError as e:
                print(f"⚠️ 缓存数据解析失败: {e}")
                return None
        
        return None
    
    def save_analysis_result(self, stock_code: str, strategy_id: str, 
                           backtest_results: Dict, deep_analysis: Dict, 
                           chart_data: Dict):
        """
        将分析结果保存到数据库
        
        Args:
            stock_code: 股票代码
            strategy_id: 策略ID
            backtest_results: 回测结果
            deep_analysis: 深度分析结果
            chart_data: 图表数据
        """
        today_str = date.today().strftime('%Y-%m-%d')
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 使用 REPLACE 语句，如果主键已存在则更新，否则插入新行
        # 使用自定义序列化函数处理numpy类型
        def safe_json_dumps(obj):
            """【已修复】安全的JSON序列化，增加对Timestamp的处理"""
            def convert_types(item):
                if isinstance(item, dict):
                    return {k: convert_types(v) for k, v in item.items()}
                if isinstance(item, list):
                    return [convert_types(i) for i in item]
                # --- [核心修复逻辑] ---
                if isinstance(item, (datetime, date, pd.Timestamp)):
                    return item.isoformat()
                # --- [numpy 类型处理] ---
                if hasattr(item, 'item'): 
                    return item.item()
                if isinstance(item, (np.bool_, bool)): 
                    return bool(item)
                if isinstance(item, (np.integer)): 
                    return int(item)
                if isinstance(item, (np.floating)): 
                    return float(item)
                return item
            
            return json.dumps(convert_types(obj), ensure_ascii=False, default=str)
        
        cursor.execute('''
            REPLACE INTO analysis_results 
            (stock_code, strategy_id, analysis_date, backtest_result, 
             deep_analysis_result, chart_data, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (
            stock_code,
            strategy_id,
            today_str,
            safe_json_dumps(backtest_results),
            safe_json_dumps(deep_analysis),
            safe_json_dumps(chart_data)
        ))
        
        conn.commit()
        conn.close()
        
        print(f"💾 新结果已保存至数据库: {stock_code} @ {strategy_id}")
    
    def update_stock_info(self, stock_code: str, stock_name: str = None, 
                         sector: str = None):
        """
        更新股票基础信息
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            sector: 所属板块
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            REPLACE INTO stock_basic_info 
            (stock_code, stock_name, sector, last_updated) 
            VALUES (?, ?, ?, datetime('now'))
        ''', (stock_code, stock_name, sector))
        
        conn.commit()
        conn.close()
    
    def get_stock_info(self, stock_code: str) -> Optional[Dict[str, str]]:
        """
        获取股票基础信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票基础信息字典
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT stock_name, sector, last_updated 
            FROM stock_basic_info 
            WHERE stock_code=?
        ''', (stock_code,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return {
                'stock_name': result[0],
                'sector': result[1],
                'last_updated': result[2]
            }
        
        return None
    
    def clear_old_cache(self, days_old: int = 7):
        """
        清理过期的缓存数据
        
        Args:
            days_old: 清理多少天前的数据
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM analysis_results 
            WHERE created_at < datetime('now', '-{} days')
        '''.format(days_old))
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        print(f"🧹 已清理 {deleted_count} 条过期缓存记录")
        return deleted_count
    
    def invalidate_cache(self, stock_code: str = None, strategy_id: str = None):
        """
        缓存失效功能
        
        Args:
            stock_code: 指定股票代码，为None时清理所有股票
            strategy_id: 指定策略ID，为None时清理所有策略
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if stock_code and strategy_id:
            cursor.execute('DELETE FROM analysis_results WHERE stock_code=? AND strategy_id=?', 
                         (stock_code, strategy_id))
            print(f"🗑️ 已清理缓存: {stock_code} @ {strategy_id}")
        elif stock_code:
            cursor.execute('DELETE FROM analysis_results WHERE stock_code=?', (stock_code,))
            print(f"🗑️ 已清理股票缓存: {stock_code}")
        elif strategy_id:
            cursor.execute('DELETE FROM analysis_results WHERE strategy_id=?', (strategy_id,))
            print(f"🗑️ 已清理策略缓存: {strategy_id}")
        else:
            cursor.execute('DELETE FROM analysis_results')
            print("🗑️ 已清理所有缓存")
        
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def get_todays_analysis_by_strategy(self, strategy_id: str) -> list:
        """
        获取指定策略在今天的所有缓存分析结果
        """
        today_str = date.today().strftime('%Y-%m-%d')
        conn = sqlite3.connect(self.db_path)
        # 让返回结果为字典形式
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT stock_code, analysis_date, deep_analysis_result 
            FROM analysis_results 
            WHERE strategy_id=? AND analysis_date=?
        ''', (strategy_id, today_str))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results

    def get_cache_stats(self) -> Dict[str, int]:
        """
        获取缓存统计信息
        
        Returns:
            缓存统计信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 总记录数
        cursor.execute('SELECT COUNT(*) FROM analysis_results')
        total_records = cursor.fetchone()[0]
        
        # 今日记录数
        today_str = date.today().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM analysis_results WHERE analysis_date=?', (today_str,))
        today_records = cursor.fetchone()[0]
        
        # 股票数量
        cursor.execute('SELECT COUNT(DISTINCT stock_code) FROM analysis_results')
        unique_stocks = cursor.fetchone()[0]
        
        # 策略数量
        cursor.execute('SELECT COUNT(DISTINCT strategy_id) FROM analysis_results')
        unique_strategies = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_records': total_records,
            'today_records': today_records,
            'unique_stocks': unique_stocks,
            'unique_strategies': unique_strategies
        }


# 全局缓存实例
analysis_cache = AnalysisCache()