"""LightGBM meta-learner training pipeline.

Trains a binary classifier on signal_events + trade_events from EventStore.
Derives per-signal category weights from LightGBM feature importance.

Key constraints (from context decisions):
- D-07: _train_sync is synchronous; called exclusively via run_in_executor.
         Never use async def / await inside _train_sync.
- D-08: Model persisted as pickle (deep6_model.pkl) + JSON metadata.
- D-15: Single-signal weight cannot exceed 3x baseline (weight_cap).
- T-09-05: SHA256 checksum of model file stored in meta JSON; verified on load.
- T-09-07: _train_sync called via executor — document this clearly.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import pickle
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    import lightgbm as lgb
except ImportError as e:
    raise ImportError("lightgbm required: pip install lightgbm") from e

import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from deep6.ml.feature_builder import (
    FEATURE_NAMES,
    build_feature_matrix,
)

log = logging.getLogger(__name__)

# The 8 category features used for weight derivation
_CATEGORY_FEATURES = [
    "cat_absorption",
    "cat_exhaustion",
    "cat_trapped",
    "cat_delta",
    "cat_imbalance",
    "cat_volume_profile",
    "cat_auction",
    "cat_poc",
]
# Map feature name → signal name (cat_absorption → absorption)
_FEATURE_TO_SIGNAL = {f: f.replace("cat_", "") for f in _CATEGORY_FEATURES}

_MIN_SAMPLES = 50  # Minimum labeled samples required to train


@dataclass
class WeightFile:
    """Result of one training run — weights + metadata.

    weights: per-signal multiplier (1.0 = baseline, capped at weight_cap).
    regime_adjustments: regime → {signal → adjustment}  (empty until HMM Phase integration).
    feature_importances: raw LightGBM gain importance for all 47 features.
    training_date: ISO date string.
    n_samples: number of labeled training samples used.
    metrics: accuracy, precision, recall, roc_auc (on hold-out set).
    wfe: Walk-Forward Efficiency — None until walk_forward.py integration.
    model_path: absolute path to the pickle file.
    model_checksum: SHA256 hex digest of the model file (T-09-05).
    """

    weights: dict[str, float]
    regime_adjustments: dict[str, dict[str, float]]
    feature_importances: dict[str, float]
    training_date: str
    n_samples: int
    metrics: dict[str, float]
    wfe: float | None
    model_path: str
    model_checksum: str = ""

    def to_json(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (excludes model_path for portability)."""
        d = asdict(self)
        # model_path is environment-specific; exclude from portable JSON
        d.pop("model_path", None)
        return d


