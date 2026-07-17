"""
诊断目标价计算偏差的模拟验证脚本
基于 morse_price_validation_matrix_v2.csv 的历史数据，
用当前公式 vs 修正公式分别回测对比效果
"""
import pandas as pd
import numpy as np

df = pd.read_csv('data/result/Calendar_Backtest/morse_price_validation_matrix_v2.csv')

# 只分析 entry_hit=True 的样本（实际能成交的）
active = df[df.entry_hit == True].copy()
print(f"分析样本: {len(active)} 条 (entry_hit=True)")
print()

# ==========================================
# 方法1: 还原当前的 target 计算逻辑
# ==========================================
# 我们需要从现有数据反推参数
# target_bias_pct = (future_max - pred_target) / pred_target
# 所以 pred_target > future_max 时 target_bias_pct < 0 (目标过高)

# 当前公式拆解模拟:
# base_target_mult = 3.2 - (trend_risk_score - 0.5) * 1.8 - (bias_penalty * 0.6)
# 我们知道:
#   distribution: trend_risk_score=0.85
#   accumulation: trend_risk_score=0.55
#   markup: trend_risk_score=0.9
#   decline: trend_risk_score=1.85

# bias_penalty 计算:
# if bias_pct > 0.15: bias_penalty = max(-0.35, bias_pct * -1.6)
# else: bias_penalty = max(-0.7, bias_pct * -2.0)

trend_risk_map = {'decline': 1.85, 'distribution': 0.85, 'accumulation': 0.55, 'markup': 0.9}

def compute_bias_penalty(bias_pct):
    if bias_pct > 0.15:
        return max(-0.35, bias_pct * -1.6)
    else:
        return max(-0.7, bias_pct * -2.0)

# 反推 bias_pct: 从 pred_entry 和 current_price 可以大致反推
# pred_entry ≈ current_price - atr * pullback_multiplier
# 但更直接的方法是从 bias_tier 估算

tier_to_bias = {
    '高位极度乖离(>15%)': 0.20,
    '多头偏离(5%~15%)': 0.10,
    '均值回归(±5%)': 0.0,
    '空头偏离(-15%~-5%)': -0.10,
    '深渊超跌(<-15%)': -0.20,
}

def simulate_current_target(row):
    """用当前公式模拟计算 target"""
    trend_risk_score = trend_risk_map.get(row.trend_phase, 1.0)
    bias_pct = tier_to_bias.get(row.bias_tier, 0.0)
    bias_penalty = compute_bias_penalty(bias_pct)
    
    # 当前公式
    base_target_mult = 3.2 - (trend_risk_score - 0.5) * 1.8 - (bias_penalty * 0.6)
    # 假设 is_high_vol = False (大部分情况)
    target_multiplier = max(1.2, base_target_mult)
    
    # 估算 atr: 从 pred_entry = current_price - atr * pullback_multiplier 反推
    # pullback_multiplier ≈ trend_risk_score + bias_penalty (+ vol_penalty)
    vol_penalty = 0.0
    pullback_mult = trend_risk_score + bias_penalty + vol_penalty
    pullback_mult = max(0.25, min(pullback_mult, 2.2))
    
    entry_diff = row.current_price - row.pred_entry
    if pullback_mult > 0 and entry_diff > 0:
        estimated_atr = entry_diff / pullback_mult
    else:
        estimated_atr = row.current_price * 0.04  # 默认4%
    
    board_limit_map = {'10CM': 0.10, '20CM': 0.20, '30CM': 0.30}
    board_limit = board_limit_map.get(row.board_type, 0.10)
    MAX_PROFIT_CAP = board_limit * 1.6
    
    target_add = min(estimated_atr * target_multiplier, row.pred_entry * MAX_PROFIT_CAP)
    sim_target = row.pred_entry + target_add
    
    # resistance 约束 (简化: 假设有阻力时 target 被压低到 0.975 * resistance)
    if pd.notna(row.resistance_level) and row.resistance_level > 0:
        if row.trend_phase == 'accumulation' and bias_pct < 0.08:
            sim_target = max(sim_target, row.resistance_level * 1.015)
        else:
            sim_target = min(sim_target, row.resistance_level * 0.975)
    
    return round(sim_target, 2)

def simulate_fixed_target_v1(row):
    """修正版1: 降低 base_target_mult 基数, 修正 bias_penalty 方向"""
    trend_risk_score = trend_risk_map.get(row.trend_phase, 1.0)
    bias_pct = tier_to_bias.get(row.bias_tier, 0.0)
    bias_penalty = compute_bias_penalty(bias_pct)
    
    # 修正1: 基数从 3.2 降到 2.2
    # 修正2: bias_penalty 在 target 中应该是正向惩罚(高位乖离降低目标)
    base_target_mult = 2.2 - (trend_risk_score - 0.5) * 1.2 + (bias_penalty * 0.4)
    target_multiplier = max(1.0, base_target_mult)
    
    vol_penalty = 0.0
    pullback_mult = trend_risk_score + bias_penalty + vol_penalty
    pullback_mult = max(0.25, min(pullback_mult, 2.2))
    
    entry_diff = row.current_price - row.pred_entry
    if pullback_mult > 0 and entry_diff > 0:
        estimated_atr = entry_diff / pullback_mult
    else:
        estimated_atr = row.current_price * 0.04
    
    board_limit_map = {'10CM': 0.10, '20CM': 0.20, '30CM': 0.30}
    board_limit = board_limit_map.get(row.board_type, 0.10)
    MAX_PROFIT_CAP = board_limit * 1.3  # 从 1.6 降到 1.3
    
    target_add = min(estimated_atr * target_multiplier, row.pred_entry * MAX_PROFIT_CAP)
    sim_target = row.pred_entry + target_add
    
    if pd.notna(row.resistance_level) and row.resistance_level > 0:
        if row.trend_phase == 'accumulation' and bias_pct < 0.08:
            sim_target = max(sim_target, row.resistance_level * 1.01)
        else:
            sim_target = min(sim_target, row.resistance_level * 0.96)
    
    return round(sim_target, 2)

