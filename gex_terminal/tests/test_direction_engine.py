"""Tests for the unified LONG/SHORT direction engine."""
from __future__ import annotations

from gex_terminal.engine.direction_engine import DirectionEngine


def test_direction_engine_returns_long_on_aligned_bullish_inputs() -> None:
    signal = DirectionEngine().compute(
        gex_regime="positive",
        gex_confidence=82,
        flow_direction="bullish",
        flow_z_score=2.4,
        dp_bias="bullish",
        dp_conviction=0.85,
        conviction_grade="A",
        conviction_rivers=4,
        grid_buy=7,
        grid_sell=2,
        vex_chex_aligned=True,
        vex_direction="tailwind",
        hmm_state="ABSORPTION_FRIENDLY",
        po3_direction="BULLISH",
        market_tide="BULLISH",
        price_above_flip=True,
    )

    assert signal.direction == "LONG"
    assert signal.confidence >= 70
    assert signal.signals_long > signal.signals_short


def test_direction_engine_returns_short_on_aligned_bearish_inputs() -> None:
    signal = DirectionEngine().compute(
        gex_regime="negative",
        gex_confidence=78,
        flow_direction="bearish",
        flow_z_score=2.1,
        dp_bias="bearish",
        dp_conviction=0.8,
        conviction_grade="A",
        conviction_rivers=5,
        grid_buy=1,
        grid_sell=6,
        vex_chex_aligned=True,
        vex_direction="headwind",
        hmm_state="ABSORPTION_FRIENDLY",
        po3_direction="BEARISH",
        market_tide="BEARISH",
        price_above_flip=False,
    )

    assert signal.direction == "SHORT"
    assert signal.confidence >= 70
    assert signal.signals_short > signal.signals_long


def test_direction_engine_returns_flat_when_confidence_is_gated_down() -> None:
    signal = DirectionEngine().compute(
        gex_regime="positive",
        gex_confidence=35,
        flow_direction="bullish",
        dp_bias="neutral",
        conviction_grade="F",
        conviction_rivers=1,
        grid_buy=3,
        grid_sell=0,
        hmm_state="CHAOTIC",
        market_tide="MIXED",
    )

    assert signal.direction == "FLAT"
    assert signal.confidence < 30
