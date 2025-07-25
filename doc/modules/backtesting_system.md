# 回测系统模块文档

## 🔄 模块概览

回测系统是验证交易策略有效性的核心模块，提供历史数据回测、性能分析、风险评估等功能。支持多种回测模式，包括传统回测、T+1规则回测、季度回测等。

## 🏗️ 系统架构

```
BacktestingSystem
├── HistoricalBacktester     # 传统历史回测
├── T1IntelligentBacktester  # T+1规则回测
├── QuarterlyBacktester      # 季度回测
├── PerformanceAnalyzer      # 性能分析器
├── RiskAnalyzer            # 风险分析器
└── ReportGenerator         # 报告生成器
```

## 📊 核心回测引擎

### 1. 基础回测系统 (backtester.py)

#### 核心类结构
```python
class BacktestingSystem:
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.current_cash = initial_capital
        self.positions = {}  # 持仓信息
        self.trade_history = []  # 交易历史
        self.daily_portfolio_value = []  # 每日组合价值
        
        # 交易参数
        self.commission_rate = 0.0003  # 手续费率
        self.slippage_rate = 0.001     # 滑点率
        self.max_position_size = 0.2   # 单股最大仓位
        
    def run_backtest(self, strategy_func: Callable, data: pd.DataFrame, 
                     config: dict, start_date: str = None, 
                     end_date: str = None) -> dict:
        """
        运行回测
        
        Args:
            strategy_func: 策略函数
            data: 历史数据
            config: 策略配置
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            dict: 回测结果
        """
        
        # 数据预处理
        backtest_data = self._prepare_data(data, start_date, end_date)
        
        # 初始化回测状态
        self._reset_backtest_state()
        
        # 逐日回测
        for i in range(len(backtest_data)):
            current_date = backtest_data.index[i]
            current_data = backtest_data.iloc[:i+1]  # 截至当前的所有数据
            current_price = backtest_data.iloc[i]
            
            # 更新持仓价值
            self._update_portfolio_value(current_date, current_price)
            
            # 生成交易信号
            if len(current_data) >= 30:  # 确保有足够数据计算指标
                signal = strategy_func(current_data, config)
                
                # 执行交易
                if signal.get('signal', False):
                    self._execute_trade(
                        symbol=data.attrs.get('symbol', 'UNKNOWN'),
                        date=current_date,
                        price=current_price['close'],
                        signal=signal
                    )
        
        # 计算最终结果
        return self._calculate_backtest_results()
    
    def _execute_trade(self, symbol: str, date: pd.Timestamp, 
                      price: float, signal: dict):
        """执行交易"""
        
        # 计算交易数量
        signal_strength = signal.get('strength', 0) / 100
        position_size = self.max_position_size * signal_strength
        
        # 买入逻辑
        if symbol not in self.positions:
            # 计算可买入股数
            available_cash = self.current_cash * position_size
            shares_to_buy = int(available_cash / (price * (1 + self.commission_rate + self.slippage_rate)))
            
            if shares_to_buy > 0:
                total_cost = shares_to_buy * price * (1 + self.commission_rate + self.slippage_rate)
                
                if total_cost <= self.current_cash:
                    # 执行买入
                    self.positions[symbol] = {
                        'shares': shares_to_buy,
                        'buy_price': price,
                        'buy_date': date,
                        'total_cost': total_cost
                    }
                    
                    self.current_cash -= total_cost
                    
                    # 记录交易
                    self.trade_history.append({
                        'date': date,
                        'symbol': symbol,
                        'action': 'BUY',
                        'shares': shares_to_buy,
                        'price': price,
                        'total_amount': total_cost,
                        'signal_strength': signal.get('strength', 0)
                    })
        
        else:
            # 卖出逻辑 (基于止盈止损或信号强度下降)
            position = self.positions[symbol]
            current_return = (price - position['buy_price']) / position['buy_price']
            
            should_sell = (
                current_return > 0.15 or  # 止盈15%
                current_return < -0.08 or  # 止损8%
                signal.get('strength', 0) < 30  # 信号强度过低
            )
            
            if should_sell:
                shares = position['shares']
                sell_amount = shares * price * (1 - self.commission_rate - self.slippage_rate)
                
                self.current_cash += sell_amount
                
                # 记录交易
                self.trade_history.append({
                    'date': date,
                    'symbol': symbol,
                    'action': 'SELL',
                    'shares': shares,
                    'price': price,
                    'total_amount': sell_amount,
                    'return': current_return,
                    'hold_days': (date - position['buy_date']).days
                })
                
                # 移除持仓
                del self.positions[symbol]
```

