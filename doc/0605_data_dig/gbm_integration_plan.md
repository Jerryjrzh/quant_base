# GBM 系统集成计划

## 一、集成目标

将 GBM Signal Scorer 集成到现有筛选和回测系统中，实现：
1. **实时筛选**: 在 morse 评分后叠加 GBM 概率过滤
2. **信号增强**: 输出 `gbm_proba` 字段供下游使用
3. **回测验证**: 在 walk_forward_tester 中验证 GBM 过滤效果

---

## 二、当前系统架构

```
用户请求
  ↓
screenergf.py::apply_morse_sniper_strategy()
  ↓ 返回 {score, trigger_price, v44_meta}
  ↓
walk_forward_tester_s.py
  ↓ 使用 score >= 85 过滤
  ↓ 执行回测
  ↓
输出交易信号
```

**问题**: score 98.2% = 95，无区分度

---

## 三、集成后架构

```
用户请求
  ↓
screenergf.py::apply_morse_sniper_strategy()
  ↓ 返回 {score, trigger_price, v44_meta, ma_slope, bias_20}
  ↓
gbm_scorer.py::GBMScorer.score()  ← 新增
  ↓ 返回 gbm_proba (0~1)
  ↓
walk_forward_tester_s.py
  ↓ 使用 gbm_proba >= 0.62 过滤  ← 修改
  ↓ 执行回测
  ↓
输出交易信号 (含 gbm_proba)
```

---

## 四、集成步骤

### Step 1: 修改 screenergf.py — 输出 GBM 所需特征

**文件**: `backend/screenergf.py`  
**位置**: `apply_morse_sniper_strategy()` 返回处 (line 888-894)

**当前代码**:
```python
return {
    'signal': True,
    'score': score,
    'position': stock_position,
    'trigger_price': trigger_buy,
    **v44_meta
}
```

**修改为**:
```python
# 提取 GBM 所需特征
gbm_features = {
    'ma_slope': slope_13,  # MA13 斜率 (已有)
    'bias_20': (close_t - ma13) / ma13,  # MA13 乖离率 (已有)
}

return {
    'signal': True,
    'score': score,
    'position': stock_position,
    'trigger_price': trigger_buy,
    **v44_meta,
    **gbm_features  # 新增
}
```

**验证**: 确保返回 dict 包含 `ma_slope` 和 `bias_20`

---

### Step 2: 修改 walk_forward_tester_s.py — 加载 GBM 并过滤

**文件**: `backend/walk_forward_tester_s.py`  
**位置**: 策略调用后 (line 150-160)

**当前代码**:
```python
if STRATEGY_TO_TEST == 'MORSE_FACTOR_SNIPER':
    from screenergf import apply_morse_sniper_strategy
    res = apply_morse_sniper_strategy(historical_df, df_15m=m15_slice,
                                      stock_code=stock_code_full, end_date=EVAL_DATE)
else:
    res = None

if res is None or not res.get('signal'):
    return None

strategy_score = res.get('score', 65)
```

**修改为**:
```python
if STRATEGY_TO_TEST == 'MORSE_FACTOR_SNIPER':
    from screenergf import apply_morse_sniper_strategy
    res = apply_morse_sniper_strategy(historical_df, df_15m=m15_slice,
                                      stock_code=stock_code_full, end_date=EVAL_DATE)
else:
    res = None

if res is None or not res.get('signal'):
    return None

# ━━━ GBM 过滤 (新增) ━━━
GBM_ENABLED = True
GBM_THRESHOLD = 0.62

if GBM_ENABLED:
    from gbm_scorer import GBMScorer
    
    # 加载模型 (单例)
    if not hasattr(globals(), '_gbm_scorer'):
        globals()['_gbm_scorer'] = GBMScorer()
        globals()['_gbm_scorer'].load('gbm_scorer_v1')
    
    # Scheme C 基础过滤
    ma_slope = res.get('ma_slope', 0)
    board_type = get_board_params(stock_code)['board_type']
    
    if ma_slope > -0.02 or board_type != '20CM':
        logger.debug(f"GBM: {stock_code_full} 未通过 Scheme C 过滤")
        return None
    
    # GBM 打分
    signal_df = pd.DataFrame([{
        'ma_slope': ma_slope,
        'bias_20': res.get('bias_20', 0),
        'score': res.get('score', 95),
        'market_env': res.get('market_env', ''),
        'v44_trend': res.get('v44_trend', ''),
        'v44_bias_tier': res.get('v44_bias_tier', ''),
    }])
    
    gbm_proba = globals()['_gbm_scorer'].score(signal_df)[0]
    res['gbm_proba'] = gbm_proba
    
    if gbm_proba < GBM_THRESHOLD:
        logger.debug(f"GBM: {stock_code_full} proba={gbm_proba:.3f} < {GBM_THRESHOLD}")
        return None
    
    logger.info(f"GBM: {stock_code_full} ✓ proba={gbm_proba:.3f}")
# ━━━ GBM 过滤结束 ━━━

strategy_score = res.get('score', 65)
```

