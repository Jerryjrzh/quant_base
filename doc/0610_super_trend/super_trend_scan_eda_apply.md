下面是针对 `super_trend_scanner_v1.py` 核心扫描逻辑的重构代码片段。重构的重点在于**坚决的拦截机制**与 **清晰的边界划分** ，彻底阻断平庸数据向训练集泄露的路径。

### 1. 新增板块动态阈值分配方法

在类中增加一个辅助方法，直接对标 EDA 报告中的 P95 爆发力数据：

**Python**

```
def _get_effective_min_gain(self, stock_code: str) -> float:
    """
    根据股票所属板块，动态返回 22d MFE 的正样本门槛 (P95)
    """
    code_lower = stock_code.lower()
    if code_lower.startswith(('sh60', 'sz00')):
        return 0.43  # 沪深主板
    elif code_lower.startswith(('sz30', 'sh68')):
        return 0.54  # 创业板、科创板
    elif code_lower.startswith(('bj8', 'bj4', 'bj9')):
        return 1.06  # 北交所
  
    return 0.51  # 默认兜底 (旧版全局中位数)
```

### 2. 核心遍历与评估逻辑重构 (`scan_single_stock` 内部)

在遍历历史 K 线切片的主循环中，强制拉平触发条件和标签打分逻辑：

**Python**

```
# 假设参数已经初始化：
# EVAL_DAYS = 22
# NEG_MAX_FUTURE_GAIN = 0.10
# MAX_DRAWDOWN = -0.25

# 提前获取该股票的动态正样本阈值
board_min_gain = self._get_effective_min_gain(stock_code)

for i in range(len(df) - FUTURE_DAYS):
    row = df.iloc[i]
    t0_price = row['close']
    t0_volume = row['volume']
  
    # --- 第一道铁闸：T0 绝对前置过滤 ---
    # 过滤停牌或死 K 线
    if t0_volume == 0 or pd.isna(t0_price):
        continue
      
    daily_gain = (row['close'] / row['pre_close']) - 1.0
    vol_ratio = row['vol_ratio'] if 'vol_ratio' in row else 1.0
  
    # 异动判定必须与异动扫描器 100% 对齐
    is_price_anomaly = daily_gain >= 0.03
    is_vol_anomaly = vol_ratio >= 1.5
  
    # 只要今天不是明确的异动日，连计算未来收益的资格都没有，直接抛弃！
    if not (is_price_anomaly or is_vol_anomaly):
        continue

    # --- 第二道铁闸：22 天严格评估窗口 ---
    # 注意这里切片长度是 EVAL_DAYS (22)，而不是提取特征用的 FUTURE_DAYS (60)
    eval_window = df.iloc[i + 1 : i + 1 + EVAL_DAYS]
  
    if len(eval_window) < EVAL_DAYS:
        continue  # 临近当前日期，未来数据不足 22 天，跳过
      
    eval_high = eval_window['high'].max()
    eval_low = eval_window['low'].min()
  
    # MFE下限0，MAE上限0，逻辑更纯粹
    mfe = max(0.0, (eval_high / t0_price) - 1.0)
    mae = min(0.0, (eval_low / t0_price) - 1.0)
  
    # --- 第三道铁闸：金字塔法则标签隔离 ---
    label = -1 
  
    # 正样本条件：达到了板块专属的 P95 爆发力，且回撤可控
    if mfe >= board_min_gain and mae >= MAX_DRAWDOWN:
        label = 1
      
    # 负样本条件：诱多假突破，涨幅甚至达不到 P50中位数 (10%)
    elif mfe <= NEG_MAX_FUTURE_GAIN:
        label = 0
      
    # 核心隔离带：MFE 在 10% 到 43%/54% 之间的，全部属于特征模糊的“随波逐流区”
    else:
        continue  # 关键！直接丢弃，不进训练集

    # ==========================================
    # 如果代码能走到这里，说明要么是极品正样本(1)，要么是纯粹的诱多负样本(0)
    # 接下来再执行特征提取（利用 FUTURE_DAYS 等窗口提取技术指标）
    # extract_features(df, i, ...)
    # ==========================================
```

### 为什么这样改能拉升 Precision？

1. **掐断了“运气票”：** 之前的逻辑允许 `daily_gain < 3%` 且没放量的平庸日混入正样本（只要未来 60 天涨了就行）。现在的 `is_price_anomaly or is_vol_anomaly` 把这部分底噪彻底清除。
2. **剔除了“干扰项”：** 在机器学习中，最毒的数据就是处于分类边界的模糊数据（比如涨了 25% 的票，它既有点像主升浪，又像普通反弹）。最后的 `else: continue` 建立了一条无视区（隔离带），这会让 LightGBM 的树在分裂时，面对的特征差异更加鲜明。

建议您先用这个逻辑替换 `super_trend_scanner_v1.py` 的相关部分，跑一个极小范围的测试（比如只扫 50 只股票），看看正样本比例是否如预期降到了 5% 左右。
