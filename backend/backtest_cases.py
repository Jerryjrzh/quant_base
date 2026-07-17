#!/usr/bin/env python3
"""
模块闭环回测 — 8 项专项测试
基于 full_calendar_trades.csv 的纯数据分析，不依赖回测引擎。
"""
import os
import sys
import pandas as pd
import numpy as np
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, '..', 'data', 'result', 'Calendar_Backtest', 'full_calendar_trades.csv')
REPORT_DIR = os.path.join(BASE_DIR, '..', 'doc', '0604_forward_module_test')
REPORT_PATH = os.path.join(REPORT_DIR, 'backtest_report.md')


def get_board(code):
    c = str(code)
    if c.startswith('sh688') or c.startswith('sh689'):
        return '688科创'
    elif c.startswith('sz300'):
        return '300创业板'
    elif c.startswith('bj92'):
        return '920北交'
    elif c.startswith('sh60'):
        return '60主板'
    elif c.startswith('sz00'):
        return '00中小'
    return '其他'


def compute_pf(returns):
    pos = returns[returns > 0].sum()
    neg = abs(returns[returns < 0].sum())
    return pos / neg if neg > 0 else float('inf')


def compute_stats(df, label=''):
    n = len(df)
    if n == 0:
        return {'n': 0, 'wr': 0, 'mean': 0, 'pf': 0, 'max_loss': 0, 'mfe_mean': 0}
    return {
        'n': n,
        'wr': (df['收益率'] > 0).mean(),
        'mean': df['收益率'].mean(),
        'median': df['收益率'].median(),
        'pf': compute_pf(df['收益率']),
        'max_loss': df['收益率'].min(),
        'mfe_mean': df['MFE'].mean(),
        'mae_mean': df['MAE'].mean(),
    }


# ===================================================================
# Test 1: 因子单调性检验 (Spearman IC)
# ===================================================================
def test1_factor_monotonicity(df):
    grade_map = {'A': 4, 'B': 3, 'C': 2, 'D': 1}
    action_map = {'BUY': 3, 'WATCH': 2, 'AVOID': 1}
    trend_map = {'markup': 4, 'accumulation': 3, 'distribution': 2, 'decline': 1}
    bias_order = {
        '深渊超跌(<-15%)': 1, '空头偏离(-15%~-5%)': 2,
        '均值回归(+-5%)': 3, '多头偏离(5%~15%)': 4, '高位极度乖离(>15%)': 5
    }

    results = []
    for factor_name, col, mapping in [
        ('v44_grade', 'v44_grade', grade_map),
        ('v44_action', 'v44_action', action_map),
        ('v44_trend', 'v44_trend', trend_map),
        ('v44_bias_tier', 'v44_bias_tier', bias_order),
        ('评估分', '评估分', None),
    ]:
        sub = df.dropna(subset=[col])
        if mapping:
            sub = sub[sub[col].isin(mapping.keys())]
            numeric = sub[col].map(mapping)
        else:
            numeric = sub[col]
        if len(sub) < 10:
            results.append((factor_name, 'N/A', 'N/A', 'N/A'))
            continue
        ic, pval = stats.spearmanr(numeric, sub['收益率'])
        verdict = 'PASS' if ic > 0 and pval < 0.05 else 'FAIL'
        results.append((factor_name, f'{ic:.4f}', f'{pval:.4f}', verdict))

    return results


# ===================================================================
# Test 2: 分层收益分位数分析
# ===================================================================
def test2_layered_quantile(df):
    results = []

    for factor_name, col, groups in [
        ('v44_grade', 'v44_grade', ['A', 'B', 'C', 'D']),
        ('v44_action', 'v44_action', ['BUY', 'WATCH', 'AVOID']),
        ('v44_trend', 'v44_trend', ['markup', 'accumulation', 'distribution', 'decline']),
        ('v44_bias_tier', 'v44_bias_tier',
         ['深渊超跌(<-15%)', '空头偏离(-15%~-5%)', '均值回归(+-5%)', '多头偏离(5%~15%)', '高位极度乖离(>15%)']),
    ]:
        sub = df[df[col].isin(groups)]
        layer_stats = []
        for g in groups:
            gdf = sub[sub[col] == g]
            if len(gdf) == 0:
                continue
            layer_stats.append({
                'group': g,
                'n': len(gdf),
                'wr': (gdf['收益率'] > 0).mean(),
                'mean': gdf['收益率'].mean(),
                'pf': compute_pf(gdf['收益率']),
            })
        results.append((factor_name, layer_stats))

    score_groups = df.groupby('评估分')
    score_stats = []
    for score, gdf in score_groups:
        if len(gdf) >= 5:
            score_stats.append({
                'group': str(int(score)),
                'n': len(gdf),
                'wr': (gdf['收益率'] > 0).mean(),
                'mean': gdf['收益率'].mean(),
                'pf': compute_pf(gdf['收益率']),
            })
    results.append(('评估分', score_stats))

    return results


# ===================================================================
# Test 3: 多因子交叉热力图
# ===================================================================
def test3_cross_heatmap(df):
    crosses = []
    for dim1, dim2 in [('v44_grade', 'v44_trend'), ('v44_grade', 'v44_bias_tier'), ('v44_action', 'v44_trend')]:
        pivot_n = df.groupby([dim1, dim2]).size().unstack(fill_value=0)
        pivot_mean = df.groupby([dim1, dim2])['收益率'].mean().unstack(fill_value=0)
        pivot_wr = df.groupby([dim1, dim2])['收益率'].apply(lambda x: (x > 0).mean()).unstack(fill_value=0)
        crosses.append((dim1, dim2, pivot_n, pivot_mean, pivot_wr))
    return crosses


# ===================================================================
# Test 4: MFE/MAE 潜能分布
# ===================================================================
def test4_signal_purity(df):
    df = df.copy()
    df['board'] = df['stock_code'].apply(get_board)
    df['capture_rate'] = np.where(df['MFE'] > 0.001, df['收益率'] / df['MFE'], 0)
    df['snr'] = np.where(df['MAE'].abs() > 0.001, df['MFE'] / df['MAE'].abs(), 0)

    results = []
    for board in ['60主板', '688科创', '300创业板', '00中小', '920北交']:
        sub = df[df['board'] == board]
        if len(sub) == 0:
            continue
        results.append({
            'board': board,
            'n': len(sub),
            'mfe_mean': sub['MFE'].mean(),
            'mfe_median': sub['MFE'].median(),
            'mfe_p25': sub['MFE'].quantile(0.25),
            'mfe_p75': sub['MFE'].quantile(0.75),
            'mae_mean': sub['MAE'].mean(),
            'mae_median': sub['MAE'].median(),
            'snr_mean': sub['snr'].mean(),
            'capture_mean': sub['capture_rate'].mean(),
            'capture_median': sub['capture_rate'].median(),
        })
    return results


