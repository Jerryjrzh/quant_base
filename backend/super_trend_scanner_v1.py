"""
Super Trend策略：历史数据扫描与T0定位脚本
使用与screenergf.py相同的配置和环境
"""

import os
import glob
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from multiprocessing import Pool, cpu_count
import warnings
warnings.filterwarnings('ignore')

# 导入与screenergf.py相同的模块
import data_loader
from data_handler import get_full_data_with_indicators
import indicators
from super_trend_feature_extractor import extract_all_features
from super_trend_data_snapshot import EpisodeSnapshot, EpisodeCollection

OUTPUT_BASE_DIR = os.path.join("data", "result", "super_trend")
EPISODE_DIR = os.path.join(OUTPUT_BASE_DIR, "episodes")

os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
os.makedirs(EPISODE_DIR, exist_ok=True)
# ================================================================
# 配置参数 — 基于 133万异动日 EDA 分布倒推（2026-06-10）
# ================================================================
MIN_DATA_DAYS = 100
EVAL_DAYS = 22              # MFE/MAE 评估窗口（22交易日 ≈ 1自然月，EDA分析维度）
FUTURE_DAYS = 60           # Episode 特征提取窗口（60交易日，保持数据充足）
MIN_GAIN = 0.51            # 22d MFE P95=50.62%，正样本取 top 5%
MAX_DRAWDOWN = -0.25       # 22d MAE P5=-26.55%，容忍极端洗盘
T0_LOOKBACK_WINDOW = 8

# 板块差异化正样本阈值（EDA 第三节：主板 P95~45%，创/科~54%）
BOARD_MIN_GAIN = {
    'main_sh': 0.43,       # 沪主板 10%涨跌幅，22d MFE P95=43.38%
    'main_sz': 0.47,       # 深主板 10%涨跌幅，22d MFE P95=46.67%
    'chinext': 0.54,       # 创业板 20%涨跌幅，22d MFE P95=54.24%
    'star':    0.53,       # 科创板 20%涨跌幅，22d MFE P95=53.05%
    'bse':     1.06,       # 北交所 30%涨跌幅，22d MFE P95=106.25%
}
USE_BOARD_SPECIFIC_GAIN = True  # False 则统一用全局 MIN_GAIN

# 负样本（假突破）阈值
NEG_MIN_DAILY_GAIN = 0.03  # 异动日涨幅>=3%（放宽采集，与异动扫描器对齐）
NEG_MAX_FUTURE_GAIN = 0.10 # 22d MFE P50=9.97%，负样本取 bottom 50%
ANOMALY_MIN_VOL_RATIO = 1.5  # 量比>=1.5（与异动扫描器 OR 触发条件对齐）


def _get_t0_date(df, idx):
    """安全获取日期，兼容 DatetimeIndex 和普通 Index"""
    return df.iloc[idx].name if hasattr(df.iloc[idx], 'name') else df.index[idx]


def _classify_market(stock_code):
    """板块分类，用于差异化正样本阈值"""
    if stock_code.startswith('sh60'):
        return 'main_sh'
    elif stock_code.startswith('sz00'):
        return 'main_sz'
    elif stock_code.startswith('sz30'):
        return 'chinext'
    elif stock_code.startswith('sh68'):
        return 'star'
    elif stock_code.startswith('bj92') or stock_code.startswith('bj8'):
        return 'bse'
    return 'other'


def _get_effective_min_gain(market_type):
    """根据板块返回有效正样本阈值"""
    if USE_BOARD_SPECIFIC_GAIN:
        return BOARD_MIN_GAIN.get(market_type, MIN_GAIN)
    return MIN_GAIN


