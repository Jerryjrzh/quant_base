import os
import pandas as pd
import talib
import data_loader

def check_right_side_recovery(stock_code, eval_date_str, holding_days, look_forward=20):
    clean_code = stock_code.replace('sh', '').replace('sz', '').replace('bj', '')
    market = stock_code[:2] if stock_code[:2] in ['sh', 'sz', 'bj'] else 'sh'
    file_path = os.path.expanduser(f"~/.local/share/tdxcfv/drive_c/tc/vipdoc/{market}/lday/{market}{clean_code}.day")
    
    df = data_loader.get_daily_data(file_path)
    if df is None or df.empty: return "数据源未找到"
        
    df['ma20'] = talib.MA(df['close'], timeperiod=20)
    _, _, hist = talib.MACD(df['close'], fastperiod=8, slowperiod=21, signalperiod=6)
    df['macd_hist'] = hist
    
    try:
        eval_date = pd.to_datetime(eval_date_str)
        if eval_date not in df.index: eval_date = df[df.index <= eval_date].index[-1]
        test_idx = df.index.get_loc(eval_date)
        exit_idx = test_idx + holding_days 
        
        recovery_df = df.iloc[exit_idx + 1 : exit_idx + 1 + look_forward]
        if recovery_df.empty: return "出局后无后续数据"
            
        right_side_days = recovery_df[(recovery_df['close'] > recovery_df['ma20']) & (recovery_df['macd_hist'] > 0)]
        if not right_side_days.empty:
            return f"✅ 错杀修复！于 {right_side_days.index[0].strftime('%Y-%m-%d')} 重回MA20右侧, 期间最大反弹 {(recovery_df['high'].max() - df.iloc[exit_idx]['close']) / df.iloc[exit_idx]['close']:.2%}"
        return "❌ 真实破位，20个工作日内持续弱势未见右侧"
    except Exception as e:
        return f"异常: {e}"

def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    
    if not os.path.exists(csv_path):
        print(f"找不到 {csv_path}。请先运行 walk_forward_tester.py。")
        return
        
    df_results = pd.read_csv(csv_path)
    executed = df_results[df_results['trade_status'] != '未成交'].copy()
    
    if executed.empty:
        print("无实际建仓成交数据。")
        return

    base_eval_date = df_results['eval_date'].iloc[0]

    win_trades = executed[executed['trade_status'] == '止盈成功']
    loss_trades = executed[executed['trade_status'] == '止损出局']
    hold_trades = executed[executed['trade_status'] == '持仓到期']

    total_win_pnl = win_trades['final_pnl'].sum()
    total_loss_pnl = loss_trades['final_pnl'].sum()
    total_hold_pnl = hold_trades['final_pnl'].sum()
    net_pnl = executed['final_pnl'].sum()

    print("\n" + "★"*60)
    print(f" 📊  自适应均线策略复盘报告 | 基准日期: {base_eval_date}")
    print("★"*60)

    print("\n【维度一：总体综合财务记账看板】")
    print("-" * 50)
    print(f" 🏢 实际成交建仓总数 : {len(executed)} 只")
    print(f" 💰 累计总利润(Net)  : {net_pnl:+.2%}  (单股等额计盈亏)")
    print(f" 🎉 累计止盈贡献利润 : {total_win_pnl:+.2%}  (共 {len(win_trades)} 只)")
    print(f" 🛑 累计止损扣减利润 : {total_loss_pnl:+.2%}  (共 {len(loss_trades)} 只)")
    print(f" ⌛ 累计到期持仓收益 : {total_hold_pnl:+.2%}  (共 {len(hold_trades)} 只)")
    print("-" * 50)

    print("\n【维度二：双网格策略操作预演 (7% 做 T 空间)】")
    print("-" * 50)
    hit_7_pct = executed[executed['MFE'] >= 0.07]
    missed_wins = hit_7_pct[hit_7_pct['trade_status'] != '止盈成功']
    print(f" 🎯 涨幅曾突破 7% 触发网格做T点 : {len(hit_7_pct)} 只")
    print(f" 🎯 最终无视波动锁定利润出局    : {len(win_trades)} 只")
    if not missed_wins.empty:
        for _, row in missed_wins.iterrows():
            print(f" ⚠️  [拯救败局] -> [{row['stock_code']}] 最高冲至 {row['MFE']:.2%} | 期末收益回落至 {row['final_pnl']:.2%} ({row['trade_status']})")
    else:
        print(" ✅ 暂无利润回撤大过山车情况，时间衰减止盈生效。")

    print("\n【维度三：止损个股明细及策略定位归因 (防错杀收盘过滤版)】")
    print("-" * 50)
    if not loss_trades.empty:
        for _, row in loss_trades.iterrows():
            strategy_desc = f"深踩型(下浮4%买/12%防守)" if row['deep_touches'] > 14 else f"常规型(下浮1.5%买/8%防守)"
            print(f" 🛑 [{row['stock_code']}] 动作: 专属MA{int(row['best_ma'])}({strategy_desc})")
            print(f"    └─ 挂单买入价: ¥{row['trigger_buy']:.2f} | 触发极限止损价: ¥{row['stop_loss']:.2f}")
            print(f"    └─ 止损结算价: ¥{row['trigger_buy'] * (1 + row['final_pnl']):.2f} (确立收盘破位出局)")
            print(f"    └─ 最终割肉收益: {row['final_pnl']:.2%} | 死扛持仓天数: {row['holding_days']} 天")
    else:
        print(" ✅ 本期无个股止损出局，防错杀机制完美。")

    # 🔻【优化点：时间衰减分类排序】
    print("\n【维度四：成功止盈个股效率排序 (10%强主升 vs 7%衰减止盈)】")
    print("-" * 50)
    if not win_trades.empty:
        sorted_win = win_trades.sort_values(['holding_days', 'MFE'], ascending=[True, False])
        for _, row in sorted_win.iterrows():
            # 判断是 10% 止盈还是 7% 时间降级止盈
            win_type = "🔥 强势 10% 止盈" if row['final_pnl'] >= 0.098 else "⏳ 降级 7% 落袋"
            print(f" 🏆 [{row['stock_code']}] 耗时 {row['holding_days']} 天 -> {win_type} | 最终收益: {row['final_pnl']:.2%} | 过程最大回撤(MAE): {row['MAE']:.2%}")
    else:
        print(" 暂无止盈记录。")

    print("\n【维度五：到期持仓盈亏追踪明细】")
    print("-" * 50)
    if not hold_trades.empty:
        for _, row in hold_trades.iterrows():
            print(f" ⌛ [{row['stock_code']}] 状态: {row['holding_days']}天持仓期满未达标 | 当前浮动盈亏: {row['final_pnl']:+.2%} | 期间最高冲到(MFE): {row['MFE']:.2%}")
    else:
        print(" 💡 无持仓到期未完结股票。")

    print("\n【维度六：止损后 20 个交易日右侧修复追踪（防假破位洗盘）】")
    print("-" * 50)
    if not loss_trades.empty:
        for _, row in loss_trades.iterrows():
            status = check_right_side_recovery(row['stock_code'], row['eval_date'], row['holding_days'])
            print(f" [{row['stock_code']}] 后续轨迹 -> {status}")
    else:
        print(" ✅ 无止损标的，无需进行右侧修复追踪。")

if __name__ == "__main__":
    main()
