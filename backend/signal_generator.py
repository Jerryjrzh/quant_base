#!/usr/bin/env python3
"""
Signal Generator v1.0 — 全局信号捕捉器 (Signal Materialization Pipeline)

架构: Stock-First Traversal
每只股票只加载一次数据、计算一次指标，然后遍历所有交易日检查信号。
相比"按日期遍历、每天扫全市场"，减少 99% 的 I/O 和指标计算开销。

输出: master_signals.csv
包含所有评分 >= 70 的信号及其未来 7 天 OHLC 数据 (上帝视角)。

数据对齐保障 (from backtester_improve_gemini.md):
  1. 15分钟数据: 时间戳硬对齐，历史真空期安全赋 0
  2. 前复权锚点漂移: 接受差异 (策略使用比例型指标)
  3. EMA/MACD预热期: 新系统更精准 (好事)
  4. 未来7天停牌穿越: 严禁iloc，必须reindex全局交易日历
"""

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import logging

import data_loader
from adjustment_processor import AdjustmentProcessor, AdjustmentConfig

# ==========================================
# 全局配置
# ==========================================
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz', 'bj']
ADJUSTMENT_TYPE = 'forward'
START_DATE = '2025-01-01'
END_DATE = '2026-04-30'
SCORE_THRESHOLD = 70
FORWARD_DAYS = 7

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'SignalGenerator'))
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# ==========================================
# 多进程初始化
# ==========================================
def _worker_init():
    """多进程子进程初始化：预热 gbbq 缓存"""
    try:
        from gbbq_reader import read_gbbq
        read_gbbq()
    except Exception:
        pass


# ==========================================
# 交易日历
# ==========================================
def get_real_trading_days(start_date, end_date):
    """读取上证指数，获取真实交易日历（跳过周末和节假日）"""
    index_path = os.path.join(BASE_PATH, 'sh', 'lday', 'sh000001.day')
    if not os.path.exists(index_path):
        logger.warning("找不到上证指数文件，降级使用标准工作日")
        return pd.date_range(start=start_date, end=end_date, freq='B')

    df_index = data_loader.get_daily_data(index_path)
    if df_index is None:
        return pd.date_range(start=start_date, end=end_date, freq='B')

    mask = (df_index.index >= pd.to_datetime(start_date)) & \
           (df_index.index <= pd.to_datetime(end_date))
    return df_index[mask].index


# ==========================================
# 板块参数
# ==========================================
def get_board_params(stock_code):
    """根据板块返回差异化参数"""
    code = stock_code[2:] if stock_code[:2] in ('sh', 'sz', 'bj') else stock_code
    if code.startswith(('688', '689')):
        return {'target_profit': 0.15, 'stop_loss': -0.08, 'board_type': '20CM'}
    elif code.startswith('30'):
        return {'target_profit': 0.12, 'stop_loss': -0.07, 'board_type': '20CM'}
    elif code.startswith('92'):
        return {'target_profit': 0.18, 'stop_loss': -0.10, 'board_type': '30CM'}
    else:
        return {'target_profit': 0.10, 'stop_loss': -0.05, 'board_type': '10CM'}


# ==========================================
# 未来 7 天 OHLC 提取 (防停牌穿越)
# ==========================================
def extract_forward_ohlc(df, signal_date, trading_days, forward_days=7):
    """
    使用全局交易日历 reindex 提取未来 N 天 OHLC。
    停牌日数据为 NaN，MFE/MAE 自动排除 NaN 计算。
    严禁使用 iloc，防止停牌穿越引入未来函数。
    """
    signal_ts = pd.Timestamp(signal_date)
    next_days = trading_days[trading_days > signal_ts][:forward_days]

    if len(next_days) == 0:
        return None

    fwd = df.reindex(next_days)
    t0_close = df.loc[signal_ts, 'close'] if signal_ts in df.index else None
    if t0_close is None or t0_close <= 0:
        return None

    row = {}
    mfe, mae = 0.0, 0.0
    mfe_day, mae_day = 0, 0

    for i, day in enumerate(next_days, 1):
        d = fwd.loc[day]
        o = d['open'] if not pd.isna(d.get('open', np.nan)) else np.nan
        h = d['high'] if not pd.isna(d.get('high', np.nan)) else np.nan
        l = d['low'] if not pd.isna(d.get('low', np.nan)) else np.nan
        c = d['close'] if not pd.isna(d.get('close', np.nan)) else np.nan

        row[f'T{i}_Open'] = round(o, 4) if not pd.isna(o) else np.nan
        row[f'T{i}_High'] = round(h, 4) if not pd.isna(h) else np.nan
        row[f'T{i}_Low'] = round(l, 4) if not pd.isna(l) else np.nan
        row[f'T{i}_Close'] = round(c, 4) if not pd.isna(c) else np.nan

        if not pd.isna(h):
            pct = (h - t0_close) / t0_close
            if pct > mfe:
                mfe = pct
                mfe_day = i
        if not pd.isna(l):
            pct = (l - t0_close) / t0_close
            if pct < mae:
                mae = pct
                mae_day = i

    row['future_mfe'] = round(mfe, 6)
    row['future_mae'] = round(mae, 6)
    row['future_mfe_day'] = mfe_day
    row['future_mae_day'] = mae_day
    return row


