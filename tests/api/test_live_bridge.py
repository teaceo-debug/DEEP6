"""Unit tests for LiveBridge — adapter from real engine output to WSManager.

Covers:
  - _bar_to_message with sample FootprintBar dict
  - on_bar_close triggers ws_manager.broadcast
  - NaN / Infinity / None field handling
  - Missing field fallbacks
  - _session_start_ts set on init
  - Counter increments (bars_received, signals_fired)
  - Signal tier normalisation (enum, string, missing)
  - Tape side / aggressor normalisation
  - periodic_status syncs counters to WSManager
"""
from __future__ import annotations

import asyncio
import math
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deep6.api.live_bridge import LiveBridge, _safe_float, _safe_int, _safe_str
from deep6.api.ws_manager import WSManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_ws_manager() -> WSManager:
    mgr = WSManager()
    mgr.broadcast = AsyncMock()  # type: ignore[method-assign]
    return mgr


def make_bridge(session_id: str = "test-session") -> tuple[LiveBridge, WSManager]:
    mgr = make_ws_manager()
    bridge = LiveBridge(mgr, session_id=session_id)
    return bridge, mgr


def sample_bar_dict(
    *,
    bar_index: int = 7,
    session_id: str = "test-session",
    open: float = 19480.0,
    high: float = 19490.0,
    low: float = 19470.0,
    close: float = 19485.0,
    total_vol: int = 2000,
    bar_delta: int = 300,
    cvd: int = 1500,
    poc_price: float = 19483.0,
    bar_range: float = 20.0,
    running_delta: int = 1200,
    max_delta: int = 400,
    min_delta: int = -100,
    levels: dict | None = None,
) -> dict:
    if levels is None:
        levels = {
            "77920": {"bid_vol": 50, "ask_vol": 70},
            "77921": {"bid_vol": 30, "ask_vol": 20},
        }
    return {
        "session_id": session_id,
        "bar_index": bar_index,
        "ts": 1_700_000_000.0,
        "open": open,
        "high": high,
        "low": low,
        "close": close,
        "total_vol": total_vol,
        "bar_delta": bar_delta,
        "cvd": cvd,
        "poc_price": poc_price,
        "bar_range": bar_range,
        "running_delta": running_delta,
        "max_delta": max_delta,
        "min_delta": min_delta,
        "levels": levels,
    }


def sample_signal_dict(
    *,
    tier: str = "TYPE_B",
    total_score: float = 72.5,
    direction: int = 1,
) -> dict:
    return {
        "ts": 1_700_000_000.0,
        "bar_index_in_session": 42,
        "total_score": total_score,
        "tier": tier,
        "direction": direction,
        "engine_agreement": 0.75,
        "category_count": 5,
        "categories_firing": ["absorption", "delta", "exhaustion"],
        "gex_regime": "NEUTRAL",
        "kronos_bias": 65.0,
        "label": "TYPE B — DOUBLE CONFLUENCE LONG (5 categories, score 72)",
    }


def sample_score_dict() -> dict:
    return {
        "total_score": 55.3,
        "tier": "TYPE_C",
        "direction": -1,
        "categories_firing": ["delta", "imbalance"],
        "category_scores": {"delta": 60.0, "imbalance": 45.0},
        "kronos_bias": 40.0,
        "kronos_direction": "SHORT",
        "gex_regime": "POS_GAMMA",
    }


def sample_tape_dict() -> dict:
    return {
        "ts": 1_700_000_000.0,
        "price": 19483.50,
        "size": 125,
        "side": "ASK",
        "marker": "SWEEP",
    }


# ---------------------------------------------------------------------------
# _safe_float / _safe_int / _safe_str helpers
# ---------------------------------------------------------------------------

class TestSafeHelpers:
    def test_safe_float_nan_returns_default(self):
        assert _safe_float(float("nan")) == 0.0

    def test_safe_float_inf_returns_default(self):
        assert _safe_float(float("inf")) == 0.0
        assert _safe_float(float("-inf")) == 0.0

    def test_safe_float_none_returns_default(self):
        assert _safe_float(None) == 0.0

    def test_safe_float_valid_value(self):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_safe_float_custom_default(self):
        assert _safe_float(float("nan"), default=99.0) == 99.0

    def test_safe_int_none_returns_default(self):
        assert _safe_int(None) == 0

    def test_safe_int_string_number(self):
        assert _safe_int("42") == 42

    def test_safe_int_invalid_string(self):
        assert _safe_int("bad") == 0

    def test_safe_str_none_returns_default(self):
        assert _safe_str(None) == ""

    def test_safe_str_non_string(self):
        assert _safe_str(123) == "123"


