"""
Super Trend策略：历史数据扫描与T0定位脚本
自动扫描全市场历史数据，定位主升浪起爆点(T0)
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import data_loader
import indicators

# 全局配置
MIN_LOOKBACK_DAYS = 60  # 最少需要的历史数据天数
FUTURE_LOOKAHEAD_DAYS = 30  # 计算未来涨幅的天数
MIN_FUTURE_GAIN = 0.50  # 最小未来涨幅 (50%)
MAX_DRAWDOWN = 0.15  # 最大回撤 (15%)
T0_WINDOW_BACK = 5  # 向前查找起爆点的天数

def load_stock_data(stock_code, end_date=None):
    """加载股票日线数据"""
    try:
        df = data_loader.get_full_data_with_indicators(stock_code)
        if df is None or len(df) < MIN_LOOKBACK_DAYS + FUTURE_LOOKAHEAD_DAYS:
            return None
            
        # 计算技术指标
        df = indicators.calculate_indicators(df)
        
        # 如果有结束日期，过滤数据
        if end_date:
            df = df[df['date'] <= end_date]
            
        return df
    except Exception as e:
        return None

def find_super_trend_candidates(df):
    """
    在单只股票数据中查找主升浪候选点
    返回：(候选点列表, 是否是正样本)
    """
    if len(df) < MIN_LOOKBACK_DAYS + FUTURE_LOOKAHEAD_DAYS:
        return [], False
        
    candidates = []
    
    # 遍历可能的T0点
    for i in range(MIN_LOOKBACK_DAYS, len(df) - FUTURE_LOOKAHEAD_DAYS):
        t0_date = df.iloc[i]['date']
        t0_price = df.iloc[i]['close']
        
        # 计算未来30天的表现
        future_window = df.iloc[i+1:i+FUTURE_LOOKAHEAD_DAYS+1]
        if len(future_window) < FUTURE_LOOKAHEAD_DAYS:
            continue
            
        # 计算未来最大涨幅(MFE)和最大回撤(MAE)
        future_high = future_window['high'].max()
        future_low = future_window['low'].min()
        mfe = (future_high / t0_price) - 1.0
        mae = (future_low / t0_price) - 1.0
        
        # 判断是否为主升浪正样本
        is_positive_sample = mfe >= MIN_FUTURE_GAIN and mae >= -MAX_DRAWDOWN
        
        # 找到起爆点(T0) - 向前查找第一根突破大阳线
        t0_index = i
        for lookback in range(1, min(T0_WINDOW_BACK, i) + 1):
            idx = i - lookback
            current = df.iloc[idx]
            prev = df.iloc[idx-1] if idx > 0 else current
            
            # 判断是否为大阳线突破
            price_change = (current['close'] / prev['close']) - 1.0
            vol_ratio = current['volume'] / df.iloc[idx-20:idx]['volume'].mean() if idx >= 20 else 1.0
            
            if price_change > 0.03 and vol_ratio > 1.5:
                t0_index = idx
                break
        
        if is_positive_sample:
            candidates.append({
                'stock_code': df['code'].iloc[0] if 'code' in df.columns else 'unknown',
                't0_date': df.iloc[t0_index]['date'],
                't0_price': df.iloc[t0_index]['close'],
                't0_index': t0_index,
                'future_mfe': mfe,
                'future_mae': mae,
                'days_after': FUTURE_LOOKAHEAD_DAYS,
                'is_positive_sample': is_positive_sample
            })
    
    return candidates, len([c for c in candidates if c['is_positive_sample']]) > 0

def scan_all_stocks(start_date=None, end_date=None):
    """
    扫描全市场历史数据，找出所有主升浪候选点
    """
    # 获取股票列表 - 这里简化处理，实际需要从TDX目录读取
    vipdoc_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    all_candidates = []
    positive_samples = 0
    negative_samples = 0
    
    # 示例：测试几只股票
    test_stocks = ['sh000001', 'sz000002', 'sh600036']
    
    for stock_code in test_stocks:
        print(f"扫描股票: {stock_code}")
        
        df = load_stock_data(stock_code, end_date)
        if df is None:
            continue
            
        candidates, has_positive = find_super_trend_candidates(df)
        
        if candidates:
            all_candidates.extend(candidates)
            
            if has_positive:
                positive_samples += 1
                print(f"  ✓ 发现正样本: {len([c for c in candidates if c['is_positive_sample']])}个")
            else:
                negative_samples += 1
    
    # 生成CSV报告
    if all_candidates:
        df_report = pd.DataFrame(all_candidates)
        report_path = "super_trend_candidates.csv"
        df_report.to_csv(report_path, index=False)
        print(f"\n扫描完成!")
        print(f"总候选点: {len(all_candidates)}")
        print(f"正样本股票数: {positive_samples}")
        print(f"负样本股票数: {negative_samples}")
        print(f"报告已保存至: {report_path}")
    
    return all_candidates

if __name__ == "__main__":
    # 扫描最近5年的数据
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365*5)
    
    print("开始Super Trend历史数据扫描...")
    scan_all_stocks(start_date, end_date)