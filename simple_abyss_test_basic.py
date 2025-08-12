#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深渊筑底策略优化版 - 基础测试脚本（无外部依赖）
"""

import json
import math
from datetime import datetime, timedelta

class BasicAbyssTest:
    """基础深渊筑底策略测试器"""
    
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
        n = 600  # 600天数据
        
        # 创建日期序列
        dates = []
        base_date = datetime.now()
        for i in range(n):
            dates.append((base_date - timedelta(days=n-1-i)).strftime('%Y-%m-%d'))
        
        # 创建理想的深渊筑底价格模式
        prices = []
        
        # 阶段1: 高位震荡 (0-150天)
        for i in range(150):
            price = 100 + (i % 10 - 5) * 0.5  # 在100附近震荡
            prices.append(price)
        
        # 阶段2: 深度下跌 (150-350天) - 70%跌幅
        for i in range(200):
            progress = i / 199  # 0到1的进度
            price = 100 - 70 * progress  # 从100跌到30
            price += (i % 7 - 3) * 0.3  # 添加小幅波动
            prices.append(price)
        
        # 阶段3: 横盘整理 (350-520天)
        for i in range(170):
            price = 30 + (i % 5 - 2) * 0.8  # 在30附近横盘
            prices.append(price)
        
        # 阶段4: 缩量挖坑 (520-570天)
        for i in range(50):
            progress = i / 49
            price = 30 - 5 * progress  # 从30跌到25
            price += (i % 3 - 1) * 0.2  # 小幅波动
            prices.append(price)
        
        # 阶段5: 拉升确认 (570-600天)
        for i in range(30):
            progress = i / 29
            price = 25 + 3 * progress  # 从25涨到28
            price += (i % 2) * 0.1  # 小幅波动
            prices.append(price)
        
        # 创建对应的成交量模式
        volumes = []
        
        # 高位阶段：正常成交量
        for i in range(150):
            volume = 1000000 + (i % 100) * 2000
            volumes.append(volume)
        
        # 下跌阶段：逐步缩量
        for i in range(200):
            progress = i / 199
            volume = int(1000000 - 700000 * progress)  # 从100万缩到30万
            volume += (i % 50) * 1000
            volumes.append(volume)
        
        # 横盘阶段：地量
        for i in range(170):
            volume = 300000 + (i % 20) * 5000
            volumes.append(volume)
        
        # 挖坑阶段：极度缩量
        for i in range(50):
            volume = 200000 + (i % 10) * 2000
            volumes.append(volume)
        
        # 拉升阶段：温和放量
        for i in range(30):
            volume = 500000 + i * 3000
            volumes.append(volume)
        
        # 创建OHLC数据
        data = []
        for i in range(n):
            close = prices[i]
            open_price = close * (1 + (i % 7 - 3) * 0.002)  # 开盘价微调
            high = max(close, open_price) * (1 + abs(i % 5) * 0.005)  # 最高价
            low = min(close, open_price) * (1 - abs(i % 3) * 0.005)   # 最低价
            
            data.append({
                'date': dates[i],
                'open': round(open_price, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'close': round(close, 2),
                'volume': volumes[i]
            })
        
        return data
    
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
    
    def calculate_std(self, values):
        """计算标准差"""
        if len(values) < 2:
            return 0
        mean = self.calculate_mean(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return math.sqrt(variance)
    
    def test_deep_decline(self, data):
        """测试第零阶段：深跌筑底"""
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
        
        # 检查成交量地量特征
        recent_volumes = self.get_volume_list(data[-30:])
        recent_volume = self.calculate_mean(recent_volumes)
        volume_threshold = self.calculate_percentile(volumes, self.config['volume_low_percentile'])
        
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
            'long_term_high': f"{long_term_high:.2f}",
            'long_term_low': f"{long_term_low:.2f}",
            'current_price': f"{current_price:.2f}",
            'conditions': conditions
        }
        
        return all_ok, details
    
    def test_hibernation_phase(self, data):
        """测试第一阶段：横盘蓄势"""
        washout_days = self.config['washout_days']
        hibernation_days = self.config['hibernation_days']
        
        # 获取横盘期数据
        start_idx = -(washout_days + hibernation_days)
        end_idx = -washout_days if washout_days > 0 else len(data)
        hibernation_data = data[start_idx:end_idx]
        
        if not hibernation_data:
            return False, "横盘期数据为空"
        
        # 计算横盘区间
        highs = self.get_price_list(hibernation_data, 'high')
        lows = self.get_price_list(hibernation_data, 'low')
        volumes = self.get_volume_list(hibernation_data)
        
        support_level = min(lows)
        resistance_level = max(highs)
        
        # 检查波动率
        volatility = (resistance_level - support_level) / support_level if support_level > 0 else float('inf')
        volatility_ok = volatility <= self.config['hibernation_volatility_max']
        
        # 检查成交量稳定性
        avg_volume = self.calculate_mean(volumes)
        volume_stability = self.calculate_std(volumes) / avg_volume if avg_volume > 0 else float('inf')
        
        details = {
            'support_level': f"{support_level:.2f}",
            'resistance_level': f"{resistance_level:.2f}",
            'volatility': f"{volatility:.2%}",
            'volatility_ok': volatility_ok,
            'avg_volume': f"{avg_volume:,.0f}",
            'volume_stability': f"{volume_stability:.2f}",
            'hibernation_days': len(hibernation_data)
        }
        
        return volatility_ok, details
    
    def test_washout_phase(self, data, hibernation_info):
        """测试第二阶段：缩量挖坑"""
        washout_days = self.config['washout_days']
        washout_data = data[-washout_days:]
        
        if not washout_data:
            return False, "挖坑期数据为空"
        
        # 从hibernation_info获取信息
        support_level = float(hibernation_info['support_level'])
        hibernation_avg_volume = float(hibernation_info['avg_volume'].replace(',', ''))
        
        # 检查是否跌破支撑
        lows = self.get_price_list(washout_data, 'low')
        washout_low = min(lows)
        support_broken = washout_low < support_level * self.config['washout_break_threshold']
        
        # 检查挖坑期的缩量特征
        pit_days = [item for item in washout_data if item['low'] < support_level]
        if not pit_days:
            return False, "无有效挖坑数据"
        
        pit_volumes = self.get_volume_list(pit_days)
        pit_avg_volume = self.calculate_mean(pit_volumes)
        volume_shrink_ratio = pit_avg_volume / hibernation_avg_volume if hibernation_avg_volume > 0 else float('inf')
        volume_shrink_ok = volume_shrink_ratio <= self.config['washout_volume_shrink_ratio']
        
        conditions = {
            'support_broken': support_broken,
            'volume_shrink_ok': volume_shrink_ok
        }
        
        all_ok = all(conditions.values())
        
        details = {
            'washout_low': f"{washout_low:.2f}",
            'support_break': f"{(support_level - washout_low) / support_level:.2%}" if support_level > 0 else "N/A",
            'volume_shrink_ratio': f"{volume_shrink_ratio:.2f}",
            'pit_days_count': len(pit_days),
            'conditions': conditions
        }
        
        return all_ok, details
    
    def test_liftoff_phase(self, data, washout_info):
        """测试第三阶段：确认拉升"""
        washout_low = float(washout_info['washout_low'])
        recent_data = data[-3:]  # 最近3天
        
        if len(recent_data) < 2:
            return False, "确认期数据不足"
        
        latest = recent_data[-1]
        prev = recent_data[-2]
        
        # 条件1：价格企稳回升
        is_price_recovering = (
            latest['close'] > latest['open'] and  # 当日阳线
            latest['close'] > prev['close'] and   # 价格上涨
            latest['low'] >= washout_low * 0.98   # 未创新低
        )
        
        # 条件2：尚未远离坑底
        rise_from_bottom = (latest['close'] - washout_low) / washout_low if washout_low > 0 else 0
        is_near_bottom = rise_from_bottom <= self.config['max_rise_from_bottom']
        
        # 条件3：成交量温和放大
        recent_volumes = self.get_volume_list(data[-10:])  # 最近10天平均量
        pit_avg_volume = self.calculate_mean(recent_volumes)
        volume_increase = latest['volume'] / pit_avg_volume if pit_avg_volume > 0 else 0
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
            'latest_close': f"{latest['close']:.2f}",
            'latest_volume': f"{latest['volume']:,}",
            'conditions': conditions
        }
        
        return all_ok, details
    
    def run_comprehensive_test(self):
        """运行完整的四阶段测试"""
        print("深渊筑底策略优化版 - 完整测试")
        print("=" * 60)
        
        # 创建测试数据
        data = self.create_test_data()
        print(f"创建测试数据: {len(data)} 天")
        
        # 基本数据验证
        closes = self.get_price_list(data, 'close')
        volumes = self.get_volume_list(data)
        
        print(f"\n数据概览:")
        print(f"  价格范围: {min(closes):.2f} - {max(closes):.2f}")
        print(f"  最大跌幅: {(max(closes) - min(closes)) / max(closes):.2%}")
        print(f"  当前价格: {closes[-1]:.2f}")
        print(f"  成交量范围: {min(volumes):,} - {max(volumes):,}")
        
        # 阶段测试
        test_results = {}
        
        # 第零阶段测试
        print(f"\n第零阶段：深跌筑底")
        print("-" * 30)
        deep_ok, deep_info = self.test_deep_decline(data)
        test_results['deep_decline'] = deep_ok
        print(f"结果: {'✓ 通过' if deep_ok else '✗ 失败'}")
        if deep_ok:
            print(f"  下跌幅度: {deep_info['drop_percent']}")
            print(f"  价格位置: {deep_info['price_position']}")
            print(f"  成交量比: {deep_info['volume_ratio']}")
            print(f"  价格区间: {deep_info['long_term_low']} - {deep_info['long_term_high']}")
        else:
            print(f"  失败原因: {deep_info}")
        
        if not deep_ok:
            print("\n❌ 第零阶段未通过，测试终止")
            return test_results
        
        # 第一阶段测试
        print(f"\n第一阶段：横盘蓄势")
        print("-" * 30)
        hibernation_ok, hibernation_info = self.test_hibernation_phase(data)
        test_results['hibernation'] = hibernation_ok
        print(f"结果: {'✓ 通过' if hibernation_ok else '✗ 失败'}")
        if hibernation_ok:
            print(f"  支撑位: {hibernation_info['support_level']}")
            print(f"  阻力位: {hibernation_info['resistance_level']}")
            print(f"  波动率: {hibernation_info['volatility']}")
            print(f"  平均成交量: {hibernation_info['avg_volume']}")
        else:
            print(f"  失败原因: {hibernation_info}")
        
        if not hibernation_ok:
            print("\n❌ 第一阶段未通过，测试终止")
            return test_results
        
        # 第二阶段测试
        print(f"\n第二阶段：缩量挖坑")
        print("-" * 30)
        washout_ok, washout_info = self.test_washout_phase(data, hibernation_info)
        test_results['washout'] = washout_ok
        print(f"结果: {'✓ 通过' if washout_ok else '✗ 失败'}")
        if washout_ok:
            print(f"  挖坑低点: {washout_info['washout_low']}")
            print(f"  支撑突破: {washout_info['support_break']}")
            print(f"  成交量收缩: {washout_info['volume_shrink_ratio']}")
            print(f"  挖坑天数: {washout_info['pit_days_count']}")
        else:
            print(f"  失败原因: {washout_info}")
        
        if not washout_ok:
            print("\n❌ 第二阶段未通过，测试终止")
            return test_results
        
        # 第三阶段测试
        print(f"\n第三阶段：确认拉升")
        print("-" * 30)
        liftoff_ok, liftoff_info = self.test_liftoff_phase(data, washout_info)
        test_results['liftoff'] = liftoff_ok
        print(f"结果: {'✓ 通过' if liftoff_ok else '✗ 失败'}")
        if liftoff_ok:
            print(f"  从坑底反弹: {liftoff_info['rise_from_bottom']}")
            print(f"  成交量放大: {liftoff_info['volume_increase']}")
            print(f"  确认条件: {liftoff_info['conditions_met']}")
            print(f"  当前价格: {liftoff_info['latest_close']}")
        else:
            print(f"  失败原因: {liftoff_info}")
        
        # 测试总结
        print(f"\n" + "=" * 60)
        print("测试总结")
        print("=" * 60)
        
        passed_stages = sum(test_results.values())
        total_stages = len(test_results)
        
        print(f"通过阶段: {passed_stages}/{total_stages}")
        
        stage_names = {
            'deep_decline': '深跌筑底',
            'hibernation': '横盘蓄势', 
            'washout': '缩量挖坑',
            'liftoff': '确认拉升'
        }
        
        for stage, result in test_results.items():
            status = "✓ 通过" if result else "✗ 失败"
            name = stage_names.get(stage, stage)
            print(f"  {name}: {status}")
        
        if passed_stages == total_stages:
            print(f"\n🎉 所有阶段测试通过！策略识别成功。")
            print(f"📈 该股票符合深渊筑底模式，可生成买入信号。")
            print(f"💡 这表明优化后的策略能够正确识别理想的深渊筑底形态。")
        else:
            print(f"\n⚠️  {total_stages - passed_stages} 个阶段测试失败。")
            print(f"🔧 需要进一步调整策略参数或逻辑。")
        
        return test_results
    
    def test_failed_scenario(self):
        """测试失败场景（半山腰股票）"""
        print(f"\n" + "=" * 60)
        print("失败场景测试：半山腰股票")
        print("=" * 60)
        
        # 创建半山腰数据
        n = 600
        dates = []
        base_date = datetime.now()
        for i in range(n):
            dates.append((base_date - timedelta(days=n-1-i)).strftime('%Y-%m-%d'))
        
        # 半山腰价格模式：只跌30%
        prices = []
        volumes = []
        
        # 高位 (0-200)
        for i in range(200):
            prices.append(100 + (i % 10 - 5) * 0.5)
            volumes.append(1000000 + (i % 100) * 2000)
        
        # 下跌到70（只跌30%）(200-400)
        for i in range(200):
            progress = i / 199
            price = 100 - 30 * progress  # 只跌30%
            prices.append(price)
            volumes.append(800000 + (i % 50) * 1000)
        
        # 在70附近震荡 (400-600)
        for i in range(200):
            prices.append(70 + (i % 8 - 4) * 1.0)
            volumes.append(600000 + (i % 30) * 2000)
        
        # 创建数据
        failed_data = []
        for i in range(n):
            close = prices[i]
            failed_data.append({
                'date': dates[i],
                'open': close * 1.001,
                'high': close * 1.01,
                'low': close * 0.99,
                'close': close,
                'volume': volumes[i]
            })
        
        # 测试这个失败场景
        deep_ok, deep_info = self.test_deep_decline(failed_data)
        print(f"深跌筛底检查: {'✓ 通过' if deep_ok else '✗ 失败'}")
        print(f"  下跌幅度: {deep_info.get('drop_percent', 'N/A')}")
        print(f"  价格位置: {deep_info.get('price_position', 'N/A')}")
        
        if deep_ok:
            print("⚠️  警告：半山腰股票通过了深跌检查，需要调整参数！")
        else:
            print("✓ 正确：半山腰股票被成功过滤掉。")
        
        return not deep_ok  # 失败场景应该返回False

def main():
    """主函数"""
    print("深渊筑底策略优化版测试开始...")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    test = BasicAbyssTest()
    
    # 运行理想场景测试
    ideal_results = test.run_comprehensive_test()
    
    # 运行失败场景测试
    failed_result = test.test_failed_scenario()
    
    # 最终评估
    print(f"\n" + "=" * 60)
    print("最终评估")
    print("=" * 60)
    
    ideal_passed = sum(ideal_results.values())
    ideal_total = len(ideal_results)
    
    print(f"理想场景: {ideal_passed}/{ideal_total} 阶段通过")
    print(f"失败场景: {'✓ 正确过滤' if failed_result else '✗ 错误通过'}")
    
    if ideal_passed == ideal_total and failed_result:
        print(f"\n🎉 策略优化成功！")
        print(f"✅ 能够正确识别深渊筑底形态")
        print(f"✅ 能够正确过滤半山腰股票")
        print(f"📊 策略具备实战应用价值")
    else:
        print(f"\n⚠️  策略需要进一步优化")
        if ideal_passed < ideal_total:
            print(f"❌ 理想场景识别不完整")
        if not failed_result:
            print(f"❌ 未能正确过滤失败场景")
    
    # 保存测试结果
    try:
        results = {
            'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'ideal_scenario': ideal_results,
            'failed_scenario_filtered': failed_result,
            'overall_success': ideal_passed == ideal_total and failed_result,
            'config': test.config
        }
        
        filename = f'abyss_test_results_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n📄 测试结果已保存至: {filename}")
        
    except Exception as e:
        print(f"保存测试结果失败: {e}")

if __name__ == '__main__':
    main()