"""Vision analysis pipeline: screenshot → Claude Vision → structured chart data."""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import sys
from types import ModuleType
from typing import Any

try:
    import anthropic
except ImportError:
    anthropic = ModuleType("anthropic")

    class _AnthropicStub:  # pragma: no cover - fallback for tests
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.messages = type("MessagesAPI", (), {})()

    anthropic.AsyncAnthropic = _AnthropicStub  # type: ignore[attr-defined]
    anthropic.Anthropic = _AnthropicStub  # type: ignore[attr-defined]
    sys.modules.setdefault("anthropic", anthropic)

from deep6.copilot.config import CopilotConfig
from deep6.copilot.budget import TokenBudgetTracker
from deep6.copilot.types import ChartAnalysis, MADLevel

logger = logging.getLogger(__name__)

_VISION_PROMPT = """Analyze this NinjaTrader trading chart screenshot. Focus on:
1. IDENTIFY all horizontal price levels drawn by the madlevels.com indicator.
   Return each as: {"price": 18450.50, "label": "MAD R1", "type": "resistance"}
   These are typically colored horizontal lines with price labels.
2. Current price action: What's the latest candle doing relative to MAD levels?
3. Any visible chart patterns (double top, flag, wedge, H&S, etc.)
4. Note any other visible support/resistance levels not from MAD

Return JSON with fields: mad_levels, price_action, visual_patterns, support_resistance, confidence
Where:
- mad_levels: array of {price: float, label: string, type: "support"|"resistance"|"pivot"}
- price_action: string description
- visual_patterns: array of pattern names
- support_resistance: array of price floats (non-MAD S/R)
- confidence: float 0-1 (how confident you are in MAD level identification)

If no MAD levels visible, set confidence < 0.3 and explain in price_action."""


