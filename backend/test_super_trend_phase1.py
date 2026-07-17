"""
Super Trend策略：第一阶段完整测试
整合扫描、特征提取、数据切片功能（全部使用真实数据）
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from super_trend_scanner_v1 import (
    scan_and_build_episodes, scan_single_stock, build_episodes,
    _load_market_index, EPISODE_DIR, OUTPUT_BASE_DIR,
)
from super_trend_data_snapshot import EpisodeCollection
from data_handler import get_full_data_with_indicators


def test_complete_pipeline():
    """端到端测试：真实扫描 → 特征提取 → 数据切片 → 训练数据"""
    print("=== Super Trend 第一阶段完整测试（真实数据） ===")

    stock_code = 'sz000002'
    end_date = datetime.now().strftime('%Y-%m-%d')

    # 1. 扫描 + 切片一步完成
    print(f"\n1. 扫描 {stock_code} 并生成数据切片...")
    candidates, collection = scan_and_build_episodes(stock_code, end_date=end_date)

    if not candidates:
        print(f"  {stock_code} 未发现候选点，尝试备选股票...")
        for alt in ['sh600036', 'sh601318', 'sz000001']:
            print(f"  尝试 {alt}...")
            candidates, collection = scan_and_build_episodes(alt, end_date=end_date)
            if candidates:
                stock_code = alt
                break

    if not candidates:
        print("所有测试股票均未发现候选点，请检查数据源。")
        return None, None, None

    pos = sum(1 for c in candidates if c['is_positive'])
    neg = len(candidates) - pos
    print(f"  扫描完成: {len(candidates)} 个候选点（正样本: {pos}, 假突破: {neg}）")
    print(f"  切片数量: {len(collection.episodes)}")

    # 2. 保存切片
    print(f"\n2. 保存数据切片...")
    collection.save_all('test_episodes.pkl')

    # 3. 生成训练数据
    print(f"\n3. 生成训练数据...")
    X, y = collection.get_training_data()

    if len(X) > 0:
        print(f"  训练数据: {len(X)} 个样本")
        print(f"  特征维度: {X.shape[1]} 个特征")
        print(f"  正样本比例: {y.mean():.1%}")

        nan_count = X.isna().sum().sum()
        if nan_count > 0:
            print(f"  NaN 数量: {nan_count}（LightGBM 自行处理）")

        print(f"\n  特征示例:")
        for col in X.columns[:5]:
            val = X[col].iloc[0]
            print(f"    {col}: {val:.4f}" if pd.notna(val) else f"    {col}: NaN")

    # 4. 验证 T+1 和大盘上下文
    print(f"\n4. 验证 EpisodeSnapshot 回测字段...")
    ep0 = collection.episodes[0]
    print(f"  股票: {ep0.stock_code}")
    print(f"  T0日期: {ep0.t0_date}")
    print(f"  日线窗口: {len(ep0.raw_data['daily'])} 天")

    t1_gap = ep0.meta.get('t1_gap_up_pct', np.nan)
    t1_low = ep0.meta.get('t1_low_pct', np.nan)
    print(f"  T+1跳空: {t1_gap:.2%}" if pd.notna(t1_gap) else "  T+1跳空: N/A")
    print(f"  T+1最低: {t1_low:.2%}" if pd.notna(t1_low) else "  T+1最低: N/A")

    mkt_ret = ep0.meta.get('market_idx_return', np.nan)
    mkt_code = ep0.meta.get('market_code', 'N/A')
    print(f"  大盘({mkt_code}): {mkt_ret:.2%}" if pd.notna(mkt_ret) else f"  大盘({mkt_code}): N/A")

    # 5. 保存训练数据
    print(f"\n5. 保存训练数据...")
    if len(X) > 0 and len(y) > 0:
        training_data = X.copy()
        training_data['target'] = y
        training_path = os.path.join(OUTPUT_BASE_DIR, 'super_trend_training_data.csv')
        training_data.to_csv(training_path, index=False)
        print(f"  训练数据已保存: {training_path}")

    # 6. 总结
    print(f"\n{'=' * 50}")
    print(f"第一阶段功能测试完成!")
    print(f"  数据扫描: {stock_code} → {len(candidates)} 个候选点")
    print(f"  数据切片: {len(collection.episodes)} 个 EpisodeSnapshot")
    print(f"  特征维度: {X.shape[1] if len(X) > 0 else 0}")
    print(f"  训练样本: {len(X)} (正: {int(y.sum())}, 负: {len(y) - int(y.sum())})")
    print(f"{'=' * 50}")

    return collection, X, y


if __name__ == "__main__":
    try:
        result = test_complete_pipeline()
        print("\n✅ 第一阶段测试成功完成!")
    except Exception as e:
        import traceback
        print(f"\n❌ 测试失败: {e}")
        traceback.print_exc()
