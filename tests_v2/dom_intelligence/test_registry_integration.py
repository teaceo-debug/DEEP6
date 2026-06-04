"""Tests for DOM intelligence detector registration in DetectorRegistry."""
from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from deep6v2.signals.dom.compat.feature_flags import (
    DOM_INTELLIGENCE_ENABLED_ENV_VAR,
    force_disable_dom_intelligence,
    force_enable_dom_intelligence,
)
from deep6v2.signals.registry import DOMIntelligenceAdapter, DetectorRegistry
from deep6v2.types.dom import DOMLevel, DOMSnapshot


def _make_snapshot(
    bids: list[tuple[float, int]] | None = None,
    asks: list[tuple[float, int]] | None = None,
) -> DOMSnapshot:
    bid_levels = [DOMLevel(price=p, volume=v) for p, v in (bids or [(20000.0, 100)])]
    ask_levels = [DOMLevel(price=p, volume=v) for p, v in (asks or [(20000.25, 100)])]
    return DOMSnapshot(
        bids=bid_levels,
        asks=ask_levels,
        timestamp=datetime.now(timezone.utc),
        version=1,
    )


@pytest.fixture(autouse=True)
def _reset_feature_flag():
    """Ensure feature flag is restored after each test."""
    original = os.environ.get(DOM_INTELLIGENCE_ENABLED_ENV_VAR)
    yield
    if original is None:
        os.environ.pop(DOM_INTELLIGENCE_ENABLED_ENV_VAR, None)
    else:
        os.environ[DOM_INTELLIGENCE_ENABLED_ENV_VAR] = original


class TestRegistryDOMIntegration:
    """Verify create_default() registers DOM detectors when flag is enabled."""

    def test_dom_detectors_registered_when_enabled(self):
        force_enable_dom_intelligence()
        registry = DetectorRegistry.create_default()
        adapters = registry.dom_intelligence_adapters
        # 5 snapshot-consuming Tier-1 detectors (CVD uses update_trade, wired separately)
        assert len(adapters) == 5, f"Expected 5 snapshot-based Tier-1 detectors, got {len(adapters)}"

    def test_dom_detectors_not_registered_when_disabled(self):
        force_disable_dom_intelligence()
        registry = DetectorRegistry.create_default()
        adapters = registry.dom_intelligence_adapters
        assert len(adapters) == 0, "DOM detectors should not register when disabled"

    def test_existing_detectors_unaffected_by_dom_flag(self):
        """Existing depth_detectors must be present regardless of DOM flag."""
        force_enable_dom_intelligence()
        registry_on = DetectorRegistry.create_default()

        force_disable_dom_intelligence()
        registry_off = DetectorRegistry.create_default()

        # Existing depth detectors count should be identical
        assert len(registry_on._depth_detectors) == len(registry_off._depth_detectors) == 3

    def test_dom_detector_ids_match_tier1_snapshot_taxonomy(self):
        """5 snapshot-consuming Tier-1 detectors; CVD is trade-based, registered separately."""
        force_enable_dom_intelligence()
        registry = DetectorRegistry.create_default()
        adapter_ids = {a.detector_id for a in registry.dom_intelligence_adapters}
        expected = {
            "dom.imbalance.v1",
            "dom.absorption.v1",
            "dom.sweep_reload.v1",
            "dom.iceberg.v1",
            "dom.thinness.v1",
        }
        assert adapter_ids == expected

    def test_on_depth_dispatches_to_dom_adapters(self):
        force_enable_dom_intelligence()
        registry = DetectorRegistry.create_default()
        snapshot = _make_snapshot(
            bids=[(20000.0, 300), (19999.75, 100), (19999.50, 50)],
            asks=[(20000.25, 50), (20000.50, 100), (20000.75, 300)],
        )
        # Should not raise
        registry.on_depth(snapshot)

    def test_drain_dom_events_returns_list(self):
        force_enable_dom_intelligence()
        registry = DetectorRegistry.create_default()
        snapshot = _make_snapshot()
        registry.on_depth(snapshot)
        events = registry.drain_dom_intelligence_events()
        assert isinstance(events, list)

    def test_drain_clears_buffer(self):
        force_enable_dom_intelligence()
        registry = DetectorRegistry.create_default()
        snapshot = _make_snapshot(
            bids=[(20000.0, 500), (19999.75, 10)],
            asks=[(20000.25, 10), (20000.50, 500)],
        )
        registry.on_depth(snapshot)
        registry.on_depth(snapshot)
        _ = registry.drain_dom_intelligence_events()
        second_drain = registry.drain_dom_intelligence_events()
        assert second_drain == []


class TestDOMIntelligenceAdapter:
    """Unit tests for the adapter wrapper itself."""

    def test_adapter_rejects_invalid_detector(self):
        with pytest.raises(TypeError, match="on_depth"):
            DOMIntelligenceAdapter(object())

    def test_adapter_collects_events(self):
        """Fake detector that returns events should have them buffered."""

        class _FakeDetector:
            detector_id = "test.fake.v1"

            def on_depth(self, snapshot: DOMSnapshot) -> list:
                from deep6v2.types.dom_intelligence import (
                    DOMIntelligenceEvent,
                    DetectorTier,
                    ReplaySafety,
                )
                from deep6v2.types.signal import Direction, SignalId

                return [
                    DOMIntelligenceEvent(
                        signal_id=SignalId.IMB_01,
                        tier=DetectorTier.MECHANICAL,
                        replay_safety=ReplaySafety.REPLAY_SAFE,
                        direction=Direction.BULLISH,
                        confidence=0.8,
                        price=20000.0,
                        timestamp_ns=1_000_000_000,
                        detector_id="test.fake.v1",
                    )
                ]

        adapter = DOMIntelligenceAdapter(_FakeDetector())
        adapter.on_depth(_make_snapshot())
        events = adapter.drain_events()
        assert len(events) == 1
        assert events[0].detector_id == "test.fake.v1"

    def test_adapter_exception_isolation(self):
        """Adapter must not propagate detector exceptions."""

        class _BadDetector:
            detector_id = "test.bad.v1"

            def on_depth(self, snapshot: DOMSnapshot) -> list:
                raise RuntimeError("boom")

        adapter = DOMIntelligenceAdapter(_BadDetector())
        # Should not raise
        adapter.on_depth(_make_snapshot())
        assert adapter.drain_events() == []

    def test_adapter_respects_max_buffer(self):
        class _FloodDetector:
            detector_id = "test.flood.v1"

            def on_depth(self, snapshot: DOMSnapshot) -> list:
                from deep6v2.types.dom_intelligence import (
                    DOMIntelligenceEvent,
                    DetectorTier,
                    ReplaySafety,
                )
                from deep6v2.types.signal import Direction, SignalId

                return [
                    DOMIntelligenceEvent(
                        signal_id=SignalId.IMB_01,
                        tier=DetectorTier.MECHANICAL,
                        replay_safety=ReplaySafety.REPLAY_SAFE,
                        direction=Direction.BULLISH,
                        confidence=0.5,
                        price=20000.0,
                        timestamp_ns=i,
                        detector_id="test.flood.v1",
                    )
                    for i in range(100)
                ]

        adapter = DOMIntelligenceAdapter(_FloodDetector(), max_events=50)
        adapter.on_depth(_make_snapshot())
        events = adapter.drain_events()
        # deque maxlen=50, so only last 50 of 100 should survive
        assert len(events) == 50
