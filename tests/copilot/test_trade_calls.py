from __future__ import annotations

from dataclasses import dataclass

import pytest

from deep6.copilot.trade_calls import TradeCallEngine
from deep6.copilot.types import ChartAnalysis, MADLevel, MarketContext, SignalSummary, TradeCall


@dataclass
class FakeScore:
    total_score: float
    tier: str
    direction: int = 1
    categories_firing: tuple[str, ...] = ("absorption", "delta")


class FakeBridgeClient:
    def __init__(self, score: FakeScore | None) -> None:
        self._score = score

    def get_latest_score(self) -> FakeScore | None:
        return self._score


class FakeAggregator:
    def __init__(self) -> None:
        self.context = MarketContext(signals=(SignalSummary(name="absorption"), SignalSummary(name="delta_reversal")))
        self.build_calls = 0
        self.format_calls = 0

    async def build_context(self) -> MarketContext:
        self.build_calls += 1
        return self.context

    def format_for_llm(self, context: MarketContext) -> str:
        self.format_calls += 1
        assert context is self.context
        return "## Current Market State\nConfluence stack aligned"


class FakeScreenCapture:
    def __init__(self, screenshot_b64: str = "ZmFrZS1wbmc=") -> None:
        self.screenshot_b64 = screenshot_b64
        self.calls = 0

    def capture_as_base64(self) -> str:
        self.calls += 1
        return self.screenshot_b64


class FakeVisionAnalyzer:
    def __init__(self, analysis: ChartAnalysis) -> None:
        self.analysis = analysis
        self.calls = 0

    async def analyze_chart(self, screenshot_b64: str) -> ChartAnalysis:
        self.calls += 1
        assert screenshot_b64 == "ZmFrZS1wbmc="
        return self.analysis


class FakeBrain:
    def __init__(self, trade_call: TradeCall) -> None:
        self.trade_call = trade_call
        self.calls: list[tuple[str, str]] = []

    async def generate_trade_call(self, context: str, screenshot_b64: str) -> TradeCall:
        self.calls.append((context, screenshot_b64))
        return self.trade_call


def build_engine(*, score: FakeScore, analysis: ChartAnalysis, trade_call: TradeCall, copilot_config) -> TradeCallEngine:
    return TradeCallEngine(
        config=copilot_config,
        bridge_client=FakeBridgeClient(score),
        aggregator=FakeAggregator(),
        brain=FakeBrain(trade_call),
        screen_capture=FakeScreenCapture(),
        vision_analyzer=FakeVisionAnalyzer(analysis),
    )


@pytest.mark.asyncio
async def test_trade_call_triggers_when_score_meets_threshold(copilot_config) -> None:
    analysis = ChartAnalysis(mad_levels=(MADLevel(price=18450.0, label="MAD S1", level_type="support"),), confidence=0.92)
    trade_call = TradeCall(direction="LONG", entry=18451.0, stop=18443.0, target=18466.0, confidence=86.0, rationale="MAD S1 held")
    engine = build_engine(score=FakeScore(total_score=72.0, tier="TYPE_B"), analysis=analysis, trade_call=trade_call, copilot_config=copilot_config)
    received: list[TradeCall] = []
    engine.on_trade_call(received.append)

    result = await engine._monitor_once()

    assert result is not None
    assert result.direction == "LONG"
    assert result.mad_levels == analysis.mad_levels
    assert result.signals == ("absorption", "delta_reversal")
    assert received == [result]
    assert engine._brain.calls[0][1] == "ZmFrZS1wbmc="
    assert "## MAD Levels" in engine._brain.calls[0][0]


@pytest.mark.asyncio
async def test_trade_call_cooldown_prevents_rapid_fire_calls(copilot_config) -> None:
    analysis = ChartAnalysis(mad_levels=(MADLevel(price=18480.0, label="MAD R1", level_type="resistance"),), confidence=0.88)
    trade_call = TradeCall(direction="SHORT", entry=18479.0, stop=18486.0, target=18460.0, confidence=84.0, rationale="Fade MAD R1")
    engine = build_engine(score=FakeScore(total_score=89.0, tier="TYPE_A"), analysis=analysis, trade_call=trade_call, copilot_config=copilot_config)
    received: list[TradeCall] = []
    engine.on_trade_call(received.append)

    first = await engine._monitor_once()
    second = await engine._monitor_once()

    assert first is not None
    assert second is None
    assert len(received) == 1
    assert len(engine._brain.calls) == 1
    assert engine._cooldown_remaining() > 0.0


@pytest.mark.asyncio
async def test_trade_call_handles_invalid_json_response_gracefully(copilot_config) -> None:
    analysis = ChartAnalysis(confidence=0.18, price_action="MAD levels not visible")
    trade_call = TradeCall(direction="NONE", confidence=0.0, rationale="Claude returned invalid JSON trade call: not-json")
    engine = build_engine(score=FakeScore(total_score=77.0, tier="TYPE_B"), analysis=analysis, trade_call=trade_call, copilot_config=copilot_config)
    received: list[TradeCall] = []
    engine.on_trade_call(received.append)

    result = await engine._monitor_once()

    assert result is not None
    assert result.direction == "NONE"
    assert result.confidence == 0.0
    assert "invalid JSON trade call" in result.rationale
    assert "MAD levels were not detected" in result.rationale
    assert received == [result]
