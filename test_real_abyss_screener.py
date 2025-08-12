#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试真实股票数据的深渊筑底策略筛选器
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json

# 添加backend路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from screener_abyss_optimized import AbyssBottomingStrategy, read_day_file, is_valid_stock_code
    print("✅ 成功导入深渊筑底策略模块")
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    sys.exit(1)


def create_mock_day_file(file_path, scenario="abyss_bottom"):
    """
    创建模拟的.day文件用于测试
    """
    import struct
    
    # 创建目录
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # 生成600天的模拟数据
    n = 600
    base_date = datetime(2023, 1, 1)
    
    if scenario == "abyss_bottom":
        # 深渊筑底模式
        prices = []
        volumes = []
        
        # 高位阶段 (0-120天)
        for i in range(120):
            prices.append(100 + (i % 8 - 4) * 0.8)
            volumes.append(1500000 + (i % 50) * 10000)
        
        # 深跌阶段 (120-300天) - 50%跌幅
        for i in range(180):
            progress = i / 179
            price = 100 - 50 * progress
            prices.append(price + (i % 5 - 2) * 0.5)
            volume = int(1500000 - 1200000 * progress)
            volumes.append(volume + (i % 30) * 2000)
        
        # 横盘阶段 (300-480天)
        for i in range(180):
            prices.append(50 + (i % 6 - 3) * 1.2)
            volumes.append(250000 + (i % 15) * 5000)
        
        # 挖坑阶段 (480-540天)
        for i in range(60):
            progress = i / 59
            price = 50 - 10 * progress
            prices.append(price + (i % 3 - 1) * 0.3)
            volumes.append(150000 + (i % 8) * 2000)
        
        # 拉升阶段 (540-600天)
        for i in range(60):
            progress = i / 59
            price = 40 + 5 * progress
            prices.append(price + (i % 2) * 0.2)
            volumes.append(300000 + i * 3000)
    
    elif scenario == "half_mountain":
        # 半山腰模式
        prices = []
        volumes = []
        
        # 高位 (0-200天)
        for i in range(200):
            prices.append(100 + (i % 10 - 5) * 0.8)
            volumes.append(1200000 + (i % 80) * 5000)
        
        # 只跌30% (200-400天)
        for i in range(200):
            progress = i / 199
            prices.append(100 - 30 * progress)
            volumes.append(1000000 + (i % 40) * 3000)
        
        # 在70附近震荡 (400-600天)
        for i in range(200):
            prices.append(70 + (i % 12 - 6) * 1.5)
            volumes.append(900000 + (i % 25) * 4000)
    
    # 写入.day文件
    with open(file_path, 'wb') as f:
        for i in range(n):
            date = base_date + timedelta(days=i)
            date_int = date.year * 10000 + date.month * 100 + date.day
            
            price = int(prices[i] * 100)  # 价格需要乘以100
            open_price = int(price * (1 + (i % 7 - 3) * 0.002))
            high_price = int(max(price, open_price) * (1 + abs(i % 5) * 0.005))
            low_price = int(min(price, open_price) * (1 - abs(i % 3) * 0.005))
            
            volume = volumes[i]
            amount = int(price * volume / 100)  # 简化的成交额计算
            
            # 打包数据 (32字节)
            data = struct.pack('<IIIIIIII', 
                             date_int, open_price, high_price, low_price, 
                             price, amount, volume, 0)
            f.write(data)
    
    print(f"✅ 创建模拟数据文件: {file_path} ({scenario})")


