import os
import pandas as pd
import numpy as np

def analyze_hologram_report():
    print("\n" + "="*80)
    print(" 🚀 启动 [狙击手全息闭环归因引擎] (Holographic Attribution)")
    print("="*80)
    
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    trades_csv = os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest', 'full_calendar_trades.csv')
    
    if not os.path.exists(trades_csv):
        print(f"❌ 找不到全量回测账单: {trades_csv}")
        return
        
    df = pd.read_csv(trades_csv)
    print(f"📂 成功加载回测总样本: {len(df)} 笔")
    
    # 把原来的过滤行替换为下面这行，确保不漏掉任何一笔真实操作！
    df_traded = df[df['trade_status'].isin([
        '止盈成功', '止损出局', '持仓到期', 
        '时间衰减平仓', '形态破坏斩仓', '移动保本平仓'
    ])]
    if df_traded.empty:
        print("⚠️ 报告中没有实际成交的单子。")
        return
        
    print(f"⚔️ 实际触发实盘建仓: {len(df_traded)} 笔")
    win_rate = (df_traded['final_pnl'] > 0).mean() * 100
    avg_pnl = df_traded['final_pnl'].mean() * 100
    print(f"🏆 全周期总体胜率 (>0%): {win_rate:.1f}% | 总体单次期望收益: {avg_pnl:+.2f}%\n")

    # --- 提取打包的特征字典 ---
    feature_dicts = []
    for f_str in df_traded['morse_features']:
        f_dict = {}
        if isinstance(f_str, str):
            for item in f_str.split('|'):
                k, v = item.split(':')
                try:
                    f_dict[k] = float(v)
                except ValueError:
                    f_dict[k] = v # 字符串特征，如 MKT
        feature_dicts.append(f_dict)
        
    df_features = pd.DataFrame(feature_dicts, index=df_traded.index)
    df_merged = pd.concat([df_traded, df_features], axis=1)

    # =========================================================
    # 维度一：大盘环境 (Beta) 依赖度测试
    # =========================================================
    print("📊 [维度一] 大盘环境 (Beta) 依赖度剖析：")
    if 'MKT' in df_merged.columns:
        mkt_stats = df_merged.groupby('MKT').agg(
            成交笔数=('stock_code', 'count'),
            胜率=('final_pnl', lambda x: (x > 0).mean() * 100),
            期望收益=('final_pnl', lambda x: x.mean() * 100)
        )
        for mkt, row in mkt_stats.iterrows():
             print(f"   ➤ 【{mkt}】环境下建仓 {row['成交笔数']:>4.0f} 笔 | 胜率: {row['胜率']:>5.1f}% | 期望收益: {row['期望收益']:>+6.2f}%")
        print("   💡 诊断: 如果股灾或阴跌时亏损极其严重，必须在 screenergf 里强制加入指数风控熔断。")
    
    # =========================================================
    # 维度二：乖离率 (Bias) 风险分布
    # =========================================================
    print("\n📉 [维度二] 均线乖离率 (追高风险) 诊断：")
    if 'B20' in df_merged.columns:
        # 将乖离率分箱
        df_merged['Bias_Band'] = pd.cut(df_merged['B20'], bins=[-1, 0, 0.05, 0.10, 0.20, 1], labels=['水下/贴线', '微偏离(0-5%)', '中偏离(5-10%)', '高偏离(10-20%)', '极度追高(>20%)'])
        bias_stats = df_merged.groupby('Bias_Band').agg(
            笔数=('stock_code', 'count'),
            胜率=('final_pnl', lambda x: (x > 0).mean() * 100),
            期望收益=('final_pnl', lambda x: x.mean() * 100)
        )
        for band, row in bias_stats.iterrows():
            if row['笔数'] > 0:
                print(f"   ➤ 【{band}】买入 {row['笔数']:>4.0f} 笔 | 胜率: {row['胜率']:>5.1f}% | 期望收益: {row['期望收益']:>+6.2f}%")
        print("   💡 诊断: 如果高偏离买入胜率极低，说明我们在主升浪高位接盘了，需限制最大乖离率。")

    # =========================================================
    # 维度三：独立基因实战证伪
    # =========================================================
    print("\n🧬 [维度三] 独立基因 (Bit位) 实战贡献度复盘：")
    features_to_check = ['T1_U', 'T1_D', 'T1_L', 'T1_B', 'M15_U', 'M15_H', 'M15_L']
    for f in features_to_check:
        if f in df_merged.columns:
            subset = df_merged[df_merged[f] == 1]
            if len(subset) > 0:
                f_win = (subset['final_pnl'] > 0).mean() * 100
                f_pnl = subset['final_pnl'].mean() * 100
                print(f"   - 包含【{f}】的样本: {len(subset):>4} 笔 | 胜率: {f_win:>5.1f}% | 独立期望收益: {f_pnl:>+6.2f}%")

    # =========================================================
    # 维度四：板块适应性
    # =========================================================
    print("\n🏢 [维度四] 板块适应性 (20CM vs 10CM)：")
    def get_board(code):
        if '688' in code or '689' in code: return '科创板(20%)'
        if '300' in code: return '创业板(20%)'
        return '主板(10%)'
    df_merged['Board'] = df_merged['stock_code'].apply(get_board)
    board_stats = df_merged.groupby('Board').agg(
        笔数=('stock_code', 'count'),
        胜率=('final_pnl', lambda x: (x > 0).mean() * 100),
        期望收益=('final_pnl', lambda x: x.mean() * 100)
    )
    for board, row in board_stats.iterrows():
         print(f"   ➤ 【{board}】成交 {row['笔数']:>4.0f} 笔 | 胜率: {row['胜率']:>5.1f}% | 期望收益: {row['期望收益']:>+6.2f}%")

if __name__ == '__main__':
    analyze_hologram_report()
