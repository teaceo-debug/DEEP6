"""Tests for Claude interpreter."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

from gex_terminal.engine.flashalpha_mcp import FlashAlphaMCPClient
from gex_terminal.engine.interpreter import ClaudeInterpreter
from gex_terminal.engine.learner import SessionLearner
from gex_terminal.schemas import BiasVerdict, ClaudeNarrative, DealerPositioning, GEXLevels


def make_bias(
    direction: str = "BULLISH",
    confidence: int = 80,
    grade: str = "A",
    regime: str = "Positive Gamma",
) -> BiasVerdict:
    return BiasVerdict(direction=direction, confidence=confidence, grade=grade, regime_name=regime)


def make_levels(
    flip: float = 21380.0,
    call_wall: float = 21500.0,
    put_wall: float = 20900.0,
) -> GEXLevels:
    return GEXLevels(gamma_flip=flip, call_wall=call_wall, put_wall=put_wall)


def make_dealer(regime: str = "positive", hedge: str = "buying") -> DealerPositioning:
    return DealerPositioning(net_gex=3_200_000_000, regime=regime, hedge_direction=hedge)


def test_conditional_call_on_material_change(tmp_path: Path):
    """Claude is called when material_change=True."""
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl")

    with patch.object(
        interp,
        "_call_claude",
        new=AsyncMock(return_value=("Positive gamma\nWatch 21,500\nRisk: lose 21,380", 0.003, 100, 30)),
    ) as mock_call:
        result = asyncio.run(
            interp.interpret(make_bias(), make_levels(), make_dealer(), material_change=True)
        )

    assert mock_call.await_count == 1
    assert result.cached is False
    assert len(result.text) > 0
    assert result.cost_usd > 0


def test_no_call_on_non_material_change(tmp_path: Path):
    """Claude is NOT called when material_change=False."""
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl")
    interp._last_narrative = ClaudeNarrative(
        text="Cached narrative text here.",
        model="claude-haiku-4-5-20251001",
        timestamp=1748527200.0,
        cached=False,
        cost_usd=0.003,
    )

    with patch.object(interp, "_call_claude", new=AsyncMock()) as mock_call:
        result = asyncio.run(
            interp.interpret(make_bias(), make_levels(), make_dealer(), material_change=False)
        )

    mock_call.assert_not_awaited()
    assert result.cached is True
    assert result.text == "Cached narrative text here."


def test_calls_every_third_cycle_during_market_hours(tmp_path: Path):
    """Scheduled live refresh fires every 3rd cycle during market hours."""
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl")

    with patch("gex_terminal.engine.interpreter.is_options_market_open", return_value=True):
        assert interp.should_call(material_change=False, cycle_count=2) is False
        assert interp.should_call(material_change=False, cycle_count=3) is True


def test_calls_every_fifth_cycle_regardless_of_market_hours(tmp_path: Path):
    """Safety cadence still fires at least every 5 cycles."""
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl")

    with patch("gex_terminal.engine.interpreter.is_options_market_open", return_value=False):
        assert interp.should_call(material_change=False, cycle_count=5) is True


def test_prompt_includes_live_cycle_context(tmp_path: Path):
    """Prompt tells Claude this is a live cycle refresh."""
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl")

    prompt = interp._build_prompt(
        make_bias(),
        make_levels(),
        make_dealer(),
        cycle_count=6,
        material_change=False,
    )

    assert "Cycle: #6" in prompt
    assert "scheduled live refresh" in prompt
    assert "Provide FRESH analysis of the CURRENT state." in prompt


def test_budget_enforcement(tmp_path: Path):
    """Claude is not called when daily budget is exceeded."""
    interp = ClaudeInterpreter(api_key="test_key", budget_daily_usd=1.0, audit_log_path=tmp_path / "usage.jsonl")
    interp._daily_spend = 1.5

    assert interp.should_call(material_change=True) is False


def test_narrative_truncated_to_240_chars(tmp_path: Path):
    """Narrative is truncated to 240 chars."""
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl")
    long_text = "A" * 300

    with patch.object(interp, "_call_claude", new=AsyncMock(return_value=(long_text, 0.003, 100, 30))):
        result = asyncio.run(
            interp.interpret(make_bias(), make_levels(), make_dealer(), material_change=True)
        )

    assert len(result.text) <= 240
    assert result.text.endswith("...")


def test_returns_cached_on_api_error(tmp_path: Path):
    """Returns cached narrative when Claude API fails."""
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl")
    interp._last_narrative = ClaudeNarrative(
        text="Last good narrative.",
        model="claude-haiku-4-5-20251001",
        timestamp=1748527200.0,
        cached=False,
        cost_usd=0.003,
    )

    with patch.object(interp, "_call_claude", new=AsyncMock(side_effect=Exception("API down"))):
        result = asyncio.run(
            interp.interpret(make_bias(), make_levels(), make_dealer(), material_change=True)
        )

    assert result.cached is True
    assert result.text == "Last good narrative."


def test_budget_tracking_logs_to_jsonl(tmp_path: Path):
    """Successful Claude calls append usage to the JSONL audit log."""
    log_path = tmp_path / "usage.jsonl"
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=log_path)

    with patch.object(
        interp,
        "_call_claude",
        new=AsyncMock(return_value=("Positive gamma\nWatch 21,500\nRisk: lose 21,380", 0.003, 120, 40)),
    ):
        asyncio.run(interp.interpret(make_bias(), make_levels(), make_dealer(), material_change=True))

    entries = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(entries) == 1
    payload = json.loads(entries[0])
    assert payload["model"] == "claude-haiku-4-5-20251001"
    assert payload["cost_usd"] == 0.003
    assert payload["direction"] == "BULLISH"
    assert payload["input_tokens"] == 120
    assert payload["output_tokens"] == 40


def test_prompt_includes_recalled_context(tmp_path: Path):
    """Prompt prepends learner recall when available."""
    learner = SessionLearner()
    learner.get_recall_context = lambda: "<recent_session_learnings>Prior session</recent_session_learnings>"
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl", learner=learner)

    prompt = interp._build_prompt(make_bias(), make_levels(), make_dealer())

    assert prompt.startswith("<recent_session_learnings>Prior session</recent_session_learnings>")


def test_prompt_includes_mcp_enrichment(tmp_path: Path):
    """Prompt includes on-demand FlashAlpha enrichment when provided."""
    interp = ClaudeInterpreter(api_key="test_key", audit_log_path=tmp_path / "usage.jsonl")

    prompt = interp._build_prompt(
        make_bias(),
        make_levels(),
        make_dealer(),
        mcp_enrichment="<flashalpha_live_data>extra context</flashalpha_live_data>",
    )

    assert "<flashalpha_live_data>extra context</flashalpha_live_data>" in prompt


def test_interpret_fetches_mcp_only_on_material_change(tmp_path: Path):
    """On-demand FlashAlpha enrichment runs only on material changes."""
    mcp_client = AsyncMock(spec=FlashAlphaMCPClient)
    mcp_client.get_enrichment_context.return_value = "<flashalpha_live_data>enriched</flashalpha_live_data>"
    interp = ClaudeInterpreter(
        api_key="test_key",
        audit_log_path=tmp_path / "usage.jsonl",
        mcp_client=mcp_client,
    )
    interp._last_narrative = ClaudeNarrative(
        text="Cached narrative text here.",
        model="claude-haiku-4-5-20251001",
        timestamp=1748527200.0,
        cached=False,
        cost_usd=0.003,
    )

    with patch.object(
        interp,
        "_call_claude",
        new=AsyncMock(return_value=("Positive gamma\nWatch 21,500\nRisk: lose 21,380", 0.003, 100, 30)),
    ):
        asyncio.run(interp.interpret(make_bias(), make_levels(), make_dealer(), material_change=True))
        asyncio.run(interp.interpret(make_bias(), make_levels(), make_dealer(), material_change=False))

    assert mcp_client.get_enrichment_context.await_count == 1


def test_interpret_gracefully_handles_mcp_failure(tmp_path: Path):
    """MCP enrichment failure does not block Claude narrative generation."""
    mcp_client = AsyncMock(spec=FlashAlphaMCPClient)
    mcp_client.get_enrichment_context.side_effect = RuntimeError("rate limit")
    interp = ClaudeInterpreter(
        api_key="test_key",
        audit_log_path=tmp_path / "usage.jsonl",
        mcp_client=mcp_client,
    )

    with patch.object(
        interp,
        "_call_claude",
        new=AsyncMock(return_value=("Positive gamma\nWatch 21,500\nRisk: lose 21,380", 0.003, 100, 30)),
    ) as mock_call:
        result = asyncio.run(interp.interpret(make_bias(), make_levels(), make_dealer(), material_change=True))

    assert mock_call.await_count == 1
    assert result.cached is False