def scan_single_stock(stock_code, end_date=None):
    """扫描单只股票，同时采集正样本（真主升浪）和高价值负样本（假突破）"""
    try:
        print(f"扫描: {stock_code}")
        
        df = get_full_data_with_indicators(stock_code, end_date=end_date)
        
        if df is None or len(df) < MIN_DATA_DAYS + FUTURE_DAYS:
            return []
        
        candidates = []
        seen_t0_indices = set()
        market_type = _classify_market(stock_code)
        effective_min_gain = _get_effective_min_gain(market_type)

        for i in range(MIN_DATA_DAYS, len(df) - FUTURE_DAYS):
            t0_price = df.iloc[i]['close']
            if t0_price <= 0.01:
                continue

            # 过滤停牌（成交量为0的死K线）
            if df.iloc[i]['volume'] == 0:
                continue

            prev_price = df.iloc[i - 1]['close'] if i > 0 else t0_price
            if prev_price <= 0.01:
                continue
            daily_gain = (t0_price / prev_price) - 1.0

            # 量比（与异动扫描器对齐：涨幅>=3% OR 量比>=1.5 才进入评估）
            vol_window = df.iloc[max(0, i - 20):i]['volume']
            avg_vol = vol_window.mean() if len(vol_window) > 0 else 1
            vol_ratio = df.iloc[i]['volume'] / avg_vol if avg_vol > 0 else 1.0
            if daily_gain < NEG_MIN_DAILY_GAIN and vol_ratio < ANOMALY_MIN_VOL_RATIO:
                continue

            # 确保 FUTURE_DAYS 窗口数据充足（供 episode 特征提取）
            future_full = df.iloc[i + 1:i + FUTURE_DAYS + 1]
            if len(future_full) < FUTURE_DAYS:
                continue

            # MFE/MAE 用 EVAL_DAYS(22天) 窗口评估，匹配 EDA 分析维度
            eval_window = df.iloc[i + 1:i + 1 + EVAL_DAYS]
            eval_high = eval_window['high'].max()
            eval_low = eval_window['low'].min()
            mfe = max(0.0, (eval_high / t0_price) - 1.0)
            mae = min(0.0, (eval_low / t0_price) - 1.0)

            # === 打标逻辑 ===
            is_positive = False
            is_valuable_negative = False

            # 正样本：22天MFE超板块P95 + 回撤可控
            if mfe >= effective_min_gain and mae >= MAX_DRAWDOWN:
                is_positive = True

            # 负样本：22天MFE低于中位数（假突破）
            elif mfe < NEG_MAX_FUTURE_GAIN:
                is_valuable_negative = True
            
            # 既非起爆点也非假突破 → 跳过（摒弃无价值的垃圾时间）
            if not is_positive and not is_valuable_negative:
                continue
            
            # 正样本：向前回溯找到真正起爆点T0
            t0_idx = i
            trigger_vol_ratio = vol_ratio
            if is_positive:
                for lookback in range(1, min(T0_LOOKBACK_WINDOW, i) + 1):
                    idx = i - lookback
                    current = df.iloc[idx]
                    prev = df.iloc[idx - 1] if idx > 0 else current
                    prev_close = prev['close']
                    if prev_close <= 0.01:
                        continue
                    price_change = (current['close'] / prev_close) - 1.0
                    vol_20d_avg = df.iloc[max(0, idx - 20):idx]['volume'].mean()
                    vol_ratio = current['volume'] / vol_20d_avg if vol_20d_avg > 0 else 1.0
                    if price_change > 0.03 and vol_ratio > 1.5:
                        t0_idx = idx
                        break
            
            # T0 去重：同一主升浪产生的重复起爆点只保留第一个
            if t0_idx in seen_t0_indices:
                continue
            seen_t0_indices.add(t0_idx)
            
            # 盲区2：提前计算 T+1 撮合数据，供后续 EpisodeSnapshot 和回测直接使用
            t0_close = df.iloc[t0_idx]['close']
            t1_idx = min(len(df) - 1, t0_idx + 1)
            t1_open = df.iloc[t1_idx]['open']
            t1_low = df.iloc[t1_idx]['low']
            t1_gap_up_pct = (t1_open / t0_close) - 1.0 if t0_close > 0.01 else np.nan
            t1_low_pct = (t1_low / t0_close) - 1.0 if t0_close > 0.01 else np.nan
            
            candidates.append({
                'stock_code': stock_code,
                't0_date': _get_t0_date(df, t0_idx),
                't0_price': df.iloc[t0_idx]['close'],
                't0_idx': t0_idx,
                't0_volume': df.iloc[t0_idx]['volume'],
                'daily_gain': daily_gain,
                'vol_ratio': trigger_vol_ratio,
                'future_mfe': mfe,
                'future_mae': mae,
                'mfe_pct': mfe * 100,
                'mae_pct': mae * 100,
                'is_positive': is_positive,
                'sample_type': 'positive' if is_positive else 'fake_breakout',
                # T+1 微观撮合数据（回测判断"能否上车"）
                't1_gap_up_pct': t1_gap_up_pct,
                't1_low_pct': t1_low_pct,
            })
        
        if candidates:
            pos = sum(1 for c in candidates if c['is_positive'])
            neg = len(candidates) - pos
            print(f"  ✓ 发现 {pos} 个正样本 + {neg} 个假突破负样本")
        
        return candidates
        
    except Exception as e:
        print(f"  错误: {e}")
        return []