#### 性能分析器
```python
class PerformanceAnalyzer:
    def __init__(self):
        self.risk_free_rate = 0.03  # 无风险利率3%
    
    def calculate_performance_metrics(self, backtest_result: dict) -> dict:
        """
        计算性能指标
        
        Returns:
            dict: 包含各种性能指标的字典
        """
        
        daily_values = backtest_result['daily_portfolio_value']
        trades = backtest_result['trades']
        
        if not daily_values:
            return {}
        
        # 基础指标
        initial_value = daily_values[0]['portfolio_value']
        final_value = daily_values[-1]['portfolio_value']
        total_return = (final_value - initial_value) / initial_value
        
        # 计算日收益率序列
        daily_returns = []
        for i in range(1, len(daily_values)):
            prev_value = daily_values[i-1]['portfolio_value']
            curr_value = daily_values[i]['portfolio_value']
            daily_return = (curr_value - prev_value) / prev_value
            daily_returns.append(daily_return)
        
        daily_returns = np.array(daily_returns)
        
        # 年化收益率
        trading_days = len(daily_returns)
        annualized_return = (1 + total_return) ** (252 / trading_days) - 1
        
        # 波动率
        volatility = np.std(daily_returns) * np.sqrt(252)
        
        # 夏普比率
        excess_return = annualized_return - self.risk_free_rate
        sharpe_ratio = excess_return / volatility if volatility > 0 else 0
        
        # 最大回撤
        max_drawdown, max_drawdown_duration = self._calculate_max_drawdown(daily_values)
        
        # 交易统计
        trade_stats = self._calculate_trade_statistics(trades)
        
        # 风险指标
        risk_metrics = self._calculate_risk_metrics(daily_returns)
        
        return {
            # 收益指标
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            
            # 风险指标
            'max_drawdown': max_drawdown,
            'max_drawdown_duration': max_drawdown_duration,
            'var_95': risk_metrics['var_95'],
            'cvar_95': risk_metrics['cvar_95'],
            
            # 交易指标
            'total_trades': trade_stats['total_trades'],
            'win_rate': trade_stats['win_rate'],
            'avg_return_per_trade': trade_stats['avg_return_per_trade'],
            'avg_hold_days': trade_stats['avg_hold_days'],
            'profit_factor': trade_stats['profit_factor'],
            
            # 其他指标
            'calmar_ratio': annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0,
            'sortino_ratio': self._calculate_sortino_ratio(daily_returns),
            'information_ratio': self._calculate_information_ratio(daily_returns)
        }
    
    def _calculate_max_drawdown(self, daily_values: list) -> tuple:
        """计算最大回撤和回撤持续时间"""
        values = [item['portfolio_value'] for item in daily_values]
        
        peak = values[0]
        max_drawdown = 0
        max_drawdown_duration = 0
        current_drawdown_duration = 0
        
        for value in values:
            if value > peak:
                peak = value
                current_drawdown_duration = 0
            else:
                drawdown = (peak - value) / peak
                max_drawdown = max(max_drawdown, drawdown)
                current_drawdown_duration += 1
                max_drawdown_duration = max(max_drawdown_duration, current_drawdown_duration)
        
        return max_drawdown, max_drawdown_duration
    
    def _calculate_trade_statistics(self, trades: list) -> dict:
        """计算交易统计"""
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_return_per_trade': 0,
                'avg_hold_days': 0,
                'profit_factor': 0
            }
        
        # 只统计卖出交易
        sell_trades = [trade for trade in trades if trade['action'] == 'SELL']
        
        if not sell_trades:
            return {
                'total_trades': len(trades),
                'win_rate': 0,
                'avg_return_per_trade': 0,
                'avg_hold_days': 0,
                'profit_factor': 0
            }
        
        # 胜率
        winning_trades = [trade for trade in sell_trades if trade.get('return', 0) > 0]
        win_rate = len(winning_trades) / len(sell_trades)
        
        # 平均收益率
        returns = [trade.get('return', 0) for trade in sell_trades]
        avg_return_per_trade = np.mean(returns)
        
        # 平均持有天数
        hold_days = [trade.get('hold_days', 0) for trade in sell_trades]
        avg_hold_days = np.mean(hold_days)
        
        # 盈亏比
        winning_returns = [r for r in returns if r > 0]
        losing_returns = [r for r in returns if r < 0]
        
        avg_win = np.mean(winning_returns) if winning_returns else 0
        avg_loss = abs(np.mean(losing_returns)) if losing_returns else 0
        
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0
        
        return {
            'total_trades': len(sell_trades),
            'win_rate': win_rate,
            'avg_return_per_trade': avg_return_per_trade,
            'avg_hold_days': avg_hold_days,
            'profit_factor': profit_factor
        }
    
    def _calculate_risk_metrics(self, daily_returns: np.ndarray) -> dict:
        """计算风险指标"""
        if len(daily_returns) == 0:
            return {'var_95': 0, 'cvar_95': 0}
        
        # VaR (Value at Risk) 95%
        var_95 = np.percentile(daily_returns, 5)
        
        # CVaR (Conditional Value at Risk) 95%
        cvar_95 = np.mean(daily_returns[daily_returns <= var_95])
        
        return {
            'var_95': var_95,
            'cvar_95': cvar_95
        }
    
    def _calculate_sortino_ratio(self, daily_returns: np.ndarray) -> float:
        """计算Sortino比率"""
        if len(daily_returns) == 0:
            return 0
        
        # 只考虑负收益的波动率
        negative_returns = daily_returns[daily_returns < 0]
        downside_deviation = np.std(negative_returns) * np.sqrt(252) if len(negative_returns) > 0 else 0
        
        if downside_deviation == 0:
            return 0
        
        annualized_return = np.mean(daily_returns) * 252
        excess_return = annualized_return - self.risk_free_rate
        
        return excess_return / downside_deviation
    
    def _calculate_information_ratio(self, daily_returns: np.ndarray) -> float:
        """计算信息比率"""
        if len(daily_returns) == 0:
            return 0
        
        # 假设基准收益率为0 (相对收益)
        excess_returns = daily_returns
        tracking_error = np.std(excess_returns) * np.sqrt(252)
        
        if tracking_error == 0:
            return 0
        
        return np.mean(excess_returns) * 252 / tracking_error
```

