"""TradeState enums, transition table, and pure guard functions for Phase 15-04 FSM.

Design references:
  D-17: 7 states — IDLE, WATCHING, ARMED, TRIGGERED, IN_POSITION, MANAGING, EXITING
  D-18: 11 transitions (T1-T11) per trade_logic.md §2
  D-21: 4 entry-trigger types — IMMEDIATE_MARKET, CONFIRMATION_BAR_MARKET,
        STOP_AFTER_CONFIRMATION, LIMIT_AT_LEVEL
  D-22: Simultaneous-trigger precedence — confluence score wins; tie broken by
        (ABSORB > EXHAUST > MOMENTUM > REJECTION)
  D-25: Invalidation rules I1-I9 (verbatim from trade_logic.md §6)
  D-27: PIN regime blocks WATCHING → ARMED; <70 score suppressed
  D-42: Kronos E10 gate — behind ``enable_e10_gating`` config flag,
        default False.

Entry trigger mapping ported verbatim from trade_logic.md §3 (17 triggers).
The four-way taxonomy is applied per the row in the §3 table ("Entry Order"
column) and the prose classifier immediately below it.

This module is INTENTIONALLY FREE of any dependency on ConfluenceRules
evaluation (S6 constraint from 15-03 handoff). Guards consume the already-
computed ``ConfluenceAnnotations`` produced upstream.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ---------------------------------------------------------------------------
# State enum (D-17)
# ---------------------------------------------------------------------------


class TradeState(Enum):
    """Seven FSM states per D-17 / trade_logic.md §2."""

    IDLE = "IDLE"
    WATCHING = "WATCHING"
    ARMED = "ARMED"
    TRIGGERED = "TRIGGERED"
    IN_POSITION = "IN_POSITION"
    MANAGING = "MANAGING"
    EXITING = "EXITING"


# ---------------------------------------------------------------------------
# Transition-ID enum (D-17 / D-18)
# ---------------------------------------------------------------------------


class TransitionId(Enum):
    """11 named transitions per trade_logic.md §2.

    T1  IDLE -> WATCHING            level qualifier
    T2  WATCHING -> ARMED           confluence ready + guard_T2_ready
    T3  ARMED -> TRIGGERED          entry trigger fires
    T4  TRIGGERED -> IN_POSITION    order fill
    T5  TRIGGERED -> ARMED          order rejected, retry in window
    T6  TRIGGERED -> IDLE           timeout without fill
    T7  IN_POSITION -> MANAGING     past first-target checkpoint
    T8  MANAGING -> EXITING         invalidation (I1-I9) or target hit
    T9  EXITING -> IDLE             exit fill confirmed
    T10 ARMED -> IDLE               confluence drop / timeout
    T11 WATCHING -> IDLE            all watched levels invalidated / timeout
    """

    T1 = "T1"
    T2 = "T2"
    T3 = "T3"
    T4 = "T4"
    T5 = "T5"
    T6 = "T6"
    T7 = "T7"
    T8 = "T8"
    T9 = "T9"
    T10 = "T10"
    T11 = "T11"


# ---------------------------------------------------------------------------
# Entry trigger taxonomy (D-21)
# ---------------------------------------------------------------------------


class EntryTriggerType(Enum):
    """4-way trigger-type taxonomy per D-21 / trade_logic.md §3."""

    IMMEDIATE_MARKET = "IMMEDIATE_MARKET"
    CONFIRMATION_BAR_MARKET = "CONFIRMATION_BAR_MARKET"
    STOP_AFTER_CONFIRMATION = "STOP_AFTER_CONFIRMATION"
    LIMIT_AT_LEVEL = "LIMIT_AT_LEVEL"


class EntryTrigger(Enum):
    """17 entry triggers (ET-01..ET-17) from trade_logic.md §3.

    Each maps to exactly one EntryTriggerType via ``trigger_type`` property.
    """

    ET_01 = "ET-01"  # CONFIRMED_ABSORB support, TYPE_A absorption, pos/transition regime
    ET_02 = "ET-02"  # Mirror of ET-01 (resistance)
    ET_03 = "ET-03"  # ABSORB within 8t of PUT_WALL (Rule 1) — immediate-market (score>=80)
    ET_04 = "ET-04"  # ABSORB within 8t of CALL_WALL (Rule 2)
    ET_05 = "ET-05"  # LVN close-through breakout → stop beyond bar extreme
    ET_06 = "ET-06"  # LVN aligned with GAMMA_FLIP — stop-after-confirmation (larger size)
    ET_07 = "ET-07"  # VAH/VAL exhaustion → limit at mid of bar range
    ET_08 = "ET-08"  # HVN edge — ABSORB + same-dir MOMENTUM within 5 bars (market on momentum bar)
    ET_09 = "ET-09"  # VPOC pin (Rule 4) — rotation limit
    ET_10 = "ET-10"  # FLIPPED zone beyond GAMMA_FLIP (Rule 5) — market on momentum bar
    ET_11 = "ET-11"  # EXHAUST + ABSORB at same price (Rule 7) — confirmation-bar market
    ET_12 = "ET-12"  # VAH/VAL + CONFIRMED_ABSORB (Rule 6) — limit at zone midpoint
    ET_13 = "ET-13"  # Naked prior-day VPOC + TRAP — stop beyond trap bar extreme
    ET_14 = "ET-14"  # IB high/low breakout — stop beyond breakout bar
    ET_15 = "ET-15"  # ABSORB away from all GEX walls — limit at absorption wick mid
    ET_16 = "ET-16"  # Volatility trigger + FLIPPED zone — market on defense-touch close
    ET_17 = "ET-17"  # HVL / LARGEST_GAMMA drift — limit at HVL (partial-exit bias; no new entry)

    @property
    def trigger_type(self) -> EntryTriggerType:
        """Map ET-XX to one of four EntryTriggerType values per trade_logic.md §3."""
        return _ENTRY_TRIGGER_TYPE_MAP[self]


# Golden taxonomy — verbatim from trade_logic.md §3 "Entry Order" column.
# Each ET-XX resolves to exactly one EntryTriggerType.
_ENTRY_TRIGGER_TYPE_MAP: dict[EntryTrigger, EntryTriggerType] = {
    # Confirmation-bar markets — prop-desk "wait for next bar close in thesis direction" pattern
    EntryTrigger.ET_01: EntryTriggerType.CONFIRMATION_BAR_MARKET,
    EntryTrigger.ET_02: EntryTriggerType.CONFIRMATION_BAR_MARKET,
    EntryTrigger.ET_08: EntryTriggerType.CONFIRMATION_BAR_MARKET,
    EntryTrigger.ET_10: EntryTriggerType.CONFIRMATION_BAR_MARKET,
    EntryTrigger.ET_11: EntryTriggerType.CONFIRMATION_BAR_MARKET,
    EntryTrigger.ET_16: EntryTriggerType.CONFIRMATION_BAR_MARKET,
    # Immediate-market — highest-conviction rules fire on current bar close
    EntryTrigger.ET_03: EntryTriggerType.IMMEDIATE_MARKET,
    EntryTrigger.ET_04: EntryTriggerType.IMMEDIATE_MARKET,
    # Stop-after-confirmation — breakout patterns; rest stop 1t beyond bar extreme
    EntryTrigger.ET_05: EntryTriggerType.STOP_AFTER_CONFIRMATION,
    EntryTrigger.ET_06: EntryTriggerType.STOP_AFTER_CONFIRMATION,
    EntryTrigger.ET_13: EntryTriggerType.STOP_AFTER_CONFIRMATION,
    EntryTrigger.ET_14: EntryTriggerType.STOP_AFTER_CONFIRMATION,
    # Limit-at-level — rotation / pin patterns; rest passive limit at level price
    EntryTrigger.ET_07: EntryTriggerType.LIMIT_AT_LEVEL,
    EntryTrigger.ET_09: EntryTriggerType.LIMIT_AT_LEVEL,
    EntryTrigger.ET_12: EntryTriggerType.LIMIT_AT_LEVEL,
    EntryTrigger.ET_15: EntryTriggerType.LIMIT_AT_LEVEL,
    EntryTrigger.ET_17: EntryTriggerType.LIMIT_AT_LEVEL,
}


# ---------------------------------------------------------------------------
# Transition table (D-17)
# ---------------------------------------------------------------------------


TRANSITION_TABLE: dict[tuple[TradeState, TradeState], TransitionId] = {
    (TradeState.IDLE, TradeState.WATCHING): TransitionId.T1,
    (TradeState.WATCHING, TradeState.ARMED): TransitionId.T2,
    (TradeState.ARMED, TradeState.TRIGGERED): TransitionId.T3,
    (TradeState.TRIGGERED, TradeState.IN_POSITION): TransitionId.T4,
    (TradeState.TRIGGERED, TradeState.ARMED): TransitionId.T5,
    (TradeState.TRIGGERED, TradeState.IDLE): TransitionId.T6,
    (TradeState.IN_POSITION, TradeState.MANAGING): TransitionId.T7,
    (TradeState.MANAGING, TradeState.EXITING): TransitionId.T8,
    (TradeState.EXITING, TradeState.IDLE): TransitionId.T9,
    (TradeState.ARMED, TradeState.IDLE): TransitionId.T10,
    (TradeState.WATCHING, TradeState.IDLE): TransitionId.T11,
}


def _build_allowed_transitions() -> dict[TradeState, set[TradeState]]:
    out: dict[TradeState, set[TradeState]] = {s: set() for s in TradeState}
    for (src, dst) in TRANSITION_TABLE:
        out[src].add(dst)
    return out


ALLOWED_TRANSITIONS: dict[TradeState, set[TradeState]] = _build_allowed_transitions()


# ---------------------------------------------------------------------------
# Pure guard functions (D-22 / D-27 / D-42 / D-25)
# ---------------------------------------------------------------------------


def guard_T2_ready(
    scorer_result,
    confluence,
    min_score: float = 70.0,
    *,
    enable_e10_gating: bool = False,
    e10_direction: int = 0,
    e10_confidence: float = 0.0,
) -> bool:
    """Guard for WATCHING -> ARMED (T2).

    Implements D-22 (score gate), D-27 (PIN regime blocks directional entry),
    and D-42 (optional Kronos E10 opposite-direction block).

    Args:
        scorer_result: ScorerResult — any duck-type with ``tier``, ``direction``,
            ``total_score`` (and optionally ``meta_flags``).
        confluence: ConfluenceAnnotations — duck-type with ``regime`` and
            ``vetoes`` (set[str]).
        min_score: minimum total_score to qualify.
        enable_e10_gating: D-42 flag — defaults to False for first release.
        e10_direction: +1 / -1 / 0, Kronos E10 predicted direction.
        e10_confidence: 0.0-1.0 Kronos E10 confidence.

    Returns:
        True if all guards pass; False otherwise.
    """
    # Hard veto — ConfluenceRules flagged a veto (e.g. SPOOF_DETECTED)
    if getattr(confluence, "vetoes", None) and len(confluence.vetoes) > 0:
        return False

    # Tier gate — DISQUALIFIED / QUIET blocked
    from deep6.scoring.scorer import SignalTier
    tier = getattr(scorer_result, "tier", None)
    if tier in (SignalTier.DISQUALIFIED, SignalTier.QUIET):
        return False

    # Direction gate — FSM needs a directional conviction
    direction = int(getattr(scorer_result, "direction", 0) or 0)
    if direction == 0:
        return False

    # D-27: PIN regime blocks WATCHING -> ARMED. Directional signals with
    # score < 70 are also suppressed under PIN (per plan body).
    regime = getattr(confluence, "regime", "NEUTRAL")
    if regime == "PIN":
        return False

    # D-22 score gate
    score = float(getattr(scorer_result, "total_score", 0.0) or 0.0)
    if score < min_score:
        return False

    # D-42: optional Kronos E10 opposite-direction block. When the flag is
    # on AND E10 disagrees with strong confidence, refuse the transition.
    if enable_e10_gating and e10_direction != 0 and e10_confidence >= 0.75:
        if e10_direction != direction:
            return False

    return True


@dataclass
class PositionLikeState:
    """Minimal fields guard_T8_invalidated reads.

    Use the live Position object from position_manager in production; this
    shape documents the duck-typed contract for tests.
    """

    direction: int  # +1 LONG / -1 SHORT
    entry_price: float
    stop_price: float
    initial_stop_price: float
    max_favorable_R: float = 0.0   # realized MFE in R units
    bars_held: int = 0
    entry_level_state: str = "CREATED"


def guard_T8_invalidated(
    position,
    bar,
    scorer_result=None,
    *,
    opposing_absorb_price: float | None = None,
    r_distance: float | None = None,
    gex_prev_regime: str | None = None,
    gex_curr_regime: str | None = None,
    bar_vol_ratio_to_20bar: float = 1.0,
    freeze_guard_frozen: bool = False,
    seconds_to_close: float = 3600.0,
    consecutive_opposite_bars: int = 0,
    opposite_score: float = 0.0,
) -> tuple[bool, str]:
    """Guard for MANAGING -> EXITING (T8). Returns (fired, rule_id).

    Implements I1-I9 from trade_logic.md §6 (D-25). All inputs are explicit
    kwargs so the caller (TradeDecisionMachine) controls policy state.

    Returns:
        (fired, rule_id). rule_id is one of {"I1".."I9", ""} — empty when
        fired=False.
    """
    # I7: FreezeGuard went frozen — bail
    if freeze_guard_frozen:
        return True, "I7"

    # I8: within 30s of 16:00 ET regardless of P&L
    if seconds_to_close <= 30.0:
        return True, "I8"

    # I1: the entry-creating Level went BROKEN
    entry_state = getattr(position, "entry_level_state", "CREATED")
    if entry_state == "BROKEN":
        return True, "I1"

    # I2: opposite-conviction tape for 2 consecutive bars, opposite_score >= 65
    if consecutive_opposite_bars >= 2 and opposite_score >= 65.0:
        return True, "I2"

    # I3: opposing CONFIRMED_ABSORB within 4 ticks of current price
    if opposing_absorb_price is not None:
        bar_close = float(getattr(bar, "close", 0.0) or 0.0)
        if abs(bar_close - opposing_absorb_price) <= 4 * 0.25:  # NQ tick = 0.25
            return True, "I3"

    # I4 / I5: GEX regime transition against a fade position
    pos_direction = int(getattr(position, "direction", 0) or 0)
    if (
        gex_prev_regime in ("POSITIVE_DAMPENING", "NEUTRAL")
        and gex_curr_regime == "NEGATIVE_AMPLIFYING"
    ):
        # Long fade = long against rising market? Treat any live position as vulnerable.
        if pos_direction > 0:
            return True, "I4"
        if pos_direction < 0:
            return True, "I5"

    # I6: capitulation print — vol >= 2x 20-bar avg AND close beyond entry-bar extreme against pos
    if bar_vol_ratio_to_20bar >= 2.0:
        bar_close = float(getattr(bar, "close", 0.0) or 0.0)
        entry_price = float(getattr(position, "entry_price", 0.0) or 0.0)
        # "Against position" — LONG loses if close << entry by some margin;
        # treat a half-R adverse move coincident with the vol spike as capitulation.
        if r_distance is not None and r_distance > 0:
            adverse = (entry_price - bar_close) * pos_direction
            if adverse >= 0.5 * r_distance:
                return True, "I6"

    # I9: MFE give-back — realized MFE >= 0.75R then retraces >= 50% (back to entry ± 1 tick)
    # Plan 15-04 (plan body) uses the tighter "MFE=10R, current=4.9R" shape ⇒ 50% give-back.
    mfe_R = float(getattr(position, "max_favorable_R", 0.0) or 0.0)
    if mfe_R >= 0.75:
        entry_price = float(getattr(position, "entry_price", 0.0) or 0.0)
        if r_distance is not None and r_distance > 0:
            current_R = (float(getattr(bar, "close", 0.0) or 0.0) - entry_price) * pos_direction / r_distance
            if current_R <= mfe_R * 0.5:
                return True, "I9"

    return False, ""


# ---------------------------------------------------------------------------
# Narrative-kind precedence (D-22 tie-breaker)
# ---------------------------------------------------------------------------


NARRATIVE_KIND_PRIORITY: dict[str, int] = {
    # Higher value = higher priority in simultaneous-trigger tie-break
    "ABSORB": 4,
    "CONFIRMED_ABSORB": 4,
    "EXHAUST": 3,
    "MOMENTUM": 2,
    "REJECTION": 1,
}


def narrative_priority(kind_name: str) -> int:
    """Return D-22 tie-break priority for a narrative LevelKind name. 0 if unknown."""
    return NARRATIVE_KIND_PRIORITY.get(kind_name, 0)
