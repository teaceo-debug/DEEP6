from __future__ import annotations

from enum import Enum

from deep6v2.config.scoring import ScoringConfig
from deep6v2.types.signal import Direction


class BiasState(str, Enum):
    NEUTRAL = "NEUTRAL"
    TRANSITIONING = "TRANSITIONING"
    BULLISH_CONFIRMED = "BULLISH_CONFIRMED"
    BEARISH_CONFIRMED = "BEARISH_CONFIRMED"


class HysteresisFSM:
    def __init__(self, confirmation_bars: int = 3, decay_bars: int = 5) -> None:
        self._state = BiasState.NEUTRAL
        self._confirmation_bars = confirmation_bars
        self._decay_bars = decay_bars
        self._consecutive_count = 0
        self._current_direction: Direction = Direction.NEUTRAL
        self._bars_since_confirmation = 0

    @property
    def state(self) -> BiasState:
        return self._state

    @property
    def direction(self) -> Direction:
        return self._current_direction

    def update(self, direction: Direction) -> BiasState:
        if self._state in {BiasState.BULLISH_CONFIRMED, BiasState.BEARISH_CONFIRMED}:
            return self._update_confirmed(direction)

        if direction is Direction.NEUTRAL:
            return self._state

        if self._current_direction is Direction.NEUTRAL:
            self._current_direction = direction
            self._consecutive_count = 1
            self._state = BiasState.TRANSITIONING
            return self._state

        if direction is not self._current_direction:
            self.reset()
            return self._state

        self._consecutive_count += 1
        if self._consecutive_count >= self._confirmation_bars:
            self._state = self._confirmed_state(direction)
            self._bars_since_confirmation = 0
            return self._state

        self._state = BiasState.TRANSITIONING
        return self._state

    def reset(self) -> None:
        self._state = BiasState.NEUTRAL
        self._consecutive_count = 0
        self._current_direction = Direction.NEUTRAL
        self._bars_since_confirmation = 0

    def _update_confirmed(self, direction: Direction) -> BiasState:
        if direction is self._current_direction:
            self._bars_since_confirmation = 0
            return self._state

        if direction is Direction.NEUTRAL:
            self._bars_since_confirmation += 1
            if self._bars_since_confirmation >= self._decay_bars:
                self.reset()
            return self._state

        self.reset()
        return self._state

    @staticmethod
    def _confirmed_state(direction: Direction) -> BiasState:
        if direction is Direction.BULLISH:
            return BiasState.BULLISH_CONFIRMED
        return BiasState.BEARISH_CONFIRMED


def is_midday_blocked(bar_index: int, config: ScoringConfig | None = None) -> bool:
    """True for bars 60-210 inclusive."""
    cfg = config or ScoringConfig()
    return cfg.midday_block_start_bar <= bar_index <= cfg.midday_block_end_bar


def is_initial_balance(bar_index: int) -> bool:
    """True for bars 0-59 inclusive."""
    return 0 <= bar_index <= 59


def get_ib_multiplier(bar_index: int, config: ScoringConfig | None = None) -> float:
    """Return the configured initial-balance multiplier or 1.0."""
    cfg = config or ScoringConfig()
    return cfg.ib_multiplier if is_initial_balance(bar_index) else 1.0


__all__ = [
    "BiasState",
    "HysteresisFSM",
    "get_ib_multiplier",
    "is_initial_balance",
    "is_midday_blocked",
]
