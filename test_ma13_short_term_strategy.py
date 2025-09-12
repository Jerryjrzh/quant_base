"""
MA13短线交易策略测试

测试MA13策略的各个组件和功能
包含单元测试和集成测试
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import unittest
from backend.strategies.ma13_short_term_strategy import MA13ShortTermStrategy
from backend.short_term_execution_planner import ShortTermExecutionPlanner
from backend.indicators import TechnicalIndicators

class TestMA13ShortTermStrategy(unittest.TestCase):
    """MA13短线策略测试类"""
    
    def setUp(self):
        """测试前准备"""
        self.strategy = MA13ShortTermStrategy()
        self.planner = ShortTermExecutionPlanner()
        self.indicators = TechnicalIndicators()
        
        # 创建测试数据
        self.df = self._create_test_data()
        self.df = self._add_indicators(self.df)
    
    def _create_test_data(self):
        """创建测试用的股票数据"""
        dates = pd.date_range(start='2025-01-01', end='2025-09-12', freq='D')
        dates = [d for d in dates if d.weekday() < 5]  # 工作日
        
        np.random.seed(123)
        
        data = []
        base_price = 2.20
        
        for i, date in enumerate(dates):
            # 模拟不同阶段的价格走势
            if i < 60:  # 底部震荡
                price = base_price + 0.15 * np.sin(i * 0.1) + np.random.normal(0, 0.02)
                price = max(2.10, min(2.35, price))
            elif i < 80:  # 突破上涨
                progress = (i - 60) / 20
                price = base_price + 0.60 * progress + np.random.normal(0, 0.015)
            elif i < 95:  # 回调
                progress = (i - 80) / 15
                price = 2.80 - 0.15 * progress + np.random.normal(0, 0.01)
            else:  # 当前反弹
                progress = (i - 95) / (len(dates) - 95)
                price = 2.65 + 0.20 * progress + np.random.normal(0, 0.012)
            
            open_price = price * (1 + np.random.normal(0, 0.008))
            high_price = price * (1 + abs(np.random.normal(0, 0.012)))
            low_price = price * (1 - abs(np.random.normal(0, 0.012)))
            volume = np.random.normal(1.5e8, 0.3e8)
            
            data.append({
                'date': date.strftime('%Y-%m-%d'),
                'open': round(open_price, 2),
                'high': round(high_price, 2),
                'low': round(low_price, 2),
                'close': round(price, 2),
                'volume': int(max(volume, 0.5e8))
            })
        
        return pd.DataFrame(data)
    
    def _add_indicators(self, df):
        """添加技术指标"""
        df['ma7'] = self.indicators.calculate_ma(df, 7)
        df['ma13'] = self.indicators.calculate_ma(df, 13)
        df['ma30'] = self.indicators.calculate_ma(df, 30)
        df['ma60'] = self.indicators.calculate_ma(df, 60)
        
        df['dif'], df['dea'] = self.indicators.calculate_macd(df)
        df['k'], df['d'], df['j'] = self.indicators.calculate_kdj(df)
        df['rsi6'] = self.indicators.calculate_rsi(df, 6)
        df['rsi12'] = self.indicators.calculate_rsi(df, 12)
        df['rsi24'] = self.indicators.calculate_rsi(df, 24)
        
        return df
    
    def test_strategy_initialization(self):
        """测试策略初始化"""
        self.assertEqual(self.strategy.name, "MA13强势回调趋势系统")
        self.assertIn('box_duration_min', self.strategy.params)
        self.assertIn('breakout_gain_min', self.strategy.params)
        self.assertIn('pullback_min', self.strategy.params)
    
    def test_stage_1_bottom_stability(self):
        """测试步骤1：底部稳定分析"""
        result = self.strategy._stage_1_bottom_stability(self.df)
        
        self.assertIn('qualified', result)
        if result['qualified']:
            self.assertIn('box_high', result)
            self.assertIn('box_low', result)
            self.assertIn('box_volatility', result)
            self.assertLess(result['box_volatility'], 0.25)  # 波动率应该合理
    
    def test_stage_2_breakout_confirmation(self):
        """测试步骤2：日线爆发确认"""
        result = self.strategy._stage_2_breakout_confirmation(self.df)
        
        self.assertIn('qualified', result)
        if result['qualified']:
            self.assertIn('breakout_gain', result)
            self.assertIn('volume_ratio', result)
            self.assertGreater(result['breakout_gain'], 0)  # 应该有正收益
    
    def test_stage_3_ma13_pullback(self):
        """测试步骤3：MA13回调分析"""
        result = self.strategy._stage_3_ma13_pullback(self.df)
        
        self.assertIn('qualified', result)
        if result['qualified']:
            self.assertIn('pullback_pct', result)
            self.assertIn('current_ma13', result)
            self.assertGreater(result['current_ma13'], 0)  # MA13应该为正
    
    def test_signal_confirmation(self):
        """测试信号确认"""
        result = self.strategy._stage_45_signal_confirmation(self.df)
        
        self.assertIn('oversold_model', result)
        self.assertIn('continuation_model', result)
        self.assertIn('signal_strength', result)
        self.assertIn('entry_timing', result)
        
        # 信号强度应该在合理范围内
        self.assertGreaterEqual(result['signal_strength'], 0)
        self.assertLessEqual(result['signal_strength'], 100)
    
    def test_key_levels_calculation(self):
        """测试关键价位计算"""
        self.strategy._calculate_key_levels(self.df)
        
        levels = self.strategy.key_levels
        
        # 检查所有关键价位都已计算
        required_levels = [
            'support_1_upper', 'support_1_lower',
            'support_2_upper', 'support_2_lower',
            'target_1', 'target_2', 'target_3', 'stop_loss'
        ]
        
        for level in required_levels:
            self.assertIn(level, levels)
            if levels[level] > 0:  # 如果有值，应该是正数
                self.assertGreater(levels[level], 0)
    
    def test_ma_bullish_alignment(self):
        """测试均线多头排列检查"""
        # 创建多头排列的数据
        test_data = pd.Series({
            'ma7': 3.0,
            'ma13': 2.8,
            'ma30': 2.6
        })
        
        result = self.strategy._check_ma_bullish_alignment(test_data)
        self.assertTrue(result)
        
        # 创建空头排列的数据
        test_data_bearish = pd.Series({
            'ma7': 2.6,
            'ma13': 2.8,
            'ma30': 3.0
        })
        
        result_bearish = self.strategy._check_ma_bullish_alignment(test_data_bearish)
        self.assertFalse(result_bearish)
    
    def test_ma_slope_calculation(self):
        """测试均线斜率计算"""
        # 创建上升趋势的MA数据
        test_df = pd.DataFrame({
            'ma13': [2.5, 2.6, 2.7, 2.8, 2.9]
        })
        
        slope = self.strategy._calculate_ma_slope(test_df, 'ma13', 5)
        self.assertGreater(slope, 0)  # 上升趋势斜率应为正
        
        # 创建下降趋势的MA数据
        test_df_down = pd.DataFrame({
            'ma13': [2.9, 2.8, 2.7, 2.6, 2.5]
        })
        
        slope_down = self.strategy._calculate_ma_slope(test_df_down, 'ma13', 5)
        self.assertLess(slope_down, 0)  # 下降趋势斜率应为负
    
    def test_full_strategy_analysis(self):
        """测试完整策略分析"""
        result = self.strategy.analyze_stock(self.df, "TEST001")
        
        # 检查返回结果的基本结构
        self.assertIn('success', result)
        self.assertIn('message', result)
        self.assertIn('strategy', result)
        self.assertIn('timestamp', result)
        
        if result['success']:
            # 检查成功结果的详细结构
            self.assertIn('stage_1', result)
            self.assertIn('stage_2', result)
            self.assertIn('stage_3', result)
            self.assertIn('signals', result)
            self.assertIn('key_levels', result)
            self.assertIn('recommendation', result)
    
    def test_execution_planner_initialization(self):
        """测试执行计划器初始化"""
        self.assertEqual(self.planner.name, "短线实战执行计划器")
        self.assertIn('support_buffer_pct', self.planner.params)
        self.assertIn('target_1_buffer', self.planner.params)
    
    def test_support_levels_calculation(self):
        """测试支撑位计算"""
        # 先运行策略分析
        strategy_result = self.strategy.analyze_stock(self.df, "TEST001")
        
        if strategy_result['success']:
            support_analysis = self.planner._calculate_support_levels(self.df, strategy_result)
            
            self.assertIn('core_support_zone', support_analysis)
            self.assertIn('final_support_zone', support_analysis)
            self.assertIn('current_position', support_analysis)
            self.assertIn('support_strength', support_analysis)
            
            # 检查支撑区间的合理性
            core_zone = support_analysis['core_support_zone']
            self.assertGreater(core_zone['upper'], core_zone['lower'])
    
    def test_target_levels_calculation(self):
        """测试目标位计算"""
        strategy_result = self.strategy.analyze_stock(self.df, "TEST001")
        
        if strategy_result['success']:
            target_analysis = self.planner._calculate_target_levels(self.df, strategy_result)
            
            self.assertIn('target_1', target_analysis)
            self.assertIn('target_2', target_analysis)
            self.assertIn('target_3', target_analysis)
            
            # 检查目标位的递增关系
            target_1_price = target_analysis['target_1']['price']
            target_2_price = target_analysis['target_2']['price']
            target_3_price = target_analysis['target_3']['price']
            
            current_price = self.df.iloc[-1]['close']
            
            self.assertGreater(target_1_price, current_price)
            self.assertGreater(target_2_price, target_1_price)
            self.assertGreater(target_3_price, target_2_price)
    
    def test_time_window_calculation(self):
        """测试时间窗口计算"""
        current_date = self.df.iloc[-1]['date']
        time_window = self.planner._calculate_time_window(self.df, current_date)
        
        self.assertIn('start_date', time_window)
        self.assertIn('min_hold_until', time_window)
        self.assertIn('max_hold_until', time_window)
        self.assertIn('golden_window_end', time_window)
        self.assertIn('expected_trading_days', time_window)
        
        # 检查日期的合理性
        self.assertGreater(time_window['expected_trading_days'], 0)
    
    def test_position_plan_generation(self):
        """测试仓位管理计划生成"""
        strategy_result = self.strategy.analyze_stock(self.df, "TEST001")
        
        if strategy_result['success']:
            position_plan = self.planner._generate_position_plan(strategy_result)
            
            self.assertIn('initial_entry', position_plan)
            self.assertIn('add_position', position_plan)
            self.assertIn('max_position', position_plan)
            self.assertIn('position_stages', position_plan)
            
            # 检查仓位比例的合理性
            initial_pct = position_plan['initial_entry']['position_pct']
            max_pct = position_plan['max_position']['position_pct']
            
            self.assertGreater(initial_pct, 0)
            self.assertLessEqual(initial_pct, max_pct)
            self.assertLessEqual(max_pct, 100)
    
    def test_risk_control_plan(self):
        """测试风险控制计划"""
        strategy_result = self.strategy.analyze_stock(self.df, "TEST001")
        
        if strategy_result['success']:
            support_analysis = self.planner._calculate_support_levels(self.df, strategy_result)
            target_analysis = self.planner._calculate_target_levels(self.df, strategy_result)
            current_price = self.df.iloc[-1]['close']
            
            risk_control = self.planner._generate_risk_control_plan(
                current_price, support_analysis, target_analysis
            )
            
            self.assertIn('stop_loss', risk_control)
            self.assertIn('take_profit_1', risk_control)
            self.assertIn('take_profit_2', risk_control)
            self.assertIn('risk_reward_ratio', risk_control)
            
            # 检查风险收益比的合理性
            self.assertGreater(risk_control['risk_reward_ratio'], 0)
    
    def test_full_execution_plan_generation(self):
        """测试完整执行计划生成"""
        strategy_result = self.strategy.analyze_stock(self.df, "TEST001")
        
        if strategy_result['success']:
            plan_result = self.planner.generate_execution_plan(self.df, strategy_result, "TEST001")
            
            self.assertIn('success', plan_result)
            
            if plan_result['success']:
                # 检查执行计划的完整性
                required_sections = [
                    'support_analysis', 'target_analysis', 'time_window',
                    'position_plan', 'risk_control', 'operation_guide',
                    'execution_summary'
                ]
                
                for section in required_sections:
                    self.assertIn(section, plan_result)
                
                # 检查关键指标
                self.assertIn('strategy_confidence', plan_result)
                self.assertIn('expected_return', plan_result)
                self.assertIn('risk_reward_ratio', plan_result)

def run_performance_test():
    """运行性能测试"""
    print("\n🚀 运行性能测试...")
    
    strategy = MA13ShortTermStrategy()
    planner = ShortTermExecutionPlanner()
    
    # 创建大量测试数据
    dates = pd.date_range(start='2024-01-01', end='2025-09-12', freq='D')
    dates = [d for d in dates if d.weekday() < 5]
    
    np.random.seed(456)
    data = []
    
    for i, date in enumerate(dates):
        price = 2.5 + 0.5 * np.sin(i * 0.01) + np.random.normal(0, 0.02)
        data.append({
            'date': date.strftime('%Y-%m-%d'),
            'open': price * (1 + np.random.normal(0, 0.01)),
            'high': price * (1 + abs(np.random.normal(0, 0.015))),
            'low': price * (1 - abs(np.random.normal(0, 0.015))),
            'close': price,
            'volume': int(np.random.normal(1.5e8, 0.3e8))
        })
    
    df = pd.DataFrame(data)
    
    # 添加技术指标
    indicators = TechnicalIndicators()
    df['ma7'] = indicators.calculate_ma(df, 7)
    df['ma13'] = indicators.calculate_ma(df, 13)
    df['ma30'] = indicators.calculate_ma(df, 30)
    df['ma60'] = indicators.calculate_ma(df, 60)
    df['dif'], df['dea'] = indicators.calculate_macd(df)
    df['k'], df['d'], df['j'] = indicators.calculate_kdj(df)
    df['rsi6'] = indicators.calculate_rsi(df, 6)
    df['rsi12'] = indicators.calculate_rsi(df, 12)
    df['rsi24'] = indicators.calculate_rsi(df, 24)
    
    # 测试策略分析性能
    start_time = datetime.now()
    
    for i in range(10):  # 运行10次
        result = strategy.analyze_stock(df, f"PERF{i:03d}")
        if result['success']:
            plan_result = planner.generate_execution_plan(df, result, f"PERF{i:03d}")
    
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print(f"✅ 性能测试完成:")
    print(f"   数据量: {len(df)}天")
    print(f"   测试次数: 10次")
    print(f"   总耗时: {duration:.2f}秒")
    print(f"   平均耗时: {duration/10:.3f}秒/次")

def main():
    """主测试函数"""
    print("🧪 MA13短线交易策略测试")
    print("=" * 50)
    
    # 运行单元测试
    print("\n📋 运行单元测试...")
    unittest.main(argv=[''], exit=False, verbosity=2)
    
    # 运行性能测试
    run_performance_test()
    
    print(f"\n🎉 所有测试完成!")

if __name__ == "__main__":
    main()