"""Tests for the GEX analyzer."""
from __future__ import annotations

import time
from datetime import datetime
from types import SimpleNamespace

from nq_atlas.types import FlowResult

from gex_terminal.engine.adapters.flashalpha import FlashAlphaResult
from gex_terminal.engine.adapters.massive import MassiveResult
from gex_terminal.engine.analyzer import GEXAnalyzer
from gex_terminal.schemas import DealerPositioning, GEXLevels, SourceHealth, ZeroDTEState


def _flashalpha_result(
    *,
    regime: str,
    gamma_flip: float = 450.0,
    call_wall: float = 455.0,
    put_wall: float = 445.0,
    summary_spot: float | None = None,
) -> FlashAlphaResult:
    now = time.time()
    raw = {}
    if summary_spot is not None:
        raw = {"summary": {"spot": summary_spot}}
    return FlashAlphaResult(
        levels=GEXLevels(
            gamma_flip=gamma_flip,
            call_wall=call_wall,
            put_wall=put_wall,
            hvl=451.0,
            zero_dte_magnet=450.5,
        ),
        dealer=DealerPositioning(
            net_gex=3_000_000_000 if regime == "positive" else -3_000_000_000,
            net_dex=1_000_000_000,
            net_vex=200_000_000,
            net_chex=-50_000_000,
            regime=regime,
            hedge_direction="buying" if regime == "positive" else "selling",
        ),
        zero_dte=ZeroDTEState(gex_pct_of_total=0.2, pin_risk="medium", gamma_acceleration=0.35),
        source_health=SourceHealth(name="flashalpha", status="ok", last_update=now, ttl_sec=60),
        raw=raw,
    )


def _massive_result(
    *,
    gamma_flip: float = 450.2,
    call_wall: float = 455.1,
    put_wall: float = 444.9,
    spot: float | None = None,
    flow_result: FlowResult | None = None,
) -> MassiveResult:
    now = time.time()
    raw_gex_result = SimpleNamespace(spot=spot) if spot is not None else None
    return MassiveResult(
        levels=GEXLevels(gamma_flip=gamma_flip, call_wall=call_wall, put_wall=put_wall),
        source_health=SourceHealth(name="massive", status="ok", last_update=now, ttl_sec=60),
        raw_gex_result=raw_gex_result,
        flow_result=flow_result,
    )


def _massive_result_with_regime(
    *,
    regime_sign: int,
    status: str = "ok",
    spot: float = 452.0,
) -> MassiveResult:
    now = time.time()
    raw_gex_result = SimpleNamespace(spot=spot, regime_sign=regime_sign)
    return MassiveResult(
        levels=GEXLevels(gamma_flip=450.2, call_wall=455.1, put_wall=444.9),
        source_health=SourceHealth(name="massive", status=status, last_update=now, ttl_sec=60),
        raw_gex_result=raw_gex_result,
        flow_result=None,
    )


def test_bullish_verdict():
    analyzer = GEXAnalyzer()

    result = analyzer.analyze(
        _flashalpha_result(regime="positive"),
        _massive_result(),
    )

    assert result.bias.direction == "BULLISH"
    assert result.bias.confidence > 60
    assert result.bias.grade in {"A+", "A", "B"}
    assert result.flow.direction == "bullish"


def test_bearish_verdict():
    analyzer = GEXAnalyzer()

    result = analyzer.analyze(
        _flashalpha_result(regime="negative"),
        _massive_result(),
    )

    assert result.bias.direction == "BEARISH"
    assert result.bias.confidence > 60
    assert result.flow.direction == "bearish"


def test_neutral_on_low_confidence():
    analyzer = GEXAnalyzer()

    result = analyzer.analyze(
        _flashalpha_result(regime="positive", gamma_flip=450.0, call_wall=455.0, put_wall=445.0),
        _massive_result(gamma_flip=470.0, call_wall=475.0, put_wall=425.0),
    )

    assert result.bias.direction == "NEUTRAL"
    assert result.bias.confidence < 50
    assert result.bias.grade == "F"


def test_material_change_on_regime_flip():
    analyzer = GEXAnalyzer()

    first = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    second = analyzer.analyze(_flashalpha_result(regime="negative"), _massive_result())

    assert first.material_change is True
    assert second.material_change is True


def test_massive_regime_drives_analysis_when_flashalpha_is_down() -> None:
    analyzer = GEXAnalyzer()
    fa_result = _flashalpha_result(regime="neutral")
    fa_result = FlashAlphaResult(
        levels=fa_result.levels,
        dealer=fa_result.dealer,
        zero_dte=fa_result.zero_dte,
        source_health=SourceHealth(name="flashalpha", status="error", last_update=time.time(), ttl_sec=60),
        raw=fa_result.raw,
    )

    result = analyzer.analyze(fa_result, _massive_result_with_regime(regime_sign=1))

    assert result.bias.direction == "BULLISH"
    assert result.dealer.regime == "positive"