def get_stock_list_from_dir(market_dir):
    """从目录获取股票列表"""
    stocks = []
    for filename in os.listdir(market_dir):
        if filename.endswith('.day'):
            stock_code = filename.replace('.day', '')
            stocks.append(stock_code)
    return stocks

def main():
    """单线程测试版：扫描 + 生成真实数据切片"""
    print("=== Super Trend 主升浪扫描器（含切片生成） ===")
    
    test_stocks = [
        'sh000001',  # 上证指数
        'sz399001',  # 深证成指
        'sh600036',  # 招商银行
        'sz000002',  # 万科A
        'sh601318',  # 中国平安
    ]
    
    all_candidates = []
    all_episodes = EpisodeCollection(data_dir=EPISODE_DIR)
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    # 预加载大盘指数（只加载一次，避免重复 IO）
    df_sh_index = _load_market_index('sh000001', end_date=end_date)
    df_sz_index = _load_market_index('sz399001', end_date=end_date)
    
    for stock_code in test_stocks:
        df_market = df_sh_index if stock_code.startswith('sh') else df_sz_index
        candidates, collection = scan_and_build_episodes(
            stock_code, end_date=end_date, df_market=df_market
        )
        all_candidates.extend(candidates)
        for ep in collection.episodes:
            all_episodes.add_episode(ep)
    
    # 保存候选点 CSV
    _save_and_report(all_candidates, os.path.join(OUTPUT_BASE_DIR, 'super_trend_candidates_v1.csv'))
    
    # 保存 Episode 切片
    if all_episodes.episodes:
        all_episodes.save_all('episodes_v1.pkl')
        
        # 生成训练数据
        X, y = all_episodes.get_training_data()
        if len(X) > 0:
            training_data = X.copy()
            training_data['target'] = y
            training_path = os.path.join(OUTPUT_BASE_DIR, 'super_trend_training_data.csv')
            training_data.to_csv(training_path, index=False)
            
            summary = all_episodes.get_summary()
            print(f"\n=== 切片生成完成 ===")
            print(f"总切片数: {summary['total_episodes']}")
            print(f"正样本: {summary['positive_count']}, 负样本: {summary['negative_count']}")
            print(f"正样本比例: {summary['positive_ratio']:.1%}")
            print(f"特征维度: {X.shape[1]}")
            print(f"训练数据已保存: {training_path}")
    else:
        print("\n未生成任何数据切片")


def _worker_wrapper(stock_code):
    """多进程 worker：扫描 + 生成切片，子进程内独立落盘避免 IPC 传输大对象"""
    end_date = datetime.now().strftime('%Y-%m-%d')
    try:
        candidates, collection = scan_and_build_episodes(
            stock_code, end_date=end_date, df_market=None
        )
        # 子进程直接落盘，每个有候选的股票生成独立 .pkl
        if collection and collection.episodes:
            collection.save_all(f"episodes_{stock_code}.pkl")
        return candidates
    except Exception as e:
        print(f"[{stock_code}] 处理异常: {e}")
        return []


