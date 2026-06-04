"""LightGBM wall classifier for Depth Radar lifecycle labels."""
from __future__ import annotations

import argparse
import ast
import json
import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

try:
    import lightgbm as lgb
except ImportError:  # pragma: no cover - runtime dependency guard
    lgb = None  # type: ignore[assignment]

from deep6.ml.depth_radar.wall_features import FEATURE_NAMES, NUM_FEATURES, WallFeatureExtractor


log = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 0.5
_EXIT_GATE_F1 = 0.80
_BINARY_CLASS_NAMES = ["NOT_SPOOF", "SPOOF"]
_MULTICLASS_CLASS_NAMES = ["GENUINE", "SPOOF", "ICEBERG", "STALE"]
_MULTICLASS_LABEL_TO_ID = {name: idx for idx, name in enumerate(_MULTICLASS_CLASS_NAMES)}


def _require_lightgbm() -> None:
    if lgb is None:
        raise RuntimeError("lightgbm is not installed. Install it with `pip install lightgbm`.")


class WallClassifier:
    """Depth Radar wall classifier backed by LightGBM."""

    def __init__(self, model_path: str | None = None) -> None:
        self.model: Any | None = None
        self.mode = "binary"
        self.feature_names = list(FEATURE_NAMES)
        self.threshold = _DEFAULT_THRESHOLD
        self.training_metrics: dict[str, Any] = {}
        self.class_names = list(_BINARY_CLASS_NAMES)

        if model_path is not None:
            self.load(model_path)

    def train(self, data_path: str, mode: str = "binary") -> dict[str, Any]:
        """Train the classifier from a labeled parquet dataset."""
        _require_lightgbm()
        if mode not in {"binary", "multiclass"}:
            raise ValueError(f"Unsupported classifier mode: {mode}")

        path = Path(data_path).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Labeled wall parquet not found: {path}")

        try:
            frame = pd.read_parquet(path)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Failed to read labeled wall parquet: {path}") from exc

        if frame.empty:
            raise ValueError(f"Labeled wall parquet is empty: {path}")
        if "label" not in frame.columns:
            raise ValueError("Labeled wall parquet must contain a `label` column.")
        if "timestamp" not in frame.columns:
            raise ValueError("Labeled wall parquet must contain a `timestamp` column for walk-forward validation.")

        frame = self._sort_temporally(frame)
        X = self._build_feature_matrix(frame)
        y = self._build_targets(frame, mode)

        if len(X) < 2:
            raise ValueError("At least 2 labeled rows are required for walk-forward validation.")

        split_idx = int(len(X) * 0.8)
        split_idx = min(max(split_idx, 1), len(X) - 1)

        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]

        if mode == "binary":
            params, sample_weight = self._build_binary_training_params(y_train)
            class_names = list(_BINARY_CLASS_NAMES)
        else:
            if not self._has_verified_binary_gate():
                log.warning("Training multiclass without verified binary F1 > 0.80 gate")
            params, sample_weight = self._build_multiclass_training_params(y_train)
            class_names = list(_MULTICLASS_CLASS_NAMES)

        train_set = lgb.Dataset(
            X_train,
            label=y_train,
            weight=sample_weight,
            feature_name=self.feature_names,
        )
        valid_set = lgb.Dataset(X_test, label=y_test, feature_name=self.feature_names, reference=train_set)

        model = lgb.train(
            params=params,
            train_set=train_set,
            num_boost_round=200,
            valid_sets=[valid_set],
            callbacks=[lgb.early_stopping(20, verbose=False), lgb.log_evaluation(-1)],
        )

        metrics = self._build_metrics(model, X_test, y_test, mode, class_names)

        self.model = model
        self.mode = mode
        self.class_names = class_names
        self.training_metrics = metrics

        log.info(
            "depth_radar.classifier.train.complete",
            extra={
                "rows": len(frame),
                "train_rows": len(X_train),
                "test_rows": len(X_test),
                "mode": mode,
                "f1": metrics["f1"],
                "precision": metrics["precision"],
                "recall": metrics["recall"],
                "accuracy": metrics["accuracy"],
            },
        )

        if mode == "binary" and metrics["f1"] < _EXIT_GATE_F1:
            warning = (
                "WARNING: Binary SPOOF classifier F1 "
                f"{metrics['f1']:.4f} is below the exit gate of {_EXIT_GATE_F1:.2f}."
            )
            log.warning(
                "depth_radar.classifier.exit_gate_failed",
                extra={"f1": metrics["f1"], "required_f1": _EXIT_GATE_F1},
            )
            print(warning)

        return metrics

    def classify(self, features: np.ndarray) -> tuple[str, float]:
        """Classify one feature vector and return (label, confidence)."""
        matrix = self._coerce_feature_matrix(features)
        if matrix.shape[0] != 1:
            raise ValueError("classify() expects a single feature vector. Use classify_batch() for batches.")
        return self.classify_batch(matrix)[0]

    def classify_with_probs(self, features: np.ndarray) -> tuple[str, float, dict[str, float]]:
        """Classify one feature vector and return (label, confidence, per-class probabilities)."""
        matrix = self._coerce_feature_matrix(features)
        if matrix.shape[0] != 1:
            raise ValueError(
                "classify_with_probs() expects a single feature vector. Use classify_batch_with_probs() for batches."
            )
        return self.classify_batch_with_probs(matrix)[0]

    def classify_batch(self, features: np.ndarray) -> list[tuple[str, float]]:
        """Classify a batch of feature vectors."""
        return [(label, confidence) for label, confidence, _ in self.classify_batch_with_probs(features)]

    def classify_batch_with_probs(self, features: np.ndarray) -> list[tuple[str, float, dict[str, float]]]:
        """Classify a batch of feature vectors with per-class probabilities."""
        model = self._require_model()
        matrix = self._coerce_feature_matrix(features)
        raw_probabilities = np.asarray(model.predict(matrix), dtype=np.float64)

        if self.mode == "multiclass":
            probability_rows = self._coerce_multiclass_probabilities(raw_probabilities, matrix.shape[0])
            results: list[tuple[str, float, dict[str, float]]] = []
            for row in probability_rows:
                label_index = int(np.argmax(row))
                label = self.class_names[label_index]
                all_probs = {
                    class_name: float(prob)
                    for class_name, prob in zip(self.class_names, row.tolist(), strict=False)
                }
                results.append((label, float(row[label_index]), all_probs))
            return results

        probabilities = raw_probabilities.reshape(-1)
        results = []
        for prob in probabilities:
            label = "SPOOF" if prob >= self.threshold else "NOT_SPOOF"
            all_probs = {
                "NOT_SPOOF": float(max(0.0, min(1.0, 1.0 - prob))),
                "SPOOF": float(max(0.0, min(1.0, prob))),
            }
            results.append((label, float(prob), all_probs))
        return results

    def save(self, path: str) -> None:
        """Persist the trained model and metadata via joblib."""
        model = self._require_model()
        output = Path(path).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "model": model,
            "mode": self.mode,
            "class_names": list(self.class_names),
            "feature_names": list(self.feature_names),
            "threshold": float(self.threshold),
            "training_metrics": dict(self.training_metrics),
        }
        joblib.dump(payload, output)
        log.info("depth_radar.classifier.saved", extra={"path": str(output), "mode": self.mode})

    def load(self, path: str) -> None:
        """Load a persisted model and metadata from joblib."""
        _require_lightgbm()

        model_path = Path(path).expanduser().resolve()
        if not model_path.exists():
            raise FileNotFoundError(f"Classifier model file not found: {model_path}")

        payload = joblib.load(model_path)
        if not isinstance(payload, dict) or "model" not in payload:
            raise ValueError(f"Invalid classifier payload in {model_path}")

        self.model = payload["model"]
        self.mode = str(payload.get("mode", "binary"))
        default_class_names = _MULTICLASS_CLASS_NAMES if self.mode == "multiclass" else _BINARY_CLASS_NAMES
        self.class_names = list(payload.get("class_names", default_class_names))
        self.feature_names = list(payload.get("feature_names", FEATURE_NAMES))
        self.threshold = float(payload.get("threshold", _DEFAULT_THRESHOLD))
        self.training_metrics = dict(payload.get("training_metrics", {}))
        log.info("depth_radar.classifier.loaded", extra={"path": str(model_path), "mode": self.mode})

    def _require_model(self) -> Any:
        _require_lightgbm()
        if self.model is None:
            raise RuntimeError("No classifier model is loaded. Train a model or pass model_path to WallClassifier().")
        return self.model

    def _sort_temporally(self, frame: pd.DataFrame) -> pd.DataFrame:
        sort_ts = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True)
        if sort_ts.notna().any():
            return frame.assign(_sort_ts=sort_ts).sort_values("_sort_ts", kind="stable").drop(columns="_sort_ts")

        log.warning("depth_radar.classifier.timestamp_parse_failed")
        return frame.sort_values("timestamp", kind="stable")

    def _build_targets(self, frame: pd.DataFrame, mode: str) -> np.ndarray:
        labels = frame["label"].astype(str).str.upper()
        if mode == "binary":
            return (labels == "SPOOF").astype(np.int8).to_numpy()

        unknown_labels = sorted(set(labels.unique()) - set(_MULTICLASS_LABEL_TO_ID))
        if unknown_labels:
            raise ValueError(f"Unsupported labels for multiclass training: {unknown_labels}")
        return labels.map(_MULTICLASS_LABEL_TO_ID).astype(np.int8).to_numpy()

    @staticmethod
    def _compute_sample_weights(targets: np.ndarray, expected_classes: list[int] | None = None) -> np.ndarray:
        unique, counts = np.unique(targets, return_counts=True)
        observed_counts = {int(label): int(count) for label, count in zip(unique, counts, strict=False)}
        if expected_classes is not None:
            missing = [label for label in expected_classes if label not in observed_counts]
            if missing:
                raise ValueError(
                    f"Training split must contain every class after temporal split. Missing classes: {missing}"
                )
        total = len(targets)
        num_classes = len(observed_counts)
        class_weights = {
            label: total / (num_classes * count)
            for label, count in observed_counts.items()
        }
        return np.asarray([class_weights[int(label)] for label in targets], dtype=np.float64)

    def _build_binary_training_params(self, y_train: np.ndarray) -> tuple[dict[str, Any], np.ndarray | None]:
        pos_count = int(y_train.sum())
        neg_count = int(len(y_train) - pos_count)
        if pos_count == 0 or neg_count == 0:
            raise ValueError(
                "Training split must contain both SPOOF and NOT_SPOOF examples after temporal split."
            )

        params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "scale_pos_weight": neg_count / pos_count,
            "verbose": -1,
        }
        return params, None

    def _build_multiclass_training_params(self, y_train: np.ndarray) -> tuple[dict[str, Any], np.ndarray]:
        params = {
            "objective": "multiclass",
            "num_class": 4,
            "metric": "multi_logloss",
            "boosting_type": "gbdt",
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "verbose": -1,
        }
        sample_weight = self._compute_sample_weights(y_train, expected_classes=list(range(4)))
        return params, sample_weight

    def _build_metrics(
        self,
        model: Any,
        X_test: np.ndarray,
        y_test: np.ndarray,
        mode: str,
        class_names: list[str],
    ) -> dict[str, Any]:
        if mode == "binary":
            y_prob = np.asarray(model.predict(X_test), dtype=np.float64).reshape(-1)
            y_pred = (y_prob >= self.threshold).astype(np.int8)
            return {
                "f1": float(f1_score(y_test, y_pred, zero_division=0)),
                "precision": float(precision_score(y_test, y_pred, zero_division=0)),
                "recall": float(recall_score(y_test, y_pred, zero_division=0)),
                "accuracy": float(accuracy_score(y_test, y_pred)),
                "confusion_matrix": confusion_matrix(y_test, y_pred, labels=[0, 1]).tolist(),
                "feature_importance": {
                    name: float(importance)
                    for name, importance in zip(
                        self.feature_names,
                        model.feature_importance(importance_type="gain"),
                        strict=False,
                    )
                },
            }

        probability_rows = self._coerce_multiclass_probabilities(
            np.asarray(model.predict(X_test), dtype=np.float64),
            len(X_test),
        )
        y_pred = np.argmax(probability_rows, axis=1).astype(np.int8)
        per_class_report = classification_report(
            y_test,
            y_pred,
            labels=list(range(len(class_names))),
            target_names=class_names,
            output_dict=True,
            zero_division=0,
        )
        weighted_f1 = float(f1_score(y_test, y_pred, average="weighted", zero_division=0))
        weighted_precision = float(precision_score(y_test, y_pred, average="weighted", zero_division=0))
        weighted_recall = float(recall_score(y_test, y_pred, average="weighted", zero_division=0))
        return {
            "f1": weighted_f1,
            "weighted_f1": weighted_f1,
            "precision": weighted_precision,
            "recall": weighted_recall,
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "confusion_matrix": confusion_matrix(y_test, y_pred, labels=list(range(len(class_names)))).tolist(),
            "per_class": {
                class_name: {
                    "precision": float(per_class_report[class_name]["precision"]),
                    "recall": float(per_class_report[class_name]["recall"]),
                    "f1": float(per_class_report[class_name]["f1-score"]),
                    "support": int(per_class_report[class_name]["support"]),
                }
                for class_name in class_names
            },
            "feature_importance": {
                name: float(importance)
                for name, importance in zip(
                    self.feature_names,
                    model.feature_importance(importance_type="gain"),
                    strict=False,
                )
            },
        }

    @staticmethod
    def _coerce_multiclass_probabilities(probabilities: np.ndarray, rows: int) -> np.ndarray:
        if probabilities.ndim == 1:
            if probabilities.size != rows * len(_MULTICLASS_CLASS_NAMES):
                raise ValueError(
                    f"Unexpected multiclass probability shape: {probabilities.shape} for {rows} rows."
                )
            return probabilities.reshape(rows, len(_MULTICLASS_CLASS_NAMES))
        if probabilities.ndim == 2 and probabilities.shape[1] == len(_MULTICLASS_CLASS_NAMES):
            return probabilities
        raise ValueError(f"Unexpected multiclass probability shape: {probabilities.shape}")

    def _has_verified_binary_gate(self) -> bool:
        if self.mode != "binary":
            return False
        return float(self.training_metrics.get("f1", 0.0)) > _EXIT_GATE_F1

    def _build_feature_matrix(self, frame: pd.DataFrame) -> np.ndarray:
        extractor = WallFeatureExtractor(normalize=False)
        average_wall_size = float(pd.to_numeric(frame.get("original_size"), errors="coerce").mean()) if "original_size" in frame.columns else 1.0
        average_wall_size = max(average_wall_size, 1.0)

        rows: list[np.ndarray] = []
        for record in frame.to_dict(orient="records"):
            wall_data = {
                "time_in_book": self._as_float(record, "time_in_book", fallback_keys=("duration_sec",)),
                "modification_count": self._as_float(record, "modification_count"),
                "cancellation_count": self._as_float(
                    record,
                    "cancellation_count",
                    fallback_keys=("cancellation_events",),
                ),
                "original_size": self._as_float(record, "original_size"),
                "max_size": self._as_float(record, "max_size", fallback_keys=("original_size",)),
                "current_size": self._as_float(record, "current_size"),
                "refill_count": self._as_float(record, "refill_count"),
                "price_crossed": self._as_bool(record.get("price_crossed", False)),
                "side": self._encode_side(record.get("side")),
                "wall_price": self._as_float(record, "wall_price", fallback_keys=("price",)),
            }
            wall_price = float(wall_data["wall_price"])
            market_context = {
                "mid_price": self._as_float(record, "mid_price", default=wall_price),
                "best_bid": self._as_float(record, "best_bid", default=wall_price),
                "best_ask": self._as_float(record, "best_ask", default=wall_price),
                "spread": self._as_float(record, "spread"),
                "avg_wall_size": self._as_float(record, "avg_wall_size", default=average_wall_size),
                "bid_volumes": self._coerce_levels(record.get("bid_volumes")),
                "ask_volumes": self._coerce_levels(record.get("ask_volumes")),
            }
            rows.append(extractor.extract(wall_data, market_context))

        if not rows:
            raise ValueError("No feature rows could be built from the labeled wall dataset.")

        return np.stack(rows, axis=0)

    def _coerce_feature_matrix(self, features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim == 1:
            if matrix.shape[0] != NUM_FEATURES:
                raise ValueError(f"Expected {NUM_FEATURES} features, got {matrix.shape[0]}.")
            matrix = matrix.reshape(1, -1)
        elif matrix.ndim == 2:
            if matrix.shape[1] != NUM_FEATURES:
                raise ValueError(f"Expected feature matrix with width {NUM_FEATURES}, got {matrix.shape[1]}.")
        else:
            raise ValueError("Features must be a 1D or 2D numpy array.")
        return matrix

    @staticmethod
    def _as_float(
        record: dict[str, Any],
        key: str,
        default: float = 0.0,
        fallback_keys: tuple[str, ...] = (),
    ) -> float:
        keys = (key, *fallback_keys)
        for candidate in keys:
            value = record.get(candidate)
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            try:
                if pd.isna(value):
                    continue
            except TypeError:
                pass
            return float(value)
        return float(default)

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return bool(value)

    @staticmethod
    def _encode_side(value: Any) -> int:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered == "ask":
                return 1
            if lowered == "bid":
                return 0
        try:
            return 1 if int(value) == 1 else 0
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _coerce_levels(value: Any) -> list[float]:
        if value is None:
            return []
        if isinstance(value, np.ndarray):
            return [float(item) for item in value.tolist()]
        if isinstance(value, (list, tuple)):
            return [float(item) for item in value]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                try:
                    parsed = ast.literal_eval(text)
                except (SyntaxError, ValueError):
                    parsed = [part.strip() for part in text.split(",") if part.strip()]
            if isinstance(parsed, (list, tuple, np.ndarray)):
                return [float(item) for item in parsed]
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Train wall classifier")
    parser.add_argument("--data", required=True, help="Labeled walls parquet")
    parser.add_argument("--output", default="deep6/models/depth_radar_classifier.joblib")
    parser.add_argument("--mode", choices=["binary", "multiclass"], default="binary")
    args = parser.parse_args()

    classifier = WallClassifier()
    metrics = classifier.train(args.data, mode=args.mode)
    classifier.save(args.output)
    print(f"Training complete. F1={metrics['f1']:.4f}")
