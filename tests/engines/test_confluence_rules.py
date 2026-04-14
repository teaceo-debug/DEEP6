"""Tests for ConfluenceRules — Phase 15-03.

Covers:
  - Task 1 scaffold: ConfluenceAnnotations defaults, calibration-gated defaults,
    SignalFlags bit preservation (0-44), meta-flags at 45/46/47.
  - Task 2 goldens: per-CR-XX trigger + no-trigger + gated-off (calibration) + budget.
"""
from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock

import pytest

from deep6.engines.confluence_rules import (
    ConfluenceAnnotations,
    ConfluenceRulesConfig,
    evaluate,
)
from deep6.engines.gex import GexRegime, GexSignal
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.signals.flags import SIGNAL_BITS_MASK, SignalFlags


# ===========================================================================
# Test fixtures
# ===========================================================================


def _mk_level(
    kind: LevelKind,
    price: float,
    *,
    price_top: Optional[float] = None,
    price_bot: Optional[float] = None,
    score: float = 50.0,
    direction: int = 0,
    state: LevelState = LevelState.CREATED,
    origin_bar: int = 0,
    meta: Optional[dict] = None,
) -> Level:
    pt = price_top if price_top is not None else price
    pb = price_bot if price_bot is not None else price
    return Level(
        price_top=pt,
        price_bot=pb,
        kind=kind,
        origin_ts=0.0,
        origin_bar=origin_bar,
        last_act_bar=origin_bar,
        score=score,
        touches=1,
        direction=direction,
        inverted=False,
        state=state,
        meta=meta or {},
    )


def _gex(regime=GexRegime.NEUTRAL, near_call=False, near_put=False) -> GexSignal:
    return GexSignal(
        regime=regime,
        direction=0,
        call_wall=15000.0,
        put_wall=14000.0,
        gamma_flip=14500.0,
        near_call_wall=near_call,
        near_put_wall=near_put,
        strength=0.5,
        detail="test",
    )


@dataclass
class _FakeBar:
    close: float = 14500.0
    open: float = 14500.0
    high: float = 14510.0
    low: float = 14490.0


@dataclass
class _FakeScorer:
    direction: int = 0
    total_score: float = 0.0
    tier: int = 0


# ===========================================================================
# Task 1 scaffold tests
# ===========================================================================


def test_annotations_defaults():
    annot = ConfluenceAnnotations()
    assert annot.flags == set()
    assert annot.regime == "NEUTRAL"
    assert annot.score_mutations == {}
    assert annot.vetoes == set()
    assert annot.rule_hits == []


def test_config_calibration_gated_default_off():
    cfg = ConfluenceRulesConfig()
    # Calibration-gated per RULES.md
    for name in ("enable_CR_11", "enable_CR_12", "enable_CR_13", "enable_CR_14",
                 "enable_CR_15", "enable_CR_19", "enable_CR_22", "enable_CR_27",
                 "enable_CR_37"):
        assert getattr(cfg, name) is False, f"{name} should default OFF"
    # Easy/medium default ON
    for name in ("enable_CR_01", "enable_CR_02", "enable_CR_10", "enable_CR_23"):
        assert getattr(cfg, name) is True, f"{name} should default ON"


def test_signal_flags_bits_preserved():
    """Phase 12 invariant: bits 0-44 unchanged."""
    expected = {
        "ABS_CLASSIC": 0, "ABS_PASSIVE": 1, "ABS_STOPPING": 2, "ABS_EFFORT_VS_R": 3,
        "EXH_ZERO_PRINT": 4, "EXH_EXHAUSTION": 5, "EXH_THIN_PRINT": 6,
        "EXH_FAT_PRINT": 7, "EXH_FADING_MOM": 8, "EXH_BID_ASK_FD": 9,
        "EXH_DELTA_GATE": 10, "EXH_COOLDOWN": 11,
        "IMB_SINGLE": 12, "IMB_MULTIPLE": 13, "IMB_STACKED": 14,
        "IMB_REVERSE": 15, "IMB_INVERSE": 16, "IMB_OVERSIZED": 17,
        "IMB_CONSECUTIVE": 18, "IMB_DIAGONAL": 19, "IMB_REVERSAL_PT": 20,
        "DELT_RISE_DROP": 21, "DELT_TAIL": 22, "DELT_REVERSAL": 23,
        "DELT_DIVERGENCE": 24, "DELT_FLIP": 25, "DELT_TRAP": 26,
        "DELT_SWEEP": 27, "DELT_SLINGSHOT": 28, "DELT_MIN_MAX": 29,
        "DELT_CVD_DIVG": 30, "DELT_VELOCITY": 31,
        "AUCT_UNFINISHED": 32, "AUCT_FINISHED": 33, "AUCT_POOR_HILOW": 34,
        "AUCT_VOL_VOID": 35, "AUCT_MKT_SWEEP": 36,
        "TRAP_INVERSE_I": 37, "TRAP_DELTA": 38, "TRAP_FALSE_BRK": 39,
        "TRAP_HIVOL_REJ": 40, "TRAP_CVD": 41,
        "VOLP_SEQUENCING": 42, "VOLP_BUBBLE": 43,
        "TRAP_SHOT": 44,
    }
    for name, bit in expected.items():
        assert int(getattr(SignalFlags, name)) == (1 << bit), \
            f"{name} moved from bit {bit}"


