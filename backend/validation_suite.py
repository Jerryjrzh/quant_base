#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【增强版】策略与回测模块分层验证套件

目的：
1. 解决改造后筛选器无结果的问题。
2. 逐层验证数据流，清晰展示股票在哪个环节被过滤。
3. 调试和验证 confluence_scorer, pattern_recognizer 等核心模块的参数和逻辑。
4. 支持指定历史日期进行回溯验证。
5. 增强调试功能，支持详细的条件和逻辑分析。
6. 支持批量回测和性能分析。
"""

import argparse
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

# 导入所有需要验证的核心模块
from data_handler import get_full_data_with_indicators
from strategy_manager import strategy_manager
from stock_pool_manager import StockPoolManager
from confluence_scorer import confluence_scorer
from pattern_recognizer import pattern_recognizer
from backtester import get_deep_analysis, run_backtest

class ValidationSuite:
    """【增强版】分层验证套件，用于诊断筛选流程"""

    def __init__(self, strategy_id: str, validation_date: str = None, debug_mode: bool = False):
        self.strategy_id = strategy_id
        self.strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
        if not self.strategy_instance:
            raise ValueError(f"策略 '{self.strategy_id}' 不存在或无法加载")
        
        self.validation_date = pd.to_datetime(validation_date) if validation_date else None
        self.debug_mode = debug_mode
        
        self.pool_manager = StockPoolManager()
        self.stats = {
            'processed': 0,
            'passed_layer0': 0,
            'passed_layer1': 0,
            'passed_layer2': 0,
            'passed_layer3': 0,
            'passed_layer4': 0,
            'backtest_completed': 0,
            'errors': 0
        }
        
        # 可配置的阈值
        self.MIN_CONFLUENCE_SCORE = confluence_scorer.scoring.get('min_confluence_score', 70.0)
        
        # 调试信息存储
        self.debug_results = []
        self.detailed_logs = []
        
        # 性能统计
        self.performance_stats = {
            'total_time': 0,
            'avg_time_per_stock': 0,
            'layer_times': {}
        }

    def _print_header(self, text):
        print("\n" + "=" * 80)
        print(f"  {text}")
        print("=" * 80)

    def _print_pass(self, layer, reason=""):
        print(f"  ✅ [PASS] Layer {layer}: {reason}")
        if self.debug_mode:
            self._log_debug(f"PASS Layer {layer}: {reason}")

    def _print_fail(self, layer, reason=""):
        print(f"  ❌ [FAIL] Layer {layer}: {reason}")
        if self.debug_mode:
            self._log_debug(f"FAIL Layer {layer}: {reason}")

    def _print_info(self, text):
        print(f"  - {text}")
        if self.debug_mode:
            self._log_debug(f"INFO: {text}")
    
    def _print_warning(self, text):
        print(f"  ⚠️ [WARNING] {text}")
        if self.debug_mode:
            self._log_debug(f"WARNING: {text}")
    
    def _log_debug(self, message):
        """记录调试信息"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.detailed_logs.append(f"[{timestamp}] {message}")
        
    def _print_score_breakdown(self, result):
        print("  📊 Confluence Score Breakdown:")
        print(f"     - 总评分 (Total Score): {result['total_score']:.2f}")
        print(f"     - 置信度 (Confidence): {result['confidence']:.2%}")
        breakdown = result.get('breakdown', {})
        print(f"     - 价格位置评分: {breakdown.get('price_position', 0):.2f} / {confluence_scorer.weights['price_position']}")
        print(f"     - MACD状态评分: {breakdown.get('macd_state', 0):.2f} / {confluence_scorer.weights['macd_state']}")
        print(f"     - KDJ状态评分: {breakdown.get('kdj_state', 0):.2f} / {confluence_scorer.weights['kdj_state']}")
        print(f"     - RSI状态评分: {breakdown.get('rsi_state', 0):.2f} / {confluence_scorer.weights['rsi_state']}")
        print(f"     - 状态历史加分: {breakdown.get('bonus_score', 0):.2f}")
        
        # 调试模式下显示更详细的信息
        if self.debug_mode:
            stateful_conditions = result.get('stateful_conditions', {})
            print(f"     - MACD整理期: {'是' if stateful_conditions.get('macd_consolidation') else '否'}")
            print(f"     - KDJ超卖期: {'是' if stateful_conditions.get('kdj_oversold_period') else '否'}")
    
    def _analyze_technical_indicators(self, df: pd.DataFrame, index: int) -> Dict:
        """【新增】详细分析技术指标状态"""
        try:
            current_data = df.iloc[index]
            prev_data = df.iloc[index-1] if index > 0 else current_data
            
            analysis = {
                'price_analysis': {},
                'macd_analysis': {},
                'kdj_analysis': {},
                'rsi_analysis': {},
                'volume_analysis': {}
            }
            
            # 价格分析
            analysis['price_analysis'] = {
                'current_price': float(current_data['close']),
                'price_change': float((current_data['close'] - prev_data['close']) / prev_data['close'] * 100),
                'volume_ratio': float(current_data.get('volume', 0) / df['volume'].rolling(20).mean().iloc[index]) if 'volume' in df.columns else 0,
                'position_in_range': self._calculate_price_position(df, index)
            }
            
            # MACD分析
            if all(col in df.columns for col in ['macd', 'diff', 'dea']):
                analysis['macd_analysis'] = {
                    'macd_value': float(current_data.get('macd', 0)),
                    'diff_value': float(current_data.get('diff', 0)),
                    'dea_value': float(current_data.get('dea', 0)),
                    'is_golden_cross': current_data.get('diff', 0) > current_data.get('dea', 0),
                    'histogram_trend': 'up' if current_data.get('macd', 0) > prev_data.get('macd', 0) else 'down',
                    'near_zero_axis': abs(current_data.get('macd', 0)) < 0.1
                }
            
            # KDJ分析
            if all(col in df.columns for col in ['k', 'd', 'j']):
                analysis['kdj_analysis'] = {
                    'k_value': float(current_data.get('k', 50)),
                    'd_value': float(current_data.get('d', 50)),
                    'j_value': float(current_data.get('j', 50)),
                    'k_trend': 'up' if current_data.get('k', 50) > prev_data.get('k', 50) else 'down',
                    'is_oversold': current_data.get('k', 50) < 20,
                    'is_golden_cross': current_data.get('k', 50) > current_data.get('d', 50)
                }
            
            # RSI分析
            if 'rsi6' in df.columns:
                analysis['rsi_analysis'] = {
                    'rsi_value': float(current_data.get('rsi6', 50)),
                    'rsi_trend': 'up' if current_data.get('rsi6', 50) > prev_data.get('rsi6', 50) else 'down',
                    'is_oversold': current_data.get('rsi6', 50) < 30,
                    'is_overbought': current_data.get('rsi6', 50) > 70
                }
            
            return analysis
            
        except Exception as e:
            self._log_debug(f"技术指标分析失败: {e}")
            return {}
    
    def _calculate_price_position(self, df: pd.DataFrame, index: int) -> Dict:
        """计算价格在不同时间窗口中的位置"""
        try:
            current_price = df.iloc[index]['close']
            positions = {}
            
            for window in [20, 60, 252]:  # 20日、60日、252日
                window_size = min(window, index + 1)
                if window_size < 10:
                    continue
                    
                start_pos = max(0, index + 1 - window_size)
                window_data = df.iloc[start_pos:index + 1]
                
                min_price = window_data['low'].min()
                max_price = window_data['high'].max()
                
                if max_price > min_price:
                    position_pct = (current_price - min_price) / (max_price - min_price)
                    positions[f'{window}d'] = {
                        'position_pct': float(position_pct),
                        'min_price': float(min_price),
                        'max_price': float(max_price)
                    }
            
            return positions
            
        except Exception as e:
            self._log_debug(f"价格位置计算失败: {e}")
            return {}

    def run_validation_for_stock(self, stock_code: str, enable_backtest: bool = True):
        """【增强版】对单只股票执行分层验证"""
        start_time = datetime.now()
        self.stats['processed'] += 1
        
        # 初始化调试结果记录
        debug_result = {
            'stock_code': stock_code,
            'strategy_id': self.strategy_id,
            'validation_date': self.validation_date.strftime('%Y-%m-%d') if self.validation_date else 'latest',
            'layers': {},
            'technical_analysis': {},
            'backtest_results': {},
            'final_advice': {},
            'processing_time': 0
        }
        
        self._print_header(f"开始验证股票: {stock_code} | 策略: {self.strategy_id}")

        try:
            # 数据加载和预处理
            df = get_full_data_with_indicators(stock_code)
            if df is None or len(df) < 50:
                error_msg = f"数据不足或加载失败，共 {len(df) if df is not None else 0} 条记录"
                self._print_fail("Data Prep", error_msg)
                debug_result['layers']['data_prep'] = {'passed': False, 'reason': error_msg}
                self.stats['errors'] += 1
                return debug_result

            run_date = self.validation_date or df.index.max()
            df_context = df.loc[:run_date]
            
            if self.validation_date:
                self._print_info(f"历史验证模式: 数据已截断至 {df_context.index.max().strftime('%Y-%m-%d')}")
            else:
                self._print_info(f"实时验证模式: 使用最新数据 {df_context.index.max().strftime('%Y-%m-%d')}")

            # Layer 0: 原始策略信号验证
            self._print_info("Layer 0: 验证原始策略信号...")
            layer0_start = datetime.now()
            
            signals_result = self.strategy_instance.apply_strategy(df_context)
            signals = signals_result[0] if isinstance(signals_result, tuple) else signals_result

            if signals is None:
                error_msg = "策略未返回任何信号 (returned None)"
                self._print_fail("0 - Raw Signal", error_msg)
                debug_result['layers']['layer0'] = {'passed': False, 'reason': error_msg}
                self.stats['errors'] += 1
                return debug_result

            # 查找有效信号
            actual_signals = signals.loc[signals.apply(lambda x: isinstance(x, str) and x != '')]
            historical_signals = actual_signals[actual_signals.index <= df_context.index.max()]
            
            if historical_signals.empty:
                error_msg = f"在 {df_context.index.max().strftime('%Y-%m-%d')} 或之前未发现任何有效信号"
                self._print_fail("0 - Raw Signal", error_msg)
                debug_result['layers']['layer0'] = {'passed': False, 'reason': error_msg}
                return debug_result
            
            latest_signal_date = historical_signals.index.max()
            signal_value = historical_signals.loc[latest_signal_date]
            
            # 检查信号时效性
            days_since_signal = (df_context.index.max() - latest_signal_date).days
            if days_since_signal > 5:
                warning_msg = f"最新信号在 {latest_signal_date.strftime('%Y-%m-%d')}，距离验证日期已有{days_since_signal}天"
                self._print_warning(warning_msg)
            
            self.stats['passed_layer0'] += 1
            self._print_pass("0 - Raw Signal", f"在 {latest_signal_date.strftime('%Y-%m-%d')} 发现有效信号: '{signal_value}'")
            
            signal_index = df_context.index.get_loc(latest_signal_date)
            debug_result['layers']['layer0'] = {
                'passed': True,
                'signal_date': latest_signal_date.strftime('%Y-%m-%d'),
                'signal_value': signal_value,
                'days_since_signal': days_since_signal,
                'processing_time': (datetime.now() - layer0_start).total_seconds()
            }

            # 技术指标详细分析
            if self.debug_mode:
                self._print_info("执行技术指标详细分析...")
                debug_result['technical_analysis'] = self._analyze_technical_indicators(df_context, signal_index)

            # Layer 1: 价格位置过滤器
            self._print_info("Layer 1: 验证价格位置过滤器 (Price Position Filter)...")
            layer1_start = datetime.now()
            
            passed, reason = confluence_scorer.filter_by_price_position(df_context, signal_index)
            
            if not passed:
                self._print_fail("1 - Price Filter", reason)
                debug_result['layers']['layer1'] = {'passed': False, 'reason': reason}
            else:
                self.stats['passed_layer1'] += 1
                self._print_pass("1 - Price Filter", reason)
                debug_result['layers']['layer1'] = {'passed': True, 'reason': reason}
            
            debug_result['layers']['layer1']['processing_time'] = (datetime.now() - layer1_start).total_seconds()

            # Layer 2: 多指标融合评分
            self._print_info("Layer 2: 计算多指标融合评分 (Confluence Score)...")
            layer2_start = datetime.now()
            
            confluence_result = confluence_scorer.calculate_confluence_score(df_context, signal_index)
            self._print_score_breakdown(confluence_result)
            
            if passed:
                self.stats['passed_layer2'] += 1
            
            debug_result['layers']['layer2'] = {
                'passed': passed,
                'confluence_result': confluence_result,
                'processing_time': (datetime.now() - layer2_start).total_seconds()
            }

            # Layer 3: 评分阈值验证
            self._print_info(f"Layer 3: 验证融合评分是否 >= {self.MIN_CONFLUENCE_SCORE}...")
            layer3_passed = confluence_result['total_score'] >= self.MIN_CONFLUENCE_SCORE
            
            if not layer3_passed:
                self._print_fail("3 - Score Threshold", f"总评分 {confluence_result['total_score']:.2f} 未达到阈值 {self.MIN_CONFLUENCE_SCORE}")
            else:
                if passed:
                    self.stats['passed_layer3'] += 1
                self._print_pass("3 - Score Threshold", f"总评分 {confluence_result['total_score']:.2f} 达到阈值")
            
            debug_result['layers']['layer3'] = {
                'passed': layer3_passed and passed,
                'score': confluence_result['total_score'],
                'threshold': self.MIN_CONFLUENCE_SCORE
            }

            # Layer 4: 形态识别
            self._print_info("Layer 4: 验证形态识别 (Pattern Recognition)...")
            layer4_start = datetime.now()
            
            pattern_result = pattern_recognizer.recognize_pattern(df_context, signal_index)
            pattern_passed = pattern_result['has_pattern']
            
            if not pattern_passed:
                self._print_fail("4 - Pattern Recognition", "未识别出明确的技术形态")
            else:
                if layer3_passed and passed:
                    self.stats['passed_layer4'] += 1
                self._print_pass("4 - Pattern Recognition", f"识别到形态: {pattern_result['best_pattern']} (置信度: {pattern_result['best_confidence']:.1%})")
            
            debug_result['layers']['layer4'] = {
                'passed': pattern_passed,
                'pattern_result': pattern_result,
                'processing_time': (datetime.now() - layer4_start).total_seconds()
            }

            # 回测分析（如果启用）
            if enable_backtest and layer3_passed and passed:
                self._print_info("执行回测分析...")
                backtest_start = datetime.now()
                
                try:
                    backtest_results = run_backtest(df_context, signals)
                    debug_result['backtest_results'] = backtest_results
                    self.stats['backtest_completed'] += 1
                    
                    if backtest_results.get('total_signals', 0) > 0:
                        self._print_info(f"回测完成: 总信号{backtest_results['total_signals']}个, 胜率{backtest_results.get('win_rate', 'N/A')}")
                    
                    debug_result['backtest_results']['processing_time'] = (datetime.now() - backtest_start).total_seconds()
                    
                except Exception as e:
                    self._print_warning(f"回测执行失败: {e}")
                    debug_result['backtest_results'] = {'error': str(e)}

            # 最终交易建议
            self._print_info("Final Layer: 生成深度分析和最终交易建议...")
            final_start = datetime.now()
            
            try:
                deep_analysis = get_deep_analysis(stock_code, df_context)
                advice = deep_analysis.get('trading_advice', {})
                
                print("  💡 最终交易建议:")
                print(f"     - 操作 (Action): {advice.get('action', 'N/A')}")
                print(f"     - 质量等级 (Grade): {advice.get('quality_grade', 'N/A')}")
                print(f"     - 置信度 (Confidence): {advice.get('confidence', 0):.1%}")
                print(f"     - 分析逻辑 (Reasons):")
                for r in advice.get('analysis_logic', []):
                    print(f"       - {r}")
                
                debug_result['final_advice'] = {
                    'advice': advice,
                    'deep_analysis': deep_analysis,
                    'processing_time': (datetime.now() - final_start).total_seconds()
                }
                
            except Exception as e:
                self._print_warning(f"生成最终建议失败: {e}")
                debug_result['final_advice'] = {'error': str(e)}

        except Exception as e:
            self._print_fail("Processing Error", f"处理股票 {stock_code} 时发生错误: {e}")
            debug_result['error'] = str(e)
            self.stats['errors'] += 1

        # 记录总处理时间
        total_time = (datetime.now() - start_time).total_seconds()
        debug_result['processing_time'] = total_time
        
        if self.debug_mode:
            self.debug_results.append(debug_result)
        
        return debug_result

    def run_suite(self, stock_codes: list = None, limit: int = None, enable_backtest: bool = True, 
                  export_results: bool = False):
        """【增强版】运行整个验证套件"""
        suite_start_time = datetime.now()
        
        target_pool = stock_codes or [s['stock_code'] for s in self.pool_manager.get_all_stocks()]
        if limit:
            target_pool = target_pool[:limit]

        self._print_header(f"开始批量验证 - 目标股票数: {len(target_pool)}")
        
        successful_results = []
        failed_results = []

        for i, stock_code in enumerate(target_pool, 1):
            try:
                print(f"\n[{i}/{len(target_pool)}] 处理股票: {stock_code}")
                result = self.run_validation_for_stock(stock_code, enable_backtest)
                
                if result.get('error'):
                    failed_results.append(result)
                else:
                    successful_results.append(result)
                    
            except Exception as e:
                self._print_header(f"处理股票 {stock_code} 时发生严重错误")
                print(f"  ❌ 错误: {e}")
                failed_results.append({
                    'stock_code': stock_code,
                    'error': str(e),
                    'processing_time': 0
                })
                self.stats['errors'] += 1
        
        # 计算性能统计
        total_time = (datetime.now() - suite_start_time).total_seconds()
        self.performance_stats['total_time'] = total_time
        self.performance_stats['avg_time_per_stock'] = total_time / len(target_pool) if target_pool else 0
        
        # 打印摘要
        self._print_summary()
        
        # 导出结果（如果启用）
        if export_results:
            self._export_results(successful_results, failed_results)
        
        return {
            'successful_results': successful_results,
            'failed_results': failed_results,
            'performance_stats': self.performance_stats
        }
    
    def run_historical_backtest(self, stock_codes: list, start_date: str, end_date: str, 
                               step_days: int = 7) -> Dict:
        """【新增】历史回测功能 - 在指定时间范围内按步长进行回测"""
        self._print_header(f"历史回测模式: {start_date} 到 {end_date}, 步长 {step_days} 天")
        
        start_dt = pd.to_datetime(start_date)
        end_dt = pd.to_datetime(end_date)
        
        backtest_results = []
        current_date = start_dt
        
        while current_date <= end_dt:
            self._print_info(f"回测日期: {current_date.strftime('%Y-%m-%d')}")
            
            # 临时设置验证日期
            original_date = self.validation_date
            self.validation_date = current_date
            
            date_results = []
            for stock_code in stock_codes:
                try:
                    result = self.run_validation_for_stock(stock_code, enable_backtest=True)
                    result['backtest_date'] = current_date.strftime('%Y-%m-%d')
                    date_results.append(result)
                except Exception as e:
                    self._log_debug(f"回测 {stock_code} 在 {current_date} 失败: {e}")
            
            backtest_results.extend(date_results)
            current_date += timedelta(days=step_days)
            
            # 恢复原始验证日期
            self.validation_date = original_date
        
        # 分析历史回测结果
        analysis = self._analyze_historical_backtest(backtest_results)
        
        return {
            'backtest_results': backtest_results,
            'analysis': analysis,
            'parameters': {
                'start_date': start_date,
                'end_date': end_date,
                'step_days': step_days,
                'stock_count': len(stock_codes)
            }
        }
    
    def _analyze_historical_backtest(self, results: List[Dict]) -> Dict:
        """分析历史回测结果"""
        if not results:
            return {'error': '无回测结果'}
        
        # 按日期分组
        by_date = {}
        for result in results:
            date = result.get('backtest_date', 'unknown')
            if date not in by_date:
                by_date[date] = []
            by_date[date].append(result)
        
        # 统计分析
        analysis = {
            'total_tests': len(results),
            'unique_dates': len(by_date),
            'success_rate_by_layer': {},
            'avg_confluence_scores': [],
            'pattern_recognition_rate': 0,
            'backtest_performance': {}
        }
        
        # 计算各层通过率
        for layer in ['layer0', 'layer1', 'layer2', 'layer3', 'layer4']:
            passed = sum(1 for r in results if r.get('layers', {}).get(layer, {}).get('passed', False))
            analysis['success_rate_by_layer'][layer] = passed / len(results) if results else 0
        
        # 计算平均融合评分
        scores = [r.get('layers', {}).get('layer2', {}).get('confluence_result', {}).get('total_score', 0) 
                 for r in results]
        analysis['avg_confluence_score'] = np.mean([s for s in scores if s > 0]) if scores else 0
        
        # 形态识别率
        pattern_detected = sum(1 for r in results 
                             if r.get('layers', {}).get('layer4', {}).get('passed', False))
        analysis['pattern_recognition_rate'] = pattern_detected / len(results) if results else 0
        
        return analysis

    def _print_summary(self):
        """【增强版】打印验证套件运行摘要"""
        self._print_header("验证套件运行摘要")
        total = self.stats['processed']
        if total == 0:
            print("未处理任何股票。")
            return
            
        p0 = self.stats['passed_layer0']
        p1 = self.stats['passed_layer1'] 
        p2 = self.stats['passed_layer2']
        p3 = self.stats['passed_layer3']
        p4 = self.stats['passed_layer4']
        backtest_completed = self.stats['backtest_completed']
        errors = self.stats['errors']

        print(f"📊 处理统计:")
        print(f"   总计处理股票: {total} 只")
        print(f"   处理成功: {total - errors} 只")
        print(f"   处理失败: {errors} 只")
        print(f"   完成回测: {backtest_completed} 只")
        
        print("\n📈 分层过滤统计:")
        print("-" * 50)
        print(f"通过 Layer 0 (原始信号): {p0:>3} / {total:>3} ({p0/total:.1%})")
        if p0 > 0:
            print(f"通过 Layer 1 (价格过滤): {p1:>3} / {p0:>3} ({p1/p0:.1%})")
        if p1 > 0:
            print(f"通过 Layer 2 (融合评分): {p2:>3} / {p1:>3} ({p2/p1:.1%})")
        if p2 > 0:
            print(f"通过 Layer 3 (评分阈值): {p3:>3} / {p2:>3} ({p3/p2:.1%})")
        if p3 > 0:
            print(f"通过 Layer 4 (形态识别): {p4:>3} / {p3:>3} ({p4/p3:.1%})")
        
        print("-" * 50)
        print(f"最终漏斗转化率: {p4/total if total > 0 else 0:.2%}")
        
        # 性能统计
        if self.performance_stats['total_time'] > 0:
            print(f"\n⏱️ 性能统计:")
            print(f"   总处理时间: {self.performance_stats['total_time']:.2f} 秒")
            print(f"   平均每股处理时间: {self.performance_stats['avg_time_per_stock']:.2f} 秒")
        
        # 调试模式下的额外信息
        if self.debug_mode and self.debug_results:
            print(f"\n🔍 调试信息:")
            print(f"   详细日志条数: {len(self.detailed_logs)}")
            print(f"   调试结果记录: {len(self.debug_results)} 条")
    
    def _export_results(self, successful_results: List[Dict], failed_results: List[Dict]):
        """导出验证结果到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 导出成功结果
        if successful_results:
            success_file = f"validation_results_success_{timestamp}.json"
            with open(success_file, 'w', encoding='utf-8') as f:
                json.dump(successful_results, f, ensure_ascii=False, indent=2, default=str)
            print(f"✅ 成功结果已导出: {success_file}")
        
        # 导出失败结果
        if failed_results:
            failed_file = f"validation_results_failed_{timestamp}.json"
            with open(failed_file, 'w', encoding='utf-8') as f:
                json.dump(failed_results, f, ensure_ascii=False, indent=2, default=str)
            print(f"❌ 失败结果已导出: {failed_file}")
        
        # 导出统计摘要
        summary = {
            'timestamp': timestamp,
            'strategy_id': self.strategy_id,
            'validation_date': self.validation_date.strftime('%Y-%m-%d') if self.validation_date else 'latest',
            'stats': self.stats,
            'performance_stats': self.performance_stats,
            'successful_count': len(successful_results),
            'failed_count': len(failed_results)
        }
        
        summary_file = f"validation_summary_{timestamp}.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2, default=str)
        print(f"📋 验证摘要已导出: {summary_file}")
        
        # 导出调试日志（如果启用调试模式）
        if self.debug_mode and self.detailed_logs:
            log_file = f"validation_debug_log_{timestamp}.txt"
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write(f"验证套件调试日志\n")
                f.write(f"策略: {self.strategy_id}\n")
                f.write(f"验证日期: {self.validation_date or 'latest'}\n")
                f.write(f"生成时间: {datetime.now()}\n")
                f.write("=" * 80 + "\n\n")
                
                for log_entry in self.detailed_logs:
                    f.write(log_entry + "\n")
            
            print(f"🔍 调试日志已导出: {log_file}")
    
    def generate_performance_report(self) -> Dict:
        """生成性能分析报告"""
        if not self.debug_results:
            return {'error': '无调试数据可分析'}
        
        report = {
            'overview': {
                'total_stocks': len(self.debug_results),
                'avg_processing_time': np.mean([r['processing_time'] for r in self.debug_results]),
                'total_processing_time': sum(r['processing_time'] for r in self.debug_results)
            },
            'layer_performance': {},
            'bottlenecks': [],
            'recommendations': []
        }
        
        # 分析各层处理时间
        for layer in ['layer0', 'layer1', 'layer2', 'layer4']:
            times = []
            for result in self.debug_results:
                layer_data = result.get('layers', {}).get(layer, {})
                if 'processing_time' in layer_data:
                    times.append(layer_data['processing_time'])
            
            if times:
                report['layer_performance'][layer] = {
                    'avg_time': np.mean(times),
                    'max_time': max(times),
                    'min_time': min(times),
                    'std_time': np.std(times)
                }
        
        # 识别瓶颈
        if report['layer_performance']:
            slowest_layer = max(report['layer_performance'].items(), 
                              key=lambda x: x[1]['avg_time'])
            report['bottlenecks'].append(f"最慢的层: {slowest_layer[0]} (平均 {slowest_layer[1]['avg_time']:.3f}s)")
        
        # 生成建议
        avg_time = report['overview']['avg_processing_time']
        if avg_time > 5:
            report['recommendations'].append("处理时间较长，建议优化数据加载和指标计算")
        if report['overview']['total_stocks'] > 100:
            report['recommendations'].append("大批量处理建议使用多进程并行处理")
        
        return report

def main():
    parser = argparse.ArgumentParser(description="【增强版】策略与回测模块分层验证套件")
    parser.add_argument('--stock-code', '-c', type=str, help='指定要验证的单个股票代码')
    parser.add_argument('--stock-codes', type=str, nargs='+', help='指定多个股票代码')
    parser.add_argument('--strategy', '-s', type=str, required=True, help='指定要验证的策略ID')
    parser.add_argument('--limit', '-l', type=int, help='限制处理的股票数量 (从股票池中选取)')
    parser.add_argument('--date', '-d', type=str, help='指定一个历史日期进行验证 (格式: YYYY-MM-DD)')
    
    # 新增参数
    parser.add_argument('--debug', action='store_true', help='启用调试模式，输出详细信息')
    parser.add_argument('--no-backtest', action='store_true', help='禁用回测功能')
    parser.add_argument('--export', action='store_true', help='导出验证结果到文件')
    parser.add_argument('--performance-report', action='store_true', help='生成性能分析报告')
    
    # 历史回测参数
    parser.add_argument('--historical-backtest', action='store_true', help='启用历史回测模式')
    parser.add_argument('--start-date', type=str, help='历史回测开始日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--end-date', type=str, help='历史回测结束日期 (格式: YYYY-MM-DD)')
    parser.add_argument('--step-days', type=int, default=7, help='历史回测步长天数 (默认: 7)')
    
    args = parser.parse_args()

    # 参数验证
    if args.historical_backtest:
        if not args.start_date or not args.end_date:
            print("❌ 历史回测模式需要指定 --start-date 和 --end-date")
            sys.exit(1)
        if not args.stock_code and not args.stock_codes:
            print("❌ 历史回测模式需要指定股票代码")
            sys.exit(1)

    # 创建验证套件实例
    suite = ValidationSuite(
        strategy_id=args.strategy, 
        validation_date=args.date,
        debug_mode=args.debug
    )
    
    try:
        if args.historical_backtest:
            # 历史回测模式
            stock_codes = []
            if args.stock_code:
                stock_codes = [args.stock_code]
            elif args.stock_codes:
                stock_codes = args.stock_codes
            
            results = suite.run_historical_backtest(
                stock_codes=stock_codes,
                start_date=args.start_date,
                end_date=args.end_date,
                step_days=args.step_days
            )
            
            print(f"\n📊 历史回测完成:")
            print(f"   测试总数: {results['analysis']['total_tests']}")
            print(f"   测试日期数: {results['analysis']['unique_dates']}")
            print(f"   平均融合评分: {results['analysis']['avg_confluence_score']:.2f}")
            
            if args.export:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"historical_backtest_{timestamp}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(results, f, ensure_ascii=False, indent=2, default=str)
                print(f"📁 历史回测结果已导出: {filename}")
        
        else:
            # 常规验证模式
            stock_codes = None
            if args.stock_code:
                stock_codes = [args.stock_code]
            elif args.stock_codes:
                stock_codes = args.stock_codes
            
            results = suite.run_suite(
                stock_codes=stock_codes,
                limit=args.limit,
                enable_backtest=not args.no_backtest,
                export_results=args.export
            )
            
            # 生成性能报告
            if args.performance_report and args.debug:
                print("\n" + "=" * 80)
                print("📈 性能分析报告")
                print("=" * 80)
                
                report = suite.generate_performance_report()
                if 'error' not in report:
                    print(f"总处理股票数: {report['overview']['total_stocks']}")
                    print(f"平均处理时间: {report['overview']['avg_processing_time']:.3f}s")
                    print(f"总处理时间: {report['overview']['total_processing_time']:.2f}s")
                    
                    if report['bottlenecks']:
                        print("\n瓶颈分析:")
                        for bottleneck in report['bottlenecks']:
                            print(f"  - {bottleneck}")
                    
                    if report['recommendations']:
                        print("\n优化建议:")
                        for rec in report['recommendations']:
                            print(f"  - {rec}")
                else:
                    print(f"无法生成性能报告: {report['error']}")
    
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断执行")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 执行过程中发生错误: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()