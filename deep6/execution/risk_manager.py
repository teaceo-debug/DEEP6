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
    last_loss_time: float = 0.0
    last_loss_direction: int = 0  # +1 LONG, -1 SHORT, 0 none
    risk_per_trade_R: float = 100.0  # copied from config for the daily_R_ratio property

    @property
    def daily_R_ratio(self) -> float:
        """Daily PnL expressed in R units (risk_per_trade_R)."""
        if self.risk_per_trade_R <= 0.0:
            return 0.0
        return self.daily_pnl / self.risk_per_trade_R


class RiskManager:
    """Stateful circuit breaker manager.

    Query can_enter() before every entry attempt.
    Call record_trade() after every position close.
    Call reset_daily() at RTH session open.
    """

    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config
        self.state = RiskState(risk_per_trade_R=config.risk_per_trade_R)

    # Back-compat alias for cfg-style tests
    @property
    def cfg(self) -> ExecutionConfig:
        return self.config

    def can_enter(
        self,
        result: ScorerResult,
        gex_signal: GexSignal | None = None,
        open_positions: list | None = None,
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

        # Graduated drawdown response (<= -4R handled above at daily_loss_limit)
        r = st.daily_R_ratio
        if r <= -3.0:
            # TYPE_A score >= 90 with absorption only
            if result.tier != SignalTier.TYPE_A:
                return GateResult(False, f"DD -3R: TYPE_A only (daily_R={r:.2f})")
            if result.total_score < 90:
                return GateResult(False, f"DD -3R: score>=90 required (daily_R={r:.2f})")
            if "absorption" not in result.categories_firing:
                return GateResult(False, f"DD -3R: absorption required (daily_R={r:.2f})")
        elif r <= -2.0:
            # 1 contract only, score >= 85 only
            if result.total_score < 85:
                return GateResult(False, f"DD -2R: score>=85 required (daily_R={r:.2f})")
            if result.tier == SignalTier.TYPE_B:
                return GateResult(False, f"DD -2R: TYPE_B blocked (daily_R={r:.2f})")
        # -1R..-2R: half-size only — enforced in size_contracts(); no gate block here.

        # Loss cooldown: no new entry within N minutes of a closed loss in same direction.
        if (
            st.last_loss_time > 0.0
            and st.last_loss_direction != 0
            and result.direction == st.last_loss_direction
        ):
            cooldown_secs = cfg.loss_cooldown_minutes * 60.0
            elapsed = now - st.last_loss_time
            if elapsed < cooldown_secs:
                remaining = (cooldown_secs - elapsed) / 60.0
                return GateResult(
                    False,
                    f"Loss cooldown: {remaining:.1f}min remaining in same direction",
                )

        # Heat management: aggregate open-risk USD cap
        if open_positions:
            open_risk = 0.0
            for pos in open_positions:
                r_dist = getattr(pos, "r_distance", None)
                if r_dist is None:
                    # Fallback: derive from entry/stop
                    r_dist = abs(pos.entry_price - pos.stop_price)
                contracts = getattr(pos, "remaining_contracts", None) or pos.contracts
                open_risk += r_dist * contracts * 50.0  # NQ $50/point
            if open_risk > cfg.max_open_risk_usd:
                return GateResult(
                    False,
                    f"Heat cap: open risk {open_risk:.0f} > {cfg.max_open_risk_usd:.0f} USD",
                )

        # --- GEX regime gate (D-16, D-17) ---
        if gex_signal is not None:
            gate = self._check_gex_gate(result, gex_signal)
            if not gate.allowed:
                return gate

        return GateResult(True, "OK")

    def size_contracts(
        self,
        result: ScorerResult,
        narrative,
        gex_signal: GexSignal | None = None,
        vpin=None,
        hmm_regime: str | None = None,
    ) -> int:
        """Variable position sizing by score + regime + microstructure.

        Returns 0 when any skip condition triggers.
        """
        cfg = self.cfg

        # --- Skip conditions ---
        if result.tier == SignalTier.TYPE_B and result.total_score < 80:
            return 0
        if vpin is not None:
            fr = getattr(vpin, "flow_regime", None)
            fr_name = fr.name if fr is not None and hasattr(fr, "name") else (
                fr if isinstance(fr, str) else None
            )
            if fr_name == "TOXIC":
                return 0
        if hmm_regime in ("CHAOTIC",):
            return 0

        # Graduated-DD hard caps
        r = self.state.daily_R_ratio
        dd_cap: int | None = None
        if r <= -3.0:
            dd_cap = 1  # also requires score>=90 + TYPE_A + absorption (enforced in can_enter)
        elif r <= -2.0:
            dd_cap = 1
        elif r <= -1.0:
            dd_cap = None  # half size handled by multiplier below
        half_size = (-2.0 < r <= -1.0)

        # Base size by score (half-Kelly scaled)
        s = result.total_score
        if s >= 90:
            base = 3
        elif s >= 80:
            base = 2
        elif s >= 70:
            base = 1
        else:
            return 0

        # Multipliers
        m = float(getattr(narrative, "strength", 1.0) or 1.0)
        if gex_signal is not None:
            reg = getattr(gex_signal.regime, "name", str(gex_signal.regime))
            if reg == "POSITIVE_DAMPENING" and result.tier == SignalTier.TYPE_A:
                m *= 1.15
            if reg == "NEGATIVE_AMPLIFYING":
                m *= 0.5
        if vpin is not None:
            fr = getattr(vpin, "flow_regime", None)
            fr_name = fr.name if fr is not None and hasattr(fr, "name") else (
                fr if isinstance(fr, str) else None
            )
            if fr_name == "ELEVATED":
                m *= 0.67
        if hmm_regime == "TRENDING":
            m *= 0.75  # TYPE_A reversals fail more in trending

        if half_size:
            m *= 0.5

        contracts = max(0, min(cfg.max_position_contracts, round(base * m)))
        if dd_cap is not None:
            contracts = min(contracts, dd_cap)
        return int(contracts)

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

    def record_trade(self, pnl: float, direction: int = 0) -> None:
        """Update risk state after a position closes.

        Called by PaperTrader/LiveTrader on every STOP_HIT, TARGET_HIT, TIMEOUT_EXIT.
        ``direction`` is +1 (LONG) or -1 (SHORT); used for loss-cooldown gating.
        """
        self.state.daily_pnl += pnl
        self.state.trades_today += 1

        if pnl < 0.0:
            self.state.consecutive_losses += 1
            if direction != 0:
                self.state.last_loss_time = time.time()
                self.state.last_loss_direction = direction
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
        self.state = RiskState(risk_per_trade_R=self.config.risk_per_trade_R)
        log.info("risk.daily_reset")
