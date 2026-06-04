"""Test AtlasState — degraded detection, snapshot_dict."""
import time
import pytest
from nq_atlas.state import AtlasState


def test_fresh_state_is_degraded():
    assert AtlasState().degraded() is True


def test_state_with_chain_not_degraded(populated_state):
    assert populated_state.degraded() is False


def test_stale_state_is_degraded(populated_state):
    # Set last_chain_ts to far in the past
    populated_state.last_chain_ts = time.time() - 1000
    assert populated_state.degraded() is True


def test_snapshot_dict_contains_expected_keys(populated_state):
    snap = populated_state.snapshot_dict()
    assert "spots" in snap
    assert "degraded" in snap
    assert "uptime_sec" in snap
    assert snap["uptime_sec"] >= 0


def test_log_error_ring_buffer():
    state = AtlasState()
    for i in range(25):
        state.log_error("test", f"error {i}")
    assert len(state.errors) == 20  # capped at 20
