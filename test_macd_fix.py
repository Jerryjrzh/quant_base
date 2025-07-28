#!/usr/bin/env python3
"""
测试MACD显示修复的脚本
"""
import os
import sys
import json
import pandas as pd
import numpy as np

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

import data_loader
import indicators

def test_macd_api_response():
    """测试MACD API响应格式"""
    print("=== 测试MACD API响应格式 ===\n")
    
    # 测试数据路径
    BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    
    # 使用测试股票
    test_stock = 'sz000001'
    market = test_stock[:2]
    file_path = os.path.join(BASE_PATH, market, 'lday', f'{test_stock}.day')
    
    if not os.path.exists(file_path):
        print("❌ 测试股票数据文件不存在")
        return
    
    print(f"📊 测试股票: {test_stock}")
    
    # 模拟后端API处理流程
    try:
        # 1. 加载数据
        df = data_loader.get_daily_data(file_path)
        if df is None:
            print("❌ 数据加载失败")
            return
        
        print(f"✅ 数据加载成功，共 {len(df)} 条记录")
        
        # 2. 计算指标（模拟app.py中的处理）
        df['ma13'] = indicators.calculate_ma(df, 13)
        df['ma45'] = indicators.calculate_ma(df, 45)
        df['dif'], df['dea'] = indicators.calculate_macd(df)
        df['k'], df['d'], df['j'] = indicators.calculate_kdj(df)
        df['rsi6'] = indicators.calculate_rsi(df, 6)
        df['rsi12'] = indicators.calculate_rsi(df, 12)
        df['rsi24'] = indicators.calculate_rsi(df, 24)
        
        print("✅ 技术指标计算完成")
        
        # 3. 准备返回数据（模拟app.py中的数据处理）
        df.replace({np.nan: None}, inplace=True)
        df_reset = df.reset_index().rename(columns={'index': 'date'})
        df_reset['date'] = df_reset['date'].dt.strftime('%Y-%m-%d')
        
        # 提取最近30天数据用于测试
        recent_data = df_reset.tail(30)
        
        kline_data = recent_data[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        indicator_data = recent_data[['date', 'ma13', 'ma45', 'dif', 'dea', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']].to_dict('records')
        
        print(f"✅ 数据格式化完成，最近30天数据")
        
        # 4. 检查MACD数据质量
        print(f"\n=== MACD数据质量检查 ===")
        
        macd_data_check = []
        for item in indicator_data[-10:]:  # 检查最近10天
            date = item['date']
            dif = item['dif']
            dea = item['dea']
            
            dif_status = "✅" if dif is not None else "❌"
            dea_status = "✅" if dea is not None else "❌"
            
            macd_data_check.append({
                'date': date,
                'dif': dif,
                'dea': dea,
                'dif_valid': dif is not None,
                'dea_valid': dea is not None
            })
            
            print(f"{date}: DIF={dif_status} DEA={dea_status}")
        
        # 5. 计算MACD显示范围（模拟前端处理）
        all_dif = [item['dif'] for item in indicator_data if item['dif'] is not None]
        all_dea = [item['dea'] for item in indicator_data if item['dea'] is not None]
        all_macd_values = all_dif + all_dea
        
        if all_macd_values:
            macd_min = min(all_macd_values) * 1.2
            macd_max = max(all_macd_values) * 1.2
            print(f"\n📊 MACD显示范围: {macd_min:.4f} 到 {macd_max:.4f}")
            
            if abs(macd_max - macd_min) < 0.001:
                print("⚠️ 警告: MACD范围过小")
            else:
                print("✅ MACD范围正常")
        else:
            print("❌ 无有效MACD数据")
        
        # 6. 生成模拟API响应
        api_response = {
            'kline_data': kline_data,
            'indicator_data': indicator_data,
            'signal_points': [],  # 简化测试
            'backtest_results': {}  # 简化测试
        }
        
        # 保存测试响应到文件
        test_response_file = 'test_macd_api_response.json'
        with open(test_response_file, 'w', encoding='utf-8') as f:
            json.dump(api_response, f, ensure_ascii=False, indent=2)
        
        print(f"\n✅ 测试API响应已保存到: {test_response_file}")
        print(f"📊 K线数据条数: {len(kline_data)}")
        print(f"📊 指标数据条数: {len(indicator_data)}")
        
        # 7. 验证前端图表配置兼容性
        print(f"\n=== 前端图表配置验证 ===")
        
        # 检查数据是否适合4个grid布局
        dates = [item['date'] for item in kline_data]
        print(f"日期数据: {len(dates)} 条")
        
        # 检查各指标数据完整性
        indicators_check = {
            'MA13': sum(1 for item in indicator_data if item['ma13'] is not None),
            'MA45': sum(1 for item in indicator_data if item['ma45'] is not None),
            'DIF': sum(1 for item in indicator_data if item['dif'] is not None),
            'DEA': sum(1 for item in indicator_data if item['dea'] is not None),
            'RSI6': sum(1 for item in indicator_data if item['rsi6'] is not None),
            'KDJ_K': sum(1 for item in indicator_data if item['k'] is not None),
        }
        
        print("指标数据完整性:")
        for indicator, count in indicators_check.items():
            percentage = (count / len(indicator_data)) * 100
            status = "✅" if percentage > 80 else "⚠️" if percentage > 50 else "❌"
            print(f"  {indicator}: {count}/{len(indicator_data)} ({percentage:.1f}%) {status}")
        
        print(f"\n🎉 MACD显示修复测试完成！")
        
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_macd_api_response()