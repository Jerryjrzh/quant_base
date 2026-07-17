# Super Trend Phase 2 — Review0 修复记录（未来数据泄露修复）

> 基于 `super_trend_phase2_review0.md` 的落地修复。核心问题：`train_test_split(shuffle=True)` 和 `lgb.cv(shuffle=True)` 导致未来数据泄露，模型回测表现虚高但实盘必崩。

---

## 一、致命隐患诊断

### 未来数据泄露 (Future Peeking)

```python
# 旧代码（致命错误）
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
# ↑ shuffle=True (默认) 导致：模型用 2024年5月数据训练，去"预测"2023年10月 → 违背因果律

# 旧交叉验证（同样致命）
cv_results = lgb.cv(params, data, nfold=5, stratified=True, shuffle=True)
# ↑ shuffle=True 导致每折训练集包含未来数据
```

**后果**：交叉验证 F1 虚高 → 实盘信号全是假阳性 → 本金回撤

---

## 二、代码变更详情

### 2.1 `super_trend_data_snapshot.py`

#### 修复：训练数据输出包含 `t0_date` 供时序排序

**`get_feature_vector()`** — 新增 `t0_date` 字段：

```python
def get_feature_vector(self):
    vector = {}
    vector.update(self.features)
    vector.update({
        'stock_code': self.stock_code,
        't0_date': str(self.t0_date),   # ← 新增：供 ML trainer 时序排序
        'is_positive': int(self.is_positive),
        'future_mfe': self.future_mfe
    })
    return vector
```

**`get_training_data()`** — 保留 `t0_date`/`stock_code` 元数据列：

```python
def get_training_data(self):
    rows = []
    y = []
    for episode in self.episodes:
        features = episode.get_feature_vector()
        row = {}
        for key, value in features.items():
            if isinstance(value, (int, float, np.number)):
                row[key] = value
            elif key in ('t0_date', 'stock_code'):    # ← 新增：保留元数据
                row[key] = value
        if row:
            rows.append(row)
            y.append(1 if episode.is_positive else 0)
    # ...
```

---

### 2.2 `super_trend_ml_trainer.py`

#### 修复 1：`__init__` 新增 `drop_cols` 和 `predict_threshold`

```python
self.drop_cols = ['target', 'stock_code', 't0_date', 'is_positive', 'future_mfe']
self.predict_threshold = 0.65   # 量化实战默认阈值
```

---

#### 修复 2：`load_training_data()` — 按 `t0_date` 严格时序排序

```python
def load_training_data(self):
    df = pd.read_csv(self.training_data_path)
    
    # 时序排序：按 t0_date 严格升序
    if 't0_date' in df.columns:
        df = df.sort_values(by='t0_date').reset_index(drop=True)
    
    # 分离特征列（剔除元数据列）
    self.feature_columns = [col for col in df.columns if col not in self.drop_cols]
    X = df[self.feature_columns]
    
    # 保存排序后的 df 供后续时序切割使用
    self._sorted_df = df
    self._sorted_y = y
    return X, y
```

---

#### 修复 3：`train_model()` — 时序切割替代 `train_test_split`

```python
def train_model(self, X, y, test_size=0.2):
    # 时序切割：前 80% 训练，后 20% 测试（严格按时间顺序，禁止 shuffle）
    split_idx = int(len(X) * (1 - test_size))
    
    X_train = X.iloc[:split_idx]     # 历史数据
    X_test = X.iloc[split_idx:]      # 未来数据
    y_train = y.iloc[:split_idx]
    y_test = y.iloc[split_idx:]
    # ...
```

**修复前 vs 修复后**：

| 维度 | 旧代码 | 新代码 |
|---|---|---|
| 切割方式 | `train_test_split(shuffle=True)` | 时序截断 `[:split_idx]` / `[split_idx:]` |
| 训练集 | 随机抽取（含未来数据） | 严格前段历史 |
| 测试集 | 随机抽取（含历史数据） | 严格后段未来 |
| 因果律 | ❌ 违背 | ✅ 遵守 |

---

#### 修复 4：`cross_validation()` — `TimeSeriesSplit` 替代 `lgb.cv(shuffle=True)`

```python
def cross_validation(self, X, y, n_splits=5):
    tscv = TimeSeriesSplit(n_splits=n_splits)
    
    for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X)):
        X_train_fold = X.iloc[train_idx]   # 时序前段
        X_val_fold = X.iloc[val_idx]       # 时序后段（严格在训练集之后）
        # ...
```

**`TimeSeriesSplit` 的折叠方式**：

```
Fold 1: [Train: 0-100]  [Val: 100-150]
Fold 2: [Train: 0-150]  [Val: 150-200]
Fold 3: [Train: 0-200]  [Val: 200-250]
Fold 4: [Train: 0-250]  [Val: 250-300]
Fold 5: [Train: 0-300]  [Val: 300-350]
```

每折的验证集都在训练集之后，严格遵守"用历史预测未来"。

---

#### 修复 5：`evaluate_model()` — 多阈值分析（Precision 优先）

