#!/usr/bin/env python3
"""
核心观察池数据库管理器

这个模块实现了高级的股票池管理功能，包括：
- SQLite数据库持久化存储
- 股票评级、参数、信任度管理
- 动态调整和优化算法
- API接口供其他模块调用
"""

import sqlite3
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import pandas as pd


class StockPoolManager:
    """核心观察池数据库管理器"""
    
    def __init__(self, db_path: str = "stock_pool.db"):
        """初始化数据库管理器"""
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # 创建核心股票池表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS core_stock_pool (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT UNIQUE NOT NULL,
                    stock_name TEXT,
                    market TEXT,
                    industry TEXT,
                    
                    -- 评级信息
                    overall_score REAL NOT NULL,
                    grade TEXT NOT NULL,
                    risk_level TEXT,
                    
                    -- 优化参数
                    optimized_params TEXT,  -- JSON格式存储
                    optimization_date DATETIME,
                    optimization_method TEXT,
                    
                    -- 信任度和绩效
                    credibility_score REAL DEFAULT 1.0,
                    win_rate REAL,
                    avg_return REAL,
                    max_drawdown REAL,
                    sharpe_ratio REAL,
                    
                    -- 状态管理
                    status TEXT DEFAULT 'active',  -- active, inactive, monitoring
                    last_signal_date DATETIME,
                    signal_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    
                    -- 时间戳
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    
                    -- 备注
                    notes TEXT
                )
            ''')
            
            # 创建信号历史表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS signal_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    signal_type TEXT NOT NULL,  -- buy, sell, hold
                    confidence REAL NOT NULL,
                    trigger_price REAL,
                    target_price REAL,
                    stop_loss REAL,
                    
                    -- 执行结果
                    actual_entry_price REAL,
                    actual_exit_price REAL,
                    actual_return REAL,
                    holding_days INTEGER,
                    
                    -- 状态
                    status TEXT DEFAULT 'pending',  -- pending, executed, closed, cancelled
                    
                    -- 时间戳
                    signal_date DATETIME NOT NULL,
                    entry_date DATETIME,
                    exit_date DATETIME,
                    
                    -- 关联
                    FOREIGN KEY (stock_code) REFERENCES core_stock_pool (stock_code)
                )
            ''')
            
            # 创建绩效跟踪表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    tracking_date DATE NOT NULL,
                    
                    -- 价格数据
                    open_price REAL,
                    close_price REAL,
                    high_price REAL,
                    low_price REAL,
                    volume INTEGER,
                    
                    -- 技术指标
                    rsi REAL,
                    macd REAL,
                    signal_line REAL,
                    
                    -- 预测vs实际
                    predicted_direction TEXT,
                    actual_direction TEXT,
                    prediction_accuracy REAL,
                    
                    -- 时间戳
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    
                    -- 关联和唯一约束
                    FOREIGN KEY (stock_code) REFERENCES core_stock_pool (stock_code),
                    UNIQUE(stock_code, tracking_date)
                )
            ''')
            
            # 创建索引
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_stock_code ON core_stock_pool(stock_code)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_overall_score ON core_stock_pool(overall_score DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON core_stock_pool(status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_signal_date ON signal_history(signal_date DESC)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_tracking_date ON performance_tracking(tracking_date DESC)')
            
            conn.commit()
            self.logger.info("数据库初始化完成")
    
    def add_stock_to_pool(self, stock_info: Dict[str, Any]) -> bool:
        """添加股票到核心观察池"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 准备数据
                stock_code = stock_info['stock_code']
                optimized_params = json.dumps(stock_info.get('params', {}))
                
                cursor.execute('''
                    INSERT OR REPLACE INTO core_stock_pool 
                    (stock_code, stock_name, market, industry, overall_score, grade, 
                     risk_level, optimized_params, optimization_date, optimization_method,
                     credibility_score, win_rate, avg_return, max_drawdown, sharpe_ratio,
                     status, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stock_code,
                    stock_info.get('stock_name', ''),
                    stock_info.get('market', self._get_market_from_code(stock_code)),
                    stock_info.get('industry', ''),
                    stock_info.get('score', 0.0),
                    self._calculate_grade(stock_info.get('score', 0.0)),
                    stock_info.get('risk_level', 'MEDIUM'),
                    optimized_params,
                    stock_info.get('analysis_date', datetime.now().isoformat()),
                    stock_info.get('optimization_method', 'default'),
                    stock_info.get('credibility_score', 1.0),
                    stock_info.get('win_rate'),
                    stock_info.get('avg_return'),
                    stock_info.get('max_drawdown'),
                    stock_info.get('sharpe_ratio'),
                    stock_info.get('status', 'active'),
                    stock_info.get('notes', ''),
                    datetime.now().isoformat()
                ))
                
                conn.commit()
                self.logger.info(f"股票 {stock_code} 已添加到核心观察池")
                return True
                
        except Exception as e:
            self.logger.error(f"添加股票到观察池失败: {e}")
            return False
    
    def get_core_pool(self, status: str = 'active', limit: Optional[int] = None) -> List[Dict]:
        """获取核心观察池股票列表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                query = '''
                    SELECT stock_code, stock_name, market, industry, overall_score, grade,
                           risk_level, optimized_params, credibility_score, win_rate,
                           avg_return, status, last_signal_date, signal_count, success_count,
                           created_at, updated_at, notes
                    FROM core_stock_pool 
                    WHERE status = ?
                    ORDER BY overall_score DESC, credibility_score DESC
                '''
                
                if limit:
                    query += f' LIMIT {limit}'
                
                cursor.execute(query, (status,))
                rows = cursor.fetchall()
                
                columns = [desc[0] for desc in cursor.description]
                result = []
                
                for row in rows:
                    stock_data = dict(zip(columns, row))
                    # 解析JSON参数
                    if stock_data['optimized_params']:
                        stock_data['optimized_params'] = json.loads(stock_data['optimized_params'])
                    result.append(stock_data)
                
                return result
                
        except Exception as e:
            self.logger.error(f"获取核心观察池失败: {e}")
            return []
    
    def update_stock_credibility(self, stock_code: str, new_credibility: float) -> bool:
        """更新股票信任度"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE core_stock_pool 
                    SET credibility_score = ?, updated_at = ?
                    WHERE stock_code = ?
                ''', (new_credibility, datetime.now().isoformat(), stock_code))
                
                conn.commit()
                
                if cursor.rowcount > 0:
                    self.logger.info(f"股票 {stock_code} 信任度已更新为 {new_credibility}")
                    return True
                else:
                    self.logger.warning(f"股票 {stock_code} 不存在于观察池中")
                    return False
                    
        except Exception as e:
            self.logger.error(f"更新股票信任度失败: {e}")
            return False
    
    def record_signal(self, signal_data: Dict[str, Any]) -> bool:
        """记录交易信号"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    INSERT INTO signal_history 
                    (stock_code, signal_type, confidence, trigger_price, target_price,
                     stop_loss, signal_date, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    signal_data['stock_code'],
                    signal_data['signal_type'],
                    signal_data['confidence'],
                    signal_data.get('trigger_price'),
                    signal_data.get('target_price'),
                    signal_data.get('stop_loss'),
                    signal_data.get('signal_date', datetime.now().isoformat()),
                    signal_data.get('status', 'pending')
                ))
                
                # 更新股票的信号计数
                cursor.execute('''
                    UPDATE core_stock_pool 
                    SET signal_count = signal_count + 1,
                        last_signal_date = ?,
                        updated_at = ?
                    WHERE stock_code = ?
                ''', (
                    signal_data.get('signal_date', datetime.now().isoformat()),
                    datetime.now().isoformat(),
                    signal_data['stock_code']
                ))
                
                conn.commit()
                self.logger.info(f"信号已记录: {signal_data['stock_code']} - {signal_data['signal_type']}")
                return True
                
        except Exception as e:
            self.logger.error(f"记录信号失败: {e}")
            return False
    
    def update_signal_result(self, signal_id: int, result_data: Dict[str, Any]) -> bool:
        """更新信号执行结果"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 更新信号结果
                cursor.execute('''
                    UPDATE signal_history 
                    SET actual_entry_price = ?, actual_exit_price = ?, actual_return = ?,
                        holding_days = ?, status = ?, entry_date = ?, exit_date = ?
                    WHERE id = ?
                ''', (
                    result_data.get('actual_entry_price'),
                    result_data.get('actual_exit_price'),
                    result_data.get('actual_return'),
                    result_data.get('holding_days'),
                    result_data.get('status', 'closed'),
                    result_data.get('entry_date'),
                    result_data.get('exit_date'),
                    signal_id
                ))
                
                # 如果是成功的交易，更新股票的成功计数
                if result_data.get('actual_return', 0) > 0:
                    cursor.execute('''
                        SELECT stock_code FROM signal_history WHERE id = ?
                    ''', (signal_id,))
                    
                    stock_code = cursor.fetchone()[0]
                    
                    cursor.execute('''
                        UPDATE core_stock_pool 
                        SET success_count = success_count + 1,
                            updated_at = ?
                        WHERE stock_code = ?
                    ''', (datetime.now().isoformat(), stock_code))
                
                conn.commit()
                self.logger.info(f"信号结果已更新: ID {signal_id}")
                return True
                
        except Exception as e:
            self.logger.error(f"更新信号结果失败: {e}")
            return False
    
    def get_stock_performance(self, stock_code: str, days: int = 30) -> Dict[str, Any]:
        """获取股票绩效统计"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 获取基本信息
                cursor.execute('''
                    SELECT overall_score, credibility_score, win_rate, avg_return,
                           signal_count, success_count, last_signal_date
                    FROM core_stock_pool 
                    WHERE stock_code = ?
                ''', (stock_code,))
                
                basic_info = cursor.fetchone()
                if not basic_info:
                    return {}
                
                # 获取最近的信号统计
                since_date = (datetime.now() - timedelta(days=days)).isoformat()
                cursor.execute('''
                    SELECT COUNT(*) as total_signals,
                           AVG(CASE WHEN actual_return > 0 THEN 1.0 ELSE 0.0 END) as recent_win_rate,
                           AVG(actual_return) as recent_avg_return,
                           MAX(signal_date) as last_signal
                    FROM signal_history 
                    WHERE stock_code = ? AND signal_date >= ?
                ''', (stock_code, since_date))
                
                recent_stats = cursor.fetchone()
                
                return {
                    'stock_code': stock_code,
                    'overall_score': basic_info[0],
                    'credibility_score': basic_info[1],
                    'historical_win_rate': basic_info[2],
                    'historical_avg_return': basic_info[3],
                    'total_signals': basic_info[4],
                    'total_successes': basic_info[5],
                    'last_signal_date': basic_info[6],
                    'recent_signals': recent_stats[0] or 0,
                    'recent_win_rate': recent_stats[1] or 0.0,
                    'recent_avg_return': recent_stats[2] or 0.0,
                    'performance_trend': self._calculate_performance_trend(
                        basic_info[2], recent_stats[1] or 0.0
                    )
                }
                
        except Exception as e:
            self.logger.error(f"获取股票绩效失败: {e}")
            return {}
    
    def adjust_pool_based_on_performance(self, min_credibility: float = 0.3) -> Dict[str, int]:
        """基于绩效调整核心观察池"""
        try:
            adjustments = {'promoted': 0, 'demoted': 0, 'removed': 0}
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 获取所有活跃股票的绩效
                cursor.execute('''
                    SELECT stock_code, credibility_score, signal_count, success_count
                    FROM core_stock_pool 
                    WHERE status = 'active'
                ''')
                
                stocks = cursor.fetchall()
                
                for stock_code, credibility, signal_count, success_count in stocks:
                    # 计算实际胜率
                    actual_win_rate = success_count / signal_count if signal_count > 0 else 0.5
                    
                    # 计算新的信任度
                    new_credibility = self._calculate_new_credibility(
                        credibility, actual_win_rate, signal_count
                    )
                    
                    # 根据信任度调整状态
                    if new_credibility < min_credibility:
                        # 移除低信任度股票
                        cursor.execute('''
                            UPDATE core_stock_pool 
                            SET status = 'inactive', updated_at = ?
                            WHERE stock_code = ?
                        ''', (datetime.now().isoformat(), stock_code))
                        adjustments['removed'] += 1
                        self.logger.info(f"股票 {stock_code} 因信任度过低被移除")
                        
                    elif new_credibility > credibility * 1.1:
                        # 提升表现良好的股票
                        cursor.execute('''
                            UPDATE core_stock_pool 
                            SET credibility_score = ?, updated_at = ?
                            WHERE stock_code = ?
                        ''', (new_credibility, datetime.now().isoformat(), stock_code))
                        adjustments['promoted'] += 1
                        self.logger.info(f"股票 {stock_code} 信任度提升至 {new_credibility:.3f}")
                        
                    elif new_credibility < credibility * 0.9:
                        # 降级表现不佳的股票
                        cursor.execute('''
                            UPDATE core_stock_pool 
                            SET credibility_score = ?, updated_at = ?
                            WHERE stock_code = ?
                        ''', (new_credibility, datetime.now().isoformat(), stock_code))
                        adjustments['demoted'] += 1
                        self.logger.info(f"股票 {stock_code} 信任度降级至 {new_credibility:.3f}")
                
                conn.commit()
                
            return adjustments
            
        except Exception as e:
            self.logger.error(f"调整观察池失败: {e}")
            return {'promoted': 0, 'demoted': 0, 'removed': 0}
    
    def get_pool_statistics(self) -> Dict[str, Any]:
        """获取观察池统计信息"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 基本统计
                cursor.execute('''
                    SELECT 
                        COUNT(*) as total_stocks,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_stocks,
                        AVG(overall_score) as avg_score,
                        AVG(credibility_score) as avg_credibility,
                        SUM(signal_count) as total_signals,
                        SUM(success_count) as total_successes
                    FROM core_stock_pool
                ''')
                
                basic_stats = cursor.fetchone()
                
                # 评级分布
                cursor.execute('''
                    SELECT grade, COUNT(*) as count
                    FROM core_stock_pool 
                    WHERE status = 'active'
                    GROUP BY grade
                    ORDER BY grade
                ''')
                
                grade_distribution = dict(cursor.fetchall())
                
                # 最近信号统计
                recent_date = (datetime.now() - timedelta(days=7)).isoformat()
                cursor.execute('''
                    SELECT COUNT(*) as recent_signals
                    FROM signal_history 
                    WHERE signal_date >= ?
                ''', (recent_date,))
                
                recent_signals = cursor.fetchone()[0]
                
                total_signals = basic_stats[4] or 0
                total_successes = basic_stats[5] or 0
                
                return {
                    'total_stocks': basic_stats[0] or 0,
                    'active_stocks': basic_stats[1] or 0,
                    'avg_score': basic_stats[2] or 0.0,
                    'avg_credibility': basic_stats[3] or 0.0,
                    'total_signals': total_signals,
                    'total_successes': total_successes,
                    'overall_win_rate': (total_successes / total_signals) if total_signals > 0 else 0.0,
                    'grade_distribution': grade_distribution,
                    'recent_signals': recent_signals or 0,
                    'last_updated': datetime.now().isoformat()
                }
                
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def export_to_json(self, filepath: str = "core_stock_pool.json") -> bool:
        """导出核心观察池到JSON文件（兼容现有格式）"""
        try:
            core_pool = self.get_core_pool()
            
            # 转换为现有格式
            export_data = []
            for stock in core_pool:
                export_data.append({
                    'stock_code': stock['stock_code'],
                    'score': stock['overall_score'],
                    'params': stock['optimized_params'] or {},
                    'analysis_date': stock['updated_at'],
                    'credibility_score': stock['credibility_score'],
                    'grade': stock['grade'],
                    'win_rate': stock['win_rate'],
                    'signal_count': stock['signal_count'],
                    'success_count': stock['success_count']
                })
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"核心观察池已导出到 {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"导出失败: {e}")
            return False
    
    def import_from_json(self, filepath: str = "core_stock_pool.json") -> bool:
        """从JSON文件导入核心观察池"""
        try:
            if not os.path.exists(filepath):
                self.logger.warning(f"文件不存在: {filepath}")
                return False
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            imported_count = 0
            for stock_info in data:
                if self.add_stock_to_pool(stock_info):
                    imported_count += 1
            
            self.logger.info(f"成功导入 {imported_count} 只股票到观察池")
            return True
            
        except Exception as e:
            self.logger.error(f"导入失败: {e}")
            return False
    
    def _get_market_from_code(self, stock_code: str) -> str:
        """从股票代码推断市场"""
        if stock_code.startswith('sh'):
            return 'SH'
        elif stock_code.startswith('sz'):
            return 'SZ'
        else:
            return 'UNKNOWN'
    
    def _calculate_grade(self, score: float) -> str:
        """根据评分计算等级"""
        if score >= 0.8:
            return 'A'
        elif score >= 0.6:
            return 'B'
        elif score >= 0.4:
            return 'C'
        elif score >= 0.2:
            return 'D'
        else:
            return 'F'
    
    def _calculate_performance_trend(self, historical_rate: Optional[float], 
                                   recent_rate: float) -> str:
        """计算绩效趋势"""
        if historical_rate is None:
            return 'NEW'
        
        if recent_rate > historical_rate * 1.1:
            return 'IMPROVING'
        elif recent_rate < historical_rate * 0.9:
            return 'DECLINING'
        else:
            return 'STABLE'
    
    def _calculate_new_credibility(self, current_credibility: float, 
                                 actual_win_rate: float, signal_count: int) -> float:
        """计算新的信任度"""
        # 基于实际胜率和信号数量调整信任度
        if signal_count < 5:
            # 信号数量太少，保持当前信任度
            return current_credibility
        
        # 期望胜率（基于当前信任度）
        expected_win_rate = 0.5 + (current_credibility - 0.5) * 0.5
        
        # 计算调整因子
        performance_ratio = actual_win_rate / expected_win_rate if expected_win_rate > 0 else 1.0
        
        # 调整信任度
        new_credibility = current_credibility * (0.8 + 0.4 * performance_ratio)
        
        # 限制在合理范围内
        return max(0.1, min(1.0, new_credibility))


def main():
    """测试函数"""
    # 设置日志
    logging.basicConfig(level=logging.INFO)
    
    # 创建管理器
    manager = StockPoolManager("test_stock_pool.db")
    
    # 测试添加股票
    test_stock = {
        'stock_code': 'sz300290',
        'stock_name': '荣科科技',
        'score': 0.75,
        'params': {
            'pre_entry_discount': 0.02,
            'moderate_stop': 0.05
        },
        'risk_level': 'MEDIUM',
        'win_rate': 0.65,
        'avg_return': 0.08
    }
    
    manager.add_stock_to_pool(test_stock)
    
    # 测试获取观察池
    pool = manager.get_core_pool()
    print(f"观察池股票数量: {len(pool)}")
    
    # 测试统计信息
    stats = manager.get_pool_statistics()
    print(f"统计信息: {stats}")
    
    # 清理测试数据库
    os.remove("test_stock_pool.db")


if __name__ == "__main__":
    main()