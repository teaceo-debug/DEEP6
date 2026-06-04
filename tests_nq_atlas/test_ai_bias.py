"""Test BiasInterpreter — prompt structure, JSON parsing, fallback."""
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from anthropic import APITimeoutError

from nq_atlas.ai_bias import BiasInterpreter
from nq_atlas.state import AtlasState


def test_prompt_is_structured(fresh_state):
    interp = BiasInterpreter(api_key="test")
    prompt = interp._build_prompt(fresh_state)
    assert "CURRENT STATE:" in prompt
    assert "RESPOND IN JSON ONLY" in prompt


def test_prompt_no_prose_wall(fresh_state):
    interp = BiasInterpreter(api_key="test")
    prompt = interp._build_prompt(fresh_state)
    lines = prompt.split("\n")
    # Count lines longer than 200 chars (prose indicator)
    long_lines = [l for l in lines if len(l) > 200]
    assert len(long_lines) == 0, f"Prompt has {len(long_lines)} prose-wall lines"


@pytest.mark.asyncio
async def test_fallback_on_timeout(fresh_state):
    interp = BiasInterpreter(api_key="test")
    interp._client = MagicMock()
    interp._client.messages = MagicMock()
    interp._client.messages.create = AsyncMock(
        side_effect=APITimeoutError(request=MagicMock())
    )
    result = await interp.interpret(fresh_state)
    assert result.degraded is True


@pytest.mark.asyncio
async def test_parses_valid_claude_response(fresh_state):
    mock_response = json.dumps({
        "direction": "BULLISH",
        "conviction": 72,
        "support_nq": 21100,
        "resistance_nq": 21350,
        "narrative": "GEX positive",
        "risk_flags": [],
    })
    interp = BiasInterpreter(api_key="test")
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=mock_response)]
    interp._client = MagicMock()
    interp._client.messages = MagicMock()
    interp._client.messages.create = AsyncMock(return_value=mock_msg)
    result = await interp.interpret(fresh_state)
    assert result.direction.value == "BULLISH"
    assert result.conviction == 72
