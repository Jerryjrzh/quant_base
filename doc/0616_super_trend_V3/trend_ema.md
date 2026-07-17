根据你提供的通达信/同花顺指标公式以及图片中的文字说明，这个交易系统的核心逻辑可以分为三个部分： **主趋势线（双重EMA）的变色** 、 **K线的红绿白三色判定** ，以及你补充的 **买卖信号（上破红线买，下破绿K卖）** 。

下面是使用 `pandas` 和 `numpy` 将该指标转化为 Python 量化脚本的代码。

### Python 还原脚本

确保你已经安装了 `pandas` 和 `numpy`。这个脚本接收一个包含 `Open`, `High`, `Low`, `Close` 的 DataFrame，并计算出所有指标颜色及买卖信号。

**Python**

```
import pandas as pd
import numpy as np

def calculate_tdx_strategy(df):
    """
    根据通达信源码和买卖规则计算趋势线、K线颜色及交易信号。
    :param df: pandas DataFrame，必须包含 'Open', 'High', 'Low', 'Close' 列
    :return: 包含指标和信号的 DataFrame
    """
    # 确保数据按时间正序排列
    df = df.copy()

    # ==========================================
    # 1. 计算主趋势线 (EMA的EMA) 及 颜色判定
    # ==========================================
    # 主趋势线:EMA(EMA(C,13),13)
    ema13 = df['Close'].ewm(span=13, adjust=False).mean()
    df['Main_Trend_Line'] = ema13.ewm(span=13, adjust=False).mean()
  
    # B:=主趋势线>REF(主趋势线,1); 判断趋势线上升还是下降
    # 上升为红色 (RED)，下降或走平为蓝色 (BLUE)
    df['MTL_Color'] = np.where(df['Main_Trend_Line'] > df['Main_Trend_Line'].shift(1), 'RED', 'BLUE')

    # ==========================================
    # 2. 计算 K线颜色 (红、绿、白)
    # ==========================================
    # 计算各周期 EMA
    ema5 = df['Close'].ewm(span=5, adjust=False).mean()
    ema10 = df['Close'].ewm(span=10, adjust=False).mean()
    ema20 = df['Close'].ewm(span=20, adjust=False).mean()

    # 定义源码中的布尔条件
    AA = ema5 > ema20
    BB = ema5 < ema20
    CC = ema5 > ema10
    CC1 = ema5 < ema10
    # DD = df['Close'] < df['Open'] # 阴线实体 (暂不直接用于颜色分类，用于画图实心空心)

    # 初始化 K 线颜色
    df['Candle_Color'] = 'NONE'

    # 按照源码 STICKLINE 的覆盖逻辑分配颜色 (后面的条件会覆盖前面的)
    df.loc[AA, 'Candle_Color'] = 'RED'    # 多头区域
    df.loc[BB, 'Candle_Color'] = 'GREEN'  # 空头区域
  
    # 震荡/观望区域覆盖为白色
    df.loc[BB & CC, 'Candle_Color'] = 'WHITE'
    df.loc[AA & CC1, 'Candle_Color'] = 'WHITE'

    # ==========================================
    # 3. 交易信号生成 (K线实体上破红线买入,下破绿K出)
    # ==========================================
    # 买入信号：K线实体上破红线 (收盘价大于趋势线，开盘价小于趋势线，且趋势线当前为红色)
    buy_condition = (
        (df['Close'] > df['Main_Trend_Line']) & 
        (df['Open'] < df['Main_Trend_Line']) & 
        (df['MTL_Color'] == 'RED')
    )
    df['Buy_Signal'] = buy_condition

    # 卖出信号：下破绿K出 
    # 逻辑释义：当前K线变为绿色，且收盘价呈下跌趋势（或跌破前一根绿K的低点）。
    # 这里采用最直接的防守逻辑：当K线颜色判定为绿色，且当前收盘价跌破昨日最低价时触发卖出。
    sell_condition = (
        (df['Candle_Color'] == 'GREEN') & 
        (df['Close'] < df['Low'].shift(1))
    )
    df['Sell_Signal'] = sell_condition

    return df

# ==========================================
# 测试用例 (使用模拟数据)
# ==========================================
if __name__ == "__main__":
    # 生成一些模拟的OHLC数据
    np.random.seed(42)
    dates = pd.date_range('2023-01-01', periods=100)
    data = {
        'Open': np.random.uniform(90, 110, 100),
        'High': np.random.uniform(105, 115, 100),
        'Low': np.random.uniform(85, 95, 100),
        'Close': np.random.uniform(90, 110, 100)
    }
    df = pd.DataFrame(data, index=dates)

    # 运行策略
    result_df = calculate_tdx_strategy(df)
  
    # 打印包含买入或卖出信号的行
    signals = result_df[(result_df['Buy_Signal'] == True) | (result_df['Sell_Signal'] == True)]
    print(signals[['Close', 'Main_Trend_Line', 'MTL_Color', 'Candle_Color', 'Buy_Signal', 'Sell_Signal']])
```

### 代码逻辑拆解说明：

1. **`Main_Trend_Line` (主趋势线)** ：使用两次指数移动平均（EMA）计算。判定当 `当前的趋势线 > 昨天的趋势线` 时，标记为 `RED`，反之为 `BLUE`。
2. **`Candle_Color` (K线颜色)** ：严格按照你给出的图表右下角公式，将短期均线（5日）与中长期均线（10日、20日）进行对比。先分配红色（做多）和绿色（做空），再将均线交织纠缠的部分（`BB AND CC` 或 `AA AND CC1`）覆盖为白色（观望平仓区）。
3. **`Buy_Signal` (买入)** ：当满足 `Close > 趋势线` 且 `Open < 趋势线`（实体穿越）**并且**当前趋势线为红色时，输出为 `True`。
4. **`Sell_Signal` (卖出)** ：“下破绿K”在量化里的实现通常是指防守位跌破。代码中默认设定为：**当K线判定为绿色，并且收盘价跌破了上一根K线的最低价时**发出离场信号。你可以根据实战情况调整这一行的 `sell_condition`。
