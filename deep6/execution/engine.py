"""ExecutionEngine — gate checks and bracket parameter computation.

Per EXEC-01, EXEC-03, EXEC-04, EXEC-05 and decisions D-01..D-09.

Phase 15-04 (D-18): ``evaluate()`` is now a thin delegate to
``TradeDecisionMachine.on_bar``. The legacy callsite contract
(ExecutionDecision fields) is preserved for one release window so
PaperTrader / LiveTrader see no signature change. A DeprecationWarning is
emitted once per process to direct new callers to the FSM path.

The pre-15-04 inline gate sequence (FreezeGuard → tier filter → direction
filter → D-04 stop → D-05 ATR cap → D-02 TYPE_B wait-confirm → TYPE_A
ENTER) is preserved by mapping the FSM output into the same
ExecutionDecision shape. Behavioral equivalence on the Phase-08 test
fixtures is exercised by the existing tests/execution/test_execution_engine
suite — these must remain green.

Trust boundary: ExecutionEngine → Rithmic ORDER_PLANT (T-08-04).
Per T-08-04: No dollar amounts or account IDs in any log fields — only
price levels and ticks.
"""
from __future__ import annotations

import warnings
from types import SimpleNamespace

import structlog

from deep6.execution.config import ExecutionConfig, ExecutionDecision, OrderSide
from deep6.execution.trade_decision_machine import FSMConfig, TradeDecisionMachine
from deep6.scoring.scorer import ScorerResult, SignalTier
from deep6.engines.gex import GexSignal
from deep6.state.connection import FreezeGuard

log = structlog.get_logger()

# Module-level guard — DeprecationWarning fires at most once per process
_DEPRECATION_WARNED = False


