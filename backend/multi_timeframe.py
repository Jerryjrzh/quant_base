import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import data_loader
import indicators
import strategies

class MultiTimeframeAnalyzer:
    """多周期分析器"""
    
    def __init__(self, stock_code, base_path=None):
        self.stock_code = stock_code
        self.base_path = base_path
        self.data = {}
        self.indicators = {}
        self.signals = {}
        
    def load_data(self):
        """加载多周期数据"""
        try:
            # 获取多周期原始数据
            multi_data = data_loader.get_multi_timeframe_data(self.stock_code, self.base_path)
            
            self.data['daily'] = multi_data['daily_data']
            self.data['5min'] = multi_data['min5_data']
            
            # 如果有5分钟数据，生成其他周期
            if self.data['5min'] is not None:
                resampled = data_loader.resample_5min_to_other_timeframes(self.data['5min'])
                self.data.update(resampled)
            
            return {
                'success': True,
                'available_timeframes': list(self.data.keys()),
                'data_status': multi_data['data_status']
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'available_timeframes': [],
                'data_status': {'daily_available': False, 'min5_available': False}
            }
    
    def calculate_indicators(self, timeframes=None):
        """计算多周期技术指标"""
        if timeframes is None:
            timeframes = list(self.data.keys())
        
        for tf in timeframes:
            if tf not in self.data or self.data[tf] is None:
                continue
                
            df = self.data[tf].copy()
            
            try:
                # 计算移动平均线
                df['ma5'] = df['close'].rolling(5).mean()
                df['ma10'] = df['close'].rolling(10).mean()
                df['ma20'] = df['close'].rolling(20).mean()
                df['ma60'] = df['close'].rolling(60).mean()
                
                # 计算MACD
                df['dif'], df['dea'] = indicators.calculate_macd(df)
                df['macd'] = df['dif'] - df['dea']
                
                # 计算KDJ
                df['k'], df['d'], df['j'] = indicators.calculate_kdj(df)
                
                # 计算RSI
                df['rsi6'] = indicators.calculate_rsi(df, 6)
                df['rsi12'] = indicators.calculate_rsi(df, 12)
                df['rsi24'] = indicators.calculate_rsi(df, 24)
                
                # 计算成交量指标
                df['volume_ma5'] = df['volume'].rolling(5).mean()
                df['volume_ma10'] = df['volume'].rolling(10).mean()
                
                # 计算价格变化率
                df['price_change'] = df['close'].pct_change()
                df['price_change_5'] = df['close'].pct_change(5)
                
                self.indicators[tf] = df
                
            except Exception as e:
                print(f"计算{tf}周期指标失败: {e}")
                continue
    
    def apply_strategies(self, strategy_name='MACD_ZERO_AXIS', timeframes=None):
        """应用多周期策略分析"""
        if timeframes is None:
            timeframes = list(self.indicators.keys())
        
        for tf in timeframes:
            if tf not in self.indicators:
                continue
                
            df = self.indicators[tf]
            
            try:
                if strategy_name == 'MACD_ZERO_AXIS':
                    signals = strategies.apply_macd_zero_axis_strategy(df)
                elif strategy_name == 'PRE_CROSS':
                    signals = strategies.apply_pre_cross(df)
                elif strategy_name == 'TRIPLE_CROSS':
                    signals = strategies.apply_triple_cross(df)
                else:
                    signals = None
                
                self.signals[tf] = signals
                
            except Exception as e:
                print(f"应用{tf}周期策略失败: {e}")
                continue
    
    def get_multi_timeframe_consensus(self, strategy_name='MACD_ZERO_AXIS'):
        """获取多周期共振分析"""
        consensus_result = {
            'stock_code': self.stock_code,
            'strategy': strategy_name,
            'timeframe_signals': {},
            'consensus_score': 0,
            'consensus_level': 'NONE',
            'recommendation': 'HOLD'
        }
        
        # 定义周期权重（日线权重最高）
        timeframe_weights = {
            'daily': 0.4,
            '60min': 0.25,
            '30min': 0.15,
            '15min': 0.1,
            '5min': 0.1
        }
        
        total_weight = 0
        weighted_score = 0
        
        for tf in ['daily', '60min', '30min', '15min', '5min']:
            if tf not in self.signals or self.signals[tf] is None:
                continue
            
            signals = self.signals[tf]
            weight = timeframe_weights.get(tf, 0)
            
            # 分析信号强度
            if hasattr(signals, 'dtype') and signals.dtype == bool:
                # 布尔类型信号
                signal_strength = 1.0 if signals.iloc[-1] else 0.0
                signal_state = 'SIGNAL' if signals.iloc[-1] else 'NO_SIGNAL'
            else:
                # 状态类型信号
                latest_signal = signals.iloc[-1]
                if latest_signal in ['PRE', 'MID', 'POST']:
                    signal_strength = {'PRE': 0.6, 'MID': 1.0, 'POST': 0.8}.get(latest_signal, 0)
                    signal_state = latest_signal
                else:
                    signal_strength = 0.0
                    signal_state = 'NO_SIGNAL'
            
            consensus_result['timeframe_signals'][tf] = {
                'signal_state': signal_state,
                'signal_strength': signal_strength,
                'weight': weight
            }
            
            weighted_score += signal_strength * weight
            total_weight += weight
        
        # 计算共振得分
        if total_weight > 0:
            consensus_result['consensus_score'] = weighted_score / total_weight
        
        # 确定共振级别和建议
        score = consensus_result['consensus_score']
        if score >= 0.8:
            consensus_result['consensus_level'] = 'STRONG'
            consensus_result['recommendation'] = 'BUY'
        elif score >= 0.6:
            consensus_result['consensus_level'] = 'MODERATE'
            consensus_result['recommendation'] = 'BUY'
        elif score >= 0.4:
            consensus_result['consensus_level'] = 'WEAK'
            consensus_result['recommendation'] = 'WATCH'
        else:
            consensus_result['consensus_level'] = 'NONE'
            consensus_result['recommendation'] = 'HOLD'
        
        return consensus_result
    
    def get_timeframe_analysis_summary(self):
        """获取多周期分析汇总"""
        summary = {
            'stock_code': self.stock_code,
            'analysis_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'available_timeframes': list(self.data.keys()),
            'timeframe_details': {}
        }
        
        for tf in self.indicators.keys():
            df = self.indicators[tf]
            if df is None or df.empty:
                continue
            
            latest_data = df.iloc[-1]
            
            # 计算趋势方向
            ma_trend = 'UP' if latest_data['close'] > latest_data.get('ma20', latest_data['close']) else 'DOWN'
            
            # MACD趋势
            macd_trend = 'UP' if latest_data.get('macd', 0) > 0 else 'DOWN'
            
            # RSI状态
            rsi_value = latest_data.get('rsi12', 50)
            if rsi_value > 70:
                rsi_status = 'OVERBOUGHT'
            elif rsi_value < 30:
                rsi_status = 'OVERSOLD'
            else:
                rsi_status = 'NORMAL'
            
            summary['timeframe_details'][tf] = {
                'latest_price': float(latest_data['close']),
                'ma_trend': ma_trend,
                'macd_trend': macd_trend,
                'rsi_value': float(rsi_value),
                'rsi_status': rsi_status,
                'volume_ratio': float(latest_data['volume'] / latest_data.get('volume_ma5', latest_data['volume'])) if latest_data.get('volume_ma5', 0) > 0 else 1.0
            }
        
        return summary

def analyze_multi_timeframe_stock(stock_code, strategy_name='MACD_ZERO_AXIS', base_path=None):
    """分析单只股票的多周期数据"""
    analyzer = MultiTimeframeAnalyzer(stock_code, base_path)
    
    # 加载数据
    load_result = analyzer.load_data()
    if not load_result['success']:
        return {
            'success': False,
            'error': load_result['error'],
            'stock_code': stock_code
        }
    
    # 计算指标
    analyzer.calculate_indicators()
    
    # 应用策略
    analyzer.apply_strategies(strategy_name)
    
    # 获取共振分析
    consensus = analyzer.get_multi_timeframe_consensus(strategy_name)
    
    # 获取分析汇总
    summary = analyzer.get_timeframe_analysis_summary()
    
    return {
        'success': True,
        'stock_code': stock_code,
        'data_status': load_result['data_status'],
        'available_timeframes': load_result['available_timeframes'],
        'consensus_analysis': consensus,
        'timeframe_summary': summary,
        'raw_data': {tf: df.tail(50).to_dict('records') for tf, df in analyzer.indicators.items()}  # 返回最近50条数据
    }