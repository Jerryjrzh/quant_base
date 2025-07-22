"""
胜率过滤器：基于历史回测数据筛选高胜率股票
针对TRIPLE_CROSS策略进行优化 - 支持可配置参数
"""
import numpy as np
import pandas as pd
import indicators
import backtester
from collections import defaultdict
# 移除不存在的导入，使用strategies模块中的配置
import strategies

class WinRateFilter:
    def __init__(self, min_win_rate=None, min_signals=None, min_avg_profit=None, config=None):
        """
        初始化胜率过滤器
        
        Args:
            min_win_rate: 最低胜率要求
            min_signals: 最少历史信号数量
            min_avg_profit: 最低平均收益率
        """
        self.min_win_rate = min_win_rate
        self.min_signals = min_signals
        self.min_avg_profit = min_avg_profit
    
    def should_exclude_stock(self, df, signal_series, stock_code):
        """
        判断是否应该排除某只股票
        
        Args:
            df: 股票数据
            signal_series: 信号序列
            stock_code: 股票代码
            
        Returns:
            tuple: (是否排除, 排除原因, 详细统计)
        """
        try:
            # 执行回测获取历史表现
            backtest_result = backtester.run_backtest(df, signal_series)
            
            if not isinstance(backtest_result, dict):
                return True, "回测失败", {}
            
            total_signals = backtest_result.get('total_signals', 0)
            if total_signals < self.min_signals:
                return True, f"历史信号数量不足({total_signals}个，需要至少{self.min_signals}个)", backtest_result
            
            # 解析胜率
            win_rate_str = backtest_result.get('win_rate', '0.0%').replace('%', '')
            try:
                win_rate = float(win_rate_str) / 100
            except:
                return True, "胜率数据解析失败", backtest_result
            
            if win_rate < self.min_win_rate:
                return True, f"胜率过低({win_rate:.1%}，需要至少{self.min_win_rate:.1%})", backtest_result
            
            # 解析平均收益率
            profit_str = backtest_result.get('avg_max_profit', '0.0%').replace('%', '')
            try:
                avg_profit = float(profit_str) / 100
            except:
                return True, "收益率数据解析失败", backtest_result
            
            if avg_profit < self.min_avg_profit:
                return True, f"平均收益过低({avg_profit:.1%}，需要至少{self.min_avg_profit:.1%})", backtest_result
            
            # 额外的质量检查
            quality_issues = self._check_quality_issues(df, backtest_result)
            if quality_issues:
                return True, f"质量问题: {'; '.join(quality_issues)}", backtest_result
            
            return False, "通过筛选", backtest_result
            
        except Exception as e:
            return True, f"过滤器执行失败: {e}", {}
    
    def _check_quality_issues(self, df, backtest_result):
        """检查额外的质量问题"""
        issues = []
        
        try:
            # 检查最大回撤
            drawdown_str = backtest_result.get('avg_max_drawdown', '0.0%').replace('%', '')
            avg_drawdown = float(drawdown_str) / 100
            
            if avg_drawdown < -0.15:  # 平均最大回撤超过15%
                issues.append(f"平均最大回撤过大({avg_drawdown:.1%})")
            
            # 检查达峰时间
            days_str = backtest_result.get('avg_days_to_peak', '0.0 天').replace(' 天', '')
            avg_days = float(days_str)
            
            if avg_days > 45:  # 平均达峰时间超过45天
                issues.append(f"达峰时间过长({avg_days:.1f}天)")
            
            # 检查交易分布
            trades = backtest_result.get('trades', [])
            if trades:
                # 检查是否有过多的失败交易
                failed_trades = [t for t in trades if not t.get('is_success', False)]
                if len(failed_trades) / len(trades) > 0.7:  # 失败率超过70%
                    issues.append("失败交易比例过高")
                
                # 检查收益分布是否过于集中
                profits = [t.get('actual_max_pnl', 0) for t in trades]
                if len(profits) > 3:
                    profit_std = np.std(profits)
                    profit_mean = np.mean(profits)
                    if profit_std / abs(profit_mean) > 2:  # 收益波动过大
                        issues.append("收益波动性过大")
            
            # 检查最近表现趋势
            recent_performance = self._analyze_recent_performance(df, trades)
            if recent_performance and recent_performance['declining_trend']:
                issues.append("最近表现呈下降趋势")
                
        except Exception as e:
            issues.append(f"质量检查异常: {e}")
        
        return issues
    
    def _analyze_recent_performance(self, df, trades):
        """分析最近的表现趋势"""
        try:
            if not trades or len(trades) < 4:
                return None
            
            # 按时间排序交易
            sorted_trades = sorted(trades, key=lambda x: x.get('signal_idx', 0))
            
            # 取最近一半的交易
            recent_count = max(2, len(sorted_trades) // 2)
            recent_trades = sorted_trades[-recent_count:]
            earlier_trades = sorted_trades[:-recent_count]
            
            if not earlier_trades:
                return None
            
            # 计算最近和早期的平均表现
            recent_avg_profit = np.mean([t.get('actual_max_pnl', 0) for t in recent_trades])
            earlier_avg_profit = np.mean([t.get('actual_max_pnl', 0) for t in earlier_trades])
            
            # 判断是否呈下降趋势
            declining_trend = recent_avg_profit < earlier_avg_profit * 0.7  # 最近表现比早期差30%以上
            
            return {
                'declining_trend': declining_trend,
                'recent_avg_profit': recent_avg_profit,
                'earlier_avg_profit': earlier_avg_profit
            }
            
        except Exception as e:
            return None

class AdvancedTripleCrossFilter:
    """针对TRIPLE_CROSS策略的高级过滤器"""
    
    def __init__(self):
        self.base_filter = WinRateFilter(min_win_rate=0.45, min_signals=3, min_avg_profit=0.10)
    
    def enhanced_triple_cross_filter(self, df, signal_idx):
        """
        增强版TRIPLE_CROSS过滤器
        
        Args:
            df: 股票数据
            signal_idx: 信号索引
            
        Returns:
            tuple: (是否排除, 排除原因, 质量评分, 交叉阶段)
        """
        try:
            # 计算技术指标
            macd_values = indicators.calculate_macd(df)
            dif, dea = macd_values[0], macd_values[1]
            kdj_values = indicators.calculate_kdj(df)
            k, d, j = kdj_values[0], kdj_values[1], kdj_values[2]
            rsi6 = indicators.calculate_rsi(df, 6)
            rsi12 = indicators.calculate_rsi(df, 12)
            
            # 获取信号当天的指标值
            signal_dif = dif.iloc[signal_idx]
            signal_dea = dea.iloc[signal_idx]
            signal_k = k.iloc[signal_idx]
            signal_d = d.iloc[signal_idx]
            signal_j = j.iloc[signal_idx]
            signal_rsi6 = rsi6.iloc[signal_idx]
            signal_rsi12 = rsi12.iloc[signal_idx]
            
            quality_score = 0
            filter_reasons = []
            
            # 1. 识别交叉阶段
            cross_stage = self._identify_cross_stage(df, signal_idx, dif, dea, k, d, rsi6, rsi12)
            
            # 2. 基于交叉阶段的不同标准
            if cross_stage == 'PRE_CROSS':
                # 交叉前：更严格的条件
                if signal_d > 60:
                    filter_reasons.append("PRE阶段KDJ D值过高，风险较大")
                elif signal_d < 25:
                    quality_score += 35  # 低位预交叉，高分
                else:
                    quality_score += 20
                
                # MACD接近度检查
                macd_gap = abs(signal_dif - signal_dea)
                if macd_gap > 0.05:
                    filter_reasons.append("PRE阶段MACD距离过远，交叉可能性低")
                else:
                    quality_score += 25
                    
            elif cross_stage == 'CROSS_MOMENT':
                # 交叉时刻：检查交叉强度
                macd_strength = abs(signal_dif - signal_dea)
                if macd_strength < 0.005:
                    filter_reasons.append("交叉强度不足，可能是假突破")
                else:
                    quality_score += 30
                
                # 成交量确认
                if self._check_volume_confirmation(df, signal_idx):
                    quality_score += 20
                else:
                    filter_reasons.append("缺乏成交量确认")
                    
            elif cross_stage == 'POST_CROSS':
                # 交叉后：检查确认强度
                if signal_dif <= signal_dea:
                    filter_reasons.append("POST阶段MACD未能维持金叉")
                else:
                    quality_score += 25
                
                # 检查是否过度延迟
                days_since_cross = self._days_since_last_cross(df, signal_idx, dif, dea)
                if days_since_cross > 7:
                    filter_reasons.append(f"交叉后延迟过久({days_since_cross}天)")
                else:
                    quality_score += 15
            
            # 3. 通用质量检查
            # 价格位置检查
            price_position = self._analyze_price_position(df, signal_idx)
            if price_position['is_high_position']:
                filter_reasons.append(f"价格位置过高({price_position['percentile']:.0f}分位)")
            else:
                quality_score += 15
            
            # 趋势一致性检查
            trend_consistency = self._check_trend_consistency(df, signal_idx)
            if not trend_consistency['is_consistent']:
                filter_reasons.append("多指标趋势不一致")
            else:
                quality_score += 20
            
            # 4. 综合评分判断
            min_quality_score = 70  # 提高最低质量分数
            should_exclude = quality_score < min_quality_score or len(filter_reasons) >= 2
            
            exclude_reason = "; ".join(filter_reasons) if filter_reasons else ""
            if should_exclude and not exclude_reason:
                exclude_reason = f"综合质量评分过低({quality_score}分)"
            
            return should_exclude, exclude_reason, quality_score, cross_stage
            
        except Exception as e:
            return True, f"过滤器执行失败: {e}", 0, "UNKNOWN"
    
    def _identify_cross_stage(self, df, signal_idx, dif, dea, k, d, rsi6, rsi12):
        """识别当前信号处于哪个交叉阶段"""
        try:
            # 检查当前状态
            macd_crossed = dif.iloc[signal_idx] > dea.iloc[signal_idx]
            kdj_crossed = k.iloc[signal_idx] > d.iloc[signal_idx]
            rsi_crossed = rsi6.iloc[signal_idx] > rsi12.iloc[signal_idx]
            
            crosses_count = sum([macd_crossed, kdj_crossed, rsi_crossed])
            
            if crosses_count == 3:
                # 检查是否刚刚发生交叉
                recent_cross = False
                for i in range(max(0, signal_idx - 3), signal_idx):
                    prev_macd = dif.iloc[i] <= dea.iloc[i]
                    prev_kdj = k.iloc[i] <= d.iloc[i]
                    prev_rsi = rsi6.iloc[i] <= rsi12.iloc[i]
                    
                    if sum([prev_macd, prev_kdj, prev_rsi]) >= 2:
                        recent_cross = True
                        break
                
                return 'CROSS_MOMENT' if recent_cross else 'POST_CROSS'
                
            elif crosses_count >= 1:
                # 部分交叉，可能是交叉进行中
                return 'CROSS_MOMENT'
            else:
                # 尚未交叉，检查是否接近
                macd_gap = dif.iloc[signal_idx] - dea.iloc[signal_idx]
                kdj_gap = k.iloc[signal_idx] - d.iloc[signal_idx]
                
                if macd_gap > -0.02 and kdj_gap > -5:
                    return 'PRE_CROSS'
                else:
                    return 'BOTTOM_FORMATION'
                    
        except Exception as e:
            return 'UNKNOWN'
    
    def _check_volume_confirmation(self, df, signal_idx):
        """检查成交量确认"""
        try:
            if 'volume' not in df.columns:
                return True  # 没有成交量数据时不作为过滤条件
            
            # 计算最近5天平均成交量
            start_idx = max(0, signal_idx - 5)
            recent_avg_volume = df['volume'].iloc[start_idx:signal_idx].mean()
            signal_volume = df['volume'].iloc[signal_idx]
            
            # 信号当天成交量应该至少是平均水平的80%
            return signal_volume >= recent_avg_volume * 0.8
            
        except Exception as e:
            return True
    
    def _days_since_last_cross(self, df, signal_idx, dif, dea):
        """计算距离上次MACD金叉的天数"""
        try:
            for i in range(signal_idx - 1, max(0, signal_idx - 10), -1):
                if dif.iloc[i-1] <= dea.iloc[i-1] and dif.iloc[i] > dea.iloc[i]:
                    return signal_idx - i
            return 10  # 如果10天内没找到，返回10
        except:
            return 5
    
    def _analyze_price_position(self, df, signal_idx):
        """分析价格在历史区间中的位置"""
        try:
            # 取最近60天的价格数据
            lookback_days = min(60, signal_idx + 1)
            start_idx = signal_idx - lookback_days + 1
            recent_data = df.iloc[start_idx:signal_idx + 1]
            
            current_price = df.iloc[signal_idx]['close']
            price_min = recent_data['low'].min()
            price_max = recent_data['high'].max()
            
            # 计算价格分位数
            percentile = (current_price - price_min) / (price_max - price_min) * 100
            
            return {
                'percentile': percentile,
                'is_high_position': percentile > 75  # 超过75分位认为是高位
            }
            
        except Exception as e:
            return {'percentile': 50, 'is_high_position': False}
    
    def _check_trend_consistency(self, df, signal_idx):
        """检查多指标趋势一致性"""
        try:
            # 计算各指标的短期趋势
            lookback = 5
            start_idx = max(0, signal_idx - lookback)
            
            # 价格趋势
            price_trend = (df.iloc[signal_idx]['close'] - df.iloc[start_idx]['close']) / df.iloc[start_idx]['close']
            
            # MACD趋势
            macd_values = indicators.calculate_macd(df)
            dif = macd_values[0]
            macd_trend = dif.iloc[signal_idx] - dif.iloc[start_idx]
            
            # KDJ趋势
            kdj_values = indicators.calculate_kdj(df)
            k = kdj_values[0]
            kdj_trend = k.iloc[signal_idx] - k.iloc[start_idx]
            
            # 判断趋势一致性
            trends = [price_trend > 0, macd_trend > 0, kdj_trend > 0]
            consistency = sum(trends) >= 2  # 至少2个指标同向
            
            return {
                'is_consistent': consistency,
                'price_trend': price_trend,
                'macd_trend': macd_trend,
                'kdj_trend': kdj_trend
            }
            
        except Exception as e:
            return {'is_consistent': True}  # 出错时不作为过滤条件