"""PaperTrader — Phase 8 simulation mode with 30-day gate and slippage model.

Per D-18: 30-day minimum paper trading before live_mode can be enabled.
Per D-19: Real Rithmic data feed; simulated fills with slippage model.
Per D-20: Gate cannot be bypassed. Counter resets if materially different code path.

Orchestrates: ExecutionEngine → RiskManager → PositionManager → PositionEvents
"""
from __future__ import annotations

import random
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Callable

import structlog

from deep6.execution.config import ExecutionConfig, OrderSide
from deep6.execution.engine import ExecutionEngine
from deep6.execution.position_manager import PositionManager, PositionEvent, PositionEventType
from deep6.execution.risk_manager import RiskManager
from deep6.scoring.scorer import ScorerResult

log = structlog.get_logger()


@dataclass
class PaperStats:
    """Intraday and cumulative paper trading performance metrics."""
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    max_drawdown: float = 0.0
    peak_pnl: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.total_trades if self.total_trades > 0 else 0.0

    def record_trade(self, pnl: float) -> None:
        self.total_trades += 1
        self.total_pnl += pnl
        if pnl > 0:
            self.wins += 1
        else:
            self.losses += 1
        # Track drawdown from peak
        if self.total_pnl > self.peak_pnl:
            self.peak_pnl = self.total_pnl
        drawdown = self.peak_pnl - self.total_pnl
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown

    def to_dict(self) -> dict:
        return {
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "total_pnl": round(self.total_pnl, 2),
            "win_rate": round(self.win_rate, 4),
            "max_drawdown": round(self.max_drawdown, 2),
        }


class LiveGate:
    """30-day paper trading gate — enforced via SQLite persistence.

    Per D-18: 30 distinct trading days required before is_gate_open() returns True.
    Per D-20: No bypass. record_trading_day() is idempotent (safe to call every bar).

    Schema: CREATE TABLE IF NOT EXISTS paper_days (date TEXT PRIMARY KEY)
    """

    TABLE_SQL = "CREATE TABLE IF NOT EXISTS paper_days (date TEXT PRIMARY KEY)"
    INSERT_SQL = "INSERT OR IGNORE INTO paper_days (date) VALUES (?)"
    COUNT_SQL = "SELECT COUNT(*) FROM paper_days"

    def __init__(self, db_path: str, required_days: int = 30) -> None:
        self.db_path = db_path
        self.required_days = required_days
        with sqlite3.connect(db_path) as conn:
            conn.execute(self.TABLE_SQL)
            conn.commit()

    def record_trading_day(self, date_str: str) -> None:
        """Record a trading day. Idempotent — duplicates ignored."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(self.INSERT_SQL, (date_str,))
            conn.commit()

    def completed_days(self) -> int:
        """Return count of distinct trading days recorded."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(self.COUNT_SQL).fetchone()
            return row[0] if row else 0

    def is_gate_open(self) -> bool:
        """True only when required_days+ trading days completed. D-20: no bypass."""
        days = self.completed_days()
        if days >= self.required_days:
            log.info(
                "live_gate.open",
                completed_days=days,
                required=self.required_days,
            )
            return True
        log.info(
            "live_gate.closed",
            completed_days=days,
            required=self.required_days,
            remaining=self.required_days - days,
        )
        return False


