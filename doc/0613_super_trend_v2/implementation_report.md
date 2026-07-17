# 结构化回测系统实施报告

**实施日期**: 2026-06-13
**基于文档**: `sys_apply_tasks.md`, `sys_apply_steps.md`
**目标**: 补齐系统缺失的"市场结构感知"层，实现信号触发 → 结构过滤 → 等待入场 → 基于结构的出场和仓位管理闭环

---

## 一、新增模块总览

| 模块 | 文件路径 | 功能 |
|------|----------|------|
| 市场结构分析 | `backend/market_structure.py` | Swing High/Low 检测、支撑/阻力位计算、Volume Profile POC、趋势方向识别 |
| 结构化入场 | `backend/structure_entry.py` | 结构过滤器、回调入场、突破确认入场、入场状态机 |
| 结构化出场与仓位 | `backend/structure_exit.py` | 结构止损、分批止盈、动态移动止损、风险仓位计算 |
| 结构化回测引擎 | `backend/structure_backtester.py` | 完整回测流程、与原 backtester 对比分析、结果导出 |
| 集成测试 | `test_structure_backtest.py` | 5 组测试覆盖所有模块 |

---

## 二、各模块核心实现

### 2.1 market_structure.py (市场结构分析)

**核心函数**:

- `detect_swing_points()`: 基于滚动窗口局部极值 + 后续测试次数确认，检测摆动高低点
  - 参数: lookback=5 (左右各看5天), min_tests=1, tolerance=1%, breakthrough=1.5%
  - 输出: `List[SwingPoint]`，每个包含位置、价格、测试次数

- `identify_trend_direction()`: 基于最近2-3个摆动点的 HH/HL/LH/LL 判断趋势
  - 输出: 'UP' | 'DOWN' | 'RANGE'
  - 退化策略: 摆动点不足时使用 MA20/MA60 关系判断

- `calculate_volume_profile_poc()`: 50-bin 成交量分布，找成交量最密集价格
  - 使用典型价格 (H+L+C)/3 分配成交量到价格 bin

- `get_key_levels()`: 聚合所有支撑/阻力源 (摆动点、MA20/MA60、POC)，去重合并，按距离排序

- `analyze_market_structure()`: 一站式分析入口，返回完整的 `MarketStructure` 对象

**数据结构**:
```python
@dataclass
class MarketStructure:
    trend_direction: str        # 'UP' | 'DOWN' | 'RANGE'
    swing_highs: List[SwingPoint]
    swing_lows: List[SwingPoint]
    supports: List[KeyLevel]    # 按距离从近到远排序
    resistances: List[KeyLevel]
    volume_poc: Optional[float]
    current_price: float
    ma20: Optional[float]
    ma60: Optional[float]
    atr: float
    structure_strength: float   # 0-1
```

### 2.2 structure_entry.py (结构化入场)

**结构过滤器** (`structure_filter`):
- 规则 1: 下降趋势中不做多 (可配置)
- 规则 2: 阻力位 <2% 且支撑位 >5% → 盈亏比差，过滤
- 规则 3: 无任何支撑位 → 入场无依据，过滤

**回调入场** (`check_pullback_entry`):
- 检测最低价触及支撑位 ±1%
- 企稳确认: 阳线实体比 >30% 且收盘在支撑上方，或下影线 > 实体 1.5 倍

**突破确认入场** (`check_breakout_entry`):
- 前一天最高价突破阻力位
- 当天回踩到阻力位附近 (原阻力变支撑) 且收盘在阻力上方

**入场状态机** (`run_entry_state_machine`):
- WAITING → 逐日检查回调/突破 → ENTRY_SIGNAL / EXPIRED
- 最大等待 5 天 (可配置)

### 2.3 structure_exit.py (结构化出场)

**止损** (`set_initial_stop`):
- 基于入场依据的支撑位下方 1.0×ATR
- 硬性保护: 不超过入场价的 5%
- 当支撑位在入场价上方时，退化到固定 5% 止损

