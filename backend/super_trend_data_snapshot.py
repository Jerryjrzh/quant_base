"""
Super Trend策略：数据切片快照机制
保存原始K线序列和特征，支持特征重构和可视化
"""

import pandas as pd
import numpy as np
import pickle
import os
from datetime import datetime, timedelta

class EpisodeSnapshot:
    """主升浪数据切片快照"""
    
    def __init__(self, stock_code, t0_date, t0_idx, df_daily,
                 df_60min=None, df_market=None,
                 features=None, future_mfe=0, is_positive=None, label=None):
        self.stock_code = stock_code
        self.t0_date = t0_date
        self.t0_idx = t0_idx
        self.future_mfe = future_mfe
        # 三分类标签：0=死水, 1=普通强势, 2=超级主升
        if label is not None:
            self.label = label
            self.is_positive = (label == 2)
        elif is_positive is not None:
            self.is_positive = is_positive
            self.label = 2 if is_positive else 0
        else:
            self.is_positive = (future_mfe > 0.50)
            self.label = 2 if self.is_positive else 0
        self.features = features or {}
        
        # 盲区1修复：日线 window_after 从 10 延长至 60，覆盖完整主升浪趋势追踪周期
        # 盲区3修复：预留 60min 接口（Phase 2 接入数据后即可启用）
        self.raw_data = {
            'daily': self._extract_daily_window(df_daily, t0_idx, window_before=20, window_after=60),
            'h1': self._extract_h1_window(df_60min, t0_idx, window_before=5, window_after=30),
        }
        
        # 盲区2修复：计算 T+1 撮合环境，用于回测判断"能否上车"
        t0_close = df_daily.iloc[t0_idx]['close']
        t1_idx = min(len(df_daily) - 1, t0_idx + 1)
        t1_open = df_daily.iloc[t1_idx]['open']
        t1_low = df_daily.iloc[t1_idx]['low']
        t1_gap_up_pct = (t1_open / t0_close) - 1.0 if t0_close > 0.01 else np.nan
        t1_low_pct = (t1_low / t0_close) - 1.0 if t0_close > 0.01 else np.nan
        
        # 盲区4修复：挂载大盘上下文（sh→上证指数，sz→深证成指）
        market_ctx = self._extract_market_context(df_daily, t0_idx, df_market)
        
        self.meta = {
            'stock_code': stock_code,
            't0_date': t0_date,
            't0_idx': t0_idx,
            'future_mfe': future_mfe,
            'is_positive': self.is_positive,
            # T+1 微观撮合数据
            't1_gap_up_pct': t1_gap_up_pct,   # 次日集合竞价跳空幅度
            't1_low_pct': t1_low_pct,          # 次日极限下探（判断能否上车）
            # 大盘贝塔上下文
            **market_ctx,
            'created_at': datetime.now().isoformat(),
        }
    
    def _extract_daily_window(self, df, t0_idx, window_before=20, window_after=10):
        """截取日线时间窗口"""
        start_idx = max(0, t0_idx - window_before)
        end_idx = min(len(df), t0_idx + window_after + 1)
        return df.iloc[start_idx:end_idx].copy()
    
    def _extract_h1_window(self, df_60min, t0_idx, window_before=5, window_after=30):
        """截取 60 分钟线时间窗口；df_60min 为 None 时返回空 DataFrame（Phase 2 待接入）"""
        if df_60min is None or df_60min.empty:
            return pd.DataFrame()
        start_idx = max(0, t0_idx - window_before)
        end_idx = min(len(df_60min), t0_idx + window_after + 1)
        return df_60min.iloc[start_idx:end_idx].copy()
    
    def _extract_market_context(self, df_daily, t0_idx, df_market=None):
        """
        提取 T0 当天的大盘贝塔上下文。
        若调用方未传 df_market，则尝试自动加载对应指数（sh→sh000001，sz→sz399001）。
        """
        ctx = {
            'market_idx_return': np.nan,
            'market_volume': np.nan,
            'market_code': None,
        }
        market_code = 'sh000001' if self.stock_code.startswith('sh') else 'sz399001'
        ctx['market_code'] = market_code
        
        if df_market is None:
            try:
                from data_handler import get_full_data_with_indicators
                t0_date = df_daily.index[t0_idx]
                end_str = t0_date.strftime('%Y-%m-%d') if hasattr(t0_date, 'strftime') else str(t0_date)
                df_market = get_full_data_with_indicators(market_code, end_date=end_str)
            except Exception:
                return ctx
        
        if df_market is None or df_market.empty:
            return ctx
        
        t0_date = df_daily.index[t0_idx]
        if t0_date in df_market.index:
            idx_row = df_market.loc[t0_date]
            prev_date_pos = df_market.index.get_loc(t0_date) - 1
            if prev_date_pos >= 0:
                prev_close = df_market.iloc[prev_date_pos]['close']
                ctx['market_idx_return'] = (
                    (idx_row['close'] / prev_close) - 1.0
                ) if prev_close > 0.01 else np.nan
            ctx['market_volume'] = idx_row.get('volume', np.nan)
        
        return ctx
    
    def to_dict(self):
        """转换为字典用于保存"""
        raw = {'daily': self.raw_data['daily'].to_dict('records')}
        if self.raw_data['h1'] is not None and not self.raw_data['h1'].empty:
            raw['h1'] = self.raw_data['h1'].to_dict('records')
        return {
            'meta': self.meta,
            'features': self.features,
            'raw_data': raw,
        }
    
    def save_to_file(self, filepath):
        """保存到文件"""
        with open(filepath, 'wb') as f:
            pickle.dump(self, f)
    
    @classmethod
    def load_from_file(cls, filepath):
        """从文件加载"""
        with open(filepath, 'rb') as f:
            return pickle.load(f)
    
    def get_feature_vector(self):
        """获取特征向量（用于机器学习），包含 t0_date 供时序切割排序"""
        vector = {}
        vector.update(self.features)
        vector.update({
            'stock_code': self.stock_code,
            't0_date': str(self.t0_date),
            'is_positive': int(self.is_positive),
            'label': self.label,
            'future_mfe': self.future_mfe
        })
        return vector
    
    def plot_summary(self):
        """打印摘要信息"""
        print(f"股票: {self.stock_code}")
        print(f"T0日期: {self.t0_date}")
        print(f"T0索引: {self.t0_idx}")
        print(f"未来涨幅: {self.future_mfe:.1%}")
        print(f"是否正样本: {'是' if self.is_positive else '否'}")
        print(f"特征数量: {len(self.features)}")
        print(f"日线窗口: {len(self.raw_data['daily'])} 天")
        h1_len = len(self.raw_data['h1']) if not self.raw_data['h1'].empty else 0
        print(f"60min窗口: {h1_len} 根（{'待接入' if h1_len == 0 else '已加载'}）")
        # T+1 撮合环境
        t1_gap = self.meta.get('t1_gap_up_pct', np.nan)
        t1_low = self.meta.get('t1_low_pct', np.nan)
        print(f"T+1跳空: {t1_gap:.2%}" if pd.notna(t1_gap) else "T+1跳空: N/A")
        print(f"T+1最低: {t1_low:.2%}" if pd.notna(t1_low) else "T+1最低: N/A")
        # 大盘上下文
        mkt_ret = self.meta.get('market_idx_return', np.nan)
        mkt_code = self.meta.get('market_code', 'N/A')
        print(f"大盘({mkt_code})当日: {mkt_ret:.2%}" if pd.notna(mkt_ret) else f"大盘({mkt_code})当日: N/A")
        
        if self.features:
            print("关键特征:")
            for key, value in list(self.features.items())[:5]:
                print(f"  {key}: {value:.4f}")