def test_massive_regime_change_counts_as_material_change_when_flashalpha_is_down() -> None:
    analyzer = GEXAnalyzer()
    fa_result = _flashalpha_result(regime="neutral")
    fa_result = FlashAlphaResult(
        levels=fa_result.levels,
        dealer=fa_result.dealer,
        zero_dte=fa_result.zero_dte,
        source_health=SourceHealth(name="flashalpha", status="error", last_update=time.time(), ttl_sec=60),
        raw=fa_result.raw,
    )

    first = analyzer.analyze(fa_result, _massive_result_with_regime(regime_sign=1))
    second = analyzer.analyze(fa_result, _massive_result_with_regime(regime_sign=-1))

    assert first.material_change is True
    assert second.material_change is True


def test_no_material_change_on_minor_fluctuation():
    analyzer = GEXAnalyzer()

    analyzer.analyze(_flashalpha_result(regime="positive", gamma_flip=450.0), _massive_result(gamma_flip=450.0))
    second = analyzer.analyze(
        _flashalpha_result(regime="positive", gamma_flip=451.0),
        _massive_result(gamma_flip=451.1),
    )

    assert second.material_change is False


def test_nq_conversion():
    analyzer = GEXAnalyzer(nq_qqq_ratio=38.5)

    result = analyzer.analyze(
        _flashalpha_result(regime="positive", gamma_flip=450.0, call_wall=455.0, put_wall=445.0),
        _massive_result(gamma_flip=450.0, call_wall=455.0, put_wall=445.0),
    )

    assert result.levels.gamma_flip == 17325.0
    assert result.levels.call_wall == 17517.5
    assert result.levels.put_wall == 17132.5


def test_dynamic_ratio_updates_from_live_spots():
    analyzer = GEXAnalyzer()

    result = analyzer.analyze(
        _flashalpha_result(regime="positive", summary_spot=21000.0),
        _massive_result(spot=512.0),
    )

    assert result.nq_qqq_ratio == 41.0156
    assert result.levels.gamma_flip == 18461.12


def test_vix_modifier_adjusts_confidence():
    analyzer = GEXAnalyzer()

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    boosted = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result(), vix=14.0)
    reduced = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result(), vix=36.0)

    assert boosted.bias.confidence == min(100, baseline.bias.confidence + 5)
    assert reduced.bias.confidence == max(0, baseline.bias.confidence - 20)


def test_positive_gamma_bullish_flow_boosts_confidence():
    analyzer = GEXAnalyzer()

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    boosted = analyzer.analyze(
        _flashalpha_result(regime="positive"),
        _massive_result(flow_result=FlowResult(net_direction=1, z_score=2.5, signed_premium_5m=2_500_000)),
    )

    assert boosted.bias.confidence == min(100, baseline.bias.confidence + 15)
    assert boosted.flow.direction == "bullish"
    assert boosted.flow.raw_direction == "bullish"
    assert boosted.flow.z_score == 2.5


def test_positive_gamma_bearish_flow_penalizes_confidence():
    analyzer = GEXAnalyzer()

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    reduced = analyzer.analyze(
        _flashalpha_result(regime="positive"),
        _massive_result(flow_result=FlowResult(net_direction=-1, z_score=0.2, signed_premium_5m=-1_500_000)),
    )

    assert reduced.bias.confidence == max(0, baseline.bias.confidence - 20)
    assert reduced.flow.raw_direction == "bearish"


def test_vanna_charm_alignment_boosts_confidence():
    analyzer = GEXAnalyzer()

    divergent = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    aligned_fa = _flashalpha_result(regime="positive")
    aligned_fa = FlashAlphaResult(
        levels=aligned_fa.levels,
        dealer=aligned_fa.dealer.model_copy(update={"net_chex": 50_000_000}),
        zero_dte=aligned_fa.zero_dte,
        source_health=aligned_fa.source_health,
        raw=aligned_fa.raw,
    )

    aligned = analyzer.analyze(aligned_fa, _massive_result())

    assert aligned.bias.confidence == min(100, divergent.bias.confidence + 10)


