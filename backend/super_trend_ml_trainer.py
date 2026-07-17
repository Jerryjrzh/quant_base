"""
Super Trend策略：模型训练模块
支持两种模式：
  cascade — 级联双模型 (Gate + Precision), P(A)×P(B)
  single  — 单模型直判 (Label2 vs Label0+1)
"""

import pandas as pd
import numpy as np
import pickle
import os
import argparse
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

import lightgbm as lgb
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
import matplotlib.pyplot as plt

MODEL_OUTPUT_DIR = os.path.join("data", "result", "super_trend", "models")
FEATURE_IMPORTANCE_DIR = os.path.join("data", "result", "super_trend", "analysis")
os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
os.makedirs(FEATURE_IMPORTANCE_DIR, exist_ok=True)


class SuperTrendModelTrainer:

    def __init__(self, training_data_path=None, mode='single'):
        self.mode = mode  # 'cascade' or 'single'
        self.model_a = None
        self.model_b = None
        self.model = None  # single 模式下的唯一模型；cascade 下指向 model_b
        self.calibrator_a = None
        self.calibrator_b = None
        self.calibrator = None  # single 模式的 Platt 校准器
        self.feature_columns = []
        self.target_column = 'label'
        self.training_data_path = training_data_path or os.path.join(
            "data", "result", "super_trend", "super_trend_training_data.csv"
        )
        self.drop_cols = ['target', 'label', 'stock_code', 't0_date', 'is_positive', 'future_mfe']
        self.predict_threshold = 0.50

        self.params = {
            'objective': 'binary',
            'metric': 'auc',
            'boosting_type': 'gbdt',
            'num_leaves': 31,
            'learning_rate': 0.01,
            'feature_fraction': 0.8,
            'bagging_fraction': 0.8,
            'bagging_freq': 5,
            'verbose': 0,
            'seed': 42,
            'scale_pos_weight': 1.0,
        }

    def load_training_data(self):
        print(f"加载训练数据: {self.training_data_path}")
        if not os.path.exists(self.training_data_path):
            raise FileNotFoundError(f"训练数据文件不存在: {self.training_data_path}")

        df = pd.read_csv(self.training_data_path)
        print(f"数据维度: {df.shape}")

        if 't0_date' in df.columns:
            df = df.sort_values(by='t0_date').reset_index(drop=True)
            print(f"时序排序完成: {df['t0_date'].iloc[0]} → {df['t0_date'].iloc[-1]}")

        if 'label' in df.columns:
            y = df['label']
            print(f"三分类标签: Label 0={((y==0).sum())}, 1={((y==1).sum())}, 2={((y==2).sum())}")
        elif 'target' in df.columns:
            y = df['target']
        elif 'is_positive' in df.columns:
            y = df['is_positive']
        else:
            raise ValueError("未找到目标列 (label / target / is_positive)")

        self.feature_columns = [col for col in df.columns if col not in self.drop_cols]
        X = df[self.feature_columns]
        self._sorted_df = df
        self._sorted_y = y

        print(f"特征数: {len(self.feature_columns)}")
        print(f"样本数: {len(X)}")
        return X, y

    def _train_booster(self, X_train, y_train, X_val, y_val, name="Model"):
        pos_count = y_train.sum()
        neg_count = len(y_train) - pos_count
        spw = np.sqrt(neg_count / pos_count) if pos_count > 0 else 1.0
        params = self.params.copy()
        params['scale_pos_weight'] = spw

        train_data = lgb.Dataset(X_train, label=y_train)
        val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)

        print(f"  [{name}] 训练: {len(X_train)} 样本 (正 {pos_count}, 负 {neg_count}, spw={spw:.2f})")
        model = lgb.train(
            params, train_data, valid_sets=[val_data],
            num_boost_round=1000,
            callbacks=[
                lgb.early_stopping(stopping_rounds=100),
                lgb.log_evaluation(period=100),
            ],
        )
        auc = roc_auc_score(y_val, model.predict(X_val))
        print(f"  [{name}] AUC={auc:.4f}, trees={model.num_trees()}")
        return model

    @staticmethod
    def _fit_platt(model, X, y, name="Model"):
        raw = model.predict(X).reshape(-1, 1)
        cal = LogisticRegression(solver='lbfgs', max_iter=1000)
        cal.fit(raw, y)
        cal_auc = roc_auc_score(y, cal.predict_proba(raw)[:, 1])
        print(f"  [{name}] Platt校准后 AUC={cal_auc:.4f}")
        return cal

    @staticmethod
    def _cal_predict(X, model, calibrator):
        raw = model.predict(X)
        if calibrator is not None:
            return calibrator.predict_proba(raw.reshape(-1, 1))[:, 1]
        return raw

    # ──────────────────────────── Single Mode ────────────────────────────

    def train_single(self, X, y, test_size=0.2):
        """单模型：Label 2 vs Label 0+1"""
        print("\n开始训练单模型 (Label 2 vs Label 0+1)...")

        split_idx = int(len(X) * (1 - test_size))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        yb_train = (y_train == 2).astype(int)
        yb_test = (y_test == 2).astype(int)

        print(f"时序切分: 训练 {len(X_train)} / 测试 {len(X_test)}")
        print(f"  正样本(Label2): 训练 {yb_train.sum()}, 测试 {yb_test.sum()}")

        self.model = self._train_booster(X_train, yb_train, X_test, yb_test, "Single")

        print("\n── Platt Scaling ──")
        self.calibrator = self._fit_platt(self.model, X_test, yb_test, "Single")

        print("\n── 单模型评估 ──")
        self.evaluate_single(X_test, y_test)
        return X_test, y_test

    def evaluate_single(self, X_test, y_test):
        proba = self._cal_predict(X_test, self.model, self.calibrator)
        y_true = (y_test == 2).astype(int)

        auc = roc_auc_score(y_true, proba) if y_true.sum() > 0 else 0
        print(f"\n单模型 AUC: {auc:.4f}")

        self._print_threshold_table(proba, y_true)
        self._print_topn_precision(proba, y_true)
        self._print_prob_distribution(proba, y_test)

        return {'auc': auc}

    # ──────────────────────────── Cascade Mode ────────────────────────────

    def train_cascade(self, X, y, test_size=0.2):
        print("\n开始训练级联模型 (Gate + Precision)...")

        split_idx = int(len(X) * (1 - test_size))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

        print(f"时序切分: 训练 {len(X_train)} / 测试 {len(X_test)}")
        for lbl in [0, 1, 2]:
            n_tr = (y_train == lbl).sum()
            n_te = (y_test == lbl).sum()
            print(f"  Label {lbl}: 训练 {n_tr} ({n_tr/len(y_train):.1%}), 测试 {n_te} ({n_te/len(y_test):.1%})")

        ya_train = (y_train > 0).astype(int)
        ya_test = (y_test > 0).astype(int)
        self.model_a = self._train_booster(X_train, ya_train, X_test, ya_test, "Gate")
        self.calibrator_a = self._fit_platt(self.model_a, X_test, ya_test, "Gate")

        mask_b_train = y_train.isin([1, 2])
        mask_b_test = y_test.isin([1, 2])
        Xb_train, yb_train = X_train[mask_b_train], (y_train[mask_b_train] == 2).astype(int)
        Xb_test, yb_test = X_test[mask_b_test], (y_test[mask_b_test] == 2).astype(int)
        self.model_b = self._train_booster(Xb_train, yb_train, Xb_test, yb_test, "Precision")
        self.model = self.model_b
        self.calibrator_b = self._fit_platt(self.model_b, Xb_test, yb_test, "Precision")

        print("\n── 级联模型评估 ──")
        self.evaluate_cascade(X_test, y_test)
        return X_test, y_test

    def evaluate_cascade(self, X_test, y_test):
        prob_a = self._cal_predict(X_test, self.model_a, self.calibrator_a)
        prob_b_all = np.zeros(len(X_test))
        mask_b = y_test.isin([1, 2])
        if mask_b.sum() > 0:
            prob_b_all[mask_b] = self._cal_predict(X_test[mask_b], self.model_b, self.calibrator_b)
        proba = prob_a * prob_b_all

        y_true = (y_test == 2).astype(int)

        auc_gate = roc_auc_score((y_test > 0).astype(int), prob_a)
        if mask_b.sum() > 0 and (y_test[mask_b] == 2).sum() > 0:
            auc_prec = roc_auc_score((y_test[mask_b] == 2).astype(int), prob_b_all[mask_b])
        else:
            auc_prec = 0
        auc_cascade = roc_auc_score(y_true, proba) if y_true.sum() > 0 else 0
        print(f"\n单模型 AUC: Gate={auc_gate:.4f}, Precision={auc_prec:.4f}")
        print(f"级联 AUC:   {auc_cascade:.4f}")

        self._print_threshold_table(proba, y_true)
        self._print_topn_precision(proba, y_true)
        self._print_prob_distribution(proba, y_test)

        return {'auc': auc_cascade}

    # ──────────────────────────── Shared Evaluation ────────────────────────────

    @staticmethod
    def _print_threshold_table(proba, y_true):
        thresholds = [0.10, 0.20, 0.30, 0.40, 0.50, 0.65]
        print(f"\n{'=' * 70}")
        print(f"{'阈值':>6} | {'精确率':>8} | {'召回率':>8} | {'F1':>8} | {'触发数':>6} | {'准确率':>8}")
        print(f"{'-' * 70}")
        for t in thresholds:
            y_pred = (proba > t).astype(int)
            n = y_pred.sum()
            if n == 0:
                print(f"{t:>6.2f} | {'N/A':>8} | {'N/A':>8} | {'N/A':>8} | {n:>6} | {'N/A':>8}")
                continue
            p = precision_score(y_true, y_pred, zero_division=0)
            r = recall_score(y_true, y_pred, zero_division=0)
            f1 = f1_score(y_true, y_pred, zero_division=0)
            acc = accuracy_score(y_true, y_pred)
            print(f"{t:>6.2f} | {p:>8.4f} | {r:>8.4f} | {f1:>8.4f} | {n:>6} | {acc:>8.4f}")
        print(f"{'=' * 70}")

    @staticmethod
    def _print_topn_precision(proba, y_true):
        print(f"\nTop N Precision:")
        sorted_idx = np.argsort(-proba)
        for n in [50, 100, 200, 500]:
            if n > len(sorted_idx):
                continue
            topn_true = y_true.values[sorted_idx[:n]] if hasattr(y_true, 'values') else y_true[sorted_idx[:n]]
            p = topn_true.sum() / n
            print(f"  Top {n:>4}: Precision={p:.4f} ({topn_true.sum()}/{n})")

    @staticmethod
    def _print_prob_distribution(proba, y_test):
        print(f"\n概率分布:")
        print(f"  min={proba.min():.4f}, max={proba.max():.4f}, "
              f"mean={proba.mean():.4f}, median={np.median(proba):.4f}")
        for lbl in [0, 1, 2]:
            m = (y_test.values if hasattr(y_test, 'values') else y_test) == lbl
            if m.sum() > 0:
                print(f"  Label {lbl} 平均概率: {proba[m].mean():.4f}")

    # ──────────────────────────── Feature Importance ────────────────────────────

    def analyze_feature_importance(self):
        if self.model is None:
            raise ValueError("模型未训练")

        importance = pd.DataFrame({
            'feature': self.feature_columns,
            'importance': self.model.feature_importance(importance_type='gain')
        }).sort_values('importance', ascending=False)

        print("\nTop 10 最重要特征:")
        for _, row in importance.head(10).iterrows():
            print(f"  {row['feature']}: {row['importance']:.0f}")

        importance_path = os.path.join(FEATURE_IMPORTANCE_DIR, 'feature_importance.csv')
        importance.to_csv(importance_path, index=False)
        print(f"特征重要性已保存: {importance_path}")

        plt.figure(figsize=(12, 8))
        top = importance.head(15)
        bars = plt.barh(range(len(top)), top['importance'])
        plt.yticks(range(len(top)), top['feature'])
        plt.xlabel('特征重要性 (Gain)')
        plt.title(f'Super Trend 特征重要性 (Top 15) — {self.mode} mode')
        for i, (v, bar) in enumerate(zip(top['importance'], bars)):
            plt.text(v, i, f' {v:.0f}', va='center')
        plt.gca().invert_yaxis()
        plt.tight_layout()
        plot_path = os.path.join(FEATURE_IMPORTANCE_DIR, 'feature_importance_plot.png')
        plt.savefig(plot_path, dpi=300, bbox_inches='tight')
        print(f"特征重要性图表已保存: {plot_path}")
        plt.show()

        return importance

    # ──────────────────────────── Save / Load ────────────────────────────

    def save_model(self, model_name=None):
        if self.model is None:
            raise ValueError("模型未训练")

        if model_name is None:
            model_name = f'trend_gbm_{self.mode}_v1.pkl'

        model_data = {
            'mode': self.mode,
            'model': self.model,
            'model_a': self.model_a,
            'model_b': self.model_b,
            'calibrator': self.calibrator,
            'calibrator_a': self.calibrator_a,
            'calibrator_b': self.calibrator_b,
            'feature_columns': self.feature_columns,
            'target_column': self.target_column,
            'params': self.params,
            'training_date': datetime.now().isoformat()
        }
        model_path = os.path.join(MODEL_OUTPUT_DIR, model_name)
        with open(model_path, 'wb') as f:
            pickle.dump(model_data, f)
        print(f"模型已保存: {model_path}")
        return model_path

    @staticmethod
    def load_model(model_path):
        with open(model_path, 'rb') as f:
            data = pickle.load(f)
        trainer = SuperTrendModelTrainer(mode=data.get('mode', 'cascade'))
        trainer.model = data.get('model')
        trainer.model_a = data.get('model_a')
        trainer.model_b = data.get('model_b', data.get('model'))
        if trainer.model is None:
            trainer.model = trainer.model_b
        trainer.calibrator = data.get('calibrator')
        trainer.calibrator_a = data.get('calibrator_a')
        trainer.calibrator_b = data.get('calibrator_b')
        trainer.feature_columns = data['feature_columns']
        trainer.target_column = data.get('target_column', 'label')
        trainer.params = data.get('params', {})
        print(f"模型已加载: {model_path} (mode={trainer.mode})")
        return trainer

    # ──────────────────────────── Cross Validation ────────────────────────────

    def cross_validation(self, X, y, n_splits=5):
        if self.mode == 'single':
            return self._cv_single(X, y, n_splits)
        return self._cv_cascade(X, y, n_splits)

    def _cv_single(self, X, y, n_splits):
        print(f"\n执行 {n_splits}-折时序交叉验证 (单模型: Label2 vs Label0+1)...")
        tscv = TimeSeriesSplit(n_splits=n_splits)
        aucs = []

        for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]
            yb_tr = (y_tr == 2).astype(int)
            yb_val = (y_val == 2).astype(int)

            fold_model = self._train_booster(X_tr, yb_tr, X_val, yb_val, f"F{fold_idx+1}")

            raw = fold_model.predict(X_val)
            cal = LogisticRegression(solver='lbfgs', max_iter=1000)
            cal.fit(raw.reshape(-1, 1), yb_val)
            proba = cal.predict_proba(raw.reshape(-1, 1))[:, 1]

            y_true = (y_val == 2).astype(int)
            auc = roc_auc_score(y_true, proba) if y_true.sum() > 0 else 0
            aucs.append(auc)
            print(f"  Fold {fold_idx+1}: AUC={auc:.4f}")

        mean_auc = np.mean(aucs)
        std_auc = np.std(aucs)
        print(f"\n时序CV结果: AUC = {mean_auc:.4f} (+/- {std_auc:.4f})")
        return {'auc-mean': mean_auc, 'auc-stdv': std_auc, 'aucs': aucs}

    def _cv_cascade(self, X, y, n_splits):
        print(f"\n执行 {n_splits}-折时序交叉验证 (级联模型)...")
        tscv = TimeSeriesSplit(n_splits=n_splits)
        aucs = []

        for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X)):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

            ya_tr = (y_tr > 0).astype(int)
            ya_val = (y_val > 0).astype(int)
            fold_a = self._train_booster(X_tr, ya_tr, X_val, ya_val, f"F{fold_idx+1}-Gate")

            mask_tr = y_tr.isin([1, 2])
            mask_val = y_val.isin([1, 2])
            Xb_tr, yb_tr = X_tr[mask_tr], (y_tr[mask_tr] == 2).astype(int)
            Xb_val, yb_val = X_val[mask_val], (y_val[mask_val] == 2).astype(int)
            fold_b = self._train_booster(Xb_tr, yb_tr, Xb_val, yb_val, f"F{fold_idx+1}-Prec")

            raw_a = fold_a.predict(X_val)
            cal_a = LogisticRegression(solver='lbfgs', max_iter=1000)
            cal_a.fit(raw_a.reshape(-1, 1), ya_val)
            prob_a = cal_a.predict_proba(raw_a.reshape(-1, 1))[:, 1]

            raw_b = np.zeros(len(X_val))
            prob_b = np.zeros(len(X_val))
            if mask_val.sum() > 0:
                raw_b[mask_val] = fold_b.predict(X_val[mask_val])
                cal_b = LogisticRegression(solver='lbfgs', max_iter=1000)
                cal_b.fit(raw_b[mask_val].reshape(-1, 1), yb_val)
                prob_b[mask_val] = cal_b.predict_proba(raw_b[mask_val].reshape(-1, 1))[:, 1]

            cascade_prob = prob_a * prob_b
            y_true = (y_val == 2).astype(int)
            auc = roc_auc_score(y_true, cascade_prob) if y_true.sum() > 0 else 0
            aucs.append(auc)
            print(f"  Fold {fold_idx+1}: 级联 AUC={auc:.4f}")

        mean_auc = np.mean(aucs)
        std_auc = np.std(aucs)
        print(f"\n时序CV结果: 级联AUC = {mean_auc:.4f} (+/- {std_auc:.4f})")
        return {'auc-mean': mean_auc, 'auc-stdv': std_auc, 'aucs': aucs}

    # ──────────────────────────── Unified Entry ────────────────────────────

    def train_model(self, X, y, test_size=0.2):
        if self.mode == 'single':
            return self.train_single(X, y, test_size)
        return self.train_cascade(X, y, test_size)

    def evaluate_model(self, X_test, y_test):
        if self.mode == 'single':
            return self.evaluate_single(X_test, y_test)
        return self.evaluate_cascade(X_test, y_test)


def main():
    parser = argparse.ArgumentParser(description='Super Trend 模型训练')
    parser.add_argument('--mode', choices=['single', 'cascade'], default='single',
                        help='训练模式: single (Label2 vs 0+1) 或 cascade (Gate+Precision)')
    args = parser.parse_args()

    mode_label = '单模型 (Label2 vs Label0+1)' if args.mode == 'single' else '级联模型 (Gate + Precision)'
    print(f"=== Super Trend 模型训练 — {mode_label} ===")

    try:
        trainer = SuperTrendModelTrainer(mode=args.mode)
        X, y = trainer.load_training_data()
        trainer.cross_validation(X, y, n_splits=5)
        X_test, y_test = trainer.train_model(X, y)
        trainer.analyze_feature_importance()
        model_path = trainer.save_model()

        print(f"\n训练完成! (mode={args.mode})")
        print(f"模型文件: {model_path}")
        return trainer

    except Exception as e:
        print(f"\n训练失败: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    trainer = main()
