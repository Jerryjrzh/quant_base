#!/usr/bin/env python3
"""
增强版强势股筛选系统测试脚本
测试所有核心功能是否正常工作
"""

import os
import sys
import json
import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

# 添加路径
sys.path.append(os.path.dirname(__file__))
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backend.momentum_strength_analyzer import MomentumStrengthAnalyzer, MomentumConfig
from backend.multi_timeframe_validator import MultiTimeframeValidator, TimeframeConfig
from enhanced_momentum_screener import EnhancedMomentumScreener

class TestMomentumStrengthAnalyzer(unittest.TestCase):
    """测试强势股分析器"""
    
    def setUp(self):
        """设置测试环境"""
        self.config = MomentumConfig(
            ma_periods=[13, 20],
            strength_threshold=0.8,
            lookback_days=30
        )
        self.analyzer = MomentumStrengthAnalyzer(self.config)
        
        # 创建模拟数据
        dates = pd.date_range('2024-01-01', periods=100, freq='D')
        np.random.seed(42)
        
        # 创建上升趋势的强势股数据
        base_price = 10.0
        prices = []
        for i in range(100):
            # 添加上升趋势和随机波动
            trend = i * 0.05
            noise = np.random.normal(0, 0.2)
            price = base_price + trend + noise
            prices.append(max(price, 1.0))  # 确保价格为正
        
        self.mock_data = pd.DataFrame({
            'open': prices,
            'high': [p * 1.02 for p in prices],
            'low': [p * 0.98 for p in prices],
            'close': prices,
            'volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
    
    def test_calculate_ma_strength(self):
        """测试MA强势计算"""
        ma_scores = self.analyzer.calculate_ma_strength(self.mock_data)
        
        self.assertIsInstance(ma_scores, dict)
        self.assertIn(13, ma_scores)
        self.assertIn(20, ma_scores)
        
        # 强势股应该有较高的MA得分
        for period, score in ma_scores.items():
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 1)
    
    def test_calculate_technical_indicators(self):
        """测试技术指标计算"""
        technical = self.analyzer.calculate_technical_indicators(self.mock_data)
        
        required_keys = ['rsi', 'rsi_signal', 'kdj_k', 'kdj_d', 'kdj_j', 
                        'kdj_signal', 'macd', 'macd_signal', 'macd_histogram']
        
        for key in required_keys:
            self.assertIn(key, technical)
        
        # RSI应该在0-100之间
        self.assertGreaterEqual(technical['rsi'], 0)
        self.assertLessEqual(technical['rsi'], 100)
        
        # 信号应该是有效值
        self.assertIn(technical['rsi_signal'], ['超买', '超卖', '正常'])
        self.assertIn(technical['kdj_signal'], ['超买', '超卖', '正常'])
    
    def test_calculate_momentum_indicators(self):
        """测试动量指标计算"""
        momentum = self.analyzer.calculate_momentum_indicators(self.mock_data)
        
        required_keys = ['momentum_5d', 'momentum_10d', 'momentum_20d', 
                        'volume_ratio', 'volume_trend']
        
        for key in required_keys:
            self.assertIn(key, momentum)
        
        # 成交量趋势应该是有效值
        self.assertIn(momentum['volume_trend'], ['放量', '缩量', '正常'])
    
    @patch('backend.momentum_strength_analyzer.MomentumStrengthAnalyzer.load_stock_data')
    def test_analyze_stock_strength(self, mock_load_data):
        """测试单股强势分析"""
        mock_load_data.return_value = self.mock_data
        
        result = self.analyzer.analyze_stock_strength('test_symbol')
        
        self.assertIsNotNone(result)
        self.assertEqual(result.symbol, 'test_symbol')
        self.assertIn(result.strength_rank, ['强势', '中等', '弱势'])
        self.assertIn(result.action_signal, ['买入', '观望', '卖出'])
        self.assertIn(result.risk_level, ['低', '中', '高'])
        
        # 得分应该在合理范围内
        self.assertGreaterEqual(result.final_score, 0)
        self.assertLessEqual(result.final_score, 100)

class TestMultiTimeframeValidator(unittest.TestCase):
    """测试多周期验证器"""
    
    def setUp(self):
        """设置测试环境"""
        self.config = TimeframeConfig(
            daily_period=30,
            weekly_period=10,
            monthly_period=3
        )
        self.validator = MultiTimeframeValidator(self.config)
        
        # 创建模拟数据
        dates = pd.date_range('2024-01-01', periods=200, freq='D')
        np.random.seed(42)
        
        base_price = 15.0
        prices = []
        for i in range(200):
            trend = i * 0.03
            noise = np.random.normal(0, 0.3)
            price = base_price + trend + noise
            prices.append(max(price, 1.0))
        
        self.mock_data = pd.DataFrame({
            'open': prices,
            'high': [p * 1.03 for p in prices],
            'low': [p * 0.97 for p in prices],
            'close': prices,
            'volume': np.random.randint(2000000, 8000000, 200)
        }, index=dates)
    
    def test_convert_to_timeframe(self):
        """测试时间周期转换"""
        # 测试日线（不变）
        daily_data = self.validator.convert_to_timeframe(self.mock_data, 'daily')
        self.assertEqual(len(daily_data), len(self.mock_data))
        
        # 测试周线转换
        weekly_data = self.validator.convert_to_timeframe(self.mock_data, 'weekly')
        self.assertLess(len(weekly_data), len(self.mock_data))
        
        # 测试月线转换
        monthly_data = self.validator.convert_to_timeframe(self.mock_data, 'monthly')
        self.assertLess(len(monthly_data), len(weekly_data))
    
    def test_analyze_trend(self):
        """测试趋势分析"""
        trend_direction, trend_strength, trend_duration = self.validator.analyze_trend(
            self.mock_data, 30
        )
        
        self.assertIn(trend_direction, ['上升', '下降', '震荡'])
        self.assertGreaterEqual(trend_strength, 0)
        self.assertLessEqual(trend_strength, 1)
        self.assertGreaterEqual(trend_duration, 0)
    
    def test_analyze_ma_alignment(self):
        """测试MA排列分析"""
        ma_alignment, price_above_ma, ma_slope = self.validator.analyze_ma_alignment(self.mock_data)
        
        self.assertIsInstance(ma_alignment, bool)
        self.assertIsInstance(price_above_ma, dict)
        self.assertIsInstance(ma_slope, dict)
        
        # 检查价格位置比例
        for period, ratio in price_above_ma.items():
            self.assertGreaterEqual(ratio, 0)
            self.assertLessEqual(ratio, 1)
    
    def test_find_support_resistance(self):
        """测试支撑阻力分析"""
        support, resistance, current_position = self.validator.find_support_resistance(
            self.mock_data, 20
        )
        
        self.assertGreater(resistance, support)
        self.assertGreaterEqual(current_position, 0)
        self.assertLessEqual(current_position, 1)
    
    @patch('backend.multi_timeframe_validator.MultiTimeframeValidator.load_stock_data')
    def test_validate_stock(self, mock_load_data):
        """测试单股多周期验证"""
        mock_load_data.return_value = self.mock_data
        
        result = self.validator.validate_stock('test_symbol')
        
        self.assertIsNotNone(result)
        self.assertEqual(result.symbol, 'test_symbol')
        self.assertIn(result.overall_trend, ['上升', '下降', '震荡'])
        self.assertIn(result.entry_timing, ['立即', '回调', '突破', '观望'])
        self.assertIn(result.risk_level, ['低', '中', '高'])
        self.assertIn(result.holding_period, ['短期', '中期', '长期'])
        
        # 检查强势得分
        self.assertGreaterEqual(result.multi_timeframe_strength, 0)
        self.assertLessEqual(result.multi_timeframe_strength, 100)

class TestEnhancedMomentumScreener(unittest.TestCase):
    """测试增强版筛选器"""
    
    def setUp(self):
        """设置测试环境"""
        self.screener = EnhancedMomentumScreener()
        
        # 创建模拟季度回测结果
        self.mock_quarterly_data = {
            'config': {
                'current_quarter': '2025Q2',
                'quarter_start': '2025-04-01',
                'selection_end': '2025-04-18',
                'backtest_start': '2025-04-21',
                'backtest_end': '2025-06-30'
            },
            'strategy': {
                'core_pool': [
                    {
                        'symbol': 'sh600036',
                        'selection_date': '2025-04-18',
                        'max_gain': 0.15,
                        'weekly_cross_confirmed': True,
                        'selection_price': 12.50
                    },
                    {
                        'symbol': 'sz000858',
                        'selection_date': '2025-04-18',
                        'max_gain': 0.12,
                        'weekly_cross_confirmed': True,
                        'selection_price': 8.30
                    }
                ]
            }
        }
    
    def test_load_quarterly_results_from_dict(self):
        """测试从字典加载季度结果"""
        # 创建临时文件
        temp_file = 'test_quarterly_result.json'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(self.mock_quarterly_data, f)
        
        try:
            stock_list = self.screener.load_quarterly_results(temp_file)
            
            self.assertEqual(len(stock_list), 2)
            self.assertIn('sh600036', stock_list)
            self.assertIn('sz000858', stock_list)
            
        finally:
            # 清理临时文件
            if os.path.exists(temp_file):
                os.remove(temp_file)
    
    def test_generate_final_recommendations(self):
        """测试最终推荐生成"""
        # 创建模拟的分析结果
        from backend.momentum_strength_analyzer import StockStrengthResult
        from backend.multi_timeframe_validator import MultiTimeframeResult, TimeframeAnalysis
        
        # 模拟强势分析结果
        mock_momentum_result = StockStrengthResult(
            symbol='test_symbol',
            ma_strength_scores={13: 0.9, 20: 0.85},
            overall_strength_score=0.87,
            strength_rank='强势',
            rsi_value=65.0,
            rsi_signal='正常',
            kdj_k=70.0,
            kdj_d=65.0,
            kdj_j=75.0,
            kdj_signal='正常',
            macd_value=0.5,
            macd_signal_value=0.3,
            macd_histogram=0.2,
            macd_signal='金叉',
            price_momentum_5d=0.03,
            price_momentum_10d=0.08,
            price_momentum_20d=0.15,
            volume_ratio=1.2,
            volume_trend='放量',
            technical_score=75.0,
            momentum_score=80.0,
            final_score=77.0,
            action_signal='买入',
            confidence_level=0.8,
            risk_level='低'
        )
        
        # 模拟多周期验证结果
        daily_analysis = TimeframeAnalysis(
            timeframe='daily',
            trend_direction='上升',
            trend_strength=0.8,
            trend_duration=15,
            ma_alignment=True,
            price_above_ma={5: 0.9, 10: 0.85, 20: 0.8},
            ma_slope={5: 0.1, 10: 0.08, 20: 0.05},
            support_level=12.0,
            resistance_level=15.0,
            current_position=0.6,
            volume_trend='放量',
            volume_price_sync=True,
            strength_score=75.0
        )
        
        mock_validation_result = MultiTimeframeResult(
            symbol='test_symbol',
            analysis_date='2025-07-25',
            daily_analysis=daily_analysis,
            weekly_analysis=daily_analysis,  # 简化，使用相同数据
            monthly_analysis=daily_analysis,
            overall_trend='上升',
            trend_consistency=0.85,
            multi_timeframe_strength=75.0,
            entry_timing='立即',
            risk_level='低',
            holding_period='中期',
            key_support=12.0,
            key_resistance=15.0,
            stop_loss=11.4,
            take_profit=[15.0, 16.5, 18.0]
        )
        
        # 设置模拟结果
        self.screener.momentum_results = [mock_momentum_result]
        self.screener.validation_results = [mock_validation_result]
        
        # 生成推荐
        recommendations = self.screener.generate_final_recommendations(
            min_momentum_score=60,
            min_timeframe_strength=60,
            max_recommendations=10
        )
        
        self.assertEqual(len(recommendations), 1)
        
        rec = recommendations[0]
        self.assertEqual(rec['symbol'], 'test_symbol')
        self.assertIn(rec['recommendation_level'], ['强烈推荐', '推荐', '关注'])
        self.assertGreater(rec['comprehensive_score'], 0)

class TestSystemIntegration(unittest.TestCase):
    """测试系统集成"""
    
    def test_file_structure(self):
        """测试文件结构完整性"""
        required_files = [
            'enhanced_momentum_screener.py',
            'demo_enhanced_momentum_screening.py',
            'backend/momentum_strength_analyzer.py',
            'backend/multi_timeframe_validator.py',
            'ENHANCED_MOMENTUM_SCREENING_GUIDE.md'
        ]
        
        for file_path in required_files:
            self.assertTrue(os.path.exists(file_path), f"缺少文件: {file_path}")
    
    def test_import_modules(self):
        """测试模块导入"""
        try:
            from backend.momentum_strength_analyzer import MomentumStrengthAnalyzer, MomentumConfig
            from backend.multi_timeframe_validator import MultiTimeframeValidator, TimeframeConfig
            from enhanced_momentum_screener import EnhancedMomentumScreener
            
            # 测试类实例化
            momentum_config = MomentumConfig()
            timeframe_config = TimeframeConfig()
            
            analyzer = MomentumStrengthAnalyzer(momentum_config)
            validator = MultiTimeframeValidator(timeframe_config)
            screener = EnhancedMomentumScreener()
            
            self.assertIsNotNone(analyzer)
            self.assertIsNotNone(validator)
            self.assertIsNotNone(screener)
            
        except ImportError as e:
            self.fail(f"模块导入失败: {e}")

def run_performance_test():
    """运行性能测试"""
    print("\n🚀 性能测试")
    print("=" * 40)
    
    # 测试数据加载性能
    start_time = datetime.now()
    
    # 创建大量模拟数据
    dates = pd.date_range('2023-01-01', periods=500, freq='D')
    np.random.seed(42)
    
    large_data = pd.DataFrame({
        'open': np.random.uniform(10, 50, 500),
        'high': np.random.uniform(10, 55, 500),
        'low': np.random.uniform(5, 45, 500),
        'close': np.random.uniform(10, 50, 500),
        'volume': np.random.randint(1000000, 10000000, 500)
    }, index=dates)
    
    # 测试强势分析性能
    config = MomentumConfig(lookback_days=100)
    analyzer = MomentumStrengthAnalyzer(config)
    
    # 模拟分析
    ma_scores = analyzer.calculate_ma_strength(large_data)
    technical = analyzer.calculate_technical_indicators(large_data)
    momentum = analyzer.calculate_momentum_indicators(large_data)
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"✅ 大数据集分析完成")
    print(f"   数据点数: {len(large_data)}")
    print(f"   处理时间: {duration:.2f} 秒")
    print(f"   MA强势得分: {len(ma_scores)} 个周期")
    print(f"   技术指标: {len(technical)} 个指标")
    print(f"   动量指标: {len(momentum)} 个指标")