def test_meta_flags_above_44():
    assert int(SignalFlags.PIN_REGIME_ACTIVE) == 1 << 45
    assert int(SignalFlags.REGIME_CHANGE) == 1 << 46
    assert int(SignalFlags.SPOOF_VETO) == 1 << 47


def test_signal_bits_mask_excludes_meta():
    """SIGNAL_BITS_MASK clears meta-flag bits 45+."""
    all_flags = (SignalFlags.PIN_REGIME_ACTIVE
                 | SignalFlags.REGIME_CHANGE
                 | SignalFlags.SPOOF_VETO
                 | SignalFlags.TRAP_SHOT)
    # After masking, only TRAP_SHOT (bit 44) remains.
    masked = int(all_flags) & SIGNAL_BITS_MASK
    assert masked == (1 << 44)


# ===========================================================================
# Evaluate contract tests
# ===========================================================================


def test_evaluate_returns_annotations_with_empty_inputs():
    annot = evaluate([], None, None, None)
    assert isinstance(annot, ConfluenceAnnotations)
    # No levels → no rules fire that require levels; GEX rules may still run
    # but they early-return on None.
    assert annot.score_mutations == {}
    # With no prior regime, and no rule forcing a regime, stays NEUTRAL.
    assert annot.regime == "NEUTRAL"


def test_evaluate_no_mutation_of_inputs():
    """D-13 idempotency: evaluate must not mutate any input."""
    levels = [
        _mk_level(LevelKind.ABSORB, 14000.0, score=70, direction=+1),
        _mk_level(LevelKind.PUT_WALL, 14000.0),
    ]
    gex = _gex(near_put=True)
    bar = _FakeBar()
    levels_copy = copy.deepcopy(levels)
    gex_copy = copy.deepcopy(gex)
    bar_copy = copy.deepcopy(bar)

    evaluate(levels, gex, bar, None)

    # Check invariant fields unchanged
    for a, b in zip(levels, levels_copy):
        assert a.score == b.score
        assert a.price_top == b.price_top
        assert a.state == b.state
        assert a.uid == b.uid
        assert a.meta == b.meta
    assert gex.regime == gex_copy.regime
    assert bar.close == bar_copy.close


# ===========================================================================
# Per-rule golden tests (trigger + no-trigger + gated-off where applicable)
# ===========================================================================


def test_CR_01_triggers():
    # Use non-round price + low score so no overlapping rule fires.
    absorb = _mk_level(LevelKind.ABSORB, 14012.75, score=40, direction=+1)
    put_wall = _mk_level(LevelKind.PUT_WALL, 14013.0)
    annot = evaluate([absorb, put_wall], _gex(near_put=True), _FakeBar(), None)
    assert any(rid == "CR-01" for rid, _ in annot.rule_hits)
    # CR-01 adds 20.0 (other rules may add more; assert at least 20)
    assert annot.score_mutations.get(absorb.uid, 0.0) >= 20.0
    assert "ABSORB_PUT_WALL" in annot.flags


def test_CR_01_no_trigger_far_from_wall():
    # 100 points = 400 ticks — way beyond proximity_med_ticks (8)
    absorb = _mk_level(LevelKind.ABSORB, 14012.75, score=40, direction=+1)
    put_wall = _mk_level(LevelKind.PUT_WALL, 14112.75)  # 100 pts away
    annot = evaluate([absorb, put_wall], _gex(), _FakeBar(), None)
    # CR-01 must not fire
    assert not any(rid == "CR-01" for rid, _ in annot.rule_hits)