class EpisodeCollection:
    """主升浪数据切片集合管理器"""
    
    def __init__(self, data_dir='episodes_data'):
        self.data_dir = data_dir
        self.episodes = []
        
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
    
    def add_episode(self, episode):
        """添加一个切片"""
        self.episodes.append(episode)
    
    def save_all(self, filename='episodes_collection.pkl'):
        """保存所有切片到文件"""
        filepath = os.path.join(self.data_dir, filename)
        with open(filepath, 'wb') as f:
            pickle.dump(self.episodes, f)
        print(f"保存了 {len(self.episodes)} 个切片到 {filepath}")
    
    def load_all(self, filename='episodes_collection.pkl'):
        """从文件加载所有切片"""
        filepath = os.path.join(self.data_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, 'rb') as f:
                self.episodes = pickle.load(f)
            print(f"从 {filepath} 加载了 {len(self.episodes)} 个切片")
        return self.episodes
    
    def get_training_data(self):
        """获取机器学习训练数据，包含 t0_date 供时序切割排序"""
        rows = []
        y = []
        
        for episode in self.episodes:
            features = episode.get_feature_vector()
            
            # 提取数值特征 + 保留 t0_date/stock_code 元数据
            row = {}
            for key, value in features.items():
                if isinstance(value, (int, float, np.number)):
                    row[key] = value
                elif key in ('t0_date', 'stock_code'):
                    row[key] = value
            
            if row:
                rows.append(row)
                y.append(episode.label)
        
        X_df = pd.DataFrame(rows)
        y_series = pd.Series(y)
        # 仅消除 inf（停牌/除零极端值）；保留 NaN 让 LightGBM 自行寻找最优分裂方向
        X_df = X_df.replace([np.inf, -np.inf], np.nan)
        return X_df, y_series
    
    def get_summary(self):
        """获取集合摘要（三分类）"""
        if not self.episodes:
            return "集合为空"

        label_counts = {0: 0, 1: 0, 2: 0}
        for e in self.episodes:
            label_counts[e.label] = label_counts.get(e.label, 0) + 1
        total = len(self.episodes)

        return {
            'total_episodes': total,
            'label_0_count': label_counts[0],
            'label_1_count': label_counts[1],
            'label_2_count': label_counts[2],
            'label_0_ratio': label_counts[0] / total if total else 0,
            'label_1_ratio': label_counts[1] / total if total else 0,
            'label_2_ratio': label_counts[2] / total if total else 0,
            # 向后兼容
            'positive_count': label_counts[2],
            'negative_count': label_counts[0] + label_counts[1],
            'positive_ratio': label_counts[2] / total if total else 0,
        }