def test_zero_dte_penalties_reduce_confidence():
    analyzer = GEXAnalyzer()

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    elevated_zero_dte = _flashalpha_result(regime="positive")
    elevated_zero_dte = FlashAlphaResult(
        levels=elevated_zero_dte.levels,
        dealer=elevated_zero_dte.dealer,
        zero_dte=ZeroDTEState(
            gex_pct_of_total=0.65,
            pin_risk="high",
            gamma_acceleration=0.35,
        ),
        source_health=elevated_zero_dte.source_health,
        raw=elevated_zero_dte.raw,
    )

    reduced = analyzer.analyze(elevated_zero_dte, _massive_result())

    assert reduced.bias.confidence == max(0, baseline.bias.confidence - 14)
    assert reduced.zero_dte.pin_risk_score == 89


def test_massive_zero_dte_divergence_penalizes_confidence():
    analyzer = GEXAnalyzer()

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    divergent_massive = _massive_result(spot=512.0)
    divergent_massive.raw_gex_result = SimpleNamespace(
        spot=512.0,
        by_expiry={"0DTE": -150_000_000.0, "1-7": 300_000_000.0, "8-30": 200_000_000.0, "31+": 100_000_000.0},
    )

    reduced = analyzer.analyze(_flashalpha_result(regime="positive"), divergent_massive)

    assert reduced.bias.confidence == max(0, baseline.bias.confidence - 7)


def test_last_hour_charm_drift_adjusts_confidence():
    analyzer = GEXAnalyzer()
    analyzer._session_time_et = lambda: datetime(2026, 5, 29, 15, 15)

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    supportive_fa = _flashalpha_result(regime="positive")
    supportive_fa = FlashAlphaResult(
        levels=supportive_fa.levels,
        dealer=supportive_fa.dealer.model_copy(update={"net_chex": 50_000_000}),
        zero_dte=ZeroDTEState(gex_pct_of_total=0.3, pin_risk="low", gamma_acceleration=0.35),
        source_health=supportive_fa.source_health,
        raw=supportive_fa.raw,
    )

    boosted = analyzer.analyze(supportive_fa, _massive_result())

    assert boosted.bias.confidence == min(100, baseline.bias.confidence + 22)


def test_hmm_trending_reduces_confidence_by_15_percent():
    analyzer = GEXAnalyzer()

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result())
    reduced = analyzer.analyze(
        _flashalpha_result(regime="positive"),
        _massive_result(),
        hmm_state="TRENDING",
    )

    assert reduced.bias.confidence == int(baseline.bias.confidence * 0.85)


def test_hmm_chaotic_reduces_confidence_by_25_percent_and_can_fail_grade():
    analyzer = GEXAnalyzer()
    fa_result = _flashalpha_result(regime="positive", gamma_flip=450.0, call_wall=455.0, put_wall=445.0)
    massive_result = _massive_result(gamma_flip=470.0, call_wall=475.0, put_wall=425.0)

    baseline = analyzer.analyze(fa_result, massive_result)

    reduced = analyzer.analyze(fa_result, massive_result, hmm_state="CHAOTIC")

    assert reduced.bias.confidence == int(baseline.bias.confidence * 0.75)
    assert reduced.bias.grade == "F"


def test_po3_confirmation_adds_five_confidence_points():
    analyzer = GEXAnalyzer()

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result(), hmm_state="ABSORPTION_FRIENDLY")
    confirmed = analyzer.analyze(
        _flashalpha_result(regime="positive"),
        _massive_result(),
        hmm_state="ABSORPTION_FRIENDLY",
        po3_direction="BULLISH",
    )

    assert confirmed.bias.confidence == min(100, baseline.bias.confidence + 5)
    assert confirmed.po3_state == "BULLISH"


def test_po3_contradiction_subtracts_ten_confidence_points():
    analyzer = GEXAnalyzer()

    baseline = analyzer.analyze(_flashalpha_result(regime="positive"), _massive_result(), hmm_state="ABSORPTION_FRIENDLY")
    contradicted = analyzer.analyze(
        _flashalpha_result(regime="positive"),
        _massive_result(),
        hmm_state="ABSORPTION_FRIENDLY",
        po3_direction="BEARISH",
    )

    assert contradicted.bias.confidence == max(0, baseline.bias.confidence - 10)
    assert contradicted.po3_state == "BEARISH"


def test_low_conviction_forces_fail_grade_and_records_river_count():
    analyzer = GEXAnalyzer()

    result = analyzer.analyze(
        _flashalpha_result(regime="positive"),
        _massive_result(flow_result=FlowResult(net_direction=-1, z_score=2.5, signed_premium_5m=-2_500_000)),
        vanna_charm_net="headwind",
        dark_pool_direction="bearish",
        hmm_state="CHAOTIC",
    )

    assert result.bias.grade == "F"
    assert result.conviction_grade == "F"
    assert result.conviction_rivers < 3