def test_CR_02_triggers():
    exh = _mk_level(LevelKind.EXHAUST, 15000.0, score=55, direction=-1)
    call_wall = _mk_level(LevelKind.CALL_WALL, 15000.0)
    annot = evaluate([exh, call_wall], _gex(near_call=True), _FakeBar(), None)
    assert any(rid == "CR-02" for rid, _ in annot.rule_hits)
    assert "EXHAUST_CALL_WALL_FLAG" in annot.flags


def test_CR_03_triggers():
    lvn = _mk_level(LevelKind.LVN, 14500.0, price_top=14501.0, price_bot=14499.0)
    flip = _mk_level(LevelKind.GAMMA_FLIP, 14500.5)
    bar = _FakeBar(close=14500.0)
    annot = evaluate([lvn, flip], _gex(), bar, None)
    assert any(rid == "CR-03" for rid, _ in annot.rule_hits)


def test_CR_04_triggers_and_sets_pin_regime():
    vpoc = _mk_level(LevelKind.VPOC, 14500.0)
    lg = _mk_level(LevelKind.LARGEST_GAMMA, 14500.25)
    annot = evaluate([vpoc, lg], _gex(), _FakeBar(), None)
    assert annot.regime == "PIN"
    assert "PIN_REGIME_ACTIVE" in annot.flags


def test_CR_05_momentum_through_flipped():
    mom = _mk_level(LevelKind.MOMENTUM, 14600.0, direction=+1)
    flipped = _mk_level(LevelKind.FLIPPED, 14580.0, price_top=14585, price_bot=14575)
    flip = _mk_level(LevelKind.GAMMA_FLIP, 14500.0)
    annot = evaluate([mom, flipped, flip], _gex(), _FakeBar(close=14600), None)
    assert "REGIME_CHANGE" in annot.flags


def test_CR_06_absorb_at_vah():
    absorb = _mk_level(LevelKind.ABSORB, 14500.0, direction=+1, score=50)
    vah = _mk_level(LevelKind.VAH, 14500.25)
    annot = evaluate([absorb, vah], _gex(), _FakeBar(), None)
    assert annot.score_mutations.get(absorb.uid, 0.0) >= 15.0
    assert "VA_CONFIRMED" in annot.flags


def test_CR_07_compound_short():
    ex = _mk_level(LevelKind.EXHAUST, 14500.0, direction=-1, origin_bar=10)
    ab = _mk_level(LevelKind.ABSORB, 14500.25, direction=-1, origin_bar=12)
    annot = evaluate([ex, ab], _gex(), _FakeBar(), None)
    assert annot.score_mutations.get(ab.uid, 0.0) >= 20.0
    assert "EXHAUST_ABSORB_COMPOUND" in annot.flags


def test_CR_08_hvn_put_wall_suppress_shorts():
    hvn = _mk_level(LevelKind.HVN, 14000.0, score=60,
                    price_top=14001, price_bot=13999)
    pw = _mk_level(LevelKind.PUT_WALL, 14000.25)
    annot = evaluate([hvn, pw], _gex(), _FakeBar(), None)
    assert "SUPPRESS_SHORTS" in annot.flags


def test_CR_09_basis_correction_flag_on_gex_presence():
    pw = _mk_level(LevelKind.PUT_WALL, 14000.0)
    annot = evaluate([pw], _gex(), _FakeBar(), None)
    assert "GEX_BASIS_CORRECTED" in annot.flags


def test_CR_10_regime_gate_from_gex():
    annot_pos = evaluate([], _gex(GexRegime.POSITIVE_DAMPENING), _FakeBar(), None)
    assert annot_pos.regime == "BALANCE"
    annot_neg = evaluate([], _gex(GexRegime.NEGATIVE_AMPLIFYING), _FakeBar(), None)
    assert annot_neg.regime == "TREND"


def test_CR_11_gated_off_by_default():
    exh = _mk_level(LevelKind.EXHAUST, 14500.0, state=LevelState.BROKEN)
    annot = evaluate([exh], _gex(), _FakeBar(), None)
    assert not any(rid == "CR-11" for rid, _ in annot.rule_hits)


