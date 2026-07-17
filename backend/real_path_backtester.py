"""
P0-1: 真实路径回测
替代 MFE 模拟，使用每日实际 high/low/close 检查止损/止盈

交易规则:
  - 买入价 = T+1 开盘价（跳空>5%不买）
  - 每日检查: low ≤ 止损线 → 止损出场; high ≥ 止盈线 → 止盈出场
  - 持有 22 天未触发 → 按第 22 天收盘价结算
  - 止损: -8%, 止盈: +30%, 手续费: 双边 0.15%
"""

import pandas as pd
import numpy as np
import os
import sys
import pickle
from datetime import datetime
from functools import lru_cache
import warnings
warnings.filterwarnings('ignore')

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

COMMISSION = 0.0015
STOP_LOSS = -0.08
TAKE_PROFIT = 0.30
HOLDING_DAYS = 22
TOP_N = 20
MAX_GAP_PCT = 0.05

_stock_cache = {}


def load_stock_daily(stock_code):
    """加载个股日线数据（带缓存）"""
    if stock_code in _stock_cache:
        return _stock_cache[stock_code]
    try:
        from data_handler import get_full_data_with_indicators
        df = get_full_data_with_indicators(stock_code)
        if df is not None and not df.empty:
            df.index = pd.to_datetime(df.index)
        _stock_cache[stock_code] = df
        return df
    except Exception:
        _stock_cache[stock_code] = None
        return None


def simulate_real_path_trade(df_stock, t0_date, stop_loss=STOP_LOSS,
                              take_profit=TAKE_PROFIT, holding_days=HOLDING_DAYS):
    """
    用真实日线价格路径模拟单笔交易。

    返回:
        dict: {return_pct, exit_day, exit_reason, daily_returns}
    """
    if df_stock is None or len(df_stock) < 5:
        return {'return_pct': 0, 'exit_day': 0, 'exit_reason': 'no_data', 'daily_returns': []}

    t0_ts = pd.Timestamp(t0_date)
    t0_matches = df_stock.index[df_stock.index == t0_ts]
    if len(t0_matches) == 0:
        closest = df_stock.index.searchsorted(t0_ts)
        if closest >= len(df_stock):
            return {'return_pct': 0, 'exit_day': 0, 'exit_reason': 'date_not_found', 'daily_returns': []}
        t0_idx = closest
    else:
        t0_idx = df_stock.index.get_loc(t0_ts)

    t0_close = df_stock.iloc[t0_idx]['close']
    t1_idx = t0_idx + 1
    if t1_idx >= len(df_stock):
        return {'return_pct': 0, 'exit_day': 0, 'exit_reason': 'no_t1', 'daily_returns': []}

    t1_open = df_stock.iloc[t1_idx]['open']
    gap_pct = (t1_open / t0_close) - 1.0 if t0_close > 0.01 else np.nan
    if pd.notna(gap_pct) and gap_pct > MAX_GAP_PCT:
        return {'return_pct': 0, 'exit_day': 0, 'exit_reason': 'gap_filter',
                'gap_pct': gap_pct, 'daily_returns': []}

    buy_price = t1_open
    stop_price = buy_price * (1 + stop_loss)
    target_price = buy_price * (1 + take_profit)

    exit_day = holding_days
    exit_price = None
    exit_reason = 'hold_to_end'
    daily_returns = []

    max_future = min(t1_idx + holding_days, len(df_stock))
    for day_offset in range(1, max_future - t1_idx + 1):
        day_idx = t1_idx + day_offset - 1
        if day_idx >= len(df_stock):
            break

        day_data = df_stock.iloc[day_idx]
        day_low = day_data['low']
        day_high = day_data['high']
        day_close = day_data['close']

        pnl_low = (day_low / buy_price) - 1.0
        pnl_high = (day_high / buy_price) - 1.0
        pnl_close = (day_close / buy_price) - 1.0
        daily_returns.append(pnl_close)

        if day_low <= stop_price:
            exit_day = day_offset
            exit_price = stop_price
            exit_reason = 'stop_loss'
            break
        elif day_high >= target_price:
            exit_day = day_offset
            exit_price = target_price
            exit_reason = 'take_profit'
            break
    else:
        end_idx = min(t1_idx + holding_days - 1, len(df_stock) - 1)
        exit_price = df_stock.iloc[end_idx]['close']

    if exit_price is None:
        end_idx = min(t1_idx + holding_days - 1, len(df_stock) - 1)
        exit_price = df_stock.iloc[end_idx]['close']

    return_pct = (exit_price / buy_price) - 1.0

    return {
        'return_pct': return_pct,
        'exit_day': exit_day,
        'exit_reason': exit_reason,
        'buy_price': buy_price,
        'exit_price': exit_price,
        'gap_pct': gap_pct if pd.notna(gap_pct) else 0,
        'daily_returns': daily_returns,
    }


