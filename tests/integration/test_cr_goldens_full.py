"""Phase 15-05 T-15-05-03 — CR-XX golden-file suite (integration-level).

For every CR-XX rule in RULES.md we assert:
  * A PURPOSE-BUILT trigger fixture produces the rule's expected flag /
    regime / veto via the integration entry point ``evaluate()``.
  * A no-trigger case (empty levels, no gex, no meta) does NOT emit the
    rule's flag.

Difference from ``tests/engines/test_confluence_rules.py`` (plan 15-03):
  This harness drives ``evaluate()`` through the full integration contract
  — ``ConfluenceRulesConfig`` + ``prior_regime`` + real FootprintBar + real
  ScorerResult — matching what the bar-engine loop will feed in Phase 16.
  The plan-03 unit tests exercise individual rule functions.

Parametrized by CR-id so pytest's failure report lists exactly which rules
broke.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from deep6.engines.confluence_rules import (
    ConfluenceAnnotations,
    ConfluenceRulesConfig,
    evaluate,
)
from deep6.engines.gex import GexRegime, GexSignal
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.narrative import NarrativeType
from deep6.scoring.scorer import ScorerResult, SignalTier


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _lv(
    kind,
    price=18500.0,
    direction=+1,
    score=70.0,
    state=LevelState.CREATED,
    meta=None,
    origin_bar=0,
    is_zone=True,
):
    if is_zone and kind in (
        LevelKind.LVN, LevelKind.HVN, LevelKind.ABSORB, LevelKind.EXHAUST,
        LevelKind.MOMENTUM, LevelKind.REJECTION, LevelKind.FLIPPED,
        LevelKind.CONFIRMED_ABSORB,
    ):
        top, bot = price + 0.5, price - 0.5
    else:
        top = bot = price
    return Level(
        price_top=top, price_bot=bot, kind=kind,
        origin_ts=time.time(), origin_bar=origin_bar, last_act_bar=origin_bar,
        score=score, touches=1, direction=direction, inverted=False,
        state=state, meta=dict(meta or {}),
    )


def _bar(close=18500.0, open_=18499.0, high=None, low=None):
    return SimpleNamespace(
        close=close, open=open_,
        high=high if high is not None else close + 0.5,
        low=low if low is not None else close - 0.5,
        timestamp=time.time(), bar_delta=100, total_vol=1000,
    )


def _scorer(direction=+1, tier=SignalTier.TYPE_B, score=70.0):
    return ScorerResult(
        total_score=score, tier=tier, direction=direction,
        engine_agreement=0.7, category_count=3, confluence_mult=1.0,
        zone_bonus=6.0, narrative=NarrativeType.ABSORPTION,
        label="test", categories_firing=["absorption", "delta"], meta_flags=0,
    )


def _gex(regime=GexRegime.NEUTRAL, call_wall=18525.0, put_wall=18475.0,
         gamma_flip=18495.0):
    return GexSignal(
        regime=regime, direction=0 if regime == GexRegime.NEUTRAL else (
            +1 if regime == GexRegime.POSITIVE_DAMPENING else -1),
        call_wall=call_wall, put_wall=put_wall, gamma_flip=gamma_flip,
        near_call_wall=False, near_put_wall=False,
        strength=0.5, detail="test",
    )


CFG = ConfluenceRulesConfig()


# ---------------------------------------------------------------------------
# Per-CR builder functions — each returns (levels, gex_signal, bar, scorer,
# config_overrides) such that the rule fires; the expected flag / veto /
# regime is tracked via FLAG_EXPECTATIONS below.
# ---------------------------------------------------------------------------


def _put_wall_absorb_scene():
    """CR-01: ABSORB+1 near PUT_WALL."""
    return [
        _lv(LevelKind.PUT_WALL, price=18475.0, is_zone=False),
        _lv(LevelKind.ABSORB, price=18475.0, direction=+1),
    ]


def _call_wall_exhaust_scene():
    """CR-02: EXHAUST-1 near CALL_WALL."""
    return [
        _lv(LevelKind.CALL_WALL, price=18525.0, is_zone=False),
        _lv(LevelKind.EXHAUST, price=18525.0, direction=-1),
    ]


def _lvn_gamma_flip_scene():
    """CR-03: LVN crossing gamma flip (close inside LVN, flip within 12 ticks)."""
    return [
        _lv(LevelKind.GAMMA_FLIP, price=18500.0, is_zone=False),
        _lv(LevelKind.LVN, price=18500.0),
    ]


def _pin_regime_scene():
    """CR-04: VPOC pinned near LARGEST_GAMMA (within 6 ticks)."""
    return [
        _lv(LevelKind.VPOC, price=18500.0, is_zone=False),
        _lv(LevelKind.LARGEST_GAMMA, price=18500.0, is_zone=False),
    ]


def _momentum_flipped_scene():
    """CR-05: MOMENTUM + FLIPPED + GAMMA_FLIP all present."""
    return [
        _lv(LevelKind.GAMMA_FLIP, price=18500.0, is_zone=False),
        _lv(LevelKind.MOMENTUM, price=18500.0),
        _lv(LevelKind.FLIPPED, price=18499.0),
    ]


def _va_absorb_scene():
    """CR-06: ABSORB within 4 ticks of VAH."""
    return [
        _lv(LevelKind.VAH, price=18500.0, is_zone=False),
        _lv(LevelKind.ABSORB, price=18500.0, direction=+1),
    ]


def _exhaust_absorb_compound_scene():
    """CR-07: EXHAUST-1 + ABSORB-1 at same price within 5 bars."""
    return [
        _lv(LevelKind.EXHAUST, price=18500.0, direction=-1, origin_bar=0),
        _lv(LevelKind.ABSORB, price=18500.0, direction=-1, origin_bar=3),
    ]


def _hvn_put_wall_scene():
    """CR-08: HVN (score>=50) within 6 ticks of PUT_WALL."""
    return [
        _lv(LevelKind.PUT_WALL, price=18475.0, is_zone=False),
        _lv(LevelKind.HVN, price=18475.0, score=60),
    ]


def _gex_present_scene():
    """CR-09: any GEX Level present."""
    return [_lv(LevelKind.CALL_WALL, price=18525.0, is_zone=False)]


# CR-10: regime gate via GexSignal (handled by gex fixture arg)


def _exhaust_broken_scene():
    """CR-11: EXHAUST Level with state=BROKEN."""
    return [_lv(LevelKind.EXHAUST, price=18500.0, state=LevelState.BROKEN)]


# CR-12..15 are unconditional stubs — any input fires when enabled.


def _absorb_high_score_scene():
    """CR-16: ABSORB with score >= 60."""
    return [_lv(LevelKind.ABSORB, price=18500.0, score=65.0)]


def _iceberg_scene():
    """CR-17: Level.meta['iceberg']=True."""
    return [_lv(LevelKind.HVN, price=18500.0, meta={"iceberg": True})]


def _queue_imbalance_scene():
    """CR-18: Level.meta['queue_imbalance'] >= 0.6."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"queue_imbalance": 0.7})]


