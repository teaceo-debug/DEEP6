from __future__ import annotations

import time
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from gexdoctor.monitor.adapters.flashalpha import FlashAlphaAdapter
from gexdoctor.monitor.schemas import FlashAlphaSnapshot


SAMPLE_LIVE_BUNDLE = {
    "as_of": "2026-05-28T14:30:00Z",
    "underlying_price": 480.50,
    "live_gex": 3_200_000_000.0,
    "live_gex_delta": -500_000_000.0,
    "live_gamma_flip": 475.0,
    "live_call_wall": 485.0,
    "live_put_wall": 470.0,
    "live_max_pain": 478.0,
    "live_pin_risk": 45.0,
    "oi_delta_confidence": 0.72,
    "contracts_with_flow": 15000,
    "flow_adjusted_dealer_risk": {
        "flow_direction": "amplifying",
        "flow_gex_pct_shift": 0.032,
        "live_net_dex": -300_000_000.0,
        "settled_net_gex": 3_000_000_000.0,
        "settled_net_dex": -280_000_000.0,
        "description": "Dealers long gamma, flow amplifying",
    },
}

SAMPLE_SETTLED = {
    "gex": {"net_gex": 2_800_000_000.0, "gamma_flip": 473.0, "spot": 479.5},
    "levels": {"call_wall": 484.0, "put_wall": 469.0, "max_pain": 477.0, "spot": 479.5},
}


@pytest.fixture
def adapter() -> FlashAlphaAdapter:
    return FlashAlphaAdapter(api_key="test-key", symbol="QQQ")


def test_parse_live_bundle_basic(adapter: FlashAlphaAdapter) -> None:
    snapshot = adapter._parse_live_bundle(SAMPLE_LIVE_BUNDLE)

    assert isinstance(snapshot, FlashAlphaSnapshot)
    assert snapshot.symbol == "QQQ"
    assert snapshot.regime.gex_sign == "positive"
    assert snapshot.regime.gamma_flip == 475.0
    assert snapshot.pin.pin_risk == 45.0


def test_dex_field_trap_uses_dealer_risk(adapter: FlashAlphaAdapter) -> None:
    snapshot = adapter._parse_live_bundle(SAMPLE_LIVE_BUNDLE)

    assert snapshot.regime.net_dex == -300_000_000.0
    assert snapshot.regime.net_dex != SAMPLE_LIVE_BUNDLE["live_gex_delta"]


def test_live_bundle_negative_gex(adapter: FlashAlphaAdapter) -> None:
    raw = deepcopy(SAMPLE_LIVE_BUNDLE)
    raw["live_gex"] = -1_000_000_000.0

    snapshot = adapter._parse_live_bundle(raw)

    assert snapshot.regime.gex_sign == "negative"


def test_settled_parse_basic(adapter: FlashAlphaAdapter) -> None:
    snapshot = adapter._parse_settled(SAMPLE_SETTLED)

    assert isinstance(snapshot, FlashAlphaSnapshot)
    assert snapshot.feed_quality.plan == "basic"
    assert snapshot.feed_quality.missing_fields
    assert snapshot.regime.net_gex == 2_800_000_000.0


def test_settled_fallback_missing_fields(adapter: FlashAlphaAdapter) -> None:
    snapshot = adapter._parse_settled(SAMPLE_SETTLED)

    assert "flow_direction" in snapshot.feed_quality.missing_fields
    assert "oi_delta_confidence" in snapshot.feed_quality.missing_fields
    assert "pin_risk" in snapshot.feed_quality.missing_fields


def test_live_bundle_missing_dex_marks_missing_field(adapter: FlashAlphaAdapter) -> None:
    raw = deepcopy(SAMPLE_LIVE_BUNDLE)
    raw["flow_adjusted_dealer_risk"] = {"flow_direction": "dampening"}

    snapshot = adapter._parse_live_bundle(raw)

    assert snapshot.regime.net_dex is None
    assert "net_dex" in snapshot.feed_quality.missing_fields


def test_live_bundle_stale_detection_marks_feed_quality(adapter: FlashAlphaAdapter) -> None:
    raw = deepcopy(SAMPLE_LIVE_BUNDLE)
    raw["as_of"] = (datetime.now(timezone.utc) - timedelta(seconds=150)).isoformat().replace("+00:00", "Z")

    snapshot = adapter._parse_live_bundle(raw)

    assert snapshot.feed_quality.latency_seconds is not None
    assert snapshot.feed_quality.latency_seconds >= 150
    assert "stale" in snapshot.feed_quality.missing_fields


def test_adapter_returns_none_on_complete_failure(adapter: FlashAlphaAdapter) -> None:
    adapter._fetch_live_bundle = AsyncMock(return_value=None)
    adapter._fetch_settled_fallback = AsyncMock(return_value=None)

    result = asyncio.run(adapter.poll())

    assert result is None


def test_cadence_guard_skips_rapid_poll(adapter: FlashAlphaAdapter) -> None:
    adapter._last_poll = time.monotonic()
    adapter._fetch_live_bundle = AsyncMock()

    result = asyncio.run(adapter.poll())

    assert result is None
    adapter._fetch_live_bundle.assert_not_awaited()


def test_session_phase_detection(adapter: FlashAlphaAdapter) -> None:
    assert adapter._detect_session_phase() in {"pre_market", "open", "intraday", "into_close"}