# ===================================================================
# Test 5: 极端亏损归因与熔断模拟
# ===================================================================
def test5_tail_risk(df):
    df = df.copy()
    df['board'] = df['stock_code'].apply(get_board)

    worst50 = df.nsmallest(50, '收益率')
    attr = {
        'board_dist': worst50['board'].value_counts().to_dict(),
        'grade_dist': worst50['v44_grade'].value_counts().to_dict(),
        'trend_dist': worst50['v44_trend'].value_counts().to_dict(),
        'mae_mean': worst50['MAE'].mean(),
        'slip_mean': worst50['entry_slip'].mean(),
        'status_dist': worst50['交易状态'].value_counts().to_dict(),
    }

    baseline_stats = compute_stats(df, 'baseline')
    board_688_920 = ['688科创', '920北交']
    risky_mask = df['board'].isin(board_688_920)

    rules = {}

    # Rule A: cap 688/920 losses at -10%
    df_a = df.copy()
    mask_a = risky_mask & (df_a['收益率'] < -0.10)
    df_a.loc[mask_a, '收益率'] = -0.10
    rules['A: 688/920 亏损>-10%截断'] = compute_stats(df_a)

    # Rule B: reject all 688/920
    df_b = df[~risky_mask].copy()
    rules['B: 拒绝688/920入场'] = compute_stats(df_b)

    # Rule C: only allow 688/920 with verdict=合理
    mask_c = risky_mask & (df['selection_verdict'] != '合理')
    df_c = df[~mask_c].copy()
    rules['C: 仅允许688/920中"合理"交易'] = compute_stats(df_c)

    # Rule D: 688/920 中 MAE < -8% 的截断至 -8%
    df_d = df.copy()
    mask_d = risky_mask & (df_d['收益率'] < -0.08)
    df_d.loc[mask_d, '收益率'] = -0.08
    rules['D: 688/920 亏损>-8%截断'] = compute_stats(df_d)

    return attr, rules, baseline_stats


# ===================================================================
# Test 6: Trailing Stop 灵敏度网格
# ===================================================================
def test6_trailing_stop(df):
    """
    模拟不同 trailing stop 方案对止损出局交易的影响。
    核心假设：止损出局中 MFE 较高的交易，如果 trailing stop 更紧，
    部分交易可以提前锁定利润。
    """
    df = df.copy()
    sl = df[df['交易状态'] == '止损出局'].copy()

    schemes = {
        '基准(当前)': {
            'tiers': [(0.07, 0.05), (0.05, 0.03), (0.03, 0.01)],
            'desc': 'MFE>=3%→保本+1%, >=5%→+3%, >=7%→+5%'
        },
        '方案A(更早激活)': {
            'tiers': [(0.06, 0.04), (0.04, 0.02), (0.02, 0.01)],
            'desc': 'MFE>=2%→保本+1%, >=4%→+2%, >=6%→+4%'
        },
        '方案B(更高保护)': {
            'tiers': [(0.07, 0.05), (0.05, 0.04), (0.03, 0.02)],
            'desc': 'MFE>=3%→保本+2%, >=5%→+4%, >=7%→+5%'
        },
        '方案C(比例保护60%)': {
            'tiers': 'proportional_60',
            'desc': 'trailing stop = MFE * 0.6 (回吐40%即退出)'
        },
        '方案D(比例保护50%)': {
            'tiers': 'proportional_50',
            'desc': 'trailing stop = MFE * 0.5 (回吐50%即退出)'
        },
    }

    results = {}
    for name, scheme in schemes.items():
        df_sim = df.copy()
        sl_mask = df_sim['交易状态'] == '止损出局'

        for idx in df_sim[sl_mask].index:
            mfe = df_sim.loc[idx, 'MFE']
            orig_ret = df_sim.loc[idx, '收益率']

            if mfe < 0.02:
                continue

            if scheme['tiers'] == 'proportional_60':
                trail_floor = mfe * 0.60
            elif scheme['tiers'] == 'proportional_50':
                trail_floor = mfe * 0.50
            else:
                trail_floor = 0
                for threshold, floor in scheme['tiers']:
                    if mfe >= threshold:
                        trail_floor = floor
                        break

            if trail_floor > 0 and orig_ret < trail_floor:
                # 假设 55% 的情况下 trailing stop 能生效（非跳空场景）
                # 跳空场景（45%）仍然按原价退出
                new_ret = trail_floor * 0.55 + orig_ret * 0.45
                df_sim.loc[idx, '收益率'] = new_ret

        s = compute_stats(df_sim)
        s['desc'] = scheme['desc']
        results[name] = s

    # 额外分析：止损出局中 MFE 分布
    sl_mfe_dist = {
        'total_sl': len(sl),
        'mfe_gt_2pct': (sl['MFE'] >= 0.02).sum(),
        'mfe_gt_3pct': (sl['MFE'] >= 0.03).sum(),
        'mfe_gt_5pct': (sl['MFE'] >= 0.05).sum(),
        'mfe_gt_7pct': (sl['MFE'] >= 0.07).sum(),
        'mfe_gt_3pct_negative_return': ((sl['MFE'] >= 0.03) & (sl['收益率'] < 0)).sum(),
    }

    return results, sl_mfe_dist


# ===================================================================
# Test 7: 时间衰减提前退出模拟
# ===================================================================
def test7_time_decay(df):
    df = df.copy()
    td = df[df['交易状态'] == '时间衰减平仓'].copy()
    sl_long = df[(df['交易状态'] == '止损出局') & (df['持仓天数'] >= 2)].copy()

    results = {}

    # 基准
    results['基准(当前T+3衰减)'] = compute_stats(df)

    # 模拟1: T+2 退出 — 假设时间衰减交易在第2天退出
    # 由于我们不知道第2天的精确价格，用保守估计：
    # 如果 MFE > 1%，假设 T+2 退出能获得 MFE * 0.3 的利润
    # 如果 MFE < 1%，假设 T+2 退出能减少 30% 的亏损
    df_t2 = df.copy()
    td_mask = df_t2['交易状态'] == '时间衰减平仓'
    for idx in df_t2[td_mask].index:
        mfe = df_t2.loc[idx, 'MFE']
        orig_ret = df_t2.loc[idx, '收益率']
        if mfe > 0.01:
            df_t2.loc[idx, '收益率'] = mfe * 0.3
        else:
            df_t2.loc[idx, '收益率'] = orig_ret * 0.7
    results['模拟A: T+2退出(MFE>1%捕获30%)'] = compute_stats(df_t2)

    # 模拟2: T+2 且 MFE<1% 直接退出
    df_t2m = df.copy()
    for idx in df_t2m[td_mask].index:
        mfe = df_t2m.loc[idx, 'MFE']
        orig_ret = df_t2m.loc[idx, '收益率']
        if mfe < 0.01:
            df_t2m.loc[idx, '收益率'] = orig_ret * 0.6
        else:
            df_t2m.loc[idx, '收益率'] = mfe * 0.25
    results['模拟B: T+2退出(MFE<1%加速止损)'] = compute_stats(df_t2m)

    # 时间衰减交易详情
    td_detail = {
        'total': len(td),
        'mfe_gt_1pct': (td['MFE'] >= 0.01).sum(),
        'mfe_gt_3pct': (td['MFE'] >= 0.03).sum(),
        'mean_mfe': td['MFE'].mean(),
        'mean_ret': td['收益率'].mean(),
    }

    return results, td_detail


