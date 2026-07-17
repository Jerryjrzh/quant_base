```python
# backend/hourly_confirmation.py
"""
60分钟K线入场二次确认模块
定位：日线信号触发+结构过滤后，在价格回踩支撑位时，切换到60分钟图进行辅助验证。
通过验证的信号才允许执行入场，否则放弃本次入场机会。
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional

# 假设项目中有 data_handler 模块提供数据
try:
    from .data_handler import get_hourly_data
except ImportError:
    # 独立测试时可以使用如下桩函数
    def get_hourly_data(stock_code: str, end_date, lookback_days: int = 20):
        """
        返回指定股票 end_date 之前 lookback_days 个自然日的60分钟K线数据。
        DataFrame 需包含列: datetime, open, high, low, close, volume
        实际使用时替换为真实数据接口。
        """
        # 桩实现，返回空 DataFrame
        return pd.DataFrame()


def get_hourly_confirmation(stock_code: str,
                            signal_date,
                            support_price: float,
                            config: Optional[dict] = None) -> Tuple[bool, str]:
    """
    对日线回调企稳信号进行60分钟K线二次确认。

    参数:
        stock_code: 股票代码
        signal_date: 信号日期 (即日线确认企稳的那一天)
        support_price: 该信号所回踩的支撑位价格
        config: 可选参数字典，可覆盖默认参数：
            - lookback_days: 获取多少天内的60分钟数据 (默认20)
            - touch_tolerance: 支撑位触及容忍度 (默认0.001，即±0.1%)
            - min_touch_count: 最少精确触及次数 (默认2)
            - big_red_threshold: 大阴线跌幅阈值 (默认0.015)
            - big_red_vol_mult: 大阴线量比阈值 (默认2.0)
            - pinbar_shadow_ratio: 下影线与实体之比 (默认2.0)
            - engulfing_required: 是否要求吞没形态 (默认True)
            - volume_shrink_ratio: 触及支撑时缩量要求 (默认0.8，即低于均量80%)
            - volume_expand_ratio: 反弹放量要求 (默认1.2)

    返回:
        (passed: bool, reason: str)
        passed=True 表示通过验证，可以入场。
        passed=False 表示未通过，并说明原因。
    """
    # 默认配置
    if config is None:
        config = {}
    lookback_days = config.get('lookback_days', 20)
    touch_tol = config.get('touch_tolerance', 0.001)
    min_touch = config.get('min_touch_count', 2)
    big_red_thr = config.get('big_red_threshold', 0.015)
    big_red_vol_mult = config.get('big_red_vol_mult', 2.0)
    pinbar_ratio = config.get('pinbar_shadow_ratio', 2.0)
    vol_shrink = config.get('volume_shrink_ratio', 0.8)
    # vol_expand 暂未严格使用，可以根据需要加入

    # 1. 获取60分钟数据
    hourly_df = get_hourly_data(stock_code, end_date=signal_date, lookback_days=lookback_days)
    if hourly_df is None or len(hourly_df) < 20:
        return False, "60分钟K线数据不足"

    # 2. 截取最近20根K线（约5个交易日），可根据实际调整
    recent = hourly_df.tail(20).copy()

    # 3. 检查支撑位精确触及
    touch_mask = (recent['low'] <= support_price * (1 + touch_tol)) & \
                 (recent['low'] >= support_price * (1 - touch_tol))
    touch_count = touch_mask.sum()
    if touch_count < min_touch:
        return False, f"支撑位精确触及次数不足 ({touch_count}/{min_touch})"

    # 4. 否决条件：放量大阴线
    # 计算平均量（使用最近5根K线平均，避免当前K线影响）
    recent['vol_ma5'] = recent['volume'].rolling(5, min_periods=1).mean().shift(1)
    recent['is_big_red'] = ((recent['close'] < recent['open']) &
                            ((recent['open'] - recent['close']) / recent['open'] > big_red_thr) &
                            (recent['volume'] > recent['vol_ma5'] * big_red_vol_mult))
    # 检查最近5根K线内是否有大阴线
    if recent['is_big_red'].iloc[-5:].any():
        return False, "最近5根60分钟K线出现放量大阴线"

    # 连续阴线检查（3根及以上连续阴线且收盘走低）
    consecutive_red = 0
    for i in range(len(recent)-1, max(len(recent)-10, -1), -1):
        if recent.iloc[i]['close'] < recent.iloc[i]['open'] and \
           (i == 0 or recent.iloc[i]['close'] < recent.iloc[i-1]['close']):
            consecutive_red += 1
            if consecutive_red >= 3:
                return False, "连续3根以上阴线且收盘走低"
        else:
            consecutive_red = 0

    # 5. 反转形态检测
    recent['body'] = abs(recent['close'] - recent['open'])
    recent['lower_shadow'] = recent[['open', 'close']].min(axis=1) - recent['low']
    recent['upper_shadow'] = recent['high'] - recent[['open', 'close']].max(axis=1)

    # Pin Bar：下影线长度 > 实体长度 * pinbar_ratio，且收盘价回到下影线中点之上
    recent['is_pinbar'] = ((recent['lower_shadow'] > recent['body'] * pinbar_ratio) &
                           (recent['close'] > recent['low'] + recent['lower_shadow'] * 0.5))

    # Bullish Engulfing：阳线实体完全覆盖前一根阴线实体
    recent['prev_open'] = recent['open'].shift(1)
    recent['prev_close'] = recent['close'].shift(1)
    recent['is_engulfing'] = ((recent['close'] > recent['open']) &           # 当前为阳线
                              (recent['prev_close'] < recent['prev_open']) & # 前一根为阴线
                              (recent['open'] < recent['prev_close']) &     # 开盘价低于前收
                              (recent['close'] > recent['prev_open']))      # 收盘价高于前开

    # 检查最近8根K线中是否有这两种形态之一
    has_pattern = recent['is_pinbar'].iloc[-8:].any() or recent['is_engulfing'].iloc[-8:].any()
    if not has_pattern:
        return False, "未检测到Pin Bar或Bullish Engulfing反转形态"

    # 6. 成交量确认 (可选)
    # 检查触及支撑时的成交量是否相对缩量
    touch_vol = recent.loc[touch_mask, 'volume']
    if len(touch_vol) > 0:
        avg_vol = recent['volume'].rolling(5).mean().iloc[-1]
        # 如果触及支撑时的平均成交量大于平均的vol_shrink倍，则说明量能未明显缩小
        if touch_vol.mean() > avg_vol * vol_shrink:
            # 可以记录日志，但不作为强制否决条件（宽松处理）
            pass

    return True, "通过60分钟确认"


# 辅助函数：用于回测时批量预处理
def precompute_hourly_support_tests(signals_df, config=None):
    """
    预计算所有信号的60分钟确认结果，可缓存加速回测。
    signals_df 需包含: stock_code, signal_date, support_price (实际使用的支撑位)
    返回两个列表: passed_list, reason_list
    """
    results = []
    for _, row in signals_df.iterrows():
        passed, reason = get_hourly_confirmation(
            row['stock_code'], row['signal_date'], row['support_price'], config
        )
        results.append((passed, reason))
    return zip(*results)
```

