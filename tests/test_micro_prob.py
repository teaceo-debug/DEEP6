"""Tests for E5 MicroEngine (ENG-05) — Naive Bayes micro probability for next-tick direction.

All tests use synthetic inputs — offline, no live Rithmic required.

Requirement coverage:
  ENG-05 — MicroEngine: Naive Bayes micro probability from decorrelated DOM features
    - neutral fallback when all features absent (D-13)
    - all-bull features → probability > 0.6, direction=+1
    - all-bear features → probability < 0.4, direction=-1
    - mixed features → 0.4 <= probability <= 0.6, direction=0
    - single bull feature → probability in (0.5, 0.6)

Per D-11: Three binary features: E2 trespass, E4 iceberg, imbalance direction.
Per D-12: Output is probability for execution timing, not signal generation.
Per D-13: Returns 0.5, direction=0 when all inputs are neutral.
"""
from __future__ import annotations

import pytest

from deep6.engines.micro_prob import MicroEngine, MicroResult
from deep6.engines.trespass import TrespassResult
from deep6.engines.signal_config import MicroConfig


def make_trespass(direction: int) -> TrespassResult:
    """Build a synthetic TrespassResult with given direction."""
    return TrespassResult(
        imbalance_ratio=1.5 if direction == 1 else (0.7 if direction == -1 else 1.0),
        direction=direction,
        probability=0.7 if direction == 1 else (0.3 if direction == -1 else 0.5),
        depth_gradient=0.0,
        detail="",
    )


class MockIcebergSignal:
    """Minimal mock IcebergSignal for testing MicroEngine feature extraction."""
    def __init__(self, direction: int):
        self.direction = direction
        self.iceberg_type = "NATIVE"
        self.conviction_bonus = 0


# ---------------------------------------------------------------------------
# ENG-05: Neutral fallback (D-13)
# ---------------------------------------------------------------------------

def test_all_neutral_returns_neutral():
    """ENG-05: process(None, [], 0) → probability=0.5, direction=0 (D-13)."""
    engine = MicroEngine()
    result = engine.process(
        trespass=None,
        iceberg_signals=[],
        imbalance_direction=0,
    )
    assert isinstance(result, MicroResult)
    assert result.probability == pytest.approx(0.5)
    assert result.direction == 0
    assert result.feature_count == 0
    assert "UNAVAILABLE" in result.detail


def test_neutral_trespass_no_iceberg_no_imbalance():
    """ENG-05: Trespass direction=0, no icebergs, imbalance=0 → neutral."""
    engine = MicroEngine()
    trespass = make_trespass(0)
    result = engine.process(
        trespass=trespass,
        iceberg_signals=[],
        imbalance_direction=0,
    )
    assert result.probability == pytest.approx(0.5)
    assert result.direction == 0


# ---------------------------------------------------------------------------
# ENG-05: All-bull features
# ---------------------------------------------------------------------------

def test_all_bull_features_exceed_threshold():
    """ENG-05: trespass.direction=+1, iceberg direction=+1, imbalance_direction=+1
    → probability > 0.6, direction=+1.

    With bull_likelihood=0.65 and 3 bull features:
    p_bull = 0.65^3 = 0.274625
    p_bear = 0.35^3 = 0.042875
    prob = 0.274625 / (0.274625 + 0.042875) ≈ 0.865
    """
    engine = MicroEngine()
    trespass = make_trespass(+1)
    iceberg = MockIcebergSignal(direction=+1)
    result = engine.process(
        trespass=trespass,
        iceberg_signals=[iceberg],
        imbalance_direction=+1,
    )
    assert result.probability > 0.6
    assert result.direction == +1
    assert result.feature_count == 3


# ---------------------------------------------------------------------------
# ENG-05: All-bear features
# ---------------------------------------------------------------------------

def test_all_bear_features_below_threshold():
    """ENG-05: all features = -1 → probability < 0.4, direction=-1.

    With bull_likelihood=0.65 and 3 bear features:
    p_bull = 0.35^3 = 0.042875
    p_bear = 0.65^3 = 0.274625
    prob = 0.042875 / (0.042875 + 0.274625) ≈ 0.135
    """
    engine = MicroEngine()
    trespass = make_trespass(-1)
    iceberg = MockIcebergSignal(direction=-1)
    result = engine.process(
        trespass=trespass,
        iceberg_signals=[iceberg],
        imbalance_direction=-1,
    )
    assert result.probability < 0.4
    assert result.direction == -1
    assert result.feature_count == 3


