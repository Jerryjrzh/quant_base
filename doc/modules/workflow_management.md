# 工作流管理模块文档

## 🔄 模块概览

工作流管理模块是系统的调度核心，实现了三阶段智能交易工作流的统一管理和调度。通过模块化设计，将复杂的交易决策过程分解为可管理的阶段，实现从"广撒网筛选"到"精耕细作跟踪"的转变。

## 🏗️ 架构设计

```
WorkflowManager
├── Phase1Manager     # 深度海选与参数优化
├── Phase2Manager     # 每日验证与信号触发
├── Phase3Manager     # 绩效跟踪与反馈
├── ConfigManager     # 配置管理
├── StateManager      # 状态管理
└── ScheduleManager   # 调度管理
```

## 📋 核心工作流管理器

### 1. 主工作流管理器 (workflow_manager.py)

#### 核心类结构
```python
class WorkflowManager:
    def __init__(self, config_file: str = "workflow_config.json"):
        self.config_manager = ConfigManager(config_file)
        self.state_manager = StateManager()
        self.logger = self._setup_logging()
        
        # 阶段管理器
        self.phase_managers = {
            'phase1': Phase1Manager(self.config_manager),
            'phase2': Phase2Manager(self.config_manager),
            'phase3': Phase3Manager(self.config_manager)
        }
        
        # 执行状态
        self.execution_state = {
            'current_phase': None,
            'last_execution': {},
            'errors': [],
            'performance_metrics': {}
        }
    
    def run_complete_workflow(self, force: bool = False) -> dict:
        """
        运行完整的三阶段工作流
        
        Args:
            force: 是否强制执行（忽略时间限制）
            
        Returns:
            dict: 执行结果
        """
        
        workflow_result = {
            'start_time': datetime.now(),
            'phases_executed': [],
            'total_duration': 0,
            'success': True,
            'errors': []
        }
        
        try:
            self.logger.info("开始执行完整工作流")
            
            # Phase 1: 深度海选与参数优化
            phase1_result = self.execute_phase('phase1', force)
            workflow_result['phases_executed'].append({
                'phase': 'phase1',
                'result': phase1_result,
                'duration': phase1_result.get('duration', 0)
            })
            
            # Phase 2: 每日验证与信号触发
            phase2_result = self.execute_phase('phase2', force)
            workflow_result['phases_executed'].append({
                'phase': 'phase2',
                'result': phase2_result,
                'duration': phase2_result.get('duration', 0)
            })
            
            # Phase 3: 绩效跟踪与反馈
            phase3_result = self.execute_phase('phase3', force)
            workflow_result['phases_executed'].append({
                'phase': 'phase3',
                'result': phase3_result,
                'duration': phase3_result.get('duration', 0)
            })
            
            # 计算总耗时
            workflow_result['total_duration'] = sum(
                phase['duration'] for phase in workflow_result['phases_executed']
            )
            
            # 更新执行状态
            self._update_execution_state(workflow_result)
            
            self.logger.info(f"工作流执行完成，总耗时: {workflow_result['total_duration']:.2f}秒")
            
        except Exception as e:
            workflow_result['success'] = False
            workflow_result['errors'].append(str(e))
            self.logger.error(f"工作流执行失败: {str(e)}")
        
        finally:
            workflow_result['end_time'] = datetime.now()
        
        return workflow_result
    
    def execute_phase(self, phase_name: str, force: bool = False) -> dict:
        """
        执行指定阶段
        
        Args:
            phase_name: 阶段名称 ('phase1', 'phase2', 'phase3')
            force: 是否强制执行
            
        Returns:
            dict: 阶段执行结果
        """
        
        if phase_name not in self.phase_managers:
            raise ValueError(f"未知的阶段: {phase_name}")
        
        phase_manager = self.phase_managers[phase_name]
        
        # 检查执行条件
        if not force and not self._should_execute_phase(phase_name):
            return {
                'executed': False,
                'reason': 'frequency_limit',
                'message': f'{phase_name} 未到执行时间',
                'duration': 0
            }
        
        # 执行阶段
        start_time = time.time()
        self.execution_state['current_phase'] = phase_name
        
        try:
            self.logger.info(f"开始执行 {phase_name}")
            
            result = phase_manager.execute()
            
            execution_time = time.time() - start_time
            result['duration'] = execution_time
            result['executed'] = True
            
            # 更新最后执行时间
            self.execution_state['last_execution'][phase_name] = datetime.now()
            
            self.logger.info(f"{phase_name} 执行完成，耗时: {execution_time:.2f}秒")
            
            return result
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_result = {
                'executed': False,
                'error': str(e),
                'duration': execution_time
            }
            
            self.execution_state['errors'].append({
                'phase': phase_name,
                'error': str(e),
                'timestamp': datetime.now()
            })
            
            self.logger.error(f"{phase_name} 执行失败: {str(e)}")
            
            return error_result
        
        finally:
            self.execution_state['current_phase'] = None
    
    def _should_execute_phase(self, phase_name: str) -> bool:
        """检查阶段是否应该执行"""
        
        # 获取阶段配置
        phase_config = self.config_manager.get_config(f'phases.{phase_name}', {})
        frequency_hours = phase_config.get('frequency_hours', 24)
        
        # 检查上次执行时间
        last_execution = self.execution_state['last_execution'].get(phase_name)
        
        if last_execution is None:
            return True  # 从未执行过
        
        # 计算时间差
        time_diff = datetime.now() - last_execution
        required_interval = timedelta(hours=frequency_hours)
        
        return time_diff >= required_interval
    
    def get_workflow_status(self) -> dict:
        """获取工作流状态"""
        
        status = {
            'current_phase': self.execution_state['current_phase'],
            'last_execution': {
                phase: execution_time.isoformat() if execution_time else None
                for phase, execution_time in self.execution_state['last_execution'].items()
            },
            'next_execution': {},
            'recent_errors': self.execution_state['errors'][-5:],  # 最近5个错误
            'system_health': self._check_system_health()
        }
        
        # 计算下次执行时间
        for phase_name in self.phase_managers.keys():
            phase_config = self.config_manager.get_config(f'phases.{phase_name}', {})
            frequency_hours = phase_config.get('frequency_hours', 24)
            
            last_execution = self.execution_state['last_execution'].get(phase_name)
            if last_execution:
                next_execution = last_execution + timedelta(hours=frequency_hours)
                status['next_execution'][phase_name] = next_execution.isoformat()
            else:
                status['next_execution'][phase_name] = "立即可执行"
        
        return status
```

