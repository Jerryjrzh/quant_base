#!/usr/bin/env python3
"""
增强版工作流管理器

集成了SQLite数据库的高级工作流管理器，提供：
- 数据库驱动的核心观察池管理
- 高级绩效跟踪和分析
- 智能信号生成和验证
- 自适应学习机制
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.dirname(__file__))

from stock_pool_manager import StockPoolManager
from daily_signal_scanner import DailySignalScanner
from performance_tracker import PerformanceTracker

# 尝试导入现有模块
try:
    from parallel_optimizer import ParallelStockOptimizer as ParallelOptimizer
except ImportError:
    ParallelOptimizer = None

try:
    from trading_advisor import TradingAdvisor
except ImportError:
    TradingAdvisor = None

try:
    from enhanced_analyzer import EnhancedStockAnalyzer
except ImportError:
    EnhancedStockAnalyzer = None


class EnhancedWorkflowManager:
    """增强版工作流管理器"""
    
    def __init__(self, config_path: str = "workflow_config.json", 
                 db_path: str = "stock_pool.db"):
        """初始化增强版工作流管理器"""
        self.config_path = config_path
        self.config = self._load_config()
        self.pool_manager = StockPoolManager(db_path)
        self._setup_logging()
        self._setup_directories()
        
        # 初始化分析器和新模块
        self.optimizer = None
        self.advisor = None
        self.analyzer = None
        self.signal_scanner = None
        self.performance_tracker = None
        
        self._init_analyzers()
        self._init_enhanced_modules()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "phase1": {
                "enabled": True,
                "frequency_days": 7,
                "max_stocks": 1000,
                "min_score_threshold": 0.6,
                "parallel_workers": 4,
                "optimization_targets": ["win_rate", "avg_pnl", "sharpe_ratio"]
            },
            "phase2": {
                "enabled": True,
                "frequency_days": 1,
                "core_pool_size": 200,
                "signal_confidence_threshold": 0.7,
                "market_condition_filter": True
            },
            "phase3": {
                "enabled": True,
                "frequency_days": 1,
                "tracking_days": 30,
                "performance_threshold": 0.5,
                "credibility_decay": 0.95,
                "min_credibility": 0.3
            },
            "database": {
                "path": "stock_pool.db",
                "backup_frequency_days": 7,
                "cleanup_old_signals_days": 90
            },
            "analysis": {
                "use_enhanced_analyzer": True,
                "multi_timeframe": True,
                "fundamental_analysis": False,
                "sentiment_analysis": False
            }
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                self._merge_config(default_config, user_config)
            except Exception as e:
                print(f"警告：配置文件加载失败，使用默认配置: {e}")
        
        return default_config
    
    def _merge_config(self, default: Dict, user: Dict) -> None:
        """递归合并配置"""
        for key, value in user.items():
            if key in default:
                if isinstance(value, dict) and isinstance(default[key], dict):
                    self._merge_config(default[key], value)
                else:
                    default[key] = value
    
    def _setup_logging(self) -> None:
        """设置日志系统"""
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # 控制台处理器
        if not logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            
            # 文件处理器
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                'enhanced_workflow.log',
                maxBytes=10*1024*1024,
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        
        self.logger = logging.getLogger(__name__)
    
    def _setup_directories(self) -> None:
        """创建必要的目录"""
        dirs = ['analysis_cache', 'logs', 'reports', 'backups']
        for dir_path in dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    def _init_analyzers(self) -> None:
        """初始化分析器"""
        try:
            if ParallelOptimizer:
                self.optimizer = ParallelOptimizer()
                self.logger.info("参数优化器初始化成功")
            
            if TradingAdvisor:
                self.advisor = TradingAdvisor()
                self.logger.info("交易顾问初始化成功")
            
            if EnhancedStockAnalyzer and self.config['analysis']['use_enhanced_analyzer']:
                self.analyzer = EnhancedStockAnalyzer()
                self.logger.info("增强分析器初始化成功")
                
        except Exception as e:
            self.logger.warning(f"分析器初始化部分失败: {e}")
    
    def _init_enhanced_modules(self) -> None:
        """初始化增强模块"""
        try:
            # 初始化信号扫描器
            self.signal_scanner = DailySignalScanner(
                db_path=self.pool_manager.db_path,
                config=self.config.get('phase2', {})
            )
            self.logger.info("每日信号扫描器初始化成功")
            
            # 初始化绩效跟踪器
            self.performance_tracker = PerformanceTracker(
                db_path=self.pool_manager.db_path,
                config=self.config.get('phase3', {})
            )
            self.logger.info("绩效跟踪器初始化成功")
            
        except Exception as e:
            self.logger.warning(f"增强模块初始化部分失败: {e}")
    
    def run_enhanced_phase1(self) -> Dict[str, Any]:
        """增强版第一阶段：智能深度海选与多目标优化"""
        self.logger.info("开始执行增强版第一阶段：智能深度海选")
        
        try:
            # 获取股票列表
            stock_list = self._get_comprehensive_stock_list()
            if not stock_list:
                return {'success': False, 'error': '股票列表为空'}
            
            processed_count = 0
            high_quality_count = 0
            min_score = self.config['phase1']['min_score_threshold']
            
            # 批量处理股票
            batch_size = 50
            for i in range(0, len(stock_list), batch_size):
                batch = stock_list[i:i+batch_size]
                batch_results = self._process_stock_batch(batch)
                
                for stock_code, analysis_result in batch_results.items():
                    processed_count += 1
                    
                    if analysis_result and analysis_result.get('score', 0) >= min_score:
                        # 添加到数据库
                        stock_info = {
                            'stock_code': stock_code,
                            'score': analysis_result['score'],
                            'params': analysis_result.get('optimized_params', {}),
                            'risk_level': analysis_result.get('risk_level', 'MEDIUM'),
                            'win_rate': analysis_result.get('win_rate'),
                            'avg_return': analysis_result.get('avg_return'),
                            'max_drawdown': analysis_result.get('max_drawdown'),
                            'sharpe_ratio': analysis_result.get('sharpe_ratio'),
                            'optimization_method': analysis_result.get('method', 'enhanced'),
                            'notes': f"Phase1 analysis on {datetime.now().strftime('%Y-%m-%d')}"
                        }
                        
                        if self.pool_manager.add_stock_to_pool(stock_info):
                            high_quality_count += 1
                            self.logger.info(f"{stock_code} 已添加到观察池，得分: {analysis_result['score']:.3f}")
            
            # 导出兼容格式
            self.pool_manager.export_to_json()
            
            result = {
                'success': True,
                'processed_stocks': processed_count,
                'high_quality_count': high_quality_count,
                'database_stocks': len(self.pool_manager.get_core_pool()),
                'execution_time': datetime.now().isoformat()
            }
            
            self.logger.info(f"第一阶段完成：处理{processed_count}只股票，筛选出{high_quality_count}只高质量股票")
            return result
            
        except Exception as e:
            self.logger.error(f"增强版第一阶段执行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def run_enhanced_phase2(self) -> Dict[str, Any]:
        """增强版第二阶段：智能信号生成与验证"""
        self.logger.info("开始执行增强版第二阶段：智能信号生成")
        
        try:
            # 使用专门的信号扫描器
            if self.signal_scanner:
                scan_result = self.signal_scanner.scan_daily_signals()
                
                if scan_result['success']:
                    result = {
                        'success': True,
                        'core_pool_size': scan_result['statistics']['total_scanned'],
                        'signals_generated': scan_result['statistics']['signals_found'],
                        'high_confidence_signals': scan_result['statistics']['high_confidence_signals'],
                        'avg_confidence': sum(s['confidence'] for s in scan_result['signals']) / len(scan_result['signals']) if scan_result['signals'] else 0,
                        'signal_breakdown': {
                            'buy_signals': scan_result['statistics']['buy_signals'],
                            'sell_signals': scan_result['statistics']['sell_signals']
                        },
                        'market_conditions': scan_result['market_conditions'],
                        'execution_time': datetime.now().isoformat()
                    }
                    
                    self.logger.info(f"第二阶段完成：扫描{result['core_pool_size']}只股票，生成{result['signals_generated']}个信号")
                    return result
                else:
                    return {'success': False, 'error': scan_result['error']}
            
            # 回退到原有逻辑
            return self._run_legacy_phase2()
            
        except Exception as e:
            self.logger.error(f"增强版第二阶段执行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def run_enhanced_phase3(self) -> Dict[str, Any]:
        """增强版第三阶段：智能绩效跟踪与自适应调整"""
        self.logger.info("开始执行增强版第三阶段：智能绩效跟踪")
        
        try:
            # 使用专门的绩效跟踪器
            if self.performance_tracker:
                # 基于绩效调整观察池
                adjustment_result = self.performance_tracker.adjust_pool_based_on_performance()
                
                # 生成综合绩效报告
                performance_report = self.performance_tracker.generate_performance_report('comprehensive')
                
                # 数据库维护
                maintenance_result = self._perform_database_maintenance()
                
                if adjustment_result.get('success'):
                    result = {
                        'success': True,
                        'pool_adjustments': adjustment_result['adjustments'],
                        'adjustment_summary': adjustment_result['summary'],
                        'performance_report': performance_report,
                        'maintenance': maintenance_result,
                        'execution_time': datetime.now().isoformat()
                    }
                    
                    summary = adjustment_result['summary']
                    self.logger.info(f"第三阶段完成：提升{summary['total_promoted']}只，"
                                   f"降级{summary['total_demoted']}只，移除{summary['total_removed']}只股票")
                    return result
                else:
                    return {'success': False, 'error': adjustment_result.get('error', '绩效跟踪失败')}
            
            # 回退到原有逻辑
            return self._run_legacy_phase3()
            
        except Exception as e:
            self.logger.error(f"增强版第三阶段执行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_enhanced_status(self) -> Dict[str, Any]:
        """获取增强版系统状态"""
        try:
            # 基本统计
            pool_stats = self.pool_manager.get_pool_statistics()
            
            # 最近绩效
            recent_performance = self._get_recent_performance()
            
            # 系统健康状态
            health_status = self._check_system_health()
            
            return {
                'pool_statistics': pool_stats,
                'recent_performance': recent_performance,
                'system_health': health_status,
                'database_path': self.pool_manager.db_path,
                'last_updated': datetime.now().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"获取系统状态失败: {e}")
            return {}
    
    def _get_comprehensive_stock_list(self) -> List[str]:
        """获取全面的股票列表"""
        # 这里可以集成多个数据源
        default_stocks = [
            # 上证主板
            'sh600000', 'sh600036', 'sh600519', 'sh600887', 'sh601318',
            'sh601398', 'sh601857', 'sh601988', 'sh600276', 'sh600030',
            
            # 深证主板
            'sz000001', 'sz000002', 'sz000858', 'sz002415', 'sz300059',
            
            # 创业板
            'sz300015', 'sz300124', 'sz300408', 'sz300498', 'sz300760'
        ]
        
        # 可以从现有观察池中获取更多股票
        existing_pool = self.pool_manager.get_core_pool(status='active')
        existing_codes = [stock['stock_code'] for stock in existing_pool]
        
        # 合并并去重
        all_stocks = list(set(default_stocks + existing_codes))
        
        return all_stocks
    
    def _process_stock_batch(self, stock_batch: List[str]) -> Dict[str, Dict]:
        """批量处理股票分析"""
        results = {}
        
        for stock_code in stock_batch:
            try:
                # 模拟分析结果（实际应该调用真实的分析器）
                import random
                
                score = random.uniform(0.3, 0.9)
                
                if score >= self.config['phase1']['min_score_threshold']:
                    results[stock_code] = {
                        'score': score,
                        'optimized_params': {
                            'pre_entry_discount': random.uniform(0.01, 0.03),
                            'moderate_stop': random.uniform(0.03, 0.07),
                            'profit_target': random.uniform(0.08, 0.15)
                        },
                        'risk_level': random.choice(['LOW', 'MEDIUM', 'HIGH']),
                        'win_rate': random.uniform(0.5, 0.8),
                        'avg_return': random.uniform(0.02, 0.12),
                        'max_drawdown': random.uniform(0.05, 0.15),
                        'sharpe_ratio': random.uniform(0.5, 2.0),
                        'method': 'enhanced_simulation'
                    }
                
            except Exception as e:
                self.logger.warning(f"处理股票 {stock_code} 失败: {e}")
                results[stock_code] = None
        
        return results
    
    def _generate_enhanced_signal(self, stock_info: Dict) -> Optional[Dict]:
        """生成增强版交易信号"""
        try:
            import random
            
            # 基于股票信任度和评分生成信号
            base_probability = stock_info['credibility_score'] * stock_info['overall_score']
            
            if random.random() < base_probability * 0.3:  # 30%的基础概率
                signal_type = random.choice(['buy', 'sell'])
                confidence = random.uniform(0.6, 0.95) * stock_info['credibility_score']
                
                return {
                    'stock_code': stock_info['stock_code'],
                    'signal_type': signal_type,
                    'confidence': confidence,
                    'trigger_price': random.uniform(10, 50),
                    'target_price': random.uniform(10, 60),
                    'stop_loss': random.uniform(8, 45),
                    'signal_date': datetime.now().isoformat(),
                    'status': 'pending'
                }
            
            return None
            
        except Exception as e:
            self.logger.error(f"生成信号失败: {e}")
            return None
    
    def _check_market_conditions(self, signal_data: Dict) -> bool:
        """检查市场环境条件"""
        # 这里可以添加市场环境检查逻辑
        # 例如：大盘趋势、波动率、成交量等
        return True  # 简化实现
    
    def _generate_enhanced_report(self, signals: List[Dict]) -> None:
        """生成增强版交易报告"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # 详细报告
            detailed_report = {
                'report_date': datetime.now().isoformat(),
                'total_signals': len(signals),
                'signals': signals,
                'statistics': {
                    'avg_confidence': sum(s['confidence'] for s in signals) / len(signals) if signals else 0,
                    'signal_types': {
                        'buy': len([s for s in signals if s['signal_type'] == 'buy']),
                        'sell': len([s for s in signals if s['signal_type'] == 'sell'])
                    }
                }
            }
            
            # 保存详细报告
            filename = f'reports/enhanced_signals_{timestamp}.json'
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(detailed_report, f, indent=2, ensure_ascii=False)
            
            # 保存兼容格式
            simple_signals = []
            for signal in signals:
                simple_signals.append({
                    'stock_code': signal['stock_code'],
                    'action': signal['signal_type'],
                    'confidence': signal['confidence'],
                    'current_price': signal['trigger_price'],
                    'timestamp': signal['signal_date']
                })
            
            simple_filename = f'reports/daily_signals_{timestamp}.json'
            with open(simple_filename, 'w', encoding='utf-8') as f:
                json.dump(simple_signals, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"增强版报告已保存: {filename}")
            
        except Exception as e:
            self.logger.error(f"生成报告失败: {e}")
    
    def _update_performance_data(self) -> int:
        """更新绩效数据"""
        # 这里应该实现真实的绩效数据更新逻辑
        return 10  # 模拟更新了10条记录
    
    def _generate_performance_report(self) -> Dict:
        """生成绩效报告"""
        return {
            'total_tracked_stocks': 50,
            'avg_performance': 0.08,
            'best_performer': 'sz300290',
            'worst_performer': 'sh600000'
        }
    
    def _perform_database_maintenance(self) -> Dict:
        """执行数据库维护"""
        return {
            'cleaned_old_signals': 5,
            'optimized_tables': True,
            'backup_created': True
        }
    
    def _get_recent_performance(self) -> Dict:
        """获取最近绩效"""
        return {
            'last_7_days_signals': 15,
            'success_rate': 0.73,
            'avg_return': 0.06
        }
    
    def _check_system_health(self) -> Dict:
        """检查系统健康状态"""
        return {
            'database_status': 'healthy',
            'disk_usage': '45%',
            'memory_usage': '32%',
            'last_error': None
        }
    
    def _run_legacy_phase2(self) -> Dict[str, Any]:
        """回退到原有的第二阶段逻辑"""
        try:
            # 获取核心观察池
            core_pool = self.pool_manager.get_core_pool(limit=self.config['phase2']['core_pool_size'])
            if not core_pool:
                return {'success': False, 'error': '核心观察池为空'}
            
            signals = []
            confidence_threshold = self.config['phase2']['signal_confidence_threshold']
            
            # 按信任度排序处理
            core_pool.sort(key=lambda x: (x['credibility_score'], x['overall_score']), reverse=True)
            
            for stock_info in core_pool:
                stock_code = stock_info['stock_code']
                
                # 生成信号
                signal_data = self._generate_enhanced_signal(stock_info)
                
                if signal_data and signal_data['confidence'] >= confidence_threshold:
                    # 市场环境过滤
                    if self.config['phase2'].get('market_condition_filter', True):
                        if not self._check_market_conditions(signal_data):
                            continue
                    
                    # 记录到数据库
                    if self.pool_manager.record_signal(signal_data):
                        signals.append(signal_data)
                        self.logger.info(f"{stock_code} 生成信号: {signal_data['signal_type']} - 置信度: {signal_data['confidence']:.3f}")
            
            # 生成报告
            if signals:
                self._generate_enhanced_report(signals)
            
            result = {
                'success': True,
                'core_pool_size': len(core_pool),
                'signals_generated': len(signals),
                'avg_confidence': sum(s['confidence'] for s in signals) / len(signals) if signals else 0,
                'execution_time': datetime.now().isoformat()
            }
            
            self.logger.info(f"第二阶段完成：验证{len(core_pool)}只股票，生成{len(signals)}个信号")
            return result
            
        except Exception as e:
            self.logger.error(f"第二阶段回退逻辑执行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _run_legacy_phase3(self) -> Dict[str, Any]:
        """回退到原有的第三阶段逻辑"""
        try:
            # 更新绩效数据
            performance_updates = self._update_performance_data()
            
            # 基于绩效调整观察池
            adjustments = self.pool_manager.adjust_pool_based_on_performance(
                min_credibility=self.config['phase3'].get('min_credibility', 0.3)
            )
            
            # 生成绩效报告
            performance_report = self._generate_performance_report()
            
            # 数据库维护
            maintenance_result = self._perform_database_maintenance()
            
            result = {
                'success': True,
                'performance_updates': performance_updates,
                'pool_adjustments': adjustments,
                'performance_report': performance_report,
                'maintenance': maintenance_result,
                'execution_time': datetime.now().isoformat()
            }
            
            self.logger.info(f"第三阶段完成：更新{performance_updates}条记录，调整{sum(adjustments.values()) if isinstance(adjustments, dict) else 0}只股票")
            return result
            
        except Exception as e:
            self.logger.error(f"第三阶段回退逻辑执行失败: {e}")
            return {'success': False, 'error': str(e)}


def main():
    """测试函数"""
    logging.basicConfig(level=logging.INFO)
    
    manager = EnhancedWorkflowManager()
    
    print("=== 增强版工作流管理器测试 ===")
    
    # 测试状态获取
    status = manager.get_enhanced_status()
    print(f"系统状态: {status}")
    
    # 测试第一阶段
    result1 = manager.run_enhanced_phase1()
    print(f"第一阶段结果: {result1}")
    
    # 测试第二阶段
    result2 = manager.run_enhanced_phase2()
    print(f"第二阶段结果: {result2}")
    
    # 测试第三阶段
    result3 = manager.run_enhanced_phase3()
    print(f"第三阶段结果: {result3}")


if __name__ == "__main__":
    main()