def run_real_path_backtest(trades_csv, top_n=TOP_N):
    """
    用真实价格路径重跑回测。

    trades_csv: 旧回测产出的交易明细（含 date, stock_code, score）
    """
    from super_trend_ranker_trainer import SuperTrendRanker

    model_path = os.path.join(_PROJECT_ROOT, 'data', 'result', 'super_trend',
                              'models', 'trend_ranker_v1.pkl')
    data_path = os.path.join(_PROJECT_ROOT, 'data', 'result', 'super_trend',
                             'super_trend_training_data_v2.csv')

    with open(model_path, 'rb') as f:
        model_data = pickle.load(f)
    model = model_data['model']
    feature_columns = model_data['feature_columns']

    df = pd.read_csv(data_path)
    df = df.sort_values('t0_date').reset_index(drop=True)
    split_idx = int(len(df) * 0.8)
    test_df = df.iloc[split_idx:].copy()

    available_features = [c for c in feature_columns if c in test_df.columns]
    X_test = test_df[available_features].fillna(0)
    scores = model.predict(X_test)
    test_df['_score'] = scores

    test_dates = sorted(test_df['t0_date'].unique())
    print(f"\n=== 真实路径回测 ===")
    print(f"测试期: {test_dates[0]} ~ {test_dates[-1]}, {len(test_dates)} 个交易日")

    all_trades = []
    daily_pnl = []

    for date in test_dates:
        day_df = test_df[test_df['t0_date'] == date].copy()
        if len(day_df) < top_n:
            continue

        day_top = day_df.nlargest(top_n, '_score')
        day_return = 0.0
        n_bought = 0

        for _, row in day_top.iterrows():
            stock_code = row['stock_code']
            result = simulate_real_path_trade(
                load_stock_daily(stock_code), date
            )

            if result['exit_reason'] == 'gap_filter':
                continue

            net_return = result['return_pct'] - 2 * COMMISSION

            trade = {
                'date': date,
                'stock_code': stock_code,
                'score': row['_score'],
                'return_pct': result['return_pct'],
                'net_return': net_return,
                'exit_day': result['exit_day'],
                'exit_reason': result['exit_reason'],
                'buy_price': result.get('buy_price', 0),
                'exit_price': result.get('exit_price', 0),
                'gap_pct': result.get('gap_pct', 0),
                'future_mfe': row.get('future_mfe', 0),
            }
            all_trades.append(trade)
            day_return += net_return
            n_bought += 1

        if n_bought > 0:
            daily_pnl.append({
                'date': date,
                'n_stocks': n_bought,
                'avg_return': day_return / n_bought,
                'total_return': day_return,
            })

        loaded = len(_stock_cache)
        if len(all_trades) % 200 == 0 and len(all_trades) > 0:
            print(f"  已处理 {len(all_trades)} 笔, 已缓存 {loaded} 只股票...")

    trades_df = pd.DataFrame(all_trades)
    daily_df = pd.DataFrame(daily_pnl)

    stats = compute_real_stats(trades_df, daily_df)
    print_results(stats)

    # 与旧 MFE 回测对比
    print_mfe_comparison(trades_df)

    # 按退出原因统计
    print_exit_reason_breakdown(trades_df)

    return trades_df, daily_df, stats


