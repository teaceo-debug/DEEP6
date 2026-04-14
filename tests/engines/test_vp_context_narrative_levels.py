"""Tests for narrative-Level persistence in E6VPContextEngine (Plan 15-02, T-15-02-01).

Covers D-06 (strength ≥ 0.4 threshold), D-07 (wick geometry for ABSORB),
D-31 (insertion point between detect_zones loop and update_zones call),
and backward-compat of VPContextResult.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pytest

from deep6.engines.absorption import AbsorptionSignal, AbsorptionType
from deep6.engines.exhaustion import ExhaustionSignal, ExhaustionType
from deep6.engines.level import LevelKind, LevelState
from deep6.engines.narrative import NarrativeResult, NarrativeType
from deep6.engines.vp_context_engine import E6VPContextEngine, VPContextResult
from deep6.state.footprint import FootprintBar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _bar(*, o=100.0, h=105.0, l=99.0, c=101.0) -> FootprintBar:
    """Minimal FootprintBar for narrative-Level tests."""
    return FootprintBar(
        open=o, high=h, low=l, close=c,
        total_vol=1000, bar_range=h - l, poc_price=(h + l) / 2.0,
    )


def _absorption(strength: float, *, direction: int = +1, wick: str = "upper", price: float = 101.0) -> AbsorptionSignal:
    return AbsorptionSignal(
        bar_type=AbsorptionType.CLASSIC,
        direction=direction,
        price=price,
        wick=wick,
        strength=strength,
        wick_pct=60.0,
        delta_ratio=0.2,
        detail="test absorption",
    )


def _exhaustion(strength: float, *, direction: int = +1, price: float = 100.0) -> ExhaustionSignal:
    return ExhaustionSignal(
        bar_type=ExhaustionType.FADING_MOMENTUM,
        direction=direction,
        price=price,
        strength=strength,
        detail="test exhaustion",
    )


def _narrative(
    *,
    bar_type: NarrativeType = NarrativeType.ABSORPTION,
    absorption: Optional[list[AbsorptionSignal]] = None,
    exhaustion: Optional[list[ExhaustionSignal]] = None,
    direction: int = +1,
    strength: float = 0.7,
    price: float = 101.0,
) -> NarrativeResult:
    return NarrativeResult(
        bar_type=bar_type,
        direction=direction,
        label="TEST",
        strength=strength,
        price=price,
        absorption=absorption or [],
        exhaustion=exhaustion or [],
        imbalances=[],
        all_signals_count=len(absorption or []) + len(exhaustion or []),
    )


def _engine() -> E6VPContextEngine:
    """E6VPContextEngine with dummy GEX key — GEX fetch never invoked."""
    return E6VPContextEngine(gex_api_key="test-key")


# ---------------------------------------------------------------------------
# D-06: strength threshold
# ---------------------------------------------------------------------------

def test_absorption_strength_below_threshold_not_persisted() -> None:
    """AbsorptionSignal.strength=0.35 < 0.4 → registry has no ABSORB Levels."""
    eng = _engine()
    nar = _narrative(absorption=[_absorption(0.35)])
    eng.process(_bar(), narrative_result=nar)
    assert eng.registry.query_by_kind(LevelKind.ABSORB) == []


def test_absorption_strength_above_threshold_persisted() -> None:
    """AbsorptionSignal.strength=0.6 → one ABSORB Level in registry."""
    eng = _engine()
    nar = _narrative(absorption=[_absorption(0.6, wick="upper")])
    eng.process(_bar(o=100.0, h=105.0, l=99.0, c=101.0), narrative_result=nar)
    abs_levels = eng.registry.query_by_kind(LevelKind.ABSORB)
    assert len(abs_levels) == 1
    assert abs_levels[0].direction == +1


# ---------------------------------------------------------------------------
# D-07: wick geometry
# ---------------------------------------------------------------------------

def test_absorb_upper_wick_geometry() -> None:
    """UW absorption on bar(o=100,h=105,l=99,c=101):
    body_top=101; price_top=105, price_bot=101."""
    eng = _engine()
    sig = _absorption(0.7, wick="upper", direction=-1, price=104.0)
    nar = _narrative(absorption=[sig], direction=-1)
    eng.process(_bar(o=100.0, h=105.0, l=99.0, c=101.0), narrative_result=nar)
    lv = eng.registry.query_by_kind(LevelKind.ABSORB)[0]
    assert lv.price_top == pytest.approx(105.0)
    assert lv.price_bot == pytest.approx(101.0)


def test_absorb_lower_wick_geometry() -> None:
    """LW absorption on bar(o=101,h=102,l=95,c=100):
    body_bot=100; price_top=100, price_bot=95."""
    eng = _engine()
    sig = _absorption(0.7, wick="lower", direction=+1, price=96.0)
    nar = _narrative(absorption=[sig], direction=+1)
    eng.process(_bar(o=101.0, h=102.0, l=95.0, c=100.0), narrative_result=nar)
    lv = eng.registry.query_by_kind(LevelKind.ABSORB)[0]
    assert lv.price_top == pytest.approx(100.0)
    assert lv.price_bot == pytest.approx(95.0)


# ---------------------------------------------------------------------------
# All four narrative kinds
# ---------------------------------------------------------------------------

def test_all_four_narrative_kinds_persist() -> None:
    """Synthetic result with above-threshold absorption+exhaustion plus MOMENTUM
    narrative bar_type (body) and direction → MOMENTUM Level created."""
    eng = _engine()
    nar = _narrative(
        bar_type=NarrativeType.MOMENTUM,
        absorption=[_absorption(0.7, wick="upper", direction=-1)],
        exhaustion=[_exhaustion(0.5, direction=-1)],
        direction=-1,
        strength=0.5,
    )
    eng.process(_bar(o=100.0, h=105.0, l=99.0, c=101.0), narrative_result=nar)
    assert len(eng.registry.query_by_kind(LevelKind.ABSORB)) == 1
    assert len(eng.registry.query_by_kind(LevelKind.EXHAUST)) == 1
    assert len(eng.registry.query_by_kind(LevelKind.MOMENTUM)) == 1


def test_rejection_narrative_persisted() -> None:
    eng = _engine()
    nar = _narrative(
        bar_type=NarrativeType.REJECTION,
        direction=-1,
        strength=0.6,
    )
    eng.process(_bar(o=100.0, h=105.0, l=99.0, c=101.0), narrative_result=nar)
    assert len(eng.registry.query_by_kind(LevelKind.REJECTION)) == 1


def test_momentum_narrative_strength_below_threshold_not_persisted() -> None:
    """MOMENTUM bar_type with strength=0.3 < 0.4 → no MOMENTUM Level."""
    eng = _engine()
    nar = _narrative(
        bar_type=NarrativeType.MOMENTUM,
        strength=0.3,
        direction=+1,
    )
    eng.process(_bar(), narrative_result=nar)
    assert eng.registry.query_by_kind(LevelKind.MOMENTUM) == []


# ---------------------------------------------------------------------------
# Backward compat
# ---------------------------------------------------------------------------

def test_vpcontext_result_backward_compatible() -> None:
    """process() without narrative_result still returns full VPContextResult."""
    eng = _engine()
    res = eng.process(_bar())
    assert isinstance(res, VPContextResult)
    assert isinstance(res.poc_signals, list)
    assert isinstance(res.active_zones, list)
    assert isinstance(res.zone_events, list)
    # gex_signal may be None (no fetch), confluence may be None — both OK
    assert hasattr(res, "poc_migration")
    assert hasattr(res, "ml_quality")


def test_process_without_narrative_no_narrative_levels() -> None:
    """When narrative_result is omitted, no narrative-kind Levels are added."""
    eng = _engine()
    eng.process(_bar())
    assert eng.registry.query_by_kind(LevelKind.ABSORB) == []
    assert eng.registry.query_by_kind(LevelKind.EXHAUST) == []
    assert eng.registry.query_by_kind(LevelKind.MOMENTUM) == []
    assert eng.registry.query_by_kind(LevelKind.REJECTION) == []
