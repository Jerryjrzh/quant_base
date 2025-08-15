#!/usr/bin/env python3
"""
测试复权显示功能
验证前端复权设置是否正确工作
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

try:
    import data_loader
    from adjustment_processor import create_adjustment_config, create_adjustment_processor
    import indicators
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    sys.exit(1)

def test_adjustment_display():
    """测试复权显示功能"""
    print("🔍 测试复权显示功能")
    print("=" * 50)
    
    # 测试股票代码
    test_stocks = ['sh688531', 'sz300290', 'sh600036']
    
    # 数据路径
    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    
    for stock_code in test_stocks:
        print(f"\n📊 测试股票: {stock_code}")
        print("-" * 30)
        
        # 构建文件路径
        if '#' in stock_code:
            market = 'ds'
        else:
            market = stock_code[:2]
        file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
        
        if not os.path.exists(file_path):
            print(f"⚠️  数据文件不存在: {file_path}")
            continue
        
        # 加载原始数据
        try:
            df_original = data_loader.get_daily_data(file_path)
            if df_original is None or len(df_original) < 30:
                print(f"⚠️  数据加载失败或数据不足")
                continue
                
            print(f"✅ 成功加载数据，共 {len(df_original)} 条记录")
            
            # 测试不同复权方式
            adjustment_types = ['none', 'forward', 'backward']
            
            for adj_type in adjustment_types:
                print(f"\n🔧 测试 {adj_type} 复权:")
                
                # 创建复权配置
                if adj_type == 'none':
                    df_adjusted = df_original.copy()
                    print("  - 不复权，使用原始数据")
                else:
                    adjustment_config = create_adjustment_config(adj_type)
                    adjustment_processor = create_adjustment_processor(adjustment_config)
                    df_adjusted = adjustment_processor.process_data(df_original, stock_code)
                    
                    # 获取调整信息
                    adj_info = adjustment_processor.get_adjustment_info(df_original, df_adjusted)
                    print(f"  - 复权类型: {adj_info['adjustment_type']}")
                    print(f"  - 调整次数: {adj_info['adjustments_applied']}")
                    print(f"  - 价格变化比例: {adj_info['price_change_ratio']:.4f}")
                
                # 显示价格对比
                latest_original = df_original.iloc[-1]
                latest_adjusted = df_adjusted.iloc[-1]
                
                print(f"  - 最新收盘价 (原始): ¥{latest_original['close']:.2f}")
                print(f"  - 最新收盘价 (调整): ¥{latest_adjusted['close']:.2f}")
                
                # 计算技术指标对比
                ma13_original = df_original['close'].rolling(13).mean().iloc[-1]
                ma13_adjusted = df_adjusted['close'].rolling(13).mean().iloc[-1]
                
                print(f"  - MA13 (原始): ¥{ma13_original:.2f}")
                print(f"  - MA13 (调整): ¥{ma13_adjusted:.2f}")
                
                # 检测价格跳跃
                price_changes = df_original['close'].pct_change().abs()
                large_changes = (price_changes > 0.15).sum()
                print(f"  - 检测到可能的除权点: {large_changes} 个")
        
        except Exception as e:
            print(f"❌ 处理股票 {stock_code} 时出错: {e}")
            continue

def test_frontend_integration():
    """测试前端集成"""
    print("\n🌐 测试前端集成")
    print("=" * 50)
    
    # 检查前端文件是否包含复权设置
    frontend_files = [
        'frontend/index.html',
        'frontend/js/app.js'
    ]
    
    for file_path in frontend_files:
        if os.path.exists(file_path):
            print(f"✅ 检查文件: {file_path}")
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 检查关键词
            keywords = ['adjustment-select', 'adjustment', '复权']
            found_keywords = []
            
            for keyword in keywords:
                if keyword in content:
                    found_keywords.append(keyword)
            
            if found_keywords:
                print(f"  - 找到复权相关内容: {', '.join(found_keywords)}")
            else:
                print(f"  - ⚠️  未找到复权相关内容")
        else:
            print(f"❌ 文件不存在: {file_path}")

def generate_test_report():
    """生成测试报告"""
    print("\n📋 生成测试报告")
    print("=" * 50)
    
    report = {
        'test_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'test_status': 'completed',
        'features_tested': [
            '复权数据处理',
            '前端界面集成',
            '技术指标计算',
            '价格跳跃检测'
        ],
        'recommendations': [
            '建议在前端添加复权状态显示',
            '建议添加复权效果对比功能',
            '建议优化复权算法的准确性',
            '建议添加复权历史记录'
        ]
    }
    
    # 保存报告
    report_file = f'adjustment_display_test_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    
    try:
        import json
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"✅ 测试报告已保存: {report_file}")
    except Exception as e:
        print(f"❌ 保存报告失败: {e}")
    
    return report

if __name__ == "__main__":
    print("🚀 开始复权显示功能测试")
    print("=" * 60)
    
    try:
        # 执行测试
        test_adjustment_display()
        test_frontend_integration()
        
        # 生成报告
        report = generate_test_report()
        
        print("\n✅ 测试完成!")
        print("\n💡 使用建议:")
        print("1. 在前端选择不同的复权方式查看效果")
        print("2. 对比同一股票在不同复权方式下的技术指标")
        print("3. 注意观察有除权除息的股票的价格变化")
        print("4. 建议使用前复权进行技术分析")
        
    except KeyboardInterrupt:
        print("\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()