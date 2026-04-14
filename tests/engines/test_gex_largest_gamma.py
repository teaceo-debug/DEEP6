"""Tests for GexLevels.largest_gamma_strike (D-28) + zero_gamma alias (D-29).

Plan 15-01, T-15-01-03.
"""
from __future__ import annotations

import pytest

from deep6.engines.gex import GexEngine, GexLevels, GexRegime
from deep6.engines.level import LevelKind
from deep6.engines.level_factory import from_gex


# ---------------------------------------------------------------------------
# D-29: zero_gamma alias
# ---------------------------------------------------------------------------

def test_zero_gamma_alias_returns_gamma_flip() -> None:
    glv = GexLevels(gamma_flip=445.25, regime=GexRegime.NEUTRAL)
    assert glv.zero_gamma == 445.25
    assert glv.zero_gamma == glv.gamma_flip


def test_zero_gamma_alias_zero_when_flip_unset() -> None:
    glv = GexLevels(regime=GexRegime.NEUTRAL)
    assert glv.zero_gamma == 0.0


# ---------------------------------------------------------------------------
# D-28: engine populates largest_gamma_strike from raw call γ×OI peak
# ---------------------------------------------------------------------------

def _contract(strike: float, kind: str, gamma: float, oi: int) -> dict:
    return {
        "details": {"strike_price": strike, "contract_type": kind},
        "greeks": {"gamma": gamma},
        "open_interest": oi,
        "day": {},
    }


def test_gex_largest_gamma_strike_populated() -> None:
    """Chain with a dominant call γ×OI at strike 450 + heavier put at 440 →
    largest_gamma_strike == 450 (raw call peak), put_wall == 440.
    """
    eng = GexEngine(api_key="test")
    chain = [
        # Call at 450 with raw γ×OI peak
        _contract(450.0, "call", gamma=0.05, oi=5000),
        # Call at 445 smaller
        _contract(445.0, "call", gamma=0.04, oi=2000),
        # Put at 440 heavier than any call
        _contract(440.0, "put", gamma=0.05, oi=8000),
        # Another put at 450 — nets against call, but doesn't affect raw call peak
        _contract(450.0, "put", gamma=0.05, oi=8000),
    ]
    levels = eng._compute_gex(chain, spot=445.0)

    # Raw call peak is at 450 (largest γ×OI on a call contract, pre-netting)
    assert levels.largest_gamma_strike == 450.0
    # call_wall is also the raw call peak by construction → same value
    assert levels.call_wall == 450.0
    # put_wall is the raw put peak → 440
    assert levels.put_wall == 440.0


def test_gex_largest_gamma_differs_from_hvl_when_puts_dominate_at_different_strike() -> None:
    """If the strike with peak |net GEX| is different from peak raw call γ×OI,
    largest_gamma_strike (call peak) and hvl (|net| peak) must differ.
    """
    eng = GexEngine(api_key="test")
    chain = [
        # Raw call peak at 460 (moderate)
        _contract(460.0, "call", gamma=0.04, oi=5000),
        # Very heavy negative net at 440 (big puts, no calls)
        _contract(440.0, "put", gamma=0.06, oi=10000),
    ]
    levels = eng._compute_gex(chain, spot=450.0)
    assert levels.largest_gamma_strike == 460.0  # raw call peak
    assert levels.hvl == 440.0                   # |net| peak
    assert levels.largest_gamma_strike != levels.hvl


# ---------------------------------------------------------------------------
# Factory emits LARGEST_GAMMA + ZERO_GAMMA
# ---------------------------------------------------------------------------

def test_from_gex_emits_largest_gamma_level_when_set() -> None:
    glv = GexLevels(
        call_wall=450.0, put_wall=440.0, gamma_flip=445.0, hvl=448.0,
        largest_gamma_strike=450.0, regime=GexRegime.POSITIVE_DAMPENING,
    )
    levels = from_gex(glv)
    kinds = {lv.kind: lv for lv in levels}
    assert LevelKind.LARGEST_GAMMA in kinds
    assert kinds[LevelKind.LARGEST_GAMMA].price_top == 450.0
    assert kinds[LevelKind.LARGEST_GAMMA].price_bot == 450.0


def test_from_gex_emits_zero_gamma_level() -> None:
    glv = GexLevels(gamma_flip=445.0, regime=GexRegime.NEUTRAL)
    levels = from_gex(glv)
    zero_gamma = [lv for lv in levels if lv.kind == LevelKind.ZERO_GAMMA]
    assert len(zero_gamma) == 1
    assert zero_gamma[0].price_top == 445.0


def test_from_gex_skips_largest_gamma_when_zero() -> None:
    glv = GexLevels(call_wall=450.0, regime=GexRegime.NEUTRAL)  # largest_gamma_strike defaults 0
    levels = from_gex(glv)
    kinds = {lv.kind for lv in levels}
    assert LevelKind.CALL_WALL in kinds
    assert LevelKind.LARGEST_GAMMA not in kinds


# ---------------------------------------------------------------------------
# Regression: existing GEX fields unchanged
# ---------------------------------------------------------------------------

def test_existing_gex_field_defaults_unchanged() -> None:
    """Adding largest_gamma_strike must not shift defaults of other fields."""
    glv = GexLevels()
    assert glv.call_wall == 0.0
    assert glv.put_wall == 0.0
    assert glv.gamma_flip == 0.0
    assert glv.hvl == 0.0
    assert glv.largest_gamma_strike == 0.0
    assert glv.regime == GexRegime.NEUTRAL
