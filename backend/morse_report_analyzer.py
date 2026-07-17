import os
import glob
import pandas as pd
import numpy as np

def analyze_morse_report():
    print("\n" + "="*80)
    print(" 🚀 启动 [狙击手回测深度解析与归因引擎]")
    print("="*80)
    
    # 1. 加载最新回测数据
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    csv_files = glob.glob(os.path.join(backend_dir, 'latest_walk_forward*.csv'))
    if not csv_files:
        print("❌ 找不到最新的回测结果 CSV 文件。")
        return
        
    latest_csv = max(csv_files, key=os.path.getmtime)
    df = pd.read_csv(latest_csv)
    print(f"📂 成功加载账单: {os.path.basename(latest_csv)} (总样本: {len(df)} 笔)")
    
    # 过滤出真实产生交易（挂单成功）的样本
    df_traded = df[df['trade_status'].isin(['止盈成功', '止损出局', '持仓到期'])]
    if df_traded.empty:
        print("⚠️ 报告中没有实际成交的单子。")
        return
        
    print(f"⚔️ 实际触发成交: {len(df_traded)} 笔")
    win_rate = (df_traded['final_pnl'] > 0).mean() * 100
    avg_pnl = df_traded['final_pnl'].mean() * 100
    print(f"🏆 总体胜率 (>0%): {win_rate:.1f}% | 总体单次期望收益: {avg_pnl:+.2f}%\n")
    
    # ---------------------------------------------------------
    # 🧬 模块一：打分机制有效性验证 (Score Validation)
    # ---------------------------------------------------------
    print("📊 [模块一] 莫尔斯总分 (fit_score) 分层表现：")
    score_stats = df_traded.groupby('fit_score').agg(
        成交笔数=('stock_code', 'count'),
        胜率=('final_pnl', lambda x: (x > 0).mean() * 100),
        平均期望收益=('final_pnl', lambda x: x.mean() * 100),
        平均冲高MFE=('MFE', lambda x: x.mean() * 100)
    ).sort_index(ascending=False)
    
    for score, row in score_stats.iterrows():
        print(f"   ➤ 【{score} 分】触发 {row['成交笔数']:>2.0f} 笔 | 胜率: {row['胜率']:>5.1f}% | 期望收益: {row['平均期望收益']:>+6.2f}% | 平均最大反弹: +{row['平均冲高MFE']:>4.1f}%")

    # ---------------------------------------------------------
    # 🔬 模块二：独立基因 Bit 位战斗力测序
    # ---------------------------------------------------------
    print("\n🧬 [模块二] 独立莫尔斯因子 (Bit位) 实战贡献度剥离：")
    # 将 "T1_U:1|T1_D:0..." 拆解为独立的列
    if 'morse_features' in df_traded.columns:
        feature_dicts = []
        for f_str in df_traded['morse_features']:
            f_dict = {}
            if isinstance(f_str, str):
                for item in f_str.split('|'):
                    k, v = item.split(':')
                    f_dict[k] = int(v)
            feature_dicts.append(f_dict)
            
        df_features = pd.DataFrame(feature_dicts, index=df_traded.index)
        df_merged = pd.concat([df_traded, df_features], axis=1)
        
        features_to_check = ['T1_U', 'T1_D', 'T1_L', 'T1_B', 'M15_U', 'M15_L']
        for f in features_to_check:
            if f in df_merged.columns:
                subset = df_merged[df_merged[f] == 1]
                if len(subset) > 0:
                    f_win = (subset['final_pnl'] > 0).mean() * 100
                    f_pnl = subset['final_pnl'].mean() * 100
                    print(f"   - 包含【{f}】的样本: {len(subset):>2} 笔 | 胜率: {f_win:>5.1f}% | 独立期望收益: {f_pnl:>+6.2f}%")

    # ---------------------------------------------------------
    # 📉 模块三：死因归因与 7 天价格轨迹透视 (极其重要！)
    # ---------------------------------------------------------
    print("\n📉 [模块三] 止损/失败案例死因剖析 (价格轨迹透视)：")
    losers = df_traded[df_traded['trade_status'] == '止损出局']
    
    if losers.empty:
        print("   🎉 恭喜！没有任何止损订单。")
    else:
        # 死因1：冲高回落被反杀 (MFE > 7% 但最终止损)
        fake_breakouts = losers[losers['MFE'] >= 0.07]
        # 死因2：压根没涨直接瀑布 (MFE < 3%)
        waterfalls = losers[losers['MFE'] < 0.03]
        
        print(f"   总计止损 {len(losers)} 笔，其中：")
        print(f"   ➤ 令人惋惜的【冲高回落反杀】: {len(fake_breakouts)} 笔 (曾经拉升超 7%，没摸到 10% 止盈线又跌破止损)")
        print(f"   ➤ 极其恶劣的【一买就套瀑布】: {len(waterfalls)} 笔 (拉升不足 3%，纯诱多)")
        
        if not fake_breakouts.empty:
            print("\n   [冲高回落案例轨迹大赏] - 考虑是否该把止盈位下调至 8%？")
            for _, row in fake_breakouts.head(5).iterrows():
                print(f"     股票 {row['stock_code']} (得分 {row['fit_score']}) | 最大反弹: +{row['MFE']*100:.1f}%")
                print(f"     7天轨迹: {row.get('future_7d_path', '无轨迹数据')}")
                
        if not waterfalls.empty:
            print("\n   [一买就套案例轨迹大赏] - 考虑是否该降低 trigger_buy (不追高，回调买)？")
            for _, row in waterfalls.head(5).iterrows():
                print(f"     股票 {row['stock_code']} (得分 {row['fit_score']}) | 最大反弹: +{row['MFE']*100:.1f}%")
                print(f"     7天轨迹: {row.get('future_7d_path', '无轨迹数据')}")

if __name__ == '__main__':
    analyze_morse_report()
