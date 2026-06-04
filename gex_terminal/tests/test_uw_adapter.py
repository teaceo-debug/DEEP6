"""Tests for Unusual Whales dark pool adapter."""
import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gex_terminal.engine.adapters.unusual_whales import (
    DarkPoolLevel,
    DarkPoolSummary,
    UnusualWhalesAdapter,
    _cluster_prints,
)
from gex_terminal.schemas import SourceHealth


# -- Fixtures --

MOCK_UW_RESPONSE = {
    "data": [
        {"price": "450.25", "premium": "2500000", "size": "5000"},
        {"price": "449.75", "premium": "1800000", "size": "3600"},
        {"price": "451.00", "premium": "500000", "size": "1000"},
        {"price": "450.50", "premium": "1200000", "size": "2400"},
        {"price": "445.00", "premium": "3000000", "size": "6000"},
        {"price": "445.25", "premium": "2000000", "size": "4000"},
    ]
}


def _mock_response(data: dict = MOCK_UW_RESPONSE, status: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=data)
    return resp


def _error_response(status: int) -> httpx.HTTPStatusError:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    req = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(f"{status}", request=req, response=resp)


# -- Unit: clustering --


def test_cluster_prints_groups_nearby_prices():
    """Prints within 0.5% are clustered together."""
    prints = [
        {"price": "450.00", "premium": "1000000"},
        {"price": "450.50", "premium": "2000000"},
        {"price": "451.00", "premium": "1500000"},
        {"price": "460.00", "premium": "500000"},
    ]
    levels, net = _cluster_prints(prints, nq_qqq_ratio=38.5)
    # 450.00, 450.50, 451.00 should cluster (within 0.5% of 450)
    # 460.00 is separate
    assert len(levels) == 2
    assert net == 5_000_000


def test_cluster_prints_empty_input():
    """Empty prints return no levels."""
    levels, net = _cluster_prints([], nq_qqq_ratio=38.5)
    assert levels == []
    assert net == 0.0


def test_cluster_prints_invalid_data_skipped():
    """Prints with bad price/premium are skipped."""
    prints = [
        {"price": "not_a_number", "premium": "1000000"},
        {"price": "450.00", "premium": "bogus"},
        {"price": "450.00", "premium": "1000000"},
    ]
    levels, _ = _cluster_prints(prints, nq_qqq_ratio=38.5)
    assert len(levels) == 1
    assert levels[0].print_count == 1


def test_cluster_converts_to_nq():
    """NQ prices are QQQ × ratio."""
    prints = [{"price": "450.00", "premium": "1000000"}]
    levels, _ = _cluster_prints(prints, nq_qqq_ratio=38.5)
    assert len(levels) == 1
    expected_nq = round(450.0 * 38.5, 0)
    assert levels[0].price_nq == expected_nq


def test_cluster_premium_weighted_center():
    """Center is premium-weighted, not simple average."""
    prints = [
        {"price": "450.00", "premium": "3000000"},
        {"price": "451.00", "premium": "1000000"},
    ]
    levels, _ = _cluster_prints(prints, nq_qqq_ratio=38.5)
    # Weighted toward 450.00 (3x the weight)
    assert levels[0].price_qqq < 450.5


# -- Integration: adapter poll --


@pytest.mark.asyncio
async def test_poll_normalizes_dark_pool_data():
    """Adapter fetches and normalizes dark pool data into clustered levels."""
    adapter = UnusualWhalesAdapter(api_key="test_key", nq_qqq_ratio=38.5)

    with patch.object(
        adapter._client, "get", new=AsyncMock(return_value=_mock_response())
    ):
        result = await adapter.poll()

    assert isinstance(result, DarkPoolSummary)
    assert result.source_health.status == "ok"
    assert result.source_health.name == "unusual_whales"
    assert len(result.levels) > 0

    # All NQ levels should be in plausible range (QQQ ~445-451 × 38.5)
    for lvl in result.levels:
        assert isinstance(lvl, DarkPoolLevel)
        assert 15_000 < lvl.price_nq < 25_000

    # Convenience accessor matches
    assert result.levels_nq == [lvl.price_nq for lvl in result.levels]


@pytest.mark.asyncio
async def test_poll_returns_pending_without_api_key():
    """Adapter returns pending status when no API key configured."""
    adapter = UnusualWhalesAdapter(api_key="")
    result = await adapter.poll()

    assert result.source_health.status == "pending"
    assert len(result.levels) == 0
    assert "not configured" in result.source_health.error_msg