```python
def evaluate_model(self, X_test, y_test):
    y_pred_proba = self.model.predict(X_test)
    
    # 多阈值对比：量化实战中宁可放过机会，不可频繁触发假信号
    thresholds = [0.50, 0.65, 0.70]
    for threshold in thresholds:
        y_pred = (y_pred_proba > threshold).astype(int)
        precision = precision_score(y_test, y_pred, zero_division=0)
        recall = recall_score(y_test, y_pred, zero_division=0)
        # ...
```

**输出示例**：

```
============================================================
  阈值 |   精确率 |   召回率 |       F1 | 触发数 |   准确率
------------------------------------------------------------
  0.50 |   0.3500 |   0.8000 |   0.4878 |     20 |   0.6500
  0.65 |   0.5500 |   0.5500 |   0.5500 |     10 |   0.7500
  0.70 |   0.6667 |   0.4000 |   0.5000 |      6 |   0.8000
============================================================
```

**目标**：阈值 0.65~0.70 下 Precision ≥ 60%，即系统发出的信号有极高胜率。

---

#### 修复 6：`lgb.train()` — LightGBM 4.x API 兼容

**问题**：LightGBM 4.0+ 移除了 `lgb.train()` 的 `early_stopping_rounds` 和 `verbose_eval` 直传参数，改为 callbacks 方式。运行时抛出：

```
TypeError: train() got an unexpected keyword argument 'early_stopping_rounds'
```

**修复**：`train_model()` 和 `cross_validation()` 两处调用统一改为 callback API：

```python
# 旧 API（LightGBM < 4.0，已废弃）
lgb.train(
    self.params, train_data,
    valid_sets=[test_data],
    num_boost_round=500,
    early_stopping_rounds=50,   # ← 报错
    verbose_eval=50,             # ← 报错
)

# 新 API（LightGBM 4.0+）
lgb.train(
    self.params, train_data,
    valid_sets=[test_data],
    num_boost_round=500,
    callbacks=[
        lgb.early_stopping(stopping_rounds=50),
        lgb.log_evaluation(period=50),
    ],
)
```

| 方法 | 修复内容 |
|---|---|
| `train_model()` | `early_stopping_rounds=50` → `callbacks=[lgb.early_stopping(50)]` |
| `train_model()` | `verbose_eval=50` → `callbacks=[lgb.log_evaluation(50)]` |
| `cross_validation()` | `early_stopping_rounds=50` → `callbacks=[lgb.early_stopping(50)]` |
| `cross_validation()` | `verbose_eval=0` → `callbacks=[lgb.log_evaluation(0)]` |

---

#### 修复 7：`params` — `is_unbalance` 与 `scale_pos_weight` 冲突

**问题**：LightGBM 不允许同时设置 `is_unbalance=True` 和 `scale_pos_weight`，两者功能重叠（均为处理类别不平衡），运行时抛出：

```
LightGBMError: Cannot set is_unbalance and scale_pos_weight at the same time
```

**修复**：移除 `is_unbalance`，保留 `scale_pos_weight=3.0`（对 26.66% 正样本比例提供更精细的权重控制）：

```python
# 旧（冲突）
self.params = {
    ...
    'is_unbalance': True,
    'scale_pos_weight': 3.0,
}

# 新（保留 scale_pos_weight）
self.params = {
    ...
    'scale_pos_weight': 3.0,
}
```

| 参数 | 机制 | 选择理由 |
|---|---|---|
| `is_unbalance=True` | 自动按正负样本比例设权重 | 粗粒度，不可调 |
| `scale_pos_weight=3.0` | 手动指定正样本权重倍数 | 精细控制，可随样本比例调整 |

---

## 三、文件变更汇总

```
backend/super_trend_data_snapshot.py    # get_feature_vector 新增 t0_date + get_training_data 保留元数据列
backend/super_trend_ml_trainer.py       # 时序切割 + TimeSeriesSplit + 多阈值评估
```

---

## 四、验证状态

| 检查项 | 状态 |
|---|---|
| 所有模块语法编译通过 | ✅ |
| `train_test_split` 已替换为时序切割 | ✅ |
| `lgb.cv(shuffle=True)` 已替换为 `TimeSeriesSplit` | ✅ |
| 多阈值评估（0.50/0.65/0.70）输出 Precision 对比表 | ✅ |
| `t0_date` 贯穿：snapshot → CSV → trainer 排序 → drop before train | ✅ |
| 默认阈值 `predict_threshold=0.65`（Precision 优先） | ✅ |
| LightGBM 4.x API 兼容（callbacks 替代直传参数） | ✅ |
| `is_unbalance` 移除，保留 `scale_pos_weight=3.0`（消除参数冲突） | ✅ |

---

## 五、下一步执行计划

1. **重新扫描数据**：运行 `python super_trend_scanner_v1.py --full`，使用已实现的 T0 去重 + 假突破负样本逻辑
2. **跑通 ML 训练流**：`python super_trend_ml_trainer.py`，观察时序 CV 结果和特征重要性
3. **概率阈值调优**：确认 0.65 阈值下 Precision ≥ 60%，否则调整阈值或增加样本量
4. **特征剪枝**：剔除 importance < 2% 的特征，降低过拟合风险
