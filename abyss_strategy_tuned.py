#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深渊筑底策略参数调优版本
基于测试结果调整参数，提高策略的实用性
"""

import json
import math
from datetime import datetime, timedelta

class TunedAbyssStrategy:
    """调优版深渊筑底策略"""
    
    def __init__(self, config_name="balanced"):
        """
        初始化策略配置
        config_name: 'strict', 'balanced', 'loose'
        """
        self.configs = {
            'strict': {
                'long_term_days': 500,
                'min_drop_percent': 0.60,      # 严格：60%跌幅
                'price_low_percentile': 0.20,   # 严格：20%低位
                'volume_low_percentile': 0.15,  # 严格：15%低量
                'hibernation_days': 45,
                'hibernation_volatility_max': 0.25,
                'washout_days': 20,
                'washout_volume_shrink_ratio': 0.75,
                'max_rise_from_bottom': 0.10,
                'liftoff_volume_increase_ratio': 1.5,
                'description': '严格模式：高质量信号，低假阳性'
            },
            'balanced': {
                'long_term_days': 500,
                'min_drop_percent': 0.45,      # 平衡：45%跌幅
                'price_low_percentile': 0.30,   # 平衡：30%低位
                'volume_low_percentile': 0.30,  # 平衡：30%低量
                'hibernation_days': 45,
                'hibernation_volatility_max': 0.35,
                'washout_days': 20,
                'washout_volume_shrink_ratio': 0.85,
                'max_rise_from_bottom': 0.15,
                'liftoff_volume_increase_ratio': 1.2,
                'description': '平衡模式：质量与数量兼顾'
            },
            'loose': {
                'long_term_days': 400,
                'min_drop_percent': 0.35,      # 宽松：35%跌幅
                'price_low_percentile': 0.40,   # 宽松：40%低位
                'volume_low_percentile': 0.40,  # 宽松：40%低量
                'hibernation_days': 30,
                'hibernation_volatility_max': 0.45,
                'washout_days': 15,
                'washout_volume_shrink_ratio': 0.90,
                'max_rise_from_bottom': 0.20,
                'liftoff_volume_increase_ratio': 1.1,
                'description': '宽松模式：更多机会，需要后续筛选'
            }
        }
        
        self.config = self.configs.get(config_name, self.configs['balanced'])
        self.config_name = config_name
    
    def create_test_data(self, scenario="ideal"):
        """创建测试数据"""
        n = 600
        dates = []
        base_date = datetime.now()
        for i in range(n):
            dates.append((base_date - timedelta(days=n-1-i)).strftime('%Y-%m-%d'))
        
        if scenario == "ideal":
            # 理想深渊筑底模式
            prices, volumes = self._create_ideal_pattern(n)
        elif scenario == "realistic":
            # 现实市场模式（有噪声）
            prices, volumes = self._create_realistic_pattern(n)
        elif scenario == "failed":
            # 半山腰模式
            prices, volumes = self._create_failed_pattern(n)
        else:
            raise ValueError(f"未知场景: {scenario}")
        
        # 创建数据结构
        data = []
        for i in range(n):
            close = prices[i]
            open_price = close * (1 + (i % 7 - 3) * 0.002)
            high = max(close, open_price) * (1 + abs(i % 5) * 0.005)
            low = min(close, open_price) * (1 - abs(i % 3) * 0.005)
            
            data.append({
                'date': dates[i],
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': int(volumes[i])
            })
        
        return data
    
    def _create_ideal_pattern(self, n):
        """创建理想模式"""
        prices = []
        volumes = []
        
        # 高位 (0-150)
        for i in range(150):
            prices.append(100 + (i % 10 - 5) * 0.5)
            volumes.append(1000000 + (i % 100) * 2000)
        
        # 深跌 (150-350) - 65%跌幅
        for i in range(200):
            progress = i / 199
            price = 100 - 65 * progress
            prices.append(price + (i % 7 - 3) * 0.3)
            # 下跌过程中成交量逐步萎缩
            volume = int(1000000 - 600000 * progress)
            volumes.append(volume + (i % 50) * 1000)
        
        # 横盘 (350-520)
        for i in range(170):
            prices.append(35 + (i % 5 - 2) * 0.8)
            # 横盘期地量
            volumes.append(250000 + (i % 20) * 3000)
        
        # 挖坑 (520-570)
        for i in range(50):
            progress = i / 49
            prices.append(35 - 8 * progress + (i % 3 - 1) * 0.2)
            # 挖坑期极度缩量
            volumes.append(150000 + (i % 10) * 2000)
        
        # 拉升 (570-600)
        for i in range(30):
            progress = i / 29
            prices.append(27 + 5 * progress + (i % 2) * 0.1)
            # 拉升期温和放量
            volumes.append(300000 + i * 5000)
        
        return prices, volumes
    
    def _create_realistic_pattern(self, n):
        """创建现实模式（有噪声）"""
        ideal_prices, ideal_volumes = self._create_ideal_pattern(n)
        
        # 添加噪声
        noisy_prices = []
        noisy_volumes = []
        
        for i in range(n):
            # 价格噪声
            noise_factor = 1 + (i % 13 - 6) * 0.01
            noisy_prices.append(ideal_prices[i] * noise_factor)
            
            # 成交量噪声
            volume_noise = 1 + (i % 17 - 8) * 0.05
            noisy_volumes.append(int(ideal_volumes[i] * abs(volume_noise)))
        
        return noisy_prices, noisy_volumes
    
    def _create_failed_pattern(self, n):
        """创建失败模式（半山腰）"""
        prices = []
        volumes = []
        
        # 高位 (0-200)
        for i in range(200):
            prices.append(100 + (i % 10 - 5) * 0.5)
            volumes.append(1000000 + (i % 100) * 2000)
        
        # 只跌35% (200-400)
        for i in range(200):
            progress = i / 199
            prices.append(100 - 35 * progress)
            volumes.append(800000 + (i % 50) * 1000)
        
        # 在65附近震荡 (400-600)
        for i in range(200):
            prices.append(65 + (i % 8 - 4) * 1.0)
            volumes.append(600000 + (i % 30) * 2000)
        
        return prices, volumes
    
    def get_price_list(self, data, field='close'):
        """获取价格列表"""
        return [item[field] for item in data]
    
    def get_volume_list(self, data):
        """获取成交量列表"""
        return [item['volume'] for item in data]
    
    def calculate_percentile(self, values, percentile):
        """计算百分位数"""
        sorted_values = sorted(values)
        n = len(sorted_values)
        index = int(n * percentile)
        if index >= n:
            index = n - 1
        return sorted_values[index]
    
    def calculate_mean(self, values):
        """计算平均值"""
        return sum(values) / len(values) if values else 0
    
    def test_deep_decline(self, data):
        """测试深跌筑底阶段"""
        long_term_days = self.config['long_term_days']
        if len(data) < long_term_days:
            return False, "数据长度不足"
        
        # 获取长期数据
        long_term_data = data[-long_term_days:]
        highs = self.get_price_list(long_term_data, 'high')
        lows = self.get_price_list(long_term_data, 'low')
        volumes = self.get_volume_list(long_term_data)
        
        long_term_high = max(highs)
        long_term_low = min(lows)
        current_price = data[-1]['close']
        
        # 检查价格位置
        price_range = long_term_high - long_term_low
        if price_range == 0:
            return False, "价格无波动"
        
        price_position = (current_price - long_term_low) / price_range
        
        # 检查下跌幅度
        drop_percent = (long_term_high - current_price) / long_term_high
        
        # 检查成交量地量特征 - 使用更灵活的方法
        recent_volumes = self.get_volume_list(data[-30:])
        recent_volume = self.calculate_mean(recent_volumes)
        
        # 计算多个时间段的成交量分位数，取较宽松的标准
        volume_thresholds = []
        for days in [250, 300, 400, 500]:
            if len(data) >= days:
                period_data = data[-days:]
                period_volumes = self.get_volume_list(period_data)
                threshold = self.calculate_percentile(period_volumes, self.config['volume_low_percentile'])
                volume_thresholds.append(threshold)
        
        # 使用最宽松的成交量阈值
        volume_threshold = max(volume_thresholds) if volume_thresholds else recent_volume * 2
        
        # 综合判断
        conditions = {
            'price_position_ok': price_position <= self.config['price_low_percentile'],
            'drop_percent_ok': drop_percent >= self.config['min_drop_percent'],
            'volume_ok': recent_volume <= volume_threshold
        }
        
        all_ok = all(conditions.values())
        
        details = {
            'drop_percent': f"{drop_percent:.2%}",
            'price_position': f"{price_position:.2%}",
            'volume_ratio': f"{recent_volume/volume_threshold:.2f}" if volume_threshold > 0 else "N/A",
            'volume_threshold': f"{volume_threshold:,.0f}",
            'recent_volume': f"{recent_volume:,.0f}",
            'conditions': conditions,
            'config_mode': self.config_name
        }
        
        return all_ok, details
    
    def apply_complete_strategy(self, data):
        """应用完整策略（简化版）"""
        # 第零阶段检查
        deep_ok, deep_info = self.test_deep_decline(data)
        if not deep_ok:
            return False, {'stage': 'deep_decline', 'reason': deep_info}
        
        # 简化的后续阶段检查
        # 在实际应用中，这里会有完整的四阶段检查
        
        return True, {
            'stage': 'complete',
            'signal': 'BUY',
            'deep_decline_info': deep_info,
            'config_mode': self.config_name
        }
    
    def run_multi_config_test(self):
        """运行多配置测试"""
        print("深渊筑底策略 - 多配置参数测试")
        print("=" * 70)
        
        scenarios = ['ideal', 'realistic', 'failed']
        results = {}
        
        for config_name in ['strict', 'balanced', 'loose']:
            print(f"\n配置模式: {config_name.upper()}")
            print(f"描述: {self.configs[config_name]['description']}")
            print("-" * 50)
            
            # 切换配置
            self.config = self.configs[config_name]
            self.config_name = config_name
            
            config_results = {}
            
            for scenario in scenarios:
                data = self.create_test_data(scenario)
                success, details = self.apply_complete_strategy(data)
                
                config_results[scenario] = {
                    'success': success,
                    'details': details
                }
                
                status = "✓ 通过" if success else "✗ 失败"
                expected = "应通过" if scenario != 'failed' else "应失败"
                correct = (success and scenario != 'failed') or (not success and scenario == 'failed')
                
                print(f"  {scenario:10s}: {status:8s} ({expected}) {'✓' if correct else '✗'}")
                
                if scenario != 'failed' and success:
                    deep_info = details.get('deep_decline_info', {})
                    print(f"    跌幅: {deep_info.get('drop_percent', 'N/A'):>8s} "
                          f"位置: {deep_info.get('price_position', 'N/A'):>8s} "
                          f"量比: {deep_info.get('volume_ratio', 'N/A'):>8s}")
            
            results[config_name] = config_results
        
        # 总结分析
        print(f"\n" + "=" * 70)
        print("配置对比分析")
        print("=" * 70)
        
        for config_name, config_results in results.items():
            correct_count = 0
            total_count = len(scenarios)
            
            for scenario, result in config_results.items():
                success = result['success']
                expected_success = scenario != 'failed'
                if (success and expected_success) or (not success and not expected_success):
                    correct_count += 1
            
            accuracy = correct_count / total_count
            print(f"{config_name:8s}: {correct_count}/{total_count} 正确 ({accuracy:.1%})")
        
        # 推荐配置
        print(f"\n推荐配置:")
        print(f"  - 追求高质量信号: 使用 'strict' 模式")
        print(f"  - 平衡质量与数量: 使用 'balanced' 模式") 
        print(f"  - 需要更多机会: 使用 'loose' 模式")
        
        return results

def main():
    """主函数"""
    print("深渊筑底策略参数调优测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    strategy = TunedAbyssStrategy()
    results = strategy.run_multi_config_test()
    
    # 保存结果
    try:
        filename = f'abyss_tuned_results_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'results': results,
                'configs': strategy.configs
            }, f, ensure_ascii=False, indent=2)
        print(f"\n📄 测试结果已保存至: {filename}")
    except Exception as e:
        print(f"保存结果失败: {e}")

if __name__ == '__main__':
    main()