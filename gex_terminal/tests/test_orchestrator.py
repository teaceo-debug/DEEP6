"""Tests for the GEX orchestrator."""
from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from nq_atlas.types import FlowResult

from gex_terminal.config import Settings
from gex_terminal.engine.adapters.flashalpha import FlashAlphaResult
from gex_terminal.engine.adapters.massive import MassiveResult
from gex_terminal.engine.analyzer import AnalysisResult, GEXAnalyzer
from gex_terminal.engine.learner import SessionLearner
from gex_terminal.engine.orchestrator import GEXOrchestrator
from gex_terminal.engine.regime_gate import HMMRegimeGate
from gex_terminal.schemas import (
    BiasVerdict,
    ClaudeNarrative,
    DealerPositioning,
    FlowSummary,
    GEXLevels,
    SourceHealth,
    VannaCharmState,
    ZeroDTEState,
)
from gex_terminal.engine.adapters.unusual_whales import DarkPoolLevel, DarkPoolSummary


def _settings() -> Settings:
    return Settings(
        flashalpha_api_key="fa",
        massive_api_key="massive",
        anthropic_api_key="anthropic",
        refresh_interval_sec=30,
    )


def _flashalpha_result(*, status: str = "ok") -> FlashAlphaResult:
    now = time.time()
    return FlashAlphaResult(
        levels=GEXLevels(gamma_flip=450.0, call_wall=455.0, put_wall=445.0, hvl=451.0),
        dealer=DealerPositioning(
            net_gex=3_200_000_000,
            net_dex=1_100_000_000,
            net_vex=250_000_000,
            net_chex=-100_000_000,
            regime="positive",
            hedge_direction="buying",
        ),
        zero_dte=ZeroDTEState(gex_pct_of_total=0.25, pin_risk="medium", gamma_acceleration=0.4),
        source_health=SourceHealth(name="flashalpha", status=status, last_update=now, ttl_sec=60),
        raw={"summary": {"gamma_flip": 450.0}},
    )


def _massive_result(*, status: str = "ok") -> MassiveResult:
    now = time.time()
    raw_gex = SimpleNamespace(spot=452.0)
    return MassiveResult(
        levels=GEXLevels(gamma_flip=450.2, call_wall=455.1, put_wall=444.9),
        source_health=SourceHealth(name="massive", status=status, last_update=now, ttl_sec=60),
        raw_gex_result=raw_gex,
        flow_result=FlowResult(net_direction=1, z_score=1.8, signed_premium_5m=1_800_000),
    )


def _uw_result(*, status: str = "ok") -> DarkPoolSummary:
    now = time.time()
    return DarkPoolSummary(
        levels=[DarkPoolLevel(price_qqq=452.0, price_nq=17402.0, total_premium=2_500_000.0, print_count=2)],
        net_premium=2_500_000.0,
        institutional_bias="bullish",
        source_health=SourceHealth(name="unusual_whales", status=status, last_update=now, ttl_sec=60),
    )


def _institutional_raw() -> dict:
    return {
        "ownership": {
            "data": [
                {
                    "institution_name": "Big Fund",
                    "shares": 1000,
                    "value_usd": 250000.0,
                }
            ]
        },
        "filings": {
            "data": [
                {
                    "institution_name": "Big Fund",
                    "filing_date": "2026-06-01",
                    "total_value_usd": 5000000.0,
                    "action": "BUY",
                }
            ]
        },
        "inst_flow": {
            "data": [
                {
                    "price": 4.25,
                    "size": 100,
                    "premium": 600000.0,
                    "executed_at": "2026-06-01T10:00:00Z",
                    "side": "BUY",
                }
            ]
        },
        "market_tide": {"data": {"call_premium": 1_500_000.0, "put_premium": 800_000.0}},
        "dp_detailed": {
            "data": [
                {"price": 451.0, "premium": 4_000_000.0, "size": 120000},
                {"price": 451.4, "premium": 2_500_000.0, "size": 80000},
            ]
        },
        "oi_change": {
            "data": [
                {"type": "CALL", "oi_change": 1000},
                {"type": "PUT", "oi_change": 500},
            ]
        },
        "flow_alerts": {
            "data": [
                {"type": "CALL", "premium": 900000.0},
                {"type": "PUT", "premium": 200000.0},
            ]
        },
    }


def _analysis_result(*, material_change: bool = True) -> AnalysisResult:
    return AnalysisResult(
        bias=BiasVerdict(direction="BULLISH", confidence=81, grade="A", regime_name="Positive Gamma"),
        levels=GEXLevels(gamma_flip=17328.85, call_wall=17519.43, put_wall=17128.57, hvl=17363.5),
        dealer=DealerPositioning(
            net_gex=3_200_000_000,
            net_dex=1_100_000_000,
            net_vex=250_000_000,
            net_chex=-100_000_000,
            regime="positive",
            hedge_direction="buying",
        ),
        flow=FlowSummary(
            direction="bullish",
            intensity=0.96,
            sweep_count=2,
            block_count=1,
            z_score=1.8,
            raw_direction="bullish",
        ),
        vanna_charm=VannaCharmState(
            vanna_exposure=250_000_000,
            charm_exposure=-100_000_000,
            net_hedge_direction="tailwind",
        ),
        zero_dte=ZeroDTEState(gex_pct_of_total=0.25, pin_risk="medium", gamma_acceleration=0.4),
        material_change=material_change,
        nq_qqq_ratio=38.5,
    )


