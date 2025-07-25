#!/usr/bin/env python3
"""
季度回测系统
按季度划分回溯过去一年的4个季度，验证和优化选股策略

功能：
1. 季度第一个月选出周线POST状态股票作为季度股票池
2. 使用短期策略测试股票池中的目标
3. 计算成功率、收益率等指标
4. 根据回测结果优化策略参数
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date
from dateutil.relativedelta import relativedelta
import json
from typing import Dict, List, Tuple, Optional
import logging
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# 添加backend路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import data_loader
import strategies
import indicators
import backtester

@dataclass
class QuarterlyBacktestConfig:
    """季度回测配置"""
    # 时间配置
    lookback_years: int = 1  # 回溯年数
    
    # 股票池配置
    pool_selection_strategy: str = 'WEEKLY_GOLDEN_CROSS_MA'  # 股票池选择策略
    pool_selection_period: int = 30  # 季度第一个月天数
    min_pool_size: int = 10  # 最小股票池大小
    max_pool_size: int = 100  # 最大股票池大小
    
    # 测试策略配置
    test_strategies: List[str] = None  # 测试策略列表
    test_period_days: int = 60  # 测试周期天数
    
    # 回测配置
    initial_capital: float = 100000.0  # 初始资金
    position_size: float = 0.1  # 单个股票仓位大小
    commission_rate: float = 0.001  # 手续费率
    slippage_rate: float = 0.0005  # 滑点率
    
    # 过滤配置
    min_price: float = 5.0  # 最低股价
    max_price: float = 200.0  # 最高股价
    min_volume: int = 1000000  # 最小成交量
    
    def __post_init__(self):
        if self.test_strategies is None:
            self.test_strategies = ['TRIPLE_CROSS', 'PRE_CROSS', 'MACD_ZERO_AXIS']

@dataclass
class QuarterlyResult:
    """季度回测结果"""
    quarter: str  # 季度标识，如"2023Q1"
    start_date: str
    end_date: str
    
    # 股票池信息
    pool_size: int
    pool_stocks: List[str]
    pool_selection_success_rate: float
    
    # 策略测试结果
    strategy_results: Dict[str, Dict]
    
    # 综合指标
    best_strategy: str
    best_strategy_return: float
    quarter_benchmark_return: float
    
    # 详细统计
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_return: float
    max_drawdown: float
    sharpe_ratio: float

class QuarterlyBacktester:
    """季度回测器"""
    
    def __init__(self, config: QuarterlyBacktestConfig = None):
        """
        初始化季度回测器
        
        Args:
            config: 回测配置
        """
        self.config = config or QuarterlyBacktestConfig()
        self.data_loader = data_loader.DataLoader() if hasattr(data_loader, 'DataLoader') else None
        
        # 设置日志
        self.logger = self._setup_logger()
        
        # 缓存数据
        self.stock_data_cache = {}
        self.quarterly_results = []
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger('QuarterlyBacktester')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def get_quarters_in_period(self, end_date: datetime = None) -> List[Tuple[str, datetime, datetime]]:
        """
        获取回测期间的季度列表
        
        Args:
            end_date: 结束日期，默认为当前日期
            
        Returns:
            List of (quarter_name, start_date, end_date)
        """
        if end_date is None:
            end_date = datetime.now()
        
        quarters = []
        
        # 计算起始日期
        start_date = end_date - relativedelta(years=self.config.lookback_years)
        
        # 找到起始季度
        start_quarter = ((start_date.month - 1) // 3) + 1
        start_year = start_date.year
        
        current_date = datetime(start_year, (start_quarter - 1) * 3 + 1, 1)
        
        while current_date < end_date:
            # 计算季度结束日期
            quarter_end = current_date + relativedelta(months=3) - timedelta(days=1)
            
            # 确保不超过结束日期
            if quarter_end > end_date:
                quarter_end = end_date
            
            quarter_name = f"{current_date.year}Q{((current_date.month - 1) // 3) + 1}"
            quarters.append((quarter_name, current_date, quarter_end))
            
            # 移动到下一个季度
            current_date = current_date + relativedelta(months=3)
        
        return quarters
    
    def load_stock_data(self, symbol: str, start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """
        加载股票数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            股票数据DataFrame
        """
        cache_key = f"{symbol}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
        
        if cache_key in self.stock_data_cache:
            return self.stock_data_cache[cache_key]
        
        try:
            # 尝试使用数据加载器
            if self.data_loader:
                df = self.data_loader.load_stock_data(symbol, start_date, end_date)
            else:
                # 使用原始数据加载方法
                base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
                market = symbol[:2]
                file_path = os.path.join(base_path, market, 'lday', f'{symbol}.day')
                
                if not os.path.exists(file_path):
                    return None
                
                df = data_loader.get_daily_data(file_path)
                if df is None:
                    return None
                
                # 过滤日期范围
                df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if df is None or df.empty:
                return None
            
            # 数据质量检查
            if len(df) < 30:  # 至少需要30天数据
                return None
            
            # 价格和成交量过滤
            if (df['close'].min() < self.config.min_price or 
                df['close'].max() > self.config.max_price or
                df['volume'].mean() < self.config.min_volume):
                return None
            
            self.stock_data_cache[cache_key] = df
            return df
            
        except Exception as e:
            self.logger.warning(f"加载股票数据失败 {symbol}: {e}")
            return None
    
    def get_stock_list(self) -> List[str]:
        """获取股票列表"""
        try:
            base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
            stock_list = []
            
            for market in ['sh', 'sz']:
                market_path = os.path.join(base_path, market, 'lday')
                if os.path.exists(market_path):
                    for file in os.listdir(market_path):
                        if file.endswith('.day'):
                            stock_code = file[:-4]  # 移除.day后缀
                            stock_list.append(stock_code)
            
            return stock_list[:500]  # 限制数量以提高测试速度
            
        except Exception as e:
            self.logger.error(f"获取股票列表失败: {e}")
            return []
    
    def select_quarterly_pool(self, quarter_start: datetime, quarter_end: datetime) -> List[str]:
        """
        选择季度股票池
        
        在季度第一个月选出周线POST状态的股票
        
        Args:
            quarter_start: 季度开始日期
            quarter_end: 季度结束日期
            
        Returns:
            股票池列表
        """
        self.logger.info(f"选择季度股票池: {quarter_start.strftime('%Y-%m-%d')} 到 {quarter_end.strftime('%Y-%m-%d')}")
        
        # 计算选择期间（季度第一个月）
        selection_end = quarter_start + timedelta(days=self.config.pool_selection_period)
        if selection_end > quarter_end:
            selection_end = quarter_end
        
        # 扩展数据加载范围以确保有足够的历史数据计算指标
        data_start = quarter_start - timedelta(days=365)  # 提前一年加载数据
        
        stock_list = self.get_stock_list()
        pool_candidates = []
        
        def process_stock(symbol):
            try:
                df = self.load_stock_data(symbol, data_start, selection_end)
                if df is None or len(df) < 100:  # 需要足够的历史数据
                    return None
                
                # 应用股票池选择策略
                strategy_func = strategies.get_strategy_function(self.config.pool_selection_strategy)
                if strategy_func is None:
                    return None
                
                signals = strategy_func(df)
                
                # 检查选择期间是否有POST信号
                selection_period_data = df[(df.index >= quarter_start) & (df.index <= selection_end)]
                if selection_period_data.empty:
                    return None
                
                selection_signals = signals.loc[selection_period_data.index]
                
                # 对于WEEKLY_GOLDEN_CROSS_MA策略，寻找BUY或HOLD信号
                if self.config.pool_selection_strategy == 'WEEKLY_GOLDEN_CROSS_MA':
                    has_signal = (selection_signals == 'BUY').any() or (selection_signals == 'HOLD').any()
                else:
                    # 对于其他策略，寻找POST信号
                    has_signal = (selection_signals == 'POST').any()
                
                if has_signal:
                    # 计算选择期间的表现作为排序依据
                    period_return = (selection_period_data['close'].iloc[-1] / selection_period_data['close'].iloc[0] - 1)
                    return (symbol, period_return)
                
                return None
                
            except Exception as e:
                self.logger.debug(f"处理股票 {symbol} 失败: {e}")
                return None
        
        # 并行处理股票
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(process_stock, symbol) for symbol in stock_list]
            
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    pool_candidates.append(result)
        
        # 按表现排序并选择股票池
        pool_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # 限制股票池大小
        pool_size = min(len(pool_candidates), self.config.max_pool_size)
        pool_size = max(pool_size, self.config.min_pool_size) if len(pool_candidates) >= self.config.min_pool_size else len(pool_candidates)
        
        selected_pool = [candidate[0] for candidate in pool_candidates[:pool_size]]
        
        self.logger.info(f"选择了 {len(selected_pool)} 只股票进入季度股票池")
        return selected_pool
    
    def test_strategy_on_pool(self, strategy_name: str, stock_pool: List[str], 
                            test_start: datetime, test_end: datetime) -> Dict:
        """
        在股票池上测试策略
        
        Args:
            strategy_name: 策略名称
            stock_pool: 股票池
            test_start: 测试开始日期
            test_end: 测试结束日期
            
        Returns:
            策略测试结果
        """
        self.logger.info(f"测试策略 {strategy_name} 在 {len(stock_pool)} 只股票上")
        
        strategy_func = strategies.get_strategy_function(strategy_name)
        if strategy_func is None:
            return {'error': f'策略 {strategy_name} 不存在'}
        
        # 扩展数据加载范围
        data_start = test_start - timedelta(days=365)
        
        all_trades = []
        successful_stocks = 0
        total_return = 0.0
        
        def test_stock(symbol):
            try:
                df = self.load_stock_data(symbol, data_start, test_end)
                if df is None or len(df) < 50:
                    return None
                
                # 应用策略
                signals = strategy_func(df)
                
                # 获取测试期间的信号
                test_period_data = df[(df.index >= test_start) & (df.index <= test_end)]
                if test_period_data.empty:
                    return None
                
                test_signals = signals.loc[test_period_data.index]
                
                # 找到信号点
                signal_points = []
                if strategy_name == 'WEEKLY_GOLDEN_CROSS_MA':
                    signal_points = test_period_data.index[test_signals == 'BUY'].tolist()
                else:
                    signal_points = test_period_data.index[test_signals.isin(['PRE', 'MID', 'POST'])].tolist()
                
                if not signal_points:
                    return None
                
                # 对每个信号点进行回测
                stock_trades = []
                for signal_date in signal_points:
                    try:
                        signal_state = test_signals.loc[signal_date]
                        
                        # 获取入场价格
                        entry_price, entry_date, entry_strategy, filtered = backtester.get_optimal_entry_price(
                            df, signal_date, signal_state
                        )
                        
                        if filtered or entry_price is None:
                            continue
                        
                        # 计算持有期收益
                        entry_idx = df.index.get_loc(entry_date)
                        max_hold_days = min(self.config.test_period_days, len(df) - entry_idx - 1)
                        
                        if max_hold_days <= 0:
                            continue
                        
                        hold_period_data = df.iloc[entry_idx:entry_idx + max_hold_days + 1]
                        
                        # 计算最大收益和最大回撤
                        returns = (hold_period_data['close'] / entry_price - 1)
                        max_return = returns.max()
                        min_return = returns.min()
                        final_return = returns.iloc[-1]
                        
                        # 计算持有天数
                        hold_days = len(hold_period_data) - 1
                        
                        trade = {
                            'symbol': symbol,
                            'signal_date': signal_date,
                            'signal_state': signal_state,
                            'entry_date': entry_date,
                            'entry_price': entry_price,
                            'entry_strategy': entry_strategy,
                            'hold_days': hold_days,
                            'max_return': max_return,
                            'min_return': min_return,
                            'final_return': final_return,
                            'success': max_return >= 0.05  # 5%以上认为成功
                        }
                        
                        stock_trades.append(trade)
                        
                    except Exception as e:
                        self.logger.debug(f"处理信号失败 {symbol} {signal_date}: {e}")
                        continue
                
                return stock_trades
                
            except Exception as e:
                self.logger.debug(f"测试股票 {symbol} 失败: {e}")
                return None
        
        # 并行测试股票
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(test_stock, symbol) for symbol in stock_pool]
            
            for future in as_completed(futures):
                result = future.result()
                if result is not None and len(result) > 0:
                    all_trades.extend(result)
                    successful_stocks += 1
        
        # 计算策略统计
        if not all_trades:
            return {
                'strategy_name': strategy_name,
                'total_trades': 0,
                'successful_stocks': 0,
                'win_rate': 0.0,
                'avg_return': 0.0,
                'avg_max_return': 0.0,
                'avg_max_drawdown': 0.0,
                'total_return': 0.0,
                'trades': []
            }
        
        # 统计计算
        total_trades = len(all_trades)
        winning_trades = sum(1 for trade in all_trades if trade['success'])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        avg_return = np.mean([trade['final_return'] for trade in all_trades])
        avg_max_return = np.mean([trade['max_return'] for trade in all_trades])
        avg_max_drawdown = np.mean([trade['min_return'] for trade in all_trades])
        
        total_return = sum(trade['final_return'] for trade in all_trades) / len(stock_pool)
        
        return {
            'strategy_name': strategy_name,
            'total_trades': total_trades,
            'successful_stocks': successful_stocks,
            'win_rate': win_rate,
            'avg_return': avg_return,
            'avg_max_return': avg_max_return,
            'avg_max_drawdown': avg_max_drawdown,
            'total_return': total_return,
            'trades': all_trades
        }
    
    def run_quarterly_backtest(self, quarter_name: str, quarter_start: datetime, quarter_end: datetime) -> QuarterlyResult:
        """
        运行单个季度的回测
        
        Args:
            quarter_name: 季度名称
            quarter_start: 季度开始日期
            quarter_end: 季度结束日期
            
        Returns:
            季度回测结果
        """
        self.logger.info(f"开始季度回测: {quarter_name}")
        
        # 1. 选择季度股票池
        stock_pool = self.select_quarterly_pool(quarter_start, quarter_end)
        
        if len(stock_pool) < self.config.min_pool_size:
            self.logger.warning(f"季度 {quarter_name} 股票池太小: {len(stock_pool)}")
        
        # 2. 计算股票池选择成功率（简化版本）
        pool_success_rate = min(len(stock_pool) / self.config.max_pool_size, 1.0)
        
        # 3. 在股票池上测试各种策略
        test_start = quarter_start + timedelta(days=self.config.pool_selection_period)
        if test_start >= quarter_end:
            test_start = quarter_start + timedelta(days=15)  # 至少留15天测试期
        
        strategy_results = {}
        for strategy_name in self.config.test_strategies:
            result = self.test_strategy_on_pool(strategy_name, stock_pool, test_start, quarter_end)
            strategy_results[strategy_name] = result
        
        # 4. 找出最佳策略
        best_strategy = None
        best_return = -float('inf')
        
        for strategy_name, result in strategy_results.items():
            if result.get('total_return', 0) > best_return:
                best_return = result.get('total_return', 0)
                best_strategy = strategy_name
        
        # 5. 计算综合统计
        all_trades = []
        for result in strategy_results.values():
            all_trades.extend(result.get('trades', []))
        
        total_trades = len(all_trades)
        winning_trades = sum(1 for trade in all_trades if trade.get('success', False))
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        avg_return = np.mean([trade['final_return'] for trade in all_trades]) if all_trades else 0
        max_drawdown = min([trade['min_return'] for trade in all_trades]) if all_trades else 0
        
        # 计算夏普比率（简化版本）
        returns = [trade['final_return'] for trade in all_trades]
        sharpe_ratio = np.mean(returns) / np.std(returns) if len(returns) > 1 and np.std(returns) > 0 else 0
        
        # 6. 创建季度结果
        quarterly_result = QuarterlyResult(
            quarter=quarter_name,
            start_date=quarter_start.strftime('%Y-%m-%d'),
            end_date=quarter_end.strftime('%Y-%m-%d'),
            pool_size=len(stock_pool),
            pool_stocks=stock_pool,
            pool_selection_success_rate=pool_success_rate,
            strategy_results=strategy_results,
            best_strategy=best_strategy or 'None',
            best_strategy_return=best_return,
            quarter_benchmark_return=0.0,  # 可以后续添加基准对比
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=total_trades - winning_trades,
            win_rate=win_rate,
            avg_return=avg_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio
        )
        
        self.logger.info(f"季度 {quarter_name} 回测完成: 最佳策略 {best_strategy}, 收益率 {best_return:.2%}")
        return quarterly_result
    
    def run_full_backtest(self) -> List[QuarterlyResult]:
        """
        运行完整的季度回测
        
        Returns:
            所有季度的回测结果
        """
        self.logger.info("开始完整季度回测")
        
        # 获取季度列表
        quarters = self.get_quarters_in_period()
        
        results = []
        for quarter_name, quarter_start, quarter_end in quarters:
            try:
                result = self.run_quarterly_backtest(quarter_name, quarter_start, quarter_end)
                results.append(result)
            except Exception as e:
                self.logger.error(f"季度 {quarter_name} 回测失败: {e}")
                continue
        
        self.quarterly_results = results
        return results
    
    def generate_optimization_report(self) -> Dict:
        """
        生成优化报告
        
        Returns:
            优化建议报告
        """
        if not self.quarterly_results:
            return {'error': '没有回测结果'}
        
        # 分析各季度最佳策略
        strategy_performance = {}
        for result in self.quarterly_results:
            for strategy_name, strategy_result in result.strategy_results.items():
                if strategy_name not in strategy_performance:
                    strategy_performance[strategy_name] = {
                        'quarters_used': 0,
                        'total_return': 0,
                        'total_trades': 0,
                        'total_wins': 0,
                        'avg_win_rate': 0,
                        'quarters': []
                    }
                
                perf = strategy_performance[strategy_name]
                perf['quarters_used'] += 1
                perf['total_return'] += strategy_result.get('total_return', 0)
                perf['total_trades'] += strategy_result.get('total_trades', 0)
                perf['total_wins'] += strategy_result.get('total_trades', 0) * strategy_result.get('win_rate', 0)
                perf['quarters'].append({
                    'quarter': result.quarter,
                    'return': strategy_result.get('total_return', 0),
                    'win_rate': strategy_result.get('win_rate', 0),
                    'trades': strategy_result.get('total_trades', 0)
                })
        
        # 计算平均表现
        for strategy_name, perf in strategy_performance.items():
            if perf['quarters_used'] > 0:
                perf['avg_return'] = perf['total_return'] / perf['quarters_used']
                perf['avg_win_rate'] = perf['total_wins'] / perf['total_trades'] if perf['total_trades'] > 0 else 0
        
        # 找出最佳策略
        best_overall_strategy = max(strategy_performance.keys(), 
                                  key=lambda x: strategy_performance[x]['avg_return'])
        
        # 季度分析
        quarterly_analysis = []
        for result in self.quarterly_results:
            quarterly_analysis.append({
                'quarter': result.quarter,
                'pool_size': result.pool_size,
                'best_strategy': result.best_strategy,
                'best_return': result.best_strategy_return,
                'win_rate': result.win_rate,
                'total_trades': result.total_trades
            })
        
        # 生成优化建议
        optimization_suggestions = []
        
        # 1. 策略选择建议
        if len(set(result.best_strategy for result in self.quarterly_results)) > 1:
            optimization_suggestions.append({
                'type': 'strategy_selection',
                'suggestion': f'不同季度最佳策略不同，建议使用自适应策略选择，整体最佳策略为 {best_overall_strategy}',
                'priority': 'high'
            })
        
        # 2. 股票池大小建议
        avg_pool_size = np.mean([result.pool_size for result in self.quarterly_results])
        if avg_pool_size < self.config.min_pool_size:
            optimization_suggestions.append({
                'type': 'pool_size',
                'suggestion': f'平均股票池大小 {avg_pool_size:.0f} 偏小，建议放宽选择条件',
                'priority': 'medium'
            })
        
        # 3. 胜率建议
        avg_win_rate = np.mean([result.win_rate for result in self.quarterly_results])
        if avg_win_rate < 0.4:
            optimization_suggestions.append({
                'type': 'win_rate',
                'suggestion': f'平均胜率 {avg_win_rate:.1%} 偏低，建议优化入场时机或止损策略',
                'priority': 'high'
            })
        
        return {
            'summary': {
                'total_quarters': len(self.quarterly_results),
                'best_overall_strategy': best_overall_strategy,
                'avg_quarterly_return': np.mean([result.best_strategy_return for result in self.quarterly_results]),
                'avg_win_rate': avg_win_rate,
                'total_trades': sum(result.total_trades for result in self.quarterly_results)
            },
            'strategy_performance': strategy_performance,
            'quarterly_analysis': quarterly_analysis,
            'optimization_suggestions': optimization_suggestions,
            'detailed_results': [asdict(result) for result in self.quarterly_results]
        }
    
    def save_results(self, filename: str = None):
        """保存回测结果"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'quarterly_backtest_results_{timestamp}.json'
        
        report = self.generate_optimization_report()
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        
        self.logger.info(f"回测结果已保存到: {filename}")
        return filename

