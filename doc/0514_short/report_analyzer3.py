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

def format_date(date_str):
    """将 YYYY-MM-DD 转为更短的 MM-DD 显示"""
    if pd.isna(date_str) or not date_str: return "未知"
    return str(date_str)[5:]

def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    
    if not os.path.exists(csv_path):
        print(f"找不到 {csv_path}。请先运行 walk_forward_tester.py。")
        return
        
    df_results = pd.read_csv(csv_path)
    executed = df_results[df_results['trade_status'] != '未成交'].copy()
    unexecuted = df_results[df_results['trade_status'] == '未成交'].copy()
    
    base_eval_date = df_results['eval_date'].iloc[0]

    win_trades = executed[executed['trade_status'] == '止盈成功']
    loss_trades = executed[executed['trade_status'] == '止损出局']
    hold_trades = executed[executed['trade_status'] == '持仓到期']

    total_win_pnl = win_trades['final_pnl'].sum() if not win_trades.empty else 0
    total_loss_pnl = loss_trades['final_pnl'].sum() if not loss_trades.empty else 0
    total_hold_pnl = hold_trades['final_pnl'].sum() if not hold_trades.empty else 0
    net_pnl = executed['final_pnl'].sum() if not executed.empty else 0

    print("\n" + "★"*70)
    print(f" 📊  自适应均线策略复盘报告 (精确时间版) | 选股日: {base_eval_date}")
    print("★"*70)

    print("\n【维度一：总体综合财务记账看板】")
    print("-" * 60)
    print(f" 🏢 实际成交建仓总数 : {len(executed)} 只 (踏空/熔断未成交 {len(unexecuted)} 只)")
    print(f" 💰 累计总利润(Net)  : {net_pnl:+.2%}  (单股等额计盈亏)")
    print(f" 🎉 累计止盈贡献利润 : {total_win_pnl:+.2%}  (共 {len(win_trades)} 只)")
    print(f" 🛑 累计止损扣减利润 : {total_loss_pnl:+.2%}  (共 {len(loss_trades)} 只)")
    print(f" ⌛ 累计到期持仓收益 : {total_hold_pnl:+.2%}  (共 {len(hold_trades)} 只)")
    print("-" * 60)

    print("\n【维度二：双网格策略操作预演 (7% 做 T 空间)】")
    print("-" * 60)
    if not executed.empty:
        hit_7_pct = executed[executed['MFE'] >= 0.07]
        missed_wins = hit_7_pct[hit_7_pct['trade_status'] != '止盈成功']
        print(f" 🎯 涨幅曾突破 7% 触发网格做T点 : {len(hit_7_pct)} 只")
        print(f" 🎯 最终无视波动锁定利润出局    : {len(win_trades)} 只")
        if not missed_wins.empty:
            for _, row in missed_wins.iterrows():
                print(f" ⚠️  [拯救败局] -> [{row['stock_code']}] 最高冲至 {row['MFE']:.2%} | 期末回落至 {row['final_pnl']:.2%} ({row['trade_status']})")
        else:
            print(" ✅ 暂无利润回撤过山车情况。")
    else:
        print("无成交数据。")

    print("\n【维度三：止损个股明细及时间轨迹 (防错杀收盘过滤版)】")
    print("-" * 60)
    if not loss_trades.empty:
        for _, row in loss_trades.iterrows():
            strategy_desc = f"深踩型(挂单-4%/防守-12%)" if row['deep_touches'] > 14 else f"常规型(挂单-1.5%/防守-8%)"
            dt_str = f"[入场: {format_date(row['entry_date'])} | 止损: {format_date(row['exit_date'])} ({row['holding_days']}天)]"
            print(f" 🛑 [{row['stock_code']}] {dt_str} 动作: MA{int(row['best_ma'])} {strategy_desc}")
            print(f"    └─ 买入价: ¥{row['trigger_buy']:.2f} | 止损割肉价: ¥{row['trigger_buy'] * (1 + row['final_pnl']):.2f}")
            print(f"    └─ 开盘滑点: {row['entry_slip']:.2%} | 最终割肉收益: {row['final_pnl']:.2%}")
    else:
        print(" ✅ 本期无个股止损出局，防错杀机制完美。")

    # 🔻【优化：维度四 成功个股加上评分明细】
    print("\n【维度四：成功止盈个股效率排序 (10%强主升 vs 7%衰减止盈)】")
    print("-" * 60)
    if not win_trades.empty:
        sorted_win = win_trades.sort_values(['holding_days', 'MFE'], ascending=[True, False])
        for _, row in sorted_win.iterrows():
            win_type = "🔥 强势 10% 止盈" if row['final_pnl'] >= 0.098 else "⏳ 降级 7% 落袋"
            dt_str = f"[入场: {format_date(row['entry_date'])} | 止盈: {format_date(row['exit_date'])} ({row['holding_days']}天)]"
            # 新增特征展示
            feature_str = f"得分: {row['fit_score']}分 | MA{int(row['best_ma'])} | 触碰: {int(row['deep_touches'])}次 | 爆发: {row.get('burst_ratio', 0)*100:.1f}% | 斜率: {row.get('ma_slope',0)*100:.1f}% | 跌速: {row.get('drop_velocity',0)*100:.1f}%"
            #feature_str = f"得分: {row['fit_score']}分 | MA{int(row['best_ma'])} | 触碰: {int(row['deep_touches'])}次 | 爆发比: {row.get('burst_ratio', 0)*100:.1f}%"
            print(f" 🏆 [{row['stock_code']}] {dt_str} -> {win_type} | 最终收益: {row['final_pnl']:.2%} | {feature_str}")
    else:
        print(" 暂无止盈记录。")

    # 🔻【优化：维度五 到期未达标个股加上评分明细】
    print("\n【维度五：到期持仓盈亏追踪明细】")
    print("-" * 60)
    if not hold_trades.empty:
        for _, row in hold_trades.iterrows():
            dt_str = f"[入场: {format_date(row['entry_date'])} | 到期: {format_date(row['exit_date'])} ({row['holding_days']}天)]"
            feature_str = f"得分: {row['fit_score']}分 | MA{int(row['best_ma'])} | 触碰: {int(row['deep_touches'])}次 | 爆发比: {row.get('burst_ratio', 0)*100:.1f}% | 斜率: {row.get('ma_slope',0)*100:.1f}% | 跌速: {row.get('drop_velocity',0)*100:.1f}% | 深度洗盘: {int(row.get('is_deep_wash',0)) }"
            print(f" ⌛ [{row['stock_code']}] {dt_str} 状态: 持仓期满未达标 | 当前浮盈: {row['final_pnl']:+.2%} | {feature_str}")
    else:
        print(" 💡 无持仓到期未完结股票。")

    # 🔻【新增核心维度】：未成交分析
    print("\n【维度六：未成交标的深度分析 (踏空与避险评估)】")
    print("-" * 60)
    if not unexecuted.empty:
        for _, row in unexecuted.iterrows():
            trigger = row['trigger_buy']
            stop = row['stop_loss']
            f_low = row['future_min_low']
            f_high = row['future_max_high']
            
            # 计算距离成交还差多少
            miss_dist = (f_low - trigger) / trigger if trigger > 0 else 0
            # 计算验证期间的最大振幅
            volatility = (f_high - f_low) / f_low if f_low > 0 else 0
            
            # 判定未成交的原因
            if f_low <= stop:
                reason = "💥 触发极端防守 (开盘暴跌或一字跌停熔断，成功避险！)"
            elif f_low <= trigger:
                reason = "📉 触发买价，但未产生 1.5% 向上抵抗 (防飞刀生效)"
            else:
                reason = f"🚀 未跌至买点 (距离挂单价差 {miss_dist:.2%})"
                
            print(f" 🔍 [{row['stock_code']}] 挂单价: ¥{trigger:.2f} | 期间最低探至: ¥{f_low:.2f}")
            print(f"    └─ 未成交原因: {reason}")
            print(f"    └─ 验证期波动: 区间振幅 {volatility:.2%} | 成交预期收益: 10%(前4天)/7%(后延)")
    else:
        print(" 💡 所有生成的信号均已成功触发成交。")

    print("\n【维度七：止损后 20 个交易日右侧修复追踪（防假破位洗盘）】")
    print("-" * 60)
    if not loss_trades.empty:
        for _, row in loss_trades.iterrows():
            status = check_right_side_recovery(row['stock_code'], row['eval_date'], row['holding_days'])
            print(f" [{row['stock_code']}] 后续轨迹 -> {status}")
    else:
        print(" ✅ 无止损标的，无需进行右侧修复追踪。")

if __name__ == "__main__":
    main()
