#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【MA13强势回调短线筛选器 - 增强版】
基于doc/0912_short/文档要求，实现两阶段筛选：
1. 日线筛选：底部稳定 → 爆发强势 → MA13回调
2. 小时线评分：超跌反弹模型 + 中继确认模型

参照当前工程的confluence_scorer评分方式进行改造
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta

from data_handler import get_full_data_with_indicators
from data_loader import get_multi_timeframe_data, resample_5min_to_other_timeframes
from confluence_scorer import ConfluenceScorer

logger = logging.getLogger(__name__)

@dataclass
class MA13ScreenResult:
    """MA13筛选结果"""
    stock_code: str
    stock_name: str = ""
    
    # 日线筛选结果
    daily_qualified: bool = False
    daily_stage: str = ""  # 海选/精选/择时
    daily_score: float = 0.0
    
    # 小时线评分结果
    hourly_score: float = 0.0
    hourly_model: str = ""  # oversold_rebound/continuation_confirm
    hourly_signals: Dict = None
    
    # 综合评分
    total_score: float = 0.0
    confidence: float = 0.0
    recommendation: Dict = None
    
    # 关键价位
    key_levels: Dict = None
    
    # 市场阶段
    market_phase: str = ""
    
    def __post_init__(self):
        if self.hourly_signals is None:
            self.hourly_signals = {}
        if self.recommendation is None:
            self.recommendation = {}
        if self.key_levels is None:
            self.key_levels = {}

