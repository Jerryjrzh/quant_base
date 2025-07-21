import pandas as pd
import data_loader
import indicators
import strategies

# --- 您需要修改这里 ---
# 请填入一只您熟悉的、成交活跃的股票代码进行诊断
# 例如：贵州茅台
STOCK_TO_DEBUG = 'sh600519'
MARKET = STOCK_TO_DEBUG[:2]
STRATEGY_TO_DEBUG = 'PRE_CROSS' # 您可以切换 'PRE_CROSS' 或 'TRIPLE_CROSS'
# --- 修改结束 ---

def run_debug():
    """对单只股票进行策略条件的单步诊断"""
    print(f"--- 开始诊断股票: {STOCK_TO_DEBUG}, 策略: {STRATEGY_TO_DEBUG} ---")

    # 1. 加载数据
    file_path = f'data/{MARKET}/lday/{STOCK_TO_DEBUG}.day'
    try:
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 150:
            print("错误：数据加载失败或数据量不足150天。")
            return
        print(f"数据加载成功，最新一天: {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
        print("最新5条数据:")
        print(df.tail())
        print("-" * 50)
    except FileNotFoundError:
        print(f"错误：找不到数据文件 {file_path}。请检查路径和文件名是否正确。")
        return

    # 2. 计算所有指标
    dif, dea = indicators.calculate_macd(df)
    k, d, j = indicators.calculate_kdj(df)
    rsi6 = indicators.calculate_rsi(df, 6)
    rsi12 = indicators.calculate_rsi(df, 12)
    
    # 3. 逐一打印策略条件及相关指标值
    print(f"--- 正在分解策略 '{STRATEGY_TO_DEBUG}' 的条件 ---")

    if STRATEGY_TO_DEBUG == 'PRE_CROSS':
        # --- “临界金叉”策略条件分解 ---
        
        # 条件1: KDJ
        cond1_kdj = (j > k) & (k > d) & (k > k.shift(1)) & (d < 50)
        print(f"\n[条件1: KDJ] J > K > D, K线向上, D < 50")
        print(f"  - 最新一天是否满足: {cond1_kdj.iloc[-1]}")
        print("  - 最近3天KDJ数值:")
        kdj_df = pd.DataFrame({'K': k.tail(3), 'D': d.tail(3), 'J': j.tail(3)})
        print(kdj_df.round(2))

        # 条件2: MACD
        macd_bar = dif - dea
        cond2_macd = (dif < dea) & (macd_bar > macd_bar.shift(1)) & (dea < 0.1)
        print(f"\n[条件2: MACD] DIF < DEA, 绿柱缩短, DEA < 0.1")
        print(f"  - 最新一天是否满足: {cond2_macd.iloc[-1]}")
        print("  - 最近3天MACD数值:")
        macd_df = pd.DataFrame({'DIF': dif.tail(3), 'DEA': dea.tail(3), 'MACD_BAR': macd_bar.tail(3)})
        print(macd_df.round(3))

        # 条件3: RSI
        cond3_rsi = (rsi6 > rsi6.shift(1)) & (rsi6 < 60)
        print(f"\n[条件3: RSI] RSI(6) 向上, 且 RSI(6) < 60")
        print(f"  - 最新一天是否满足: {cond3_rsi.iloc[-1]}")
        print("  - 最近3天RSI(6)数值:")
        print(rsi6.tail(3).round(2))
        
        # 最终结果
        final_signal = cond1_kdj & cond2_macd & cond3_rsi
        print("-" * 50)
        print(f"最终诊断结果: {final_signal.iloc[-1]}")
        
    else:
        print("暂不支持诊断其他策略，请在脚本中添加。")

if __name__ == '__main__':
    run_debug()
