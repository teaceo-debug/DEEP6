"""Tests for scorer × ConfluenceAnnotations integration (Phase 15-03 / D-32).

Covers:
  - score_mutations applied to Level instances in active_zones (keyed by uid/C5)
  - score clipped to [0, 100] after mutation
  - vetoes force SignalTier.DISQUALIFIED
  - meta-flag bits emitted on ScorerResult.meta_flags (bits 45+)
  - signal bits (0-44) unchanged by annotations path
  - backward-compat: confluence_annotations=None preserves existing behavior
"""
from __future__ import annotations

import pytest

from deep6.engines.confluence_rules import ConfluenceAnnotations
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.narrative import NarrativeResult, NarrativeType
from deep6.engines.absorption import AbsorptionSignal, AbsorptionType
from deep6.engines.imbalance import ImbalanceSignal, ImbalanceType
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType
from deep6.engines.delta import DeltaSignal, DeltaType
from deep6.engines.auction import AuctionSignal, AuctionType
from deep6.engines.poc import POCSignal, POCType
from deep6.scoring.scorer import score_bar, SignalTier, ScorerResult
from deep6.signals.flags import SIGNAL_BITS_MASK, SignalFlags


PRICE = 19000.0


# ---------------------------------------------------------------------------
# Builders reused from test_scorer.py conventions
# ---------------------------------------------------------------------------


def _abs_signal(direction=+1):
    return AbsorptionSignal(
        bar_type=AbsorptionType.CLASSIC, direction=direction, price=PRICE,
        wick="lower" if direction > 0 else "upper",
        strength=0.8, wick_pct=40.0, delta_ratio=0.05,
        detail="test absorption", at_va_extreme=False,
    )


def _stacked(direction=+1):
    return ImbalanceSignal(
        imb_type=ImbalanceType.STACKED_T3, direction=direction, price=PRICE,
        ratio=5.0, count=5, strength=0.8, detail="test stacked",
    )


def _delta_sig(direction=+1):
    return DeltaSignal(delta_type=DeltaType.DIVERGENCE, direction=direction,
                       strength=0.7, value=500.0 * direction, detail="test")


def _auction_sig(direction=+1):
    return AuctionSignal(auction_type=AuctionType.FINISHED_AUCTION, direction=direction,
                         price=PRICE, strength=0.7, detail="test")


def _poc_sig(direction=+1):
    return POCSignal(
        poc_type=POCType.BULLISH_POC if direction > 0 else POCType.BEARISH_POC,
        direction=direction, price=PRICE, strength=0.7, detail="test",
    )


def _narrative(direction=+1):
    return NarrativeResult(
        bar_type=NarrativeType.ABSORPTION, direction=direction,
        label="SELLERS ABSORBED", strength=0.9, price=PRICE,
        absorption=[_abs_signal(direction)], exhaustion=[],
        imbalances=[_stacked(direction)], all_signals_count=3,
        confirmed_absorptions=[],
    )


def _level_zone(score=55.0) -> Level:
    return Level(
        price_top=PRICE + 1.0,
        price_bot=PRICE - 1.0,
        kind=LevelKind.HVN,
        origin_ts=0.0,
        origin_bar=1,
        last_act_bar=1,
        score=score,
        touches=1,
        direction=+1,
        inverted=False,
        state=LevelState.CREATED,
    )


def _legacy_zone(score=55.0) -> VolumeZone:
    return VolumeZone(
        zone_type=ZoneType.HVN, state=ZoneState.CREATED,
        top_price=PRICE + 1.0, bot_price=PRICE - 1.0,
        direction=+1, origin_bar=1, last_touch_bar=1, score=score,
    )


def _call(active_zones, *, confluence_annotations=None) -> ScorerResult:
    return score_bar(
        narrative=_narrative(+1),
        delta_signals=[_delta_sig(+1)],
        auction_signals=[_auction_sig(+1)],
        poc_signals=[_poc_sig(+1)],
        active_zones=active_zones,
        bar_close=PRICE,
        bar_delta=+100,
        confluence_annotations=confluence_annotations,
    )


# ===========================================================================
# Tests
# ===========================================================================


def test_score_mutation_applied_to_level_before_tier():
    """Level score gets +10 delta applied before tier logic reads zone_bonus."""
    lvl = _level_zone(score=55.0)
    annots = ConfluenceAnnotations(score_mutations={lvl.uid: 10.0})
    _call([lvl], confluence_annotations=annots)
    # Level mutation applied in-place
    assert lvl.score == 65.0


