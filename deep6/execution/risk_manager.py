"""RiskManager — circuit breakers for Phase 8 execution layer.

Per EXEC-02, EXEC-06, and decisions D-10..D-17 from CONTEXT.md.

Circuit breakers (D-10..D-13):
  - Daily loss limit: -$500 per contract halts ALL new entries
  - Consecutive loss pause: 3 losses → 30-minute pause
  - Max position contracts: 1 during paper trading
  - Max trades per day: 10

GEX regime gate (D-16, D-17):
  - NEGATIVE_AMPLIFYING: block TYPE_B; TYPE_A requires absorption (not exhaustion alone)
  - Wall conflict (LONG at call wall, SHORT at put wall): blocked regardless of tier

All state is mutable (not frozen) — accumulates intraday.
reset_daily() called by SessionManager at RTH open.
"""
from __future__ import annotations

import time
from collections import namedtuple
from dataclasses import dataclass, field

import structlog

from deep6.execution.config import ExecutionConfig
from deep6.engines.gex import GexSignal, GexRegime
from deep6.scoring.scorer import ScorerResult, SignalTier

log = structlog.get_logger()

GateResult = namedtuple("GateResult", ["allowed", "reason"])


@dataclass
class RiskState:
    """Mutable intraday risk accumulator. Reset by reset_daily() at session open."""
    daily_pnl: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    paused_until: float = 0.0     # Unix timestamp; 0.0 = not paused


class RiskManager:
    """Stateful circuit breaker manager.

    Query can_enter() before every entry attempt.
    Call record_trade() after every position close.
    Call reset_daily() at RTH session open.
    """

    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config
        self.state = RiskState()

    def can_enter(
        self,
        result: ScorerResult,
        gex_signal: GexSignal | None = None,
    ) -> GateResult:
        """Check all risk gates. Returns GateResult(True, "OK") if all pass.

        Gates evaluated in order — first failure returns immediately.
        """
        cfg = self.config
        st = self.state

        # --- Circuit breakers (D-10..D-13) ---

        # D-10: Daily loss limit
        if st.daily_pnl <= -cfg.daily_loss_limit:
            log.warning(
                "risk.daily_loss_limit_hit",
                daily_pnl=st.daily_pnl,
                limit=cfg.daily_loss_limit,
            )
            return GateResult(
                False,
                f"Daily loss limit hit: {st.daily_pnl:.2f} USD (limit: -{cfg.daily_loss_limit:.0f})",
            )

        # D-11: Consecutive loss pause
        now = time.time()
        if now < st.paused_until:
            remaining = (st.paused_until - now) / 60.0
            return GateResult(False, f"Consecutive loss pause active: {remaining:.1f} min remaining")

        # D-13: Max trades per day
        if st.trades_today >= cfg.max_trades_per_day:
            return GateResult(
                False,
                f"Max trades per day reached: {st.trades_today}/{cfg.max_trades_per_day}",
            )

        # --- GEX regime gate (D-16, D-17) ---
        if gex_signal is not None:
            gate = self._check_gex_gate(result, gex_signal)
            if not gate.allowed:
                return gate

        return GateResult(True, "OK")

    def _check_gex_gate(self, result: ScorerResult, gex: GexSignal) -> GateResult:
        """GEX regime and wall conflict gate (D-16, D-17).

        D-16: NEGATIVE_AMPLIFYING blocks TYPE_B; TYPE_A requires absorption (not exhaustion alone)
        D-17: LONG at call_wall or SHORT at put_wall → block regardless of tier
        """
        # D-17: Wall conflict — fighting dealer hedging flow
        if gex.near_call_wall and result.direction > 0:
            return GateResult(False, "Wall conflict: LONG at call wall (dealer selling) — D-17")
        if gex.near_put_wall and result.direction < 0:
            return GateResult(False, "Wall conflict: SHORT at put wall (dealer buying) — D-17")

        # D-16: NEGATIVE_AMPLIFYING regime restrictions
        if gex.regime == GexRegime.NEGATIVE_AMPLIFYING:
            if result.tier == SignalTier.TYPE_B:
                return GateResult(False, "NEGATIVE_AMPLIFYING regime: TYPE_B blocked — D-16")
            if result.tier == SignalTier.TYPE_A:
                has_absorption = "absorption" in result.categories_firing
                if not has_absorption:
                    return GateResult(
                        False,
                        "NEGATIVE_AMPLIFYING regime: TYPE_A requires absorption signal "
                        "(exhaustion alone insufficient) — D-16",
                    )

        return GateResult(True, "GEX gate passed")

    def record_trade(self, pnl: float) -> None:
        """Update risk state after a position closes.

        Called by PaperTrader/LiveTrader on every STOP_HIT, TARGET_HIT, TIMEOUT_EXIT.
        """
        self.state.daily_pnl += pnl
        self.state.trades_today += 1

        if pnl < 0.0:
            self.state.consecutive_losses += 1
            log.info(
                "risk.loss_recorded",
                pnl=pnl,
                consecutive=self.state.consecutive_losses,
                daily_pnl=self.state.daily_pnl,
            )
            if self.state.consecutive_losses >= self.config.consecutive_loss_limit:
                pause_secs = self.config.pause_minutes * 60
                self.state.paused_until = time.time() + pause_secs
                log.warning(
                    "risk.consecutive_loss_pause",
                    consecutive=self.state.consecutive_losses,
                    pause_minutes=self.config.pause_minutes,
                )
        else:
            # D-11: Win resets consecutive loss counter
            self.state.consecutive_losses = 0
            log.info("risk.win_recorded", pnl=pnl, daily_pnl=self.state.daily_pnl)

    def reset_daily(self) -> None:
        """Reset all intraday accumulators. Called at RTH session open."""
        self.state = RiskState()
        log.info("risk.daily_reset")
