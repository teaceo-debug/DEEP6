from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from deep6.copilot.config import CopilotConfig
from deep6.copilot.budget import TokenBudgetTracker
from deep6.copilot.narrative import NarrativeEngine
from deep6.copilot.types import ChartAnalysis, MarketContext


class FakeAggregator:
    def __init__(self) -> None:
        self.build_calls = 0
        self.formatted_contexts: list[MarketContext] = []

    async def build_context(self) -> MarketContext:
        self.build_calls += 1
        return MarketContext()

    def format_for_llm(self, context: MarketContext) -> str:
        self.formatted_contexts.append(context)
        return f"context-{self.build_calls}"


class FakeScreenCapture:
    def __init__(self) -> None:
        self.capture_calls = 0

    def capture_as_base64(self) -> str:
        self.capture_calls += 1
        return "ZmFrZS1zY3JlZW5zaG90"


class FakeVisionAnalyzer:
    def __init__(self) -> None:
        self.calls = 0

    async def analyze_chart(self, screenshot_b64: str) -> ChartAnalysis:
        self.calls += 1
        return ChartAnalysis(raw_analysis=screenshot_b64, confidence=0.9)


class FakeBrain:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    async def generate_narrative(self, context: str, screenshot_b64: str | None = None) -> AsyncIterator[str]:
        self.calls.append((context, screenshot_b64))
        self.total_input_tokens += 10
        self.total_output_tokens += 4
        for chunk in ("MAD ", "holding"):
            yield chunk


class FlakyBrain(FakeBrain):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    async def generate_narrative(self, context: str, screenshot_b64: str | None = None) -> AsyncIterator[str]:
        self.calls.append((context, screenshot_b64))
        self.attempts += 1
        if self.attempts == 1:
            raise RuntimeError("claude temporarily unavailable")
        self.total_input_tokens += 8
        self.total_output_tokens += 3
        yield "Recovered"


def make_config(**overrides: object) -> CopilotConfig:
    data = {
        "claude_api_key": "test-key",
        "narrative_interval_sec": 0.01,
        "screenshot_interval_sec": 60,
    }
    data.update(overrides)
    return CopilotConfig(**data)


@pytest.mark.asyncio
async def test_narrative_loop_starts_streams_chunks_and_reuses_screenshot() -> None:
    aggregator = FakeAggregator()
    brain = FakeBrain()
    screen_capture = FakeScreenCapture()
    vision_analyzer = FakeVisionAnalyzer()
    budget_tracker = TokenBudgetTracker(token_budget_per_hour=10_000)
    engine = NarrativeEngine(
        make_config(),
        aggregator,
        brain,
        screen_capture,
        vision_analyzer,
        budget_tracker,
    )

    chunks: list[str] = []
    completed: list[str] = []
    done = asyncio.Event()

    engine.on_narrative_chunk(chunks.append)
    engine.on_narrative_complete(lambda text: completed.append(text) or (done.set() if len(completed) >= 2 else None))
    engine._is_rth = lambda: True  # type: ignore[method-assign]

    await engine.start()
    await asyncio.wait_for(done.wait(), timeout=0.5)
    await engine.stop()

    assert aggregator.build_calls >= 2
    assert len(brain.calls) >= 2
    assert all(call[1] == "ZmFrZS1zY3JlZW5zaG90" for call in brain.calls)
    assert screen_capture.capture_calls == 1
    assert vision_analyzer.calls == 1
    assert chunks[:2] == ["MAD ", "holding"]
    assert completed[:2] == ["MAD holding", "MAD holding"]
    assert budget_tracker.get_status().calls_this_hour >= 2


@pytest.mark.asyncio
async def test_rth_gate_blocks_narrative_generation_outside_session() -> None:
    aggregator = FakeAggregator()
    brain = FakeBrain()
    engine = NarrativeEngine(
        make_config(narrative_interval_sec=0.01),
        aggregator,
        brain,
        FakeScreenCapture(),
        FakeVisionAnalyzer(),
        TokenBudgetTracker(token_budget_per_hour=10_000),
        now_provider=lambda: datetime(2026, 5, 12, 6, 0, tzinfo=ZoneInfo("America/Chicago")),
    )

    await engine.start()
    await asyncio.sleep(0.05)
    await engine.stop()

    assert aggregator.build_calls == 0
    assert brain.calls == []


@pytest.mark.asyncio
async def test_narrative_loop_recovers_after_brain_error() -> None:
    aggregator = FakeAggregator()
    brain = FlakyBrain()
    engine = NarrativeEngine(
        make_config(),
        aggregator,
        brain,
        FakeScreenCapture(),
        FakeVisionAnalyzer(),
        TokenBudgetTracker(token_budget_per_hour=10_000),
    )

    completed: list[str] = []
    done = asyncio.Event()
    engine.on_narrative_complete(lambda text: completed.append(text) or done.set())
    engine._is_rth = lambda: True  # type: ignore[method-assign]

    await engine.start()
    await asyncio.wait_for(done.wait(), timeout=0.5)
    await engine.stop()

    assert aggregator.build_calls >= 2
    assert len(brain.calls) >= 2
    assert completed
    assert completed[0] == "Recovered"