def main():
    """主函数"""
    print("季度回测系统")
    print("=" * 50)
    
    # 创建配置
    config = QuarterlyBacktestConfig(
        lookback_years=1,
        pool_selection_strategy='WEEKLY_GOLDEN_CROSS_MA',
        test_strategies=['TRIPLE_CROSS', 'PRE_CROSS', 'MACD_ZERO_AXIS', 'WEEKLY_GOLDEN_CROSS_MA'],
        max_pool_size=50,  # 减少数量以提高测试速度
        test_period_days=45
    )
    
    # 创建回测器
    backtester = QuarterlyBacktester(config)
    
    # 运行回测
    print("开始运行季度回测...")
    results = backtester.run_full_backtest()
    
    if results:
        print(f"\n回测完成！共完成 {len(results)} 个季度的回测")
        
        # 生成报告
        report = backtester.generate_optimization_report()
        
        # 显示摘要
        summary = report['summary']
        print(f"\n=== 回测摘要 ===")
        print(f"总季度数: {summary['total_quarters']}")
        print(f"最佳整体策略: {summary['best_overall_strategy']}")
        print(f"平均季度收益率: {summary['avg_quarterly_return']:.2%}")
        print(f"平均胜率: {summary['avg_win_rate']:.1%}")
        print(f"总交易次数: {summary['total_trades']}")
        
        # 显示优化建议
        print(f"\n=== 优化建议 ===")
        for suggestion in report['optimization_suggestions']:
            priority_icon = "🔴" if suggestion['priority'] == 'high' else "🟡"
            print(f"{priority_icon} {suggestion['suggestion']}")
        
        # 保存结果
        filename = backtester.save_results()
        print(f"\n详细结果已保存到: {filename}")
        
    else:
        print("回测失败，没有生成结果")

if __name__ == "__main__":
    main()