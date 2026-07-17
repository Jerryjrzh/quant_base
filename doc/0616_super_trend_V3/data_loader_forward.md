我看了一遍，你这里的确存在一个比较严重的问题：

**日线复权了，分钟线完全没复权。**

而你的 v5 方案里面：

```python
T-120 Position_Ratio
BBI
MA13
ATR20
Golden Trend
```

很多都是从：

```python
_load_daily_via_60m()
fetch_hourly_kline()
get_min_data()
```

出来的小时线计算。

如果小时线未复权：

```text
除权前 100
除权后 50

小时线:
100 -> 50

直接出现50%断崖

MA全部失真
ATR暴涨
BBI失真
Position_Ratio失真
```

结果：

```text
Zone Tag错误
Trend Tag错误
ATR错误
```

后面统计全部污染。

---

# 第一种方案（推荐）

不要对5分钟线单独复权。

而是：

```text
日线生成复权因子

↓

映射到分钟线

↓

分钟线统一乘因子
```

这是机构标准做法。

---

# 增加函数

```python
def _apply_minute_adjustment(
    df_min: pd.DataFrame,
    stock_code: str,
    adj_type: str
) -> pd.DataFrame:
```

思路：

```python
获取原始日线

↓

获取复权日线

↓

计算每日因子

factor =
adj_close/raw_close

↓

映射到分钟线

↓

OHLC全部乘factor
```

---

# 示例实现

```python
def _apply_minute_adjustment(
        df_min: pd.DataFrame,
        stock_code: str,
        adj_type: str):

    if df_min is None or df_min.empty:
        return df_min

    try:
        _, daily_file, _ = _build_paths(stock_code)

        raw_daily = get_daily_data(
            daily_file,
            stock_code
        )

        if raw_daily is None:
            return df_min

        adj_daily = _apply_adjustment(
            raw_daily.copy(),
            stock_code,
            adj_type
        )

        factor_df = pd.DataFrame({
            'factor':
            adj_daily['close']
            /
            raw_daily['close']
        })

        factor_df.index = pd.to_datetime(
            factor_df.index
        ).normalize()

        df = df_min.copy()

        df['trade_date'] = (
            pd.to_datetime(df.index)
            .normalize()
        )

        df = df.merge(
            factor_df,
            left_on='trade_date',
            right_index=True,
            how='left'
        )

        df['factor'] = (
            df['factor']
            .ffill()
            .fillna(1.0)
        )

        for col in [
            'open',
            'high',
            'low',
            'close'
        ]:
            if col in df.columns:
                df[col] *= df['factor']

        df.drop(
            columns=['trade_date', 'factor'],
            inplace=True
        )

        return df

    except Exception as e:
        print(
            f"[data_loader] 分钟线复权失败 "
            f"{stock_code}: {e}"
        )
        return df_min
```

---

# 第二步修改 get_multi_timeframe_data

原来：

```python
df_5min = get_5min_data(min5_file)
```

改：

```python
df_5min = get_5min_data(min5_file)

if adjustment != 'none':
    df_5min = _apply_minute_adjustment(
        df_5min,
        stock_code,
        adjustment
    )
```

即：

```python
# 5分钟线
if os.path.exists(min5_file):
    try:
        df_5min = get_5min_data(min5_file)

        if (
            df_5min is not None
            and not df_5min.empty
        ):

            if adjustment != 'none':
                df_5min = _apply_minute_adjustment(
                    df_5min,
                    stock_code,
                    adjustment
                )

            result['min5_data'] = df_5min
            result['data_status']['min5_available'] = True

    except Exception as e:
        ...
```

---

# 第三步修改 fetch_hourly_kline

你现在：

```python
data = get_multi_timeframe_data(
    stock_code,
    base_path
)
```

实际上默认：

```python
adjustment='none'
```

所以即使前面修复也不会生效。

改成：

```python
def fetch_hourly_kline(
    stock_code,
    start_date=None,
    end_date=None,
    base_path=None,
    adjustment='forward'
):
```

然后：

```python
data = get_multi_timeframe_data(
    stock_code,
    base_path,
    adjustment=adjustment
)
```

---

# 第四步修改 get_min_data

改：

```python
def get_min_data(
    stock_code,
    period='60m',
    base_path=None,
    adjustment='forward'
):
```

然后：

```python
data = get_multi_timeframe_data(
    stock_code,
    base_path,
    adjustment=adjustment
)
```

---

# 更大的问题

我发现一个更危险的地方：

```python
get_daily_data_in_range()
```

这里明显已经坏了：

```python
day_file, _ = _build_paths(stock_code, base_path)
```

但 `_build_paths()` 返回：

```python
market,
daily,
min5
```

三个值。

这里会直接：

```python
ValueError:
too many values to unpack
```

应该改：

```python
_, day_file, _ = _build_paths(
    stock_code,
    base_path
)
```

---

而且这里：

```python
return get_daily_data(
    file_path_or_code=day_file,
    start_date=start_date,
    end_date=end_date,
    adjustment=adjustment,
    stock_code=stock_code
)
```

你的 `get_daily_data()` 定义是：

```python
def get_daily_data(
    file_path,
    stock_code=None
)
```

根本没有：

```python
file_path_or_code
start_date
end_date
adjustment
```

参数。

说明：

```python
get_daily_data_in_range()
```

是从旧版本拷过来的。

目前实际上不可用。

---

我的结论：

对于你的 v5 项目，优先级应该是：

```text
P0
修复分钟线复权
★★★★★★★★★★

P0
修复 get_daily_data_in_range
★★★★★★★★★★

P1
检查 _load_daily_via_60m
是否已经使用复权小时线
★★★★★★★★☆

P2
再做 Position Zone
★★★★★★★☆☆☆
```

因为如果小时线未复权，那么你后面做的：

```python
Position_Ratio
BBI
MA13
ATR20
Golden Trend
```

全部都会被历史除权事件污染，最终导致整个 Position×DD 统计失真。
