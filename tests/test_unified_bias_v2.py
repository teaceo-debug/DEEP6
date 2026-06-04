"""Characterization tests for the legacy v2 UnifiedBiasEngine."""

from __future__ import annotations

import pytest

from deep6.bias_engine.unified_bias import (
    TradeGrade,
    UnifiedBiasEngine,
    _alignment_confidence,
    _derive_trade_setup,
    _score_to_grade,
)


@pytest.fixture
def engine() -> UnifiedBiasEngine:
    return UnifiedBiasEngine()


def test_compute_all_bullish(engine: UnifiedBiasEngine):
    """All available bullish sources produce max score, A+, and LONG setup."""
    result = engine.compute(
        po3_score=100.0,
        pd_array_score=100.0,
        mtf_score=100.0,
        gex_score=100.0,
        gex_available=True,
        orderflow_score=100.0,
        news_score=100.0,
        ai_score=100.0,
        ai_available=True,
        current_price=20000.0,
        pd_high=20040.0,
        pw_high=20080.0,
        nearest_fvg_high=19995.0,
        nearest_fvg_low=19985.0,
        atr=20.0,
        session_phase="DISTRIBUTION",
        judas_status="BULL_CONFIRMED",
    )

    assert result.score == 100.0
    assert result.direction == "STRONG_BULL"
    assert result.confidence == 1.0
    assert result.grade == TradeGrade.A_PLUS
    assert result.setup is not None
    assert result.setup.direction == "LONG"
    assert result.setup.entry_zone_high == 19995.0
    assert result.setup.entry_zone_low == 19985.0
    assert result.setup.stop_loss == 19975.0
    assert result.setup.target_1 == 20040.0
    assert result.setup.target_2 == 20080.0
    assert "Judas Bull confirmed" in result.setup.entry_trigger


def test_compute_all_bearish(engine: UnifiedBiasEngine):
    """All available bearish sources produce max negative score and SHORT setup."""
    result = engine.compute(
        po3_score=-100.0,
        pd_array_score=-100.0,
        mtf_score=-100.0,
        gex_score=-100.0,
        gex_available=True,
        orderflow_score=-100.0,
        news_score=-100.0,
        ai_score=-100.0,
        ai_available=True,
        current_price=20000.0,
        pd_low=19940.0,
        pw_low=19880.0,
        nearest_fvg_high=20020.0,
        nearest_fvg_low=20010.0,
        atr=20.0,
        session_phase="MANIPULATION",
        judas_status="BEAR_CONFIRMED",
    )

    assert result.score == -100.0
    assert result.direction == "STRONG_BEAR"
    assert result.confidence == 1.0
    assert result.grade == TradeGrade.A_PLUS
    assert result.setup is not None
    assert result.setup.direction == "SHORT"
    assert result.setup.entry_zone_high == 20020.0
    assert result.setup.entry_zone_low == 20010.0
    assert result.setup.stop_loss == 20030.0
    assert result.setup.target_1 == 19940.0
    assert result.setup.target_2 == 19880.0
    assert result.setup.session_window == "Wait — manipulation phase, no entry yet"
    assert "Judas Bear confirmed" in result.setup.entry_trigger


def test_compute_mixed(engine: UnifiedBiasEngine):
    """Mixed sources can leave direction bullish but confidence too weak to produce a setup."""
    result = engine.compute(
        po3_score=100.0,
        pd_array_score=50.0,
        mtf_score=25.0,
        gex_score=-50.0,
        gex_available=True,
        orderflow_score=-25.0,
        news_score=0.0,
        ai_score=0.0,
        ai_available=True,
        current_price=20000.0,
        atr=20.0,
    )

    assert result.score == 30.0
    assert result.direction == "BULL"
    assert result.confidence == pytest.approx(0.457, rel=0, abs=1e-3)
    assert result.grade == TradeGrade.C
    assert result.setup is None


def test_compute_unavailable_sources_dilute_score(engine: UnifiedBiasEngine):
    """Unavailable sources are zeroed but still remain in the denominator."""
    result = engine.compute(
        po3_score=100.0,
        pd_array_score=100.0,
        mtf_score=100.0,
        gex_score=100.0,
        gex_available=False,
        orderflow_score=100.0,
        orderflow_available=False,
        news_score=100.0,
        news_available=False,
        ai_score=100.0,
        ai_available=False,
    )

    assert result.score == 65.0
    assert result.direction == "STRONG_BULL"
    assert result.confidence == 1.0
    unavailable = {component.name: component for component in result.components if not component.available}
    assert unavailable["GEX/Flow"].raw_score == 0.0
    assert unavailable["Order Flow"].weighted == 0.0
    assert unavailable["News/Macro"].raw_score == 0.0
    assert unavailable["Claude AI"].raw_score == 0.0


