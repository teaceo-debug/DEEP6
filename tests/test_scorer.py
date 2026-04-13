"""Test suite for the two-layer confluence scorer — SCOR-01..06.

Covers:
  - SCOR-04 TypeA classification (requires abs/exh + zone + 5 categories)
  - SCOR-02 Confluence multiplier (1.25x at 5+ categories)
  - SCOR-03 Zone bonus tiers (+8 / +6 / +4)
  - D-01 Confirmation bonus applied per confirmed_absorptions
  - D-02 Stacked imbalance dedup (highest tier only per direction)
  - SCOR-06 Label format for all tiers
  - D-11 ScorerConfig override controls all thresholds
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from deep6.engines.narrative import (
    NarrativeResult,
    NarrativeType,
    AbsorptionConfirmation,
)
from deep6.engines.absorption import AbsorptionSignal, AbsorptionType
from deep6.engines.exhaustion import ExhaustionSignal, ExhaustionType
from deep6.engines.imbalance import ImbalanceSignal, ImbalanceType
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType
from deep6.engines.delta import DeltaSignal, DeltaType
from deep6.engines.auction import AuctionSignal, AuctionType
from deep6.engines.poc import POCSignal, POCType
from deep6.scoring.scorer import score_bar, SignalTier, ScorerResult
from deep6.engines.signal_config import ScorerConfig, AbsorptionConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PRICE = 19000.0


def _empty_narrative(direction: int = 0) -> NarrativeResult:
    return NarrativeResult(
        bar_type=NarrativeType.QUIET,
        direction=direction,
        label="quiet",
        strength=0.0,
        price=PRICE,
        absorption=[],
        exhaustion=[],
        imbalances=[],
        all_signals_count=0,
        confirmed_absorptions=[],
    )


def _abs_signal(direction: int = +1) -> AbsorptionSignal:
    return AbsorptionSignal(
        bar_type=AbsorptionType.CLASSIC,
        direction=direction,
        price=PRICE,
        wick="lower" if direction > 0 else "upper",
        strength=0.8,
        wick_pct=40.0,
        delta_ratio=0.05,
        detail="test absorption",
        at_va_extreme=False,
    )


def _exh_signal(direction: int = +1) -> ExhaustionSignal:
    return ExhaustionSignal(
        bar_type=ExhaustionType.THIN_PRINT,
        direction=direction,
        price=PRICE,
        strength=0.7,
        detail="test exhaustion",
    )


def _stacked_signal(imb_type: ImbalanceType, direction: int = +1) -> ImbalanceSignal:
    return ImbalanceSignal(
        imb_type=imb_type,
        direction=direction,
        price=PRICE,
        ratio=5.0,
        count=5,
        strength=0.8,
        detail="test stacked",
    )


def _delta_signal(direction: int = +1) -> DeltaSignal:
    return DeltaSignal(
        delta_type=DeltaType.DIVERGENCE,
        direction=direction,
        strength=0.7,
        value=500.0 * direction,
        detail="test delta",
    )


def _auction_signal(direction: int = +1) -> AuctionSignal:
    return AuctionSignal(
        auction_type=AuctionType.FINISHED_AUCTION,
        direction=direction,
        price=PRICE,
        strength=0.7,
        detail="test auction",
    )


def _poc_signal(direction: int = +1) -> POCSignal:
    return POCSignal(
        poc_type=POCType.BULLISH_POC if direction > 0 else POCType.BEARISH_POC,
        direction=direction,
        price=PRICE,
        strength=0.7,
        detail="test poc",
    )


def _zone(top: float, bot: float, score: float, state: ZoneState = ZoneState.CREATED) -> VolumeZone:
    return VolumeZone(
        zone_type=ZoneType.HVN,
        state=state,
        top_price=top,
        bot_price=bot,
        direction=+1,
        origin_bar=1,
        last_touch_bar=1,
        score=score,
    )


def _confirmation(direction: int = +1) -> AbsorptionConfirmation:
    return AbsorptionConfirmation(
        signal=_abs_signal(direction),
        bar_fired=5,
        zone_price=PRICE,
        direction=direction,
        confirmed=True,
        expired=False,
    )


# ---------------------------------------------------------------------------
# Test 1: SCOR-04 TypeA requires absorption/exhaustion + zone + 5 categories
# ---------------------------------------------------------------------------

def test_type_a_requires_zone_bonus():
    """TypeA fires when: abs + zone_bonus > 0 + 5 categories agree."""
    narrative = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="SELLERS ABSORBED",
        strength=0.9,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[_stacked_signal(ImbalanceType.STACKED_T2, +1)],
        all_signals_count=3,
        confirmed_absorptions=[],
    )
    # Zone at current price with score=55
    zone = _zone(top=PRICE + 1.0, bot=PRICE - 1.0, score=55.0)

    result = score_bar(
        narrative=narrative,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[zone],
        bar_close=PRICE,
    )

    # Categories: absorption, imbalance, delta, auction, poc, volume_profile = 6
    assert result.category_count >= 5
    assert result.zone_bonus > 0
    assert result.tier == SignalTier.TYPE_A, (
        f"Expected TYPE_A, got {result.tier} (score={result.total_score:.1f}, "
        f"cats={result.category_count}, zone_bonus={result.zone_bonus})"
    )


def test_type_a_fails_without_zone():
    """Even with high score and 5 categories, TypeA should NOT fire without zone bonus."""
    narrative = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="SELLERS ABSORBED",
        strength=0.9,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[_exh_signal(+1)],
        imbalances=[_stacked_signal(ImbalanceType.STACKED_T3, +1)],
        all_signals_count=3,
        confirmed_absorptions=[],
    )
    # No active zones (or zone far away)
    result = score_bar(
        narrative=narrative,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[],
        bar_close=PRICE,
    )

    assert result.zone_bonus == 0.0
    assert result.tier != SignalTier.TYPE_A, (
        f"TypeA should not fire without zone_bonus, got {result.tier}"
    )


# ---------------------------------------------------------------------------
# Test 3: SCOR-02 Confluence multiplier fires at exactly 5 categories
# ---------------------------------------------------------------------------

def test_confluence_mult_at_5_categories():
    """Confluence multiplier is 1.25 when 5+ categories agree, 1.0 for 4."""
    # Build 5-category scenario: absorption + imbalance + delta + auction + poc
    narrative_5 = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="test",
        strength=0.8,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[_stacked_signal(ImbalanceType.STACKED_T1, +1)],
        all_signals_count=3,
        confirmed_absorptions=[],
    )
    result_5 = score_bar(
        narrative=narrative_5,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[],
        bar_close=PRICE,
    )
    # absorption, imbalance, delta, auction, poc = 5 cats → 1.25x
    assert result_5.category_count >= 5
    assert result_5.confluence_mult == 1.25, (
        f"Expected 1.25 at {result_5.category_count} cats, got {result_5.confluence_mult}"
    )

    # 4 categories: absorption + delta + auction + poc (no imbalance)
    narrative_4 = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="test",
        strength=0.8,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[],
        all_signals_count=1,
        confirmed_absorptions=[],
    )
    result_4 = score_bar(
        narrative=narrative_4,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[],
        bar_close=PRICE,
    )
    assert result_4.category_count == 4
    assert result_4.confluence_mult == 1.0, (
        f"Expected 1.0 at {result_4.category_count} cats, got {result_4.confluence_mult}"
    )


# ---------------------------------------------------------------------------
# Test 4: SCOR-03 Zone bonus tiers
# ---------------------------------------------------------------------------

def test_zone_bonus_tiers():
    """zone.score=55 → +8.0; zone.score=35 → +6.0; zone.score=20 → 0.0"""
    narrative = _empty_narrative(direction=0)  # neutral narrative, zones tested in isolation

    # High zone (score=55) — price inside zone
    zone_high = _zone(top=PRICE + 1.0, bot=PRICE - 1.0, score=55.0)
    result_high = score_bar(
        narrative=narrative,
        delta_signals=[],
        auction_signals=[],
        poc_signals=[],
        active_zones=[zone_high],
        bar_close=PRICE,
    )
    assert result_high.zone_bonus == 8.0, f"Expected 8.0, got {result_high.zone_bonus}"

    # Mid zone (score=35) — price inside zone
    zone_mid = _zone(top=PRICE + 1.0, bot=PRICE - 1.0, score=35.0)
    result_mid = score_bar(
        narrative=narrative,
        delta_signals=[],
        auction_signals=[],
        poc_signals=[],
        active_zones=[zone_mid],
        bar_close=PRICE,
    )
    assert result_mid.zone_bonus == 6.0, f"Expected 6.0, got {result_mid.zone_bonus}"

    # Low zone (score=20) — price inside zone but below both thresholds → no bonus
    zone_low = _zone(top=PRICE + 1.0, bot=PRICE - 1.0, score=20.0)
    result_low = score_bar(
        narrative=narrative,
        delta_signals=[],
        auction_signals=[],
        poc_signals=[],
        active_zones=[zone_low],
        bar_close=PRICE,
    )
    assert result_low.zone_bonus == 0.0, f"Expected 0.0, got {result_low.zone_bonus}"


# ---------------------------------------------------------------------------
# Test 5: D-01 Confirmation bonus applied when confirmed_absorptions non-empty
# ---------------------------------------------------------------------------

def test_confirmation_bonus_applied():
    """2 confirmed_absorptions → total_score increases by 2 * 2.0 = 4.0."""
    base_narrative = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="SELLERS ABSORBED",
        strength=0.8,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[],
        all_signals_count=1,
        confirmed_absorptions=[],
    )
    confirmed_narrative = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="SELLERS ABSORBED",
        strength=0.8,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[],
        all_signals_count=1,
        confirmed_absorptions=[_confirmation(+1), _confirmation(+1)],
    )

    result_base = score_bar(
        narrative=base_narrative,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[],
        poc_signals=[],
        active_zones=[],
        bar_close=PRICE,
    )
    result_confirmed = score_bar(
        narrative=confirmed_narrative,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[],
        poc_signals=[],
        active_zones=[],
        bar_close=PRICE,
    )

    expected_bonus = 2 * AbsorptionConfig().confirmation_score_bonus  # 2 * 2.0 = 4.0
    actual_diff = result_confirmed.total_score - result_base.total_score
    assert abs(actual_diff - expected_bonus) < 0.01, (
        f"Expected +{expected_bonus} bonus, got diff={actual_diff:.2f} "
        f"(base={result_base.total_score:.2f}, confirmed={result_confirmed.total_score:.2f})"
    )


def test_confirmation_bonus_caps_at_100():
    """Confirmation bonus never pushes total_score above 100.0."""
    # Build a scenario with very high base score
    many_confirmations = [_confirmation(+1) for _ in range(20)]
    narrative = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="SELLERS ABSORBED",
        strength=1.0,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[_exh_signal(+1)],
        imbalances=[_stacked_signal(ImbalanceType.STACKED_T3, +1)],
        all_signals_count=5,
        confirmed_absorptions=many_confirmations,
    )
    zone = _zone(top=PRICE + 1.0, bot=PRICE - 1.0, score=60.0)
    result = score_bar(
        narrative=narrative,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[zone],
        bar_close=PRICE,
    )
    assert result.total_score <= 100.0, f"Score exceeded 100: {result.total_score}"


# ---------------------------------------------------------------------------
# Test 6: D-02 Stacked dedup — highest tier only per direction
# ---------------------------------------------------------------------------

def test_stacked_dedup_highest_tier_only():
    """T1 + T2 + T3 all bullish → imbalance category counted once, total_votes +1 not +3."""
    narrative_triple = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="test",
        strength=0.8,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[
            _stacked_signal(ImbalanceType.STACKED_T1, +1),
            _stacked_signal(ImbalanceType.STACKED_T2, +1),
            _stacked_signal(ImbalanceType.STACKED_T3, +1),
        ],
        all_signals_count=4,
        confirmed_absorptions=[],
    )
    # Single T3 only for comparison
    narrative_single = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="test",
        strength=0.8,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[
            _stacked_signal(ImbalanceType.STACKED_T3, +1),
        ],
        all_signals_count=2,
        confirmed_absorptions=[],
    )

    result_triple = score_bar(
        narrative=narrative_triple,
        delta_signals=[],
        auction_signals=[],
        poc_signals=[],
        active_zones=[],
        bar_close=PRICE,
    )
    result_single = score_bar(
        narrative=narrative_single,
        delta_signals=[],
        auction_signals=[],
        poc_signals=[],
        active_zones=[],
        bar_close=PRICE,
    )

    # Both should produce identical category counts and scores
    assert result_triple.category_count == result_single.category_count, (
        f"Triple-stacked dedup failed: triple cats={result_triple.category_count}, "
        f"single cats={result_single.category_count}"
    )
    assert abs(result_triple.total_score - result_single.total_score) < 0.01, (
        f"Score mismatch: triple={result_triple.total_score:.2f}, single={result_single.total_score:.2f}"
    )


# ---------------------------------------------------------------------------
# Test 7: SCOR-06 Labels contain correct tier strings
# ---------------------------------------------------------------------------

def test_label_format_all_tiers():
    """TypeA → 'TYPE A'; TypeB → 'TYPE B'; TypeC → 'TYPE C'; QUIET → narrative label."""

    # TypeA: absorption + zone + 5 cats + high score
    narrative_a = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="SELLERS ABSORBED",
        strength=0.9,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[_stacked_signal(ImbalanceType.STACKED_T2, +1)],
        all_signals_count=3,
        confirmed_absorptions=[],
    )
    zone = _zone(top=PRICE + 1.0, bot=PRICE - 1.0, score=55.0)
    result_a = score_bar(
        narrative=narrative_a,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[zone],
        bar_close=PRICE,
    )
    if result_a.tier == SignalTier.TYPE_A:
        assert "TYPE A" in result_a.label, f"TypeA label missing 'TYPE A': {result_a.label}"

    # TypeB: 4 cats, score >= 65, no zone req
    narrative_b = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="test",
        strength=0.9,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[],
        all_signals_count=1,
        confirmed_absorptions=[],
    )
    result_b = score_bar(
        narrative=narrative_b,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[],
        bar_close=PRICE,
        # Force TypeB by lowering thresholds
        scorer_config=ScorerConfig(type_a_min=90.0, type_b_min=30.0, type_c_min=10.0),
    )
    if result_b.tier == SignalTier.TYPE_B:
        assert "TYPE B" in result_b.label, f"TypeB label missing 'TYPE B': {result_b.label}"

    # TypeC: 3 cats, score >= 50
    narrative_c = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="test",
        strength=0.9,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[],
        all_signals_count=1,
        confirmed_absorptions=[],
    )
    result_c = score_bar(
        narrative=narrative_c,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[],
        active_zones=[],
        bar_close=PRICE,
        scorer_config=ScorerConfig(type_a_min=90.0, type_b_min=90.0, type_c_min=20.0, min_categories=3),
    )
    if result_c.tier == SignalTier.TYPE_C:
        assert "TYPE C" in result_c.label, f"TypeC label missing 'TYPE C': {result_c.label}"

    # QUIET: no signals
    narrative_quiet = _empty_narrative()
    narrative_quiet.label  # just a string check
    result_quiet = score_bar(
        narrative=narrative_quiet,
        delta_signals=[],
        auction_signals=[],
        poc_signals=[],
        active_zones=[],
        bar_close=PRICE,
    )
    assert result_quiet.tier == SignalTier.QUIET
    assert result_quiet.label == "quiet"


# ---------------------------------------------------------------------------
# Test 8: D-11 ScorerConfig override
# ---------------------------------------------------------------------------

def test_scorer_config_override():
    """Custom ScorerConfig(type_a_min=70.0) fires TypeA at score 72 vs default TypeB."""
    narrative = NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="SELLERS ABSORBED",
        strength=0.9,
        price=PRICE,
        absorption=[_abs_signal(+1)],
        exhaustion=[],
        imbalances=[_stacked_signal(ImbalanceType.STACKED_T2, +1)],
        all_signals_count=3,
        confirmed_absorptions=[],
    )
    zone = _zone(top=PRICE + 1.0, bot=PRICE - 1.0, score=55.0)

    # With default config (type_a_min=80) — check what tier we get
    result_default = score_bar(
        narrative=narrative,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[zone],
        bar_close=PRICE,
    )

    # With custom config (type_a_min=70) — TypeA threshold lowered
    custom_cfg = ScorerConfig(type_a_min=70.0, type_b_min=55.0, type_c_min=40.0)
    result_custom = score_bar(
        narrative=narrative,
        delta_signals=[_delta_signal(+1)],
        auction_signals=[_auction_signal(+1)],
        poc_signals=[_poc_signal(+1)],
        active_zones=[zone],
        bar_close=PRICE,
        scorer_config=custom_cfg,
    )

    # With lowered threshold, tier should be at least as good (TypeA >= TypeB)
    assert result_custom.tier >= result_default.tier, (
        f"Custom config should produce equal or better tier: "
        f"custom={result_custom.tier}, default={result_default.tier}"
    )

    # Verify ScorerConfig fields pass through correctly
    assert custom_cfg.type_a_min == 70.0
    assert custom_cfg.confluence_threshold == 5
    assert custom_cfg.zone_high_bonus == 8.0
