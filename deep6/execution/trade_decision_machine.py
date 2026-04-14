"""TradeDecisionMachine — 7-state FSM per Phase 15-04.

Consumes pre-computed ``ConfluenceAnnotations`` (S6: FSM MUST NOT call
``confluence_rules.evaluate()`` internally). The bar-engine loop is
responsible for running ConfluenceRules ONCE per bar and passing the
result to both ``score_bar`` and this FSM.

Design references (15-CONTEXT.md):
  D-17/D-18  7 states, 11 transitions
  D-19       every transition persisted to ``fsm_transitions``
  D-20       confirmation-bar triggers fire on NEXT bar's close
  D-21       4 entry-trigger types
  D-22       simultaneous-trigger precedence by score, then narrative kind
  D-23       stop = max(structural+2t, 2.0×ATR(14)), capped at 1.5% account
  D-24       target = opposing zone OR 1.5R floor; runner trailed by OF-exhaust
  D-25       invalidations I1-I9 including I9 MFE give-back
  D-26       sizing = floor(risk_budget / stop_distance × conviction × regime
             × recency × 0.25)  (Kelly fraction 0.25)
  D-27       PIN regime blocks WATCHING -> ARMED; limit orders at pinned
             strike cancelled if unfilled within 3 bars
  D-42       E10 gate behind config flag (default False)

Watchlist + pending-entry trackers KEY BY ``Level.uid`` (C5) — not object
identity. Levels mutate across bars; uid is the stable integer key.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import structlog

from deep6.execution.config import ExecutionConfig, OrderSide
from deep6.execution.trade_state import (
    ALLOWED_TRANSITIONS,
    TRANSITION_TABLE,
    EntryTrigger,
    EntryTriggerType,
    NARRATIVE_KIND_PRIORITY,
    TradeState,
    TransitionId,
    guard_T2_ready,
    guard_T8_invalidated,
    narrative_priority,
)
from deep6.engines.level import Level, LevelKind, LevelState
from deep6.scoring.scorer import ScorerResult, SignalTier

log = structlog.get_logger()

NQ_TICK = 0.25
NQ_DOLLARS_PER_POINT = 50.0


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class OrderIntent:
    """FSM output: a broker-agnostic order instruction.

    The ExecutionEngine delegate and LiveTrader translate this into the
    actual Rithmic ORDER_PLANT call. Fields kept minimal to match legacy
    ``ExecutionDecision`` mapping.
    """

    action: str                          # "ENTER" | "EXIT" | "CANCEL" | "SKIP"
    side: OrderSide | None = None
    order_type: str = "MARKET"           # "MARKET" | "LIMIT" | "STOP"
    entry_price: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    contracts: int = 1
    trigger_id: str = ""                 # ET-XX that produced this intent
    reason: str = ""
    level_uid: int | None = None         # C5 — for tracking pins/limits
    meta: dict = field(default_factory=dict)


@dataclass
class PendingTrigger:
    """Confirmation-bar entries waiting one bar per D-20.

    type == CONFIRMATION_BAR_MARKET  -> fire market at next bar close
    type == STOP_AFTER_CONFIRMATION  -> rest stop 1t beyond confirmation bar extreme
    """

    trigger: EntryTrigger
    side: OrderSide
    created_bar_index: int
    signal_bar_high: float
    signal_bar_low: float
    level_uid: int
    payload: dict = field(default_factory=dict)


@dataclass
class FSMConfig:
    """FSM-level knobs (D-20/22/27/42).

    Kept separate from ExecutionConfig so the existing frozen config and its
    callers are untouched.
    """

    trigger_timeout_bars: int = 3          # T6 — TRIGGERED -> IDLE without fill
    armed_timeout_bars: int = 5            # T10 — ARMED confluence drop / timeout
    watching_timeout_bars: int = 8         # T11 — WATCHING timeout
    pin_limit_cancel_bars: int = 3         # D-27 — unfilled limit at pinned strike
    min_level_score: float = 60.0          # T1 — IDLE -> WATCHING
    min_confluence_score_for_T2: float = 70.0
    proximity_ticks_for_T1: int = 16       # LevelBus.query_near radius at IDLE
    first_target_R: float = 1.0            # T7 — IN_POSITION -> MANAGING at 1R
    enable_e10_gating: bool = False        # D-42 (default OFF)
    kelly_fraction: float = 0.25           # D-26
    risk_budget_usd: float = 100.0         # D-26 (0.20 × 500 daily loss limit)
    max_account_risk_pct: float = 0.015    # D-23 — 1.5% account cap on stop $


# ---------------------------------------------------------------------------
# TradeDecisionMachine
# ---------------------------------------------------------------------------


class TradeDecisionMachine:
    """7-state FSM binding LevelBus + ScorerResult + ConfluenceAnnotations into
    broker-agnostic OrderIntents.

    Typical wiring (bar-engine loop, landing in Phase 16):

        annotations = confluence_rules.evaluate(levels, gex, bar, scorer_result)
        result = score_bar(..., confluence_annotations=annotations)
        intents = fsm.on_bar(bar, level_bus, result, annotations)
        for intent in intents:
            if risk_manager.can_enter(result, gex, open_positions).allowed:
                broker.submit(intent)

    Thread-safety: runs in asyncio loop (single-threaded). Do not share
    across event loops.
    """

    def __init__(
        self,
        execution_config: ExecutionConfig,
        fsm_config: FSMConfig | None = None,
        freeze_guard: Any = None,
        risk_manager: Any = None,
        position_manager: Any = None,
        event_writer: Any = None,      # duck-type: .record_transition(...)
        account_balance_usd: float = 25000.0,
    ) -> None:
        self.execution_config = execution_config
        self.fsm_config = fsm_config or FSMConfig()
        self.freeze_guard = freeze_guard
        self.risk_manager = risk_manager
        self.position_manager = position_manager
        self.event_writer = event_writer
        self.account_balance_usd = account_balance_usd

        self._state: TradeState = TradeState.IDLE
        self._state_bar_entered: int = 0
        self._bar_index_last: int = -1
        self._watched_uids: list[int] = []
        self._armed_level_uid: int | None = None
        self._armed_side: OrderSide | None = None
        self._pending: list[PendingTrigger] = []
        self._resting_limits: list[OrderIntent] = []   # D-27 3-bar cancel
        self._current_position_snapshot: Any = None    # set on T4
        self._last_order_intent: OrderIntent | None = None
        self._prior_annotations = None                  # for I2 / regime-drift

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def state(self) -> TradeState:
        return self._state

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    # ------------------------------------------------------------------
    # Primary per-bar entry point
    # ------------------------------------------------------------------

    def on_bar(
        self,
        bar: Any,
        level_bus: Any,
        scorer_result: ScorerResult,
        confluence_annotations: Any,
        *,
        bar_index: int | None = None,
        atr: float = 10.0,
        tick_size: float = NQ_TICK,
    ) -> list[OrderIntent]:
        """Advance the FSM by one bar. Returns OrderIntents emitted this bar.

        ``confluence_annotations`` MUST be the already-computed
        ``ConfluenceAnnotations`` from the bar-engine loop (S6 — FSM never
        calls ``evaluate()`` itself).
        """
        if bar_index is None:
            bar_index = self._bar_index_last + 1
        self._bar_index_last = bar_index

        intents: list[OrderIntent] = []

        # 0. Global veto + FreezeGuard checks — before any state logic.
        if self.freeze_guard is not None and getattr(self.freeze_guard, "is_frozen", False):
            # Force reset to IDLE; cancel pendings and resting limits.
            self._force_idle(
                bar, bar_index, intents, trigger="FREEZE", reason="FreezeGuard frozen"
            )
            self._prior_annotations = confluence_annotations
            return intents

        # Spoof veto — mirror D-22 / plan S6 (confluence_annotations.vetoes owns it)
        if (
            confluence_annotations is not None
            and "SPOOF_DETECTED" in getattr(confluence_annotations, "vetoes", set())
            and self._state in (TradeState.WATCHING, TradeState.ARMED)
        ):
            self._force_idle(
                bar, bar_index, intents, trigger="SPOOF_VETO",
                reason="SPOOF_DETECTED veto — forced IDLE",
            )
            self._prior_annotations = confluence_annotations
            return intents

        # 1. Fire pending confirmation-bar triggers from the PRIOR bar (D-20).
        intents.extend(self._fire_pending_triggers(bar, bar_index, scorer_result))

        # 2. Cancel resting limits at pinned strike after N bars (D-27).
        self._age_and_cancel_resting_limits(bar_index, intents, confluence_annotations)

        # 3. Per-state dispatch. After a successful transition, re-dispatch
        #    so the new state can also evaluate within this same bar (e.g.
        #    WATCHING -> ARMED then ARMED -> TRIGGERED on the same close).
        #    Cap iterations to avoid infinite loops from malformed handlers.
        max_hops = 4
        seen_states: set[TradeState] = set()
        for _ in range(max_hops):
            current = self._state
            if current in seen_states:
                break
            seen_states.add(current)
            handler = _STATE_HANDLERS[current]
            handler(self, bar, level_bus, scorer_result, confluence_annotations,
                    bar_index, atr, tick_size, intents)
            if self._state == current:
                break

        self._prior_annotations = confluence_annotations
        return intents

    # ------------------------------------------------------------------
    # External events
    # ------------------------------------------------------------------

    def on_fill(self, fill: Any, *, bar_index: int | None = None) -> None:
        """Transition TRIGGERED -> IN_POSITION (T4)."""
        if self._state != TradeState.TRIGGERED:
            log.warning("fsm.on_fill_unexpected_state", state=self._state.name)
            return
        self._current_position_snapshot = fill
        self._transition(
            to=TradeState.IN_POSITION,
            bar_ts=getattr(fill, "ts", time.time()),
            bar_index=bar_index if bar_index is not None else self._bar_index_last,
            trigger="FILL",
            regime=None,
            confluence_score=None,
            payload={"fill": str(fill)},
        )

    def on_reject(
        self, reject: Any, *, bar_index: int | None = None, retry_ok: bool = True
    ) -> None:
        """TRIGGERED -> ARMED (T5) or IDLE (T6)."""
        if self._state != TradeState.TRIGGERED:
            log.warning("fsm.on_reject_unexpected_state", state=self._state.name)
            return
        target = TradeState.ARMED if retry_ok else TradeState.IDLE
        tid_name = "REJECT_RETRY" if retry_ok else "REJECT_IDLE"
        self._transition(
            to=target,
            bar_ts=getattr(reject, "ts", time.time()),
            bar_index=bar_index if bar_index is not None else self._bar_index_last,
            trigger=tid_name,
            regime=None,
            confluence_score=None,
            payload={"reject": str(reject)},
        )

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    def _handle_idle(
        self, bar, level_bus, scorer_result, annotations,
        bar_index, atr, tick_size, intents: list[OrderIntent],
    ) -> None:
        """T1: IDLE -> WATCHING when any level score>=60 near price.

        Skip if we just collapsed to IDLE this bar — avoid immediate re-entry
        inside the same on_bar() cascade.
        """
        if self._state_bar_entered == bar_index:
            return
        bar_close = float(getattr(bar, "close", 0.0) or 0.0)
        top_levels = level_bus.get_top_n(6) if level_bus is not None else []
        proximity_points = self.fsm_config.proximity_ticks_for_T1 * tick_size
        near_strong = [
            lv for lv in top_levels
            if lv.score >= self.fsm_config.min_level_score
            and lv.state != LevelState.INVALIDATED
            and abs(bar_close - lv.midpoint()) <= proximity_points
        ]
        if near_strong:
            self._watched_uids = [lv.uid for lv in near_strong]
            self._transition(
                to=TradeState.WATCHING,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger="LEVEL_QUALIFIER",
                regime=getattr(annotations, "regime", None),
                confluence_score=scorer_result.total_score if scorer_result else None,
                payload={"level_uids": self._watched_uids},
            )

    def _handle_watching(
        self, bar, level_bus, scorer_result, annotations,
        bar_index, atr, tick_size, intents: list[OrderIntent],
    ) -> None:
        """T2 (ARMED) OR T11 (IDLE) on invalidation / timeout."""
        # Prune watched uids that went INVALIDATED or BROKEN.
        active_uids = []
        if level_bus is not None:
            for uid in self._watched_uids:
                lv = _find_by_uid(level_bus, uid)
                if lv is not None and lv.state not in (LevelState.INVALIDATED, LevelState.BROKEN):
                    active_uids.append(uid)
        self._watched_uids = active_uids

        # Freshly entered WATCHING this bar — don't also arm on entry bar.
        if self._state_bar_entered == bar_index:
            return

        # T11: all levels invalidated or timed out
        if (
            not self._watched_uids
            or (bar_index - self._state_bar_entered) >= self.fsm_config.watching_timeout_bars
        ):
            self._transition(
                to=TradeState.IDLE,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger="WATCHING_TIMEOUT_OR_INVALIDATED",
                regime=getattr(annotations, "regime", None),
                confluence_score=scorer_result.total_score if scorer_result else None,
                payload={},
            )
            return

        # T2: guard_T2_ready checks D-22/D-27/D-42
        ready = guard_T2_ready(
            scorer_result,
            annotations,
            min_score=self.fsm_config.min_confluence_score_for_T2,
            enable_e10_gating=self.fsm_config.enable_e10_gating,
        )
        if ready:
            self._armed_side = (
                OrderSide.LONG if scorer_result.direction > 0 else OrderSide.SHORT
            )
            # Pick the highest-score watched level on the correct side
            candidate_uid = self._watched_uids[0]
            if level_bus is not None:
                candidates = [
                    _find_by_uid(level_bus, u) for u in self._watched_uids
                ]
                candidates = [c for c in candidates if c is not None]
                if candidates:
                    candidates.sort(key=lambda lv: lv.score, reverse=True)
                    candidate_uid = candidates[0].uid
            self._armed_level_uid = candidate_uid
            self._transition(
                to=TradeState.ARMED,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger="CONFLUENCE_READY",
                regime=getattr(annotations, "regime", None),
                confluence_score=scorer_result.total_score,
                payload={"armed_level_uid": candidate_uid},
            )

    def _handle_armed(
        self, bar, level_bus, scorer_result, annotations,
        bar_index, atr, tick_size, intents: list[OrderIntent],
    ) -> None:
        """T3 (TRIGGERED) via entry trigger, or T10 (IDLE) on drop/timeout."""
        # T10: confluence dropped below threshold OR armed timeout
        if (
            scorer_result.total_score < self.fsm_config.min_confluence_score_for_T2
            or (bar_index - self._state_bar_entered) >= self.fsm_config.armed_timeout_bars
        ):
            self._transition(
                to=TradeState.IDLE,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger="CONFLUENCE_DROP_OR_TIMEOUT",
                regime=getattr(annotations, "regime", None),
                confluence_score=scorer_result.total_score,
                payload={},
            )
            return

        # Evaluate triggers in D-22 priority order
        triggers = self._detect_entry_triggers(
            bar, level_bus, scorer_result, annotations, tick_size
        )
        if not triggers:
            return
        # Precedence: sort by narrative priority desc, then by a stable order
        triggers.sort(key=lambda t: (-t[2], t[0].value))
        chosen_et, side, _priority = triggers[0]
        ttype = chosen_et.trigger_type

        bar_close = float(getattr(bar, "close", 0.0) or 0.0)
        bar_high = float(getattr(bar, "high", bar_close) or bar_close)
        bar_low = float(getattr(bar, "low", bar_close) or bar_close)
        lv = _find_by_uid(level_bus, self._armed_level_uid) if level_bus else None

        if ttype == EntryTriggerType.IMMEDIATE_MARKET:
            intent = self._build_entry_intent(
                et=chosen_et, side=side, order_type="MARKET",
                entry_price=bar_close, lv=lv, bar_high=bar_high, bar_low=bar_low,
                atr=atr, tick_size=tick_size, level_bus=level_bus,
                scorer_result=scorer_result, annotations=annotations,
            )
            intents.append(intent)
            self._transition_to_triggered(
                bar, bar_index, scorer_result, annotations, chosen_et.value
            )
        elif ttype == EntryTriggerType.LIMIT_AT_LEVEL:
            limit_price = lv.midpoint() if lv is not None else bar_close
            intent = self._build_entry_intent(
                et=chosen_et, side=side, order_type="LIMIT",
                entry_price=limit_price, lv=lv, bar_high=bar_high, bar_low=bar_low,
                atr=atr, tick_size=tick_size, level_bus=level_bus,
                scorer_result=scorer_result, annotations=annotations,
            )
            intents.append(intent)
            # D-27 tracking: if we're in PIN regime, track for 3-bar cancel
            if getattr(annotations, "regime", "NEUTRAL") == "PIN":
                intent.meta["pin_age_bar"] = bar_index
                self._resting_limits.append(intent)
            self._transition_to_triggered(
                bar, bar_index, scorer_result, annotations, chosen_et.value
            )
        elif ttype == EntryTriggerType.CONFIRMATION_BAR_MARKET:
            # D-20: fires NEXT bar — queue pending
            self._pending.append(PendingTrigger(
                trigger=chosen_et, side=side, created_bar_index=bar_index,
                signal_bar_high=bar_high, signal_bar_low=bar_low,
                level_uid=self._armed_level_uid or 0,
                payload={"score": scorer_result.total_score},
            ))
            # Stay in ARMED; no state change
        elif ttype == EntryTriggerType.STOP_AFTER_CONFIRMATION:
            # D-20 style: queue stop at 1t beyond signal-bar extreme
            self._pending.append(PendingTrigger(
                trigger=chosen_et, side=side, created_bar_index=bar_index,
                signal_bar_high=bar_high, signal_bar_low=bar_low,
                level_uid=self._armed_level_uid or 0,
                payload={"type": "STOP"},
            ))
            # Stay in ARMED

    def _handle_triggered(
        self, bar, level_bus, scorer_result, annotations,
        bar_index, atr, tick_size, intents: list[OrderIntent],
    ) -> None:
        """T6: timeout without fill -> IDLE."""
        if (bar_index - self._state_bar_entered) >= self.fsm_config.trigger_timeout_bars:
            self._transition(
                to=TradeState.IDLE,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger="TRIGGER_TIMEOUT",
                regime=getattr(annotations, "regime", None),
                confluence_score=scorer_result.total_score if scorer_result else None,
                payload={},
            )

    def _handle_in_position(
        self, bar, level_bus, scorer_result, annotations,
        bar_index, atr, tick_size, intents: list[OrderIntent],
    ) -> None:
        """T7: past first-target checkpoint -> MANAGING."""
        # Ask position_manager for R-progress; fall back to snapshot math.
        pos = self._current_position_snapshot
        if pos is None:
            return
        r_distance = abs(
            float(getattr(pos, "entry_price", 0.0))
            - float(getattr(pos, "stop_price", 0.0))
        )
        if r_distance <= 0:
            return
        bar_close = float(getattr(bar, "close", 0.0) or 0.0)
        direction = int(getattr(pos, "direction", 0) or 0)
        r_multiple = (bar_close - float(getattr(pos, "entry_price", 0.0))) * direction / r_distance
        if r_multiple >= self.fsm_config.first_target_R:
            self._transition(
                to=TradeState.MANAGING,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger="FIRST_TARGET",
                regime=getattr(annotations, "regime", None),
                confluence_score=scorer_result.total_score if scorer_result else None,
                payload={"r_multiple": r_multiple},
            )

    def _handle_managing(
        self, bar, level_bus, scorer_result, annotations,
        bar_index, atr, tick_size, intents: list[OrderIntent],
    ) -> None:
        """T8: invalidation I1-I9 fires -> EXITING."""
        pos = self._current_position_snapshot
        if pos is None:
            return
        # MFE tracking: delegate to position_manager if available.
        if self.position_manager is not None and hasattr(self.position_manager, "current_mfe_R"):
            mfe = self.position_manager.current_mfe_R(pos)
            setattr(pos, "max_favorable_R", max(getattr(pos, "max_favorable_R", 0.0) or 0.0, mfe))

        r_distance = abs(
            float(getattr(pos, "entry_price", 0.0))
            - float(getattr(pos, "stop_price", 0.0))
        )
        fired, rule = guard_T8_invalidated(
            pos, bar, scorer_result, r_distance=r_distance,
        )
        if fired:
            intent = OrderIntent(
                action="EXIT",
                side=getattr(pos, "side", None),
                order_type="MARKET",
                entry_price=float(getattr(bar, "close", 0.0) or 0.0),
                trigger_id=rule,
                reason=f"Invalidation {rule}",
            )
            intents.append(intent)
            self._transition(
                to=TradeState.EXITING,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger=rule,
                regime=getattr(annotations, "regime", None),
                confluence_score=scorer_result.total_score if scorer_result else None,
                payload={"rule": rule},
            )

    def _handle_exiting(
        self, bar, level_bus, scorer_result, annotations,
        bar_index, atr, tick_size, intents: list[OrderIntent],
    ) -> None:
        """T9: EXITING -> IDLE when exit fill confirmed.

        In absence of a fill callback, auto-advance after one bar for replay
        use. Real broker path calls on_fill for the exit and maps here.
        """
        if (bar_index - self._state_bar_entered) >= 1:
            self._transition(
                to=TradeState.IDLE,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger="EXIT_FILL",
                regime=getattr(annotations, "regime", None),
                confluence_score=scorer_result.total_score if scorer_result else None,
                payload={},
            )
            self._current_position_snapshot = None

    # ------------------------------------------------------------------
    # Trigger detection (simplified but faithful)
    # ------------------------------------------------------------------

    def _detect_entry_triggers(
        self, bar, level_bus, scorer_result, annotations, tick_size: float,
    ) -> list[tuple[EntryTrigger, OrderSide, int]]:
        """Return list of (EntryTrigger, side, priority).

        Priority integer drives D-22 tie-break (higher wins). For Phase 15-04
        MVP we detect a pragmatic subset based on the already-computed
        ``ConfluenceAnnotations.flags`` and ``scorer_result.categories_firing``
        plus Level kinds at the armed level. Full per-trigger implementations
        live in Phase 16; this layer ensures the FSM wiring is exercised.
        """
        triggers: list[tuple[EntryTrigger, OrderSide, int]] = []
        if scorer_result.direction == 0:
            return triggers
        side = OrderSide.LONG if scorer_result.direction > 0 else OrderSide.SHORT

        flags: set[str] = set(getattr(annotations, "flags", set()) or set())
        cats = set(scorer_result.categories_firing or [])
        lv = _find_by_uid(level_bus, self._armed_level_uid) if level_bus else None
        lv_kind = lv.kind if lv is not None else None

        # ET-03 / ET-04 — ABSORB within 8t of PUT/CALL wall (Rule 1/2) — IMMEDIATE_MARKET
        if (
            ("ABSORB_PUT_WALL" in flags or "ABSORB_CALL_WALL" in flags)
            and "absorption" in cats
            and scorer_result.total_score >= 80
        ):
            et = EntryTrigger.ET_03 if side == OrderSide.LONG else EntryTrigger.ET_04
            triggers.append((et, side, narrative_priority("ABSORB")))

        # ET-01 / ET-02 — CONFIRMED_ABSORB, TYPE_A, score>=80 — CONFIRMATION_BAR_MARKET
        if (
            "absorption" in cats
            and scorer_result.tier == SignalTier.TYPE_A
            and scorer_result.total_score >= 80
            and lv_kind in (LevelKind.CONFIRMED_ABSORB, LevelKind.ABSORB)
        ):
            et = EntryTrigger.ET_01 if side == OrderSide.LONG else EntryTrigger.ET_02
            triggers.append((et, side, narrative_priority("ABSORB") - 1))

        # ET-07 — VAH/VAL exhaustion -> LIMIT_AT_LEVEL
        if (
            "exhaustion" in cats
            and lv_kind in (LevelKind.VAH, LevelKind.VAL)
        ):
            triggers.append((EntryTrigger.ET_07, side, narrative_priority("EXHAUST")))

        # ET-05 / ET-06 — LVN breakout -> STOP_AFTER_CONFIRMATION (momentum-led)
        if (
            lv_kind == LevelKind.LVN
            and "volume_profile" in cats
            and scorer_result.total_score >= 70
        ):
            et = EntryTrigger.ET_06 if "GEX_BASIS_CORRECTED" in flags else EntryTrigger.ET_05
            triggers.append((et, side, narrative_priority("MOMENTUM")))

        # ET-09 — VPOC pin (Rule 4) -> LIMIT_AT_LEVEL (only under PIN regime;
        # T2 guard already blocked this code-path under PIN, so this rule
        # path is effectively disabled in 15-04 MVP and kept for completeness)
        if (
            getattr(annotations, "regime", "NEUTRAL") == "PIN"
            and lv_kind == LevelKind.VPOC
        ):  # pragma: no cover — gated out by T2 guard in practice
            triggers.append((EntryTrigger.ET_09, side, narrative_priority("REJECTION")))

        return triggers

    # ------------------------------------------------------------------
    # Pending + resting limit lifecycle
    # ------------------------------------------------------------------

    def _fire_pending_triggers(
        self, bar, bar_index: int, scorer_result: ScorerResult,
    ) -> list[OrderIntent]:
        """D-20: triggers queued on bar N fire on bar N+1's close."""
        intents: list[OrderIntent] = []
        if self._state != TradeState.ARMED:
            # Pending only meaningful while ARMED.
            return intents
        stil_pending: list[PendingTrigger] = []
        bar_close = float(getattr(bar, "close", 0.0) or 0.0)
        for pt in self._pending:
            if pt.created_bar_index >= bar_index:
                stil_pending.append(pt)
                continue
            # D-20: confirmation bar must close in thesis direction with
            # preserved conviction. If scorer direction flipped or tier
            # collapsed, drop the pending.
            pt_dir = +1 if pt.side == OrderSide.LONG else -1
            if (
                scorer_result is None
                or scorer_result.direction != pt_dir
                or scorer_result.tier
                    in (SignalTier.QUIET, SignalTier.DISQUALIFIED, SignalTier.TYPE_C)
            ):
                continue  # drop pending silently — confluence no longer holds
            if pt.trigger.trigger_type == EntryTriggerType.CONFIRMATION_BAR_MARKET:
                intent = OrderIntent(
                    action="ENTER",
                    side=pt.side,
                    order_type="MARKET",
                    entry_price=bar_close,
                    trigger_id=pt.trigger.value,
                    reason=f"D-20 confirmation bar for {pt.trigger.value}",
                    level_uid=pt.level_uid,
                )
                intents.append(intent)
                self._transition_to_triggered_simple(bar, bar_index, pt.trigger.value)
            elif pt.trigger.trigger_type == EntryTriggerType.STOP_AFTER_CONFIRMATION:
                # Rest a stop 1t beyond the signal bar's extreme in thesis direction
                if pt.side == OrderSide.LONG:
                    stop_trigger_price = pt.signal_bar_high + NQ_TICK
                else:
                    stop_trigger_price = pt.signal_bar_low - NQ_TICK
                intent = OrderIntent(
                    action="ENTER",
                    side=pt.side,
                    order_type="STOP",
                    entry_price=stop_trigger_price,
                    trigger_id=pt.trigger.value,
                    reason=f"Stop after confirmation for {pt.trigger.value}",
                    level_uid=pt.level_uid,
                )
                intents.append(intent)
                self._transition_to_triggered_simple(bar, bar_index, pt.trigger.value)
        self._pending = stil_pending
        return intents

    def _age_and_cancel_resting_limits(
        self, bar_index: int, intents: list[OrderIntent], annotations,
    ) -> None:
        """D-27: resting limits at pinned strike cancelled after N bars unfilled."""
        if not self._resting_limits:
            return
        kept: list[OrderIntent] = []
        for oi in self._resting_limits:
            age_bar = int(oi.meta.get("pin_age_bar", bar_index))
            if bar_index - age_bar >= self.fsm_config.pin_limit_cancel_bars:
                intents.append(OrderIntent(
                    action="CANCEL",
                    side=oi.side,
                    trigger_id=oi.trigger_id,
                    reason=f"D-27 pin-regime limit unfilled {bar_index - age_bar} bars",
                    level_uid=oi.level_uid,
                ))
            else:
                kept.append(oi)
        self._resting_limits = kept

    # ------------------------------------------------------------------
    # Transition bookkeeping + persistence (D-19)
    # ------------------------------------------------------------------

    def _transition(
        self,
        *,
        to: TradeState,
        bar_ts: float,
        bar_index: int,
        trigger: str | None,
        regime: str | None,
        confluence_score: float | None,
        payload: dict,
    ) -> None:
        src = self._state
        if to not in ALLOWED_TRANSITIONS.get(src, set()):
            # Forbidden transition — raise (threat T-15-04-01).
            raise ValueError(
                f"Illegal FSM transition: {src.name} -> {to.name}"
            )
        tid = TRANSITION_TABLE[(src, to)]
        self._state = to
        self._state_bar_entered = bar_index
        if to == TradeState.IDLE:
            # Clear per-trade context on IDLE (threat T-15-04-05)
            self._pending.clear()
            self._resting_limits.clear()
            self._watched_uids.clear()
            self._armed_level_uid = None
            self._armed_side = None

        log.info(
            "fsm.transition",
            src=src.name, dst=to.name, tid=tid.value,
            trigger=trigger, regime=regime, confluence_score=confluence_score,
            bar_index=bar_index,
        )
        if self.event_writer is not None and hasattr(self.event_writer, "record_transition"):
            self.event_writer.record_transition(
                bar_ts=bar_ts,
                bar_index=bar_index,
                from_state=src.name,
                to_state=to.name,
                transition_id=tid.value,
                trigger=trigger,
                regime=regime,
                confluence_score=confluence_score,
                payload=payload,
            )

    def _force_idle(
        self, bar, bar_index: int, intents: list[OrderIntent], *,
        trigger: str, reason: str,
    ) -> None:
        """Emergency path: cancel orders + collapse to IDLE via the allowed edge."""
        if self._state == TradeState.IDLE:
            return
        # Cancel any resting limits first
        for oi in self._resting_limits:
            intents.append(OrderIntent(
                action="CANCEL", side=oi.side, trigger_id=oi.trigger_id,
                reason=f"{reason} (cancel resting limit)", level_uid=oi.level_uid,
            ))
        # Route via the correct outgoing edge; only WATCHING/ARMED have a direct
        # IDLE edge. For other states, we must traverse via EXITING -> IDLE.
        if self._state in (TradeState.WATCHING, TradeState.ARMED, TradeState.TRIGGERED):
            to_state = TradeState.IDLE
        elif self._state in (TradeState.IN_POSITION, TradeState.MANAGING):
            # Route IN_POSITION -> MANAGING -> EXITING is too many edges; use the
            # MANAGING -> EXITING legal edge and then EXITING -> IDLE on next tick.
            if self._state == TradeState.IN_POSITION:
                self._transition(
                    to=TradeState.MANAGING,
                    bar_ts=getattr(bar, "timestamp", time.time()),
                    bar_index=bar_index,
                    trigger=trigger, regime=None, confluence_score=None,
                    payload={"reason": reason, "route": "force_idle_pre"},
                )
            self._transition(
                to=TradeState.EXITING,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger=trigger, regime=None, confluence_score=None,
                payload={"reason": reason, "route": "force_idle"},
            )
            to_state = TradeState.IDLE
        else:  # EXITING
            to_state = TradeState.IDLE

        if self._state != TradeState.IDLE:
            self._transition(
                to=to_state,
                bar_ts=getattr(bar, "timestamp", time.time()),
                bar_index=bar_index,
                trigger=trigger, regime=None, confluence_score=None,
                payload={"reason": reason},
            )

    def _transition_to_triggered(
        self, bar, bar_index: int, scorer_result, annotations, et_id: str,
    ) -> None:
        self._transition(
            to=TradeState.TRIGGERED,
            bar_ts=getattr(bar, "timestamp", time.time()),
            bar_index=bar_index,
            trigger=et_id,
            regime=getattr(annotations, "regime", None),
            confluence_score=scorer_result.total_score,
            payload={"armed_level_uid": self._armed_level_uid},
        )

    def _transition_to_triggered_simple(self, bar, bar_index: int, et_id: str) -> None:
        self._transition(
            to=TradeState.TRIGGERED,
            bar_ts=getattr(bar, "timestamp", time.time()),
            bar_index=bar_index,
            trigger=et_id, regime=None, confluence_score=None,
            payload={},
        )

    # ------------------------------------------------------------------
    # Intent construction + policy helpers (D-23, D-24, D-26)
    # ------------------------------------------------------------------

    def _build_entry_intent(
        self, *, et: EntryTrigger, side: OrderSide, order_type: str,
        entry_price: float, lv: Level | None, bar_high: float, bar_low: float,
        atr: float, tick_size: float, level_bus: Any, scorer_result: ScorerResult,
        annotations: Any,
    ) -> OrderIntent:
        stop_price = self._compute_stop(
            entry_price=entry_price, side=side, lv=lv, atr=atr, tick_size=tick_size,
            bar_high=bar_high, bar_low=bar_low,
        )
        target_price = self._compute_target(
            entry_price=entry_price, stop_price=stop_price, side=side,
            level_bus=level_bus,
        )
        stop_distance = abs(entry_price - stop_price)
        contracts = self._compute_size(
            stop_distance=stop_distance, scorer_result=scorer_result,
            annotations=annotations,
        )
        return OrderIntent(
            action="ENTER", side=side, order_type=order_type,
            entry_price=entry_price, stop_price=stop_price, target_price=target_price,
            contracts=contracts, trigger_id=et.value,
            reason=f"FSM entry {et.value} ({et.trigger_type.value})",
            level_uid=lv.uid if lv is not None else None,
        )

    def _compute_stop(
        self, *, entry_price: float, side: OrderSide, lv: Level | None,
        atr: float, tick_size: float, bar_high: float, bar_low: float,
    ) -> float:
        """D-23: max(structural+2t, 2.0×ATR), capped at 1.5% account."""
        structural_distance = 0.0
        if lv is not None:
            if side == OrderSide.LONG:
                structural_distance = max(0.0, entry_price - lv.price_bot) + 2 * tick_size
            else:
                structural_distance = max(0.0, lv.price_top - entry_price) + 2 * tick_size
        vol_distance = 2.0 * atr
        stop_distance = max(structural_distance, vol_distance)
        # 1.5% of account cap
        max_risk_usd = self.account_balance_usd * self.fsm_config.max_account_risk_pct
        max_distance_pts = max_risk_usd / NQ_DOLLARS_PER_POINT
        stop_distance = min(stop_distance, max_distance_pts)
        if side == OrderSide.LONG:
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance

    def _compute_target(
        self, *, entry_price: float, stop_price: float, side: OrderSide, level_bus: Any,
    ) -> float:
        """D-24: opposing zone in profit direction OR 1.5R floor (whichever farther)."""
        stop_distance = abs(entry_price - stop_price)
        rr_floor = (
            entry_price + 1.5 * stop_distance
            if side == OrderSide.LONG
            else entry_price - 1.5 * stop_distance
        )
        if level_bus is None:
            return rr_floor
        # Pick nearest opposing structural level in profit direction
        opposing_kinds = (
            LevelKind.VAH, LevelKind.VAL, LevelKind.LVN,
            LevelKind.CALL_WALL, LevelKind.PUT_WALL,
        )
        candidates: list[float] = []
        try:
            all_levels = level_bus.get_top_n(50)
        except Exception:
            all_levels = []
        for lv in all_levels:
            if lv.kind not in opposing_kinds:
                continue
            if lv.state == LevelState.INVALIDATED:
                continue
            tgt = lv.midpoint()
            if side == OrderSide.LONG and tgt > entry_price:
                candidates.append(tgt)
            elif side == OrderSide.SHORT and tgt < entry_price:
                candidates.append(tgt)
        if not candidates:
            return rr_floor
        if side == OrderSide.LONG:
            primary = min(candidates)  # nearest above
            return max(primary, rr_floor)
        else:
            primary = max(candidates)  # nearest below
            return min(primary, rr_floor)

    def _compute_size(
        self, *, stop_distance: float, scorer_result: ScorerResult, annotations: Any,
    ) -> int:
        """D-26: floor(risk_budget / stop_distance × conviction × regime × recency × kelly)."""
        if stop_distance <= 0:
            return 0
        dollars_per_contract = stop_distance * NQ_DOLLARS_PER_POINT
        if dollars_per_contract <= 0:
            return 0
        base = self.fsm_config.risk_budget_usd / dollars_per_contract

        # conviction_mult
        s = scorer_result.total_score
        cats = len(scorer_result.categories_firing or [])
        if scorer_result.tier == SignalTier.TYPE_A and s >= 90 and cats >= 6:
            conviction = 1.00
        elif scorer_result.tier == SignalTier.TYPE_A and s >= 80:
            conviction = 0.75
        elif scorer_result.tier == SignalTier.TYPE_B and s >= 70:
            conviction = 0.50
        elif scorer_result.tier == SignalTier.TYPE_B and s >= 65:
            conviction = 0.30
        else:
            conviction = 0.0

        # regime_mult
        regime = getattr(annotations, "regime", "NEUTRAL")
        regime_mult = {
            "TREND": 1.00, "BALANCE": 1.00, "NEUTRAL": 1.00, "PIN": 0.80
        }.get(regime, 1.0)

        # CR-08 SUPPRESS_SHORTS: 0.6× on SHORT direction (15-03 handoff instruction)
        if (
            "SUPPRESS_SHORTS" in getattr(annotations, "flags", set())
            and scorer_result.direction < 0
        ):
            regime_mult *= 0.6

        # recency_mult: 0.5 after 2+ consecutive losses (via risk_manager if present)
        recency = 1.0
        if self.risk_manager is not None:
            consec_losses = getattr(self.risk_manager.state, "consecutive_losses", 0)
            if consec_losses >= 2:
                recency = 0.5

        raw = base * conviction * regime_mult * recency * self.fsm_config.kelly_fraction
        contracts = max(0, int(math.floor(raw)))
        contracts = min(contracts, self.execution_config.max_position_contracts)
        return contracts


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _find_by_uid(level_bus: Any, uid: int | None) -> Level | None:
    if uid is None or level_bus is None:
        return None
    try:
        # Direct access to private list when available — minimal API surface
        for lv in getattr(level_bus, "_levels", []):
            if lv.uid == uid:
                return lv
    except Exception:  # pragma: no cover
        pass
    # Fallback: iterate get_top_n(large)
    try:
        for lv in level_bus.get_top_n(1000):
            if lv.uid == uid:
                return lv
    except Exception:  # pragma: no cover
        pass
    return None


_STATE_HANDLERS: dict[TradeState, Callable] = {
    TradeState.IDLE: TradeDecisionMachine._handle_idle,
    TradeState.WATCHING: TradeDecisionMachine._handle_watching,
    TradeState.ARMED: TradeDecisionMachine._handle_armed,
    TradeState.TRIGGERED: TradeDecisionMachine._handle_triggered,
    TradeState.IN_POSITION: TradeDecisionMachine._handle_in_position,
    TradeState.MANAGING: TradeDecisionMachine._handle_managing,
    TradeState.EXITING: TradeDecisionMachine._handle_exiting,
}
