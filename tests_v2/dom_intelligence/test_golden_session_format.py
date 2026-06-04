from __future__ import annotations

from datetime import UTC, datetime

import numpy as np

from deep6v2.signals.dom.golden_session import (
    GoldenSessionRecord,
    GoldenSessionRecorder,
    GoldenSessionSerializer,
)
from deep6v2.types.dom import DOMLevel, DOMSnapshot, DOMUpdate
from deep6v2.types.dom_intelligence import (
    DOMIntelligenceEvent,
    DOMIntelligenceFeatureRow,
    DOMIntelligenceOutput,
    DetectorTier,
    ReplaySafety,
)
from deep6v2.types.execution import OrderSide
from deep6v2.types.signal import Direction, SignalId


def _event(snapshot: DOMSnapshot) -> DOMIntelligenceEvent:
    return DOMIntelligenceEvent(
        signal_id=SignalId.ABS_01,
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        direction=Direction.BULLISH,
        confidence=0.94,
        price=21_000.25,
        timestamp_ns=1_748_356_200_123_456_789,
        detector_id="dom.absorption.v1",
        metadata={"detector_tag": "absorption", "strength": 0.87},
        dom_state_snapshot=snapshot,
    )


def _snapshot() -> DOMSnapshot:
    return DOMSnapshot(
        timestamp=datetime(2026, 5, 27, 14, 30, tzinfo=UTC),
        bids=[DOMLevel(price=21_000.0, volume=120), DOMLevel(price=20_999.75, volume=80)],
        asks=[DOMLevel(price=21_000.25, volume=140)],
    )


def _output(snapshot: DOMSnapshot) -> DOMIntelligenceOutput:
    feature_row = DOMIntelligenceFeatureRow(
        timestamp_ns=1_234,
        feature_names=["imbalance", "depth_ratio"],
        feature_values=np.array([1.5, 0.75]),
        bar_index=17,
        session_id="2026-05-27-RTH",
        source_detector_ids=["dom.absorption.v1"],
    )
    return DOMIntelligenceOutput(
        events=[_event(snapshot)],
        feature_row=feature_row,
        evaluated_at_ns=1_234_567,
        bar_index=17,
        dom_state_version=3,
    )


def test_round_trip_preserves_session_id_timestamps_levels_and_detector_metadata() -> None:
    timestamps = iter([111_000, 222_000])
    recorder = GoldenSessionRecorder(
        clock=lambda: next(timestamps),
        metadata={"date": "2026-05-27", "session_type": "RTH", "notes": "golden parity"},
    )

    recorder.record_update(DOMUpdate(side=OrderSide.BUY, level=0, price=21_000.0, volume=120))
    recorder.record_update(DOMUpdate(side=OrderSide.SELL, level=1, price=21_000.25, volume=140))
    snapshot = _snapshot()
    recorder.record_output(_output(snapshot))

    record = recorder.finalize(session_id="session-123", instrument="NQ")
    restored = GoldenSessionSerializer.from_json(GoldenSessionSerializer.to_json(record))

    assert restored.session_id == "session-123"
    assert restored.recorded_at_iso == record.recorded_at_iso
    assert restored.instrument == "NQ"
    assert restored.format_version == "1.0"
    assert restored.metadata == record.metadata
    assert restored.dom_updates[0]["timestamp_ns"] == 111_000
    assert restored.dom_updates[1]["timestamp_ns"] == 222_000
    assert restored.dom_updates[0]["level"] == 0
    assert restored.dom_updates[1]["level"] == 1
    assert restored.dom_updates[0]["side"] == "BUY"
    assert restored.intelligence_outputs[0]["events"][0]["metadata"]["detector_tag"] == "absorption"
    assert restored.intelligence_outputs[0]["events"][0]["dom_state_snapshot"]["bids"][0]["price"] == 21_000.0


def test_dom_updates_preserve_order_after_round_trip() -> None:
    timestamps = iter([1, 2, 3])
    recorder = GoldenSessionRecorder(clock=lambda: next(timestamps))

    for level in range(3):
        recorder.record_update(DOMUpdate(side=OrderSide.BUY, level=level, price=21_000.0 + level, volume=100 + level))

    record = recorder.finalize(session_id="ordered")
    restored = GoldenSessionSerializer.from_json(GoldenSessionSerializer.to_json(record))

    assert [item["level"] for item in restored.dom_updates] == [0, 1, 2]
    assert [item["price"] for item in restored.dom_updates] == [21_000.0, 21_001.0, 21_002.0]


def test_intelligence_outputs_preserve_detector_metadata_after_round_trip() -> None:
    recorder = GoldenSessionRecorder(clock=lambda: 100)
    snapshot = _snapshot()
    recorder.record_output(_output(snapshot))

    restored = GoldenSessionSerializer.from_json(
        GoldenSessionSerializer.to_json(recorder.finalize(session_id="outputs"))
    )

    event = restored.intelligence_outputs[0]["events"][0]
    assert event["detector_id"] == "dom.absorption.v1"
    assert event["metadata"] == {"detector_tag": "absorption", "strength": 0.87}
    assert event["timestamp_ns"] == 1_748_356_200_123_456_789
    assert event["dom_state_snapshot"]["asks"][0]["volume"] == 140


def test_metadata_round_trips_cleanly() -> None:
    recorder = GoldenSessionRecorder(clock=lambda: 42, metadata={"date": "2026-05-27", "notes": "ok"})
    record = recorder.finalize(session_id="meta")
    restored = GoldenSessionSerializer.from_json(GoldenSessionSerializer.to_json(record))

    assert restored.metadata == {"date": "2026-05-27", "notes": "ok"}


def test_format_version_is_preserved() -> None:
    record = GoldenSessionRecord(
        session_id="v1",
        recorded_at_iso="2026-05-27T14:30:00+00:00",
        instrument="NQ",
        dom_updates=[],
        intelligence_outputs=[],
        metadata={},
        format_version="1.0",
    )

    restored = GoldenSessionSerializer.from_json(GoldenSessionSerializer.to_json(record))
    assert restored.format_version == "1.0"


def test_empty_updates_list_serializes_and_deserializes_cleanly(tmp_path) -> None:
    record = GoldenSessionRecord(
        session_id="empty",
        recorded_at_iso="2026-05-27T14:30:00+00:00",
        instrument="NQ",
        dom_updates=[],
        intelligence_outputs=[],
        metadata={},
    )

    path = tmp_path / "golden.json"
    GoldenSessionSerializer.to_file(record, str(path))
    restored = GoldenSessionSerializer.from_file(str(path))

    assert restored.dom_updates == []
    assert restored.intelligence_outputs == []
    assert path.read_text(encoding="utf-8")
