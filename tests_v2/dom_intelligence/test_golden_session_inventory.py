"""Verify golden session inventory — fixture existence, format, and schema compliance.

Validates:
1. All 3 fixture files exist
2. Deserialization via GoldenSessionSerializer.from_json()
3. format_version == "1.0"
4. instrument == "NQ"
5. Minimum dom_update counts per scenario
6. dom_update schema: price, side, volume, timestamp_ns keys present
7. intelligence_output schema conformance (DOMIntelligenceOutput-compatible)
8. Disconnect session has pre- and post-disconnect outputs
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deep6v2.signals.dom.golden_session import (
    GoldenSessionRecord,
    GoldenSessionSerializer,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"

REQUIRED_DOM_UPDATE_KEYS = {"price", "side", "volume", "timestamp_ns"}

REQUIRED_OUTPUT_KEYS = {"events", "evaluated_at_ns", "bar_index", "dom_state_version"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_session(name: str) -> GoldenSessionRecord:
    path = FIXTURES_DIR / name
    assert path.exists(), f"Fixture not found: {path}"
    return GoldenSessionSerializer.from_file(str(path))


# ---------------------------------------------------------------------------
# Fixture existence
# ---------------------------------------------------------------------------
class TestFixtureExistence:
    def test_quiet_rth_exists(self) -> None:
        assert (FIXTURES_DIR / "golden_quiet_rth.json").exists()

    def test_volatile_exists(self) -> None:
        assert (FIXTURES_DIR / "golden_volatile.json").exists()

    def test_disconnect_exists(self) -> None:
        assert (FIXTURES_DIR / "golden_disconnect.json").exists()


# ---------------------------------------------------------------------------
# Deserialization and format version
# ---------------------------------------------------------------------------
class TestDeserialization:
    @pytest.fixture(params=["golden_quiet_rth.json", "golden_volatile.json", "golden_disconnect.json"])
    def session(self, request: pytest.FixtureRequest) -> GoldenSessionRecord:
        return _load_session(request.param)

    def test_deserializes_to_record(self, session: GoldenSessionRecord) -> None:
        assert isinstance(session, GoldenSessionRecord)

    def test_format_version(self, session: GoldenSessionRecord) -> None:
        assert session.format_version == "1.0"

    def test_instrument_nq(self, session: GoldenSessionRecord) -> None:
        assert session.instrument == "NQ"

    def test_session_id_non_empty(self, session: GoldenSessionRecord) -> None:
        assert session.session_id


# ---------------------------------------------------------------------------
# DOM update counts
# ---------------------------------------------------------------------------
class TestDOMUpdateCounts:
    def test_quiet_rth_has_50_plus_updates(self) -> None:
        session = _load_session("golden_quiet_rth.json")
        assert len(session.dom_updates) >= 50

    def test_volatile_has_80_plus_updates(self) -> None:
        session = _load_session("golden_volatile.json")
        assert len(session.dom_updates) >= 80

    def test_disconnect_has_30_plus_updates(self) -> None:
        session = _load_session("golden_disconnect.json")
        assert len(session.dom_updates) >= 30


# ---------------------------------------------------------------------------
# DOM update schema
# ---------------------------------------------------------------------------
class TestDOMUpdateSchema:
    @pytest.fixture(params=["golden_quiet_rth.json", "golden_volatile.json", "golden_disconnect.json"])
    def session(self, request: pytest.FixtureRequest) -> GoldenSessionRecord:
        return _load_session(request.param)

    def test_all_updates_have_required_keys(self, session: GoldenSessionRecord) -> None:
        for i, update in enumerate(session.dom_updates):
            missing = REQUIRED_DOM_UPDATE_KEYS - set(update.keys())
            assert not missing, f"Update {i} missing keys: {missing}"

    def test_prices_are_numeric(self, session: GoldenSessionRecord) -> None:
        for update in session.dom_updates:
            assert isinstance(update["price"], (int, float))

    def test_volumes_are_positive(self, session: GoldenSessionRecord) -> None:
        for update in session.dom_updates:
            assert isinstance(update["volume"], int)
            assert update["volume"] > 0

    def test_timestamps_are_positive_ints(self, session: GoldenSessionRecord) -> None:
        for update in session.dom_updates:
            assert isinstance(update["timestamp_ns"], int)
            assert update["timestamp_ns"] > 0

    def test_side_is_valid(self, session: GoldenSessionRecord) -> None:
        valid_sides = {"BUY", "SELL"}
        for update in session.dom_updates:
            assert update["side"] in valid_sides, f"Invalid side: {update['side']}"


# ---------------------------------------------------------------------------
# Intelligence output schema
# ---------------------------------------------------------------------------
class TestIntelligenceOutputSchema:
    @pytest.fixture(params=["golden_quiet_rth.json", "golden_volatile.json", "golden_disconnect.json"])
    def session(self, request: pytest.FixtureRequest) -> GoldenSessionRecord:
        return _load_session(request.param)

    def test_outputs_have_required_keys(self, session: GoldenSessionRecord) -> None:
        for i, output in enumerate(session.intelligence_outputs):
            missing = REQUIRED_OUTPUT_KEYS - set(output.keys())
            assert not missing, f"Output {i} missing keys: {missing}"

    def test_events_is_list(self, session: GoldenSessionRecord) -> None:
        for output in session.intelligence_outputs:
            assert isinstance(output["events"], list)

    def test_evaluated_at_ns_is_nonneg(self, session: GoldenSessionRecord) -> None:
        for output in session.intelligence_outputs:
            assert output["evaluated_at_ns"] >= 0


# ---------------------------------------------------------------------------
# Scenario-specific checks
# ---------------------------------------------------------------------------
class TestQuietRTH:
    def test_no_events(self) -> None:
        session = _load_session("golden_quiet_rth.json")
        for output in session.intelligence_outputs:
            assert output["events"] == [], "Quiet session should have no events"

    def test_has_2_outputs(self) -> None:
        session = _load_session("golden_quiet_rth.json")
        assert len(session.intelligence_outputs) == 2


class TestVolatile:
    def test_has_events(self) -> None:
        session = _load_session("golden_volatile.json")
        total_events = sum(len(o["events"]) for o in session.intelligence_outputs)
        assert total_events >= 5, f"Volatile session should have >=5 events, got {total_events}"

    def test_has_5_outputs(self) -> None:
        session = _load_session("golden_volatile.json")
        assert len(session.intelligence_outputs) == 5

    def test_events_have_mechanical_tier(self) -> None:
        session = _load_session("golden_volatile.json")
        for output in session.intelligence_outputs:
            for event in output["events"]:
                assert event["tier"] == "MECHANICAL"

    def test_events_are_replay_safe(self) -> None:
        session = _load_session("golden_volatile.json")
        for output in session.intelligence_outputs:
            for event in output["events"]:
                assert event["replay_safety"] == "REPLAY_SAFE"


class TestDisconnect:
    def test_has_pre_and_post_outputs(self) -> None:
        session = _load_session("golden_disconnect.json")
        assert len(session.intelligence_outputs) >= 2, "Need pre- and post-disconnect outputs"

    def test_pre_disconnect_has_event(self) -> None:
        session = _load_session("golden_disconnect.json")
        pre = session.intelligence_outputs[0]
        assert len(pre["events"]) >= 1

    def test_post_reconnect_has_event(self) -> None:
        session = _load_session("golden_disconnect.json")
        post = session.intelligence_outputs[-1]
        assert len(post["events"]) >= 1

    def test_timestamp_gap_between_phases(self) -> None:
        """Post-reconnect updates should have significantly later timestamps than pre-disconnect."""
        session = _load_session("golden_disconnect.json")
        updates = session.dom_updates
        # Find the gap: timestamps should jump by >1s (1_000_000_000 ns)
        max_gap = 0
        for i in range(1, len(updates)):
            gap = updates[i]["timestamp_ns"] - updates[i - 1]["timestamp_ns"]
            if gap > max_gap:
                max_gap = gap
        assert max_gap > 1_000_000_000, f"Expected reconnect gap >1s, max gap was {max_gap}ns"

    def test_metadata_has_lifecycle_flag(self) -> None:
        session = _load_session("golden_disconnect.json")
        assert session.metadata.get("has_lifecycle_event") is True


# ---------------------------------------------------------------------------
# Roundtrip integrity
# ---------------------------------------------------------------------------
class TestRoundtrip:
    @pytest.fixture(params=["golden_quiet_rth.json", "golden_volatile.json", "golden_disconnect.json"])
    def fixture_name(self, request: pytest.FixtureRequest) -> str:
        return request.param

    def test_json_roundtrip(self, fixture_name: str) -> None:
        original = _load_session(fixture_name)
        json_str = GoldenSessionSerializer.to_json(original)
        restored = GoldenSessionSerializer.from_json(json_str)
        assert original.session_id == restored.session_id
        assert original.format_version == restored.format_version
        assert original.instrument == restored.instrument
        assert len(original.dom_updates) == len(restored.dom_updates)
        assert len(original.intelligence_outputs) == len(restored.intelligence_outputs)
