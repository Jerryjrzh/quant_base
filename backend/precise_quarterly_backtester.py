#!/usr/bin/env python3
"""
精确季度回测系统 - 增强版强势股票筛选
按照具体的时间窗口和条件进行季度回测

增强版筛选流程：
1. 六周周线稳步上升趋势确认（新增）
2. 最近三周日线不能出现死叉（新增）
3. 季度第三周结束，通过周线金叉判断
4. 季度初三周内单日涨幅超过7%确认强势
5. 选入核心池，对当季剩余时间进行回测
6. 输出具体操作策略

新增强势股票筛选条件：
- 六周周线稳步上升：至少60%的周期上涨，整体涨幅≥3%，均线排列良好
- 三周无死叉：5日均线不跌破10日均线，保持强势格局
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json
import logging
from dataclasses import dataclass, asdict

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import data_loader
import strategies
import indicators

# 导入现实回测模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from enhanced_realistic_backtester import RealisticBacktester, TradingWindow, MarketImpact, ExecutionWindow
    REALISTIC_BACKTESTING_AVAILABLE = True
except ImportError:
    REALISTIC_BACKTESTING_AVAILABLE = False

# 导入T+1智能交易系统
try:
    from t1_intelligent_trading_system import T1IntelligentTradingSystem, TradingAction, TrendExpectation
    T1_TRADING_AVAILABLE = True
except ImportError:
    T1_TRADING_AVAILABLE = False

@dataclass
class PreciseQuarterlyConfig:
    """精确季度回测配置"""
    # 当前季度配置
    current_quarter: str = "2025Q2"  # 当前季度
    quarter_start: str = "2025-06-17"  # 季度开始
    selection_end: str = "2025-07-18"   # 选股结束日期（第三周结束）
    backtest_start: str = "2025-07-21"  # 回测开始日期
    backtest_end: str = "2025-07-25"    # 回测结束日期（当前日期）
    
    # 选股条件
    min_daily_gain: float = 0.07  # 单日最小涨幅7%
    require_weekly_golden_cross: bool = True  # 需要周线金叉
    
    # 回测配置
    initial_capital: float = 100000.0
    max_position_size: float = 0.2  # 单股最大仓位20%
    commission_rate: float = 0.001
    
    # 过滤条件
    min_price: float = 5.0
    max_price: float = 200.0
    min_volume: int = 1000000

@dataclass
class StockSelection:
    """股票选择结果"""
    symbol: str
    selection_date: str  # 选入日期
    max_gain_date: str   # 最大涨幅日期
    max_gain: float      # 最大涨幅
    weekly_cross_confirmed: bool  # 周线金叉确认
    selection_price: float  # 选入时价格

@dataclass
class BacktestTrade:
    """回测交易记录"""
    symbol: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    return_rate: float
    hold_days: int
    strategy: str
    # T+1相关字段
    trading_action: str = ""  # 交易动作
    trend_expectation: str = ""  # 走势预期
    confidence: float = 0.0  # 信号置信度
    t1_compliant: bool = True  # T+1规则合规

@dataclass
class QuarterlyStrategy:
    """季度操作策略"""
    quarter: str
    core_pool: List[StockSelection]
    recommended_trades: List[BacktestTrade]
    strategy_summary: Dict
    performance_metrics: Dict

class PreciseQuarterlyBacktester:
    """精确季度回测器"""
    
    def __init__(self, config: PreciseQuarterlyConfig = None):
        self.config = config or PreciseQuarterlyConfig()
        self.logger = self._setup_logger()
        
        # 转换日期
        self.quarter_start = datetime.strptime(self.config.quarter_start, '%Y-%m-%d')
        self.selection_end = datetime.strptime(self.config.selection_end, '%Y-%m-%d')
        self.backtest_start = datetime.strptime(self.config.backtest_start, '%Y-%m-%d')
        self.backtest_end = datetime.strptime(self.config.backtest_end, '%Y-%m-%d')
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger('PreciseQuarterlyBacktester')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def load_stock_data(self, symbol: str, start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """加载股票数据"""
        try:
            base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
            market = symbol[:2]
            file_path = os.path.join(base_path, market, 'lday', f'{symbol}.day')
            
            if not os.path.exists(file_path):
                return None
            
            df = data_loader.get_daily_data(file_path)
            if df is None or df.empty:
                return None
            
            # 扩展数据范围以确保有足够的历史数据计算指标
            extended_start = start_date - timedelta(days=365)
            df = df[(df.index >= extended_start) & (df.index <= end_date)]
            
            if len(df) < 50:  # 需要足够的历史数据
                return None
            
            return df
            
        except Exception as e:
            self.logger.debug(f"加载股票数据失败 {symbol}: {e}")
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
                            stock_code = file[:-4]
                            stock_list.append(stock_code)
            
            return stock_list[:7000]  # 限制数量以提高速度
            
        except Exception as e:
            self.logger.error(f"获取股票列表失败: {e}")
            return []
    
    def check_weekly_golden_cross(self, df: pd.DataFrame, check_date: datetime) -> bool:
        """检查周线金叉状态"""
        try:
            # 转换为周线数据
            weekly_df = self.convert_to_weekly(df, check_date)
            if weekly_df is None or len(weekly_df) < 30:
                return False
            
            # 应用周线金叉策略
            signals = strategies.apply_weekly_golden_cross_ma_strategy(weekly_df)
            
            # 检查最近的信号
            recent_signals = signals[signals.isin(['BUY', 'HOLD'])].tail(5)
            return not recent_signals.empty
            
        except Exception as e:
            self.logger.debug(f"周线金叉检查失败: {e}")
            return False
    
    def check_six_weeks_uptrend(self, df: pd.DataFrame, check_date: datetime) -> bool:
        """检查六周周线稳步上升趋势"""
        try:
            # 转换为周线数据
            weekly_df = self.convert_to_weekly(df, check_date)
            if weekly_df is None or len(weekly_df) < 10:
                return False
            
            # 获取最近6周的数据
            recent_weeks = weekly_df.tail(6)
            if len(recent_weeks) < 6:
                return False
            
            # 检查周线收盘价是否稳步上升
            closes = recent_weeks['close'].values
            
            # 计算上升趋势的强度
            upward_weeks = 0
            for i in range(1, len(closes)):
                if closes[i] > closes[i-1]:
                    upward_weeks += 1
            
            # 至少4周上升，允许1-2周的小幅调整
            upward_ratio = upward_weeks / (len(closes) - 1)
            
            # 整体趋势向上：最后一周价格 > 第一周价格的5%
            overall_gain = (closes[-1] - closes[0]) / closes[0]
            
            # 计算5周和10周均线
            if len(weekly_df) >= 10:
                weekly_df_copy = weekly_df.copy()
                weekly_df_copy['ma5'] = weekly_df_copy['close'].rolling(window=5).mean()
                weekly_df_copy['ma10'] = weekly_df_copy['close'].rolling(window=10).mean()
                
                # 检查最新的均线排列
                latest_data = weekly_df_copy.iloc[-1]
                ma_alignment = (latest_data['close'] > latest_data['ma5'] > latest_data['ma10'])
            else:
                ma_alignment = True  # 如果数据不足，不进行均线检查
            
            # 综合判断：上升比例 >= 60%，整体涨幅 >= 3%，均线排列良好
            is_strong_uptrend = (upward_ratio >= 0.6 and 
                               overall_gain >= 0.03 and 
                               ma_alignment)
            
            if is_strong_uptrend:
                self.logger.debug(f"六周强势上升: 上升比例={upward_ratio:.1%}, 整体涨幅={overall_gain:.1%}")
            
            return is_strong_uptrend
            
        except Exception as e:
            self.logger.debug(f"六周趋势检查失败: {e}")
            return False
    
    def check_no_daily_death_cross(self, df: pd.DataFrame, check_date: datetime) -> bool:
        """检查最近三周日线不能出现死叉"""
        try:
            # 计算检查的开始日期（三周前）
            three_weeks_ago = check_date - timedelta(weeks=3)
            
            # 获取最近三周的日线数据
            recent_df = df[(df.index >= three_weeks_ago) & (df.index <= check_date)]
            if len(recent_df) < 10:  # 至少需要10个交易日
                return False
            
            # 计算5日和10日移动平均线
            recent_df = recent_df.copy()
            recent_df['ma5'] = recent_df['close'].rolling(window=5).mean()
            recent_df['ma10'] = recent_df['close'].rolling(window=10).mean()
            
            # 检查是否出现死叉（5日均线跌破10日均线）
            # 死叉定义：前一天5日均线 > 10日均线，当天5日均线 < 10日均线
            for i in range(1, len(recent_df)):
                if (pd.notna(recent_df.iloc[i-1]['ma5']) and 
                    pd.notna(recent_df.iloc[i-1]['ma10']) and
                    pd.notna(recent_df.iloc[i]['ma5']) and 
                    pd.notna(recent_df.iloc[i]['ma10'])):
                    
                    prev_ma5 = recent_df.iloc[i-1]['ma5']
                    prev_ma10 = recent_df.iloc[i-1]['ma10']
                    curr_ma5 = recent_df.iloc[i]['ma5']
                    curr_ma10 = recent_df.iloc[i]['ma10']
                    
                    # 检测死叉
                    if prev_ma5 > prev_ma10 and curr_ma5 < curr_ma10:
                        self.logger.debug(f"检测到死叉: {recent_df.index[i].strftime('%Y-%m-%d')}")
                        return False
            
            # 额外检查：当前5日均线应该在10日均线之上
            if (pd.notna(recent_df.iloc[-1]['ma5']) and 
                pd.notna(recent_df.iloc[-1]['ma10'])):
                current_ma5 = recent_df.iloc[-1]['ma5']
                current_ma10 = recent_df.iloc[-1]['ma10']
                
                if current_ma5 < current_ma10 * 0.98:  # 允许2%的误差
                    self.logger.debug(f"当前均线排列不佳: MA5={current_ma5:.2f} < MA10={current_ma10:.2f}")
                    return False
            
            return True
            
        except Exception as e:
            self.logger.debug(f"日线死叉检查失败: {e}")
            return False
    
    def convert_to_weekly(self, daily_df: pd.DataFrame, end_date: datetime) -> Optional[pd.DataFrame]:
        """将日线数据转换为周线数据"""
        try:
            # 过滤到指定日期
            df = daily_df[daily_df.index <= end_date].copy()
            if df.empty:
                return None
            
            # 按周重采样
            weekly_df = df.resample('W').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            return weekly_df
            
        except Exception as e:
            self.logger.debug(f"周线转换失败: {e}")
            return None
    
    def find_max_daily_gain(self, df: pd.DataFrame, start_date: datetime, end_date: datetime) -> Tuple[float, datetime]:
        """找到指定期间的最大单日涨幅"""
        try:
            period_df = df[(df.index >= start_date) & (df.index <= end_date)]
            if period_df.empty:
                return 0.0, start_date
            
            # 计算单日涨幅
            period_df = period_df.copy()
            period_df['daily_return'] = period_df['close'].pct_change()
            
            # 找到最大涨幅
            max_return_idx = period_df['daily_return'].idxmax()
            max_return = period_df.loc[max_return_idx, 'daily_return']
            
            return max_return, max_return_idx
            
        except Exception as e:
            self.logger.debug(f"计算最大涨幅失败: {e}")
            return 0.0, start_date
    
    def select_core_pool(self) -> List[StockSelection]:
        """选择核心股票池 - 增强版强势股票筛选"""
        self.logger.info(f"开始选择核心股票池: {self.config.quarter_start} 到 {self.config.selection_end}")
        self.logger.info("筛选条件: 六周周线稳步上升 + 最近三周日线无死叉 + 单日涨幅7%+ + 周线金叉")
        
        stock_list = self.get_stock_list()
        core_pool = []
        
        # 统计筛选过程
        stats = {
            'total_checked': 0,
            'basic_filter_passed': 0,
            'six_weeks_uptrend_passed': 0,
            'no_death_cross_passed': 0,
            'weekly_golden_cross_passed': 0,
            'daily_gain_passed': 0,
            'final_selected': 0
        }
        
        for symbol in stock_list:
            try:
                stats['total_checked'] += 1
                
                # 加载数据 - 需要更多历史数据用于六周趋势分析
                extended_start = self.quarter_start - timedelta(days=90)  # 扩展到90天前
                df = self.load_stock_data(symbol, extended_start, self.selection_end)
                if df is None:
                    continue
                
                # 基本过滤
                current_price = df.loc[df.index <= self.selection_end, 'close'].iloc[-1]
                avg_volume = df.loc[df.index <= self.selection_end, 'volume'].mean()
                
                if (current_price < self.config.min_price or 
                    current_price > self.config.max_price or
                    avg_volume < self.config.min_volume):
                    continue
                
                stats['basic_filter_passed'] += 1
                
                # 新增条件1: 检查六周周线稳步上升趋势
                if not self.check_six_weeks_uptrend(df, self.selection_end):
                    continue
                
                stats['six_weeks_uptrend_passed'] += 1
                self.logger.debug(f"{symbol}: 通过六周上升趋势检查")
                
                # 新增条件2: 检查最近三周日线不能出现死叉
                if not self.check_no_daily_death_cross(df, self.selection_end):
                    continue
                
                stats['no_death_cross_passed'] += 1
                self.logger.debug(f"{symbol}: 通过三周无死叉检查")
                
                # 原有条件: 检查周线金叉
                if self.config.require_weekly_golden_cross:
                    if not self.check_weekly_golden_cross(df, self.selection_end):
                        continue
                
                stats['weekly_golden_cross_passed'] += 1
                self.logger.debug(f"{symbol}: 通过周线金叉检查")
                
                # 原有条件: 检查季度初三周内的最大涨幅
                max_gain, max_gain_date = self.find_max_daily_gain(
                    df, self.quarter_start, self.selection_end
                )
                
                if max_gain >= self.config.min_daily_gain:
                    stats['daily_gain_passed'] += 1
                    
                    selection = StockSelection(
                        symbol=symbol,
                        selection_date=self.selection_end.strftime('%Y-%m-%d'),
                        max_gain_date=max_gain_date.strftime('%Y-%m-%d'),
                        max_gain=max_gain,
                        weekly_cross_confirmed=True,
                        selection_price=current_price
                    )
                    core_pool.append(selection)
                    stats['final_selected'] += 1
                    
                    self.logger.info(f"✅ 选入核心池: {symbol}")
                    self.logger.info(f"   最大涨幅: {max_gain:.1%} (日期: {max_gain_date.strftime('%Y-%m-%d')})")
                    self.logger.info(f"   选入价格: ¥{current_price:.2f}")
                
            except Exception as e:
                self.logger.debug(f"处理股票 {symbol} 失败: {e}")
                continue
        
        # 输出筛选统计
        self.logger.info(f"\n📊 筛选统计报告:")
        self.logger.info(f"总检查股票数: {stats['total_checked']}")
        self.logger.info(f"基本条件通过: {stats['basic_filter_passed']} ({stats['basic_filter_passed']/stats['total_checked']*100:.1f}%)")
        self.logger.info(f"六周上升趋势: {stats['six_weeks_uptrend_passed']} ({stats['six_weeks_uptrend_passed']/stats['basic_filter_passed']*100:.1f}%)")
        self.logger.info(f"三周无死叉: {stats['no_death_cross_passed']} ({stats['no_death_cross_passed']/stats['six_weeks_uptrend_passed']*100:.1f}%)")
        self.logger.info(f"周线金叉确认: {stats['weekly_golden_cross_passed']} ({stats['weekly_golden_cross_passed']/stats['no_death_cross_passed']*100:.1f}%)")
        self.logger.info(f"单日涨幅7%+: {stats['daily_gain_passed']} ({stats['daily_gain_passed']/stats['weekly_golden_cross_passed']*100:.1f}%)")
        self.logger.info(f"最终选入: {stats['final_selected']} 只强势股票")
        
        return core_pool
    
    def backtest_single_stock_strategies(self, stock: StockSelection, df: pd.DataFrame) -> List[BacktestTrade]:
        """对单只股票进行智能多策略回测，选择最优策略避免长期持有"""
        backtest_df = df[(df.index >= self.backtest_start) & (df.index <= self.backtest_end)]
        if backtest_df.empty:
            return []
        
        # 预计算技术指标
        backtest_df = self._prepare_technical_indicators(backtest_df, df)
        
        strategies_results = []
        
        # 策略1: 智能止盈止损策略
        strategies_results.extend(self._smart_profit_stop_strategy(stock, backtest_df))
        
        # 策略2: 动态均线策略
        strategies_results.extend(self._dynamic_ma_strategy(stock, backtest_df))
        
        # 策略3: 技术指标组合策略
        strategies_results.extend(self._technical_combo_strategy(stock, backtest_df))
        
        # 策略4: 趋势跟踪策略
        strategies_results.extend(self._trend_following_strategy(stock, backtest_df))
        
        # 策略5: 波动率突破策略
        strategies_results.extend(self._volatility_breakout_strategy(stock, backtest_df))
        
        # 策略6: 时间止损策略（避免长期持有）
        strategies_results.extend(self._time_based_exit_strategy(stock, backtest_df))
        
        return strategies_results
    
    def _prepare_technical_indicators(self, backtest_df: pd.DataFrame, full_df: pd.DataFrame) -> pd.DataFrame:
        """预计算技术指标"""
        try:
            df = backtest_df.copy()
            
            # 移动平均线
            df['ma5'] = df['close'].rolling(window=5).mean()
            df['ma10'] = df['close'].rolling(window=10).mean()
            df['ma20'] = df['close'].rolling(window=20).mean()
            
            # RSI
            try:
                rsi_full = indicators.calculate_rsi(full_df.loc[:self.backtest_end])
                df['rsi'] = rsi_full.reindex(df.index)
            except:
                df['rsi'] = 50  # 默认值
            
            # 布林带
            df['bb_upper'] = df['close'].rolling(window=20).mean() + 2 * df['close'].rolling(window=20).std()
            df['bb_lower'] = df['close'].rolling(window=20).mean() - 2 * df['close'].rolling(window=20).std()
            df['bb_middle'] = df['close'].rolling(window=20).mean()
            
            # ATR (平均真实波幅)
            df['tr'] = np.maximum(df['high'] - df['low'], 
                                 np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                           abs(df['low'] - df['close'].shift(1))))
            df['atr'] = df['tr'].rolling(window=14).mean()
            
            # 价格变化率
            df['price_change'] = df['close'].pct_change()
            df['volatility'] = df['price_change'].rolling(window=10).std()
            
            return df
            
        except Exception as e:
            self.logger.debug(f"技术指标计算失败: {e}")
            return backtest_df
    
    def _smart_profit_stop_strategy(self, stock: StockSelection, df: pd.DataFrame) -> List[BacktestTrade]:
        """智能止盈止损策略 - 根据波动率动态调整"""
        results = []
        
        try:
            entry_date = df.index[0]
            entry_price = df.loc[entry_date, 'open']
            
            # 计算初始止损位和止盈位
            initial_atr = df.loc[entry_date:entry_date+timedelta(days=5), 'atr'].mean()
            if pd.isna(initial_atr):
                initial_atr = entry_price * 0.02  # 默认2%
            
            stop_loss = entry_price - 2 * initial_atr  # 2倍ATR止损
            take_profit = entry_price + 3 * initial_atr  # 3倍ATR止盈
            trailing_stop = stop_loss
            
            for date in df.index[1:]:
                current_price = df.loc[date, 'close']
                current_high = df.loc[date, 'high']
                current_low = df.loc[date, 'low']
                
                # 更新移动止损
                if current_price > entry_price:
                    new_trailing_stop = current_price - 2 * df.loc[date, 'atr'] if not pd.isna(df.loc[date, 'atr']) else current_price * 0.95
                    trailing_stop = max(trailing_stop, new_trailing_stop)
                
                # 检查退出条件
                exit_price = None
                exit_reason = ""
                
                if current_low <= trailing_stop:
                    exit_price = max(trailing_stop, current_low)
                    exit_reason = "移动止损"
                elif current_high >= take_profit:
                    exit_price = min(take_profit, current_high)
                    exit_reason = "止盈"
                elif (date - entry_date).days >= 30:  # 最长持有30天
                    exit_price = current_price
                    exit_reason = "时间止损"
                
                if exit_price:
                    return_rate = (exit_price - entry_price) / entry_price
                    hold_days = (date - entry_date).days
                    
                    results.append(BacktestTrade(
                        symbol=stock.symbol,
                        entry_date=entry_date.strftime('%Y-%m-%d'),
                        entry_price=entry_price,
                        exit_date=date.strftime('%Y-%m-%d'),
                        exit_price=exit_price,
                        return_rate=return_rate,
                        hold_days=hold_days,
                        strategy=f"智能止盈止损({exit_reason})"
                    ))
                    break
                    
        except Exception as e:
            self.logger.debug(f"智能止盈止损策略失败: {e}")
        
        return results
    
    def _dynamic_ma_strategy(self, stock: StockSelection, df: pd.DataFrame) -> List[BacktestTrade]:
        """动态均线策略 - 根据市场状态调整均线参数"""
        results = []
        
        try:
            entry_date = df.index[0]
            entry_price = df.loc[entry_date, 'open']
            
            for date in df.index[10:]:  # 需要足够数据计算均线
                current_price = df.loc[date, 'close']
                ma5 = df.loc[date, 'ma5']
                ma10 = df.loc[date, 'ma10']
                volatility = df.loc[date, 'volatility']
                
                # 根据波动率调整退出条件
                if pd.notna(volatility) and volatility > 0.03:  # 高波动
                    exit_threshold = 0.97  # 更严格的止损
                else:
                    exit_threshold = 0.95  # 正常止损
                
                # 退出条件
                exit_price = None
                exit_reason = ""
                
                if pd.notna(ma5) and pd.notna(ma10):
                    if current_price < ma5 * exit_threshold:
                        exit_price = current_price
                        exit_reason = "跌破MA5"
                    elif ma5 < ma10 and current_price < ma10:
                        exit_price = current_price
                        exit_reason = "均线死叉"
                
                # 时间止损
                if (date - entry_date).days >= 25:
                    exit_price = current_price
                    exit_reason = "时间止损"
                
                if exit_price:
                    return_rate = (exit_price - entry_price) / entry_price
                    hold_days = (date - entry_date).days
                    
                    results.append(BacktestTrade(
                        symbol=stock.symbol,
                        entry_date=entry_date.strftime('%Y-%m-%d'),
                        entry_price=entry_price,
                        exit_date=date.strftime('%Y-%m-%d'),
                        exit_price=exit_price,
                        return_rate=return_rate,
                        hold_days=hold_days,
                        strategy=f"动态均线({exit_reason})"
                    ))
                    break
                    
        except Exception as e:
            self.logger.debug(f"动态均线策略失败: {e}")
        
        return results
    
    def _technical_combo_strategy(self, stock: StockSelection, df: pd.DataFrame) -> List[BacktestTrade]:
        """技术指标组合策略 - RSI + 布林带 + 均线"""
        results = []
        
        try:
            entry_date = df.index[0]
            entry_price = df.loc[entry_date, 'open']
            
            for date in df.index[20:]:  # 需要足够数据
                current_price = df.loc[date, 'close']
                rsi = df.loc[date, 'rsi']
                bb_upper = df.loc[date, 'bb_upper']
                bb_lower = df.loc[date, 'bb_lower']
                ma20 = df.loc[date, 'ma20']
                
                exit_price = None
                exit_reason = ""
                
                # 多重退出信号
                if pd.notna(rsi) and rsi >= 75:  # RSI超买
                    exit_price = current_price
                    exit_reason = "RSI超买"
                elif pd.notna(bb_upper) and current_price >= bb_upper:  # 触及布林带上轨
                    exit_price = current_price
                    exit_reason = "布林带上轨"
                elif pd.notna(ma20) and current_price < ma20 * 0.95:  # 跌破20日均线5%
                    exit_price = current_price
                    exit_reason = "跌破MA20"
                elif (date - entry_date).days >= 20:  # 时间止损
                    exit_price = current_price
                    exit_reason = "时间止损"
                
                if exit_price:
                    return_rate = (exit_price - entry_price) / entry_price
                    hold_days = (date - entry_date).days
                    
                    results.append(BacktestTrade(
                        symbol=stock.symbol,
                        entry_date=entry_date.strftime('%Y-%m-%d'),
                        entry_price=entry_price,
                        exit_date=date.strftime('%Y-%m-%d'),
                        exit_price=exit_price,
                        return_rate=return_rate,
                        hold_days=hold_days,
                        strategy=f"技术组合({exit_reason})"
                    ))
                    break
                    
        except Exception as e:
            self.logger.debug(f"技术组合策略失败: {e}")
        
        return results
    
    def _trend_following_strategy(self, stock: StockSelection, df: pd.DataFrame) -> List[BacktestTrade]:
        """趋势跟踪策略 - 跟随趋势直到反转"""
        results = []
        
        try:
            entry_date = df.index[0]
            entry_price = df.loc[entry_date, 'open']
            highest_price = entry_price
            
            for date in df.index[1:]:
                current_price = df.loc[date, 'close']
                current_high = df.loc[date, 'high']
                
                # 更新最高价
                highest_price = max(highest_price, current_high)
                
                # 计算回撤
                drawdown = (highest_price - current_price) / highest_price
                
                exit_price = None
                exit_reason = ""
                
                # 回撤超过8%或时间超过15天
                if drawdown >= 0.08:
                    exit_price = current_price
                    exit_reason = "回撤止损"
                elif (date - entry_date).days >= 15:
                    exit_price = current_price
                    exit_reason = "时间止损"
                
                if exit_price:
                    return_rate = (exit_price - entry_price) / entry_price
                    hold_days = (date - entry_date).days
                    
                    results.append(BacktestTrade(
                        symbol=stock.symbol,
                        entry_date=entry_date.strftime('%Y-%m-%d'),
                        entry_price=entry_price,
                        exit_date=date.strftime('%Y-%m-%d'),
                        exit_price=exit_price,
                        return_rate=return_rate,
                        hold_days=hold_days,
                        strategy=f"趋势跟踪({exit_reason})"
                    ))
                    break
                    
        except Exception as e:
            self.logger.debug(f"趋势跟踪策略失败: {e}")
        
        return results
    
    def _volatility_breakout_strategy(self, stock: StockSelection, df: pd.DataFrame) -> List[BacktestTrade]:
        """波动率突破策略 - 基于波动率的进出场"""
        results = []
        
        try:
            entry_date = df.index[0]
            entry_price = df.loc[entry_date, 'open']
            
            for date in df.index[10:]:
                current_price = df.loc[date, 'close']
                volatility = df.loc[date, 'volatility']
                price_change = df.loc[date, 'price_change']
                
                exit_price = None
                exit_reason = ""
                
                # 基于波动率的退出
                if pd.notna(volatility) and pd.notna(price_change):
                    if volatility > 0.05 and price_change < -0.03:  # 高波动且下跌
                        exit_price = current_price
                        exit_reason = "波动率突破"
                    elif (date - entry_date).days >= 12:  # 短期持有
                        exit_price = current_price
                        exit_reason = "时间止损"
                
                if exit_price:
                    return_rate = (exit_price - entry_price) / entry_price
                    hold_days = (date - entry_date).days
                    
                    results.append(BacktestTrade(
                        symbol=stock.symbol,
                        entry_date=entry_date.strftime('%Y-%m-%d'),
                        entry_price=entry_price,
                        exit_date=date.strftime('%Y-%m-%d'),
                        exit_price=exit_price,
                        return_rate=return_rate,
                        hold_days=hold_days,
                        strategy=f"波动突破({exit_reason})"
                    ))
                    break
                    
        except Exception as e:
            self.logger.debug(f"波动突破策略失败: {e}")
        
        return results
    
    def _time_based_exit_strategy(self, stock: StockSelection, df: pd.DataFrame) -> List[BacktestTrade]:
        """时间基础退出策略 - 强制避免长期持有"""
        results = []
        
        try:
            entry_date = df.index[0]
            entry_price = df.loc[entry_date, 'open']
            
            # 多个时间节点的强制退出
            time_exits = [7, 10, 14]  # 7天、10天、14天
            
            for exit_days in time_exits:
                target_date = entry_date + timedelta(days=exit_days)
                
                # 找到最接近的交易日
                available_dates = df.index[df.index >= target_date]
                if len(available_dates) == 0:
                    continue
                    
                exit_date = available_dates[0]
                exit_price = df.loc[exit_date, 'close']
                return_rate = (exit_price - entry_price) / entry_price
                hold_days = (exit_date - entry_date).days
                
                results.append(BacktestTrade(
                    symbol=stock.symbol,
                    entry_date=entry_date.strftime('%Y-%m-%d'),
                    entry_price=entry_price,
                    exit_date=exit_date.strftime('%Y-%m-%d'),
                    exit_price=exit_price,
                    return_rate=return_rate,
                    hold_days=hold_days,
                    strategy=f"时间退出({exit_days}天)"
                ))
                
        except Exception as e:
            self.logger.debug(f"时间退出策略失败: {e}")
        
        return results
    
    def backtest_core_pool(self, core_pool: List[StockSelection]) -> List[BacktestTrade]:
        """对核心股票池进行智能回测，集成T+1交易决策"""
        self.logger.info(f"开始智能回测核心股票池: {self.config.backtest_start} 到 {self.config.backtest_end}")
        
        optimal_trades = []
        strategy_performance = {}
        
        # 初始化各种回测模块
        realistic_backtester = None
        t1_trading_system = None
        
        if REALISTIC_BACKTESTING_AVAILABLE:
            realistic_backtester = RealisticBacktester()
            self.logger.info("✅ 现实回测模块已启用")
        
        if T1_TRADING_AVAILABLE:
            t1_trading_system = T1IntelligentTradingSystem(
                initial_capital=self.config.initial_capital
            )
            self.logger.info("✅ T+1智能交易系统已启用")
        
        for stock in core_pool:
            try:
                # 加载回测期间的数据
                df = self.load_stock_data(stock.symbol, self.quarter_start, self.backtest_end)
                if df is None:
                    continue
                
                # 优先使用T+1智能交易系统
                if t1_trading_system:
                    optimal_trade = self._backtest_with_t1_system(stock, df, t1_trading_system)
                else:
                    # 回退到传统多策略回测
                    stock_trades = self.backtest_single_stock_strategies(stock, df)
                    if stock_trades:
                        optimal_trade = self._select_optimal_strategy(stock_trades)
                        
                        # 如果启用现实回测，进行多窗口验证
                        if realistic_backtester:
                            realistic_trade = self._validate_with_realistic_backtesting(
                                stock, df, optimal_trade, realistic_backtester
                            )
                            if realistic_trade:
                                optimal_trade = realistic_trade
                    else:
                        continue
                
                if optimal_trade:
                    optimal_trades.append(optimal_trade)
                    
                    # 统计策略性能
                    strategy_name = optimal_trade.strategy.split('(')[0]
                    if strategy_name not in strategy_performance:
                        strategy_performance[strategy_name] = {'count': 0, 'total_return': 0.0, 'wins': 0}
                    
                    strategy_performance[strategy_name]['count'] += 1
                    strategy_performance[strategy_name]['total_return'] += optimal_trade.return_rate
                    if optimal_trade.return_rate > 0:
                        strategy_performance[strategy_name]['wins'] += 1
                    
                    self.logger.info(f"✅ {stock.symbol}: {optimal_trade.strategy}")
                    self.logger.info(f"   收益率: {optimal_trade.return_rate:.2%}, 持有: {optimal_trade.hold_days}天")
                    if hasattr(optimal_trade, 't1_compliant') and optimal_trade.t1_compliant:
                        self.logger.info(f"   T+1合规: ✅")
                
            except Exception as e:
                self.logger.debug(f"回测股票 {stock.symbol} 失败: {e}")
                continue
        
        # 输出策略性能统计
        self._log_strategy_performance(strategy_performance)
        
        # 按收益率排序
        optimal_trades.sort(key=lambda x: x.return_rate, reverse=True)
        
        return optimal_trades
    
    def _backtest_with_t1_system(self, stock: StockSelection, df: pd.DataFrame, 
                                t1_system: 'T1IntelligentTradingSystem') -> Optional[BacktestTrade]:
        """使用T+1智能交易系统进行回测"""
        try:
            backtest_df = df[(df.index >= self.backtest_start) & (df.index <= self.backtest_end)]
            if backtest_df.empty:
                return None
            
            # 模拟T+1交易过程
            entry_signal = None
            exit_signal = None
            current_position = None
            
            # 遍历回测期间的每一天
            for current_date in backtest_df.index:
                # 更新持仓状态
                current_prices = {stock.symbol: backtest_df.loc[current_date, 'close']}
                t1_system.update_positions(current_date, current_prices)
                
                # 生成交易信号
                signal = t1_system.generate_trading_signal(stock.symbol, df, current_date)
                
                if signal:
                    if signal.action == TradingAction.BUY and not current_position:
                        # 买入信号
                        entry_signal = signal
                        current_position = {
                            'symbol': stock.symbol,
                            'entry_date': current_date,
                            'entry_price': signal.price,
                            'can_sell': False  # T+1规则
                        }
                        
                    elif signal.action == TradingAction.SELL and current_position:
                        # 卖出信号 - 检查T+1规则
                        if current_date > current_position['entry_date']:  # 次日才能卖出
                            exit_signal = signal
                            break
                    
                    # 更新持仓的可售状态
                    if current_position and current_date > current_position['entry_date']:
                        current_position['can_sell'] = True
            
            # 如果有完整的买卖信号，创建交易记录
            if entry_signal and exit_signal:
                entry_date = datetime.strptime(entry_signal.date, '%Y-%m-%d')
                exit_date = datetime.strptime(exit_signal.date, '%Y-%m-%d')
                
                return_rate = (exit_signal.price - entry_signal.price) / entry_signal.price
                hold_days = (exit_date - entry_date).days
                
                return BacktestTrade(
                    symbol=stock.symbol,
                    entry_date=entry_signal.date,
                    entry_price=entry_signal.price,
                    exit_date=exit_signal.date,
                    exit_price=exit_signal.price,
                    return_rate=return_rate,
                    hold_days=hold_days,
                    strategy=f"T+1智能交易({exit_signal.reason})",
                    trading_action=f"{entry_signal.action.value}→{exit_signal.action.value}",
                    trend_expectation=entry_signal.trend_expectation.value,
                    confidence=(entry_signal.confidence + exit_signal.confidence) / 2,
                    t1_compliant=True
                )
            
            # 如果只有买入信号，按期末价格计算
            elif entry_signal and current_position:
                exit_date = backtest_df.index[-1]
                exit_price = backtest_df.loc[exit_date, 'close']
                entry_date = datetime.strptime(entry_signal.date, '%Y-%m-%d')
                
                return_rate = (exit_price - entry_signal.price) / entry_signal.price
                hold_days = (exit_date - entry_date).days
                
                return BacktestTrade(
                    symbol=stock.symbol,
                    entry_date=entry_signal.date,
                    entry_price=entry_signal.price,
                    exit_date=exit_date.strftime('%Y-%m-%d'),
                    exit_price=exit_price,
                    return_rate=return_rate,
                    hold_days=hold_days,
                    strategy="T+1智能交易(持有至期末)",
                    trading_action=f"{entry_signal.action.value}→持有",
                    trend_expectation=entry_signal.trend_expectation.value,
                    confidence=entry_signal.confidence,
                    t1_compliant=True
                )
            
            return None
            
        except Exception as e:
            self.logger.debug(f"T+1系统回测失败 {stock.symbol}: {e}")
            return None
    
    def _validate_with_realistic_backtesting(self, stock: StockSelection, df: pd.DataFrame, 
                                           optimal_trade: BacktestTrade, 
                                           realistic_backtester: 'RealisticBacktester') -> BacktestTrade:
        """使用现实回测验证最优策略"""
        try:
            # 转换日期
            signal_date = datetime.strptime(optimal_trade.entry_date, '%Y-%m-%d')
            exit_signal_date = datetime.strptime(optimal_trade.exit_date, '%Y-%m-%d')
            
            # 进行多窗口现实回测
            realistic_trades = realistic_backtester.backtest_with_windows(
                stock.symbol, df, signal_date, exit_signal_date, optimal_trade.strategy
            )
            
            if realistic_trades:
                # 选择最优窗口
                optimal_realistic_trade = realistic_backtester.select_optimal_window(realistic_trades)
                
                # 转换为标准BacktestTrade格式
                validated_trade = BacktestTrade(
                    symbol=stock.symbol,
                    entry_date=optimal_realistic_trade.entry_date,
                    entry_price=optimal_realistic_trade.entry_price,
                    exit_date=optimal_realistic_trade.exit_date,
                    exit_price=optimal_realistic_trade.exit_price,
                    return_rate=optimal_realistic_trade.net_return_rate,  # 使用净收益率
                    hold_days=optimal_realistic_trade.hold_days,
                    strategy=f"{optimal_trade.strategy}_现实验证"
                )
                
                # 记录现实回测的额外信息
                self.logger.debug(f"{stock.symbol} 现实回测结果:")
                self.logger.debug(f"  理论收益: {optimal_trade.return_rate:.2%}")
                self.logger.debug(f"  实际净收益: {optimal_realistic_trade.net_return_rate:.2%}")
                self.logger.debug(f"  总滑点: {abs(optimal_realistic_trade.entry_slippage) + abs(optimal_realistic_trade.exit_slippage):.3%}")
                self.logger.debug(f"  执行质量: {optimal_realistic_trade.execution_quality:.2f}")
                
                return validated_trade
            
        except Exception as e:
            self.logger.debug(f"现实回测验证失败 {stock.symbol}: {e}")
        
        # 如果现实回测失败，返回原始交易
        return optimal_trade
    
    def _select_optimal_strategy(self, trades: List[BacktestTrade]) -> BacktestTrade:
        """选择最优策略 - 综合考虑收益率、持有时间和风险"""
        if not trades:
            return None
        
        if len(trades) == 1:
            return trades[0]
        
        # 计算每个策略的综合评分
        scored_trades = []
        
        for trade in trades:
            # 基础收益率评分 (40%)
            return_score = trade.return_rate * 0.4
            
            # 时间效率评分 (30%) - 持有时间越短越好
            max_days = max(t.hold_days for t in trades)
            time_score = (1 - trade.hold_days / max_days) * 0.3 if max_days > 0 else 0
            
            # 风险调整评分 (30%) - 避免过度风险
            risk_penalty = 0
            if trade.return_rate < -0.1:  # 亏损超过10%的惩罚
                risk_penalty = -0.1
            elif trade.hold_days > 20:  # 持有超过20天的惩罚
                risk_penalty = -0.05
            
            risk_score = 0.3 + risk_penalty
            
            # 综合评分
            total_score = return_score + time_score + risk_score
            
            scored_trades.append((trade, total_score))
        
        # 选择评分最高的策略
        optimal_trade = max(scored_trades, key=lambda x: x[1])[0]
        
        return optimal_trade
    
    def _log_strategy_performance(self, performance: Dict):
        """输出策略性能统计"""
        if not performance:
            return
        
        self.logger.info(f"\n📊 策略性能统计:")
        self.logger.info("-" * 50)
        
        for strategy, stats in sorted(performance.items(), key=lambda x: x[1]['total_return'], reverse=True):
            avg_return = stats['total_return'] / stats['count'] if stats['count'] > 0 else 0
            win_rate = stats['wins'] / stats['count'] if stats['count'] > 0 else 0
            
            self.logger.info(f"{strategy}:")
            self.logger.info(f"  使用次数: {stats['count']}")
            self.logger.info(f"  平均收益: {avg_return:.2%}")
            self.logger.info(f"  胜率: {win_rate:.1%}")
            self.logger.info(f"  总收益: {stats['total_return']:.2%}")
            self.logger.info("")
    
    def generate_strategy_summary(self, core_pool: List[StockSelection], trades: List[BacktestTrade]) -> Dict:
        """生成策略摘要"""
        if not trades:
            return {
                "total_stocks": len(core_pool),
                "traded_stocks": 0,
                "avg_return": 0.0,
                "win_rate": 0.0,
                "total_return": 0.0,
                "best_trade": None,
                "worst_trade": None
            }
        
        returns = [trade.return_rate for trade in trades]
        winning_trades = [trade for trade in trades if trade.return_rate > 0]
        
        best_trade = max(trades, key=lambda x: x.return_rate)
        worst_trade = min(trades, key=lambda x: x.return_rate)
        
        return {
            "total_stocks": len(core_pool),
            "traded_stocks": len(trades),
            "avg_return": np.mean(returns),
            "win_rate": len(winning_trades) / len(trades),
            "total_return": sum(returns) / len(core_pool),  # 平均到所有选中的股票
            "best_trade": {
                "symbol": best_trade.symbol,
                "return": best_trade.return_rate,
                "entry_date": best_trade.entry_date
            },
            "worst_trade": {
                "symbol": worst_trade.symbol,
                "return": worst_trade.return_rate,
                "entry_date": worst_trade.entry_date
            }
        }
    
    def calculate_performance_metrics(self, trades: List[BacktestTrade]) -> Dict:
        """计算性能指标"""
        if not trades:
            return {
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "volatility": 0.0,
                "avg_hold_days": 0.0
            }
        
        returns = np.array([trade.return_rate for trade in trades])
        hold_days = [trade.hold_days for trade in trades]
        
        # 计算夏普比率（简化版本）
        sharpe_ratio = np.mean(returns) / np.std(returns) if np.std(returns) > 0 else 0
        
        # 计算最大回撤（简化版本）
        cumulative_returns = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = np.min(drawdown)
        
        return {
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "volatility": np.std(returns),
            "avg_hold_days": np.mean(hold_days)
        }
    
    def run_quarterly_backtest(self) -> QuarterlyStrategy:
        """运行季度回测"""
        self.logger.info(f"开始 {self.config.current_quarter} 季度回测")
        
        # 第一步：选择核心股票池
        core_pool = self.select_core_pool()
        
        # 第二步：回测核心股票池
        trades = self.backtest_core_pool(core_pool)
        
        # 第三步：生成策略摘要
        strategy_summary = self.generate_strategy_summary(core_pool, trades)
        
        # 第四步：计算性能指标
        performance_metrics = self.calculate_performance_metrics(trades)
        
        # 第五步：生成季度策略
        quarterly_strategy = QuarterlyStrategy(
            quarter=self.config.current_quarter,
            core_pool=core_pool,
            recommended_trades=trades,
            strategy_summary=strategy_summary,
            performance_metrics=performance_metrics
        )
        
        return quarterly_strategy
    
    def save_results(self, strategy: QuarterlyStrategy, filename: str = None) -> str:
        """保存结果"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'precise_quarterly_strategy_{self.config.current_quarter}_{timestamp}.json'
        
        # 转换为可序列化的格式
        result = {
            "config": asdict(self.config),
            "strategy": asdict(strategy)
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)
        
        self.logger.info(f"结果已保存到: {filename}")
        return filename