def compute_real_stats(trades_df, daily_df):
    """计算真实路径回测统计"""
    if trades_df.empty:
        return {'error': '无交易记录'}

    n_trades = len(trades_df)
    n_days = len(daily_df)

    avg_return = trades_df['net_return'].mean()
    median_return = trades_df['net_return'].median()
    winning = trades_df[trades_df['net_return'] > 0]
    losing = trades_df[trades_df['net_return'] <= 0]
    win_rate = len(winning) / n_trades if n_trades > 0 else 0

    avg_win = winning['net_return'].mean() if len(winning) > 0 else 0
    avg_loss = abs(losing['net_return'].mean()) if len(losing) > 0 else 1
    profit_factor = avg_win / avg_loss if avg_loss > 0 else float('inf')

    # 逐笔交易期望值 (bps)
    ev_bps = avg_return * 10000

    # 简单年化估算 (非复利, 等权分配)
    trades_per_year = n_trades / max(n_days / 252, 0.5)
    simple_annual = avg_return * trades_per_year

    # 日复利组合净值 (100% daily rebalance, 仅供参考)
    daily_returns = daily_df['avg_return'].values
    cum_returns = np.cumprod(1 + daily_returns)
    total_return = cum_returns[-1] - 1 if len(cum_returns) > 0 else 0

    n_years = n_days / 252
    annualized_return = (1 + total_return) ** (1 / max(n_years, 0.01)) - 1

    if np.std(daily_returns) > 0:
        sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
    else:
        sharpe = 0

    running_max = np.maximum.accumulate(cum_returns)
    drawdowns = (cum_returns - running_max) / running_max
    max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0

    avg_exit_day = trades_df['exit_day'].mean()

    n_stop = len(trades_df[trades_df['exit_reason'].isin(['stop_loss', 'stop_loss_atr'])])
    n_tp = len(trades_df[trades_df['exit_reason'] == 'take_profit'])
    n_trail = len(trades_df[trades_df['exit_reason'] == 'trailing_stop'])
    n_hold = len(trades_df[trades_df['exit_reason'] == 'hold_to_end'])

    # MFE 捕获分析
    avg_mfe = trades_df['future_mfe'].mean() if 'future_mfe' in trades_df.columns else 0
    mfe_capture = avg_return / avg_mfe if avg_mfe > 0 else 0

    # 持有到期子统计 (信号纯净度指标)
    hold_df = trades_df[trades_df['exit_reason'] == 'hold_to_end']
    hold_avg = hold_df['net_return'].mean() if len(hold_df) > 0 else 0
    hold_wr = len(hold_df[hold_df['net_return'] > 0]) / len(hold_df) if len(hold_df) > 0 else 0

    # 止损交易的 MFE (被误杀程度)
    sl_df = trades_df[trades_df['exit_reason'].isin(['stop_loss', 'stop_loss_atr'])]
    sl_avg_mfe = sl_df['future_mfe'].mean() if len(sl_df) > 0 and 'future_mfe' in sl_df.columns else 0

    return {
        'total_trades': n_trades,
        'trading_days': n_days,
        'ev_per_trade': avg_return,
        'ev_bps': ev_bps,
        'simple_annual': simple_annual,
        'trades_per_year': trades_per_year,
        'total_return': total_return,
        'annualized_return': annualized_return,
        'sharpe_ratio': sharpe,
        'max_drawdown': max_drawdown,
        'win_rate': win_rate,
        'avg_return': avg_return,
        'median_return': median_return,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
        'profit_factor': profit_factor,
        'avg_exit_day': avg_exit_day,
        'n_stop_loss': n_stop,
        'n_take_profit': n_tp,
        'n_trailing_stop': n_trail,
        'n_hold': n_hold,
        'avg_mfe': avg_mfe,
        'mfe_capture': mfe_capture,
        'hold_avg_return': hold_avg,
        'hold_win_rate': hold_wr,
        'stop_loss_avg_mfe': sl_avg_mfe,
    }


