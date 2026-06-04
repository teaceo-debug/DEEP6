from __future__ import annotations

from datetime import UTC, datetime, timedelta

from deep6v2.state.dom import DOMState
from deep6v2.types.dom import DOMSnapshot, DOMUpdate
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DOMIntelligenceOutput
from deep6v2.types.execution import OrderSide


class ReplayDOMAdapter:
    """Bridges historical MBO/reconstructed DOM events into DOMIntelligenceOutput.

    RULE: This adapter wraps the existing ReplayEngine output — it does NOT
    recreate a separate replay mechanism. It receives pre-ordered DOM events
    and produces the same DOMIntelligenceOutput contract as LiveDOMAdapter.

    DETERMINISM GUARANTEE: Given the same input sequence, this adapter
    MUST produce byte-identical output for replay parity testing.
    """

    _REPLAY_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

    def __init__(self, dom_state: DOMState, session_id: str = "") -> None:
        """Receive existing DOMState — do NOT instantiate a new one."""
        self._dom_state = dom_state
        self._session_id = session_id
        self._version: int = 0
        self._event_index: int = 0

    def reset(self, session_id: str = "") -> None:
        """Reset adapter state for a new replay session."""
        self._dom_state.reset()
        self._session_id = session_id
        self._version = 0
        self._event_index = 0

    def process_event(self, update: DOMUpdate) -> DOMSnapshot:
        """Process one historical DOM event deterministically.

        - Applies update to DOM state
        - Increments version
        - Returns snapshot
        - MUST be deterministic: same input → same output
        """
        self._dom_state.update_level(self._side_to_dom_side(update.side), update.price, update.volume)
        self._version += 1
        snapshot = self._dom_state.snapshot(timestamp=self._snapshot_timestamp())
        self._event_index += 1
        return snapshot

    def build_output(
        self,
        events: list[DOMIntelligenceEvent],
        snapshot: DOMSnapshot,
        bar_index: int,
        evaluated_at_ns: int,
    ) -> DOMIntelligenceOutput:
        """Same interface as LiveDOMAdapter.build_output() for parity testing."""
        normalized_events = [
            event
            if event.dom_state_snapshot is not None
            else self._copy_event_with_snapshot(event, snapshot)
            for event in events
        ]
        return DOMIntelligenceOutput(
            events=normalized_events,
            evaluated_at_ns=evaluated_at_ns,
            bar_index=bar_index,
            dom_state_version=self._version,
        )

    def replay_sequence(self, updates: list[DOMUpdate]) -> list[DOMSnapshot]:
        """Process a sequence of DOM updates and return all resulting snapshots.

        This is the primary batch-replay interface.
        """
        return [self.process_event(update) for update in updates]

    @staticmethod
    def _side_to_dom_side(side: OrderSide) -> str:
        return "bid" if side is OrderSide.BUY else "ask"

    def _snapshot_timestamp(self) -> datetime:
        return self._REPLAY_EPOCH + timedelta(microseconds=self._event_index)

    @staticmethod
    def _copy_event_with_snapshot(
        event: DOMIntelligenceEvent,
        snapshot: DOMSnapshot,
    ) -> DOMIntelligenceEvent:
        return DOMIntelligenceEvent(
            signal_id=event.signal_id,
            tier=event.tier,
            replay_safety=event.replay_safety,
            direction=event.direction,
            confidence=event.confidence,
            price=event.price,
            timestamp_ns=event.timestamp_ns,
            detector_id=event.detector_id,
            metadata=dict(event.metadata),
            dom_state_snapshot=snapshot,
        )


__all__ = ["ReplayDOMAdapter"]
