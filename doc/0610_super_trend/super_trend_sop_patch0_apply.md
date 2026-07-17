为了将这三大进阶特征（时序落差、状态计数、小时线展平）真正落地到你的 `Project Supernova`（主升浪挖掘项目）中，我们需要使用 `pandas` 和 `scipy` 编写高效的特征提取代码。

在量化工程中，我们通常会定义一个 **特征提取算子（Feature Extractor）** 。假设你已经定位到了某个疑似的起爆点 `T0`（例如某一天放量突破），你需要把这一天及其之前的历史数据传入该算子。

以下是针对这 3 个方案的模块化 Python 示例代码：

### 核心准备与依赖

**Python**

```
import pandas as pd
import numpy as np
from scipy.stats import linregress

# 假设 df_daily 和 df_60min 已经按照时间升序排列 (时间序列标准格式)
# 并且包含了常规量价指标如: close, low, volume, rsi6, macd, dif, dea, ma30, ma60_vol 等
```

### 方案 1：区间极值与落差（Delta & Range）提取

 **逻辑目标** ：量化 RSI 的“旱地拔葱”斜率、MACD 的“坑深”、以及价格的“触底反弹幅度”。

**Python**

```
def extract_scheme_1_delta_range(df_daily, t0_index, window=15):
    """
    方案1：提取区间极值与落差特征
    """
    # 截取 T-15 到 T0 的日线时间窗
    start_idx = max(0, t0_index - window)
    window_df = df_daily.iloc[start_idx : t0_index + 1]
  
    t0_row = window_df.iloc[-1]
  
    features = {}
  
    # 1. RSI 爆发力 (T0的RSI 减去 过去15天的最低RSI)
    # 量化图中 RSI(6) 从 40 飙升到 80 的陡峭程度
    rsi_min = window_df['rsi6'].min()
    features['rsi_explosion_force'] = t0_row['rsi6'] - rsi_min
  
    # 2. MACD 坑深 (过去15天 MACD 柱子的最低值)
    # 量化洗盘时主力砸盘的极限深度
    features['macd_pit_depth'] = window_df['macd'].min()
  
    # 3. 坑底反弹幅度 (T0 收盘价 相对于 过去15天最低价 的涨幅)
    # 区分是在坑底摩擦，还是已经走出了凌厉的反弹
    lowest_price = window_df['low'].min()
    features['price_rebound_from_pit'] = (t0_row['close'] / lowest_price) - 1.0
  
    return features
```

### 方案 2：持续状态与计数（Duration & Counting）提取

 **逻辑目标** ：量化洗盘的“熬人”程度，包括水下天数、破位天数和地量天数。

**Python**

```
def extract_scheme_2_duration_counting(df_daily, t0_index, window=15):
    """
    方案2：提取持续状态与计数特征
    """
    start_idx = max(0, t0_index - window)
    window_df = df_daily.iloc[start_idx : t0_index + 1]
  
    features = {}
  
    # 1. 水下窒息天数 (DIF 和 DEA 同时小于 0 的天数)
    # 过滤掉那些假洗盘，真正的洗盘一定伴随 MACD 下潜
    underwater_mask = (window_df['dif'] < 0) & (window_df['dea'] < 0)
    features['days_underwater'] = underwater_mask.sum()
  
    # 2. 假破位恐慌天数 (收盘价跌破 MA30 的天数)
    # 识别“老鸭头”和“黄金坑”形态
    fake_breakdown_mask = window_df['close'] < window_df['ma30']
    features['days_below_ma30'] = fake_breakdown_mask.sum()
  
    # 3. 极致地量天数 (单日成交量不足 60日均量 50% 的天数)
    # 量化“百日地量”特征，证明散户已经绝望不再交易，主力控盘度极高
    # 假设 df_daily 中已有 'ma60_vol' 字段
    if 'ma60_vol' in window_df.columns:
        dry_up_mask = window_df['volume'] < (window_df['ma60_vol'] * 0.5)
        features['vol_dryup_count'] = dry_up_mask.sum()
    else:
        # 如果没有均量字段，用过去时间窗的平均量近似代替
        avg_vol = window_df['volume'].mean()
        features['vol_dryup_count'] = (window_df['volume'] < (avg_vol * 0.5)).sum()
      
    return features
```

