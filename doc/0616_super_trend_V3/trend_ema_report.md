 ▪ ---

   趋势 EMA (通达信双 EMA 策略) 实施报告

   一、需求来源

   doc/0616_super_trend_V3/trend_ema.md — 通达信/同花顺趋势 EMA 指标公式的 Python
   还原，包含三部分核心逻辑：
   ┌────────────────┬─────────────────────────┬───────────────────────────────────────┐
   │ 模块           │ 原始公式                │ 说明                                  │
   ├────────────────┼─────────────────────────┼───────────────────────────────────────┤
   │ 主趋势线 (MTL) │ EMA(EMA(Close, 13), 13) │ 双重 EMA 平滑，上升红色/下降蓝色      │
   │ K线三色        │ EMA5 vs EMA10 vs EMA20  │ RED(多头) / GREEN(空头) / WHITE(震荡) │
   │ 买卖信号       │ 上破红线买，下破绿K卖   │ Close 穿越 MTL + 趋势方向确认         │
   └────────────────┴─────────────────────────┴───────────────────────────────────────┘
   ---

   二、修改文件清单
   ┌────────────────────┬───────────────────────┬─────────────────────────────────────┐
   │ 文件               │ 改动类型              │ 行范围                              │
   ├────────────────────┼───────────────────────┼─────────────────────────────────────┤
   │ backend/app.py     │ 新增计算 + 修改序列化 │ L570-595, L703                      │
   │ frontend/js/app.js │ 新增数据提取 +        │ L375-384, L473, L528-565, L680-725, │
   │                    │ 图表渲染              │ L905-959                            │
   └────────────────────┴───────────────────────┴─────────────────────────────────────┘
   ---

   三、后端实现 (backend/app.py)

   3.1 指标计算 (L570-595)

   插入位置：GT 双轨计算之后、策略回测之前。
    # 趋势EMA指标 (通达信双EMA策略)
    close = df['close'].astype(float)
    ema13 = close.ewm(span=13, adjust=False).mean()
    df['mtl'] = ema13.ewm(span=13, adjust=False).mean()          # 主趋势线
    df['mtl_rising'] = (df['mtl'] > df['mtl'].shift(1)).astype(int)  # 1=上升, 0=下降

    df['ema5']  = close.ewm(span=5, adjust=False).mean()
    df['ema10'] = close.ewm(span=10, adjust=False).mean()
    df['ema20'] = close.ewm(span=20, adjust=False).mean()

    # K线三色分类
    aa  = df['ema5'] > df['ema20']   # 多头区域
    bb  = df['ema5'] < df['ema20']   # 空头区域
    cc  = df['ema5'] > df['ema10']
    cc1 = df['ema5'] < df['ema10']

    candle_color = pd.Series(0, index=df.index)
    candle_color[aa] = 1              # RED (多头)
    candle_color[bb] = -1             # GREEN (空头)
    candle_color[bb & cc] = 0         # WHITE (震荡覆盖)
    candle_color[aa & cc1] = 0        # WHITE (震荡覆盖)
    df['candle_color'] = candle_color

    # 买卖信号
    buy_sig  = (close > df['mtl']) & (df['open'] < df['mtl']) & (df['mtl_rising'] == 1)
    sell_sig = (candle_color == -1) & (close < df['low'].shift(1))
    df['trend_buy']  = buy_sig.astype(int)
    df['trend_sell'] = sell_sig.astype(int)
   与原始 spec 的映射关系：
   ┌────────────────────────────────┬───────────────────────┬───────────────────────────────┐
   │ Spec 变量                      │ 本地实现              │ 编码方式                      │
   ├────────────────────────────────┼───────────────────────┼───────────────────────────────┤
   │ Main_Trend_Line                │ df['mtl']             │ float                         │
   │ MTL_Color (RED/BLUE)           │ df['mtl_rising']      │ int: 1=上升, 0=下降           │
   │ Candle_Color (RED/GREEN/WHITE) │ df['candle_color']    │ int: 1=RED, -1=GREEN, 0=WHITE │
   │ Buy_Signal                     │ df['trend_buy']       │ int: 0/1                      │
   │ Sell_Signal                    │ df['trend_sell']      │ int: 0/1                      │
   │ AA / BB / CC / CC1             │ 局部变量 aa/bb/cc/cc1 │ bool Series                   │
   └────────────────────────────────┴───────────────────────┴───────────────────────────────┘
   3.2 响应序列化 (L703)
    # 修改前:
    indicator_data = df_reset[['date', ..., 'gt_upper', 'gt_lower', 'gt_mid']].to_dict('records')

    # 修改后: 新增 8 个字段
    indicator_data = df_reset[[..., 'gt_mid', 'mtl', 'mtl_rising', 'ema5', 'ema10', 'ema20',
                               'candle_color', 'trend_buy', 'trend_sell']].to_dict('records')
   ---

   四、前端实现 (frontend/js/app.js)

   4.1 数据提取 (L375-384)
    const mtlData         = chartData.indicator_data.map(item => item.mtl);
    const mtlRisingData   = chartData.indicator_data.map(item => item.mtl_rising);
    const ema5Data        = chartData.indicator_data.map(item => item.ema5);
    const ema10Data       = chartData.indicator_data.map(item => item.ema10);
    const ema20Data       = chartData.indicator_data.map(item => item.ema20);
    const candleColorData = chartData.indicator_data.map(item => item.candle_color);
    const trendBuyData    = chartData.indicator_data.map(item => item.trend_buy);
    const trendSellData   = chartData.indicator_data.map(item => item.trend_sell);

    const hasCandleColor  = candleColorData.some(v => v !== null && v !== undefined);
   4.2 K线三色着色 (L528-565)

   对 candlestick series 的 itemStyle 四个属性 (color, color0, borderColor, borderColor0)
   统一使用函数回调：
   ┌───────────────────┬─────────────────────┬─────────────────┐
   │ candle_color 值   │ 含义                │ 渲染颜色        │
   ├───────────────────┼─────────────────────┼─────────────────┤
   │ 1                 │ 多头 (EMA5 > EMA20) │ #e74c3c 红色    │
   │ -1                │ 空头 (EMA5 < EMA20) │ #2ecc71 绿色    │
   │ 0 (有趋势数据时)  │ 震荡 (均线交织)     │ #b0b0b0 灰色    │
   │ null (无趋势数据) │ 回退默认            │ 阳线红 / 阴线绿 │
   └───────────────────┴─────────────────────┴─────────────────┘
   性能优化：hasCandleColor 预计算标志，避免每根 K 线调用 Array.some()。

   4.3 MTL 主趋势线 (L682-695)
    name: 'MTL', type: 'line', lineWidth: 2
    color: function(params) {
        return mtlRisingData[params.dataIndex] === 1 ? '#e74c3c' : '#3498db';
    }
    // 上升 = 红色, 下降 = 蓝色
   4.4 EMA 辅助线 (L697-725)
   ┌───────┬────────────┬───────────────┐
   │ 线名  │ 颜色       │ 样式          │
   ├───────┼────────────┼───────────────┤
   │ EMA5  │ #ff6b6b 红 │ 虚线 (dotted) │
   │ EMA10 │ #4ecdc4 青 │ 虚线 (dotted) │
   │ EMA20 │ #9b59b6 紫 │ 虚线 (dotted) │
   └───────┴────────────┴───────────────┘
   4.5 买卖信号标记 (L905-959)
   ┌──────────┬─────────────────────┬────────────┬──────────────────┐
   │ 信号     │ 图形                │ 颜色       │ 位置             │
   ├──────────┼─────────────────────┼────────────┼──────────────────┤
   │ 趋势买入 │ 正三角 triangle     │ #ff4444 红 │ K线最低价 (low)  │
   │ 趋势卖出 │ 倒钉 pin rotate 180 │ #00aa00 绿 │ K线最高价 (high) │
   └──────────┴─────────────────────┴────────────┴──────────────────┘
   两个 scatter series 通过 option.series.push() 动态添加，仅在存在信号时才渲染。

   4.6 Legend 更新 (L473)

   新增条目：MTL, EMA5, EMA10, EMA20, 趋势买入, 趋势卖出（可通过点击图例切换显示/隐藏）

   ---

   五、数据流总览
    ┌─────────────┐
    │  app.py     │  OHLCV → EMA13 → MTL → mtl_rising
    │  L570-595   │       → EMA5/10/20 → candle_color
    │             │       → buy_sig / sell_sig → trend_buy / trend_sell
    └──────┬──────┘
           │ indicator_data (JSON)
           ▼
    ┌─────────────┐
    │  app.js     │  indicator_data → mtlData / ema*Data / candleColorData ...
    │  L375-384   │
    └──────┬──────┘
           │
           ├── K线 candlestick itemStyle → 三色着色
           ├── MTL line series → 红/蓝变色线
           ├── EMA5/10/20 line series → 虚线
           ├── scatter: 趋势买入 → 红色三角 (low)
           └── scatter: 趋势卖出 → 绿色倒钉 (high)
   ---

   六、验证方法

   1. 启动 Flask 后端，打开前端页面
   2. 输入任意股票代码，加载日线图表
   3. 检查项：
     - K 线呈现红/绿/灰三色（非传统阳红阴绿）
     - MTL 粗线在上升趋势时为红色，下降时为蓝色
     - EMA5/10/20 虚线叠加在主图上
     - 红色三角出现在 Close 上穿 MTL 且 MTL 上升的位置
     - 绿色倒钉出现在 K 线变绿且跌破前低的位置
     - 点击图例可独立开关每个指标

   ---

   七、待优化项
   ┌──────────────────┬─────────────────────────────────────────────────────────────┬────────┐
   │ 项目             │ 说明                                                        │ 优先级 │
   ├──────────────────┼─────────────────────────────────────────────────────────────┼────────┤
   │ 分时周期适配     │ 60min 以下周期 EMA 参数可能需要调整                         │ 中     │
   │ 信号回测集成     │ 趋势买卖信号尚未接入 backtester                             │ 中     │
   │ MTL 颜色平滑     │ lineStyle.color                                             │ 低     │
   │                  │ 函数回调可能导致段间颜色不连续，可考虑拆分为两段 series     │        │
   │ candle_color NaN │ 首行 mtl_rising 因 shift 产生 NaN，已被 df.replace({np.nan: │ 已完成 │
   │ 处理             │ None}) 转 null                                              │        │
   └──────────────────┴─────────────────────────────────────────────────────────────┴────────┘