def simulate_fixed_target_v2(row):
    """修正版2: 更激进的方案 - 基于 market_span 校准"""
    trend_risk_score = trend_risk_map.get(row.trend_phase, 1.0)
    bias_pct = tier_to_bias.get(row.bias_tier, 0.0)
    bias_penalty = compute_bias_penalty(bias_pct)
    
    # 完全重构: target = entry * (1 + expected_return)
    # expected_return 基于 trend_phase 和历史 market_span
    base_return = {
        'decline': 0.03,
        'distribution': 0.06,
        'accumulation': 0.10,
        'markup': 0.08,
    }.get(row.trend_phase, 0.06)
    
    # 高位乖离降低预期
    if bias_pct > 0.15:
        base_return *= 0.7
    elif bias_pct > 0.05:
        base_return *= 0.85
    elif bias_pct < -0.15:
        base_return *= 0.6  # 超跌反弹不确定
    
    board_limit_map = {'10CM': 0.10, '20CM': 0.20, '30CM': 0.30}
    board_limit = board_limit_map.get(row.board_type, 0.10)
    
    target_price = row.pred_entry * (1 + base_return)
    target_price = min(target_price, row.pred_entry * (1 + board_limit * 1.2))
    
    if pd.notna(row.resistance_level) and row.resistance_level > 0:
        target_price = min(target_price, row.resistance_level * 0.96)
    
    return round(target_price, 2)


# ==========================================
# 运行模拟对比
# ==========================================
active['sim_current_target'] = active.apply(simulate_current_target, axis=1)
active['sim_fixed_v1_target'] = active.apply(simulate_fixed_target_v1, axis=1)
active['sim_fixed_v2_target'] = active.apply(simulate_fixed_target_v2, axis=1)

# 计算各版本的 target_hit 和 bias
for col in ['sim_current_target', 'sim_fixed_v1_target', 'sim_fixed_v2_target']:
    active[f'{col}_hit'] = (active.future_min_low <= active[col]) & (active[col] <= active.future_max_high)
    active[f'{col}_bias'] = (active.future_max_high - active[col]) / active[col]

print("=" * 80)
print("回测对比结果 (entry_hit=True 样本)")
print("=" * 80)

versions = [
    ('实际算法(pred_target)', 'pred_target'),
    ('模拟当前公式', 'sim_current_target'),
    ('修正版1(调参)', 'sim_fixed_v1_target'),
    ('修正版2(重构)', 'sim_fixed_v2_target'),
]

for label, col in versions:
    target_col = col if col != 'pred_target' else 'pred_target'
    hit_col = 'target_hit' if col == 'pred_target' else f'{col}_hit'
    bias_col = 'target_bias_pct' if col == 'pred_target' else f'{col}_bias'
    
    hit_rate = active[hit_col].mean() * 100
    mean_bias = active[bias_col].mean()
    median_bias = active[bias_col].median()
    neg_bias_pct = (active[bias_col] < 0).mean() * 100
    
    print(f"\n{label}:")
    print(f"  target_hit率: {hit_rate:.1f}%")
    print(f"  target_bias 均值: {mean_bias:.4f} (正值=利润外溢, 负值=目标过高)")
    print(f"  target_bias 中位数: {median_bias:.4f}")
    print(f"  目标过高比例(bias<0): {neg_bias_pct:.1f}%")

# 分场景对比
print("\n" + "=" * 80)
print("分场景对比 target_hit 率")
print("=" * 80)

for dim in ['trend_phase', 'board_type', 'bias_tier']:
    print(f"\n--- 按 {dim} ---")
    for val in active[dim].unique():
        sub = active[active[dim] == val]
        if len(sub) < 10:
            continue
        orig_hit = sub.target_hit.mean() * 100
        v1_hit = sub['sim_fixed_v1_target_hit'].mean() * 100
        v2_hit = sub['sim_fixed_v2_target_hit'].mean() * 100
        print(f"  {val} ({len(sub)}条): 原始={orig_hit:.1f}% -> 修正v1={v1_hit:.1f}% -> 修正v2={v2_hit:.1f}%")

# 利润空间分析
print("\n" + "=" * 80)
print("利润空间分析")
print("=" * 80)

for label, col in versions:
    target_col = col
    expected_profit = ((active[target_col] / active.pred_entry) - 1).mean() * 100
    actual_profit = ((active.future_max_high / active.pred_entry) - 1).mean() * 100
    print(f"{label}: 平均预期利润={expected_profit:.2f}%, 实际可达利润={actual_profit:.2f}%, 差值={expected_profit-actual_profit:.2f}%")