**验证**: 运行回测，检查日志输出 GBM 过滤信息

---

### Step 3: 修改 signal_generator.py — 保存 GBM 概率

**文件**: `backend/signal_generator.py`  
**位置**: `scan_stock_worker()` 信号输出处

**当前代码**:
```python
if result and result.get('score', 0) >= SCORE_THRESHOLD:
    # 提取 forward OHLC
    ...
    signal_row = {
        'signal_date': date_str,
        'stock_code': stock_code,
        'score': result['score'],
        ...
    }
    signals.append(signal_row)
```

**修改为**:
```python
if result and result.get('score', 0) >= SCORE_THRESHOLD:
    # ━━━ GBM 打分 (新增) ━━━
    from gbm_scorer import GBMScorer
    
    # 加载模型 (worker 初始化时加载一次)
    if not hasattr(scan_stock_worker, '_gbm_scorer'):
        scan_stock_worker._gbm_scorer = GBMScorer()
        scan_stock_worker._gbm_scorer.load('gbm_scorer_v1')
    
    # GBM 打分
    signal_df = pd.DataFrame([{
        'ma_slope': result.get('ma_slope', 0),
        'bias_20': result.get('bias_20', 0),
        'score': result['score'],
        'market_env': result.get('market_env', ''),
        'v44_trend': result.get('v44_trend', ''),
        'v44_bias_tier': result.get('v44_bias_tier', ''),
    }])
    gbm_proba = scan_stock_worker._gbm_scorer.score(signal_df)[0]
    # ━━━ GBM 打分结束 ━━━
    
    # 提取 forward OHLC
    ...
    signal_row = {
        'signal_date': date_str,
        'stock_code': stock_code,
        'score': result['score'],
        'gbm_proba': gbm_proba,  # 新增
        ...
    }
    signals.append(signal_row)
```

**验证**: 重新生成 master_signals.csv，检查包含 `gbm_proba` 列

---

### Step 4: 创建集成测试脚本

**文件**: `backend/test_gbm_integration.py` (新建)

**功能**:
- 加载 GBM 模型
- 对 10 个样本股票执行筛选
- 验证 GBM 过滤逻辑
- 输出过滤前后信号数