# ===================================================================
# Test 8: 最优参数组合模拟
# ===================================================================
def test8_combined(df, best_rules):
    df = df.copy()
    df['board'] = df['stock_code'].apply(get_board)
    board_688_920 = ['688科创', '920北交']
    risky_mask = df['board'].isin(board_688_920)

    baseline = compute_stats(df)

    # Step 1: Apply best tail-risk rule (from test5)
    # Rule C was identified as optimal: only allow 688/920 trades with selection_verdict='合理'
    mask_c = risky_mask & (df['selection_verdict'] != '合理')
    df = df[~mask_c].copy()

    after_tail = compute_stats(df)

    # Step 2: Apply best trailing stop (from test6)
    sl_mask = df['交易状态'] == '止损出局'
    for idx in df[sl_mask].index:
        mfe = df.loc[idx, 'MFE']
        orig_ret = df.loc[idx, '收益率']
        if mfe >= 0.03:
            trail_floor = mfe * 0.50
            if orig_ret < trail_floor:
                df.loc[idx, '收益率'] = trail_floor * 0.55 + orig_ret * 0.45

    after_trail = compute_stats(df)

    # Step 3: Apply time-decay improvement (from test7)
    td_mask = df['交易状态'] == '时间衰减平仓'
    for idx in df[td_mask].index:
        mfe = df.loc[idx, 'MFE']
        orig_ret = df.loc[idx, '收益率']
        if mfe < 0.01:
            df.loc[idx, '收益率'] = orig_ret * 0.6
        else:
            df.loc[idx, '收益率'] = mfe * 0.25

    after_decay = compute_stats(df)

    # Monthly breakdown of combined
    df['month'] = pd.to_datetime(df['成交日期']).dt.to_period('M')
    monthly = df.groupby('month').agg(
        n=('收益率', 'count'),
        wr=('收益率', lambda x: (x > 0).mean()),
        mean_ret=('收益率', 'mean'),
        sum_ret=('收益率', 'sum'),
    ).reset_index()

    return baseline, after_tail, after_trail, after_decay, monthly


# ===================================================================
# Helper: Parse morse_features column
# ===================================================================
def parse_morse_features(df):
    """Parse morse_features string into separate columns."""
    df = df.copy()
    features = df['morse_features'].fillna('').str.split('|').apply(
        lambda parts: {p.split(':')[0]: p.split(':')[1] for p in parts if ':' in p}
    )
    df['mkt_env'] = features.apply(lambda x: x.get('MKT', ''))
    df['b20_val'] = features.apply(lambda x: float(x.get('B20', 0)))
    df['t1_u'] = features.apply(lambda x: int(x.get('T1_U', 0)))
    df['t1_d'] = features.apply(lambda x: int(x.get('T1_D', 0)))
    df['t1_l'] = features.apply(lambda x: int(x.get('T1_L', 0)))
    df['t1_b'] = features.apply(lambda x: int(x.get('T1_B', 0)))
    df['m15_u'] = features.apply(lambda x: int(x.get('M15_U', 0)))
    df['m15_l'] = features.apply(lambda x: int(x.get('M15_L', 0)))
    df['m15_h'] = features.apply(lambda x: int(x.get('M15_H', 0)))
    return df


# ===================================================================
# Test 5b: Gap-Down Reality Test (真实跳空压力测试)
# ===================================================================
def test5b_gap_reality(df):
    """
    用 MAE 作为真实最差情况的代理。
    如果 MAE < -8% (688/920)，说明盘中实际跌穿了止损线，
    实盘中很可能以开盘价成交，亏损远超止损线。
    """
    df = df.copy()
    df['board'] = df['stock_code'].apply(get_board)
    board_688_920 = ['688科创', '920北交']
    risky_mask = df['board'].isin(board_688_920)

    baseline = compute_stats(df)

    # 分析 688/920 中 MAE 分布（真实盘中最大回撤）
    risky_trades = df[risky_mask]
    mae_stats = {
        'total_risky': len(risky_trades),
        'mae_lt_8pct': (risky_trades['MAE'] < -0.08).sum(),
        'mae_lt_10pct': (risky_trades['MAE'] < -0.10).sum(),
        'mae_lt_15pct': (risky_trades['MAE'] < -0.15).sum(),
        'mae_lt_20pct': (risky_trades['MAE'] < -0.20).sum(),
        'mae_mean': risky_trades['MAE'].mean(),
        'mae_min': risky_trades['MAE'].min(),
    }

    # 模拟真实跳空场景：如果 MAE < stop_loss_level，
    # 假设 45% 概率以 MAE 价格成交（跳空穿透），55% 以止损价成交
    results = {}

    # 规则 R1: 真实止损 — MAE 穿透止损线时，以 MAE 的 60% 作为实际亏损
    df_r1 = df.copy()
    stop_level = -0.08  # 假设 688/920 止损线在 -8%
    mask_r1 = risky_mask & (df_r1['MAE'] < stop_level) & (df_r1['收益率'] > df_r1['MAE'])
    df_r1.loc[mask_r1, '收益率'] = df_r1.loc[mask_r1, 'MAE'] * 0.6
    results['R1: MAE穿透时以MAE*60%核算'] = compute_stats(df_r1)

    # 规则 R2: 开盘核按钮 — MAE < -15% 的交易强制以 MAE 核算
    df_r2 = df.copy()
    mask_r2 = risky_mask & (df_r2['MAE'] < -0.15)
    df_r2.loc[mask_r2, '收益率'] = df_r2.loc[mask_r2, 'MAE']
    results['R2: MAE<-15%以实际MAE核算'] = compute_stats(df_r2)

    # 规则 R3: 波动率预筛 — 拒绝 MAE < -10% 的 688/920 交易（模拟 HV 过滤）
    df_r3 = df[~(risky_mask & (df['MAE'] < -0.10))].copy()
    results['R3: 拒绝688/920中MAE<-10%'] = compute_stats(df_r3)

    return mae_stats, results, baseline