def _sha256_file(path: str) -> str:
    """Compute SHA256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class LGBMTrainer:
    """LightGBM meta-learner trainer.

    Usage (inside async context):
        trainer = LGBMTrainer(store, model_path="./deep6_model.pkl")
        weight_file = await trainer.train()

    IMPORTANT — D-07 / T-09-07:
        _train_sync is a pure synchronous method. It is always called via
        asyncio.get_event_loop().run_in_executor(None, ...) and must never
        contain await / async def. Violating this constraint will block the
        event loop at 1,000+ DOM callbacks/sec.
    """

    def __init__(
        self,
        store: Any,  # EventStore — typed as Any to avoid circular import
        model_path: str = "./deep6_model.pkl",
        meta_path: str = "./deep6_model_meta.json",
        weight_cap: float = 3.0,
    ) -> None:
        self.store = store
        self.model_path = str(Path(model_path).expanduser().resolve())
        self.meta_path = str(Path(meta_path).expanduser().resolve())
        self.weight_cap = weight_cap

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def train(self) -> WeightFile | None:
        """Fetch data from EventStore and train the meta-learner.

        Runs training in ThreadPoolExecutor (D-07) to avoid blocking the loop.

        Returns:
            WeightFile on success, None if insufficient data (< 50 labeled samples).
        """
        signal_rows = await self.store.fetch_signal_events(limit=5000)
        trade_rows = await self.store.fetch_trade_events(limit=2000)

        loop = asyncio.get_event_loop()
        result: WeightFile | None = await loop.run_in_executor(
            None,
            self._train_sync,
            signal_rows,
            trade_rows,
        )
        return result

    async def load_current_weights(self) -> WeightFile | None:
        """Load the most recent WeightFile from the meta JSON, if it exists.

        Verifies model file checksum against stored SHA256 (T-09-05).

        Returns:
            WeightFile if meta JSON and model file both exist and checksum passes,
            None otherwise.
        """
        meta_path = Path(self.meta_path)
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "r") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("lgbm.load_weights.failed", extra={"exc": str(exc)})
            return None

        model_path = self.model_path
        model_checksum = data.get("model_checksum", "")

        # T-09-05: Verify checksum before loading pickle
        if model_checksum and Path(model_path).exists():
            actual = _sha256_file(model_path)
            if actual != model_checksum:
                log.error(
                    "lgbm.checksum_mismatch",
                    extra={"expected": model_checksum, "actual": actual},
                )
                return None

        return WeightFile(
            weights=data.get("weights", {}),
            regime_adjustments=data.get("regime_adjustments", {}),
            feature_importances=data.get("feature_importances", {}),
            training_date=data.get("training_date", ""),
            n_samples=int(data.get("n_samples", 0)),
            metrics=data.get("metrics", {}),
            wfe=data.get("wfe"),
            model_path=model_path,
            model_checksum=model_checksum,
        )

    # ------------------------------------------------------------------
    # Private sync implementation — MUST remain sync (D-07)
    # ------------------------------------------------------------------

    def _train_sync(
        self,
        signal_rows: list[dict],
        trade_rows: list[dict],
    ) -> WeightFile | None:
        """Pure synchronous training implementation.

        Called exclusively via run_in_executor — do NOT use await here.

        Steps:
        1. Build feature matrix via feature_builder.
        2. Guard: require >= _MIN_SAMPLES labeled samples.
        3. Train LGBMClassifier (80/20 train/val split).
        4. Compute hold-out metrics.
        5. Derive per-signal weights from category feature importances (D-15).
        6. Persist model (pickle) + metadata (JSON).
        7. Return WeightFile.

        Returns:
            WeightFile on success, None if < _MIN_SAMPLES samples.
        """
        X, y = build_feature_matrix(signal_rows, trade_rows)

        if len(X) < _MIN_SAMPLES:
            log.info(
                "lgbm.train.skipped_insufficient_data",
                extra={"n_samples": len(X), "minimum": _MIN_SAMPLES},
            )
            return None

        # --- Train / validation split ---
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y if y.sum() > 1 else None
        )

        model = lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,  # suppress LightGBM stdout
        )
        model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(20, verbose=False), lgb.log_evaluation(-1)],
        )

        # --- Hold-out metrics ---
        # Use booster directly to avoid sklearn feature-name mismatch warnings
        # when predicting on plain numpy arrays.
        booster = model.booster_
        y_prob = booster.predict(X_val)          # shape (N,) — float probabilities
        y_pred = (y_prob >= 0.5).astype(int)
        metrics: dict[str, float] = {
            "accuracy": float(accuracy_score(y_val, y_pred)),
            "precision": float(precision_score(y_val, y_pred, zero_division=0)),
            "recall": float(recall_score(y_val, y_pred, zero_division=0)),
        }
        if len(np.unique(y_val)) > 1:
            metrics["roc_auc"] = float(roc_auc_score(y_val, y_prob))
        else:
            metrics["roc_auc"] = 0.5

        # --- Feature importances (all 47) ---
        raw_importances = model.feature_importances_  # array shape (47,)
        feature_importances = {
            name: float(raw_importances[i]) for i, name in enumerate(FEATURE_NAMES)
        }

        # --- Derive per-signal weights from category feature importances (D-15) ---
        cat_importances = {
            f: float(raw_importances[FEATURE_NAMES.index(f)]) for f in _CATEGORY_FEATURES
        }
        total_imp = sum(cat_importances.values()) or 1.0
        mean_imp = total_imp / len(cat_importances)
        signal_weights: dict[str, float] = {
            _FEATURE_TO_SIGNAL[feat]: min(imp / mean_imp, self.weight_cap)
            for feat, imp in cat_importances.items()
        }

        # --- Persist model (pickle) ---
        Path(self.model_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self.model_path, "wb") as fh:
            pickle.dump(model, fh, protocol=pickle.HIGHEST_PROTOCOL)

        # T-09-05: Compute and store checksum
        checksum = _sha256_file(self.model_path)

        weight_file = WeightFile(
            weights=signal_weights,
            regime_adjustments={},  # Populated in Phase 9 Plan 03 after HMM integration
            feature_importances=feature_importances,
            training_date=time.strftime("%Y-%m-%d", time.gmtime()),
            n_samples=len(X),
            metrics=metrics,
            wfe=None,
            model_path=self.model_path,
            model_checksum=checksum,
        )

        # --- Persist metadata (JSON) ---
        Path(self.meta_path).parent.mkdir(parents=True, exist_ok=True)
        meta_dict = weight_file.to_json()
        meta_dict["model_checksum"] = checksum  # Re-add for storage
        with open(self.meta_path, "w") as fh:
            json.dump(meta_dict, fh, indent=2)

        log.info(
            "lgbm.train.complete",
            extra={
                "n_samples": len(X),
                "accuracy": metrics["accuracy"],
                "roc_auc": metrics["roc_auc"],
            },
        )

        return weight_file