@pytest.mark.asyncio
async def test_poll_degrades_on_auth_error():
    """Adapter returns AUTH_FAILED on 401."""
    adapter = UnusualWhalesAdapter(api_key="invalid_key")

    with patch.object(
        adapter._client,
        "get",
        new=AsyncMock(side_effect=_error_response(401)),
    ):
        result = await adapter.poll()

    assert result.source_health.status == "error"
    assert "AUTH" in result.source_health.error_msg
    assert adapter._error_count == 1


@pytest.mark.asyncio
async def test_poll_degrades_on_rate_limit():
    """Adapter returns RATE_LIMITED on 429."""
    adapter = UnusualWhalesAdapter(api_key="test_key")

    with patch.object(
        adapter._client,
        "get",
        new=AsyncMock(side_effect=_error_response(429)),
    ):
        result = await adapter.poll()

    assert result.source_health.status == "error"
    assert "RATE" in result.source_health.error_msg


@pytest.mark.asyncio
async def test_poll_returns_last_known_on_error():
    """After a successful poll, errors preserve last known data."""
    adapter = UnusualWhalesAdapter(api_key="test_key", nq_qqq_ratio=38.5)

    # First poll succeeds
    with patch.object(
        adapter._client, "get", new=AsyncMock(return_value=_mock_response())
    ):
        first = await adapter.poll()
    assert first.source_health.status == "ok"
    first_levels = first.levels_nq

    # Second poll fails — should return last known levels
    with patch.object(
        adapter._client,
        "get",
        new=AsyncMock(side_effect=Exception("timeout")),
    ):
        second = await adapter.poll()

    assert second.source_health.status == "error"
    assert second.levels_nq == first_levels
    assert second.institutional_bias == first.institutional_bias


@pytest.mark.asyncio
async def test_error_count_tracks_consecutive_failures():
    """Error count increments on failure, resets on success."""
    adapter = UnusualWhalesAdapter(api_key="test_key")

    with patch.object(
        adapter._client,
        "get",
        new=AsyncMock(side_effect=Exception("fail")),
    ):
        await adapter.poll()
        await adapter.poll()

    assert adapter._error_count == 2

    with patch.object(
        adapter._client, "get", new=AsyncMock(return_value=_mock_response())
    ):
        await adapter.poll()

    assert adapter._error_count == 0


@pytest.mark.asyncio
async def test_nq_conversion_math():
    """Dark pool levels correctly convert from QQQ to NQ prices."""
    adapter = UnusualWhalesAdapter(api_key="test_key", nq_qqq_ratio=40.0)

    single_print = {"data": [{"price": "500.0", "premium": "5000000"}]}
    with patch.object(
        adapter._client,
        "get",
        new=AsyncMock(return_value=_mock_response(single_print)),
    ):
        result = await adapter.poll()

    # 500.0 × 40.0 = 20,000
    assert len(result.levels) == 1
    assert result.levels[0].price_nq == 20_000.0
    assert result.levels[0].price_qqq == 500.0


@pytest.mark.asyncio
async def test_custom_symbol():
    """Adapter passes custom symbol in API path."""
    adapter = UnusualWhalesAdapter(api_key="test_key", symbol="SPY")

    with patch.object(
        adapter._client, "get", new=AsyncMock(return_value=_mock_response())
    ) as mock_get:
        await adapter.poll()

    call_args = mock_get.call_args
    assert "/api/darkpool/SPY" in call_args.args[0]


@pytest.mark.asyncio
async def test_bias_from_premium():
    """Institutional bias reflects net premium direction."""
    adapter = UnusualWhalesAdapter(api_key="test_key")

    # All positive premium → bullish
    bullish_data = {
        "data": [
            {"price": "450.0", "premium": "5000000"},
            {"price": "451.0", "premium": "3000000"},
        ]
    }
    with patch.object(
        adapter._client,
        "get",
        new=AsyncMock(return_value=_mock_response(bullish_data)),
    ):
        result = await adapter.poll()
    assert result.institutional_bias == "bullish"


@pytest.mark.asyncio
async def test_empty_response():
    """Empty data array returns empty levels with ok status."""
    adapter = UnusualWhalesAdapter(api_key="test_key")

    with patch.object(
        adapter._client,
        "get",
        new=AsyncMock(return_value=_mock_response({"data": []})),
    ):
        result = await adapter.poll()

    assert result.source_health.status == "ok"
    assert result.levels == []
    assert result.institutional_bias == "neutral"
