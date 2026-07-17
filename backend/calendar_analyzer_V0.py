import os
import pandas as pd
import data_loader

def load_market_index(index_code="sz399300"):
    """加载大盘指数作为环境参考 (默认上证，可改为 sz399300 沪深300)"""
    market_prefix = index_code[:2]
    index_path = os.path.expanduser(f"~/.local/share/tdxcfv/drive_c/tc/vipdoc/{market_prefix}/lday/{index_code}.day")
    if os.path.exists(index_path):
        df_index = data_loader.get_daily_data(index_path)
        df_index['market_pct'] = df_index['close'].pct_change()
        return df_index
    return None

def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    trades_csv = os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest', 'full_calendar_trades.csv')
    
    if not os.path.exists(trades_csv):
        print(f"❌ 找不到日历数据 {trades_csv}，请先运行 calendar_batch_runner.py")
        return

    df_trades = pd.read_csv(trades_csv)
    if df_trades.empty:
        print("回测周期内无成交数据。")
        return

    # === 按退出日期 (exit_date) 统计每日盈亏 ===
    df_trades['exit_date'] = pd.to_datetime(df_trades['exit_date'])
    daily_yield = df_trades.groupby('exit_date').agg(
        trade_count=('final_pnl', 'count'),
        win_count=('final_pnl', lambda x: (x > 0).sum()),
        loss_count=('final_pnl', lambda x: (x < -0.01).sum()),
        avg_pnl=('final_pnl', 'mean')
    ).reset_index()

    # === 与大盘走势强绑定 ===
    df_index = load_market_index("sh000001") # 上证指数
    if df_index is not None:
        daily_yield = daily_yield.merge(df_index[['market_pct']], left_on='exit_date', right_index=True, how='left')
    else:
        daily_yield['market_pct'] = 0.0

    print("\n" + "★"*70)
    print(" 📅 策略收益日历与大盘环境拟合报告 (2025.01 - 2026.04)")
    print("★"*70)

    # 1. 总体宏观指标
    total_trades = len(df_trades)
    win_trades = len(df_trades[df_trades['trade_status'] == '止盈成功'])
    loss_trades = len(df_trades[df_trades['trade_status'] == '止损出局'])
    
    absolute_win_rate = win_trades / total_trades if total_trades > 0 else 0
    overall_pnl = df_trades['final_pnl'].mean()
    
    print(f"\n【维度一：全周期总体表现 (硬核统计)】")
    print("-" * 60)
    print(f" - 总成交笔数 : {total_trades} 笔")
    print(f" - 胜率 (严格止盈) : {absolute_win_rate:.2%} (指触发 9.8% 或 7% 目标出局的比例)")
    print(f" - 笔均净利润   : {overall_pnl:.2%} (包含所有的止损和未达标到期单)")
    print(f" - 最终状态分布 : 止盈 {win_trades} 笔 | 止损 {loss_trades} 笔 | 到期平仓 {total_trades - win_trades - loss_trades} 笔")

    # 2. Beta vs Alpha 拟合分析
    print("\n【维度二：大盘环境拟合 (Beta环境依赖 vs Alpha超额收益)】")
    print("-" * 60)
    market_up_days = daily_yield[daily_yield['market_pct'] > 0]
    market_down_days = daily_yield[daily_yield['market_pct'] < 0]
    market_crash_days = daily_yield[daily_yield['market_pct'] < -0.015] # 股灾日(跌超1.5%)

    up_pnl = market_up_days['avg_pnl'].mean() if not market_up_days.empty else 0
    down_pnl = market_down_days['avg_pnl'].mean() if not market_down_days.empty else 0
    crash_pnl = market_crash_days['avg_pnl'].mean() if not market_crash_days.empty else 0

    print(f" 📈 大盘上涨日 ({len(market_up_days)}天) | 策略平均单日收益: {up_pnl:+.2%}")
    print(f" 📉 大盘下跌日 ({len(market_down_days)}天) | 策略平均单日收益: {down_pnl:+.2%}")
    print(f" 🌩️ 股灾日避险 (大盘跌幅>1.5%) | 策略平均单日收益: {crash_pnl:+.2%} (正数为逆势赚钱！)")

    # 3. 集中亏损日提取归因
    print("\n【维度三：极端亏损日历复盘 (请对照大盘K线寻找死穴)】")
    print("-" * 60)
    bad_days = daily_yield[daily_yield['avg_pnl'] < -0.015].sort_values('avg_pnl')
    if not bad_days.empty:
        print("以下交易日发生了系统性的集中亏损：")
        for _, row in bad_days.head(10).iterrows():
            date_str = row['exit_date'].strftime('%Y-%m-%d')
            print(f" 🛑 {date_str} | 策略平均亏损: {row['avg_pnl']:.2%} | 当日大盘: {row['market_pct']:.2%} | 出局单数: {int(row['trade_count'])}")
    else:
        print(" ✅ 全周期内，无任何单日平均亏损超过 1.5% 的崩盘日！策略自带强风控免疫。")

if __name__ == "__main__":
    main()