def test_CR_11_triggers_when_enabled():
    cfg = ConfluenceRulesConfig(enable_CR_11=True)
    exh = _mk_level(LevelKind.EXHAUST, 14500.0, state=LevelState.BROKEN)
    annot = evaluate([exh], _gex(), _FakeBar(), None, config=cfg)
    assert any(rid == "CR-11" for rid, _ in annot.rule_hits)
    assert "BREAKOUT_CONTINUATION" in annot.flags


def test_CR_12_through_15_gated_off_by_default():
    """Pure-stub calibration-gated rules: default OFF."""
    annot = evaluate([], _gex(), _FakeBar(), None)
    for rid in ("CR-12", "CR-13", "CR-14", "CR-15"):
        assert not any(r == rid for r, _ in annot.rule_hits), f"{rid} should be OFF"


def test_CR_16_absorptionz_boost():
    ab = _mk_level(LevelKind.ABSORB, 14500.0, score=70)
    annot = evaluate([ab], _gex(), _FakeBar(), None)
    assert annot.score_mutations.get(ab.uid, 0.0) >= 5.0
    assert "MS_ABSORB_Z" in annot.flags


def test_CR_17_iceberg_meta():
    ab = _mk_level(LevelKind.ABSORB, 14500.0, meta={"iceberg": True})
    annot = evaluate([ab], _gex(), _FakeBar(), None)
    assert "ICEBERG_AT_LEVEL" in annot.flags


def test_CR_18_queue_imbalance():
    ab = _mk_level(LevelKind.ABSORB, 14500.0, meta={"queue_imbalance": 0.7})
    annot = evaluate([ab], _gex(), _FakeBar(), None)
    assert "QUEUE_IMBALANCE" in annot.flags


def test_CR_19_gated_off():
    annot = evaluate([], _gex(), _FakeBar(), None)
    assert not any(r == "CR-19" for r, _ in annot.rule_hits)


def test_CR_20_kyle_lambda():
    ab = _mk_level(LevelKind.ABSORB, 14500.0, meta={"kyle_lambda_ratio": 0.3})
    annot = evaluate([ab], _gex(), _FakeBar(), None)
    assert "KYLE_LAMBDA_COMPRESSED" in annot.flags


