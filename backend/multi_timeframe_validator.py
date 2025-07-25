#!/usr/bin/env python3
"""
多周期验证系统
在不同的时间周期测试确认强势股票的表现
包括日线、周线、月线的综合分析
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
class TimeframeConfig:
    """多周期配置"""
    # 时间周期设置
    daily_period: int = 60      # 日线分析周期
    weekly_period: int = 20     # 周线分析周期  
    monthly_period: int = 6     # 月线分析周期
    
    # MA参数
    ma_periods: List[int] = None  # [5, 10, 20, 60]
    
    # 强势判断标准
    daily_strength_threshold: float = 0.8    # 日线强势阈值
    weekly_strength_threshold: float = 0.85  # 周线强势阈值
    monthly_strength_threshold: float = 0.9  # 月线强势阈值
    
    # 趋势确认参数
    trend_confirmation_days: int = 5  # 趋势确认天数
    volume_confirmation: bool = True  # 是否需要成交量确认
    
    def __post_init__(self):
        if self.ma_periods is None:
            self.ma_periods = [5, 10, 20, 60]

@dataclass
class TimeframeAnalysis:
    """单个时间周期分析结果"""
    timeframe: str  # 'daily', 'weekly', 'monthly'
    
    # 趋势分析
    trend_direction: str  # '上升', '下降', '震荡'
    trend_strength: float  # 趋势强度 0-1
    trend_duration: int   # 趋势持续天数
    
    # MA分析
    ma_alignment: bool    # MA是否多头排列
    price_above_ma: Dict[int, float]  # 价格在各MA之上的比例
    ma_slope: Dict[int, float]        # 各MA的斜率
    
    # 支撑阻力
    support_level: float  # 支撑位
    resistance_level: float  # 阻力位
    current_position: float  # 当前位置 (0-1, 0=支撑, 1=阻力)
    
    # 成交量分析
    volume_trend: str     # '放量', '缩量', '正常'
    volume_price_sync: bool  # 量价配合
    
    # 强势评分
    strength_score: float  # 该周期强势得分 0-100

@dataclass
class MultiTimeframeResult:
    """多周期综合分析结果"""
    symbol: str
    analysis_date: str
    
    # 各周期分析
    daily_analysis: TimeframeAnalysis
    weekly_analysis: TimeframeAnalysis
    monthly_analysis: TimeframeAnalysis
    
    # 综合评估
    overall_trend: str        # 综合趋势方向
    trend_consistency: float  # 趋势一致性 0-1
    multi_timeframe_strength: float  # 多周期强势得分 0-100
    
    # 操作建议
    entry_timing: str         # '立即', '回调', '突破', '观望'
    risk_level: str          # '低', '中', '高'
    holding_period: str      # '短期', '中期', '长期'
    
    # 关键价位
    key_support: float       # 关键支撑
    key_resistance: float    # 关键阻力
    stop_loss: float         # 建议止损位
    take_profit: List[float] # 建议止盈位

class MultiTimeframeValidator:
    """多周期验证器"""
    
    def __init__(self, config: TimeframeConfig = None):
        self.config = config or TimeframeConfig()
        self.logger = self._setup_logger()
        self.data_cache = {}
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志"""
        logger = logging.getLogger('MultiTimeframeValidator')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger
    
    def load_stock_data(self, symbol: str, days: int = 300) -> Optional[pd.DataFrame]:
        """加载股票数据"""
        cache_key = f"{symbol}_{days}"
        if cache_key in self.data_cache:
            return self.data_cache[cache_key]
        
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
            market = symbol[:2]
            file_path = os.path.join(base_path, market, 'lday', f'{symbol}.day')
            
            if not os.path.exists(file_path):
                return None
            
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 100:
                return None
            
            # 过滤到指定日期范围
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            
            if len(df) < 50:
                return None
            
            self.data_cache[cache_key] = df
            return df
            
        except Exception as e:
            self.logger.warning(f"加载股票数据失败 {symbol}: {e}")
            return None
    
    def convert_to_timeframe(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """转换到指定时间周期"""
        if timeframe == 'daily':
            return df
        
        try:
            # 设置重采样规则
            if timeframe == 'weekly':
                rule = 'W'
            elif timeframe == 'monthly':
                rule = 'M'
            else:
                return df
            
            # 重采样
            resampled = df.resample(rule).agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
            
            return resampled
            
        except Exception as e:
            self.logger.warning(f"时间周期转换失败 {timeframe}: {e}")
            return df
    
    def analyze_trend(self, df: pd.DataFrame, period: int) -> Tuple[str, float, int]:
        """分析趋势方向和强度"""
        if len(df) < period:
            return '震荡', 0.5, 0
        
        try:
            # 使用最近period天的数据
            recent_data = df.tail(period)
            
            # 计算趋势线斜率
            x = np.arange(len(recent_data))
            y = recent_data['close'].values
            
            # 线性回归计算斜率
            slope = np.polyfit(x, y, 1)[0]
            
            # 计算R²确定趋势强度
            correlation = np.corrcoef(x, y)[0, 1]
            trend_strength = abs(correlation)
            
            # 确定趋势方向
            if slope > 0 and trend_strength > 0.3:
                trend_direction = '上升'
            elif slope < 0 and trend_strength > 0.3:
                trend_direction = '下降'
            else:
                trend_direction = '震荡'
            
            # 计算趋势持续天数
            if trend_direction != '震荡':
                # 寻找趋势开始点
                duration = 1
                for i in range(len(recent_data) - 2, -1, -1):
                    if trend_direction == '上升':
                        if recent_data['close'].iloc[i] < recent_data['close'].iloc[i + 1]:
                            duration += 1
                        else:
                            break
                    else:  # 下降
                        if recent_data['close'].iloc[i] > recent_data['close'].iloc[i + 1]:
                            duration += 1
                        else:
                            break
            else:
                duration = 0
            
            return trend_direction, trend_strength, duration
            
        except Exception as e:
            self.logger.warning(f"趋势分析失败: {e}")
            return '震荡', 0.5, 0
    
    def analyze_ma_alignment(self, df: pd.DataFrame) -> Tuple[bool, Dict[int, float], Dict[int, float]]:
        """分析MA排列和价格位置"""
        price_above_ma = {}
        ma_slope = {}
        
        try:
            mas = {}
            for period in self.config.ma_periods:
                if len(df) >= period:
                    mas[period] = df['close'].rolling(window=period).mean()
                    
                    # 计算价格在MA之上的比例
                    above_ratio = (df['close'] > mas[period]).sum() / len(df)
                    price_above_ma[period] = above_ratio
                    
                    # 计算MA斜率
                    if len(mas[period]) >= 5:
                        recent_ma = mas[period].tail(5)
                        x = np.arange(len(recent_ma))
                        slope = np.polyfit(x, recent_ma.values, 1)[0]
                        ma_slope[period] = slope
                    else:
                        ma_slope[period] = 0
            
            # 检查MA多头排列
            ma_alignment = True
            if len(mas) >= 2:
                sorted_periods = sorted(self.config.ma_periods)
                current_values = {}
                
                for period in sorted_periods:
                    if period in mas and not mas[period].empty:
                        current_values[period] = mas[period].iloc[-1]
                
                # 检查短期MA > 长期MA
                periods_list = list(current_values.keys())
                for i in range(len(periods_list) - 1):
                    short_period = periods_list[i]
                    long_period = periods_list[i + 1]
                    if current_values[short_period] <= current_values[long_period]:
                        ma_alignment = False
                        break
            
            return ma_alignment, price_above_ma, ma_slope
            
        except Exception as e:
            self.logger.warning(f"MA分析失败: {e}")
            return False, {}, {}
    
    def find_support_resistance(self, df: pd.DataFrame, period: int = 20) -> Tuple[float, float, float]:
        """寻找支撑阻力位"""
        try:
            if len(df) < period:
                current_price = df['close'].iloc[-1]
                return current_price * 0.95, current_price * 1.05, 0.5
            
            recent_data = df.tail(period)
            
            # 支撑位：最近period天的最低点
            support = recent_data['low'].min()
            
            # 阻力位：最近period天的最高点
            resistance = recent_data['high'].max()
            
            # 当前位置
            current_price = df['close'].iloc[-1]
            if resistance > support:
                current_position = (current_price - support) / (resistance - support)
            else:
                current_position = 0.5
            
            return support, resistance, current_position
            
        except Exception as e:
            self.logger.warning(f"支撑阻力分析失败: {e}")
            current_price = df['close'].iloc[-1] if not df.empty else 0
            return current_price * 0.95, current_price * 1.05, 0.5
    
    def analyze_volume(self, df: pd.DataFrame, period: int = 20) -> Tuple[str, bool]:
        """分析成交量"""
        try:
            if len(df) < period:
                return '正常', True
            
            recent_data = df.tail(period)
            
            # 计算平均成交量
            avg_volume = recent_data['volume'].mean()
            recent_volume = recent_data['volume'].tail(5).mean()
            
            # 成交量趋势
            if recent_volume > avg_volume * 1.5:
                volume_trend = '放量'
            elif recent_volume < avg_volume * 0.7:
                volume_trend = '缩量'
            else:
                volume_trend = '正常'
            
            # 量价配合分析
            price_changes = recent_data['close'].pct_change().tail(5)
            volume_changes = recent_data['volume'].pct_change().tail(5)
            
            # 计算量价相关性
            correlation = price_changes.corr(volume_changes)
            volume_price_sync = not pd.isna(correlation) and correlation > 0.3
            
            return volume_trend, volume_price_sync
            
        except Exception as e:
            self.logger.warning(f"成交量分析失败: {e}")
            return '正常', True
    
    def calculate_timeframe_strength(self, analysis: Dict) -> float:
        """计算单个时间周期的强势得分"""
        score = 0
        
        try:
            # 趋势得分 (30分)
            if analysis['trend_direction'] == '上升':
                trend_score = 30 * analysis['trend_strength']
            elif analysis['trend_direction'] == '下降':
                trend_score = 0
            else:  # 震荡
                trend_score = 15
            score += trend_score
            
            # MA排列得分 (25分)
            if analysis['ma_alignment']:
                score += 25
            else:
                score += 10
            
            # 价格位置得分 (20分)
            if analysis['price_above_ma']:
                avg_above_ratio = np.mean(list(analysis['price_above_ma'].values()))
                score += 20 * avg_above_ratio
            
            # 支撑阻力位置得分 (15分)
            if 0.3 <= analysis['current_position'] <= 0.7:
                score += 15  # 中间位置较安全
            elif analysis['current_position'] > 0.7:
                score += 10  # 接近阻力位
            else:
                score += 5   # 接近支撑位
            
            # 成交量得分 (10分)
            if analysis['volume_trend'] == '放量' and analysis['volume_price_sync']:
                score += 10
            elif analysis['volume_trend'] == '正常':
                score += 7
            else:
                score += 3
            
            return min(100, max(0, score))
            
        except Exception as e:
            self.logger.warning(f"强势得分计算失败: {e}")
            return 50
    
    def analyze_single_timeframe(self, df: pd.DataFrame, timeframe: str, period: int) -> TimeframeAnalysis:
        """分析单个时间周期"""
        
        # 转换到指定时间周期
        tf_data = self.convert_to_timeframe(df, timeframe)
        
        if tf_data.empty:
            # 返回默认值
            return TimeframeAnalysis(
                timeframe=timeframe,
                trend_direction='震荡',
                trend_strength=0.5,
                trend_duration=0,
                ma_alignment=False,
                price_above_ma={},
                ma_slope={},
                support_level=0,
                resistance_level=0,
                current_position=0.5,
                volume_trend='正常',
                volume_price_sync=True,
                strength_score=50
            )
        
        # 趋势分析
        trend_direction, trend_strength, trend_duration = self.analyze_trend(tf_data, period)
        
        # MA分析
        ma_alignment, price_above_ma, ma_slope = self.analyze_ma_alignment(tf_data)
        
        # 支撑阻力
        support_level, resistance_level, current_position = self.find_support_resistance(tf_data, period)
        
        # 成交量分析
        volume_trend, volume_price_sync = self.analyze_volume(tf_data, period)
        
        # 计算强势得分
        analysis_data = {
            'trend_direction': trend_direction,
            'trend_strength': trend_strength,
            'ma_alignment': ma_alignment,
            'price_above_ma': price_above_ma,
            'current_position': current_position,
            'volume_trend': volume_trend,
            'volume_price_sync': volume_price_sync
        }
        
        strength_score = self.calculate_timeframe_strength(analysis_data)
        
        return TimeframeAnalysis(
            timeframe=timeframe,
            trend_direction=trend_direction,
            trend_strength=trend_strength,
            trend_duration=trend_duration,
            ma_alignment=ma_alignment,
            price_above_ma=price_above_ma,
            ma_slope=ma_slope,
            support_level=support_level,
            resistance_level=resistance_level,
            current_position=current_position,
            volume_trend=volume_trend,
            volume_price_sync=volume_price_sync,
            strength_score=strength_score
        )
    
    def determine_overall_assessment(self, daily: TimeframeAnalysis, 
                                   weekly: TimeframeAnalysis, 
                                   monthly: TimeframeAnalysis) -> Tuple[str, float, float, str, str, str]:
        """确定综合评估"""
        
        # 趋势一致性
        trends = [daily.trend_direction, weekly.trend_direction, monthly.trend_direction]
        trend_counts = {trend: trends.count(trend) for trend in set(trends)}
        
        # 综合趋势方向
        overall_trend = max(trend_counts, key=trend_counts.get)
        
        # 趋势一致性得分
        max_count = max(trend_counts.values())
        trend_consistency = max_count / 3
        
        # 多周期强势得分 (加权平均)
        multi_timeframe_strength = (
            daily.strength_score * 0.4 +      # 日线权重40%
            weekly.strength_score * 0.35 +    # 周线权重35%
            monthly.strength_score * 0.25     # 月线权重25%
        )
        
        # 入场时机判断
        if (overall_trend == '上升' and trend_consistency >= 0.67 and 
            multi_timeframe_strength >= 70):
            if daily.current_position < 0.3:
                entry_timing = '立即'  # 接近支撑位
            elif daily.current_position > 0.8:
                entry_timing = '回调'  # 接近阻力位
            else:
                entry_timing = '立即'
        elif overall_trend == '上升' and multi_timeframe_strength >= 60:
            entry_timing = '回调'
        elif overall_trend == '震荡' and multi_timeframe_strength >= 50:
            entry_timing = '突破'
        else:
            entry_timing = '观望'
        
        # 风险等级
        if trend_consistency >= 0.67 and multi_timeframe_strength >= 70:
            risk_level = '低'
        elif trend_consistency >= 0.33 and multi_timeframe_strength >= 50:
            risk_level = '中'
        else:
            risk_level = '高'
        
        # 持有周期
        if monthly.trend_direction == '上升' and monthly.strength_score >= 70:
            holding_period = '长期'
        elif weekly.trend_direction == '上升' and weekly.strength_score >= 60:
            holding_period = '中期'
        else:
            holding_period = '短期'
        
        return (overall_trend, trend_consistency, multi_timeframe_strength, 
                entry_timing, risk_level, holding_period)
    
    def calculate_key_levels(self, daily: TimeframeAnalysis, 
                           weekly: TimeframeAnalysis, 
                           monthly: TimeframeAnalysis,
                           current_price: float) -> Tuple[float, float, float, List[float]]:
        """计算关键价位"""
        
        # 关键支撑 (取各周期支撑位的最高值)
        key_support = max(daily.support_level, weekly.support_level, monthly.support_level)
        
        # 关键阻力 (取各周期阻力位的最低值)
        key_resistance = min(daily.resistance_level, weekly.resistance_level, monthly.resistance_level)
        
        # 止损位 (支撑位下方3-5%)
        stop_loss = key_support * 0.95
        
        # 止盈位 (多个目标)
        take_profit = []
        
        # 第一目标：阻力位
        take_profit.append(key_resistance)
        
        # 第二目标：阻力位上方10%
        take_profit.append(key_resistance * 1.1)
        
        # 第三目标：基于风险收益比
        risk = current_price - stop_loss
        if risk > 0:
            take_profit.append(current_price + risk * 2)  # 1:2风险收益比
            take_profit.append(current_price + risk * 3)  # 1:3风险收益比
        
        # 排序并去重
        take_profit = sorted(list(set([tp for tp in take_profit if tp > current_price])))
        
        return key_support, key_resistance, stop_loss, take_profit[:4]  # 最多4个目标
    
    def validate_stock(self, symbol: str) -> Optional[MultiTimeframeResult]:
        """验证单只股票的多周期表现"""
        
        df = self.load_stock_data(symbol)
        if df is None:
            return None
        
        try:
            # 分析各个时间周期
            daily_analysis = self.analyze_single_timeframe(
                df, 'daily', self.config.daily_period
            )
            
            weekly_analysis = self.analyze_single_timeframe(
                df, 'weekly', self.config.weekly_period
            )
            
            monthly_analysis = self.analyze_single_timeframe(
                df, 'monthly', self.config.monthly_period
            )
            
            # 综合评估
            (overall_trend, trend_consistency, multi_timeframe_strength,
             entry_timing, risk_level, holding_period) = self.determine_overall_assessment(
                daily_analysis, weekly_analysis, monthly_analysis
            )
            
            # 计算关键价位
            current_price = df['close'].iloc[-1]
            key_support, key_resistance, stop_loss, take_profit = self.calculate_key_levels(
                daily_analysis, weekly_analysis, monthly_analysis, current_price
            )
            
            # 创建结果
            result = MultiTimeframeResult(
                symbol=symbol,
                analysis_date=datetime.now().strftime('%Y-%m-%d'),
                daily_analysis=daily_analysis,
                weekly_analysis=weekly_analysis,
                monthly_analysis=monthly_analysis,
                overall_trend=overall_trend,
                trend_consistency=trend_consistency,
                multi_timeframe_strength=multi_timeframe_strength,
                entry_timing=entry_timing,
                risk_level=risk_level,
                holding_period=holding_period,
                key_support=key_support,
                key_resistance=key_resistance,
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"多周期验证失败 {symbol}: {e}")
            return None
    
    def validate_stock_pool(self, stock_list: List[str]) -> List[MultiTimeframeResult]:
        """验证股票池"""
        self.logger.info(f"开始多周期验证 {len(stock_list)} 只股票")
        
        results = []
        
        def validate_single_stock(symbol):
            return self.validate_stock(symbol)
        
        # 并行验证
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(validate_single_stock, symbol) for symbol in stock_list]
            
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result)
        
        # 按多周期强势得分排序
        results.sort(key=lambda x: x.multi_timeframe_strength, reverse=True)
        
        self.logger.info(f"完成验证，有效结果 {len(results)} 个")
        return results
    
    def generate_validation_report(self, results: List[MultiTimeframeResult]) -> str:
        """生成验证报告"""
        
        if not results:
            return "没有验证结果"
        
        report = []
        report.append("=" * 80)
        report.append("🔍 多周期验证报告")
        report.append("=" * 80)
        
        # 统计概览
        total_stocks = len(results)
        strong_stocks = len([r for r in results if r.multi_timeframe_strength >= 70])
        medium_stocks = len([r for r in results if 50 <= r.multi_timeframe_strength < 70])
        weak_stocks = len([r for r in results if r.multi_timeframe_strength < 50])
        
        uptrend_stocks = len([r for r in results if r.overall_trend == '上升'])
        consistent_stocks = len([r for r in results if r.trend_consistency >= 0.67])
        
        report.append(f"\n📊 验证概览:")
        report.append(f"  总验证股票: {total_stocks}")
        report.append(f"  强势股票: {strong_stocks} ({strong_stocks/total_stocks:.1%})")
        report.append(f"  中等股票: {medium_stocks} ({medium_stocks/total_stocks:.1%})")
        report.append(f"  弱势股票: {weak_stocks} ({weak_stocks/total_stocks:.1%})")
        report.append(f"")
        report.append(f"  上升趋势: {uptrend_stocks} ({uptrend_stocks/total_stocks:.1%})")
        report.append(f"  趋势一致: {consistent_stocks} ({consistent_stocks/total_stocks:.1%})")
        
        # 多周期强势排行榜
        top_results = results[:15]
        
        report.append(f"\n🏆 多周期强势排行榜 (前15名):")
        report.append("-" * 90)
        report.append(f"{'排名':<4} {'代码':<10} {'综合得分':<8} {'趋势一致性':<10} {'综合趋势':<8} {'入场时机':<8} {'风险等级':<8}")
        report.append("-" * 90)
        
        for i, result in enumerate(top_results, 1):
            report.append(f"{i:<4} {result.symbol:<10} {result.multi_timeframe_strength:<8.1f} "
                        f"{result.trend_consistency:<10.2f} {result.overall_trend:<8} "
                        f"{result.entry_timing:<8} {result.risk_level:<8}")
        
        # 各周期强势分析
        report.append(f"\n📈 各周期强势分析:")
        report.append("-" * 60)
        
        daily_avg = np.mean([r.daily_analysis.strength_score for r in results])
        weekly_avg = np.mean([r.weekly_analysis.strength_score for r in results])
        monthly_avg = np.mean([r.monthly_analysis.strength_score for r in results])
        
        report.append(f"  日线平均强势: {daily_avg:.1f}")
        report.append(f"  周线平均强势: {weekly_avg:.1f}")
        report.append(f"  月线平均强势: {monthly_avg:.1f}")
        
        # 趋势分布
        daily_trends = [r.daily_analysis.trend_direction for r in results]
        weekly_trends = [r.weekly_analysis.trend_direction for r in results]
        monthly_trends = [r.monthly_analysis.trend_direction for r in results]
        
        report.append(f"\n📊 趋势分布:")
        report.append("-" * 40)
        
        for timeframe, trends in [('日线', daily_trends), ('周线', weekly_trends), ('月线', monthly_trends)]:
            up_count = trends.count('上升')
            down_count = trends.count('下降')
            side_count = trends.count('震荡')
            
            report.append(f"  {timeframe}: 上升{up_count}只 下降{down_count}只 震荡{side_count}只")
        
        # 操作建议统计
        entry_timings = [r.entry_timing for r in results]
        risk_levels = [r.risk_level for r in results]
        holding_periods = [r.holding_period for r in results]
        
        report.append(f"\n💡 操作建议分布:")
        report.append("-" * 40)
        
        for timing in ['立即', '回调', '突破', '观望']:
            count = entry_timings.count(timing)
            report.append(f"  {timing}: {count}只 ({count/total_stocks:.1%})")
        
        report.append(f"\n⚠️ 风险等级分布:")
        for risk in ['低', '中', '高']:
            count = risk_levels.count(risk)
            report.append(f"  {risk}风险: {count}只 ({count/total_stocks:.1%})")
        
        # 重点推荐
        immediate_buy = [r for r in results if r.entry_timing == '立即' and r.risk_level in ['低', '中']][:5]
        
        if immediate_buy:
            report.append(f"\n⭐ 重点推荐 (立即买入，风险可控):")
            report.append("-" * 80)
            
            for i, result in enumerate(immediate_buy, 1):
                current_price = 0  # 需要从数据中获取当前价格
                report.append(f"{i}. {result.symbol}")
                report.append(f"   多周期强势: {result.multi_timeframe_strength:.1f}")
                report.append(f"   趋势一致性: {result.trend_consistency:.2f}")
                report.append(f"   风险等级: {result.risk_level}")
                report.append(f"   关键支撑: ¥{result.key_support:.2f}")
                report.append(f"   关键阻力: ¥{result.key_resistance:.2f}")
                report.append(f"   建议止损: ¥{result.stop_loss:.2f}")
                if result.take_profit:
                    tp_str = " ".join([f"¥{tp:.2f}" for tp in result.take_profit[:2]])
                    report.append(f"   目标价位: {tp_str}")
                report.append("")
        
        # 操作策略建议
        report.append(f"\n📋 操作策略建议:")
        report.append("-" * 40)
        report.append(f"  1. 优先选择多周期趋势一致的股票")
        report.append(f"  2. 关注日线、周线、月线的强势得分")
        report.append(f"  3. 在关键支撑位附近分批建仓")
        report.append(f"  4. 严格按照止损位控制风险")
        report.append(f"  5. 根据持有周期调整仓位管理")
        
        return "\n".join(report)
    
    def save_validation_results(self, results: List[MultiTimeframeResult], filename: str = None):
        """保存验证结果"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'multi_timeframe_validation_{timestamp}.json'
        
        # 转换为可序列化的格式
        serializable_results = []
        for result in results:
            result_dict = asdict(result)
            serializable_results.append(result_dict)
        
        validation_data = {
            'timestamp': datetime.now().isoformat(),
            'config': asdict(self.config),
            'total_validated': len(results),
            'results': serializable_results,
            'summary': {
                'strong_stocks': len([r for r in results if r.multi_timeframe_strength >= 70]),
                'uptrend_stocks': len([r for r in results if r.overall_trend == '上升']),
                'consistent_stocks': len([r for r in results if r.trend_consistency >= 0.67]),
                'avg_strength': np.mean([r.multi_timeframe_strength for r in results]) if results else 0
            }
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(validation_data, f, ensure_ascii=False, indent=2, default=str)
        
        self.logger.info(f"验证结果已保存到: {filename}")
        return filename

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='多周期验证系统')
    parser.add_argument('--stock-list', required=True, help='股票列表文件或股票代码(逗号分隔)')
    parser.add_argument('--min-strength', type=float, default=60, help='最低强势得分')
    parser.add_argument('--save-report', action='store_true', help='保存验证报告')
    
    args = parser.parse_args()
    
    print("🔍 多周期验证系统")
    print("=" * 50)
    
    # 解析股票列表
    if os.path.exists(args.stock_list):
        # 从文件加载
        try:
            with open(args.stock_list, 'r', encoding='utf-8') as f:
                if args.stock_list.endswith('.json'):
                    data = json.load(f)
                    if 'strategy' in data and 'core_pool' in data['strategy']:
                        stock_list = [stock['symbol'] for stock in data['strategy']['core_pool']]
                    else:
                        stock_list = data if isinstance(data, list) else []
                else:
                    stock_list = [line.strip() for line in f if line.strip()]
        except Exception as e:
            print(f"❌ 加载股票列表失败: {e}")
            return
    else:
        # 从命令行参数解析
        stock_list = [s.strip() for s in args.stock_list.split(',')]
    
    if not stock_list:
        print("❌ 没有有效的股票列表")
        return
    
    print(f"📊 准备验证 {len(stock_list)} 只股票")
    
    # 创建验证器
    config = TimeframeConfig()
    validator = MultiTimeframeValidator(config)
    
    # 执行验证
    results = validator.validate_stock_pool(stock_list)
    
    if not results:
        print("❌ 没有有效的验证结果")
        return
    
    # 过滤结果
    filtered_results = [r for r in results if r.multi_timeframe_strength >= args.min_strength]
    
    print(f"✅ 验证完成！")
    print(f"   总验证数: {len(results)}")
    print(f"   符合条件: {len(filtered_results)}")
    
    # 生成报告
    report = validator.generate_validation_report(results)
    print("\n" + report)
    
    # 保存结果
    if args.save_report:
        result_file = validator.save_validation_results(results)
        
        # 保存文本报告
        report_file = result_file.replace('.json', '_report.txt')
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📄 报告已保存:")
        print(f"   数据文件: {result_file}")
        print(f"   文本报告: {report_file}")

if __name__ == "__main__":
    main()