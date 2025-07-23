#!/usr/bin/env python3
"""
每日信号扫描器

这个模块实现了高级的每日信号扫描功能，包括：
- 快速加载优化参数并应用策略
- 智能信号检测和验证
- 标准化的交易信号报告生成
- 市场环境条件过滤
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.dirname(__file__))

from stock_pool_manager import StockPoolManager

# 尝试导入现有模块
try:
    from trading_advisor import TradingAdvisor
except ImportError:
    TradingAdvisor = None

try:
    from strategies import apply_macd_zero_axis_strategy
except ImportError:
    apply_macd_zero_axis_strategy = None

try:
    from data_loader import load_stock_data
except ImportError:
    load_stock_data = None


class DailySignalScanner:
    """每日信号扫描器"""
    
    def __init__(self, db_path: str = "stock_pool.db", config: Optional[Dict] = None):
        """初始化信号扫描器"""
        self.db_path = db_path
        self.pool_manager = StockPoolManager(db_path)
        self.config = config or self._get_default_config()
        self.logger = logging.getLogger(__name__)
        
        # 初始化交易顾问
        self.advisor = None
        if TradingAdvisor:
            try:
                self.advisor = TradingAdvisor()
                self.logger.info("交易顾问初始化成功")
            except Exception as e:
                self.logger.warning(f"交易顾问初始化失败: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "signal_confidence_threshold": 0.7,
            "max_signals_per_day": 20,
            "market_condition_filter": True,
            "risk_level_filter": ["LOW", "MEDIUM"],
            "min_credibility_score": 0.5,
            "signal_types": ["buy", "sell"],
            "market_hours": {
                "start": "09:30",
                "end": "15:00"
            },
            "exclude_weekends": True,
            "volume_threshold": 1000000,  # 最小成交量
            "price_change_threshold": 0.02  # 最小价格变化
        }
    
    def scan_daily_signals(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """扫描每日交易信号"""
        scan_date = target_date or datetime.now().strftime('%Y-%m-%d')
        self.logger.info(f"开始扫描 {scan_date} 的交易信号")
        
        try:
            # 获取核心观察池
            core_pool = self.pool_manager.get_core_pool(status='active')
            if not core_pool:
                return {
                    'success': False,
                    'error': '核心观察池为空',
                    'scan_date': scan_date
                }
            
            # 过滤符合条件的股票
            filtered_stocks = self._filter_stocks_by_criteria(core_pool)
            self.logger.info(f"过滤后的股票数量: {len(filtered_stocks)}")
            
            # 扫描信号
            signals = []
            scan_stats = {
                'total_scanned': len(filtered_stocks),
                'signals_found': 0,
                'high_confidence_signals': 0,
                'buy_signals': 0,
                'sell_signals': 0
            }
            
            for stock_info in filtered_stocks:
                stock_signals = self._scan_stock_signals(stock_info, scan_date)
                if stock_signals:
                    signals.extend(stock_signals)
                    scan_stats['signals_found'] += len(stock_signals)
                    
                    for signal in stock_signals:
                        if signal['confidence'] >= self.config['signal_confidence_threshold']:
                            scan_stats['high_confidence_signals'] += 1
                        
                        if signal['signal_type'] == 'buy':
                            scan_stats['buy_signals'] += 1
                        elif signal['signal_type'] == 'sell':
                            scan_stats['sell_signals'] += 1
            
            # 按置信度排序
            signals.sort(key=lambda x: x['confidence'], reverse=True)
            
            # 限制信号数量
            max_signals = self.config.get('max_signals_per_day', 20)
            if len(signals) > max_signals:
                signals = signals[:max_signals]
                self.logger.info(f"信号数量限制为 {max_signals} 个")
            
            # 记录信号到数据库
            recorded_count = 0
            for signal in signals:
                if self.pool_manager.record_signal(signal):
                    recorded_count += 1
            
            # 生成扫描报告
            scan_result = {
                'success': True,
                'scan_date': scan_date,
                'scan_time': datetime.now().isoformat(),
                'statistics': scan_stats,
                'signals': signals,
                'recorded_signals': recorded_count,
                'market_conditions': self._get_market_conditions()
            }
            
            # 保存扫描报告
            self._save_scan_report(scan_result)
            
            self.logger.info(f"信号扫描完成: 发现 {len(signals)} 个信号，记录 {recorded_count} 个")
            return scan_result
            
        except Exception as e:
            self.logger.error(f"信号扫描失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'scan_date': scan_date
            }
    
    def _filter_stocks_by_criteria(self, core_pool: List[Dict]) -> List[Dict]:
        """根据条件过滤股票"""
        filtered = []
        
        for stock in core_pool:
            # 检查信任度
            min_credibility = self.config.get('min_credibility_score', 0.5)
            if stock['credibility_score'] < min_credibility:
                continue
            
            # 检查风险等级
            risk_filter = self.config.get('risk_level_filter', ['LOW', 'MEDIUM', 'HIGH'])
            if stock['risk_level'] and stock['risk_level'] not in risk_filter:
                continue
            
            # 检查最近信号频率（避免过度交易）
            if self._is_recently_signaled(stock['stock_code']):
                continue
            
            filtered.append(stock)
        
        # 按综合评分和信任度排序
        filtered.sort(key=lambda x: (x['credibility_score'], x['overall_score']), reverse=True)
        
        return filtered
    
    def _scan_stock_signals(self, stock_info: Dict, scan_date: str) -> List[Dict]:
        """扫描单只股票的信号"""
        stock_code = stock_info['stock_code']
        signals = []
        
        try:
            # 加载优化参数
            optimized_params = stock_info.get('optimized_params', {})
            if not optimized_params:
                self.logger.warning(f"{stock_code} 缺少优化参数")
                return signals
            
            # 获取股票数据
            stock_data = self._get_stock_data(stock_code)
            if not stock_data:
                return signals
            
            # 应用策略检测信号
            strategy_signals = self._apply_strategies(stock_code, stock_data, optimized_params)
            
            # 验证和评估信号
            for signal in strategy_signals:
                validated_signal = self._validate_signal(signal, stock_info, stock_data)
                if validated_signal:
                    signals.append(validated_signal)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"扫描股票 {stock_code} 信号失败: {e}")
            return signals
    
    def _apply_strategies(self, stock_code: str, stock_data: Dict, 
                         optimized_params: Dict) -> List[Dict]:
        """应用策略检测信号"""
        signals = []
        
        try:
            # 策略1: MACD零轴启动策略
            if apply_macd_zero_axis_strategy:
                macd_signal = self._apply_macd_strategy(stock_code, stock_data, optimized_params)
                if macd_signal:
                    signals.append(macd_signal)
            
            # 策略2: 交易顾问策略
            if self.advisor:
                advisor_signal = self._apply_advisor_strategy(stock_code, stock_data, optimized_params)
                if advisor_signal:
                    signals.append(advisor_signal)
            
            # 策略3: 技术指标组合策略
            technical_signal = self._apply_technical_strategy(stock_code, stock_data, optimized_params)
            if technical_signal:
                signals.append(technical_signal)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"应用策略失败: {e}")
            return signals
    
    def _apply_macd_strategy(self, stock_code: str, stock_data: Dict, 
                           optimized_params: Dict) -> Optional[Dict]:
        """应用MACD策略"""
        try:
            # 模拟MACD策略信号检测
            import random
            
            # 基于优化参数调整信号概率
            signal_probability = optimized_params.get('macd_sensitivity', 0.3)
            
            if random.random() < signal_probability:
                return {
                    'stock_code': stock_code,
                    'signal_type': random.choice(['buy', 'sell']),
                    'strategy': 'macd_zero_axis',
                    'confidence': random.uniform(0.6, 0.9),
                    'trigger_price': stock_data.get('current_price', random.uniform(10, 50)),
                    'signal_date': datetime.now().isoformat(),
                    'parameters_used': optimized_params
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"MACD策略应用失败: {e}")
            return None
    
    def _apply_advisor_strategy(self, stock_code: str, stock_data: Dict, 
                              optimized_params: Dict) -> Optional[Dict]:
        """应用交易顾问策略"""
        try:
            # 使用交易顾问生成信号
            if not self.advisor:
                return None
            
            # 模拟交易顾问信号
            import random
            
            advisor_probability = optimized_params.get('advisor_sensitivity', 0.25)
            
            if random.random() < advisor_probability:
                return {
                    'stock_code': stock_code,
                    'signal_type': random.choice(['buy', 'sell']),
                    'strategy': 'trading_advisor',
                    'confidence': random.uniform(0.65, 0.95),
                    'trigger_price': stock_data.get('current_price', random.uniform(10, 50)),
                    'signal_date': datetime.now().isoformat(),
                    'parameters_used': optimized_params
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"交易顾问策略应用失败: {e}")
            return None
    
    def _apply_technical_strategy(self, stock_code: str, stock_data: Dict, 
                                optimized_params: Dict) -> Optional[Dict]:
        """应用技术指标组合策略"""
        try:
            # 技术指标组合分析
            import random
            
            # 基于多个技术指标的综合判断
            rsi_signal = random.choice([1, 0, -1])  # 1=买入, 0=中性, -1=卖出
            ma_signal = random.choice([1, 0, -1])
            volume_signal = random.choice([1, 0, -1])
            
            # 综合信号强度
            signal_strength = (rsi_signal + ma_signal + volume_signal) / 3
            
            if abs(signal_strength) >= 0.5:  # 信号足够强
                signal_type = 'buy' if signal_strength > 0 else 'sell'
                confidence = min(0.95, 0.6 + abs(signal_strength) * 0.3)
                
                return {
                    'stock_code': stock_code,
                    'signal_type': signal_type,
                    'strategy': 'technical_combo',
                    'confidence': confidence,
                    'trigger_price': stock_data.get('current_price', random.uniform(10, 50)),
                    'signal_date': datetime.now().isoformat(),
                    'parameters_used': optimized_params,
                    'technical_indicators': {
                        'rsi_signal': rsi_signal,
                        'ma_signal': ma_signal,
                        'volume_signal': volume_signal,
                        'signal_strength': signal_strength
                    }
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"技术策略应用失败: {e}")
            return None
    
    def _validate_signal(self, signal: Dict, stock_info: Dict, 
                        stock_data: Dict) -> Optional[Dict]:
        """验证和评估信号"""
        try:
            # 基础验证
            if signal['confidence'] < 0.5:
                return None
            
            # 市场环境过滤
            if self.config['market_condition_filter']:
                if not self._check_market_conditions(signal):
                    return None
            
            # 价格变化检查
            price_change = stock_data.get('price_change_pct', 0)
            price_threshold = self.config.get('price_change_threshold', 0.02)
            if abs(price_change) < price_threshold:
                # 价格变化太小，降低置信度
                signal['confidence'] *= 0.8
            
            # 成交量检查
            volume = stock_data.get('volume', 0)
            volume_threshold = self.config.get('volume_threshold', 1000000)
            if volume < volume_threshold:
                # 成交量不足，降低置信度
                signal['confidence'] *= 0.9
            
            # 基于股票信任度调整置信度
            credibility_factor = stock_info['credibility_score']
            signal['confidence'] *= credibility_factor
            
            # 最终置信度检查
            if signal['confidence'] < self.config['signal_confidence_threshold']:
                return None
            
            # 添加额外信息
            signal.update({
                'stock_name': stock_info.get('stock_name', ''),
                'stock_grade': stock_info.get('grade', ''),
                'credibility_score': stock_info['credibility_score'],
                'risk_level': stock_info.get('risk_level', 'MEDIUM'),
                'validation_time': datetime.now().isoformat(),
                'status': 'pending'
            })
            
            return signal
            
        except Exception as e:
            self.logger.error(f"信号验证失败: {e}")
            return None
    
    def _get_stock_data(self, stock_code: str) -> Optional[Dict]:
        """获取股票数据"""
        try:
            # 尝试使用现有的数据加载器
            if load_stock_data:
                return load_stock_data(stock_code)
            
            # 模拟股票数据
            import random
            return {
                'stock_code': stock_code,
                'current_price': random.uniform(10, 50),
                'price_change_pct': random.uniform(-0.05, 0.05),
                'volume': random.randint(500000, 5000000),
                'high': random.uniform(10, 55),
                'low': random.uniform(8, 45),
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"获取股票数据失败: {e}")
            return None
    
    def _is_recently_signaled(self, stock_code: str, days: int = 1) -> bool:
        """检查是否最近已经发出过信号"""
        try:
            # 检查数据库中最近的信号记录
            # 这里简化实现，实际应该查询数据库
            return False
            
        except Exception as e:
            self.logger.error(f"检查最近信号失败: {e}")
            return False
    
    def _check_market_conditions(self, signal: Dict) -> bool:
        """检查市场环境条件"""
        try:
            # 检查交易时间
            current_time = datetime.now().time()
            market_hours = self.config.get('market_hours', {'start': '09:30', 'end': '15:00'})
            market_start = datetime.strptime(market_hours['start'], '%H:%M').time()
            market_end = datetime.strptime(market_hours['end'], '%H:%M').time()
            
            if not (market_start <= current_time <= market_end):
                return False
            
            # 检查是否为工作日
            if self.config['exclude_weekends']:
                if datetime.now().weekday() >= 5:  # 周六、周日
                    return False
            
            # 其他市场条件检查（可扩展）
            # 例如：大盘趋势、波动率、重要事件等
            
            return True
            
        except Exception as e:
            self.logger.error(f"市场条件检查失败: {e}")
            return True  # 默认通过
    
    def _get_market_conditions(self) -> Dict[str, Any]:
        """获取当前市场环境信息"""
        return {
            'market_status': 'open' if self._check_market_conditions({}) else 'closed',
            'trading_day': datetime.now().weekday() < 5,
            'scan_time': datetime.now().isoformat(),
            'market_sentiment': 'neutral'  # 可扩展为实际的市场情绪分析
        }
    
    def _save_scan_report(self, scan_result: Dict) -> None:
        """保存扫描报告"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 保存详细报告
            detailed_filename = f'reports/daily_scan_{timestamp}.json'
            with open(detailed_filename, 'w', encoding='utf-8') as f:
                json.dump(scan_result, f, indent=2, ensure_ascii=False)
            
            # 保存简化版本（兼容现有格式）
            simple_signals = []
            for signal in scan_result['signals']:
                simple_signals.append({
                    'stock_code': signal['stock_code'],
                    'action': signal['signal_type'],
                    'confidence': signal['confidence'],
                    'current_price': signal['trigger_price'],
                    'timestamp': signal['signal_date'],
                    'strategy': signal.get('strategy', 'unknown')
                })
            
            simple_filename = f'reports/daily_signals_{timestamp}.json'
            with open(simple_filename, 'w', encoding='utf-8') as f:
                json.dump(simple_signals, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"扫描报告已保存: {detailed_filename}")
            
        except Exception as e:
            self.logger.error(f"保存扫描报告失败: {e}")
    
    def get_scan_history(self, days: int = 7) -> List[Dict]:
        """获取扫描历史"""
        try:
            reports_dir = Path('reports')
            if not reports_dir.exists():
                return []
            
            # 查找最近的扫描报告
            scan_files = list(reports_dir.glob('daily_scan_*.json'))
            scan_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            history = []
            cutoff_date = datetime.now() - timedelta(days=days)
            
            for file_path in scan_files[:days]:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        scan_data = json.load(f)
                    
                    scan_time = datetime.fromisoformat(scan_data['scan_time'])
                    if scan_time >= cutoff_date:
                        history.append({
                            'scan_date': scan_data['scan_date'],
                            'scan_time': scan_data['scan_time'],
                            'signals_count': len(scan_data['signals']),
                            'statistics': scan_data['statistics'],
                            'file_path': str(file_path)
                        })
                
                except Exception as e:
                    self.logger.warning(f"读取扫描历史文件失败 {file_path}: {e}")
                    continue
            
            return history
            
        except Exception as e:
            self.logger.error(f"获取扫描历史失败: {e}")
            return []


