"""Integration tests for CopilotBrain + NarrativeEngine pipeline.

Tests real class logic with mocked Anthropic client.
No real API calls, no real screenshots.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time as dt_time
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from deep6.copilot.brain import CopilotBrain
from deep6.copilot.budget import TokenBudgetTracker
from deep6.copilot.config import CopilotConfig
from deep6.copilot.context import ContextAggregator
from deep6.copilot.narrative import NarrativeEngine
from deep6.copilot.types import MarketContext
from deep6.copilot.vision import ScreenCapture
from deep6.copilot.vision_analysis import VisionAnalyzer


_CT = ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# CopilotBrain: streaming narrative
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brain_streaming(copilot_config: CopilotConfig):
    """Brain.generate_narrative yields non-empty string chunks."""
    brain = CopilotBrain(copilot_config)

    # Build a mock stream context manager that yields text chunks
    chunks = ["NQ is ", "testing ", "resistance at ", "18500."]

    mock_stream = MagicMock()
    mock_stream.__enter__ = MagicMock(return_value=mock_stream)
    mock_stream.__exit__ = MagicMock(return_value=False)
    mock_stream.text_stream = iter(chunks)
    mock_final = MagicMock()
    mock_final.usage.input_tokens = 200
    mock_final.usage.output_tokens = 50
    mock_stream.get_final_message.return_value = mock_final

    brain._client.messages.stream = MagicMock(return_value=mock_stream)

    collected: list[str] = []
    async for chunk in brain.generate_narrative("Market context here"):
        collected.append(chunk)

    assert len(collected) == len(chunks)
    assert all(c for c in collected)  # All non-empty
    full = "".join(collected)
    assert "18500" in full


# ---------------------------------------------------------------------------
# NarrativeEngine: RTH gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_narrative_skips_outside_rth(copilot_config: CopilotConfig):
    """NarrativeEngine does not call brain.generate_narrative outside RTH."""
    # 2:00 AM CT — well outside RTH (7:30 AM - 3:00 PM CT)
    fake_now = datetime(2026, 5, 12, 2, 0, 0, tzinfo=_CT)

    brain = MagicMock(spec=CopilotBrain)
    brain.generate_narrative = AsyncMock()
    brain.total_input_tokens = 0
    brain.total_output_tokens = 0

    aggregator = MagicMock(spec=ContextAggregator)
    aggregator.build_context = AsyncMock(return_value=MarketContext())
    aggregator.format_for_llm = MagicMock(return_value="context")

    screen_capture = MagicMock(spec=ScreenCapture)
    budget = TokenBudgetTracker(token_budget_per_hour=500_000)

    engine = NarrativeEngine(
        config=copilot_config,
        aggregator=aggregator,
        brain=brain,
        screen_capture=screen_capture,
        vision_analyzer=None,
        budget_tracker=budget,
        now_provider=lambda: fake_now,
    )

    # Override the interval so the loop fires quickly
    engine.config = MagicMock()
    engine.config.narrative_interval_sec = 0.01
    engine.config.screenshot_interval_sec = 30

    await engine.start()
    # Let one iteration pass
    await asyncio.sleep(0.05)
    await engine.stop()

    # Brain should NOT have been called (outside RTH)
    brain.generate_narrative.assert_not_called()


# ---------------------------------------------------------------------------
# CopilotBrain: retry on 429 rate limit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_brain_retry_on_rate_limit(copilot_config: CopilotConfig):
    """Brain retries on rate limit error and succeeds on second attempt."""
    brain = CopilotBrain(copilot_config)

    # First call raises RateLimitError (429), second succeeds
    # Create an exception that _is_retryable_error recognizes
    rate_limit_exc = Exception("rate limit exceeded")
    rate_limit_exc.status_code = 429  # type: ignore[attr-defined]

    mock_response = MagicMock()
    mock_response.usage.input_tokens = 150
    mock_response.usage.output_tokens = 80
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '{"direction": "LONG", "entry": 18500, "stop": 18480, "target": 18550, "confidence": 75, "mad_levels": [], "signals": ["absorption"], "rationale": "Strong support"}'
    mock_response.content = [text_block]

    call_count = 0

    def mock_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise rate_limit_exc
        return mock_response

    brain._client.messages.create = mock_create

    # _retry_with_backoff wraps asyncio.to_thread(create), so we patch sleep
    with patch("asyncio.sleep", new_callable=AsyncMock):
        trade_call = await brain.generate_trade_call(
            "Test context",
            "dGVzdF9zY3JlZW5zaG90",  # "test_screenshot" b64
        )

    assert call_count == 2  # First failed, second succeeded
    assert trade_call.direction == "LONG"
    assert trade_call.confidence == 75.0
    assert "absorption" in trade_call.signals