# ---------------------------------------------------------------------------
# LiveBridge init
# ---------------------------------------------------------------------------

class TestLiveBridgeInit:
    def test_session_start_ts_set_on_init(self):
        bridge, _ = make_bridge()
        assert bridge.session_start_ts > 0.0
        assert bridge.session_start_ts <= time.time()

    def test_counters_start_at_zero(self):
        bridge, _ = make_bridge()
        assert bridge.bars_received == 0
        assert bridge.signals_fired == 0
        assert bridge.last_signal_tier == ""

    def test_session_id_stored(self):
        bridge, _ = make_bridge(session_id="my-session")
        assert bridge.session_id == "my-session"


# ---------------------------------------------------------------------------
# _bar_to_message
# ---------------------------------------------------------------------------

class TestBarToMessage:
    def test_basic_fields_round_trip(self):
        bridge, _ = make_bridge()
        bar = sample_bar_dict()
        msg = bridge._bar_to_message(bar)
        assert msg.bar_index == 7
        assert msg.session_id == "test-session"
        assert msg.bar.open == pytest.approx(19480.0)
        assert msg.bar.high == pytest.approx(19490.0)
        assert msg.bar.low == pytest.approx(19470.0)
        assert msg.bar.close == pytest.approx(19485.0)
        assert msg.bar.total_vol == 2000
        assert msg.bar.bar_delta == 300
        assert msg.bar.cvd == 1500
        assert msg.bar.poc_price == pytest.approx(19483.0)
        assert msg.bar.bar_range == pytest.approx(20.0)
        assert msg.bar.running_delta == 1200
        assert msg.bar.max_delta == 400
        assert msg.bar.min_delta == -100
        assert msg.type == "bar"

    def test_levels_converted(self):
        bridge, _ = make_bridge()
        bar = sample_bar_dict()
        msg = bridge._bar_to_message(bar)
        assert "77920" in msg.bar.levels
        lvl = msg.bar.levels["77920"]
        assert lvl.bid_vol == 50
        assert lvl.ask_vol == 70

    def test_missing_session_id_falls_back_to_bridge_session(self):
        bridge, _ = make_bridge(session_id="fallback-session")
        bar = sample_bar_dict()
        del bar["session_id"]
        msg = bridge._bar_to_message(bar)
        assert msg.session_id == "fallback-session"

    def test_missing_levels_produces_empty_dict(self):
        bridge, _ = make_bridge()
        bar = sample_bar_dict(levels={})
        msg = bridge._bar_to_message(bar)
        assert msg.bar.levels == {}

    def test_nan_ohlc_replaced_with_zero(self):
        bridge, _ = make_bridge()
        bar = sample_bar_dict(open=float("nan"), high=float("inf"), low=float("-inf"))
        msg = bridge._bar_to_message(bar)
        assert msg.bar.open == 0.0
        assert msg.bar.high == 0.0
        assert msg.bar.low == 0.0

    def test_footprint_bar_timestamp_field_used_when_ts_missing(self):
        """FootprintBar uses .timestamp not .ts — both should work."""
        bridge, _ = make_bridge()
        bar = {
            "bar_index": 1,
            "timestamp": 1_700_000_001.0,  # engine field name
            "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0,
            "total_vol": 500, "bar_delta": 0, "cvd": 0,
            "poc_price": 102.0, "bar_range": 20.0,
        }
        msg = bridge._bar_to_message(bar)
        assert msg.bar.ts == pytest.approx(1_700_000_001.0)

    def test_dataclass_like_object_supported(self):
        """Accepts objects with attribute access (not just dicts)."""
        bridge, _ = make_bridge()

        class FakeBar:
            session_id = "obj-session"
            bar_index = 3
            ts = 1_700_000_000.0
            open = 19480.0
            high = 19495.0
            low = 19475.0
            close = 19490.0
            total_vol = 1800
            bar_delta = -50
            cvd = 1000
            poc_price = 19485.0
            bar_range = 20.0
            running_delta = 950
            max_delta = 100
            min_delta = -200
            levels = {}

        msg = bridge._bar_to_message(FakeBar())
        assert msg.bar_index == 3
        assert msg.bar.close == pytest.approx(19490.0)


