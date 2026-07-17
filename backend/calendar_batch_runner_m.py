import os
import re
import sys
import subprocess
import pandas as pd
import data_loader
import shutil
import uuid
from datetime import datetime
from multiprocessing import Pool, cpu_count, current_process

def get_real_trading_days(start_date, end_date):
    """读取上证指数，获取真实的交易日历，跳过周末和节假日"""
    index_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000001.day")
    if not os.path.exists(index_path):
        print("⚠️ 找不到上证指数文件，降级使用标准工作日。")
        return pd.date_range(start=start_date, end=end_date, freq='B')
    
    df_index = data_loader.get_daily_data(index_path)
    mask = (df_index.index >= pd.to_datetime(start_date)) & (df_index.index <= pd.to_datetime(end_date))
    return df_index[mask].index

def process_single_day(args):
    """
    【单日隔离执行核心】
    每个进程拿到属于自己的那一天，生成专属的脚本和 CSV 路径，避免文件读写冲突。
    """
    date_str, original_code, backend_dir = args
    
    # 1. 为当前进程生成独一无二的 UUID 标识，确保文件隔离
    # 👇【修改】去除日期中的连字符，防止 multiprocessing import 模块时语法报错
    safe_date_str = date_str.replace('-', '')
    process_id = f"{safe_date_str}_{uuid.uuid4().hex[:6]}"
    temp_script_path = os.path.join(backend_dir, f'_temp_tester_{process_id}.py')
    temp_csv_path = os.path.join(backend_dir, f'latest_walk_forward_{process_id}.csv')
    temp_journal_path = os.path.join(backend_dir, f'latest_daily_journal_{process_id}.csv')
    
    try:
        # 2. 动态修改代码：不仅修改日期、策略，还要修改它的 CSV 输出路径！
        modified_code = original_code
        
        # 替换 EVAL_DATE
        modified_code = re.sub(
            r"EVAL_DATE\s*=\s*['\"].*?['\"]", 
            f"EVAL_DATE = '{date_str}'", 
            modified_code,
            count=1
        )
        
        # 强制策略和参数统一
        modified_code = re.sub(
            r"STRATEGY_TO_TEST\s*=\s*['\"].*?['\"]",
            f"STRATEGY_TO_TEST = 'MORSE_FACTOR_SNIPER'",
            modified_code
        )
        # 🚨 最关键的隔离：将脚本底部的 CSV 导出名修改为当前进程的专属名
        modified_code = re.sub(
            r"latest_walk_forward\.csv",
            f"latest_walk_forward_{process_id}.csv",
            modified_code
        )
        modified_code = re.sub(
            r"latest_daily_journal\.csv",
            f"latest_daily_journal_{process_id}.csv",
            modified_code
        )

        with open(temp_script_path, 'w', encoding='utf-8') as f:
            f.write(modified_code)

        # 3. 挂载子进程执行
        #print(f"  [子进程启动] 正在压测 {date_str} ...")
        result = subprocess.run(
            [sys.executable, temp_script_path], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )

        # 4. 读取专属 CSV 结果 (保留所有记录，包括未成交/挂单超时/放弃信号)
        trades_df = None
        status_msg = "❌ 无结果"
        if os.path.exists(temp_csv_path):
            try:
                df = pd.read_csv(temp_csv_path)
                if not df.empty:
                    trades_df = df
                    executed = df[~df['交易状态'].isin(['未成交', '等待实盘验证(T+1)', '大幅低开放弃', '挂单超时撤销', '弱势低开撤单'])]
                    status_msg = f"✅ 共{len(df)}笔 (成交{len(executed)}笔, 未成交{len(df)-len(executed)}笔)"
                else:
                    status_msg = "➖ 无信号"
            except Exception as e:
                status_msg = f"❌ 读取错误: {e}"

        return {'date': date_str, 'status': status_msg, 'data': trades_df}

    except Exception as e:
         return {'date': date_str, 'status': f"❌ 进程崩溃: {e}", 'data': None}
         
    finally:
        # 5. 阅后即焚：无论成功与否，强制清理临时脚本和临时 CSV
        if os.path.exists(temp_script_path):
            try: os.remove(temp_script_path)
            except: pass
        if os.path.exists(temp_csv_path):
            try: os.remove(temp_csv_path)
            except: pass
        if os.path.exists(temp_journal_path):
            try: os.remove(temp_journal_path)
            except: pass

def main():
    START_DATE = '2024-01-01'
    END_DATE = '2026-05-30'
    
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    tester_path = os.path.join(backend_dir, 'walk_forward_tester_s.py')
    
    result_dir = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest'))
    os.makedirs(result_dir, exist_ok=True)
    master_csv_path = os.path.join(result_dir, 'full_calendar_trades_v49.csv')

    if not os.path.exists(tester_path):
        print(f"❌ 找不到基准脚本: {tester_path}")
        return

    with open(tester_path, 'r', encoding='utf-8') as f:
        original_code = f.read()

    trading_days = get_real_trading_days(START_DATE, END_DATE)
    total_days = len(trading_days)
    
    # 获取合理的进程数（保留一个核心给系统，防止卡死）
    #workers = max(1, cpu_count() - 2)
    workers = 4
    print(f"\n🚀 启动全日历 [多进程极速] 自动化回测调度中枢...")
    print(f"📅 任务区间: {START_DATE} 至 {END_DATE} (共 {total_days} 个实际交易日)")
    print(f"🏎️ 并发引擎: 开启 {workers} 个并行切片车间")
    print(f"⚙️ 基准脚本: walk_forward_tester_s.py\n")

    # 组装任务参数列表
    tasks = [(d.strftime('%Y-%m-%d'), original_code, backend_dir) for d in trading_days]
    
    all_trades = []
    completed = 0

    # 使用 imap_unordered 实现进度条的实时刷新（无需等待所有任务完成才输出）
    with Pool(processes=workers) as pool:
        for result in pool.imap_unordered(process_single_day, tasks):
            completed += 1
            print(f"[{completed:03d}/{total_days}] {result['date']} 处理完毕 -> {result['status']}")
            
            if result['data'] is not None:
                all_trades.append(result['data'])

    # 汇总并保存
    if all_trades:
        final_df = pd.concat(all_trades, ignore_index=True)
        # 去重
        final_df.drop_duplicates(subset=['stock_code', '成交日期'], inplace=True)
        
        # 按照入场日期排序，方便查看
        final_df.sort_values(by=['成交日期', 'stock_code'], inplace=True)
        
        final_df.to_csv(master_csv_path, index=False, float_format='%.4f')
        print(f"\n🎉 极速批量回测圆满结束！共捕获 {len(final_df)} 笔有效交易。")
        print(f"💾 数据已归档至: {master_csv_path}")
    else:
        print("\n⚠️ 批量回测结束，但在该时间段内未发现任何有效交易。")

if __name__ == '__main__':
    main()
