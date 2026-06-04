"""Signal quality validation against a fixed replay dataset.

Methodology:
- Uses a deterministic, hand-curated replay fixture instead of live APIs.
- Sessions are balanced across positive gamma, negative gamma, pin/neutral,
  and pre-event contexts.
- Fixture values are realistic for 2026-style QQQ levels (440-460) and an
  NQ/QQQ ratio near 38.5, but are intentionally simplified to validate the
  analyzer's explicit regime-to-bias logic rather than historical tick parity.

Pass thresholds:
- Overall directional accuracy >= 55%
- Positive gamma regime accuracy >= 60%
- Negative gamma regime accuracy >= 55%
- No catastrophic errors (BULLISH when BEARISH with confidence > 80%)
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any
from types import ModuleType

import pytest

if "flashalpha" not in sys.modules:
    flashalpha_stub = ModuleType("flashalpha")

    class _StubFlashAlpha:  # pragma: no cover - import shim only
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    flashalpha_stub.FlashAlpha = _StubFlashAlpha
    sys.modules["flashalpha"] = flashalpha_stub

if "scipy" not in sys.modules:
    scipy_stub = ModuleType("scipy")
    scipy_stats_stub = ModuleType("scipy.stats")

    class _Norm:  # pragma: no cover - import shim only
        @staticmethod
        def pdf(value: float) -> float:
            return math.exp(-(value**2) / 2.0) / math.sqrt(2.0 * math.pi)

    scipy_stats_stub.norm = _Norm()
    scipy_stub.stats = scipy_stats_stub
    sys.modules["scipy"] = scipy_stub
    sys.modules["scipy.stats"] = scipy_stats_stub

from gex_terminal.engine.adapters.flashalpha import FlashAlphaResult
from gex_terminal.engine.adapters.massive import MassiveResult
from gex_terminal.engine.analyzer import GEXAnalyzer
from gex_terminal.schemas import DealerPositioning, GEXLevels, SourceHealth, ZeroDTEState

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "replay_sessions.json"
FIXTURE_TS = time.time()


def load_sessions() -> list[dict[str, Any]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def make_fa_result(session: dict[str, Any]) -> FlashAlphaResult:
    """Build FlashAlphaResult from a replay session."""
    net_gex_sign = session["net_gex_sign"]
    regime = session["gex_regime"]
    levels = GEXLevels(
        gamma_flip=session["gamma_flip_qqq"],
        call_wall=session["call_wall_qqq"],
        put_wall=session["put_wall_qqq"],
    )
    dealer = DealerPositioning(
        net_gex=net_gex_sign * 3_000_000_000,
        regime=regime,
        hedge_direction="buying" if net_gex_sign > 0 else "selling" if net_gex_sign < 0 else "neutral",
    )
    zero_dte = ZeroDTEState(pin_risk="high" if session["session_bucket"] == "pre_event" else "low")
    health = SourceHealth(name="flashalpha", status="ok", last_update=FIXTURE_TS, ttl_sec=60)
    return FlashAlphaResult(levels=levels, dealer=dealer, zero_dte=zero_dte, source_health=health, raw={})


def make_massive_result(session: dict[str, Any]) -> MassiveResult:
    """Build MassiveResult from a replay session."""
    levels = GEXLevels(
        gamma_flip=session["gamma_flip_qqq"],
        call_wall=session["call_wall_qqq"],
        put_wall=session["put_wall_qqq"],
    )
    health = SourceHealth(name="massive", status="ok", last_update=FIXTURE_TS, ttl_sec=60)
    return MassiveResult(levels=levels, source_health=health, raw_gex_result=None, flow_result=None)


def _emit_metric(request: pytest.FixtureRequest, line: str) -> None:
    terminal_reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if terminal_reporter is not None:
        terminal_reporter.write_line(line)


def _scored_accuracy(rows: list[dict[str, Any]]) -> tuple[int, int, float]:
    correct = sum(1 for row in rows if row["predicted"] != "NEUTRAL" and row["predicted"] == row["actual"])
    total = sum(1 for row in rows if row["predicted"] != "NEUTRAL")
    accuracy = (correct / total) if total else 0.0
    return correct, total, accuracy


def _evaluate_sessions(analyzer: GEXAnalyzer, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for session in sessions:
        result = analyzer.analyze(make_fa_result(session), make_massive_result(session))
        rows.append(
            {
                "date": session["date"],
                "bucket": session["session_bucket"],
                "regime": session["gex_regime"],
                "predicted": result.bias.direction,
                "actual": session["actual_direction"],
                "confidence": result.bias.confidence,
            }
        )
    return rows


class TestSignalQuality:
    """Signal quality validation against a fixed historical replay dataset."""

    def setup_method(self) -> None:
        self.sessions = load_sessions()
        self.analyzer = GEXAnalyzer()

    def test_fixture_has_minimum_sessions(self) -> None:
        assert len(self.sessions) >= 10, f"Need >=10 sessions, got {len(self.sessions)}"

    def test_fixture_covers_required_distribution(self) -> None:
        regimes = Counter(session["gex_regime"] for session in self.sessions)
        buckets = Counter(session["session_bucket"] for session in self.sessions)

        assert regimes["positive"] == 5, f"Expected 5 positive sessions, got {regimes['positive']}"
        assert regimes["negative"] == 5, f"Expected 5 negative sessions, got {regimes['negative']}"
        assert regimes["neutral"] == 5, f"Expected 5 neutral sessions, got {regimes['neutral']}"
        assert buckets["pin_neutral"] == 3, f"Expected 3 pin/neutral sessions, got {buckets['pin_neutral']}"
        assert buckets["pre_event"] == 2, f"Expected 2 pre-event sessions, got {buckets['pre_event']}"

    def test_signal_quality_thresholds_and_breakdown(self, request: pytest.FixtureRequest) -> None:
        rows = _evaluate_sessions(self.analyzer, self.sessions)

        overall_correct, overall_total, overall_accuracy = _scored_accuracy(rows)
        positive_rows = [row for row in rows if row["regime"] == "positive"]
        negative_rows = [row for row in rows if row["regime"] == "negative"]
        neutral_rows = [row for row in rows if row["regime"] == "neutral"]
        positive_correct, positive_total, positive_accuracy = _scored_accuracy(positive_rows)
        negative_correct, negative_total, negative_accuracy = _scored_accuracy(negative_rows)
        neutral_predictions = Counter(row["predicted"] for row in neutral_rows)

        _emit_metric(request, "Signal quality breakdown:")
        _emit_metric(request, f"  Overall accuracy: {overall_accuracy:.1%} ({overall_correct}/{overall_total})")
        _emit_metric(request, f"  Positive gamma accuracy: {positive_accuracy:.1%} ({positive_correct}/{positive_total})")
        _emit_metric(request, f"  Negative gamma accuracy: {negative_accuracy:.1%} ({negative_correct}/{negative_total})")
        _emit_metric(
            request,
            "  Neutral regime predictions: "
            f"NEUTRAL={neutral_predictions.get('NEUTRAL', 0)}, "
            f"BULLISH={neutral_predictions.get('BULLISH', 0)}, "
            f"BEARISH={neutral_predictions.get('BEARISH', 0)}",
        )

        assert overall_total > 0, "All predictions were NEUTRAL — cannot compute accuracy"
        assert positive_total > 0, "No non-neutral positive gamma predictions"
        assert negative_total > 0, "No non-neutral negative gamma predictions"
        assert overall_accuracy >= 0.55, f"Overall accuracy {overall_accuracy:.1%} < 55% threshold"
        assert positive_accuracy >= 0.60, f"Positive gamma accuracy {positive_accuracy:.1%} < 60% threshold"
        assert negative_accuracy >= 0.55, f"Negative gamma accuracy {negative_accuracy:.1%} < 55% threshold"

    def test_no_catastrophic_errors(self, request: pytest.FixtureRequest) -> None:
        rows = _evaluate_sessions(self.analyzer, self.sessions)
        catastrophic = [
            row
            for row in rows
            if row["predicted"] == "BULLISH" and row["actual"] == "BEARISH" and row["confidence"] > 80
        ]
        _emit_metric(request, f"Catastrophic errors: {len(catastrophic)}")
        assert catastrophic == [], f"Catastrophic errors found: {catastrophic}"

    def test_deterministic_results(self) -> None:
        first_pass = [
            self.analyzer.analyze(make_fa_result(session), make_massive_result(session)).bias.direction
            for session in self.sessions
        ]

        self.analyzer = GEXAnalyzer()

        second_pass = [
            self.analyzer.analyze(make_fa_result(session), make_massive_result(session)).bias.direction
            for session in self.sessions
        ]

        assert first_pass == second_pass, "Results are not deterministic"