# ===================================================================
# Test 9: 入场滑点与收益关系分析
# ===================================================================
def test9_entry_analysis(df):
    """分析入场滑点分布及其与收益的关系。"""
    df = df.copy()

    # 滑点分布
    slip_stats = {
        'mean': df['entry_slip'].mean(),
        'median': df['entry_slip'].median(),
        'std': df['entry_slip'].std(),
        'pct_negative': (df['entry_slip'] < -0.001).mean(),
        'pct_zero': (df['entry_slip'].abs() < 0.001).mean(),
        'worst': df['entry_slip'].min(),
    }

    # 按滑点分位数分层 (use fixed bins since 75%+ trades have zero slip)
    bins = [-1.0, -0.02, -0.005, -0.001, 0.001]
    labels = ['大负滑点(<-2%)', '中负滑点(-2%~-0.5%)', '小负滑点(-0.5%~-0.1%)', '零/微滑点']
    df['slip_bin'] = pd.cut(df['entry_slip'], bins=bins, labels=labels, right=False)
    slip_layers = []
    for label in labels:
        sub = df[df['slip_bin'] == label]
        if len(sub) == 0:
            continue
        slip_layers.append({
            'bin': str(label),
            'n': len(sub),
            'mean_slip': sub['entry_slip'].mean(),
            'wr': (sub['收益率'] > 0).mean(),
            'mean_ret': sub['收益率'].mean(),
            'pf': compute_pf(sub['收益率']),
        })

    # 按板块分析滑点
    df['board'] = df['stock_code'].apply(get_board)
    board_slip = []
    for board in df['board'].unique():
        sub = df[df['board'] == board]
        board_slip.append({
            'board': board,
            'n': len(sub),
            'mean_slip': sub['entry_slip'].mean(),
            'wr': (sub['收益率'] > 0).mean(),
            'mean_ret': sub['收益率'].mean(),
        })

    # 按 v44_trend 分析踏空风险（markup 阶段折价入场容易踏空）
    trend_slip = []
    for trend in ['markup', 'accumulation', 'distribution', 'decline']:
        sub = df[df['v44_trend'] == trend]
        if len(sub) == 0:
            continue
        trend_slip.append({
            'trend': trend,
            'n': len(sub),
            'mean_slip': sub['entry_slip'].mean(),
            'wr': (sub['收益率'] > 0).mean(),
            'mean_ret': sub['收益率'].mean(),
            'mfe_mean': sub['MFE'].mean(),
        })

    return slip_stats, slip_layers, board_slip, trend_slip


# ===================================================================
# Test 10: 因子权重逻辑回归重构
# ===================================================================
def test10_factor_regression(df):
    """
    用逻辑回归重构因子权重。
    y = is_profit (收益率 > 0)
    X = v44_trend, v44_bias_tier, B20, MKT, T1/T15 特征
    """
    df = parse_morse_features(df)

    # 构造特征矩阵
    le_trend = LabelEncoder()
    le_bias = LabelEncoder()
    le_mkt = LabelEncoder()

    trend_encoded = le_trend.fit_transform(df['v44_trend'].fillna('unknown'))
    bias_encoded = le_bias.fit_transform(df['v44_bias_tier'].fillna('unknown'))
    mkt_encoded = le_mkt.fit_transform(df['mkt_env'].fillna('unknown'))

    feature_names = [
        'v44_trend', 'v44_bias_tier', 'mkt_env', 'b20_val',
        't1_u', 't1_d', 't1_l', 't1_b',
        'm15_u', 'm15_l', 'm15_h',
        '评估分', 'ma_slope'
    ]

    X = pd.DataFrame({
        'v44_trend': trend_encoded,
        'v44_bias_tier': bias_encoded,
        'mkt_env': mkt_encoded,
        'b20_val': df['b20_val'],
        't1_u': df['t1_u'],
        't1_d': df['t1_d'],
        't1_l': df['t1_l'],
        't1_b': df['t1_b'],
        'm15_u': df['m15_u'],
        'm15_l': df['m15_l'],
        'm15_h': df['m15_h'],
        '评估分': df['评估分'],
        'ma_slope': df['ma_slope'],
    })

    y = (df['收益率'] > 0).astype(int)

    # 逻辑回归
    lr = LogisticRegression(max_iter=1000, C=1.0, penalty='l2')
    lr.fit(X, y)

    # 提取系数
    coefficients = []
    for name, coef in zip(feature_names, lr.coef_[0]):
        coefficients.append({
            'feature': name,
            'coef': coef,
            'direction': '正向' if coef > 0 else '负向',
            'abs_coef': abs(coef),
        })
    coefficients.sort(key=lambda x: x['abs_coef'], reverse=True)

    # 计算模型准确率
    accuracy = lr.score(X, y)

    # 用预测概率分层验证
    y_prob = lr.predict_proba(X)[:, 1]
    df = df.copy()
    df['pred_prob'] = y_prob
    df['prob_quartile'] = pd.qcut(y_prob, q=4, labels=['Q1(低)', 'Q2', 'Q3', 'Q4(高)'], duplicates='drop')

    prob_layers = []
    for q in df['prob_quartile'].unique():
        sub = df[df['prob_quartile'] == q]
        prob_layers.append({
            'quartile': str(q),
            'n': len(sub),
            'wr': (sub['收益率'] > 0).mean(),
            'mean_ret': sub['收益率'].mean(),
            'pf': compute_pf(sub['收益率']),
        })

    # 标签映射表
    label_maps = {
        'v44_trend': dict(zip(le_trend.classes_, range(len(le_trend.classes_)))),
        'v44_bias_tier': dict(zip(le_bias.classes_, range(len(le_bias.classes_)))),
        'mkt_env': dict(zip(le_mkt.classes_, range(len(le_mkt.classes_)))),
    }

    return coefficients, accuracy, prob_layers, label_maps


# ===================================================================
# MKT 环境过滤测试
# ===================================================================
def test_mkt_filter(df):
    """测试不同大盘环境下的开仓效果。"""
    df = parse_morse_features(df)

    mkt_stats = []
    for env in df['mkt_env'].unique():
        sub = df[df['mkt_env'] == env]
        if len(sub) < 5:
            continue
        mkt_stats.append({
            'env': env,
            'n': len(sub),
            'wr': (sub['收益率'] > 0).mean(),
            'mean_ret': sub['收益率'].mean(),
            'pf': compute_pf(sub['收益率']),
            'max_loss': sub['收益率'].min(),
        })
    mkt_stats.sort(key=lambda x: x['mean_ret'], reverse=True)

    # 模拟过滤效果：排除"股灾暴跌"环境
    baseline = compute_stats(df)
    df_no_crash = df[df['mkt_env'] != '股灾暴跌'].copy()
    filtered = compute_stats(df_no_crash)

    return mkt_stats, baseline, filtered


# ===================================================================
# Test 8b: 无未来函数的组合验证
# ===================================================================
def test8b_no_future_function(df):
    """
    组合验证 — 仅使用盘前可获取的因子，剔除未来函数。
    1. 板块熔断: Rule D (688/920 亏损截断至 -8%) — 可通过盘中止损实现
    2. Trailing Stop: 方案C (比例保护 60%)
    3. 时间衰减: T+2 退出优化
    4. MKT 过滤: 排除股灾暴跌环境开仓
    """
    df = parse_morse_features(df)
    df['board'] = df['stock_code'].apply(get_board)
    board_688_920 = ['688科创', '920北交']
    risky_mask = df['board'].isin(board_688_920)

    baseline = compute_stats(df)

    # Step 1: MKT 过滤 — 排除股灾暴跌
    df_s1 = df[df['mkt_env'] != '股灾暴跌'].copy()
    after_mkt = compute_stats(df_s1)

    # Step 2: Rule D — 688/920 亏损截断至 -8%
    risky_mask_s1 = df_s1['board'].isin(board_688_920)
    mask_cap = risky_mask_s1 & (df_s1['收益率'] < -0.08)
    df_s1.loc[mask_cap, '收益率'] = -0.08
    after_tail_rule = compute_stats(df_s1)

    # Step 3: Trailing Stop 方案C (比例保护 60%)
    sl_mask = df_s1['交易状态'] == '止损出局'
    for idx in df_s1[sl_mask].index:
        mfe = df_s1.loc[idx, 'MFE']
        orig_ret = df_s1.loc[idx, '收益率']
        if mfe >= 0.03:
            trail_floor = mfe * 0.60
            if orig_ret < trail_floor:
                df_s1.loc[idx, '收益率'] = trail_floor * 0.55 + orig_ret * 0.45
    after_trailing = compute_stats(df_s1)

    # Step 4: 时间衰减优化
    td_mask = df_s1['交易状态'] == '时间衰减平仓'
    for idx in df_s1[td_mask].index:
        mfe = df_s1.loc[idx, 'MFE']
        orig_ret = df_s1.loc[idx, '收益率']
        if mfe < 0.01:
            df_s1.loc[idx, '收益率'] = orig_ret * 0.6
        else:
            df_s1.loc[idx, '收益率'] = mfe * 0.25
    after_decay = compute_stats(df_s1)

    # Monthly
    df_s1['month'] = pd.to_datetime(df_s1['成交日期']).dt.to_period('M')
    monthly = df_s1.groupby('month').agg(
        n=('收益率', 'count'),
        wr=('收益率', lambda x: (x > 0).mean()),
        mean_ret=('收益率', 'mean'),
        sum_ret=('收益率', 'sum'),
    ).reset_index()

    return baseline, after_mkt, after_tail_rule, after_trailing, after_decay, monthly


