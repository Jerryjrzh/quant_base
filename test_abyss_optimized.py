#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深渊筑底优化策略测试脚本
测试策略的各个阶段识别能力和信号生成准确性
"""

import sys
import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import json

# 添加backend路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from screener_abyss_optimized import AbyssBottomingOptimized
except ImportError:
    print("无法导入优化策略模块，请检查路径")
    sys.exit(1)


class AbyssStrategyTester:
    """深渊筑底策略测试器"""
    
    def __init__(self):
        self.strategy = AbyssBottomingOptimized()
        self.test_results = []
    
    def create_ideal_test_data(self, scenario_name="ideal"):
        """
        创建理想的测试数据，包含完整的深渊筑底四个阶段
        """
        print(f"\n创建测试场景: {scenario_name}")
        
        # 生成600天的数据
        dates = pd.date_range(end=datetime.now(), periods=600, freq='D')
        n = len(dates)
        
        np.random.seed(42)  # 固定随机种子
        
        if scenario_name == "ideal":
            # 理想场景：完美的深渊筑底模式
            prices = self._create_ideal_price_pattern(n)
            volumes = self._create_ideal_volume_pattern(n)
            
        elif scenario_name == "noisy":
            # 噪声场景：有干扰的深渊筑底模式
            prices = self._create_noisy_price_pattern(n)
            volumes = self._create_noisy_volume_pattern(n)
            
        elif scenario_name == "failed":
            # 失败场景：不符合深渊筑底条件
            prices = self._create_failed_price_pattern(n)
            volumes = self._create_failed_volume_pattern(n)
            
        else:
            raise ValueError(f"未知测试场景: {scenario_name}")
        
        # 确保价格为正
        prices = np.maximum(prices, 1)
        
        # 创建OHLC数据
        opens = prices * (1 + np.random.normal(0, 0.005, n))
        highs = np.maximum(prices, opens) * (1 + np.abs(np.random.normal(0, 0.01, n)))
        lows = np.minimum(prices, opens) * (1 - np.abs(np.random.normal(0, 0.01, n)))
        closes = prices
        
        df = pd.DataFrame({
            'open': opens,
            'high': highs,
            'low': lows,
            'close': closes,
            'volume': volumes.astype(int)
        }, index=dates)
        
        return df
    
    def _create_ideal_price_pattern(self, n):
        """创建理想的价格模式"""
        prices = []
        
        # 阶段1: 高位震荡 (0-150天)
        high_phase = np.random.normal(100, 3, 150)
        prices.extend(high_phase)
        
        # 阶段2: 深度下跌 (150-350天) - 跌幅70%
        decline_start = 100
        decline_end = 30
        decline_phase = np.linspace(decline_start, decline_end, 200)
        decline_phase += np.random.normal(0, 1, 200)
        prices.extend(decline_phase)
        
        # 阶段3: 横盘整理 (350-520天) - 45天横盘
        consolidation_phase = np.random.normal(30, 1.5, 170)
        prices.extend(consolidation_phase)
        
        # 阶段4: 缩量挖坑 (520-570天) - 20天挖坑
        washout_start = 30
        washout_end = 25
        washout_phase = np.linspace(washout_start, washout_end, 50)
        washout_phase += np.random.normal(0, 0.5, 50)
        prices.extend(washout_phase)
        
        # 阶段5: 拉升确认 (570-600天)
        liftoff_phase = np.linspace(25, 28, 30)
        liftoff_phase += np.random.normal(0, 0.3, 30)
        prices.extend(liftoff_phase)
        
        return np.array(prices)
    
    def _create_ideal_volume_pattern(self, n):
        """创建理想的成交量模式"""
        volumes = []
        
        # 高位阶段：正常成交量
        volumes.extend(np.random.randint(800000, 1200000, 150))
        
        # 下跌阶段：逐步缩量
        decline_volumes = np.linspace(1000000, 300000, 200)
        decline_volumes += np.random.normal(0, 50000, 200)
        volumes.extend(decline_volumes.astype(int))
        
        # 横盘阶段：地量
        volumes.extend(np.random.randint(200000, 400000, 170))
        
        # 挖坑阶段：极度缩量
        volumes.extend(np.random.randint(100000, 250000, 50))
        
        # 拉升阶段：温和放量
        volumes.extend(np.random.randint(400000, 600000, 30))
        
        return np.array(volumes)
    
    def _create_noisy_price_pattern(self, n):
        """创建有噪声的价格模式"""
        # 基于理想模式添加更多噪声
        ideal_prices = self._create_ideal_price_pattern(n)
        noise = np.random.normal(0, 2, n).cumsum() * 0.1
        return ideal_prices + noise
    
    def _create_noisy_volume_pattern(self, n):
        """创建有噪声的成交量模式"""
        ideal_volumes = self._create_ideal_volume_pattern(n)
        noise_factor = 1 + np.random.normal(0, 0.3, n)
        return (ideal_volumes * np.abs(noise_factor)).astype(int)
    
    def _create_failed_price_pattern(self, n):
        """创建不符合条件的价格模式（半山腰）"""
        prices = []
        
        # 高位
        prices.extend(np.random.normal(100, 3, 200))
        
        # 只跌30%（不够深）
        decline_phase = np.linspace(100, 70, 200)
        prices.extend(decline_phase)
        
        # 在半山腰横盘
        prices.extend(np.random.normal(70, 3, 200))
        
        return np.array(prices)
    
    def _create_failed_volume_pattern(self, n):
        """创建不符合条件的成交量模式"""
        # 成交量没有明显的地量特征
        return np.random.randint(500000, 1000000, n)
    
    def test_strategy_phases(self, df, scenario_name):
        """测试策略各阶段的识别能力"""
        print(f"\n测试场景: {scenario_name}")
        print("-" * 50)
        
        # 计算技术指标
        df = self.strategy.calculate_technical_indicators(df)
        
        # 测试第零阶段
        deep_decline_ok, deep_decline_info = self.strategy.check_deep_decline_phase(df)
        print(f"第零阶段 (深跌筑底): {'✓' if deep_decline_ok else '✗'}")
        if deep_decline_ok:
            print(f"  - 下跌幅度: {deep_decline_info.get('drop_percent', 'N/A')}")
            print(f"  - 价格位置: {deep_decline_info.get('price_position', 'N/A')}")
        else:
            print(f"  - 失败原因: {deep_decline_info}")
        
        if not deep_decline_ok:
            return False
        
        # 准备阶段数据
        washout_days = self.strategy.config['washout_days']
        hibernation_days = self.strategy.config['hibernation_days']
        
        washout_period = df.tail(washout_days)
        hibernation_period = df.iloc[-(washout_days + hibernation_days):-washout_days]
        
        # 测试第一阶段
        hibernation_ok, hibernation_info = self.strategy.check_hibernation_phase(df, hibernation_period)
        print(f"第一阶段 (横盘蓄势): {'✓' if hibernation_ok else '✗'}")
        if hibernation_ok:
            print(f"  - 波动率: {hibernation_info.get('volatility', 'N/A')}")
            print(f"  - 均线收敛: {hibernation_info.get('ma_convergence', 'N/A')}")
        else:
            print(f"  - 失败原因: {hibernation_info}")
        
        if not hibernation_ok:
            return False
        
        # 测试第二阶段
        washout_ok, washout_info = self.strategy.check_washout_phase(df, hibernation_info, washout_period)
        print(f"第二阶段 (缩量挖坑): {'✓' if washout_ok else '✗'}")
        if washout_ok:
            print(f"  - 支撑突破: {washout_info.get('support_break', 'N/A')}")
            print(f"  - 成交量收缩: {washout_info.get('volume_shrink_ratio', 'N/A')}")
        else:
            print(f"  - 失败原因: {washout_info}")
        
        if not washout_ok:
            return False
        
        # 测试第三阶段
        liftoff_ok, liftoff_info = self.strategy.check_liftoff_confirmation(df, washout_info)
        print(f"第三阶段 (确认拉升): {'✓' if liftoff_ok else '✗'}")
        if liftoff_ok:
            print(f"  - 从坑底反弹: {liftoff_info.get('rise_from_bottom', 'N/A')}")
            print(f"  - 成交量放大: {liftoff_info.get('volume_increase', 'N/A')}")
            print(f"  - 确认条件: {liftoff_info.get('conditions_met', 'N/A')}")
        else:
            print(f"  - 失败原因: {liftoff_info}")
        
        return liftoff_ok
    
    def test_complete_strategy(self, df, scenario_name):
        """测试完整策略"""
        print(f"\n完整策略测试: {scenario_name}")
        print("-" * 50)
        
        signal_series, details = self.strategy.apply_strategy(df)
        
        if signal_series is not None and details is not None:
            has_signal = signal_series.iloc[-1] == 'BUY'
            print(f"策略结果: {'✓ 生成买入信号' if has_signal else '✗ 无信号'}")
            
            if has_signal:
                print("信号详情:")
                for phase, info in details.items():
                    if phase != 'strategy_version':
                        print(f"  {phase}: {info}")
            
            return has_signal
        else:
            print("策略结果: ✗ 无信号")
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("深渊筑底优化策略 - 全面测试")
        print("=" * 60)
        
        test_scenarios = ["ideal", "noisy", "failed"]
        results = {}
        
        for scenario in test_scenarios:
            print(f"\n{'='*20} 测试场景: {scenario.upper()} {'='*20}")
            
            # 创建测试数据
            df = self.create_ideal_test_data(scenario)
            
            # 测试各阶段
            phases_ok = self.test_strategy_phases(df, scenario)
            
            # 测试完整策略
            strategy_ok = self.test_complete_strategy(df, scenario)
            
            results[scenario] = {
                'phases_passed': phases_ok,
                'strategy_passed': strategy_ok,
                'expected_result': scenario != "failed"
            }
            
            # 保存测试数据（可选）
            if scenario == "ideal":
                self.save_test_data(df, f"test_data_{scenario}.csv")
        
        # 输出测试总结
        self.print_test_summary(results)
        
        return results
    
    def save_test_data(self, df, filename):
        """保存测试数据"""
        try:
            df.to_csv(filename)
            print(f"\n测试数据已保存至: {filename}")
        except Exception as e:
            print(f"保存测试数据失败: {e}")
    
    def print_test_summary(self, results):
        """打印测试总结"""
        print("\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        
        total_tests = len(results)
        passed_tests = 0
        
        for scenario, result in results.items():
            expected = result['expected_result']
            actual = result['strategy_passed']
            
            if expected == actual:
                status = "✓ PASS"
                passed_tests += 1
            else:
                status = "✗ FAIL"
            
            print(f"{scenario.upper():10s}: {status:8s} (期望: {expected}, 实际: {actual})")
        
        print("-" * 60)
        print(f"总体结果: {passed_tests}/{total_tests} 测试通过")
        
        if passed_tests == total_tests:
            print("🎉 所有测试通过！策略工作正常。")
        else:
            print("⚠️  部分测试失败，需要检查策略逻辑。")
    
    def create_visualization(self, df, scenario_name):
        """创建可视化图表"""
        try:
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
            
            # 价格图
            ax1.plot(df.index, df['close'], label='收盘价', linewidth=1)
            ax1.plot(df.index, df['ma30'], label='MA30', alpha=0.7)
            ax1.set_title(f'深渊筑底策略测试 - {scenario_name}')
            ax1.set_ylabel('价格')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 成交量图
            ax2.bar(df.index, df['volume'], alpha=0.6, label='成交量')
            ax2.plot(df.index, df['volume_ma20'], color='red', label='成交量MA20')
            ax2.set_ylabel('成交量')
            ax2.set_xlabel('日期')
            ax2.legend()
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            plt.savefig(f'abyss_test_{scenario_name}.png', dpi=300, bbox_inches='tight')
            plt.show()
            
            print(f"图表已保存: abyss_test_{scenario_name}.png")
            
        except Exception as e:
            print(f"创建可视化失败: {e}")


def main():
    """主函数"""
    print("深渊筑底优化策略测试开始...")
    
    tester = AbyssStrategyTester()
    
    # 运行所有测试
    results = tester.run_all_tests()
    
    # 创建可视化（可选）
    try:
        ideal_df = tester.create_ideal_test_data("ideal")
        tester.create_visualization(ideal_df, "ideal")
    except Exception as e:
        print(f"创建可视化失败: {e}")
    
    # 保存测试结果
    try:
        with open(f'abyss_test_results_{datetime.now().strftime("%Y%m%d_%H%M")}.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("测试结果已保存")
    except Exception as e:
        print(f"保存测试结果失败: {e}")


if __name__ == '__main__':
    main()