def print_results(stats):
    """打印回测结果"""
    print(f"\n{'='*60}")
    print(f"  真实路径回测结果")
    print(f"{'='*60}")
    print(f"  总交易笔数:     {stats['total_trades']}")
    print(f"  交易天数:       {stats['trading_days']}")
    print(f"  ── 逐笔交易指标 (核心) ──")
    print(f"  每笔期望值:     {stats['ev_per_trade']:+.4f} ({stats['ev_bps']:+.0f} bps)")
    ev_ok = '✅ 正期望' if stats['ev_bps'] > 0 else '❌ 负期望'
    print(f"  期望值判定:     {ev_ok}")
    print(f"  简单年化:       {stats['simple_annual']:+.2%} (每笔 EV × {stats['trades_per_year']:.0f} 笔/年)")
    print(f"  胜率:           {stats['win_rate']:.2%}")
    print(f"  平均收益:       {stats['avg_return']:+.4f}")
    print(f"  中位收益:       {stats['median_return']:+.4f}")
    print(f"  平均盈利:       {stats['avg_win']:+.4f}")
    print(f"  平均亏损:       {stats['avg_loss']:.4f}")
    print(f"  盈亏比:         {stats['profit_factor']:.2f}")
    print(f"  ── 退出分布 ──")
    n = stats['total_trades']
    print(f"  止损出场:       {stats['n_stop_loss']} ({stats['n_stop_loss']/n:.1%})")
    print(f"  止盈出场:       {stats['n_take_profit']} ({stats['n_take_profit']/n:.1%})")
    if stats.get('n_trailing_stop', 0) > 0:
        print(f"  追踪止损:       {stats['n_trailing_stop']} ({stats['n_trailing_stop']/n:.1%})")
    print(f"  持有到期:       {stats['n_hold']} ({stats['n_hold']/n:.1%})")
    print(f"  平均持仓天数:   {stats['avg_exit_day']:.1f}")
    print(f"  ── MFE 捕获分析 ──")
    print(f"  平均 future_mfe:  {stats['avg_mfe']:.2%}")
    print(f"  MFE 捕获率:       {stats['mfe_capture']:.1%} (实际收益/MFE)")
    print(f"  止损交易 avg MFE: {stats['stop_loss_avg_mfe']:.2%} (被误杀程度)")
    print(f"  ── 持有到期信号质量 ──")
    print(f"  持有到期笔数:     {stats['n_hold']}")
    print(f"  持有到期平均收益: {stats['hold_avg_return']:+.2%}")
    print(f"  持有到期胜率:     {stats['hold_win_rate']:.1%}")
    hold_ok = '✅ 选股有效' if stats['hold_avg_return'] > 0 else '❌ 选股无效'
    print(f"  信号判定:         {hold_ok}")
    print(f"  ── 组合净值 (100% daily rebalance, 仅供参考) ──")
    print(f"  日复利终值:     {1 + stats['total_return']:.6f}")
    print(f"  年化收益:       {stats['annualized_return']:.2%}")
    print(f"  夏普比率:       {stats['sharpe_ratio']:.2f}")
    print(f"  最大回撤:       {stats['max_drawdown']:.2%}")
    print(f"{'='*60}")


def print_mfe_comparison(trades_df):
    """与 MFE 模拟对比"""
    print(f"\n── MFE模拟 vs 真实路径对比 ──")
    mfe_sim_return = trades_df['future_mfe'].mean() * 0.5 - 2 * COMMISSION
    real_return = trades_df['net_return'].mean()
    print(f"  MFE模拟平均收益:  {mfe_sim_return:.4f}")
    print(f"  真实路径平均收益: {real_return:.4f}")
    print(f"  回测水分挤出:     {(mfe_sim_return - real_return):.4f} ({(mfe_sim_return - real_return)/abs(mfe_sim_return)*100:.1f}%)")


def print_exit_reason_breakdown(trades_df):
    """按退出原因分组统计"""
    print(f"\n── 退出原因分组统计 ──")
    for reason in ['stop_loss', 'take_profit', 'hold_to_end']:
        subset = trades_df[trades_df['exit_reason'] == reason]
        if len(subset) > 0:
            print(f"  {reason:<15} n={len(subset):>5}  avg={subset['net_return'].mean():.4f}  "
                  f"win_rate={len(subset[subset['net_return']>0])/len(subset):.1%}  "
                  f"avg_days={subset['exit_day'].mean():.1f}")