# ==========================================
# 大盘环境判断
# ==========================================
_market_env_cache = {}

def get_market_env(date_str, df_index):
    """获取大盘当日环境标签（带缓存避免重复计算）"""
    if date_str in _market_env_cache:
        return _market_env_cache[date_str]

    env = "震荡"
    if df_index is not None and date_str in df_index.index:
        idx_loc = df_index.index.get_loc(date_str)
        if idx_loc > 0:
            idx_pct = (df_index['close'].iloc[idx_loc] -
                       df_index['close'].iloc[idx_loc - 1]) / \
                      df_index['close'].iloc[idx_loc - 1]
            if idx_pct > 0.01:
                env = "顺风大涨"
            elif idx_pct < -0.015:
                env = "股灾暴跌"
            elif idx_pct < -0.005:
                env = "弱势阴跌"

    _market_env_cache[date_str] = env
    return env


# ==========================================
# 核心 Worker
# ==========================================
def scan_stock_worker(args):
    """
    单只股票的全周期信号扫描 worker。
    按股票遍历所有交易日，数据只加载一次。
    """
    file_path, market, trading_days_list = args
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace(market, '')

    # 快速过滤无效股票代码
    if not (stock_code.startswith(('60', '688', '00', '30', '92')) and
            len(stock_code) == 6):
        return []

    try:
        # 1. 加载日线 + 复权 (只做一次)
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 150:
            return []

        if ADJUSTMENT_TYPE != 'none':
            adj_proc = AdjustmentProcessor(
                AdjustmentConfig(adjustment_type=ADJUSTMENT_TYPE))
            df = adj_proc.process_data(df, stock_code)

        # 2. 加载 15 分钟线 (只做一次)
        df_15m = data_loader.get_min_data(stock_code, period='15m')

        # 3. 预加载上证指数用于大盘环境判断
        df_index = None
        index_path = os.path.join(BASE_PATH, 'sh', 'lday', 'sh000001.day')
        if os.path.exists(index_path):
            df_index = data_loader.get_daily_data(index_path)

        # 4. 板块参数
        board_params = get_board_params(stock_code_full)

        # 5. 转换 trading_days 为 DatetimeIndex
        trading_days = pd.DatetimeIndex(trading_days_list)

        signals = []

        # 6. 遍历交易日
        for eval_date in trading_days:
            eval_date_str = eval_date.strftime('%Y-%m-%d')

            # 检查该日是否有数据
            if eval_date not in df.index:
                continue

            # 切片历史数据 (含当日)
            historical = df[:eval_date]
            if len(historical) < 150:
                continue

            # 15m 时间戳硬对齐：截取到当日 15:30
            m15_slice = None
            if df_15m is not None and not df_15m.empty:
                try:
                    m15_df = df_15m.copy()
                    if 'datetime' in m15_df.columns:
                        m15_df.index = pd.to_datetime(m15_df['datetime'])
                    elif not isinstance(m15_df.index, pd.DatetimeIndex):
                        m15_df.index = pd.to_datetime(m15_df.index)
                    cutoff = pd.to_datetime(f"{eval_date_str} 15:30:00")
                    m15_slice = m15_df[m15_df.index <= cutoff]
                    if len(m15_slice) < 20:
                        m15_slice = None
                except Exception:
                    m15_slice = None

            # 调用莫尔斯狙击策略
            from screenergf import apply_morse_sniper_strategy
            res = apply_morse_sniper_strategy(
                historical,
                df_15m=m15_slice,
                stock_code=stock_code_full,
                end_date=eval_date_str
            )

            if res is None or not res.get('signal'):
                continue

            score = res.get('score', 0)
            if score < SCORE_THRESHOLD:
                continue

            # ---- 信号命中，提取完整数据 ----

            # 提取特征因子
            t0_close = historical['close'].iloc[-1]
            vol_ma20_d = historical['volume'].rolling(20).mean().iloc[-1]
            row_t1 = historical.iloc[-1]

            d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
            d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
            d_lower_shadow = (min(row_t1['close'], row_t1['open']) -
                              row_t1['low']) / (row_t1['open'] + 1e-9)

            T1_U = 1 if d_pct > 0.062 else 0
            T1_D = 1 if d_pct < -0.062 else 0
            T1_L = 1 if d_vol < 0.8 else 0
            T1_B = 1 if d_lower_shadow > 0.026 else 0

            M15_U, M15_L, M15_H = 0, 0, 0
            if m15_slice is not None and len(m15_slice) > 20:
                vol_ma20_m15 = m15_slice['volume'].rolling(20).mean().iloc[-1]
                row_m15 = m15_slice.iloc[-1]
                m_pct = (row_m15['close'] - row_m15['open']) / \
                        (row_m15['open'] + 1e-9)
                m_vol = row_m15['volume'] / (vol_ma20_m15 + 1e-9)
                M15_U = 1 if m_pct > 0.0062 else 0
                M15_L = 1 if m_vol < 0.5 else 0
                M15_H = 1 if m_vol > 2.5 else 0

            ma20 = historical['close'].rolling(20).mean().iloc[-1]
            bias_20 = (t0_close - ma20) / ma20 if ma20 > 0 else 0.0

            try:
                ma20_prev = historical['close'].rolling(20).mean().iloc[-5]
                ma_slope = (ma20 - ma20_prev) / ma20_prev if ma20_prev > 0 else 0.0
            except Exception:
                ma_slope = 0.0

            market_env = get_market_env(eval_date_str, df_index)

            morse_features = (
                f"S:{score}|MKT:{market_env}|B20:{bias_20:.3f}|"
                f"T1_U:{T1_U}|T1_D:{T1_D}|T1_L:{T1_L}|T1_B:{T1_B}|"
                f"M15_U:{M15_U}|M15_L:{M15_L}|M15_H:{M15_H}"
            )

            # 形态标签
            labels = []
            if T1_U:
                labels.append('T1_U')
            elif T1_D:
                labels.append('T1_D')
            if T1_L:
                labels.append('T1_L')
            if T1_B:
                labels.append('T1_B')
            if M15_U:
                labels.append('M15_U')
            if abs(d_pct) <= 0.01:
                labels.append('T1_X')
            pattern_label = '+'.join(labels) if labels else 'neutral'

            # V4.4 定价
            v44_ok = 'v44_entry' in res
            trigger_buy = res.get('v44_entry', res.get('trigger_price', 0))
            if v44_ok:
                static_tp = res.get('v44_target', 0)
                static_sl = res.get('v44_stop', 0)
            else:
                static_tp = trigger_buy * (1 + board_params['target_profit'])
                static_sl = trigger_buy * (1 + board_params['stop_loss'])

            # 提取未来 7 天 OHLC (reindex 防停牌穿越)
            fwd = extract_forward_ohlc(df, eval_date, trading_days, FORWARD_DAYS)
            if fwd is None:
                continue

            signal = {
                'signal_date': eval_date_str,
                'stock_code': stock_code_full,
                'score': score,
                'pattern_label': pattern_label,
                'board_type': board_params['board_type'],
                'close_t0': round(float(t0_close), 4),
                'trigger_buy': round(float(trigger_buy), 4),
                'stop_loss': round(float(static_sl), 4),
                'take_profit': round(float(static_tp), 4),
                'v44_entry': round(float(res.get('v44_entry', 0)), 4) if v44_ok else np.nan,
                'v44_target': round(float(res.get('v44_target', 0)), 4) if v44_ok else np.nan,
                'v44_stop': round(float(res.get('v44_stop', 0)), 4) if v44_ok else np.nan,
                'v44_trend': res.get('v44_trend', '') if v44_ok else '',
                'v44_bias_tier': res.get('v44_bias_tier', '') if v44_ok else '',
                'v44_grade': res.get('v44_grade', '') if v44_ok else '',
                'ma_slope': round(float(ma_slope), 6),
                'bias_20': round(float(bias_20), 6),
                'morse_features': morse_features,
                'market_env': market_env,
            }
            signal.update(fwd)
            signals.append(signal)

        return signals

    except Exception as e:
        logger.error(f"处理 {stock_code_full} 失败: {e}")
        return []


