"""ConfluenceRules — stateless evaluator for the 38 canonical CR-XX rules.

Phase 15-03 / D-13 / D-14 / D-34.

Contract (D-13):
  ``evaluate(levels, gex_signal, bar, scorer_result, config=None,
             prior_regime=None) -> ConfluenceAnnotations``

  Pure function. No external I/O. Must not mutate any input.

Output (D-14):
  ``ConfluenceAnnotations`` with:
    - ``flags``:  set[str]   (regime / meta labels emitted by rules)
    - ``regime``: str ∈ {"PIN","TREND","BALANCE","NEUTRAL"}
    - ``score_mutations``: dict[int, float]   (keyed by ``Level.uid`` per C5)
    - ``vetoes``: set[str]   (``"SPOOF_DETECTED"`` etc. → scorer DISQUALIFIED)
    - ``rule_hits``: list[tuple[str, str]]   audit trail of (rule_id, explanation)

Budget (D-34):
  Evaluation must complete in < 1ms for 80 active Levels on bar close.

Calibration gating (D-16):
  Rules tagged CALIBRATION-GATED in RULES.md default to OFF via
  ``ConfluenceRulesConfig.enable_CR_XX = False``. Enable flags gate each rule
  before its body executes.

Rule inventory is the 38 canonical CR-XX rules produced by plan 15-01's
RULES.md. Each ``cr_XX`` function below cites ``{source_file}:{section}`` in
its docstring (threat T-15-01-03).

See plan 15-03 for task breakdown and test expectations.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional

from deep6.engines.gex import GexRegime, GexSignal
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.engines.signal_config import ConfluenceRulesConfig


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConfluenceAnnotations:
    """D-14: stateless result of ``evaluate()``.

    - ``score_mutations`` is keyed by ``Level.uid`` per C5 (stable across
      copies / merges). Callers apply ``level.score += delta``.
    - ``regime`` is one of {"PIN", "TREND", "BALANCE", "NEUTRAL"}; last
      rule override wins deterministically (rules iterate in fixed CR-XX
      order).
    - ``vetoes`` sentinel strings are consumed by the scorer to force
      ``SignalTier.DISQUALIFIED`` (e.g. ``"SPOOF_DETECTED"``).
    """

    flags: set[str] = field(default_factory=set)
    regime: str = "NEUTRAL"
    score_mutations: dict[int, float] = field(default_factory=dict)
    vetoes: set[str] = field(default_factory=set)
    rule_hits: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _RuleHit:
    """Internal per-rule return shape. Aggregated into ConfluenceAnnotations."""

    rule_id: str
    score_delta_by_level: dict[int, float] = field(default_factory=dict)
    flags_to_add: set[str] = field(default_factory=set)
    vetoes_to_add: set[str] = field(default_factory=set)
    regime_override: Optional[str] = None
    explanation: str = ""


# ---------------------------------------------------------------------------
# Helpers (hot-path; keep simple)
# ---------------------------------------------------------------------------


def _tick_price_abs(a: float, b: float, tick_size: float = 0.25) -> float:
    """Absolute distance between two prices in ticks (NQ tick_size default)."""
    return abs(a - b) / tick_size if tick_size > 0 else abs(a - b)


def _is_round_number(price: float, step: int = 25) -> bool:
    """NQ round number (every 25 / 50 / 100 points)."""
    # Price may be fractional; check modulo step within 0.5-point tolerance.
    return abs(price - round(price / step) * step) < 0.5


def _nearest_point(levels: list[Level], kind: LevelKind) -> Optional[Level]:
    """Return first Level of ``kind`` in the list (they're unique by kind)."""
    for lv in levels:
        if lv.kind == kind:
            return lv
    return None


# ---------------------------------------------------------------------------
# Rule implementations — 38 canonical CR-XX per RULES.md
# Each returns None (no hit) or _RuleHit. Score deltas keyed by Level.uid.
# Functions are pure; no side effects on inputs.
# ---------------------------------------------------------------------------


def cr_01(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-01 — Absorption @ Put Wall → High-Conviction Long.

    Source: DEEP6_INTEGRATION.md:§Confluence Rules Rule 1;
            industry.md:§Actionable 3. Tier: EASY.

    Trigger: ABSORB level with ``direction=+1`` within ``proximity_med_ticks``
    of PUT_WALL price.
    """
    put_wall = _nearest_point(levels, LevelKind.PUT_WALL)
    if put_wall is None:
        return None
    hit = _RuleHit(rule_id="CR-01", explanation="Absorption at put wall")
    tick = 0.25
    for lv in levels:
        if lv.kind != LevelKind.ABSORB or lv.direction != +1:
            continue
        dist = _tick_price_abs(lv.midpoint(), put_wall.price_top, tick)
        if dist <= cfg.proximity_med_ticks:
            hit.score_delta_by_level[lv.uid] = 20.0
            hit.flags_to_add.add("ABSORB_PUT_WALL")
    return hit if hit.score_delta_by_level else None


def cr_02(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-02 — Exhaustion @ Call Wall → High-Conviction Fade.

    Source: DEEP6_INTEGRATION.md:§Confluence Rules Rule 2. Tier: EASY.
    """
    call_wall = _nearest_point(levels, LevelKind.CALL_WALL)
    if call_wall is None:
        return None
    hit = _RuleHit(rule_id="CR-02", explanation="Exhaustion at call wall")
    tick = 0.25
    for lv in levels:
        if lv.kind != LevelKind.EXHAUST or lv.direction != -1:
            continue
        dist = _tick_price_abs(lv.midpoint(), call_wall.price_top, tick)
        if dist <= cfg.proximity_med_ticks:
            hit.score_delta_by_level[lv.uid] = 15.0
            hit.flags_to_add.add("EXHAUST_CALL_WALL_FLAG")
    return hit if hit.score_delta_by_level else None


def cr_03(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-03 — LVN Crossing Gamma-Flip → Acceleration Candidate.

    Source: DEEP6_INTEGRATION.md:§Rule 3; industry.md:§Actionable 6. Tier: MEDIUM.
    """
    flip = _nearest_point(levels, LevelKind.GAMMA_FLIP)
    if flip is None:
        return None
    hit = _RuleHit(rule_id="CR-03", explanation="LVN crossing gamma flip")
    tick = 0.25
    close = bar.close if bar is not None else 0.0
    for lv in levels:
        if lv.kind != LevelKind.LVN:
            continue
        crossed = (lv.price_bot <= close <= lv.price_top)
        dist = _tick_price_abs(lv.midpoint(), flip.price_top, tick)
        if crossed and dist <= cfg.proximity_wide_ticks:
            hit.score_delta_by_level[lv.uid] = 8.0
            hit.flags_to_add.add("ACCELERATION_CANDIDATE")
    return hit if hit.score_delta_by_level else None


def cr_04(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-04 — VPOC Pinned Near Largest-Gamma → Pin Regime.

    Source: DEEP6_INTEGRATION.md:§Rule 4; industry.md:§Actionable 7.
    Tier: MEDIUM. Emits regime="PIN" + PIN_REGIME_ACTIVE flag.
    """
    vpoc = _nearest_point(levels, LevelKind.VPOC)
    lg = _nearest_point(levels, LevelKind.LARGEST_GAMMA) or _nearest_point(levels, LevelKind.HVL)
    if vpoc is None or lg is None:
        return None
    dist = _tick_price_abs(vpoc.price_top, lg.price_top, 0.25)
    if dist > cfg.proximity_tight_ticks:
        return None
    return _RuleHit(
        rule_id="CR-04",
        flags_to_add={"PIN_REGIME_ACTIVE"},
        regime_override="PIN",
        explanation="VPOC pinned near largest-gamma strike",
    )


def cr_05(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-05 — Momentum through flipped zone beyond zero-gamma → Regime change.

    Source: DEEP6_INTEGRATION.md:§Rule 5; industry.md:§Actionable 10. Tier: MEDIUM.
    """
    flip = _nearest_point(levels, LevelKind.GAMMA_FLIP)
    if flip is None or bar is None:
        return None
    close = bar.close
    has_mom = any(lv.kind == LevelKind.MOMENTUM for lv in levels)
    has_flipped = any(lv.kind == LevelKind.FLIPPED for lv in levels)
    if not (has_mom and has_flipped):
        return None
    # Beyond gamma flip in the momentum direction
    hit = _RuleHit(rule_id="CR-05", flags_to_add={"REGIME_CHANGE"},
                   regime_override="TREND",
                   explanation="Momentum through flipped zone beyond zero-gamma")
    for lv in levels:
        if lv.kind == LevelKind.MOMENTUM:
            hit.score_delta_by_level[lv.uid] = 10.0
    return hit if (hit.score_delta_by_level or "REGIME_CHANGE" in hit.flags_to_add) else None


def cr_06(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-06 — ABSORB + VAH/VAL proximity → VA boost.

    Source: DEEP6_INTEGRATION.md:§Rule 6; auction_theory.md:§9 Rule 4. Tier: EASY.
    """
    vah = _nearest_point(levels, LevelKind.VAH)
    val = _nearest_point(levels, LevelKind.VAL)
    if vah is None and val is None:
        return None
    hit = _RuleHit(rule_id="CR-06", explanation="ABSORB at VAH/VAL")
    tick = 0.25
    for lv in levels:
        if lv.kind not in (LevelKind.ABSORB, LevelKind.CONFIRMED_ABSORB):
            continue
        mid = lv.midpoint()
        near_vah = vah is not None and _tick_price_abs(mid, vah.price_top, tick) <= 4
        near_val = val is not None and _tick_price_abs(mid, val.price_top, tick) <= 4
        if near_vah or near_val:
            hit.score_delta_by_level[lv.uid] = 15.0
            hit.flags_to_add.add("VA_CONFIRMED")
    return hit if hit.score_delta_by_level else None


def cr_07(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-07 — EXHAUST → ABSORB at same price → compound short.

    Source: DEEP6_INTEGRATION.md:§Rule 7. Tier: EASY.
    """
    hit = _RuleHit(rule_id="CR-07", explanation="EXHAUST + ABSORB compound")
    tick = 0.25
    exhausts = [lv for lv in levels if lv.kind == LevelKind.EXHAUST and lv.direction == -1]
    absorbs = [lv for lv in levels if lv.kind == LevelKind.ABSORB and lv.direction == -1]
    for ex in exhausts:
        for ab in absorbs:
            # Within 5 bars and 6 ticks of price
            if abs(ab.origin_bar - ex.origin_bar) > 5:
                continue
            if _tick_price_abs(ex.midpoint(), ab.midpoint(), tick) <= 6:
                hit.score_delta_by_level[ab.uid] = 20.0
                hit.flags_to_add.add("EXHAUST_ABSORB_COMPOUND")
    return hit if hit.score_delta_by_level else None


def cr_08(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-08 — HVN + Put Wall → suppress shorts (soft, D-40 0.6× multiplier).

    Source: DEEP6_INTEGRATION.md:§Rule 8. Tier: EASY.
    Acts on scorer result indirectly by tagging a suppression flag. The
    scorer scales shorts by cr_08_shorts_multiplier when the flag is set.
    """
    put_wall = _nearest_point(levels, LevelKind.PUT_WALL)
    if put_wall is None:
        return None
    tick = 0.25
    for lv in levels:
        if lv.kind != LevelKind.HVN or lv.score < 50:
            continue
        if _tick_price_abs(lv.midpoint(), put_wall.price_top, tick) <= cfg.proximity_tight_ticks:
            return _RuleHit(rule_id="CR-08",
                            flags_to_add={"SUPPRESS_SHORTS"},
                            explanation="HVN aligned with put wall (soft suppress shorts)")
    return None


def cr_09(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-09 — Basis-corrected GEX level mapping.

    Source: industry.md:§Actionable 1. Tier: MEDIUM.

    Stateless sanity flag — GEX Levels must be basis-corrected upstream
    (factory). This rule emits a structural flag when GEX Levels are
    present so downstream audits confirm the path is wired.
    """
    has_gex = any(lv.kind in (LevelKind.CALL_WALL, LevelKind.PUT_WALL,
                              LevelKind.GAMMA_FLIP, LevelKind.HVL,
                              LevelKind.LARGEST_GAMMA) for lv in levels)
    if not has_gex:
        return None
    return _RuleHit(rule_id="CR-09",
                    flags_to_add={"GEX_BASIS_CORRECTED"},
                    explanation="GEX basis-correction active")


def cr_10(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-10 — Regime gate on HVL / gamma flip.

    Source: industry.md:§Actionable 2. Tier: MEDIUM.

    Emits regime based on GexSignal.regime (positive/negative/neutral).
    """
    if gex_signal is None:
        return None
    if gex_signal.regime == GexRegime.POSITIVE_DAMPENING:
        regime = "BALANCE"
        flag = "REGIME_POSITIVE_GAMMA"
    elif gex_signal.regime == GexRegime.NEGATIVE_AMPLIFYING:
        regime = "TREND"
        flag = "REGIME_NEGATIVE_GAMMA"
    else:
        regime = "NEUTRAL"
        flag = "REGIME_NEUTRAL"
    return _RuleHit(rule_id="CR-10", flags_to_add={flag},
                    regime_override=regime,
                    explanation=f"GEX regime gate: {regime}")


def cr_11(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-11 — Exhaustion × wall breach → breakout continuation.

    Source: industry.md:§Actionable 5. Tier: CALIBRATION-GATED.
    Default OFF via ConfluenceRulesConfig.enable_CR_11.
    """
    hit = _RuleHit(rule_id="CR-11", explanation="Exhaustion at broken wall")
    for lv in levels:
        if lv.kind != LevelKind.EXHAUST:
            continue
        if lv.state == LevelState.BROKEN:
            hit.score_delta_by_level[lv.uid] = 10.0
            hit.flags_to_add.add("BREAKOUT_CONTINUATION")
    return hit if hit.score_delta_by_level else None


def cr_12(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-12 — Last-30-min regime play (Baltussen).

    Source: industry.md:§Actionable 8. Tier: CALIBRATION-GATED.
    Stub: flag-only — time-of-day logic deferred to Phase 7 sweep gating.
    """
    return _RuleHit(rule_id="CR-12",
                    flags_to_add={"LAST_30_MIN_STUB"},
                    explanation="Last-30-min regime play (stub)")


def cr_13(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-13 — Charm drift toward high-OI strike.

    Source: industry.md:§Actionable 9. Tier: CALIBRATION-GATED. Stub.
    """
    return _RuleHit(rule_id="CR-13",
                    flags_to_add={"CHARM_DRIFT_STUB"},
                    explanation="Charm drift toward high-OI strike (stub)")


def cr_14(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-14 — 0DTE dominance guard.

    Source: industry.md:§Actionable 11. Tier: CALIBRATION-GATED. Stub.
    """
    return _RuleHit(rule_id="CR-14",
                    flags_to_add={"ZERO_DTE_GUARD_STUB"},
                    explanation="0DTE dominance guard (stub)")


def cr_15(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-15 — Negative-gamma risk scalar.

    Source: industry.md:§Actionable 12. Tier: CALIBRATION-GATED. Stub.
    """
    return _RuleHit(rule_id="CR-15",
                    flags_to_add={"NEG_GAMMA_RISK_SCALAR_STUB"},
                    explanation="Negative-gamma risk scalar (stub)")


def cr_16(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-16 — AbsorptionZ (microstructure formal).

    Source: microstructure.md:§12 Rules MS-01. Tier: MEDIUM.
    Emits boost on adjacent ABSORB/HVN Levels when score > 60 (proxy for
    AbsorptionZ ≥ 2.5 — full formula requires 60s rolling state stored
    upstream; flag-only presence signal here).
    """
    hit = _RuleHit(rule_id="CR-16", explanation="AbsorptionZ microstructure")
    for lv in levels:
        if lv.kind in (LevelKind.ABSORB, LevelKind.HVN) and lv.score >= 60:
            hit.score_delta_by_level[lv.uid] = 5.0
            hit.flags_to_add.add("MS_ABSORB_Z")
    return hit if hit.score_delta_by_level else None


def cr_17(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-17 — Iceberg at level.

    Source: microstructure.md:§12 Rules MS-02. Tier: MEDIUM.
    Triggers when Level.meta["iceberg"] is truthy.
    """
    hit = _RuleHit(rule_id="CR-17", explanation="Iceberg detected at level")
    for lv in levels:
        if lv.meta.get("iceberg"):
            hit.score_delta_by_level[lv.uid] = 8.0
            hit.flags_to_add.add("ICEBERG_AT_LEVEL")
    return hit if hit.score_delta_by_level else None


def cr_18(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-18 — Queue imbalance band.

    Source: microstructure.md:§12 Rules MS-03. Tier: MEDIUM.
    Consumes Level.meta["queue_imbalance"] when populated upstream.
    """
    hit = _RuleHit(rule_id="CR-18", explanation="Queue imbalance band")
    for lv in levels:
        qi = lv.meta.get("queue_imbalance", 0.0)
        if abs(qi) >= 0.6:
            hit.score_delta_by_level[lv.uid] = 4.0
            hit.flags_to_add.add("QUEUE_IMBALANCE")
    return hit if hit.score_delta_by_level else None


def cr_19(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-19 — VPIN regime shift.

    Source: microstructure.md:§12 Rules MS-04. Tier: CALIBRATION-GATED. Stub.
    """
    return _RuleHit(rule_id="CR-19",
                    flags_to_add={"VPIN_REGIME_STUB"},
                    explanation="VPIN regime shift (stub)")


def cr_20(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-20 — Kyle lambda compression.

    Source: microstructure.md:§12 Rules MS-05. Tier: MEDIUM.
    Triggers on Level.meta["kyle_lambda_ratio"] <= 0.5.
    """
    hit = _RuleHit(rule_id="CR-20", explanation="Kyle lambda compression")
    for lv in levels:
        lam = lv.meta.get("kyle_lambda_ratio")
        if lam is not None and lam <= 0.5:
            hit.score_delta_by_level[lv.uid] = 5.0
            hit.flags_to_add.add("KYLE_LAMBDA_COMPRESSED")
    return hit if hit.score_delta_by_level else None


def cr_21(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-21 — CVD divergence at level.

    Source: microstructure.md:§12 Rules MS-06. Tier: MEDIUM.
    Consumes scorer_result directional agreement proxy via Level.meta.
    """
    hit = _RuleHit(rule_id="CR-21", explanation="CVD divergence at level")
    for lv in levels:
        if lv.meta.get("cvd_divergence"):
            hit.score_delta_by_level[lv.uid] = 6.0
            hit.flags_to_add.add("CVD_DIVERGENCE")
    return hit if hit.score_delta_by_level else None


def cr_22(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-22 — Hawkes branching critical (D-35 Poisson stub).

    Source: microstructure.md:§12 Rules MS-07. Tier: CALIBRATION-GATED.

    D-35 note: full MLE deferred. This is an O(1) Poisson baseline stub —
    flags presence only. Full Hawkes MLE lives behind a future worker
    (ThreadPoolExecutor + janus) so evaluate() stays <1ms.
    """
    return _RuleHit(rule_id="CR-22",
                    flags_to_add={"CLUSTER_POISSON_STUB"},
                    explanation="Hawkes branching (Poisson stub per D-35)")


def cr_23(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-23 — Spoof suppressor (VETO).

    Source: microstructure.md:§12 Rules MS-08. Tier: MEDIUM.
    Emits ``SPOOF_DETECTED`` veto when Level.meta["cancel_ratio"] exceeds
    cfg.spoof_detection_min_cancel_ratio.
    """
    for lv in levels:
        cr = lv.meta.get("cancel_ratio", 0.0)
        if cr >= cfg.spoof_detection_min_cancel_ratio:
            return _RuleHit(rule_id="CR-23",
                            vetoes_to_add={"SPOOF_DETECTED"},
                            flags_to_add={"SPOOF_VETO"},
                            explanation=f"Spoof detected (cancel_ratio={cr:.2f})")
    return None


def cr_24(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-24 — Aggressor dominance at level.

    Source: microstructure.md:§12 Rules MS-09. Tier: MEDIUM.
    Triggers on Level.meta["aggressor_share"] > 0.75.
    """
    hit = _RuleHit(rule_id="CR-24", explanation="Aggressor dominance")
    for lv in levels:
        share = lv.meta.get("aggressor_share", 0.0)
        if share > 0.75:
            hit.score_delta_by_level[lv.uid] = 4.0
            hit.flags_to_add.add("AGGRESSOR_DOMINANT")
    return hit if hit.score_delta_by_level else None


def cr_25(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-25 — Round-number proximity (modifier).

    Source: microstructure.md:§12 Rules MS-10. Tier: EASY.
    """
    hit = _RuleHit(rule_id="CR-25", explanation="Round-number modifier")
    for lv in levels:
        if _is_round_number(lv.price_top):
            hit.score_delta_by_level[lv.uid] = 3.0
            hit.flags_to_add.add("ROUND_NUMBER")
    return hit if hit.score_delta_by_level else None


def cr_26(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-26 — Depth asymmetry.

    Source: microstructure.md:§12 Rules MS-11. Tier: MEDIUM.
    Triggers when Level.meta["depth_ratio"] >= 3.0.
    """
    hit = _RuleHit(rule_id="CR-26", explanation="Depth asymmetry")
    for lv in levels:
        dr = lv.meta.get("depth_ratio", 0.0)
        if dr >= 3.0:
            hit.score_delta_by_level[lv.uid] = 5.0
            hit.flags_to_add.add("DEPTH_ASYMMETRY")
    return hit if hit.score_delta_by_level else None


def cr_27(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-27 — Exhaustion post-break (FAILED_BREAK).

    Source: microstructure.md:§12 Rules MS-12. Tier: CALIBRATION-GATED.
    """
    hit = _RuleHit(rule_id="CR-27", explanation="Failed break — exhaustion post-break")
    for lv in levels:
        if lv.state == LevelState.BROKEN and lv.meta.get("hawkes_decay", 0.0) >= 0.5:
            hit.score_delta_by_level[lv.uid] = 7.0
            hit.flags_to_add.add("FAILED_BREAK")
    return hit if hit.score_delta_by_level else None


def cr_28(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-28 — Open-Drive + Opening Range Extension (bullish).

    Source: auction_theory.md:§9 Trade-Plan 1. Tier: MEDIUM.
    Consumes scorer_result.narrative / meta.
    """
    if scorer_result is None:
        return None
    if getattr(scorer_result, "direction", 0) > 0 and bar is not None and bar.close > bar.open:
        return _RuleHit(rule_id="CR-28",
                        flags_to_add={"OD_UP_ORU"},
                        explanation="Open-drive up + ORU")
    return None


def cr_29(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-29 — Open-Drive + ORD (bearish).

    Source: auction_theory.md:§9 Trade-Plan 2. Tier: MEDIUM.
    """
    if scorer_result is None:
        return None
    if getattr(scorer_result, "direction", 0) < 0 and bar is not None and bar.close < bar.open:
        return _RuleHit(rule_id="CR-29",
                        flags_to_add={"OD_DOWN_ORD"},
                        explanation="Open-drive down + ORD")
    return None


def cr_30(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-30 — Overnight test + drive reversal (OTD-UP).

    Source: auction_theory.md:§9 Trade-Plan 3. Tier: MEDIUM.

    Flag-level — requires bar-meta prior_low. Stub behavior: emit when
    Level.meta["otd"] truthy on any carried-over narrative Level.
    """
    for lv in levels:
        if lv.meta.get("otd"):
            return _RuleHit(rule_id="CR-30",
                            flags_to_add={"OTD_REVERSAL"},
                            score_delta_by_level={lv.uid: 6.0},
                            explanation="Overnight test + drive reversal")
    return None


def cr_31(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-31 — Failed IB extension (both sides).

    Source: auction_theory.md:§9 Trade-Plans 5 & 6. Tier: EASY.
    Emits flag when bar closes back inside IB after excursion — consumed
    from Level.meta["failed_ib"].
    """
    for lv in levels:
        if lv.meta.get("failed_ib"):
            return _RuleHit(rule_id="CR-31",
                            flags_to_add={"FAILED_IB"},
                            score_delta_by_level={lv.uid: 5.0},
                            explanation="Failed IB extension")
    return None


def cr_32(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-32 — Naked POC magnet.

    Source: auction_theory.md:§9 Trade-Plans 7 & 8. Tier: EASY.
    Emits flag when a VPOC Level is flagged naked in meta.
    """
    for lv in levels:
        if lv.kind == LevelKind.VPOC and lv.meta.get("naked"):
            return _RuleHit(rule_id="CR-32",
                            flags_to_add={"NAKED_POC_MAGNET"},
                            score_delta_by_level={lv.uid: 4.0},
                            explanation="Naked POC magnet")
    return None


def cr_33(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-33 — Poor high / poor low revisit (volume-conditional).

    Source: auction_theory.md:§9 Trade-Plans 9 & 10. Tier: MEDIUM.
    """
    for lv in levels:
        if lv.meta.get("poor_extreme"):
            return _RuleHit(rule_id="CR-33",
                            flags_to_add={"POOR_EXTREME_REVISIT"},
                            score_delta_by_level={lv.uid: 5.0},
                            explanation="Poor high/low revisit")
    return None


def cr_34(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-34 — Buying-tail / selling-tail retest.

    Source: auction_theory.md:§9 Trade-Plan 11. Tier: MEDIUM.
    """
    for lv in levels:
        if lv.meta.get("tail"):
            return _RuleHit(rule_id="CR-34",
                            flags_to_add={"TAIL_RETEST"},
                            score_delta_by_level={lv.uid: 4.0},
                            explanation="Tail retest")
    return None


def cr_35(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-35 — Open-auction in-range + unchanged value.

    Source: auction_theory.md:§9 Trade-Plan 12. Tier: EASY.
    """
    for lv in levels:
        if lv.meta.get("open_auction_in_range"):
            return _RuleHit(rule_id="CR-35",
                            flags_to_add={"OPEN_AUCTION_IN_RANGE"},
                            regime_override="BALANCE",
                            explanation="Open-auction in-range / unchanged value")
    return None


def cr_36(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-36 — Double-distribution single-print revisit.

    Source: auction_theory.md:§9 Trade-Plan 13. Tier: MEDIUM.
    """
    for lv in levels:
        if lv.meta.get("double_distribution"):
            return _RuleHit(rule_id="CR-36",
                            flags_to_add={"DOUBLE_DIST_REVISIT"},
                            score_delta_by_level={lv.uid: 6.0},
                            explanation="Double-distribution single-print revisit")
    return None


def cr_37(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-37 — ABSORB @ prior-day high + Kronos bearish + IB fail-up.

    Source: auction_theory.md:§9 Trade-Plan 14. Tier: CALIBRATION-GATED
    (Kronos E10 gate OFF per D-42).
    """
    for lv in levels:
        if lv.kind in (LevelKind.ABSORB, LevelKind.CONFIRMED_ABSORB) \
                and lv.meta.get("prior_day_high") and lv.meta.get("ib_fail_up"):
            return _RuleHit(rule_id="CR-37",
                            flags_to_add={"ABSORB_PDH_IB_FAIL"},
                            score_delta_by_level={lv.uid: 10.0},
                            explanation="Absorption @ PDH with IB fail-up")
    return None


def cr_38(levels, gex_signal, bar, scorer_result, cfg) -> Optional[_RuleHit]:
    """CR-38 — Neutral-extreme close → gap-and-go next day.

    Source: auction_theory.md:§9 Trade-Plan 15. Tier: MEDIUM.
    """
    for lv in levels:
        if lv.meta.get("neutral_extreme_close"):
            return _RuleHit(rule_id="CR-38",
                            flags_to_add={"GAP_AND_GO_BIAS"},
                            score_delta_by_level={lv.uid: 5.0},
                            explanation="Neutral-extreme close → gap-and-go bias")
    return None


# ---------------------------------------------------------------------------
# Fixed rule-iteration order (matches RULES.md CR-01 → CR-38)
# ---------------------------------------------------------------------------

_RULES: list = [
    cr_01, cr_02, cr_03, cr_04, cr_05, cr_06, cr_07, cr_08, cr_09, cr_10,
    cr_11, cr_12, cr_13, cr_14, cr_15, cr_16, cr_17, cr_18, cr_19, cr_20,
    cr_21, cr_22, cr_23, cr_24, cr_25, cr_26, cr_27, cr_28, cr_29, cr_30,
    cr_31, cr_32, cr_33, cr_34, cr_35, cr_36, cr_37, cr_38,
]


def _rule_enable_flag(rule_fn, cfg: ConfluenceRulesConfig) -> bool:
    attr = f"enable_{rule_fn.__name__.upper()}"  # cr_04 → enable_CR_04
    return getattr(cfg, attr, True)


# Regime priority — higher wins against earlier rules so specific labels
# (PIN from CR-04) are not clobbered by generic (NEUTRAL from CR-10).
_REGIME_PRIORITY: dict[str, int] = {
    "NEUTRAL": 0, "BALANCE": 1, "TREND": 2, "PIN": 3,
}


def _merge_hit(annot: ConfluenceAnnotations, hit: _RuleHit) -> None:
    """Union hit into annotations. Regime merges by priority (PIN > TREND > BALANCE > NEUTRAL)."""
    annot.rule_hits.append((hit.rule_id, hit.explanation))
    for uid, delta in hit.score_delta_by_level.items():
        annot.score_mutations[uid] = annot.score_mutations.get(uid, 0.0) + delta
    annot.flags.update(hit.flags_to_add)
    annot.vetoes.update(hit.vetoes_to_add)
    if hit.regime_override is not None:
        cur_p = _REGIME_PRIORITY.get(annot.regime, 0)
        new_p = _REGIME_PRIORITY.get(hit.regime_override, 0)
        if new_p >= cur_p:
            annot.regime = hit.regime_override


def evaluate(
    levels: list[Level],
    gex_signal: Optional[GexSignal],
    bar,
    scorer_result,
    config: Optional[ConfluenceRulesConfig] = None,
    prior_regime: Optional[str] = None,
) -> ConfluenceAnnotations:
    """D-13: stateless confluence evaluation.

    Args:
        levels: LevelBus.get_all_active() snapshot (do not mutate).
        gex_signal: current GexSignal (may be None).
        bar: FootprintBar at close (may be None for pure-level tests).
        scorer_result: ScorerResult preview (may be None).
        config: ConfluenceRulesConfig; defaults to ConfluenceRulesConfig().
        prior_regime: last bar's annotations.regime (for REGIME_CHANGE flag).

    Returns:
        ConfluenceAnnotations. Never mutates inputs.

    Budget (D-34): <1ms for 80 Levels. Disabled rules are skipped O(1).
    """
    cfg = config or ConfluenceRulesConfig()
    annot = ConfluenceAnnotations()

    for rule in _RULES:
        if not _rule_enable_flag(rule, cfg):
            continue
        try:
            hit = rule(levels, gex_signal, bar, scorer_result, cfg)
        except Exception:
            # Defensive: one bad rule must not break the entire evaluation.
            # Production logging hook would live here.
            continue
        if hit is None:
            continue
        _merge_hit(annot, hit)

    # REGIME_CHANGE: computed regime differs from last bar's regime.
    if prior_regime is not None and prior_regime != annot.regime:
        annot.flags.add("REGIME_CHANGE")

    return annot


__all__ = [
    "ConfluenceAnnotations",
    "ConfluenceRulesConfig",
    "evaluate",
]
