"""Tests for Massive.com adapter."""
from datetime import datetime, timezone

import pytest
from unittest.mock import AsyncMock, patch

from nq_atlas.types import ChainSnapshot, FlowResult, GEXResult, OptionsContract

from gex_terminal.engine.adapters.massive import MassiveAdapter, MassiveResult
from gex_terminal.schemas import GEXLevels, SourceHealth


def _mock_chain() -> ChainSnapshot:
    """Build a minimal QQQ chain snapshot for testing."""
    contracts = [
        OptionsContract(
            symbol="O:QQQ250530C00450000",
            strike=450.0,
            expiry="2025-12-19",
            call_put="call",
            bid=12.0,
            ask=12.5,
            oi=5000,
            delta=0.55,
            gamma=0.015,
            iv=0.22,
        ),
        OptionsContract(
            symbol="O:QQQ250530C00460000",
            strike=460.0,
            expiry="2025-12-19",
            call_put="call",
            bid=5.0,
            ask=5.5,
            oi=12000,
            delta=0.35,
            gamma=0.012,
            iv=0.20,
        ),
        OptionsContract(
            symbol="O:QQQ250530P00440000",
            strike=440.0,
            expiry="2025-12-19",
            call_put="put",
            bid=8.0,
            ask=8.5,
            oi=8000,
            delta=-0.40,
            gamma=0.014,
            iv=0.24,
        ),
        OptionsContract(
            symbol="O:QQQ250530P00430000",
            strike=430.0,
            expiry="2025-12-19",
            call_put="put",
            bid=4.0,
            ask=4.5,
            oi=10000,
            delta=-0.25,
            gamma=0.010,
            iv=0.26,
        ),
    ]
    return ChainSnapshot(
        underlying="QQQ",
        spot_price=452.0,
        timestamp=datetime.now(tz=timezone.utc),
        contracts=contracts,
    )


@pytest.mark.asyncio
async def test_poll_normalizes_data():
    """Adapter polls chain, computes GEX, normalizes to schemas."""
    adapter = MassiveAdapter(api_key="test_key")
    mock_chain = _mock_chain()

    with patch.object(
        adapter._client, "get_options_chain", new=AsyncMock(return_value=mock_chain)
    ):
        result = await adapter.poll()

    assert isinstance(result, MassiveResult)
    assert isinstance(result.levels, GEXLevels)
    assert isinstance(result.source_health, SourceHealth)
    assert isinstance(result.raw_gex_result, GEXResult)
    assert isinstance(result.flow_result, FlowResult)

    assert result.source_health.status == "ok"
    assert result.source_health.name == "massive"
    assert result.raw_gex_result.spot == 452.0
    # Calls have positive GEX, puts have negative — net should be nonzero
    assert result.raw_gex_result.net_gex != 0.0
    assert result.flow_result is not None


@pytest.mark.asyncio
async def test_poll_computes_levels():
    """GEXEngine computes flip, call_wall, put_wall from chain."""
    adapter = MassiveAdapter(api_key="test_key", level_cache_path=None)
    mock_chain = _mock_chain()

    with patch.object(
        adapter._client, "get_options_chain", new=AsyncMock(return_value=mock_chain)
    ):
        result = await adapter.poll()

    # call_wall should be one of the call strikes (highest positive GEX)
    assert result.levels.call_wall in (450.0, 460.0) or result.levels.call_wall is None
    # put_wall should be one of the put strikes (most negative GEX)
    assert result.levels.put_wall in (430.0, 440.0) or result.levels.put_wall is None


@pytest.mark.asyncio
async def test_poll_degrades_on_error():
    """Adapter returns error SourceHealth when API fails."""
    adapter = MassiveAdapter(api_key="invalid_key")

    with patch.object(
        adapter._client,
        "get_options_chain",
        new=AsyncMock(side_effect=Exception("connection refused")),
    ):
        result = await adapter.poll()

    assert result.source_health.status == "error"
    assert "connection refused" in result.source_health.error_msg
    assert isinstance(result.levels, GEXLevels)
    assert result.raw_gex_result is None
    assert result.flow_result is None


@pytest.mark.asyncio
async def test_poll_returns_last_known_on_error():
    """After a successful poll, errors return last known data."""
    adapter = MassiveAdapter(api_key="test_key")
    mock_chain = _mock_chain()

    # First poll succeeds
    with patch.object(
        adapter._client, "get_options_chain", new=AsyncMock(return_value=mock_chain)
    ):
        first = await adapter.poll()

    assert first.source_health.status == "ok"
    first_flip = first.levels.gamma_flip

    # Second poll fails — should return last known levels
    with patch.object(
        adapter._client,
        "get_options_chain",
        new=AsyncMock(side_effect=Exception("timeout")),
    ):
        second = await adapter.poll()

    assert second.source_health.status == "error"
    assert second.levels.gamma_flip == first_flip
    assert second.raw_gex_result is not None  # preserved from first poll


@pytest.mark.asyncio
async def test_error_count_tracks_consecutive_failures():
    """Error count increments on failure, resets on success."""
    adapter = MassiveAdapter(api_key="test_key")
    mock_chain = _mock_chain()

    with patch.object(
        adapter._client,
        "get_options_chain",
        new=AsyncMock(side_effect=Exception("fail")),
    ):
        await adapter.poll()
        await adapter.poll()

    assert adapter._error_count == 2

    with patch.object(
        adapter._client, "get_options_chain", new=AsyncMock(return_value=mock_chain)
    ):
        await adapter.poll()

    assert adapter._error_count == 0


@pytest.mark.asyncio
async def test_custom_symbol():
    """Adapter passes custom symbol to MassiveClient."""
    adapter = MassiveAdapter(api_key="test_key", symbol="SPY")
    mock_chain = _mock_chain()

    with patch.object(
        adapter._client, "get_options_chain", new=AsyncMock(return_value=mock_chain)
    ) as mock_method:
        await adapter.poll()

    mock_method.assert_called_once_with("SPY")
