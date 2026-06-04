"""Live DOM adapter bridging RithmicClient/DOMState into DOMIntelligenceOutput.

This adapter wraps the existing Rithmic transport — it does NOT recreate or
replace it. It only translates DOM events into the dom_intelligence contract
format.

DOM STATE OWNERSHIP RULE:
  LiveDOMAdapter receives a DOMState instance in its constructor.
  It MUST NOT instantiate a new DOMState or subclass DOMState.
"""

from __future__ import annotations

from deep6v2.state.dom import DOMState
from deep6v2.types.dom import DOMSnapshot, DOMUpdate
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DOMIntelligenceOutput,
)
from deep6v2.types.execution import OrderSide

# OrderSide -> DOMState side string mapping
_SIDE_MAP: dict[OrderSide, str] = {
    OrderSide.BUY: "bid",
    OrderSide.SELL: "ask",
}


class FeedStaleError(RuntimeError):
    """Raised when a stale live feed is used for detection."""


class LiveDOMAdapter:
    """Bridges RithmicClient/DOMState into DOMIntelligenceOutput for detectors.

    RULE: This adapter wraps the existing Rithmic transport — it does NOT
    recreate or replace it. It only translates DOM events into the
    dom_intelligence contract format.
    """

    def __init__(self, dom_state: DOMState) -> None:
        """Takes existing DOMState — does NOT instantiate a new one."""
        self._dom_state = dom_state
        self._version: int = 0
        self._session_id: str = ""
        self._stale: bool = False

    @property
    def version(self) -> int:
        """Current DOM state version counter."""
        return self._version

    @property
    def session_id(self) -> str:
        """Current session identifier."""
        return self._session_id

    def set_session(self, session_id: str) -> None:
        """Called on session start to set session context."""
        self._session_id = session_id

    def mark_stale(self) -> None:
        """Mark feed as stale (e.g., disconnect detected)."""
        self._stale = True

    def clear_stale(self) -> None:
        """Clear stale flag (e.g., reconnect succeeded)."""
        self._stale = False

    def is_stale(self) -> bool:
        """Returns True if feed is currently stale."""
        return self._stale

    def on_dom_update(self, update: DOMUpdate) -> DOMSnapshot:
        """Process a raw DOM update and return updated snapshot.

        - Applies update to self._dom_state
        - Increments self._version
        - Returns a DOMSnapshot reflecting current book state
        - If stale, raises FeedStaleError
        """
        if self._stale:
            raise FeedStaleError("Live feed is stale — cannot process DOM update")

        side_str = _SIDE_MAP[update.side]
        self._dom_state.update_level(side_str, update.price, update.volume)
        self._version += 1
        return self._dom_state.snapshot()

    def build_output(
        self,
        events: list[DOMIntelligenceEvent],
        snapshot: DOMSnapshot,
        bar_index: int,
        evaluated_at_ns: int,
    ) -> DOMIntelligenceOutput:
        """Packages detector events into DOMIntelligenceOutput."""
        return DOMIntelligenceOutput(
            events=events,
            feature_row=None,
            evaluated_at_ns=evaluated_at_ns,
            bar_index=bar_index,
            dom_state_version=self._version,
        )


__all__ = ["FeedStaleError", "LiveDOMAdapter"]