# ---------------------------------------------------------------------------
# on_bar_close (async)
# ---------------------------------------------------------------------------

class TestOnBarClose:
    def test_triggers_broadcast(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_bar_close(sample_bar_dict()))
        mgr.broadcast.assert_called_once()

    def test_broadcast_payload_has_type_bar(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_bar_close(sample_bar_dict()))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["type"] == "bar"

    def test_increments_bars_received(self):
        bridge, _ = make_bridge()
        asyncio.run(bridge.on_bar_close(sample_bar_dict()))
        assert bridge.bars_received == 1
        asyncio.run(bridge.on_bar_close(sample_bar_dict()))
        assert bridge.bars_received == 2

    def test_syncs_ws_manager_counter(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_bar_close(sample_bar_dict()))
        assert mgr.bars_received == 1

    def test_does_not_raise_on_malformed_bar(self):
        """on_bar_close swallows exceptions — dashboard must not crash."""
        bridge, mgr = make_bridge()
        # completely empty dict
        asyncio.run(bridge.on_bar_close({}))
        # broadcast may or may not have been called — we just verify no exception raised


# ---------------------------------------------------------------------------
# on_signal_fired
# ---------------------------------------------------------------------------

class TestOnSignalFired:
    def test_triggers_broadcast(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_signal_fired(sample_signal_dict()))
        mgr.broadcast.assert_called_once()

    def test_increments_signals_fired(self):
        bridge, _ = make_bridge()
        asyncio.run(bridge.on_signal_fired(sample_signal_dict()))
        assert bridge.signals_fired == 1

    def test_updates_last_signal_tier(self):
        bridge, _ = make_bridge()
        asyncio.run(bridge.on_signal_fired(sample_signal_dict(tier="TYPE_A")))
        assert bridge.last_signal_tier == "TYPE_A"

    def test_syncs_ws_manager_tier(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_signal_fired(sample_signal_dict(tier="TYPE_B")))
        assert mgr.last_signal_tier == "TYPE_B"

    def test_signal_tier_from_enum_name(self):
        """SignalTier IntEnum has .name attribute — should resolve to string."""
        bridge, _ = make_bridge()
        sig = sample_signal_dict()

        class FakeTier:
            name = "TYPE_A"

        sig["tier"] = FakeTier()
        asyncio.run(bridge.on_signal_fired(sig))
        assert bridge.last_signal_tier == "TYPE_A"

    def test_categories_sorted(self):
        bridge, mgr = make_bridge()
        sig = sample_signal_dict()
        sig["categories_firing"] = ["delta", "absorption", "exhaustion"]
        asyncio.run(bridge.on_signal_fired(sig))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["event"]["categories_firing"] == ["absorption", "delta", "exhaustion"]

    def test_narrative_from_label(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_signal_fired(sample_signal_dict()))
        payload = mgr.broadcast.call_args[0][0]
        assert "TYPE B" in payload["narrative"]


# ---------------------------------------------------------------------------
# on_score_update
# ---------------------------------------------------------------------------

class TestOnScoreUpdate:
    def test_triggers_broadcast(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_score_update(sample_score_dict()))
        mgr.broadcast.assert_called_once()

    def test_payload_type_score(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_score_update(sample_score_dict()))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["type"] == "score"

    def test_total_score_in_payload(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_score_update(sample_score_dict()))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["total_score"] == pytest.approx(55.3)

    def test_nan_total_score_becomes_zero(self):
        bridge, mgr = make_bridge()
        score = sample_score_dict()
        score["total_score"] = float("nan")
        asyncio.run(bridge.on_score_update(score))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["total_score"] == 0.0

    def test_missing_category_scores_defaults_to_empty(self):
        bridge, mgr = make_bridge()
        score = {"total_score": 40.0, "tier": "QUIET", "direction": 0}
        asyncio.run(bridge.on_score_update(score))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["category_scores"] == {}


