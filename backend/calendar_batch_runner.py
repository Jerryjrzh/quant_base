import os
import re
import sys
import subprocess
import pandas as pd
import data_loader
from datetime import datetime

def get_real_trading_days(start_date, end_date):
    """读取上证指数，获取真实的交易日历，跳过周末和节假日，避免白跑"""
    index_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000001.day")
    if not os.path.exists(index_path):
        print("⚠️ 找不到上证指数文件，降级使用标准工作日。")
        return pd.date_range(start=start_date, end=end_date, freq='B')
    
    df_index = data_loader.get_daily_data(index_path)
    mask = (df_index.index >= pd.to_datetime(start_date)) & (df_index.index <= pd.to_datetime(end_date))
    return df_index[mask].index

def main():
    START_DATE = '2025-01-01'
    END_DATE = '2026-04-30'
    
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    tester_path = os.path.join(backend_dir, 'walk_forward_tester_s.py')
    temp_tester_path = os.path.join(backend_dir, '_temp_walk_forward_tester.py')
    latest_csv = os.path.join(backend_dir, 'latest_walk_forward.csv')
    
    # 统一治理：输出目录
    result_dir = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest'))
    os.makedirs(result_dir, exist_ok=True)
    master_csv_path = os.path.join(result_dir, 'full_calendar_trades.csv')

    if not os.path.exists(tester_path):
        print(f"❌ 找不到基准脚本: {tester_path}")
        return

    with open(tester_path, 'r', encoding='utf-8') as f:
        original_code = f.read()

    trading_days = get_real_trading_days(START_DATE, END_DATE)
    total_days = len(trading_days)
    all_trades = []
    
    print(f"\n🚀 启动全日历自动化回测调度中枢...")
    print(f"📅 任务区间: {START_DATE} 至 {END_DATE} (共 {total_days} 个实际交易日)")
    print(f"⚙️ 基准脚本: walk_forward_tester_s.py (逻辑 100% 镜像)\n")

    for i, current_date in enumerate(trading_days, 1):
        date_str = current_date.strftime('%Y-%m-%d')
        print(f"[{i:03d}/{total_days}] 正在压测 {date_str} ... ", end='', flush=True)

        # 动态修改 EVAL_DATE (正则替换，避免走样)
        modified_code = re.sub(
            r"EVAL_DATE\s*=\s*['\"][^'\"]*['\"]", 
            f"EVAL_DATE = '{date_str}'", 
            original_code,
            count=1
        )

        with open(temp_tester_path, 'w', encoding='utf-8') as f:
            f.write(modified_code)

        # 挂载子进程执行，使用当前虚拟环境的 python
        subprocess.run(
            [sys.executable, temp_tester_path], 
            stdout=subprocess.DEVNULL, # 屏蔽子脚本的疯狂输出，保持主控台清爽
            stderr=subprocess.DEVNULL
        )

        # 收集结果
        if os.path.exists(latest_csv):
            try:
                df = pd.read_csv(latest_csv)
                # 过滤掉未成交的单子，只保留产生了真实入场的
                executed = df[(df['trade_status'] != '未成交') & (df['trade_status'] != '等待实盘验证(T+1)')].copy()
                if not executed.empty:
                    all_trades.append(executed)
                    print(f"✅ 捕获 {len(executed)} 笔建仓")
                else:
                    print("➖ 无建仓信号")
            except Exception as e:
                print(f"❌ 读取错误")
        else:
            print("❌ CSV 未生成")

    # 汇总并保存
    if all_trades:
        final_df = pd.concat(all_trades, ignore_index=True)
        # 去重：如果因为日期重叠导致同一只股票在同一次行情被记录了两次，进行去重
        final_df.drop_duplicates(subset=['stock_code', 'entry_date'], inplace=True)
        
        final_df.to_csv(master_csv_path, index=False, float_format='%.4f')
        print(f"\n🎉 批量回测圆满结束！共捕获 {len(final_df)} 笔有效交易。")
        print(f"💾 数据已归档至: {master_csv_path}")
    else:
        print("\n⚠️ 批量回测结束，但在该时间段内未发现任何交易。")

    # 清理临时文件
    if os.path.exists(temp_tester_path):
        os.remove(temp_tester_path)

if __name__ == '__main__':
    main()
