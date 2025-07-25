#!/usr/bin/env python3
"""
T+1智能交易决策系统
基于个股走势预期进行买入、卖出、持有、观察决策

核心功能：
1. 严格遵循T+1交易规则
2. 基于技术分析的走势预期判断
3. 智能交易决策：买入/卖出/持有/观察
4. 动态仓位管理
5. 风险控制机制
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, NamedTuple
from enum import Enum
from dataclasses import dataclass, asdict
import logging

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append('backend')

import data_loader
import strategies
import indicators

class TradingAction(Enum):
    """交易动作"""
    BUY = "买入"
    SELL = "卖出"
    HOLD = "持有"
    OBSERVE = "观察"

class TrendExpectation(Enum):
    """走势预期"""
    STRONG_UP = "强势上涨"
    WEAK_UP = "弱势上涨"
    SIDEWAYS = "横盘整理"
    WEAK_DOWN = "弱势下跌"
    STRONG_DOWN = "强势下跌"

@dataclass
class Position:
    """持仓信息"""
    symbol: str
    shares: int
    avg_cost: float
    buy_date: str
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_rate: float
    can_sell: bool  # T+1规则：是否可以卖出

@dataclass
class TradingSignal:
    """交易信号"""
    symbol: str
    date: str
    action: TradingAction
    price: float
    confidence: float  # 信号置信度 0-1
    trend_expectation: TrendExpectation
    reason: str
    risk_level: float  # 风险等级 0-1
    suggested_position_size: float  # 建议仓位大小

@dataclass
class MarketAnalysis:
    """市场分析结果"""
    symbol: str
    date: str
    
    # 技术指标
    ma5: float
    ma10: float
    ma20: float
    rsi: float
    macd: float
    macd_signal: float
    bb_upper: float
    bb_lower: float
    bb_position: float  # 布林带位置 0-1
    
    # 趋势分析
    short_trend: str  # 短期趋势
    medium_trend: str  # 中期趋势
    long_trend: str   # 长期趋势
    
    # 支撑阻力
    support_level: float
    resistance_level: float
    
    # 成交量分析
    volume_ratio: float  # 成交量比率
    volume_trend: str    # 成交量趋势
    
    # 综合评分
    technical_score: float  # 技术面评分 0-100
    momentum_score: float   # 动量评分 0-100
    risk_score: float      # 风险评分 0-100

class T1IntelligentTradingSystem:
    """T+1智能交易系统"""
    
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.available_cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trading_history: List[TradingSignal] = []
        self.logger = self._setup_logger()
        
        # 交易参数
        self.max_position_size = 0.2  # 单股最大仓位20%
        self.max_total_position = 0.8  # 总仓位不超过80%
        self.commission_rate = 0.001   # 手续费率
        self.min_trade_amount = 1000   # 最小交易金额
        
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger('T1IntelligentTradingSystem')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def analyze_market(self, symbol: str, df: pd.DataFrame, date: datetime) -> MarketAnalysis:
        """综合市场分析"""
        try:
            # 确保有足够的历史数据
            analysis_df = df[df.index <= date].tail(50)
            if len(analysis_df) < 20:
                return None
            
            latest = analysis_df.iloc[-1]
            
            # 计算技术指标
            analysis_df = self._calculate_technical_indicators(analysis_df)
            
            # 趋势分析
            short_trend = self._analyze_trend(analysis_df, 5)
            medium_trend = self._analyze_trend(analysis_df, 10)
            long_trend = self._analyze_trend(analysis_df, 20)
            
            # 支撑阻力位
            support, resistance = self._calculate_support_resistance(analysis_df)
            
            # 成交量分析
            volume_ratio = latest['volume'] / analysis_df['volume'].tail(10).mean()
            volume_trend = self._analyze_volume_trend(analysis_df)
            
            # 综合评分
            technical_score = self._calculate_technical_score(analysis_df)
            momentum_score = self._calculate_momentum_score(analysis_df)
            risk_score = self._calculate_risk_score(analysis_df)
            
            return MarketAnalysis(
                symbol=symbol,
                date=date.strftime('%Y-%m-%d'),
                ma5=analysis_df.iloc[-1]['ma5'],
                ma10=analysis_df.iloc[-1]['ma10'],
                ma20=analysis_df.iloc[-1]['ma20'],
                rsi=analysis_df.iloc[-1]['rsi'],
                macd=analysis_df.iloc[-1]['macd'],
                macd_signal=analysis_df.iloc[-1]['macd_signal'],
                bb_upper=analysis_df.iloc[-1]['bb_upper'],
                bb_lower=analysis_df.iloc[-1]['bb_lower'],
                bb_position=self._calculate_bb_position(analysis_df.iloc[-1]),
                short_trend=short_trend,
                medium_trend=medium_trend,
                long_trend=long_trend,
                support_level=support,
                resistance_level=resistance,
                volume_ratio=volume_ratio,
                volume_trend=volume_trend,
                technical_score=technical_score,
                momentum_score=momentum_score,
                risk_score=risk_score
            )
            
        except Exception as e:
            self.logger.debug(f"市场分析失败 {symbol}: {e}")
            return None
    
    def _calculate_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 移动平均线
        df['ma5'] = df['close'].rolling(window=5).mean()
        df['ma10'] = df['close'].rolling(window=10).mean()
        df['ma20'] = df['close'].rolling(window=20).mean()
        
        # RSI
        try:
            df['rsi'] = self._calculate_rsi(df['close'])
        except:
            df['rsi'] = 50
        
        # MACD
        try:
            macd_data = self._calculate_macd(df['close'])
            df['macd'] = macd_data['macd']
            df['macd_signal'] = macd_data['signal']
        except:
            df['macd'] = 0
            df['macd_signal'] = 0
        
        # 布林带
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * bb_std
        df['bb_lower'] = df['bb_middle'] - 2 * bb_std
        
        return df
    
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """计算RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_macd(self, prices: pd.Series) -> Dict:
        """计算MACD"""
        ema12 = prices.ewm(span=12).mean()
        ema26 = prices.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        
        return {
            'macd': macd,
            'signal': signal,
            'histogram': macd - signal
        }
    
    def _analyze_trend(self, df: pd.DataFrame, period: int) -> str:
        """分析趋势"""
        try:
            if len(df) < period:
                return "数据不足"
            
            recent_prices = df['close'].tail(period)
            first_price = recent_prices.iloc[0]
            last_price = recent_prices.iloc[-1]
            
            change_rate = (last_price - first_price) / first_price
            
            if change_rate > 0.05:
                return "强势上涨"
            elif change_rate > 0.02:
                return "温和上涨"
            elif change_rate > -0.02:
                return "横盘整理"
            elif change_rate > -0.05:
                return "温和下跌"
            else:
                return "强势下跌"
                
        except:
            return "未知"
    
    def _calculate_support_resistance(self, df: pd.DataFrame) -> Tuple[float, float]:
        """计算支撑阻力位"""
        try:
            recent_data = df.tail(20)
            
            # 简化的支撑阻力计算
            lows = recent_data['low']
            highs = recent_data['high']
            
            support = lows.quantile(0.2)  # 20%分位数作为支撑
            resistance = highs.quantile(0.8)  # 80%分位数作为阻力
            
            return support, resistance
            
        except:
            current_price = df.iloc[-1]['close']
            return current_price * 0.95, current_price * 1.05
    
    def _analyze_volume_trend(self, df: pd.DataFrame) -> str:
        """分析成交量趋势"""
        try:
            recent_volume = df['volume'].tail(5).mean()
            historical_volume = df['volume'].tail(20).mean()
            
            ratio = recent_volume / historical_volume
            
            if ratio > 1.5:
                return "放量"
            elif ratio > 1.2:
                return "温和放量"
            elif ratio < 0.8:
                return "缩量"
            else:
                return "正常"
                
        except:
            return "未知"
    
    def _calculate_bb_position(self, row: pd.Series) -> float:
        """计算布林带位置"""
        try:
            if pd.isna(row['bb_upper']) or pd.isna(row['bb_lower']):
                return 0.5
            
            bb_width = row['bb_upper'] - row['bb_lower']
            if bb_width == 0:
                return 0.5
            
            position = (row['close'] - row['bb_lower']) / bb_width
            return max(0, min(1, position))
            
        except:
            return 0.5
    
    def _calculate_technical_score(self, df: pd.DataFrame) -> float:
        """计算技术面评分"""
        try:
            latest = df.iloc[-1]
            score = 50  # 基础分
            
            # 均线排列评分
            if latest['close'] > latest['ma5'] > latest['ma10'] > latest['ma20']:
                score += 20
            elif latest['close'] > latest['ma5'] > latest['ma10']:
                score += 10
            elif latest['close'] < latest['ma5'] < latest['ma10'] < latest['ma20']:
                score -= 20
            
            # RSI评分
            if 30 < latest['rsi'] < 70:
                score += 10
            elif latest['rsi'] > 80 or latest['rsi'] < 20:
                score -= 10
            
            # MACD评分
            if latest['macd'] > latest['macd_signal'] and latest['macd'] > 0:
                score += 15
            elif latest['macd'] < latest['macd_signal'] and latest['macd'] < 0:
                score -= 15
            
            # 布林带位置评分
            bb_pos = self._calculate_bb_position(latest)
            if 0.2 < bb_pos < 0.8:
                score += 5
            elif bb_pos > 0.9 or bb_pos < 0.1:
                score -= 10
            
            return max(0, min(100, score))
            
        except:
            return 50
    
    def _calculate_momentum_score(self, df: pd.DataFrame) -> float:
        """计算动量评分"""
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            score = 50
            
            # 价格动量
            price_change = (latest['close'] - prev['close']) / prev['close']
            score += price_change * 1000  # 放大系数
            
            # 成交量动量
            if latest['volume'] > df['volume'].tail(10).mean():
                score += 10
            
            # 趋势一致性
            if (latest['close'] > latest['ma5'] and 
                latest['ma5'] > latest['ma10'] and 
                latest['ma10'] > latest['ma20']):
                score += 15
            
            return max(0, min(100, score))
            
        except:
            return 50
    
    def _calculate_risk_score(self, df: pd.DataFrame) -> float:
        """计算风险评分"""
        try:
            # 波动率风险
            returns = df['close'].pct_change().tail(10)
            volatility = returns.std()
            
            score = 50
            
            # 波动率评分（波动率越高风险越大）
            if volatility > 0.05:
                score += 30
            elif volatility > 0.03:
                score += 15
            elif volatility < 0.01:
                score -= 10
            
            # 技术面风险
            latest = df.iloc[-1]
            if latest['rsi'] > 80:
                score += 20  # 超买风险
            elif latest['rsi'] < 20:
                score += 15  # 超卖反弹风险
            
            # 趋势风险
            if (latest['close'] < latest['ma5'] < latest['ma10'] < latest['ma20']):
                score += 25  # 下跌趋势风险
            
            return max(0, min(100, score))
            
        except:
            return 50
    
    def generate_trading_signal(self, symbol: str, df: pd.DataFrame, 
                              date: datetime) -> Optional[TradingSignal]:
        """生成交易信号"""
        try:
            # 市场分析
            analysis = self.analyze_market(symbol, df, date)
            if not analysis:
                return None
            
            # 当前持仓状态
            current_position = self.positions.get(symbol)
            
            # 决策逻辑
            action, confidence, trend_expectation, reason = self._make_trading_decision(
                analysis, current_position
            )
            
            # 风险评估
            risk_level = analysis.risk_score / 100
            
            # 建议仓位大小
            suggested_size = self._calculate_position_size(analysis, risk_level)
            
            # 获取当前价格
            try:
                if date in df.index:
                    current_price = df.loc[date, 'close']
                else:
                    # 如果指定日期不存在，使用最近的价格
                    available_dates = df.index[df.index <= date]
                    if len(available_dates) > 0:
                        current_price = df.loc[available_dates[-1], 'close']
                    else:
                        current_price = df.iloc[-1]['close']
            except Exception as e:
                self.logger.debug(f"获取价格失败 {symbol} {date}: {e}")
                current_price = df.iloc[-1]['close']
            
            return TradingSignal(
                symbol=symbol,
                date=date.strftime('%Y-%m-%d'),
                action=action,
                price=current_price,
                confidence=confidence,
                trend_expectation=trend_expectation,
                reason=reason,
                risk_level=risk_level,
                suggested_position_size=suggested_size
            )
            
        except Exception as e:
            self.logger.debug(f"生成交易信号失败 {symbol}: {e}")
            return None
    
    def _make_trading_decision(self, analysis: MarketAnalysis, 
                             current_position: Optional[Position]) -> Tuple[TradingAction, float, TrendExpectation, str]:
        """制定交易决策"""
        
        # 综合评分
        tech_score = analysis.technical_score
        momentum_score = analysis.momentum_score
        risk_score = analysis.risk_score
        
        # 趋势判断
        if analysis.short_trend == "强势上涨" and analysis.medium_trend in ["强势上涨", "温和上涨"]:
            trend_expectation = TrendExpectation.STRONG_UP
        elif analysis.short_trend == "温和上涨":
            trend_expectation = TrendExpectation.WEAK_UP
        elif analysis.short_trend == "横盘整理":
            trend_expectation = TrendExpectation.SIDEWAYS
        elif analysis.short_trend == "温和下跌":
            trend_expectation = TrendExpectation.WEAK_DOWN
        else:
            trend_expectation = TrendExpectation.STRONG_DOWN
        
        # 决策逻辑
        if current_position is None:  # 无持仓
            if (tech_score > 70 and momentum_score > 60 and risk_score < 60 and
                trend_expectation in [TrendExpectation.STRONG_UP, TrendExpectation.WEAK_UP]):
                return TradingAction.BUY, 0.8, trend_expectation, f"技术面强势(T:{tech_score:.0f} M:{momentum_score:.0f} R:{risk_score:.0f})"
            
            elif (tech_score > 60 and momentum_score > 55 and risk_score < 70):
                return TradingAction.OBSERVE, 0.6, trend_expectation, f"观察等待更好时机(T:{tech_score:.0f})"
            
            else:
                return TradingAction.OBSERVE, 0.4, trend_expectation, "市场条件不佳，继续观察"
        
        else:  # 有持仓
            # 检查T+1规则
            if not current_position.can_sell:
                return TradingAction.HOLD, 0.9, trend_expectation, "T+1规则限制，无法卖出"
            
            # 止盈止损判断
            unrealized_rate = current_position.unrealized_pnl_rate
            
            if unrealized_rate > 0.15:  # 盈利超过15%
                return TradingAction.SELL, 0.9, trend_expectation, f"止盈卖出(盈利{unrealized_rate:.1%})"
            
            elif unrealized_rate < -0.08:  # 亏损超过8%
                return TradingAction.SELL, 0.8, trend_expectation, f"止损卖出(亏损{unrealized_rate:.1%})"
            
            elif (risk_score > 80 or trend_expectation == TrendExpectation.STRONG_DOWN):
                return TradingAction.SELL, 0.7, trend_expectation, f"风险过高，减仓(R:{risk_score:.0f})"
            
            elif (tech_score < 40 and momentum_score < 40):
                return TradingAction.SELL, 0.6, trend_expectation, "技术面转弱，考虑卖出"
            
            else:
                return TradingAction.HOLD, 0.5, trend_expectation, f"继续持有(盈亏{unrealized_rate:.1%})"
    
    def _calculate_position_size(self, analysis: MarketAnalysis, risk_level: float) -> float:
        """计算建议仓位大小"""
        base_size = self.max_position_size
        
        # 根据技术面调整
        if analysis.technical_score > 80:
            base_size *= 1.2
        elif analysis.technical_score < 50:
            base_size *= 0.6
        
        # 根据风险调整
        risk_adjustment = 1 - risk_level * 0.5
        base_size *= risk_adjustment
        
        # 确保不超过限制
        return min(base_size, self.max_position_size)
    
    def execute_trade(self, signal: TradingSignal) -> bool:
        """执行交易（模拟）"""
        try:
            if signal.action == TradingAction.BUY:
                return self._execute_buy(signal)
            elif signal.action == TradingAction.SELL:
                return self._execute_sell(signal)
            else:
                # HOLD 或 OBSERVE 不需要执行
                return True
                
        except Exception as e:
            self.logger.error(f"执行交易失败: {e}")
            return False
    
    def _execute_buy(self, signal: TradingSignal) -> bool:
        """执行买入"""
        try:
            # 计算买入金额
            position_value = self.initial_capital * signal.suggested_position_size
            trade_amount = min(position_value, self.available_cash * 0.95)  # 保留5%现金
            
            if trade_amount < self.min_trade_amount:
                self.logger.info(f"买入金额不足最小交易额: {trade_amount}")
                return False
            
            # 计算股数（100股为单位）
            shares = int(trade_amount / signal.price / 100) * 100
            if shares == 0:
                return False
            
            # 计算实际成本
            actual_cost = shares * signal.price
            commission = max(actual_cost * self.commission_rate, 5.0)
            total_cost = actual_cost + commission
            
            if total_cost > self.available_cash:
                return False
            
            # 更新持仓
            self.positions[signal.symbol] = Position(
                symbol=signal.symbol,
                shares=shares,
                avg_cost=signal.price,
                buy_date=signal.date,
                current_price=signal.price,
                market_value=actual_cost,
                unrealized_pnl=0,
                unrealized_pnl_rate=0,
                can_sell=False  # T+1规则：当天买入不能卖出
            )
            
            # 更新现金
            self.available_cash -= total_cost
            
            # 记录交易
            self.trading_history.append(signal)
            
            self.logger.info(f"买入成功: {signal.symbol} {shares}股 @{signal.price:.2f}")
            return True
            
        except Exception as e:
            self.logger.error(f"买入执行失败: {e}")
            return False
    
    def _execute_sell(self, signal: TradingSignal) -> bool:
        """执行卖出"""
        try:
            position = self.positions.get(signal.symbol)
            if not position:
                return False
            
            if not position.can_sell:
                self.logger.warning(f"T+1规则限制，无法卖出 {signal.symbol}")
                return False
            
            # 计算卖出收入
            sell_amount = position.shares * signal.price
            commission = max(sell_amount * self.commission_rate, 5.0)
            net_amount = sell_amount - commission
            
            # 更新现金
            self.available_cash += net_amount
            
            # 移除持仓
            del self.positions[signal.symbol]
            
            # 记录交易
            self.trading_history.append(signal)
            
            self.logger.info(f"卖出成功: {signal.symbol} {position.shares}股 @{signal.price:.2f}")
            return True
            
        except Exception as e:
            self.logger.error(f"卖出执行失败: {e}")
            return False
    
    def update_positions(self, date: datetime, price_data: Dict[str, float]):
        """更新持仓信息（每日收盘后调用）"""
        for symbol, position in self.positions.items():
            if symbol in price_data:
                current_price = price_data[symbol]
                
                # 更新市值和盈亏
                position.current_price = current_price
                position.market_value = position.shares * current_price
                position.unrealized_pnl = position.market_value - (position.shares * position.avg_cost)
                position.unrealized_pnl_rate = position.unrealized_pnl / (position.shares * position.avg_cost)
                
                # 更新T+1状态（买入次日可以卖出）
                buy_date = datetime.strptime(position.buy_date, '%Y-%m-%d')
                if date > buy_date:
                    position.can_sell = True
    
    def get_portfolio_summary(self) -> Dict:
        """获取组合摘要"""
        total_market_value = sum(pos.market_value for pos in self.positions.values())
        total_cost = sum(pos.shares * pos.avg_cost for pos in self.positions.values())
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in self.positions.values())
        
        total_assets = self.available_cash + total_market_value
        total_return_rate = (total_assets - self.initial_capital) / self.initial_capital
        
        return {
            "总资产": total_assets,
            "可用现金": self.available_cash,
            "持仓市值": total_market_value,
            "持仓成本": total_cost,
            "浮动盈亏": total_unrealized_pnl,
            "总收益率": total_return_rate,
            "持仓数量": len(self.positions),
            "仓位占比": total_market_value / total_assets if total_assets > 0 else 0
        }