def test_compute_macro_blackout_is_context_only(engine: UnifiedBiasEngine):
    """macro_blackout is passed through to the output and does not alter v2 scoring."""
    base = dict(
        po3_score=80.0,
        pd_array_score=40.0,
        mtf_score=20.0,
        gex_score=0.0,
        gex_available=True,
        orderflow_score=10.0,
        news_score=15.0,
        ai_score=30.0,
        ai_available=True,
        current_price=20000.0,
        pd_high=20030.0,
        pw_high=20060.0,
        atr=15.0,
    )

    normal = engine.compute(**base, macro_blackout=False)
    blackout = engine.compute(**base, macro_blackout=True)

    assert normal.score == blackout.score
    assert normal.direction == blackout.direction
    assert normal.grade == blackout.grade
    assert normal.confidence == blackout.confidence
    assert normal.macro_blackout is False
    assert blackout.macro_blackout is True


def test_compute_extreme_divergence_warning(engine: UnifiedBiasEngine):
    """Available scores with >120 point range emit the extreme divergence warning."""
    result = engine.compute(
        po3_score=100.0,
        pd_array_score=100.0,
        mtf_score=100.0,
        gex_score=-30.0,
        gex_available=True,
        orderflow_score=-30.0,
        news_score=-30.0,
        ai_score=-30.0,
        ai_available=True,
    )

    assert result.divergence_warning == "Extreme signal divergence (130pts) — reduce size"


def test_compute_moderate_divergence_warning(engine: UnifiedBiasEngine):
    """Available scores with >80 point range emit the moderate divergence warning."""
    result = engine.compute(
        po3_score=50.0,
        pd_array_score=50.0,
        mtf_score=50.0,
        gex_score=-40.0,
        gex_available=True,
        orderflow_score=-40.0,
        news_score=-40.0,
        ai_score=-40.0,
        ai_available=True,
    )

    assert result.divergence_warning == "Moderate divergence (90pts) — half size"


def test_score_to_grade_strong_bull():
    assert _score_to_grade(0.85) == TradeGrade.A_PLUS


def test_score_to_grade_lean_bull():
    assert _score_to_grade(0.70) == TradeGrade.A


def test_score_to_grade_neutral():
    assert _score_to_grade(0.55) == TradeGrade.B


def test_score_to_grade_lean_bear():
    assert _score_to_grade(0.40) == TradeGrade.C


def test_score_to_grade_strong_bear():
    assert _score_to_grade(0.399) == TradeGrade.F


def test_alignment_confidence_perfect():
    assert _alignment_confidence([100.0, 100.0, 100.0]) == 1.0


def test_alignment_confidence_split():
    assert _alignment_confidence([100.0, -100.0]) == 0.0


def test_alignment_confidence_empty():
    assert _alignment_confidence([]) == 0.0


def test_derive_setup_long():
    """Bullish setup uses FVG inputs, prior highs, and Distribution window text."""
    setup = _derive_trade_setup(
        direction="BULL",
        score=30.0,
        price=20000.0,
        pd_high=20040.0,
        pd_low=19940.0,
        pw_high=20080.0,
        pw_low=19880.0,
        fvg_high=19995.0,
        fvg_low=19985.0,
        atr=20.0,
        phase="DISTRIBUTION",
        judas_status="BULL_CONFIRMED",
    )

    assert setup.direction == "LONG"
    assert setup.entry_zone_high == 19995.0
    assert setup.entry_zone_low == 19985.0
    assert setup.stop_loss == 19975.0
    assert setup.target_1 == 20040.0
    assert setup.target_2 == 20080.0
    assert setup.risk_pts == 10.0
    assert setup.reward_pts == 45.0
    assert setup.rrr == 4.5
    assert setup.session_window == "07:00–10:00 ET NY AM killzone — execute now"


def test_derive_setup_short():
    """Bearish setup mirrors long logic around premium entry and lower targets."""
    setup = _derive_trade_setup(
        direction="STRONG_BEAR",
        score=-80.0,
        price=20000.0,
        pd_high=20040.0,
        pd_low=19940.0,
        pw_high=20080.0,
        pw_low=19880.0,
        fvg_high=20020.0,
        fvg_low=20010.0,
        atr=20.0,
        phase="ACCUMULATION",
        judas_status="BEAR_CONFIRMED",
    )

    assert setup.direction == "SHORT"
    assert setup.entry_zone_high == 20020.0
    assert setup.entry_zone_low == 20010.0
    assert setup.stop_loss == 20030.0
    assert setup.target_1 == 19940.0
    assert setup.target_2 == 19880.0
    assert setup.risk_pts == 10.0
    assert setup.reward_pts == 70.0
    assert setup.rrr == 7.0
    assert setup.session_window == "Wait for London open (00:00 ET)"


def test_derive_setup_wait():
    """Non-directional bias returns a WAIT setup with only the trigger message."""
    setup = _derive_trade_setup(
        direction="NEUTRAL",
        score=0.0,
        price=20000.0,
        pd_high=20040.0,
        pd_low=19940.0,
        pw_high=20080.0,
        pw_low=19880.0,
        fvg_high=0.0,
        fvg_low=0.0,
        atr=20.0,
        phase="DISTRIBUTION",
        judas_status="",
    )

    assert setup.direction == "WAIT"
    assert setup.entry_zone_high is None
    assert setup.entry_trigger == "Await clearer bias alignment"