### 2. 阶段管理器基类

#### 基础阶段管理器
```python
class BasePhaseManager:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.phase_name = self.__class__.__name__.lower().replace('manager', '')
    
    def execute(self) -> dict:
        """执行阶段逻辑 - 子类必须实现"""
        raise NotImplementedError("子类必须实现execute方法")
    
    def validate_prerequisites(self) -> dict:
        """验证执行前提条件"""
        return {'valid': True, 'issues': []}
    
    def cleanup_after_execution(self):
        """执行后清理工作"""
        pass
    
    def get_phase_config(self) -> dict:
        """获取阶段配置"""
        return self.config_manager.get_config(f'phases.{self.phase_name}', {})
    
    def save_phase_result(self, result: dict):
        """保存阶段结果"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{self.phase_name}_result_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False, default=str)
            
            self.logger.info(f"阶段结果已保存: {filename}")
            
        except Exception as e:
            self.logger.error(f"保存阶段结果失败: {str(e)}")
```

### 3. Phase1Manager - 深度海选与参数优化

#### 实现逻辑
```python
class Phase1Manager(BasePhaseManager):
    def __init__(self, config_manager: ConfigManager):
        super().__init__(config_manager)
        self.stock_pool_manager = StockPoolManager()
        self.parameter_optimizer = ParameterOptimizer()
        self.screener = EnhancedScreener()
    
    def execute(self) -> dict:
        """
        执行Phase1: 深度海选与参数优化
        
        主要任务:
        1. 获取股票列表
        2. 参数优化
        3. 批量筛选
        4. 质量评估
        5. 生成核心观察池
        """
        
        phase1_result = {
            'phase': 'phase1',
            'start_time': datetime.now(),
            'tasks_completed': [],
            'core_pool_generated': False,
            'statistics': {}
        }
        
        try:
            # 1. 获取股票列表
            self.logger.info("获取股票列表...")
            stock_list = self._get_stock_list()
            phase1_result['tasks_completed'].append('stock_list_loaded')
            phase1_result['statistics']['total_stocks'] = len(stock_list)
            
            # 2. 参数优化
            self.logger.info("开始参数优化...")
            optimization_result = self._optimize_parameters(stock_list[:50])  # 使用前50只股票优化
            phase1_result['tasks_completed'].append('parameter_optimization')
            phase1_result['optimization_result'] = optimization_result
            
            # 3. 批量筛选
            self.logger.info("开始批量筛选...")
            screening_result = self._batch_screening(stock_list, optimization_result['best_params'])
            phase1_result['tasks_completed'].append('batch_screening')
            phase1_result['screening_result'] = screening_result
            
            # 4. 质量评估和过滤
            self.logger.info("进行质量评估...")
            quality_filtered_stocks = self._quality_assessment(screening_result['signals'])
            phase1_result['tasks_completed'].append('quality_assessment')
            phase1_result['statistics']['quality_filtered_count'] = len(quality_filtered_stocks)
            
            # 5. 生成核心观察池
            self.logger.info("生成核心观察池...")
            core_pool = self._generate_core_pool(quality_filtered_stocks)
            phase1_result['tasks_completed'].append('core_pool_generation')
            phase1_result['core_pool'] = core_pool
            phase1_result['core_pool_generated'] = True
            
            # 6. 保存结果
            self.stock_pool_manager.save_core_pool(core_pool)
            self.save_phase_result(phase1_result)
            
            self.logger.info(f"Phase1完成: 生成核心观察池 {len(core_pool)} 只股票")
            
        except Exception as e:
            phase1_result['error'] = str(e)
            self.logger.error(f"Phase1执行失败: {str(e)}")
        
        finally:
            phase1_result['end_time'] = datetime.now()
            phase1_result['duration'] = (
                phase1_result['end_time'] - phase1_result['start_time']
            ).total_seconds()
        
        return phase1_result
    
    def _optimize_parameters(self, sample_stocks: List[str]) -> dict:
        """参数优化"""
        
        config = self.get_phase_config()
        optimization_config = config.get('optimization', {})
        
        # 设置优化参数范围
        param_ranges = {
            'macd_fast_period': range(8, 16),
            'macd_slow_period': range(20, 30),
            'kdj_period': range(20, 35),
            'rsi_period': range(10, 20)
        }
        
        # 运行参数优化
        optimization_result = self.parameter_optimizer.optimize_parameters(
            sample_stocks, 
            param_ranges,
            max_combinations=optimization_config.get('max_combinations', 100)
        )
        
        return optimization_result
    
    def _batch_screening(self, stock_list: List[str], optimized_params: dict) -> dict:
        """批量筛选"""
        
        config = self.get_phase_config()
        screening_config = config.get('screening', {})
        
        # 设置筛选参数
        screening_params = {
            'strategies': ['TRIPLE_CROSS', 'PRE_CROSS'],
            'min_signal_strength': screening_config.get('min_signal_strength', 70),
            'enable_win_rate_filter': screening_config.get('enable_win_rate_filter', True),
            'parallel_workers': screening_config.get('parallel_workers', 4)
        }
        
        # 更新策略参数
        screening_params.update(optimized_params)
        
        # 执行筛选
        screening_result = self.screener.batch_screen_stocks(stock_list, screening_params)
        
        return screening_result
    
    def _quality_assessment(self, signals: List[dict]) -> List[dict]:
        """质量评估"""
        
        config = self.get_phase_config()
        quality_config = config.get('quality_assessment', {})
        
        min_quality_score = quality_config.get('min_quality_score', 70)
        max_risk_score = quality_config.get('max_risk_score', 60)
        
        quality_filtered = []
        
        for signal in signals:
            # 质量评分
            quality_score = signal.get('quality_score', 0)
            risk_score = signal.get('risk_score', 100)
            
            # 过滤条件
            if (quality_score >= min_quality_score and 
                risk_score <= max_risk_score):
                quality_filtered.append(signal)
        
        return quality_filtered
    
    def _generate_core_pool(self, filtered_signals: List[dict]) -> dict:
        """生成核心观察池"""
        
        config = self.get_phase_config()
        pool_config = config.get('core_pool', {})
        
        max_pool_size = pool_config.get('max_size', 50)
        
        # 按质量分数排序
        sorted_signals = sorted(
            filtered_signals, 
            key=lambda x: x.get('quality_score', 0), 
            reverse=True
        )
        
        # 选择前N只股票
        selected_signals = sorted_signals[:max_pool_size]
        
        # 构建核心观察池
        core_pool = {
            'generated_at': datetime.now().isoformat(),
            'pool_size': len(selected_signals),
            'selection_criteria': {
                'min_quality_score': config.get('quality_assessment', {}).get('min_quality_score', 70),
                'max_risk_score': config.get('quality_assessment', {}).get('max_risk_score', 60),
                'max_pool_size': max_pool_size
            },
            'stocks': []
        }
        
        for signal in selected_signals:
            stock_info = {
                'symbol': signal['symbol'],
                'quality_score': signal.get('quality_score', 0),
                'risk_score': signal.get('risk_score', 0),
                'signal_strength': signal.get('strength', 0),
                'strategy': signal.get('strategy', 'UNKNOWN'),
                'last_signal_date': signal.get('date', ''),
                'entry_reason': signal.get('reason', ''),
                'technical_indicators': signal.get('indicators', {}),
                'weight': self._calculate_stock_weight(signal)
            }
            
            core_pool['stocks'].append(stock_info)
        
        return core_pool
    
    def _calculate_stock_weight(self, signal: dict) -> float:
        """计算股票权重"""
        
        quality_score = signal.get('quality_score', 0)
        signal_strength = signal.get('strength', 0)
        risk_score = signal.get('risk_score', 100)
        
        # 权重计算公式
        weight = (quality_score * 0.4 + signal_strength * 0.4 + (100 - risk_score) * 0.2) / 100
        
        return round(weight, 3)
```

