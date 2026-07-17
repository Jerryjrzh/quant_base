```python
# backend/hourly_optimizer.py
"""
60分钟K线入场/出场优化模块
定位：在日线确认的入场日/持仓期间，用小时线执行价格优化和风险预警。
     不是过滤器，而是执行层增强。
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, Any


def optimize_entry_with_hourly(df_60m_entry_day: pd.DataFrame,
                               support_price: float,
                               original_entry_price: float) -> Dict[str, Any]:
    """
    在日线确认的入场日当天，尝试寻找比次日开盘价更优的入场点。
    
    参数:
        df_60m_entry_day: 入场日当天及前一日尾盘的60分钟K线 (必须包含当日开盘价)
        support_price: 该信号对应的支撑位价格
        original_entry_price: 原系统的入场价 (通常为入场日次日开盘价，此处简化为入场日开盘价)
    
    返回:
        {
            'optimized_price': float,  # 优化后的入场价 (若未找到则为 original_entry_price)
            'is_optimized': bool,
            'reason': str,
            'skip_entry': bool,  # 是否建议放弃当日入场 (高开远离支撑)
            'early_warning': bool,  # 是否触发盘中破位预警
            'warning_reason': str
        }
    """
    result = {
        'optimized_price': original_entry_price,
        'is_optimized': False,
        'reason': '未找到优化机会',
        'skip_entry': False,
        'early_warning': False,
        'warning_reason': ''
    }

    if df_60m_entry_day.empty:
        result['reason'] = '60分钟数据为空'
        return result

    # 取当日数据 (假设 df_60m_entry_day 的日期与入场日匹配)
    day_bars = df_60m_entry_day.copy()
    if len(day_bars) < 4:
        return result

    # ---- 规则2：开盘高开保护 ----
    open_price = day_bars['open'].iloc[0]
    if open_price > support_price * 1.03:
        result['skip_entry'] = True
        result['reason'] = f'开盘高开{open_price/support_price-1:.1%}，远离支撑，放弃当日入场'
        return result

    # ---- 计算支撑触及与反转 ----
    # 寻找首次触及支撑位±1.5%的K线
    touch_tolerance = 0.015
    touch_mask = (day_bars['low'] <= support_price * (1 + touch_tolerance)) & \
                 (day_bars['low'] >= support_price * (1 - touch_tolerance))
    
    if not touch_mask.any():
        result['reason'] = '当日未触及支撑区'
        # 没有触及支撑，维持原入场价
        return result

    first_touch_idx = touch_mask.idxmax()  # 第一个触及的索引

    # 从触及点开始，向后寻找反转形态 (Pin Bar / Bullish Engulfing / 缩量企稳)
    subsequent_bars = day_bars.loc[first_touch_idx:]
    if len(subsequent_bars) < 2:
        return result

    # 计算技术指标
    subsequent_bars = subsequent_bars.copy()
    subsequent_bars['body'] = abs(subsequent_bars['close'] - subsequent_bars['open'])
    subsequent_bars['lower_shadow'] = subsequent_bars[['open', 'close']].min(axis=1) - subsequent_bars['low']
    subsequent_bars['upper_shadow'] = subsequent_bars['high'] - subsequent_bars[['open', 'close']].max(axis=1)
    subsequent_bars['vol_ma5'] = subsequent_bars['volume'].rolling(5, min_periods=1).mean().shift(1)

    # Pin Bar
    is_pinbar = (subsequent_bars['lower_shadow'] > subsequent_bars['body'] * 2) & \
                (subsequent_bars['close'] > subsequent_bars['low'] + subsequent_bars['lower_shadow'] * 0.5)

    # Bullish Engulfing
    prev_open = subsequent_bars['open'].shift(1)
    prev_close = subsequent_bars['close'].shift(1)
    is_engulf = (subsequent_bars['close'] > subsequent_bars['open']) & \
                (prev_close < prev_open) & \
                (subsequent_bars['open'] < prev_close) & \
                (subsequent_bars['close'] > prev_open)

    # 缩量企稳 (成交量 < 20期均量的80%，温和阳线)
    subsequent_bars['vol_ma20'] = subsequent_bars['volume'].rolling(20, min_periods=5).mean().shift(1)
    vol_shrink = subsequent_bars['volume'] < subsequent_bars['vol_ma20'] * 0.8
    mild_bull = (subsequent_bars['close'] > subsequent_bars['open']) & \
                ((subsequent_bars['close'] - subsequent_bars['open']) / subsequent_bars['open']).between(0.002, 0.008)
    is_shrink_stable = vol_shrink & mild_bull

    # 寻找第一个反转信号
    pattern_mask = is_pinbar | is_engulf | is_shrink_stable
    if pattern_mask.any():
        first_pattern_idx = pattern_mask.idxmax()
        # 优化入场价 = 该反转K线的下一根K线开盘价，或者若已收盘则用收盘价
        # 由于回测无法知道实盘下一根K线开盘价，我们保守地用该K线收盘价 (作为已确认信号)
        optimized_price = subsequent_bars.loc[first_pattern_idx, 'close']
        # 确保优化价在支撑位附近且优于原价
        if optimized_price < original_entry_price and optimized_price > support_price * 0.98:
            result['optimized_price'] = optimized_price
            result['is_optimized'] = True
            result['reason'] = f'在触及支撑后出现反转形态，优化入场价 {optimized_price:.2f} < {original_entry_price:.2f}'
        else:
            result['reason'] = '优化价格未优于原入场价或脱离支撑区'
    else:
        result['reason'] = '触及支撑后未出现有效反转形态'

    # ---- 规则3：盘中破位预警 ----
    # 检查是否有60分钟K线收盘有效跌破支撑位0.5%以上，且随后1小时未收回
    close_below = subsequent_bars['close'] < support_price * 0.995
    if close_below.any():
        first_breach_idx = close_below.idxmax()
        # 检查随后1小时 (2根K线) 是否收回
        recovery_bars = subsequent_bars.loc[first_breach_idx:].iloc[1:3]  # 后两根
        if len(recovery_bars) > 0:
            recovered = (recovery_bars['close'] > support_price).any()
            if not recovered:
                result['early_warning'] = True
                result['warning_reason'] = f'60分钟收盘跌破支撑{first_breach_idx}且未收回，建议次日开盘卖出'
                # 注意：预警触发后，实际出场逻辑在 validate 脚本中处理

    return result


def hourly_stop_loss_enhancement(df_60m_current_day: pd.DataFrame,
                                 current_stop_price: float,
                                 dynamic_support: float) -> Tuple[bool, str, Optional[float]]:
    """
    持仓期间，利用60分钟K线提前判断是否应止损。
    返回: (should_exit_early: bool, reason: str, exit_price: float or None)
    """
    if df_60m_current_day.empty:
        return False, '无数据', None

    bars = df_60m_current_day.copy()
    if len(bars) < 4:
        return False, '数据不足', None

    # 检查连续2根60分钟K线收盘价跌破当前动态支撑，且第二根不放量 (排除假破位)
    bars['close_below_support'] = bars['close'] < dynamic_support * 0.995
    bars['vol_ma5'] = bars['volume'].rolling(5, min_periods=1).mean().shift(1)
    bars['volume_not_expanding'] = bars['volume'] <= bars['vol_ma5'] * 1.2

    # 寻找连续2根满足条件
    below = bars['close_below_support'] & bars['volume_not_expanding']
    consecutive_two = below & below.shift(1)
    if consecutive_two.any():
        # 取第一次触发的位置，用第二根的收盘价作为出场价 (次日开盘更合理，但回测保守用收盘)
        exit_idx = consecutive_two.idxmax()
        exit_price = bars.loc[exit_idx, 'close']
        return True, f'60分钟连续破位{exit_idx}', exit_price

    return False, '未触发', None


def hourly_take_profit_enhancement(df_60m_current_day: pd.DataFrame,
                                   profit_ratio: float,
                                   highest_close: float) -> Tuple[bool, str]:
    """
    持仓期间，利用60分钟衰竭形态提前止盈。
    返回: (should_take_profit: bool, reason: str)
    """
    if df_60m_current_day.empty or profit_ratio < 0.05:
        return False, '盈利不足或数据为空'

    bars = df_60m_current_day.tail(8).copy()  # 最近8根K线
    if len(bars) < 4:
        return False, '数据不足'

    bars['body'] = abs(bars['close'] - bars['open'])
    bars['upper_shadow'] = bars['high'] - bars[['open', 'close']].max(axis=1)
    bars['vol_ma5'] = bars['volume'].rolling(5, min_periods=1).mean().shift(1)

    # 高位放量滞涨 (单根60分钟涨幅<0.5%，但量>3倍均量)
    is_stall = (bars['close'] > bars['open']) & \
               ((bars['close'] - bars['open']) / bars['open'] < 0.005) & \
               (bars['volume'] > bars['vol_ma5'] * 3.0)

    # 长上影线+缩量 (上影>实体2倍，量<均量)
    is_shooting_star = (bars['upper_shadow'] > bars['body'] * 2) & \
                       (bars['volume'] < bars['vol_ma5'] * 0.7)

    if is_stall.any() or is_shooting_star.any():
        return True, '60分钟出现衰竭形态'
    return False, '无衰竭信号'
```