### 2. T+1智能回测系统 (integrated_t1_backtester.py)

#### T+1规则实现
```python
class IntegratedT1Backtester:
    def __init__(self, initial_capital: float = 100000.0):
        self.trading_system = T1IntelligentTradingSystem(initial_capital)
        self.performance_analyzer = PerformanceAnalyzer()
    
    def run_t1_backtest(self, stock_data: Dict[str, pd.DataFrame], 
                       start_date: str = None, end_date: str = None) -> dict:
        """
        运行T+1规则回测
        
        Args:
            stock_data: 股票数据字典 {symbol: DataFrame}
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            dict: T+1回测结果
        """
        
        # 获取所有交易日期
        all_dates = self._get_all_trading_dates(stock_data, start_date, end_date)
        
        backtest_results = {
            'trading_signals': [],
            'portfolio_history': [],
            'performance_metrics': {},
            't1_compliance': True,
            'violations': []
        }
        
        # 逐日执行T+1交易逻辑
        for date in all_dates:
            # 更新T+1状态 (买入次日可卖出)
            self.trading_system.update_positions(date, self._get_prices_for_date(stock_data, date))
            
            # 为每只股票生成交易信号
            for symbol, df in stock_data.items():
                try:
                    # 获取截至当前日期的数据
                    current_data = df[df.index <= date]
                    
                    if len(current_data) < 30:  # 数据不足
                        continue
                    
                    # 生成T+1交易信号
                    signal = self.trading_system.generate_trading_signal(symbol, current_data, date)
                    
                    # 验证T+1规则合规性
                    compliance_check = self._verify_t1_compliance(signal, symbol, date)
                    
                    if not compliance_check['compliant']:
                        backtest_results['violations'].append(compliance_check)
                        backtest_results['t1_compliance'] = False
                        continue
                    
                    # 执行交易
                    if signal.action in [TradingAction.BUY, TradingAction.SELL]:
                        execution_result = self.trading_system.execute_trade(signal)
                        
                        if execution_result:
                            backtest_results['trading_signals'].append({
                                'date': date.strftime('%Y-%m-%d'),
                                'symbol': symbol,
                                'action': signal.action.value,
                                'price': signal.price,
                                'confidence': signal.confidence,
                                'reason': signal.reason,
                                'trend_expectation': signal.trend_expectation.value
                            })
                
                except Exception as e:
                    logger.error(f"T+1回测错误 {symbol} on {date}: {str(e)}")
            
            # 记录每日组合状态
            portfolio_value = self.trading_system.get_portfolio_value(
                self._get_prices_for_date(stock_data, date)
            )
            
            backtest_results['portfolio_history'].append({
                'date': date.strftime('%Y-%m-%d'),
                'portfolio_value': portfolio_value,
                'cash': self.trading_system.current_cash,
                'positions': len(self.trading_system.positions),
                'total_return': (portfolio_value - self.trading_system.initial_capital) / self.trading_system.initial_capital
            })
        
        # 计算性能指标
        backtest_results['performance_metrics'] = self._calculate_t1_performance(backtest_results)
        
        return backtest_results
    
    def _verify_t1_compliance(self, signal: TradingSignal, symbol: str, date: datetime) -> dict:
        """验证T+1规则合规性"""
        
        if signal.action != TradingAction.SELL:
            return {'compliant': True}
        
        # 检查是否有持仓
        if symbol not in self.trading_system.positions:
            return {
                'compliant': False,
                'violation_type': 'NO_POSITION',
                'message': f'尝试卖出未持有的股票: {symbol}'
            }
        
        position = self.trading_system.positions[symbol]
        
        # 检查T+1规则
        if not position.can_sell:
            return {
                'compliant': False,
                'violation_type': 'T1_VIOLATION',
                'message': f'违反T+1规则: {symbol} 买入日期 {position.buy_date}, 当前日期 {date.strftime("%Y-%m-%d")}'
            }
        
        return {'compliant': True}
    
    def _calculate_t1_performance(self, backtest_results: dict) -> dict:
        """计算T+1回测性能指标"""
        
        portfolio_history = backtest_results['portfolio_history']
        trading_signals = backtest_results['trading_signals']
        
        if not portfolio_history:
            return {}
        
        # 基础收益指标
        initial_value = portfolio_history[0]['portfolio_value']
        final_value = portfolio_history[-1]['portfolio_value']
        total_return = (final_value - initial_value) / initial_value
        
        # 计算日收益率
        daily_returns = []
        for i in range(1, len(portfolio_history)):
            prev_value = portfolio_history[i-1]['portfolio_value']
            curr_value = portfolio_history[i]['portfolio_value']
            daily_return = (curr_value - prev_value) / prev_value
            daily_returns.append(daily_return)
        
        # 年化指标
        trading_days = len(daily_returns)
        annualized_return = (1 + total_return) ** (252 / trading_days) - 1 if trading_days > 0 else 0
        volatility = np.std(daily_returns) * np.sqrt(252) if daily_returns else 0
        
        # 夏普比率
        risk_free_rate = 0.03
        sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0
        
        # 最大回撤
        max_drawdown = self._calculate_max_drawdown_from_history(portfolio_history)
        
        # T+1特定指标
        buy_signals = [s for s in trading_signals if s['action'] == 'BUY']
        sell_signals = [s for s in trading_signals if s['action'] == 'SELL']
        
        # 交易频率
        total_days = len(portfolio_history)
        trading_frequency = len(trading_signals) / total_days if total_days > 0 else 0
        
        return {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'volatility': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'total_trades': len(trading_signals),
            'buy_signals': len(buy_signals),
            'sell_signals': len(sell_signals),
            'trading_frequency': trading_frequency,
            't1_compliance_rate': 1.0 if backtest_results['t1_compliance'] else 0.0,
            'violations_count': len(backtest_results['violations'])
        }
```

