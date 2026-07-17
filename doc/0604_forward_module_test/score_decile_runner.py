#!/usr/bin/env python3
"""
打分分层回测运行器 (Score Decile Runner)
将 screenergf.py 的入场门槛从 85 分临时降至 60 分，
跑一次日历回测，收集所有 60+ 分数的交易数据用于分层分析。
"""
import os
import re
import sys
import subprocess
import shutil
import uuid
import pandas as pd
from datetime import datetime
from multiprocessing import Pool

# ===== 配置 =====
SCORE_THRESHOLD = 60  # 从 85 降至 60，开闸放水
START_DATE = '2025-09-01'  # 选取 2 周代表性区间（交易活跃期，快速出结果）
END_DATE = '2025-09-12'
WORKERS = 4
# ================

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENERGF_PATH = os.path.join(BACKEND_DIR, 'screenergf.py')
SCREENERGF_BACKUP = SCREENERGF_PATH + '.bak_score_test'
TESTER_PATH = os.path.join(BACKEND_DIR, 'walk_forward_tester_s.py')
RESULT_DIR = os.path.join(BACKEND_DIR, '..', 'data', 'result', 'Score_Decile_Test')
MASTER_CSV = os.path.join(RESULT_DIR, 'score_decile_trades.csv')


def patch_screenergf():
    """临时修改 screenergf.py 的打分门槛"""
    shutil.copy2(SCREENERGF_PATH, SCREENERGF_BACKUP)
    with open(SCREENERGF_PATH, 'r', encoding='utf-8') as f:
        code = f.read()
    patched = re.sub(
        r'if score >= 85:',
        f'if score >= {SCORE_THRESHOLD}:',
        code, count=1
    )
    with open(SCREENERGF_PATH, 'w', encoding='utf-8') as f:
        f.write(patched)
    print(f"✅ screenergf.py 门槛已临时修改: 85 -> {SCORE_THRESHOLD}")


def restore_screenergf():
    """恢复 screenergf.py 原始版本"""
    if os.path.exists(SCREENERGF_BACKUP):
        shutil.move(SCREENERGF_BACKUP, SCREENERGF_PATH)
        print(f"✅ screenergf.py 已恢复原始版本 (门槛 85)")


def get_trading_days(start, end):
    """获取真实交易日"""
    import data_loader
    idx_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000001.day")
    if not os.path.exists(idx_path):
        return pd.date_range(start=start, end=end, freq='B')
    df_idx = data_loader.get_daily_data(idx_path)
    mask = (df_idx.index >= pd.to_datetime(start)) & (df_idx.index <= pd.to_datetime(end))
    return df_idx[mask].index


def process_day(args):
    date_str, original_code, backend_dir = args
    pid = f"{date_str}_{uuid.uuid4().hex[:6]}"
    temp_script = os.path.join(backend_dir, f'_temp_score_{pid}.py')
    temp_csv = os.path.join(backend_dir, f'latest_walk_forward_{pid}.csv')

    try:
        code = original_code
        code = re.sub(r"EVAL_DATE\s*=\s*['\"].*?['\"]", f"EVAL_DATE = '{date_str}'", code, count=1)
        code = re.sub(r"STRATEGY_TO_TEST\s*=\s*['\"].*?['\"]", "STRATEGY_TO_TEST = 'MORSE_FACTOR_SNIPER'", code)
        code = re.sub(r"latest_walk_forward\.csv", f"latest_walk_forward_{pid}.csv", code)
        code = re.sub(r"latest_daily_journal\.csv", f"latest_daily_journal_{pid}.csv", code)

        with open(temp_script, 'w', encoding='utf-8') as f:
            f.write(code)

        subprocess.run([sys.executable, temp_script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if os.path.exists(temp_csv):
            df = pd.read_csv(temp_csv)
            executed = df[~df['交易状态'].isin(['未成交', '等待实盘验证(T+1)', '大幅低开放弃', '挂单超时撤销', '弱势低开撤单'])].copy()
            if not executed.empty:
                return {'date': date_str, 'status': f"✅ {len(executed)} 笔", 'data': executed}
            return {'date': date_str, 'status': "➖ 无建仓", 'data': None}
        return {'date': date_str, 'status': "❌ 无结果", 'data': None}
    except Exception as e:
        return {'date': date_str, 'status': f"❌ {e}", 'data': None}
    finally:
        for p in [temp_script, temp_csv, os.path.join(backend_dir, f'latest_daily_journal_{pid}.csv')]:
            try:
                os.remove(p)
            except:
                pass


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)

    print(f"\n{'='*60}")
    print(f" 🧪 打分分层回测 (Score Decile Test)")
    print(f"{'='*60}")
    print(f" 门槛: {SCORE_THRESHOLD} 分 (原始 85 分)")
    print(f" 区间: {START_DATE} ~ {END_DATE}")
    print(f" 并发: {WORKERS} 进程")
    print(f"{'='*60}\n")

    patch_screenergf()

    try:
        with open(TESTER_PATH, 'r', encoding='utf-8') as f:
            original_code = f.read()

        days = get_trading_days(START_DATE, END_DATE)
        total = len(days)
        print(f"📅 共 {total} 个交易日待处理\n")

        tasks = [(d.strftime('%Y-%m-%d'), original_code, BACKEND_DIR) for d in days]

        all_trades = []
        done = 0
        with Pool(WORKERS) as pool:
            for r in pool.imap_unordered(process_day, tasks):
                done += 1
                print(f"[{done:03d}/{total}] {r['date']} -> {r['status']}")
                if r['data'] is not None:
                    all_trades.append(r['data'])

        if all_trades:
            final = pd.concat(all_trades, ignore_index=True)
            final.drop_duplicates(subset=['stock_code', '成交日期'], inplace=True)
            final.sort_values(['成交日期', 'stock_code'], inplace=True)
            final.to_csv(MASTER_CSV, index=False, float_format='%.4f')
            print(f"\n🎉 完成! 共 {len(final)} 笔交易 (门槛 {SCORE_THRESHOLD} 分)")
            print(f"💾 数据已保存: {MASTER_CSV}")
        else:
            print("\n⚠️ 无有效交易")

    finally:
        restore_screenergf()


if __name__ == '__main__':
    main()
