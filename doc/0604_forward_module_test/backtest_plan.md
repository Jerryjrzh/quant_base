# 模块闭环回测计划

## Context

上一轮全周期日历回测（3,760 笔，PF=1.81）暴露了三大问题：
1. V4.4 评级体系反向（grade/action/trend 与收益负相关）
2. 科创/北交尾部风险未受控（-20%~-30% 极端亏损）
3. 止损出局的"赢小输大"（39.6% 的止损单 MFE>=3% 却仍亏损）

本计划基于现有 `full_calendar_trades.csv` 数据，按 module_test.md 的 4 个维度执行解耦回测，产出量化证据以指导参数修正。

## 产出物

所有文件输出到 `doc/0604_forward_module_test/`:

| 文件 | 内容 |
|------|------|
| `backtest_plan.md` | 本文件 — 回测计划 |
| `backtest_cases.py` | 回测脚本（纯数据分析，不重新跑全日历） |
| `backtest_report.md` | 回测报告（含结论和改进参数建议） |

## 回测维度与测试用例

### 维度一：打分体系诊断（Test 1-3）

基于 CSV 中的 v44_grade / v44_action / v44_trend / v44_bias_tier / 评估分 字段。

**Test 1: 因子单调性检验 (Factor Monotonicity)**
- 对每个因子（grade/action/trend/bias_tier/评估分），计算分层 IC：
  - 将因子映射为数值（A=4, B=3, C=2, D=1 等）
  - 计算 Spearman 相关系数 vs 收益率
  - IC > 0 表示因子方向正确，IC < 0 表示反向
- 通过标准：所有因子 IC > 0 且 p < 0.05

**Test 2: 分层收益分位数分析**
- 对每个因子按分层（Top/Bottom）计算：
  - 胜率差（Top WR - Bottom WR）
  - 收益差（Top mean - Bottom mean）
- 验证因子是否具备单调递增性

**Test 3: 多因子交叉热力图**
- grade × trend, grade × bias_tier, action × trend 的交叉矩阵
- 识别是否存在"好组合"和"毒组合"

### 维度二：信号纯净度与尾部风险（Test 4-5）

**Test 4: MFE/MAE 潜能分布**
- 按板块（60/688/300/00/920）计算：
  - MFE 均值/中位数/分位数
  - MAE 均值/中位数/分位数
  - MFE/|MAE| 比值（信号信噪比）
  - 实收/MFE 比值（捕获率 = 收益率/MFE）
- 目标：验证选股信号本身的 alpha 纯度

**Test 5: 极端亏损归因与熔断模拟**
- 提取 Top 50 最大亏损交易
- 分析特征分布（板块、grade、trend、MAE、entry_slip）
- 模拟加入板块熔断规则后的效果：
  - 规则 A：688/920 板块 MAE > -10% 的提前止损
  - 规则 B：688/920 板块直接拒绝入场
  - 规则 C：仅允许 688/920 中 selection_verdict='合理' 的交易
- 计算每条规则下：PF 变化、最大单笔亏损、总收益变化

### 维度三：出场机制参数寻优（Test 6-7）

**Test 6: Trailing Stop 灵敏度网格**
- CSV 中每笔交易有 MFE（盘中最高浮盈），可模拟不同 trailing stop 策略：
  - 当前：MFE>=3% 保本+1%, >=5% 保本+3%, >=7% 保本+5%
  - 方案 A：MFE>=2% 保本+1%, >=4% 保本+2%, >=6% 保本+4%
  - 方案 B：MFE>=3% 保本+2%, >=5% 保本+4%, >=7% 保本+5%
  - 方案 C：固定 trailing stop = MFE * 0.6（即回吐 40% 就退出）
- 对每个方案，在止损出局交易上模拟：
  - 如果 trailing stop 触发价 > 实际止损价 → 按 trailing stop 退出
  - 计算新收益率、新胜率、新 PF
- 通过标准：笔均收益从 +0.83% 提升至 +1.2%+

**Test 7: 时间衰减提前退出模拟**
- 对"时间衰减平仓"（205 笔）和"止损出局"中持仓>=2 天的交易：
  - 模拟 T+2 退出（而非 T+3）的效果
  - 模拟 T+2 且 MFE<1% 时提前退出的效果
- 计算均收益变化

### 维度四：组合集成验证（Test 8）

**Test 8: 最优参数组合模拟**
- 将维度 1-3 中表现最佳的参数组合：
  - 板块熔断规则（Test 5 最优）
  - trailing stop 方案（Test 6 最优）
  - 时间衰减方案（Test 7 最优）
- 在全部 3,760 笔上叠加模拟
- 输出：新 PF、新胜率、新月度收益曲线、新最大回撤
- 目标：PF 从 1.81 → 2.2+

## 实现方式

单个 Python 脚本 `backtest_cases.py`，使用 pandas 直接读取 CSV，不依赖回测引擎。
通过 `python3 -c` 或直接 `python backtest_cases.py` 执行。
结果写入 `backtest_report.md`。

## 关键文件

- 数据源: `data/result/Calendar_Backtest/full_calendar_trades.csv`
- V4.4 打分逻辑: `backend/backtester.py:786-1005` (_generate_forward_advice_v4)
- 出场逻辑: `backend/walk_forward_tester_s.py:163-280` (trailing stop + time decay)
- 选股逻辑: `backend/screenergf.py:800-876` (apply_morse_sniper_strategy)

## 验证方式

1. 运行 `python backend/backtest_cases.py` 生成报告
2. 检查报告中每个 Test 的通过/不通过判定
3. 确认 Test 8 组合后 PF > 2.0
