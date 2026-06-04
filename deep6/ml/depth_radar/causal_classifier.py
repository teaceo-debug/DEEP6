"""V4 causal wall classifier for live Depth Radar inference."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from deep6.ml.depth_radar.causal_features import CAUSAL_FEATURE_NAMES, NUM_CAUSAL_FEATURES


log = logging.getLogger(__name__)

DEFAULT_INTENT_MODEL = "deep6/models/intent_classifier_v4.joblib"
DEFAULT_INTERACTION_MODEL = "deep6/models/interaction_predictor_v4.joblib"
_DEFAULT_FALLBACK_INTENT = "PASSIVE_REAL"
_DEFAULT_FALLBACK_CONFIDENCE = 0.7


class CausalClassifier:
    """V4 classifier using trained LightGBM models on 44 causal features."""

    def __init__(
        self,
        intent_model_path: str | None = DEFAULT_INTENT_MODEL,
        interaction_model_path: str | None = DEFAULT_INTERACTION_MODEL,
    ) -> None:
        self._intent_model: Any | None = None
        self._interaction_model: Any | None = None
        self._intent_class_names: list[str] = []
        self._interaction_class_names: list[str] = []
        self._intent_feature_names = list(CAUSAL_FEATURE_NAMES)
        self._interaction_feature_names = list(CAUSAL_FEATURE_NAMES)
        self._intent_model_path: Path | None = None
        self._interaction_model_path: Path | None = None

        self._load_intent_model(intent_model_path)
        self._load_interaction_model(interaction_model_path)

    @property
    def intent_model_loaded(self) -> bool:
        return self._intent_model is not None

    @property
    def interaction_model_loaded(self) -> bool:
        return self._interaction_model is not None

    def classify_intent(self, features: np.ndarray) -> tuple[str, float, dict[str, float]]:
        """Classify wall intent from 44 causal features."""
        if not self.intent_model_loaded:
            return (
                _DEFAULT_FALLBACK_INTENT,
                _DEFAULT_FALLBACK_CONFIDENCE,
                {_DEFAULT_FALLBACK_INTENT: _DEFAULT_FALLBACK_CONFIDENCE},
            )

        row = self._coerce_feature_vector(features)
        probabilities = self._predict_probabilities(
            model=self._intent_model,
            class_names=self._intent_class_names,
            features=row,
        )
        return self._probabilities_to_result(probabilities, self._intent_class_names)

    def predict_interaction(self, features: np.ndarray) -> tuple[str, float, dict[str, float]] | None:
        """Predict BOUNCE/BREAK/CHURN from 44 causal features."""
        if not self.interaction_model_loaded:
            return None

        row = self._coerce_feature_vector(features)
        probabilities = self._predict_probabilities(
            model=self._interaction_model,
            class_names=self._interaction_class_names,
            features=row,
        )
        return self._probabilities_to_result(probabilities, self._interaction_class_names)

    def classify_wall(self, wall_dict: dict) -> dict:
        """Classify a live MBOWallEngine wall dict and return an enriched copy."""
        enriched = dict(wall_dict)
        features = self._features_from_wall(enriched)

        try:
            if self.intent_model_loaded:
                intent, confidence, probs = self.classify_intent(features)
            else:
                intent = str(enriched.get("intent", _DEFAULT_FALLBACK_INTENT))
                confidence = _DEFAULT_FALLBACK_CONFIDENCE
                probs = {intent: confidence}
        except Exception:
            log.exception("depth_radar.causal_classifier.intent_inference_failed")
            intent = str(enriched.get("intent", _DEFAULT_FALLBACK_INTENT))
            confidence = _DEFAULT_FALLBACK_CONFIDENCE
            probs = {intent: confidence}

        enriched["intent"] = intent
        enriched["confidence"] = float(confidence)
        enriched["intent_confidence"] = float(confidence)
        enriched["intent_probs"] = probs

        try:
            interaction = self.predict_interaction(features)
        except Exception:
            log.exception("depth_radar.causal_classifier.interaction_inference_failed")
            interaction = None
        if interaction is not None:
            label, interaction_confidence, interaction_probs = interaction
            enriched["interaction"] = label
            enriched["interaction_confidence"] = float(interaction_confidence)
            enriched["interaction_probs"] = interaction_probs

        return enriched

    def _load_intent_model(self, model_path: str | None) -> None:
        payload = self._safe_load_payload(model_path, model_kind="intent")
        if payload is None:
            return
        self._intent_model = payload["model"]
        self._intent_class_names = payload["class_names"]
        self._intent_feature_names = payload["feature_names"]
        self._intent_model_path = payload["path"]

    def _load_interaction_model(self, model_path: str | None) -> None:
        payload = self._safe_load_payload(model_path, model_kind="interaction")
        if payload is None:
            return
        self._interaction_model = payload["model"]
        self._interaction_class_names = payload["class_names"]
        self._interaction_feature_names = payload["feature_names"]
        self._interaction_model_path = payload["path"]

    def _safe_load_payload(self, model_path: str | None, model_kind: str) -> dict[str, Any] | None:
        if not model_path:
            return None

        resolved = Path(model_path).expanduser().resolve()
        if not resolved.exists():
            log.info("depth_radar.causal_classifier.%s_model_missing path=%s", model_kind, resolved)
            return None

        try:
            payload = joblib.load(resolved)
        except FileNotFoundError:
            log.info("depth_radar.causal_classifier.%s_model_missing path=%s", model_kind, resolved)
            return None
        except Exception:
            log.exception("depth_radar.causal_classifier.%s_model_load_failed path=%s", model_kind, resolved)
            return None

        if not isinstance(payload, dict) or "model" not in payload:
            log.warning("depth_radar.causal_classifier.%s_model_invalid path=%s", model_kind, resolved)
            return None

        class_names = [str(name) for name in payload.get("class_names", [])]
        feature_names = [str(name) for name in payload.get("feature_names", CAUSAL_FEATURE_NAMES)]
        if not class_names:
            log.warning("depth_radar.causal_classifier.%s_model_missing_classes path=%s", model_kind, resolved)
            return None
        if len(feature_names) != NUM_CAUSAL_FEATURES:
            log.warning(
                "depth_radar.causal_classifier.%s_model_feature_mismatch path=%s expected=%d actual=%d",
                model_kind,
                resolved,
                NUM_CAUSAL_FEATURES,
                len(feature_names),
            )
            return None
        if feature_names != list(CAUSAL_FEATURE_NAMES):
            log.warning(
                "depth_radar.causal_classifier.%s_model_feature_order_mismatch path=%s",
                model_kind,
                resolved,
            )
            return None

        log.info(
            "depth_radar.causal_classifier.%s_model_loaded path=%s version=%s",
            model_kind,
            resolved,
            payload.get("version", "unknown"),
        )
        return {
            "model": payload["model"],
            "class_names": class_names,
            "feature_names": feature_names,
            "path": resolved,
        }

    def _features_from_wall(self, wall_dict: dict[str, Any]) -> np.ndarray:
        return np.asarray(
            [float(wall_dict.get(name, 0.0) or 0.0) for name in CAUSAL_FEATURE_NAMES],
            dtype=np.float64,
        )

    @staticmethod
    def _coerce_feature_vector(features: np.ndarray) -> np.ndarray:
        matrix = np.asarray(features, dtype=np.float64)
        if matrix.ndim == 1:
            if matrix.shape[0] != NUM_CAUSAL_FEATURES:
                raise ValueError(
                    f"Expected {NUM_CAUSAL_FEATURES} causal features, got shape {matrix.shape}."
                )
            return matrix.reshape(1, -1)
        if matrix.ndim == 2 and matrix.shape == (1, NUM_CAUSAL_FEATURES):
            return matrix
        raise ValueError(
            f"Expected feature vector shape ({NUM_CAUSAL_FEATURES},) or (1, {NUM_CAUSAL_FEATURES}), got {matrix.shape}."
        )

    @staticmethod
    def _predict_probabilities(model: Any, class_names: list[str], features: np.ndarray) -> np.ndarray:
        probabilities = np.asarray(model.predict(features), dtype=np.float64)
        if probabilities.ndim == 1:
            if probabilities.size != len(class_names):
                raise ValueError(
                    f"Unexpected probability shape {probabilities.shape} for {len(class_names)} classes."
                )
            return probabilities
        if probabilities.ndim == 2 and probabilities.shape == (1, len(class_names)):
            return probabilities[0]
        raise ValueError(f"Unexpected probability shape {probabilities.shape} for classifier output.")

    @staticmethod
    def _probabilities_to_result(probabilities: np.ndarray, class_names: list[str]) -> tuple[str, float, dict[str, float]]:
        label_index = int(np.argmax(probabilities))
        label = class_names[label_index]
        probs = {
            class_name: float(prob)
            for class_name, prob in zip(class_names, probabilities.tolist(), strict=False)
        }
        return label, float(probabilities[label_index]), probs


__all__ = ["CausalClassifier", "DEFAULT_INTENT_MODEL", "DEFAULT_INTERACTION_MODEL"]
