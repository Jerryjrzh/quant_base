import os
import pandas as pd
import numpy as np
import data_loader

def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    trades_csv = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest', 'full_calendar_trades.csv'))
    output_html = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest', 'trading_calendar_matrix.html'))

    if not os.path.exists(trades_csv):
        print(f"❌ 找不到全日历交易数据: {trades_csv}，请确保已运行批量回测脚本。")
        return

    # 1. 读取交易明细并对齐日期格式
    df = pd.read_csv(trades_csv)
    df['eval_date'] = pd.to_datetime(df['eval_date'])   # 条件单下达日期 (T)
    df['entry_date'] = pd.to_datetime(df['entry_date']) # 条件单买入触发日期 (T+1)
    df['exit_date'] = pd.to_datetime(df['exit_date'])   # 卖出结账日期

    # 2. 加载上证指数计算大盘每日涨跌幅
    index_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000001.day")
    df_index = data_loader.get_daily_data(index_path)
    if df_index is not None:
        df_index['market_pct'] = df_index['close'].pct_change()
    else:
        df_index = pd.DataFrame(columns=['market_pct'])

    # 3. 按触发/建仓日历天数聚合交易
    # A股实战中，我们重点看有实际建仓行为发生的“资金生效日”
    calendar_days = pd.date_range(start='2025-01-01', end='2026-04-30', freq='D')
    
    html_cards = []

    print("🚀 开始编译 HTML 矩阵日历...")
    for current_day in calendar_days:
        # 寻找这一天产生的交易
        day_trades = df[df['entry_date'] == current_day]
        
        # 提取大盘当天的真实幅度
        try:
            m_pct = df_index.loc[current_day, 'market_pct']
            m_str = f"{m_pct:+.2%}" if not pd.isna(m_pct) else "休市"
        except:
            m_str = "休市"

        # 如果这一天是周末或大盘休市，且策略没有产生交易，则不打印或者不作为核心矩阵展示
        if m_str == "休市" and day_trades.empty:
            continue

        # 初始化参数
        day_str = current_day.strftime('%Y-%m-%d')
        total_num = len(day_trades)
        loss_num = len(day_trades[day_trades['trade_status'] == '止损出局'])
        avg_pnl = day_trades['final_pnl'].mean() if total_num > 0 else 0.0

        # 根据用户指示的色标逻辑设定 CSS 类
        if total_num > 0 and loss_num > 0:
            # 🚨 触发了亏损/止损：标记为绿色高亮 (警示绿)
            status_class = "day-card loss-alert-green"
            badge = f"🚨 发生止损 {loss_num} 只"
        elif total_num > 0 and loss_num == 0:
            # 🏆 有建仓交易且零止损：标记为红色高亮 (胜利红)
            status_class = "day-card win-victory-red"
            badge = f"🔥 零止损完美运行"
        else:
            # 无交易日
            status_class = "day-card neutral-grey"
            badge = "💤 无建仓动作"

        # 生成个股明细流水
        detail_html = ""
        if total_num > 0:
            detail_html += "<div class='trade-details-wrapper'>"
            for _, row in day_trades.iterrows():
                pnl_class = "text-red" if row['final_pnl'] > 0 else "text-green"
                detail_html += (
                    f"<div class='stock-row'>"
                    f" <span>[{row['stock_code']}]</span> "
                    f" <span>下单T日: {row['eval_date'].strftime('%m-%d')}</span> "
                    f" <span>结账日: {row['exit_date'].strftime('%m-%d')}</span> "
                    f" <span class='{pnl_class}'>盈亏: {row['final_pnl']:+.2%}</span>"
                    f"</div>"
                )
            detail_html += "</div>"

        # 构建单个HTML日历盒子
        card_html = (
            f"<div class='{status_class}'>\n"
            f"  <div class='card-header-date'>{day_str} <span class='market-badge'>大盘: {m_str}</span></div>\n"
            f"  <div class='card-summary-line'>建仓数: {total_num} 只 | 日均收益: {avg_pnl:+.2%}</div>\n"
            f"  <div class='card-status-badge'>{badge}</div>\n"
            f"  {detail_html}\n"
            f"</div>\n"
        )
        html_cards.append(card_html)

    # 4. 组装高保真 HTML 模板
    html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>量化策略收益全景日历矩阵</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background-color: #fafafa;
            color: #333;
            margin: 0;
            padding: 24px;
        }}
        .container {{
            max-width: 2800px;
            margin: 0 auto;
        }}
        h1 {{
            text-align: center;
            color: #1a1a1a;
            font-size: 28px;
            margin-bottom: 8px;
        }}
        .subtitle {{
            text-align: center;
            color: #666;
            margin-bottom: 32px;
        }}
        .legend-bar {{
            background: white;
            padding: 16px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            margin-bottom: 24px;
            display: flex;
            gap: 24px;
            justify-content: center;
            font-size: 14px;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 8px; }}
        .box-sample {{ width: 20px; height: 20px; border-radius: 4px; }}
        
        /* 日历流动栅格布局 */
        .calendar-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
            gap: 16px;
        }}
        
        .day-card {{
            background: #ffffff;
            border: 1px solid #e0e0e0;
            border-radius: 12px;
            padding: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.02);
            transition: all 0.2s ease;
        }}
        .day-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(0,0,0,0.06);
        }}
        
        /* 🟩 核心色标：止损高亮绿 (采用优雅的复古莫兰迪绿色调，不刺眼) */
        .loss-alert-green {{
            background-color: #edf7ed !important;
            border-color: #b7deb7 !important;
        }}
        .loss-alert-green .card-status-badge {{
            color: #1e4620;
            background: #c8e6c9;
        }}
        
        /* 🟥 核心色标：零止损胜利红 (采用饱满的淡粉红衬托红色文本) */
        .win-victory-red {{
            background-color: #fff0f0 !important;
            border-color: #ffcccc !important;
        }}
        .win-victory-red .card-status-badge {{
            color: #a80000;
            background: #ffcdd2;
        }}
        
        .neutral-grey {{ background-color: #fcfcfc; border-color: #eeeeee; color: #999; }}
        
        .card-header-date {{
            font-weight: bold;
            font-size: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
            color: #111;
        }}
        .market-badge {{ font-size: 12px; font-weight: normal; color: #666; }}
        .card-summary-line {{ font-size: 13px; color: #555; margin-bottom: 12px; }}
        
        .card-status-badge {{
            display: inline-block;
            font-size: 12px;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            margin-bottom: 12px;
            background: #eeeeee;
            color: #666;
        }}
        
        .trade-details-wrapper {{
            border-top: 1px dashed #dcdcdc;
            padding-top: 8px;
            max-height: 150px;
            overflow-y: auto;
            font-size: 12px;
        }}
        .stock-row {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid #f5f5f5;
        }}
        .text-red {{ color: #d32f2f; font-weight: bold; }}
        .text-green {{ color: #388e3c; font-weight: bold; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 自适应均线策略交易对账日历看板</h1>
        <div class="subtitle">执行周期: 2025.01.01 - 2026.04.30 | 严格匹配 V3.0 防飞刀/防错杀状态机</div>
        
        <div class="legend-bar">
            <div class="legend-item">
                <div class="box-sample" style="background: #fff0f0; border: 1px solid #ffcccc;"></div>
                <span>🟥 胜利红盒子：当天有实际交易，且【零个股触发止损】</span>
            </div>
            <div class="legend-item">
                <div class="box-sample" style="background: #edf7ed; border: 1px solid #b7deb7;"></div>
                <span>🟩 警示绿盒子：当天建仓的股票中【有标的不幸沦为例外止损】</span>
            </div>
            <div class="legend-item">
                <div class="box-sample" style="background: #fcfcfc; border: 1px solid #eeeeee;"></div>
                <span>⬜ 灰色盒子：当天大盘休市或策略处于冷静期，无建仓信号</span>
            </div>
        </div>

        <div class="calendar-grid">
            {"".join(html_cards)}
        </div>
    </div>
</body>
</html>
"""

    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html_template)
    print(f"🎉 机构级高保真全景 HTML 交易日历编译成功！")
    print(f"💾 请立刻双击打开体验: {output_html}")

if __name__ == '__main__':
    main()
