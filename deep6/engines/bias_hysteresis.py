"""Hysteresis state machine for stabilizing raw bias scores."""
from __future__ import annotations

from typing import Optional

from deep6.engines.bias_contracts import BiasState
from deep6.engines.signal_config import BiasHysteresisConfig

# Max absolute score: ICT(4) + Macro(3) + Flow(2) + Kronos(3) + GEX(3) = 15
# Composer clamps to ±12, but accept the full theoretical range for safety.
_MAX_SCORE = 15


class BiasHysteresisFSM:
    """Convert raw total bias score into a stable BiasState."""

    def __init__(self, config: BiasHysteresisConfig | None = None) -> None:
        self._config = config or BiasHysteresisConfig()
        self._state = BiasState.NEUTRAL
        self._previous_state: BiasState | None = None
        self._bars_in_state = 0
        self._last_score: Optional[int] = None

    def update(self, total_score: int) -> BiasState:
        """Feed a new raw score and return the stable hysteresis state."""
        self._validate_score(total_score)

        if self._is_emergency_flip(total_score):
            next_state = self._target_state(total_score)
        else:
            next_state = self._next_state(total_score)

        self._last_score = total_score
        self._set_state(next_state)
        return self._state

    @property
    def state(self) -> BiasState:
        return self._state

    @property
    def current_state(self) -> BiasState:
        return self._state

    @property
    def previous_state(self) -> BiasState | None:
        return self._previous_state

    @property
    def bars_in_state(self) -> int:
        return self._bars_in_state

    def _target_state(self, score: int) -> BiasState:
        """Return the naive state mapping for a score without hysteresis."""
        cfg = self._config
        if score >= cfg.enter_strong_threshold:
            return BiasState.STRONG_BULL
        if score >= cfg.enter_lean_threshold:
            return BiasState.LEAN_BULL
        if score <= -cfg.enter_strong_threshold:
            return BiasState.STRONG_BEAR
        if score <= -cfg.enter_lean_threshold:
            return BiasState.LEAN_BEAR
        return BiasState.NEUTRAL

    def _is_emergency_flip(self, score: int) -> bool:
        return (
            self._last_score is not None
            and abs(score - self._last_score) >= self._config.emergency_delta
        )

    def _next_state(self, score: int) -> BiasState:
        cfg = self._config

        if self._state is BiasState.STRONG_BULL:
            if score >= cfg.degrade_strong_threshold:
                return BiasState.STRONG_BULL
            if score <= -cfg.enter_strong_threshold:
                return BiasState.STRONG_BEAR
            return BiasState.NEUTRAL

        if self._state is BiasState.LEAN_BULL:
            if score >= cfg.enter_strong_threshold:
                return BiasState.STRONG_BULL
            if score >= cfg.degrade_lean_threshold:
                return BiasState.LEAN_BULL
            if score <= -cfg.enter_strong_threshold:
                return BiasState.STRONG_BEAR
            if score <= -cfg.enter_lean_threshold:
                return BiasState.LEAN_BEAR
            return BiasState.NEUTRAL

        if self._state is BiasState.STRONG_BEAR:
            if score <= -cfg.degrade_strong_threshold:
                return BiasState.STRONG_BEAR
            if score >= cfg.enter_strong_threshold:
                return BiasState.STRONG_BULL
            return BiasState.NEUTRAL

        if self._state is BiasState.LEAN_BEAR:
            if score <= -cfg.enter_strong_threshold:
                return BiasState.STRONG_BEAR
            if score <= -cfg.degrade_lean_threshold:
                return BiasState.LEAN_BEAR
            if score >= cfg.enter_strong_threshold:
                return BiasState.STRONG_BULL
            if score >= cfg.enter_lean_threshold:
                return BiasState.LEAN_BULL
            return BiasState.NEUTRAL

        return self._target_state(score)

    def _set_state(self, next_state: BiasState) -> None:
        if next_state is self._state:
            self._bars_in_state += 1
            return

        self._previous_state = self._state
        self._state = next_state
        self._bars_in_state = 1

    @staticmethod
    def _validate_score(score: int) -> None:
        if not isinstance(score, int):
            raise TypeError("total_score must be an int")
        if score < -_MAX_SCORE or score > _MAX_SCORE:
            raise ValueError(f"total_score must be within [-{_MAX_SCORE}, {_MAX_SCORE}]")


__all__ = ["BiasHysteresisFSM"]
