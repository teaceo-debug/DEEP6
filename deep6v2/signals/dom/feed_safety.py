from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import time_ns

from deep6v2.signals.dom.adapters.live_adapter import LiveDOMAdapter


class FeedState(str, Enum):
    CONNECTED = "CONNECTED"
    STALE = "STALE"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"


@dataclass(slots=True)
class FeedTransition:
    from_state: FeedState
    to_state: FeedState
    reason: str
    timestamp_ns: int


class FeedStateManager:
    """Manages live feed lifecycle and guards against stale state propagation."""

    def __init__(self, adapter: LiveDOMAdapter) -> None:
        self._adapter = adapter
        self._state = FeedState.CONNECTED
        self._history: list[FeedTransition] = []

    @property
    def state(self) -> FeedState:
        return self._state

    def transition_history(self) -> list[FeedTransition]:
        return list(self._history)

    def is_safe_for_detection(self) -> bool:
        """Returns True only when state is CONNECTED."""
        return self._state is FeedState.CONNECTED

    def on_disconnect(self, reason: str = "") -> FeedTransition:
        self._adapter.mark_stale()
        return self._record_transition(FeedState.DISCONNECTED, reason or "disconnect")

    def on_reconnect(self) -> FeedTransition:
        self._record_transition(FeedState.RECONNECTING, "reconnect started")
        self._adapter.clear_stale()
        return self._record_transition(FeedState.CONNECTED, "reconnect complete")

    def on_session_rollover(self, new_session_id: str) -> FeedTransition:
        self._record_transition(FeedState.RECONNECTING, f"session rollover -> {new_session_id}")
        self._reset_adapter_state(new_session_id)
        self._adapter.clear_stale()
        return self._record_transition(FeedState.CONNECTED, f"session rollover complete -> {new_session_id}")

    def on_stale_detected(self, reason: str = "") -> FeedTransition:
        self._adapter.mark_stale()
        return self._record_transition(FeedState.STALE, reason or "stale detected")

    def _record_transition(self, to_state: FeedState, reason: str) -> FeedTransition:
        transition = FeedTransition(
            from_state=self._state,
            to_state=to_state,
            reason=reason,
            timestamp_ns=time_ns(),
        )
        self._history.append(transition)
        self._state = to_state
        return transition

    def _reset_adapter_state(self, new_session_id: str) -> None:
        dom_state = getattr(self._adapter, "_dom_state", None)
        if dom_state is not None and hasattr(dom_state, "reset"):
            dom_state.reset()
        if hasattr(self._adapter, "_version"):
            self._adapter._version = 0
        self._adapter.set_session(new_session_id)


__all__ = ["FeedState", "FeedStateManager", "FeedTransition"]
