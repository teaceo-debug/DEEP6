"""Claude API wrapper for the DEEP6 AI chart copilot."""

from __future__ import annotations

import asyncio
import json
import logging
import time
import sys
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from types import ModuleType
from typing import Any

try:
    import anthropic  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - optional dependency
    anthropic = ModuleType("anthropic")

    class _AnthropicStub:  # pragma: no cover - fallback for tests
        def __init__(self, *args: object, **kwargs: object) -> None:
            self.messages = type("MessagesAPI", (), {})()

    class RateLimitError(Exception):
        pass

    class InternalServerError(Exception):
        pass

    anthropic.Anthropic = _AnthropicStub  # type: ignore[attr-defined]
    anthropic.AsyncAnthropic = _AnthropicStub  # type: ignore[attr-defined]
    anthropic.RateLimitError = RateLimitError  # type: ignore[attr-defined]
    anthropic.InternalServerError = InternalServerError  # type: ignore[attr-defined]
    sys.modules.setdefault("anthropic", anthropic)

from deep6.copilot.config import CopilotConfig
from deep6.copilot.types import MADLevel, TradeCall

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert NQ futures scalping copilot. MAD levels (from madlevels.com) "
    "are your PRIMARY framework — reference them in EVERY analysis.\n"
    "Your job: (1) Running market narrative, (2) Specific trade calls when high-confidence "
    "setups form, (3) Event warnings, (4) Regime change flags.\n"
    "RULES: NEVER suggest a trade without MAD levels. Say explicitly if you can't see MAD "
    "levels. Cite signals by name. Be concise."
)

Message = dict[str, Any]