### 3. 季度回测系统 (quarterly_backtester.py)

#### 季度策略回测
```python
class QuarterlyBacktester:
    def __init__(self):
        self.quarters = {
            'Q1': ['01', '02', '03'],
            'Q2': ['04', '05', '06'],
            'Q3': ['07', '08', '09'],
            'Q4': ['10', '11', '12']
        }
    
    def run_quarterly_backtest(self, strategy_func: Callable, 
                              stock_data: Dict[str, pd.DataFrame],
                              config: dict, years: List[int]) -> dict:
        """
        运行季度回测
        
        Args:
            strategy_func: 策略函数
            stock_data: 股票数据
            config: 策略配置
            years: 回测年份列表
            
        Returns:
            dict: 季度回测结果
        """
        
        quarterly_results = {}
        
        for year in years:
            yearly_results = {}
            
            for quarter, months in self.quarters.items():
                quarter_key = f"{year}{quarter}"
                
                # 筛选季度数据
                quarter_data = self._filter_quarter_data(stock_data, year, months)
                
                if not quarter_data:
                    continue
                
                # 执行季度回测
                quarter_result = self._run_single_quarter_backtest(
                    strategy_func, quarter_data, config, year, quarter
                )
                
                yearly_results[quarter] = quarter_result
            
            quarterly_results[year] = yearly_results
        
        # 计算季度统计
        quarterly_stats = self._calculate_quarterly_statistics(quarterly_results)
        
        return {
            'quarterly_results': quarterly_results,
            'quarterly_statistics': quarterly_stats,
            'seasonal_analysis': self._analyze_seasonal_patterns(quarterly_results)
        }
    
    def _run_single_quarter_backtest(self, strategy_func: Callable,
                                   quarter_data: Dict[str, pd.DataFrame],
                                   config: dict, year: int, quarter: str) -> dict:
        """运行单个季度的回测"""
        
        backtester = BacktestingSystem(initial_capital=100000)
        quarter_results = []
        
        for symbol, df in quarter_data.items():
            if len(df) < 20:  # 数据不足
                continue
            
            try:
                # 运行回测
                result = backtester.run_backtest(strategy_func, df, config)
                
                result['symbol'] = symbol
                result['year'] = year
                result['quarter'] = quarter
                
                quarter_results.append(result)
                
            except Exception as e:
                logger.error(f"季度回测错误 {symbol} {year}{quarter}: {str(e)}")
        
        # 汇总季度结果
        return self._aggregate_quarter_results(quarter_results)
    
    def _aggregate_quarter_results(self, quarter_results: List[dict]) -> dict:
        """汇总季度结果"""
        
        if not quarter_results:
            return {}
        
        # 计算平均指标
        total_returns = [r['performance']['total_return'] for r in quarter_results 
                        if 'performance' in r and 'total_return' in r['performance']]
        
        win_rates = [r['performance']['win_rate'] for r in quarter_results 
                    if 'performance' in r and 'win_rate' in r['performance']]
        
        sharpe_ratios = [r['performance']['sharpe_ratio'] for r in quarter_results 
                        if 'performance' in r and 'sharpe_ratio' in r['performance']]
        
        return {
            'stocks_analyzed': len(quarter_results),
            'avg_return': np.mean(total_returns) if total_returns else 0,
            'avg_win_rate': np.mean(win_rates) if win_rates else 0,
            'avg_sharpe_ratio': np.mean(sharpe_ratios) if sharpe_ratios else 0,
            'best_performer': max(quarter_results, key=lambda x: x.get('performance', {}).get('total_return', 0)),
            'worst_performer': min(quarter_results, key=lambda x: x.get('performance', {}).get('total_return', 0))
        }
    
    def _analyze_seasonal_patterns(self, quarterly_results: dict) -> dict:
        """分析季节性模式"""
        
        seasonal_stats = {quarter: [] for quarter in self.quarters.keys()}
        
        # 收集各季度数据
        for year_data in quarterly_results.values():
            for quarter, quarter_data in year_data.items():
                if 'avg_return' in quarter_data:
                    seasonal_stats[quarter].append(quarter_data['avg_return'])
        
        # 计算季节性统计
        seasonal_analysis = {}
        for quarter, returns in seasonal_stats.items():
            if returns:
                seasonal_analysis[quarter] = {
                    'avg_return': np.mean(returns),
                    'std_return': np.std(returns),
                    'best_year': max(returns),
                    'worst_year': min(returns),
                    'consistency': 1 - (np.std(returns) / abs(np.mean(returns))) if np.mean(returns) != 0 else 0
                }
        
        # 找出最佳季度
        best_quarter = max(seasonal_analysis.keys(), 
                          key=lambda q: seasonal_analysis[q]['avg_return'])
        
        return {
            'seasonal_stats': seasonal_analysis,
            'best_quarter': best_quarter,
            'seasonal_ranking': sorted(seasonal_analysis.keys(), 
                                     key=lambda q: seasonal_analysis[q]['avg_return'], 
                                     reverse=True)
        }
```

