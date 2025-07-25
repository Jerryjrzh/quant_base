#!/usr/bin/env python3
"""
多周期数据管理器
负责多时间框架数据的加载、同步、缓存和管理
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.dirname(__file__))

import data_loader
import indicators

class MultiTimeframeDataManager:
    """多周期数据管理器"""
    
    def __init__(self, cache_dir: str = "analysis_cache"):
        """初始化多周期数据管理器"""
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        
        # 定义支持的时间周期（使用新的pandas频率字符串格式）
        self.timeframes = {
            '5min': {'freq': '5min', 'description': '5分钟'},
            '15min': {'freq': '15min', 'description': '15分钟'},
            '30min': {'freq': '30min', 'description': '30分钟'},
            '1hour': {'freq': '1h', 'description': '1小时'},
            '4hour': {'freq': '4h', 'description': '4小时'},
            '1day': {'freq': '1D', 'description': '日线'},
            '1week': {'freq': '1W', 'description': '周线'}
        }
        
        # 周期权重（用于信号融合）
        self.timeframe_weights = {
            '1week': 0.40,   # 长期趋势权重（最高）
            '1day': 0.25,    # 主趋势权重
            '4hour': 0.20,   # 中期趋势权重
            '1hour': 0.10,   # 短期趋势权重
            '30min': 0.03,   # 入场时机权重
            '15min': 0.015,  # 精确入场权重
            '5min': 0.005    # 微调权重
        }
        
        # 数据缓存
        self.data_cache = {}
        self.indicators_cache = {}
        
        # 日志设置
        self.logger = logging.getLogger(__name__)
        
    def get_synchronized_data(self, stock_code: str, timeframes: List[str] = None) -> Dict:
        """获取时间同步的多周期数据"""
        if timeframes is None:
            timeframes = list(self.timeframes.keys())
        
        try:
            self.logger.info(f"获取{stock_code}的多周期数据: {timeframes}")
            
            # 检查缓存
            cache_key = f"{stock_code}_{'-'.join(timeframes)}"
            if cache_key in self.data_cache:
                cache_data = self.data_cache[cache_key]
                if self._is_cache_valid(cache_data):
                    return cache_data
            
            # 获取基础数据
            multi_data = data_loader.get_multi_timeframe_data(stock_code)
            
            if not multi_data['data_status']['daily_available'] and not multi_data['data_status']['min5_available']:
                return {'error': f'无法获取{stock_code}的基础数据'}
            
            # 构建多周期数据集
            synchronized_data = {
                'stock_code': stock_code,
                'timeframes': {},
                'alignment_info': {},
                'data_quality': {},
                'last_update': datetime.now().isoformat()
            }
            
            # 处理每个时间周期
            for timeframe in timeframes:
                try:
                    tf_data = self._get_timeframe_data(multi_data, timeframe)
                    if tf_data is not None and not tf_data.empty:
                        # 数据质量检查
                        quality_info = self._check_data_quality(tf_data, timeframe)
                        
                        synchronized_data['timeframes'][timeframe] = tf_data
                        synchronized_data['data_quality'][timeframe] = quality_info
                        
                        self.logger.info(f"  {timeframe}: {len(tf_data)} 条数据")
                    else:
                        self.logger.warning(f"  {timeframe}: 无数据")
                        
                except Exception as e:
                    self.logger.error(f"处理{timeframe}数据失败: {e}")
                    continue
            
            # 时间轴对齐
            if len(synchronized_data['timeframes']) > 1:
                alignment_info = self._align_timeframes(synchronized_data['timeframes'])
                synchronized_data['alignment_info'] = alignment_info
            
            # 缓存结果
            self.data_cache[cache_key] = synchronized_data
            
            return synchronized_data
            
        except Exception as e:
            self.logger.error(f"获取{stock_code}多周期数据失败: {e}")
            return {'error': str(e)}
    
    def _get_timeframe_data(self, multi_data: Dict, timeframe: str) -> Optional[pd.DataFrame]:
        """获取指定时间周期的数据"""
        try:
            if timeframe == '1day':
                # 日线数据
                return multi_data.get('daily_data')
            
            elif timeframe == '5min':
                # 5分钟数据
                return multi_data.get('min5_data')
            
            elif timeframe == '1week':
                # 周线数据需要从日线数据重采样
                daily_data = multi_data.get('daily_data')
                if daily_data is None or daily_data.empty:
                    return None
                return self._resample_data(daily_data, timeframe)
            
            else:
                # 其他周期需要从5分钟数据重采样
                min5_data = multi_data.get('min5_data')
                if min5_data is None or min5_data.empty:
                    return None
                
                return self._resample_data(min5_data, timeframe)
                
        except Exception as e:
            self.logger.error(f"获取{timeframe}数据失败: {e}")
            return None
    
    def _resample_data(self, min5_data: pd.DataFrame, target_timeframe: str) -> pd.DataFrame:
        """将5分钟数据重采样到目标时间周期"""
        try:
            freq = self.timeframes[target_timeframe]['freq']
            
            # 确保索引是DatetimeIndex
            if not isinstance(min5_data.index, pd.DatetimeIndex):
                if 'datetime' in min5_data.columns:
                    min5_data = min5_data.set_index('datetime')
                else:
                    return None
            
            # 重采样规则
            agg_rules = {
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }
            
            # 如果有amount列也处理
            if 'amount' in min5_data.columns:
                agg_rules['amount'] = 'sum'
            
            # 执行重采样
            resampled = min5_data.resample(freq).agg(agg_rules)
            
            # 移除空值行
            resampled = resampled.dropna()
            
            return resampled
            
        except Exception as e:
            self.logger.error(f"重采样到{target_timeframe}失败: {e}")
            return None
    
    def _align_timeframes(self, timeframes_data: Dict) -> Dict:
        """对齐不同周期的时间轴"""
        try:
            alignment_info = {
                'common_start_time': None,
                'common_end_time': None,
                'time_coverage': {},
                'data_gaps': {}
            }
            
            # 找到共同的时间范围
            start_times = []
            end_times = []
            
            for timeframe, df in timeframes_data.items():
                if df is not None and not df.empty:
                    # 确保索引是DatetimeIndex
                    if not isinstance(df.index, pd.DatetimeIndex):
                        self.logger.warning(f"{timeframe}数据索引不是DatetimeIndex，跳过时间对齐")
                        continue
                    
                    start_time = df.index[0]
                    end_time = df.index[-1]
                    
                    # 确保是Timestamp对象
                    if isinstance(start_time, pd.Timestamp) and isinstance(end_time, pd.Timestamp):
                        start_times.append(start_time)
                        end_times.append(end_time)
                        
                        alignment_info['time_coverage'][timeframe] = {
                            'start': start_time.isoformat(),
                            'end': end_time.isoformat(),
                            'count': len(df)
                        }
                    else:
                        self.logger.warning(f"{timeframe}数据时间格式异常，跳过时间对齐")
            
            if start_times and end_times:
                try:
                    max_start = max(start_times)
                    min_end = min(end_times)
                    alignment_info['common_start_time'] = max_start.isoformat()
                    alignment_info['common_end_time'] = min_end.isoformat()
                except Exception as e:
                    self.logger.error(f"计算共同时间范围失败: {e}")
                    alignment_info['common_start_time'] = None
                    alignment_info['common_end_time'] = None
            
            # 检查数据缺口
            for timeframe, df in timeframes_data.items():
                if df is not None and not df.empty:
                    gaps = self._detect_data_gaps(df, timeframe)
                    if gaps:
                        alignment_info['data_gaps'][timeframe] = gaps
            
            return alignment_info
            
        except Exception as e:
            self.logger.error(f"时间轴对齐失败: {e}")
            return {}
    
    def _detect_data_gaps(self, df: pd.DataFrame, timeframe: str) -> List[Dict]:
        """检测数据缺口"""
        try:
            gaps = []
            freq = self.timeframes[timeframe]['freq']
            
            # 生成期望的时间序列
            expected_times = pd.date_range(
                start=df.index[0],
                end=df.index[-1],
                freq=freq
            )
            
            # 找到缺失的时间点
            missing_times = expected_times.difference(df.index)
            
            if len(missing_times) > 0:
                # 将连续的缺失时间分组
                gap_groups = []
                current_group = [missing_times[0]]
                
                for i in range(1, len(missing_times)):
                    time_diff = missing_times[i] - missing_times[i-1]
                    expected_diff = pd.Timedelta(freq)
                    
                    if time_diff <= expected_diff * 1.5:  # 允许一定的误差
                        current_group.append(missing_times[i])
                    else:
                        gap_groups.append(current_group)
                        current_group = [missing_times[i]]
                
                gap_groups.append(current_group)
                
                # 转换为缺口信息
                for group in gap_groups:
                    gaps.append({
                        'start': group[0].isoformat(),
                        'end': group[-1].isoformat(),
                        'duration': len(group),
                        'timeframe': timeframe
                    })
            
            return gaps
            
        except Exception as e:
            self.logger.error(f"检测{timeframe}数据缺口失败: {e}")
            return []
    
    def _check_data_quality(self, df: pd.DataFrame, timeframe: str) -> Dict:
        """检查数据质量"""
        try:
            quality_info = {
                'total_records': len(df),
                'null_values': df.isnull().sum().to_dict(),
                'duplicate_timestamps': df.index.duplicated().sum(),
                'price_anomalies': 0,
                'volume_anomalies': 0,
                'quality_score': 1.0
            }
            
            if len(df) == 0:
                quality_info['quality_score'] = 0.0
                return quality_info
            
            # 检查价格异常
            if 'close' in df.columns:
                price_changes = df['close'].pct_change().abs()
                # 单周期涨跌幅超过20%视为异常
                price_anomalies = (price_changes > 0.20).sum()
                quality_info['price_anomalies'] = price_anomalies
            
            # 检查成交量异常
            if 'volume' in df.columns:
                volume_median = df['volume'].median()
                if volume_median > 0:
                    volume_ratios = df['volume'] / volume_median
                    # 成交量超过中位数50倍视为异常
                    volume_anomalies = (volume_ratios > 50).sum()
                    quality_info['volume_anomalies'] = volume_anomalies
            
            # 计算质量评分
            total_issues = (
                sum(quality_info['null_values'].values()) +
                quality_info['duplicate_timestamps'] +
                quality_info['price_anomalies'] +
                quality_info['volume_anomalies']
            )
            
            if len(df) > 0:
                quality_info['quality_score'] = max(0.0, 1.0 - (total_issues / len(df)))
            
            return quality_info
            
        except Exception as e:
            self.logger.error(f"检查{timeframe}数据质量失败: {e}")
            return {'quality_score': 0.0, 'error': str(e)}
    
    def calculate_multi_timeframe_indicators(self, stock_code: str, timeframes: List[str] = None) -> Dict:
        """计算多周期技术指标"""
        try:
            if timeframes is None:
                timeframes = list(self.timeframes.keys())
            
            # 检查指标缓存
            cache_key = f"{stock_code}_indicators_{'-'.join(timeframes)}"
            if cache_key in self.indicators_cache:
                cache_data = self.indicators_cache[cache_key]
                if self._is_cache_valid(cache_data):
                    return cache_data
            
            # 获取多周期数据
            sync_data = self.get_synchronized_data(stock_code, timeframes)
            if 'error' in sync_data:
                return sync_data
            
            indicators_result = {
                'stock_code': stock_code,
                'timeframes': {},
                'cross_timeframe_analysis': {},
                'last_update': datetime.now().isoformat()
            }
            
            # 为每个时间周期计算指标
            for timeframe in timeframes:
                df = sync_data['timeframes'].get(timeframe)
                if df is None or df.empty:
                    continue
                
                try:
                    tf_indicators = self._calculate_timeframe_indicators(df, timeframe)
                    indicators_result['timeframes'][timeframe] = tf_indicators
                    
                    self.logger.info(f"  {timeframe}指标计算完成")
                    
                except Exception as e:
                    self.logger.error(f"计算{timeframe}指标失败: {e}")
                    continue
            
            # 跨周期分析
            if len(indicators_result['timeframes']) > 1:
                cross_analysis = self._analyze_cross_timeframe_patterns(indicators_result['timeframes'])
                indicators_result['cross_timeframe_analysis'] = cross_analysis
            
            # 缓存结果
            self.indicators_cache[cache_key] = indicators_result
            
            return indicators_result
            
        except Exception as e:
            self.logger.error(f"计算{stock_code}多周期指标失败: {e}")
            return {'error': str(e)}
    
    def _calculate_timeframe_indicators(self, df: pd.DataFrame, timeframe: str) -> Dict:
        """计算单个时间周期的技术指标"""
        try:
            tf_indicators = {
                'timeframe': timeframe,
                'data_points': len(df),
                'indicators': {},
                'signals': {},
                'trend_analysis': {}
            }
            
            # 基础技术指标
            # MACD
            macd_values = indicators.calculate_macd(df)
            tf_indicators['indicators']['macd'] = {
                'dif': macd_values[0].tolist() if hasattr(macd_values[0], 'tolist') else [],
                'dea': macd_values[1].tolist() if hasattr(macd_values[1], 'tolist') else [],
                'histogram': (macd_values[0] - macd_values[1]).tolist() if len(macd_values) >= 2 else []
            }
            
            # KDJ
            kdj_values = indicators.calculate_kdj(df)
            tf_indicators['indicators']['kdj'] = {
                'k': kdj_values[0].tolist() if hasattr(kdj_values[0], 'tolist') else [],
                'd': kdj_values[1].tolist() if hasattr(kdj_values[1], 'tolist') else [],
                'j': kdj_values[2].tolist() if hasattr(kdj_values[2], 'tolist') else []
            }
            
            # RSI
            rsi_6 = indicators.calculate_rsi(df, 6)
            rsi_14 = indicators.calculate_rsi(df, 14)
            tf_indicators['indicators']['rsi'] = {
                'rsi_6': rsi_6.tolist() if hasattr(rsi_6, 'tolist') else [],
                'rsi_14': rsi_14.tolist() if hasattr(rsi_14, 'tolist') else []
            }
            
            # 移动平均线
            ma_5 = df['close'].rolling(window=5).mean()
            ma_10 = df['close'].rolling(window=10).mean()
            ma_20 = df['close'].rolling(window=20).mean()
            tf_indicators['indicators']['ma'] = {
                'ma_5': ma_5.tolist() if hasattr(ma_5, 'tolist') else [],
                'ma_10': ma_10.tolist() if hasattr(ma_10, 'tolist') else [],
                'ma_20': ma_20.tolist() if hasattr(ma_20, 'tolist') else []
            }
            
            # 布林带
            bb_upper, bb_middle, bb_lower = indicators.calculate_bollinger_bands(df)
            tf_indicators['indicators']['bollinger'] = {
                'upper': bb_upper.tolist() if hasattr(bb_upper, 'tolist') else [],
                'middle': bb_middle.tolist() if hasattr(bb_middle, 'tolist') else [],
                'lower': bb_lower.tolist() if hasattr(bb_lower, 'tolist') else []
            }
            
            # 趋势分析
            tf_indicators['trend_analysis'] = self._analyze_trend(df, timeframe)
            
            # 信号分析
            tf_indicators['signals'] = self._analyze_signals(df, tf_indicators['indicators'], timeframe)
            
            return tf_indicators
            
        except Exception as e:
            self.logger.error(f"计算{timeframe}指标失败: {e}")
            return {'error': str(e)}
    
    def _analyze_trend(self, df: pd.DataFrame, timeframe: str) -> Dict:
        """分析趋势"""
        try:
            if len(df) < 20:
                return {'trend': 'insufficient_data'}
            
            # 价格趋势
            recent_prices = df['close'].tail(20)
            price_trend = 'sideways'
            
            if recent_prices.iloc[-1] > recent_prices.iloc[0] * 1.05:
                price_trend = 'uptrend'
            elif recent_prices.iloc[-1] < recent_prices.iloc[0] * 0.95:
                price_trend = 'downtrend'
            
            # 成交量趋势
            volume_trend = 'stable'
            if 'volume' in df.columns and len(df) >= 10:
                recent_volume = df['volume'].tail(10).mean()
                historical_volume = df['volume'].head(-10).mean()
                
                if recent_volume > historical_volume * 1.2:
                    volume_trend = 'increasing'
                elif recent_volume < historical_volume * 0.8:
                    volume_trend = 'decreasing'
            
            # 波动率
            returns = df['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252) if len(returns) > 0 else 0
            
            return {
                'price_trend': price_trend,
                'volume_trend': volume_trend,
                'volatility': volatility,
                'trend_strength': abs(recent_prices.iloc[-1] / recent_prices.iloc[0] - 1),
                'timeframe': timeframe
            }
            
        except Exception as e:
            self.logger.error(f"分析{timeframe}趋势失败: {e}")
            return {'error': str(e)}
    
    def _analyze_signals(self, df: pd.DataFrame, indicators_dict: Dict, timeframe: str) -> Dict:
        """分析交易信号"""
        try:
            signals = {
                'macd_signals': [],
                'kdj_signals': [],
                'rsi_signals': [],
                'ma_signals': [],
                'composite_signal': 'neutral'
            }
            
            if len(df) < 2:
                return signals
            
            # MACD信号
            macd_dif = indicators_dict.get('macd', {}).get('dif', [])
            macd_dea = indicators_dict.get('macd', {}).get('dea', [])
            
            if len(macd_dif) >= 2 and len(macd_dea) >= 2:
                if macd_dif[-2] <= macd_dea[-2] and macd_dif[-1] > macd_dea[-1]:
                    signals['macd_signals'].append('golden_cross')
                elif macd_dif[-2] >= macd_dea[-2] and macd_dif[-1] < macd_dea[-1]:
                    signals['macd_signals'].append('death_cross')
            
            # KDJ信号
            kdj_k = indicators_dict.get('kdj', {}).get('k', [])
            kdj_d = indicators_dict.get('kdj', {}).get('d', [])
            
            if len(kdj_k) >= 2 and len(kdj_d) >= 2:
                if kdj_k[-2] <= kdj_d[-2] and kdj_k[-1] > kdj_d[-1] and kdj_d[-1] < 30:
                    signals['kdj_signals'].append('oversold_golden_cross')
                elif kdj_k[-2] >= kdj_d[-2] and kdj_k[-1] < kdj_d[-1] and kdj_d[-1] > 70:
                    signals['kdj_signals'].append('overbought_death_cross')
            
            # RSI信号
            rsi_14 = indicators_dict.get('rsi', {}).get('rsi_14', [])
            if len(rsi_14) >= 1:
                if rsi_14[-1] < 30:
                    signals['rsi_signals'].append('oversold')
                elif rsi_14[-1] > 70:
                    signals['rsi_signals'].append('overbought')
            
            # 移动平均线信号
            ma_5 = indicators_dict.get('ma', {}).get('ma_5', [])
            ma_20 = indicators_dict.get('ma', {}).get('ma_20', [])
            
            if len(ma_5) >= 2 and len(ma_20) >= 2:
                if ma_5[-2] <= ma_20[-2] and ma_5[-1] > ma_20[-1]:
                    signals['ma_signals'].append('ma5_cross_ma20_up')
                elif ma_5[-2] >= ma_20[-2] and ma_5[-1] < ma_20[-1]:
                    signals['ma_signals'].append('ma5_cross_ma20_down')
            
            # 综合信号
            bullish_signals = len([s for s in signals['macd_signals'] if 'golden' in s]) + \
                             len([s for s in signals['kdj_signals'] if 'golden' in s]) + \
                             len([s for s in signals['ma_signals'] if 'up' in s])
            
            bearish_signals = len([s for s in signals['macd_signals'] if 'death' in s]) + \
                            len([s for s in signals['kdj_signals'] if 'death' in s]) + \
                            len([s for s in signals['ma_signals'] if 'down' in s])
            
            if bullish_signals > bearish_signals:
                signals['composite_signal'] = 'bullish'
            elif bearish_signals > bullish_signals:
                signals['composite_signal'] = 'bearish'
            
            return signals
            
        except Exception as e:
            self.logger.error(f"分析{timeframe}信号失败: {e}")
            return {'error': str(e)}
    
    def _analyze_cross_timeframe_patterns(self, timeframes_indicators: Dict) -> Dict:
        """分析跨周期模式"""
        try:
            cross_analysis = {
                'trend_alignment': {},
                'signal_convergence': {},
                'strength_analysis': {},
                'recommendation': 'neutral'
            }
            
            # 趋势一致性分析
            trends = {}
            for timeframe, indicators in timeframes_indicators.items():
                trend_info = indicators.get('trend_analysis', {})
                trends[timeframe] = trend_info.get('price_trend', 'unknown')
            
            # 计算趋势一致性
            uptrend_count = sum(1 for trend in trends.values() if trend == 'uptrend')
            downtrend_count = sum(1 for trend in trends.values() if trend == 'downtrend')
            total_timeframes = len(trends)
            
            cross_analysis['trend_alignment'] = {
                'trends': trends,
                'uptrend_ratio': uptrend_count / total_timeframes if total_timeframes > 0 else 0,
                'downtrend_ratio': downtrend_count / total_timeframes if total_timeframes > 0 else 0,
                'alignment_strength': max(uptrend_count, downtrend_count) / total_timeframes if total_timeframes > 0 else 0
            }
            
            # 信号收敛分析
            signal_convergence = {}
            for timeframe, indicators in timeframes_indicators.items():
                signals = indicators.get('signals', {})
                composite_signal = signals.get('composite_signal', 'neutral')
                signal_convergence[timeframe] = composite_signal
            
            bullish_convergence = sum(1 for signal in signal_convergence.values() if signal == 'bullish')
            bearish_convergence = sum(1 for signal in signal_convergence.values() if signal == 'bearish')
            
            cross_analysis['signal_convergence'] = {
                'signals': signal_convergence,
                'bullish_convergence': bullish_convergence / total_timeframes if total_timeframes > 0 else 0,
                'bearish_convergence': bearish_convergence / total_timeframes if total_timeframes > 0 else 0,
                'convergence_strength': max(bullish_convergence, bearish_convergence) / total_timeframes if total_timeframes > 0 else 0
            }
            
            # 强度分析（基于周期权重）
            weighted_bullish_score = 0
            weighted_bearish_score = 0
            
            for timeframe, signal in signal_convergence.items():
                weight = self.timeframe_weights.get(timeframe, 0.1)
                if signal == 'bullish':
                    weighted_bullish_score += weight
                elif signal == 'bearish':
                    weighted_bearish_score += weight
            
            cross_analysis['strength_analysis'] = {
                'weighted_bullish_score': weighted_bullish_score,
                'weighted_bearish_score': weighted_bearish_score,
                'net_score': weighted_bullish_score - weighted_bearish_score
            }
            
            # 综合建议
            net_score = cross_analysis['strength_analysis']['net_score']
            alignment_strength = cross_analysis['trend_alignment']['alignment_strength']
            
            if net_score > 0.3 and alignment_strength > 0.6:
                cross_analysis['recommendation'] = 'strong_buy'
            elif net_score > 0.1 and alignment_strength > 0.4:
                cross_analysis['recommendation'] = 'buy'
            elif net_score < -0.3 and alignment_strength > 0.6:
                cross_analysis['recommendation'] = 'strong_sell'
            elif net_score < -0.1 and alignment_strength > 0.4:
                cross_analysis['recommendation'] = 'sell'
            else:
                cross_analysis['recommendation'] = 'neutral'
            
            return cross_analysis
            
        except Exception as e:
            self.logger.error(f"跨周期分析失败: {e}")
            return {'error': str(e)}
    
    def _is_cache_valid(self, cache_data: Dict, max_age_minutes: int = 30) -> bool:
        """检查缓存是否有效"""
        try:
            if 'last_update' not in cache_data:
                return False
            
            last_update = datetime.fromisoformat(cache_data['last_update'])
            age = datetime.now() - last_update
            
            return age.total_seconds() < max_age_minutes * 60
            
        except:
            return False
    
    def clear_cache(self):
        """清空缓存"""
        self.data_cache.clear()
        self.indicators_cache.clear()
        self.logger.info("缓存已清空")
    
    def get_cache_info(self) -> Dict:
        """获取缓存信息"""
        return {
            'data_cache_size': len(self.data_cache),
            'indicators_cache_size': len(self.indicators_cache),
            'supported_timeframes': list(self.timeframes.keys()),
            'timeframe_weights': self.timeframe_weights
        }

def main():
    """测试函数"""
    print("🕐 多周期数据管理器测试")
    print("=" * 50)
    
    # 创建管理器
    manager = MultiTimeframeDataManager()
    
    # 测试股票
    test_stocks = ['sz300290', 'sz002691']
    
    for stock_code in test_stocks:
        print(f"\n📊 测试股票: {stock_code}")
        
        # 获取多周期数据
        sync_data = manager.get_synchronized_data(stock_code)
        
        if 'error' in sync_data:
            print(f"  ❌ 数据获取失败: {sync_data['error']}")
            continue
        
        print(f"  ✅ 获取到 {len(sync_data['timeframes'])} 个时间周期的数据")
        
        for timeframe, df in sync_data['timeframes'].items():
            quality = sync_data['data_quality'][timeframe]
            print(f"    {timeframe}: {len(df)} 条数据, 质量评分: {quality['quality_score']:.2f}")
        
        # 计算多周期指标
        indicators_result = manager.calculate_multi_timeframe_indicators(stock_code)
        
        if 'error' in indicators_result:
            print(f"  ❌ 指标计算失败: {indicators_result['error']}")
            continue
        
        print(f"  ✅ 计算了 {len(indicators_result['timeframes'])} 个时间周期的指标")
        
        # 显示跨周期分析结果
        cross_analysis = indicators_result.get('cross_timeframe_analysis', {})
        if cross_analysis:
            recommendation = cross_analysis.get('recommendation', 'neutral')
            alignment_strength = cross_analysis.get('trend_alignment', {}).get('alignment_strength', 0)
            print(f"  📈 跨周期分析: {recommendation} (趋势一致性: {alignment_strength:.2f})")
        
        break  # 只测试第一个有效股票

if __name__ == "__main__":
    main()