# ==========================================
# 主函数
# ==========================================
def main():
    start_time = datetime.now()

    logger.info("=" * 60)
    logger.info("Signal Generator v1.0 — 全局信号捕捉器")
    logger.info(f"策略: MORSE_FACTOR_SNIPER")
    logger.info(f"日期范围: {START_DATE} ~ {END_DATE}")
    logger.info(f"评分门槛: >= {SCORE_THRESHOLD}")
    logger.info(f"前瞻窗口: {FORWARD_DAYS} 天")
    logger.info("=" * 60)

    # 1. 获取交易日历
    trading_days = get_real_trading_days(START_DATE, END_DATE)
    logger.info(f"交易日历: {len(trading_days)} 个交易日 "
                f"({trading_days[0].strftime('%Y-%m-%d')} ~ "
                f"{trading_days[-1].strftime('%Y-%m-%d')})")

    # 2. 收集所有日线文件
    all_files = []
    for market in MARKETS:
        path = os.path.join(BASE_PATH, market, 'lday', '*.day')
        files = glob.glob(path)
        all_files.extend([(f, market) for f in files])

    logger.info(f"日线文件: {len(all_files)} 个")

    # 3. 多进程扫描
    trading_days_list = list(trading_days)
    tasks = [(f, m, trading_days_list) for f, m in all_files]
    workers = cpu_count()

    logger.info(f"启动 {workers} 个并行 worker ...")

    all_signals = []
    completed = 0
    total = len(tasks)

    with Pool(processes=workers, initializer=_worker_init) as pool:
        for result in pool.imap_unordered(scan_stock_worker, tasks):
            completed += 1
            if completed % 200 == 0 or completed == total:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = completed / elapsed if elapsed > 0 else 0
                eta = (total - completed) / rate if rate > 0 else 0
                logger.info(
                    f"[{completed:04d}/{total}] "
                    f"已捕获 {len(all_signals)} 个信号 | "
                    f"速度 {rate:.1f} 只/秒 | "
                    f"预计剩余 {eta:.0f} 秒"
                )
            if result:
                all_signals.extend(result)

    # 4. 保存结果
    if all_signals:
        df_signals = pd.DataFrame(all_signals)

        # 排序: 日期 + 评分降序
        df_signals.sort_values(
            ['signal_date', 'score'], ascending=[True, False], inplace=True)

        # 保存 CSV
        csv_path = os.path.join(OUTPUT_DIR, 'master_signals.csv')
        df_signals.to_csv(csv_path, index=False, float_format='%.6f')

        # 保存 Parquet (可选，更快读取)
        try:
            pq_path = os.path.join(OUTPUT_DIR, 'master_signals.parquet')
            df_signals.to_parquet(pq_path, index=False)
            logger.info(f"Parquet 已保存: {pq_path}")
        except Exception:
            pass

        elapsed_total = (datetime.now() - start_time).total_seconds()

        logger.info("=" * 60)
        logger.info(f"扫描完成!")
        logger.info(f"  总信号数: {len(df_signals)}")
        logger.info(f"  日期覆盖: {df_signals['signal_date'].min()} ~ "
                     f"{df_signals['signal_date'].max()}")
        logger.info(f"  股票覆盖: {df_signals['stock_code'].nunique()} 只")
        logger.info(f"  评分分布: "
                     f"min={df_signals['score'].min()}, "
                     f"median={df_signals['score'].median():.0f}, "
                     f"max={df_signals['score'].max()}")
        logger.info(f"  MFE 分布: "
                     f"mean={df_signals['future_mfe'].mean():.4f}, "
                     f"median={df_signals['future_mfe'].median():.4f}")
        logger.info(f"  耗时: {elapsed_total:.1f} 秒 "
                     f"({elapsed_total / 60:.1f} 分钟)")
        logger.info(f"  输出: {csv_path}")
        logger.info("=" * 60)
    else:
        logger.warning("未捕获任何信号，请检查评分门槛和日期范围")


if __name__ == '__main__':
    main()
