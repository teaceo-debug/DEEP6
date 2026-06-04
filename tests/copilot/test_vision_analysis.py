from __future__ import annotations

import base64
import io
from types import SimpleNamespace

import pytest
from PIL import Image

from deep6.copilot.types import ChartAnalysis
from deep6.copilot.vision_analysis import VisionAnalyzer


def make_image_b64(color: str = "white", *, size: tuple[int, int] = (50, 50), mutate: bool = False) -> str:
    image = Image.new("RGB", size, color=color)
    if mutate:
        for x in range(5):
            for y in range(5):
                image.putpixel((x, y), (0, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class FakeMessagesAPI:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    async def create(self, **_: object):
        text = self._responses[self.calls]
        self.calls += 1
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        )


class FakeAnthropicClient:
    def __init__(self, responses: list[str]) -> None:
        self.messages = FakeMessagesAPI(responses)


@pytest.mark.asyncio
async def test_analyze_chart_parses_mad_levels(copilot_config) -> None:
    analyzer = VisionAnalyzer(copilot_config)
    analyzer._client = FakeAnthropicClient(
        [
            '{"mad_levels": [{"price": 18450.5, "label": "MAD R1", "type": "resistance"}, '
            '{"price": 18420.25, "label": "MAD P", "type": "pivot"}], '
            '"price_action": "Testing MAD R1", "visual_patterns": ["flag"], '
            '"support_resistance": [18410.0, 18460.0], "confidence": 0.82}'
        ]
    )

    analysis = await analyzer.analyze_chart(make_image_b64())

    assert analysis.mad_levels[0].price == 18450.5
    assert analysis.mad_levels[0].label == "MAD R1"
    assert analysis.mad_levels[0].level_type == "resistance"
    assert analysis.visual_patterns == ("flag",)
    assert analysis.support_resistance == (18410.0, 18460.0)
    assert analysis.confidence == 0.82
    assert analyzer._client.messages.calls == 1


@pytest.mark.asyncio
async def test_analyze_chart_uses_hash_cache_for_identical_screenshot(copilot_config) -> None:
    analyzer = VisionAnalyzer(copilot_config)
    analyzer._client = FakeAnthropicClient(
        ['{"mad_levels": [{"price": 18450.5, "label": "MAD R1", "type": "resistance"}], "confidence": 0.9}']
    )
    screenshot_b64 = make_image_b64()

    first = await analyzer.analyze_chart(screenshot_b64)
    second = await analyzer.analyze_chart(screenshot_b64)

    assert first == second
    assert analyzer._client.messages.calls == 1


@pytest.mark.asyncio
async def test_analyze_chart_skips_api_call_when_frame_diff_is_below_threshold(copilot_config) -> None:
    analyzer = VisionAnalyzer(copilot_config)
    analyzer._client = FakeAnthropicClient(
        [
            '{"mad_levels": [{"price": 18400.0, "label": "MAD S1", "type": "support"}], '
            '"price_action": "Holding support", "visual_patterns": ["higher low"], '
            '"support_resistance": [18390.0], "confidence": 0.77}',
            '{"mad_levels": [{"price": 99999.0, "label": "SHOULD NOT HAPPEN", "type": "pivot"}], "confidence": 1.0}',
        ]
    )

    first = await analyzer.analyze_chart(make_image_b64())
    second = await analyzer.analyze_chart(make_image_b64(mutate=True))

    assert second == first
    assert analyzer._client.messages.calls == 1


@pytest.mark.asyncio
async def test_analyze_chart_returns_low_confidence_on_invalid_json(copilot_config) -> None:
    analyzer = VisionAnalyzer(copilot_config)
    analyzer._client = FakeAnthropicClient(["not-json"])

    analysis = await analyzer.analyze_chart(make_image_b64())

    assert analysis == ChartAnalysis(confidence=0.0, raw_analysis="not-json")
    assert analyzer._client.messages.calls == 1


def test_parse_analysis_drops_confidence_when_mad_levels_missing(copilot_config) -> None:
    analyzer = VisionAnalyzer(copilot_config)

    analysis = analyzer._parse_analysis(
        '{"mad_levels": [], "price_action": "Levels not visible", "visual_patterns": ["range"], '
        '"support_resistance": [18420.0], "confidence": 0.91}'
    )

    assert analysis.mad_levels == ()
    assert analysis.confidence == 0.25