**分批止盈** (`set_take_profit_levels`):
- 第一目标: 最近阻力位 (默认 10%)
- 第二目标: 次近阻力位 (默认 20%)
- 第一目标触发后减仓 50%，剩余止损上移到成本价

**动态移动止损** (`update_trailing_stop`):
- 基于新的 swing low 上移止损
- 追踪止损: 最高点 - 2×ATR

**仓位计算** (`calculate_position_size`):
- 每笔最大风险 = 总资金 × 0.5%
- 仓位 = 风险金额 / 每股风险
- A股 100 股整数取整

**持仓管理状态机** (`run_position_manager`):
- 逐日检查: 止损 → 第一目标止盈 → 第二目标止盈 → 移动止损 → 到期
- 完整记录每笔分拆交易的盈亏

### 2.4 structure_backtester.py (结构化回测引擎)

**核心流程**:
```
信号列表 → 逐信号:
  1. 分析信号日市场结构
  2. 结构过滤 (不通过则跳过)
  3. 入场状态机 (5天内无机会则过期)
  4. 制定出场计划 (止损+止盈+仓位)
  5. 持仓管理模拟 (逐日)
→ 汇总统计 + 对比基准
```

**对比分析** (`compare_with_baseline`):
- 基准: T+1 开盘买入, 固定止损-8%, 止盈+30%, 持有22天
- 对比指标: 胜率、平均盈亏、过滤效果

---

## 三、集成测试结果

### 3.1 单元测试 (合成数据)

| 测试项 | 结果 | 备注 |
|--------|------|------|
| Swing High/Low 检测 | ✓ 通过 | 检测到 6 个高点、1 个低点 |
| 趋势方向识别 | ✓ 通过 | 正确识别为 RANGE |
| Volume Profile POC | ✓ 通过 | POC=14.11，在价格范围内 |
| 关键价位计算 | ✓ 通过 | 4 个支撑 (含 MA20/MA60/POC)，0 个阻力 |
| 完整结构分析 | ✓ 通过 | 趋势 UP, 强度 0.77 |
| 结构过滤器 | ✓ 通过 | 正确过滤下降趋势和盈亏比差的信号 |
| 入场状态机 | ✓ 通过 | 正确触发 pullback 入场 |
| 止损计算 | ✓ 通过 | 无有效支撑时退化到固定 5% |
| 止盈计算 | ✓ 通过 | 2 个止盈目标，均高于入场价 |
| 仓位计算 | ✓ 通过 | 6400 股，风险 0.50%，100 股整数 |
| 完整交易模拟 | ✓ 通过 | 到期出场，盈亏 +9.70% |

### 3.2 真实股票数据测试

| 股票 | 信号数 | 交易数 | 过滤数 | 过期数 | 胜率 | 平均盈亏 | 基准胜率 | 基准盈亏 | 盈亏改善 | 胜率改善 |
|------|--------|--------|--------|--------|------|----------|----------|----------|----------|----------|
| 贵州茅台 (sh600519) | 8 | 3 | 2 | 3 | 33.3% | +1.76% | 25.0% | +1.27% | +0.49% | +8.3% |
| 五粮液 (sz000858) | 10 | 4 | 3 | 3 | 75.0% | +3.76% | 70.0% | +5.73% | -1.97% | +5.0% |
| 立讯精密 (sz002475) | 10 | 3 | 1 | 6 | 33.3% | -1.99% | 40.0% | -0.12% | -1.87% | -6.7% |
| 中国平安 (sh601318) | 10 | 5 | 3 | 2 | 20.0% | -2.71% | 30.0% | -2.92% | +0.21% | -10.0% |

### 3.3 关键发现