class StubInterpreter:
    def __init__(self) -> None:
        self.daily_spend = 0.004
        self.calls: list[tuple[bool, int]] = []

    async def interpret(self, *, bias, levels, dealer, material_change, cycle_count=0):
        del bias, levels, dealer
        self.calls.append((material_change, cycle_count))
        return ClaudeNarrative(
            text="Positive gamma\nWatch 17,520\nRisk below 17,330",
            model="claude-test",
            timestamp=time.time(),
            cached=not material_change,
            cost_usd=0.004 if material_change else 0.0,
        )


class StubLearner(SessionLearner):
    def __init__(self) -> None:
        self.recorded: list[dict] = []
        self.saved_notes: list[str] = []

    def record_cycle(self, **kwargs) -> None:
        self.recorded.append(kwargs)

    def save_session(self, notes: str = "", actual_outcome: str = "unknown") -> None:
        del actual_outcome
        self.saved_notes.append(notes)


@pytest.mark.asyncio
async def test_full_cycle_with_mock_adapters():
    fa_result = _flashalpha_result()
    massive_result = _massive_result()
    uw_result = _uw_result()
    fa_adapter = SimpleNamespace(poll=AsyncMock(return_value=fa_result))
    massive_adapter = SimpleNamespace(poll=AsyncMock(return_value=massive_result))
    uw_adapter = SimpleNamespace(
        poll=AsyncMock(return_value=uw_result),
        poll_institutional=AsyncMock(return_value=_institutional_raw()),
    )
    analyzer = SimpleNamespace(analyze=Mock(return_value=_analysis_result()))
    regime_gate = SimpleNamespace(update=Mock(return_value="TRENDING"))
    interpreter = StubInterpreter()
    learner = StubLearner()
    orchestrator = GEXOrchestrator(
        _settings(),
        fa_adapter=fa_adapter,
        massive_adapter=massive_adapter,
        uw_adapter=uw_adapter,
        analyzer=analyzer,
        regime_gate=regime_gate,
        interpreter=interpreter,
        learner=learner,
        initial_massive_delay_sec=0.0,
    )

    snapshot = await orchestrator._run_cycle()

    assert snapshot.bias.direction == "BULLISH"
    assert snapshot.levels.gamma_flip == 17328.85
    assert snapshot.sources["flashalpha"].status == "ok"
    assert snapshot.sources["massive"].status == "ok"
    assert snapshot.hmm_regime == "TRENDING"
    assert snapshot.direction_signal == "LONG"
    assert snapshot.direction_confidence > 0
    assert snapshot.direction_reason
    assert interpreter.calls == [(True, 1)]
    assert snapshot.institutional is not None
    assert snapshot.institutional.signal_grid.confluence_buy >= 1
    assert len(snapshot.institutional.dp_levels) >= 1
    assert learner.recorded[0]["bias_direction"] == "BULLISH"
    assert learner.recorded[0]["flow_direction"] == "bullish"
    fa_adapter.poll.assert_awaited_once()
    massive_adapter.poll.assert_awaited_once()
    regime_gate.update.assert_called_once()
    analyzer.analyze.assert_called_once_with(
        fa_result,
        massive_result,
        nq_spot=None,
        qqq_spot=452.0,
        hmm_state="TRENDING",
        dark_pool_direction=uw_result.institutional_bias,
        dp_levels_nq=uw_result.levels_nq,
    )


@pytest.mark.asyncio
async def test_source_failure_graceful():
    fa_adapter = SimpleNamespace(poll=AsyncMock(side_effect=RuntimeError("flashalpha down")))
    massive_adapter = SimpleNamespace(poll=AsyncMock(return_value=_massive_result()))
    uw_adapter = SimpleNamespace(
        poll=AsyncMock(return_value=_uw_result()),
        poll_institutional=AsyncMock(return_value=_institutional_raw()),
    )
    analyzer = GEXAnalyzer()
    interpreter = StubInterpreter()
    orchestrator = GEXOrchestrator(
        _settings(),
        fa_adapter=fa_adapter,
        massive_adapter=massive_adapter,
        uw_adapter=uw_adapter,
        analyzer=analyzer,
        interpreter=interpreter,
        initial_massive_delay_sec=0.0,
    )

    snapshot = await orchestrator._run_cycle()

    assert snapshot.sources["flashalpha"].status == "error"
    assert snapshot.sources["flashalpha"].error_msg == "flashalpha down"
    assert snapshot.sources["massive"].status == "ok"
    assert snapshot.bias.direction in {"NEUTRAL", "BULLISH", "BEARISH"}


