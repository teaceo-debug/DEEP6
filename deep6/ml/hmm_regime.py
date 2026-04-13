"""3-state Gaussian HMM regime detector.

States:
  ABSORPTION_FRIENDLY — Low vol, balanced flow (optimal for absorption/exhaustion signals)
  TRENDING            — Directional delta, expanding range
  CHAOTIC             — High vol, wide spread (absorption signals unreliable)

Features used (5-dimensional):
  [atr_ratio, spread_proxy, trade_rate, delta_abs_mean, range_to_atr]

Per D-09: GaussianHMM on (ATR_ratio, spread, trade_rate, delta_abs_mean, range_to_atr).
Per D-11: Online Viterbi decoding per bar via predict_current().
Per D-12: Nightly retrain on rolling 30-day window via async retrain().
Per T-09-08: Regime transitions logged with structlog (log.info).
Per T-09-07 pattern: retrain() calls fit() in run_in_executor — never blocks event loop.
"""
from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Any

try:
    from hmmlearn.hmm import GaussianHMM
except ImportError as e:
    raise ImportError("hmmlearn required: pip install hmmlearn") from e

import numpy as np

log = logging.getLogger(__name__)

_MIN_ROWS_FOR_FIT = 30   # Minimum signal rows required to train HMM
_N_HMM_FEATURES = 5     # Dimensionality of the HMM observation space


class RegimeState(str, Enum):
    """Market regime states decoded by the Gaussian HMM."""
    ABSORPTION_FRIENDLY = "ABSORPTION_FRIENDLY"   # Low vol, balanced flow
    TRENDING = "TRENDING"                          # Directional delta, expanding range
    CHAOTIC = "CHAOTIC"                            # High vol, wide spread


def _extract_hmm_features(signal_rows: list[dict]) -> np.ndarray:
    """Build (N, 5) float32 observation matrix for GaussianHMM.

    Columns:
      0  atr_ratio         = total_score / 100.0  (proxy until ATR available)
      1  spread_proxy      = 1.0 - engine_agreement  (lower agreement = wider spread)
      2  trade_rate        = category_count / 8.0  (normalized signal density)
      3  delta_abs_mean    = abs(direction) * engine_agreement
      4  range_to_atr      = (total_score / 100.0) * (category_count / 8.0)  (composite)

    Args:
        signal_rows: list of dicts from EventStore.fetch_signal_events()

    Returns:
        np.ndarray of shape (N, 5), dtype float32.
    """
    if not signal_rows:
        return np.zeros((0, _N_HMM_FEATURES), dtype=np.float32)

    n = len(signal_rows)
    X = np.zeros((n, _N_HMM_FEATURES), dtype=np.float32)

    for i, row in enumerate(signal_rows):
        total_score = float(row.get("total_score") or 0.0)
        engine_agreement = float(row.get("engine_agreement") or 0.0)
        category_count = float(row.get("category_count") or 0)
        direction = float(row.get("direction") or 0)

        atr_ratio = total_score / 100.0
        spread_proxy = 1.0 - engine_agreement
        trade_rate = category_count / 8.0
        delta_abs_mean = abs(direction) * engine_agreement
        range_to_atr = atr_ratio * trade_rate

        X[i] = [atr_ratio, spread_proxy, trade_rate, delta_abs_mean, range_to_atr]

    return X


