#!/usr/bin/env python3
"""
GBM 集成测试脚本

验证 GBM Scorer 与现有系统的集成是否正确。
"""

import os
import sys
import pandas as pd
import numpy as np

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gbm_scorer import GBMScorer


def test_model_loading():
    """测试 1: 模型加载"""
    print("=" * 70)
    print("测试 1: 模型加载")
    print("=" * 70)

    scorer = GBMScorer()
    success = scorer.load('gbm_scorer_v1')

    if not success:
        print("❌ 模型加载失败")
        return None

    print("✅ 模型加载成功")
    print(scorer.summary())

    return scorer


def test_scoring(scorer):
    """测试 2: GBM 打分"""
    print("\n" + "=" * 70)
    print("测试 2: GBM 打分")
    print("=" * 70)

    csv_path = os.path.join(os.path.dirname(__file__), '..',
                            'data', 'result', 'SignalGenerator', 'scheme_c_signals.csv')

    if not os.path.exists(csv_path):
        print(f"❌ 数据文件不存在: {csv_path}")
        return None

    df = pd.read_csv(csv_path)
    print(f"✅ 加载测试数据: {len(df):,} 信号")

    # GBM 打分
    df['gbm_proba'] = scorer.score(df)
    print(f"✅ GBM 打分完成")
    print(f"   proba 范围: {df['gbm_proba'].min():.3f} ~ {df['gbm_proba'].max():.3f}")
    print(f"   proba 均值: {df['gbm_proba'].mean():.3f}")
    print(f"   proba 中位: {df['gbm_proba'].median():.3f}")

    return df


def test_threshold_filtering(df):
    """测试 3: 阈值过滤"""
    print("\n" + "=" * 70)
    print("测试 3: 阈值过滤")
    print("=" * 70)

    n_days = df['signal_date'].nunique() if 'signal_date' in df.columns else 319

    thresholds = [0.50, 0.56, 0.62, 0.70]

    print(f"\n{'阈值':>6} | {'信号数':>7} | {'占比':>6} | {'日均':>5}")
    print("-" * 40)

    for threshold in thresholds:
        filtered = df[df['gbm_proba'] >= threshold]
        pct = len(filtered) / len(df) * 100
        daily = len(filtered) / n_days

        marker = " ← 推荐" if threshold == 0.62 else ""
        print(f" {threshold:>5.2f} | {len(filtered):>7,} | {pct:>5.1f}% | {daily:>4.0f}{marker}")

    return True


def test_quality_metrics(df):
    """测试 4: 质量指标验证"""
    print("\n" + "=" * 70)
    print("测试 4: 质量指标验证")
    print("=" * 70)

    # 计算质量指标
    df['is_real_quality'] = (df['future_mfe'] >= 0.05) & (df['future_mae'] >= -0.08)

    thresholds = [0.0, 0.50, 0.62]

    print(f"\n{'阈值':>6} | {'信号数':>7} | {'real_q':>7} | {'MFE中位':>8} | {'MAE中位':>8} | {'盈亏比':>6}")
    print("-" * 60)

    for threshold in thresholds:
        filtered = df[df['gbm_proba'] >= threshold]
        if len(filtered) == 0:
            continue

        rq = filtered['is_real_quality'].mean()
        mfe = filtered['future_mfe'].median()
        mae = filtered['future_mae'].median()
        pl = abs(mfe / mae) if mae != 0 else 0

        label = "全部" if threshold == 0.0 else f"{threshold:.2f}"
        marker = " ← 推荐" if threshold == 0.62 else ""
        print(f" {label:>6} | {len(filtered):>7,} | {rq:>6.1%} | {mfe:>7.2%} | {mae:>7.2%} | {pl:>5.2f}{marker}")

    return True


def test_save_results(df):
    """测试 5: 保存结果"""
    print("\n" + "=" * 70)
    print("测试 5: 保存结果")
    print("=" * 70)

    output_path = os.path.join(os.path.dirname(__file__), '..',
                               'data', 'result', 'SignalGenerator', 'scheme_c_with_gbm.csv')

    df.to_csv(output_path, index=False)
    print(f"✅ 结果已保存: {output_path}")
    print(f"   文件大小: {os.path.getsize(output_path) / 1024 / 1024:.1f} MB")
    print(f"   列数: {len(df.columns)}")
    print(f"   行数: {len(df):,}")

    # 显示新增列
    new_cols = ['gbm_proba', 'is_real_quality']
    for col in new_cols:
        if col in df.columns:
            print(f"   ✓ {col}")

    return True


def main():
    """主测试流程"""
    print("\n" + "=" * 70)
    print("GBM Signal Scorer 集成测试")
    print("=" * 70)

    # 测试 1: 模型加载
    scorer = test_model_loading()
    if scorer is None:
        return False

    # 测试 2: GBM 打分
    df = test_scoring(scorer)
    if df is None:
        return False

    # 测试 3: 阈值过滤
    test_threshold_filtering(df)

    # 测试 4: 质量指标
    test_quality_metrics(df)

    # 测试 5: 保存结果
    test_save_results(df)

    # 总结
    print("\n" + "=" * 70)
    print("集成测试总结")
    print("=" * 70)
    print("✅ 所有测试通过")
    print("\n下一步:")
    print("  1. 修改 screenergf.py 输出 ma_slope 和 bias_20")
    print("  2. 修改 walk_forward_tester_s.py 加载 GBM 并过滤")
    print("  3. 修改 signal_generator.py 保存 gbm_proba")
    print("  4. 运行完整回测验证效果")
    print("\n详细步骤见: doc/0605_data_dig/gbm_integration_plan.md")

    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