## 📈 高级回测功能

### 1. 多策略对比回测
```python
class MultiStrategyBacktester:
    def __init__(self):
        self.strategies = {}
        self.results = {}
    
    def add_strategy(self, name: str, strategy_func: Callable, config: dict):
        """添加策略"""
        self.strategies[name] = {
            'func': strategy_func,
            'config': config
        }
    
    def run_comparison_backtest(self, stock_data: Dict[str, pd.DataFrame]) -> dict:
        """运行多策略对比回测"""
        
        comparison_results = {}
        
        for strategy_name, strategy_info in self.strategies.items():
            logger.info(f"运行策略回测: {strategy_name}")
            
            backtester = BacktestingSystem()
            strategy_results = []
            
            for symbol, df in stock_data.items():
                try:
                    result = backtester.run_backtest(
                        strategy_info['func'], 
                        df, 
                        strategy_info['config']
                    )
                    result['symbol'] = symbol
                    strategy_results.append(result)
                    
                except Exception as e:
                    logger.error(f"策略 {strategy_name} 回测 {symbol} 失败: {str(e)}")
            
            comparison_results[strategy_name] = self._aggregate_strategy_results(strategy_results)
        
        # 生成对比分析
        comparison_analysis = self._generate_comparison_analysis(comparison_results)
        
        return {
            'strategy_results': comparison_results,
            'comparison_analysis': comparison_analysis,
            'ranking': self._rank_strategies(comparison_results)
        }
    
    def _generate_comparison_analysis(self, results: dict) -> dict:
        """生成对比分析"""
        
        metrics = ['avg_return', 'avg_win_rate', 'avg_sharpe_ratio', 'avg_max_drawdown']
        comparison = {}
        
        for metric in metrics:
            comparison[metric] = {}
            values = []
            
            for strategy_name, strategy_result in results.items():
                value = strategy_result.get(metric, 0)
                comparison[metric][strategy_name] = value
                values.append(value)
            
            # 找出最佳和最差策略
            if values:
                best_strategy = max(comparison[metric].keys(), 
                                  key=lambda s: comparison[metric][s])
                worst_strategy = min(comparison[metric].keys(), 
                                   key=lambda s: comparison[metric][s])
                
                comparison[metric]['best'] = best_strategy
                comparison[metric]['worst'] = worst_strategy
        
        return comparison
```

