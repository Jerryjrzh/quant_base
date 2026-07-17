#!/usr/bin/env python3
"""
Signal Backtest Validator v2
基于 Gemini Review 的三大改进验证:
1. Logistic Regression 打分器 (替代失效的 95 分)
2. 截面优选 (Cross-sectional Ranking)
3. 动态追踪止盈 (Dynamic Trailing Stop)
"""

import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import warnings
warnings.filterwarnings('ignore')

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 数据加载与预处理
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def load_and_prepare():
    """加载数据并准备特征"""
    df = pd.read_csv('data/result/SignalGenerator/master_signals.csv')

    # Scheme C 基础过滤
    df = df[(df['ma_slope'] <= -0.02) & (df['board_type'] == '20CM')].copy()

    # Gemini 定义的实盘质量标签 (T0 可计算)
    df['is_real_quality'] = (df['future_mfe'] >= 0.05) & (df['future_mae'] >= -0.08)

    # 特征工程
    df['signal_date'] = pd.to_datetime(df['signal_date'])
    df['month'] = df['signal_date'].dt.to_period('M')

    # One-hot 编码
    df = pd.get_dummies(df, columns=['market_env', 'v44_trend', 'v44_bias_tier'],
                        prefix=['env', 'trend', 'bias'], drop_first=False)

    return df