class HMMRegimeDetector:
    """3-state Gaussian HMM for market regime detection.

    State mapping is determined after fitting by examining mean vectors:
      - Lowest spread_proxy mean  → ABSORPTION_FRIENDLY
      - Highest delta_abs_mean    → TRENDING
      - Highest spread_proxy mean → CHAOTIC

    Typical usage:
        detector = HMMRegimeDetector()
        detector.fit(signal_rows)
        regime = detector.predict_current(recent_rows[-20:])
    """

    def __init__(
        self,
        n_states: int = 3,
        covariance_type: str = "full",
        n_iter: int = 100,
        random_state: int = 42,
    ) -> None:
        self._n_states = n_states
        self._covariance_type = covariance_type
        self._n_iter = n_iter
        self._random_state = random_state
        self._model: GaussianHMM | None = None
        # Maps HMM hidden state index (0..n_states-1) → RegimeState
        self._state_map: dict[int, RegimeState] = {}
        self._prev_regime: RegimeState | None = None  # For T-09-08 transition logging

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def is_fitted(self) -> bool:
        """Return True if the model has been trained at least once."""
        return self._model is not None

    def fit(self, signal_rows: list[dict]) -> None:
        """Train the 3-state Gaussian HMM on signal_rows.

        Minimum _MIN_ROWS_FOR_FIT rows required. Silently returns if
        insufficient data (safe to call speculatively).

        State-to-regime mapping uses mean vectors after fitting:
          - Lowest spread_proxy mean  → ABSORPTION_FRIENDLY
          - Highest delta_abs_mean    → TRENDING
          - Highest spread_proxy mean → CHAOTIC

        D-07 pattern: this is a synchronous method designed to be called
        from retrain() via run_in_executor — never call directly from
        the asyncio event loop with large datasets.
        """
        if len(signal_rows) < _MIN_ROWS_FOR_FIT:
            log.info(
                "hmm.fit.skipped_insufficient_data",
                extra={"n_rows": len(signal_rows), "minimum": _MIN_ROWS_FOR_FIT},
            )
            return

        X = _extract_hmm_features(signal_rows)

        model = GaussianHMM(
            n_components=self._n_states,
            covariance_type=self._covariance_type,
            n_iter=self._n_iter,
            random_state=self._random_state,
        )
        model.fit(X)

        # --- Map hidden state indices → RegimeState via mean vectors ---
        # means shape: (n_states, n_features)
        means = model.means_  # (3, 5)
        # Feature indices in the 5-column matrix
        _SPREAD_IDX = 1   # spread_proxy
        _DELTA_IDX = 3    # delta_abs_mean

        spread_means = means[:, _SPREAD_IDX]
        delta_means = means[:, _DELTA_IDX]

        # CHAOTIC = highest spread_proxy
        chaotic_state = int(np.argmax(spread_means))
        # TRENDING = highest delta_abs_mean (excluding CHAOTIC candidate)
        trending_candidates = [s for s in range(self._n_states) if s != chaotic_state]
        trending_state = int(max(trending_candidates, key=lambda s: delta_means[s]))
        # ABSORPTION_FRIENDLY = the remaining state
        absorption_state = int(
            next(
                s for s in range(self._n_states)
                if s != chaotic_state and s != trending_state
            )
        )

        self._state_map = {
            absorption_state: RegimeState.ABSORPTION_FRIENDLY,
            trending_state: RegimeState.TRENDING,
            chaotic_state: RegimeState.CHAOTIC,
        }
        self._model = model

        log.info(
            "hmm.fit.complete",
            extra={
                "n_rows": len(signal_rows),
                "state_map": {k: v.value for k, v in self._state_map.items()},
            },
        )

    def predict_current(
        self,
        recent_rows: list[dict],
        n_recent: int = 20,
    ) -> RegimeState:
        """Decode the current regime via online Viterbi.

        Takes the last n_recent rows, runs full Viterbi decode, returns the
        last predicted state. Falls back to ABSORPTION_FRIENDLY if:
          - model not fitted
          - recent_rows is empty
          - X has fewer than 2 rows (HMM requires a sequence)

        Per D-11: Viterbi runs on the full recent window, not just the new
        observation — correct behaviour for GaussianHMM.

        Args:
            recent_rows: Recent signal_events rows (most recent = last).
            n_recent:    Maximum window size to pass to Viterbi.

        Returns:
            RegimeState enum member.
        """
        if self._model is None or not recent_rows:
            return RegimeState.ABSORPTION_FRIENDLY

        rows = recent_rows[-n_recent:]
        X = _extract_hmm_features(rows)

        if len(X) < 2:
            # HMM needs at least 2 observations for meaningful Viterbi
            return RegimeState.ABSORPTION_FRIENDLY

        try:
            state_seq = self._model.predict(X)
        except Exception as exc:
            log.warning("hmm.predict.failed", extra={"exc": str(exc)})
            return RegimeState.ABSORPTION_FRIENDLY

        last_state_idx = int(state_seq[-1])
        current_regime = self._state_map.get(last_state_idx, RegimeState.ABSORPTION_FRIENDLY)

        # T-09-08: Log regime transitions
        if self._prev_regime is not None and current_regime != self._prev_regime:
            log.info(
                "hmm.regime_change",
                extra={
                    "from_state": self._prev_regime.value,
                    "to_state": current_regime.value,
                    "ts": recent_rows[-1].get("ts") if recent_rows else None,
                },
            )
        self._prev_regime = current_regime

        return current_regime

    async def retrain(
        self,
        store: Any,  # EventStore — typed as Any to avoid circular import
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        """Retrain the HMM on the most recent 5000 signal events.

        Per D-12: Designed for nightly retrain. Uses run_in_executor to
        ensure fit() never blocks the asyncio event loop (D-07 pattern).

        Args:
            store: EventStore instance.
            loop:  Event loop to use; defaults to asyncio.get_event_loop().
        """
        rows = await store.fetch_signal_events(limit=5000)
        _loop = loop or asyncio.get_event_loop()
        await _loop.run_in_executor(None, self.fit, rows)
        log.info("hmm.retrain.complete", extra={"n_rows": len(rows)})