class CopilotBrain:
    """Thin Claude wrapper for streaming narrative and structured trade calls."""

    def __init__(self, config: CopilotConfig) -> None:
        self._config = config
        self._client = anthropic.Anthropic(api_key=config.claude_api_key)
        self._history: deque[dict[str, str]] = deque(maxlen=10)
        self._total_input_tokens = 0
        self._total_output_tokens = 0

    @property
    def total_input_tokens(self) -> int:
        return self._total_input_tokens

    @property
    def total_output_tokens(self) -> int:
        return self._total_output_tokens

    async def generate_narrative(
        self,
        context: str,
        screenshot_b64: str | None = None,
    ) -> AsyncIterator[str]:
        """Yield narrative chunks from a streaming Sonnet call."""
        messages = self._build_messages(context, screenshot_b64)
        queue: asyncio.Queue[str | object] = asyncio.Queue()
        sentinel = object()
        loop = asyncio.get_running_loop()
        emitted: list[str] = []
        usage_holder: dict[str, int | Exception | None] = {
            "input": None,
            "output": None,
            "error": None,
        }

        def worker() -> None:
            attempts = 0
            while True:
                saw_output = False
                try:
                    with self._client.messages.stream(
                        model=self._config.claude_narrative_model,
                        max_tokens=1024,
                        messages=messages,
                        system=SYSTEM_PROMPT,
                    ) as stream:
                        for text in stream.text_stream:
                            saw_output = True
                            emitted.append(text)
                            asyncio.run_coroutine_threadsafe(queue.put(text), loop).result()
                        final_message = stream.get_final_message()
                    usage_holder["input"] = getattr(final_message.usage, "input_tokens", None)
                    usage_holder["output"] = getattr(final_message.usage, "output_tokens", None)
                    break
                except Exception as exc:  # noqa: BLE001
                    retryable = self._is_retryable_error(exc)
                    if saw_output or not retryable or attempts >= 2:
                        usage_holder["error"] = exc
                        logger.warning("brain.narrative_failed error=%s", exc)
                        break
                    time.sleep(2**attempts)
                    attempts += 1
            asyncio.run_coroutine_threadsafe(queue.put(sentinel), loop).result()

        task = asyncio.create_task(asyncio.to_thread(worker))
        while True:
            chunk = await queue.get()
            if chunk is sentinel:
                break
            yield str(chunk)
        await task

        if usage_holder["error"] is not None and not emitted:
            yield f"[Analysis unavailable: {usage_holder['error']}]"
            return

        full_text = "".join(emitted)
        self._record_usage(
            messages=messages,
            response_text=full_text,
            input_tokens=self._coerce_usage_value(usage_holder["input"]),
            output_tokens=self._coerce_usage_value(usage_holder["output"]),
        )
        self._add_to_history("user", context)
        self._add_to_history("assistant", full_text)

    async def generate_trade_call(self, context: str, screenshot_b64: str) -> TradeCall:
        """Return a parsed trade call from a non-streaming vision request."""
        prompt = (
            f"{context}\n\n"
            "Return JSON only with fields: direction, entry, stop, target, confidence, "
            "mad_levels, signals, rationale. confidence must be 0-100. mad_levels must be "
            "an array of objects with price, label, level_type. If you cannot form a valid "
            "trade call, still return JSON with direction 'NONE', confidence 0, empty arrays, "
            "and explain why in rationale."
        )
        messages = self._build_messages(prompt, screenshot_b64)

        response = await self._retry_with_backoff(
            lambda: asyncio.to_thread(
                self._client.messages.create,
                model=self._config.claude_vision_model,
                max_tokens=1024,
                messages=messages,
                system=SYSTEM_PROMPT,
            )
        )

        text = self._extract_text(getattr(response, "content", []))
        self._record_usage(
            messages=messages,
            response_text=text,
            input_tokens=self._coerce_usage_value(getattr(getattr(response, "usage", None), "input_tokens", None)),
            output_tokens=self._coerce_usage_value(getattr(getattr(response, "usage", None), "output_tokens", None)),
        )
        self._add_to_history("user", prompt)
        self._add_to_history("assistant", text)
        return self._parse_trade_call(text)

    def _build_messages(self, context: str, screenshot_b64: str | None) -> list[Message]:
        messages: list[Message] = [{"role": item["role"], "content": item["content"]} for item in self._history]
        if screenshot_b64:
            messages.append(
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
                        {"type": "text", "text": context},
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": context})
        return messages

    def _add_to_history(self, role: str, content: str) -> None:
        self._history.append({"role": role, "content": content})

    def _count_tokens(self, messages: list[Message]) -> int:
        return max(1, len(json.dumps(messages, ensure_ascii=False)) // 4)

    async def _retry_with_backoff(
        self,
        fn: Callable[[], Awaitable[Any]],
        max_retries: int = 3,
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                return await fn()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if not self._is_retryable_error(exc) or attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2**attempt)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Retry helper exhausted without executing callable")

    def _is_retryable_error(self, exc: Exception) -> bool:
        return isinstance(exc, (anthropic.RateLimitError, anthropic.InternalServerError)) or getattr(exc, "status_code", None) in {429, 500}

    def _record_usage(
        self,
        *,
        messages: list[Message],
        response_text: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        counted_input = input_tokens if input_tokens is not None else self._count_tokens(messages)
        counted_output = output_tokens if output_tokens is not None else max(1, len(response_text) // 4)
        self._total_input_tokens += counted_input
        self._total_output_tokens += counted_output

    def _coerce_usage_value(self, value: Any) -> int | None:
        if isinstance(value, int):
            return value
        return None

    def _extract_text(self, content_blocks: Any) -> str:
        parts: list[str] = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
                continue
            if getattr(block, "type", None) == "text":
                parts.append(str(getattr(block, "text", "")))
        return "".join(parts).strip()

    def _parse_trade_call(self, text: str) -> TradeCall:
        try:
            payload = self._extract_json_object(text)
            data = json.loads(payload)
            mad_levels = tuple(self._parse_mad_level(level) for level in data.get("mad_levels", []))
            return TradeCall(
                direction=str(data.get("direction", "NONE")),
                entry=float(data.get("entry", 0.0)),
                stop=float(data.get("stop", 0.0)),
                target=float(data.get("target", 0.0)),
                confidence=max(0.0, min(100.0, float(data.get("confidence", 0.0)))),
                mad_levels=mad_levels,
                signals=tuple(str(signal) for signal in data.get("signals", [])),
                rationale=str(data.get("rationale", "")),
                timestamp=time.time(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("brain.trade_call_parse_failed error=%s text=%r", exc, text[:200])
            return TradeCall(
                direction="NONE",
                confidence=0.0,
                rationale=f"Claude returned invalid JSON trade call: {text[:200]}",
                timestamp=time.time(),
            )

    def _extract_json_object(self, text: str) -> str:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON object found in Claude response")
        return text[start : end + 1]

    def _parse_mad_level(self, level: Any) -> MADLevel:
        if not isinstance(level, dict):
            raise TypeError("MAD level payload must be an object")
        return MADLevel(
            price=float(level.get("price", 0.0)),
            label=str(level.get("label", "")),
            level_type=str(level.get("level_type", "")),
        )
