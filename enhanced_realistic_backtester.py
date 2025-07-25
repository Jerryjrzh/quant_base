#!/usr/bin/env python3
"""
增强现实回测系统
验证不同买入卖出窗口，模拟实际操作保证收益率准确性

核心功能：
1. 多时间窗口买入验证
2. 实际滑点和手续费模拟
3. 流动性约束考虑
4. 分批买入卖出策略
5. 市场冲击成本计算
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, NamedTuple
import json
import logging
from dataclasses import dataclass, asdict
from enum import Enum

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append('backend')

import data_loader
import strategies
import indicators

class OrderType(Enum):
    """订单类型"""
    MARKET = "市价单"
    LIMIT = "限价单"
    STOP = "止损单"

class ExecutionWindow(Enum):
    """执行时间窗口"""
    OPEN = "开盘"
    CLOSE = "收盘"
    INTRADAY = "盘中"
    VWAP = "成交量加权平均价"

@dataclass
class TradingWindow:
    """交易窗口配置"""
    entry_window: ExecutionWindow = ExecutionWindow.OPEN
    exit_window: ExecutionWindow = ExecutionWindow.CLOSE
    entry_delay_days: int = 0  # 买入延迟天数
    exit_delay_days: int = 0   # 卖出延迟天数
    batch_size: float = 1.0    # 批次大小（1.0表示一次性买入）
    max_volume_ratio: float = 0.1  # 最大成交量占比

@dataclass
class MarketImpact:
    """市场冲击成本"""
    linear_cost: float = 0.001    # 线性成本
    sqrt_cost: float = 0.0005     # 平方根成本
    fixed_cost: float = 0.0002    # 固定成本
    bid_ask_spread: float = 0.002 # 买卖价差

@dataclass
class RealisticTrade:
    """现实交易记录"""
    symbol: str
    strategy: str
    
    # 买入信息
    signal_date: str          # 信号产生日期
    entry_date: str           # 实际买入日期
    entry_price: float        # 实际买入价格
    target_entry_price: float # 目标买入价格
    entry_slippage: float     # 买入滑点
    
    # 卖出信息
    exit_signal_date: str     # 卖出信号日期
    exit_date: str            # 实际卖出日期
    exit_price: float         # 实际卖出价格
    target_exit_price: float  # 目标卖出价格
    exit_slippage: float      # 卖出滑点
    
    # 成本和收益
    commission_cost: float    # 手续费
    market_impact_cost: float # 市场冲击成本
    net_return_rate: float    # 净收益率
    gross_return_rate: float  # 毛收益率
    hold_days: int            # 持有天数
    
    # 执行质量
    execution_quality: float  # 执行质量评分
    liquidity_score: float    # 流动性评分

class RealisticBacktester:
    """现实回测器"""
    
    def __init__(self, trading_windows: List[TradingWindow] = None, 
                 market_impact: MarketImpact = None):
        self.trading_windows = trading_windows or self._default_trading_windows()
        self.market_impact = market_impact or MarketImpact()
        self.logger = self._setup_logger()
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger('RealisticBacktester')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def _default_trading_windows(self) -> List[TradingWindow]:
        """默认交易窗口配置"""
        return [
            # 理想情况：开盘买入，收盘卖出
            TradingWindow(ExecutionWindow.OPEN, ExecutionWindow.CLOSE, 0, 0, 1.0, 0.1),
            
            # 现实情况1：次日开盘买入，当日收盘卖出
            TradingWindow(ExecutionWindow.OPEN, ExecutionWindow.CLOSE, 1, 0, 1.0, 0.1),
            
            # 现实情况2：当日收盘买入，次日开盘卖出
            TradingWindow(ExecutionWindow.CLOSE, ExecutionWindow.OPEN, 0, 1, 1.0, 0.1),
            
            # 保守情况：次日开盘买入，次日收盘卖出
            TradingWindow(ExecutionWindow.OPEN, ExecutionWindow.CLOSE, 1, 1, 1.0, 0.1),
            
            # 分批买入：VWAP买入，收盘卖出
            TradingWindow(ExecutionWindow.VWAP, ExecutionWindow.CLOSE, 0, 0, 0.5, 0.05),
            
            # 谨慎操作：延迟2天买入，延迟1天卖出
            TradingWindow(ExecutionWindow.OPEN, ExecutionWindow.CLOSE, 2, 1, 1.0, 0.1),
        ]
    
    def calculate_execution_price(self, df: pd.DataFrame, date: datetime, 
                                window: ExecutionWindow, volume_ratio: float) -> Tuple[float, float]:
        """计算执行价格和滑点"""
        try:
            if date not in df.index:
                # 找到最近的交易日
                available_dates = df.index[df.index >= date]
                if len(available_dates) == 0:
                    return None, 0.0
                date = available_dates[0]
            
            row = df.loc[date]
            
            if window == ExecutionWindow.OPEN:
                base_price = row['open']
            elif window == ExecutionWindow.CLOSE:
                base_price = row['close']
            elif window == ExecutionWindow.VWAP:
                # 简化的VWAP计算
                base_price = (row['high'] + row['low'] + 2 * row['close']) / 4
            else:  # INTRADAY
                base_price = (row['high'] + row['low']) / 2
            
            # 计算滑点
            slippage = self._calculate_slippage(row, volume_ratio)
            execution_price = base_price * (1 + slippage)
            
            return execution_price, slippage
            
        except Exception as e:
            self.logger.debug(f"计算执行价格失败: {e}")
            return None, 0.0
    
    def _calculate_slippage(self, row: pd.Series, volume_ratio: float) -> float:
        """计算滑点"""
        # 基础滑点（买卖价差的一半）
        base_slippage = self.market_impact.bid_ask_spread / 2
        
        # 市场冲击成本
        impact_cost = (self.market_impact.linear_cost * volume_ratio + 
                      self.market_impact.sqrt_cost * np.sqrt(volume_ratio) +
                      self.market_impact.fixed_cost)
        
        # 波动率调整
        try:
            volatility = abs(row['high'] - row['low']) / row['close']
            volatility_adjustment = min(volatility * 0.5, 0.01)  # 最大1%
        except:
            volatility_adjustment = 0.001
        
        total_slippage = base_slippage + impact_cost + volatility_adjustment
        return min(total_slippage, 0.05)  # 最大滑点5%
    
    def _calculate_commission(self, trade_value: float) -> float:
        """计算手续费"""
        # 简化的手续费计算：万分之五，最低5元
        commission_rate = 0.0005
        min_commission = 5.0
        
        commission = max(trade_value * commission_rate, min_commission)
        return commission
    
    def _calculate_liquidity_score(self, df: pd.DataFrame, date: datetime, 
                                 volume_ratio: float) -> float:
        """计算流动性评分"""
        try:
            if date not in df.index:
                return 0.5  # 默认评分
            
            row = df.loc[date]
            
            # 成交量评分
            recent_volume = df.loc[:date, 'volume'].tail(10).mean()
            volume_score = min(row['volume'] / recent_volume, 2.0) / 2.0
            
            # 价格稳定性评分
            price_range = (row['high'] - row['low']) / row['close']
            stability_score = max(0, 1 - price_range * 10)
            
            # 成交量占比评分
            volume_impact_score = max(0, 1 - volume_ratio * 5)
            
            # 综合评分
            liquidity_score = (volume_score * 0.4 + 
                             stability_score * 0.3 + 
                             volume_impact_score * 0.3)
            
            return min(max(liquidity_score, 0.0), 1.0)
            
        except Exception as e:
            self.logger.debug(f"流动性评分计算失败: {e}")
            return 0.5
    
    def backtest_with_windows(self, symbol: str, df: pd.DataFrame, 
                            signal_date: datetime, exit_signal_date: datetime,
                            strategy_name: str) -> List[RealisticTrade]:
        """使用不同交易窗口进行回测"""
        results = []
        
        for i, window in enumerate(self.trading_windows):
            try:
                trade = self._simulate_trade_with_window(
                    symbol, df, signal_date, exit_signal_date, 
                    strategy_name, window, i
                )
                if trade:
                    results.append(trade)
                    
            except Exception as e:
                self.logger.debug(f"窗口 {i} 回测失败: {e}")
                continue
        
        return results
    
    def _simulate_trade_with_window(self, symbol: str, df: pd.DataFrame,
                                  signal_date: datetime, exit_signal_date: datetime,
                                  strategy_name: str, window: TradingWindow,
                                  window_id: int) -> Optional[RealisticTrade]:
        """模拟单个交易窗口的交易"""
        
        # 计算实际买入日期
        entry_date = signal_date + timedelta(days=window.entry_delay_days)
        
        # 计算实际卖出日期
        exit_date = exit_signal_date + timedelta(days=window.exit_delay_days)
        
        # 确保有足够的数据
        if entry_date >= exit_date or exit_date not in df.index:
            return None
        
        # 计算买入价格和滑点
        entry_price, entry_slippage = self.calculate_execution_price(
            df, entry_date, window.entry_window, window.max_volume_ratio
        )
        
        if entry_price is None:
            return None
        
        # 计算目标买入价格（无滑点）
        target_entry_price = entry_price / (1 + entry_slippage)
        
        # 计算卖出价格和滑点
        exit_price, exit_slippage = self.calculate_execution_price(
            df, exit_date, window.exit_window, window.max_volume_ratio
        )
        
        if exit_price is None:
            return None
        
        # 计算目标卖出价格（无滑点）
        target_exit_price = exit_price / (1 - exit_slippage)  # 卖出时滑点为负
        
        # 计算交易成本
        trade_value = 10000  # 假设交易金额
        commission_cost = self._calculate_commission(trade_value)
        
        # 市场冲击成本
        market_impact_cost = (abs(entry_slippage) + abs(exit_slippage)) * trade_value
        
        # 计算收益率
        gross_return_rate = (exit_price - entry_price) / entry_price
        total_cost_rate = (commission_cost + market_impact_cost) / trade_value
        net_return_rate = gross_return_rate - total_cost_rate
        
        # 计算持有天数
        hold_days = (exit_date - entry_date).days
        
        # 计算执行质量评分
        execution_quality = self._calculate_execution_quality(
            entry_slippage, exit_slippage, hold_days
        )
        
        # 计算流动性评分
        liquidity_score = (
            self._calculate_liquidity_score(df, entry_date, window.max_volume_ratio) +
            self._calculate_liquidity_score(df, exit_date, window.max_volume_ratio)
        ) / 2
        
        return RealisticTrade(
            symbol=symbol,
            strategy=f"{strategy_name}_窗口{window_id}",
            signal_date=signal_date.strftime('%Y-%m-%d'),
            entry_date=entry_date.strftime('%Y-%m-%d'),
            entry_price=entry_price,
            target_entry_price=target_entry_price,
            entry_slippage=entry_slippage,
            exit_signal_date=exit_signal_date.strftime('%Y-%m-%d'),
            exit_date=exit_date.strftime('%Y-%m-%d'),
            exit_price=exit_price,
            target_exit_price=target_exit_price,
            exit_slippage=exit_slippage,
            commission_cost=commission_cost,
            market_impact_cost=market_impact_cost,
            net_return_rate=net_return_rate,
            gross_return_rate=gross_return_rate,
            hold_days=hold_days,
            execution_quality=execution_quality,
            liquidity_score=liquidity_score
        )
    
    def _calculate_execution_quality(self, entry_slippage: float, 
                                   exit_slippage: float, hold_days: int) -> float:
        """计算执行质量评分"""
        # 滑点评分（滑点越小评分越高）
        slippage_score = max(0, 1 - (abs(entry_slippage) + abs(exit_slippage)) * 50)
        
        # 时间效率评分
        time_score = max(0, 1 - hold_days / 30)
        
        # 综合评分
        execution_quality = slippage_score * 0.6 + time_score * 0.4
        
        return min(max(execution_quality, 0.0), 1.0)
    
    def select_optimal_window(self, trades: List[RealisticTrade]) -> RealisticTrade:
        """选择最优交易窗口"""
        if not trades:
            return None
        
        if len(trades) == 1:
            return trades[0]
        
        # 计算每个窗口的综合评分
        scored_trades = []
        
        for trade in trades:
            # 净收益率评分 (40%)
            return_score = trade.net_return_rate * 0.4
            
            # 执行质量评分 (30%)
            quality_score = trade.execution_quality * 0.3
            
            # 流动性评分 (20%)
            liquidity_score = trade.liquidity_score * 0.2
            
            # 时间效率评分 (10%)
            time_score = max(0, 1 - trade.hold_days / 30) * 0.1
            
            # 综合评分
            total_score = return_score + quality_score + liquidity_score + time_score
            
            scored_trades.append((trade, total_score))
        
        # 选择评分最高的窗口
        optimal_trade = max(scored_trades, key=lambda x: x[1])[0]
        
        return optimal_trade
    
    def analyze_window_performance(self, all_trades: List[List[RealisticTrade]]) -> Dict:
        """分析不同窗口的性能"""
        window_stats = {}
        
        for window_id in range(len(self.trading_windows)):
            window_trades = []
            for trades in all_trades:
                for trade in trades:
                    if f"窗口{window_id}" in trade.strategy:
                        window_trades.append(trade)
            
            if window_trades:
                avg_net_return = np.mean([t.net_return_rate for t in window_trades])
                avg_gross_return = np.mean([t.gross_return_rate for t in window_trades])
                avg_slippage = np.mean([abs(t.entry_slippage) + abs(t.exit_slippage) for t in window_trades])
                avg_execution_quality = np.mean([t.execution_quality for t in window_trades])
                avg_liquidity = np.mean([t.liquidity_score for t in window_trades])
                win_rate = len([t for t in window_trades if t.net_return_rate > 0]) / len(window_trades)
                
                window_stats[f"窗口{window_id}"] = {
                    "交易数量": len(window_trades),
                    "平均净收益": avg_net_return,
                    "平均毛收益": avg_gross_return,
                    "平均滑点": avg_slippage,
                    "执行质量": avg_execution_quality,
                    "流动性评分": avg_liquidity,
                    "胜率": win_rate,
                    "窗口配置": self.trading_windows[window_id]
                }
        
        return window_stats

def demo_realistic_backtesting():
    """演示现实回测功能"""
    print("🎯 现实回测系统演示")
    print("=" * 60)
    
    # 创建回测器
    backtester = RealisticBacktester()
    
    # 模拟股票数据
    dates = pd.date_range(start='2025-07-01', periods=30, freq='D')
    np.random.seed(42)
    
    base_price = 10.0
    prices = [base_price]
    volumes = []
    
    for i in range(29):
        # 模拟价格变化
        change = np.random.normal(0.01, 0.02)
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, prices[-1] * 0.95))
        
        # 模拟成交量
        volume = np.random.randint(1000000, 5000000)
        volumes.append(volume)
    
    volumes.append(volumes[-1])  # 最后一天的成交量
    
    # 创建DataFrame
    df = pd.DataFrame({
        'open': [p * (1 + np.random.normal(0, 0.005)) for p in prices],
        'high': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        'low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        'close': prices,
        'volume': volumes
    }, index=dates)
    
    # 模拟交易信号
    signal_date = dates[5]
    exit_signal_date = dates[15]
    
    print(f"📊 模拟交易:")
    print(f"  股票代码: TEST001")
    print(f"  买入信号: {signal_date.strftime('%Y-%m-%d')}")
    print(f"  卖出信号: {exit_signal_date.strftime('%Y-%m-%d')}")
    print(f"  信号价格: ¥{df.loc[signal_date, 'close']:.2f} → ¥{df.loc[exit_signal_date, 'close']:.2f}")
    
    # 执行多窗口回测
    trades = backtester.backtest_with_windows(
        "TEST001", df, signal_date, exit_signal_date, "测试策略"
    )
    
    print(f"\n📈 不同窗口回测结果:")
    print("-" * 80)
    
    for i, trade in enumerate(trades):
        print(f"窗口{i}: {backtester.trading_windows[i].entry_window.value}买入 → {backtester.trading_windows[i].exit_window.value}卖出")
        print(f"  延迟: 买入+{backtester.trading_windows[i].entry_delay_days}天, 卖出+{backtester.trading_windows[i].exit_delay_days}天")
        print(f"  实际交易: {trade.entry_date} ¥{trade.entry_price:.3f} → {trade.exit_date} ¥{trade.exit_price:.3f}")
        print(f"  毛收益率: {trade.gross_return_rate:.2%}")
        print(f"  净收益率: {trade.net_return_rate:.2%}")
        print(f"  总滑点: {abs(trade.entry_slippage) + abs(trade.exit_slippage):.3%}")
        print(f"  执行质量: {trade.execution_quality:.2f}")
        print(f"  流动性评分: {trade.liquidity_score:.2f}")
        print()
    
    # 选择最优窗口
    optimal_trade = backtester.select_optimal_window(trades)
    
    print(f"🏆 最优交易窗口:")
    print(f"  策略: {optimal_trade.strategy}")
    print(f"  净收益率: {optimal_trade.net_return_rate:.2%}")
    print(f"  执行质量: {optimal_trade.execution_quality:.2f}")
    print(f"  持有天数: {optimal_trade.hold_days}天")
    
    # 分析窗口性能
    window_stats = backtester.analyze_window_performance([trades])
    
    print(f"\n📊 窗口性能分析:")
    print("-" * 60)
    
    for window_name, stats in window_stats.items():
        print(f"{window_name}:")
        print(f"  平均净收益: {stats['平均净收益']:.2%}")
        print(f"  平均滑点: {stats['平均滑点']:.3%}")
        print(f"  执行质量: {stats['执行质量']:.2f}")
        print(f"  流动性评分: {stats['流动性评分']:.2f}")
        print()

if __name__ == "__main__":
    demo_realistic_backtesting()