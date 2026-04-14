"""Integration tests: VPIN multiplier wired into scorer.score_bar.

Verifies phase 12-01 locked contract:
* VPIN modulates FUSED confidence only (scorer total_score)
* VPIN applies as FINAL stage, AFTER IB multiplier, BEFORE clip
* VPIN does NOT stack with IB multiplier on per-signal scores (they are
  separate line items in scorer.py — enforced via source inspection)
* Clip bounds total_score to [0, 100]
* Default vpin_modifier=1.0 preserves pre-VPIN behavior (legacy tests)
"""
from __future__ import annotations

import inspect
import re

import pytest

from deep6.engines.narrative import NarrativeResult, NarrativeType
from deep6.engines.absorption import AbsorptionSignal, AbsorptionType
from deep6.engines.exhaustion import ExhaustionSignal, ExhaustionType
from deep6.engines.imbalance import ImbalanceSignal, ImbalanceType
from deep6.engines.volume_profile import VolumeZone, ZoneState, ZoneType
from deep6.engines.delta import DeltaSignal, DeltaType
from deep6.engines.auction import AuctionSignal, AuctionType
from deep6.engines.poc import POCSignal, POCType
from deep6.scoring.scorer import score_bar, SignalTier
from deep6.scoring import scorer as scorer_module


PRICE = 19000.0


# ---- Minimal signal factories (mirrors tests/test_scorer.py) ----

def _abs(direction: int = +1) -> AbsorptionSignal:
    return AbsorptionSignal(
        bar_type=AbsorptionType.CLASSIC, direction=direction, price=PRICE,
        wick="lower" if direction > 0 else "upper", strength=0.8,
        wick_pct=40.0, delta_ratio=0.05, detail="t", at_va_extreme=False,
    )


def _exh(direction: int = +1) -> ExhaustionSignal:
    return ExhaustionSignal(
        bar_type=ExhaustionType.THIN_PRINT, direction=direction, price=PRICE,
        strength=0.7, detail="t",
    )


def _imb(direction: int = +1) -> ImbalanceSignal:
    return ImbalanceSignal(
        imb_type=ImbalanceType.STACKED_T3, direction=direction, price=PRICE,
        ratio=5.0, count=5, strength=0.8, detail="t",
    )


def _delta(direction: int = +1) -> DeltaSignal:
    return DeltaSignal(
        delta_type=DeltaType.DIVERGENCE, direction=direction, strength=0.7,
        value=500.0 * direction, detail="t",
    )


def _auction(direction: int = +1) -> AuctionSignal:
    return AuctionSignal(
        auction_type=AuctionType.FINISHED_AUCTION, direction=direction,
        price=PRICE, strength=0.7, detail="t",
    )


def _poc(direction: int = +1) -> POCSignal:
    return POCSignal(
        poc_type=POCType.BULLISH_POC if direction > 0 else POCType.BEARISH_POC,
        direction=direction, price=PRICE, strength=0.7, detail="t",
    )


def _zone(score: float = 80.0) -> VolumeZone:
    return VolumeZone(
        zone_type=ZoneType.HVN, state=ZoneState.CREATED,
        top_price=PRICE + 1.0, bot_price=PRICE - 1.0, direction=+1,
        origin_bar=1, last_touch_bar=1, score=score,
    )


def _high_confluence_narrative() -> NarrativeResult:
    return NarrativeResult(
        bar_type=NarrativeType.ABSORPTION,
        direction=+1,
        label="SELLERS ABSORBED",
        strength=0.9,
        price=PRICE,
        absorption=[_abs(+1)],
        exhaustion=[_exh(+1)],
        imbalances=[_imb(+1)],
        all_signals_count=3,
        confirmed_absorptions=[],
    )


def _score(vpin_modifier: float = 1.0, bar_index: int = 10):
    """Wrapper: score a high-confluence bar with the requested vpin_modifier."""
    return score_bar(
        narrative=_high_confluence_narrative(),
        delta_signals=[_delta(+1)],
        auction_signals=[_auction(+1)],
        poc_signals=[_poc(+1)],
        active_zones=[_zone(80.0)],
        bar_close=PRICE,
        bar_delta=500,
        bar_index_in_session=bar_index,
        vpin_modifier=vpin_modifier,
    )


# ---- Tests ----