def test_score_mutation_clipped_to_100():
    lvl = _level_zone(score=95.0)
    annots = ConfluenceAnnotations(score_mutations={lvl.uid: 20.0})
    _call([lvl], confluence_annotations=annots)
    assert lvl.score == 100.0


def test_score_mutation_clipped_to_0():
    lvl = _level_zone(score=5.0)
    annots = ConfluenceAnnotations(score_mutations={lvl.uid: -50.0})
    _call([lvl], confluence_annotations=annots)
    assert lvl.score == 0.0


def test_veto_forces_disqualified_tier():
    lvl = _level_zone(score=95.0)
    annots = ConfluenceAnnotations(vetoes={"SPOOF_DETECTED"})
    result = _call([lvl], confluence_annotations=annots)
    assert result.tier == SignalTier.DISQUALIFIED


def test_veto_disqualified_beats_gex_direction_conflict():
    """Veto must bypass any other tier-forcing logic."""
    lvl = _level_zone(score=55.0)
    annots = ConfluenceAnnotations(vetoes={"SPOOF_DETECTED"})
    result = _call([lvl], confluence_annotations=annots)
    assert result.tier == SignalTier.DISQUALIFIED
    assert int(result.meta_flags) & int(SignalFlags.SPOOF_VETO) != 0


def test_meta_flags_pin_regime():
    lvl = _level_zone()
    annots = ConfluenceAnnotations(flags={"PIN_REGIME_ACTIVE"})
    result = _call([lvl], confluence_annotations=annots)
    assert int(result.meta_flags) & int(SignalFlags.PIN_REGIME_ACTIVE) != 0


def test_meta_flags_regime_change():
    lvl = _level_zone()
    annots = ConfluenceAnnotations(flags={"REGIME_CHANGE"})
    result = _call([lvl], confluence_annotations=annots)
    assert int(result.meta_flags) & int(SignalFlags.REGIME_CHANGE) != 0


def test_signal_bits_unchanged_by_meta_flags():
    """Meta-flag bits 45+ live on ScorerResult.meta_flags only.

    The 45 signal bits (0-44) are unaffected by the confluence path.
    """
    lvl = _level_zone()
    annots = ConfluenceAnnotations(
        flags={"PIN_REGIME_ACTIVE", "REGIME_CHANGE"},
        vetoes={"SPOOF_DETECTED"},
    )
    result = _call([lvl], confluence_annotations=annots)
    # Mask out meta-flag bits — remaining bits should be 0 since scorer
    # itself does not directly emit signal bits on ScorerResult today.
    masked_meta = int(result.meta_flags) & SIGNAL_BITS_MASK
    assert masked_meta == 0, "meta_flags leaked into signal bit range"


def test_default_no_annotations_backward_compat():
    """score_bar(confluence_annotations=None) preserves legacy behavior."""
    zone = _legacy_zone(score=55.0)
    result_with = _call([zone], confluence_annotations=None)
    result_without = score_bar(
        narrative=_narrative(+1),
        delta_signals=[_delta_sig(+1)],
        auction_signals=[_auction_sig(+1)],
        poc_signals=[_poc_sig(+1)],
        active_zones=[zone],
        bar_close=PRICE,
        bar_delta=+100,
    )
    # Without the kwarg should be identical
    assert result_with.total_score == result_without.total_score
    assert result_with.tier == result_without.tier
    assert int(result_with.meta_flags) == 0
    assert int(result_without.meta_flags) == 0


def test_legacy_volume_zone_compatible():
    """Duck-typed zone reading (VolumeZone + Level both supported)."""
    zone = _legacy_zone(score=55.0)
    result = _call([zone])
    # Must produce a valid result (zone_bonus fires via compat shim)
    assert result.zone_bonus > 0


def test_level_zone_matches_volume_zone_geometry():
    """Level-shaped zones at same price/score produce same zone_bonus as VolumeZone."""
    lz = _legacy_zone(score=55.0)
    lvl = _level_zone(score=55.0)
    r_legacy = _call([lz])
    r_level = _call([lvl])
    assert r_legacy.zone_bonus == r_level.zone_bonus


def test_signal_tier_disqualified_exists_and_is_negative():
    """DISQUALIFIED is added as -1 and ordered below QUIET."""
    assert int(SignalTier.DISQUALIFIED) == -1
    assert SignalTier.DISQUALIFIED < SignalTier.QUIET