# CR-19: VPIN regime stub — unconditional when enabled.


def _kyle_lambda_scene():
    """CR-20: Level.meta['kyle_lambda_ratio'] <= 0.5."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"kyle_lambda_ratio": 0.3})]


def _cvd_divergence_scene():
    """CR-21: Level.meta['cvd_divergence']=True."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"cvd_divergence": True})]


# CR-22: Hawkes/Poisson stub — unconditional when enabled.


def _spoof_scene():
    """CR-23: Level.meta['cancel_ratio'] >= 0.85."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"cancel_ratio": 0.9})]


def _aggressor_scene():
    """CR-24: Level.meta['aggressor_share'] > 0.75."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"aggressor_share": 0.8})]


def _round_number_scene():
    """CR-25: Level price exactly on a round-number (multiple of 25)."""
    return [_lv(LevelKind.VPOC, price=18500.0, is_zone=False)]


def _depth_asymmetry_scene():
    """CR-26: Level.meta['depth_ratio'] >= 3.0."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"depth_ratio": 3.5})]


def _failed_break_scene():
    """CR-27: BROKEN Level with Level.meta['hawkes_decay'] >= 0.5."""
    return [_lv(LevelKind.ABSORB, price=18500.0, state=LevelState.BROKEN,
                meta={"hawkes_decay": 0.6})]


# CR-28/29: scorer.direction + bar shape


def _otd_scene():
    """CR-30: Level.meta['otd']=True."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"otd": True})]