### 2. 风险调整回测
```python
class RiskAdjustedBacktester:
    def __init__(self):
        self.risk_models = {
            'var': self._calculate_var_limit,
            'volatility': self._calculate_volatility_limit,
            'drawdown': self._calculate_drawdown_limit
        }
    
    def run_risk_adjusted_backtest(self, strategy_func: Callable,
                                  stock_data: Dict[str, pd.DataFrame],
                                  config: dict, risk_config: dict) -> dict:
        """
        运行风险调整回测
        
        Args:
            strategy_func: 策略函数
            stock_data: 股票数据
            config: 策略配置
            risk_config: 风险控制配置
                {
                    'max_var': 0.05,           # 最大VaR
                    'max_volatility': 0.20,    # 最大波动率
                    'max_drawdown': 0.15,      # 最大回撤
                    'position_limit': 0.10     # 单股最大仓位
                }
        """
        
        backtester = BacktestingSystem()
        
        # 设置风险参数
        backtester.max_position_size = risk_config.get('position_limit', 0.10)
        
        risk_adjusted_results = []
        
        for symbol, df in stock_data.items():
            try:
                # 运行基础回测
                base_result = backtester.run_backtest(strategy_func, df, config)
                
                # 应用风险调整
                risk_adjusted_result = self._apply_risk_adjustments(
                    base_result, risk_config
                )
                
                risk_adjusted_result['symbol'] = symbol
                risk_adjusted_results.append(risk_adjusted_result)
                
            except Exception as e:
                logger.error(f"风险调整回测错误 {symbol}: {str(e)}")
        
        return {
            'risk_adjusted_results': risk_adjusted_results,
            'risk_compliance': self._check_risk_compliance(risk_adjusted_results, risk_config),
            'risk_metrics': self._calculate_risk_metrics(risk_adjusted_results)
        }
    
    def _apply_risk_adjustments(self, base_result: dict, risk_config: dict) -> dict:
        """应用风险调整"""
        
        adjusted_result = base_result.copy()
        
        # 检查各项风险指标
        performance = base_result.get('performance', {})
        
        # VaR调整
        if 'max_var' in risk_config:
            var_95 = performance.get('var_95', 0)
            if abs(var_95) > risk_config['max_var']:
                # 降低仓位
                position_adjustment = risk_config['max_var'] / abs(var_95)
                adjusted_result['position_adjustment'] = position_adjustment
        
        # 波动率调整
        if 'max_volatility' in risk_config:
            volatility = performance.get('volatility', 0)
            if volatility > risk_config['max_volatility']:
                volatility_adjustment = risk_config['max_volatility'] / volatility
                adjusted_result['volatility_adjustment'] = volatility_adjustment
        
        # 回撤调整
        if 'max_drawdown' in risk_config:
            max_drawdown = performance.get('max_drawdown', 0)
            if max_drawdown > risk_config['max_drawdown']:
                drawdown_adjustment = risk_config['max_drawdown'] / max_drawdown
                adjusted_result['drawdown_adjustment'] = drawdown_adjustment
        
        return adjusted_result
```

