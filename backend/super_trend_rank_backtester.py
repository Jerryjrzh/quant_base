"""
Super Trend V1 Phase 5: 端到端回测框架
排序模型驱动的 Top N 等权买入策略回测

交易规则:
  - 每日取模型打分 Top N 异动股票
  - 过滤: 涨停买不到, T+1 开盘跳空 > 5%
  - 等权买入, 持有 22 天或触发止损/止盈
  - 止损: -8%, 止盈: +30%
  - 手续费: 双边 0.15%
"""

import pandas as pd
import numpy as np
import os
import sys
import pickle
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

def _proj(*parts):
    return os.path.join(_PROJECT_ROOT, *parts)


COMMISSION = 0.0015  # 双边手续费 0.15%
STOP_LOSS = -0.08    # 止损 -8%
TAKE_PROFIT = 0.30   # 止盈 +30%
HOLDING_DAYS = 22    # 最大持仓天数
TOP_N = 20           # 每日选股数
MAX_GAP_PCT = 0.05   # T+1 跳空过滤阈值


class RankBacktester:
    """排序模型回测引擎"""

    def __init__(self, model_path=None, training_data_path=None):
        self.model_path = model_path or _proj(
            "data", "result", "super_trend", "models", "trend_ranker_v1.pkl"
        )
        self.training_data_path = training_data_path or _proj(
            "data", "result", "super_trend", "super_trend_training_data_v2.csv"
        )
        self.ranker = None
        self.trades = []

    def load_model(self):
        """加载排序模型"""
        from super_trend_ranker_trainer import SuperTrendRanker
        if os.path.exists(self.model_path):
            self.ranker = SuperTrendRanker.load_model(self.model_path)
        else:
            print(f"模型文件不存在: {self.model_path}，需先训练模型")
            return False
        return True

    def _train_quick_model(self):
        """快速训练模型（用于回测验证）"""
        import lightgbm as lgb
        from super_trend_ranker_trainer import SuperTrendRanker

        ranker = SuperTrendRanker(training_data_path=self.training_data_path)
        df = ranker.load_training_data()

        split_date = df.iloc[int(len(df) * 0.8)]['t0_date']
        df_train = df[df['t0_date'] < split_date]

        X_tr = df_train[ranker.feature_columns].fillna(0)
        y_tr = df_train['_relevance'].values
        g_tr = ranker._prepare_groups(df_train)

        train_data = lgb.Dataset(X_tr, label=y_tr, group=g_tr)
        ranker.model = lgb.train(
            {**ranker.params, 'verbose': -1},
            train_data, num_boost_round=200,
        )
        self.ranker = ranker
        self._test_df = df[df['t0_date'] >= split_date]
        print(f"快速模型训练完成: {ranker.model.num_trees()} 棵树")
        return True

    def run(self, top_n=TOP_N):
        """
        运行回测：按交易日循环，每日取 Top N 股票等权买入。

        返回:
            dict: 回测结果汇总
        """
        if self.ranker is None:
            if not self.load_model():
                if not self._train_quick_model():
                    return None

        if not hasattr(self, '_test_df') or self._test_df is None:
            df = pd.read_csv(self.training_data_path)
            df = df.sort_values('t0_date').reset_index(drop=True)
            split_idx = int(len(df) * 0.8)
            self._test_df = df.iloc[split_idx:].copy()

        test_df = self._test_df.copy()
        feature_cols = self.ranker.feature_columns
        available_features = [c for c in feature_cols if c in test_df.columns]
        missing = [c for c in feature_cols if c not in test_df.columns]
        if missing:
            print(f"  警告: 缺少 {len(missing)} 个特征列 (新特征需重新扫描)")

        X_test = test_df[available_features].fillna(0)
        scores = self.ranker.model.predict(X_test)
        test_df['_score'] = scores

        test_dates = sorted(test_df['t0_date'].unique())
        print(f"\n=== 回测开始 ===")
        print(f"测试期: {test_dates[0]} ~ {test_dates[-1]}, 共 {len(test_dates)} 个交易日")

        all_trades = []
        daily_pnl = []

        for date in test_dates:
            day_df = test_df[test_df['t0_date'] == date].copy()
            if len(day_df) < top_n:
                continue

            day_df = day_df.nlargest(top_n, '_score')

            day_return = 0.0
            n_bought = 0
            for _, row in day_df.iterrows():
                t1_gap = row.get('t1_gap_up_pct', np.nan)
                if pd.notna(t1_gap) and t1_gap > MAX_GAP_PCT:
                    continue

                future_mfe = row.get('future_mfe', 0)
                future_mae = row.get('future_mae', 0)

                if pd.isna(future_mfe):
                    future_mfe = 0
                if pd.isna(future_mae):
                    future_mae = 0

                simulated_return = self._simulate_trade(future_mfe, future_mae)
                net_return = simulated_return - 2 * COMMISSION

                trade = {
                    'date': date,
                    'stock_code': row.get('stock_code', ''),
                    'score': row['_score'],
                    'future_mfe': future_mfe,
                    'future_mae': future_mae,
                    'simulated_return': simulated_return,
                    'net_return': net_return,
                    'filtered_gap': pd.notna(t1_gap) and t1_gap > MAX_GAP_PCT,
                }
                all_trades.append(trade)
                day_return += net_return
                n_bought += 1

            if n_bought > 0:
                avg_return = day_return / n_bought
                daily_pnl.append({
                    'date': date,
                    'n_stocks': n_bought,
                    'avg_return': avg_return,
                    'total_return': day_return,
                })

        self.trades = pd.DataFrame(all_trades)
        self.daily_pnl = pd.DataFrame(daily_pnl)

        results = self._compute_stats()
        self._print_results(results)
        return results

    def _simulate_trade(self, future_mfe, future_mae):
        """
        模拟单笔交易收益。

        基于 MFE/MAE 估算:
          - 若 MAE 触及止损线 → 止损出场
          - 若 MFE 触及止盈线 → 止盈出场
          - 否则 → 持有到期，收益 = MFE * 捕获率

        返回: 模拟收益率
        """
        if future_mae <= STOP_LOSS:
            return STOP_LOSS * 0.8
        elif future_mfe >= TAKE_PROFIT:
            return TAKE_PROFIT * 0.85
        else:
            capture_rate = 0.5
            return future_mfe * capture_rate

    def _compute_stats(self):
        """计算回测统计"""
        if self.daily_pnl.empty:
            return {'error': '无交易记录'}

        n_days = len(self.daily_pnl)
        total_trades = len(self.trades)

        trades_per_day = self.daily_pnl['n_stocks'].mean()
        avg_trade_return = self.trades['net_return'].mean()
        daily_portfolio_return = avg_trade_return * trades_per_day / HOLDING_DAYS

        n_years = n_days / 252
        total_return = daily_portfolio_return * n_days
        annualized_return = total_return / max(n_years, 0.01)

        daily_returns = self.daily_pnl['avg_return'].values / HOLDING_DAYS
        if np.std(daily_returns) > 0:
            sharpe = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252)
        else:
            sharpe = 0

        cum_returns = np.cumsum(daily_returns)
        running_max = np.maximum.accumulate(cum_returns)
        drawdowns = cum_returns - running_max
        max_drawdown = np.min(drawdowns) if len(drawdowns) > 0 else 0

        winning = self.trades[self.trades['net_return'] > 0]
        win_rate = len(winning) / total_trades if total_trades > 0 else 0

        avg_mfe = self.trades['future_mfe'].mean()
        avg_net = self.trades['net_return'].mean()

        return {
            'total_trades': total_trades,
            'trading_days': n_days,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'avg_trade_return': avg_net,
            'avg_future_mfe': avg_mfe,
            'avg_daily_stocks': self.daily_pnl['n_stocks'].mean(),
        }

    def _print_results(self, results):
        """打印回测结果"""
        print(f"\n{'='*60}")
        print(f"  回测结果汇总")
        print(f"{'='*60}")
        print(f"  总交易笔数: {results['total_trades']}")
        print(f"  交易天数:   {results['trading_days']}")
        print(f"  总收益率:   {results['total_return']:.2%}")
        print(f"  年化收益:   {results['annualized_return']:.2%}")
        print(f"  夏普比率:   {results['sharpe_ratio']:.2f}")
        print(f"  最大回撤:   {results['max_drawdown']:.2%}")
        print(f"  胜率:       {results['win_rate']:.2%}")
        print(f"  平均交易收益: {results['avg_trade_return']:.4f}")
        print(f"  平均 MFE:   {results['avg_future_mfe']:.4f}")
        print(f"  日均选股数: {results['avg_daily_stocks']:.1f}")
        print(f"{'='*60}")

    def compare_with_baseline(self):
        """与基准（全量异动等权买入）对比"""
        if self.trades.empty:
            return

        print(f"\n── 与基准对比 ──")

        model_avg = self.trades['net_return'].mean()
        model_mfe = self.trades['future_mfe'].mean()

        test_df = self._test_df.copy()
        baseline_mfe = test_df['future_mfe'].mean()
        baseline_avg = test_df['future_mfe'].mean() * 0.5 - 2 * COMMISSION

        print(f"  模型 Top{TOP_N}:  平均净收益={model_avg:.4f}, 平均MFE={model_mfe:.4f}")
        print(f"  全量基线:     平均净收益={baseline_avg:.4f}, 平均MFE={baseline_mfe:.4f}")

        improvement = (model_avg - baseline_avg) / abs(baseline_avg) if baseline_avg != 0 else 0
        print(f"  提升幅度:     {improvement:.1%}")


def main():
    print("=== Super Trend V1: 端到端回测 ===")

    bt = RankBacktester()
    results = bt.run(top_n=TOP_N)

    if results and 'error' not in results:
        bt.compare_with_baseline()

        bt.trades.to_csv(_proj('data', 'result', 'super_trend', 'backtest_trades.csv'), index=False)
        bt.daily_pnl.to_csv(_proj('data', 'result', 'super_trend', 'backtest_daily_pnl.csv'), index=False)
        print(f"\n交易明细已保存")

    return results


if __name__ == "__main__":
    main()