1. **过滤效果**: 所有股票均成功过滤了部分信号 (1-3 个)，被过滤信号主要为下降趋势或盈亏比差的信号
2. **入场分布**: pullback (回调入场) 占主导 (~70%)，breakout (突破入场) 较少
3. **出场分布**: stop_loss 和 breakeven_stop 较多，说明结构化止损有效限制了亏损
4. **贵州茅台**: 结构化回测胜率 (33.3%) 高于基准 (25.0%)，盈亏也有改善
5. **五粮液**: 结构化回测胜率 (75.0%) 高于基准 (70.0%)，但平均盈亏略低 (分批止盈导致)
6. **立讯精密/中国平安**: 在弱势股上结构化回测效果不如预期，说明结构入场更适合趋势明确的股票

---

## 四、实施中的异常与修复

### 4.1 异常 1: f-string 格式化错误

**问题**: `f"{signal.support_used.price:.2f if signal.support_used else 'N/A'}"` 中条件表达式被错误地放入了格式说明符内

**影响**: `structure_entry.py` 的 `find_entry_opportunity` 函数和测试文件中的格式化输出

**修复**: 将条件判断提取到 f-string 外部
```python
# 修复前 (错误)
f"依据支撑 {signal.support_used.price:.2f if signal.support_used else 'N/A'}"

# 修复后
support_str = f"{signal.support_used.price:.2f}" if signal.support_used else "N/A"
f"依据支撑 {support_str}"
```

### 4.2 异常 2: 止损价高于入场价

**问题**: 当 `support_used.price` 高于 `entry_price` 时 (例如 POC 在入场价上方)，止损计算 `support_price - buffer` 得到的止损价高于入场价，导致逻辑错误

**影响**: `structure_exit.py` 的 `set_initial_stop` 函数

**修复**: 增加 `support_used.price < entry_price` 的条件判断，不满足时退化到固定百分比止损
```python
# 修复后
if support_used is not None and support_used.price < entry_price:
    # 基于支撑位设置止损
    ...
else:
    # 退化到固定止损
    stop_price = entry_price * (1 - config.max_stop_loss_pct)
```

### 4.3 异常 3: datetime 导入缺失

**问题**: 测试脚本中使用了 `datetime.now()` 但未导入 `datetime`

**修复**: 添加 `from datetime import datetime`

---

## 五、与现有系统的集成关系

```
现有系统                          新增模块
┌──────────────────┐           ┌─────────────────────┐
│  screenergf.py   │──信号──→  │ structure_backtester │
│  (选股/打分)      │           │                     │
├──────────────────┤           │  ┌─────────────────┐ │
│  backtester.py   │           │  │market_structure  │ │
│  (原始回测)       │           │  │ (结构分析)       │ │
├──────────────────┤           │  ├─────────────────┤ │
│  indicators.py   │──指标──→  │  │structure_entry   │ │
│  (MA/MACD/ATR)   │           │  │ (入场状态机)     │ │
├──────────────────┤           │  ├─────────────────┤ │
│  data_handler.py │──数据──→  │  │structure_exit    │ │
│  (数据加载)       │           │  │ (出场+仓位)      │ │
└──────────────────┘           │  └─────────────────┘ │
                               └─────────────────────┘
```

- **不修改现有模块**: 新增模块完全独立，不修改 `backtester.py`、`indicators.py` 等现有文件
- **可替换集成**: `structure_backtester.py` 中的 `detect_simple_signals` 是占位函数，可直接替换为现有 screener 的信号
- **数据兼容**: 直接使用 `data_handler.get_full_data_with_indicators()` 获取的标准 OHLCV + 指标 DataFrame

---

## 六、后续优化方向

1. **阶段二 - 回测引擎集成**: 将结构化入场/出场逻辑集成到现有 `backtester.py` 的 `run_backtest` 函数中
2. **阶段三 - 模型特征**: 将结构质量转化为模型特征 (如 `entry_proximity_to_support_rank`, `support_level_count`)
3. **参数优化**: 使用历史数据网格搜索最优的 `max_wait_days`, `stop_loss_atr_multiplier`, `tp1_reduce_ratio` 等参数
4. **多股票组合回测**: 实现跨多只股票的组合回测，考虑资金分配和最大持仓数限制
5. **前端展示**: 在 web dashboard 中展示结构化分析结果 (支撑/阻力位、入场/出场标记)
