"""Tests for DEEP6 bidirectional bridge."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gex_terminal.engine.deep6_bridge import DEEP6Bridge
from gex_terminal.schemas import BiasVerdict


def make_verdict(
    direction: str = "BULLISH",
    confidence: int = 80,
    grade: str = "A",
    regime: str = "Positive Gamma",
) -> BiasVerdict:
    return BiasVerdict(direction=direction, confidence=confidence, grade=grade, regime_name=regime)


@pytest.mark.asyncio
async def test_push_sends_correct_payload() -> None:
    """Push sends GEXDoctorPayload with correct score."""
    bridge = DEEP6Bridge()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    with patch.object(bridge._client, "post", new=AsyncMock(return_value=mock_response)) as mock_post:
        result = await bridge.push_gex_snapshot(make_verdict(direction="BULLISH", confidence=82), {})

    assert result is True
    call_args = mock_post.call_args
    payload = call_args.kwargs["json"]
    assert payload["domain"] == "gex_doctor"
    assert payload["score"] == 3
    assert payload["max_range"] == 3
    assert isinstance(payload["score"], int)
    assert isinstance(payload["updated_at"], float)

    await bridge.close()


@pytest.mark.asyncio
async def test_push_degrades_gracefully_on_error() -> None:
    """Push returns False when DEEP6 is not running."""
    bridge = DEEP6Bridge()

    with patch.object(bridge._client, "post", new=AsyncMock(side_effect=Exception("Connection refused"))):
        result = await bridge.push_gex_snapshot(make_verdict(), {})

    assert result is False
    assert bridge.connected is False

    await bridge.close()


@pytest.mark.asyncio
async def test_read_bias_returns_correct_fields() -> None:
    """Read returns bias_score (int), bias_label (str), confidence (float)."""
    bridge = DEEP6Bridge()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(
        return_value={
            "bias_score": 4,
            "bias_label": "LEAN_BULL",
            "confidence": 0.72,
            "bias_state": 1,
        }
    )

    with patch.object(bridge._client, "get", new=AsyncMock(return_value=mock_response)):
        score, label, conf = await bridge.read_bias()

    assert score == 4
    assert isinstance(score, int)
    assert label == "LEAN_BULL"
    assert conf == 0.72
    assert bridge.last_bias_score == 4
    assert bridge.last_bias_label == "LEAN_BULL"
    assert bridge.last_confidence == 0.72

    await bridge.close()


@pytest.mark.asyncio
async def test_read_bias_returns_none_when_deep6_offline() -> None:
    """Read returns (None, None, None) when DEEP6 is not running."""
    bridge = DEEP6Bridge()

    with patch.object(bridge._client, "get", new=AsyncMock(side_effect=Exception("Connection refused"))):
        score, label, conf = await bridge.read_bias()

    assert score is None
    assert label is None
    assert conf is None
    assert bridge.connected is False

    await bridge.close()


def test_verdict_to_score_mapping() -> None:
    """BiasVerdict confidence maps to correct integer score."""
    bridge = DEEP6Bridge()

    assert bridge._verdict_to_score(make_verdict("BULLISH", 85)) == 3
    assert bridge._verdict_to_score(make_verdict("BULLISH", 70)) == 2
    assert bridge._verdict_to_score(make_verdict("BULLISH", 55)) == 1
    assert bridge._verdict_to_score(make_verdict("NEUTRAL", 80)) == 0
    assert bridge._verdict_to_score(make_verdict("BEARISH", 85)) == -3
    assert bridge._verdict_to_score(make_verdict("BEARISH", 70)) == -2
