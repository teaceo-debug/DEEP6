"""Tests for gexdoctor.monitor.price_service — NQ spot price with fallback."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from gexdoctor.monitor.price_service import NQPriceService
from gexdoctor.monitor.schemas import NQQuote


def _make_response(status_code: int, json_data: dict | None = None) -> httpx.Response:
    """Create a mock httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "http://test"),
    )
    return resp


@pytest.fixture
def svc_polygon():
    """Service with only Polygon key."""
    return NQPriceService(polygon_api_key="pk_test", flash_api_key="")


@pytest.fixture
def svc_both():
    """Service with both keys."""
    return NQPriceService(polygon_api_key="pk_test", flash_api_key="fa_test")


@pytest.fixture
def svc_flash_only():
    """Service with only FlashAlpha key."""
    return NQPriceService(polygon_api_key="", flash_api_key="fa_test")


@pytest.mark.asyncio
async def test_polygon_success(svc_both: NQPriceService):
    """Polygon returns NQ=21800 → NQQuote with source='polygon'."""
    polygon_resp = _make_response(200, {"results": {"p": 21800.0}})

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=polygon_resp):
        quote = await svc_both.get_nq_quote()

    assert quote.nq_price == 21800.0
    assert quote.source == "polygon"
    assert quote.stale is False


@pytest.mark.asyncio
async def test_polygon_404_fallback_to_flashalpha(svc_both: NQPriceService):
    """Polygon 404 → falls back to FlashAlpha QQQ=480."""
    polygon_resp = _make_response(404)
    flash_resp = _make_response(200, {"spot": 480.0})

    async def mock_get(url, **kwargs):
        if "polygon" in url:
            return polygon_resp
        return flash_resp

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
        quote = await svc_both.get_nq_quote()

    assert quote.source == "flashalpha_qqq"
    assert quote.qqq_price == 480.0
    assert quote.nq_qqq_factor == 45.0
    assert quote.nq_price == 480.0 * 45.0
    assert quote.stale is False


@pytest.mark.asyncio
async def test_both_fail_returns_stale(svc_both: NQPriceService):
    """Both sources fail but cache exists → stale=True."""
    # Seed the cache first
    svc_both._cache = NQQuote(
        nq_price=21500.0,
        qqq_price=478.0,
        nq_qqq_factor=44.98,
        source="polygon",
        timestamp="2025-01-01T00:00:00+00:00",
        stale=False,
    )
    svc_both._last_fetch = 0.0  # force refetch

    polygon_resp = _make_response(500)
    flash_resp = _make_response(500)

    async def mock_get(url, **kwargs):
        if "polygon" in url:
            return polygon_resp
        return flash_resp

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
        quote = await svc_both.get_nq_quote()

    assert quote.stale is True
    assert quote.source == "stale_cache"
    assert quote.nq_price == 21500.0


@pytest.mark.asyncio
async def test_both_fail_no_cache_raises(svc_both: NQPriceService):
    """Both sources fail, no cache → RuntimeError."""
    polygon_resp = _make_response(500)
    flash_resp = _make_response(500)

    async def mock_get(url, **kwargs):
        if "polygon" in url:
            return polygon_resp
        return flash_resp

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=mock_get):
        with pytest.raises(RuntimeError, match="No NQ price available"):
            await svc_both.get_nq_quote()


@pytest.mark.asyncio
async def test_cache_returns_within_min_refresh(svc_polygon: NQPriceService):
    """Second call within 5s returns cached value without HTTP request."""
    polygon_resp = _make_response(200, {"results": {"p": 21800.0}})

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=polygon_resp) as mock_get:
        q1 = await svc_polygon.get_nq_quote()
        q2 = await svc_polygon.get_nq_quote()

    # Only one HTTP call should have been made
    assert mock_get.call_count == 1
    assert q1.nq_price == q2.nq_price


@pytest.mark.asyncio
async def test_get_conversion_factors_returns_dict(svc_both: NQPriceService):
    """get_conversion_factors returns dict with required keys."""
    polygon_resp = _make_response(200, {"results": {"p": 21800.0}})

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=polygon_resp):
        factors = await svc_both.get_conversion_factors()

    assert "nq_qqq_factor" in factors
    assert "nq_ndx_basis" in factors
    assert "nq_price" in factors
    assert factors["nq_price"] == 21800.0


@pytest.mark.asyncio
async def test_no_polygon_key_skips_polygon(svc_flash_only: NQPriceService):
    """Empty polygon_api_key → polygon not called, falls back to FlashAlpha."""
    flash_resp = _make_response(200, {"underlying_price": 480.0})

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=flash_resp) as mock_get:
        quote = await svc_flash_only.get_nq_quote()

    assert quote.source == "flashalpha_qqq"
    # Should only call FlashAlpha (not Polygon)
    assert mock_get.call_count == 1
    call_url = mock_get.call_args[0][0]
    assert "flashalpha" in call_url


@pytest.mark.asyncio
async def test_flashalpha_qqq_estimate_uses_ratio(svc_flash_only: NQPriceService):
    """QQQ=480, default factor=45.0 → nq_price=21600."""
    flash_resp = _make_response(200, {"spot": 480.0})

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=flash_resp):
        quote = await svc_flash_only.get_nq_quote()

    assert quote.qqq_price == 480.0
    assert quote.nq_qqq_factor == 45.0
    assert quote.nq_price == 21600.0  # 480 * 45