### 4. Phase2Manager - 每日验证与信号触发

#### 实现逻辑
```python
class Phase2Manager(BasePhaseManager):
    def __init__(self, config_manager: ConfigManager):
        super().__init__(config_manager)
        self.stock_pool_manager = StockPoolManager()
        self.signal_scanner = DailySignalScanner()
        self.trading_advisor = TradingAdvisor()
    
    def execute(self) -> dict:
        """
        执行Phase2: 每日验证与信号触发
        
        主要任务:
        1. 加载核心观察池
        2. 每日信号扫描
        3. 信号质量验证
        4. 生成交易建议
        5. 发送通知
        """
        
        phase2_result = {
            'phase': 'phase2',
            'start_time': datetime.now(),
            'tasks_completed': [],
            'signals_generated': 0,
            'trading_recommendations': []
        }
        
        try:
            # 1. 加载核心观察池
            self.logger.info("加载核心观察池...")
            core_pool = self.stock_pool_manager.load_core_pool()
            
            if not core_pool or not core_pool.get('stocks'):
                # 核心池为空，触发Phase1
                self.logger.warning("核心观察池为空，触发Phase1执行")
                phase1_manager = Phase1Manager(self.config_manager)
                phase1_result = phase1_manager.execute()
                
                if phase1_result.get('core_pool_generated'):
                    core_pool = self.stock_pool_manager.load_core_pool()
                else:
                    raise Exception("无法生成核心观察池")
            
            phase2_result['tasks_completed'].append('core_pool_loaded')
            phase2_result['core_pool_size'] = len(core_pool['stocks'])
            
            # 2. 每日信号扫描
            self.logger.info("开始每日信号扫描...")
            scan_result = self._daily_signal_scan(core_pool['stocks'])
            phase2_result['tasks_completed'].append('daily_signal_scan')
            phase2_result['scan_result'] = scan_result
            
            # 3. 信号质量验证
            self.logger.info("进行信号质量验证...")
            verified_signals = self._verify_signal_quality(scan_result['signals'])
            phase2_result['tasks_completed'].append('signal_verification')
            phase2_result['verified_signals'] = verified_signals
            phase2_result['signals_generated'] = len(verified_signals)
            
            # 4. 生成交易建议
            if verified_signals:
                self.logger.info("生成交易建议...")
                trading_recommendations = self._generate_trading_recommendations(verified_signals)
                phase2_result['tasks_completed'].append('trading_recommendations')
                phase2_result['trading_recommendations'] = trading_recommendations
                
                # 5. 保存交易信号
                self._save_trading_signals(verified_signals, trading_recommendations)
                phase2_result['tasks_completed'].append('signals_saved')
            
            # 6. 发送通知
            if phase2_result['signals_generated'] > 0:
                self._send_notifications(phase2_result)
                phase2_result['tasks_completed'].append('notifications_sent')
            
            self.logger.info(f"Phase2完成: 生成 {phase2_result['signals_generated']} 个交易信号")
            
        except Exception as e:
            phase2_result['error'] = str(e)
            self.logger.error(f"Phase2执行失败: {str(e)}")
        
        finally:
            phase2_result['end_time'] = datetime.now()
            phase2_result['duration'] = (
                phase2_result['end_time'] - phase2_result['start_time']
            ).total_seconds()
        
        return phase2_result
    
    def _daily_signal_scan(self, core_stocks: List[dict]) -> dict:
        """每日信号扫描"""
        
        config = self.get_phase_config()
        scan_config = config.get('signal_scan', {})
        
        scan_params = {
            'strategies': scan_config.get('strategies', ['TRIPLE_CROSS', 'PRE_CROSS']),
            'min_confidence': scan_config.get('min_confidence', 0.7),
            'enable_t1_check': scan_config.get('enable_t1_check', True)
        }
        
        # 提取股票代码
        symbols = [stock['symbol'] for stock in core_stocks]
        
        # 执行扫描
        scan_result = self.signal_scanner.scan_daily_signals(symbols, scan_params)
        
        return scan_result
    
    def _verify_signal_quality(self, signals: List[dict]) -> List[dict]:
        """验证信号质量"""
        
        config = self.get_phase_config()
        verification_config = config.get('signal_verification', {})
        
        min_quality_threshold = verification_config.get('min_quality_threshold', 75)
        max_risk_threshold = verification_config.get('max_risk_threshold', 50)
        
        verified_signals = []
        
        for signal in signals:
            # 重新计算质量分数
            quality_score = self._recalculate_quality_score(signal)
            risk_score = self._calculate_current_risk_score(signal)
            
            # 验证条件
            if (quality_score >= min_quality_threshold and 
                risk_score <= max_risk_threshold):
                
                signal['verified_quality_score'] = quality_score
                signal['current_risk_score'] = risk_score
                signal['verification_status'] = 'PASSED'
                verified_signals.append(signal)
            else:
                signal['verification_status'] = 'FAILED'
                signal['failure_reason'] = self._get_failure_reason(quality_score, risk_score, verification_config)
        
        return verified_signals
    
    def _generate_trading_recommendations(self, verified_signals: List[dict]) -> List[dict]:
        """生成交易建议"""
        
        recommendations = []
        
        for signal in verified_signals:
            recommendation = self.trading_advisor.generate_recommendation(signal)
            recommendations.append(recommendation)
        
        return recommendations
    
    def _save_trading_signals(self, signals: List[dict], recommendations: List[dict]):
        """保存交易信号"""
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 保存信号数据
        signals_file = f"daily_signals_{timestamp}.json"
        with open(f"reports/{signals_file}", 'w', encoding='utf-8') as f:
            json.dump(signals, f, indent=2, ensure_ascii=False, default=str)
        
        # 保存交易建议
        recommendations_file = f"trading_recommendations_{timestamp}.json"
        with open(f"reports/{recommendations_file}", 'w', encoding='utf-8') as f:
            json.dump(recommendations, f, indent=2, ensure_ascii=False, default=str)
        
        self.logger.info(f"交易信号已保存: {signals_file}, {recommendations_file}")
```