def test_default_modifier_preserves_existing_behavior():
    """vpin_modifier defaults to 1.0 — identical score vs. not passing it."""
    result_default = _score(vpin_modifier=1.0)
    # Call WITHOUT vpin_modifier kwarg to be sure the default equals 1.0
    result_absent = score_bar(
        narrative=_high_confluence_narrative(),
        delta_signals=[_delta(+1)],
        auction_signals=[_auction(+1)],
        poc_signals=[_poc(+1)],
        active_zones=[_zone(80.0)],
        bar_close=PRICE,
        bar_delta=500,
        bar_index_in_session=10,
    )
    assert result_default.total_score == result_absent.total_score


def test_vpin_reduces_fused_score_when_toxic():
    """Toxic VPIN modifier (<1.0) must reduce total_score proportionally."""
    base = _score(vpin_modifier=1.0)
    toxic = _score(vpin_modifier=0.2)
    assert toxic.total_score < base.total_score
    # Score roughly scales by modifier (pre-clip), with clip at 100.
    # base is capped at <= 100; toxic is base * 0.2, so toxic <= 20.
    assert toxic.total_score <= 20.0 + 1e-6


def test_vpin_expands_fused_score_when_clean_but_clips_at_100():
    """Clean VPIN modifier (>1.0) grows score but must clip at 100."""
    base = _score(vpin_modifier=1.0)
    clean = _score(vpin_modifier=1.2)
    # clean >= base (monotone); both capped at 100
    assert clean.total_score >= base.total_score
    assert clean.total_score <= 100.0


def test_clip_bounds_score_to_zero_hundred():
    """Any VPIN modifier still yields 0 <= total_score <= 100."""
    for mod in (0.2, 0.5, 0.8, 1.0, 1.2):
        r = _score(vpin_modifier=mod)
        assert 0.0 <= r.total_score <= 100.0


def test_toxic_vpin_can_demote_tier_but_never_changes_direction():
    """Very low VPIN modifier can drop TYPE_A below threshold → lower tier,
    but direction is untouched (VPIN is orthogonal to the 44-signal vote)."""
    base = _score(vpin_modifier=1.0)
    crushed = _score(vpin_modifier=0.2)
    assert crushed.direction == base.direction
    # crushed cannot be a HIGHER tier than base
    assert int(crushed.tier) <= int(base.tier)


def test_ib_and_vpin_are_separate_line_items():
    """scorer.py must apply VPIN as a FINAL, separate multiplier — never fused
    with the IB multiplier on per-signal scores.

    Enforced by inspecting the source: IB is applied inside the base-score
    composition; VPIN is applied on the fused `total_score` afterward. There
    must be distinct statements for each, in that order, with a clip at the
    end.
    """
    src = inspect.getsource(scorer_module)
    # IB multiplier must still exist as its own line
    assert "ib_mult" in src, "IB multiplier removed — regression"
    # VPIN multiplier must be applied on total_score only, as a separate stmt
    assert "vpin_modifier" in src, "vpin_modifier kwarg missing from scorer"
    assert re.search(r"total_score\s*\*=\s*vpin_modifier", src), (
        "VPIN must be applied as: total_score *= vpin_modifier "
        "(final stage, separate line from ib_mult)"
    )
    # No evidence of a compound product pre-fusion like "ib_mult * vpin_modifier"
    assert "ib_mult * vpin_modifier" not in src, (
        "IB and VPIN must NOT be multiplied together (footgun FOOTGUN 1)"
    )
    assert "vpin_modifier * ib_mult" not in src, (
        "IB and VPIN must NOT be multiplied together (footgun FOOTGUN 1)"
    )


def test_final_stage_ordering_vpin_after_ib_before_clip():
    """Source order in scorer.py: ib_mult usage -> vpin_modifier -> clip.

    Protects the locked multiplier order: base → category → zone → IB → VPIN → clip.
    """
    src = inspect.getsource(scorer_module)
    ib_pos = src.find("ib_mult")
    # Find the FIRST assignment using vpin_modifier on total_score
    vpin_match = re.search(r"total_score\s*\*=\s*vpin_modifier", src)
    assert vpin_match is not None
    vpin_pos = vpin_match.start()
    assert ib_pos != -1 and ib_pos < vpin_pos, (
        "IB multiplier must be applied BEFORE the VPIN multiplier"
    )
    # The clip on total_score to [0, 100] must appear AFTER vpin_modifier
    tail = src[vpin_pos:]
    assert re.search(r"max\(\s*0\.0\s*,\s*min\(\s*100\.0\s*,\s*total_score", tail), (
        "After VPIN is applied, total_score must be clipped to [0, 100] "
        "using max(0.0, min(100.0, total_score))"
    )