```python
# scripts/validate_hourly_optimizer.py
"""
验证60分钟入场优化 + 持仓预警的有效性。
对比基线 (原入场价+原出场) 与优化后的盈亏。
"""

import sys
sys.path.append('.')
import pandas as pd
import numpy as np
from backend.hourly_optimizer import (
    optimize_entry_with_hourly,
    hourly_stop_loss_enhancement,
    hourly_take_profit_enhancement
)
from backend.data_handler import get_hourly_data  # 需实现

# 加载基线交易数据
trades_df = pd.read_csv('doc/0613_super_trend_v2/review4_final_backtest.csv')
baseline = trades_df[trades_df['status'] == 'traded'].copy()

# 缓存60分钟数据
cache = {}
def load_60m(stock, date):
    key = (stock, str(date)[:10])
    if key not in cache:
        # 假设 get_hourly_data 返回截至 date 的过去N天60分钟数据
        cache[key] = get_hourly_data(stock, end_date=date, lookback_days=10)
    return cache[key]

# 逐笔模拟
results = []
for idx, row in baseline.iterrows():
    stock = row['stock_code']
    entry_date = pd.Timestamp(row['entry_date'])
    original_entry = row['entry_price']  # 原系统入场价
    support = row.get('support_price', original_entry * 0.95)  # 简化

    # 加载入场日60分钟数据 (日期为 entry_date 当天)
    df_entry_day = load_60m(stock, entry_date)
    # 优化入场
    opt_result = optimize_entry_with_hourly(df_entry_day, support, original_entry)

    # 决定是否入场及入场价
    if opt_result['skip_entry']:
        # 放弃入场，盈亏为0
        results.append({
            'trade_id': idx,
            'entry_optimized': False,
            'pnl_original': row['pnl_pct'],
            'pnl_optimized': 0.0,
            'entry_price_original': original_entry,
            'entry_price_optimized': None,
            'warning_exit': False
        })
        continue

    optimized_entry = opt_result['optimized_price']

    # 模拟持仓出场：沿用原系统的出场日期/价格，但根据入场价调整盈亏
    # 简化：假设出场价格不变，重新计算盈亏
    original_exit_price = row['exit_price']
    # 优化后盈亏 = (原出场价 / 优化入场价 - 1)   # 注意需扣除原系统已算的手续费影响，此处近似
    pnl_optimized = (original_exit_price / optimized_entry - 1) if optimized_entry > 0 else 0

    # 盘中预警处理：若触发 early_warning，则在次日开盘卖出 (近似用原 exit_date 的次日开盘)
    if opt_result['early_warning']:
        # 这里需要持仓期间的出场模拟，简化处理：在预警日次日开盘卖出
        # 由于没有具体路径，我们用原 exit_price 做一个粗略假设：预警出场价会优于原止损价
        # 例如，如果原出场是止损，预警提前卖出价格可能更高
        # 严谨回测需重跑出场模拟，当前先以原出场价为基准
        pass  # 留待 Phase 2 实现

    results.append({
        'trade_id': idx,
        'entry_optimized': opt_result['is_optimized'],
        'pnl_original': row['pnl_pct'],
        'pnl_optimized': pnl_optimized,
        'entry_price_original': original_entry,
        'entry_price_optimized': optimized_entry,
        'warning_exit': opt_result['early_warning']
    })

res_df = pd.DataFrame(results)

# 统计
print("========== 入场优化效果 ==========")
print(f"总交易数: {len(res_df)}")
print(f"优化入场笔数: {res_df['entry_optimized'].sum()}")
print(f"因高开放弃: {(res_df['entry_price_optimized'].isna() & ~res_df['entry_optimized']).sum()}")

valid_trades = res_df[res_df['pnl_optimized'].notna()]
original_avg = valid_trades['pnl_original'].mean()
optimized_avg = valid_trades['pnl_optimized'].mean()
print(f"原平均盈亏: {original_avg:.4f}")
print(f"优化后平均盈亏: {optimized_avg:.4f}")
print(f"改善幅度: {optimized_avg - original_avg:.4f}")

# 按月统计
valid_trades['month'] = pd.to_datetime(baseline.loc[valid_trades.index, 'entry_date']).dt.to_period('M')
monthly = valid_trades.groupby('month').agg(
    original_avg=('pnl_original', 'mean'),
    optimized_avg=('pnl_optimized', 'mean')
)
print("\n========== 月度改善 ==========")
print(monthly.to_string())

res_df.to_csv('doc/0613_super_trend_v2/hourly_entry_optimization.csv', index=False)
```

上述代码实现了您提出的新思路：**小时线用于寻找更优入场价**。接下来，您可以基于394笔真实数据运行 `validate_hourly_optimizer.py`，观察平均盈亏是否提升。如果入场优化有效，我们再继续开发出场预警模块（Phase 2）。