## 📊 回测报告生成

### 回测报告生成器
```python
class BacktestReportGenerator:
    def __init__(self):
        self.report_templates = {
            'summary': self._generate_summary_report,
            'detailed': self._generate_detailed_report,
            'comparison': self._generate_comparison_report
        }
    
    def generate_backtest_report(self, backtest_results: dict, 
                               report_type: str = 'summary') -> dict:
        """生成回测报告"""
        
        if report_type not in self.report_templates:
            raise ValueError(f"不支持的报告类型: {report_type}")
        
        return self.report_templates[report_type](backtest_results)
    
    def _generate_summary_report(self, results: dict) -> dict:
        """生成摘要报告"""
        
        performance = results.get('performance', {})
        
        return {
            'report_type': 'summary',
            'generated_at': datetime.now().isoformat(),
            'key_metrics': {
                '总收益率': f"{performance.get('total_return', 0):.2%}",
                '年化收益率': f"{performance.get('annualized_return', 0):.2%}",
                '夏普比率': f"{performance.get('sharpe_ratio', 0):.2f}",
                '最大回撤': f"{performance.get('max_drawdown', 0):.2%}",
                '胜率': f"{performance.get('win_rate', 0):.2%}",
                '交易次数': performance.get('total_trades', 0)
            },
            'risk_assessment': self._assess_risk_level(performance),
            'recommendations': self._generate_recommendations(performance)
        }
    
    def _assess_risk_level(self, performance: dict) -> str:
        """评估风险水平"""
        
        max_drawdown = performance.get('max_drawdown', 0)
        volatility = performance.get('volatility', 0)
        sharpe_ratio = performance.get('sharpe_ratio', 0)
        
        risk_score = 0
        
        # 回撤风险
        if max_drawdown > 0.20:
            risk_score += 3
        elif max_drawdown > 0.10:
            risk_score += 2
        elif max_drawdown > 0.05:
            risk_score += 1
        
        # 波动率风险
        if volatility > 0.30:
            risk_score += 3
        elif volatility > 0.20:
            risk_score += 2
        elif volatility > 0.15:
            risk_score += 1
        
        # 夏普比率调整
        if sharpe_ratio < 0.5:
            risk_score += 2
        elif sharpe_ratio < 1.0:
            risk_score += 1
        
        if risk_score >= 6:
            return "高风险"
        elif risk_score >= 3:
            return "中等风险"
        else:
            return "低风险"
    
    def _generate_recommendations(self, performance: dict) -> List[str]:
        """生成改进建议"""
        
        recommendations = []
        
        # 收益率建议
        total_return = performance.get('total_return', 0)
        if total_return < 0.05:
            recommendations.append("收益率偏低，建议优化策略参数或选股标准")
        
        # 夏普比率建议
        sharpe_ratio = performance.get('sharpe_ratio', 0)
        if sharpe_ratio < 1.0:
            recommendations.append("风险调整收益不佳，建议加强风险控制")
        
        # 胜率建议
        win_rate = performance.get('win_rate', 0)
        if win_rate < 0.4:
            recommendations.append("胜率偏低，建议改进信号过滤条件")
        
        # 回撤建议
        max_drawdown = performance.get('max_drawdown', 0)
        if max_drawdown > 0.15:
            recommendations.append("最大回撤过大，建议设置更严格的止损条件")
        
        # 交易频率建议
        total_trades = performance.get('total_trades', 0)
        if total_trades < 5:
            recommendations.append("交易次数过少，可能错过机会，建议适当放宽信号条件")
        elif total_trades > 50:
            recommendations.append("交易过于频繁，建议提高信号质量要求")
        
        return recommendations
```

