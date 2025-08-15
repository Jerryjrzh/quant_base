#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持仓列表管理模块
功能：
1. 持仓列表的增删改查
2. 深度扫描和操作建议
3. 补仓价、预期到顶日期、卖出提醒等分析
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import data_loader
import indicators
import strategies
from adjustment_processor import create_adjustment_config, create_adjustment_processor
import backtester

class PortfolioManager:
    def __init__(self, data_path: str = None):
        """初始化持仓管理器"""
        self.data_path = data_path or os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        self.portfolio_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio', 'portfolio.json')
        self.cache_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio', 'portfolio_scan_cache.json')
        self.ensure_portfolio_file()
        self.ensure_cache_file()
    
    def ensure_portfolio_file(self):
        """确保持仓文件存在"""
        os.makedirs(os.path.dirname(self.portfolio_file), exist_ok=True)
        if not os.path.exists(self.portfolio_file):
            self.save_portfolio([])
    
    def ensure_cache_file(self):
        """确保缓存文件存在"""
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        if not os.path.exists(self.cache_file):
            self.save_scan_cache({})
    
    def load_portfolio(self) -> List[Dict]:
        """加载持仓列表"""
        try:
            with open(self.portfolio_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def save_portfolio(self, portfolio: List[Dict]):
        """保存持仓列表"""
        with open(self.portfolio_file, 'w', encoding='utf-8') as f:
            json.dump(portfolio, f, ensure_ascii=False, indent=2)
    
    def add_position(self, stock_code: str, purchase_price: float, quantity: int, 
                    purchase_date: str = None, note: str = "") -> Dict:
        """添加持仓"""
        portfolio = self.load_portfolio()
        
        # 检查是否已存在
        for position in portfolio:
            if position['stock_code'] == stock_code:
                raise ValueError(f"股票 {stock_code} 已在持仓列表中")
        
        new_position = {
            'stock_code': stock_code,
            'purchase_price': purchase_price,
            'quantity': quantity,
            'purchase_date': purchase_date or datetime.now().strftime('%Y-%m-%d'),
            'note': note,
            'created_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_analysis_time': None
        }
        
        portfolio.append(new_position)
        self.save_portfolio(portfolio)
        return new_position
    
    def remove_position(self, stock_code: str) -> bool:
        """删除持仓"""
        portfolio = self.load_portfolio()
        original_count = len(portfolio)
        portfolio = [p for p in portfolio if p['stock_code'] != stock_code]
        
        if len(portfolio) < original_count:
            self.save_portfolio(portfolio)
            return True
        return False
    
    def update_position(self, stock_code: str, **kwargs) -> bool:
        """更新持仓信息"""
        portfolio = self.load_portfolio()
        
        for position in portfolio:
            if position['stock_code'] == stock_code:
                for key, value in kwargs.items():
                    if key in position:
                        position[key] = value
                position['updated_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.save_portfolio(portfolio)
                return True
        return False
    
    def get_stock_data(self, stock_code: str, adjustment_type: str = 'forward') -> Optional[pd.DataFrame]:
        """获取股票数据 - 使用统一数据处理模块"""
        from data_handler import get_full_data_with_indicators
        return get_full_data_with_indicators(stock_code, adjustment_type)
    
    def calculate_technical_indicators(self, df: pd.DataFrame, stock_code: str, 
                                     adjustment_type: str = 'forward') -> pd.DataFrame:
        """计算技术指标 - 使用统一数据处理模块"""
        from data_handler import calculate_all_indicators
        return calculate_all_indicators(df, stock_code, adjustment_type)
    
    def analyze_position_deep(self, stock_code: str, purchase_price: float, 
                            purchase_date: str) -> Dict:
        """深度分析单个持仓（调用backtester）"""
        try:
            df = self.get_stock_data(stock_code)
            if df is None:
                return {'error': f'无法获取股票 {stock_code} 的数据'}
            df = self.calculate_technical_indicators(df, stock_code)
            
            # 【核心修改】直接调用缓存/生成函数
            backtest_analysis_full = self._get_or_generate_backtest_analysis(stock_code, df)

            # 计算 profit_loss 等简单逻辑
            current_price = backtest_analysis_full.get('current_price', float(df.iloc[-1]['close']))
            profit_loss_pct = ((current_price - purchase_price) / purchase_price) * 100
            
            # 组装结果 (现在的数据源是 backtest_analysis_full)
            analysis = {
                'stock_code': stock_code,
                'current_price': current_price,
                'purchase_price': purchase_price,
                'profit_loss_pct': profit_loss_pct,
                'analysis_time': backtest_analysis_full.get('analysis_time'),
                
                # 直接使用 backtester 的结果
                'backtest_analysis': backtest_analysis_full.get('backtest_analysis'),
                'position_advice': backtest_analysis_full.get('trading_advice'),
                
                # 简化的持仓特定信息
                'purchase_date': purchase_date,
                'holding_days': (datetime.now() - datetime.strptime(purchase_date, '%Y-%m-%d')).days,
            }
            
            return analysis
            
        except Exception as e:
            return {'error': f'分析失败: {str(e)}'}
    
    def _get_or_generate_backtest_analysis(self, stock_code: str, df: pd.DataFrame) -> Dict:
        """获取或生成回测分析结果（通过调用backtester模块）"""
        backtest_cache_file = os.path.join(os.path.dirname(self.cache_file), f'backtest_cache_{stock_code}.json')
        
        try:
            # 缓存逻辑保持不变
            if os.path.exists(backtest_cache_file):
                with open(backtest_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                cache_time = datetime.strptime(cache_data['cache_time'], '%Y-%m-%d %H:%M:%S')
                if (datetime.now() - cache_time).days < 7:
                    # 确保返回的数据结构与新版一致
                    analysis_data = cache_data.get('analysis_results', {})
                    analysis_data['from_cache'] = True
                    return analysis_data
            
            # 【核心修改】调用 backtester 生成新的回测分析
            analysis_results = backtester.get_deep_analysis(stock_code, df)
            
            # 保存到缓存
            cache_data = {
                'cache_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'analysis_results': analysis_results
            }
            with open(backtest_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            analysis_results['from_cache'] = False
            return analysis_results
            
        except Exception as e:
            return {'error': f'回测分析失败: {str(e)}'}
    

            return f'预计还有{days_to_peak}天到达高点，耐心持有'
    
    def load_scan_cache(self) -> Dict:
        """加载扫描缓存"""
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    
    def save_scan_cache(self, cache_data: Dict):
        """保存扫描缓存"""
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
    
    def is_cache_valid(self, cache_time: str) -> bool:
        """检查缓存是否有效（一个交易日内）"""
        try:
            cache_dt = datetime.strptime(cache_time, '%Y-%m-%d %H:%M:%S')
            current_dt = datetime.now()
            
            # 如果是同一天，缓存有效
            if cache_dt.date() == current_dt.date():
                return True
            
            # 如果缓存是昨天的，但今天是周末，缓存仍然有效
            yesterday = current_dt.date() - timedelta(days=1)
            if cache_dt.date() == yesterday:
                # 周六(5)和周日(6)使用上一个交易日的缓存
                if current_dt.weekday() in [5, 6]:
                    return True
                # 周一使用周五的缓存
                if current_dt.weekday() == 0 and cache_dt.weekday() == 4:
                    return True
            
            return False
        except Exception:
            return False
    
    def get_cached_scan_results(self) -> Optional[Dict]:
        """获取缓存的扫描结果"""
        cache = self.load_scan_cache()
        
        if 'scan_time' in cache and 'results' in cache:
            if self.is_cache_valid(cache['scan_time']):
                return cache['results']
        
        return None
    
    def scan_all_positions(self, force_refresh: bool = False) -> Dict:
        """扫描所有持仓"""
        # 智能缓存策略：先尝试从缓存获取
        if not force_refresh:
            cached_results = self.get_cached_scan_results()
            if cached_results:
                # 添加缓存标识和提示信息
                cached_results['from_cache'] = True
                cached_results['cache_info'] = f'使用缓存数据（{cached_results["scan_time"]}），提升响应速度'
                print(f"📋 使用缓存的持仓扫描结果: {cached_results['scan_time']}")
                return cached_results
        
        # 执行实际扫描
        print(f"🔍 开始执行持仓深度扫描...")
        start_time = datetime.now()
        
        portfolio = self.load_portfolio()
        results = {
            'scan_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_positions': len(portfolio),
            'positions': [],
            'summary': {
                'profitable_count': 0,
                'loss_count': 0,
                'total_profit_loss': 0,
                'high_risk_count': 0,
                'action_required_count': 0
            },
            'from_cache': False
        }
        
        # 逐个分析持仓
        for i, position in enumerate(portfolio, 1):
            print(f"📊 分析持仓 {i}/{len(portfolio)}: {position['stock_code']}")
            
            analysis = self.analyze_position_deep(
                position['stock_code'],
                position['purchase_price'],
                position['purchase_date']
            )
            
            if 'error' not in analysis:
                # 更新持仓的最后分析时间
                self.update_position(position['stock_code'], 
                                   last_analysis_time=analysis['analysis_time'])
                
                # 统计汇总
                profit_loss = analysis['profit_loss_pct']
                if profit_loss > 0:
                    results['summary']['profitable_count'] += 1
                else:
                    results['summary']['loss_count'] += 1
                
                results['summary']['total_profit_loss'] += profit_loss
                
                if analysis['risk_assessment']['risk_level'] == 'HIGH':
                    results['summary']['high_risk_count'] += 1
                
                if analysis['position_advice']['action'] in ['REDUCE', 'STOP_LOSS', 'ADD']:
                    results['summary']['action_required_count'] += 1
            
            # 合并持仓基本信息和分析结果
            position_result = {**position, **analysis}
            results['positions'].append(position_result)
        
        # 计算扫描耗时
        end_time = datetime.now()
        scan_duration = (end_time - start_time).total_seconds()
        results['scan_duration'] = f"{scan_duration:.1f}秒"
        
        # 保存到缓存
        cache_data = {
            'scan_time': results['scan_time'],
            'results': results
        }
        self.save_scan_cache(cache_data)
        
        print(f"✅ 持仓扫描完成，耗时 {scan_duration:.1f}秒，已保存到缓存")
        
        return results


# 便捷函数
def create_portfolio_manager() -> PortfolioManager:
    """创建持仓管理器实例"""
    return PortfolioManager()