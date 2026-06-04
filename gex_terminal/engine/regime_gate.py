"""HMM regime gate — wraps deep6 HMM to classify market tradability."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_VALID_STATES = {"ABSORPTION_FRIENDLY", "TRENDING", "CHAOTIC"}


class HMMRegimeGate:
    """Uses deep6 HMM to classify market regime for tradability gating."""

    def __init__(self) -> None:
        self._detector = None
        self._last_state = "UNKNOWN"
        self._signal_rows: list[dict[str, float]] = []
        self._buffer_size = 30
        self._predict_window = 20
        self._load_detector()

    def _load_detector(self) -> None:
        try:
            from deep6.ml.hmm_regime import HMMRegimeDetector

            self._detector = HMMRegimeDetector()
        except Exception as exc:
            logger.warning("HMM detector unavailable: %s — defaulting to UNKNOWN", exc)

    def update(self, features: list[float]) -> str:
        """Feed new feature vector and return current regime state."""
        if self._detector is None:
            return "UNKNOWN"
        row = self._feature_vector_to_signal_row(features)
        if row is None:
            return self._last_state

        try:
            self._signal_rows.append(row)
            max_rows = self._buffer_size * 3
            if len(self._signal_rows) > max_rows:
                self._signal_rows = self._signal_rows[-(self._buffer_size * 2) :]

            if len(self._signal_rows) >= self._buffer_size and not self._detector.is_fitted():
                self._detector.fit(self._signal_rows)

            if self._detector.is_fitted():
                state = self._detector.predict_current(self._signal_rows[-self._predict_window :]).value
                if state in _VALID_STATES:
                    self._last_state = state
        except Exception as exc:
            logger.debug("HMM update error: %s", exc)
        return self._last_state

    def _feature_vector_to_signal_row(self, features: list[float]) -> dict[str, float] | None:
        if len(features) < 5:
            return None

        try:
            atr_ratio, spread, trade_rate, delta_abs_mean, range_to_atr = [float(value) for value in features[:5]]
        except (TypeError, ValueError):
            return None

        atr_ratio = max(0.0, min(1.0, atr_ratio))
        spread = max(0.0, min(1.0, spread))
        trade_rate = max(0.0, min(1.0, trade_rate))
        delta_abs_mean = max(0.0, min(1.0, delta_abs_mean))
        range_to_atr = max(0.0, min(1.0, range_to_atr))

        engine_agreement = max(0.0, min(1.0, 1.0 - spread))
        if atr_ratio > 0.0 and range_to_atr > 0.0:
            inferred_trade_rate = max(0.0, min(1.0, range_to_atr / atr_ratio))
            trade_rate = inferred_trade_rate if trade_rate == 0.0 else (trade_rate + inferred_trade_rate) / 2.0

        direction = delta_abs_mean if engine_agreement <= 0.0 else delta_abs_mean / engine_agreement

        return {
            "total_score": atr_ratio * 100.0,
            "engine_agreement": engine_agreement,
            "category_count": trade_rate * 8.0,
            "direction": direction,
        }

    @property
    def state(self) -> str:
        return self._last_state


__all__ = ["HMMRegimeGate"]
