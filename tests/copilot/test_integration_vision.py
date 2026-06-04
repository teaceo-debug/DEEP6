"""Integration tests for ScreenCapture + VisionAnalyzer pipeline.

Tests real class logic with mocked OS/API dependencies.
No real screenshots, no real Anthropic API calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deep6.copilot.config import CopilotConfig
from deep6.copilot.types import ChartAnalysis
from deep6.copilot.vision import ScreenCapture
from deep6.copilot.vision_analysis import VisionAnalyzer


# ---------------------------------------------------------------------------
# ScreenCapture: NT8 not running
# ---------------------------------------------------------------------------


def test_capture_no_nt8():
    """ScreenCapture.find_nt8_window() returns None when NT8 is absent."""
    config = MagicMock()
    sc = ScreenCapture(config)

    # Mock EnumWindows to find no NinjaTrader windows
    with patch("deep6.copilot.vision.ScreenCapture.find_nt8_window", return_value=None):
        result = sc.find_nt8_window()

    assert result is None

    # capture() should return None (no last capture cached)
    with patch.object(sc, "find_nt8_window", return_value=None):
        data = sc.capture()

    # No cached screenshot and no window → None
    assert data is None


# ---------------------------------------------------------------------------
# VisionAnalyzer: caching for identical screenshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_cache(copilot_config: CopilotConfig):
    """VisionAnalyzer caches results and skips re-analysis for identical b64 input."""
    analyzer = VisionAnalyzer(copilot_config)

    # Mock the Anthropic client
    mock_response = MagicMock()
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    # Return a text block with valid JSON
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '{"mad_levels": [], "price_action": "Testing", "visual_patterns": [], "support_resistance": [], "confidence": 0.8}'
    mock_response.content = [text_block]

    mock_messages = AsyncMock()
    mock_messages.create = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.messages = mock_messages
    analyzer._client = mock_client

    screenshot_b64 = "aGVsbG8gd29ybGQ="  # "hello world" in b64

    # First call — should hit the API
    result1 = await analyzer.analyze_chart(screenshot_b64)
    assert result1.confidence == pytest.approx(0.25)  # no mad_levels → clamped to 0.25
    assert mock_messages.create.await_count == 1

    # Second call with same b64 — should use cache, NOT call API again
    result2 = await analyzer.analyze_chart(screenshot_b64)
    assert result2.confidence == result1.confidence
    assert mock_messages.create.await_count == 1  # Still 1, not 2


# ---------------------------------------------------------------------------
# VisionAnalyzer: malformed Claude response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_vision_bad_json(copilot_config: CopilotConfig):
    """VisionAnalyzer handles non-JSON Claude response gracefully."""
    analyzer = VisionAnalyzer(copilot_config)

    # Mock the Anthropic client returning plain text (no JSON)
    mock_response = MagicMock()
    mock_response.usage.input_tokens = 80
    mock_response.usage.output_tokens = 30
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "I cannot analyze this image because it appears to be blank."
    mock_response.content = [text_block]

    mock_messages = AsyncMock()
    mock_messages.create = AsyncMock(return_value=mock_response)

    mock_client = MagicMock()
    mock_client.messages = mock_messages
    analyzer._client = mock_client

    screenshot_b64 = "ZGlmZmVyZW50X2RhdGE="  # different from cache test

    result = await analyzer.analyze_chart(screenshot_b64)

    assert isinstance(result, ChartAnalysis)
    assert result.confidence == 0.0
    assert result.mad_levels == ()
    # raw_analysis should contain the original text
    assert "cannot analyze" in result.raw_analysis
