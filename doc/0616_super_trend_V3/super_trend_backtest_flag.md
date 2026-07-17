这是一个非常专业的量化进阶思路。您所描述的，实际上是从传统的“事件驱动（Event-Driven）” **跨越到了高级量化系统中的** “状态机驱动（State-Machine Driven）”。

孤立地看一个入场切片（例如公式亮起黄色信号）是盲人摸象。只有将整个交易划分为 **评估周期（T-N）、信号发生（T0）、观察建仓周期（T1-Tm）和持仓操作周期（Tm-Tx）** ，并将每个周期的信号特征串联起来，才能完成真正的操作摸底。

结合您之前提到的“深渊底部”与“主升浪”模型，我们可以将这套“全周期状态机”的设计落地。

### 第一阶段：全生命周期切片与特征标记

我们需要在时间轴上切出四个独立的周期，每个周期只负责收集特定的“标记（Tags）”，不急于做动作。

#### 1. 评估周期 (T-120 到 T-1) —— 定性宏观状态

* **动作：** 扫描历史数据，不对任何短期波动做反应。
* **标记内容：**
  * `Position_Tag` (位置标记): 极寒深渊底 (0~0.2) / 底部启动 (0.2~0.4) / 主升浪中继 (0.4~0.7) / 高位区 (>0.8)。
  * **趋势标记:** BBI 是否多头排列？MA13 是否向上发散？
  * **波动率标记:** 过去 20 天的 ATR（真实波动幅度），用于后续计算安全网格。

#### 2. 信号发生节点 (T0) —— 激活观察状态

* **动作：** 价格触及“金钻趋势”下轨，公式发出预警信号。
* **标记内容：**
  * `Trigger_Tag` (触发标记): 记录当日的 `Close_T0` 和 `Golden_Trend_T0` 价格。
  * **状态转换：** 系统从 `WAITING` (空闲) 切换为 `OBSERVING` (伏击观察)。**注意：此时绝对不买入。**

#### 3. 操作观察周期 (T1 到 T+10) —— 锚定入场点

这是传统回测最容易忽略的一环。信号发生后，根据全量数据回测出的回调深度，在此周期内布置网格。

* **标记内容：**
  * **量价标记:** 是否出现地量（缩量至前期的1/3）？
  * **辅助指标标记:** MA13 是否在下方形成支撑？KDJ 是否在底部钝化后拐头？小级别 MACD 是否金叉？
  * `Price_Action_Tag`: 价格是否跌入我们根据回测数据反推的回调目标区（例如 T0 价格的 -5% 到 -10% 区间）。

#### 4. 持仓评估周期 (持仓后) —— 动态退出机制

* **动作：** 订单成交，系统状态切换为 `HOLDING`。
* **标记内容：**
  * `Max_Rebound_Tag`: 入场后的最大反弹高度。
  * **均线标记:** 收盘价与 MA13 的相对关系（是否有效击穿）。

### 第二阶段：基于标记组合的“动作映射矩阵”

有了上述四个周期的标记，我们就可以倒推并制定严格的操作纪律。以下是核心操作回测逻辑的映射：

| **T-N 评估标记 (宏观位置)**                         | **T0 触发标记** | **T1~T10 观察周期标记 (确认与入场)**                                                         | **动作指令 (Action)**                                                                              |
| --------------------------------------------------------- | --------------------- | -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **深渊底部 (Pos < 0.2)**``长期缩量，均线走平 | 触及下轨              | **形态:**缩量企稳``**指标:**RSI 超卖``**价格:**T0 触发价附近 (0~-3%)                 | **【左侧吸筹】**``分批买入，止损设在前期绝对低点。反弹目标设为60%分位，以时间换空间。       |
| **主升浪中继 (0.4~0.7)**``MA13多头，BBI向上  | 触及下轨              | **价格:**必须砸出深坑 (例如跌入**-8% ~ -12%**区间)``**形态:**长下影线或 MACD 拒绝死叉 | **【右侧狙击】**``重仓介入。因为主升浪洗盘极深，必须等急跌。吃 80% 分位反弹利润后迅速止盈。 |
| **主升浪中继 (0.4~0.7)**                            | 触及下轨              | **价格:**T1~T10 一直高位横盘，**未跌入**-8% 预定回调区                                       | **【放弃操作】**``洗盘不充分，强行上车容易吃高位套牢。T+10 后系统重置为 WAITING。           |
| **高位区 (Pos > 0.8)**``涨幅过大             | 触及下轨              | 任何形态                                                                                           | **【强制熔断】**``忽略信号，严禁买入（破位风险极高）。                                      |

### 第三阶段：代码落地 —— 状态机回测框架

