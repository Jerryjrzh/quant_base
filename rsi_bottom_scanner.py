#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSI底部扫描器 - 基于RSI6指标识别短期底部入手机会
根据RSI短期周期预期RSI6底部和价格底部的到达时间，按置信度排序
"""

import os
import sys
import glob
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from multiprocessing import Pool, cpu_count
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import logging

# 添加backend目录到路径
backend_dir = os.path.dirname(os.path.abspath(__file__))
if os.path.exists(os.path.join(backend_dir, 'backend')):
    sys.path.insert(0, os.path.join(backend_dir, 'backend'))
else:
    sys.path.insert(0, backend_dir)

import data_loader
import indicators

@dataclass
class RSIBottomSignal:
    """RSI底部信号数据结构"""
    stock_code: str
    current_price: float
    current_rsi6: float
    current_rsi12: float
    current_rsi24: float
    
    # 底部预测
    predicted_bottom_days: int  # 预计到达底部的天数
    predicted_bottom_price: float  # 预计底部价格
    predicted_bottom_rsi6: float  # 预计RSI6底部值
    
    # 置信度评估
    confidence_score: float  # 0-1之间的置信度
    confidence_factors: Dict[str, float]  # 各项置信度因子
    
    # 技术分析
    price_trend: str  # 价格趋势：下降/横盘/上升
    rsi_divergence: bool  # RSI与价格是否存在背离
    volume_confirmation: bool  # 成交量是否确认
    
    # 历史表现
    historical_accuracy: float  # 历史预测准确率
    avg_rebound_gain: float  # 平均反弹收益
    
    # 风险评估
    risk_level: str  # 风险等级：低/中/高
    stop_loss_price: float  # 建议止损价
    
    # 时间信息
    scan_date: str
    last_update: str

class RSIBottomAnalyzer:
    """RSI底部分析器"""
    
    def __init__(self):
        self.rsi6_oversold_threshold = 20  # RSI6超卖阈值
        self.rsi6_extreme_oversold = 10    # RSI6极度超卖
        self.min_data_points = 120         # 最少数据点要求
        
        # 历史回测参数
        self.lookback_periods = 252  # 回看一年数据
        self.rebound_check_days = 20  # 反弹检查天数
        
    def analyze_rsi_bottom_opportunity(self, df: pd.DataFrame, stock_code: str) -> Optional[RSIBottomSignal]:
        """分析单只股票的RSI底部机会"""
        try:
            if len(df) < self.min_data_points:
                return None
            
            # 计算多周期RSI
            rsi6 = indicators.calculate_rsi(df, periods=6)
            rsi12 = indicators.calculate_rsi(df, periods=12)
            rsi24 = indicators.calculate_rsi(df, periods=24)
            
            # 添加到DataFrame
            df['rsi6'] = rsi6
            df['rsi12'] = rsi12
            df['rsi24'] = rsi24
            
            current_idx = len(df) - 1
            current_price = df['close'].iloc[current_idx]
            current_rsi6 = rsi6.iloc[current_idx]
            current_rsi12 = rsi12.iloc[current_idx]
            current_rsi24 = rsi24.iloc[current_idx]
            
            # 检查是否处于RSI底部区域
            if not self._is_in_bottom_zone(current_rsi6, current_rsi12):
                return None
            
            # 预测底部时间和价格
            bottom_prediction = self._predict_bottom_timing(df, current_idx)
            if not bottom_prediction:
                return None
            
            # 计算置信度
            confidence_analysis = self._calculate_confidence(df, current_idx, bottom_prediction)
            
            # 分析技术面
            technical_analysis = self._analyze_technical_factors(df, current_idx)
            
            # 历史表现分析
            historical_performance = self._analyze_historical_performance(df, current_idx)
            
            # 风险评估
            risk_assessment = self._assess_risk(df, current_idx, current_price)
            
            # 构建信号
            signal = RSIBottomSignal(
                stock_code=stock_code,
                current_price=current_price,
                current_rsi6=current_rsi6,
                current_rsi12=current_rsi12,
                current_rsi24=current_rsi24,
                
                predicted_bottom_days=bottom_prediction['days_to_bottom'],
                predicted_bottom_price=bottom_prediction['predicted_price'],
                predicted_bottom_rsi6=bottom_prediction['predicted_rsi6'],
                
                confidence_score=confidence_analysis['total_confidence'],
                confidence_factors=confidence_analysis['factors'],
                
                price_trend=technical_analysis['price_trend'],
                rsi_divergence=technical_analysis['rsi_divergence'],
                volume_confirmation=technical_analysis['volume_confirmation'],
                
                historical_accuracy=historical_performance['accuracy'],
                avg_rebound_gain=historical_performance['avg_gain'],
                
                risk_level=risk_assessment['risk_level'],
                stop_loss_price=risk_assessment['stop_loss'],
                
                scan_date=datetime.now().strftime('%Y-%m-%d'),
                last_update=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
            
            return signal
            
        except Exception as e:
            logging.error(f"分析{stock_code}时出错: {e}")
            return None
    
    def _is_in_bottom_zone(self, rsi6: float, rsi12: float) -> bool:
        """判断是否处于底部区域"""
        # RSI6必须在超卖区域或接近
        if rsi6 > 30:
            return False
        
        # RSI12也应该相对较低
        if rsi12 > 40:
            return False
        
        return True
    
    def _predict_bottom_timing(self, df: pd.DataFrame, current_idx: int) -> Optional[Dict]:
        """预测底部到达时间"""
        try:
            # 分析RSI6的下降趋势
            rsi6_series = df['rsi6'].iloc[max(0, current_idx-20):current_idx+1]
            
            if len(rsi6_series) < 10:
                return None
            
            # 计算RSI6的变化率
            rsi6_change_rate = rsi6_series.diff().mean()
            current_rsi6 = rsi6_series.iloc[-1]
            
            # 预测到达极值的天数
            if rsi6_change_rate >= 0:  # 如果RSI6已经开始上升
                days_to_bottom = 0
                predicted_rsi6 = current_rsi6
            else:
                # 预测到达10-15区间的天数
                target_rsi6 = 12.5  # 目标RSI6值
                if current_rsi6 <= target_rsi6:
                    days_to_bottom = 0
                    predicted_rsi6 = current_rsi6
                else:
                    days_to_bottom = min(10, max(1, int((current_rsi6 - target_rsi6) / abs(rsi6_change_rate))))
                    predicted_rsi6 = max(5, current_rsi6 + rsi6_change_rate * days_to_bottom)
            
            # 基于RSI预测价格
            current_price = df['close'].iloc[current_idx]
            price_rsi_correlation = self._calculate_price_rsi_correlation(df, current_idx)
            
            if price_rsi_correlation != 0:
                rsi_price_ratio = (predicted_rsi6 - current_rsi6) / current_rsi6
                predicted_price_change = rsi_price_ratio * price_rsi_correlation
                predicted_price = current_price * (1 + predicted_price_change)
            else:
                predicted_price = current_price * 0.95  # 默认预期下跌5%
            
            return {
                'days_to_bottom': days_to_bottom,
                'predicted_price': predicted_price,
                'predicted_rsi6': predicted_rsi6
            }
            
        except Exception as e:
            logging.error(f"预测底部时间失败: {e}")
            return None
    
    def _calculate_price_rsi_correlation(self, df: pd.DataFrame, current_idx: int) -> float:
        """计算价格与RSI6的相关性"""
        try:
            lookback = min(60, current_idx)
            if lookback < 20:
                return 0.5  # 默认相关性
            
            start_idx = current_idx - lookback
            price_changes = df['close'].iloc[start_idx:current_idx+1].pct_change()
            rsi6_changes = df['rsi6'].iloc[start_idx:current_idx+1].pct_change()
            
            correlation = price_changes.corr(rsi6_changes)
            return correlation if not pd.isna(correlation) else 0.5
            
        except:
            return 0.5
    
    def _calculate_confidence(self, df: pd.DataFrame, current_idx: int, bottom_prediction: Dict) -> Dict:
        """计算置信度"""
        factors = {}
        
        # 1. RSI位置置信度 (0-0.3)
        current_rsi6 = df['rsi6'].iloc[current_idx]
        if current_rsi6 <= 10:
            factors['rsi_position'] = 0.3
        elif current_rsi6 <= 15:
            factors['rsi_position'] = 0.25
        elif current_rsi6 <= 20:
            factors['rsi_position'] = 0.2
        else:
            factors['rsi_position'] = 0.1
        
        # 2. 趋势一致性 (0-0.2)
        rsi6_trend = self._calculate_trend_consistency(df['rsi6'], current_idx, 10)
        factors['trend_consistency'] = 0.2 if rsi6_trend < -0.5 else 0.1
        
        # 3. 成交量确认 (0-0.15)
        volume_factor = self._analyze_volume_pattern(df, current_idx)
        factors['volume_confirmation'] = volume_factor * 0.15
        
        # 4. 历史准确性 (0-0.2)
        historical_accuracy = self._get_historical_accuracy(df, current_idx)
        factors['historical_accuracy'] = historical_accuracy * 0.2
        
        # 5. 多周期RSI一致性 (0-0.15)
        multi_rsi_consistency = self._check_multi_rsi_consistency(df, current_idx)
        factors['multi_rsi_consistency'] = multi_rsi_consistency * 0.15
        
        total_confidence = sum(factors.values())
        
        return {
            'total_confidence': min(1.0, total_confidence),
            'factors': factors
        }
    
    def _calculate_trend_consistency(self, series: pd.Series, current_idx: int, lookback: int) -> float:
        """计算趋势一致性"""
        try:
            if current_idx < lookback:
                return 0
            
            recent_data = series.iloc[current_idx-lookback:current_idx+1]
            trend = np.polyfit(range(len(recent_data)), recent_data, 1)[0]
            return trend
            
        except:
            return 0
    
    def _analyze_volume_pattern(self, df: pd.DataFrame, current_idx: int) -> float:
        """分析成交量模式"""
        try:
            if 'volume' not in df.columns or current_idx < 20:
                return 0.5
            
            recent_volume = df['volume'].iloc[current_idx-5:current_idx+1].mean()
            avg_volume = df['volume'].iloc[current_idx-20:current_idx-5].mean()
            
            if avg_volume == 0:
                return 0.5
            
            volume_ratio = recent_volume / avg_volume
            
            # 适度放量更好
            if 1.2 <= volume_ratio <= 2.0:
                return 1.0
            elif 1.0 <= volume_ratio < 1.2:
                return 0.8
            elif 0.8 <= volume_ratio < 1.0:
                return 0.6
            else:
                return 0.3
                
        except:
            return 0.5
    
    def _get_historical_accuracy(self, df: pd.DataFrame, current_idx: int) -> float:
        """获取历史预测准确性"""
        try:
            # 简化的历史准确性计算
            # 查找过去的RSI底部信号，检查后续表现
            
            lookback = min(self.lookback_periods, current_idx - 30)
            if lookback < 60:
                return 0.6  # 默认准确性
            
            rsi6_series = df['rsi6'].iloc[current_idx-lookback:current_idx]
            price_series = df['close'].iloc[current_idx-lookback:current_idx]
            
            # 找到历史RSI6底部点
            bottom_signals = []
            for i in range(10, len(rsi6_series)-10):
                if (rsi6_series.iloc[i] <= 20 and 
                    rsi6_series.iloc[i] == rsi6_series.iloc[i-5:i+6].min()):
                    bottom_signals.append(i)
            
            if len(bottom_signals) < 3:
                return 0.6
            
            # 检查这些底部信号后的表现
            successful_signals = 0
            for signal_idx in bottom_signals:
                if signal_idx + 20 < len(price_series):
                    entry_price = price_series.iloc[signal_idx]
                    future_prices = price_series.iloc[signal_idx:signal_idx+20]
                    max_gain = (future_prices.max() - entry_price) / entry_price
                    
                    if max_gain > 0.05:  # 5%以上收益算成功
                        successful_signals += 1
            
            accuracy = successful_signals / len(bottom_signals)
            return min(1.0, accuracy)
            
        except:
            return 0.6
    
    def _check_multi_rsi_consistency(self, df: pd.DataFrame, current_idx: int) -> float:
        """检查多周期RSI一致性"""
        try:
            rsi6 = df['rsi6'].iloc[current_idx]
            rsi12 = df['rsi12'].iloc[current_idx]
            rsi24 = df['rsi24'].iloc[current_idx]
            
            # 检查RSI是否都在相对低位
            low_count = 0
            if rsi6 <= 25:
                low_count += 1
            if rsi12 <= 35:
                low_count += 1
            if rsi24 <= 45:
                low_count += 1
            
            return low_count / 3.0
            
        except:
            return 0.5
    
    def _analyze_technical_factors(self, df: pd.DataFrame, current_idx: int) -> Dict:
        """分析技术面因素"""
        try:
            # 价格趋势
            if current_idx >= 20:
                recent_prices = df['close'].iloc[current_idx-20:current_idx+1]
                price_trend_slope = np.polyfit(range(len(recent_prices)), recent_prices, 1)[0]
                
                if price_trend_slope > 0.01:
                    price_trend = "上升"
                elif price_trend_slope < -0.01:
                    price_trend = "下降"
                else:
                    price_trend = "横盘"
            else:
                price_trend = "数据不足"
            
            # RSI背离分析
            rsi_divergence = self._detect_rsi_divergence(df, current_idx)
            
            # 成交量确认
            volume_confirmation = self._analyze_volume_pattern(df, current_idx) > 0.7
            
            return {
                'price_trend': price_trend,
                'rsi_divergence': rsi_divergence,
                'volume_confirmation': volume_confirmation
            }
            
        except:
            return {
                'price_trend': "未知",
                'rsi_divergence': False,
                'volume_confirmation': False
            }
    
    def _detect_rsi_divergence(self, df: pd.DataFrame, current_idx: int) -> bool:
        """检测RSI背离"""
        try:
            if current_idx < 40:
                return False
            
            # 查找最近的价格低点和RSI低点
            lookback = 30
            price_data = df['close'].iloc[current_idx-lookback:current_idx+1]
            rsi_data = df['rsi6'].iloc[current_idx-lookback:current_idx+1]
            
            # 找到最近两个低点
            price_lows = []
            rsi_lows = []
            
            for i in range(5, len(price_data)-5):
                if (price_data.iloc[i] == price_data.iloc[i-5:i+6].min() and
                    price_data.iloc[i] < price_data.iloc[i-1] and
                    price_data.iloc[i] < price_data.iloc[i+1]):
                    price_lows.append((i, price_data.iloc[i]))
                    rsi_lows.append((i, rsi_data.iloc[i]))
            
            if len(price_lows) >= 2:
                # 检查是否存在底背离
                latest_price_low = price_lows[-1][1]
                prev_price_low = price_lows[-2][1]
                latest_rsi_low = rsi_lows[-1][1]
                prev_rsi_low = rsi_lows[-2][1]
                
                # 价格创新低但RSI没有创新低
                if latest_price_low < prev_price_low and latest_rsi_low > prev_rsi_low:
                    return True
            
            return False
            
        except:
            return False
    
    def _analyze_historical_performance(self, df: pd.DataFrame, current_idx: int) -> Dict:
        """分析历史表现"""
        try:
            accuracy = self._get_historical_accuracy(df, current_idx)
            
            # 计算平均反弹收益
            avg_gain = self._calculate_average_rebound_gain(df, current_idx)
            
            return {
                'accuracy': accuracy,
                'avg_gain': avg_gain
            }
            
        except:
            return {
                'accuracy': 0.6,
                'avg_gain': 0.08
            }
    
    def _calculate_average_rebound_gain(self, df: pd.DataFrame, current_idx: int) -> float:
        """计算平均反弹收益"""
        try:
            lookback = min(self.lookback_periods, current_idx - 30)
            if lookback < 60:
                return 0.08  # 默认8%
            
            rsi6_series = df['rsi6'].iloc[current_idx-lookback:current_idx]
            price_series = df['close'].iloc[current_idx-lookback:current_idx]
            
            gains = []
            for i in range(10, len(rsi6_series)-20):
                if rsi6_series.iloc[i] <= 20:
                    entry_price = price_series.iloc[i]
                    future_prices = price_series.iloc[i:i+20]
                    max_gain = (future_prices.max() - entry_price) / entry_price
                    gains.append(max_gain)
            
            return np.mean(gains) if gains else 0.08
            
        except:
            return 0.08
    
    def _assess_risk(self, df: pd.DataFrame, current_idx: int, current_price: float) -> Dict:
        """评估风险"""
        try:
            # 基于ATR计算止损
            if current_idx >= 14:
                atr = indicators.calculate_atr(df, 14).iloc[current_idx]
                stop_loss = current_price - (atr * 2)
            else:
                stop_loss = current_price * 0.92  # 默认8%止损
            
            # 风险等级评估
            rsi6 = df['rsi6'].iloc[current_idx]
            if rsi6 <= 10:
                risk_level = "低"
            elif rsi6 <= 20:
                risk_level = "中"
            else:
                risk_level = "高"
            
            return {
                'risk_level': risk_level,
                'stop_loss': stop_loss
            }
            
        except:
            return {
                'risk_level': "中",
                'stop_loss': current_price * 0.92
            }

class RSIBottomScanner:
    """RSI底部扫描器主类"""
    
    def __init__(self):
        self.base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        self.markets = ['sh', 'sz', 'bj']
        self.analyzer = RSIBottomAnalyzer()
        
        # 设置日志
        self.setup_logging()
        
    def setup_logging(self):
        """设置日志"""
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f'rsi_bottom_scan_{datetime.now().strftime("%Y%m%d_%H%M")}.log')
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
    
    def scan_single_stock(self, args) -> Optional[RSIBottomSignal]:
        """扫描单只股票"""
        file_path, market = args
        stock_code_full = os.path.basename(file_path).split('.')[0]
        stock_code_no_prefix = stock_code_full.replace(market, '')
        
        # 过滤无效股票代码
        valid_prefixes = ('600', '601', '603', '000', '001', '002', '003', '300', '688')
        if not stock_code_no_prefix.startswith(valid_prefixes):
            return None
        
        try:
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 120:
                return None
            
            signal = self.analyzer.analyze_rsi_bottom_opportunity(df, stock_code_full)
            return signal
            
        except Exception as e:
            logging.error(f"扫描{stock_code_full}失败: {e}")
            return None
    
    def run_scan(self) -> List[RSIBottomSignal]:
        """运行扫描"""
        print("🔍 开始RSI底部扫描...")
        start_time = datetime.now()
        
        # 收集所有文件
        all_files = []
        for market in self.markets:
            path = os.path.join(self.base_path, market, 'lday', '*.day')
            files = glob.glob(path)
            all_files.extend([(f, market) for f in files])
        
        if not all_files:
            print("❌ 未找到数据文件")
            return []
        
        print(f"📊 找到{len(all_files)}个数据文件，开始多进程扫描...")
        
        # 多进程扫描
        with Pool(processes=cpu_count()) as pool:
            results = pool.map(self.scan_single_stock, all_files)
        
        # 过滤有效信号
        valid_signals = [r for r in results if r is not None]
        
        # 按置信度排序
        valid_signals.sort(key=lambda x: x.confidence_score, reverse=True)
        
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()
        
        print(f"✅ 扫描完成！")
        print(f"📈 发现{len(valid_signals)}个RSI底部机会")
        print(f"⏱️ 耗时: {processing_time:.2f}秒")
        
        return valid_signals
    
    def save_results(self, signals: List[RSIBottomSignal], output_dir: str = None):
        """保存扫描结果"""
        if not signals:
            print("⚠️ 没有信号需要保存")
            return
        
        if output_dir is None:
            output_dir = os.path.join(os.path.dirname(__file__), 'rsi_scan_results')
        
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 保存JSON格式
        json_file = os.path.join(output_dir, f'rsi_bottom_signals_{timestamp}.json')
        signals_data = []
        
        for signal in signals:
            signals_data.append({
                'stock_code': signal.stock_code,
                'current_price': signal.current_price,
                'current_rsi6': signal.current_rsi6,
                'current_rsi12': signal.current_rsi12,
                'current_rsi24': signal.current_rsi24,
                'predicted_bottom_days': signal.predicted_bottom_days,
                'predicted_bottom_price': signal.predicted_bottom_price,
                'predicted_bottom_rsi6': signal.predicted_bottom_rsi6,
                'confidence_score': signal.confidence_score,
                'confidence_factors': signal.confidence_factors,
                'price_trend': signal.price_trend,
                'rsi_divergence': signal.rsi_divergence,
                'volume_confirmation': signal.volume_confirmation,
                'historical_accuracy': signal.historical_accuracy,
                'avg_rebound_gain': signal.avg_rebound_gain,
                'risk_level': signal.risk_level,
                'stop_loss_price': signal.stop_loss_price,
                'scan_date': signal.scan_date,
                'last_update': signal.last_update
            })
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(signals_data, f, ensure_ascii=False, indent=2)
        
        # 保存文本报告
        txt_file = os.path.join(output_dir, f'rsi_bottom_report_{timestamp}.txt')
        self.generate_text_report(signals, txt_file)
        
        print(f"📄 结果已保存:")
        print(f"  JSON: {json_file}")
        print(f"  报告: {txt_file}")
    
    def generate_text_report(self, signals: List[RSIBottomSignal], output_file: str):
        """生成文本报告"""
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("RSI底部扫描报告\n")
            f.write("=" * 80 + "\n")
            f.write(f"扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"发现信号: {len(signals)}个\n\n")
            
            if not signals:
                f.write("未发现符合条件的RSI底部机会\n")
                return
            
            # 统计信息
            high_confidence = len([s for s in signals if s.confidence_score >= 0.7])
            medium_confidence = len([s for s in signals if 0.5 <= s.confidence_score < 0.7])
            low_confidence = len([s for s in signals if s.confidence_score < 0.5])
            
            f.write("置信度分布:\n")
            f.write(f"  高置信度 (≥70%): {high_confidence}个\n")
            f.write(f"  中置信度 (50-70%): {medium_confidence}个\n")
            f.write(f"  低置信度 (<50%): {low_confidence}个\n\n")
            
            # 风险等级分布
            risk_stats = {}
            for signal in signals:
                risk_stats[signal.risk_level] = risk_stats.get(signal.risk_level, 0) + 1
            
            f.write("风险等级分布:\n")
            for risk, count in risk_stats.items():
                f.write(f"  {risk}风险: {count}个\n")
            f.write("\n")
            
            # 详细信号列表
            f.write("=" * 80 + "\n")
            f.write("详细信号列表 (按置信度排序)\n")
            f.write("=" * 80 + "\n\n")
            
            for i, signal in enumerate(signals, 1):
                f.write(f"{i:2d}. {signal.stock_code}\n")
                f.write(f"    当前价格: ¥{signal.current_price:.2f}\n")
                f.write(f"    RSI指标: RSI6={signal.current_rsi6:.1f}, RSI12={signal.current_rsi12:.1f}, RSI24={signal.current_rsi24:.1f}\n")
                f.write(f"    底部预测: {signal.predicted_bottom_days}天后到达¥{signal.predicted_bottom_price:.2f} (RSI6={signal.predicted_bottom_rsi6:.1f})\n")
                f.write(f"    置信度: {signal.confidence_score:.1%} ({signal.risk_level}风险)\n")
                f.write(f"    技术面: {signal.price_trend}趋势")
                if signal.rsi_divergence:
                    f.write(", RSI背离")
                if signal.volume_confirmation:
                    f.write(", 成交量确认")
                f.write("\n")
                f.write(f"    历史表现: 准确率{signal.historical_accuracy:.1%}, 平均收益{signal.avg_rebound_gain:.1%}\n")
                f.write(f"    建议止损: ¥{signal.stop_loss_price:.2f}\n")
                f.write(f"    置信度因子: ")
                for factor, value in signal.confidence_factors.items():
                    f.write(f"{factor}={value:.2f} ")
                f.write("\n\n")

def main():
    """主函数"""
    scanner = RSIBottomScanner()
    signals = scanner.run_scan()
    
    if signals:
        scanner.save_results(signals)
        
        print("\n🎯 推荐入手顺序 (前10名):")
        print("-" * 80)
        for i, signal in enumerate(signals[:10], 1):
            confidence_emoji = "🟢" if signal.confidence_score >= 0.7 else "🟡" if signal.confidence_score >= 0.5 else "🔴"
            risk_emoji = "🟢" if signal.risk_level == "低" else "🟡" if signal.risk_level == "中" else "🔴"
            
            print(f"{i:2d}. {signal.stock_code} {confidence_emoji}{risk_emoji}")
            print(f"    价格: ¥{signal.current_price:.2f} | RSI6: {signal.current_rsi6:.1f}")
            print(f"    预测: {signal.predicted_bottom_days}天后见底¥{signal.predicted_bottom_price:.2f}")
            print(f"    置信度: {signal.confidence_score:.1%} | 历史收益: {signal.avg_rebound_gain:.1%}")
            print()
    else:
        print("⚠️ 当前市场条件下未发现合适的RSI底部机会")

if __name__ == "__main__":
    main()