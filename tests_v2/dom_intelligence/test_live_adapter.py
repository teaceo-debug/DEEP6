"""Tests for LiveDOMAdapter — bridges DOMState into DOMIntelligenceOutput."""

from __future__ import annotations

import pytest

from deep6v2.signals.dom.adapters.live_adapter import FeedStaleError, LiveDOMAdapter
from deep6v2.state.dom import DOMState
from deep6v2.types.dom import DOMUpdate
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DOMIntelligenceOutput,
    DetectorTier,
    ReplaySafety,
)
from deep6v2.types.execution import OrderSide
from deep6v2.types.signal import Direction, SignalId


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def dom_state() -> DOMState:
    """Fresh DOMState centred at 20000.0."""
    return DOMState(base_price=20000.0, num_levels=4000)


@pytest.fixture()
def adapter(dom_state: DOMState) -> LiveDOMAdapter:
    """Adapter wrapping the shared DOMState fixture."""
    return LiveDOMAdapter(dom_state)


def _bid_update(price: float = 20000.0, volume: int = 50) -> DOMUpdate:
    return DOMUpdate(side=OrderSide.BUY, level=0, price=price, volume=volume)


def _ask_update(price: float = 20000.25, volume: int = 30) -> DOMUpdate:
    return DOMUpdate(side=OrderSide.SELL, level=0, price=price, volume=volume)


def _make_event(
    price: float = 20000.0,
    ts_ns: int = 1_000_000,
) -> DOMIntelligenceEvent:
    return DOMIntelligenceEvent(
        signal_id=SignalId.ABS_01,
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        direction=Direction.BULLISH,
        confidence=0.85,
        price=price,
        timestamp_ns=ts_ns,
        detector_id="test_detector",
    )


# ---------------------------------------------------------------------------
# 1. on_dom_update returns DOMSnapshot with updated bid/ask
# ---------------------------------------------------------------------------
class TestOnDomUpdateReturnsSnapshot:
    def test_bid_update_populates_bids(self, adapter: LiveDOMAdapter) -> None:
        snap = adapter.on_dom_update(_bid_update(price=20000.0, volume=50))
        assert len(snap.bids) >= 1
        assert snap.bids[0].price == 20000.0
        assert snap.bids[0].volume == 50

    def test_ask_update_populates_asks(self, adapter: LiveDOMAdapter) -> None:
        snap = adapter.on_dom_update(_ask_update(price=20000.25, volume=30))
        assert len(snap.asks) >= 1
        assert snap.asks[0].price == 20000.25
        assert snap.asks[0].volume == 30

    def test_both_sides(self, adapter: LiveDOMAdapter) -> None:
        adapter.on_dom_update(_bid_update(price=20000.0, volume=50))
        snap = adapter.on_dom_update(_ask_update(price=20000.25, volume=30))
        assert len(snap.bids) >= 1
        assert len(snap.asks) >= 1


# ---------------------------------------------------------------------------
# 2. on_dom_update increments version counter
# ---------------------------------------------------------------------------
class TestVersionIncrement:
    def test_starts_at_zero(self, adapter: LiveDOMAdapter) -> None:
        assert adapter.version == 0

    def test_increments_on_each_update(self, adapter: LiveDOMAdapter) -> None:
        adapter.on_dom_update(_bid_update())
        assert adapter.version == 1
        adapter.on_dom_update(_ask_update())
        assert adapter.version == 2
        adapter.on_dom_update(_bid_update(volume=99))
        assert adapter.version == 3


# ---------------------------------------------------------------------------
# 3. on_dom_update raises FeedStaleError when stale
# ---------------------------------------------------------------------------
class TestFeedStaleRaises:
    def test_raises_when_stale(self, adapter: LiveDOMAdapter) -> None:
        adapter.mark_stale()
        with pytest.raises(FeedStaleError):
            adapter.on_dom_update(_bid_update())

    def test_no_raise_after_clear(self, adapter: LiveDOMAdapter) -> None:
        adapter.mark_stale()
        adapter.clear_stale()
        snap = adapter.on_dom_update(_bid_update())
        assert snap is not None


# ---------------------------------------------------------------------------
# 4. is_stale state transitions
# ---------------------------------------------------------------------------
class TestIsStale:
    def test_false_initially(self, adapter: LiveDOMAdapter) -> None:
        assert adapter.is_stale() is False

    def test_true_after_mark(self, adapter: LiveDOMAdapter) -> None:
        adapter.mark_stale()
        assert adapter.is_stale() is True

    def test_false_after_clear(self, adapter: LiveDOMAdapter) -> None:
        adapter.mark_stale()
        adapter.clear_stale()
        assert adapter.is_stale() is False


# ---------------------------------------------------------------------------
# 5. build_output returns DOMIntelligenceOutput with correct fields
# ---------------------------------------------------------------------------
class TestBuildOutput:
    def test_bar_index_and_version(self, adapter: LiveDOMAdapter) -> None:
        # Pump two updates to set version=2
        adapter.on_dom_update(_bid_update())
        snap = adapter.on_dom_update(_ask_update())

        output = adapter.build_output(
            events=[],
            snapshot=snap,
            bar_index=42,
            evaluated_at_ns=999_000,
        )
        assert output.bar_index == 42
        assert output.dom_state_version == 2
        assert output.evaluated_at_ns == 999_000

    def test_events_passed_through(self, adapter: LiveDOMAdapter) -> None:
        snap = adapter.on_dom_update(_bid_update())
        evt = _make_event()
        output = adapter.build_output(
            events=[evt],
            snapshot=snap,
            bar_index=0,
            evaluated_at_ns=1_000,
        )
        assert len(output.events) == 1
        assert output.events[0] is evt


# ---------------------------------------------------------------------------
# 6. build_output matches DOMIntelligenceOutput schema
# ---------------------------------------------------------------------------
class TestOutputContract:
    def test_is_correct_type(self, adapter: LiveDOMAdapter) -> None:
        snap = adapter.on_dom_update(_bid_update())
        output = adapter.build_output(
            events=[],
            snapshot=snap,
            bar_index=0,
            evaluated_at_ns=0,
        )
        assert isinstance(output, DOMIntelligenceOutput)

    def test_events_is_list(self, adapter: LiveDOMAdapter) -> None:
        snap = adapter.on_dom_update(_bid_update())
        output = adapter.build_output(
            events=[],
            snapshot=snap,
            bar_index=0,
            evaluated_at_ns=0,
        )
        assert isinstance(output.events, list)

    def test_feature_row_optional(self, adapter: LiveDOMAdapter) -> None:
        snap = adapter.on_dom_update(_bid_update())
        output = adapter.build_output(
            events=[],
            snapshot=snap,
            bar_index=0,
            evaluated_at_ns=0,
        )
        assert output.feature_row is None


# ---------------------------------------------------------------------------
# 7. Adapter does NOT instantiate a new DOMState
# ---------------------------------------------------------------------------
class TestNoDOMStateCreation:
    def test_shares_dom_state_reference(self, dom_state: DOMState, adapter: LiveDOMAdapter) -> None:
        """Adapter's internal _dom_state is the exact same object passed in."""
        assert adapter._dom_state is dom_state

    def test_update_reflects_in_shared_state(self, dom_state: DOMState, adapter: LiveDOMAdapter) -> None:
        """Mutations through adapter are visible on the original DOMState."""
        adapter.on_dom_update(_bid_update(price=20000.0, volume=77))
        assert dom_state.get_best_bid() == 20000.0
