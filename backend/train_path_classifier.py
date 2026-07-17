#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 2 + 3 + 4: 小时线路径分类器训练 + 集成回测

输入:
  - doc/0613_super_trend_v2/path_labels.csv (Step 1 产出)
  - 60m 数据 (data_loader)
  - review4_final_backtest.csv (基线)

流程:
  1. 对 traded + expired 信号提取小时线特征
  2. 训练 LightGBM/RF 三分类器 (Smooth/Pullback/Failure)
  3. 对 traded 信号预测路径概率
  4. 计算 path-weighted score，对比基线 PnL

输出:
  - doc/0613_super_trend_v2/path_classifier_report.md
  - doc/0613_super_trend_v2/path_predictions.csv
"""

import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

# 兼容放在 scripts/ 或 backend/ 下
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(_SCRIPT_DIR) == 'backend':
    _BACKEND_DIR = _SCRIPT_DIR
    _PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
else:
    _PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
    _BACKEND_DIR = os.path.join(_PROJECT_ROOT, 'backend')
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import pandas as pd
import numpy as np

try:
    import lightgbm as lgb
    HAS_LGB = True
except ImportError:
    HAS_LGB = False

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score

import data_loader
from hourly_features import extract_hourly_features

DOC_DIR = os.path.join(_PROJECT_ROOT, 'doc', '0613_super_trend_v2')
REVIEW4_CSV = os.path.join(DOC_DIR, 'review4_final_backtest.csv')
LABELS_CSV = os.path.join(DOC_DIR, 'path_labels.csv')
OUTPUT_MD = os.path.join(DOC_DIR, 'path_classifier_report.md')
OUTPUT_CSV = os.path.join(DOC_DIR, 'path_predictions.csv')

TRAIN_CUTOFF = '2025-09-01'
VAL_CUTOFF = '2026-01-01'

FEATURE_COLS = [
    'ma20_slope', 'close_ma20_ratio', 'close_ma60_ratio',
    'volatility_20', 'avg_amplitude', 'gap_freq',
    'up_down_vol_ratio', 'volume_trend',
    'drawdown_depth_80', 'rebound_ratio_80',
    'new_high_freq', 'ma20_touch_freq',
    'momentum_20', 'vol_5_20_ratio',
]


def extract_features_for_signals(signals_df: pd.DataFrame,
                                 max_per_group: int = 1500) -> pd.DataFrame:
    """对一组信号提取小时线特征，返回 DataFrame"""
    results = []
    total = len(signals_df)
    t0 = time.time()
    for i, (idx, row) in enumerate(signals_df.iterrows()):
        if (i + 1) % 50 == 0 or i == 0:
            print(f"      特征提取 {i + 1}/{total} ({time.time()-t0:.0f}s) ...")
        if i >= max_per_group:
            break
        try:
            feat = extract_hourly_features(row['stock_code'], row['t0_date'])
        except Exception:
            feat = None
        if feat is None:
            continue
        feat['signal_idx'] = row.get('signal_idx', idx)
        feat['stock_code'] = row['stock_code']
        feat['t0_date'] = row['t0_date']
        feat['status'] = row.get('status', '')
        results.append(feat)
    print(f"      特征提取完成: {len(results)}/{total} 成功, 耗时 {time.time()-t0:.1f}s")
    return pd.DataFrame(results)


def run():
    print("=" * 60)
    print("  Step 2+3+4: 小时线路径分类器训练与集成")
    print("=" * 60)

    # ---- 加载基线与标签 ----
    base = pd.read_csv(REVIEW4_CSV)
    base['t0_date'] = pd.to_datetime(base['t0_date'])
    labels = pd.read_csv(LABELS_CSV)
    labels['t0_date'] = pd.to_datetime(labels['t0_date'])

    # 合并标签到基线
    merged = base.merge(
        labels[['signal_idx', 'path_label', 'path_label_name',
                'max_drawdown', 'trend_smoothness', 'final_return']],
        left_index=True, right_on='signal_idx', how='left'
    )
    print(f"  基线信号: {len(merged)}")
    print(f"  有路径标签: {merged['path_label'].notna().sum()}")

    # ---- 选择训练/评估样本: traded + expired ----
    target_statuses = ['traded', 'expired']
    sample = merged[merged['status'].isin(target_statuses) &
                    merged['path_label'].notna()].copy()
    print(f"  候选样本 (traded+expired 且有标签): {len(sample)}")

    if len(sample) < 100:
        print("  样本不足，退出")
        return

    # ---- 提取特征 ----
    print("\n  --- 提取 60m 特征 ---")
    feat_df = extract_features_for_signals(sample, max_per_group=2000)
    if len(feat_df) < 50:
        print("  成功提取特征过少，退出")
        return

    # 合并
    data = sample.merge(feat_df, on='signal_idx', how='inner', suffixes=('', '_feat'))
    print(f"  合并后样本: {len(data)}")

    # ---- 训练/验证/测试划分 (按时序) ----
    data = data.sort_values('t0_date')
    train = data[data['t0_date'] < TRAIN_CUTOFF].copy()
    val = data[(data['t0_date'] >= TRAIN_CUTOFF) &
               (data['t0_date'] < VAL_CUTOFF)].copy()
    test = data[data['t0_date'] >= VAL_CUTOFF].copy()
    print(f"  训练: {len(train)}, 验证: {len(val)}, 测试: {len(test)}")

    # 打印标签分布
    for name, split in [('训练', train), ('验证', val), ('测试', test)]:
        if len(split) > 0:
            dist = split['path_label'].value_counts().sort_index()
            print(f"    {name} 标签分布: {dict(dist)}")

    if len(train) < 30 or len(test) < 10:
        print("  划分后样本不足")
        # 继续跑，但提示

    # 确保训练集包含所有 3 个类别 (LightGBM 要求)
    train_classes = set(train['path_label'].unique())
    missing = {0, 1, 2} - train_classes
    if missing and len(val) > 0:
        print(f"  训练集缺少类别 {missing}，从验证集借用样本")
        for cls in missing:
            borrow = val[val['path_label'] == cls].head(5)
            if len(borrow) > 0:
                train = pd.concat([train, borrow], ignore_index=True)
                val = val.drop(borrow.index)
        print(f"  借用后: 训练 {len(train)}, 验证 {len(val)}")

    # ---- 训练分类器 ----
    X_train = train[FEATURE_COLS].fillna(0).values
    y_train = train['path_label'].astype(int).values
    X_test = test[FEATURE_COLS].fillna(0).values
    y_test = test['path_label'].astype(int).values

    from sklearn.preprocessing import LabelEncoder
    le = LabelEncoder()
    le.fit([0, 1, 2])  # 确保三分类都注册

    y_train_enc = le.transform(y_train).astype(np.int32)

    if HAS_LGB:
        print("\n  训练 LightGBM ...")
        clf = lgb.LGBMClassifier(
            objective='multiclass', num_class=3,
            num_leaves=31, learning_rate=0.05,
            n_estimators=200, subsample=0.8,
            colsample_bytree=0.8, random_state=42,
            verbose=-1
        )
        if len(val) > 10:
            X_val = val[FEATURE_COLS].fillna(0).values
            y_val_enc = le.transform(val['path_label'].astype(int).values).astype(np.int32)
            clf.fit(X_train, y_train_enc,
                    eval_set=[(X_val, y_val_enc)],
                    callbacks=[lgb.early_stopping(30, verbose=False)])
        else:
            clf.fit(X_train, y_train_enc)
        model_name = 'LightGBM'
    else:
        print("\n  LightGBM 不可用, 使用 RandomForest ...")
        clf = RandomForestClassifier(
            n_estimators=200, max_depth=8,
            min_samples_leaf=5, random_state=42, n_jobs=-1
        )
        clf.fit(X_train, y_train_enc)
        model_name = 'RandomForest'

    y_pred_enc = clf.predict(X_test) if len(X_test) > 0 else np.array([])
    y_pred = le.inverse_transform(y_pred_enc.astype(int)) if len(y_pred_enc) > 0 else np.array([])
    y_proba = clf.predict_proba(data[FEATURE_COLS].fillna(0).values)

    print("\n  测试集评估:")
    if len(y_test) > 0:
        print(f"    Accuracy: {accuracy_score(y_test, y_pred):.3f}")
        print(classification_report(
            y_test, y_pred,
            target_names=['Smooth', 'Pullback', 'Failure'],
            zero_division=0
        ))
    else:
        print("    (无测试集)")

    # ---- 特征重要性 ----
    if HAS_LGB:
        importances = clf.feature_importances_
    else:
        importances = clf.feature_importances_
    imp_df = pd.DataFrame({
        'feature': FEATURE_COLS,
        'importance': importances
    }).sort_values('importance', ascending=False)

    # ---- 集成: 对 traded 信号计算 path-weighted score ----
    print("\n  --- 集成回测 ---")
    traded = data[data['status'] == 'traded'].copy()
    if len(traded) < 10:
        print("  traded 样本过少")
        # 回退到全量
        traded_idx = data[data['status'] == 'traded'].index
        traded = data.loc[traded_idx].copy()

    # 取 traded 在原 base 中的信息
    traded_full = base[base['status'] == 'traded'].copy()
    traded_full = traded_full.merge(
        labels[['signal_idx', 'path_label', 'path_label_name', 'final_return']],
        left_index=True, right_on='signal_idx', how='left'
    )

    # 对 traded_full 提取特征 (如果还未提取)
    traded_feat = feat_df[feat_df['status'] == 'traded'].copy()
    if len(traded_feat) < len(traded_full) * 0.5:
        print(f"  traded 特征不足 ({len(traded_feat)}/{len(traded_full)}), 补充提取...")
        extra = extract_features_for_signals(traded_full, max_per_group=2000)
        traded_feat = pd.concat([traded_feat, extra]).drop_duplicates('signal_idx')

    traded_full = traded_full.merge(
        traded_feat.set_index('signal_idx')[FEATURE_COLS],
        left_on='signal_idx', right_index=True, how='left'
    )

    valid_mask = traded_full[FEATURE_COLS[0]].notna()
    print(f"  traded 有特征: {valid_mask.sum()}/{len(traded_full)}")

    valid_traded = traded_full[valid_mask].copy()
    X_traded = valid_traded[FEATURE_COLS].fillna(0).values
    proba_traded = clf.predict_proba(X_traded)
    pred_traded = clf.predict(X_traded)

    valid_traded['p_smooth'] = proba_traded[:, 0]
    valid_traded['p_pullback'] = proba_traded[:, 1]
    valid_traded['p_failure'] = proba_traded[:, 2]
    valid_traded['pred_path'] = pred_traded
    valid_traded['pred_path_name'] = (
        pd.Series(pred_traded).map({0: 'Smooth', 1: 'Pullback', 2: 'Failure'})
    )

    # path_quality: Smooth=1.0, Pullback=0.5, Failure=0.0
    valid_traded['path_quality'] = (
        valid_traded['p_smooth'] * 1.0 +
        valid_traded['p_pullback'] * 0.5 +
        valid_traded['p_failure'] * 0.0
    )

    # 原 operable_score (可能缺失)
    if 'operable_score' not in valid_traded.columns:
        valid_traded['operable_score'] = 1.0
    valid_traded['final_score'] = (
        valid_traded['operable_score'] * valid_traded['path_quality']
    )

    # 用原 backtest PnL (total_pnl_pct) 评估
    if 'total_pnl_pct' in valid_traded.columns:
        pnl_col = 'total_pnl_pct'
    elif 'hold_return' in valid_traded.columns:
        pnl_col = 'hold_return'
    else:
        pnl_col = None

    if pnl_col:
        valid_traded['original_pnl'] = valid_traded[pnl_col]

    valid_traded.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"  已保存 {OUTPUT_CSV}")

    # ---- 生成报告 ----
    generate_report(
        valid_traded, imp_df, model_name,
        y_test, y_pred,
        len(train), len(val), len(test),
        HAS_LGB
    )


def generate_report(traded, imp_df, model_name,
                    y_test, y_pred,
                    n_train, n_val, n_test, has_lgb):
    lines = []
    lines.append("# 小时线路径分类器报告 (Step 2+3+4)\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append(f"**模型**: {model_name}\n")
    lines.append("")

    lines.append("## 一、样本划分\n")
    lines.append(f"- 训练 (<{TRAIN_CUTOFF}): {n_train}")
    lines.append(f"- 验证 ({TRAIN_CUTOFF}~{VAL_CUTOFF}): {n_val}")
    lines.append(f"- 测试 (≥{VAL_CUTOFF}): {n_test}")
    lines.append("")

    lines.append("## 二、测试集评估\n")
    if len(y_test) > 0:
        lines.append(f"- Accuracy: {accuracy_score(y_test, y_pred):.3f}")
        lines.append(f"- 基线 (随机猜测 3 分类): 0.333")
        lines.append("")
        lines.append("```\n" + classification_report(
            y_test, y_pred,
            target_names=['Smooth', 'Pullback', 'Failure'],
            zero_division=0
        ) + "\n```")
    else:
        lines.append("无测试集\n")

    lines.append("## 三、特征重要性 (Top 10)\n")
    lines.append("| 排名 | 特征 | 重要性 |")
    lines.append("|------|------|--------|")
    for rank, (_, r) in enumerate(imp_df.head(10).iterrows(), 1):
        lines.append(f"| {rank} | {r['feature']} | {r['importance']:.3f} |")
    lines.append("")

    lines.append("## 四、traded 信号路径预测分布\n")
    lines.append("| 预测路径 | n | 占比 |")
    lines.append("|----------|---|------|")
    for name in ['Smooth', 'Pullback', 'Failure']:
        n = (traded['pred_path_name'] == name).sum()
        lines.append(f"| {name} | {n} | {n/len(traded):.1%} |")
    lines.append("")

    lines.append("## 五、路径概率与 PnL 的关系\n")
    # 按 path_quality 三分位分层
    if 'original_pnl' in traded.columns and not traded['original_pnl'].isna().all():
        traded = traded.copy()
        try:
            traded['quality_bin'] = pd.qcut(traded['path_quality'], 3,
                                            labels=['low', 'mid', 'high'],
                                            duplicates='drop')
        except ValueError:
            traded['quality_bin'] = pd.cut(traded['path_quality'], 3,
                                           labels=['low', 'mid', 'high'])
        lines.append("按 path_quality 三分位:\n")
        lines.append("| 分位 | n | 占比 | avg PnL | 胜率 | avg path_quality |")
        lines.append("|------|---|------|---------|------|-----------------|")
        for q in ['low', 'mid', 'high']:
            sub = traded[traded['quality_bin'] == q]
            if len(sub) == 0:
                continue
            lines.append(f"| {q} | {len(sub)} | {len(sub)/len(traded):.1%} | "
                         f"{sub['original_pnl'].mean():.4f} | "
                         f"{(sub['original_pnl']>0).mean():.1%} | "
                         f"{sub['path_quality'].mean():.3f} |")
        lines.append("")

        # 按预测路径分层
        lines.append("按预测路径:\n")
        lines.append("| 预测路径 | n | avg PnL | 胜率 | avg p_smooth | avg p_failure |")
        lines.append("|----------|---|---------|------|--------------|--------------|")
        for name in ['Smooth', 'Pullback', 'Failure']:
            sub = traded[traded['pred_path_name'] == name]
            if len(sub) == 0:
                continue
            lines.append(f"| {name} | {len(sub)} | {sub['original_pnl'].mean():.4f} | "
                         f"{(sub['original_pnl']>0).mean():.1%} | "
                         f"{sub['p_smooth'].mean():.3f} | "
                         f"{sub['p_failure'].mean():.3f} |")
        lines.append("")

        # 整体基线 vs path-weighted 对比 (以 path_quality 作为加权)
        baseline_avg = traded['original_pnl'].mean()
        baseline_wr = (traded['original_pnl'] > 0).mean()
        # 如果按 path_quality > 阈值过滤
        for thresh in [0.3, 0.4, 0.5, 0.6]:
            sub = traded[traded['path_quality'] >= thresh]
            if len(sub) < 10:
                continue
            lines.append(f"### 过滤阈值 path_quality ≥ {thresh}\n")
            lines.append(f"- 通过笔数: {len(sub)} ({len(sub)/len(traded):.1%})")
            lines.append(f"- 通过 avg PnL: {sub['original_pnl'].mean():.4f} "
                         f"(基线 {baseline_avg:.4f}, "
                         f"差 {sub['original_pnl'].mean()-baseline_avg:+.4f})")
            lines.append(f"- 通过 WR: {(sub['original_pnl']>0).mean():.1%} "
                         f"(基线 {baseline_wr:.1%})")
            lines.append(f"- 被过滤 avg PnL: "
                         f"{traded[traded['path_quality']<thresh]['original_pnl'].mean():.4f}")
            lines.append("")

    lines.append("## 六、结论\n")
    if 'original_pnl' in traded.columns:
        high_q = traded[traded['path_quality'] >= 0.5]
        low_q = traded[traded['path_quality'] < 0.5]
        if len(high_q) > 10 and len(low_q) > 10:
            diff = high_q['original_pnl'].mean() - low_q['original_pnl'].mean()
            if diff > 0:
                lines.append(f"- [PASS] 高 path_quality 组 avg PnL > 低组 "
                             f"({diff:+.4f})")
            else:
                lines.append(f"- [FAIL] 高 path_quality 组未显著优于低组 "
                             f"({diff:+.4f})")
        if len(y_test) > 0:
            acc = accuracy_score(y_test, y_pred)
            if acc > 0.5:
                lines.append(f"- [PASS] 测试集 Accuracy > 0.5 ({acc:.3f})")
            else:
                lines.append(f"- [FAIL] 测试集 Accuracy 不足 ({acc:.3f})")
    lines.append("")
    lines.append("**后续建议**: 若 PASS，将 path_quality 集成到主 pipeline 的 operable_score 中。")

    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"  已写入 {OUTPUT_MD}")


if __name__ == '__main__':
    run()
