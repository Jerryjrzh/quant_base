代码和计划我都仔细看过了。整体工程化思维非常严谨，Phase 2 的规划目标清晰，模块划分和从 Phase 1 承接的逻辑都非常顺畅。

LightGBM 确实是处理这类非线性、存在缺失值的结构化金融特征的绝佳选择，本地单机训练速度极快，非常适合目前的量化开发节奏。

不过，在审阅 `super_trend_ml_trainer.py` 时，我发现了一个在量化机器学习中 **极其致命、可能导致模型在回测时表现完美但实盘直接崩溃的隐患** 。下面我们先来修复这个问题，再对接下来的执行步骤进行梳理。

### 一、 核心代码 Review（The Fatal Flaw）

**致命隐患：未来数据泄露 (Future Peeking)**

在 `super_trend_ml_trainer.py` 的 `prepare_data` 方法中，你使用了 `scikit-learn` 的 `train_test_split`：

**Python**

```
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=42)
```

`train_test_split` 默认 `shuffle=True`（随机打乱）。这意味着你的训练集和测试集是在时间上交错的。

举个例子：模型可能会用 2024 年 5 月的“主升浪”特征进行训练，然后去“预测”测试集中 2023 年 10 月的切片。这在真实的股票市场中是绝对违背因果律的，会导致模型在交叉验证时 F1-Score 极高，但实盘完全失效。

**修复方案：按时间顺序进行严格的时序切割（Chronological Split）**

在量化建模中，我们必须遵循“用历史预测未来”的原则。你需要先按 `t0_date` 排序，再进行截断切割。

请修改 `prepare_data` 方法的逻辑：

**Python**

```
def prepare_data(self, test_size=0.2):
    # 确保 t0_date 存在用于排序
    if 't0_date' in self.df.columns:
        # 1. 严格按时间排序
        self.df = self.df.sort_values(by='t0_date').reset_index(drop=True)
      
    y = self.df['target'] if 'target' in self.df.columns else self.df['is_positive']
    X = self.df.drop(columns=self.drop_cols, errors='ignore')
  
    # 2. 按时间序列先后顺序切分（禁止 random shuffle）
    split_idx = int(len(self.df) * (1 - test_size))
  
    X_train = X.iloc[:split_idx]
    X_test = X.iloc[split_idx:]
    y_train = y.iloc[:split_idx]
    y_test = y.iloc[split_idx:]
  
    print(f"时序切分完成: 训练集 {len(X_train)} 样本, 测试集 {len(X_test)} 样本")
  
    # 3. SMOTE 采样（注意：SMOTE 只能作用于训练集，不能污染测试集，你原代码这点做得是对的）
    if self.use_smote:
        print("应用 SMOTE 进行过采样...")
        smote = SMOTE(random_state=42)
        X_train, y_train = smote.fit_resample(X_train, y_train)
        print(f"SMOTE 处理后训练集: {len(X_train)} 样本")
      
    return X_train, X_test, y_train, y_test
```

### 二、 Phase 2 计划与代码亮点

* **指标评估非常全面：** 包含了 ROC-AUC、Precision、Recall 和 F1。对于抓主升浪这种策略， **Precision（查准率）的优先级绝对高于 Recall（查全率）** 。宁可放过一些机会，也绝不能频繁触发假信号导致本金回撤。
* **不平衡处理：** 同时保留了 `scale_pos_weight` 和 `SMOTE` 两个选项。LightGBM 原生的 `is_unbalance=True` 已经足够强大，配合超参数调优，通常比强行生成人造数据的 SMOTE 表现更好（因为金融数据的噪声极大，SMOTE 容易放大噪声）。
* **特征重要性（Feature Importance）输出：** 这一点极其重要。这就像是长跑后的心率和配速复盘，跑完之后我们可以明确看到 MACD、RSI 或是你设计的“水下点火”特征哪个起到了决定性作用。

### 三、 接下来需要执行的内容 (Action Plan)

顺着你的 Phase 2 计划，接下来最紧凑的执行路径如下：

#### 1. 挂载排重机制并重新扫描数据 (Phase 1 返工)

这是目前最大的瓶颈。拿着未经排重、且负样本定义严苛的旧数据去跑 Phase 2，只会得到一个毫无实战价值的模型。

* **动作：** 将我们讨论过的 **$T_0$** 去重冷却逻辑（`seen_t0_indices`）加入扫描器，放宽负样本触发门槛，并将正样本目标提升至 **$100\%$** 的真正主升浪。
* **目标：** 至少跑出 300-500 个干净的独立正样本，以及 1500+ 个高质量的负样本（假突破）。

#### 2. 跑通 ML 训练流并分析特征

* **动作：** 使用新生成的数据运行 `super_trend_ml_trainer.py`。
* **目标：** 重点观察  **Feature Importance Plot** 。如果有某些特征的重要性占比低于 2% 或为 0，可以直接在后续版本中剔除，减少计算开销，降低过拟合风险。

#### 3. 概率阈值调优 (Threshold Tuning)

在量化实战中，我们通常不会使用模型默认的 `0.5` 作为买入判定线。

* **动作：** 在训练完成后，使用测试集调用 `predict_proba(X_test)`，而不是直接 `predict()`。
* **目标：** 将买入阈值提高到 `0.65` 或 `0.7`。观察在这个严苛条件下，Precision 是否能达到 60% 甚至 70% 以上。这就意味着系统发出的信号，有极高的胜率。

修复掉时序切割的隐患后，这套基础设施已经具备了直接对接全市场数据的能力。

你是希望先将精力放在完善 Phase 1 的扫描器提取出几千个高质量样本，还是想先用手头的小样本把修正后的 `super_trend_ml_trainer.py` 端到端跑通看一遍完整的输出日志？