**代码**:
```python
#!/usr/bin/env python3
"""GBM 集成测试"""

import pandas as pd
from gbm_scorer import GBMScorer

def test_gbm_scorer():
    """测试 GBM 打分器"""
    print("=" * 70)
    print("GBM Scorer 集成测试")
    print("=" * 70)
    
    # 1. 加载模型
    scorer = GBMScorer()
    if not scorer.load('gbm_scorer_v1'):
        print("❌ 模型加载失败")
        return False
    
    print("✅ 模型加载成功")
    print(scorer.summary())
    
    # 2. 加载测试数据
    csv_path = '../data/result/SignalGenerator/scheme_c_signals.csv'
    df = pd.read_csv(csv_path)
    print(f"\n✅ 加载测试数据: {len(df)} 信号")
    
    # 3. GBM 打分
    df['gbm_proba'] = scorer.score(df)
    print(f"✅ GBM 打分完成")
    print(f"   proba 范围: {df['gbm_proba'].min():.3f} ~ {df['gbm_proba'].max():.3f}")
    print(f"   proba 均值: {df['gbm_proba'].mean():.3f}")
    
    # 4. 阈值过滤
    for threshold in [0.50, 0.56, 0.62]:
        filtered = df[df['gbm_proba'] >= threshold]
        print(f"\n阈值 {threshold}:")
        print(f"   信号数: {len(filtered)} ({len(filtered)/len(df)*100:.1f}%)")
        print(f"   日均: {len(filtered)/319:.1f}")
    
    # 5. 保存结果
    output_path = '../data/result/SignalGenerator/scheme_c_with_gbm.csv'
    df.to_csv(output_path, index=False)
    print(f"\n✅ 结果已保存: {output_path}")
    
    return True

if __name__ == '__main__':
    test_gbm_scorer()
```

---

### Step 5: 更新配置文件

**文件**: `backend/config.json` (或环境变量)

**新增配置**:
```json
{
  "gbm": {
    "enabled": true,
    "model_name": "gbm_scorer_v1",
    "threshold": 0.62,
    "scheme_c": {
      "ma_slope_max": -0.02,
      "board_type": "20CM"
    }
  }
}
```

---

### Step 6: 创建回归测试

**文件**: `backend/test_regression_gbm.py` (新建)

**功能**:
- 对比 GBM 过滤前后的回测结果
- 验证 GBM 不引入 bug
- 确保性能不退化

**测试用例**:
1. GBM disabled → 结果与原系统一致
2. GBM enabled → 信号数减少，质量提升
3. 模型加载失败 → 降级为原系统

---

### Step 7: 更新文档

**文件**: 
- `README.md`: 添加 GBM 使用说明
- `doc/0605_data_dig/gbm_scorer_technical_doc.md`: 已完成
- `doc/0605_data_dig/signal_backtest_v2_report.md`: 已完成

---

## 五、集成时间表

| 步骤 | 任务 | 预计时间 | 依赖 |
|:---:|------|:---:|------|
| 1 | 修改 screenergf.py | 10 min | 无 |
| 2 | 修改 walk_forward_tester_s.py | 20 min | Step 1 |
| 3 | 修改 signal_generator.py | 15 min | Step 1 |
| 4 | 创建集成测试 | 10 min | Step 2 |
| 5 | 更新配置 | 5 min | 无 |
| 6 | 回归测试 | 30 min | Step 2-4 |
| 7 | 更新文档 | 10 min | 全部 |

**总计**: ~100 分钟

---

## 六、风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|:---:|:---:|----------|
| GBM 模型加载失败 | 高 | 低 | 降级为原系统 |
| GBM 过滤过严，无信号 | 中 | 中 | 降低阈值至 0.56 |
| 性能下降 (推理开销) | 低 | 低 | GBM 推理 <1ms |
| 特征不匹配 | 高 | 低 | 严格验证特征列 |

---

## 七、验收标准

### 功能验收

- [ ] screenergf.py 返回 `ma_slope` 和 `bias_20`
- [ ] walk_forward_tester_s.py 加载 GBM 并过滤
- [ ] signal_generator.py 输出 `gbm_proba` 列
- [ ] 集成测试通过

### 性能验收

- [ ] GBM 推理时间 < 10ms / 信号
- [ ] 信号数减少 > 70% (17,484 → ~1,028)
- [ ] real_quality 率提升 > 10pp (46% → 56%)

### 回归验收

- [ ] GBM disabled 时，结果与原系统一致
- [ ] 无新增 bug
- [ ] 日志输出正常

---

## 八、后续优化

### Phase 2 (可选)

1. **在线学习**: 每月重训练模型
2. **A/B 测试**: 对比 GBM vs 原系统实盘表现
3. **阈值自适应**: 根据市场状态动态调整阈值
4. **特征扩展**: 加入 RSI、MACD 等技术指标

---

**文档版本**: 1.0  
**创建时间**: 2026-06-05  
**维护者**: Qoder CLI