def extract_features(df):
    """提取 T0 可用特征"""
    feature_cols = ['ma_slope', 'bias_20', 'score']

    # 添加 one-hot 列
    one_hot_cols = [c for c in df.columns if c.startswith(('env_', 'trend_', 'bias_'))]
    feature_cols.extend(one_hot_cols)

    X = df[feature_cols].fillna(0)
    y = df['is_real_quality'].astype(int)

    return X, y, feature_cols


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 验证一: Logistic Regression 打分器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_lr_scorer(df):
    """训练 LR 模型并在测试集验证"""
    print("="*70)
    print("验证一: Logistic Regression 打分器")
    print("="*70)

    # 时间切分: 前 12 月训练, 后 4 月测试
    train_months = df[df['month'] <= pd.Period('2025-12', 'M')]
    test_months = df[df['month'] > pd.Period('2025-12', 'M')]

    print(f"\n训练集: {train_months['signal_date'].min().date()} ~ {train_months['signal_date'].max().date()}")
    print(f"  样本数: {len(train_months):,}, 正例: {train_months['is_real_quality'].mean():.1%}")

    print(f"测试集: {test_months['signal_date'].min().date()} ~ {test_months['signal_date'].max().date()}")
    print(f"  样本数: {len(test_months):,}, 正例: {test_months['is_real_quality'].mean():.1%}")

    # 提取特征
    X_train, y_train, feature_cols = extract_features(train_months)
    X_test, y_test, _ = extract_features(test_months)

    # 标准化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    # 训练 LR
    lr = LogisticRegression(random_state=42, class_weight='balanced', max_iter=1000)
    lr.fit(X_train_scaled, y_train)

    # 预测概率
    train_proba = lr.predict_proba(X_train_scaled)[:, 1]
    test_proba = lr.predict_proba(X_test_scaled)[:, 1]

    # 评估
    train_pred = (train_proba >= 0.5).astype(int)
    test_pred = (test_proba >= 0.5).astype(int)

    print(f"\n训练集性能:")
    print(f"  Accuracy:  {accuracy_score(y_train, train_pred):.3f}")
    print(f"  Precision: {precision_score(y_train, train_pred):.3f}")
    print(f"  Recall:    {recall_score(y_train, train_pred):.3f}")
    print(f"  F1:        {f1_score(y_train, train_pred):.3f}")

    print(f"\n测试集性能:")
    print(f"  Accuracy:  {accuracy_score(y_test, test_pred):.3f}")
    print(f"  Precision: {precision_score(y_test, test_pred):.3f}")
    print(f"  Recall:    {recall_score(y_test, test_pred):.3f}")
    print(f"  F1:        {f1_score(y_test, test_pred):.3f}")

    # 特征重要性
    print(f"\nTop 10 特征权重:")
    coef_df = pd.DataFrame({
        'feature': feature_cols,
        'coef': lr.coef_[0]
    }).sort_values('coef', key=abs, ascending=False).head(10)

    for _, row in coef_df.iterrows():
        print(f"  {row['feature']:<20} {row['coef']:>8.4f}")

    # 概率分位分析
    test_months = test_months.copy()
    test_months['lr_proba'] = test_proba

    print(f"\n测试集 LR 概率分位分析:")
    print(f"{'分位':>6} | {'概率范围':>12} | {'信号数':>6} | {'real_quality':>12} | {'MFE中位':>8} | {'MAE中位':>8}")
    print("-" * 70)

    for q in [0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        if q == 0:
            subset = test_months[test_months['lr_proba'] < test_months['lr_proba'].quantile(0.2)]
            label = "0-20%"
        elif q == 1.0:
            subset = test_months[test_months['lr_proba'] >= test_months['lr_proba'].quantile(0.8)]
            label = "80-100%"
        else:
            subset = test_months[(test_months['lr_proba'] >= test_months['lr_proba'].quantile(q)) &
                                 (test_months['lr_proba'] < test_months['lr_proba'].quantile(q + 0.2))]
            label = f"{int(q*100)}-{int((q+0.2)*100)}%"

        if len(subset) == 0:
            continue

        print(f"{label:>6} | {subset['lr_proba'].min():.3f}~{subset['lr_proba'].max():.3f} | "
              f"{len(subset):>6} | {subset['is_real_quality'].mean():>11.1%} | "
              f"{subset['future_mfe'].median():>7.2%} | {subset['future_mae'].median():>7.2%}")

    return test_months, lr, scaler


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 验证二: 截面优选 (Cross-sectional Ranking)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_cross_sectional(test_df):
    """按日期截面排名, 只选 Top N"""
    print("\n" + "="*70)
    print("验证二: 截面优选 (Cross-sectional Ranking)")
    print("="*70)

    results = []

    for top_n in [1, 3, 5, 10]:
        # 每天选概率最高的 Top N
        daily_top = test_df.sort_values('lr_proba', ascending=False).groupby('signal_date').head(top_n)

        n_signals = len(daily_top)
        n_days = daily_top['signal_date'].nunique()
        real_q_rate = daily_top['is_real_quality'].mean()
        mfe_med = daily_top['future_mfe'].median()
        mae_med = daily_top['future_mae'].median()
        pl_ratio = abs(mfe_med / mae_med) if mae_med != 0 else np.inf

        results.append({
            'top_n': top_n,
            'n_signals': n_signals,
            'n_days': n_days,
            'real_q_rate': real_q_rate,
            'mfe_median': mfe_med,
            'mae_median': mae_med,
            'pl_ratio': pl_ratio
        })

        print(f"\nTop {top_n} per day:")
        print(f"  总信号: {n_signals}, 覆盖 {n_days} 天")
        print(f"  real_quality: {real_q_rate:.1%}")
        print(f"  MFE 中位: {mfe_med:.2%}, MAE 中位: {mae_med:.2%}")
        print(f"  盈亏比: {pl_ratio:.2f}")

    # 对比: 不设阈值 (全部信号)
    all_q = test_df['is_real_quality'].mean()
    all_mfe = test_df['future_mfe'].median()
    all_mae = test_df['future_mae'].median()
    all_pl = abs(all_mfe / all_mae)

    print(f"\n对比 - 全部信号 (无截面优选):")
    print(f"  总信号: {len(test_df)}, real_quality: {all_q:.1%}")
    print(f"  MFE 中位: {all_mfe:.2%}, MAE 中位: {all_mae:.2%}, 盈亏比: {all_pl:.2f}")

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 验证三: 动态追踪止盈 (Dynamic Trailing Stop)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def simulate_trailing_stop(df, breakeven_trigger=0.03, trailing_pct=0.30):
    """
    模拟动态追踪止盈
    - 浮盈达到 breakeven_trigger (3%) 时, 止损上移至成本+0.5%
    - 浮盈超过 5% 后, 从最高点回落 trailing_pct (30%) 利润时平仓
    """
    results = []

    for _, row in df.iterrows():
        entry_price = row['close_t0']
        max_profit = 0
        exit_price = None
        exit_reason = None

        # 模拟 T1~T7
        for day in range(1, 8):
            high_col = f'T{day}_High'
            low_col = f'T{day}_Low'
            close_col = f'T{day}_Close'

            if pd.isna(row[high_col]) or pd.isna(row[low_col]):
                continue

            day_high = row[high_col]
            day_low = row[low_col]
            day_close = row[close_col]

            # 计算日内浮盈
            intraday_high_pct = (day_high - entry_price) / entry_price
            intraday_low_pct = (day_low - entry_price) / entry_price
            close_pct = (day_close - entry_price) / entry_price

            # 更新最大浮盈
            if intraday_high_pct > max_profit:
                max_profit = intraday_high_pct

            # 检查止损
            if max_profit >= breakeven_trigger:
                # 保本线已激活
                stop_level = entry_price * 1.005  # 成本 + 0.5%
                if day_low <= stop_level:
                    exit_price = stop_level
                    exit_reason = 'breakeven_stop'
                    break

            # 检查追踪止盈
            if max_profit >= 0.05:
                # 从最高点回落 30% 利润
                trailing_stop_pct = max_profit * (1 - trailing_pct)
                trailing_stop_price = entry_price * (1 + trailing_stop_pct)

                if day_close <= trailing_stop_price:
                    exit_price = trailing_stop_price
                    exit_reason = 'trailing_stop'
                    break

        # 如果 7 天未触发, 按 T7 收盘价平仓
        if exit_price is None:
            t7_close = row['T7_Close']
            if not pd.isna(t7_close):
                exit_price = t7_close
                exit_reason = 'time_exit'
            else:
                continue

        pnl_pct = (exit_price - entry_price) / entry_price
        results.append({
            'signal_date': row['signal_date'],
            'stock_code': row['stock_code'],
            'pnl_pct': pnl_pct,
            'exit_reason': exit_reason,
            'max_profit': max_profit
        })

    return pd.DataFrame(results)


def validate_trailing_stop(test_df):
    """对比固定止盈 vs 动态追踪止盈"""
    print("\n" + "="*70)
    print("验证三: 动态追踪止盈 vs 固定止盈")
    print("="*70)

    # 策略 1: 固定止盈 (MFE 的 60%)
    test_df = test_df.copy()
    test_df['fixed_exit_pct'] = test_df['future_mfe'] * 0.6
    test_df['fixed_win'] = test_df['fixed_exit_pct'] > 0

    fixed_win_rate = test_df['fixed_win'].mean()
    fixed_avg_pnl = test_df['fixed_exit_pct'].mean()

    print(f"\n策略 1: 固定止盈 (MFE × 60%)")
    print(f"  胜率: {fixed_win_rate:.1%}")
    print(f"  平均收益: {fixed_avg_pnl:.2%}")

    # 策略 2: 动态追踪止盈
    trailing_results = simulate_trailing_stop(test_df, breakeven_trigger=0.03, trailing_pct=0.30)

    if len(trailing_results) == 0:
        print("\n策略 2: 动态追踪止盈 - 无有效交易")
        return

    trailing_win_rate = (trailing_results['pnl_pct'] > 0).mean()
    trailing_avg_pnl = trailing_results['pnl_pct'].mean()

    print(f"\n策略 2: 动态追踪止盈 (3% 保本, 30% 回撤)")
    print(f"  交易数: {len(trailing_results)}")
    print(f"  胜率: {trailing_win_rate:.1%}")
    print(f"  平均收益: {trailing_avg_pnl:.2%}")

    # 出场原因分布
    print(f"\n  出场原因:")
    for reason, count in trailing_results['exit_reason'].value_counts().items():
        pct = count / len(trailing_results)
        avg_pnl = trailing_results[trailing_results['exit_reason'] == reason]['pnl_pct'].mean()
        print(f"    {reason:<20} {count:>5} ({pct:>5.1%}) avg_pnl: {avg_pnl:>7.2%}")

    # 策略 3: 固定止损 + 动态止盈
    test_df['fixed_sl'] = -0.08  # 固定 -8% 止损
    test_df['hybrid_exit'] = test_df.apply(
        lambda r: max(r['fixed_sl'], min(r['future_mfe'] * 0.7, r['future_mae'])),
        axis=1
    )
    hybrid_win_rate = (test_df['hybrid_exit'] > 0).mean()
    hybrid_avg_pnl = test_df['hybrid_exit'].mean()

    print(f"\n策略 3: 固定止损(-8%) + 动态止盈(MFE×70%)")
    print(f"  胜率: {hybrid_win_rate:.1%}")
    print(f"  平均收益: {hybrid_avg_pnl:.2%}")

    return trailing_results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. 主流程
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    print("Signal Backtest Validator v2")
    print("基于 Gemini Review 的三大改进验证\n")

    # 加载数据
    df = load_and_prepare()
    print(f"Scheme C (slope≤-2% + 20CM) 数据: {len(df):,} 信号\n")

    # 验证一: LR 打分器
    test_df, lr_model, scaler = validate_lr_scorer(df)

    # 验证二: 截面优选
    cs_results = validate_cross_sectional(test_df)

    # 验证三: 动态止盈
    trailing_results = validate_trailing_stop(test_df)

    # 保存结果
    output = {
        'test_df': test_df,
        'lr_model': lr_model,
        'scaler': scaler,
        'cross_sectional_results': cs_results,
        'trailing_results': trailing_results
    }

    return output


if __name__ == '__main__':
    main()
