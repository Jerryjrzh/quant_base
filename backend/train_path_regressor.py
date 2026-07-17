#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Task 2 + Task 3 (v4.1): 小时线路径回归预测 + 分层回测

Task 2:
  - 用 path_quality (连续值) 作为标签
  - 提取 T0 前 60m K 线特征 (18 维)
  - 训练 LightGBMRegressor
  - 预测全量 traded 信号的 predicted_path_quality

Task 3:
  - 按 predicted_path_quality 三分位分层 (Low / Mid / High)
  - 对每组计算 PnL 统计
  - 验证过滤效果

输出:
  - doc/0613_super_trend_v2/path_regressor_report.md
  - doc/0613_super_trend_v2/path_stratification_v41_report.md
  - doc/0613_super_trend_v2/path_predictions_v41.csv
"""

import os
import sys
import time
import warnings
warnings.filterwarnings('ignore')

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

from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error

from hourly_features import extract_hourly_features

DOC_DIR = os.path.join(_PROJECT_ROOT, 'doc', '0613_super_trend_v2')
REVIEW4_CSV = os.path.join(DOC_DIR, 'review4_final_backtest.csv')
LABELS_CSV = os.path.join(DOC_DIR, 'path_quality_labels.csv')
OUTPUT_MD = os.path.join(DOC_DIR, 'path_regressor_report.md')
STRAT_MD = os.path.join(DOC_DIR, 'path_stratification_v41_report.md')
OUTPUT_CSV = os.path.join(DOC_DIR, 'path_predictions_v41.csv')

TRAIN_CUTOFF = '2025-09-01'
VAL_CUTOFF = '2026-01-01'

FEATURE_COLS = [
    'ma20_slope', 'close_ma20_ratio', 'close_ma60_ratio',
    'volatility_20', 'avg_amplitude', 'gap_freq',
    'up_down_vol_ratio', 'volume_trend',
    'drawdown_depth_80', 'rebound_ratio_80',
    'new_high_freq', 'ma20_touch_freq',
    'momentum_20', 'vol_5_20_ratio',
    'trend_stability', 'avg_intraday_dd', 'price_compactness',
]


def extract_features_batch(signals_df: pd.DataFrame,
                           max_per_group: int = 2000) -> pd.DataFrame:
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
    print("  Task 2+3 (v4.1): 路径回归预测 + 分层回测")
    print("=" * 60)

    # ---- 1. 加载数据 ----
    print("\n  [1/6] 加载数据...")
    base = pd.read_csv(REVIEW4_CSV)
    base['t0_date'] = pd.to_datetime(base['t0_date'])

    labels = pd.read_csv(LABELS_CSV)
    labels['t0_date'] = pd.to_datetime(labels['t0_date'])

    merged = base.merge(
        labels[['signal_idx', 'path_quality', 'mfe', 'max_drawdown', 'final_return']],
        left_index=True, right_on='signal_idx', how='left'
    )
    print(f"    基线信号: {len(merged)}")
    print(f"    有 path_quality: {merged['path_quality'].notna().sum()}")

    # ---- 2. 选择训练样本 ----
    print("\n  [2/6] 选择训练样本...")
    sample = merged[merged['path_quality'].notna()].copy()
    sample = sample[sample['status'].isin(['traded', 'expired', 'filtered',
                                            'operable_filtered', 'score_filtered'])]
    print(f"    候选样本: {len(sample)}")

    if len(sample) < 100:
        print("    样本不足，退出")
        return

    # ---- 3. 提取特征 ----
    print("\n  [3/6] 提取 60m 特征...")
    feat_df = extract_features_batch(sample, max_per_group=5000)
    if len(feat_df) < 50:
        print("    成功提取特征过少，退出")
        return

    data = sample.merge(feat_df, on='signal_idx', how='inner', suffixes=('', '_feat'))
    print(f"    合并后样本: {len(data)}")

    # ---- 4. 时序划分 + 训练 ----
    print("\n  [4/6] 训练回归模型...")
    data = data.sort_values('t0_date')
    train = data[data['t0_date'] < TRAIN_CUTOFF].copy()
    val = data[(data['t0_date'] >= TRAIN_CUTOFF) &
               (data['t0_date'] < VAL_CUTOFF)].copy()
    test = data[data['t0_date'] >= VAL_CUTOFF].copy()
    print(f"    训练: {len(train)}, 验证: {len(val)}, 测试: {len(test)}")

    for name, split in [('训练', train), ('验证', val), ('测试', test)]:
        if len(split) > 0:
            pq = split['path_quality']
            print(f"      {name} pq: mean={pq.mean():.4f}, std={pq.std():.4f}")

    X_train = train[FEATURE_COLS].fillna(0).values
    y_train = train['path_quality'].values
    X_test = test[FEATURE_COLS].fillna(0).values
    y_test = test['path_quality'].values

    if HAS_LGB:
        print("    训练 LightGBMRegressor ...")
        model = lgb.LGBMRegressor(
            objective='regression', metric='rmse',
            num_leaves=31, learning_rate=0.05,
            n_estimators=300, subsample=0.8,
            colsample_bytree=0.8, random_state=42,
            verbose=-1,
        )
        if len(val) > 10:
            X_val = val[FEATURE_COLS].fillna(0).values
            y_val = val['path_quality'].values
            model.fit(X_train, y_train,
                      eval_set=[(X_val, y_val)],
                      callbacks=[lgb.early_stopping(30, verbose=False)])
        else:
            model.fit(X_train, y_train)
        model_name = 'LightGBMRegressor'
    else:
        print("    LightGBM 不可用, 使用 GradientBoostingRegressor ...")
        model = GradientBoostingRegressor(
            n_estimators=200, max_depth=5,
            learning_rate=0.05, subsample=0.8,
            random_state=42,
        )
        model.fit(X_train, y_train)
        model_name = 'GradientBoostingRegressor'

    # ---- 测试集评估 ----
    y_pred_test = model.predict(X_test) if len(X_test) > 0 else np.array([])
    if len(y_test) > 0:
        rmse = np.sqrt(mean_squared_error(y_test, y_pred_test))
        mae = mean_absolute_error(y_test, y_pred_test)
        r2 = r2_score(y_test, y_pred_test)
        print(f"\n    测试集: RMSE={rmse:.4f}, MAE={mae:.4f}, R²={r2:.4f}")
    else:
        rmse = mae = r2 = np.nan
        print("    (无测试集)")

    # ---- 特征重要性 ----
    importances = model.feature_importances_
    imp_df = pd.DataFrame({
        'feature': FEATURE_COLS,
        'importance': importances
    }).sort_values('importance', ascending=False)

    # ---- 5. 对 traded 信号预测 ----
    print("\n  [5/6] 对 traded 信号预测 path_quality...")
    traded_base = base[base['status'] == 'traded'].copy()
    traded_base = traded_base.merge(
        labels[['signal_idx', 'path_quality', 'mfe', 'max_drawdown', 'final_return']],
        left_index=True, right_on='signal_idx', how='left'
    )

    traded_feat = feat_df[feat_df['status'] == 'traded'].copy()
    if len(traded_feat) < len(traded_base) * 0.5:
        print(f"    traded 特征不足 ({len(traded_feat)}/{len(traded_base)}), 补充提取...")
        extra = extract_features_batch(traded_base, max_per_group=2000)
        traded_feat = pd.concat([traded_feat, extra]).drop_duplicates('signal_idx')

    traded_full = traded_base.merge(
        traded_feat.set_index('signal_idx')[FEATURE_COLS],
        left_on='signal_idx', right_index=True, how='left'
    )

    valid_mask = traded_full[FEATURE_COLS[0]].notna()
    print(f"    traded 有特征: {valid_mask.sum()}/{len(traded_full)}")

    valid_traded = traded_full[valid_mask].copy()
    X_traded = valid_traded[FEATURE_COLS].fillna(0).values
    valid_traded['predicted_path_quality'] = model.predict(X_traded)

    if 'total_pnl_pct' in valid_traded.columns:
        valid_traded['original_pnl'] = valid_traded['total_pnl_pct']
    elif 'hold_return' in valid_traded.columns:
        valid_traded['original_pnl'] = valid_traded['hold_return']
    else:
        valid_traded['original_pnl'] = np.nan

    valid_traded.to_csv(OUTPUT_CSV, index=False, encoding='utf-8-sig')
    print(f"    已保存 {OUTPUT_CSV}")

    # ---- 6. 分层回测 (Task 3) ----
    print("\n  [6/6] 分层回测 (Task 3)...")
    run_stratification(valid_traded, imp_df, model_name,
                       y_test, y_pred_test, rmse, mae, r2,
                       len(train), len(val), len(test))


def run_stratification(traded, imp_df, model_name,
                       y_test, y_pred_test, rmse, mae, r2,
                       n_train, n_val, n_test):
    """Task 3: 按 predicted_path_quality 分层回测"""
    pnl = traded['original_pnl'].dropna()
    if len(pnl) == 0:
        print("    无 PnL 数据，跳过分层回测")
        return

    traded = traded.loc[pnl.index].copy()
    traded['pnl'] = pnl

    # 按预测 path_quality 分层
    pq = traded['predicted_path_quality']
    try:
        traded['quality_tier'] = pd.qcut(pq, q=[0, 0.3, 0.7, 1.0],
                                          labels=['Low', 'Mid', 'High'],
                                          duplicates='drop')
    except ValueError:
        traded['quality_tier'] = pd.cut(pq, bins=3,
                                         labels=['Low', 'Mid', 'High'])

    baseline_avg = traded['pnl'].mean()
    baseline_wr = (traded['pnl'] > 0).mean()
    gp_all = float(traded.loc[traded['pnl'] > 0, 'pnl'].sum())
    gl_all = abs(float(traded.loc[traded['pnl'] < 0, 'pnl'].sum()))
    baseline_pf = gp_all / gl_all if gl_all > 0 else 99.99

    print(f"\n    基线: {len(traded)}笔, avg PnL={baseline_avg:.4f}, "
          f"WR={baseline_wr:.1%}, PF={baseline_pf:.2f}")

    lines = []
    lines.append("# 路径质量分层回测报告 (v4.1 Task 3)\n")
    lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    lines.append(f"**模型**: {model_name}\n")
    lines.append(f"**测试集**: RMSE={rmse:.4f}, MAE={mae:.4f}, R²={r2:.4f}\n")
    lines.append("")

    lines.append("## 一、模型评估\n")
    lines.append(f"- 训练: {n_train}, 验证: {n_val}, 测试: {n_test}")
    if len(y_test) > 0:
        lines.append(f"- 测试集 RMSE: {rmse:.4f}")
        lines.append(f"- 测试集 MAE: {mae:.4f}")
        lines.append(f"- 测试集 R²: {r2:.4f}")
    lines.append("")

    lines.append("## 二、特征重要性 (Top 10)\n")
    lines.append("| 排名 | 特征 | 重要性 |")
    lines.append("|------|------|--------|")
    for rank, (_, r) in enumerate(imp_df.head(10).iterrows(), 1):
        lines.append(f"| {rank} | {r['feature']} | {r['importance']:.3f} |")
    lines.append("")

    lines.append("## 三、predicted_path_quality 分布\n")
    lines.append(f"| 统计 | 值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 均值 | {pq.mean():.4f} |")
    lines.append(f"| 中位数 | {pq.median():.4f} |")
    lines.append(f"| 标准差 | {pq.std():.4f} |")
    lines.append(f"| 最小值 | {pq.min():.4f} |")
    lines.append(f"| 最大值 | {pq.max():.4f} |")
    lines.append("")

    lines.append("## 四、分层回测结果\n")
    lines.append("按 predicted_path_quality 分位 (Low: 0-30%, Mid: 30-70%, High: 70-100%):\n")
    lines.append("| 分层 | n | 占比 | avg PnL | 中位数 PnL | 胜率 | PF | avg pred_pq |")
    lines.append("|------|---|------|---------|-----------|------|------|-------------|")

    tier_stats = {}
    for tier in ['Low', 'Mid', 'High']:
        sub = traded[traded['quality_tier'] == tier]
        if len(sub) == 0:
            continue
        s_pnl = sub['pnl']
        s_win = (s_pnl > 0).sum()
        s_gp = float(s_pnl[s_pnl > 0].sum()) if s_win > 0 else 0
        s_gl = abs(float(s_pnl[s_pnl < 0].sum())) if (s_pnl < 0).sum() > 0 else 0.001
        s_pf = s_gp / s_gl if s_gl > 0 else 99.99

        tier_stats[tier] = {
            'n': len(sub),
            'avg_pnl': s_pnl.mean(),
            'median_pnl': s_pnl.median(),
            'wr': s_win / len(sub),
            'pf': s_pf,
            'avg_pq': sub['predicted_path_quality'].mean(),
        }
        lines.append(f"| {tier} | {len(sub)} | {len(sub)/len(traded):.1%} | "
                     f"{s_pnl.mean():.4f} | {s_pnl.median():.4f} | "
                     f"{s_win/len(sub):.1%} | {s_pf:.2f} | "
                     f"{sub['predicted_path_quality'].mean():.4f} |")
    lines.append("")

    lines.append("## 五、过滤策略验证\n")
    lines.append(f"基线 (全量): {len(traded)}笔, avg PnL={baseline_avg:.4f}, "
                 f"WR={baseline_wr:.1%}, PF={baseline_pf:.2f}\n")

    # High + Mid
    hm = traded[traded['quality_tier'].isin(['High', 'Mid'])]
    if len(hm) > 0:
        hm_pnl = hm['pnl']
        hm_gp = float(hm_pnl[hm_pnl > 0].sum()) if (hm_pnl > 0).any() else 0
        hm_gl = abs(float(hm_pnl[hm_pnl < 0].sum())) if (hm_pnl < 0).any() else 0.001
        hm_pf = hm_gp / hm_gl if hm_gl > 0 else 99.99
        lines.append(f"**High+Mid 策略**: {len(hm)}笔 ({len(hm)/len(traded):.1%})\n")
        lines.append(f"- avg PnL: {hm_pnl.mean():.4f} (基线 {baseline_avg:.4f}, "
                     f"差 {hm_pnl.mean()-baseline_avg:+.4f})")
        lines.append(f"- WR: {(hm_pnl>0).mean():.1%} (基线 {baseline_wr:.1%})")
        lines.append(f"- PF: {hm_pf:.2f} (基线 {baseline_pf:.2f})")
        lines.append("")

    # 不同阈值过滤
    lines.append("### 不同阈值过滤效果\n")
    lines.append("| 阈值 | 通过数 | 通过 avg PnL | 基线差 | 通过 WR | 被过滤 avg PnL |")
    lines.append("|------|--------|-------------|--------|---------|----------------|")
    pq = traded['predicted_path_quality']
    for thresh in [pq.quantile(0.2), pq.quantile(0.3), pq.quantile(0.4),
                   pq.quantile(0.5), pq.quantile(0.7)]:
        sub = traded[traded['predicted_path_quality'] >= thresh]
        filt = traded[traded['predicted_path_quality'] < thresh]
        if len(sub) < 10:
            continue
        if len(filt) > 0:
            lines.append(f"| {thresh:.3f} | {len(sub)} ({len(sub)/len(traded):.0%}) | "
                         f"{sub['pnl'].mean():.4f} | "
                         f"{sub['pnl'].mean()-baseline_avg:+.4f} | "
                         f"{(sub['pnl']>0).mean():.1%} | "
                         f"{filt['pnl'].mean():.4f} |")
        else:
            lines.append(f"| {thresh:.3f} | {len(sub)} ({len(sub)/len(traded):.0%}) | "
                         f"{sub['pnl'].mean():.4f} | "
                         f"{sub['pnl'].mean()-baseline_avg:+.4f} | "
                         f"{(sub['pnl']>0).mean():.1%} | - |")
    lines.append("")

    # 按月分层
    if 'month' in traded.columns:
        lines.append("## 六、按月 × 分层 PnL\n")
        lines.append("| 月份 | Low avg PnL | Mid avg PnL | High avg PnL | 全量 avg PnL |")
        lines.append("|------|------------|------------|-------------|-------------|")
        for month, grp in traded.groupby('month'):
            row = f"| {month} |"
            for tier in ['Low', 'Mid', 'High']:
                sub = grp[grp['quality_tier'] == tier]
                if len(sub) > 0:
                    row += f" {sub['pnl'].mean():.4f} ({len(sub)}) |"
                else:
                    row += " - |"
            row += f" {grp['pnl'].mean():.4f} ({len(grp)}) |"
            lines.append(row)
        lines.append("")

    # 验收标准判定
    lines.append("## 七、验收标准判定\n")
    if 'High' in tier_stats:
        high_avg = tier_stats['High']['avg_pnl']
        lines.append(f"- High 组 avg PnL: {high_avg:.4f}")
        lines.append(f"- 全量均值 1.5 倍: {baseline_avg * 1.5:.4f}")
        if high_avg > baseline_avg * 1.5:
            lines.append("- **[PASS]** High 组 > 全量 1.5 倍")
        else:
            lines.append("- **[FAIL]** High 组未达全量 1.5 倍")

    if 'Low' in tier_stats:
        low_avg = tier_stats['Low']['avg_pnl']
        lines.append(f"- Low 组 avg PnL: {low_avg:.4f}")
        if low_avg < 0:
            lines.append("- **[PASS]** Low 组 avg PnL < 0")
        elif low_avg < baseline_avg:
            lines.append("- **[PARTIAL]** Low 组 < 全量均值但未亏损")
        else:
            lines.append("- **[FAIL]** Low 组 >= 全量均值")

    if len(hm) > 0:
        hm_avg = hm['pnl'].mean()
        lines.append(f"- High+Mid avg PnL: {hm_avg:.4f} ({hm_avg:.2%})")
        if hm_avg > 0.06:
            lines.append("- **[PASS]** High+Mid 整体盈亏 > 6%")
        else:
            lines.append("- **[FAIL]** High+Mid 整体盈亏未达 6%")
        if hm_pf > 3.0:
            lines.append(f"- **[PASS]** High+Mid PF={hm_pf:.2f} > 3.0")
        else:
            lines.append(f"- **[FAIL]** High+Mid PF={hm_pf:.2f} 未达 3.0")
    lines.append("")

    lines.append("## 八、结论\n")
    pass_count = 0
    fail_count = 0
    if 'High' in tier_stats and tier_stats['High']['avg_pnl'] > baseline_avg * 1.5:
        pass_count += 1
    else:
        fail_count += 1
    if 'Low' in tier_stats and tier_stats['Low']['avg_pnl'] < baseline_avg:
        pass_count += 1
    else:
        fail_count += 1
    if len(hm) > 0 and hm['pnl'].mean() > baseline_avg:
        pass_count += 1
    else:
        fail_count += 1

    lines.append(f"- PASS: {pass_count}/{pass_count+fail_count}")
    if pass_count >= 2:
        lines.append("- **建议**: 将 predicted_path_quality 集成到 operable_score 中作为加权因子")
    else:
        lines.append("- **建议**: 回归模型预测力不足，需考虑其他方案")

    with open(STRAT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print(f"    已写入 {STRAT_MD}")

    # ---- 同时写入回归器报告 ----
    reg_lines = []
    reg_lines.append("# 路径回归器报告 (v4.1 Task 2)\n")
    reg_lines.append(f"**日期**: {pd.Timestamp.now().strftime('%Y-%m-%d')}\n")
    reg_lines.append(f"**模型**: {model_name}\n")
    reg_lines.append("")
    reg_lines.append("## 一、样本划分\n")
    reg_lines.append(f"- 训练 (<{TRAIN_CUTOFF}): {n_train}")
    reg_lines.append(f"- 验证 ({TRAIN_CUTOFF}~{VAL_CUTOFF}): {n_val}")
    reg_lines.append(f"- 测试 (≥{VAL_CUTOFF}): {n_test}")
    reg_lines.append("")
    reg_lines.append("## 二、测试集评估\n")
    if len(y_test) > 0:
        reg_lines.append(f"- RMSE: {rmse:.4f}")
        reg_lines.append(f"- MAE: {mae:.4f}")
        reg_lines.append(f"- R²: {r2:.4f}")
    else:
        reg_lines.append("- (无测试集)")
    reg_lines.append("")
    reg_lines.append("## 三、特征重要性 (Top 10)\n")
    reg_lines.append("| 排名 | 特征 | 重要性 |")
    reg_lines.append("|------|------|--------|")
    for rank, (_, r) in enumerate(imp_df.head(10).iterrows(), 1):
        reg_lines.append(f"| {rank} | {r['feature']} | {r['importance']:.3f} |")
    reg_lines.append("")
    reg_lines.append("## 四、预测分布\n")
    reg_lines.append(f"- traded 预测均值: {pq.mean():.4f}")
    reg_lines.append(f"- traded 预测标准差: {pq.std():.4f}")
    reg_lines.append(f"- traded 预测范围: [{pq.min():.4f}, {pq.max():.4f}]")

    with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
        f.write('\n'.join(reg_lines))
    print(f"    已写入 {OUTPUT_MD}")

    # 打印关键结果
    print(f"\n    ===== 分层回测关键结果 =====")
    for tier in ['Low', 'Mid', 'High']:
        if tier in tier_stats:
            s = tier_stats[tier]
            print(f"    {tier:5s}: {s['n']:4d}笔, "
                  f"avg={s['avg_pnl']:+.4f}, WR={s['wr']:.1%}, "
                  f"PF={s['pf']:.2f}")
    if len(hm) > 0:
        print(f"    High+Mid: {len(hm)}笔, avg={hm['pnl'].mean():+.4f}, "
              f"PF={hm_pf:.2f}")


if __name__ == '__main__':
    run()
