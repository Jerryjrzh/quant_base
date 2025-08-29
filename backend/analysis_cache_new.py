"""
【V1.1 - 已修复】分析结果缓存系统
修复了在序列化pandas.Timestamp对象时发生的TypeError
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
    
    # ... (_ensure_database_exists logic remains the same) ...
    def _ensure_database_exists(self):
        """确保数据库和表结构存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS analysis_results (
                stock_code TEXT, strategy_id TEXT, analysis_date TEXT,
                backtest_result TEXT, deep_analysis_result TEXT, chart_data TEXT,
                created_at TEXT, PRIMARY KEY (stock_code, strategy_id, analysis_date)
            )
        ''')
        conn.commit()
        conn.close()

    def get_cached_analysis(self, stock_code: str, strategy_id: str) -> Optional[Dict[str, Any]]:
        """从数据库获取缓存的分析结果"""
        today_str = date.today().strftime('%Y-%m-%d')
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            'SELECT backtest_result, deep_analysis_result, chart_data FROM analysis_results WHERE stock_code=? AND strategy_id=? AND analysis_date=?',
            (stock_code, strategy_id, today_str)
        )
        result = cursor.fetchone()
        conn.close()
        
        if result:
            print(f"✅ 从数据库缓存命中: {stock_code} @ {strategy_id}")
            try:
                # Renamed for clarity in V4.1 response structure
                return {
                    'historical_backtest': json.loads(result[0]) if result[0] else {},
                    'deep_analysis': json.loads(result[1]) if result[1] else {},
                    'chart_data': json.loads(result[2]) if result[2] else {}
                }
            except json.JSONDecodeError as e:
                print(f"⚠️ 缓存数据解析失败: {e}")
                return None
        return None
    
    def save_analysis_result(self, stock_code: str, strategy_id: str, 
                           backtest_results: Dict, deep_analysis: Dict, 
                           chart_data: Dict):
        """将分析结果保存到数据库"""
        today_str = date.today().strftime('%Y-%m-%d')
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
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
                if hasattr(item, 'item'): return item.item()
                if isinstance(item, (np.bool_, bool)): return bool(item)
                if isinstance(item, (np.integer)): return int(item)
                if isinstance(item, (np.floating)): return float(item)
                return item
            
            return json.dumps(convert_types(obj), ensure_ascii=False, default=str)
        
        cursor.execute('''
            REPLACE INTO analysis_results 
            (stock_code, strategy_id, analysis_date, backtest_result, 
             deep_analysis_result, chart_data, created_at) 
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        ''', (
            stock_code, strategy_id, today_str,
            safe_json_dumps(backtest_results),
            safe_json_dumps(deep_analysis),
            safe_json_dumps(chart_data)
        ))
        
        conn.commit()
        conn.close()
        print(f"💾 新结果已保存至数据库: {stock_code} @ {strategy_id}")

    # ... (other methods like update_stock_info, clear_old_cache, etc., remain the same) ...

# 全局缓存实例
analysis_cache = AnalysisCache()