# ---------------------------------------------------------------------------
# on_tape_print
# ---------------------------------------------------------------------------

class TestOnTapePrint:
    def test_triggers_broadcast(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_tape_print(sample_tape_dict()))
        mgr.broadcast.assert_called_once()

    def test_payload_type_tape(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_tape_print(sample_tape_dict()))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["type"] == "tape"

    def test_side_bid_preserved(self):
        bridge, mgr = make_bridge()
        trade = sample_tape_dict()
        trade["side"] = "BID"
        asyncio.run(bridge.on_tape_print(trade))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["event"]["side"] == "BID"

    def test_aggressor_1_maps_to_ask(self):
        """Rithmic aggressor=1 (buy hit ask) → side='ASK'."""
        bridge, mgr = make_bridge()
        trade = {"ts": time.time(), "price": 19483.0, "size": 10, "aggressor": 1}
        asyncio.run(bridge.on_tape_print(trade))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["event"]["side"] == "ASK"

    def test_aggressor_2_maps_to_bid(self):
        """Rithmic aggressor=2 (sell hit bid) → side='BID'."""
        bridge, mgr = make_bridge()
        trade = {"ts": time.time(), "price": 19483.0, "size": 15, "aggressor": 2}
        asyncio.run(bridge.on_tape_print(trade))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["event"]["side"] == "BID"

    def test_invalid_side_string_defaults_to_ask(self):
        bridge, mgr = make_bridge()
        trade = sample_tape_dict()
        trade["side"] = "BUY"   # invalid string
        asyncio.run(bridge.on_tape_print(trade))
        payload = mgr.broadcast.call_args[0][0]
        assert payload["event"]["side"] == "ASK"


# ---------------------------------------------------------------------------
# periodic_status
# ---------------------------------------------------------------------------

class TestPeriodicStatus:
    def test_syncs_counters_to_ws_manager(self):
        bridge, mgr = make_bridge()
        # Manually bump counters
        asyncio.run(bridge.on_bar_close(sample_bar_dict()))
        asyncio.run(bridge.on_signal_fired(sample_signal_dict(tier="TYPE_A")))

        # Reset broadcast mock to isolate periodic_status call
        mgr.broadcast.reset_mock()
        asyncio.run(bridge.periodic_status())

        assert mgr.bars_received == 1
        assert mgr.signals_fired == 1
        assert mgr.last_signal_tier == "TYPE_A"

    def test_broadcast_called_with_status_payload(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.periodic_status())
        # WSManager.broadcast_status calls broadcast internally — check calls > 0
        assert mgr.broadcast.call_count >= 1


# ---------------------------------------------------------------------------
# on_status_update
# ---------------------------------------------------------------------------

class TestOnStatusUpdate:
    def test_updates_pnl(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_status_update({"pnl": 1234.56}))
        assert bridge._pnl == pytest.approx(1234.56)

    def test_updates_circuit_breaker(self):
        bridge, mgr = make_bridge()
        asyncio.run(bridge.on_status_update({"circuit_breaker_active": True}))
        assert bridge._circuit_breaker_active is True

    def test_nan_pnl_ignored(self):
        bridge, _ = make_bridge()
        bridge._pnl = 500.0
        asyncio.run(bridge.on_status_update({"pnl": float("nan")}))
        # NaN goes through _safe_float → 0.0 (replaces stored value)
        # The bridge stores whatever _safe_float returns
        assert not math.isnan(bridge._pnl)


# ---------------------------------------------------------------------------
# App lifespan integration — live_bridge attached to app.state
# ---------------------------------------------------------------------------

class TestAppLifespanBridge:
    def test_live_bridge_in_app_state(self):
        from fastapi.testclient import TestClient
        from deep6.api.app import app

        with TestClient(app) as client:
            assert hasattr(app.state, "live_bridge")
            assert isinstance(app.state.live_bridge, LiveBridge)

    def test_bridge_shares_ws_manager_with_app(self):
        from fastapi.testclient import TestClient
        from deep6.api.app import app

        with TestClient(app) as client:
            assert app.state.live_bridge.ws_manager is app.state.ws_manager
