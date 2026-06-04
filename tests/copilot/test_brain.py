from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from deep6.copilot.brain import CopilotBrain


class FakeRetryableError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"retryable {status_code}")
        self.status_code = status_code


class FakeStream:
    def __init__(self, chunks: list[str], input_tokens: int = 12, output_tokens: int = 7) -> None:
        self.text_stream = chunks
        self._final_message = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
        )

    def __enter__(self) -> FakeStream:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def get_final_message(self):
        return self._final_message


@pytest.mark.asyncio
async def test_generate_narrative_streams_chunks_and_tracks_tokens(copilot_config) -> None:
    client = Mock()
    client.messages.stream.return_value = FakeStream(["MAD ", "levels ", "holding"])

    with patch("anthropic.Anthropic", return_value=client):
        brain = CopilotBrain(copilot_config)
        chunks = [chunk async for chunk in brain.generate_narrative("Context here")]

    assert chunks == ["MAD ", "levels ", "holding"]
    assert brain.total_input_tokens == 12
    assert brain.total_output_tokens == 7
    assert list(brain._history)[-2:] == [
        {"role": "user", "content": "Context here"},
        {"role": "assistant", "content": "MAD levels holding"},
    ]


@pytest.mark.asyncio
async def test_generate_trade_call_retries_and_parses_response(copilot_config) -> None:
    response = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="text",
                text='{"direction":"LONG","entry":18450.0,"stop":18440.0,"target":18480.0,'
                '"confidence":87,"mad_levels":[{"price":18450.0,"label":"MAD S1","level_type":"support"}],'
                '"signals":["absorption","delta_reversal"],"rationale":"MAD S1 held with absorption."}',
            )
        ],
        usage=SimpleNamespace(input_tokens=30, output_tokens=20),
    )
    client = Mock()
    client.messages.create.side_effect = [FakeRetryableError(429), response]

    with patch("anthropic.Anthropic", return_value=client):
        brain = CopilotBrain(copilot_config)
        trade_call = await brain.generate_trade_call("Trade context", "ZmFrZS1wbmc=")

    assert client.messages.create.call_count == 2
    assert trade_call.direction == "LONG"
    assert trade_call.entry == 18450.0
    assert trade_call.confidence == 87.0
    assert trade_call.mad_levels[0].label == "MAD S1"
    assert trade_call.signals == ("absorption", "delta_reversal")
    assert brain.total_input_tokens == 30
    assert brain.total_output_tokens == 20


@pytest.mark.asyncio
async def test_generate_trade_call_returns_low_confidence_on_invalid_json(copilot_config) -> None:
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="not valid json")],
        usage=SimpleNamespace(input_tokens=9, output_tokens=4),
    )
    client = Mock()
    client.messages.create.return_value = response

    with patch("anthropic.Anthropic", return_value=client):
        brain = CopilotBrain(copilot_config)
        trade_call = await brain.generate_trade_call("Trade context", "ZmFrZS1wbmc=")

    assert trade_call.direction == "NONE"
    assert trade_call.confidence == 0.0
    assert "invalid JSON trade call" in trade_call.rationale


def test_build_messages_includes_vision_block_and_history_rolls(copilot_config) -> None:
    client = Mock()

    with patch("anthropic.Anthropic", return_value=client):
        brain = CopilotBrain(copilot_config)

    for idx in range(12):
        brain._add_to_history("assistant", f"msg-{idx}")

    messages = brain._build_messages("Current context", "ZmFrZS1wbmc=")

    assert len(brain._history) == 10
    assert list(brain._history)[0] == {"role": "assistant", "content": "msg-2"}
    assert messages[-1]["content"][0]["source"]["media_type"] == "image/png"
    assert messages[-1]["content"][1]["text"] == "Current context"