def _failed_ib_scene():
    """CR-31: Level.meta['failed_ib']=True."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"failed_ib": True})]


def _naked_poc_scene():
    """CR-32: VPOC with meta['naked']=True."""
    return [_lv(LevelKind.VPOC, price=18500.0, is_zone=False,
                meta={"naked": True})]


def _poor_extreme_scene():
    """CR-33: Level.meta['poor_extreme']=True."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"poor_extreme": True})]


def _tail_retest_scene():
    """CR-34: Level.meta['tail']=True."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"tail": True})]


def _open_auction_scene():
    """CR-35: Level.meta['open_auction_in_range']=True."""
    return [_lv(LevelKind.VPOC, price=18500.0, is_zone=False,
                meta={"open_auction_in_range": True})]


def _double_dist_scene():
    """CR-36: Level.meta['double_distribution']=True."""
    return [_lv(LevelKind.ABSORB, price=18500.0, meta={"double_distribution": True})]


def _absorb_pdh_scene():
    """CR-37: ABSORB/CONFIRMED_ABSORB + prior_day_high + ib_fail_up."""
    return [_lv(LevelKind.CONFIRMED_ABSORB, price=18500.0,
                meta={"prior_day_high": True, "ib_fail_up": True})]


def _neutral_extreme_scene():
    """CR-38: Level.meta['neutral_extreme_close']=True."""
    return [_lv(LevelKind.ABSORB, price=18500.0,
                meta={"neutral_extreme_close": True})]


# ---------------------------------------------------------------------------
# Expectations table — single source of truth per CR-XX
# (levels_builder, gex_builder, bar, scorer_result, config_enables,
#  expected_flag | expected_veto | expected_regime)
# ---------------------------------------------------------------------------


def _cfg_with(**overrides):
    cfg = ConfluenceRulesConfig(**overrides)
    return cfg


CR_EXPECTATIONS: dict[str, dict] = {
    "CR-01": {
        "levels": _put_wall_absorb_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "ABSORB_PUT_WALL",
    },
    "CR-02": {
        "levels": _call_wall_exhaust_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(direction=-1), "flag": "EXHAUST_CALL_WALL_FLAG",
    },
    "CR-03": {
        "levels": _lvn_gamma_flip_scene, "gex": None, "bar": _bar(close=18500.0),
        "scorer": _scorer(), "flag": "ACCELERATION_CANDIDATE",
    },
    "CR-04": {
        "levels": _pin_regime_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "PIN_REGIME_ACTIVE", "regime": "PIN",
    },
    "CR-05": {
        "levels": _momentum_flipped_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "REGIME_CHANGE",
    },
    "CR-06": {
        "levels": _va_absorb_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "VA_CONFIRMED",
    },
    "CR-07": {
        "levels": _exhaust_absorb_compound_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(direction=-1), "flag": "EXHAUST_ABSORB_COMPOUND",
    },
    "CR-08": {
        "levels": _hvn_put_wall_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "SUPPRESS_SHORTS",
    },
    "CR-09": {
        "levels": _gex_present_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "GEX_BASIS_CORRECTED",
    },
    "CR-10": {
        "levels": list, "gex": lambda: _gex(regime=GexRegime.POSITIVE_DAMPENING),
        "bar": _bar(), "scorer": _scorer(), "flag": "REGIME_POSITIVE_GAMMA",
        "regime": "BALANCE",
    },
    "CR-11": {
        "levels": _exhaust_broken_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "BREAKOUT_CONTINUATION",
        "cfg_overrides": {"enable_CR_11": True},
    },
    "CR-12": {
        "levels": list, "gex": None, "bar": _bar(), "scorer": _scorer(),
        "flag": "LAST_30_MIN_STUB",
        "cfg_overrides": {"enable_CR_12": True},
    },
    "CR-13": {
        "levels": list, "gex": None, "bar": _bar(), "scorer": _scorer(),
        "flag": "CHARM_DRIFT_STUB",
        "cfg_overrides": {"enable_CR_13": True},
    },
    "CR-14": {
        "levels": list, "gex": None, "bar": _bar(), "scorer": _scorer(),
        "flag": "ZERO_DTE_GUARD_STUB",
        "cfg_overrides": {"enable_CR_14": True},
    },
    "CR-15": {
        "levels": list, "gex": None, "bar": _bar(), "scorer": _scorer(),
        "flag": "NEG_GAMMA_RISK_SCALAR_STUB",
        "cfg_overrides": {"enable_CR_15": True},
    },
    "CR-16": {
        "levels": _absorb_high_score_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "MS_ABSORB_Z",
    },
    "CR-17": {
        "levels": _iceberg_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "ICEBERG_AT_LEVEL",
    },
    "CR-18": {
        "levels": _queue_imbalance_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "QUEUE_IMBALANCE",
    },
    "CR-19": {
        "levels": list, "gex": None, "bar": _bar(), "scorer": _scorer(),
        "flag": "VPIN_REGIME_STUB",
        "cfg_overrides": {"enable_CR_19": True},
    },
    "CR-20": {
        "levels": _kyle_lambda_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "KYLE_LAMBDA_COMPRESSED",
    },
    "CR-21": {
        "levels": _cvd_divergence_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "CVD_DIVERGENCE",
    },
    "CR-22": {
        "levels": list, "gex": None, "bar": _bar(), "scorer": _scorer(),
        "flag": "CLUSTER_POISSON_STUB",
        "cfg_overrides": {"enable_CR_22": True},
    },
    "CR-23": {
        "levels": _spoof_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "SPOOF_VETO", "veto": "SPOOF_DETECTED",
    },
    "CR-24": {
        "levels": _aggressor_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "AGGRESSOR_DOMINANT",
    },
    "CR-25": {
        "levels": _round_number_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "ROUND_NUMBER",
    },
    "CR-26": {
        "levels": _depth_asymmetry_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "DEPTH_ASYMMETRY",
    },
    "CR-27": {
        "levels": _failed_break_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "FAILED_BREAK",
        "cfg_overrides": {"enable_CR_27": True},
    },
    "CR-28": {
        "levels": list, "gex": None,
        "bar": _bar(close=18510.0, open_=18500.0),
        "scorer": _scorer(direction=+1), "flag": "OD_UP_ORU",
    },
    "CR-29": {
        "levels": list, "gex": None,
        "bar": _bar(close=18490.0, open_=18500.0),
        "scorer": _scorer(direction=-1), "flag": "OD_DOWN_ORD",
    },
    "CR-30": {
        "levels": _otd_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "OTD_REVERSAL",
    },
    "CR-31": {
        "levels": _failed_ib_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "FAILED_IB",
    },
    "CR-32": {
        "levels": _naked_poc_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "NAKED_POC_MAGNET",
    },
    "CR-33": {
        "levels": _poor_extreme_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "POOR_EXTREME_REVISIT",
    },
    "CR-34": {
        "levels": _tail_retest_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "TAIL_RETEST",
    },
    "CR-35": {
        "levels": _open_auction_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "OPEN_AUCTION_IN_RANGE",
        "regime": "BALANCE",
    },
    "CR-36": {
        "levels": _double_dist_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "DOUBLE_DIST_REVISIT",
    },
    "CR-37": {
        "levels": _absorb_pdh_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "ABSORB_PDH_IB_FAIL",
        "cfg_overrides": {"enable_CR_37": True},
    },
    "CR-38": {
        "levels": _neutral_extreme_scene, "gex": None, "bar": _bar(),
        "scorer": _scorer(), "flag": "GAP_AND_GO_BIAS",
    },
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_all_cr_rules_covered():
    """Inventory check: all 38 CR-XX have a golden fixture."""
    expected = {f"CR-{i:02d}" for i in range(1, 39)}
    assert set(CR_EXPECTATIONS.keys()) == expected, (
        f"Missing goldens: {expected - set(CR_EXPECTATIONS.keys())}"
    )


@pytest.mark.parametrize("cr_id", sorted(CR_EXPECTATIONS.keys()))
def test_cr_trigger_emits_expected(cr_id):
    """Each CR-XX trigger fixture must surface its flag/veto/regime."""
    spec = CR_EXPECTATIONS[cr_id]
    levels_builder = spec["levels"]
    levels = levels_builder() if callable(levels_builder) else list(levels_builder)
    gex_builder = spec.get("gex")
    gex = gex_builder() if callable(gex_builder) else gex_builder
    bar = spec["bar"]
    scorer_result = spec["scorer"]
    cfg = _cfg_with(**spec.get("cfg_overrides", {}))

    annotations = evaluate(levels, gex, bar, scorer_result, config=cfg)

    expected_flag = spec.get("flag")
    if expected_flag is not None:
        assert expected_flag in annotations.flags, (
            f"{cr_id}: flag {expected_flag!r} missing from {annotations.flags}"
        )
    expected_veto = spec.get("veto")
    if expected_veto is not None:
        assert expected_veto in annotations.vetoes, (
            f"{cr_id}: veto {expected_veto!r} missing from {annotations.vetoes}"
        )
    expected_regime = spec.get("regime")
    if expected_regime is not None:
        assert annotations.regime == expected_regime, (
            f"{cr_id}: regime {annotations.regime!r} != expected {expected_regime!r}"
        )


@pytest.mark.parametrize("cr_id", sorted(CR_EXPECTATIONS.keys()))
def test_cr_no_trigger_on_empty_input(cr_id):
    """Empty levels + no gex + quiet scorer ⇒ rule's flag must NOT emit.

    Two exceptions inside the no-trigger contract:
      * GEX-basis flag (CR-09) does not fire (correctly) because levels
        are empty.
      * CR-10 regime flag does not fire because gex_signal is None.
      * CR-28/29 narrative rules still fire when scorer.direction is 0
        and bar close==open — the scene is designed around that sentinel.

    For each CR-XX we call evaluate() with ``cfg_overrides`` disabled
    (calibration-gated stubs stay off) so the unconditional stubs also
    produce nothing.
    """
    spec = CR_EXPECTATIONS[cr_id]
    annotations = evaluate(
        [], None,
        SimpleNamespace(close=0.0, open=0.0, high=0.0, low=0.0,
                        timestamp=time.time(), bar_delta=0, total_vol=0),
        _scorer(direction=0, tier=SignalTier.QUIET, score=10.0),
        config=ConfluenceRulesConfig(),  # all defaults; calibration-gated remain off
    )
    expected_flag = spec.get("flag")
    if expected_flag is not None:
        assert expected_flag not in annotations.flags, (
            f"{cr_id}: no-trigger case still emitted flag {expected_flag!r}"
        )
    expected_veto = spec.get("veto")
    if expected_veto is not None:
        assert expected_veto not in annotations.vetoes, (
            f"{cr_id}: no-trigger case still emitted veto {expected_veto!r}"
        )


def test_cr_audit_rule_hit_trail():
    """rule_hits audit trail records every triggered rule."""
    # Combine several triggers so we see multiple rule_hits entries
    levels = [
        _lv(LevelKind.PUT_WALL, price=18475.0, is_zone=False),
        _lv(LevelKind.ABSORB, price=18475.0, direction=+1),
        _lv(LevelKind.CALL_WALL, price=18525.0, is_zone=False),
        _lv(LevelKind.EXHAUST, price=18525.0, direction=-1),
    ]
    annotations = evaluate(
        levels, None, _bar(), _scorer(), config=ConfluenceRulesConfig(),
    )
    rule_ids_hit = {rid for rid, _ in annotations.rule_hits}
    assert "CR-01" in rule_ids_hit
    assert "CR-02" in rule_ids_hit


def test_cr_calibration_gated_off_by_default():
    """Calibration-gated rules produce no flags under default config."""
    annotations = evaluate(
        [], None, _bar(), _scorer(), config=ConfluenceRulesConfig(),
    )
    # The 9 calibration-gated stubs each have a distinctive flag name
    gated_flags = {
        "LAST_30_MIN_STUB", "CHARM_DRIFT_STUB", "ZERO_DTE_GUARD_STUB",
        "NEG_GAMMA_RISK_SCALAR_STUB", "VPIN_REGIME_STUB",
        "CLUSTER_POISSON_STUB",
    }
    assert not (gated_flags & annotations.flags), (
        f"Calibration-gated flags leaked by default: "
        f"{gated_flags & annotations.flags}"
    )
