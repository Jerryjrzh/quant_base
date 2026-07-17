#!/usr/bin/env python3
"""
GBM Signal Scorer v1.0 — 梯度提升信号打分器

替代失效的 morse 评分系统 (98.2% = 95分)，用 GBM 模型输出 0~1 概率值。

功能:
  - train(): 用历史信号数据训练 GBM 模型
  - score(): 对新信号输出 GBM 概率
  - save()/load(): 模型序列化/反序列化

模型规格:
  - 算法: GradientBoostingClassifier (100 trees, depth=3, lr=0.1)
  - 特征: ma_slope, bias_20, score + one-hot(market_env, v44_trend, v44_bias_tier)
  - 目标: is_real_quality = (MFE≥5%) AND (MAE≥-8%)
  - 训练集: 2025-01 ~ 2025-12 (12,773 样本)
  - 测试集: 2026-01 ~ 2026-04 (4,711 样本, F1=0.571)

推荐阈值:
  - 极精选: proba ≥ 0.62 (日均14信号, real_q=56.2%, 盈亏比=2.36)
  - 精选:   proba ≥ 0.56 (日均25信号, real_q=52.1%, 盈亏比=2.01)
  - 均衡:   proba ≥ 0.44 (日均50信号, real_q=48.2%, 盈亏比=1.63)
"""

import os
import json
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'model')

RAW_FEATURES = ['ma_slope', 'bias_20', 'score']
ONEHOT_PREFIXES = ['market_env', 'v44_trend', 'v44_bias_tier']


