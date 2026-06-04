"""Tests for the DOM feature-row builder (Task 13).

Verifies:
1. Empty output → all-zeros feature row
2. Imbalance event → non-zero imbalance features
3. feature_names length == feature_values length
4. FEATURE_NAMES is stable (same order on re-import)
5. feature_values dtype is float64
6. source_detector_ids populated from events
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from deep6v2.signals.dom.features.feature_builder import (
    FEATURE_NAMES,
    NUM_FEATURES,
    DOMFeatureBuilder,
    get_feature_names,
)
from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DOMIntelligenceFeatureRow,
    DOMIntelligenceOutput,
    DetectorTier,
    ReplaySafety,
)
from deep6v2.types.signal import Direction, SignalId


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_snapshot(
    bid_prices: list[float] | None = None,
    ask_prices: list[float] | None = None,
    bid_vol: int = 100,
    ask_vol: int = 100,
) -> DOMSnapshot:
    """Create a DOM snapshot with customizable bid/ask levels."""
    if bid_prices is None:
        bid_prices = [21000.00 - i * 0.25 for i in range(10)]
    if ask_prices is None:
        ask_prices = [21000.25 + i * 0.25 for i in range(10)]

    bids = [DOMLevel(price=p, volume=bid_vol) for p in bid_prices]
    asks = [DOMLevel(price=p, volume=ask_vol) for p in ask_prices]
    return DOMSnapshot(timestamp=datetime(2026, 1, 15, 10, 30, 0), bids=bids, asks=asks)


def _make_event(
    detector_id: str = "dom.imbalance.v1",
    tier: DetectorTier = DetectorTier.MECHANICAL,
    confidence: float = 0.8,
    metadata: dict | None = None,
) -> DOMIntelligenceEvent:
    """Create a DOM intelligence event for testing."""
    return DOMIntelligenceEvent(
        signal_id=SignalId.IMB_01,
        tier=tier,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        direction=Direction.BULLISH,
        confidence=confidence,
        price=21000.00,
        timestamp_ns=1_000_000_000,
        detector_id=detector_id,
        metadata=metadata or {},
    )


def _make_output(events: list[DOMIntelligenceEvent] | None = None) -> DOMIntelligenceOutput:
    """Create a DOMIntelligenceOutput with optional events."""
    return DOMIntelligenceOutput(
        events=events or [],
        evaluated_at_ns=1_000_000_000,
        bar_index=42,
        dom_state_version=1,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFeatureBuilderEmptyOutput:
    """Test 1: Empty output → all-zeros feature row (except DOM snapshot features)."""

    def test_no_events_produces_snapshot_features_only(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot(bid_vol=100, ask_vol=100)
        output = _make_output(events=[])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")

        assert isinstance(row, DOMIntelligenceFeatureRow)
        # Heuristic features should be 0.0
        heuristic_names = [
            "pull_replace_ratio", "micro_momentum", "large_burst_count",
            "micro_vol_ratio", "tps_intensity",
        ]
        for name in heuristic_names:
            idx = row.feature_names.index(name)
            assert row.feature_values[idx] == 0.0, f"{name} should be 0.0 with no events"

    def test_no_events_no_source_detectors(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        output = _make_output(events=[])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")
        assert row.source_detector_ids == []


class TestFeatureBuilderImbalanceEvent:
    """Test 2: Imbalance event → non-zero imbalance features."""

    def test_asymmetric_dom_produces_nonzero_imbalance(self) -> None:
        builder = DOMFeatureBuilder()
        # Bid-heavy DOM: 200 bid vs 50 ask
        snapshot = _make_snapshot(bid_vol=200, ask_vol=50)
        event = _make_event(
            detector_id="dom.imbalance.v1",
            metadata={
                "bid_ask_imbalance_ratio": 4.0,
                "depth_asymmetry_score": 0.6,
                "book_thinness": 1250.0,
            },
        )
        output = _make_output(events=[event])

        row = builder.build(output, snapshot, bar_index=1, session_id="test-session")

        # Imbalance ratio from snapshot: 200*5 / (50*5) = 4.0
        # But event metadata overrides via max-magnitude
        ratio_idx = row.feature_names.index("bid_ask_imbalance_ratio")
        assert row.feature_values[ratio_idx] != 0.0

        asym_idx = row.feature_names.index("depth_asymmetry_score")
        assert row.feature_values[asym_idx] != 0.0

    def test_symmetric_dom_near_zero_asymmetry(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot(bid_vol=100, ask_vol=100)
        output = _make_output(events=[])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")

        asym_idx = row.feature_names.index("depth_asymmetry_score")
        assert abs(row.feature_values[asym_idx]) < 1e-9


class TestFeatureNamesLength:
    """Test 3: feature_names length == feature_values length."""

    def test_lengths_match(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        output = _make_output(events=[])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")
        assert len(row.feature_names) == len(row.feature_values)

    def test_lengths_match_num_features(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        output = _make_output(events=[])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")
        assert len(row.feature_names) == NUM_FEATURES
        assert len(row.feature_values) == NUM_FEATURES


class TestFeatureNamesStability:
    """Test 4: FEATURE_NAMES is stable (same order on re-import)."""

    def test_feature_names_order_stable(self) -> None:
        from deep6v2.signals.dom.features.feature_builder import (
            FEATURE_NAMES as NAMES_REIMPORT,
        )
        assert FEATURE_NAMES is NAMES_REIMPORT
        assert FEATURE_NAMES == NAMES_REIMPORT

    def test_get_feature_names_returns_copy(self) -> None:
        names = get_feature_names()
        assert names == FEATURE_NAMES
        assert names is not FEATURE_NAMES  # defensive copy

    def test_feature_names_expected_order(self) -> None:
        expected = [
            "bid_ask_imbalance_ratio",
            "depth_asymmetry_score",
            "book_thinness",
            "cvd_value",
            "cvd_acceleration",
            "pull_replace_ratio",
            "micro_momentum",
            "large_burst_count",
            "micro_vol_ratio",
            "tps_intensity",
        ]
        assert FEATURE_NAMES == expected


class TestFeatureValuesDtype:
    """Test 5: feature_values dtype is float64."""

    def test_dtype_float64(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        output = _make_output(events=[])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")
        assert row.feature_values.dtype == np.float64

    def test_dtype_float64_with_events(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        event = _make_event(metadata={"value": 42})
        output = _make_output(events=[event])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")
        assert row.feature_values.dtype == np.float64


class TestSourceDetectorIds:
    """Test 6: source_detector_ids populated from events."""

    def test_single_event_detector_id(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        event = _make_event(detector_id="dom.pull_replace.v1", tier=DetectorTier.HEURISTIC)
        output = _make_output(events=[event])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")
        assert "dom.pull_replace.v1" in row.source_detector_ids

    def test_multiple_events_unique_ids(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        events = [
            _make_event(detector_id="dom.imbalance.v1"),
            _make_event(detector_id="dom.cvd.v1"),
            _make_event(detector_id="dom.imbalance.v1"),  # duplicate
        ]
        output = _make_output(events=events)

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")
        assert len(row.source_detector_ids) == 2
        assert "dom.imbalance.v1" in row.source_detector_ids
        assert "dom.cvd.v1" in row.source_detector_ids

    def test_heuristic_events_populate_features(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        events = [
            _make_event(
                detector_id="dom.tps.v1",
                tier=DetectorTier.HEURISTIC,
                confidence=0.9,
                metadata={"tps_intensity": 3.5},
            ),
            _make_event(
                detector_id="dom.large_burst.v1",
                tier=DetectorTier.HEURISTIC,
                confidence=0.7,
                metadata={"large_burst_count": 5.0},
            ),
        ]
        output = _make_output(events=events)

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")

        tps_idx = row.feature_names.index("tps_intensity")
        assert row.feature_values[tps_idx] == 3.5

        burst_idx = row.feature_names.index("large_burst_count")
        assert row.feature_values[burst_idx] == 5.0


class TestMetadataPassthrough:
    """Additional: metadata values flow correctly into feature vector."""

    def test_cvd_metadata(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        event = _make_event(
            detector_id="dom.cvd.v1",
            metadata={"cvd_value": 1500.0, "cvd_acceleration": -23.5},
        )
        output = _make_output(events=[event])

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")

        cvd_idx = row.feature_names.index("cvd_value")
        assert row.feature_values[cvd_idx] == 1500.0

        accel_idx = row.feature_names.index("cvd_acceleration")
        assert row.feature_values[accel_idx] == -23.5

    def test_session_id_and_bar_index_passthrough(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        output = _make_output(events=[])

        row = builder.build(output, snapshot, bar_index=77, session_id="sess-abc-123")
        assert row.bar_index == 77
        assert row.session_id == "sess-abc-123"

    def test_timestamp_from_output(self) -> None:
        builder = DOMFeatureBuilder()
        snapshot = _make_snapshot()
        output = _make_output(events=[])
        output.evaluated_at_ns = 5_000_000_000

        row = builder.build(output, snapshot, bar_index=0, session_id="test-session")
        assert row.timestamp_ns == 5_000_000_000
