这段选股公式的核心逻辑是构建一个 **双重平滑的动态支撑通道** （金钻趋势与金牛2的带状区域），辅助以 **BBI多空分水岭** ，并在价格跌入或跌破底部支撑线（金钻趋势）时给出黄色的视觉提示，同时对涨停板进行紫红色高亮。

在将其转化为自动化回测脚本之前，必须首先排除一个量化回测中的致命陷阱： **XMA（偏移移动平均）** 。在多数传统看盘软件中，XMA属于 **未来函数** （会引用未来数据进行当前计算）。如果直接回测包含XMA的公式，信号会不断“漂移”重绘，导致回测出一条虚假的、完美的资金曲线，但实盘将面临严重亏损。

要进行真实有效的数据驱动回测并制定操作策略，需要将XMA替换为无未来函数的双重指数移动平均（EMA），并将操作逻辑建立在严格的位置判定之上。

### 核心操作逻辑与定性

技术图形和指标逻辑本身并不具备绝对的预测力。**所有的技术形态只有在特定的历史价格位置被识别时才有效，位置决定定性。** 公式中频繁亮起的“黄色柱体”（即价格触及或跌破金钻趋势线）仅仅是一个触发器。如何操作，取决于该信号发生时的宏观位置：

1. **极寒底部的左侧买点：** 当价格处于长周期（如年线级别）的绝对低位区域，长期缩量下跌后，价格触及“金钻趋势”下轨并出现黄色提示。此时的位置决定了信号的性质是“探底”，风险暴露极低，可以直接在此处结合缩量企稳信号进行分批建仓。
2. **主升浪中的回调上车：** 当整体价格重心已经突破底部区间，均线系统（如MA13等）多头排列，此时价格因短期波动急跌砸破“金钻趋势”线。由于大级别处于向上的主升波段中，这里的触线属于“主力洗盘”的极佳倒车接人位置。
3. **高位破位的规避区（陷阱）：** 如果价格已经在高位经历过大幅爆炒，随后跌破BBI线，再触及“金钻趋势”线。此时的位置定性为“头部破位”，这里的黄色信号是下跌中继的诱多，应作为绝对的卖出或规避信号，坚决放弃操作。

### Python  pandas 回测脚本框架

以下是将该逻辑转换为真实可回测的 Python 脚本。脚本去除了未来函数，并加入了一个简单的“位置评估”模块，只有在位置判定安全时，才将触轨视为买入信号。

**Python**

```
import pandas as pd
import numpy as np

def calculate_indicators(df):
    """
    计算替代版的金钻趋势与BBI指标（消除未来函数）
    传入的 df 需包含: 'open', 'high', 'low', 'close'
    """
    # 1. 消除未来函数，使用双重EMA替代XMA进行真实平滑计算
    # 第一层平滑
    df['EMA25_H'] = df['high'].ewm(span=25, adjust=False).mean()
    df['EMA25_L'] = df['low'].ewm(span=25, adjust=False).mean()
  
    # 第二层平滑
    df['D_EMA25_H'] = df['EMA25_H'].ewm(span=25, adjust=False).mean()
    df['D_EMA25_L'] = df['EMA25_L'].ewm(span=25, adjust=False).mean()
  
    # 2. 计算上轨(金牛)与下轨(金钻趋势)
    df['Golden_Bull'] = (df['D_EMA25_H'] - df['D_EMA25_L']) * 1 + df['D_EMA25_H']
    df['Golden_Trend'] = df['D_EMA25_L'] - (df['D_EMA25_H'] - df['D_EMA25_L']) * 1
  
    # 3. 计算金牛2 (下轨的EMA)
    df['Golden_Bull2'] = df['Golden_Trend'].ewm(span=25, adjust=False).mean()
  
    # 4. 计算 BBI (多空指数)
    df['BBI'] = (df['close'].rolling(5).mean() + 
                 df['close'].rolling(10).mean() + 
                 df['close'].rolling(20).mean() + 
                 df['close'].rolling(30).mean()) / 4
               
    # 5. 涨停判定 (简单粗暴的10%限制，如果是创业板可改为20%)
    df['Limit_Up'] = np.where(df['close'] >= df['close'].shift(1) * 1.098, 1, 0)
  
    return df

def generate_signals(df):
    """
    结合“位置定性”生成交易信号
    """
    # 计算当前价格在过去120个交易日中的相对位置分位 (0-1之间，0为绝对底部，1为绝对顶部)
    df['Rolling_Min_120'] = df['low'].rolling(120).min()
    df['Rolling_Max_120'] = df['high'].rolling(120).max()
    df['Position_Ratio'] = (df['close'] - df['Rolling_Min_120']) / (df['Rolling_Max_120'] - df['Rolling_Min_120'] + 1e-9)
  
    # 定义触轨条件（即原公式中的黄色 STICKLINE 区域）
    # 当最低价跌破金钻趋势线，且收盘价还能收回来一些，或者整体在趋势线附近运行
    touch_bottom_band = df['low'] <= df['Golden_Trend']
  
    # 交易逻辑：位置决定定性
    df['Signal'] = 0
  
    for i in range(120, len(df)):
        # 必须满足技术形态触发
        if touch_bottom_band.iloc[i]:
          
            current_position = df['Position_Ratio'].iloc[i]
          
            # 过滤逻辑 1: 底部确认 (位置分位 < 0.3)
            # 此时的触轨大概率是洗盘或探底，有操作价值
            if current_position < 0.30:
                df.at[df.index[i], 'Signal'] = 1  # 产生买入信号
              
            # 过滤逻辑 2: 高位陷阱规避 (位置分位 > 0.7)
            # 此时处于高位区，触及下轨往往意味着破位，坚决不操作或做空/平仓
            elif current_position > 0.70:
                df.at[df.index[i], 'Signal'] = -1 # 产生卖出/止损信号
              
    return df

# === 模拟执行 ===
# 假设有一个名为 data 的 DataFrame 包含了 OHLC 数据
# data = pd.read_csv('your_stock_data.csv')
# df_with_indicators = calculate_indicators(data)
# df_with_signals = generate_signals(df_with_indicators)
# print(df_with_signals[df_with_signals['Signal'] == 1][['close', 'Golden_Trend', 'Position_Ratio']])
```

### 回测参数优化的下一步

在使用上述无未来函数的代码进行回测时，建议重点观测以下数据的表现来进一步固化操作：

1. **反弹高度与回调深度的分布：** 当信号在“低位”（`Position_Ratio < 0.3`）触发后，记录后续20个交易日内的平均最大涨幅与平均最大回撤。
2. **动态出场设定：** 止盈止损不应设置固定比例（如8%），而应根据回测数据中同级别位置的反弹分布的80%分位数作为止盈目标，将入场触发价下方的ATR（真实波动幅度）缓冲作为防守底线。这样捞到的“鱼”才能安稳落袋。