class GBMScorer:
    """GBM 信号打分器"""

    def __init__(self):
        self.model = None
        self.feature_cols = None
        self.train_columns = None
        self.metadata = {}

    def train(self, df: pd.DataFrame, train_end: str = '2025-12-31') -> dict:
        """
        训练 GBM 模型

        Args:
            df: master_signals.csv 加载后的 DataFrame
            train_end: 训练集截止日期

        Returns:
            训练评估指标 dict
        """
        df = df.copy()
        df['signal_date'] = pd.to_datetime(df['signal_date'])

        # 目标变量
        df['is_real_quality'] = (df['future_mfe'] >= 0.05) & (df['future_mae'] >= -0.08)

        # One-hot 编码
        df = pd.get_dummies(df, columns=ONEHOT_PREFIXES, prefix=ONEHOT_PREFIXES)

        # 时间切分
        train_mask = df['signal_date'] <= pd.to_datetime(train_end)
        test_mask = df['signal_date'] > pd.to_datetime(train_end)

        train_df = df[train_mask]
        test_df = df[test_mask]

        # 确定特征列
        onehot_cols = [c for c in df.columns if any(c.startswith(p + '_') for p in ONEHOT_PREFIXES)]
        self.feature_cols = RAW_FEATURES + onehot_cols
        self.train_columns = list(df.columns)

        X_train = train_df[self.feature_cols].fillna(0)
        y_train = train_df['is_real_quality'].astype(int)
        X_test = test_df[self.feature_cols].fillna(0)
        y_test = test_df['is_real_quality'].astype(int)

        # 训练
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            max_depth=3,
            learning_rate=0.1,
            subsample=0.8,
            random_state=42
        )
        self.model.fit(X_train, y_train)

        # 评估
        y_pred = self.model.predict(X_test)
        y_proba = self.model.predict_proba(X_test)[:, 1]

        metrics = {
            'train_samples': len(train_df),
            'test_samples': len(test_df),
            'train_positive_rate': float(y_train.mean()),
            'test_positive_rate': float(y_test.mean()),
            'f1': float(f1_score(y_test, y_pred)),
            'precision': float(precision_score(y_test, y_pred)),
            'recall': float(recall_score(y_test, y_pred)),
            'train_end': train_end,
        }

        self.metadata = {
            'feature_cols': self.feature_cols,
            'metrics': metrics,
            'feature_importance': dict(zip(
                self.feature_cols,
                [round(float(x), 6) for x in self.model.feature_importances_]
            )),
        }

        return metrics

    def score(self, df: pd.DataFrame) -> np.ndarray:
        """
        对信号打分，返回 GBM 概率数组

        Args:
            df: 包含信号特征的 DataFrame (与 master_signals.csv 格式一致)

        Returns:
            numpy array of probabilities [0, 1]
        """
        if self.model is None:
            raise RuntimeError("模型未加载，请先调用 load() 或 train()")

        df = df.copy()
        if 'signal_date' in df.columns:
            df['signal_date'] = pd.to_datetime(df['signal_date'])

        df = pd.get_dummies(df, columns=ONEHOT_PREFIXES, prefix=ONEHOT_PREFIXES)

        # 补齐缺失列
        for col in self.feature_cols:
            if col not in df.columns:
                df[col] = 0

        X = df[self.feature_cols].fillna(0)
        return self.model.predict_proba(X)[:, 1]

    def filter(self, df: pd.DataFrame, threshold: float = 0.62) -> pd.DataFrame:
        """
        按阈值过滤信号

        Args:
            df: 信号 DataFrame
            threshold: GBM 概率阈值

        Returns:
            过滤后的 DataFrame (新增 gbm_proba 列)
        """
        df = df.copy()
        df['gbm_proba'] = self.score(df)
        return df[df['gbm_proba'] >= threshold].copy()

    def save(self, name: str = 'gbm_scorer_v1') -> str:
        """
        序列化模型到磁盘

        Args:
            name: 模型名称

        Returns:
            保存路径
        """
        if self.model is None:
            raise RuntimeError("无模型可保存")

        os.makedirs(MODEL_DIR, exist_ok=True)
        model_path = os.path.join(MODEL_DIR, f'{name}.pkl')
        meta_path = os.path.join(MODEL_DIR, f'{name}_meta.json')

        with open(model_path, 'wb') as f:
            pickle.dump(self.model, f)

        with open(meta_path, 'w') as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)

        return model_path

    def load(self, name: str = 'gbm_scorer_v1') -> bool:
        """
        从磁盘加载模型

        Args:
            name: 模型名称

        Returns:
            是否加载成功
        """
        model_path = os.path.join(MODEL_DIR, f'{name}.pkl')
        meta_path = os.path.join(MODEL_DIR, f'{name}_meta.json')

        if not os.path.exists(model_path):
            return False

        with open(model_path, 'rb') as f:
            self.model = pickle.load(f)

        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                self.metadata = json.load(f)
            self.feature_cols = self.metadata.get('feature_cols', RAW_FEATURES)

        return True

    def summary(self) -> str:
        """返回模型摘要"""
        if not self.metadata:
            return "模型未加载"
        m = self.metadata.get('metrics', {})
        lines = [
            "GBM Signal Scorer",
            f"  训练集: {m.get('train_samples', '?')} 样本 (正例 {m.get('train_positive_rate', 0):.1%})",
            f"  测试集: {m.get('test_samples', '?')} 样本 (正例 {m.get('test_positive_rate', 0):.1%})",
            f"  F1: {m.get('f1', 0):.3f} | Precision: {m.get('precision', 0):.3f} | Recall: {m.get('recall', 0):.3f}",
            f"  特征数: {len(self.metadata.get('feature_cols', []))}",
        ]

        fi = self.metadata.get('feature_importance', {})
        if fi:
            top5 = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:5]
            lines.append("  Top 5 特征:")
            for name, imp in top5:
                lines.append(f"    {name:<30} {imp:.4f}")

        return '\n'.join(lines)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI: 训练 & 保存
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def train_and_save():
    """从 master_signals.csv 训练模型并保存"""
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'data', 'result', 'SignalGenerator', 'master_signals.csv')
    df = pd.read_csv(csv_path)

    # Scheme C 基础过滤
    df = df[(df['ma_slope'] <= -0.02) & (df['board_type'] == '20CM')].copy()
    print(f"Scheme C 数据: {len(df):,} 信号")

    scorer = GBMScorer()
    metrics = scorer.train(df)

    print(f"\n训练完成:")
    print(f"  F1: {metrics['f1']:.3f}")
    print(f"  Precision: {metrics['precision']:.3f}")
    print(f"  Recall: {metrics['recall']:.3f}")

    path = scorer.save()
    print(f"\n模型已保存: {path}")
    print(scorer.summary())

    return scorer


if __name__ == '__main__':
    train_and_save()