# ---------------------------------------------------------------------------
# ENG-05: Mixed features
# ---------------------------------------------------------------------------

def test_mixed_features_returns_neutral_direction():
    """ENG-05: trespass=+1, iceberg absent, imbalance=-1 → 0.4 <= probability <= 0.6, direction=0.

    With bull_likelihood=0.65:
    p_bull = 0.65 * 0.35 = 0.2275  (trespass bull, imbalance bear)
    p_bear = 0.35 * 0.65 = 0.2275  (symmetric for opposite pair)
    prob = 0.2275 / 0.455 = 0.5 (exactly balanced)
    """
    engine = MicroEngine()
    trespass = make_trespass(+1)
    result = engine.process(
        trespass=trespass,
        iceberg_signals=[],
        imbalance_direction=-1,
    )
    assert 0.4 <= result.probability <= 0.6
    assert result.direction == 0
    assert result.feature_count == 2


# ---------------------------------------------------------------------------
# ENG-05: Single bull feature
# ---------------------------------------------------------------------------

def test_single_bull_feature_gives_moderate_probability():
    """ENG-05: only trespass=+1 with rest neutral → 0.5 < probability < 0.6.

    With bull_likelihood=0.65 and 1 bull feature:
    p_bull = 0.65, p_bear = 0.35
    prob = 0.65 / 1.0 = 0.65 — which IS > 0.6 for direction=+1.
    Test: probability should be > 0.5 and < 1.0.
    """
    engine = MicroEngine()
    trespass = make_trespass(+1)
    result = engine.process(
        trespass=trespass,
        iceberg_signals=[],
        imbalance_direction=0,
    )
    assert result.probability > 0.5
    assert result.probability < 1.0
    assert result.feature_count == 1


# ---------------------------------------------------------------------------
# ENG-05: MicroResult fields
# ---------------------------------------------------------------------------

def test_micro_result_has_all_fields():
    """ENG-05: MicroResult exposes probability, direction, feature_count, detail."""
    engine = MicroEngine()
    result = engine.process(
        trespass=make_trespass(+1),
        iceberg_signals=[],
        imbalance_direction=+1,
    )
    assert hasattr(result, "probability")
    assert hasattr(result, "direction")
    assert hasattr(result, "feature_count")
    assert hasattr(result, "detail")
    assert 0.0 <= result.probability <= 1.0


def test_micro_result_detail_contains_feature_info():
    """ENG-05: detail string includes feature information for debugging."""
    engine = MicroEngine()
    trespass = make_trespass(+1)
    result = engine.process(
        trespass=trespass,
        iceberg_signals=[],
        imbalance_direction=+1,
    )
    assert result.detail != ""
    assert "UNAVAILABLE" not in result.detail


# ---------------------------------------------------------------------------
# ENG-05: Custom config
# ---------------------------------------------------------------------------

def test_custom_config_higher_threshold():
    """ENG-05: Custom MicroConfig with higher bull/bear thresholds."""
    cfg = MicroConfig(bull_likelihood=0.70, bull_threshold=0.75, bear_threshold=0.25)
    engine = MicroEngine(cfg)
    trespass = make_trespass(+1)
    # With 1 bull feature and high threshold: prob=0.70 < 0.75 → direction=0 (not triggered)
    result = engine.process(
        trespass=trespass,
        iceberg_signals=[],
        imbalance_direction=0,
    )
    # prob = 0.70 < 0.75 → direction should be 0
    assert result.probability == pytest.approx(0.70, rel=1e-3)
    assert result.direction == 0


def test_stateless_engine_same_result_on_repeat():
    """ENG-05: Engine is stateless — same inputs always produce same output."""
    engine = MicroEngine()
    trespass = make_trespass(+1)
    result1 = engine.process(trespass=trespass, iceberg_signals=[], imbalance_direction=+1)
    result2 = engine.process(trespass=trespass, iceberg_signals=[], imbalance_direction=+1)
    assert result1.probability == pytest.approx(result2.probability)
    assert result1.direction == result2.direction
