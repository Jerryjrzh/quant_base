#!/usr/bin/env python3
"""
调试MACD显示问题的脚本
"""
import os
import sys
import pandas as pd
import numpy as np

# 添加backend目录到路径
backend_dir = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_dir)

import data_loader
import indicators

def debug_macd_calculation():
    """调试MACD计算和数据"""
    print("=== MACD显示问题调试 ===\n")
    
    # 测试数据路径
    BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    
    # 找一个测试股票
    test_stocks = ['sz000001', 'sh600000', 'sz300001']
    test_stock = None
    test_file = None
    
    for stock in test_stocks:
        market = stock[:2]
        file_path = os.path.join(BASE_PATH, market, 'lday', f'{stock}.day')
        if os.path.exists(file_path):
            test_stock = stock
            test_file = file_path
            break
    
    if not test_file:
        print("❌ 未找到测试股票数据文件")
        return
    
    print(f"📊 使用测试股票: {test_stock}")
    print(f"📁 数据文件: {test_file}")
    
    # 加载数据
    try:
        df = data_loader.get_daily_data(test_file)
        if df is None:
            print("❌ 数据加载失败")
            return
        
        print(f"✅ 数据加载成功，共 {len(df)} 条记录")
        print(f"📅 数据时间范围: {df.index[0]} 到 {df.index[-1]}")
        
    except Exception as e:
        print(f"❌ 数据加载异常: {e}")
        return
    
    # 计算MACD
    try:
        print("\n=== MACD计算测试 ===")
        dif, dea = indicators.calculate_macd(df)
        
        print(f"✅ MACD计算完成")
        print(f"📊 DIF序列长度: {len(dif)}")
        print(f"📊 DEA序列长度: {len(dea)}")
        
        # 检查数据质量
        dif_valid = dif.dropna()
        dea_valid = dea.dropna()
        
        print(f"📈 DIF有效数据: {len(dif_valid)}/{len(dif)} ({len(dif_valid)/len(dif)*100:.1f}%)")
        print(f"📈 DEA有效数据: {len(dea_valid)}/{len(dea)} ({len(dea_valid)/len(dea)*100:.1f}%)")
        
        # 显示最近的数据
        print(f"\n=== 最近10天MACD数据 ===")
        recent_data = df.tail(10).copy()
        recent_data['dif'] = dif.tail(10)
        recent_data['dea'] = dea.tail(10)
        
        for idx, row in recent_data.iterrows():
            date_str = idx.strftime('%Y-%m-%d')
            close_price = row['close']
            dif_val = row['dif']
            dea_val = row['dea']
            
            dif_str = f"{dif_val:.4f}" if not pd.isna(dif_val) else "NaN"
            dea_str = f"{dea_val:.4f}" if not pd.isna(dea_val) else "NaN"
            
            print(f"{date_str}: 收盘={close_price:.2f}, DIF={dif_str}, DEA={dea_str}")
        
        # 检查数据范围
        print(f"\n=== MACD数据范围 ===")
        if len(dif_valid) > 0:
            print(f"DIF范围: {dif_valid.min():.4f} 到 {dif_valid.max():.4f}")
        if len(dea_valid) > 0:
            print(f"DEA范围: {dea_valid.min():.4f} 到 {dea_valid.max():.4f}")
        
        # 模拟前端数据处理
        print(f"\n=== 前端数据格式测试 ===")
        df_copy = df.copy()
        df_copy['dif'] = dif
        df_copy['dea'] = dea
        
        # 替换NaN为None（模拟前端处理）
        df_copy.replace({np.nan: None}, inplace=True)
        df_reset = df_copy.reset_index().rename(columns={'index': 'date'})
        df_reset['date'] = df_reset['date'].dt.strftime('%Y-%m-%d')
        
        # 提取指标数据
        indicator_data = df_reset[['date', 'dif', 'dea']].tail(5).to_dict('records')
        
        print("最近5天前端格式数据:")
        for item in indicator_data:
            date = item['date']
            dif_val = item['dif']
            dea_val = item['dea']
            print(f"  {date}: DIF={dif_val}, DEA={dea_val}")
        
        # 检查是否有足够的非空数据用于显示
        non_null_dif = [item for item in indicator_data if item['dif'] is not None]
        non_null_dea = [item for item in indicator_data if item['dea'] is not None]
        
        print(f"\n=== 显示数据检查 ===")
        print(f"最近5天中DIF非空数据: {len(non_null_dif)}/5")
        print(f"最近5天中DEA非空数据: {len(non_null_dea)}/5")
        
        if len(non_null_dif) == 0 or len(non_null_dea) == 0:
            print("⚠️ 警告: 最近数据中MACD值为空，这可能是显示问题的原因")
        else:
            print("✅ 最近数据中MACD值正常")
        
    except Exception as e:
        print(f"❌ MACD计算异常: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # 检查前端图表配置
    print(f"\n=== 前端图表配置检查 ===")
    
    # 计算MACD合理范围（模拟前端逻辑）
    all_dif_dea = list(dif.dropna()) + list(dea.dropna())
    if all_dif_dea:
        macd_min = min(all_dif_dea) * 1.2
        macd_max = max(all_dif_dea) * 1.2
        print(f"MACD Y轴范围: {macd_min:.4f} 到 {macd_max:.4f}")
        
        if abs(macd_max - macd_min) < 0.001:
            print("⚠️ 警告: MACD数据范围过小，可能导致显示问题")
        else:
            print("✅ MACD数据范围正常")
    else:
        print("❌ 无法计算MACD范围，所有数据为空")

if __name__ == "__main__":
    debug_macd_calculation()