def create_historical_config(quarter: str) -> PreciseQuarterlyConfig:
    """创建历史季度配置"""
    if quarter == "2025Q2":
        return PreciseQuarterlyConfig(
            current_quarter="2025Q2",
            quarter_start="2025-04-01",
            selection_end="2025-04-18",
            backtest_start="2025-04-21",
            backtest_end="2025-06-30",
        )
    elif quarter == "2025Q3":
        return PreciseQuarterlyConfig(
            current_quarter="2025Q3",
            quarter_start="2025-07-01",
            selection_end="2025-07-18",
            backtest_start="2025-07-21",
            backtest_end="2025-07-24",
        )
    else:
        raise ValueError(f"不支持的季度: {quarter}")

def print_strategy_report(strategy: QuarterlyStrategy):
    """打印策略报告 - 增强版支持T+1信息"""
    print(f"\n{'='*60}")
    print(f"📊 {strategy.quarter} 季度操作策略报告")
    print(f"{'='*60}")
    
    # 核心股票池
    print(f"\n🎯 核心股票池 ({len(strategy.core_pool)} 只)")
    print("-" * 60)
    for i, stock in enumerate(strategy.core_pool, 1):
        print(f"{i:2d}. {stock.symbol}")
        print(f"    选入日期: {stock.selection_date}")
        print(f"    最大涨幅: {stock.max_gain:.1%} (日期: {stock.max_gain_date})")
        print(f"    选入价格: ¥{stock.selection_price:.2f}")
        print(f"    周线金叉: {'✓' if stock.weekly_cross_confirmed else '✗'}")
    
    # 回测交易
    if strategy.recommended_trades:
        print(f"\n📈 回测交易记录 ({len(strategy.recommended_trades)} 笔)")
        print("-" * 60)
        
        # 统计T+1相关信息
        t1_trades = [t for t in strategy.recommended_trades if hasattr(t, 't1_compliant') and t.t1_compliant]
        traditional_trades = [t for t in strategy.recommended_trades if not (hasattr(t, 't1_compliant') and t.t1_compliant)]
        
        if t1_trades:
            print(f"\n🔥 T+1智能交易 ({len(t1_trades)} 笔)")
            print("-" * 40)
            for i, trade in enumerate(t1_trades, 1):
                print(f"{i:2d}. {trade.symbol} - {trade.strategy}")
                print(f"    交易动作: {trade.trading_action}")
                print(f"    走势预期: {trade.trend_expectation}")
                print(f"    买入: {trade.entry_date} ¥{trade.entry_price:.2f}")
                print(f"    卖出: {trade.exit_date} ¥{trade.exit_price:.2f}")
                print(f"    收益率: {trade.return_rate:.2%}")
                print(f"    持有天数: {trade.hold_days} 天")
                print(f"    信号置信度: {trade.confidence:.2f}")
                print(f"    T+1合规: {'✅' if trade.t1_compliant else '❌'}")
                print()
        
        if traditional_trades:
            print(f"\n📊 传统策略交易 ({len(traditional_trades)} 笔)")
            print("-" * 40)
            for i, trade in enumerate(traditional_trades, 1):
                print(f"{i:2d}. {trade.symbol} - {trade.strategy}")
                print(f"    买入: {trade.entry_date} ¥{trade.entry_price:.2f}")
                print(f"    卖出: {trade.exit_date} ¥{trade.exit_price:.2f}")
                print(f"    收益率: {trade.return_rate:.2%}")
                print(f"    持有天数: {trade.hold_days} 天")
                print()
    
    # 策略摘要
    summary = strategy.strategy_summary
    print(f"\n📋 策略摘要")
    print("-" * 60)
    print(f"总选股数量: {summary['total_stocks']}")
    print(f"实际交易数量: {summary['traded_stocks']}")
    print(f"平均收益率: {summary['avg_return']:.2%}")
    print(f"胜率: {summary['win_rate']:.1%}")
    print(f"总体收益率: {summary['total_return']:.2%}")
    
    if summary['best_trade']:
        print(f"最佳交易: {summary['best_trade']['symbol']} ({summary['best_trade']['return']:.2%})")
    if summary['worst_trade']:
        print(f"最差交易: {summary['worst_trade']['symbol']} ({summary['worst_trade']['return']:.2%})")
    
    # 性能指标
    metrics = strategy.performance_metrics
    print(f"\n📊 性能指标")
    print("-" * 60)
    print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
    print(f"最大回撤: {metrics['max_drawdown']:.2%}")
    print(f"收益波动率: {metrics['volatility']:.2%}")
    print(f"平均持有天数: {metrics['avg_hold_days']:.1f} 天")

def main():
    """主函数"""
    print("🎯 精确季度回测系统")
    print("=" * 50)
    
    # 当前季度回测
    print("\n📅 当前季度 (2025Q3) 回测")
    current_config = PreciseQuarterlyConfig()
    current_backtester = PreciseQuarterlyBacktester(current_config)
    current_strategy = current_backtester.run_quarterly_backtest()
    
    print_strategy_report(current_strategy)
    current_file = current_backtester.save_results(current_strategy)
    
    # 历史季度回测
    print(f"\n{'='*50}")
    print("\n📅 历史季度 (2025Q2) 回测")
    historical_config = create_historical_config("2025Q2")
    historical_backtester = PreciseQuarterlyBacktester(historical_config)
    historical_strategy = historical_backtester.run_quarterly_backtest()
    
    print_strategy_report(historical_strategy)
    historical_file = historical_backtester.save_results(historical_strategy)
    
    print(f"\n🎉 回测完成！")
    print(f"当前季度结果: {current_file}")
    print(f"历史季度结果: {historical_file}")

if __name__ == "__main__":
    main()