### 5. Phase3Manager - 绩效跟踪与反馈

#### 实现逻辑
```python
class Phase3Manager(BasePhaseManager):
    def __init__(self, config_manager: ConfigManager):
        super().__init__(config_manager)
        self.performance_tracker = PerformanceTracker()
        self.stock_pool_manager = StockPoolManager()
        self.feedback_optimizer = FeedbackOptimizer()
    
    def execute(self) -> dict:
        """
        执行Phase3: 绩效跟踪与反馈
        
        主要任务:
        1. 加载历史交易信号
        2. 计算信号绩效
        3. 分析表现差异
        4. 核心池动态调整
        5. 参数反馈优化
        """
        
        phase3_result = {
            'phase': 'phase3',
            'start_time': datetime.now(),
            'tasks_completed': [],
            'performance_analysis': {},
            'pool_adjustments': {}
        }
        
        try:
            # 1. 加载历史交易信号
            self.logger.info("加载历史交易信号...")
            historical_signals = self._load_historical_signals()
            phase3_result['tasks_completed'].append('historical_signals_loaded')
            phase3_result['historical_signals_count'] = len(historical_signals)
            
            # 2. 计算信号绩效
            self.logger.info("计算信号绩效...")
            performance_analysis = self._analyze_signal_performance(historical_signals)
            phase3_result['tasks_completed'].append('performance_analysis')
            phase3_result['performance_analysis'] = performance_analysis
            
            # 3. 识别表现差的股票
            self.logger.info("识别表现差异...")
            underperformers = self._identify_underperformers(performance_analysis)
            phase3_result['tasks_completed'].append('underperformers_identified')
            phase3_result['underperformers'] = underperformers
            
            # 4. 核心池动态调整
            self.logger.info("调整核心观察池...")
            pool_adjustments = self._adjust_core_pool(underperformers, performance_analysis)
            phase3_result['tasks_completed'].append('core_pool_adjusted')
            phase3_result['pool_adjustments'] = pool_adjustments
            
            # 5. 参数反馈优化
            self.logger.info("参数反馈优化...")
            optimization_feedback = self._generate_optimization_feedback(performance_analysis)
            phase3_result['tasks_completed'].append('optimization_feedback')
            phase3_result['optimization_feedback'] = optimization_feedback
            
            # 6. 生成绩效报告
            self._generate_performance_report(phase3_result)
            phase3_result['tasks_completed'].append('performance_report_generated')
            
            self.logger.info(f"Phase3完成: 调整核心池 {len(pool_adjustments.get('removed', []))} 只股票")
            
        except Exception as e:
            phase3_result['error'] = str(e)
            self.logger.error(f"Phase3执行失败: {str(e)}")
        
        finally:
            phase3_result['end_time'] = datetime.now()
            phase3_result['duration'] = (
                phase3_result['end_time'] - phase3_result['start_time']
            ).total_seconds()
        
        return phase3_result
    
    def _analyze_signal_performance(self, historical_signals: List[dict]) -> dict:
        """分析信号绩效"""
        
        performance_data = {}
        
        for signal in historical_signals:
            symbol = signal['symbol']
            
            if symbol not in performance_data:
                performance_data[symbol] = {
                    'signals': [],
                    'total_return': 0,
                    'win_count': 0,
                    'loss_count': 0,
                    'avg_return': 0,
                    'win_rate': 0,
                    'max_return': 0,
                    'max_loss': 0
                }
            
            # 计算信号收益
            signal_return = self.performance_tracker.calculate_signal_return(signal)
            performance_data[symbol]['signals'].append({
                'date': signal['date'],
                'return': signal_return,
                'hold_days': signal.get('hold_days', 0)
            })
            
            # 更新统计
            performance_data[symbol]['total_return'] += signal_return
            
            if signal_return > 0:
                performance_data[symbol]['win_count'] += 1
                performance_data[symbol]['max_return'] = max(
                    performance_data[symbol]['max_return'], signal_return
                )
            else:
                performance_data[symbol]['loss_count'] += 1
                performance_data[symbol]['max_loss'] = min(
                    performance_data[symbol]['max_loss'], signal_return
                )
        
        # 计算最终统计
        for symbol, data in performance_data.items():
            total_signals = len(data['signals'])
            if total_signals > 0:
                data['avg_return'] = data['total_return'] / total_signals
                data['win_rate'] = data['win_count'] / total_signals
        
        return performance_data
    
    def _identify_underperformers(self, performance_analysis: dict) -> List[dict]:
        """识别表现差的股票"""
        
        config = self.get_phase_config()
        underperform_config = config.get('underperformance_criteria', {})
        
        min_win_rate = underperform_config.get('min_win_rate', 0.4)
        min_avg_return = underperform_config.get('min_avg_return', 0.02)
        min_signals = underperform_config.get('min_signals', 3)
        
        underperformers = []
        
        for symbol, data in performance_analysis.items():
            if len(data['signals']) < min_signals:
                continue  # 信号数量不足，不做判断
            
            # 判断表现差的条件
            is_underperformer = (
                data['win_rate'] < min_win_rate or
                data['avg_return'] < min_avg_return
            )
            
            if is_underperformer:
                underperformers.append({
                    'symbol': symbol,
                    'win_rate': data['win_rate'],
                    'avg_return': data['avg_return'],
                    'total_signals': len(data['signals']),
                    'reason': self._get_underperformance_reason(data, underperform_config)
                })
        
        return underperformers
    
    def _adjust_core_pool(self, underperformers: List[dict], 
                         performance_analysis: dict) -> dict:
        """调整核心观察池"""
        
        # 加载当前核心池
        current_pool = self.stock_pool_manager.load_core_pool()
        
        if not current_pool:
            return {'removed': [], 'added': [], 'updated': []}
        
        adjustments = {
            'removed': [],
            'added': [],
            'updated': []
        }
        
        # 移除表现差的股票
        underperformer_symbols = {up['symbol'] for up in underperformers}
        
        updated_stocks = []
        for stock in current_pool['stocks']:
            if stock['symbol'] in underperformer_symbols:
                adjustments['removed'].append({
                    'symbol': stock['symbol'],
                    'reason': 'underperformance',
                    'original_weight': stock.get('weight', 0)
                })
            else:
                # 更新权重
                if stock['symbol'] in performance_analysis:
                    perf_data = performance_analysis[stock['symbol']]
                    new_weight = self._calculate_updated_weight(stock, perf_data)
                    
                    if new_weight != stock.get('weight', 0):
                        adjustments['updated'].append({
                            'symbol': stock['symbol'],
                            'old_weight': stock.get('weight', 0),
                            'new_weight': new_weight
                        })
                        stock['weight'] = new_weight
                
                updated_stocks.append(stock)
        
        # 更新核心池
        current_pool['stocks'] = updated_stocks
        current_pool['last_updated'] = datetime.now().isoformat()
        current_pool['adjustment_reason'] = 'performance_feedback'
        
        # 保存更新后的核心池
        self.stock_pool_manager.save_core_pool(current_pool)
        
        return adjustments
```

