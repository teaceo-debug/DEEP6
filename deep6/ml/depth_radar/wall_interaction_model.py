"""LightGBM model for wall interaction outcome prediction."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover - runtime dependency guard
    lgb = None  # type: ignore[assignment]

from deep6.ml.depth_radar.wall_interaction_labeler import INTERACTION_FEATURE_NAMES


log = logging.getLogger(__name__)

CLASS_NAMES = ["BOUNCE", "BREAK", "HOLD"]
LABEL_TO_ID = {name: idx for idx, name in enumerate(CLASS_NAMES)}


def _require_lightgbm() -> None:
    if lgb is None:
        raise RuntimeError("lightgbm is not installed. Install it with `pip install lightgbm`.")


class WallInteractionPredictor:
    def __init__(self, model_path: str | None = None) -> None:
        self.model: Any | None = None
        self.feature_names = list(INTERACTION_FEATURE_NAMES)
        self.class_names = list(CLASS_NAMES)
        self.training_metrics: dict[str, Any] = {}
        if model_path is not None:
            self.load(model_path)

    def train(self, data_path: str) -> dict[str, Any]:
        _require_lightgbm()
        path = Path(data_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Wall interaction parquet not found: {path}")
        frame = pd.read_parquet(path)
        if frame.empty:
            raise ValueError(f"Wall interaction parquet is empty: {path}")
        missing = [name for name in [*self.feature_names, "label", "timestamp"] if name not in frame.columns]
        if missing:
            raise ValueError(f"Wall interaction parquet missing required columns: {missing}")

        frame = self._sort_temporally(frame)
        X = frame[self.feature_names].astype(np.float64).to_numpy(copy=True)
        y = frame["label"].astype(str).str.upper().map(LABEL_TO_ID)
        if y.isna().any():
            unknown = sorted(set(frame.loc[y.isna(), "label"].astype(str).str.upper().unique()))
            raise ValueError(f"Unsupported labels in training data: {unknown}")
        y_arr = y.astype(np.int8).to_numpy()
        if len(X) < 2:
            raise ValueError("At least 2 rows are required for temporal train/test split.")

        split_idx = int(len(X) * 0.8)
        split_idx = min(max(split_idx, 1), len(X) - 1)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y_arr[:split_idx], y_arr[split_idx:]

        sample_weight = self._compute_sample_weights(y_train)
        train_set = lgb.Dataset(X_train, label=y_train, weight=sample_weight, feature_name=self.feature_names)
        valid_set = lgb.Dataset(X_test, label=y_test, feature_name=self.feature_names, reference=train_set)
        params = {
            "objective": "multiclass",
            "num_class": len(CLASS_NAMES),
            "metric": "multi_logloss",
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.9,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "min_data_in_leaf": 20,
            "verbose": -1,
        }
        self.model = lgb.train(
            params=params,
            train_set=train_set,
            num_boost_round=300,
            valid_sets=[valid_set],
            callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(-1)],
        )
        metrics = self._build_metrics(X_test, y_test)
        metrics["train_rows"] = len(X_train)
        metrics["test_rows"] = len(X_test)
        metrics["label_distribution"] = frame["label"].value_counts().to_dict()
        self.training_metrics = metrics
        return metrics

    def predict(self, features: np.ndarray) -> tuple[str, float, dict[str, float]]:
        model = self._require_model()
        matrix = self._coerce_feature_matrix(features)
        probs = np.asarray(model.predict(matrix), dtype=np.float64)
        if probs.ndim == 1:
            probs = probs.reshape(1, -1)
        row = probs[0]
        label_idx = int(np.argmax(row))
        label = self.class_names[label_idx]
        prob_map = {name: float(prob) for name, prob in zip(self.class_names, row.tolist(), strict=False)}
        return label, float(row[label_idx]), prob_map

    def save(self, path: str) -> None:
        model = self._require_model()
        output = Path(path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": model,
                "feature_names": list(self.feature_names),
                "class_names": list(self.class_names),
                "training_metrics": dict(self.training_metrics),
            },
            output,
        )

    def load(self, path: str) -> None:
        _require_lightgbm()
        model_path = Path(path).expanduser().resolve()
        if not model_path.exists():
            raise FileNotFoundError(f"Predictor model file not found: {model_path}")
        payload = joblib.load(model_path)
        if not isinstance(payload, dict) or "model" not in payload:
            raise ValueError(f"Invalid predictor payload in {model_path}")
        self.model = payload["model"]
        self.feature_names = list(payload.get("feature_names", INTERACTION_FEATURE_NAMES))
        self.class_names = list(payload.get("class_names", CLASS_NAMES))
        self.training_metrics = dict(payload.get("training_metrics", {}))

    def _require_model(self) -> Any:
        _require_lightgbm()
        if self.model is None:
            raise RuntimeError("No wall interaction model loaded. Train or load a model first.")
        return self.model

    def _sort_temporally(self, frame: pd.DataFrame) -> pd.DataFrame:
        sort_ts = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        if sort_ts.notna().any():
            return frame.assign(_sort_ts=sort_ts).sort_values("_sort_ts", kind="stable").drop(columns="_sort_ts")
        return frame.sort_values("timestamp", kind="stable")

    def _compute_sample_weights(self, targets: np.ndarray) -> np.ndarray:
        unique, counts = np.unique(targets, return_counts=True)
        observed = {int(label): int(count) for label, count in zip(unique, counts, strict=False)}
        missing = [label for label in range(len(CLASS_NAMES)) if label not in observed]
        if missing:
            raise ValueError(f"Training split must contain all classes after temporal split. Missing: {missing}")
        total = len(targets)
        num_classes = len(observed)
        weights = {label: total / (num_classes * count) for label, count in observed.items()}
        return np.asarray([weights[int(label)] for label in targets], dtype=np.float64)

    def _build_metrics(self, X_test: np.ndarray, y_test: np.ndarray) -> dict[str, Any]:
        model = self._require_model()
        probs = np.asarray(model.predict(X_test), dtype=np.float64)
        if probs.ndim == 1:
            probs = probs.reshape(len(X_test), len(CLASS_NAMES))
        y_pred = np.argmax(probs, axis=1).astype(np.int8)
        report = classification_report(
            y_test,
            y_pred,
            labels=list(range(len(CLASS_NAMES))),
            target_names=CLASS_NAMES,
            output_dict=True,
            zero_division=0,
        )
        return {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "confusion_matrix": confusion_matrix(y_test, y_pred, labels=list(range(len(CLASS_NAMES)))).tolist(),
            "per_class": {
                class_name: {
                    "precision": float(report[class_name]["precision"]),
                    "recall": float(report[class_name]["recall"]),
                    "f1": float(report[class_name]["f1-score"]),
                    "support": int(report[class_name]["support"]),
                }
                for class_name in CLASS_NAMES
            },
            "macro_f1": float(report["macro avg"]["f1-score"]),
            "weighted_f1": float(report["weighted avg"]["f1-score"]),
            "feature_importance": {
                name: float(importance)
                for name, importance in zip(
                    self.feature_names,
                    model.feature_importance(importance_type="gain"),
                    strict=False,
                )
            },
        }

    def _coerce_feature_matrix(self, features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim == 1:
            if matrix.shape[0] != len(self.feature_names):
                raise ValueError(f"Expected {len(self.feature_names)} features, got {matrix.shape[0]}")
            return matrix.reshape(1, -1)
        if matrix.ndim == 2 and matrix.shape[1] == len(self.feature_names):
            return matrix
        raise ValueError(f"Expected feature matrix width {len(self.feature_names)}, got shape {matrix.shape}")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train wall interaction outcome predictor")
    parser.add_argument("--data", required=True, help="Wall interaction parquet path")
    parser.add_argument("--output", required=True, help="Joblib output path")
    return parser


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _build_arg_parser().parse_args()
    predictor = WallInteractionPredictor()
    metrics = predictor.train(args.data)
    predictor.save(args.output)
    print(json.dumps(metrics, indent=2, sort_keys=True))