@pytest.mark.asyncio
async def test_cycle_count_increments():
    fa_adapter = SimpleNamespace(poll=AsyncMock(return_value=_flashalpha_result()))
    massive_adapter = SimpleNamespace(poll=AsyncMock(return_value=_massive_result()))
    uw_adapter = SimpleNamespace(
        poll=AsyncMock(return_value=_uw_result()),
        poll_institutional=AsyncMock(return_value=_institutional_raw()),
    )
    analyzer = SimpleNamespace(analyze=Mock(side_effect=[_analysis_result(), _analysis_result(material_change=False)]))
    interpreter = StubInterpreter()
    orchestrator = GEXOrchestrator(
        _settings(),
        fa_adapter=fa_adapter,
        massive_adapter=massive_adapter,
        uw_adapter=uw_adapter,
        analyzer=analyzer,
        interpreter=interpreter,
        initial_massive_delay_sec=0.0,
    )

    await orchestrator._run_cycle()
    await orchestrator._run_cycle()

    assert orchestrator.cycle_count == 2
    assert interpreter.calls == [(True, 1), (True, 2)]


@pytest.mark.asyncio
async def test_standalone_deep6_bias_when_bridge_unavailable():
    fa_adapter = SimpleNamespace(poll=AsyncMock(return_value=_flashalpha_result()))
    massive_adapter = SimpleNamespace(poll=AsyncMock(return_value=_massive_result()))
    uw_adapter = SimpleNamespace(
        poll=AsyncMock(return_value=_uw_result()),
        poll_institutional=AsyncMock(return_value=_institutional_raw()),
    )
    analyzer = SimpleNamespace(analyze=Mock(return_value=_analysis_result()))
    interpreter = StubInterpreter()
    bridge = SimpleNamespace(
        push_gex_snapshot=AsyncMock(side_effect=RuntimeError("offline")),
        read_bias=AsyncMock(),
    )
    orchestrator = GEXOrchestrator(
        _settings(),
        fa_adapter=fa_adapter,
        massive_adapter=massive_adapter,
        uw_adapter=uw_adapter,
        analyzer=analyzer,
        interpreter=interpreter,
        bridge=bridge,
        initial_massive_delay_sec=0.0,
    )

    snapshot = await orchestrator._run_cycle()

    assert snapshot.deep6_bias_score is None
    assert snapshot.deep6_bias_label == "STANDALONE"
    assert snapshot.deep6_confidence is None
    bridge.read_bias.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcast_called_with_snapshot():
    fa_result = _flashalpha_result()
    massive_result = _massive_result()
    uw_result = _uw_result()
    fa_adapter = SimpleNamespace(poll=AsyncMock(return_value=fa_result))
    massive_adapter = SimpleNamespace(poll=AsyncMock(return_value=massive_result))
    uw_adapter = SimpleNamespace(
        poll=AsyncMock(return_value=uw_result),
        poll_institutional=AsyncMock(return_value=_institutional_raw()),
    )
    analyzer = SimpleNamespace(analyze=Mock(return_value=_analysis_result()))
    interpreter = StubInterpreter()
    broadcast = AsyncMock()
    orchestrator = GEXOrchestrator(
        _settings(),
        fa_adapter=fa_adapter,
        massive_adapter=massive_adapter,
        uw_adapter=uw_adapter,
        analyzer=analyzer,
        interpreter=interpreter,
        initial_massive_delay_sec=0.0,
    )
    orchestrator.set_broadcast(broadcast)

    snapshot = await orchestrator._run_cycle()

    broadcast.assert_awaited_once()
    payload = broadcast.await_args.args[0]
    assert payload["bias"]["direction"] == "BULLISH"
    assert payload["sources"]["flashalpha"]["status"] == "ok"
    assert payload["hmm_regime"] == "UNKNOWN"
    assert payload["direction_signal"] == "LONG"
    assert payload["institutional"]["signal_grid"]["confluence_buy"] >= 1
    assert payload["timestamp"] == snapshot.timestamp


def test_build_hmm_features_returns_five_normalized_values():
    orchestrator = GEXOrchestrator(_settings(), regime_gate=HMMRegimeGate())

    features = orchestrator._build_hmm_features(_flashalpha_result(), _massive_result())

    assert len(features) == 5
    assert all(0.0 <= value <= 1.0 for value in features)


def test_stop_only_signals_loop_and_save_is_explicit():
    learner = StubLearner()
    orchestrator = GEXOrchestrator(_settings(), learner=learner)

    orchestrator.stop()

    assert learner.saved_notes == []


def test_save_session_learning_uses_learner_notes():
    learner = StubLearner()
    orchestrator = GEXOrchestrator(_settings(), learner=learner)
    orchestrator._cycle_count = 3

    orchestrator._save_session_learning()

    assert learner.saved_notes == ["Session ended after 3 cycles."]
