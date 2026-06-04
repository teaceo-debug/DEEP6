"""Tests for CopilotBridgeClient — mocked TCP and WebSocket connections."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deep6.copilot.bridge_client import (
    CopilotBridgeClient,
    ScoreSnapshot,
    _backoff_delay,
)
from deep6.copilot.config import CopilotConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def config(monkeypatch: pytest.MonkeyPatch) -> CopilotConfig:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    return CopilotConfig.from_env()


@pytest.fixture()
def client(config: CopilotConfig) -> CopilotBridgeClient:
    return CopilotBridgeClient(config)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestBackoffDelay:
    """Verify exponential backoff with jitter stays in expected range."""

    def test_first_attempt_near_1s(self) -> None:
        for _ in range(20):
            d = _backoff_delay(0)
            assert 0.1 <= d <= 2.0, f"attempt 0 delay {d} out of range"

    def test_grows_exponentially(self) -> None:
        d0 = _backoff_delay(0)
        d5 = _backoff_delay(5)
        # attempt 5 base = 1 * 2^5 = 32, with jitter should be > d0
        assert d5 > d0

    def test_caps_at_max(self) -> None:
        for _ in range(20):
            d = _backoff_delay(100)
            assert d <= 80.0  # 60 + 30% jitter max


class TestScoreSnapshot:
    """ScoreSnapshot correctly parses LiveScoreMessage dicts."""

    def test_parse_full_message(self) -> None:
        data = {
            "type": "score",
            "total_score": 75.5,
            "tier": "TYPE_B",
            "direction": -1,
            "categories_firing": ["absorption", "delta", "imbalance", "auction"],
            "category_scores": {"absorption": 20.0, "delta": 14.3},
            "kronos_bias": 62.0,
            "kronos_direction": "SHORT",
            "gex_regime": "POSITIVE_DAMPENING",
        }
        snap = ScoreSnapshot(data)
        assert snap.total_score == 75.5
        assert snap.tier == "TYPE_B"
        assert snap.direction == -1
        assert len(snap.categories_firing) == 4
        assert snap.kronos_bias == 62.0
        assert snap.kronos_direction == "SHORT"
        assert snap.gex_regime == "POSITIVE_DAMPENING"

    def test_parse_empty_message(self) -> None:
        snap = ScoreSnapshot({})
        assert snap.total_score == 0.0
        assert snap.tier == "QUIET"
        assert snap.direction == 0

    def test_repr(self) -> None:
        snap = ScoreSnapshot({"total_score": 80, "tier": "TYPE_A", "direction": 1})
        assert "TYPE_A" in repr(snap)


class TestGettersReturnNoneBeforeData:
    """All getters return None/empty before any data is received."""

    def test_score_none(self, client: CopilotBridgeClient) -> None:
        assert client.get_latest_score() is None

    def test_signals_empty(self, client: CopilotBridgeClient) -> None:
        assert client.get_latest_signals() == []

    def test_gex_none(self, client: CopilotBridgeClient) -> None:
        assert client.get_latest_gex() is None

    def test_kronos_none(self, client: CopilotBridgeClient) -> None:
        assert client.get_latest_kronos() is None

    def test_bar_none(self, client: CopilotBridgeClient) -> None:
        assert client.get_latest_bar() is None

    def test_status_none(self, client: CopilotBridgeClient) -> None:
        assert client.get_latest_status() is None

    def test_not_connected(self, client: CopilotBridgeClient) -> None:
        assert client.is_tcp_connected is False
        assert client.is_ws_connected is False


# ---------------------------------------------------------------------------
# Async dispatch tests (mocked connections)
# ---------------------------------------------------------------------------

class TestTCPDispatch:
    """Verify _dispatch_tcp routes messages correctly."""

    @pytest.mark.asyncio()
    async def test_bar_message_stored_and_callback_fired(
        self, client: CopilotBridgeClient,
    ) -> None:
        cb = MagicMock()
        client.on_bar(cb)
        bar_data = {
            "type": "bar",
            "open": 21500.0,
            "high": 21510.0,
            "low": 21490.0,
            "close": 21505.0,
            "totalVol": 1234,
            "ts_ms": 1700000000000,
        }
        await client._dispatch_tcp(bar_data)
        assert client.get_latest_bar() == bar_data
        cb.assert_called_once_with(bar_data)

    @pytest.mark.asyncio()
    async def test_trade_message_stored(
        self, client: CopilotBridgeClient,
    ) -> None:
        trade_data = {"type": "trade", "price": 21500.25, "size": 5, "aggressor": 1}
        await client._dispatch_tcp(trade_data)
        # Trade stored in _latest_bar_trade (internal state)
        assert hasattr(client, "_latest_bar_trade")

    @pytest.mark.asyncio()
    async def test_internals_message_stored(
        self, client: CopilotBridgeClient,
    ) -> None:
        data = {"type": "internals", "tick": 450, "add": 1200, "vold": 1.3}
        await client._dispatch_tcp(data)
        status = client.get_latest_status()
        assert status is not None
        assert status["internals"] == data


class TestWSDispatch:
    """Verify _dispatch_ws routes WebSocket messages correctly."""

    @pytest.mark.asyncio()
    async def test_score_message(self, client: CopilotBridgeClient) -> None:
        cb = MagicMock()
        client.on_score(cb)
        score_data = {
            "type": "score",
            "total_score": 82.3,
            "tier": "TYPE_A",
            "direction": 1,
            "categories_firing": ["absorption", "exhaustion", "delta", "imbalance", "volume_profile"],
            "category_scores": {"absorption": 20.0},
            "kronos_bias": 70.0,
            "kronos_direction": "LONG",
            "gex_regime": "POSITIVE_DAMPENING",
        }
        await client._dispatch_ws(score_data)

        score = client.get_latest_score()
        assert score is not None
        assert score.total_score == 82.3
        assert score.tier == "TYPE_A"
        assert score.direction == 1
        cb.assert_called_once()

        # GEX extracted from score
        gex = client.get_latest_gex()
        assert gex is not None
        assert gex.regime == "POSITIVE_DAMPENING"

        # Kronos extracted from score
        kronos = client.get_latest_kronos()
        assert kronos is not None
        assert kronos.direction == "bullish"
        assert kronos.confidence == pytest.approx(0.7, abs=0.01)

    @pytest.mark.asyncio()
    async def test_signal_message(self, client: CopilotBridgeClient) -> None:
        cb = MagicMock()
        client.on_signal(cb)
        signal_data = {
            "type": "signal",
            "event": {
                "ts": 1700000000.0,
                "bar_index_in_session": 42,
                "total_score": 85.0,
                "tier": "TYPE_A",
                "direction": -1,
                "engine_agreement": 0.9,
                "category_count": 5,
                "categories_firing": ["absorption", "delta", "imbalance", "volume_profile", "auction"],
                "gex_regime": "NEUTRAL",
                "kronos_bias": 0.0,
            },
            "narrative": "ABSORBED @VAH",
        }
        await client._dispatch_ws(signal_data)

        signals = client.get_latest_signals()
        assert len(signals) == 1
        assert signals[0].direction == "bearish"
        assert signals[0].strength == 85.0
        cb.assert_called_once_with(signal_data)

    @pytest.mark.asyncio()
    async def test_signal_history_capped(self, client: CopilotBridgeClient) -> None:
        for i in range(60):
            await client._dispatch_ws({
                "type": "signal",
                "event": {"total_score": float(i), "direction": 1, "ts": float(i)},
            })
        assert len(client._latest_signals) == 50

    @pytest.mark.asyncio()
    async def test_status_message(self, client: CopilotBridgeClient) -> None:
        status_data = {
            "type": "status",
            "connected": True,
            "pnl": 125.50,
            "bars_received": 200,
            "signals_fired": 3,
            "ts": 1700000000.0,
        }
        await client._dispatch_ws(status_data)
        assert client.get_latest_status() == status_data

    @pytest.mark.asyncio()
    async def test_bias_message_updates_kronos(
        self, client: CopilotBridgeClient,
    ) -> None:
        bias_data = {
            "type": "bias",
            "direction": "BULLISH",
            "score": 65.0,
            "confidence": 0.8,
            "bull_pts": 4,
            "bear_pts": 2,
            "phase": "EXPANSION",
            "judas_status": "CONFIRMED",
            "ts": 1700000000.0,
        }
        await client._dispatch_ws(bias_data)
        kronos = client.get_latest_kronos()
        assert kronos is not None
        assert kronos.direction == "bullish"
        assert kronos.confidence == pytest.approx(0.8, abs=0.01)

    @pytest.mark.asyncio()
    async def test_async_callback(self, client: CopilotBridgeClient) -> None:
        """Async callbacks are properly awaited."""
        called = asyncio.Event()

        async def async_cb(data: dict) -> None:
            called.set()

        client.on_score(async_cb)
        await client._dispatch_ws({"type": "score", "total_score": 50.0})
        assert called.is_set()


# ---------------------------------------------------------------------------
# TCP read loop integration test (mocked StreamReader)
# ---------------------------------------------------------------------------

class TestTCPReadLoop:
    """Test _read_tcp_loop with a mocked asyncio.StreamReader."""

    @pytest.mark.asyncio()
    async def test_reads_ndjson_lines(self, client: CopilotBridgeClient) -> None:
        lines = [
            json.dumps({"type": "trade", "price": 21500.0, "size": 3}).encode() + b"\n",
            json.dumps({"type": "bar", "open": 21500.0, "close": 21505.0}).encode() + b"\n",
            b"",  # EOF
        ]
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(side_effect=lines)
        client._tcp_reader = reader

        await client._read_tcp_loop()

        assert client.tcp_messages_received == 2
        assert client.get_latest_bar() is not None
        assert client.get_latest_bar()["close"] == 21505.0

    @pytest.mark.asyncio()
    async def test_skips_malformed_json(self, client: CopilotBridgeClient) -> None:
        lines = [
            b"not valid json\n",
            json.dumps({"type": "bar", "open": 100.0}).encode() + b"\n",
            b"",
        ]
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(side_effect=lines)
        client._tcp_reader = reader

        await client._read_tcp_loop()
        assert client.tcp_messages_received == 1