## 🎯 使用示例

### 完整回测流程
```python
from backend.backtester import BacktestingSystem
from backend.integrated_t1_backtester import IntegratedT1Backtester
from backend.quarterly_backtester import QuarterlyBacktester
from backend.data_loader import DataLoader
from backend.strategies import analyze_triple_cross

# 1. 准备数据
loader = DataLoader()
stock_data = {
    '000001': loader.load_stock_data('000001'),
    '000002': loader.load_stock_data('000002'),
    '600000': loader.load_stock_data('600000')
}

# 2. 策略配置
config = {
    'macd': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
    'kdj': {'period': 27, 'k_smooth': 3, 'd_smooth': 3},
    'rsi': {'period': 14},
    'signal_threshold': 70
}

# 3. 传统回测
print("=== 传统回测 ===")
backtester = BacktestingSystem(initial_capital=100000)
for symbol, df in stock_data.items():
    result = backtester.run_backtest(analyze_triple_cross, df, config)
    print(f"{symbol}: 收益率 {result['performance']['total_return']:.2%}")

# 4. T+1回测
print("\n=== T+1回测 ===")
t1_backtester = IntegratedT1Backtester(initial_capital=100000)
t1_result = t1_backtester.run_t1_backtest(stock_data)
print(f"T+1回测收益率: {t1_result['performance_metrics']['total_return']:.2%}")
print(f"T+1合规率: {t1_result['performance_metrics']['t1_compliance_rate']:.2%}")

# 5. 季度回测
print("\n=== 季度回测 ===")
quarterly_backtester = QuarterlyBacktester()
quarterly_result = quarterly_backtester.run_quarterly_backtest(
    analyze_triple_cross, stock_data, config, [2023, 2024]
)

for quarter, stats in quarterly_result['seasonal_analysis']['seasonal_stats'].items():
    print(f"{quarter}: 平均收益率 {stats['avg_return']:.2%}")

# 6. 生成报告
from backend.backtester import BacktestReportGenerator
report_generator = BacktestReportGenerator()

summary_report = report_generator.generate_backtest_report(result, 'summary')
print(f"\n=== 回测报告 ===")
print(f"风险评估: {summary_report['risk_assessment']}")
for recommendation in summary_report['recommendations']:
    print(f"建议: {recommendation}")
```

回测系统通过多层次、多维度的验证机制，为策略优化和风险控制提供了科学的依据。无论是传统回测还是T+1规则回测，都能准确反映策略在真实市场环境中的表现。