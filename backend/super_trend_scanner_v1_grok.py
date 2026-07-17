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
from super_trend_feature_extractor_v2 import extract_all_v2_features
from super_trend_data_snapshot import EpisodeSnapshot, EpisodeCollection
from super_trend_label_builder import compute_path_stability_from_df
from super_trend_market_ranker import build_market_rank_cache, extract_rank_features

OUTPUT_BASE_DIR = os.path.join("data", "result", "super_trend")
EPISODE_DIR = os.path.join(OUTPUT_BASE_DIR, "episodes")

os.makedirs(OUTPUT_BASE_DIR, exist_ok=True)
os.makedirs(EPISODE_DIR, exist_ok=True)
# ================================================================
# 配置参数 — 三分类标签体系（2026-06-12 三方 review 共识）
# ================================================================
MIN_DATA_DAYS = 100
EVAL_DAYS = 22              # MFE/MAE 评估窗口（22交易日 ≈ 1自然月）
FUTURE_DAYS = 60           # Episode 特征提取窗口（60交易日）
MAX_DRAWDOWN = -0.25       # 22d MAE P5=-26.55%，容忍极端洗盘
T0_LOOKBACK_WINDOW = 8

# 三分类标签阈值
# Label 0 (死水/陷阱): 22d MFE < 10%  → 教会模型什么是坑
# Label 1 (普通强势):   10% ≤ 22d MFE < P95  → 困难负样本，填补盲区
# Label 2 (超级主升):   22d MFE ≥ P95  → 真正的起爆信号
LABEL1_THRESHOLD = 0.10    # 22d MFE P50=9.97%，Label 0 vs 1 分界线
LABEL2_GLOBAL = 0.51       # 22d MFE P95=50.62%，Label 1 vs 2 全局阈值

# 板块差异化 Label 2 阈值（EDA P95 校准值）
BOARD_MIN_GAIN = {
    'main_sh': 0.43,       # 沪主板 10%涨跌幅，22d MFE P95=43.38%
    'main_sz': 0.47,       # 深主板 10%涨跌幅，22d MFE P95=46.67%
    'chinext': 0.54,       # 创业板 20%涨跌幅，22d MFE P95=54.24%
    'star':    0.53,       # 科创板 20%涨跌幅，22d MFE P95=53.05%
    'bse':     1.06,       # 北交所 30%涨跌幅，22d MFE P95=106.25%
}
USE_BOARD_SPECIFIC_GAIN = True

# 异动触发条件（GPT/Gemini 共识：恢复原始宽松门槛，避免 T0 过晚）
ANOMALY_MIN_DAILY_GAIN = 0.03    # 涨幅>=3%
ANOMALY_MIN_VOL_RATIO = 1.5      # 量比>=1.5（OR 条件：任一满足即触发）


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
    """根据板块返回 Label 2（超级主升）阈值"""
    if USE_BOARD_SPECIFIC_GAIN:
        return BOARD_MIN_GAIN.get(market_type, LABEL2_GLOBAL)
    return LABEL2_GLOBAL


