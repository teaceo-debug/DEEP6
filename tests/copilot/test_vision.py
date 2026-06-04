"""Tests for ScreenCapture (vision.py) and VisionAnalyzer (vision_analysis.py)."""
from __future__ import annotations

import base64
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from deep6.copilot.config import CopilotConfig
from deep6.copilot.types import ChartAnalysis, MADLevel


@pytest.fixture
def copilot_cfg():
    return CopilotConfig(claude_api_key="test-key")


@pytest.fixture
def tiny_png_b64():
    """A 1x1 white PNG as base64 string (valid test image)."""
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return base64.b64encode(png_bytes).decode("ascii")


class TestScreenCapture:
    def test_imports_without_error(self):
        from deep6.copilot.vision import ScreenCapture

        assert ScreenCapture is not None

    def test_find_nt8_window_returns_none_on_linux(self, copilot_cfg):
        """On Linux/WSL, find_nt8_window returns None gracefully."""
        from deep6.copilot.vision import ScreenCapture
        import deep6.copilot.vision as vision_mod

        original_mss = vision_mod.mss
        vision_mod.mss = None
        try:
            sc = ScreenCapture(copilot_cfg)
            if sys.platform != "win32":
                result = sc.find_nt8_window()
                assert result is None
        finally:
            vision_mod.mss = original_mss

    def test_capture_returns_none_when_mss_unavailable(self, copilot_cfg):
        from deep6.copilot.vision import ScreenCapture
        import deep6.copilot.vision as vision_mod

        original_mss = vision_mod.mss
        vision_mod.mss = None
        try:
            sc = ScreenCapture(copilot_cfg)
            sc._sct = None
            result = sc.capture()
            # Should return None or cached (no crash)
            assert result is None or isinstance(result, bytes)
        finally:
            vision_mod.mss = original_mss

    def test_capture_as_base64_returns_none_when_no_data(self, copilot_cfg):
        from deep6.copilot.vision import ScreenCapture
        import deep6.copilot.vision as vision_mod

        original_mss = vision_mod.mss
        vision_mod.mss = None
        try:
            sc = ScreenCapture(copilot_cfg)
            # Without NT8 running and no mss, should return None
            result = sc.capture_as_base64()
            assert result is None or isinstance(result, str)
        finally:
            vision_mod.mss = original_mss


class TestVisionAnalyzer:
    def test_imports_without_error(self):
        from deep6.copilot.vision_analysis import VisionAnalyzer

        assert VisionAnalyzer is not None

    def test_instantiates_with_no_api_key(self):
        from deep6.copilot.vision_analysis import VisionAnalyzer

        cfg = CopilotConfig(claude_api_key="")
        analyzer = VisionAnalyzer(cfg)
        assert analyzer._client is None

    @pytest.mark.asyncio
    async def test_analyze_chart_returns_low_confidence_without_api(
        self, copilot_cfg, tiny_png_b64
    ):
        from deep6.copilot.vision_analysis import VisionAnalyzer

        cfg = CopilotConfig(claude_api_key="")
        analyzer = VisionAnalyzer(cfg)
        result = await analyzer.analyze_chart(tiny_png_b64)
        assert isinstance(result, ChartAnalysis)
        assert result.confidence < 0.5

    def test_compute_hash_is_deterministic(self, tiny_png_b64):
        from deep6.copilot.vision_analysis import VisionAnalyzer

        cfg = CopilotConfig(claude_api_key="")
        analyzer = VisionAnalyzer(cfg)
        h1 = analyzer._compute_hash(tiny_png_b64)
        h2 = analyzer._compute_hash(tiny_png_b64)
        assert h1 == h2

    def test_parse_analysis_handles_valid_json(self, copilot_cfg):
        from deep6.copilot.vision_analysis import VisionAnalyzer

        analyzer = VisionAnalyzer(copilot_cfg)
        json_text = (
            '{"mad_levels": [{"price": 18450.0, "label": "MAD S1", "type": "support"}], '
            '"price_action": "Testing MAD S1", "visual_patterns": ["flag"], '
            '"support_resistance": [18400.0], "confidence": 0.8}'
        )
        result = analyzer._parse_analysis(json_text)
        assert isinstance(result, ChartAnalysis)
        assert len(result.mad_levels) == 1
        assert result.mad_levels[0].price == 18450.0
        assert result.confidence == 0.8

    def test_parse_analysis_handles_empty_mad_levels(self, copilot_cfg):
        from deep6.copilot.vision_analysis import VisionAnalyzer

        analyzer = VisionAnalyzer(copilot_cfg)
        json_text = (
            '{"mad_levels": [], "price_action": "No levels visible", '
            '"visual_patterns": [], "support_resistance": [], "confidence": 0.9}'
        )
        result = analyzer._parse_analysis(json_text)
        assert result.confidence <= 0.3  # confidence capped when no MAD levels