def _get_all_stock_codes():
    """从 VIPDOC 目录动态获取全市场股票代码"""
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = (
        glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day"))
        + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
        + glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day"))
    )
    filtered_stocks = []
    allowed_prefixes = ('sh60', 'sh68', 'sz00', 'sz30', 'bj92', 'bj8')
    for f in files:
        stock_code = os.path.basename(f).replace('.day', '')
        if any(stock_code.startswith(prefix) for prefix in allowed_prefixes):
            filtered_stocks.append(stock_code)
    return filtered_stocks


def _load_market_index(market_code='sh000001', end_date=None):
    """
    加载大盘指数数据，供 EpisodeSnapshot 的 df_market 参数使用。
    在 main() 中调用一次，避免每只股票重复加载同一份指数数据。
    返回 DataFrame 或 None（加载失败时）。
    """
    try:
        df = get_full_data_with_indicators(market_code, end_date=end_date)
        return df
    except Exception as e:
        print(f"  [警告] 无法加载大盘指数 {market_code}: {e}")
        return None


def build_episodes(candidates, df, df_market=None):
    """
    桥接函数：将扫描器产出的候选点字典 → 特征提取 → EpisodeSnapshot 切片。
    这是扫描与训练之间缺失的关键一环。

    参数:
        candidates: scan_single_stock() 返回的候选点列表
        df: 该股票的完整日线 DataFrame（含指标列）
        df_market: 对应大盘指数 DataFrame（可选，由 _extract_market_context 自动补全）

    返回:
        EpisodeCollection 实例
    """
    collection = EpisodeCollection(data_dir=EPISODE_DIR)

    for cand in candidates:
        t0_idx = cand['t0_idx']
        if t0_idx >= len(df):
            continue

        features = extract_all_features(df, t0_idx)

        episode = EpisodeSnapshot(
            stock_code=cand['stock_code'],
            t0_date=cand['t0_date'],
            t0_idx=t0_idx,
            df_daily=df,
            df_market=df_market,
            features=features,
            future_mfe=cand['future_mfe'],
            is_positive=cand['is_positive'],
        )
        collection.add_episode(episode)

    return collection


def scan_and_build_episodes(stock_code, end_date=None, df_market=None):
    """
    单只股票的完整流水线：加载数据 → 扫描候选点 → 特征提取 → 生成 EpisodeSnapshot 切片。
    返回 (candidates, collection) 元组。
    """
    df = get_full_data_with_indicators(stock_code, end_date=end_date)
    if df is None or len(df) < MIN_DATA_DAYS + FUTURE_DAYS:
        return [], EpisodeCollection(data_dir=EPISODE_DIR)

    candidates = scan_single_stock(stock_code, end_date=end_date)
    if not candidates:
        return [], EpisodeCollection(data_dir=EPISODE_DIR)

    collection = build_episodes(candidates, df, df_market=df_market)
    return candidates, collection


def _save_and_report(all_candidates, output_file):
    """汇总并保存扫描结果"""
    if all_candidates:
        df_results = pd.DataFrame(all_candidates)
        df_results.to_csv(output_file, index=False)
        
        print(f"\n=== 扫描完成 ===")
        print(f"总候选点: {len(all_candidates)}")
        print(f"平均涨幅: {df_results['mfe_pct'].mean():.1f}%")
        print(f"最大涨幅: {df_results['mfe_pct'].max():.1f}%")
        print(f"结果已保存: {output_file}")
        
        print(f"\n前5个候选点:")
        for i, row in df_results.head().iterrows():
            print(f"{i+1}. {row['stock_code']} - T0: {row['t0_date']} "
                  f"(涨{row['mfe_pct']:.1f}%, 撤{row['mae_pct']:.1f}%)")
    else:
        print("未发现主升浪候选点")