class VisionAnalyzer:
    """Analyzes chart screenshots via Claude Vision to extract MAD levels."""

    SIMILARITY_THRESHOLD = 0.05

    def __init__(self, config: CopilotConfig, budget_tracker: TokenBudgetTracker | None = None) -> None:
        self._config = config
        self._budget_tracker = budget_tracker
        self._last_hash: str | None = None
        self._last_screenshot_b64: str | None = None
        self._last_analysis: ChartAnalysis | None = None
        self._last_input_tokens = 0
        self._last_output_tokens = 0
        if anthropic is not None and config.claude_api_key:
            self._client = anthropic.AsyncAnthropic(api_key=config.claude_api_key)
        else:
            self._client = None
            logger.warning("vision.anthropic_unavailable reason=no_api_key_or_not_installed")

    @property
    def last_input_tokens(self) -> int:
        return self._last_input_tokens

    @property
    def last_output_tokens(self) -> int:
        return self._last_output_tokens

    async def analyze_chart(self, screenshot_b64: str) -> ChartAnalysis:
        """Analyze screenshot and return structured chart data.

        Uses frame differencing to skip re-analysis of identical screenshots.
        """
        img_hash = self._compute_hash(screenshot_b64)
        if img_hash == self._last_hash and self._last_analysis is not None:
            logger.debug("vision.cache_hit hash=%s", img_hash[:8])
            return self._last_analysis

        if self._last_screenshot_b64 is not None and self._last_analysis is not None:
            if self._compute_change_ratio(self._last_screenshot_b64, screenshot_b64) <= self.SIMILARITY_THRESHOLD:
                logger.debug("vision.similarity_cache_hit hash=%s", img_hash[:8])
                self._last_hash = img_hash
                self._last_screenshot_b64 = screenshot_b64
                return self._last_analysis

        if self._client is None:
            analysis = ChartAnalysis(confidence=0.0, price_action="Vision unavailable — no API key")
            self._last_hash = img_hash
            self._last_screenshot_b64 = screenshot_b64
            self._last_analysis = analysis
            return self._last_analysis

        if self._budget_tracker is not None and not self._budget_tracker.can_make_call(estimated_tokens=3000):
            logger.warning("Vision API call skipped: token budget exceeded")
            analysis = ChartAnalysis(confidence=0.0, price_action="Budget exceeded")
            self._last_hash = img_hash
            self._last_screenshot_b64 = screenshot_b64
            self._last_analysis = analysis
            return analysis

        try:
            response = await self._client.messages.create(
                model=self._config.claude_vision_model,
                max_tokens=1024,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": screenshot_b64,
                                },
                            },
                            {"type": "text", "text": _VISION_PROMPT},
                        ],
                    }
                ],
            )
            self._last_input_tokens = response.usage.input_tokens
            self._last_output_tokens = response.usage.output_tokens
            if self._budget_tracker is not None:
                self._budget_tracker.record_usage(
                    self._last_input_tokens,
                    self._last_output_tokens,
                    call_type="vision",
                )
        except Exception as exc:
            logger.warning("vision.analysis_failed error=%s", exc)
            return ChartAnalysis(confidence=0.0, price_action=f"Vision error: {exc}")

        text = self._extract_text(response.content)
        analysis = self._parse_analysis(text)
        self._last_hash = img_hash
        self._last_screenshot_b64 = screenshot_b64
        self._last_analysis = analysis
        return analysis

    def _compute_hash(self, screenshot_b64: str) -> str:
        """Compute SHA-256 hash of screenshot for frame differencing."""
        return hashlib.sha256(screenshot_b64.encode("ascii", errors="ignore")).hexdigest()

    def _parse_analysis(self, text: str) -> ChartAnalysis:
        """Parse Claude's JSON response into ChartAnalysis."""
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start < 0 or end <= 0:
                return ChartAnalysis(confidence=0.0, raw_analysis=text)

            data: dict[str, Any] = json.loads(text[start:end])

            mad_levels = tuple(
                MADLevel(
                    price=float(m.get("price", 0)),
                    label=str(m.get("label", "")),
                    level_type=str(m.get("type", m.get("level_type", ""))),
                )
                for m in (data.get("mad_levels") or [])
                if isinstance(m, dict) and m.get("price")
            )

            raw_patterns = data.get("visual_patterns") or []
            visual_patterns = tuple(str(p) for p in raw_patterns) if isinstance(raw_patterns, list) else tuple()

            raw_support_resistance = data.get("support_resistance") or []
            support_resistance = (
                tuple(float(p) for p in raw_support_resistance if isinstance(p, (int, float)))
                if isinstance(raw_support_resistance, list)
                else tuple()
            )

            confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5))))
            if not mad_levels:
                confidence = min(confidence, 0.25)

            return ChartAnalysis(
                mad_levels=mad_levels,
                price_action=str(data.get("price_action", "")),
                visual_patterns=visual_patterns,
                support_resistance=support_resistance,
                confidence=confidence,
                raw_analysis=text,
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("vision.parse_failed error=%s", exc)
            return ChartAnalysis(confidence=0.0, raw_analysis=text)

    def _compute_change_ratio(self, previous_b64: str, current_b64: str) -> float:
        """Estimate byte-level change ratio for near-identical screenshots."""
        try:
            previous = base64.b64decode(previous_b64, validate=False)
            current = base64.b64decode(current_b64, validate=False)
        except Exception:
            return 1.0

        if previous == current:
            return 0.0
        if not previous or not current:
            return 1.0

        try:
            from io import BytesIO
            from PIL import Image

            previous_image = Image.open(BytesIO(previous)).convert("RGB")
            current_image = Image.open(BytesIO(current)).convert("RGB")
        except Exception:
            return 1.0

        if previous_image.size != current_image.size:
            return 1.0

        total_pixels = previous_image.size[0] * previous_image.size[1]
        if total_pixels == 0:
            return 0.0

        previous_pixels = previous_image.load()
        current_pixels = current_image.load()
        changed = 0
        for x in range(previous_image.size[0]):
            for y in range(previous_image.size[1]):
                if previous_pixels[x, y] != current_pixels[x, y]:
                    changed += 1

        return changed / total_pixels

    def _extract_text(self, content_blocks: list[Any]) -> str:
        parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
                continue
            if getattr(block, "type", None) == "text":
                parts.append(str(getattr(block, "text", "")))
        return "".join(parts).strip()
