"""Tests for FlashAlpha adapter."""
import pytest
from unittest.mock import AsyncMock, patch

from gex_terminal.engine.adapters.flashalpha import FlashAlphaAdapter, FlashAlphaResult
from gex_terminal.schemas import DealerPositioning, GEXLevels, SourceHealth, ZeroDTEState


MOCK_FA_RESPONSE = {
    "summary": {
        "gamma_flip": 450.25,
        "regime": "positive",
        "hedge_direction": "buying",
        "exposures": {
            "net_gex": 3_200_000_000,
            "net_dex": -1_100_000_000,
        },
    },
    "levels": {
        "levels": {
            "call_wall": 455.0,
            "put_wall": 445.0,
            "hvl": 451.0,
            "zero_dte_magnet": 450.0,
        }
    },
    "zero_dte": {
        "gex_pct_of_total": 0.23,
        "pin_risk": "low",
        "gamma_acceleration": 0.42,
    },
    "vex": {"net_vex": 450_000_000},
    "chex": {"net_chex": -200_000_000},
    "symbol": "QQQ",
    "ts": 1748527200.0,
}


@pytest.mark.asyncio
async def test_poll_normalizes_data():
    """Adapter polls and normalizes FlashAlpha data to schemas."""
    adapter = FlashAlphaAdapter(api_key="test_key")

    with patch.object(adapter._client, "get_all", new=AsyncMock(return_value=MOCK_FA_RESPONSE)):
        result = await adapter.poll()

    assert isinstance(result, FlashAlphaResult)
    assert isinstance(result.levels, GEXLevels)
    assert isinstance(result.dealer, DealerPositioning)
    assert isinstance(result.zero_dte, ZeroDTEState)
    assert isinstance(result.source_health, SourceHealth)

    assert result.source_health.status == "ok"
    assert result.levels.gamma_flip == 450.25
    assert result.levels.call_wall == 455.0
    assert result.dealer.regime == "positive"
    assert result.dealer.net_gex == 3_200_000_000
    assert result.zero_dte.pin_risk == "low"


@pytest.mark.asyncio
async def test_poll_degrades_gracefully_on_error():
    """Adapter returns error SourceHealth when API fails."""
    adapter = FlashAlphaAdapter(api_key="invalid_key")

    with patch.object(adapter._client, "get_all", new=AsyncMock(side_effect=Exception("API error"))):
        result = await adapter.poll()

    assert result.source_health.status == "error"
    assert "API error" in result.source_health.error_msg
    assert isinstance(result.levels, GEXLevels)


@pytest.mark.asyncio
async def test_poll_returns_last_known_on_error():
    """After a successful poll, errors return last known data."""
    adapter = FlashAlphaAdapter(api_key="test_key")

    with patch.object(adapter._client, "get_all", new=AsyncMock(return_value=MOCK_FA_RESPONSE)):
        first = await adapter.poll()

    assert first.source_health.status == "ok"

    with patch.object(adapter._client, "get_all", new=AsyncMock(side_effect=Exception("timeout"))):
        second = await adapter.poll()

    assert second.source_health.status == "error"
    assert second.levels.gamma_flip == 450.25
