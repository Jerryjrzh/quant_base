#!/usr/bin/env python3
"""
强势股筛选优化系统
基于技术指标回测，在季度筛选基础上进一步提高胜率
重点识别强势股票（价格很少触及MA13或MA20）
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# 添加backend路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import data_loader
import indicators

@dataclass
class MomentumConfig:
    """强势分析配置"""
    # MA强势判断参数
    ma_periods: List[int] = None  # MA周期 [13, 20, 34, 55]
    strength_threshold: float = 0.95  # 强势阈值：95%时间在MA之上
    touch_tolerance: float = 0.02  # 触及容忍度：2%以内算触及
    
    # 技术指标参数
    rsi_period: int = 14
    rsi_overbought: float = 70
    rsi_oversold: float = 30
    
    kdj_period: int = 27
    kdj_overbought: float = 80
    kdj_oversold: float = 20
    
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    
    # 回测参数
    lookback_days: int = 60  # 回测天数
    min_data_points: int = 100  # 最少数据点
    
    def __post_init__(self):
        if self.ma_periods is None:
            self.ma_periods = [13, 20, 34, 55]

@dataclass
class StockStrengthResult:
    """股票强势分析结果"""
    symbol: str
    
    # MA强势分析
    ma_strength_scores: Dict[int, float]  # 各MA周期的强势得分
    overall_strength_score: float  # 综合强势得分
    strength_rank: str  # 强势等级：强势/中等/弱势
    
    # 技术指标状态
    rsi_value: float
    rsi_signal: str  # 超买/正常/超卖
    
    kdj_k: float
    kdj_d: float
    kdj_j: float
    kdj_signal: str
    
    macd_value: float
    macd_signal_value: float
    macd_histogram: float
    macd_signal: str  # 金叉/死叉/震荡
    
    # 价格动量
    price_momentum_5d: float  # 5日动量
    price_momentum_10d: float  # 10日动量
    price_momentum_20d: float  # 20日动量
    
    # 成交量分析
    volume_ratio: float  # 成交量比率
    volume_trend: str  # 放量/缩量/正常
    
    # 综合评分
    technical_score: float  # 技术面得分 (0-100)
    momentum_score: float  # 动量得分 (0-100)
    final_score: float  # 最终得分 (0-100)
    
    # 操作建议
    action_signal: str  # 买入/观望/卖出
    confidence_level: float  # 信心度 (0-1)
    risk_level: str  # 风险等级：低/中/高

class MomentumStrengthAnalyzer:
    """强势股分析器"""
    
    def __init__(self, config: MomentumConfig = None):
        self.config = config or MomentumConfig()
        self.logger = self._setup_logger()
        self.data_cache = {}
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger('MomentumStrengthAnalyzer')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def load_stock_data(self, symbol: str, days: int = None) -> Optional[pd.DataFrame]:
        """加载股票数据"""
        if days is None:
            days = self.config.lookback_days + 100  # 额外加载数据用于指标计算
        
        if symbol in self.data_cache:
            return self.data_cache[symbol]
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 使用数据加载器
            base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
            market = symbol[:2]
            file_path = os.path.join(base_path, market, 'lday', f'{symbol}.day')
            
            if not os.path.exists(file_path):
                return None
            
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < self.config.min_data_points:
                return None
            
            # 过滤到指定日期范围
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if len(df) < self.config.min_data_points:
                return None
            
            self.data_cache[symbol] = df
            return df
            
        except Exception as e:
            self.logger.warning(f"加载股票数据失败 {symbol}: {e}")
            return None
    
    def calculate_ma_strength(self, df: pd.DataFrame) -> Dict[int, float]:
        """
        计算MA强势得分
        
        强势股特征：价格很少触及MA13或MA20
        """
        ma_scores = {}
        
        for period in self.config.ma_periods:
            # 计算MA
            ma = df['close'].rolling(window=period).mean()
            
            # 计算价格相对MA的位置
            price_above_ma = df['close'] > ma
            
            # 计算触及MA的次数（价格在MA附近的容忍范围内）
            touch_threshold = ma * (1 - self.config.touch_tolerance)
            price_near_ma = (df['close'] >= touch_threshold) & (df['close'] <= ma * (1 + self.config.touch_tolerance))
            
            # 强势得分 = 在MA之上的时间比例 - 触及MA的惩罚
            above_ratio = price_above_ma.sum() / len(price_above_ma)
            touch_penalty = price_near_ma.sum() / len(price_near_ma) * 0.5  # 触及惩罚
            
            strength_score = max(0, above_ratio - touch_penalty)
            ma_scores[period] = strength_score
        
        return ma_scores
    
    def calculate_technical_indicators(self, df: pd.DataFrame) -> Dict:
        """计算技术指标"""
        result = {}
        
        try:
            # RSI
            rsi = indicators.calculate_rsi(df['close'], self.config.rsi_period)
            result['rsi'] = rsi.iloc[-1] if not rsi.empty else 50
            
            if result['rsi'] > self.config.rsi_overbought:
                result['rsi_signal'] = '超买'
            elif result['rsi'] < self.config.rsi_oversold:
                result['rsi_signal'] = '超卖'
            else:
                result['rsi_signal'] = '正常'
            
            # KDJ
            kdj = indicators.calculate_kdj(df, self.config.kdj_period)
            if not kdj.empty:
                result['kdj_k'] = kdj['K'].iloc[-1]
                result['kdj_d'] = kdj['D'].iloc[-1]
                result['kdj_j'] = kdj['J'].iloc[-1]
                
                if result['kdj_k'] > self.config.kdj_overbought:
                    result['kdj_signal'] = '超买'
                elif result['kdj_k'] < self.config.kdj_oversold:
                    result['kdj_signal'] = '超卖'
                else:
                    result['kdj_signal'] = '正常'
            else:
                result['kdj_k'] = result['kdj_d'] = result['kdj_j'] = 50
                result['kdj_signal'] = '正常'
            
            # MACD
            macd_data = indicators.calculate_macd(
                df['close'], 
                self.config.macd_fast, 
                self.config.macd_slow, 
                self.config.macd_signal
            )
            
            if not macd_data.empty:
                result['macd'] = macd_data['MACD'].iloc[-1]
                result['macd_signal'] = macd_data['Signal'].iloc[-1]
                result['macd_histogram'] = macd_data['Histogram'].iloc[-1]
                
                # MACD信号判断
                if len(macd_data) >= 2:
                    prev_histogram = macd_data['Histogram'].iloc[-2]
                    curr_histogram = macd_data['Histogram'].iloc[-1]
                    
                    if prev_histogram <= 0 and curr_histogram > 0:
                        result['macd_signal_type'] = '金叉'
                    elif prev_histogram >= 0 and curr_histogram < 0:
                        result['macd_signal_type'] = '死叉'
                    else:
                        result['macd_signal_type'] = '震荡'
                else:
                    result['macd_signal_type'] = '震荡'
            else:
                result['macd'] = result['macd_signal'] = result['macd_histogram'] = 0
                result['macd_signal_type'] = '震荡'
            
        except Exception as e:
            self.logger.warning(f"计算技术指标失败: {e}")
            # 设置默认值
            result.update({
                'rsi': 50, 'rsi_signal': '正常',
                'kdj_k': 50, 'kdj_d': 50, 'kdj_j': 50, 'kdj_signal': '正常',
                'macd': 0, 'macd_signal': 0, 'macd_histogram': 0, 'macd_signal_type': '震荡'
            })
        
        return result
    
    def calculate_momentum_indicators(self, df: pd.DataFrame) -> Dict:
        """计算动量指标"""
        result = {}
        
        try:
            close_prices = df['close']
            
            # 价格动量
            if len(close_prices) >= 5:
                result['momentum_5d'] = (close_prices.iloc[-1] / close_prices.iloc[-5] - 1)
            else:
                result['momentum_5d'] = 0
            
            if len(close_prices) >= 10:
                result['momentum_10d'] = (close_prices.iloc[-1] / close_prices.iloc[-10] - 1)
            else:
                result['momentum_10d'] = 0
            
            if len(close_prices) >= 20:
                result['momentum_20d'] = (close_prices.iloc[-1] / close_prices.iloc[-20] - 1)
            else:
                result['momentum_20d'] = 0
            
            # 成交量分析
            volumes = df['volume']
            if len(volumes) >= 20:
                avg_volume_20 = volumes.iloc[-20:].mean()
                recent_volume = volumes.iloc[-5:].mean()
                result['volume_ratio'] = recent_volume / avg_volume_20
                
                if result['volume_ratio'] > 1.5:
                    result['volume_trend'] = '放量'
                elif result['volume_ratio'] < 0.7:
                    result['volume_trend'] = '缩量'
                else:
                    result['volume_trend'] = '正常'
            else:
                result['volume_ratio'] = 1.0
                result['volume_trend'] = '正常'
            
        except Exception as e:
            self.logger.warning(f"计算动量指标失败: {e}")
            result.update({
                'momentum_5d': 0, 'momentum_10d': 0, 'momentum_20d': 0,
                'volume_ratio': 1.0, 'volume_trend': '正常'
            })
        
        return result
    
    def calculate_comprehensive_score(self, ma_scores: Dict, technical: Dict, momentum: Dict) -> Tuple[float, float, float]:
        """计算综合评分"""
        
        # 1. 技术面得分 (0-100)
        technical_score = 0
        
        # RSI得分 (30分)
        if technical['rsi_signal'] == '正常':
            rsi_score = 30
        elif technical['rsi_signal'] == '超买':
            rsi_score = 15  # 超买风险
        else:  # 超卖
            rsi_score = 20
        technical_score += rsi_score
        
        # KDJ得分 (25分)
        if technical['kdj_signal'] == '正常':
            kdj_score = 25
        elif technical['kdj_signal'] == '超买':
            kdj_score = 10
        else:  # 超卖
            kdj_score = 15
        technical_score += kdj_score
        
        # MACD得分 (25分)
        if technical['macd_signal_type'] == '金叉':
            macd_score = 25
        elif technical['macd_signal_type'] == '死叉':
            macd_score = 5
        else:  # 震荡
            macd_score = 15
        technical_score += macd_score
        
        # MA强势得分 (20分)
        ma_strength = np.mean(list(ma_scores.values()))
        ma_score = ma_strength * 20
        technical_score += ma_score
        
        # 2. 动量得分 (0-100)
        momentum_score = 0
        
        # 短期动量 (40分)
        momentum_5d = momentum['momentum_5d']
        if momentum_5d > 0.05:  # 5日涨幅>5%
            momentum_score += 40
        elif momentum_5d > 0:
            momentum_score += 20
        else:
            momentum_score += 0
        
        # 中期动量 (35分)
        momentum_10d = momentum['momentum_10d']
        if momentum_10d > 0.1:  # 10日涨幅>10%
            momentum_score += 35
        elif momentum_10d > 0:
            momentum_score += 20
        else:
            momentum_score += 0
        
        # 成交量得分 (25分)
        if momentum['volume_trend'] == '放量':
            volume_score = 25
        elif momentum['volume_trend'] == '正常':
            volume_score = 15
        else:  # 缩量
            volume_score = 5
        momentum_score += volume_score
        
        # 3. 最终得分 (技术面60% + 动量40%)
        final_score = technical_score * 0.6 + momentum_score * 0.4
        
        return technical_score, momentum_score, final_score
    
    def determine_action_signal(self, ma_scores: Dict, technical: Dict, momentum: Dict, final_score: float) -> Tuple[str, float, str]:
        """确定操作信号"""
        
        # 计算信心度
        confidence = final_score / 100
        
        # 风险等级评估
        risk_factors = 0
        
        # RSI风险
        if technical['rsi_signal'] == '超买':
            risk_factors += 1
        
        # KDJ风险
        if technical['kdj_signal'] == '超买':
            risk_factors += 1
        
        # MACD风险
        if technical['macd_signal_type'] == '死叉':
            risk_factors += 1
        
        # MA强势风险
        ma_strength = np.mean(list(ma_scores.values()))
        if ma_strength < 0.7:
            risk_factors += 1
        
        # 动量风险
        if momentum['momentum_5d'] < -0.03:  # 5日跌幅>3%
            risk_factors += 1
        
        # 确定风险等级
        if risk_factors <= 1:
            risk_level = '低'
        elif risk_factors <= 3:
            risk_level = '中'
        else:
            risk_level = '高'
        
        # 确定操作信号
        if final_score >= 75 and risk_level in ['低', '中']:
            action = '买入'
        elif final_score >= 60 and risk_level == '低':
            action = '买入'
        elif final_score >= 40:
            action = '观望'
        else:
            action = '卖出'
        
        return action, confidence, risk_level
    
    def analyze_stock_strength(self, symbol: str) -> Optional[StockStrengthResult]:
        """分析单只股票的强势程度"""
        
        df = self.load_stock_data(symbol)
        if df is None:
            return None
        
        try:
            # 1. 计算MA强势得分
            ma_scores = self.calculate_ma_strength(df)
            overall_strength = np.mean(list(ma_scores.values()))
            
            # 确定强势等级
            if overall_strength >= self.config.strength_threshold:
                strength_rank = '强势'
            elif overall_strength >= 0.8:
                strength_rank = '中等'
            else:
                strength_rank = '弱势'
            
            # 2. 计算技术指标
            technical = self.calculate_technical_indicators(df)
            
            # 3. 计算动量指标
            momentum = self.calculate_momentum_indicators(df)
            
            # 4. 计算综合评分
            technical_score, momentum_score, final_score = self.calculate_comprehensive_score(
                ma_scores, technical, momentum
            )
            
            # 5. 确定操作信号
            action, confidence, risk_level = self.determine_action_signal(
                ma_scores, technical, momentum, final_score
            )
            
            # 6. 创建结果对象
            result = StockStrengthResult(
                symbol=symbol,
                ma_strength_scores=ma_scores,
                overall_strength_score=overall_strength,
                strength_rank=strength_rank,
                rsi_value=technical['rsi'],
                rsi_signal=technical['rsi_signal'],
                kdj_k=technical['kdj_k'],
                kdj_d=technical['kdj_d'],
                kdj_j=technical['kdj_j'],
                kdj_signal=technical['kdj_signal'],
                macd_value=technical['macd'],
                macd_signal_value=technical['macd_signal'],
                macd_histogram=technical['macd_histogram'],
                macd_signal=technical['macd_signal_type'],
                price_momentum_5d=momentum['momentum_5d'],
                price_momentum_10d=momentum['momentum_10d'],
                price_momentum_20d=momentum['momentum_20d'],
                volume_ratio=momentum['volume_ratio'],
                volume_trend=momentum['volume_trend'],
                technical_score=technical_score,
                momentum_score=momentum_score,
                final_score=final_score,
                action_signal=action,
                confidence_level=confidence,
                risk_level=risk_level
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"分析股票 {symbol} 失败: {e}")
            return None
    
    def analyze_stock_pool(self, stock_list: List[str]) -> List[StockStrengthResult]:
        """分析股票池"""
        self.logger.info(f"开始分析 {len(stock_list)} 只股票的强势程度")
        
        results = []
        
        def analyze_single_stock(symbol):
            return self.analyze_stock_strength(symbol)
        
        # 并行分析
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(analyze_single_stock, symbol) for symbol in stock_list]
            
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result)
        
        # 按最终得分排序
        results.sort(key=lambda x: x.final_score, reverse=True)
        
        self.logger.info(f"完成分析，有效结果 {len(results)} 个")
        return results
    
    def filter_by_strength_criteria(self, results: List[StockStrengthResult], 
                                  min_score: float = 60, 
                                  strength_ranks: List[str] = None,
                                  action_signals: List[str] = None) -> List[StockStrengthResult]:
        """按强势标准过滤"""
        
        if strength_ranks is None:
            strength_ranks = ['强势', '中等']
        
        if action_signals is None:
            action_signals = ['买入']
        
        filtered = []
        for result in results:
            if (result.final_score >= min_score and 
                result.strength_rank in strength_ranks and
                result.action_signal in action_signals):
                filtered.append(result)
        
        return filtered
    
    def generate_strength_report(self, results: List[StockStrengthResult]) -> str:
        """生成强势分析报告"""
        
        if not results:
            return "没有分析结果"
        
        report = []
        report.append("=" * 80)
        report.append("🚀 强势股筛选优化报告")
        report.append("=" * 80)
        
        # 统计概览
        total_stocks = len(results)
        strong_stocks = len([r for r in results if r.strength_rank == '强势'])
        medium_stocks = len([r for r in results if r.strength_rank == '中等'])
        weak_stocks = len([r for r in results if r.strength_rank == '弱势'])
        
        buy_signals = len([r for r in results if r.action_signal == '买入'])
        hold_signals = len([r for r in results if r.action_signal == '观望'])
        sell_signals = len([r for r in results if r.action_signal == '卖出'])
        
        report.append(f"\n📊 统计概览:")
        report.append(f"  总股票数: {total_stocks}")
        report.append(f"  强势股票: {strong_stocks} ({strong_stocks/total_stocks:.1%})")
        report.append(f"  中等股票: {medium_stocks} ({medium_stocks/total_stocks:.1%})")
        report.append(f"  弱势股票: {weak_stocks} ({weak_stocks/total_stocks:.1%})")
        report.append(f"")
        report.append(f"  买入信号: {buy_signals} ({buy_signals/total_stocks:.1%})")
        report.append(f"  观望信号: {hold_signals} ({hold_signals/total_stocks:.1%})")
        report.append(f"  卖出信号: {sell_signals} ({sell_signals/total_stocks:.1%})")
        
        # 强势股票详细列表
        strong_results = [r for r in results if r.strength_rank == '强势'][:20]  # 显示前20只
        
        if strong_results:
            report.append(f"\n🏆 强势股票排行榜 (前20名):")
            report.append("-" * 80)
            report.append(f"{'排名':<4} {'代码':<10} {'综合得分':<8} {'强势得分':<8} {'操作信号':<6} {'风险等级':<6} {'信心度':<6}")
            report.append("-" * 80)
            
            for i, result in enumerate(strong_results, 1):
                report.append(f"{i:<4} {result.symbol:<10} {result.final_score:<8.1f} "
                            f"{result.overall_strength_score:<8.2f} {result.action_signal:<6} "
                            f"{result.risk_level:<6} {result.confidence_level:<6.2f}")
        
        # 买入推荐列表
        buy_results = [r for r in results if r.action_signal == '买入'][:15]
        
        if buy_results:
            report.append(f"\n💰 买入推荐列表 (前15名):")
            report.append("-" * 100)
            report.append(f"{'代码':<10} {'综合得分':<8} {'技术得分':<8} {'动量得分':<8} {'RSI':<6} {'MACD':<8} {'5日涨幅':<8}")
            report.append("-" * 100)
            
            for result in buy_results:
                report.append(f"{result.symbol:<10} {result.final_score:<8.1f} "
                            f"{result.technical_score:<8.1f} {result.momentum_score:<8.1f} "
                            f"{result.rsi_value:<6.1f} {result.macd_signal:<8} "
                            f"{result.price_momentum_5d:<8.2%}")
        
        # MA强势分析
        report.append(f"\n📈 MA强势分析:")
        report.append("-" * 60)
        
        # 统计各MA周期的强势表现
        ma_stats = {}
        for period in self.config.ma_periods:
            strong_count = len([r for r in results if r.ma_strength_scores.get(period, 0) >= 0.9])
            ma_stats[period] = strong_count
        
        for period, count in ma_stats.items():
            report.append(f"  MA{period} 强势股票: {count} 只 ({count/total_stocks:.1%})")
        
        # 技术指标分布
        report.append(f"\n🔧 技术指标分布:")
        report.append("-" * 40)
        
        rsi_overbought = len([r for r in results if r.rsi_signal == '超买'])
        rsi_normal = len([r for r in results if r.rsi_signal == '正常'])
        rsi_oversold = len([r for r in results if r.rsi_signal == '超卖'])
        
        report.append(f"  RSI超买: {rsi_overbought} 只")
        report.append(f"  RSI正常: {rsi_normal} 只")
        report.append(f"  RSI超卖: {rsi_oversold} 只")
        
        macd_golden = len([r for r in results if r.macd_signal == '金叉'])
        macd_dead = len([r for r in results if r.macd_signal == '死叉'])
        macd_shock = len([r for r in results if r.macd_signal == '震荡'])
        
        report.append(f"  MACD金叉: {macd_golden} 只")
        report.append(f"  MACD死叉: {macd_dead} 只")
        report.append(f"  MACD震荡: {macd_shock} 只")
        
        # 操作建议
        report.append(f"\n💡 操作建议:")
        report.append("-" * 40)
        
        if buy_results:
            top_pick = buy_results[0]
            report.append(f"🎯 首选标的: {top_pick.symbol}")
            report.append(f"   综合得分: {top_pick.final_score:.1f}")
            report.append(f"   强势等级: {top_pick.strength_rank}")
            report.append(f"   风险等级: {top_pick.risk_level}")
            report.append(f"   信心度: {top_pick.confidence_level:.2f}")
            
            report.append(f"\n📋 操作策略:")
            report.append(f"   1. 重点关注强势股票，价格很少触及MA13/MA20")
            report.append(f"   2. 优先选择技术指标配合良好的标的")
            report.append(f"   3. 注意成交量配合，放量上涨更可靠")
            report.append(f"   4. 设置合理止损位，控制风险")
        
        # 风险提示
        report.append(f"\n⚠️ 风险提示:")
        report.append("-" * 40)
        report.append(f"   • 技术分析基于历史数据，不保证未来表现")
        report.append(f"   • 强势股票可能存在高位风险，注意及时止盈")
        report.append(f"   • 建议分散投资，不要集中持仓")
        report.append(f"   • 密切关注市场整体趋势变化")
        
        return "\n".join(report)
    
    def save_analysis_results(self, results: List[StockStrengthResult], filename: str = None):
        """保存分析结果"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'momentum_strength_analysis_{timestamp}.json'
        
        # 转换为可序列化的格式
        serializable_results = [asdict(result) for result in results]
        
        analysis_data = {
            'timestamp': datetime.now().isoformat(),
            'config': asdict(self.config),
            'total_analyzed': len(results),
            'results': serializable_results,
            'summary': {
                'strong_stocks': len([r for r in results if r.strength_rank == '强势']),
                'medium_stocks': len([r for r in results if r.strength_rank == '中等']),
                'weak_stocks': len([r for r in results if r.strength_rank == '弱势']),
                'buy_signals': len([r for r in results if r.action_signal == '买入']),
                'avg_score': np.mean([r.final_score for r in results]) if results else 0
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2, default=str)
        
        self.logger.info(f"分析结果已保存到: {filename}")
        return filename

def load_quarterly_stock_pool(json_file: str) -> List[str]:
    """从季度回测结果中加载股票池"""
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 提取核心股票池
        core_pool = data.get('strategy', {}).get('core_pool', [])
        stock_list = [stock['symbol'] for stock in core_pool]
        
        print(f"从 {json_file} 加载了 {len(stock_list)} 只股票")
        return stock_list
        
    except Exception as e:
        print(f"加载股票池失败: {e}")
        return []

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='强势股筛选优化系统')
    parser.add_argument('--quarterly-result', required=True, help='季度回测结果文件')
    parser.add_argument('--min-score', type=float, default=60, help='最低综合得分')
    parser.add_argument('--strength-threshold', type=float, default=0.95, help='强势阈值')
    parser.add_argument('--save-report', action='store_true', help='保存分析报告')
    
    args = parser.parse_args()
    
    print("🚀 强势股筛选优化系统")
    print("=" * 50)
    
    # 加载季度股票池
    stock_list = load_quarterly_stock_pool(args.quarterly_result)
    if not stock_list:
        print("❌ 无法加载股票池，程序退出")
        return
    
    # 创建配置
    config = MomentumConfig(
        strength_threshold=args.strength_threshold,
        lookback_days=60
    )
    
    # 创建分析器
    analyzer = MomentumStrengthAnalyzer(config)
    
    # 分析股票池
    print(f"📊 开始分析 {len(stock_list)} 只股票...")
    results = analyzer.analyze_stock_pool(stock_list)
    
    if not results:
        print("❌ 没有有效的分析结果")
        return
    
    # 过滤强势股票
    filtered_results = analyzer.filter_by_strength_criteria(
        results, 
        min_score=args.min_score,
        strength_ranks=['强势', '中等'],
        action_signals=['买入', '观望']
    )
    
    print(f"✅ 分析完成！")
    print(f"   总股票数: {len(results)}")
    print(f"   符合条件: {len(filtered_results)}")
    
    # 生成报告
    report = analyzer.generate_strength_report(results)
    print("\n" + report)
    
    # 保存结果
    if args.save_report:
        result_file = analyzer.save_analysis_results(results)
        
        # 保存文本报告
        report_file = result_file.replace('.json', '_report.txt')
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📄 报告已保存:")
        print(f"   数据文件: {result_file}")
        print(f"   文本报告: {report_file}")

if __name__ == "__main__":
    main()