def main():
    """主测试函数"""
    print("🧪 增强版强势股筛选系统测试")
    print("=" * 50)
    print(f"📅 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 运行单元测试
    print("\n📋 运行单元测试...")
    
    # 创建测试套件
    test_suite = unittest.TestSuite()
    
    # 添加测试用例
    test_suite.addTest(unittest.makeSuite(TestMomentumStrengthAnalyzer))
    test_suite.addTest(unittest.makeSuite(TestMultiTimeframeValidator))
    test_suite.addTest(unittest.makeSuite(TestEnhancedMomentumScreener))
    test_suite.addTest(unittest.makeSuite(TestSystemIntegration))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # 测试结果统计
    print(f"\n📊 测试结果统计:")
    print(f"   总测试数: {result.testsRun}")
    print(f"   成功数: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"   失败数: {len(result.failures)}")
    print(f"   错误数: {len(result.errors)}")
    
    if result.failures:
        print(f"\n❌ 失败的测试:")
        for test, traceback in result.failures:
            print(f"   • {test}: {traceback.split('AssertionError:')[-1].strip()}")
    
    if result.errors:
        print(f"\n💥 错误的测试:")
        for test, traceback in result.errors:
            print(f"   • {test}: {traceback.split('Exception:')[-1].strip()}")
    
    # 运行性能测试
    try:
        run_performance_test()
    except Exception as e:
        print(f"⚠️ 性能测试失败: {e}")
    
    # 总结
    if result.wasSuccessful():
        print(f"\n✅ 所有测试通过！系统运行正常")
        print(f"🎯 增强版强势股筛选系统已准备就绪")
    else:
        print(f"\n❌ 部分测试失败，请检查系统配置")
    
    return result.wasSuccessful()

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)