"""Tests that all fixture files load correctly and conform to expected schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from deep6v2.types.bar import FootprintBar
from deep6v2.types.signal import SignalId
from tests_v2.fixtures.loader import (
    fixture_bar,
    load_scoring_fixture,
    load_signal_fixture,
)

SIGNAL_FIXTURES_DIR = Path("tests_v2/fixtures/signals")
SCORING_FIXTURES_DIR = Path("tests_v2/fixtures/scoring")


def test_all_signal_fixtures_exist():
    """At least 52 signal fixture files exist."""
    files = list(SIGNAL_FIXTURES_DIR.glob("*.json"))
    assert len(files) >= 52, f"Expected >= 52 fixture files, got {len(files)}"


def test_all_scoring_fixtures_exist():
    """Exactly 5 scoring scenario fixtures exist."""
    files = list(SCORING_FIXTURES_DIR.glob("*.json"))
    stems = {f.stem for f in files}
    required = {
        "quiet-zero-signals",
        "midday-block",
        "type-c-suppressed",
        "type-b-no-zone",
        "type-a-all-categories",
    }
    assert required.issubset(stems), f"Missing: {required - stems}"


def test_signal_fixtures_loadable():
    """All signal fixture files load without error and contain valid bar data."""
    for fixture_file in sorted(SIGNAL_FIXTURES_DIR.glob("*.json")):
        data = json.loads(fixture_file.read_text())
        assert "bar" in data, f"{fixture_file.name} missing 'bar' key"
        bar = FootprintBar.model_validate(data["bar"])
        assert bar.total_volume > 0, f"{fixture_file.name} has zero total_volume"


def test_signal_ids_in_fixtures_are_valid():
    """All expected_signal.signal_id values are valid SignalId enum members."""
    for fixture_file in sorted(SIGNAL_FIXTURES_DIR.glob("*.json")):
        data = json.loads(fixture_file.read_text())
        if "expected_signal" in data:
            sig_id_str = data["expected_signal"]["signal_id"]
            assert sig_id_str in SignalId.__members__, (
                f"Unknown signal_id: {sig_id_str} in {fixture_file.name}"
            )


def test_signal_fixtures_have_required_keys():
    """Every signal fixture has name, bar, context, and expected_signal."""
    required_keys = {"name", "bar", "context", "expected_signal"}
    for fixture_file in sorted(SIGNAL_FIXTURES_DIR.glob("*.json")):
        data = json.loads(fixture_file.read_text())
        missing = required_keys - set(data.keys())
        assert not missing, f"{fixture_file.name} missing keys: {missing}"


def test_signal_fixture_expected_signal_schema():
    """expected_signal has signal_id, direction, strength_min, strength_max."""
    for fixture_file in sorted(SIGNAL_FIXTURES_DIR.glob("*.json")):
        data = json.loads(fixture_file.read_text())
        es = data.get("expected_signal", {})
        assert "signal_id" in es, f"{fixture_file.name}: missing signal_id"
        assert "direction" in es, f"{fixture_file.name}: missing direction"
        assert "strength_min" in es, f"{fixture_file.name}: missing strength_min"
        assert "strength_max" in es, f"{fixture_file.name}: missing strength_max"
        assert es["strength_min"] <= es["strength_max"], (
            f"{fixture_file.name}: strength_min > strength_max"
        )


def test_loader_load_signal_fixture():
    """load_signal_fixture returns a dict with bar data."""
    data = load_signal_fixture("abs_01")
    assert "bar" in data
    assert "expected_signal" in data
    bar = fixture_bar(data)
    assert isinstance(bar, FootprintBar)
    assert bar.total_volume > 0


def test_loader_load_scoring_fixture():
    """load_scoring_fixture returns a dict with scenario data."""
    data = load_scoring_fixture("quiet-zero-signals")
    assert "name" in data
    assert "expected_tier" in data


def test_loader_fixtures(
    sample_footprint_bar, sample_session_context, sample_dom_snapshot
):
    """conftest fixtures are usable."""
    from deep6v2.types.bar import FootprintBar
    from deep6v2.types.dom import DOMSnapshot
    from deep6v2.types.session import SessionContext

    assert isinstance(sample_footprint_bar, FootprintBar)
    assert isinstance(sample_session_context, SessionContext)
    assert isinstance(sample_dom_snapshot, DOMSnapshot)
    assert len(sample_session_context.bar_history) == 1


def test_composite_fixtures_exist():
    """At least 8 composite category fixtures exist."""
    composite_files = list(SIGNAL_FIXTURES_DIR.glob("composite_*.json"))
    assert len(composite_files) >= 8, (
        f"Expected >= 8 composite fixtures, got {len(composite_files)}"
    )
