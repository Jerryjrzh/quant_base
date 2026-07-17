 ▪ 现在我有了完整的代码图景，给你详细梳理。

   ---

   一、Disabled 关闭的原因

   enabled 在 step2_gt_param_inference() 中由 4 个条件决定（line 215-220）：
    enabled = (
        zone != 'high_trap'       # 条件1: 不是高位陷阱区
        and not deep_broken       # 条件2: DD 不是 >20%
        and len(sub) >= 5         # 条件3: 该格子历史样本 >= 5
        and rb_gt5 > 0.3          # 条件4: 历史反弹>5%的比例 > 30%
    )
   从参数矩阵看被关闭的格子：
   ┌─────────────────────┬──────────────────┬────────────────────────────────────────┐
   │ 关闭格子            │ 关闭原因         │ 逻辑                                   │
   ├─────────────────────┼──────────────────┼────────────────────────────────────────┤
   │ abyss_bottom >20%   │ DD>20%           │ 深度回撤，趋势可能继续下行，抄底风险大 │
   │ bottom_start >20%   │ DD>20%           │ 同上                                   │
   │ main_wave >20%      │ DD>20%           │ 同上                                   │
   │ high_zone >20%      │ DD>20%           │ 同上                                   │
   │ high_trap (全部6格) │ zone=high_trap   │ 高位陷阱区，本身就不应入场             │
   │ bottom_start 3~5%   │ 样本数<5 (仅2个) │ 统计意义不足                           │
   └─────────────────────┴──────────────────┴────────────────────────────────────────┘
   这6个格子关闭后影响了多少信号？
   - high_trap 全部6格 — 约占全部信号的很大一部分
   - 所有 >20% DD tier — 深度回撤信号被全面屏蔽
   - 这是 2877/4403 = 65.3% 信号被 disabled 的原因

   这个设计的意义： 参数矩阵是基于历史统计推断的。如果某个 zone+DD
   组合历史上反弹概率很低（<30%），或回撤太深（>20%），说明该类信号不适合用 GT
   通道策略交易，直接关闭。

   ---

   二、完整操作流程梳理

   阶段 0：数据准备（由 path_analysis_v5.py 预先生成）
    60m K线数据 → 聚合为日线 → 标注每个信号日的:
      - zone_tag (abyss_bottom / bottom_start / main_wave / high_zone / high_trap)
      - max_drawdown (信号前最大回撤)
      - rebound_pct (信号后反弹幅度)
      - golden_trend_t0 (T0 时刻的 GT 值)
      - position_ratio, atr20_pct, trend_tag...
   输出两个 CSV：signal_tags_v5.csv + path_analysis_v5.csv

   阶段 1：main() 加载数据
    加载 signal_tags (4423笔) + path_analysis (4423行)
    → 合并为 merged_df
    → 过滤 unknown zone → 4403 有效信号
   阶段 2：参数矩阵推断 (step2_gt_param_inference)
    对 5个zone × 6个DD tier = 30个格子，逐一计算:
      ├── n: 自适应EMA周期 (基于历史ATR/趋势/回撤)
      ├── entry_buffer: 0.03 (入场缓冲)
      ├── sl_buffer: 0.03 (止损缓冲)
      ├── tp_mult: zone映射 (abyss=3.0, bottom=2.5, main=2.0, high=1.5)
      ├── gt_ratio: GT/收盘价 中位数
      └── enabled: 四条件过滤
     
    输出: cross_tab_params_v5_gt.csv (30格)
   阶段 3：逐信号回测 (step3_gt_backtest)

   每个信号走以下决策树：
    信号 i (stock, t0_date, zone_tag, dd_tier)
    │
    ├─ ① 参数查找
    │   查找 param_lookup[(zone_tag, dd_tier)]
    │   找不到 → 降级查找同 zone 的任意 enabled 参数
    │   还找不到 → 使用 fallback_param
    │
    ├─ ② 开关检查: param.enabled?
    │   ├─ False → 加载前瞻日线, 计算 fwd_low/high 供分析
    │   │         → status='disabled', 跳过
    │   │
    │   └─ True ↓
    │
    ├─ ③ 冷却期检查: 同股上次入场 < 5天?
    │   ├─ Yes → status='cooldown', 跳过
    │   │
    │   └─ No ↓
    │
    ├─ ④ 加载历史数据
    │   ├── daily_pre: T0 前 ~300天 日线 (优先60m聚合, 不够则 fallback)
    │   └── daily_fwd: T0 后 ~45天 日线 (聚合为 FUTURE_DAYS=22 交易日)
    │
    ├─ ⑤ GT 计算 (_compute_gt_on_combined)
    │   ├── 合并 [daily_pre + daily_fwd] 为 combined
    │   ├── 自适应参数 (基于 daily_pre 冻结):
    │   │   ├── n = calc_adaptive_n(pre)   ← EMA 周期
    │   │   ├── k = calc_adaptive_k(pre)   ← 通道宽度倍数
    │   │   └── offset = calc_adaptive_offset(pre) ← 偏移系数
    │   ├── 在 combined 上计算:
    │   │   ├── EMA_H = double_smooth(high, n)  ← 上轨
    │   │   ├── EMA_L = double_smooth(low, n)   ← 下轨
    │   │   └── GT = (EMA_L - (EMA_H - EMA_L) * k) * offset ← 金钻趋势线
    │   └── 提取:
    │       ├── gt_t0: T0 时刻 GT 值 (入场目标价)
    │       ├── fwd_gt: T+1~T+22 的 GT 序列 (随新K线演化)
    │       └── fwd_ema_h: T+1~T+22 的上轨序列
    │
    ├─ ⑥ 逐日入场扫描 (T+0 ~ T+21)
    │   for day_i in range(22):
    │   │
    │   ├─ 入场条件: day_low <= fwd_gt[day_i] × (1 + 0.03)
    │   │   含义: 价格回撤到 GT 下轨附近 (3%缓冲)
    │   │
    │   ├─ 条件不满足 → continue (观察下一天)
    │   │
    │   ├─ 条件满足 → V3 60m 双轨确认:
    │   │   ├── 加载入场日当天 60m K线
    │   │   ├── 计算 EMA_L (double_smooth, span=n)
    │   │   ├── EMA_L[-1] > EMA_L[-2]? (下轨斜率转正=拐头向上)
    │   │   │   ├─ No → continue (小时级别仍在下跌, 跳过)
    │   │   │   └─ Yes ↓
    │   │
    │   ├─ 确认入场:
    │   │   ├── entry_price = day_close (入场日收盘价)
    │   │   ├── gt_at_entry = fwd_gt[day_i] (入场时 GT)
    │   │   ├── channel = ema_h - gt (入场时通道宽度)
    │   │   │
    │   │   ├── 止损价: sl = min(entry, gt_at_entry) × (1 - 0.03)
    │   │   │   └─ 取 entry 和 GT 的较低值, 再下浮 3%
    │   │   │
    │   │   └── 止盈价: channel_pct = min(channel/entry, 10%)
    │   │                  tp = entry × (1 + channel_pct × tp_mult)
    │   │       └─ 通道宽度占入场价比例, 封顶10%, 乘以 zone 倍数
    │   │
    │   └─ 入场日即刻检查:
    │       ├── day_high >= tp → 当日止盈 (tp)
    │       ├── day_low <= sl → 当日止损 (sl)
    │       └── 均未触发 → 进入持仓状态
    │
    ├─ ⑦ 持仓期逐日监控 (entry_day+1 ~ T+21)
    │   for day_i in range(entry_day+1, 22):
    │   │
    │   ├── day_high >= tp → 止盈退出 (tp)
    │   │   pnl = tp / entry - 1
    │   │
    │   ├── day_low <= sl → 止损退出 (sl)
    │   │   pnl = sl / entry - 1
    │   │
    │   └── 均未触发 → 继续持有
    │
    ├─ ⑧ 到期处理 (T+21 仍在持有)
    │   pnl = last_close / entry - 1
    │   status = 'expire'
    │
    ├─ ⑨ 未触发入场 (22天内价格从未触及 GT)
    │   status = 'observe_expire'
    │
    └─ ⑩ 入场后更新冷却期
        if status == 'simulated':
            last_entry[stock] = t0_date
   阶段 4：对比报告
    加载 v5 基线回测 → 与 v5_gt 逐维度对比:
      一、整体对比 (入场率/胜率/PF/盈亏)
      二、按 Zone 对比
      三、动态入场分析 (入场日分布/gap/通道宽度)
      四、止盈/止损/到期分布
      五、V3 过滤统计 (disabled/cooldown/no_entry 分布)
      六、按回调深度对比
      七、典型差异案例
      八、结论与建议
   ---

   三、信号漏斗总结
    4403 总信号
    ├── 2877 disabled (65.3%) — 参数矩阵关闭 (high_trap / DD>20% / 样本不足)
    ├──   29 cooldown  (0.7%) — 同股5天内已入场
    ├── 1419 进入回测引擎
    │   ├──   78 simulated    (1.8%) — 成交
    │   │     ├── 12 tp       (15.4% of 成交)
    │   │     ├── 52 sl       (66.7%)
    │   │     └── 14 expire   (17.9%)
    │   └── 1341 observe_expire / no_forward_data 等 — 未触发入场
   78/4403 = 1.77% 的入场率，核心瓶颈是 disabled 关了 65% 的信号。
   这是参数矩阵的保守策略：high_trap 和深回撤信号不参与交易。如果需要增加交易量，可以放宽 enabled
   条件（比如允许 >20% DD tier，或降低 rb_gt5 阈值从 0.3 到 0.2）。