class PaperTrader:
    """Top-level paper trading orchestrator.

    Wires ExecutionEngine → RiskManager → PositionManager for every bar close.
    Uses real Rithmic price data; fills are simulated with slippage model (D-19).
    30-day gate enforced by LiveGate (D-18, D-20).

    Call complete_bar() at every bar close where a ScorerResult is available.
    Call reset_daily() at RTH session open.
    """

    def __init__(
        self,
        config: ExecutionConfig,
        db_path: str,
        on_event: Callable[[PositionEvent], None] | None = None,
    ) -> None:
        self.config = config
        self._stats = PaperStats()
        self._events: list[PositionEvent] = []

        def _route_event(ev: PositionEvent) -> None:
            self._events.append(ev)
            if on_event is not None:
                try:
                    on_event(ev)
                except Exception as exc:
                    log.error("paper_trader.event_callback_error", error=str(exc))

        from deep6.state.connection import FreezeGuard
        self._freeze_guard = FreezeGuard()
        self.engine = ExecutionEngine(config, self._freeze_guard)
        self.risk = RiskManager(config)
        self.positions = PositionManager(config, _route_event)
        self.live_gate = LiveGate(db_path, config.paper_trading_days)

    def _simulate_fill(self, decision, tick_size: float) -> float:
        """Apply slippage model (D-19): 1 fixed tick + 0 or 1 random tick.

        LONG: fill = entry + slippage (adverse)
        SHORT: fill = entry - slippage (adverse)
        """
        fixed = self.config.paper_slippage_fixed_ticks * tick_size
        rand = random.randint(0, self.config.paper_slippage_random_ticks) * tick_size
        slippage = fixed + rand
        if decision.side == OrderSide.LONG:
            return decision.entry_price + slippage
        else:
            return decision.entry_price - slippage

    def complete_bar(
        self,
        result: ScorerResult,
        bar_close: float,
        bar_high: float,
        bar_low: float,
        atr: float,
        tick_size: float = 0.25,
        gex_signal=None,
        zone_target: float | None = None,
        e5_prob: float | None = None,
        date_str: str | None = None,
    ) -> list[PositionEvent]:
        """Full bar-close pipeline: evaluate → gate → fill → track.

        Returns list of PositionEvents fired this bar (may be empty).
        """
        from datetime import date as _date
        ds = date_str or _date.today().isoformat()
        self.live_gate.record_trading_day(ds)

        # Evaluate entry opportunity
        decision = self.engine.evaluate(
            result=result,
            entry_price=bar_close,
            bar_high=bar_high,
            bar_low=bar_low,
            atr=atr,
            tick_size=tick_size,
            zone_target=zone_target,
            e5_prob=e5_prob,
            gex_signal=gex_signal,
        )

        if decision.action == "ENTER":
            gate = self.risk.can_enter(result, gex_signal)
            if gate.allowed:
                fill_price = self._simulate_fill(decision, tick_size)
                # Rebuild decision with simulated fill price
                from dataclasses import replace
                filled_decision = replace(decision, entry_price=fill_price)
                try:
                    self.positions.open_position(filled_decision)
                    log.info(
                        "paper_trader.enter",
                        fill=fill_price,
                        stop=decision.stop_price,
                        target=decision.target_price,
                        score=decision.signal_score,
                        tier=decision.signal_tier,
                    )
                except ValueError as exc:
                    log.warning("paper_trader.position_limit", error=str(exc))
            else:
                log.info(
                    "paper_trader.gate_blocked",
                    reason=gate.reason,
                    tier=result.tier.name,
                )
        else:
            log.debug(
                "paper_trader.skip",
                action=decision.action,
                reason=decision.reason,
            )

        # Evaluate open positions against this bar
        close_events = self.positions.on_bar(bar_close, bar_high, bar_low, result)
        for ev in close_events:
            if ev.event_type in (
                PositionEventType.STOP_HIT,
                PositionEventType.TARGET_HIT,
                PositionEventType.TIMEOUT_EXIT,
                PositionEventType.MANUAL_EXIT,
            ):
                self.risk.record_trade(ev.pnl)
                self._stats.record_trade(ev.pnl)
                log.info(
                    "paper_trader.trade_closed",
                    event_type=ev.event_type.value,
                    pnl=ev.pnl,
                    bars=ev.bars_held,
                    total_pnl=self._stats.total_pnl,
                    win_rate=self._stats.win_rate,
                )

        return close_events

    def reset_daily(self) -> None:
        """Called at RTH session open. Resets intraday risk accumulators."""
        self.risk.reset_daily()
        log.info("paper_trader.daily_reset", stats=self._stats.to_dict())

    @property
    def paper_stats(self) -> PaperStats:
        return self._stats

    @property
    def is_ready_for_live(self) -> bool:
        """True only when 30-day paper gate is complete. D-20: no bypass."""
        return self.live_gate.is_gate_open()
