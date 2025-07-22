"""
增强分析器 - 集成参数优化和交易建议
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Tuple, Optional
import data_loader
import strategies
import indicators
from parametric_advisor import ParametricTradingAdvisor, TradingParameters
from trading_advisor import TradingAdvisor

class EnhancedTradingAnalyzer:
    """增强交易分析器"""
    
    def __init__(self):
        self.base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        self.cache_dir = "analysis_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def analyze_stock_comprehensive(self, stock_code, use_optimized_params=True):
        """综合分析单只股票"""
        print(f"🔍 开始综合分析股票: {stock_code}")
        
        # 加载数据
        stock_data = self._load_stock_data(stock_code)
        if stock_data is None:
            return {'error': f'无法加载股票数据: {stock_code}'}
        
        df, signals = stock_data['df'], stock_data['signals']
        
        # 基础分析
        basic_analysis = self._perform_basic_analysis(df, signals)
        
        # 参数化分析
        parametric_analysis = self._perform_parametric_analysis(df, signals, stock_code, use_optimized_params)
        
        # 交易建议
        trading_advice = self._generate_trading_advice(df, signals, parametric_analysis.get('best_advisor'))
        
        # 风险评估
        risk_assessment = self._assess_risk_profile(df, signals)
        
        # 综合评分
        overall_score = self._calculate_overall_score(basic_analysis, parametric_analysis, risk_assessment)
        
        return {
            'stock_code': stock_code,
            'analysis_date': datetime.now().isoformat(),
            'basic_analysis': basic_analysis,
            'parametric_analysis': parametric_analysis,
            'trading_advice': trading_advice,
            'risk_assessment': risk_assessment,
            'overall_score': overall_score,
            'recommendation': self._generate_recommendation(overall_score, trading_advice)
        }
    
    def _load_stock_data(self, stock_code):
        """加载股票数据"""
        try:
            market = stock_code[:2]
            file_path = os.path.join(self.base_path, market, 'lday', f'{stock_code}.day')
            
            if not os.path.exists(file_path):
                return None
            
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < 100:
                return None
            
            df.set_index('date', inplace=True)
            
            # 计算技术指标
            macd_values = indicators.calculate_macd(df)
            df['dif'], df['dea'] = macd_values[0], macd_values[1]
            
            # 生成信号
            signals = strategies.apply_macd_zero_axis_strategy(df)
            
            return {'df': df, 'signals': signals}
            
        except Exception as e:
            print(f"加载股票数据失败: {e}")
            return None
    
    def _perform_basic_analysis(self, df, signals):
        """基础分析"""
        try:
            # 价格统计
            current_price = df.iloc[-1]['close']
            price_change_30d = (current_price - df.iloc[-30]['close']) / df.iloc[-30]['close'] if len(df) >= 30 else 0
            price_change_90d = (current_price - df.iloc[-90]['close']) / df.iloc[-90]['close'] if len(df) >= 90 else 0
            
            # 波动率
            returns = df['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)
            
            # 信号统计
            signal_count = len(signals[signals != '']) if signals is not None else 0
            recent_signals = signals[signals != ''].tail(10) if signals is not None and signals.any() else pd.Series()
            
            # 趋势分析
            ma20 = df['close'].rolling(20).mean().iloc[-1] if len(df) >= 20 else current_price
            ma60 = df['close'].rolling(60).mean().iloc[-1] if len(df) >= 60 else current_price
            
            trend_direction = 'up' if current_price > ma20 > ma60 else 'down' if current_price < ma20 < ma60 else 'sideways'
            
            return {
                'current_price': current_price,
                'price_change_30d': price_change_30d,
                'price_change_90d': price_change_90d,
                'volatility': volatility,
                'signal_count': signal_count,
                'recent_signal_count': len(recent_signals),
                'trend_direction': trend_direction,
                'ma20': ma20,
                'ma60': ma60
            }
            
        except Exception as e:
            return {'error': f'基础分析失败: {e}'}
    
    def _perform_parametric_analysis(self, df, signals, stock_code, use_optimized_params):
        """参数化分析"""
        try:
            # 尝试加载优化参数
            optimized_params = None
            if use_optimized_params:
                param_file = f"{self.cache_dir}/optimized_parameters_{stock_code}.json"
                if os.path.exists(param_file):
                    try:
                        with open(param_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        optimized_params = TradingParameters(**data['best_parameters'])
                        print(f"📂 使用已保存的优化参数")
                    except:
                        pass
            
            # 如果没有优化参数，进行快速优化
            if optimized_params is None and signals is not None and signals.any():
                signal_count = len(signals[signals != ''])
                if signal_count >= 3:  # 至少需要3个信号才进行优化
                    print(f"🔧 执行快速参数优化...")
                    advisor = ParametricTradingAdvisor()
                    optimization_result = self._quick_optimize(df, signals)
                    if optimization_result and optimization_result['best_parameters']:
                        optimized_params = optimization_result['best_parameters']
                        # 保存优化结果
                        self._save_optimization_result(stock_code, optimization_result)
            
            # 使用优化参数或默认参数
            if optimized_params:
                advisor = ParametricTradingAdvisor(optimized_params)
                print(f"✅ 使用优化参数")
            else:
                advisor = ParametricTradingAdvisor()
                print(f"📋 使用默认参数")
            
            # 执行回测
            backtest_result = advisor.backtest_parameters(df, signals, 'moderate') if signals is not None else {'error': '无信号数据'}
            
            return {
                'using_optimized_params': optimized_params is not None,
                'parameters': advisor.parameters,
                'backtest_result': backtest_result,
                'best_advisor': advisor
            }
            
        except Exception as e:
            return {'error': f'参数化分析失败: {e}'}
    
    def _quick_optimize(self, df, signals):
        """快速参数优化（减少搜索空间）"""
        try:
            # 简化的参数搜索空间
            param_ranges = {
                'pre_entry_discount': [0.02, 0.03, 0.05],
                'moderate_stop': [0.03, 0.05, 0.08],
                'moderate_profit': [0.10, 0.15, 0.20],
                'max_holding_days': [20, 30]
            }
            
            best_params = None
            best_score = -1
            
            import itertools
            combinations = list(itertools.product(*param_ranges.values()))
            
            for combination in combinations:
                test_params = TradingParameters()
                test_params.pre_entry_discount = combination[0]
                test_params.moderate_stop = combination[1]
                test_params.moderate_profit = combination[2]
                test_params.max_holding_days = combination[3]
                
                test_advisor = ParametricTradingAdvisor(test_params)
                result = test_advisor.backtest_parameters(df, signals, 'moderate')
                
                if 'error' not in result and result['total_trades'] >= 1:
                    # 综合评分：胜率 * 0.6 + 平均收益 * 0.4
                    score = result['win_rate'] * 0.6 + max(0, result['avg_pnl']) * 0.4
                    if score > best_score:
                        best_score = score
                        best_params = test_params
            
            return {
                'best_parameters': best_params,
                'best_score': best_score,
                'optimization_target': 'composite_score'
            }
            
        except Exception as e:
            print(f"快速优化失败: {e}")
            return None
    
    def _save_optimization_result(self, stock_code, result):
        """保存优化结果"""
        try:
            file_path = f"{self.cache_dir}/optimized_parameters_{stock_code}.json"
            save_data = {
                'stock_code': stock_code,
                'optimization_date': datetime.now().isoformat(),
                'best_parameters': result['best_parameters'].__dict__,
                'best_score': result['best_score'],
                'optimization_target': result['optimization_target']
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"保存优化结果失败: {e}")
    
    def _generate_trading_advice(self, df, signals, advisor):
        """生成交易建议"""
        try:
            if signals is None or not signals.any():
                return {'message': '无有效信号，暂无交易建议'}
            
            # 找到最近的信号
            recent_signals = signals[signals != ''].tail(3)
            if recent_signals.empty:
                return {'message': '无最近信号，暂无交易建议'}
            
            latest_signal_date = recent_signals.index[-1]
            latest_signal_idx = df.index.get_loc(latest_signal_date)
            latest_signal_state = recent_signals.iloc[-1]
            
            # 使用参数化顾问生成建议
            if advisor:
                advice = advisor.get_parametric_entry_recommendations(df, latest_signal_idx, latest_signal_state)
            else:
                # 使用默认顾问
                default_advisor = TradingAdvisor()
                advice = default_advisor.get_entry_recommendations(df, latest_signal_idx, latest_signal_state)
            
            return {
                'latest_signal_date': latest_signal_date.strftime('%Y-%m-%d'),
                'latest_signal_state': latest_signal_state,
                'advice': advice
            }
            
        except Exception as e:
            return {'error': f'生成交易建议失败: {e}'}
    
    def _assess_risk_profile(self, df, signals):
        """评估风险概况"""
        try:
            # 价格波动风险
            returns = df['close'].pct_change().dropna()
            volatility = returns.std() * np.sqrt(252)
            max_drawdown = self._calculate_max_drawdown(df['close'])
            
            # 信号质量风险
            signal_count = len(signals[signals != '']) if signals is not None else 0
            signal_density = signal_count / len(df) if len(df) > 0 else 0
            
            # 趋势稳定性
            ma_slopes = []
            for period in [10, 20, 60]:
                if len(df) >= period + 5:
                    ma = df['close'].rolling(period).mean()
                    slope = (ma.iloc[-1] - ma.iloc[-6]) / ma.iloc[-6]
                    ma_slopes.append(abs(slope))
            
            trend_stability = 1 - np.mean(ma_slopes) if ma_slopes else 0.5
            
            # 综合风险评分 (0-1, 越低越安全)
            volatility_risk = min(volatility / 0.5, 1)  # 标准化到0-1
            drawdown_risk = min(abs(max_drawdown) / 0.3, 1)
            signal_risk = 1 - min(signal_density * 10, 1)  # 信号密度越高风险越低
            
            overall_risk = (volatility_risk * 0.4 + drawdown_risk * 0.3 + signal_risk * 0.3)
            
            risk_level = 'low' if overall_risk < 0.3 else 'medium' if overall_risk < 0.7 else 'high'
            
            return {
                'volatility': volatility,
                'max_drawdown': max_drawdown,
                'signal_count': signal_count,
                'signal_density': signal_density,
                'trend_stability': trend_stability,
                'overall_risk_score': overall_risk,
                'risk_level': risk_level
            }
            
        except Exception as e:
            return {'error': f'风险评估失败: {e}'}
    
    def _calculate_max_drawdown(self, prices):
        """计算最大回撤"""
        try:
            peak = prices.expanding().max()
            drawdown = (prices - peak) / peak
            return drawdown.min()
        except:
            return 0
    
    def _calculate_overall_score(self, basic_analysis, parametric_analysis, risk_assessment):
        """计算综合评分"""
        try:
            score = 0
            max_score = 100
            
            # 基础分析得分 (30分)
            if 'error' not in basic_analysis:
                # 趋势得分
                if basic_analysis['trend_direction'] == 'up':
                    score += 15
                elif basic_analysis['trend_direction'] == 'sideways':
                    score += 8
                
                # 信号质量得分
                if basic_analysis['signal_count'] >= 5:
                    score += 10
                elif basic_analysis['signal_count'] >= 2:
                    score += 5
                
                # 近期表现得分
                if basic_analysis['price_change_30d'] > 0:
                    score += 5
            
            # 参数化分析得分 (40分)
            if 'error' not in parametric_analysis:
                backtest = parametric_analysis.get('backtest_result', {})
                if 'error' not in backtest:
                    # 胜率得分
                    win_rate = backtest.get('win_rate', 0)
                    score += min(win_rate * 30, 20)
                    
                    # 收益得分
                    avg_pnl = backtest.get('avg_pnl', 0)
                    if avg_pnl > 0:
                        score += min(avg_pnl * 100, 15)
                    
                    # 交易次数得分
                    if backtest.get('total_trades', 0) >= 3:
                        score += 5
            
            # 风险评估得分 (30分)
            if 'error' not in risk_assessment:
                risk_level = risk_assessment.get('risk_level', 'high')
                if risk_level == 'low':
                    score += 20
                elif risk_level == 'medium':
                    score += 12
                else:
                    score += 5
                
                # 趋势稳定性得分
                stability = risk_assessment.get('trend_stability', 0)
                score += stability * 10
            
            return {
                'total_score': min(score, max_score),
                'max_score': max_score,
                'score_percentage': min(score / max_score, 1.0),
                'grade': self._get_grade(score / max_score)
            }
            
        except Exception as e:
            return {'error': f'评分计算失败: {e}'}
    
    def _get_grade(self, percentage):
        """获取评级"""
        if percentage >= 0.8:
            return 'A'
        elif percentage >= 0.6:
            return 'B'
        elif percentage >= 0.4:
            return 'C'
        elif percentage >= 0.2:
            return 'D'
        else:
            return 'F'
    
    def _generate_recommendation(self, overall_score, trading_advice):
        """生成投资建议"""
        try:
            score_pct = overall_score.get('score_percentage', 0)
            grade = overall_score.get('grade', 'F')
            
            if score_pct >= 0.7:
                action = 'BUY'
                reason = '综合评分优秀，技术指标良好，建议买入'
            elif score_pct >= 0.5:
                action = 'HOLD'
                reason = '综合评分中等，可考虑持有或小仓位买入'
            elif score_pct >= 0.3:
                action = 'WATCH'
                reason = '综合评分偏低，建议观望等待更好机会'
            else:
                action = 'AVOID'
                reason = '综合评分较差，建议避免投资'
            
            return {
                'action': action,
                'grade': grade,
                'confidence': score_pct,
                'reason': reason,
                'risk_warning': '投资有风险，建议结合个人风险承受能力决策'
            }
            
        except Exception as e:
            return {'error': f'生成建议失败: {e}'}
    
    def batch_analyze_stocks(self, stock_codes, use_optimized_params=True):
        """批量分析股票"""
        print(f"🚀 开始批量分析 {len(stock_codes)} 只股票")
        
        results = {}
        
        for i, stock_code in enumerate(stock_codes, 1):
            print(f"\n[{i}/{len(stock_codes)}] 分析 {stock_code}...")
            
            result = self.analyze_stock_comprehensive(stock_code, use_optimized_params)
            results[stock_code] = result
            
            if 'error' not in result:
                score = result['overall_score']['total_score']
                grade = result['overall_score']['grade']
                action = result['recommendation']['action']
                print(f"✅ {stock_code}: 评分 {score:.1f}, 等级 {grade}, 建议 {action}")
            else:
                print(f"❌ {stock_code}: {result['error']}")
        
        # 生成排名
        valid_results = {k: v for k, v in results.items() if 'error' not in v}
        if valid_results:
            sorted_stocks = sorted(
                valid_results.items(),
                key=lambda x: x[1]['overall_score']['total_score'],
                reverse=True
            )
            
            print(f"\n📊 股票排名 (按综合评分):")
            for i, (stock_code, result) in enumerate(sorted_stocks[:10], 1):
                score = result['overall_score']['total_score']
                grade = result['overall_score']['grade']
                action = result['recommendation']['action']
                print(f"  {i:2d}. {stock_code}: {score:5.1f}分 ({grade}级) - {action}")
        
        return results