### 方案 3：60分钟动态展平（Flattening）提取

 **逻辑目标** ：降维打击，把 60 分钟级别的“水下试盘金叉”和“修复斜率”压扁成日线的单列特征。

**Python**

```
def extract_scheme_3_60min_flattening(df_60min, t0_date, lookback_hours=20):
    """
    方案3：降维打击，提取 60 分钟微观特征
    t0_date: 日线 T0 对应的日期字符串或 datetime
    lookback_hours: 回溯的小时K线数量 (20根约等于过去5个交易日)
    """
    # 1. 对齐时间：截取 T0 收盘前的小时线数据
    window_60m = df_60min[df_60min['date'] <= t0_date].tail(lookback_hours)
  
    features = {}
  
    if len(window_60m) < 5:
        # 数据不足时的降级处理
        features['h1_water_cross_count'] = 0
        features['h1_dif_repair_slope'] = 0.0
        return features

    # 2. 小时线水下金叉试盘次数 (The Ignition Count)
    # 条件: DIF 上穿 DEA，且 DIF 处于零轴下方
    dif = window_60m['dif']
    dea = window_60m['dea']
  
    # 使用 shift(1) 寻找交叉点
    cross_up = (dif > dea) & (dif.shift(1) <= dea.shift(1))
    underwater_cross = cross_up & (dif < 0)
  
    features['h1_water_cross_count'] = underwater_cross.sum()
  
    # 3. 小时线 DIF 修复动能 (线性回归斜率)
    # 用最近 10 根 60分钟线的 DIF 斜率，量化“暗流涌动”向上的速度
    recent_10_dif = dif.tail(10).values
    if len(recent_10_dif) == 10:
        # scipy.stats.linregress(x, y) 返回 (slope, intercept, r, p, se)
        slope, _, _, _, _ = linregress(range(10), recent_10_dif)
        features['h1_dif_repair_slope'] = slope
    else:
        features['h1_dif_repair_slope'] = 0.0
      
    return features
```

### 🚀 终极整合：特征组装管道 (Pipeline)

在实际的机器训练脚本中，你会把上面三个函数组装在一起，为机器学习提供一张宽表（Wide Table）：

**Python**

```
def build_supernova_features(df_daily, df_60min, t0_index):
    """
    主调函数：合并所有时序特征，生成最终供 LightGBM 学习的一维特征字典
    """
    t0_date = df_daily.iloc[t0_index]['date']
  
    # 执行三大特征提取方案
    feat_1 = extract_scheme_1_delta_range(df_daily, t0_index, window=15)
    feat_2 = extract_scheme_2_duration_counting(df_daily, t0_index, window=15)
    feat_3 = extract_scheme_3_60min_flattening(df_60min, t0_date, lookback_hours=20)
  
    # 还可以加入当天的基础静态特征
    base_features = {
        't0_gbm_c_score': df_daily.iloc[t0_index].get('gbm_proba', 0), # 抄底模型的原评分
        't0_close': df_daily.iloc[t0_index]['close'],
        't0_vol_ratio': df_daily.iloc[t0_index]['volume'] / (df_daily['volume'].rolling(20).mean().iloc[t0_index] + 1e-5)
    }
  
    # 将字典合并
    final_features = {**base_features, **feat_1, **feat_2, **feat_3}
  
    return final_features

# ==========================================
# 模拟执行测试
# ==========================================
# 假设我们找到了一个起爆点索引是 250 (中船特气的某个 T0)
# features_dict = build_supernova_features(df_daily, df_60min, 250)
# features_df = pd.DataFrame([features_dict]) 
# 这行 DataFrame 就可以直接 `model.predict(features_df)` 或者写入 CSV 作为训练集了！
```

### 代码避坑指南 (Architect's Note)

在运行上述代码前，请特别注意两点：

1. **防止数据泄露（Data Leakage）** ：注意代码中的切片是 `iloc[start_idx : t0_index + 1]`。这保证了模型绝对看不到 `t0_index + 1` 之后的数据。如果这里切错了，机器学习模型在回测时会变成能预知未来的神仙（过拟合），实盘立马爆仓。
2. **处理平移后的 NaN** ：像 `linregress` 和 `.sum()` 如果遇到了刚上市不久的新股，会导致数据不足产生 `NaN`。在实际投入 LightGBM 前，建议加上 `.fillna(0)` 的保护处理。
