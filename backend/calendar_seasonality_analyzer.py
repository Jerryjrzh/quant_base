import os
import pandas as pd
import numpy as np
import data_loader

def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    trades_csv = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest', 'full_calendar_trades.csv'))
    output_dir = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest'))
    report_txt_path = os.path.join(output_dir, 'monthly_seasonality_report.txt')

    if not os.path.exists(trades_csv):
        print(f"❌ 找不到全日历交易数据: {trades_csv}，请确保已运行 calendar_batch_runner.py")
        return

    # 1. 加载交易数据并按买入月份进行归类
    df_trades = pd.read_csv(trades_csv)
    df_trades['entry_date'] = pd.to_datetime(df_trades['entry_date'])
    df_trades['year_month'] = df_trades['entry_date'].dt.to_period('M')

    # 2. 加载上证指数计算大盘月度波幅
    index_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000001.day")
    df_index = data_loader.get_daily_data(index_path)
    if df_index is not None:
        df_index['ym'] = df_index.index.to_period('M')
        # 计算大盘月度收益率与最高/最低振幅
        market_monthly = df_index.groupby('ym').agg(
            m_open=('open', 'first'),
            m_close=('close', 'last'),
            m_high=('high', 'max'),
            m_low=('low', 'min')
        )
        market_monthly['market_return'] = (market_monthly['m_close'] - market_monthly['m_open']) / market_monthly['m_open']
        market_monthly['market_amplitude'] = (market_monthly['m_high'] - market_monthly['m_low']) / market_monthly['m_low']
    else:
        market_monthly = pd.DataFrame()

    # 3. 按月聚合策略表现
    monthly_stats = df_trades.groupby('year_month').agg(
        total_trades=('final_pnl', 'count'),
        win_count=('trade_status', lambda x: (x == '止盈成功').sum()),
        loss_count=('trade_status', lambda x: (x == '止损出局').sum()),
        hold_count=('trade_status', lambda x: (x == '持仓到期').sum()),
        avg_pnl=('final_pnl', 'mean')
    )

    # 4. 合并数据
    if not market_monthly.empty:
        monthly_stats = monthly_stats.join(market_monthly[['market_return', 'market_amplitude']], how='left')

    # 5. 开始打印与生成可视化日历报告
    report_lines = []
    
    header = "★" * 70 + "\n" + " 📅  A股量化策略月度执行日历与大盘波动拟合看板\n" + "★" * 70 + "\n"
    print(header)
    report_lines.append(header)

    # 遍历每一个月份，生成日历卡片
    for ym, row in monthly_stats.iterrows():
        year = ym.year
        month = ym.month
        
        # 标记高危敏感月份（3月和4月年报季风险）
        is_risk_month = month in [3, 4]
        month_label = f"【{year}年 {month:02d}月】"
        if is_risk_month:
            month_label += " 🚨 财报窗口高危月 (建议收紧/熔断短线)"
        else:
            month_label += " ✨ 趋势运行安全月"

        win_rate = row['win_count'] / row['total_trades'] if row['total_trades'] > 0 else 0
        m_ret = row.get('market_return', 0.0)
        m_amp = row.get('market_amplitude', 0.0)

        card = (
            f"┌────────────────────────────────────────────────────────────────────┐\n"
            f"  {month_label:<52}\n"
            f"├────────────────────────────────────────────────────────────────────┤\n"
            f"  📈 大盘环境 -> 月度涨跌幅: {m_ret:+.2%}  |  大盘日内极限波幅: {m_amp:.2%}\n"
            f"  ⚙️ 策略表现 -> 触发建仓数: {int(row['total_trades']):>4} 笔  |  严格止盈胜率: {win_rate:.2%}\n"
            f"  💰 财务对账 -> 期望笔均收益: {row['avg_pnl']:+.2%}\n"
            f"                 [🎉 止盈: {int(row['win_count'])}笔  |  🛑 止损: {int(row['loss_count'])}笔  |  ⌛ 到期: {int(row['hold_count'])}笔]\n"
            f"└────────────────────────────────────────────────────────────────────┘\n"
        )
        print(card)
        report_lines.append(card)

    # 战略性总结意见
    summary = (
        "💡 【实战前瞻性风控指导方案】\n"
        "--------------------------------------------------------------------\n"
        "1. 软打分硬切换：后续每逢 3月15日 - 4月30日，执行卡自动进入【财报季极端防守模式】。\n"
        "2. 挂单深度收紧：在此期间，常规型标的直接拒绝生成，深踩型标的由下浮 4% 强制收紧至下浮 6.5% 挂单。\n"
        "3. 降维打击左侧：财报季只允许做周线底部的多头共振股，严禁任何形式的短线情绪破位追逐。\n"
    )
    print(summary)
    report_lines.append(summary)

    # 【代码治理】：归档到指定结果目录
    with open(report_txt_path, 'w', encoding='utf-8') as f:
        f.writelines(report_lines)
    print(f"📄 详细的可视化季节性日历报告已保存至: {report_txt_path}")

if __name__ == '__main__':
    main()
