"""Tests for PositioningInterpreter — deterministic FlashAlpha → BiasResult."""
from __future__ import annotations

import pytest

from gexdoctor.monitor.interpreter import PositioningInterpreter
from gexdoctor.monitor.schemas import (
    BiasResult,
    FADealerRisk,
    FAFeedQuality,
    FAHigherOrder,
    FAOISimulator,
    FAPinData,
    FARegime,
    FAVolContext,
    FlashAlphaSnapshot,
)


def _snap(
    price: float = 22100.0,
    gex_sign: str = "positive",
    gamma_flip: float = 22000.0,
    call_wall: float | None = 22300.0,
    put_wall: float | None = 21800.0,
    flow_direction: str = "neutral",
    flow_gex_pct_shift: float | None = None,
    pin_risk: float | None = None,
    dte: int | None = 5,
    oi_delta_confidence: float | None = 0.6,
    session_phase: str = "intraday",
    vex_sign: str | None = None,
    vix: float | None = None,
    net_dex: float | None = None,
    missing_fields: list[str] | None = None,
) -> FlashAlphaSnapshot:
    """Build a minimal valid FlashAlphaSnapshot for testing."""
    return FlashAlphaSnapshot(
        timestamp="2026-05-28T14:30:00Z",
        symbol="NQ",
        underlying_price=price,
        session_phase=session_phase,
        dte=dte,
        regime=FARegime(
            net_gex=1_000_000_000.0 if gex_sign == "positive" else -500_000_000.0,
            gex_sign=gex_sign,
            gamma_flip=gamma_flip,
            call_wall=call_wall,
            put_wall=put_wall,
            net_dex=net_dex,
        ),
        dealer_risk=FADealerRisk(
            flow_direction=flow_direction,
            flow_gex_pct_shift=flow_gex_pct_shift,
        ),
        pin=FAPinData(pin_risk=pin_risk),
        oi_simulator=FAOISimulator(oi_delta_confidence=oi_delta_confidence),
        higher_order=FAHigherOrder(vex_sign=vex_sign),
        vol_context=FAVolContext(vix=vix),
        feed_quality=FAFeedQuality(missing_fields=missing_fields or []),
    )


@pytest.fixture
def interp() -> PositioningInterpreter:
    return PositioningInterpreter()


# --- Step 1: Regime label ---


def test_positive_gex_label(interp: PositioningInterpreter):
    result = interp.interpret(_snap(gex_sign="positive"))
    assert "long gamma" in result.regime


def test_negative_gex_label(interp: PositioningInterpreter):
    result = interp.interpret(_snap(gex_sign="negative"))
    assert "short gamma" in result.regime


# --- Step 2: Price zone ---


def test_price_above_call_wall_zone(interp: PositioningInterpreter):
    result = interp.interpret(_snap(price=22350.0, call_wall=22300.0))
    assert result.price_zone == "above_call_wall"


def test_price_in_long_gamma_upper_zone(interp: PositioningInterpreter):
    # flip < price < call_wall, gex=positive
    result = interp.interpret(
        _snap(price=22100.0, gamma_flip=22000.0, call_wall=22300.0, gex_sign="positive")
    )
    assert result.price_zone == "long_gamma_upper"


def test_price_below_put_wall_zone(interp: PositioningInterpreter):
    result = interp.interpret(_snap(price=21750.0, put_wall=21800.0))
    assert result.price_zone == "below_put_wall"


# --- Step 3: Regime playbook ---


def test_regime_playbook_positive_amplifying(interp: PositioningInterpreter):
    result = interp.interpret(
        _snap(gex_sign="positive", flow_direction="amplifying")
    )
    # State should be range_tightening; play mentions "long gamma intensifying"
    assert "long gamma intensifying" in result.lean or "range" in result.lean.lower()


def test_regime_playbook_negative_amplifying(interp: PositioningInterpreter):
    result = interp.interpret(
        _snap(gex_sign="negative", flow_direction="amplifying", price=21900.0, gamma_flip=22000.0)
    )
    # State should be trend_expanding; play mentions "short gamma intensifying"
    assert "short gamma intensifying" in result.lean or "trend" in result.lean.lower()


def test_regime_flip_playbook(interp: PositioningInterpreter):
    result = interp.interpret(
        _snap(flow_direction="regime flip")
    )
    # Regime flip play mentions "GEX sign flipped" or "behavior is changing"
    assert "flipped" in result.lean.lower() or "changing" in result.lean.lower()


# --- Step 5: Heuristics ---


def test_pin_heuristic_fires(interp: PositioningInterpreter):
    result = interp.interpret(_snap(pin_risk=80.0, dte=0))
    assert any("pin_into_expiry" in c for c in result.caveats)


def test_stale_anchor_fires(interp: PositioningInterpreter):
    result = interp.interpret(_snap(flow_gex_pct_shift=0.15))
    assert any("stale_anchor" in c for c in result.caveats)


def test_low_confidence_heuristic_fires(interp: PositioningInterpreter):
    result = interp.interpret(_snap(oi_delta_confidence=0.2))
    assert any("low_confidence" in c for c in result.caveats)


def test_flip_proximity_fires(interp: PositioningInterpreter):
    # Price within 5pts of gamma_flip
    result = interp.interpret(_snap(price=22003.0, gamma_flip=22000.0))
    assert any("flip_proximity" in c for c in result.caveats)


# --- Step 6: Bias direction ---


def test_bias_near_flip_is_neutral(interp: PositioningInterpreter):
    result = interp.interpret(_snap(price=22002.0, gamma_flip=22000.0))
    assert result.direction == "neutral"


def test_bias_long_gamma_upper_amplifying_is_bearish(interp: PositioningInterpreter):
    # Above flip, positive GEX, amplifying -> range tightening -> bearish (caps/mean-revert)
    result = interp.interpret(
        _snap(
            price=22100.0,
            gamma_flip=22000.0,
            call_wall=22300.0,
            gex_sign="positive",
            flow_direction="amplifying",
        )
    )
    assert result.direction == "bearish"
