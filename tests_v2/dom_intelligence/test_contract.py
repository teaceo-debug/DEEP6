from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime

import numpy as np
import pytest

from deep6v2.types.dom import DOMLevel, DOMSnapshot
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DOMIntelligenceFeatureRow,
    DOMIntelligenceOutput,
    DetectorTier,
    ReplaySafety,
)
from deep6v2.types.signal import Direction, SignalId


def _sample_snapshot() -> DOMSnapshot:
    return DOMSnapshot(
        timestamp=datetime(2026, 5, 27, 14, 30, tzinfo=UTC),
        bids=[DOMLevel(price=21000.0, volume=125)],
        asks=[DOMLevel(price=21000.25, volume=140)],
    )


def test_dom_intelligence_event_has_required_fields():
    assert [field.name for field in fields(DOMIntelligenceEvent)] == [
        "signal_id",
        "tier",
        "replay_safety",
        "direction",
        "confidence",
        "price",
        "timestamp_ns",
        "detector_id",
        "metadata",
        "dom_state_snapshot",
    ]


def test_replay_safety_enum_contract():
    assert [member.name for member in ReplaySafety] == [
        "REPLAY_SAFE",
        "LIVE_ONLY",
        "REPLAY_DEGRADED",
    ]


def test_detector_tier_enum_contract():
    assert [member.name for member in DetectorTier] == [
        "MECHANICAL",
        "HEURISTIC",
        "DISCRETIONARY_OVERLAY",
    ]


def test_dom_intelligence_output_contract():
    feature_row = DOMIntelligenceFeatureRow(
        timestamp_ns=123,
        feature_names=["imbalance_5", "depth_ratio"],
        feature_values=np.array([1.2, 0.8]),
        bar_index=17,
        session_id="2026-05-27-RTH",
        source_detector_ids=["dom.imbalance.v1"],
    )
    event = DOMIntelligenceEvent(
        signal_id=SignalId.REGIME_CHANGE,
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        direction=Direction.NEUTRAL,
        confidence=0.72,
        price=21000.25,
        timestamp_ns=123,
        detector_id="dom.imbalance.v1",
    )

    output = DOMIntelligenceOutput(
        events=[event],
        feature_row=feature_row,
        evaluated_at_ns=456,
        bar_index=17,
        dom_state_version=3,
    )

    assert output.events == [event]
    assert output.feature_row == feature_row
    assert output.dom_state_version == 3


def test_dom_intelligence_feature_row_aligns_feature_names_and_values():
    row = DOMIntelligenceFeatureRow(
        timestamp_ns=1,
        feature_names=["a", "b", "c"],
        feature_values=np.array([1.0, 2.0, 3.0], dtype=np.float32),
        bar_index=0,
        session_id="session-1",
        source_detector_ids=["dom.depth.v1"],
    )

    assert len(row.feature_names) == len(row.feature_values)
    assert row.feature_values.dtype == np.float64


def test_dom_intelligence_feature_row_rejects_length_mismatch():
    with pytest.raises(ValueError, match="same length"):
        DOMIntelligenceFeatureRow(
            timestamp_ns=1,
            feature_names=["a", "b"],
            feature_values=np.array([1.0]),
            bar_index=0,
            session_id="session-1",
            source_detector_ids=["dom.depth.v1"],
        )


def test_dom_ownership_docstring_is_present():
    doc = DOMIntelligenceEvent.__module__
    module = __import__(doc, fromlist=["__doc__"])

    assert module.__doc__ is not None
    assert "DOM STATE OWNERSHIP RULE" in module.__doc__
    assert "MUST NOT instantiate a parallel or shadow DOMState" in module.__doc__
    assert "All detectors receive DOMSnapshot instances" in module.__doc__


def test_dom_intelligence_event_round_trip_access():
    snapshot = _sample_snapshot()
    event = DOMIntelligenceEvent(
        signal_id=SignalId.PIN_REGIME,
        tier=DetectorTier.HEURISTIC,
        replay_safety=ReplaySafety.REPLAY_DEGRADED,
        direction=Direction.BULLISH,
        confidence=0.91,
        price=21000.25,
        timestamp_ns=1_748_356_200_123_456_789,
        detector_id="dom.pull_replace.v1",
        metadata={"pull_ratio": 2.1, "window_ms": 250},
        dom_state_snapshot=snapshot,
    )

    assert event.signal_id is SignalId.PIN_REGIME
    assert event.tier is DetectorTier.HEURISTIC
    assert event.replay_safety is ReplaySafety.REPLAY_DEGRADED
    assert event.direction is Direction.BULLISH
    assert event.confidence == pytest.approx(0.91)
    assert event.price == 21000.25
    assert event.timestamp_ns == 1_748_356_200_123_456_789
    assert event.detector_id == "dom.pull_replace.v1"
    assert event.metadata["pull_ratio"] == pytest.approx(2.1)
    assert event.dom_state_snapshot == snapshot
