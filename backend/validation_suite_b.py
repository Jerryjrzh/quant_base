#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【独立脚本】策略与回测模块分层验证套件

目的：
1. 解决改造后筛选器无结果的问题。
2. 逐层验证数据流，清晰展示股票在哪个环节被过滤。
3. 调试和验证 confluence_scorer, pattern_recognizer 等核心模块的参数和逻辑。
"""

import argparse
import pandas as pd
from datetime import datetime

# 导入所有需要验证的核心模块
from data_handler import get_full_data_with_indicators
from strategy_manager import strategy_manager
from stock_pool_manager import StockPoolManager
from confluence_scorer import confluence_scorer
from pattern_recognizer import pattern_recognizer
from backtester import get_deep_analysis

class ValidationSuite:
    """分层验证套件，用于诊断筛选流程"""

    def __init__(self, strategy_id: str):
        self.strategy_id = strategy_id
        self.strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
        if not self.strategy_instance:
            raise ValueError(f"策略 '{strategy_id}' 不存在或无法加载")
        
        self.pool_manager = StockPoolManager()
        self.stats = {
            'processed': 0,
            'passed_layer0': 0,
            'passed_layer1': 0,
            'passed_layer2': 0,
            'passed_layer3': 0,
            'passed_layer4': 0,
        }
        # 可配置的阈值，用于诊断
        self.MIN_CONFLUENCE_SCORE = 70.0

    def _print_header(self, text):
        print("\n" + "=" * 80)
        print(f"  {text}")
        print("=" * 80)

    def _print_pass(self, layer, reason=""):
        print(f"  ✅ [PASS] Layer {layer}: {reason}")

    def _print_fail(self, layer, reason=""):
        print(f"  ❌ [FAIL] Layer {layer}: {reason}")

    def _print_info(self, text):
        print(f"  - {text}")
        
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

    def run_validation_for_stock(self, stock_code: str):
        """对单只股票执行分层验证"""
        self.stats['processed'] += 1
        self._print_header(f"开始验证股票: {stock_code} | 策略: {self.strategy_id}")

        # --- 准备数据 ---
        df = get_full_data_with_indicators(stock_code)
        if df is None or len(df) < 50:
            self._print_fail("Data Prep", f"数据不足或加载失败，共 {len(df) if df is not None else 0} 条记录")
            return

        # --- Layer 0: 原始策略信号验证 ---
        self._print_info("Layer 0: 验证原始策略信号...")
        signals = self.strategy_instance.apply_strategy(df)
        if isinstance(signals, tuple):
            signals = signals[0]
        
        actual_signals = signals.loc[signals.apply(lambda x: isinstance(x, str) and x != '')]
        if actual_signals.empty:
            self._print_fail("0 - Raw Signal", "策略未产生任何有效信号")
            return
        
        latest_signal_date = actual_signals.index.max()
        if (df.index.max() - latest_signal_date).days > 5:
            self._print_fail("0 - Raw Signal", f"最新信号在 {latest_signal_date.strftime('%Y-%m-%d')}，已过期")
            return
        
        self.stats['passed_layer0'] += 1
        self._print_pass("0 - Raw Signal", f"在 {latest_signal_date.strftime('%Y-%m-%d')} 发现信号: '{actual_signals.iloc[-1]}'")
        signal_index = df.index.get_loc(latest_signal_date)

        # --- Layer 1: 价格位置快速过滤 ---
        self._print_info("Layer 1: 验证价格位置过滤器 (Price Position Filter)...")
        passed, reason = confluence_scorer.filter_by_price_position(df, signal_index)
        if not passed:
            self._print_fail("1 - Price Filter", reason)
           # return

        self.stats['passed_layer1'] += 1
        self._print_pass("1 - Price Filter", reason)

        # --- Layer 2: 多指标融合评分 ---
        self._print_info("Layer 2: 计算多指标融合评分 (Confluence Score)...")
        confluence_result = confluence_scorer.calculate_confluence_score(df, signal_index)
        self._print_score_breakdown(confluence_result)
        self.stats['passed_layer2'] += 1

        # --- Layer 3: 融合评分阈值验证 ---
        self._print_info(f"Layer 3: 验证融合评分是否 >= {self.MIN_CONFLUENCE_SCORE}...")
        if confluence_result['total_score'] < self.MIN_CONFLUENCE_SCORE:
            self._print_fail("3 - Score Threshold", f"总评分 {confluence_result['total_score']:.2f} 未达到阈值")
           # return
        
        self.stats['passed_layer3'] += 1
        self._print_pass("3 - Score Threshold", f"总评分 {confluence_result['total_score']:.2f} 达到阈值")

        # --- Layer 4: 形态识别验证 ---
        self._print_info("Layer 4: 验证形态识别 (Pattern Recognition)...")
        pattern_result = pattern_recognizer.recognize_pattern(df, signal_index)
        if not pattern_result['has_pattern']:
            self._print_fail("4 - Pattern Recognition", "未识别出明确的技术形态")
            # 注意：即使没有形态，也可能是一个好的信号，所以我们不在此处终止
        else:
            self.stats['passed_layer4'] += 1
            self._print_pass("4 - Pattern Recognition", f"识别到形态: {pattern_result['best_pattern']} (置信度: {pattern_result['best_confidence']:.1%})")

        # --- Final Layer: 深度分析与交易建议 ---
        self._print_info("Final Layer: 生成深度分析和最终交易建议...")
        deep_analysis = get_deep_analysis(stock_code, df)
        advice = deep_analysis.get('trading_advice', {})
        print("  💡 最终交易建议:")
        print(f"     - 操作 (Action): {advice.get('action', 'N/A')}")
        print(f"     - 质量等级 (Grade): {advice.get('quality_grade', 'N/A')}")
        print(f"     - 置信度 (Confidence): {advice.get('confidence', 0):.1%}")
        print(f"     - 分析逻辑 (Reasons):")
        for r in advice.get('analysis_logic', []):
            print(f"       - {r}")

    def run_suite(self, stock_codes: list = None, limit: int = None):
        """运行整个验证套件"""
        if stock_codes:
            target_pool = stock_codes
        else:
            all_stocks = self.pool_manager.get_all_stocks()
            target_pool = [s['stock_code'] for s in all_stocks]
        
        if limit:
            target_pool = target_pool[:limit]

        for stock_code in target_pool:
            try:
                self.run_validation_for_stock(stock_code)
            except Exception as e:
                self._print_header(f"处理股票 {stock_code} 时发生严重错误")
                print(f"  ❌ 错误: {e}")
        
        self._print_summary()

    def _print_summary(self):
        self._print_header("验证套件运行摘要")
        total = self.stats['processed']
        if total == 0:
            print("未处理任何股票。")
            return
            
        p0 = self.stats['passed_layer0']
        p1 = self.stats['passed_layer1']
        p2 = self.stats['passed_layer2'] # 总是等于p1
        p3 = self.stats['passed_layer3']
        p4 = self.stats['passed_layer4']

        print(f"总计处理股票: {total} 只")
        print("-" * 40)
        print(f"通过 Layer 0 (原始信号): {p0} / {total} ({p0/total:.1%})")
        print(f"通过 Layer 1 (价格过滤): {p1} / {p0 if p0 > 0 else 1} ({p1/p0 if p0 > 0 else 0:.1%})")
        print(f"通过 Layer 3 (评分阈值): {p3} / {p1 if p1 > 0 else 1} ({p3/p1 if p1 > 0 else 0:.1%})")
        print(f"通过 Layer 4 (形态识别): {p4} / {p3 if p3 > 0 else 1} ({p4/p3 if p3 > 0 else 0:.1%})")
        print("-" * 40)
        print(f"最终漏斗转化率: {p3/total if total > 0 else 0:.2%}")

def main():
    parser = argparse.ArgumentParser(description="策略与回测模块分层验证套件")
    parser.add_argument('--stock-code', '-c', type=str, help='指定要验证的单个股票代码')
    parser.add_argument('--strategy', '-s', type=str, required=True, help='指定要验证的策略ID')
    parser.add_argument('--limit', '-l', type=int, help='限制处理的股票数量 (从股票池中选取)')
    
    args = parser.parse_args()

    suite = ValidationSuite(strategy_id=args.strategy)
    
    if args.stock_code:
        suite.run_suite(stock_codes=[args.stock_code])
    else:
        suite.run_suite(limit=args.limit)

if __name__ == "__main__":
    main()