def main_multiprocessing(chunk_size=1000):
    """多进程全市场扫描，每 chunk_size 个切片落盘一次防止内存溢出"""
    from tqdm import tqdm

    print("=== Super Trend 全市场多进程扫描器 ===")

    # 清理旧数据：防止上一轮的 pkl/csv 污染本轮合并
    old_pkls = glob.glob(os.path.join(EPISODE_DIR, "episodes_*.pkl"))
    old_chunks = glob.glob(os.path.join(OUTPUT_BASE_DIR, "super_trend_candidates_chunk_*.csv"))
    if old_pkls or old_chunks:
        print(f"[清理] 删除 {len(old_pkls)} 个旧 episode pkl + {len(old_chunks)} 个旧 chunk csv")
        for f in old_pkls + old_chunks:
            os.remove(f)

    stocks = _get_all_stock_codes()
    if not stocks:
        print("未在 VIPDOC 目录找到股票文件，请检查路径配置。")
        return
    
    n_workers = cpu_count()
    print(f"找到 {len(stocks)} 只待扫描股票，启动 {n_workers} 核全速扫描...")
    
    all_candidates = []
    chunk_idx = 0
    
    with Pool(processes=n_workers) as pool:
        for candidates in tqdm(
            pool.imap_unordered(_worker_wrapper, stocks),
            total=len(stocks),
            desc="全市场扫描进度"
        ):
            if candidates:
                all_candidates.extend(candidates)
            
            # 每收集 chunk_size 个切片，分块落盘防止内存溢出
            if len(all_candidates) >= chunk_size * (chunk_idx + 1):
                chunk_file = f'super_trend_candidates_chunk_{chunk_idx}.csv'
                chunk_path = os.path.join(OUTPUT_BASE_DIR, chunk_file)
                pd.DataFrame(all_candidates[chunk_idx * chunk_size:]).to_csv(chunk_path, index=False)
                print(f"  [落盘] {chunk_path} ({chunk_size} 条)")
                chunk_idx += 1
        if all_candidates:
            df_results = pd.DataFrame(all_candidates)
            final_output = os.path.join(OUTPUT_BASE_DIR, 'super_trend_candidates_full.csv')
            df_results.to_csv(final_output, index=False)
    #_save_and_report(all_candidates, 'super_trend_candidates_full.csv')

    # 合并所有子进程落盘的 per-stock .pkl 切片
    _merge_episode_pkls()


def _merge_episode_pkls():
    """合并 EPISODE_DIR 下所有 episodes_*.pkl 为单一文件并导出训练 CSV"""
    import pickle

    pkl_files = glob.glob(os.path.join(EPISODE_DIR, "episodes_*.pkl"))
    if not pkl_files:
        print("\n[合并] 未找到任何 per-stock episode .pkl 文件")
        return

    merged = EpisodeCollection(data_dir=EPISODE_DIR)
    for path in pkl_files:
        try:
            with open(path, 'rb') as f:
                episodes = pickle.load(f)
            for ep in episodes:
                merged.add_episode(ep)
        except Exception as e:
            print(f"  [警告] 无法加载 {path}: {e}")

    merged_path = os.path.join(EPISODE_DIR, "episodes_merged.pkl")
    merged.save_all("episodes_merged.pkl")

    summary = merged.get_summary()
    print(f"\n=== 切片合并完成 ===")
    print(f"总切片数: {summary['total_episodes']}")
    print(f"正样本: {summary['positive_count']}, 负样本: {summary['negative_count']}")
    print(f"正样本比例: {summary['positive_ratio']:.1%}")
    print(f"合并文件: {merged_path}")

    X, y = merged.get_training_data()
    if len(X) > 0:
        training_data = X.copy()
        training_data['target'] = y
        training_path = os.path.join(OUTPUT_BASE_DIR, 'super_trend_training_data.csv')
        training_data.to_csv(training_path, index=False)
        print(f"训练数据已保存: {training_path}  特征维度: {X.shape[1]}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--full':
        main_multiprocessing()
    else:
        main()