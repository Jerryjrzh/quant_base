#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速检查 5min/60m 数据覆盖情况"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))
import pandas as pd
import data_loader

csv = 'doc/0613_super_trend_v2/review4_final_backtest.csv'
df = pd.read_csv(csv)
print(f"总信号: {len(df)}")

# 抽样检查
codes = df['stock_code'].unique()[:10].tolist()
print(f"\n抽样 {len(codes)} 只票:")
for c in codes:
    try:
        d = data_loader.get_multi_timeframe_data(c)
        has_min = d and d.get('data_status', {}).get('min5_available', False)
        if has_min:
            df5 = d['min5_data']
            start = df5.index.min()
            end = df5.index.max()
            print(f"  {c}: 5min {len(df5)} bars, {start} ~ {end}")
        else:
            print(f"  {c}: 5min 不可用")
    except Exception as e:
        print(f"  {c}: 异常 {e}")

# 全量检查 (traded 部分)
print("\n全量 traded 信号 5min 可用率:")
traded = df[df['status'] == 'traded']
ok = 0
for c in traded['stock_code'].unique():
    try:
        d = data_loader.get_multi_timeframe_data(c)
        if d and d.get('data_status', {}).get('min5_available', False):
            ok += 1
    except Exception:
        pass
print(f"  traded 涉及股票 {len(traded['stock_code'].unique())} 只, "
      f"5min 可用 {ok} 只 ({ok/max(len(traded['stock_code'].unique()),1):.1%})")