# 测试函数
def test_snapshot_mechanism():
    """测试数据切片机制"""
    print("=== 数据切片快照机制测试 ===")
    
    # 创建测试数据（200天，确保 window_after=60 能被完整覆盖）
    dates = pd.date_range(start='2024-01-01', periods=200, freq='D')
    df = pd.DataFrame({
        'open': 100 + np.random.randn(200).cumsum() * 1,
        'high': 102 + np.random.randn(200).cumsum() * 1.5,
        'low': 98 + np.random.randn(200).cumsum() * 1,
        'close': 100 + np.random.randn(200).cumsum() * 2,
        'volume': np.random.randint(100000, 1000000, 200),
        'rsi': 30 + np.random.rand(200) * 40,
        'macd': np.random.randn(200) * 2,
    }, index=dates)
    
    # 创建数据切片
    stock_code = 'sh600036'
    t0_idx = 50
    t0_date = df.index[t0_idx]
    future_mfe = 0.65  # 65%涨幅
    
    # 模拟特征
    features = {
        'rsi_explosion_force': 25.3,
        'macd_pit_depth': -1.8,
        'price_rebound_from_pit': 0.12,
        'days_underwater': 8,
        'days_below_ma30': 6,
    }
    
    # 创建切片
    episode = EpisodeSnapshot(stock_code, t0_date, t0_idx, df, features, future_mfe)
    
    # 显示摘要
    episode.plot_summary()
    
    # 保存和加载测试
    test_file = 'test_episode.pkl'
    episode.save_to_file(test_file)
    
    loaded_episode = EpisodeSnapshot.load_from_file(test_file)
    print(f"\n加载验证 - 股票: {loaded_episode.stock_code}, 未来涨幅: {loaded_episode.future_mfe:.1%}")
    
    # 清理测试文件
    if os.path.exists(test_file):
        os.remove(test_file)
    
    return episode

if __name__ == "__main__":
    episode = test_snapshot_mechanism()
    print("\n数据切片快照机制测试完成")