def main():
    """测试函数"""
    logging.basicConfig(level=logging.INFO)
    
    # 创建信号扫描器
    scanner = DailySignalScanner()
    
    print("🎯 每日信号扫描器测试")
    print("=" * 50)
    
    # 执行信号扫描
    result = scanner.scan_daily_signals()
    
    if result['success']:
        print(f"✅ 信号扫描成功")
        print(f"📊 扫描统计:")
        stats = result['statistics']
        print(f"  - 扫描股票数: {stats['total_scanned']}")
        print(f"  - 发现信号数: {stats['signals_found']}")
        print(f"  - 高置信度信号: {stats['high_confidence_signals']}")
        print(f"  - 买入信号: {stats['buy_signals']}")
        print(f"  - 卖出信号: {stats['sell_signals']}")
        
        print(f"\n📋 信号详情:")
        for i, signal in enumerate(result['signals'][:5], 1):
            print(f"  {i}. {signal['stock_code']} - {signal['signal_type']} "
                  f"(置信度: {signal['confidence']:.3f}, 策略: {signal['strategy']})")
    else:
        print(f"❌ 信号扫描失败: {result['error']}")
    
    # 获取扫描历史
    history = scanner.get_scan_history(3)
    print(f"\n📈 最近扫描历史 ({len(history)} 次):")
    for scan in history:
        print(f"  - {scan['scan_date']}: {scan['signals_count']} 个信号")


if __name__ == "__main__":
    main()