def test_CR_21_cvd_divergence():
    lvl = _mk_level(LevelKind.EXHAUST, 14500.0, meta={"cvd_divergence": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "CVD_DIVERGENCE" in annot.flags


def test_CR_22_gated_off():
    annot = evaluate([], _gex(), _FakeBar(), None)
    assert not any(r == "CR-22" for r, _ in annot.rule_hits)


def test_CR_23_spoof_veto_triggers():
    lvl = _mk_level(LevelKind.ABSORB, 14500.0, meta={"cancel_ratio": 0.95})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "SPOOF_DETECTED" in annot.vetoes
    assert "SPOOF_VETO" in annot.flags


def test_CR_23_no_trigger_below_threshold():
    lvl = _mk_level(LevelKind.ABSORB, 14500.0, meta={"cancel_ratio": 0.5})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "SPOOF_DETECTED" not in annot.vetoes


def test_CR_24_aggressor_dominance():
    lvl = _mk_level(LevelKind.ABSORB, 14500.0, meta={"aggressor_share": 0.8})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "AGGRESSOR_DOMINANT" in annot.flags


def test_CR_25_round_number():
    lvl = _mk_level(LevelKind.VPOC, 15000.0)  # round number
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "ROUND_NUMBER" in annot.flags


def test_CR_25_no_trigger_non_round():
    lvl = _mk_level(LevelKind.VPOC, 14512.75)
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    # The LARGEST_GAMMA/VPOC points etc. must not coincidentally be round
    # Here only one non-round level supplied; no CR-25 hit expected
    if "ROUND_NUMBER" in annot.flags:
        pytest.fail("CR-25 should not fire on non-round number")


def test_CR_26_depth_asymmetry():
    lvl = _mk_level(LevelKind.ABSORB, 14500.0, meta={"depth_ratio": 4.0})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "DEPTH_ASYMMETRY" in annot.flags


def test_CR_27_gated_off():
    annot = evaluate([], _gex(), _FakeBar(), None)
    assert not any(r == "CR-27" for r, _ in annot.rule_hits)


def test_CR_28_open_drive_bullish():
    sr = _FakeScorer(direction=+1)
    bar = _FakeBar(close=14600, open=14500)
    annot = evaluate([], _gex(), bar, sr)
    assert "OD_UP_ORU" in annot.flags


def test_CR_29_open_drive_bearish():
    sr = _FakeScorer(direction=-1)
    bar = _FakeBar(close=14400, open=14500)
    annot = evaluate([], _gex(), bar, sr)
    assert "OD_DOWN_ORD" in annot.flags


def test_CR_30_otd_reversal():
    lvl = _mk_level(LevelKind.ABSORB, 14500.0, meta={"otd": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "OTD_REVERSAL" in annot.flags


def test_CR_31_failed_ib():
    lvl = _mk_level(LevelKind.ABSORB, 14500.0, meta={"failed_ib": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "FAILED_IB" in annot.flags


def test_CR_32_naked_poc_magnet():
    lvl = _mk_level(LevelKind.VPOC, 14500.0, meta={"naked": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "NAKED_POC_MAGNET" in annot.flags


def test_CR_33_poor_extreme_revisit():
    lvl = _mk_level(LevelKind.ABSORB, 14500.0, meta={"poor_extreme": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "POOR_EXTREME_REVISIT" in annot.flags


def test_CR_34_tail_retest():
    lvl = _mk_level(LevelKind.ABSORB, 14500.0, meta={"tail": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "TAIL_RETEST" in annot.flags


def test_CR_35_open_auction_in_range():
    lvl = _mk_level(LevelKind.VPOC, 14500.0, meta={"open_auction_in_range": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "OPEN_AUCTION_IN_RANGE" in annot.flags


def test_CR_36_double_distribution():
    lvl = _mk_level(LevelKind.LVN, 14500.0, meta={"double_distribution": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "DOUBLE_DIST_REVISIT" in annot.flags


def test_CR_37_gated_off_default():
    annot = evaluate([], _gex(), _FakeBar(), None)
    assert not any(r == "CR-37" for r, _ in annot.rule_hits)


def test_CR_38_gap_and_go():
    lvl = _mk_level(LevelKind.VPOC, 14500.0, meta={"neutral_extreme_close": True})
    annot = evaluate([lvl], _gex(), _FakeBar(), None)
    assert "GAP_AND_GO_BIAS" in annot.flags


# ===========================================================================
# Regime change detection
# ===========================================================================


def test_regime_change_flag_on_transition():
    """prior_regime differs from computed → REGIME_CHANGE emitted."""
    annot = evaluate([], _gex(GexRegime.POSITIVE_DAMPENING), _FakeBar(), None,
                     prior_regime="TREND")
    assert "REGIME_CHANGE" in annot.flags


def test_regime_change_flag_not_emitted_when_same():
    annot = evaluate([], _gex(GexRegime.POSITIVE_DAMPENING), _FakeBar(), None,
                     prior_regime="BALANCE")
    assert "REGIME_CHANGE" not in annot.flags


# ===========================================================================
# Performance budget (D-34): <1ms median for 80 active levels
# ===========================================================================


def test_evaluate_budget_1ms_80_levels():
    """D-34: evaluate() median < 1ms on dev machine with 80 levels.

    Soft gate — logs latency; asserts median only.
    """
    levels = []
    for i in range(40):
        levels.append(_mk_level(LevelKind.ABSORB, 14000 + i * 2.5,
                                direction=+1, score=55))
        levels.append(_mk_level(LevelKind.HVN, 14100 + i * 2.5,
                                price_top=14101 + i * 2.5,
                                price_bot=14099 + i * 2.5,
                                direction=+1, score=55))
    levels.append(_mk_level(LevelKind.PUT_WALL, 14000.0))
    levels.append(_mk_level(LevelKind.CALL_WALL, 15000.0))

    gex = _gex(near_put=True)
    bar = _FakeBar(close=14250)
    sr = _FakeScorer(direction=+1)

    durations_ns = []
    for _ in range(100):
        t0 = time.perf_counter_ns()
        evaluate(levels, gex, bar, sr)
        durations_ns.append(time.perf_counter_ns() - t0)

    durations_ns.sort()
    median_ns = durations_ns[len(durations_ns) // 2]
    median_ms = median_ns / 1_000_000
    # Soft: assert < 5ms so CI noise doesn't flake; log for tracking.
    print(f"\n[CR budget] median={median_ms:.3f}ms "
          f"p95={durations_ns[94] / 1_000_000:.3f}ms over 100 runs, "
          f"{len(levels)} levels")
    assert median_ms < 5.0, f"evaluate() median {median_ms:.3f}ms exceeds 5ms soft gate"