# ================================================================
# 增强特征工程（Grok review P1）
# ================================================================
def _extract_enhanced_features(df, t0_idx, df_market=None):
    """提取增强特征：均线排列、相对强度、波动率、乖离率等"""
    features = {}
    if t0_idx < 60 or t0_idx >= len(df):
        return features

    current = df.iloc[t0_idx]

    # 1. 均线多头排列强度：MA5>MA10>MA20>MA60 连续满足的天数（市场共识结构）
    ma_cols = ['ma5', 'ma10', 'ma20', 'ma60']
    if all(c in df.columns for c in ma_cols):
        alignment_days = 0
        for lookback in range(t0_idx, max(t0_idx - 20, -1), -1):
            row = df.iloc[lookback]
            if (pd.notna(row['ma5']) and pd.notna(row['ma10']) and
                pd.notna(row['ma20']) and pd.notna(row['ma60']) and
                row['ma5'] > row['ma10'] > row['ma20'] > row['ma60']):
                alignment_days += 1
            else:
                break
        features['ma_bull_alignment_days'] = alignment_days

    # 2. 乖离率 MA20（使用真正的 MA20）
    if 'ma20' in df.columns and pd.notna(current.get('ma20', np.nan)) and current['ma20'] > 0.01:
        features['bias_ma20'] = (current['close'] / current['ma20']) - 1.0

    # 3. 乖离率 MA60
    if 'ma60' in df.columns and pd.notna(current.get('ma60', np.nan)) and current['ma60'] > 0.01:
        features['bias_ma60'] = (current['close'] / current['ma60']) - 1.0

    # 4. ATR 百分位（当前 ATR 在过去 60 天的排名百分位）
    if 'atr' in df.columns and pd.notna(current.get('atr', np.nan)):
        atr_window = df['atr'].iloc[max(0, t0_idx - 60):t0_idx + 1].dropna()
        if len(atr_window) > 10:
            atr_pct = (atr_window < current['atr']).sum() / len(atr_window)
            features['atr_percentile'] = atr_pct

    # 5. 布林带宽度
    boll_cols = ['bb_upper', 'bb_lower', 'bb_middle']
    if all(c in df.columns for c in boll_cols):
        mid = current.get('bb_middle', np.nan)
        if pd.notna(mid) and mid > 0.01:
            features['boll_width'] = (current['bb_upper'] - current['bb_lower']) / mid

    # 6. 突破前连续缩量天数
    if 'volume' in df.columns:
        vol_shrink_days = 0
        for lookback in range(t0_idx - 1, max(t0_idx - 15, 0), -1):
            if lookback > 0 and df.iloc[lookback]['volume'] < df.iloc[lookback - 1]['volume']:
                vol_shrink_days += 1
            else:
                break
        features['pre_breakout_vol_shrink_days'] = vol_shrink_days

    # 7. 放量确认强度：T0 量 / 前5日均量
    if 'volume' in df.columns:
        vol_5d = df['volume'].iloc[max(0, t0_idx - 5):t0_idx].mean()
        if vol_5d > 0:
            features['vol_breakout_ratio'] = current['volume'] / vol_5d

    # 8. 价格位置百分位
    price_window = df['close'].iloc[max(0, t0_idx - 120):t0_idx + 1]
    if len(price_window) > 20:
        p_min, p_max = price_window.min(), price_window.max()
        if p_max > p_min:
            features['price_position_120d'] = (current['close'] - p_min) / (p_max - p_min)

    # 9. 个股 20 日涨幅
    if t0_idx >= 20:
        ret_20d = (current['close'] / df.iloc[t0_idx - 20]['close']) - 1.0
        features['stock_return_20d'] = ret_20d

    # 10. 换手率代理：20日平均成交量 / 120日平均成交量
    if 'volume' in df.columns and t0_idx >= 120:
        vol_20d = df['volume'].iloc[t0_idx - 20:t0_idx].mean()
        vol_120d = df['volume'].iloc[t0_idx - 120:t0_idx].mean()
        if vol_120d > 0:
            features['vol_turnover_ratio'] = vol_20d / vol_120d

    # 11. 量能百分位：当前成交量在 120 天中的排名百分位（GPT review 新增）
    if 'volume' in df.columns and t0_idx >= 120:
        vol_window = df['volume'].iloc[t0_idx - 120:t0_idx + 1]
        if len(vol_window) > 20:
            features['volume_percentile_120d'] = (vol_window < current['volume']).sum() / len(vol_window)

    # 12. 相对强弱 RS20 = 个股20日涨幅 - 大盘20日涨幅（GPT review 核心建议）
    #     严格日期对齐 + nearest-date fallback（避免交易日差异导致覆盖率过低）
    if df_market is not None and t0_idx >= 20:
        try:
            t0_date_str = str(_get_t0_date(df, t0_idx))[:10]
            start_date_str = str(_get_t0_date(df, t0_idx - 20))[:10]

            mkt_date_strs = np.array([str(d)[:10] for d in df_market.index])

            # exact match for t0
            mkt_t0_pos = None
            exact = np.where(mkt_date_strs == t0_date_str)[0]
            if len(exact) > 0:
                mkt_t0_pos = int(exact[0])
            else:
                idx = np.searchsorted(mkt_date_strs, t0_date_str)
                if idx >= len(mkt_date_strs):
                    idx = len(mkt_date_strs) - 1
                mkt_t0_pos = int(idx)

            # exact match for start, fallback to nearest
            mkt_start_pos = None
            exact = np.where(mkt_date_strs == start_date_str)[0]
            if len(exact) > 0:
                mkt_start_pos = int(exact[0])
            else:
                idx = np.searchsorted(mkt_date_strs, start_date_str)
                if idx >= len(mkt_date_strs):
                    idx = len(mkt_date_strs) - 1
                if idx > 0 and (idx == len(mkt_date_strs) or
                    abs((pd.Timestamp(mkt_date_strs[idx - 1]) - pd.Timestamp(start_date_str)).days) <
                    abs((pd.Timestamp(mkt_date_strs[idx]) - pd.Timestamp(start_date_str)).days)):
                    idx = idx - 1
                mkt_start_pos = int(idx)

            if (mkt_t0_pos is not None and mkt_start_pos is not None
                    and mkt_t0_pos > mkt_start_pos):
                mkt_ret = (df_market.iloc[mkt_t0_pos]['close'] /
                           df_market.iloc[mkt_start_pos]['close']) - 1.0
                stock_ret_20d = features.get('stock_return_20d', 0)
                features['rs_20d'] = stock_ret_20d - mkt_ret
        except Exception:
            pass

    return features


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

            # 量比（异动触发：涨幅>=3% OR 量比>=1.5，恢复原始宽松门槛）
            vol_window = df.iloc[max(0, i - 20):i]['volume']
            avg_vol = vol_window.mean() if len(vol_window) > 0 else 1
            vol_ratio = df.iloc[i]['volume'] / avg_vol if avg_vol > 0 else 1.0
            if daily_gain < ANOMALY_MIN_DAILY_GAIN and vol_ratio < ANOMALY_MIN_VOL_RATIO:
                continue

            # 确保 FUTURE_DAYS 窗口数据充足（供 episode 特征提取）
            future_full = df.iloc[i + 1:i + FUTURE_DAYS + 1]
            if len(future_full) < FUTURE_DAYS:
                continue

            # MFE/MAE 用 EVAL_DAYS(22天) 窗口评估
            eval_window = df.iloc[i + 1:i + 1 + EVAL_DAYS]
            eval_high = eval_window['high'].max()
            eval_low = eval_window['low'].min()
            mfe = max(0.0, (eval_high / t0_price) - 1.0)
            mae = min(0.0, (eval_low / t0_price) - 1.0)

            # === 三分类打标逻辑（GPT/Gemini 共识：填补 Label Gap） ===
            # Label 0: 死水/陷阱（22d MFE < 10%）
            # Label 1: 普通强势（10% ≤ MFE < P95）— 困难负样本，填补盲区
            # Label 2: 超级主升（MFE ≥ P95 + 回撤可控）
            if mfe >= effective_min_gain and mae >= MAX_DRAWDOWN:
                label = 2
            elif mfe >= LABEL1_THRESHOLD:
                label = 1
            else:
                label = 0

            # T0 回溯：恢复原始 3%+1.5x 门槛（避免 T0 偏晚）
            t0_idx = i
            trigger_vol_ratio = vol_ratio
            if label == 2:
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
            
            # Phase 3: 计算路径稳定性指标（供标签重构使用）
            path_stab = compute_path_stability_from_df(df, t0_idx, eval_days=EVAL_DAYS)

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
                'label': label,
                'is_positive': label == 2,
                # T+1 微观撮合数据（回测判断"能否上车"）
                't1_gap_up_pct': t1_gap_up_pct,
                't1_low_pct': t1_low_pct,
                # Phase 3: 路径稳定性（惩罚脉冲式冲高回落）
                'path_sharpe': path_stab['path_sharpe'],
                'path_up_capture': path_stab['path_up_capture'],
                'path_smoothness': path_stab['path_smoothness'],
                'path_return_22d': path_stab['path_return_22d'],
            })

        if candidates:
            n0 = sum(1 for c in candidates if c['label'] == 0)
            n1 = sum(1 for c in candidates if c['label'] == 1)
            n2 = sum(1 for c in candidates if c['label'] == 2)
            print(f"  ✓ Label 0/1/2 = {n0}/{n1}/{n2}")
        
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

    # 预加载大盘指数（统一使用上证综指，sz399001.day 格式异常不可用）
    df_sh_index = _load_market_index('sh000001', end_date=end_date)

    # Phase 2: 预加载全市场排名缓存
    try:
        rank_matrix = build_market_rank_cache(end_date=end_date)
        print(f"  排名矩阵已加载: {rank_matrix.shape}")
    except Exception as e:
        print(f"  [警告] 排名矩阵加载失败: {e}，跳过排名特征")
        rank_matrix = None

    for stock_code in test_stocks:
        df_market = df_sh_index
        candidates, collection = scan_and_build_episodes(
            stock_code, end_date=end_date, df_market=df_market,
            rank_matrix=rank_matrix,
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
        df_market = _load_market_index('sh000001', end_date=end_date)
        # Phase 2: 加载排名缓存（子进程独立加载，pickle 文件读取很快）
        try:
            rank_matrix = build_market_rank_cache(end_date=end_date)
        except Exception:
            rank_matrix = None
        candidates, collection = scan_and_build_episodes(
            stock_code, end_date=end_date, df_market=df_market,
            rank_matrix=rank_matrix,
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


def build_episodes(candidates, df, df_market=None, rank_matrix=None):
    """
    桥接函数：将扫描器产出的候选点字典 → 特征提取 → EpisodeSnapshot 切片。
    这是扫描与训练之间缺失的关键一环。

    参数:
        candidates: scan_single_stock() 返回的候选点列表
        df: 该股票的完整日线 DataFrame（含指标列）
        df_market: 对应大盘指数 DataFrame（可选，由 _extract_market_context 自动补全）
        rank_matrix: 全市场日涨幅排名矩阵（可选，由 build_market_rank_cache 产出）

    返回:
        EpisodeCollection 实例
    """
    collection = EpisodeCollection(data_dir=EPISODE_DIR)

    for cand in candidates:
        t0_idx = cand['t0_idx']
        if t0_idx >= len(df):
            continue

        features = extract_all_features(df, t0_idx)
        enhanced = _extract_enhanced_features(df, t0_idx, df_market=df_market)
        features.update(enhanced)

        # Phase 1: V2 时序特征（均线束、黄金坑、量能序列、价格行为）
        v2_feats = extract_all_v2_features(df, t0_idx)
        features.update(v2_feats)

        # Phase 2: 全市场排名序列特征
        if rank_matrix is not None:
            rank_feats = extract_rank_features(rank_matrix, cand['stock_code'], cand['t0_date'])
            features.update(rank_feats)

        # Phase 3: 路径稳定性指标传入 features，使其出现在训练数据 CSV 中
        for key in ('path_sharpe', 'path_up_capture', 'path_smoothness', 'path_return_22d'):
            if key in cand:
                features[key] = cand[key]

        episode = EpisodeSnapshot(
            stock_code=cand['stock_code'],
            t0_date=cand['t0_date'],
            t0_idx=t0_idx,
            df_daily=df,
            df_market=df_market,
            features=features,
            future_mfe=cand['future_mfe'],
            label=cand['label'],
        )
        collection.add_episode(episode)

    return collection


def scan_and_build_episodes(stock_code, end_date=None, df_market=None, rank_matrix=None):
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

    collection = build_episodes(candidates, df, df_market=df_market, rank_matrix=rank_matrix)
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
    print(f"Label 0 (死水):    {summary['label_0_count']:>10,} ({summary['label_0_ratio']:.1%})")
    print(f"Label 1 (普通强势): {summary['label_1_count']:>10,} ({summary['label_1_ratio']:.1%})")
    print(f"Label 2 (超级主升): {summary['label_2_count']:>10,} ({summary['label_2_ratio']:.1%})")
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