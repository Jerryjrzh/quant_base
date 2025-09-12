"""
MA13强势回调短线交易策略

基于doc/0912_short/中的策略文档实现的短线交易系统
核心逻辑：底部稳定 → 日线爆发 → MA13回调 → 小时确认
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
import sys
import os

# 添加backend目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

class MA13ShortTermStrategy:
    """MA13强势回调短线交易策略"""
    
    def __init__(self):
        self.name = "MA13强势回调趋势系统"
        self.description = "基于MA13支撑的短线趋势跟踪策略"
        self.version = "1.0"
        
        # 策略参数
        self.params = {
            # 步骤1: 海选参数
            'box_duration_min': 60,  # 底部箱体最小天数
            'box_volatility_max': 0.20,  # 箱体波动率上限
            'market_cap_min': 50,  # 最小市值(亿)
            'market_cap_max': 200,  # 最大市值(亿)
            
            # 步骤2: 精选参数
            'breakout_gain_min': 0.20,  # 突破涨幅下限
            'volume_ratio_min': 0.7,  # 成交量放大倍数 (降低要求以适应演示)
            
            # 步骤3: 择时参数
            'pullback_min': 0.02,  # 回调幅度下限 (降低要求)
            'pullback_max': 0.15,  # 回调幅度上限
            'ma13_support_buffer': 0.02,  # MA13支撑缓冲区
            
            # 步骤4&5: 小时线确认参数
            'rsi_oversold': 30,  # RSI超卖线
            'rsi_support': 50,  # RSI支撑线
            'kdj_oversold': 30,  # KDJ超卖线
            'kdj_support_min': 40,  # KDJ支撑下限
            'kdj_support_max': 90,  # KDJ支撑上限
            
            # 风控参数
            'stop_loss_pct': 0.05,  # 止损幅度
            'take_profit_1': 0.10,  # 第一止盈位
            'take_profit_2': 0.20,  # 第二止盈位
            'max_hold_days': 10,  # 最大持仓天数
        }
        
        # 信号状态
        self.signals = {
            'stage_1_qualified': False,  # 海选通过
            'stage_2_qualified': False,  # 精选通过
            'stage_3_qualified': False,  # 择时通过
            'stage_4_oversold_signal': False,  # 超跌模型信号
            'stage_5_continuation_signal': False,  # 中继模型信号
        }
        
        # 关键价位
        self.key_levels = {
            'support_1_upper': 0,  # 第一支撑区上轨
            'support_1_lower': 0,  # 第一支撑区下轨(MA13)
            'support_2_upper': 0,  # 第二支撑区上轨(MA30)
            'support_2_lower': 0,  # 第二支撑区下轨
            'target_1': 0,  # 第一目标位
            'target_2': 0,  # 第二目标位
            'target_3': 0,  # 第三目标位
            'stop_loss': 0,  # 止损位
        }

    def analyze_stock(self, df: pd.DataFrame, stock_code: str = None) -> Dict:
        """
        分析股票是否符合MA13短线策略
        
        Args:
            df: 股票数据DataFrame，包含OHLCV和技术指标
            stock_code: 股票代码
            
        Returns:
            分析结果字典
        """
        try:
            if len(df) < 150:  # 需要足够的历史数据
                return self._create_result(False, "历史数据不足")
            
            # 确保数据按日期排序
            df = df.sort_values('date').reset_index(drop=True)
            
            # 步骤1: 海选 - 底部稳定
            stage_1_result = self._stage_1_bottom_stability(df)
            if not stage_1_result['qualified']:
                return self._create_result(False, f"海选未通过: {stage_1_result['reason']}")
            
            # 步骤2: 精选 - 日线爆发
            stage_2_result = self._stage_2_breakout_confirmation(df)
            if not stage_2_result['qualified']:
                return self._create_result(False, f"精选未通过: {stage_2_result['reason']}")
            
            # 步骤3: 择时 - MA13回调
            stage_3_result = self._stage_3_ma13_pullback(df)
            if not stage_3_result['qualified']:
                return self._create_result(False, f"择时未通过: {stage_3_result['reason']}")
            
            # 计算关键价位
            self._calculate_key_levels(df)
            
            # 步骤4&5: 小时线确认(模拟)
            signal_result = self._stage_45_signal_confirmation(df)
            
            # 生成交易建议
            recommendation = self._generate_recommendation(df, signal_result)
            
            return self._create_result(
                True, 
                "策略条件满足",
                {
                    'stage_1': stage_1_result,
                    'stage_2': stage_2_result,
                    'stage_3': stage_3_result,
                    'signals': signal_result,
                    'key_levels': self.key_levels.copy(),
                    'recommendation': recommendation,
                    'stock_code': stock_code,
                    'analysis_date': df.iloc[-1]['date']
                }
            )
            
        except Exception as e:
            logger.error(f"分析股票 {stock_code} 时出错: {str(e)}")
            return self._create_result(False, f"分析出错: {str(e)}")

    def _stage_1_bottom_stability(self, df: pd.DataFrame) -> Dict:
        """步骤1: 海选 - 底部稳定分析"""
        try:
            # 分析最近6个月的数据
            recent_months = min(120, len(df))
            recent_data = df.tail(recent_months)
            
            # 检查是否有足够的箱体震荡期
            if len(recent_data) < self.params['box_duration_min']:
                return {'qualified': False, 'reason': '数据长度不足'}
            
            # 寻找箱体震荡区间
            box_period = recent_data.head(self.params['box_duration_min'])
            box_high = box_period['high'].max()
            box_low = box_period['low'].min()
            box_volatility = (box_high - box_low) / box_low
            
            # 检查箱体波动率
            if box_volatility > self.params['box_volatility_max']:
                return {'qualified': False, 'reason': f'箱体波动率过大: {box_volatility:.2%}'}
            
            # 检查MA60趋势
            if 'ma60' in df.columns:
                ma60_slope = self._calculate_ma_slope(recent_data, 'ma60', 20)
                if ma60_slope < -0.001:  # MA60下降趋势
                    return {'qualified': False, 'reason': 'MA60呈下降趋势'}
            
            return {
                'qualified': True,
                'box_high': box_high,
                'box_low': box_low,
                'box_volatility': box_volatility,
                'box_duration': len(box_period)
            }
            
        except Exception as e:
            return {'qualified': False, 'reason': f'底部稳定分析出错: {str(e)}'}

    def _stage_2_breakout_confirmation(self, df: pd.DataFrame) -> Dict:
        """步骤2: 精选 - 日线爆发确认"""
        try:
            # 分析最近20天的突破情况
            recent_data = df.tail(20)
            
            # 计算从底部的涨幅
            box_low = df.tail(120)['low'].min()  # 近期底部
            current_price = recent_data.iloc[-1]['close']
            breakout_gain = (current_price - box_low) / box_low
            
            # 检查突破涨幅
            if breakout_gain < self.params['breakout_gain_min']:
                return {'qualified': False, 'reason': f'突破涨幅不足: {breakout_gain:.2%}'}
            
            # 检查成交量放大
            recent_volume = recent_data['volume'].mean()
            historical_volume = df.tail(60).head(40)['volume'].mean()  # 使用更早期的数据作为基准
            volume_ratio = recent_volume / historical_volume if historical_volume > 0 else 0
            
            if volume_ratio < self.params['volume_ratio_min']:
                return {'qualified': False, 'reason': f'成交量放大不足: {volume_ratio:.2f}倍'}
            
            # 检查均线多头排列
            latest = recent_data.iloc[-1]
            ma_bullish = self._check_ma_bullish_alignment(latest)
            
            if not ma_bullish:
                return {'qualified': False, 'reason': '均线未形成多头排列'}
            
            return {
                'qualified': True,
                'breakout_gain': breakout_gain,
                'volume_ratio': volume_ratio,
                'box_low': box_low,
                'current_price': current_price
            }
            
        except Exception as e:
            return {'qualified': False, 'reason': f'日线爆发确认出错: {str(e)}'}

    def _stage_3_ma13_pullback(self, df: pd.DataFrame) -> Dict:
        """步骤3: 择时 - MA13回调分析"""
        try:
            recent_data = df.tail(20)
            
            # 找到近期高点
            recent_high = recent_data['high'].max()
            current_price = recent_data.iloc[-1]['close']
            
            # 计算回调幅度
            pullback_pct = (recent_high - current_price) / recent_high
            
            # 检查回调幅度是否在合理范围
            if pullback_pct < self.params['pullback_min']:
                return {'qualified': False, 'reason': f'回调幅度不足: {pullback_pct:.2%}'}
            
            if pullback_pct > self.params['pullback_max']:
                return {'qualified': False, 'reason': f'回调幅度过大: {pullback_pct:.2%}'}
            
            # 检查MA13支撑
            if 'ma13' not in df.columns:
                return {'qualified': False, 'reason': 'MA13数据缺失'}
            
            current_ma13 = recent_data.iloc[-1]['ma13']
            ma13_support_level = current_ma13 * (1 - self.params['ma13_support_buffer'])
            
            # 检查是否在MA13支撑区域
            if current_price < ma13_support_level:
                return {'qualified': False, 'reason': f'跌破MA13支撑: {current_price:.2f} < {ma13_support_level:.2f}'}
            
            # 检查RSI位置
            if 'rsi6' in df.columns:
                current_rsi = recent_data.iloc[-1]['rsi6']
                if current_rsi < self.params['rsi_support']:
                    return {'qualified': False, 'reason': f'RSI位置偏低: {current_rsi:.1f}'}
            
            return {
                'qualified': True,
                'recent_high': recent_high,
                'pullback_pct': pullback_pct,
                'current_ma13': current_ma13,
                'support_level': ma13_support_level
            }
            
        except Exception as e:
            return {'qualified': False, 'reason': f'MA13回调分析出错: {str(e)}'}

    def _stage_45_signal_confirmation(self, df: pd.DataFrame) -> Dict:
        """步骤4&5: 小时线信号确认(基于日线数据模拟)"""
        try:
            recent_data = df.tail(5)  # 最近5天数据
            latest = recent_data.iloc[-1]
            
            signals = {
                'oversold_model': False,  # 超跌反弹模型
                'continuation_model': False,  # 中继确认模型
                'signal_strength': 0,  # 信号强度(0-100)
                'entry_timing': 'wait'  # 入场时机: wait/oversold/continuation
            }
            
            # 模型一: 超跌反弹信号
            oversold_signals = []
            
            # KDJ超卖金叉
            if all(col in df.columns for col in ['k', 'd', 'j']):
                if (latest['j'] > latest['k'] and 
                    latest['k'] > latest['d'] and 
                    latest['j'] < self.params['kdj_oversold']):
                    oversold_signals.append('kdj_oversold_cross')
            
            # MACD水下金叉
            if all(col in df.columns for col in ['dif', 'dea']):
                if (latest['dif'] > latest['dea'] and 
                    latest['dif'] < 0 and latest['dea'] < 0):
                    oversold_signals.append('macd_underwater_cross')
            
            # RSI从超卖区回升
            if 'rsi6' in df.columns:
                prev_rsi = recent_data.iloc[-2]['rsi6'] if len(recent_data) > 1 else latest['rsi6']
                if prev_rsi < self.params['rsi_oversold'] and latest['rsi6'] > self.params['rsi_oversold']:
                    oversold_signals.append('rsi_oversold_recovery')
            
            if len(oversold_signals) >= 1:
                signals['oversold_model'] = True
                signals['signal_strength'] += 30
                if signals['entry_timing'] == 'wait':
                    signals['entry_timing'] = 'oversold'
            
            # 模型二: 中继确认信号
            continuation_signals = []
            
            # MACD零轴上方拒绝死叉
            if all(col in df.columns for col in ['dif', 'dea']):
                if (latest['dif'] > 0 and latest['dea'] > 0 and 
                    latest['dif'] > latest['dea']):
                    continuation_signals.append('macd_above_zero_bullish')
            
            # KDJ中轴金叉
            if all(col in df.columns for col in ['k', 'd', 'j']):
                if (latest['j'] > latest['k'] and 
                    latest['k'] > latest['d'] and 
                    self.params['kdj_support_min'] <= latest['j'] <= self.params['kdj_support_max']):
                    continuation_signals.append('kdj_mid_cross')
            
            # RSI中轴支撑
            if 'rsi6' in df.columns:
                if latest['rsi6'] > self.params['rsi_support']:
                    continuation_signals.append('rsi_support_hold')
            
            if len(continuation_signals) >= 2:
                signals['continuation_model'] = True
                signals['signal_strength'] += 50
                signals['entry_timing'] = 'continuation'
            
            # 成交量确认
            if len(recent_data) >= 2:
                volume_increase = latest['volume'] > recent_data.iloc[-2]['volume'] * 1.1
                if volume_increase:
                    signals['signal_strength'] += 20
            
            signals['oversold_signals'] = oversold_signals
            signals['continuation_signals'] = continuation_signals
            
            return signals
            
        except Exception as e:
            logger.error(f"信号确认分析出错: {str(e)}")
            return {
                'oversold_model': False,
                'continuation_model': False,
                'signal_strength': 0,
                'entry_timing': 'wait'
            }

    def _calculate_key_levels(self, df: pd.DataFrame):
        """计算关键支撑位和目标位"""
        try:
            recent_data = df.tail(20)
            latest = recent_data.iloc[-1]
            
            # 支撑位计算
            if 'ma13' in df.columns:
                ma13 = latest['ma13']
                self.key_levels['support_1_lower'] = ma13  # MA13支撑
                
                # 第一支撑区上轨(近期回调低点)
                recent_low = recent_data['low'].min()
                self.key_levels['support_1_upper'] = max(recent_low, ma13 * 1.02)
            
            if 'ma30' in df.columns:
                ma30 = latest['ma30']
                self.key_levels['support_2_upper'] = ma30  # MA30支撑
                
                # 第二支撑区下轨(箱体上轨)
                box_high = df.tail(120)['high'].quantile(0.8)  # 近期箱体上轨
                self.key_levels['support_2_lower'] = min(ma30 * 0.95, box_high)
            
            # 目标位计算
            current_price = latest['close']
            
            # 第一目标位: 前期高点
            recent_high = recent_data['high'].max()
            self.key_levels['target_1'] = recent_high * 1.02
            
            # 第二目标位: 等幅测算
            box_low = df.tail(120)['low'].min()
            box_height = recent_high - box_low
            self.key_levels['target_2'] = recent_high + box_height * 0.5
            
            # 第三目标位: 乐观目标
            self.key_levels['target_3'] = recent_high * 1.20
            
            # 止损位
            self.key_levels['stop_loss'] = ma13 * (1 - self.params['stop_loss_pct'])
            
        except Exception as e:
            logger.error(f"计算关键价位出错: {str(e)}")

    def _generate_recommendation(self, df: pd.DataFrame, signals: Dict) -> Dict:
        """生成交易建议"""
        try:
            latest = df.iloc[-1]
            current_price = latest['close']
            
            recommendation = {
                'action': 'wait',  # wait/buy_light/buy_heavy
                'entry_price': current_price,
                'position_size': 0,  # 建议仓位比例
                'stop_loss': self.key_levels['stop_loss'],
                'take_profit_1': self.key_levels['target_1'],
                'take_profit_2': self.key_levels['target_2'],
                'max_hold_days': self.params['max_hold_days'],
                'risk_reward_ratio': 0,
                'confidence': 0  # 信心度(0-100)
            }
            
            # 根据信号强度决定操作
            if signals['signal_strength'] >= 70:
                recommendation['action'] = 'buy_heavy'
                recommendation['position_size'] = 0.7  # 70%仓位
                recommendation['confidence'] = 85
            elif signals['signal_strength'] >= 40:
                recommendation['action'] = 'buy_light'
                recommendation['position_size'] = 0.3  # 30%仓位
                recommendation['confidence'] = 65
            else:
                recommendation['confidence'] = 30
            
            # 计算风险收益比
            if recommendation['stop_loss'] > 0:
                risk = current_price - recommendation['stop_loss']
                reward = recommendation['take_profit_1'] - current_price
                if risk > 0:
                    recommendation['risk_reward_ratio'] = reward / risk
            
            # 入场时机建议
            recommendation['entry_timing'] = signals['entry_timing']
            recommendation['signal_type'] = []
            
            if signals['oversold_model']:
                recommendation['signal_type'].append('超跌反弹')
            if signals['continuation_model']:
                recommendation['signal_type'].append('中继确认')
            
            return recommendation
            
        except Exception as e:
            logger.error(f"生成交易建议出错: {str(e)}")
            return {'action': 'wait', 'confidence': 0}

    def _check_ma_bullish_alignment(self, data_row) -> bool:
        """检查均线多头排列"""
        try:
            ma_columns = ['ma7', 'ma13', 'ma30']
            ma_values = []
            
            for col in ma_columns:
                if col in data_row and pd.notna(data_row[col]):
                    ma_values.append(data_row[col])
            
            if len(ma_values) < 2:
                return False
            
            # 检查是否递减排列(短期>长期)，允许一定的容差
            tolerance = 0.02  # 2%的容差
            for i in range(len(ma_values)-1):
                if ma_values[i] < ma_values[i+1] * (1 - tolerance):
                    return False
            return True
            
        except Exception:
            return False

    def _calculate_ma_slope(self, df: pd.DataFrame, ma_column: str, periods: int = 5) -> float:
        """计算均线斜率"""
        try:
            if ma_column not in df.columns or len(df) < periods:
                return 0
            
            recent_ma = df[ma_column].tail(periods).dropna()
            if len(recent_ma) < 2:
                return 0
            
            # 计算线性回归斜率
            x = np.arange(len(recent_ma))
            y = recent_ma.values
            slope = np.polyfit(x, y, 1)[0]
            
            return slope / recent_ma.iloc[-1]  # 标准化斜率
            
        except Exception:
            return 0

    def _create_result(self, success: bool, message: str, data: Dict = None) -> Dict:
        """创建统一的结果格式"""
        result = {
            'success': success,
            'message': message,
            'strategy': self.name,
            'timestamp': datetime.now().isoformat()
        }
        
        if data:
            result.update(data)
        
        return result

    def get_strategy_info(self) -> Dict:
        """获取策略信息"""
        return {
            'name': self.name,
            'description': self.description,
            'version': self.version,
            'parameters': self.params,
            'stages': [
                '步骤1: 海选 - 底部稳定',
                '步骤2: 精选 - 日线爆发', 
                '步骤3: 择时 - MA13回调',
                '步骤4: 超跌反弹模型',
                '步骤5: 中继确认模型'
            ]
        }