def test_strategy_with_mock_data():
    """使用模拟数据测试策略"""
    print("\n" + "="*60)
    print("深渊筑底策略真实数据测试")
    print("="*60)
    
    # 创建测试目录
    test_dir = "test_data"
    os.makedirs(test_dir, exist_ok=True)
    
    # 创建策略实例
    strategy = AbyssBottomingStrategy()
    print(f"✅ 策略初始化完成")
    print(f"📋 策略参数: {strategy.config}")
    
    # 测试场景
    test_cases = [
        ("sh600001.day", "abyss_bottom", "深渊筑底模式", True),
        ("sz000001.day", "half_mountain", "半山腰模式", False),
    ]
    
    results = {}
    
    for filename, scenario, description, expected_signal in test_cases:
        print(f"\n📊 测试场景: {description}")
        print("-" * 40)
        
        # 创建模拟数据文件
        file_path = os.path.join(test_dir, filename)
        create_mock_day_file(file_path, scenario)
        
        # 读取数据
        df = read_day_file(file_path)
        if df is None:
            print(f"❌ 读取数据失败: {filename}")
            continue
        
        print(f"📈 数据概览:")
        print(f"  数据长度: {len(df)} 天")
        print(f"  价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
        print(f"  最大跌幅: {(df['close'].max() - df['close'].min()) / df['close'].max():.2%}")
        print(f"  当前价格: {df['close'].iloc[-1]:.2f}")
        print(f"  成交量范围: {df['volume'].min():,} - {df['volume'].max():,}")
        
        # 应用策略
        signal_series, details = strategy.apply_strategy(df)
        
        # 检查结果
        has_signal = signal_series is not None and signal_series.iloc[-1] in ['POTENTIAL_BUY', 'BUY', 'STRONG_BUY']
        is_correct = (has_signal and expected_signal) or (not has_signal and not expected_signal)
        
        print(f"\n🎯 策略结果:")
        if has_signal:
            signal_type = signal_series.iloc[-1]
            stage_passed = details.get('stage_passed', 0)
            print(f"  信号类型: {signal_type}")
            print(f"  通过阶段: {stage_passed}/4")
            
            # 显示详细信息
            if 'deep_decline' in details:
                deep_info = details['deep_decline']
                print(f"  下跌幅度: {deep_info.get('drop_percent', 0):.2%}")
                print(f"  价格位置: {deep_info.get('price_position', 0):.2%}")
                
                volume_analysis = deep_info.get('volume_analysis', {})
                if volume_analysis:
                    print(f"  成交量萎缩: {volume_analysis.get('shrink_ratio', 0):.2f}")
                    print(f"  地量持续: {volume_analysis.get('consistency_ratio', 0):.2%}")
        else:
            print(f"  无信号")
        
        expected_str = "应有信号" if expected_signal else "应无信号"
        result_str = "✅ 正确" if is_correct else "❌ 错误"
        print(f"  预期结果: {expected_str}")
        print(f"  测试结果: {result_str}")
        
        results[scenario] = {
            'has_signal': has_signal,
            'expected': expected_signal,
            'correct': is_correct,
            'details': details
        }
    
    # 测试总结
    print(f"\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    correct_count = sum(1 for r in results.values() if r['correct'])
    total_count = len(results)
    accuracy = correct_count / total_count if total_count > 0 else 0
    
    print(f"总体准确率: {correct_count}/{total_count} ({accuracy:.1%})")
    
    for scenario, result in results.items():
        status = "✅ 正确" if result['correct'] else "❌ 错误"
        print(f"  {scenario}: {status}")
    
    if accuracy == 1.0:
        print(f"\n🎉 所有测试通过！策略工作正常。")
        print(f"📊 策略已准备好用于真实股票数据筛选。")
    else:
        print(f"\n⚠️ 部分测试失败，需要检查策略逻辑。")
    
    # 清理测试文件
    try:
        import shutil
        shutil.rmtree(test_dir)
        print(f"\n🧹 清理测试文件完成")
    except Exception as e:
        print(f"清理测试文件失败: {e}")
    
    return results


def test_stock_code_validation():
    """测试股票代码验证功能"""
    print(f"\n📋 测试股票代码验证功能")
    print("-" * 40)
    
    test_codes = [
        ("sh600001", "sh", True),   # 沪市主板
        ("sh688001", "sh", True),   # 科创板
        ("sz000001", "sz", True),   # 深市主板
        ("sz300001", "sz", True),   # 创业板
        ("sz002001", "sz", True),   # 中小板
        ("bj430001", "bj", True),   # 北交所
        ("sh900001", "sh", False),  # 无效代码
        ("sz400001", "sz", False),  # 无效代码
    ]
    
    correct_count = 0
    for code, market, expected in test_codes:
        result = is_valid_stock_code(code, market)
        is_correct = result == expected
        if is_correct:
            correct_count += 1
        
        status = "✅" if is_correct else "❌"
        print(f"  {code} ({market}): {result} {status}")
    
    accuracy = correct_count / len(test_codes)
    print(f"\n股票代码验证准确率: {correct_count}/{len(test_codes)} ({accuracy:.1%})")
    
    return accuracy == 1.0


def main():
    """主函数"""
    print("深渊筑底策略真实数据筛选器测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试股票代码验证
    code_validation_ok = test_stock_code_validation()
    
    # 测试策略逻辑
    strategy_results = test_strategy_with_mock_data()
    
    # 最终评估
    print(f"\n" + "="*60)
    print("最终评估")
    print("="*60)
    
    strategy_accuracy = sum(1 for r in strategy_results.values() if r['correct']) / len(strategy_results)
    
    print(f"股票代码验证: {'✅ 通过' if code_validation_ok else '❌ 失败'}")
    print(f"策略逻辑测试: {strategy_accuracy:.1%} 准确率")
    
    if code_validation_ok and strategy_accuracy == 1.0:
        print(f"\n🎉 所有测试通过！")
        print(f"✅ 深渊筑底策略筛选器已准备就绪")
        print(f"📊 可以开始筛选真实股票数据")
        print(f"\n🚀 使用方法:")
        print(f"  python backend/screener_abyss_optimized.py")
    else:
        print(f"\n⚠️ 部分测试失败，需要进一步调试")
    
    # 保存测试结果
    try:
        test_results = {
            'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'code_validation': code_validation_ok,
            'strategy_accuracy': strategy_accuracy,
            'strategy_results': strategy_results,
            'overall_status': 'PASS' if code_validation_ok and strategy_accuracy == 1.0 else 'FAIL'
        }
        
        with open(f'abyss_screener_test_results_{datetime.now().strftime("%Y%m%d_%H%M")}.json', 'w', encoding='utf-8') as f:
            json.dump(test_results, f, ensure_ascii=False, indent=2)
        print(f"\n📄 测试结果已保存")
    except Exception as e:
        print(f"保存测试结果失败: {e}")


if __name__ == '__main__':
    main()