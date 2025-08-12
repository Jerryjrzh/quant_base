#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持仓列表管理模块
功能：
1. 持仓列表的增删改查
2. 深度扫描和操作建议
3. 补仓价、预期到顶日期、卖出提醒等分析
"""

import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import data_loader
import indicators
import strategies
from adjustment_processor import create_adjustment_config, create_adjustment_processor

class PortfolioManager:
    def __init__(self, data_path: str = None):
        """初始化持仓管理器"""
        self.data_path = data_path or os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        self.portfolio_file = os.path.join(os.path.dirname(__file__), '..', 'data', 'portfolio.json')
        self.ensure_portfolio_file()
    
    def ensure_portfolio_file(self):
        """确保持仓文件存在"""
        os.makedirs(os.path.dirname(self.portfolio_file), exist_ok=True)
        if not os.path.exists(self.portfolio_file):
            self.save_portfolio([])
    
    def load_portfolio(self) -> List[Dict]:
        """加载持仓列表"""
        try:
            with open(self.portfolio_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def save_portfolio(self, portfolio: List[Dict]):
        """保存持仓列表"""
        with open(self.portfolio_file, 'w', encoding='utf-8') as f:
            json.dump(portfolio, f, ensure_ascii=False, indent=2)
    
    def add_position(self, stock_code: str, purchase_price: float, quantity: int, 
                    purchase_date: str = None, note: str = "") -> Dict:
        """添加持仓"""
        portfolio = self.load_portfolio()
        
        # 检查是否已存在
        for position in portfolio:
            if position['stock_code'] == stock_code:
                raise ValueError(f"股票 {stock_code} 已在持仓列表中")
        
        new_position = {
            'stock_code': stock_code,
            'purchase_price': purchase_price,
            'quantity': quantity,
            'purchase_date': purchase_date or datetime.now().strftime('%Y-%m-%d'),
            'note': note,
            'created_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_analysis_time': None
        }
        
        portfolio.append(new_position)
        self.save_portfolio(portfolio)
        return new_position
    
    def remove_position(self, stock_code: str) -> bool:
        """删除持仓"""
        portfolio = self.load_portfolio()
        original_count = len(portfolio)
        portfolio = [p for p in portfolio if p['stock_code'] != stock_code]
        
        if len(portfolio) < original_count:
            self.save_portfolio(portfolio)
            return True
        return False
    
    def update_position(self, stock_code: str, **kwargs) -> bool:
        """更新持仓信息"""
        portfolio = self.load_portfolio()
        
        for position in portfolio:
            if position['stock_code'] == stock_code:
                for key, value in kwargs.items():
                    if key in position:
                        position[key] = value
                position['updated_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.save_portfolio(portfolio)
                return True
        return False
    
    def get_stock_data(self, stock_code: str, adjustment_type: str = 'forward') -> Optional[pd.DataFrame]:
        """获取股票数据"""
        try:
            market = stock_code[:2]
            file_path = os.path.join(self.data_path, market, 'lday', f'{stock_code}.day')
            
            if not os.path.exists(file_path):
                return None
            
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 50:
                return None
            
            # 应用复权处理
            if adjustment_type != 'none':
                adjustment_config = create_adjustment_config(adjustment_type)
                adjustment_processor = create_adjustment_processor(adjustment_config)
                df = adjustment_processor.process_data(df, stock_code)
            
            return df
        except Exception as e:
            print(f"获取股票数据失败 {stock_code}: {e}")
            return None
    
    def calculate_technical_indicators(self, df: pd.DataFrame, stock_code: str, 
                                     adjustment_type: str = 'forward') -> pd.DataFrame:
        """计算技术指标"""
        # 基础指标
        df['ma5'] = indicators.calculate_ma(df, 5)
        df['ma13'] = indicators.calculate_ma(df, 13)
        df['ma21'] = indicators.calculate_ma(df, 21)
        df['ma45'] = indicators.calculate_ma(df, 45)
        df['ma60'] = indicators.calculate_ma(df, 60)
        
        # 创建复权配置
        adjustment_config = create_adjustment_config(adjustment_type) if adjustment_type != 'none' else None
        
        # MACD指标
        macd_config = indicators.MACDIndicatorConfig(adjustment_config=adjustment_config)
        df['dif'], df['dea'] = indicators.calculate_macd(df, config=macd_config, stock_code=stock_code)
        df['macd'] = df['dif'] - df['dea']
        
        # KDJ指标
        kdj_config = indicators.KDJIndicatorConfig(adjustment_config=adjustment_config)
        df['k'], df['d'], df['j'] = indicators.calculate_kdj(df, config=kdj_config, stock_code=stock_code)
        
        # RSI指标
        df['rsi6'] = indicators.calculate_rsi(df, 6)
        df['rsi12'] = indicators.calculate_rsi(df, 12)
        df['rsi24'] = indicators.calculate_rsi(df, 24)
        
        # 布林带
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = indicators.calculate_bollinger_bands(df)
        
        return df
    
    def analyze_position_deep(self, stock_code: str, purchase_price: float, 
                            purchase_date: str) -> Dict:
        """深度分析单个持仓"""
        try:
            # 获取数据
            df = self.get_stock_data(stock_code)
            if df is None:
                return {'error': f'无法获取股票 {stock_code} 的数据'}
            
            # 计算技术指标
            df = self.calculate_technical_indicators(df, stock_code)
            
            # 获取最新数据
            latest = df.iloc[-1]
            current_price = float(latest['close'])
            
            # 计算持仓收益
            profit_loss = (current_price - purchase_price) / purchase_price * 100
            
            # 分析结果
            analysis = {
                'stock_code': stock_code,
                'current_price': current_price,
                'purchase_price': purchase_price,
                'profit_loss_pct': profit_loss,
                'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'technical_analysis': self._analyze_technical_indicators(df),
                'position_advice': self._generate_position_advice(df, purchase_price, purchase_date),
                'risk_assessment': self._assess_position_risk(df, purchase_price),
                'price_targets': self._calculate_price_targets(df, current_price),
                'timing_analysis': self._analyze_timing(df, purchase_date)
            }
            
            return analysis
            
        except Exception as e:
            return {'error': f'分析失败: {str(e)}'}
    
    def _analyze_technical_indicators(self, df: pd.DataFrame) -> Dict:
        """技术指标分析"""
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        analysis = {
            'trend_analysis': {},
            'momentum_analysis': {},
            'support_resistance': {}
        }
        
        # 趋势分析
        ma_signals = []
        if latest['close'] > latest['ma5']:
            ma_signals.append('价格在MA5之上')
        if latest['close'] > latest['ma13']:
            ma_signals.append('价格在MA13之上')
        if latest['ma5'] > latest['ma13']:
            ma_signals.append('MA5在MA13之上')
        if latest['ma13'] > latest['ma45']:
            ma_signals.append('MA13在MA45之上')
            
        analysis['trend_analysis'] = {
            'ma_signals': ma_signals,
            'trend_strength': len(ma_signals) / 4.0,  # 趋势强度评分
            'price_position': self._get_price_position(latest)
        }
        
        # 动量分析
        rsi = latest['rsi6']
        macd = latest['macd']
        kdj_k = latest['k']
        
        momentum_signals = []
        if rsi < 30:
            momentum_signals.append('RSI超卖')
        elif rsi > 70:
            momentum_signals.append('RSI超买')
        
        if macd > 0 and macd > prev['macd']:
            momentum_signals.append('MACD向上')
        elif macd < 0 and macd < prev['macd']:
            momentum_signals.append('MACD向下')
            
        if kdj_k > 80:
            momentum_signals.append('KDJ超买')
        elif kdj_k < 20:
            momentum_signals.append('KDJ超卖')
        
        analysis['momentum_analysis'] = {
            'rsi_value': float(rsi) if not pd.isna(rsi) else 50,
            'macd_value': float(macd) if not pd.isna(macd) else 0,
            'kdj_k_value': float(kdj_k) if not pd.isna(kdj_k) else 50,
            'momentum_signals': momentum_signals
        }
        
        # 支撑阻力分析
        recent_data = df.tail(30)
        resistance = float(recent_data['high'].max())
        support = float(recent_data['low'].min())
        
        analysis['support_resistance'] = {
            'resistance_level': resistance,
            'support_level': support,
            'distance_to_resistance': (resistance - latest['close']) / latest['close'] * 100,
            'distance_to_support': (latest['close'] - support) / latest['close'] * 100
        }
        
        return analysis
    
    def _get_price_position(self, latest_data) -> str:
        """获取价格相对位置"""
        price = latest_data['close']
        ma5 = latest_data['ma5']
        ma13 = latest_data['ma13']
        ma45 = latest_data['ma45']
        
        if price > ma5 > ma13 > ma45:
            return '强势上升'
        elif price > ma5 > ma13:
            return '中期上升'
        elif price > ma5:
            return '短期上升'
        elif price < ma5 < ma13 < ma45:
            return '弱势下降'
        elif price < ma5 < ma13:
            return '中期下降'
        else:
            return '震荡整理'
    
    def _generate_position_advice(self, df: pd.DataFrame, purchase_price: float, 
                                purchase_date: str) -> Dict:
        """生成持仓操作建议"""
        latest = df.iloc[-1]
        current_price = float(latest['close'])
        profit_pct = (current_price - purchase_price) / purchase_price * 100
        
        advice = {
            'action': 'HOLD',
            'confidence': 0.5,
            'reasons': [],
            'add_position_price': None,
            'reduce_position_price': None,
            'stop_loss_price': None
        }
        
        # 基于收益情况的建议
        if profit_pct > 20:
            advice['action'] = 'REDUCE'
            advice['confidence'] = 0.7
            advice['reasons'].append(f'已获利{profit_pct:.1f}%，建议减仓锁定利润')
            advice['reduce_position_price'] = current_price * 0.95
        elif profit_pct < -15:
            advice['action'] = 'STOP_LOSS'
            advice['confidence'] = 0.8
            advice['reasons'].append(f'亏损{abs(profit_pct):.1f}%，建议止损')
            advice['stop_loss_price'] = current_price * 0.98
        elif profit_pct < -5:
            # 检查是否适合补仓
            rsi = latest['rsi6']
            if not pd.isna(rsi) and rsi < 35:
                advice['action'] = 'ADD'
                advice['confidence'] = 0.6
                advice['reasons'].append('RSI超卖，价格回调，可考虑补仓')
                advice['add_position_price'] = current_price * 0.95
            else:
                advice['reasons'].append(f'小幅亏损{abs(profit_pct):.1f}%，继续观察')
        else:
            advice['reasons'].append(f'盈利{profit_pct:.1f}%，继续持有')
        
        # 技术面分析
        ma13 = latest['ma13']
        ma45 = latest['ma45']
        
        if not pd.isna(ma13) and not pd.isna(ma45):
            if current_price < ma45:
                advice['reasons'].append('价格跌破长期均线，趋势转弱')
                if advice['action'] == 'HOLD':
                    advice['action'] = 'WATCH'
                    advice['confidence'] = max(0.3, advice['confidence'] - 0.2)
            elif current_price > ma13 > ma45:
                advice['reasons'].append('价格在均线之上，趋势良好')
                advice['confidence'] = min(0.9, advice['confidence'] + 0.1)
        
        return advice
    
    def _assess_position_risk(self, df: pd.DataFrame, purchase_price: float) -> Dict:
        """评估持仓风险"""
        latest = df.iloc[-1]
        recent_data = df.tail(30)
        
        # 计算波动率
        returns = df['close'].pct_change().dropna()
        volatility = float(returns.std() * np.sqrt(252) * 100)  # 年化波动率
        
        # 计算最大回撤
        rolling_max = df['close'].rolling(window=30).max()
        drawdown = (df['close'] - rolling_max) / rolling_max
        max_drawdown = float(abs(drawdown.min()) * 100)
        
        # 风险等级评估
        risk_score = 0
        risk_factors = []
        
        if volatility > 40:
            risk_score += 3
            risk_factors.append(f'高波动率({volatility:.1f}%)')
        elif volatility > 25:
            risk_score += 2
            risk_factors.append(f'中等波动率({volatility:.1f}%)')
        else:
            risk_score += 1
            risk_factors.append(f'低波动率({volatility:.1f}%)')
        
        if max_drawdown > 20:
            risk_score += 3
            risk_factors.append(f'大幅回撤({max_drawdown:.1f}%)')
        elif max_drawdown > 10:
            risk_score += 2
            risk_factors.append(f'中等回撤({max_drawdown:.1f}%)')
        
        # 价格相对位置风险
        current_price = latest['close']
        recent_high = float(recent_data['high'].max())
        recent_low = float(recent_data['low'].min())
        
        price_position = (current_price - recent_low) / (recent_high - recent_low)
        if price_position > 0.8:
            risk_score += 2
            risk_factors.append('价格接近近期高点')
        elif price_position < 0.2:
            risk_factors.append('价格接近近期低点')
        
        # 风险等级
        if risk_score >= 6:
            risk_level = 'HIGH'
        elif risk_score >= 4:
            risk_level = 'MEDIUM'
        else:
            risk_level = 'LOW'
        
        return {
            'risk_level': risk_level,
            'risk_score': risk_score,
            'volatility': volatility,
            'max_drawdown': max_drawdown,
            'risk_factors': risk_factors,
            'price_position_pct': float(price_position * 100)
        }
    
    def _calculate_price_targets(self, df: pd.DataFrame, current_price: float) -> Dict:
        """计算价格目标"""
        recent_data = df.tail(60)
        
        # 支撑阻力位
        resistance_levels = []
        support_levels = []
        
        # 基于历史高低点
        highs = recent_data['high'].rolling(window=5).max()
        lows = recent_data['low'].rolling(window=5).min()
        
        # 找出重要的支撑阻力位
        for i in range(5, len(recent_data)-5):
            if highs.iloc[i] == recent_data['high'].iloc[i]:
                resistance_levels.append(float(recent_data['high'].iloc[i]))
            if lows.iloc[i] == recent_data['low'].iloc[i]:
                support_levels.append(float(recent_data['low'].iloc[i]))
        
        # 去重并排序
        resistance_levels = sorted(list(set(resistance_levels)), reverse=True)
        support_levels = sorted(list(set(support_levels)))
        
        # 找出最近的支撑阻力位
        next_resistance = None
        next_support = None
        
        for level in resistance_levels:
            if level > current_price:
                next_resistance = level
                break
        
        for level in reversed(support_levels):
            if level < current_price:
                next_support = level
                break
        
        # 基于技术指标的目标位
        latest = df.iloc[-1]
        bb_upper = latest['bb_upper'] if not pd.isna(latest['bb_upper']) else current_price * 1.1
        bb_lower = latest['bb_lower'] if not pd.isna(latest['bb_lower']) else current_price * 0.9
        
        return {
            'next_resistance': next_resistance,
            'next_support': next_support,
            'bb_upper_target': float(bb_upper),
            'bb_lower_target': float(bb_lower),
            'short_term_target': current_price * 1.05,  # 5%目标
            'medium_term_target': current_price * 1.15,  # 15%目标
            'stop_loss_level': current_price * 0.92  # 8%止损
        }
    
    def _analyze_timing(self, df: pd.DataFrame, purchase_date: str) -> Dict:
        """时间分析"""
        try:
            purchase_dt = datetime.strptime(purchase_date, '%Y-%m-%d')
            current_dt = datetime.now()
            holding_days = (current_dt - purchase_dt).days
            
            # 基于历史数据预测到顶时间
            recent_signals = self._find_recent_peaks(df)
            avg_cycle_days = self._calculate_average_cycle(recent_signals)
            
            # 预期到顶日期
            if avg_cycle_days and holding_days < avg_cycle_days:
                expected_peak_date = purchase_dt + timedelta(days=avg_cycle_days)
                days_to_peak = (expected_peak_date - current_dt).days
            else:
                expected_peak_date = None
                days_to_peak = None
            
            return {
                'holding_days': holding_days,
                'expected_peak_date': expected_peak_date.strftime('%Y-%m-%d') if expected_peak_date else None,
                'days_to_peak': days_to_peak,
                'avg_cycle_days': avg_cycle_days,
                'timing_advice': self._get_timing_advice(holding_days, days_to_peak)
            }
            
        except Exception as e:
            return {
                'error': f'时间分析失败: {str(e)}',
                'holding_days': 0
            }
    
    def _find_recent_peaks(self, df: pd.DataFrame, window: int = 10) -> List[int]:
        """找出近期的峰值点"""
        peaks = []
        highs = df['high'].values
        
        for i in range(window, len(highs) - window):
            if highs[i] == max(highs[i-window:i+window+1]):
                peaks.append(i)
        
        return peaks
    
    def _calculate_average_cycle(self, peaks: List[int]) -> Optional[int]:
        """计算平均周期"""
        if len(peaks) < 2:
            return None
        
        cycles = []
        for i in range(1, len(peaks)):
            cycles.append(peaks[i] - peaks[i-1])
        
        return int(np.mean(cycles)) if cycles else None
    
    def _get_timing_advice(self, holding_days: int, days_to_peak: Optional[int]) -> str:
        """获取时间建议"""
        if days_to_peak is None:
            if holding_days > 90:
                return '持有时间较长，建议关注卖出时机'
            else:
                return '继续持有，关注技术面变化'
        
        if days_to_peak <= 0:
            return '可能已接近周期高点，建议考虑减仓'
        elif days_to_peak <= 10:
            return f'预计{days_to_peak}天内可能到达高点，密切关注'
        elif days_to_peak <= 30:
            return f'预计{days_to_peak}天后可能到达高点，继续持有'
        else:
            return f'预计还有{days_to_peak}天到达高点，耐心持有'
    
    def scan_all_positions(self) -> Dict:
        """扫描所有持仓"""
        portfolio = self.load_portfolio()
        results = {
            'scan_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total_positions': len(portfolio),
            'positions': [],
            'summary': {
                'profitable_count': 0,
                'loss_count': 0,
                'total_profit_loss': 0,
                'high_risk_count': 0,
                'action_required_count': 0
            }
        }
        
        for position in portfolio:
            analysis = self.analyze_position_deep(
                position['stock_code'],
                position['purchase_price'],
                position['purchase_date']
            )
            
            if 'error' not in analysis:
                # 更新持仓的最后分析时间
                self.update_position(position['stock_code'], 
                                   last_analysis_time=analysis['analysis_time'])
                
                # 统计汇总
                profit_loss = analysis['profit_loss_pct']
                if profit_loss > 0:
                    results['summary']['profitable_count'] += 1
                else:
                    results['summary']['loss_count'] += 1
                
                results['summary']['total_profit_loss'] += profit_loss
                
                if analysis['risk_assessment']['risk_level'] == 'HIGH':
                    results['summary']['high_risk_count'] += 1
                
                if analysis['position_advice']['action'] in ['REDUCE', 'STOP_LOSS', 'ADD']:
                    results['summary']['action_required_count'] += 1
            
            # 合并持仓基本信息和分析结果
            position_result = {**position, **analysis}
            results['positions'].append(position_result)
        
        return results


# 便捷函数
def create_portfolio_manager() -> PortfolioManager:
    """创建持仓管理器实例"""
    return PortfolioManager()