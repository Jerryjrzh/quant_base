# 金钻趋势双轨校准: 模块化提取 + 前端集成 实施报告

**日期**: 2026-06-17

## 一、背景

双轨校准（日线 + 小时线）已在 `calibrate_golden_trend.py` 中验证:
- 中位偏差从纯日线 2.33% 降至 **0.12%**（19 倍改善）
- 小时线在 65.3% 的信号中胜出
- 84.7% 的信号偏差 ≤5%

本次工作将 GT 计算从校准脚本中提取为独立模块，并集成到前端图表，实现切换 K 线周期时自动自适应计算并展示双轨。

## 二、架构变更

### 2.1 数据流

```
用户切换周期 → loadChart() → /api/unified_analysis/<stock>?timeframe=60min
     ↓
unified_analysis_service.py
     ├── get_full_data_with_indicators() → data_handler.calculate_all_indicators()
     │     └── golden_trend.calculate_golden_trend(df, adaptive=True)
     │           ├── 自适应 N (ATR/趋势)
     │           ├── 自适应 K (振幅)
     │           ├── 自适应 offset (回撤深度)
     │           └── 计算 EMA_H, EMA_L, GT, channel_ratio
     ├── _resample_to_timeframe() (非日线时重采样)
     ├── _prepare_chart_data()
     │     ├── indicator_cols 增加 gt_upper, gt_lower, gt_mid
     │     └── golden_trend_meta 从 df.attrs 读取
     └── 返回 chart_data + golden_trend_meta
     ↓
frontend/js/app.js → renderEchart()
     ├── GT上轨: 金色虚线 (EMA_H)
     ├── GT下轨: 红色虚线 (Golden Trend 值)
     ├── GT中轨: 淡金色实线 ((EMA_H + EMA_L)/2)
     └── 标题副标题: GT 参数 + 通道比 + 重叠警告
```

### 2.2 自适应参数机制

每个周期的 GT 参数独立计算，基于当前 K 线数据的历史特征:

| 参数 | 计算逻辑 | 日线典型值 | 60min 典型值 |
|------|----------|-----------|-------------|
| N | ATR 越大→N 越大，趋势 R² 越强→N 越小 | 15~25 | 10~20 |
| K | 近 60 根 K 线平均振幅 → K = 0.5 + avg_range × 30 | 0.8~1.5 | 0.5~1.2 |
| offset | 60 根最大回撤 >25% → 0.95, >15% → 0.98 | 0.95~1.0 | 0.98~1.0 |
| double_smooth | 自适应模式下固定 True | True | True |

## 三、变更文件清单

### 新建

| 文件 | 行数 | 说明 |
|------|------|------|
| `backend/golden_trend.py` | 155 | GT 计算模块，遵循 indicators.py 的 dataclass config 模式 |

### 修改

| 文件 | 改动说明 |
|------|----------|
| `backend/calibrate_golden_trend.py` | 删除 5 个重复函数定义，改为 `from golden_trend import` |
| `backend/path_analysis_v5.py` | 导入源改为 `from golden_trend import` |
| `backend/data_handler.py` | `calculate_all_indicators()` 增加 GT 计算 + df.attrs 传递 meta |
| `backend/app.py` | `get_stock_analysis()` 增加 GT 计算 + response 增加 golden_trend_meta |
| `backend/unified_analysis_service.py` | `_prepare_chart_data()` 增加 GT 列/NaN 填充/meta 传递；修复 `get_deep_analysis` 参数顺序 bug |
| `frontend/js/app.js` | 提取 GT 数据 + 3 条线系列 + 标题参数展示 + 重叠警告 |

## 四、核心代码说明

### 4.1 `golden_trend.py` 模块 API

```python
# 配置类
@dataclass
class GoldenTrendConfig(IndicatorConfig):
    n: int = 25
    double_smooth: bool = True
    k: float = 1.0
    offset_coef: float = 1.0
    adaptive: bool = True

# 统一入口
def calculate_golden_trend(df, config=None, stock_code=None):
    """返回 (gt_series, ema_h, ema_l, meta_dict)"""

# 底层函数 (供校准脚本使用)
def calc_golden_trend(high, low, n, double_smooth, k, offset_coef) -> pd.Series
def calc_ema_rails(high, low, n, double_smooth) -> (ema_h, ema_l)
def calc_adaptive_n(df) -> int
def calc_adaptive_k(df) -> float
def calc_adaptive_offset(df) -> float
def calc_channel_ratio(high, low, n, double_smooth) -> float
```

### 4.2 前端渲染

```javascript
// 三条 GT 线系列
GT上轨: 金色虚线 (#FFD700, width=2, dashed) → EMA_H
GT下轨: 红色虚线 (#FF4500, width=2, dashed) → Golden Trend 值
GT中轨: 淡金实线 (#FFD700, width=1, opacity=0.3) → (EMA_H + EMA_L)/2

// 标题副标题
GT(N=15, k=1.2, off=0.98, 双平滑) 通道3.5%
// 双轨重叠时变红:
GT(N=25, k=0.5, off=1.0) 通道1.2% ⚠双轨重叠
```

### 4.3 Bug 修复

**`get_deep_analysis` 参数顺序 bug**:
```python
# 修复前 (df 被传到 analysis_date 位置)
backtester.get_deep_analysis(stock_code, df)

# 修复后 (使用关键字参数)
backtester.get_deep_analysis(stock_code, df=df)
```

此 bug 在 Python 3.14 中因 DataFrame 真值判断更严格而暴露。

## 五、验证清单

| 步骤 | 预期结果 |
|------|----------|
| 启动 `python3 backend/app.py` | 无 import 错误 |
| 选择股票，日线模式 | 主图出现金色虚线(上轨)/红色虚线(下轨)，标题显示 GT 参数 |
| 切换到 60min | GT 参数重新自适应(通常 N 更小)，线条更新 |
| 切换到周线 | GT 正常工作(数据较少时参数合理) |
| 双轨重叠个股 | 标题变红显示 ⚠双轨重叠 |
| `python3 backend/calibrate_golden_trend.py` | 校准脚本正常运行(导入新模块) |
| `python3 backend/path_analysis_v5.py` | v5 回测正常运行(导入新模块) |

## 六、后续可选优化

1. **双时间框架 GT 对比**: 主图显示当前周期 GT，小窗叠加另一周期 GT 作为参考
2. **GT 参数持久化**: 将校准后的最优参数存入 CSV/DB，前端直接加载而非实时自适应
3. **GT 区域填充**: 上下轨之间用半透明色块填充，直观展示通道范围
4. **Tooltip 增强**: 鼠标悬停时显示当前 K 线的 GT 上轨/下轨/通道宽度具体数值