def _extract_raw_trade_path(df_stock, t0_date, holding_days=HOLDING_DAYS):
    """
    抽取单笔交易在日期 t0_date 之后的原始价格路径，不做任何出场判断。

    返回:
        dict:
            buy_price: T+1 开盘价
            atr_at_entry: T0 当日的 ATR(20)
            gap_pct: T+1 开盘相对 T0 收盘的跳空幅度
            future_days: list of dict(open, high, low, close)，长度 up to holding_days
    返回 None 的情形: 数据缺失 / 日期未找到 / T+1 不存在 / 跳空 > MAX_GAP_PCT
    """
    if df_stock is None or len(df_stock) < 5:
        return None

    t0_ts = pd.Timestamp(t0_date)
    t0_matches = df_stock.index[df_stock.index == t0_ts]
    if len(t0_matches) == 0:
        closest = df_stock.index.searchsorted(t0_ts)
        if closest >= len(df_stock):
            return None
        t0_idx = closest
    else:
        t0_idx = df_stock.index.get_loc(t0_ts)

    t0_close = df_stock.iloc[t0_idx]['close']
    t1_idx = t0_idx + 1
    if t1_idx >= len(df_stock):
        return None

    t1_open = df_stock.iloc[t1_idx]['open']
    gap_pct = (t1_open / t0_close) - 1.0 if t0_close > 0.01 else np.nan
    if pd.notna(gap_pct) and gap_pct > MAX_GAP_PCT:
        return None

    atr_at_entry = None
    if 'atr' in df_stock.columns:
        atr_val = df_stock.iloc[t0_idx]['atr']
        if pd.notna(atr_val) and atr_val > 0:
            atr_at_entry = float(atr_val)

    max_end = min(t1_idx + holding_days, len(df_stock))
    future_days = []
    for i in range(t1_idx, max_end):
        row = df_stock.iloc[i]
        future_days.append({
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
        })

    return {
        'buy_price': float(t1_open),
        'atr_at_entry': atr_at_entry,
        'gap_pct': float(gap_pct) if pd.notna(gap_pct) else 0.0,
        'future_days': future_days,
    }


def simulate_real_path_trade_v2(raw, stop_loss=STOP_LOSS, take_profit=TAKE_PROFIT,
                                scheme='fixed', atr_mult=2.0,
                                trailing_activation=0.15, trailing_pct=0.08,
                                holding_days=HOLDING_DAYS):
    """
    支持多种出场方案的单笔交易模拟。

    scheme:
      - 'fixed':    固定百分比止损/止盈 (默认，与原 simulate_real_path_trade 等价)
      - 'atr':      ATR 动态止损, 止损线 = buy_price - atr_mult * ATR(20)
      - 'trailing': 追踪止损, 浮盈 >= activation 后, 从最高点回撤 trailing_pct 出场
    """
    if raw is None:
        return None

    buy_price = raw['buy_price']
    if buy_price is None or buy_price <= 0:
        return None

    days = raw['future_days']
    atr_at_entry = raw.get('atr_at_entry', None)
    n_days = len(days)
    if n_days == 0:
        return None

    exit_price = None
    exit_day = holding_days
    exit_reason = 'hold_to_end'

    if scheme == 'fixed':
        stop_price = buy_price * (1 + stop_loss)
        target_price = buy_price * (1 + take_profit)
        for i, d in enumerate(days):
            if d['low'] <= stop_price:
                exit_price = stop_price
                exit_day = i + 1
                exit_reason = 'stop_loss'
                break
            if d['high'] >= target_price:
                exit_price = target_price
                exit_day = i + 1
                exit_reason = 'take_profit'
                break

    elif scheme == 'atr':
        if atr_at_entry is None or atr_at_entry <= 0 or pd.isna(atr_at_entry):
            atr_at_entry = buy_price * 0.05
        stop_price = buy_price - atr_mult * atr_at_entry
        target_price = buy_price * (1 + take_profit)
        for i, d in enumerate(days):
            if d['low'] <= stop_price:
                exit_price = stop_price
                exit_day = i + 1
                exit_reason = 'stop_loss_atr'
                break
            if d['high'] >= target_price:
                exit_price = target_price
                exit_day = i + 1
                exit_reason = 'take_profit'
                break

    elif scheme == 'trailing':
        stop_price = buy_price * (1 + stop_loss)
        target_price = buy_price * (1 + take_profit)
        peak_price = buy_price
        trailing_active = False
        for i, d in enumerate(days):
            if not trailing_active:
                if d['low'] <= stop_price:
                    exit_price = stop_price
                    exit_day = i + 1
                    exit_reason = 'stop_loss'
                    break
                if d['high'] >= target_price:
                    exit_price = target_price
                    exit_day = i + 1
                    exit_reason = 'take_profit'
                    break
                if d['high'] > peak_price:
                    peak_price = d['high']
                if (peak_price / buy_price - 1) >= trailing_activation:
                    trailing_active = True
            if trailing_active:
                if d['high'] > peak_price:
                    peak_price = d['high']
                trailing_stop = peak_price * (1 - trailing_pct)
                trailing_stop = max(trailing_stop, stop_price)
                if d['low'] <= trailing_stop:
                    exit_price = max(trailing_stop, d['open'])
                    if d['open'] <= trailing_stop:
                        exit_price = trailing_stop
                    exit_day = i + 1
                    exit_reason = 'trailing_stop'
                    break

    if exit_price is None:
        exit_price = days[-1]['close']
        exit_day = n_days

    return {
        'return_pct': (exit_price / buy_price) - 1.0,
        'exit_day': exit_day,
        'exit_reason': exit_reason,
        'buy_price': buy_price,
        'exit_price': exit_price,
    }


