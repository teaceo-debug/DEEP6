from __future__ import annotations

from enum import Enum


class KillSwitchState(str, Enum):
    GO = "GO"
    CAUTION = "CAUTION"
    STOP = "STOP"


class KillSwitch:
    """Emergency stop mechanism for risk management."""

    def __init__(self, max_consecutive_losses: int = 3, volatility_threshold: float = 2.0) -> None:
        self._state = KillSwitchState.GO
        self._consecutive_losses = 0
        self._max_consecutive = max_consecutive_losses
        self._volatility_threshold = volatility_threshold

    @property
    def state(self) -> KillSwitchState:
        return self._state

    @property
    def allows_new_trades(self) -> bool:
        return self._state == KillSwitchState.GO

    def on_trade_result(self, pnl: float) -> KillSwitchState:
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
            if self._state == KillSwitchState.CAUTION:
                self._state = KillSwitchState.GO
        if self._consecutive_losses >= self._max_consecutive:
            self._state = KillSwitchState.CAUTION
        return self._state

    def on_daily_loss_breach(self) -> KillSwitchState:
        self._state = KillSwitchState.STOP
        return self._state

    def on_volatility_spike(self, current_atr: float, baseline_atr: float) -> KillSwitchState:
        if baseline_atr > 0 and current_atr / baseline_atr > self._volatility_threshold:
            self._state = KillSwitchState.CAUTION
        return self._state

    def manual_stop(self) -> KillSwitchState:
        self._state = KillSwitchState.STOP
        return self._state

    def reset(self) -> None:
        self._state = KillSwitchState.GO
        self._consecutive_losses = 0


__all__ = ["KillSwitch", "KillSwitchState"]