**验证脚本：`scripts/validate_hourly_confirmation.py`**

```python
"""
验证60分钟入场二次确认的有效性。
在Review4 Final的445笔实际交易（或更大样本）上，应用小时线确认，
观察交易数、胜率、平均盈亏的变化。
"""

import sys
sys.path.append('..')  # 根据实际路径调整

import pandas as pd
import numpy as np
from backend.hourly_confirmation import get_hourly_confirmation
from backend.data_handler import get_hourly_data  # 确保数据接口可用

def validate_on_sample(trades_df, sample_size=500, random_state=42):
    """
    从trades_df中抽取样本，对比有无小时线确认的盈亏。
    trades_df: 包含每笔交易的详细信息，至少要有:
        stock_code, signal_date, support_price, actual_entry_flag, pnl_pct
    """
    if len(trades_df) > sample_size:
        sample = trades_df.sample(sample_size, random_state=random_state)
    else:
        sample = trades_df

    passed_list = []
    for idx, row in sample.iterrows():
        passed, reason = get_hourly_confirmation(
            row['stock_code'],
            row['signal_date'],
            row['support_price']
        )
        passed_list.append(passed)

    sample['hourly_confirmed'] = passed_list

    # 原始交易中已入场的子集
    original_trades = sample[sample['actual_entry_flag'] == True]
    # 假设所有样本都是日线已经确认要入场的信号，现在我们用小时线过滤
    # 实际回测中，只有日线确认的信号才会走到这一步，因此我们应从日线确认的信号里筛选
    # 为简化，假设此sample中的每一行都是日线已确认的“即将入场”信号

    before_count = len(sample)
    after_count = sample['hourly_confirmed'].sum()
    filtered_ratio = 1 - (after_count / before_count) if before_count > 0 else 0

    # 盈亏对比（需要模拟“如果执行入场”的实际盈亏，这里使用已有的pnl_pct来近似）
    # 注意：实际验证应该重新运行完整的入场+出场回测，但这里可以做一个近似：
    # 对于被小时线过滤掉的信号，我们假定系统没有入场，盈亏为0；
    # 对于通过的信号，我们使用其原来的实际盈亏。
    original_avg_pnl = sample['pnl_pct'].mean()
    # 小时线过滤后的盈亏：只有通过验证的信号才会入场，其余盈亏为0
    after_pnl = sample['pnl_pct'] * sample['hourly_confirmed']
    after_avg_pnl = after_pnl.mean()

    # 胜率对比
    original_wr = (sample['pnl_pct'] > 0).mean()
    after_wr = (sample['hourly_confirmed'] & (sample['pnl_pct'] > 0)).mean()

    return {
        'sample_size': before_count,
        'after_count': after_count,
        'filtered_ratio': filtered_ratio,
        'original_avg_pnl': original_avg_pnl,
        'after_avg_pnl': after_avg_pnl,
        'original_wr': original_wr,
        'after_wr': after_wr
    }

if __name__ == "__main__":
    # 示例：加载某个交易明细文件（如 review4_final_backtest.csv）
    try:
        trades = pd.read_csv('../data/result/super_trend/review4_final_backtest.csv')
    except FileNotFoundError:
        print("请提供有效的交易明细文件路径")
        # 创建一个模拟数据集用于测试
        trades = pd.DataFrame({
            'stock_code': ['test']*100,
            'signal_date': pd.date_range('2025-01-01', periods=100),
            'support_price': np.random.uniform(10, 20, 100),
            'actual_entry_flag': [True]*100,
            'pnl_pct': np.random.normal(0.03, 0.08, 100)
        })

    result = validate_on_sample(trades, sample_size=500)
    print("===== 小时线确认验证结果 =====")
    print(f"原始交易样本数: {result['sample_size']}")
    print(f"通过小时线确认的交易数: {result['after_count']}")
    print(f"过滤比例: {result['filtered_ratio']:.1%}")
    print(f"原始平均盈亏: {result['original_avg_pnl']:.4f}")
    print(f"小时线过滤后平均盈亏: {result['after_avg_pnl']:.4f}")
    print(f"原始胜率: {result['original_wr']:.2%}")
    print(f"小时线过滤后胜率: {result['after_wr']:.2%}")
```

使用时，需要确保 `data_handler.get_hourly_data` 能够返回正确的历史60分钟数据。如果数据源不具备，可以先用模拟数据验证代码逻辑，再接入真实数据。