## 🎯 使用示例

### 完整工作流执行
```python
from backend.workflow_manager import WorkflowManager

# 1. 初始化工作流管理器
workflow_manager = WorkflowManager("workflow_config.json")

# 2. 运行完整工作流
print("=== 运行完整工作流 ===")
result = workflow_manager.run_complete_workflow()

print(f"执行状态: {'成功' if result['success'] else '失败'}")
print(f"总耗时: {result['total_duration']:.2f}秒")

for phase_info in result['phases_executed']:
    phase_name = phase_info['phase']
    phase_result = phase_info['result']
    duration = phase_info['duration']
    
    print(f"{phase_name}: {'完成' if phase_result.get('executed', False) else '跳过'} ({duration:.2f}s)")

# 3. 查看工作流状态
print("\n=== 工作流状态 ===")
status = workflow_manager.get_workflow_status()

print(f"当前执行阶段: {status['current_phase'] or '无'}")
print("最后执行时间:")
for phase, last_time in status['last_execution'].items():
    print(f"  {phase}: {last_time or '从未执行'}")

print("下次执行时间:")
for phase, next_time in status['next_execution'].items():
    print(f"  {phase}: {next_time}")

# 4. 单独执行某个阶段
print("\n=== 单独执行Phase2 ===")
phase2_result = workflow_manager.execute_phase('phase2', force=True)

if phase2_result.get('executed'):
    print(f"Phase2执行完成: 生成 {phase2_result.get('signals_generated', 0)} 个信号")
else:
    print(f"Phase2跳过: {phase2_result.get('reason', '未知原因')}")
```

