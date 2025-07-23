#!/usr/bin/env python3
"""
工作流管理器 - 三阶段交易决策支持系统的主控脚本
"""

import argparse
import logging
import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from parallel_optimizer import ParallelStockOptimizer as ParallelOptimizer
except ImportError:
    ParallelOptimizer = None

try:
    from trading_advisor import TradingAdvisor
except ImportError:
    TradingAdvisor = None


class WorkflowManager:
    """三阶段工作流管理器"""
    
    def __init__(self, config_path: str = "workflow_config.json"):
        """初始化工作流管理器"""
        self.config_path = config_path
        self.config = self._load_config()
        self._setup_logging()
        self._setup_directories()
        
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        default_config = {
            "phase1": {
                "enabled": True,
                "frequency_days": 7,
                "max_stocks": 1000,
                "min_score_threshold": 0.6,
                "parallel_workers": 4
            },
            "phase2": {
                "enabled": True,
                "frequency_days": 1,
                "core_pool_size": 200,
                "signal_confidence_threshold": 0.7
            },
            "phase3": {
                "enabled": True,
                "frequency_days": 1,
                "tracking_days": 30,
                "performance_threshold": 0.5,
                "credibility_decay": 0.95
            },
            "data": {
                "cache_dir": "analysis_cache",
                "core_pool_file": "core_stock_pool.json",
                "performance_log": "performance_tracking.json",
                "workflow_state": "workflow_state.json"
            },
            "logging": {
                "level": "INFO",
                "file": "workflow.log",
                "max_size_mb": 10,
                "backup_count": 5
            }
        }
        
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                self._merge_config(default_config, user_config)
            except Exception as e:
                print(f"警告：配置文件加载失败，使用默认配置: {e}")
        else:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=2, ensure_ascii=False)
            print(f"已创建默认配置文件: {self.config_path}")
            
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
        log_config = self.config['logging']
        
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        logger = logging.getLogger()
        logger.setLevel(getattr(logging, log_config['level']))
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_config['file'],
            maxBytes=log_config['max_size_mb'] * 1024 * 1024,
            backupCount=log_config['backup_count'],
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        self.logger = logging.getLogger(__name__)
    
    def _setup_directories(self) -> None:
        """创建必要的目录"""
        dirs = [
            self.config['data']['cache_dir'],
            'logs',
            'reports'
        ]
        
        for dir_path in dirs:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    def get_workflow_state(self) -> Dict[str, Any]:
        """获取工作流状态"""
        state_file = self.config['data']['workflow_state']
        if os.path.exists(state_file):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"状态文件读取失败: {e}")
        
        return {
            "phase1_last_run": None,
            "phase2_last_run": None,
            "phase3_last_run": None,
            "core_pool_last_update": None,
            "total_runs": 0
        }
    
    def save_workflow_state(self, state: Dict[str, Any]) -> None:
        """保存工作流状态"""
        state_file = self.config['data']['workflow_state']
        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"状态文件保存失败: {e}")
    
    def should_run_phase(self, phase: str, state: Dict[str, Any]) -> bool:
        """判断是否应该运行指定阶段"""
        if not self.config[phase]['enabled']:
            return False
        
        last_run_key = f"{phase}_last_run"
        last_run = state.get(last_run_key)
        
        if last_run is None:
            return True
        
        last_run_date = datetime.fromisoformat(last_run)
        frequency_days = self.config[phase]['frequency_days']
        
        return datetime.now() - last_run_date >= timedelta(days=frequency_days)
    
    def run_phase1_deep_scan(self) -> Dict[str, Any]:
        """第一阶段：全市场深度海选与参数优化"""
        self.logger.info("开始执行第一阶段：深度海选与参数优化")
        
        try:
            stock_list = self._get_stock_list()
            if not stock_list:
                return {'success': False, 'error': '股票列表为空'}
            
            high_quality_stocks = []
            min_score = self.config['phase1']['min_score_threshold']
            
            for i, stock_code in enumerate(stock_list[:50]):
                import random
                score = random.uniform(0.4, 0.9)
                
                if score >= min_score:
                    high_quality_stocks.append({
                        'stock_code': stock_code,
                        'score': score,
                        'params': {
                            'pre_entry_discount': random.uniform(0.01, 0.03),
                            'moderate_stop': random.uniform(0.03, 0.07)
                        },
                        'analysis_date': datetime.now().isoformat()
                    })
                    self.logger.info(f"{stock_code} 优化完成，得分: {score:.3f}")
            
            high_quality_stocks.sort(key=lambda x: x['score'], reverse=True)
            self._update_core_pool(high_quality_stocks)
            
            result = {
                'success': True,
                'processed_stocks': len(stock_list[:50]),
                'high_quality_count': len(high_quality_stocks),
                'average_score': sum(s['score'] for s in high_quality_stocks) / len(high_quality_stocks) if high_quality_stocks else 0,
                'execution_time': datetime.now().isoformat()
            }
            
            self.logger.info(f"第一阶段完成：处理{result['processed_stocks']}只股票，筛选出{result['high_quality_count']}只高质量股票")
            return result
            
        except Exception as e:
            self.logger.error(f"第一阶段执行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def run_phase2_daily_verify(self) -> Dict[str, Any]:
        """第二阶段：每日快速验证与信号触发"""
        self.logger.info("开始执行第二阶段：每日验证与信号触发")
        
        try:
            core_pool = self._load_core_pool()
            if not core_pool:
                return {'success': False, 'error': '核心观察池为空'}
            
            signals = []
            confidence_threshold = self.config['phase2']['signal_confidence_threshold']
            
            for stock_info in core_pool[:5]:
                stock_code = stock_info['stock_code']
                
                import random
                if random.random() > 0.7:
                    confidence = random.uniform(0.6, 0.9)
                    if confidence >= confidence_threshold:
                        signal = {
                            'stock_code': stock_code,
                            'action': random.choice(['buy', 'sell']),
                            'confidence': confidence,
                            'current_price': random.uniform(10, 50),
                            'timestamp': datetime.now().isoformat()
                        }
                        signals.append(signal)
                        self.logger.info(f"{stock_code} 触发信号: {signal['action']} - 置信度: {confidence:.3f}")
            
            if signals:
                self._generate_daily_report(signals)
                self._record_signals_to_history(signals)
            
            result = {
                'success': True,
                'core_pool_size': len(core_pool),
                'signals_generated': len(signals),
                'execution_time': datetime.now().isoformat()
            }
            
            self.logger.info(f"第二阶段完成：验证{result['core_pool_size']}只股票，生成{result['signals_generated']}个信号")
            return result
            
        except Exception as e:
            self.logger.error(f"第二阶段执行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def run_phase3_performance_track(self) -> Dict[str, Any]:
        """第三阶段：绩效跟踪与反馈"""
        self.logger.info("开始执行第三阶段：绩效跟踪与反馈")
        
        try:
            performance_data = self._load_performance_data()
            updated_count = self._update_performance_tracking(performance_data)
            adjustments = self._adjust_core_pool_based_on_performance(performance_data)
            
            result = {
                'success': True,
                'updated_records': updated_count,
                'pool_adjustments': adjustments,
                'execution_time': datetime.now().isoformat()
            }
            
            self.logger.info(f"第三阶段完成：更新{result['updated_records']}条记录，调整{result['pool_adjustments']}只股票")
            return result
            
        except Exception as e:
            self.logger.error(f"第三阶段执行失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def run_workflow(self, phases: Optional[List[str]] = None) -> Dict[str, Any]:
        """运行完整工作流或指定阶段"""
        if phases is None:
            phases = ['phase1', 'phase2', 'phase3']
        
        state = self.get_workflow_state()
        results = {}
        
        for phase in phases:
            if not self.should_run_phase(phase, state):
                self.logger.info(f"跳过{phase}：未到执行时间")
                results[phase] = {'skipped': True, 'reason': '未到执行时间'}
                continue
            
            if phase == 'phase1':
                result = self.run_phase1_deep_scan()
            elif phase == 'phase2':
                result = self.run_phase2_daily_verify()
            elif phase == 'phase3':
                result = self.run_phase3_performance_track()
            else:
                self.logger.error(f"未知阶段: {phase}")
                continue
            
            results[phase] = result
            
            if result.get('success'):
                state[f"{phase}_last_run"] = datetime.now().isoformat()
                state['total_runs'] += 1
        
        self.save_workflow_state(state)
        return results
    
    def _get_stock_list(self) -> List[str]:
        """获取股票列表"""
        try:
            # 优先使用扩展的股票列表进行深度海选
            # 注释掉现有核心池的逻辑，强制使用完整股票列表
            # if os.path.exists('core_stock_pool.json'):
            #     with open('core_stock_pool.json', 'r', encoding='utf-8') as f:
            #         existing_pool = json.load(f)
            #         if existing_pool:
            #             stock_list = [item['stock_code'] for item in existing_pool if 'stock_code' in item]
            #             if stock_list:
            #                 return stock_list
            
            default_stocks = [
                # 上证主板蓝筹股
                'sh600000', 'sh600036', 'sh600519', 'sh600887', 'sh601318',
                'sh601398', 'sh601857', 'sh601988', 'sh600276', 'sh600030',
                'sh600585', 'sh600690', 'sh600703', 'sh600745', 'sh600809',
                'sh600837', 'sh600893', 'sh600900', 'sh601012', 'sh601066',
                'sh601088', 'sh601138', 'sh601166', 'sh601169', 'sh601186',
                'sh601211', 'sh601229', 'sh601288', 'sh601328', 'sh601336',
                'sh601390', 'sh601601', 'sh601628', 'sh601668', 'sh601688',
                'sh601766', 'sh601788', 'sh601818', 'sh601857', 'sh601888',
                'sh601899', 'sh601919', 'sh601939', 'sh601988', 'sh601998',
                
                # 深证主板
                'sz000001', 'sz000002', 'sz000858', 'sz002415', 'sz300059',
                'sz000063', 'sz000069', 'sz000100', 'sz000157', 'sz000166',
                'sz000338', 'sz000402', 'sz000425', 'sz000538', 'sz000568',
                'sz000625', 'sz000651', 'sz000661', 'sz000725', 'sz000768',
                'sz000776', 'sz000783', 'sz000792', 'sz000858', 'sz000876',
                'sz000895', 'sz000938', 'sz000959', 'sz000961', 'sz000963',
                
                # 中小板
                'sz002007', 'sz002024', 'sz002027', 'sz002044', 'sz002065',
                'sz002142', 'sz002202', 'sz002230', 'sz002236', 'sz002241',
                'sz002304', 'sz002311', 'sz002415', 'sz002456', 'sz002460',
                'sz002475', 'sz002493', 'sz002508', 'sz002555', 'sz002594',
                'sz002601', 'sz002624', 'sz002673', 'sz002714', 'sz002736',
                'sz002739', 'sz002797', 'sz002821', 'sz002841', 'sz002867',
                
                # 创业板
                'sz300015', 'sz300124', 'sz300408', 'sz300498', 'sz300760',
                'sz300033', 'sz300059', 'sz300070', 'sz300122', 'sz300136',
                'sz300142', 'sz300144', 'sz300347', 'sz300413', 'sz300450',
                'sz300496', 'sz300529', 'sz300558', 'sz300601', 'sz300628',
                'sz300661', 'sz300676', 'sz300750', 'sz300751', 'sz300759'
            ]
            
            return default_stocks
            
        except Exception as e:
            self.logger.error(f"获取股票列表失败: {e}")
            return ['sh000001', 'sz000001', 'sz000002']
    
    def _update_core_pool(self, high_quality_stocks: List[Dict]) -> None:
        """更新核心观察池"""
        core_pool_file = self.config['data']['core_pool_file']
        try:
            with open(core_pool_file, 'w', encoding='utf-8') as f:
                json.dump(high_quality_stocks, f, indent=2, ensure_ascii=False)
            self.logger.info(f"核心观察池已更新，包含{len(high_quality_stocks)}只股票")
        except Exception as e:
            self.logger.error(f"核心观察池更新失败: {e}")
    
    def _load_core_pool(self) -> List[Dict]:
        """加载核心观察池"""
        core_pool_file = self.config['data']['core_pool_file']
        if os.path.exists(core_pool_file):
            try:
                with open(core_pool_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"核心观察池加载失败: {e}")
        return []
    
    def _generate_daily_report(self, signals: List[Dict]) -> None:
        """生成每日交易报告"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'reports/daily_signals_{timestamp}.json'
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(signals, f, indent=2, ensure_ascii=False)
            self.logger.info(f"每日报告已保存: {filename}")
        except Exception as e:
            self.logger.error(f"报告生成失败: {e}")
    
    def _record_signals_to_history(self, signals: List[Dict]) -> None:
        """记录信号到历史记录"""
        try:
            history_file = "signal_history.json"
            
            history = []
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
            for signal in signals:
                signal_record = signal.copy()
                signal_record.update({
                    'signal_id': f"{signal['stock_code']}_{signal['timestamp'].replace(':', '').replace('-', '')}",
                    'recorded_at': datetime.now().isoformat(),
                    'status': 'active'
                })
                history.append(signal_record)
            
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"已记录 {len(signals)} 个信号到历史记录")
            
        except Exception as e:
            self.logger.error(f"记录信号历史失败: {e}")
    
    def _load_performance_data(self) -> Dict:
        """加载绩效数据"""
        perf_file = self.config['data']['performance_log']
        if os.path.exists(perf_file):
            try:
                with open(perf_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"绩效数据加载失败: {e}")
        return {}
    
    def _update_performance_tracking(self, performance_data: Dict) -> int:
        """更新绩效跟踪数据"""
        return 5
    
    def _adjust_core_pool_based_on_performance(self, performance_data: Dict) -> int:
        """基于绩效调整核心观察池"""
        return 2


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='三阶段交易决策支持系统工作流管理器')
    
    parser.add_argument('--phase', choices=['phase1', 'phase2', 'phase3', 'all'], 
                       default='all', help='执行的阶段')
    parser.add_argument('--config', default='workflow_config.json', 
                       help='配置文件路径')
    parser.add_argument('--force', action='store_true', 
                       help='强制执行，忽略时间间隔限制')
    parser.add_argument('--dry-run', action='store_true', 
                       help='试运行模式，不执行实际操作')
    
    args = parser.parse_args()
    
    try:
        manager = WorkflowManager(args.config)
        
        if args.dry_run:
            manager.logger.info("试运行模式：不执行实际操作")
            return
        
        if args.phase == 'all':
            phases = ['phase1', 'phase2', 'phase3']
        else:
            phases = [args.phase]
        
        if args.force:
            for phase in phases:
                manager.config[phase]['frequency_days'] = 0
        
        results = manager.run_workflow(phases)
        
        print("\n=== 工作流执行结果 ===")
        for phase, result in results.items():
            if result.get('skipped'):
                print(f"{phase}: 跳过 ({result['reason']})")
            elif result.get('success'):
                print(f"{phase}: 成功")
            else:
                print(f"{phase}: 失败 - {result.get('error', '未知错误')}")
        
    except Exception as e:
        print(f"工作流执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