要实现这种“跨周期”的逻辑，传统的 Pandas 向量化回测（直接 `df['signal'] = 1`）是做不到的，因为它无法处理“T0触发信号后，挂单等待T3跌到目标价才成交”的**路径依赖**问题。

我们需要在脚本中引入状态机（State Machine）循环结构进行摸底：

**Python**

```
import pandas as pd
import numpy as np

# 假设 df 已经包含了基础指标：Golden_Trend, MA13, MACD, Position_Ratio 等

def run_state_machine_backtest(df):
    # 定义系统状态
    STATE_WAITING = 0
    STATE_OBSERVING = 1
    STATE_HOLDING = 2
  
    current_state = STATE_WAITING
  
    # 交易记录
    trades = []
    current_trade = {}
  
    # 观察期倒计时
    observe_countdown = 0 
  
    for i in range(120, len(df)):
        row = df.iloc[i]
      
        # ---------------------------------------------------------
        # 状态 0: 寻找 T0 触发点 (评估周期 -> 信号发生)
        # ---------------------------------------------------------
        if current_state == STATE_WAITING:
            # 标记：触及金钻趋势下轨
            if row['low'] <= row['Golden_Trend']:
              
                # 评估宏观位置标记
                if row['Position_Ratio'] < 0.3: # 深渊底部
                    current_state = STATE_OBSERVING
                    observe_countdown = 10 # 给予 10 天的观察期
                    # 底部入场锚定：不需要深调，触发价附近即可
                    target_entry_price = row['Golden_Trend'] * 0.98 
                    trade_type = 'Bottom_Catch'
                  
                elif 0.3 <= row['Position_Ratio'] <= 0.7: # 主升浪
                    current_state = STATE_OBSERVING
                    observe_countdown = 10
                    # 主升浪入场锚定：洗盘深，锚定 -10% 的回调网格 (根据您的v4.2数据反推)
                    target_entry_price = row['close'] * 0.90 
                    trade_type = 'Main_Wave_Dip'
                  
                # 如果 Position_Ratio > 0.7 (高位)，则状态不变，忽略信号
      
        # ---------------------------------------------------------
        # 状态 1: 观察与入场狙击 (操作观察周期)
        # ---------------------------------------------------------
        elif current_state == STATE_OBSERVING:
            observe_countdown -= 1
          
            # 价格跌入我们锚定的目标价，且满足确认标记（如 MA13 支撑，或缩量）
            if row['low'] <= target_entry_price:
                # 此时完成入场！
                current_state = STATE_HOLDING
                entry_price = target_entry_price
              
                # 根据交易类型锚定出场动作 (利用之前回测的 80% 分位反弹数据)
                if trade_type == 'Bottom_Catch':
                    take_profit = entry_price * 1.15 # 假设底部反弹目标 15%
                    stop_loss = entry_price * 0.95   # 底部防守 5%
                else: # Main_Wave_Dip
                    take_profit = entry_price * 1.25 # 主升浪急跌后反弹猛，目标 25%
                    stop_loss = entry_price * 0.92   # 跌破主升趋势线止损
              
                current_trade = {
                    'entry_date': row.name,
                    'entry_price': entry_price,
                    'type': trade_type
                }
          
            # 如果过了观察期都没跌到目标价，或者价格直接飞了，取消观察
            elif observe_countdown <= 0:
                current_state = STATE_WAITING
              
        # ---------------------------------------------------------
        # 状态 2: 持仓管理与退出 (持仓评估周期)
        # ---------------------------------------------------------
        elif current_state == STATE_HOLDING:
            # 检查止损标记
            if row['low'] <= stop_loss:
                current_trade['exit_date'] = row.name
                current_trade['exit_price'] = stop_loss
                current_trade['pnl'] = (stop_loss - entry_price) / entry_price
                trades.append(current_trade)
                current_state = STATE_WAITING
              
            # 检查止盈标记
            elif row['high'] >= take_profit:
                current_trade['exit_date'] = row.name
                current_trade['exit_price'] = take_profit
                current_trade['pnl'] = (take_profit - entry_price) / entry_price
                trades.append(current_trade)
                current_state = STATE_WAITING
              
    return pd.DataFrame(trades)
```

### 摸底核心总结

通过这种方式，我们不再是去“预测”金钻公式是否有效，而是利用它的高敏度去 **框定一个波动事件** 。

公式发黄柱 =  **鱼塘里有动静（事件发生）** 。

前期位置标记 =  **确认是在深海还是浅滩（定性）** 。

锚定触发价与倒计时 =  **根据深海/浅滩的特性，决定网格撒在多深的地方（操作执行）** 。

这种结合了微观切片与宏观周期的全量摸底，才能将“波动价值”真正转化为实盘可执行的收益。
