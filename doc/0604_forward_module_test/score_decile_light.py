#!/usr/bin/env python3
"""
轻量级打分分层测试 (Lightweight Score Decile Test)
跳过 V4.4 定价和复杂出场逻辑，直接计算：
  - screenergf 打分（门槛降至 60）
  - T+3 固定窗口的绝对收益率、MFE、MAE
用于验证 60-85 分区间的交易质量。
"""
import os
import glob
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
import data_loader

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
RESULT_DIR = os.path.join(BACKEND_DIR, '..', 'data', 'result', 'Score_Decile_Test')
OUTPUT_CSV = os.path.join(RESULT_DIR, 'score_decile_trades.csv')

EVAL_DATES = [
    '2025-07-07', '2025-07-14', '2025-07-21', '2025-07-28',
    '2025-08-04', '2025-08-11', '2025-08-18', '2025-08-25',
    '2025-09-01', '2025-09-08',
]
FORWARD_DAYS = 3
SCORE_THRESHOLD = 60


def score_stock(file_path):
    """对单只股票在所有 eval dates 上打分并计算前瞻收益"""
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    if not (stock_code.startswith(('60', '688', '00', '300', '92')) and len(stock_code) == 6):
        return []

    try:
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 150:
            return []

        results = []
        for eval_date_str in EVAL_DATES:
            eval_date = pd.to_datetime(eval_date_str)
            hist = df[df.index <= eval_date]
            if len(hist) < 150:
                continue

            last_idx_pos = df.index.get_loc(hist.index[-1])
            future = df.iloc[last_idx_pos + 1: last_idx_pos + 1 + FORWARD_DAYS]
            if len(future) < 2:
                continue

            try:
                from screenergf import apply_morse_sniper_strategy
                res = apply_morse_sniper_strategy(hist, df_15m=None,
                                                  stock_code=stock_code_full, end_date=eval_date_str)
            except Exception:
                continue

            if res is None or not res.get('signal'):
                continue

            score = res.get('score', 0)
            if score < SCORE_THRESHOLD:
                continue

            close_t0 = float(hist['close'].iloc[-1])
            future_highs = future['high'].values
            future_lows = future['low'].values
            future_close = float(future['close'].iloc[-1])

            mfe = (future_highs.max() - close_t0) / close_t0
            mae = (future_lows.min() - close_t0) / close_t0
            ret = (future_close - close_t0) / close_t0

            results.append({
                'stock_code': stock_code_full,
                'eval_date': eval_date_str,
                'score': score,
                't0_close': round(close_t0, 2),
                'forward_ret': round(ret, 4),
                'MFE': round(mfe, 4),
                'MAE': round(mae, 4),
                'future_days': len(future),
                'trigger_price': round(res.get('trigger_price', 0), 2),
                'has_v44': 'v44_entry' in res,
            })
        return results
    except Exception:
        return []


def main():
    os.makedirs(RESULT_DIR, exist_ok=True)

    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = (glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) +
             glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) +
             glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day")))

    print(f"\n{'='*60}")
    print(f" 🧪 轻量级打分分层测试 (Lightweight Score Decile)")
    print(f"{'='*60}")
    print(f" 门槛: {SCORE_THRESHOLD} 分 (原始 85)")
    print(f" 采样日: {len(EVAL_DATES)} 天 ({EVAL_DATES[0]} ~ {EVAL_DATES[-1]})")
    print(f" 前瞻窗口: T+{FORWARD_DAYS}")
    print(f" 股票文件: {len(files)}")
    print(f" 并发: {cpu_count()} 进程")
    print(f"{'='*60}\n")

    with Pool(cpu_count()) as pool:
        raw = pool.map(score_stock, files)

    all_results = [r for batch in raw for r in batch]
    print(f"\n✅ 扫描完成，共 {len(all_results)} 笔有效信号 (score >= {SCORE_THRESHOLD})")

    if all_results:
        df = pd.DataFrame(all_results)
        df.to_csv(OUTPUT_CSV, index=False, float_format='%.4f')
        print(f"💾 数据已保存: {OUTPUT_CSV}")

        # Quick summary
        print(f"\n{'='*60}")
        print(" 快速分层预览:")
        print(f"{'='*60}")
        for lo, hi, label in [(60, 70, '60-69'), (70, 80, '70-79'), (80, 85, '80-84'), (85, 95, '85-94'), (95, 200, '95+')]:
            sub = df[(df['score'] >= lo) & (df['score'] < hi)]
            if len(sub) == 0:
                continue
            wr = (sub['forward_ret'] > 0).mean()
            mr = sub['forward_ret'].mean()
            print(f"  [{label:>5}] {len(sub):>5} 笔 | 胜率 {wr:.1%} | 均收益 {mr:+.2%} | MFE {sub['MFE'].mean():.2%}")

    print(f"\n运行 score_decile_analysis.py 生成完整报告。")


if __name__ == '__main__':
    main()
