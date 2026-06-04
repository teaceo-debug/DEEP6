"""deep6.ml — LightGBM meta-learner and optional HMM regime detector."""
from deep6.ml.feature_builder import FEATURE_NAMES, build_feature_matrix
from deep6.ml.lgbm_trainer import LGBMTrainer, WeightFile

try:
    from deep6.ml.hmm_regime import HMMRegimeDetector, RegimeState
except ImportError:  # pragma: no cover - optional dependency guard
    HMMRegimeDetector = None  # type: ignore[assignment]
    RegimeState = None  # type: ignore[assignment]

__all__ = [
    "FEATURE_NAMES",
    "build_feature_matrix",
    "LGBMTrainer",
    "WeightFile",
    "HMMRegimeDetector",
    "RegimeState",
]
