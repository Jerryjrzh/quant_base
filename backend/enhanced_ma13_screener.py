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

from backend.data_handler import get_full_data_with_indicators
from backend.data_loader import get_multi_timeframe_data, resample_5min_to_other_timeframes, fetch_hourly_kline
from backend.confluence_scorer import ConfluenceScorer

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
        
        # 日线筛选参数 - 根据Grok建议放宽标准
        self.daily_params = {
            # 海选参数 - 放宽积累期要求
            'accumulation_days': 45,  # 底部盘整最少天数 (从60降至45)
            'box_volatility_max': 0.25,  # 箱体波动率上限 (从0.20放宽至0.25)
            'ma60_slope_min': -0.001,  # MA60斜率最小值 (允许轻微下降)
            
            # 精选参数
            'breakout_days': 10,  # 突破确认天数
            'breakout_gain_min': 0.15,  # 突破涨幅最小值 (从0.20降至0.15)
            'volume_ratio_min': 1.1,  # 成交量放大倍数 (从1.2降至1.1)
            
            # 择时参数 - 增加浅回调奖励
            'pullback_max': 0.15,  # 最大回调幅度
            'pullback_tolerance': 0.03,  # MA13支撑容忍度 (从0.02放宽至0.03)
            'rsi_support_min': 45,  # RSI支撑最小值 (从50降至45)
        }
        
        # 小时线评分参数 - 根据Grok建议放宽参数
        self.hourly_params = {
            # 超跌反弹模型 - 放宽超卖阈值
            'oversold_kdj_max': 40,  # KDJ超卖阈值 (从30放宽至40)
            'oversold_rsi_max': 35,  # RSI超卖阈值
            'macd_underwater_cross': True,  # MACD水下金叉
            
            # 中继确认模型 - 放宽RSI要求
            'continuation_kdj_min': 50,  # KDJ中继最小值
            'continuation_rsi_min': 50,  # RSI中继最小值 (从60降至50)
            'macd_above_zero': True,  # MACD零轴上方
            'macd_refuse_death_cross': True,  # 拒绝死叉
        }
        
        # 评分权重（参照confluence_scorer）- 根据Grok评估调整
        self.scoring_weights = {
            'daily_stage_weight': 0.4,  # 日线阶段权重
            'hourly_model_weight': 0.3,  # 小时线模型权重
            'technical_signals_weight': 0.25,  # 技术信号权重 (从0.2提升至0.25)
            'market_phase_weight': 0.05,  # 市场阶段权重 (从0.1降至0.05以平衡)
        }
        
        # 评分阈值 - 根据Grok评估进一步放宽标准
        self.score_thresholds = {
            'min_daily_score': 35,  # 日线最低分数 (从40进一步降至35)
            'min_hourly_score': 25,  # 小时线最低分数 (从30降至25)
            'min_total_score': 60,  # 总分最低分数 (保持60)
            'high_confidence_score': 80,  # 高信心度分数 (从85降至80)
        }
        
        # 两阶段架构参数 - 新增
        self.stage1_params = {
            'backtrack_days': 30,  # 回溯天数寻找爆发起点
            'explosion_vol_multiplier': 1.5,  # 爆发成交量倍数
            'explosion_rise_threshold': 0.15,  # 爆发涨幅阈值
            'pool_qualification_threshold': 70,  # 历史资格池门槛
        }

    def screen_stocks(self, stock_codes: List[str], use_two_stage: bool = True) -> List[MA13ScreenResult]:
        """
        批量筛选股票 - 支持两阶段架构
        
        Args:
            stock_codes: 股票代码列表
            use_two_stage: 是否使用两阶段架构
            
        Returns:
            筛选结果列表
        """
        if use_two_stage:
            # 第一阶段：历史形态资格审查
            qualified_pool = self.run_historical_qualification(stock_codes)
            logger.info(f"历史资格审查完成，合格股票池: {len(qualified_pool)}只")
            
            # 第二阶段：对合格股票进行实时择时分析
            results = []
            for stock_code, qual_score in qualified_pool.items():
                try:
                    result = self.analyze_single_stock(stock_code, stage1_qual=qual_score)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.error(f"第二阶段分析股票 {stock_code} 失败: {e}")
                    continue
        else:
            # 传统单阶段筛选
            results = []
            for stock_code in stock_codes:
                try:
                    # 动量预过滤器：获取动量信息
                    momentum_info = self._momentum_pre_filter(stock_code)
                    if not momentum_info['pass']:
                        logger.debug(f"股票 {stock_code} 未通过动量预过滤")
                        continue
                    
                    result = self.analyze_single_stock(stock_code)
                    if result:
                        # 将动量信息整合到结果中，用于后续奖励计算
                        result.momentum_info = momentum_info
                        results.append(result)
                except Exception as e:
                    logger.error(f"分析股票 {stock_code} 失败: {e}")
                    continue
        
        # 按总分排序
        results.sort(key=lambda x: x.total_score, reverse=True)
        return results

    def run_historical_qualification(self, stock_list: List[str]) -> Dict[str, float]:
        """
        第一阶段：历史形态资格审查
        回答问题："这只股票在历史上是否走出了'底部积累 → 强势突破'的漂亮形态？"
        
        Args:
            stock_list: 股票代码列表
            
        Returns:
            Dict[股票代码, 资格得分]: 通过资格审查的股票池
        """
        qualified_pool = {}
        
        for stock_code in stock_list:
            try:
                daily_df = get_full_data_with_indicators(stock_code)
                if daily_df is None or len(daily_df) < 90:
                    continue
                
                # 寻找爆发起点
                recent_data = daily_df.tail(self.stage1_params['backtrack_days'])
                explosion_idx = self._find_explosion_start(recent_data, daily_df)
                
                if explosion_idx == -1:
                    logger.debug(f"{stock_code}: 未找到明确的爆发起点")
                    continue
                
                # 分析爆发前的积累期
                pre_explosion_df = daily_df.iloc[:explosion_idx]
                if len(pre_explosion_df) < 60:
                    continue
                
                acc_score = self._check_accumulation_phase(pre_explosion_df)
                
                # 分析爆发后的突破期
                post_explosion_df = daily_df.iloc[explosion_idx:]
                break_score = self._check_breakout_phase(post_explosion_df)
                
                # 计算历史资格得分 (积累40% + 突破60%)
                qual_score = acc_score * 0.4 + break_score * 0.6
                
                if qual_score >= self.stage1_params['pool_qualification_threshold']:
                    qualified_pool[stock_code] = qual_score
                    logger.info(f"{stock_code}: 历史资格得分 {qual_score:.1f} (积累:{acc_score:.1f}, 突破:{break_score:.1f})")
                
            except Exception as e:
                logger.error(f"历史资格审查失败 {stock_code}: {e}")
                continue
        
        return qualified_pool

    def _find_explosion_start(self, recent_data: pd.DataFrame, full_df: pd.DataFrame) -> int:
        """
        寻找爆发起点：成交量显著放大 + 价格快速拉升的时间点
        
        Args:
            recent_data: 最近N天数据
            full_df: 完整历史数据
            
        Returns:
            爆发起点在完整数据中的索引，-1表示未找到
        """
        try:
            if len(recent_data) < 10 or 'volume' not in recent_data.columns:
                return -1
            
            # 计算20日均量作为基准
            base_volume = full_df['volume'].tail(60).head(40).mean()  # 排除最近20天
            if base_volume <= 0:
                return -1
            
            # 寻找成交量放大且价格上涨的点
            for i in range(len(recent_data) - 5):  # 保留最后5天用于确认
                current_idx = len(full_df) - len(recent_data) + i
                
                # 检查成交量放大
                current_vol = recent_data.iloc[i]['volume']
                vol_ratio = current_vol / base_volume
                
                if vol_ratio < self.stage1_params['explosion_vol_multiplier']:
                    continue
                
                # 检查后续5日涨幅
                if i + 5 < len(recent_data):
                    start_price = recent_data.iloc[i]['close']
                    end_price = recent_data.iloc[i + 5]['close']
                    rise_ratio = (end_price - start_price) / start_price
                    
                    if rise_ratio >= self.stage1_params['explosion_rise_threshold']:
                        logger.debug(f"找到爆发起点: 索引{current_idx}, 量比{vol_ratio:.2f}, 5日涨幅{rise_ratio:.2%}")
                        return current_idx
            
            return -1
            
        except Exception as e:
            logger.error(f"寻找爆发起点失败: {e}")
            return -1

    def analyze_single_stock(self, stock_code: str, stage1_qual: float = None) -> Optional[MA13ScreenResult]:
        """
        分析单只股票 - 支持两阶段架构，完全解耦评分逻辑
        
        Args:
            stock_code: 股票代码
            stage1_qual: 第一阶段历史资格得分（可选）
            
        Returns:
            分析结果
        """
        # 获取日线数据
        daily_df = get_full_data_with_indicators(stock_code)
        if daily_df is None or len(daily_df) < 100:
            return None
        
        # 初始化结果
        result = MA13ScreenResult(stock_code=stock_code)
        
        # 获取预过滤器信息（用于后续奖励计算）
        result.pre_filter = self._momentum_pre_filter(stock_code)
        
        if stage1_qual is not None:
            # 两阶段模式：第二阶段专注实时择时
            result.stage1_qualification = stage1_qual
            daily_analysis = self._analyze_recent_pullback(daily_df)  # 专注最近回调
        else:
            # 传统模式：完整日线分析
            daily_analysis = self._analyze_daily_data(daily_df, stock_code)
        
        result.daily_stage = daily_analysis['stage']
        result.daily_score = daily_analysis['score']
        
        # 【关键修复】：完全移除早期返回，始终执行所有分析阶段
        
        # 小时线分析（无论日线得分如何都执行）
        hourly_analysis = self._analyze_hourly_data(stock_code, daily_df)
        if hourly_analysis:
            result.hourly_score = hourly_analysis['score']
            result.hourly_model = hourly_analysis['model']
            result.hourly_signals = hourly_analysis['signals']
        
        # 市场阶段识别
        market_phase_analysis = self._analyze_market_phase(daily_df, result.pre_filter)
        result.market_phase = market_phase_analysis['phase']
        
        # 综合评分（始终计算，整合所有奖励）
        result.total_score = self._calculate_total_score(result)
        result.confidence = self._calculate_confidence(result)
        
        # 【修复后的合格判断】：基于总分门槛，不依赖单项得分
        result.daily_qualified = result.total_score >= self.score_thresholds['min_total_score']
        
        # 生成建议和关键价位
        result.recommendation = self._generate_recommendation(result, daily_df)
        result.key_levels = self._calculate_key_levels(daily_df)
        
        return result

    def _analyze_recent_pullback(self, df: pd.DataFrame) -> Dict:
        """
        第二阶段专用：分析最近回调情况（专注择时）
        
        Args:
            df: 日线数据
            
        Returns:
            回调分析结果
        """
        # 只关注最近20天的回调情况
        recent_data = df.tail(20)
        if len(recent_data) < 10:
            return {'qualified': False, 'stage': 'data_insufficient', 'score': 0}
        
        # 专注回调质量评分
        pullback_score = self._check_pullback_phase(recent_data)
        
        # 当前支撑评分
        support_score = self._check_current_support(recent_data)
        
        total_score = pullback_score + support_score
        
        return {
            'qualified': total_score >= 20,  # 降低门槛
            'stage': 'pullback_timing' if total_score >= 20 else 'pullback_weak',
            'score': total_score
        }

    def _check_current_support(self, recent_data: pd.DataFrame) -> float:
        """
        检查当前支撑强度
        
        Args:
            recent_data: 最近数据
            
        Returns:
            支撑得分 (0-15分)
        """
        score = 0.0
        latest = recent_data.iloc[-1]
        current_price = latest['close']
        
        # MA13支撑 (0-10分)
        if 'ma13' in latest:
            ma13_price = latest['ma13']
            distance_ratio = abs(current_price - ma13_price) / ma13_price
            
            if distance_ratio <= self.daily_params['pullback_tolerance']:
                score += 10 * (1 - distance_ratio / self.daily_params['pullback_tolerance'])
        
        # 成交量支撑 (0-5分)
        if 'volume' in recent_data.columns:
            recent_vol = recent_data['volume'].tail(3).mean()
            base_vol = recent_data['volume'].head(10).mean()
            if recent_vol > base_vol * 1.1:
                score += 5
        
        return min(score, 15.0)

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
        检查积累期（底部稳定）- 放宽积累期判断标准
        
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
        
        # 检查箱体震荡特征 - 放宽波动率容忍度
        price_high = recent_data['high'].max()
        price_low = recent_data['low'].min()
        box_height = (price_high - price_low) / price_low
        
        # 箱体波动率评分 (0-10分) - 从0.20放宽至0.25
        max_volatility = 0.25
        if box_height <= max_volatility:
            score += 10 * (1 - box_height / max_volatility)
        elif box_height <= 0.35:  # 给予部分分数，不完全否决
            score += 5 * (1 - (box_height - max_volatility) / 0.10)
        
        # MA60趋势评分 (0-15分) - 提高权重并增加斜率奖励
        if 'ma60' in recent_data.columns:
            ma60_values = recent_data['ma60'].dropna()
            if len(ma60_values) >= 30:
                # 使用线性回归计算斜率
                x = np.arange(len(ma60_values))
                ma60_slope = np.polyfit(x, ma60_values, 1)[0] / ma60_values.iloc[0] if ma60_values.iloc[0] > 0 else 0
                
                if ma60_slope >= 0:  # 上升趋势
                    score += 10 + min(ma60_slope * 1000, 5)  # 基础10分+斜率奖励最高5分
                elif ma60_slope >= -0.001:  # 轻微下降也给予部分分数
                    score += 5
        
        # 底部时间评分 (0-10分) - 降低时间要求
        accumulation_days = len(recent_data)
        if accumulation_days >= 45:  # 从60天降至45天
            score += 10 * min(accumulation_days / 90, 1.0)  # 从120天降至90天满分
        
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
        检查回调期（MA13回调）- 增加浅回调奖励机制
        
        Args:
            df: 日线数据
            
        Returns:
            回调期得分 (0-30分) - 提高上限
        """
        score = 0.0
        
        recent_data = df.tail(20)  # 最近20天
        if len(recent_data) < 5:  # 降低数据要求
            return score
        
        current_price = recent_data['close'].iloc[-1]
        
        # 寻找近期高点
        recent_high = recent_data['high'].max()
        pullback_ratio = (recent_high - current_price) / recent_high
        
        # 【Grok建议】回调幅度评分 (0-20分) - 增加浅回调奖励
        if 0.01 <= pullback_ratio <= self.daily_params['pullback_max']:  # 从2%降至1%
            if pullback_ratio <= 0.05:  # 浅回调奖励 (<=5%)
                score += 20  # 满分奖励强势股
                logger.debug(f"浅回调奖励: {pullback_ratio:.2%} -> +20分")
            elif pullback_ratio <= 0.10:  # 适中回调 (5%-10%)
                score += 15
            else:  # 深度回调 (10%-15%)
                score += 10
        elif pullback_ratio <= 0.03:  # 极浅回调也给予部分分数
            score += 25  # 超强势股特别奖励
            logger.debug(f"极浅回调特别奖励: {pullback_ratio:.2%} -> +25分")
        
        # MA13支撑评分 (0-10分) - 使用放宽后的容忍度
        if 'ma13' in recent_data.columns:
            ma13_current = recent_data['ma13'].iloc[-1]
            ma13_distance = abs(current_price - ma13_current) / ma13_current
            
            # 使用配置中的放宽容忍度
            tolerance = self.daily_params['pullback_tolerance']  # 0.03
            if ma13_distance <= tolerance:
                score += 10 * (1 - ma13_distance / tolerance)
                logger.debug(f"MA13支撑: 距离{ma13_distance:.2%} -> +{10 * (1 - ma13_distance / tolerance):.1f}分")
        
        return min(score, 30.0)  # 提高上限至30分

    def _analyze_hourly_data(self, stock_code: str, daily_df: pd.DataFrame) -> Optional[Dict]:
        """
        小时线数据分析 - 双模型评分 (修复数据获取和列名问题)
        
        Args:
            stock_code: 股票代码
            daily_df: 日线数据
            
        Returns:
            小时线分析结果
        """
        try:
            # 使用修复后的fetch_hourly_kline函数
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
            
            hourly_df = fetch_hourly_kline(stock_code, start_date, end_date)
            
            # 【关键修复】：强制修复列名问题
            if not hourly_df.empty:
                # 确保有datetime列
                if 'datetime' not in hourly_df.columns:
                    if hourly_df.index.name == 'datetime' or isinstance(hourly_df.index, pd.DatetimeIndex):
                        hourly_df = hourly_df.reset_index()
                        if 'index' in hourly_df.columns:
                            hourly_df = hourly_df.rename(columns={'index': 'datetime'})
                    elif 'date' in hourly_df.columns:
                        hourly_df = hourly_df.rename(columns={'date': 'datetime'})
                
                logger.info(f"小时线数据列名: {list(hourly_df.columns)}, 数据量: {len(hourly_df)}")
            
            # 如果小时线数据不足，使用后备方案但给予基础分数
            if hourly_df.empty or len(hourly_df) < 5:  # 从12降至5，更宽松
                logger.warning(f"小时线数据不足 {stock_code} (数据量: {len(hourly_df)}), 使用后备方案")
                return self._hourly_fallback_analysis(daily_df)
            
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
            return self._hourly_fallback_analysis(daily_df)

    def _hourly_fallback_analysis(self, daily_df: pd.DataFrame) -> Dict:
        """
        小时线分析后备方案 - 使用日线指标代理评分
        
        Args:
            daily_df: 日线数据
            
        Returns:
            后备分析结果
        """
        recent_data = daily_df.tail(5)
        latest = recent_data.iloc[-1]
        
        # 基于日线指标模拟小时线评分 - 提高基础分数
        score = 0.0
        model = 'daily_proxy'
        signals = {}
        
        # MACD评分 - 提高权重
        if 'dif' in latest and 'dea' in latest:
            if latest['dif'] > latest['dea']:
                score += 25  # 从20提升至25
                signals['macd_golden_cross'] = True
                
                # 额外奖励：MACD强势
                if latest['dif'] > 0:
                    score += 5
                    signals['macd_above_zero'] = True
        
        # KDJ评分 - 放宽范围
        if 'j' in latest:
            j_value = latest['j']
            if 30 <= j_value <= 90:  # 从20-80放宽至30-90
                score += 20  # 从15提升至20
                signals['kdj_moderate'] = True
        
        # RSI评分 - 放宽要求
        if 'rsi6' in latest:
            rsi_value = latest['rsi6']
            if 35 <= rsi_value <= 75:  # 从40-70放宽至35-75
                score += 15  # 从10提升至15
                signals['rsi_healthy'] = True
        
        # 成交量确认
        if 'volume' in daily_df.columns:
            recent_vol = daily_df['volume'].tail(3).mean()
            base_vol = daily_df['volume'].tail(20).mean()
            if recent_vol > base_vol * 1.1:
                score += 10
                signals['volume_amplified'] = True
        
        return {
            'score': min(score, 60.0),  # 提高上限至60分
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
        
        # KDJ超卖反弹 (0-15分) - 放宽KDJ阈值
        if 'rsi' in latest:  # 用RSI模拟KDJ
            rsi_value = latest['rsi']
            if rsi_value <= self.hourly_params['oversold_kdj_max']:  # 使用放宽后的40阈值
                # 检查是否从更低位置反弹
                recent_rsi = hourly_df['rsi'].tail(10)
                if rsi_value > recent_rsi.min():
                    score += 15
        
        # 成交量确认 (0-10分) - 增加成交量奖励
        if 'volume' in hourly_df.columns:
            recent_volume = hourly_df['volume'].tail(5).mean()
            base_volume = hourly_df['volume'].tail(20).mean()
            vol_ratio = recent_volume / base_volume if base_volume > 0 else 1.0
            if vol_ratio > 1.1:
                score += 10
                # 【中优先级修复】额外成交量奖励
                if vol_ratio > 1.5:
                    score += 10  # 成交量大幅放大额外奖励
        
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
        
        # KDJ中轴金叉 (0-15分) - 使用放宽后的RSI要求
        if 'rsi' in latest:  # 用RSI模拟KDJ
            rsi_value = latest['rsi']
            if self.hourly_params['continuation_rsi_min'] <= rsi_value <= 80:  # 现在是50而不是60
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

    def _analyze_market_phase(self, df: pd.DataFrame, pre_filter: Dict = None) -> Dict:
        """
        分析市场阶段 - 增加后备方案和默认判断
        
        Args:
            df: 日线数据
            
        Returns:
            市场阶段分析结果
        """
        # 使用confluence_scorer的市场阶段识别
        try:
            phase_result = self.confluence_scorer.detect_market_phase(df, len(df) - 1)
            phase = phase_result.get('phase', '')
            confidence = phase_result.get('confidence', 0.5)
            
            # 如果confluence_scorer返回空或unknown，使用简化判断
            if not phase or phase == 'unknown':
                phase = self._simple_market_phase_detection(df, pre_filter)
                confidence = 0.6
            
            return {
                'phase': phase,
                'confidence': confidence
            }
        except Exception as e:
            logger.error(f"市场阶段分析失败: {e}")
            # 使用简化的市场阶段检测作为后备
            phase = self._simple_market_phase_detection(df, pre_filter)
            return {'phase': phase, 'confidence': 0.5}
    
    def _simple_market_phase_detection(self, df: pd.DataFrame, pre_filter: Dict = None) -> str:
        """
        简化的市场阶段检测 - 作为后备方案
        
        Args:
            df: 日线数据
            
        Returns:
            市场阶段字符串
        """
        try:
            recent_data = df.tail(20)
            if len(recent_data) < 10:
                return 'neutral'
            
            # 计算价格趋势
            current_price = recent_data['close'].iloc[-1]
            price_20d_ago = recent_data['close'].iloc[0]
            price_trend = (current_price - price_20d_ago) / price_20d_ago
            
            # 计算成交量趋势
            vol_ratio = 1.0
            if 'volume' in recent_data.columns:
                recent_vol = recent_data['volume'].tail(5).mean()
                base_vol = recent_data['volume'].head(10).mean()
                vol_ratio = recent_vol / base_vol if base_vol > 0 else 1.0
            
            # 计算MA斜率
            ma_slope = 0.0
            if 'ma30' in recent_data.columns:
                ma30_values = recent_data['ma30'].dropna()
                if len(ma30_values) >= 10:
                    x = np.arange(len(ma30_values))
                    ma_slope = np.polyfit(x, ma30_values, 1)[0] / ma30_values.iloc[0] if ma30_values.iloc[0] > 0 else 0
            
            # 判断市场阶段
            phase = None
            if price_trend > 0.05 and vol_ratio > 1.1 and ma_slope > 0:
                phase = 'markup'  # 上升阶段
            elif price_trend > -0.05 and vol_ratio > 1.2:
                phase = 'accumulation'  # 积累阶段
            elif price_trend < -0.10:
                phase = 'decline'  # 下跌阶段
            else:
                phase = 'neutral'  # 中性阶段
            
            # 【新增】默认markup逻辑：如果预过滤器显示强势，默认为markup
            if not phase or phase == 'neutral':
                if pre_filter and pre_filter.get('pass', False):
                    rise_pct = pre_filter.get('rise_pct', 0)
                    pre_vol_ratio = pre_filter.get('vol_ratio', 1.0)
                    
                    if pre_vol_ratio > 1.1 or rise_pct > 15:
                        phase = 'markup'
                        logger.info(f"默认设置为markup阶段: vol_ratio={pre_vol_ratio:.2f}, rise_pct={rise_pct:.1f}%")
            
            logger.info(f"市场阶段检测: {phase} (price_trend={price_trend:.3f}, vol_ratio={vol_ratio:.2f}, ma_slope={ma_slope:.4f})")
            return phase
                
        except Exception as e:
            logger.error(f"简化市场阶段检测失败: {e}")
            # 如果有预过滤器信息且显示强势，默认为markup
            if pre_filter and pre_filter.get('pass', False):
                return 'markup'
            return 'neutral'

    def _calculate_total_score(self, result: MA13ScreenResult) -> float:
        """
        计算综合得分 - 完全重构奖励逻辑，确保所有奖励都能正确应用
        
        Args:
            result: 筛选结果
            
        Returns:
            综合得分
        """
        # 基础分数（确保最低分数）
        daily_score = max(result.daily_score, 0)
        hourly_score = max(result.hourly_score, 0)
        base_total = daily_score + hourly_score
        
        # 【Grok建议】市场阶段奖励 - 自动应用默认markup
        phase_bonus = 0.0
        if result.market_phase == 'markup':
            phase_bonus = 15  # 上升阶段奖励15分
        elif result.market_phase == 'accumulation':
            phase_bonus = 10  # 积累阶段奖励10分
        elif result.market_phase == 'neutral':
            phase_bonus = 5   # 中性阶段基础分
        else:  # distribution, decline
            phase_bonus = 0   # 不扣分，只是不加分
        
        # 【Grok建议】强制应用动量奖励
        momentum_bonus = 0.0
        if hasattr(result, 'pre_filter') and result.pre_filter:
            rise_pct = result.pre_filter.get('rise_pct', 0)
            vol_ratio = result.pre_filter.get('vol_ratio', 1.0)
            
            # 动量奖励：降低门槛，按比例给分
            if rise_pct >= 10:  # 从15%降至10%
                momentum_bonus = min(rise_pct / 10 * 3, 12)  # 按比例给分，最高12分
                logger.info(f"动量奖励: rise_pct={rise_pct:.1f}% -> +{momentum_bonus:.1f}分")
            
            # 成交量奖励
            if vol_ratio >= 1.1:
                vol_bonus = min((vol_ratio - 1.0) * 10, 8)
                momentum_bonus += vol_bonus
                logger.info(f"成交量奖励: vol_ratio={vol_ratio:.2f} -> +{vol_bonus:.1f}分")
            
            # 热门板块奖励
            if result.pre_filter.get('tag_bonus', False):
                momentum_bonus += 2
                logger.info(f"热门板块奖励: +2分")
        
        # 【Grok建议】强制应用信号奖励
        signal_bonus = 0.0
        if result.hourly_model and result.hourly_signals:
            signal_count = sum(1 for v in result.hourly_signals.values() if v)
            signal_bonus = 2 * signal_count  # 每个信号+2分
            logger.info(f"信号奖励: {signal_count}个信号 -> +{signal_bonus}分")
        
        # 【新增】历史资格奖励（两阶段模式）
        history_bonus = 0.0
        if hasattr(result, 'stage1_qualification') and result.stage1_qualification:
            if result.stage1_qualification >= 80:
                history_bonus = 10
                logger.info(f"历史资格奖励: qual={result.stage1_qualification:.1f} -> +{history_bonus}分")
        
        # 【新增】小时线模型奖励
        model_bonus = 0.0
        if result.hourly_model:
            if result.hourly_model == 'continuation_confirm':
                model_bonus = 5  # 中继确认额外奖励
            elif result.hourly_model == 'oversold_rebound':
                model_bonus = 3  # 超跌反弹额外奖励
            logger.info(f"模型奖励: {result.hourly_model} -> +{model_bonus}分")
        
        # 计算最终总分
        total = base_total + phase_bonus + momentum_bonus + signal_bonus + history_bonus + model_bonus
        
        logger.info(f"总分详细: 基础={base_total:.1f} + 阶段={phase_bonus} + 动量={momentum_bonus:.1f} + 信号={signal_bonus} + 历史={history_bonus} + 模型={model_bonus} = {total:.1f}")
        
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
        
        # 【Grok建议】改进操作建议逻辑 - 降低门槛，增加操作性
        if result.total_score >= self.score_thresholds['min_total_score'] and result.confidence > 0.2:
            # 根据模型类型确定操作
            if result.hourly_model == 'continuation_confirm':
                action = 'buy_continuation'
                position_size = 0.5  # 中继确认50%仓位
            elif result.hourly_model == 'oversold_rebound':
                action = 'buy_oversold'
                position_size = 0.3  # 超跌反弹30%仓位
            else:
                action = 'buy_moderate'
                position_size = 0.4  # 其他情况40%仓位
        elif result.total_score >= 50:  # 给予观察建议
            action = 'watch'
            position_size = 0.0
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

    def _momentum_pre_filter(self, stock_code: str) -> Dict:
        """
        动量预过滤器 - 快速筛选有潜力的强势股，返回详细信息用于后续奖励
        
        Args:
            stock_code: 股票代码
            
        Returns:
            Dict: 包含pass, rise_pct, vol_ratio等信息
        """
        try:
            # 获取基础日线数据
            daily_df = get_full_data_with_indicators(stock_code)
            if daily_df is None or len(daily_df) < 30:
                return {'pass': False, 'rise_pct': 0, 'vol_ratio': 1.0}
            
            recent_data = daily_df.tail(20)
            current_price = recent_data['close'].iloc[-1]
            
            # 检查20日内涨幅是否>10%（从12%放宽至10%）
            low_20d = recent_data['low'].min()
            rise_pct = (current_price - low_20d) / low_20d * 100
            
            # 检查成交量是否放大
            vol_ratio = 1.0
            if 'volume' in recent_data.columns:
                recent_vol = recent_data['volume'].tail(5).mean()
                base_vol = recent_data['volume'].head(15).mean()
                vol_ratio = recent_vol / base_vol if base_vol > 0 else 1.0
            
            # 【Grok建议】进一步放宽过滤条件
            pass_filter = (rise_pct >= 8 or vol_ratio >= 1.1)  # 涨幅8%或成交量1.1倍（改为或条件）
            
            # 检查是否为热门板块（扩展标签）
            import re
            tag_bonus = False
            if re.match(r'00[2-3]\d{3}|688\d{3}', stock_code):  # 002xxx, 003xxx, 688xxx
                tag_bonus = True
            
            result = {
                'pass': pass_filter or tag_bonus,  # 热门板块可以放宽条件
                'rise_pct': rise_pct,
                'vol_ratio': vol_ratio,
                'tag_bonus': tag_bonus
            }
            
            logger.debug(f"动量预过滤 {stock_code}: 涨幅{rise_pct:.1f}%, 量比{vol_ratio:.2f}, 通过={result['pass']}")
            return result
            
        except Exception as e:
            logger.error(f"动量预过滤失败 {stock_code}: {e}")
            return {'pass': True, 'rise_pct': 0, 'vol_ratio': 1.0, 'tag_bonus': False}  # 出错时不过滤

# 全局实例
enhanced_ma13_screener = EnhancedMA13Screener()