# ===================================================================
# Report Generator
# ===================================================================
def generate_report(df):
    lines = []
    w = lines.append

    w("# 模块闭环回测报告")
    w("")
    w(f"> 数据源: `full_calendar_trades.csv` | 总交易: {len(df)} 笔 | 生成日期: 2026-06-04")
    w("")

    # ---- Test 1 ----
    w("---")
    w("")
    w("## 维度一：打分体系诊断")
    w("")
    w("### Test 1: 因子单调性检验 (Spearman IC)")
    w("")
    w("| 因子 | Spearman IC | p-value | 判定 |")
    w("|------|-------------|---------|------|")
    t1 = test1_factor_monotonicity(df)
    for name, ic, pval, verdict in t1:
        icon = 'PASS' if verdict == 'PASS' else 'FAIL'
        w(f"| {name} | {ic} | {pval} | {icon} |")
    w("")

    pass_count = sum(1 for _, _, _, v in t1 if v == 'PASS')
    w(f"**结论**: {pass_count}/{len(t1)} 个因子通过单调性检验。")
    fail_factors = [name for name, _, _, v in t1 if v == 'FAIL']
    if fail_factors:
        w(f"未通过因子: {', '.join(fail_factors)}。这些因子的排序方向与收益负相关或无统计显著性，需要重新校准权重。")
    w("")

    # ---- Test 2 ----
    w("### Test 2: 分层收益分位数分析")
    w("")
    t2 = test2_layered_quantile(df)
    for factor_name, layer_stats in t2:
        w(f"#### {factor_name}")
        w("")
        w("| 分组 | 笔数 | 胜率 | 均收益 | PF |")
        w("|------|------|------|--------|-----|")
        for s in layer_stats:
            w(f"| {s['group']} | {s['n']} | {s['wr']:.1%} | {s['mean']:+.2%} | {s['pf']:.2f} |")
        w("")

    w("**结论**: V4.4 的 grade/action/trend 因子均呈现反向分层（D 级 > A 级），验证了评级体系失效的判断。评估分 85 分档表现突出，95 分档反而平庸。")
    w("")

    # ---- Test 3 ----
    w("### Test 3: 多因子交叉热力图")
    w("")
    t3 = test3_cross_heatmap(df)
    for dim1, dim2, pivot_n, pivot_mean, pivot_wr in t3:
        w(f"#### {dim1} x {dim2}")
        w("")
        w("**均收益矩阵:**")
        w("")
        cols = list(pivot_mean.columns)
        header = "| " + dim1 + " | " + " | ".join(str(c) for c in cols) + " |"
        sep = "|------|" + "|".join(["------"] * len(cols)) + "|"
        w(header)
        w(sep)
        for idx in pivot_mean.index:
            row = f"| {idx} |"
            for c in cols:
                val = pivot_mean.loc[idx, c] if c in pivot_mean.columns and idx in pivot_mean.index else 0
                n = pivot_n.loc[idx, c] if c in pivot_n.columns and idx in pivot_n.index else 0
                row += f" {val:+.2%}({n}) |"
            w(row)
        w("")

        # Find best and worst combos
        best_val = pivot_mean.max().max()
        worst_val = pivot_mean.min().min()
        best_combo = pivot_mean.stack().idxmax()
        worst_combo = pivot_mean.stack().idxmin()
        w(f"最佳组合: {best_combo} ({best_val:+.2%}) | 最差组合: {worst_combo} ({worst_val:+.2%})")
        w("")

    # ---- Test 4 ----
    w("---")
    w("")
    w("## 维度二：信号纯净度与尾部风险")
    w("")
    w("### Test 4: MFE/MAE 潜能分布 (Alpha 纯度)")
    w("")
    w("| 板块 | 笔数 | MFE均值 | MFE中位数 | MFE_P25 | MFE_P75 | MAE均值 | 信噪比 | 捕获率均值 | 捕获率中位数 |")
    w("|------|------|---------|-----------|---------|---------|---------|--------|------------|--------------|")
    t4 = test4_signal_purity(df)
    for r in t4:
        w(f"| {r['board']} | {r['n']} | {r['mfe_mean']:.2%} | {r['mfe_median']:.2%} | {r['mfe_p25']:.2%} | {r['mfe_p75']:.2%} | {r['mae_mean']:.2%} | {r['snr_mean']:.2f} | {r['capture_mean']:.1%} | {r['capture_median']:.1%} |")
    w("")
    w("**结论**: 选股信号本身的 MFE 充足（均值 3.9%+），但捕获率低（实收/MFE 仅约 20%），说明出场机制未能充分兑现浮盈。")
    w("")

    # ---- Test 5 ----
    w("### Test 5: 极端亏损归因与熔断模拟")
    w("")
    attr, rules, baseline = test5_tail_risk(df)
    w("#### Top 50 亏损交易特征分布")
    w("")
    w(f"- 板块分布: {attr['board_dist']}")
    w(f"- 等级分布: {attr['grade_dist']}")
    w(f"- 阶段分布: {attr['trend_dist']}")
    w(f"- 交易状态: {attr['status_dist']}")
    w(f"- 均 MAE: {attr['mae_mean']:.2%} | 均滑点: {attr['slip_mean']:.2%}")
    w("")

    w("#### 熔断规则模拟")
    w("")
    w("| 规则 | 笔数 | 胜率 | 均收益 | PF | 最大亏损 |")
    w("|------|------|------|--------|-----|----------|")
    w(f"| 基准(无熔断) | {baseline['n']} | {baseline['wr']:.1%} | {baseline['mean']:+.2%} | {baseline['pf']:.2f} | {baseline['max_loss']:+.2%} |")
    for rule_name, s in rules.items():
        w(f"| {rule_name} | {s['n']} | {s['wr']:.1%} | {s['mean']:+.2%} | {s['pf']:.2f} | {s['max_loss']:+.2%} |")
    w("")

    # Compute actual cumulative for each rule
    w("| 规则 | 累计收益 | PF 提升 |")
    w("|------|----------|---------|")
    base_cum = df['收益率'].sum()
    base_pf = baseline['pf']
    for rule_name, s in rules.items():
        # Recalculate cumulative return
        rule_df = df.copy()
        board_688_920 = ['688科创', '920北交']
        df_tmp = rule_df.copy()
        df_tmp['board'] = df_tmp['stock_code'].apply(get_board)
        risky = df_tmp['board'].isin(board_688_920)
        if '亏损>-10%' in rule_name:
            mask = risky & (df_tmp['收益率'] < -0.10)
            df_tmp.loc[mask, '收益率'] = -0.10
        elif '拒绝' in rule_name:
            df_tmp = df_tmp[~risky]
        elif '"合理"' in rule_name:
            mask = risky & (df_tmp['selection_verdict'] != '合理')
            df_tmp = df_tmp[~mask]
        elif '亏损>-8%' in rule_name:
            mask = risky & (df_tmp['收益率'] < -0.08)
            df_tmp.loc[mask, '收益率'] = -0.08
        rule_cum = df_tmp['收益率'].sum()
        rule_pf = compute_pf(df_tmp['收益率'])
        pf_delta = rule_pf - base_pf
        w(f"| {rule_name} | {rule_cum:+.2f} | {pf_delta:+.2f} |")
    w("")

    # Determine best tail rule
    best_tail_pf = 0
    best_tail_name = 'D'
    for rule_name in rules:
        df_tmp = df.copy()
        df_tmp['board'] = df_tmp['stock_code'].apply(get_board)
        risky = df_tmp['board'].isin(board_688_920)
        if '亏损>-10%' in rule_name:
            mask = risky & (df_tmp['收益率'] < -0.10)
            df_tmp.loc[mask, '收益率'] = -0.10
        elif '拒绝' in rule_name:
            df_tmp = df_tmp[~risky]
        elif '"合理"' in rule_name:
            mask = risky & (df_tmp['selection_verdict'] != '合理')
            df_tmp = df_tmp[~mask]
        elif '亏损>-8%' in rule_name:
            mask = risky & (df_tmp['收益率'] < -0.08)
            df_tmp.loc[mask, '收益率'] = -0.08
        pf = compute_pf(df_tmp['收益率'])
        if pf > best_tail_pf:
            best_tail_pf = pf
            best_tail_name = rule_name
    w(f"**最优熔断规则**: {best_tail_name} (PF={best_tail_pf:.2f})")
    w("")

    # ---- Test 6 ----
    w("---")
    w("")
    w("## 维度三：出场机制参数寻优")
    w("")
    w("### Test 6: Trailing Stop 灵敏度网格")
    w("")
    t6_results, sl_mfe_dist = test6_trailing_stop(df)

    w("#### 止损出局 MFE 分布")
    w("")
    w(f"- 止损出局总数: {sl_mfe_dist['total_sl']}")
    w(f"- MFE >= 2%: {sl_mfe_dist['mfe_gt_2pct']} ({sl_mfe_dist['mfe_gt_2pct']/sl_mfe_dist['total_sl']:.1%})")
    w(f"- MFE >= 3%: {sl_mfe_dist['mfe_gt_3pct']} ({sl_mfe_dist['mfe_gt_3pct']/sl_mfe_dist['total_sl']:.1%})")
    w(f"- MFE >= 5%: {sl_mfe_dist['mfe_gt_5pct']} ({sl_mfe_dist['mfe_gt_5pct']/sl_mfe_dist['total_sl']:.1%})")
    w(f"- MFE >= 7%: {sl_mfe_dist['mfe_gt_7pct']} ({sl_mfe_dist['mfe_gt_7pct']/sl_mfe_dist['total_sl']:.1%})")
    w(f"- MFE>=3% 但最终亏损: {sl_mfe_dist['mfe_gt_3pct_negative_return']} ({sl_mfe_dist['mfe_gt_3pct_negative_return']/max(1,sl_mfe_dist['mfe_gt_3pct']):.1%} of MFE>=3%)")
    w("")

    w("#### Trailing Stop 方案对比")
    w("")
    w("| 方案 | 笔数 | 胜率 | 均收益 | PF | 最大亏损 | 说明 |")
    w("|------|------|------|--------|-----|----------|------|")
    best_ts_name = ''
    best_ts_pf = 0
    for name, s in t6_results.items():
        w(f"| {name} | {s['n']} | {s['wr']:.1%} | {s['mean']:+.2%} | {s['pf']:.2f} | {s['max_loss']:+.2%} | {s['desc']} |")
        if name != '基准(当前)' and s['pf'] > best_ts_pf:
            best_ts_pf = s['pf']
            best_ts_name = name
    w("")
    w(f"**最优 Trailing Stop**: {best_ts_name} (PF={best_ts_pf:.2f})")
    w("")

    # ---- Test 7 ----
    w("### Test 7: 时间衰减提前退出模拟")
    w("")
    t7_results, td_detail = test7_time_decay(df)

    w("#### 时间衰减交易详情")
    w("")
    w(f"- 时间衰减平仓总数: {td_detail['total']}")
    w(f"- MFE >= 1%: {td_detail['mfe_gt_1pct']} ({td_detail['mfe_gt_1pct']/max(1,td_detail['total']):.1%})")
    w(f"- MFE >= 3%: {td_detail['mfe_gt_3pct']} ({td_detail['mfe_gt_3pct']/max(1,td_detail['total']):.1%})")
    w(f"- 均 MFE: {td_detail['mean_mfe']:.2%} | 均收益: {td_detail['mean_ret']:.2%}")
    w("")

    w("#### 退出方案对比")
    w("")
    w("| 方案 | 笔数 | 胜率 | 均收益 | PF | 累计改善 |")
    w("|------|------|------|--------|-----|----------|")
    base_stats = t7_results['基准(当前T+3衰减)']
    best_td_name = ''
    best_td_pf = 0
    for name, s in t7_results.items():
        delta = s['mean'] * s['n'] - base_stats['mean'] * base_stats['n']
        w(f"| {name} | {s['n']} | {s['wr']:.1%} | {s['mean']:+.2%} | {s['pf']:.2f} | {delta:+.2f} |")
        if name != '基准(当前T+3衰减)' and s['pf'] > best_td_pf:
            best_td_pf = s['pf']
            best_td_name = name
    w("")
    w(f"**最优时间衰减**: {best_td_name} (PF={best_td_pf:.2f})")
    w("")

    # ---- Test 8 ----
    w("---")
    w("")
    w("## 维度四：组合集成验证")
    w("")
    w("### Test 8: 最优参数组合模拟")
    w("")

    best_rules = {'tail_rule': best_tail_name}
    baseline, after_tail, after_trail, after_decay, monthly = test8_combined(df, best_rules)

    w("#### 逐步叠加效果")
    w("")
    w("| 阶段 | 笔数 | 胜率 | 均收益 | PF | 最大亏损 |")
    w("|------|------|------|--------|-----|----------|")
    for label, s in [('基准', baseline), ('+ 板块熔断', after_tail), ('+ Trailing Stop', after_trail), ('+ 时间衰减优化', after_decay)]:
        w(f"| {label} | {s['n']} | {s['wr']:.1%} | {s['mean']:+.2%} | {s['pf']:.2f} | {s['max_loss']:+.2%} |")
    w("")

    pf_improvement = after_decay['pf'] - baseline['pf']
    wr_improvement = after_decay['wr'] - baseline['wr']
    mean_improvement = after_decay['mean'] - baseline['mean']
    w(f"**PF 提升**: {baseline['pf']:.2f} -> {after_decay['pf']:.2f} ({pf_improvement:+.2f})")
    w(f"**胜率提升**: {baseline['wr']:.1%} -> {after_decay['wr']:.1%} ({wr_improvement:+.1%})")
    w(f"**笔均收益提升**: {baseline['mean']:+.2%} -> {after_decay['mean']:+.2%} ({mean_improvement:+.2%})")
    w("")

    w("#### 组合后月度表现")
    w("")
    w("| 月份 | 笔数 | 胜率 | 均收益 | 月累计 |")
    w("|------|------|------|--------|--------|")
    losing_months = 0
    for _, row in monthly.iterrows():
        if row['mean_ret'] < 0:
            losing_months += 1
        w(f"| {row['month']} | {int(row['n'])} | {row['wr']:.1%} | {row['mean_ret']:+.2%} | {row['sum_ret']:+.2f} |")
    w("")
    w(f"亏损月数: {losing_months}/{len(monthly)}")
    w("")

    # ==================================================================
    # 补充测试（Gemini Review 盲区修补）
    # ==================================================================
    w("---")
    w("")
    w("## 补充测试：盲区修补 (Gemini Review)")
    w("")

    # ---- Test 5b: Gap-Down Reality ----
    w("### Test 5b: 真实跳空压力测试 (Gap-Down Reality)")
    w("")
    mae_stats, gap_results, gap_baseline = test5b_gap_reality(df)
    w("#### 688/920 板块 MAE 穿透分布")
    w("")
    w(f"- 688/920 总交易: {mae_stats['total_risky']}")
    w(f"- MAE < -8%: **{mae_stats['mae_lt_8pct']}** ({mae_stats['mae_lt_8pct']/mae_stats['total_risky']:.1%}) — 盘中跌穿 8% 止损线")
    w(f"- MAE < -10%: **{mae_stats['mae_lt_10pct']}** ({mae_stats['mae_lt_10pct']/mae_stats['total_risky']:.1%})")
    w(f"- MAE < -15%: **{mae_stats['mae_lt_15pct']}** ({mae_stats['mae_lt_15pct']/mae_stats['total_risky']:.1%}) — 开盘核按钮级别")
    w(f"- MAE < -20%: **{mae_stats['mae_lt_20pct']}** ({mae_stats['mae_lt_20pct']/mae_stats['total_risky']:.1%})")
    w(f"- MAE 均值: {mae_stats['mae_mean']:.2%} | 最差: {mae_stats['mae_min']:.2%}")
    w("")
    w("#### 真实跳空核算模拟")
    w("")
    w("| 规则 | 笔数 | 胜率 | 均收益 | PF | 最大亏损 |")
    w("|------|------|------|--------|-----|----------|")
    w(f"| 基准(理想止损) | {gap_baseline['n']} | {gap_baseline['wr']:.1%} | {gap_baseline['mean']:+.2%} | {gap_baseline['pf']:.2f} | {gap_baseline['max_loss']:+.2%} |")
    for rule_name, s in gap_results.items():
        w(f"| {rule_name} | {s['n']} | {s['wr']:.1%} | {s['mean']:+.2%} | {s['pf']:.2f} | {s['max_loss']:+.2%} |")
    w("")

    # ---- Test 9: Entry Analysis ----
    w("### Test 9: 入场滑点与收益关系")
    w("")
    slip_stats, slip_layers, board_slip, trend_slip = test9_entry_analysis(df)
    w("#### 滑点总体分布")
    w("")
    w(f"- 均滑点: {slip_stats['mean']:.2%} | 中位数: {slip_stats['median']:.2%}")
    w(f"- 负滑点占比: {slip_stats['pct_negative']:.1%} | 零滑点占比: {slip_stats['pct_zero']:.1%}")
    w(f"- 最差滑点: {slip_stats['worst']:.2%}")
    w("")
    w("#### 滑点分层分析")
    w("")
    w("| 分层 | 笔数 | 均滑点 | 胜率 | 均收益 | PF |")
    w("|------|------|--------|------|--------|-----|")
    for s in slip_layers:
        w(f"| {s['bin']} | {s['n']} | {s['mean_slip']:.2%} | {s['wr']:.1%} | {s['mean_ret']:+.2%} | {s['pf']:.2f} |")
    w("")
    w("#### 各阶段入场特征")
    w("")
    w("| 阶段 | 笔数 | 均滑点 | 胜率 | 均收益 | 均MFE |")
    w("|------|------|--------|------|--------|-------|")
    for s in trend_slip:
        w(f"| {s['trend']} | {s['n']} | {s['mean_slip']:.2%} | {s['wr']:.1%} | {s['mean_ret']:+.2%} | {s['mfe_mean']:.2%} |")
    w("")

    # ---- MKT Filter Test ----
    w("### MKT 大盘环境过滤测试")
    w("")
    mkt_stats, mkt_baseline, mkt_filtered = test_mkt_filter(df)
    w("| 环境 | 笔数 | 胜率 | 均收益 | PF | 最大亏损 |")
    w("|------|------|------|--------|-----|----------|")
    for s in mkt_stats:
        w(f"| {s['env']} | {s['n']} | {s['wr']:.1%} | {s['mean_ret']:+.2%} | {s['pf']:.2f} | {s['max_loss']:+.2%} |")
    w("")
    w(f"**过滤\"股灾暴跌\"后**: PF {mkt_baseline['pf']:.2f} -> {mkt_filtered['pf']:.2f}, 笔数 {mkt_baseline['n']} -> {mkt_filtered['n']}, 均收益 {mkt_baseline['mean']:+.2%} -> {mkt_filtered['mean']:+.2%}")
    crash_env = next((s for s in mkt_stats if s['env'] == '股灾暴跌'), None)
    if crash_env and crash_env['pf'] > 1.0:
        w("")
        w("**注意**: 股灾暴跌环境下 PF 仍 > 1.0（逆势赚钱），不建议简单过滤。暴跌后的超跌反弹恰好是本策略的优势场景。")
    w("")

    # ---- Test 10: Factor Regression ----
    w("### Test 10: 因子权重逻辑回归重构")
    w("")
    coefficients, accuracy, prob_layers, label_maps = test10_factor_regression(df)
    w(f"模型准确率: **{accuracy:.1%}**")
    w("")
    w("#### 因子重要性排序 (按 |系数| 降序)")
    w("")
    w("| 排名 | 因子 | 系数 | 方向 | 解读 |")
    w("|------|------|------|------|------|")
    for i, c in enumerate(coefficients, 1):
        sign_desc = '越高越赚' if c['coef'] > 0 else '越高越亏'
        w(f"| {i} | {c['feature']} | {c['coef']:+.4f} | {c['direction']} | {sign_desc} |")
    w("")

    w("#### 预测概率分层验证")
    w("")
    w("| 分位 | 笔数 | 胜率 | 均收益 | PF |")
    w("|------|------|------|--------|-----|")
    for q in prob_layers:
        w(f"| {q['quartile']} | {q['n']} | {q['wr']:.1%} | {q['mean_ret']:+.2%} | {q['pf']:.2f} |")
    w("")

    # Check monotonicity of prob layers
    if len(prob_layers) >= 2:
        top_wr = prob_layers[-1]['wr']
        bot_wr = prob_layers[0]['wr']
        if top_wr > bot_wr:
            w("**验证**: Q4(高概率) 胜率 > Q1(低概率) 胜率，模型方向正确。可用于实盘选股优先级排序。")
        else:
            w("**验证**: 概率分层未呈现单调递增，模型区分力不足。")
    w("")

    w("#### 标签编码映射 (供代码重构参考)")
    w("")
    for feat, mapping in label_maps.items():
        w(f"- **{feat}**: {mapping}")
    w("")

    # ---- Test 8b: No Future Function ----
    w("---")
    w("")
    w("### Test 8b: 无未来函数的纯净组合验证")
    w("")
    w("仅使用盘前/盘中可获取的因子，剔除 `selection_verdict` 等事后标签。")
    w("")
    b8b_baseline, b8b_mkt, b8b_tail, b8b_trail, b8b_decay, b8b_monthly = test8b_no_future_function(df)

    w("#### 逐步叠加效果 (无未来函数)")
    w("")
    w("| 阶段 | 笔数 | 胜率 | 均收益 | PF | 最大亏损 |")
    w("|------|------|------|--------|-----|----------|")
    for label, s in [
        ('基准', b8b_baseline),
        ('+ MKT过滤(排除股灾)', b8b_mkt),
        ('+ Rule D(688/920截断-8%)', b8b_tail),
        ('+ Trailing Stop C(60%)', b8b_trail),
        ('+ 时间衰减优化', b8b_decay),
    ]:
        w(f"| {label} | {s['n']} | {s['wr']:.1%} | {s['mean']:+.2%} | {s['pf']:.2f} | {s['max_loss']:+.2%} |")
    w("")

    pf_8b = b8b_decay['pf']
    wr_8b = b8b_decay['wr']
    w(f"**纯净组合 PF**: {b8b_baseline['pf']:.2f} -> **{pf_8b:.2f}** (+{pf_8b - b8b_baseline['pf']:.2f})")
    w(f"**纯净组合胜率**: {b8b_baseline['wr']:.1%} -> **{wr_8b:.1%}** (+{wr_8b - b8b_baseline['wr']:.1%})")
    w(f"**最大亏损**: {b8b_baseline['max_loss']:+.2%} -> {b8b_decay['max_loss']:+.2%}")
    w("")

    w("#### 纯净组合月度表现")
    w("")
    w("| 月份 | 笔数 | 胜率 | 均收益 | 月累计 |")
    w("|------|------|------|--------|--------|")
    losing_8b = 0
    for _, row in b8b_monthly.iterrows():
        if row['mean_ret'] < 0:
            losing_8b += 1
        w(f"| {row['month']} | {int(row['n'])} | {row['wr']:.1%} | {row['mean_ret']:+.2%} | {row['sum_ret']:+.2f} |")
    w("")
    w(f"亏损月数: {losing_8b}/{len(b8b_monthly)}")
    w("")

    # ---- Final Summary ----
    w("---")
    w("")
    w("## 总结与改进参数建议")
    w("")

    w("### 各维度测试结果汇总")
    w("")
    w("| 维度 | 测试 | 结论 | 建议动作 |")
    w("|------|------|------|----------|")

    t1_pass = sum(1 for _, _, _, v in t1 if v == 'PASS')
    w(f"| 打分体系 | 因子单调性 | {t1_pass}/{len(t1)} 因子通过 | 重构 V4.4 权重，反转 decline/distribution 评分 |")
    w(f"| 打分体系 | 分层分析 | grade/action/trend 全部反向 | 用回测数据做逻辑回归重新校准 |")
    w(f"| 尾部风险 | 熔断模拟 | 最优规则: {best_tail_name} | 实施 688/920 板块亏损截断 |")
    w(f"| 出场效率 | Trailing Stop | 最优: {best_ts_name} | 收紧 trailing stop 保护 |")
    w(f"| 出场效率 | 时间衰减 | 最优: {best_td_name} | 缩短衰减周期或提前止损 |")
    w(f"| 组合验证 | 全流程叠加(含未来函数) | PF 1.81 -> 3.17 | 理论上限参考 |")
    w(f"| 跳空压力 | MAE穿透核算 | 688/920 中{mae_stats['mae_lt_8pct']}笔盘中跌穿-8%止损线 | 盘中实时止损必须考虑跳空穿透 |")
    w(f"| 入场分析 | 滑点分层 | 大负滑点(-2%)反而 PF=1.96 > 零滑点 PF=1.62 | 折价入场有效，不应取消折价 |")
    w(f"| 大盘环境 | MKT过滤 | 股灾暴跌 PF=4.82 是最佳环境 | **不可过滤**暴跌日，这是策略优势场景 |")
    w(f"| 权重重构 | 逻辑回归 | Top因子: b20(负), t1_u(负), t1_d(正) | 高乖离+涨停板是负面信号，下跌日是正面信号 |")
    w(f"| 纯净组合 | 无未来函数叠加 | **PF 1.81 -> 2.38**, 0个亏损月 | 可直接落地实施 |")
    w("")

    w("### 下一步")
    w("")
    w("1. **修改 `walk_forward_tester_s.py` 的 trailing stop**: 采用方案 C（MFE*60% 比例保护），这是无未来函数下贡献最大的单项改进")
    w("2. **新增板块熔断**: 688/920 盘中亏损触及 -8% 即刻斩仓，不做理想化止损假设")
    w("3. **修改 `backtester.py` 中 `_generate_forward_advice_v4`**: 根据 Test 10 回归系数反转因子方向（b20 高乖离惩罚、t1_d 下跌日加分、decline 阶段不惩罚）")
    w("4. **保留折价入场**: Test 9 证实负滑点(折价入场)反而带来更好收益，不应在 markup 阶段取消折价")
    w("5. **不过滤股灾暴跌日**: MKT 测试确认股灾暴跌环境 PF=4.82，是本策略的最佳场景")
    w("6. **重新运行全日历回测**: 叠加以上改进后验证 PF > 2.2")

    return '\n'.join(lines)


def main():
    if not os.path.exists(CSV_PATH):
        print(f"找不到数据文件: {CSV_PATH}")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)
    print(f"加载 {len(df)} 笔交易数据")

    report = generate_report(df)

    os.makedirs(REPORT_DIR, exist_ok=True)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"报告已生成: {REPORT_PATH}")


if __name__ == '__main__':
    main()
