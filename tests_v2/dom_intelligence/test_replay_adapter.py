from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import get_type_hints

from deep6v2.signals.dom.adapters.replay_adapter import ReplayDOMAdapter
from deep6v2.state.dom import DOMState
from deep6v2.types.dom import DOMSnapshot, DOMUpdate
from deep6v2.types.dom_intelligence import DOMIntelligenceEvent, DetectorTier, ReplaySafety
from deep6v2.types.execution import OrderSide
from deep6v2.types.signal import Direction, SignalId

ROOT = Path(__file__).resolve().parents[2]
LIVE_ADAPTER_PATH = ROOT / "deep6v2" / "signals" / "dom" / "adapters" / "live_adapter.py"


@dataclass
class SnapshotSequence:
    snapshots: list[DOMSnapshot]

    def to_json(self) -> str:
        payload = [snapshot.model_dump(mode="json") for snapshot in self.snapshots]
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _build_state() -> DOMState:
    return DOMState(base_price=20_000.0, num_levels=4000)


def _updates() -> list[DOMUpdate]:
    return [
        DOMUpdate(side=OrderSide.BUY, level=0, price=20_010.00, volume=100),
        DOMUpdate(side=OrderSide.BUY, level=1, price=20_009.75, volume=60),
        DOMUpdate(side=OrderSide.SELL, level=0, price=20_010.25, volume=125),
        DOMUpdate(side=OrderSide.SELL, level=1, price=20_010.50, volume=80),
        DOMUpdate(side=OrderSide.BUY, level=0, price=20_010.00, volume=90),
        DOMUpdate(side=OrderSide.SELL, level=1, price=20_010.50, volume=0),
    ]


def _event() -> DOMIntelligenceEvent:
    return DOMIntelligenceEvent(
        signal_id=SignalId.IMB_01,
        tier=DetectorTier.MECHANICAL,
        replay_safety=ReplaySafety.REPLAY_SAFE,
        direction=Direction.BULLISH,
        confidence=0.82,
        price=20_010.00,
        timestamp_ns=123,
        detector_id="dom.imbalance.v1",
        metadata={"threshold": 1.5},
    )


def _snapshot_json(snapshot: DOMSnapshot) -> str:
    return json.dumps(snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def test_process_event_is_deterministic_for_fixture_sequence() -> None:
    updates = _updates()

    first_adapter = ReplayDOMAdapter(_build_state(), session_id="golden-a")
    first_snapshots = [_snapshot_json(first_adapter.process_event(update)) for update in updates]

    second_adapter = ReplayDOMAdapter(_build_state(), session_id="golden-a")
    second_snapshots = [_snapshot_json(second_adapter.process_event(update)) for update in updates]

    assert first_snapshots == second_snapshots
    assert first_adapter._version == len(updates)


def test_replay_sequence_processes_all_events_in_order() -> None:
    adapter = ReplayDOMAdapter(_build_state(), session_id="sequence")

    snapshots = adapter.replay_sequence(_updates())

    assert len(snapshots) == len(_updates())
    assert [(level.price, level.volume) for level in snapshots[-1].bids] == [
        (20_010.0, 90),
        (20_009.75, 60),
    ]
    assert [(level.price, level.volume) for level in snapshots[-1].asks] == [
        (20_010.25, 125),
    ]
    assert [snapshot.timestamp for snapshot in snapshots] == [
        datetime(1970, 1, 1, 0, 0, 0, microsecond=index, tzinfo=UTC)
        for index in range(len(_updates()))
    ]


def test_reset_clears_state_and_replay_is_identical_after_rerun() -> None:
    adapter = ReplayDOMAdapter(_build_state(), session_id="first")
    first_run = SnapshotSequence(adapter.replay_sequence(_updates())).to_json()

    adapter.reset(session_id="second")
    second_run = SnapshotSequence(adapter.replay_sequence(_updates())).to_json()

    assert first_run == second_run
    assert adapter._session_id == "second"


def test_build_output_sets_dom_state_version_and_preserves_signature_contract() -> None:
    adapter = ReplayDOMAdapter(_build_state(), session_id="output")
    snapshot = adapter.process_event(_updates()[0])

    output = adapter.build_output(
        events=[_event()],
        snapshot=snapshot,
        bar_index=17,
        evaluated_at_ns=456,
    )

    assert output.dom_state_version == 1
    assert output.bar_index == 17
    assert output.evaluated_at_ns == 456
    assert output.events[0].dom_state_snapshot == snapshot


def test_replay_sequence_is_byte_identical_across_separate_runs() -> None:
    updates = _updates()
    first = SnapshotSequence(ReplayDOMAdapter(_build_state(), session_id="a").replay_sequence(updates)).to_json()
    second = SnapshotSequence(ReplayDOMAdapter(_build_state(), session_id="b").replay_sequence(updates)).to_json()

    assert first == second


def test_adapter_receives_domstate_in_constructor_without_instantiating_new_one() -> None:
    dom_state = _build_state()
    adapter = ReplayDOMAdapter(dom_state, session_id="owned")

    adapter.process_event(_updates()[0])

    assert adapter._dom_state is dom_state
    assert dom_state.get_best_bid() == 20_010.0


def test_build_output_signature_matches_live_adapter_interface_contract() -> None:
    replay_parameters = list(get_type_hints(ReplayDOMAdapter.build_output).items())

    assert replay_parameters == [
        ("events", list[DOMIntelligenceEvent]),
        ("snapshot", DOMSnapshot),
        ("bar_index", int),
        ("evaluated_at_ns", int),
        ("return", __import__("deep6v2.types.dom_intelligence", fromlist=["DOMIntelligenceOutput"]).DOMIntelligenceOutput),
    ]
    if LIVE_ADAPTER_PATH.exists():
        live_source = LIVE_ADAPTER_PATH.read_text(encoding="utf-8")
        assert "def build_output(" in live_source
        assert "events: list[DOMIntelligenceEvent]" in live_source
        assert "snapshot: DOMSnapshot" in live_source
        assert "bar_index: int" in live_source
        assert "evaluated_at_ns: int" in live_source
