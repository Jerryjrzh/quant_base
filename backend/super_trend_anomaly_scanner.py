"""
Super Trend策略：全量异动扫描器
不做任何正/负样本判断，只要有放量或异动全部落盘，供后续 EDA 分析倒推阈值。
"""

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import warnings
warnings.filterwarnings('ignore')

import data_loader
from data_handler import get_full_data_with_indicators

OUTPUT_DIR = os.path.join("data", "result", "super_trend", "eda")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 极低触发门槛：宁可多抓不可漏掉
MIN_DATA_DAYS = 120
ANOMALY_MIN_GAIN = 0.03       # 当日涨幅 >= 3%
ANOMALY_MIN_VOL_RATIO = 1.5   # 或量比 >= 1.5 倍

# 多时间窗口观察未来表现
FUTURE_WINDOWS = [10, 22, 60]

# 板块分类
def _classify_market(stock_code):
    if stock_code.startswith('sh60'):
        return 'main_sh'       # 沪主板 (10%涨跌幅)
    elif stock_code.startswith('sz00'):
        return 'main_sz'       # 深主板 (10%涨跌幅)
    elif stock_code.startswith('sz30'):
        return 'chinext'       # 创业板 (20%涨跌幅)
    elif stock_code.startswith('sh68'):
        return 'star'          # 科创板 (20%涨跌幅)
    elif stock_code.startswith('bj92') or stock_code.startswith('bj8'):
        return 'bse'           # 北交所 (30%涨跌幅)
    return 'other'


def _get_t0_date(df, idx):
    return df.iloc[idx].name if hasattr(df.iloc[idx], 'name') else df.index[idx]


def scan_single_stock(stock_code, end_date=None):
    """扫描单只股票的全部异动日，不做正负样本判断"""
    try:
        df = get_full_data_with_indicators(stock_code, end_date=end_date)
        if df is None or len(df) < MIN_DATA_DAYS + max(FUTURE_WINDOWS):
            return []

        market_type = _classify_market(stock_code)
        anomalies = []

        for i in range(MIN_DATA_DAYS, len(df) - max(FUTURE_WINDOWS)):
            t0_price = df.iloc[i]['close']
            if t0_price <= 0.01:
                continue

            prev_price = df.iloc[i - 1]['close'] if i > 0 else t0_price
            if prev_price <= 0.01:
                continue

            # 过滤停牌或一字死水（成交量为 0 的 K 线无异动意义）
            if df.iloc[i]['volume'] == 0:
                continue

            daily_gain = (t0_price / prev_price) - 1.0

            # 量比
            vol_window = df.iloc[max(0, i - 20):i]['volume']
            avg_vol = vol_window.mean() if len(vol_window) > 0 else 1
            vol_ratio = df.iloc[i]['volume'] / avg_vol if avg_vol > 0 else 1.0

            # 触发条件：涨幅 >= 3% 或 量比 >= 1.5
            if daily_gain < ANOMALY_MIN_GAIN and vol_ratio < ANOMALY_MIN_VOL_RATIO:
                continue

            # 所处位置：T0 收盘价相对过去 120 天最低点的涨幅
            lookback_low = df.iloc[max(0, i - 120):i]['low'].min()
            position_from_bottom = (t0_price / lookback_low - 1.0) if lookback_low > 0.01 else np.nan

            lookback_high = df.iloc[max(0, i - 120):i]['high'].max()
            position_from_top = (1.0 - t0_price / lookback_high) if lookback_high > 0.01 else np.nan

            # 未来多窗口 MFE/MAE
            record = {
                'stock_code': stock_code,
                't0_date': str(_get_t0_date(df, i)),
                'market_type': market_type,
                't0_close': t0_price,
                't0_volume': df.iloc[i]['volume'],
                'daily_gain': daily_gain,
                'vol_ratio': vol_ratio,
                'position_from_bottom': position_from_bottom,
                'position_from_top': position_from_top,
            }

            # 技术指标（如有）
            record['t0_rsi'] = df.iloc[i].get('rsi', np.nan)
            record['t0_macd'] = df.iloc[i].get('macd', np.nan)

            for w in FUTURE_WINDOWS:
                future_slice = df.iloc[i + 1:i + 1 + w]
                if len(future_slice) < w:
                    record[f'future_mfe_{w}d'] = np.nan
                    record[f'future_mae_{w}d'] = np.nan
                    continue
                future_high = future_slice['high'].max()
                future_low = future_slice['low'].min()
                # MFE 最小为 0（从未超过 T0 价格则无涨幅），MAE 最大为 0（从未跌破则无回撤）
                record[f'future_mfe_{w}d'] = max(0.0, (future_high / t0_price) - 1.0)
                record[f'future_mae_{w}d'] = min(0.0, (future_low / t0_price) - 1.0)

            anomalies.append(record)

        if anomalies:
            print(f"  {stock_code}: {len(anomalies)} 个异动日")

        return anomalies

    except Exception as e:
        print(f"  {stock_code} 错误: {e}")
        return []


def _worker(stock_code):
    return scan_single_stock(stock_code)


def _get_all_stock_codes():
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = (
        glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day"))
        + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
        + glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day"))
    )
    filtered = []
    allowed = ('sh60', 'sh68', 'sz00', 'sz30', 'bj92', 'bj8')
    for f in files:
        code = os.path.basename(f).replace('.day', '')
        if any(code.startswith(p) for p in allowed):
            filtered.append(code)
    return filtered


def main():
    from tqdm import tqdm

    print("=== Super Trend 全量异动扫描器（EDA 专用） ===")
    print(f"触发条件: daily_gain >= {ANOMALY_MIN_GAIN:.0%} 或 vol_ratio >= {ANOMALY_MIN_VOL_RATIO}")

    stocks = _get_all_stock_codes()
    if not stocks:
        print("未找到股票文件，请检查 VIPDOC 路径。")
        return

    n_workers = cpu_count()
    print(f"共 {len(stocks)} 只股票，启动 {n_workers} 核扫描...")

    all_anomalies = []

    with Pool(processes=n_workers) as pool:
        for result in tqdm(
            pool.imap_unordered(_worker, stocks),
            total=len(stocks),
            desc="全量异动扫描"
        ):
            if result:
                all_anomalies.extend(result)

    if all_anomalies:
        df_out = pd.DataFrame(all_anomalies)
        output_path = os.path.join(OUTPUT_DIR, 'all_market_anomalies.csv')
        df_out.to_csv(output_path, index=False)

        print(f"\n=== 扫描完成 ===")
        print(f"异动总数: {len(df_out)}")
        print(f"涉及股票: {df_out['stock_code'].nunique()} 只")
        print(f"时间范围: {df_out['t0_date'].min()} → {df_out['t0_date'].max()}")
        print(f"板块分布:")
        for mtype, count in df_out['market_type'].value_counts().items():
            print(f"  {mtype}: {count} ({count / len(df_out):.1%})")
        print(f"\n结果已保存: {output_path}")
    else:
        print("未发现任何异动日。")


if __name__ == "__main__":
    main()