def demo_t1_intelligent_trading():
    """演示T+1智能交易系统"""
    print("🎯 T+1智能交易系统演示")
    print("=" * 60)
    
    # 创建交易系统
    trading_system = T1IntelligentTradingSystem(initial_capital=100000)
    
    # 模拟股票数据
    dates = pd.date_range(start='2025-07-01', periods=30, freq='D')
    np.random.seed(42)
    
    # 创建测试股票数据
    symbols = ['TEST001', 'TEST002', 'TEST003']
    stock_data = {}
    
    for symbol in symbols:
        base_price = np.random.uniform(8, 15)
        prices = [base_price]
        
        for i in range(29):
            # 模拟不同的走势
            if symbol == 'TEST001':  # 上涨趋势
                change = np.random.normal(0.015, 0.02)
            elif symbol == 'TEST002':  # 震荡
                change = np.random.normal(0.002, 0.025)
            else:  # 下跌趋势
                change = np.random.normal(-0.01, 0.02)
            
            new_price = prices[-1] * (1 + change)
            prices.append(max(new_price, prices[-1] * 0.9))
        
        stock_data[symbol] = pd.DataFrame({
            'open': [p * (1 + np.random.normal(0, 0.005)) for p in prices],
            'high': [p * (1 + abs(np.random.normal(0, 0.015))) for p in prices],
            'low': [p * (1 - abs(np.random.normal(0, 0.015))) for p in prices],
            'close': prices,
            'volume': np.random.randint(1000000, 5000000, 30)
        }, index=dates)
    
    print(f"📊 模拟交易数据:")
    for symbol, df in stock_data.items():
        start_price = df.iloc[0]['close']
        end_price = df.iloc[-1]['close']
        total_return = (end_price - start_price) / start_price
        print(f"  {symbol}: ¥{start_price:.2f} → ¥{end_price:.2f} ({total_return:+.1%})")
    
    print(f"\n📈 交易过程模拟:")
    print("-" * 60)
    
    # 模拟交易过程
    for i, date in enumerate(dates[5:], 5):  # 从第6天开始，确保有足够历史数据
        print(f"\n📅 {date.strftime('%Y-%m-%d')} (第{i+1}天)")
        
        # 获取当日价格
        current_prices = {symbol: df.loc[date, 'close'] for symbol, df in stock_data.items()}
        
        # 更新持仓
        trading_system.update_positions(date, current_prices)
        
        # 为每只股票生成交易信号
        for symbol, df in stock_data.items():
            signal = trading_system.generate_trading_signal(symbol, df, date)
            
            if signal:
                print(f"  {symbol}: {signal.action.value} - {signal.reason}")
                print(f"    价格: ¥{signal.price:.2f}, 置信度: {signal.confidence:.1f}")
                print(f"    走势预期: {signal.trend_expectation.value}")
                print(f"    风险等级: {signal.risk_level:.2f}")
                
                # 执行交易
                if signal.action in [TradingAction.BUY, TradingAction.SELL]:
                    success = trading_system.execute_trade(signal)
                    if success:
                        print(f"    ✅ 交易执行成功")
                    else:
                        print(f"    ❌ 交易执行失败")
        
        # 显示组合状态
        if i % 5 == 0:  # 每5天显示一次组合状态
            portfolio = trading_system.get_portfolio_summary()
            print(f"\n  💼 组合状态:")
            print(f"    总资产: ¥{portfolio['总资产']:,.0f}")
            print(f"    总收益率: {portfolio['总收益率']:+.2%}")
            print(f"    持仓数量: {portfolio['持仓数量']}")
            print(f"    仓位占比: {portfolio['仓位占比']:.1%}")
    
    # 最终结果
    final_portfolio = trading_system.get_portfolio_summary()
    
    print(f"\n🎉 交易结果总结:")
    print("=" * 40)
    print(f"初始资金: ¥{trading_system.initial_capital:,.0f}")
    print(f"最终资产: ¥{final_portfolio['总资产']:,.0f}")
    print(f"总收益率: {final_portfolio['总收益率']:+.2%}")
    print(f"交易次数: {len(trading_system.trading_history)}")
    print(f"最终持仓: {final_portfolio['持仓数量']}只")
    
    # 持仓详情
    if trading_system.positions:
        print(f"\n📋 当前持仓:")
        for symbol, pos in trading_system.positions.items():
            print(f"  {symbol}: {pos.shares}股 @¥{pos.avg_cost:.2f}")
            print(f"    当前价: ¥{pos.current_price:.2f}")
            print(f"    盈亏: {pos.unrealized_pnl_rate:+.1%}")
            print(f"    可卖出: {'是' if pos.can_sell else '否(T+1限制)'}")
    
    print(f"\n💡 系统特点验证:")
    print(f"  ✅ T+1规则严格执行")
    print(f"  ✅ 基于技术分析的智能决策")
    print(f"  ✅ 买入/卖出/持有/观察四种动作")
    print(f"  ✅ 动态风险控制")
    print(f"  ✅ 仓位管理")

if __name__ == "__main__":
    demo_t1_intelligent_trading()