### 配置文件示例
```json
{
  "phases": {
    "phase1": {
      "frequency_hours": 168,
      "optimization": {
        "max_combinations": 100,
        "sample_size": 50
      },
      "screening": {
        "min_signal_strength": 70,
        "enable_win_rate_filter": true,
        "parallel_workers": 4
      },
      "quality_assessment": {
        "min_quality_score": 70,
        "max_risk_score": 60
      },
      "core_pool": {
        "max_size": 50
      }
    },
    "phase2": {
      "frequency_hours": 24,
      "signal_scan": {
        "strategies": ["TRIPLE_CROSS", "PRE_CROSS"],
        "min_confidence": 0.7,
        "enable_t1_check": true
      },
      "signal_verification": {
        "min_quality_threshold": 75,
        "max_risk_threshold": 50
      }
    },
    "phase3": {
      "frequency_hours": 72,
      "underperformance_criteria": {
        "min_win_rate": 0.4,
        "min_avg_return": 0.02,
        "min_signals": 3
      }
    }
  },
  "logging": {
    "level": "INFO",
    "file": "workflow.log",
    "max_size_mb": 10,
    "backup_count": 5
  },
  "notifications": {
    "enabled": true,
    "email": {
      "enabled": false,
      "smtp_server": "smtp.example.com",
      "recipients": ["user@example.com"]
    },
    "webhook": {
      "enabled": false,
      "url": "https://hooks.example.com/webhook"
    }
  }
}
```

工作流管理模块通过精心设计的三阶段架构，实现了从传统的一次性分析到持续跟踪优化的转变，为智能交易决策提供了强大的基础设施支持。