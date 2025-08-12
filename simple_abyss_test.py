#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深渊筑底策略优化版 - 简化测试脚本
"""

import pandas as pd
import numpy as np
from datetime import datetime

class SimpleAbyssTest:
    def __init__(self):
        self.config = {
            'long_term_days': 500,
            'min_drop_percent': 0.50,
            'price_low_percentile': 0.25,
            'volume_low_percentile': 0.20,
            'hibernation_days': 45,
            'hibernation_volatility_max': 0.30,
            'washout_days': 20,
            'washout_volume_shrink_ratio': 0.80,
            'max_rise_from_bottom': 0.12,
            'liftoff_volume_increase_ratio': 1.3,
        }
    
    def create_test_data(self):
        """创建理想的深渊筑底测试数据"""
        dates = pd.date_range(end=datetime.now(), periods=600, freq='D')
        n = len(dates)
        
        # 设置随机种子以便复现
        np.random.seed(42)
        
        # 创建理想的深渊筑底模式
        prices = []
        
        # 阶段1: 高位震荡 (0-150天)
        high_phase = np.random.normal(100, 3, 150)
        prices.extend(high_phase)
        
        # 阶段2: 深度下跌 (150-350天) - 70%跌幅
        decline_phase = np.linspace(100, 30, 200)
        decline_phase += np.random.normal(0, 1, 200)  # 添加噪声
        prices.extend(decline_phase)
        
        # 阶段3: 横盘整理 (350-520天)
        consolidation_phase = np.random.normal(30, 1.5, 170)
        prices.extend(consolidation_phase)
        
        # 阶段4: 缩量挖坑 (520-570天)
        washout_phase = np.linspace(30, 25, 50)
        washout_phase += np.random.normal(0, 0.5, 50)
        prices.extend(washout_phase)
        
        # 阶段5: 拉升确认 (570-600天)
        liftoff_phase = np.linspace(25, 28, 30)
        liftoff_phase += np.random.normal(0, 0.3, 30)
        prices.extend(liftoff_phase)
        
        prices = np.array(prices)
        prices = np.maximum(prices, 1)  # 确保价格为正
        
        # 创建对应的成交量模式
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
        
        volumes = np.array(volumes)
        volumes = np.maximum(volumes, 50000)  # 确保成交量为正
        
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
    
    def test_deep_decline(self, df):
        """测试第零阶段：深跌筑底"""
        long_term_days = self.config['long_term_days']
        if len(df) < long_term_days:
            return False, "数据长度不足"
        
        df_long_term = df.tail(long_term_days)
        long_term_high = df_long_term['high'].max()
        long_term_low = df_long_term['low'].min()
        current_price = df['close'].iloc[-1]
        
        # 检查价格位置
        price_range = long_term_high - long_term_low
        if price_range == 0:
            return False, "价格无波动"
        
        price_position = (current_price - long_term_low) / price_range
        
        # 检查下跌幅度
        drop_percent = (long_term_high - current_price) / long_term_high
        
        # 检查成交量地量特征
        recent_volume = df['volume'].tail(30).mean()
        volume_threshold = df_long_term['volume'].quantile(self.config['volume_low_percentile'])
        
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
            'volume_ratio': f"{recent_volume/volume_threshold:.2f}",
            'conditions': conditions
        }
        
        return all_ok, details
    
    def test_hibernation_phase(self, df):
        """测试第一阶段：横盘蓄势"""
        washout_days = self.config['washout_days']
        hibernation_days = self.config['hibernation_days']
        
        hibernation_period = df.iloc[-(washout_days + hibernation_days):-washout_days]
        
        if hibernation_period.empty:
            return False, "横盘期数据为空"
        
        # 计算横盘区间
        support_level = hibernation_period['low'].min()
        resistance_level = hibernation_period['high'].max()
        
        # 检查波动率
        volatility = (resistance_level - support_level) / support_level
        volatility_ok = volatility <= self.config['hibernation_volatility_max']
        
        # 检查成交量稳定性
        avg_volume = hibernation_period['volume'].mean()
        volume_stability = hibernation_period['volume'].std() / avg_volume if avg_volume > 0 else float('inf')
        
        details = {
            'support_level': f"{support_level:.2f}",
            'resistance_level': f"{resistance_level:.2f}",
            'volatility': f"{volatility:.2%}",
            'volatility_ok': volatility_ok,
            'avg_volume': f"{avg_volume:,.0f}",
            'volume_stability': f"{volume_stability:.2f}"
        }
        
        return volatility_ok, details
    
    def test_washout_phase(self, df, hibernation_info):
        """测试第二阶段：缩量挖坑"""
        washout_days = self.config['washout_days']
        washout_period = df.tail(washout_days)
        
        if washout_period.empty:
            return False, "挖坑期数据为空"
        
        # 从hibernation_info获取支撑位
        support_level = float(hibernation_info['support_level'])
        hibernation_avg_volume = float(hibernation_info['avg_volume'].replace(',', ''))
        
        # 检查是否跌破支撑
        washout_low = washout_period['low'].min()
        support_broken = washout_low < support_level * self.config['washout_break_threshold']
        
        # 检查挖坑期的缩量特征
        pit_days = washout_period[washout_period['low'] < support_level]
        if pit_days.empty:
            return False, "无有效挖坑数据"
        
        pit_avg_volume = pit_days['volume'].mean()
        volume_shrink_ratio = pit_avg_volume / hibernation_avg_volume
        volume_shrink_ok = volume_shrink_ratio <= self.config['washout_volume_shrink_ratio']
        
        conditions = {
            'support_broken': support_broken,
            'volume_shrink_ok': volume_shrink_ok
        }
        
        all_ok = all(conditions.values())
        
        details = {
            'washout_low': f"{washout_low:.2f}",
            'support_break': f"{(support_level - washout_low) / support_level:.2%}",
            'volume_shrink_ratio': f"{volume_shrink_ratio:.2f}",
            'pit_days_count': len(pit_days),
            'conditions': conditions
        }
        
        return all_ok, details
    
    def test_liftoff_phase(self, df, washout_info):
        """测试第三阶段：确认拉升"""
        washout_low = float(washout_info['washout_low'])
        recent_data = df.tail(3)  # 最近3天
        
        if recent_data.empty:
            return False, "确认期数据不足"
        
        latest = recent_data.iloc[-1]
        prev = recent_data.iloc[-2] if len(recent_data) > 1 else latest
        
        # 条件1：价格企稳回升
        is_price_recovering = (
            latest['close'] > latest['open'] and  # 当日阳线
            latest['close'] > prev['close'] and   # 价格上涨
            latest['low'] >= washout_low * 0.98   # 未创新低
        )
        
        # 条件2：尚未远离坑底
        rise_from_bottom = (latest['close'] - washout_low) / washout_low
        is_near_bottom = rise_from_bottom <= self.config['max_rise_from_bottom']
        
        # 条件3：成交量温和放大
        pit_avg_volume = df.tail(10)['volume'].mean()  # 简化计算
        volume_increase = latest['volume'] / pit_avg_volume
        is_volume_confirming = volume_increase >= self.config['liftoff_volume_increase_ratio']
        
        conditions = {
            'price_recovering': is_price_recovering,
            'near_bottom': is_near_bottom,
            'volume_confirming': is_volume_confirming
        }
        
        conditions_met = sum(conditions.values())
        all_ok = conditions_met >= 2  # 至少满足2个条件
        
        details = {
            'rise_from_bottom': f"{rise_from_bottom:.2%}",
            'volume_increase': f"{volume_increase:.2f}x",
            'conditions_met': f"{conditions_met}/3",
            'conditions': conditions
        }
        
        return all_ok, details
    
    def run_comprehensive_test(self):
        """运行完整的四阶段测试"""
        print("深渊筑底策略优化版 - 完整测试")
        print("=" * 60)
        
        # 创建测试数据
        df = self.create_test_data()
        print(f"创建测试数据: {len(df)} 天")
        
        # 基本数据验证
        print(f"\n数据概览:")
        print(f"  价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
        print(f"  最大跌幅: {(df['close'].max() - df['close'].min()) / df['close'].max():.2%}")
        print(f"  当前价格: {df['close'].iloc[-1]:.2f}")
        print(f"  成交量范围: {df['volume'].min():,} - {df['volume'].max():,}")
        
        # 阶段测试
        test_results = {}
        
        # 第零阶段测试
        print(f"\n第零阶段：深跌筑底")
        print("-" * 30)
        deep_ok, deep_info = self.test_deep_decline(df)
        test_results['deep_decline'] = deep_ok
        print(f"结果: {'✓ 通过' if deep_ok else '✗ 失败'}")
        if deep_ok:
            print(f"  下跌幅度: {deep_info['drop_percent']}")
            print(f"  价格位置: {deep_info['price_position']}")
            print(f"  成交量比: {deep_info['volume_ratio']}")
        else:
            print(f"  失败原因: {deep_info}")
        
        if not deep_ok:
            print("\n❌ 第零阶段未通过，测试终止")
            return test_results
        
        # 第一阶段测试
        print(f"\n第一阶段：横盘蓄势")
        print("-" * 30)
        hibernation_ok, hibernation_info = self.test_hibernation_phase(df)
        test_results['hibernation'] = hibernation_ok
        print(f"结果: {'✓ 通过' if hibernation_ok else '✗ 失败'}")
        if hibernation_ok:
            print(f"  支撑位: {hibernation_info['support_level']}")
            print(f"  阻力位: {hibernation_info['resistance_level']}")
            print(f"  波动率: {hibernation_info['volatility']}")
        else:
            print(f"  失败原因: {hibernation_info}")
        
        if not hibernation_ok:
            print("\n❌ 第一阶段未通过，测试终止")
            return test_results
        
        # 第二阶段测试
        print(f"\n第二阶段：缩量挖坑")
        print("-" * 30)
        washout_ok, washout_info = self.test_washout_phase(df, hibernation_info)
        test_results['washout'] = washout_ok
        print(f"结果: {'✓ 通过' if washout_ok else '✗ 失败'}")
        if washout_ok:
            print(f"  挖坑低点: {washout_info['washout_low']}")
            print(f"  支撑突破: {washout_info['support_break']}")
            print(f"  成交量收缩: {washout_info['volume_shrink_ratio']}")
        else:
            print(f"  失败原因: {washout_info}")
        
        if not washout_ok:
            print("\n❌ 第二阶段未通过，测试终止")
            return test_results
        
        # 第三阶段测试
        print(f"\n第三阶段：确认拉升")
        print("-" * 30)
        liftoff_ok, liftoff_info = self.test_liftoff_phase(df, washout_info)
        test_results['liftoff'] = liftoff_ok
        print(f"结果: {'✓ 通过' if liftoff_ok else '✗ 失败'}")
        if liftoff_ok:
            print(f"  从坑底反弹: {liftoff_info['rise_from_bottom']}")
            print(f"  成交量放大: {liftoff_info['volume_increase']}")
            print(f"  确认条件: {liftoff_info['conditions_met']}")
        else:
            print(f"  失败原因: {liftoff_info}")
        
        # 测试总结
        print(f"\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        
        passed_stages = sum(test_results.values())
        total_stages = len(test_results)
        
        print(f"通过阶段: {passed_stages}/{total_stages}")
        
        for stage, result in test_results.items():
            status = "✓ 通过" if result else "✗ 失败"
            print(f"  {stage}: {status}")
        
        if passed_stages == total_stages:
            print(f"\n🎉 所有阶段测试通过！策略识别成功。")
            print(f"📈 该股票符合深渊筑底模式，可生成买入信号。")
        else:
            print(f"\n⚠️  部分阶段测试失败。")
        
        return test_results

def main():
    """主函数"""
    test = SimpleAbyssTest()
    results = test.run_comprehensive_test()
    
    # 保存测试结果
    try:
        import json
        with open(f'abyss_test_results_{datetime.now().strftime("%Y%m%d_%H%M")}.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n📄 测试结果已保存")
    except Exception as e:
        print(f"保存测试结果失败: {e}")

if __name__ == '__main__':
    main()