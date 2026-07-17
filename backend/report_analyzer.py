import os
import pandas as pd
import talib
import data_loader

def check_right_side_recovery(stock_code, eval_date_str, holding_days, look_forward=20):
    clean_code = stock_code.replace('sh', '').replace('sz', '').replace('bj', '')
    market = stock_code[:2] if stock_code[:2] in ['sh', 'sz', 'bj'] else 'sh'
    file_path = os.path.expanduser(f"~/.local/share/tdxcfv/drive_c/tc/vipdoc/{market}/lday/{market}{clean_code}.day")
    
    df = data_loader.get_daily_data(file_path)
    if df is None or df.empty: return None
        
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
            return f"✅ 错杀修复！于 {right_side_days.index[0].strftime('%Y-%m-%d')} 重回右侧, 期间最大反弹 {(recovery_df['high'].max() - df.iloc[exit_idx]['close']) / df.iloc[exit_idx]['close']:.2%}"
        return "❌ 真实破位，持续弱势未见右侧"
    except Exception as e:
        return f"异常: {e}"

def analyze_grid_strategy(df_results):
    print("\n" + "="*50)
    print("🕸️ 【核心分析】双网格操作收益预演 (7% 做 T)")
    print("="*50)
    
    executed = df_results[df_results['trade_status'] != '未成交'].copy()
    if executed.empty: return
    
    # 模拟在最高点附近触达 7% 的标的
    hit_7_pct = executed[executed['MFE'] >= 0.07]
    full_win = executed[executed['trade_status'] == '止盈成功']
    
    # 意难平：到了7%但没到10%最终没赚钱的
    missed_wins = hit_7_pct[hit_7_pct['trade_status'] != '止盈成功']
    
    print(f"📊 实际建仓总数: {len(executed)} 只")
    print(f"🎯 涨幅曾突破 7% 的标的: {len(hit_7_pct)} 只 (触发网格T点)")
    print(f"🎯 最终死扛到 10% 止盈: {len(full_win)} 只")
    
    if len(missed_wins) > 0:
        print(f"\n⚠️ 如果执行【7%减仓做T + 成本线下移】网格，你将拯救以下 {len(missed_wins)} 只败局：")
        for _, row in missed_wins.iterrows():
            status = "最终变成亏损止损！" if row['trade_status'] == '止损出局' else f"期末收益回落至 {row['final_pnl']:.2%}"
            print(f"  - [{row['stock_code']}] 最高曾冲到 {row['MFE']:.2%} -> {status}")
    else:
        print("\n✅ 所有达到 7% 的股票最终都达到了 10%，当前参数容错率极高。")

def main():
    # 自动寻找测试脚本刚刚生成的那个固定文件
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    
    if not os.path.exists(csv_path):
        print(f"找不到 {csv_path}。请先运行 walk_forward_tester.py。")
        return
        
    df_results = pd.read_csv(csv_path)
    
    # 1. 网格策略回测
    analyze_grid_strategy(df_results)
    
    # 2. 成功排序
    print("\n" + "="*50)
    print("🏆 成功止盈个股排序 (按持仓天数与MFE)")
    print("="*50)
    success_df = df_results[df_results['trade_status'] == '止盈成功'].sort_values(['holding_days', 'MFE'], ascending=[True, False])
    for _, row in success_df.iterrows():
        print(f"[{row['stock_code']}] 耗时: {row['holding_days']}天 | MAE: {row['MAE']:.2%} | MA{row['best_ma']}")

    # 3. 止损异常
    print("\n" + "="*50)
    print("🚨 止损异常监控 (低开核按钮)")
    print("="*50)
    loss_df = df_results[df_results['trade_status'] == '止损出局']
    flash_crashes = loss_df[loss_df['entry_slip'] < -0.025]
    print(f"开盘直接砸破触发价 > 2.5% 的标的 (防范滑点): {len(flash_crashes)} 只")
    for _, row in flash_crashes.iterrows():
        print(f"  - [{row['stock_code']}] 滑点 {row['entry_slip']:.2%} | 最终 {row['final_pnl']:.2%}")

    # 4. 右侧修复
    print("\n" + "="*50)
    print("🔄 止损后 20 个交易日右侧修复追踪")
    print("="*50)
    for _, row in loss_df.iterrows():
        status = check_right_side_recovery(row['stock_code'], row['eval_date'], row['holding_days'])
        print(f"[{row['stock_code']}] {status}")

if __name__ == "__main__":
    main()