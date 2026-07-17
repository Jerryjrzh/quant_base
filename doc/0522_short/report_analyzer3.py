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
        exit_idx = df.index.get_loc(eval_date) + holding_days 
        recovery_df = df.iloc[exit_idx + 1 : exit_idx + 1 + look_forward]
        if recovery_df.empty: return "出局后无后续数据"
        right_side_days = recovery_df[(recovery_df['close'] > recovery_df['ma20']) & (recovery_df['macd_hist'] > 0)]
        if not right_side_days.empty:
            return f"✅ 错杀修复！于 {right_side_days.index[0].strftime('%Y-%m-%d')} 重回MA20右侧, 最大反弹 {(recovery_df['high'].max() - df.iloc[exit_idx]['close']) / df.iloc[exit_idx]['close']:.2%}"
        return "❌ 真实破位，持续弱势"
    except Exception as e: return f"异常: {e}"

def format_date(date_str):
    if pd.isna(date_str) or not date_str: return "等待触发"
    return str(date_str)[5:]

def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    if not os.path.exists(csv_path): return
    df_results = pd.read_csv(csv_path)
    
    executed = df_results[~df_results['trade_status'].isin(['未成交', '等待实盘验证(T+1)'])].copy()
    unexecuted = df_results[df_results['trade_status'] == '未成交'].copy()
    t1_previews = df_results[df_results['trade_status'] == '等待实盘验证(T+1)'].copy()
    base_eval_date = df_results['eval_date'].iloc[0]

    print("\n" + "★"*75)
    print(f" 📊  自适应均线深踩策略量化对账单 (V12 矩阵执行版) | 选股日: {base_eval_date}")
    print("★"*75)

    print(f"\n【总体财务看盘】成交建仓: {len(executed)}只 | 宽容拦截未成交: {len(unexecuted)}只 | 实盘T+1就绪: {len(t1_previews)}只")
    print(f" 💰 全池单期等额平均净收益率: {executed['final_pnl'].mean():+.2%}" if not executed.empty else " 💰 暂无历史成交结算")
    print("-" * 75)

    # 🛠️ 实盘前台条件单调度执行卡
    target_source = t1_previews if not t1_previews.empty else unexecuted
    if not target_source.empty:
        print("\n【⚡ 明日实盘自动化交易执行卡 (前台券商条件单配置依据) ⚡】")
        print("=" * 75)
        for _, row in target_source.sort_values('fit_score', ascending=False).iterrows():
            st_type = "🚨 深度砸坑型" if row['is_deep_wash'] == 1 else "✨ 轨道常规型"
            print(f" 🎯 标的代码: {row['stock_code'].upper()} | 综合排序评分: {row['fit_score']} 分 ({st_type})")
            print(f"    ├─ 专属均线: MA{int(row['best_ma'])} | 历史触碰: {int(row['deep_touches'])}次 | 支撑斜率: {row['ma_slope']*100:+.1f}%")
            print(f"    ├─ 🛒 条件单买入触发价: ¥{row['trigger_buy']:.2f} (买入后需反弹产生 1.5% 抵抗强度)")
            print(f"    ├─ 🛑 条件单盘中硬止损: ¥{row['stop_loss']:.2f} (收盘价正式破位或砸穿该位置清仓)")
            print(f"    └─ 阶梯网格分仓做 T 指引:")
            print(f"        ① 锁利主线 -> 4天内脉冲至 ¥{row['trigger_buy']*1.098:.2f} (持仓锁定 +9.8% 利润出局)")
            print(f"        ② 时间衰减 -> 第5天起止盈降级至 ¥{row['trigger_buy']*1.075:.2f} (+7.5% 自动降档落袋)")
            print("-" * 75)

    print("\n【维度四：结算完毕个股效率排序】")
    if not executed.empty:
        for _, row in executed.sort_values('holding_days').iterrows():
            print(f" 🏆 [{row['stock_code']}] [{format_date(row['entry_date'])} -> {format_date(row['exit_date'])} ({row['holding_days']}天)] | 收益: {row['final_pnl']:.2%} | 得分: {row['fit_score']}分 | 跌速: {row['drop_velocity']*100:.1f}%")
    else: print(" 暂无已结算历史头寸。")

if __name__ == "__main__":
    main()