class EnhancedMA13Screener:
    """
    【MA13强势回调短线筛选器 - 增强版】
    
    核心逻辑：
    1. 日线四步筛选：海选(底部稳定) → 精选(日线爆发) → 择时(MA13回调) → 确认(小时线验证)
    2. 小时线双模型：超跌反弹模型 + 中继确认模型
    3. 融合评分：参照confluence_scorer的评分方式
    """
    
    def __init__(self):
        self.confluence_scorer = ConfluenceScorer()
        
        # 日线筛选参数
        self.daily_params = {
            # 海选参数
            'accumulation_days': 60,  # 底部盘整最少天数
            'box_volatility_max': 0.20,  # 箱体波动率上限
            'ma60_slope_min': 0.0,  # MA60斜率最小值
            
            # 精选参数
            'breakout_days': 10,  # 突破确认天数
            'breakout_gain_min': 0.20,  # 突破涨幅最小值
            'volume_ratio_min': 1.2,  # 成交量放大倍数
            
            # 择时参数
            'pullback_max': 0.15,  # 最大回调幅度
            'ma13_support_tolerance': 0.02,  # MA13支撑容忍度
            'rsi_support_min': 50,  # RSI支撑最小值
        }
        
        # 小时线评分参数
        self.hourly_params = {
            # 超跌反弹模型
            'oversold_kdj_max': 30,  # KDJ超卖阈值
            'oversold_rsi_max': 35,  # RSI超卖阈值
            'macd_underwater_cross': True,  # MACD水下金叉
            
            # 中继确认模型
            'continuation_kdj_min': 50,  # KDJ中继最小值
            'continuation_rsi_min': 60,  # RSI中继最小值
            'macd_above_zero': True,  # MACD零轴上方
            'macd_refuse_death_cross': True,  # 拒绝死叉
        }
        
        # 评分权重（参照confluence_scorer）
        self.scoring_weights = {
            'daily_stage_weight': 0.4,  # 日线阶段权重
            'hourly_model_weight': 0.3,  # 小时线模型权重
            'technical_signals_weight': 0.2,  # 技术信号权重
            'market_phase_weight': 0.1,  # 市场阶段权重
        }
        
        # 评分阈值
        self.score_thresholds = {
            'min_daily_score': 60,  # 日线最低分数
            'min_hourly_score': 50,  # 小时线最低分数
            'min_total_score': 70,  # 总分最低分数
            'high_confidence_score': 85,  # 高信心度分数
        }

    def screen_stocks(self, stock_codes: List[str]) -> List[MA13ScreenResult]:
        """
        批量筛选股票
        
        Args:
            stock_codes: 股票代码列表
            
        Returns:
            筛选结果列表
        """
        results = []
        
        for stock_code in stock_codes:
            try:
                result = self.analyze_single_stock(stock_code)
                if result and result.total_score >= self.score_thresholds['min_total_score']:
                    results.append(result)
            except Exception as e:
                logger.error(f"分析股票 {stock_code} 失败: {e}")
                continue
        
        # 按总分排序
        results.sort(key=lambda x: x.total_score, reverse=True)
        return results

    def analyze_single_stock(self, stock_code: str) -> Optional[MA13ScreenResult]:
        """
        分析单只股票
        
        Args:
            stock_code: 股票代码
            
        Returns:
            分析结果
        """
        # 获取日线数据
        daily_df = get_full_data_with_indicators(stock_code)
        if daily_df is None or len(daily_df) < 100:
            return None
        
        # 初始化结果
        result = MA13ScreenResult(stock_code=stock_code)
        
        # 第一阶段：日线筛选
        daily_analysis = self._analyze_daily_data(daily_df, stock_code)
        result.daily_qualified = daily_analysis['qualified']
        result.daily_stage = daily_analysis['stage']
        result.daily_score = daily_analysis['score']
        
        # 如果日线不符合条件，直接返回
        if not result.daily_qualified:
            return result
        
        # 第二阶段：小时线分析
        hourly_analysis = self._analyze_hourly_data(stock_code, daily_df)
        if hourly_analysis:
            result.hourly_score = hourly_analysis['score']
            result.hourly_model = hourly_analysis['model']
            result.hourly_signals = hourly_analysis['signals']
        
        # 第三阶段：市场阶段识别
        market_phase_analysis = self._analyze_market_phase(daily_df)
        result.market_phase = market_phase_analysis['phase']
        
        # 第四阶段：综合评分
        result.total_score = self._calculate_total_score(result)
        result.confidence = self._calculate_confidence(result)
        
        # 第五阶段：生成建议
        result.recommendation = self._generate_recommendation(result, daily_df)
        result.key_levels = self._calculate_key_levels(daily_df)
        
        return result

    def _analyze_daily_data(self, df: pd.DataFrame, stock_code: str) -> Dict:
        """
        日线数据分析 - 四步筛选法
        
        Args:
            df: 日线数据
            stock_code: 股票代码
            
        Returns:
            分析结果字典
        """
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # 步骤1：海选 - 底部稳定
        accumulation_score = self._check_accumulation_phase(df)
        if accumulation_score < 20:
            return {'qualified': False, 'stage': 'accumulation_failed', 'score': accumulation_score}
        
        # 步骤2：精选 - 日线爆发
        breakout_score = self._check_breakout_phase(df)
        if breakout_score < 20:
            return {'qualified': False, 'stage': 'breakout_failed', 'score': accumulation_score + breakout_score}
        
        # 步骤3：择时 - MA13回调
        pullback_score = self._check_pullback_phase(df)
        if pullback_score < 15:
            return {'qualified': False, 'stage': 'pullback_failed', 'score': accumulation_score + breakout_score + pullback_score}
        
        total_daily_score = accumulation_score + breakout_score + pullback_score
        
        return {
            'qualified': total_daily_score >= self.score_thresholds['min_daily_score'],
            'stage': 'ma13_pullback_ready',
            'score': total_daily_score
        }

    def _check_accumulation_phase(self, df: pd.DataFrame) -> float:
        """
        检查积累期（底部稳定）
        
        Args:
            df: 日线数据
            
        Returns:
            积累期得分 (0-30分)
        """
        score = 0.0
        
        # 获取过去3-6个月的数据
        lookback_days = min(180, len(df))
        recent_data = df.tail(lookback_days)
        
        if len(recent_data) < 60:
            return score
        
        # 检查箱体震荡特征
        price_high = recent_data['high'].max()
        price_low = recent_data['low'].min()
        box_height = (price_high - price_low) / price_low
        
        # 箱体波动率评分 (0-10分)
        if box_height <= self.daily_params['box_volatility_max']:
            score += 10 * (1 - box_height / self.daily_params['box_volatility_max'])
        
        # MA60趋势评分 (0-10分)
        if 'ma60' in recent_data.columns:
            ma60_start = recent_data['ma60'].iloc[0]
            ma60_end = recent_data['ma60'].iloc[-1]
            ma60_slope = (ma60_end - ma60_start) / ma60_start if ma60_start > 0 else 0
            
            if ma60_slope >= self.daily_params['ma60_slope_min']:
                score += 10 * min(ma60_slope / 0.1, 1.0)  # 最高10分
        
        # 底部时间评分 (0-10分)
        accumulation_days = len(recent_data)
        if accumulation_days >= self.daily_params['accumulation_days']:
            score += 10 * min(accumulation_days / 120, 1.0)  # 120天满分
        
        return min(score, 30.0)

    def _check_breakout_phase(self, df: pd.DataFrame) -> float:
        """
        检查突破期（日线爆发）
        
        Args:
            df: 日线数据
            
        Returns:
            突破期得分 (0-30分)
        """
        score = 0.0
        
        # 获取最近的突破数据
        recent_data = df.tail(30)  # 最近30天
        current_price = recent_data['close'].iloc[-1]
        
        # 寻找突破点
        breakout_days = self.daily_params['breakout_days']
        if len(recent_data) < breakout_days:
            return score
        
        # 计算突破涨幅
        base_price = recent_data['close'].iloc[-(breakout_days+1)]
        breakout_gain = (current_price - base_price) / base_price
        
        # 突破涨幅评分 (0-15分)
        if breakout_gain >= self.daily_params['breakout_gain_min']:
            score += 15 * min(breakout_gain / 0.4, 1.0)  # 40%涨幅满分
        
        # 成交量确认评分 (0-10分)
        if 'volume' in recent_data.columns:
            recent_volume = recent_data['volume'].tail(breakout_days).mean()
            base_volume = recent_data['volume'].head(20).mean()
            volume_ratio = recent_volume / base_volume if base_volume > 0 else 1.0
            
            if volume_ratio >= self.daily_params['volume_ratio_min']:
                score += 10 * min((volume_ratio - 1.0) / 1.0, 1.0)  # 2倍量满分
        
        # 均线多头排列评分 (0-5分)
        if all(col in recent_data.columns for col in ['ma5', 'ma13', 'ma30']):
            latest = recent_data.iloc[-1]
            if latest['ma5'] > latest['ma13'] > latest['ma30']:
                score += 5
        
        return min(score, 30.0)

    def _check_pullback_phase(self, df: pd.DataFrame) -> float:
        """
        检查回调期（MA13回调）
        
        Args:
            df: 日线数据
            
        Returns:
            回调期得分 (0-25分)
        """
        score = 0.0
        
        recent_data = df.tail(20)  # 最近20天
        if len(recent_data) < 10:
            return score
        
        current_price = recent_data['close'].iloc[-1]
        
        # 寻找近期高点
        recent_high = recent_data['high'].max()
        pullback_ratio = (recent_high - current_price) / recent_high
        
        # 回调幅度评分 (0-10分)
        if 0.05 <= pullback_ratio <= self.daily_params['pullback_max']:
            # 5%-15%回调为最佳区间
            optimal_pullback = 0.10
            deviation = abs(pullback_ratio - optimal_pullback)
            score += 10 * (1 - deviation / 0.05)
        
        # MA13支撑评分 (0-10分)
        if 'ma13' in recent_data.columns:
            ma13_current = recent_data['ma13'].iloc[-1]
            ma13_distance = abs(current_price - ma13_current) / ma13_current
            
            if ma13_distance <= self.daily_params['ma13_support_tolerance']:
                score += 10 * (1 - ma13_distance / self.daily_params['ma13_support_tolerance'])
        
        # RSI支撑评分 (0-5分)
        if 'rsi6' in recent_data.columns:
            rsi_current = recent_data['rsi6'].iloc[-1]
            if rsi_current >= self.daily_params['rsi_support_min']:
                score += 5
        
        return min(score, 25.0)

    def _analyze_hourly_data(self, stock_code: str, daily_df: pd.DataFrame) -> Optional[Dict]:
        """
        小时线数据分析 - 双模型评分
        
        Args:
            stock_code: 股票代码
            daily_df: 日线数据
            
        Returns:
            小时线分析结果
        """
        try:
            # 获取多时间框架数据
            multi_data = get_multi_timeframe_data(stock_code)
            
            if not multi_data['data_status']['min5_available']:
                # 如果没有5分钟数据，使用日线数据模拟小时线分析
                return self._simulate_hourly_analysis(daily_df)
            
            # 重采样为小时线数据
            timeframes = resample_5min_to_other_timeframes(multi_data['min5_data'])
            
            if '60min' not in timeframes or timeframes['60min'].empty:
                return self._simulate_hourly_analysis(daily_df)
            
            hourly_df = timeframes['60min']
            
            # 计算小时线技术指标
            hourly_df = self._calculate_hourly_indicators(hourly_df)
            
            # 双模型评分
            oversold_score = self._evaluate_oversold_model(hourly_df)
            continuation_score = self._evaluate_continuation_model(hourly_df)
            
            # 选择最佳模型
            if oversold_score > continuation_score:
                return {
                    'score': oversold_score,
                    'model': 'oversold_rebound',
                    'signals': self._extract_oversold_signals(hourly_df)
                }
            else:
                return {
                    'score': continuation_score,
                    'model': 'continuation_confirm',
                    'signals': self._extract_continuation_signals(hourly_df)
                }
                
        except Exception as e:
            logger.error(f"小时线分析失败 {stock_code}: {e}")
            return self._simulate_hourly_analysis(daily_df)

    def _simulate_hourly_analysis(self, daily_df: pd.DataFrame) -> Dict:
        """
        模拟小时线分析（当没有分时数据时）
        
        Args:
            daily_df: 日线数据
            
        Returns:
            模拟的小时线分析结果
        """
        recent_data = daily_df.tail(5)
        latest = recent_data.iloc[-1]
        
        # 基于日线指标模拟小时线评分
        score = 0.0
        model = 'simulated'
        signals = {}
        
        # MACD评分
        if 'dif' in latest and 'dea' in latest:
            if latest['dif'] > latest['dea']:
                score += 20
                signals['macd_golden_cross'] = True
        
        # KDJ评分
        if 'j' in latest:
            j_value = latest['j']
            if 20 <= j_value <= 80:
                score += 15
                signals['kdj_moderate'] = True
        
        # RSI评分
        if 'rsi6' in latest:
            rsi_value = latest['rsi6']
            if 40 <= rsi_value <= 70:
                score += 10
                signals['rsi_healthy'] = True
        
        return {
            'score': min(score, 50.0),
            'model': model,
            'signals': signals
        }

    def _calculate_hourly_indicators(self, hourly_df: pd.DataFrame) -> pd.DataFrame:
        """
        计算小时线技术指标
        
        Args:
            hourly_df: 小时线数据
            
        Returns:
            包含技术指标的小时线数据
        """
        # 这里应该调用indicators模块计算技术指标
        # 为了简化，我们使用简单的移动平均和基础指标
        
        # 移动平均线
        hourly_df['ma5'] = hourly_df['close'].rolling(5).mean()
        hourly_df['ma20'] = hourly_df['close'].rolling(20).mean()
        
        # 简化的MACD
        exp1 = hourly_df['close'].ewm(span=12).mean()
        exp2 = hourly_df['close'].ewm(span=26).mean()
        hourly_df['dif'] = exp1 - exp2
        hourly_df['dea'] = hourly_df['dif'].ewm(span=9).mean()
        hourly_df['macd'] = hourly_df['dif'] - hourly_df['dea']
        
        # 简化的RSI
        delta = hourly_df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        hourly_df['rsi'] = 100 - (100 / (1 + rs))
        
        return hourly_df

    def _evaluate_oversold_model(self, hourly_df: pd.DataFrame) -> float:
        """
        评估超跌反弹模型
        
        Args:
            hourly_df: 小时线数据
            
        Returns:
            模型得分 (0-50分)
        """
        if len(hourly_df) < 20:
            return 0.0
        
        score = 0.0
        latest = hourly_df.iloc[-1]
        
        # MACD水下金叉 (0-20分)
        if 'dif' in latest and 'dea' in latest and 'macd' in latest:
            if latest['dif'] > latest['dea'] and latest['macd'] < 0:
                # 检查是否刚刚金叉
                prev_data = hourly_df.iloc[-5:-1]
                if any(prev_data['dif'] <= prev_data['dea']):
                    score += 20
        
        # KDJ超卖反弹 (0-15分)
        if 'rsi' in latest:  # 用RSI模拟KDJ
            rsi_value = latest['rsi']
            if rsi_value <= self.hourly_params['oversold_rsi_max']:
                # 检查是否从更低位置反弹
                recent_rsi = hourly_df['rsi'].tail(10)
                if rsi_value > recent_rsi.min():
                    score += 15
        
        # 成交量确认 (0-10分)
        if 'volume' in hourly_df.columns:
            recent_volume = hourly_df['volume'].tail(5).mean()
            base_volume = hourly_df['volume'].tail(20).mean()
            if recent_volume > base_volume * 1.1:
                score += 10
        
        # 止跌K线形态 (0-5分)
        if len(hourly_df) >= 3:
            recent_closes = hourly_df['close'].tail(3)
            if recent_closes.iloc[-1] > recent_closes.iloc[-2]:
                score += 5
        
        return min(score, 50.0)

    def _evaluate_continuation_model(self, hourly_df: pd.DataFrame) -> float:
        """
        评估中继确认模型
        
        Args:
            hourly_df: 小时线数据
            
        Returns:
            模型得分 (0-50分)
        """
        if len(hourly_df) < 20:
            return 0.0
        
        score = 0.0
        latest = hourly_df.iloc[-1]
        
        # MACD零轴上方拒绝死叉 (0-20分)
        if 'dif' in latest and 'dea' in latest and 'macd' in latest:
            if latest['macd'] > 0 and latest['dif'] > latest['dea']:
                # 检查是否拒绝死叉
                recent_data = hourly_df.tail(10)
                min_macd = recent_data['macd'].min()
                if min_macd > -0.01:  # 几乎没有跌破零轴
                    score += 20
        
        # KDJ中轴金叉 (0-15分)
        if 'rsi' in latest:  # 用RSI模拟KDJ
            rsi_value = latest['rsi']
            if self.hourly_params['continuation_rsi_min'] <= rsi_value <= 80:
                score += 15
        
        # 均线支撑 (0-10分)
        if 'ma20' in latest:
            if latest['close'] > latest['ma20']:
                score += 10
        
        # Higher Low形态 (0-5分)
        if len(hourly_df) >= 10:
            recent_lows = hourly_df['low'].tail(10)
            if len(recent_lows) >= 2:
                if recent_lows.iloc[-1] > recent_lows.iloc[-5]:
                    score += 5
        
        return min(score, 50.0)

    def _extract_oversold_signals(self, hourly_df: pd.DataFrame) -> Dict:
        """提取超跌反弹信号"""
        latest = hourly_df.iloc[-1]
        return {
            'macd_underwater_cross': latest.get('dif', 0) > latest.get('dea', 0) and latest.get('macd', 0) < 0,
            'rsi_oversold_bounce': latest.get('rsi', 50) <= 35,
            'volume_increase': True,  # 简化处理
            'hammer_candle': False,  # 需要K线形态分析
        }

    def _extract_continuation_signals(self, hourly_df: pd.DataFrame) -> Dict:
        """提取中继确认信号"""
        latest = hourly_df.iloc[-1]
        return {
            'macd_above_zero': latest.get('macd', 0) > 0,
            'macd_refuse_death_cross': True,  # 简化处理
            'rsi_middle_range': 50 <= latest.get('rsi', 50) <= 80,
            'higher_low_pattern': True,  # 需要形态分析
        }

    def _analyze_market_phase(self, df: pd.DataFrame) -> Dict:
        """
        分析市场阶段
        
        Args:
            df: 日线数据
            
        Returns:
            市场阶段分析结果
        """
        # 使用confluence_scorer的市场阶段识别
        try:
            phase_result = self.confluence_scorer.detect_market_phase(df, len(df) - 1)
            return {
                'phase': phase_result.get('phase', 'unknown'),
                'confidence': phase_result.get('confidence', 0.5)
            }
        except Exception as e:
            logger.error(f"市场阶段分析失败: {e}")
            return {'phase': 'unknown', 'confidence': 0.5}

    def _calculate_total_score(self, result: MA13ScreenResult) -> float:
        """
        计算综合得分
        
        Args:
            result: 筛选结果
            
        Returns:
            综合得分
        """
        weights = self.scoring_weights
        
        # 基础分数
        daily_weighted = result.daily_score * weights['daily_stage_weight']
        hourly_weighted = result.hourly_score * weights['hourly_model_weight']
        
        # 市场阶段加权
        phase_bonus = 0.0
        if result.market_phase in ['markup', 'accumulation']:
            phase_bonus = 10 * weights['market_phase_weight']
        
        # 技术信号加权
        signal_bonus = 0.0
        if result.hourly_signals:
            signal_count = sum(1 for v in result.hourly_signals.values() if v)
            signal_bonus = min(signal_count * 5, 20) * weights['technical_signals_weight']
        
        total = daily_weighted + hourly_weighted + phase_bonus + signal_bonus
        return min(total, 100.0)

    def _calculate_confidence(self, result: MA13ScreenResult) -> float:
        """
        计算信心度
        
        Args:
            result: 筛选结果
            
        Returns:
            信心度 (0-1)
        """
        confidence = 0.0
        
        # 基于总分的基础信心度
        confidence += result.total_score / 100.0 * 0.6
        
        # 日线阶段完整性加成
        if result.daily_stage == 'ma13_pullback_ready':
            confidence += 0.2
        
        # 小时线模型确认加成
        if result.hourly_model in ['oversold_rebound', 'continuation_confirm']:
            confidence += 0.1
        
        # 市场阶段适宜性加成
        if result.market_phase in ['markup', 'accumulation']:
            confidence += 0.1
        
        return min(confidence, 1.0)

    def _generate_recommendation(self, result: MA13ScreenResult, df: pd.DataFrame) -> Dict:
        """
        生成操作建议
        
        Args:
            result: 筛选结果
            df: 日线数据
            
        Returns:
            操作建议字典
        """
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # 基于总分和信心度确定操作
        if result.total_score >= self.score_thresholds['high_confidence_score']:
            action = 'buy_heavy'
            position_size = 0.7
        elif result.total_score >= self.score_thresholds['min_total_score']:
            if result.hourly_model == 'oversold_rebound':
                action = 'buy_light'
                position_size = 0.3
            else:
                action = 'buy_moderate'
                position_size = 0.5
        else:
            action = 'wait'
            position_size = 0.0
        
        # 计算风险收益比
        ma13_price = latest.get('ma13', current_price)
        stop_loss = ma13_price * 0.95  # MA13下方5%
        target_1 = current_price * 1.15  # 15%目标
        target_2 = current_price * 1.25  # 25%目标
        
        risk = (current_price - stop_loss) / current_price
        reward = (target_1 - current_price) / current_price
        risk_reward_ratio = reward / risk if risk > 0 else 0
        
        return {
            'action': action,
            'position_size': position_size,
            'confidence': result.confidence * 100,
            'risk_reward_ratio': risk_reward_ratio,
            'entry_timing': result.hourly_model,
            'hold_days': '3-8天',
            'stop_loss_pct': risk * 100,
            'target_gain_pct': reward * 100,
        }

    def _calculate_key_levels(self, df: pd.DataFrame) -> Dict:
        """
        计算关键价位
        
        Args:
            df: 日线数据
            
        Returns:
            关键价位字典
        """
        latest = df.iloc[-1]
        current_price = latest['close']
        
        # 支撑位
        ma13_support = latest.get('ma13', current_price)
        ma30_support = latest.get('ma30', current_price)
        
        # 阻力位
        recent_high = df.tail(20)['high'].max()
        
        # 目标位
        target_1 = current_price * 1.15
        target_2 = current_price * 1.25
        
        # 止损位
        stop_loss = ma13_support * 0.95
        
        return {
            'current_price': current_price,
            'support_1_upper': ma13_support,
            'support_1_lower': ma13_support * 0.98,
            'support_2_upper': ma30_support,
            'support_2_lower': ma30_support * 0.98,
            'resistance_1': recent_high,
            'target_1': target_1,
            'target_2': target_2,
            'stop_loss': stop_loss,
        }

# 全局实例
enhanced_ma13_screener = EnhancedMA13Screener()