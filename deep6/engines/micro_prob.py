"""E5 MicroEngine — ENG-05. Naive Bayes micro probability for next-tick direction.

Combines three decorrelated binary features using heuristic Naive Bayes:
  1. E2 trespass direction (DOM queue imbalance)
  2. E4 iceberg presence and direction
  3. Imbalance direction from narrative engine

Output: probability 0-1 for next-tick directional move. Used for execution timing,
NOT for trade signal generation (D-12).

Per D-11: Each feature contributes independently (Naive Bayes assumption).
Per D-13: Returns 0.5 (neutral) when DOM unavailable or all inputs neutral.
Per T-04-09: Denominator guard when both P_bull and P_bear collapse to near-zero.

Usage:
    engine = MicroEngine()
    result = engine.process(
        trespass=trespass_result,     # TrespassResult or None
        iceberg_signals=[...],        # list[IcebergSignal] or []
        imbalance_direction=+1,       # -1, 0, or +1
    )
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from deep6.engines.signal_config import MicroConfig
from deep6.engines.trespass import TrespassResult


@dataclass
class MicroResult:
    """Result from MicroEngine.process().

    Fields:
        probability:    Float in [0, 1] — probability of bullish next-tick direction.
                        0.5 = neutral (no signal or DOM unavailable).
        direction:      +1 bull, -1 bear, 0 neutral (based on bull/bear thresholds).
        feature_count:  Number of active (non-neutral) features in this computation.
        detail:         Diagnostic string showing feature contributions.
    """
    probability: float
    direction: int
    feature_count: int
    detail: str


# Pre-built neutral result (D-13: DOM unavailable fallback)
_NEUTRAL_UNAVAILABLE = MicroResult(
    probability=0.5,
    direction=0,
    feature_count=0,
    detail="DOM_UNAVAILABLE",
)


class MicroEngine:
    """E5 Naive Bayes micro probability engine (ENG-05).

    Stateless and re-entrant — all inputs passed as arguments.
    Instantiated once at startup, reused for every bar close.

    The Naive Bayes computation:
      For each active feature with direction d ∈ {+1, -1}:
        P_bull *= bull_likelihood  if d == +1
        P_bull *= (1 - bull_likelihood)  if d == -1
        P_bear = symmetrically opposite

      Final probability = P_bull / (P_bull + P_bear)

    Where bull_likelihood (default 0.65) = P(feature direction = bull | market is bull).
    """

    def __init__(self, config: MicroConfig | None = None) -> None:
        self.config = config if config is not None else MicroConfig()

    def process(
        self,
        trespass: Optional[TrespassResult],
        iceberg_signals: list,
        imbalance_direction: int,
    ) -> MicroResult:
        """Compute Naive Bayes micro probability from decorrelated DOM features.

        Args:
            trespass:            TrespassResult from E2 engine, or None if unavailable.
            iceberg_signals:     List of IcebergSignal from E4 engine (may be empty).
            imbalance_direction: Directional bias from narrative engine (-1, 0, +1).

        Returns:
            MicroResult with probability, direction, feature_count, detail.
            Returns neutral (0.5, direction=0) if all features are neutral or DOM
            is unavailable (D-13).
        """
        cfg = self.config

        # Collect active feature directions
        features: list[tuple[str, int]] = []

        # Feature 1: E2 DOM queue imbalance direction
        if trespass is not None and trespass.direction != 0:
            features.append(("trespass", trespass.direction))

        # Feature 2: E4 iceberg presence and direction
        if iceberg_signals:
            # Aggregate iceberg direction: majority vote across all signals
            iceberg_dir_sum = sum(
                getattr(sig, "direction", 0) for sig in iceberg_signals
            )
            if iceberg_dir_sum > 0:
                features.append(("iceberg", +1))
            elif iceberg_dir_sum < 0:
                features.append(("iceberg", -1))

        # Feature 3: Imbalance direction from narrative
        if imbalance_direction != 0:
            features.append(("imbalance", imbalance_direction))

        # D-13: No active features → neutral fallback
        if not features:
            return _NEUTRAL_UNAVAILABLE

        # Naive Bayes computation
        p_bull = 1.0
        p_bear = 1.0
        L = cfg.bull_likelihood       # P(feature=bull | market=bull)
        L_inv = 1.0 - L              # P(feature=bear | market=bull)

        for name, direction in features:
            if direction == +1:
                p_bull *= L
                p_bear *= L_inv
            elif direction == -1:
                p_bull *= L_inv
                p_bear *= L

        # T-04-09: Denominator guard — prevent div-by-zero on near-zero collapse
        denom = p_bull + p_bear
        if denom < 1e-9:
            probability = 0.5
        else:
            probability = p_bull / denom

        # Clamp to [0, 1] (floating point safety)
        probability = max(0.0, min(1.0, probability))

        # Direction from thresholds
        if probability >= cfg.bull_threshold:
            direction_out = +1
        elif probability <= cfg.bear_threshold:
            direction_out = -1
        else:
            direction_out = 0

        # Build detail string
        feature_str = ", ".join(f"{n}={d:+d}" for n, d in features)
        detail = (
            f"p_bull={p_bull:.4f}, p_bear={p_bear:.4f} → prob={probability:.3f}; "
            f"features=[{feature_str}]"
        )

        return MicroResult(
            probability=probability,
            direction=direction_out,
            feature_count=len(features),
            detail=detail,
        )