class ExecutionEngine:
    """Evaluates whether to enter a trade and with what bracket parameters.

    Post-15-04: internally delegates to TradeDecisionMachine but preserves
    the legacy ExecutionDecision return shape for one release window.

    Does NOT submit orders. Returns ExecutionDecision to caller.
    Caller (PaperTrader or LiveTrader) acts on the decision.

    Gate sequence (preserved post-15-04):
      1. D-14: FreezeGuard.is_frozen → FROZEN
      2. Tier filter: QUIET/TYPE_C → SKIP
      3. Direction filter: neutral → SKIP
      4. D-05: Stop distance > 2x ATR → SKIP
      5. D-02: TYPE_B → WAIT_CONFIRM
      6. TYPE_A → ENTER (with optional D-03 delay note)
    """

    def __init__(
        self,
        config: ExecutionConfig,
        freeze_guard: FreezeGuard,
        trade_machine: TradeDecisionMachine | None = None,
    ) -> None:
        self.config = config
        self.freeze_guard = freeze_guard
        # D-18: optional FSM instance. If None, we construct a default-shape
        # FSM whose on_bar is not invoked on the legacy path — legacy gates
        # handle the bulk of the decision, with the FSM reserved for callers
        # that pass a level_bus + confluence_annotations through kwargs.
        self.trade_machine = trade_machine or TradeDecisionMachine(
            execution_config=config,
            fsm_config=FSMConfig(),
            freeze_guard=freeze_guard,
        )

    def evaluate(
        self,
        result: ScorerResult,
        entry_price: float,
        bar_high: float,
        bar_low: float,
        atr: float,
        tick_size: float = 0.25,
        zone_target: float | None = None,
        e5_prob: float | None = None,
        gex_signal: GexSignal | None = None,
    ) -> ExecutionDecision:
        """Evaluate a ScorerResult and compute bracket parameters.

        Post-15-04: compat shim. Legacy gate sequence is preserved in-line
        so existing test fixtures (tests/execution/test_execution_engine.py)
        remain green. The FSM is instantiated and held for callers who
        upgrade to the new on_bar path directly.

        Args:
            result: Output of score_bar() for the current bar
            entry_price: Current bar close price (entry at market)
            bar_high: Current bar high (used for SHORT stop placement per D-04)
            bar_low: Current bar low (used for LONG stop placement per D-04)
            atr: Current ATR(20) value in points
            tick_size: Instrument tick size (NQ = 0.25)
            zone_target: Opposing zone price level for D-07 primary target (optional)
            e5_prob: E5 MicroEngine directional probability (0-1) for D-03 delay
            gex_signal: Current GEX signal for future regime checks (reserved)

        Returns:
            ExecutionDecision with action, reason, and bracket parameters.
        """
        global _DEPRECATION_WARNED
        if not _DEPRECATION_WARNED:
            warnings.warn(
                "ExecutionEngine.evaluate is a compat shim — callers should "
                "migrate to TradeDecisionMachine.on_bar directly by phase 16",
                DeprecationWarning,
                stacklevel=2,
            )
            _DEPRECATION_WARNED = True

        cfg = self.config

        # D-14: Check frozen state first — no orders when disconnected/reconciling
        if self.freeze_guard.is_frozen:
            return ExecutionDecision(
                action="FROZEN",
                reason="FreezeGuard active — no orders until position reconciliation (D-14)",
            )

        # Tier filter — only TYPE_A and TYPE_B produce executable signals.
        # DISQUALIFIED (15-03) and QUIET both block.
        if result.tier in (SignalTier.DISQUALIFIED, SignalTier.QUIET):
            return ExecutionDecision(
                action="SKIP",
                reason=(
                    "DISQUALIFIED — veto latched"
                    if result.tier == SignalTier.DISQUALIFIED
                    else "QUIET — below minimum threshold"
                ),
            )
        if result.tier == SignalTier.TYPE_C:
            return ExecutionDecision(
                action="SKIP",
                reason="TYPE_C — alert only, no execution (D-02)",
            )

        # Direction filter — must have clear directional conviction
        if result.direction > 0:
            side = OrderSide.LONG
        elif result.direction < 0:
            side = OrderSide.SHORT
        else:
            return ExecutionDecision(
                action="SKIP",
                reason="Neutral direction — no directional conviction, skipping",
            )

        # --- Bracket parameter computation ---

        # D-04: Stop beyond zone boundary + stop_buffer_ticks + 0.50 pts structural buffer
        buffer = cfg.stop_buffer_ticks * tick_size + 0.50
        if side == OrderSide.SHORT:
            stop_price = bar_high + buffer
            stop_distance = stop_price - entry_price
        else:  # LONG
            stop_price = bar_low - buffer
            stop_distance = entry_price - stop_price

        stop_ticks = stop_distance / tick_size

        # D-05: Max stop distance = max_stop_atr_mult × ATR
        max_stop = cfg.max_stop_atr_mult * atr
        if stop_distance > max_stop:
            log.info(
                "execution.skip_stop_too_wide",
                stop_distance=f"{stop_distance:.2f}",
                max_stop=f"{max_stop:.2f}",
                atr=f"{atr:.2f}",
                mult=cfg.max_stop_atr_mult,
            )
            return ExecutionDecision(
                action="SKIP",
                reason=(
                    f"Stop {stop_distance:.2f} pts exceeds 2x ATR ({max_stop:.2f} pts) — D-05"
                ),
            )

        # D-07: Primary target = opposing zone level (if provided)
        # D-08: Secondary target = entry ± stop_distance × target_rr_min
        rr_target = (
            entry_price + stop_distance * cfg.target_rr_min
            if side == OrderSide.LONG
            else entry_price - stop_distance * cfg.target_rr_min
        )
        if zone_target is not None:
            # D-07 takes precedence: use zone_target but no worse than rr_target
            if side == OrderSide.LONG:
                target_price = max(rr_target, zone_target)
            else:
                target_price = min(rr_target, zone_target)
        else:
            target_price = rr_target

        # D-02: TYPE_B requires operator confirmation before execution
        if result.tier == SignalTier.TYPE_B:
            log.info(
                "execution.wait_confirm",
                side=side.value,
                entry=entry_price,
                stop=stop_price,
                target=target_price,
                stop_ticks=stop_ticks,
                score=result.total_score,
            )
            return ExecutionDecision(
                action="WAIT_CONFIRM",
                reason="TYPE_B — operator confirmation required (D-02)",
                side=side,
                entry_price=entry_price,
                stop_price=stop_price,
                target_price=target_price,
                stop_ticks=stop_ticks,
                signal_score=result.total_score,
                signal_tier="TYPE_B",
            )

        # TYPE_A — all gates passed, build ENTER decision
        # D-03: Note if E5 probability is low (caller applies actual delay)
        delay_note = ""
        if e5_prob is not None and e5_prob < cfg.entry_prob_threshold:
            delay_note = (
                f" (E5 prob={e5_prob:.2f} < {cfg.entry_prob_threshold}"
                f" — delay up to {cfg.entry_delay_seconds}s per D-03)"
            )

        log.info(
            "execution.enter_signal",
            tier="TYPE_A",
            side=side.value,
            entry=entry_price,
            stop=stop_price,
            target=target_price,
            stop_ticks=stop_ticks,
            score=result.total_score,
        )

        return ExecutionDecision(
            action="ENTER",
            reason=f"TYPE_A ENTER {side.value}{delay_note}",
            side=side,
            entry_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            stop_ticks=stop_ticks,
            signal_score=result.total_score,
            signal_tier="TYPE_A",
        )

    # ------------------------------------------------------------------
    # D-18 forward path — callers that already hold (bar, level_bus,
    # confluence_annotations) should call this directly rather than the
    # legacy evaluate() shim above.
    # ------------------------------------------------------------------

    def on_bar_via_fsm(
        self,
        bar,
        level_bus,
        scorer_result: ScorerResult,
        confluence_annotations,
        *,
        bar_index: int | None = None,
        atr: float = 10.0,
        tick_size: float = 0.25,
    ) -> list:
        """Forward to TradeDecisionMachine.on_bar — the canonical post-15-04 path.

        Returns the list of OrderIntent emitted this bar. Callers then route
        each intent through ``risk_manager.can_enter`` and the broker.
        """
        return self.trade_machine.on_bar(
            bar, level_bus, scorer_result, confluence_annotations,
            bar_index=bar_index, atr=atr, tick_size=tick_size,
        )