def precompute_raw_trade_paths(test_df, model, feature_columns,
                               start_date, end_date, top_n=TOP_N):
    """
    对指定区间内每日的 Top N 股票，预计算 raw trade paths (entry price + ATR + 未来 OHLC)，
    供后续多方案参数网格复用，避免重复加载日线数据。
    """
    mask = (test_df['t0_date'] >= start_date) & (test_df['t0_date'] <= end_date)
    sub = test_df[mask].copy()
    if sub.empty:
        return []

    feats = [c for c in feature_columns if c in sub.columns]
    sub['_score'] = model.predict(sub[feats].fillna(0))

    dates = sorted(sub['t0_date'].unique())
    raw_paths = []

    for date in dates:
        day_df = sub[sub['t0_date'] == date]
        if len(day_df) < top_n:
            continue
        day_top = day_df.nlargest(top_n, '_score')
        for _, row in day_top.iterrows():
            stock_code = row['stock_code']
            df_stock = load_stock_daily(stock_code)
            raw = _extract_raw_trade_path(df_stock, date, HOLDING_DAYS)
            if raw is None:
                continue
            raw['date'] = date
            raw['stock_code'] = stock_code
            raw['score'] = row['_score']
            raw['future_mfe'] = row.get('future_mfe', np.nan)
            raw_paths.append(raw)

    return raw_paths


def run_backtest_with_v2(raw_paths, **kwargs):
    """
    对一组预计算的 raw paths 应用 v2 策略 (scheme / stop_loss / take_profit / atr_mult /
    trailing_activation / trailing_pct)，返回 trades_df / daily_df / stats。
    """
    all_trades = []
    daily_pnl = []

    grouped = {}
    for r in raw_paths:
        grouped.setdefault(r['date'], []).append(r)

    for date in sorted(grouped.keys()):
        day_return = 0.0
        n_bought = 0
        for raw in grouped[date]:
            result = simulate_real_path_trade_v2(raw, **kwargs)
            if result is None:
                continue
            net_return = result['return_pct'] - 2 * COMMISSION
            all_trades.append({
                'date': date,
                'stock_code': raw['stock_code'],
                'score': raw['score'],
                'return_pct': result['return_pct'],
                'net_return': net_return,
                'exit_day': result['exit_day'],
                'exit_reason': result['exit_reason'],
                'buy_price': result['buy_price'],
                'exit_price': result['exit_price'],
                'future_mfe': raw.get('future_mfe', np.nan),
            })
            day_return += net_return
            n_bought += 1
        if n_bought > 0:
            daily_pnl.append({
                'date': date,
                'n_stocks': n_bought,
                'avg_return': day_return / n_bought,
                'total_return': day_return,
            })

    trades_df = pd.DataFrame(all_trades)
    daily_df = pd.DataFrame(daily_pnl)
    stats = compute_real_stats(trades_df, daily_df) if not trades_df.empty else {'error': 'empty'}
    return trades_df, daily_df, stats


def main():
    print("=== P0-1: 真实路径回测 ===")

    trades_csv = os.path.join(_PROJECT_ROOT, 'data', 'result', 'super_trend',
                              'backtest_trades.csv')

    trades_df, daily_df, stats = run_real_path_backtest(trades_csv)

    if 'error' not in stats:
        out_dir = os.path.join(_PROJECT_ROOT, 'data', 'result', 'super_trend')
        trades_df.to_csv(os.path.join(out_dir, 'backtest_real_trades.csv'), index=False)
        daily_df.to_csv(os.path.join(out_dir, 'backtest_real_daily_pnl.csv'), index=False)
        print(f"\n交易明细已保存")

    return stats


if __name__ == "__main__":
    main()
