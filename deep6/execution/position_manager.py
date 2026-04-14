"""Position lifecycle management for Phase 8 execution layer.

Tracks all open positions, enforces max hold time (D-09), moves stop to
breakeven on absorption confirmation (D-06), and emits structured events
consumed by Phase 9 ML backend and Phase 10 dashboard.

Per D-21: tracks entry_price, stop, target, bars_held, unrealized_pnl.
Per D-22: emits events on entry, stop_hit, target_hit, timeout_exit, manual_exit.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import structlog

from deep6.execution.config import ExecutionConfig, ExecutionDecision, OrderSide
from deep6.scoring.scorer import ScorerResult

log = structlog.get_logger()

NQ_DOLLARS_PER_POINT = 50.0


class PositionEventType(str, Enum):
    ENTRY = "ENTRY"
    STOP_HIT = "STOP_HIT"
    TARGET_HIT = "TARGET_HIT"
    TIMEOUT_EXIT = "TIMEOUT_EXIT"
    MANUAL_EXIT = "MANUAL_EXIT"
    BREAKEVEN_MOVE = "BREAKEVEN_MOVE"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    TRAIL_MOVE = "TRAIL_MOVE"


@dataclass
class Position:
    """Single open position with full lifecycle state."""
    id: str
    side: OrderSide
    entry_price: float
    stop_price: float
    target_price: float
    contracts: int
    signal_score: float
    signal_tier: str
    open_ts: float = field(default_factory=time.time)
    bars_held: int = 0
    is_breakeven: bool = False
    unrealized_pnl: float = 0.0

    # Scale-out / trailing state
    initial_contracts: int = 0          # Set by PositionManager.open_position
    remaining_contracts: int = 0        # Decremented on each partial exit
    partial_exits: list[dict] = field(default_factory=list)  # [{bar, contracts, price, reason}]
    r_distance: float = 0.0             # |entry - initial_stop| in price points
    breakeven_moved_at: int | None = None  # bar index when BE move occurred
    trail_stop: float | None = None     # Active trailing stop price (final 1/3)
    recent_highs: list[float] = field(default_factory=list)  # last 5 bar highs (for SHORT trail)
    recent_lows: list[float] = field(default_factory=list)   # last 5 bar lows (for LONG trail)

    @property
    def direction(self) -> int:
        return +1 if self.side == OrderSide.LONG else -1

    def update_pnl(self, current_price: float) -> None:
        """Update unrealized P&L based on current price.
        NQ = $50 per point per contract.
        """
        contracts = self.remaining_contracts or self.contracts
        self.unrealized_pnl = (
            (current_price - self.entry_price)
            * self.direction
            * NQ_DOLLARS_PER_POINT
            * contracts
        )


@dataclass
class PositionEvent:
    """Structured event emitted on every position lifecycle transition.
    JSON-serializable for Phase 9 ML ingest and Phase 10 dashboard push.
    """
    event_type: PositionEventType
    position_id: str
    side: OrderSide
    entry_price: float
    exit_price: float
    pnl: float
    bars_held: int
    ts: float
    signal_tier: str
    signal_score: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict:
        """Return plain dict — Enum values serialized as strings."""
        return {
            "event_type": self.event_type.value,
            "position_id": self.position_id,
            "side": self.side.value,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "pnl": self.pnl,
            "bars_held": self.bars_held,
            "ts": self.ts,
            "signal_tier": self.signal_tier,
            "signal_score": self.signal_score,
            "reason": self.reason,
        }


class PositionManager:
    """Manages open position lifecycle.

    Call open_position() on ENTER decision.
    Call on_bar() at every bar close — handles stop/target/timeout/breakeven.
    Call close_position() for manual exits.

    on_event callback receives every PositionEvent for Phase 9/10 routing.
    """

    def __init__(
        self,
        config: ExecutionConfig,
        on_event: Callable[[PositionEvent], None],
    ) -> None:
        self.config = config
        self._on_event = on_event
        self._positions: dict[str, Position] = {}

    @property
    def positions(self) -> list[Position]:
        """Read-only snapshot of open positions."""
        return list(self._positions.values())

    @property
    def position_count(self) -> int:
        return len(self._positions)

    def open_position(self, decision: ExecutionDecision, contracts: int = 1) -> Position:
        """Open a new position from an ENTER decision.

        Raises ValueError if max_position_contracts would be exceeded.
        Emits ENTRY PositionEvent.
        """
        total_contracts = sum(p.contracts for p in self._positions.values()) + contracts
        if total_contracts > self.config.max_position_contracts:
            raise ValueError(
                f"Cannot open {contracts} contract(s): would exceed max "
                f"{self.config.max_position_contracts} (currently {self.position_count} open)"
            )

        pos = Position(
            id=str(uuid.uuid4()),
            side=decision.side,
            entry_price=decision.entry_price,
            stop_price=decision.stop_price,
            target_price=decision.target_price,
            contracts=contracts,
            signal_score=decision.signal_score,
            signal_tier=decision.signal_tier,
            initial_contracts=contracts,
            remaining_contracts=contracts,
            r_distance=abs(decision.entry_price - decision.stop_price),
        )
        self._positions[pos.id] = pos

        event = PositionEvent(
            event_type=PositionEventType.ENTRY,
            position_id=pos.id,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=0.0,
            pnl=0.0,
            bars_held=0,
            ts=pos.open_ts,
            signal_tier=pos.signal_tier,
            signal_score=pos.signal_score,
            reason=decision.reason,
        )
        self._on_event(event)
        log.info(
            "position.opened",
            id=pos.id,
            side=pos.side.value,
            entry=pos.entry_price,
            stop=pos.stop_price,
            target=pos.target_price,
        )
        return pos

    def on_bar(
        self,
        bar_close: float,
        bar_high: float,
        bar_low: float,
        result: ScorerResult,
        atr: float = 10.0,
    ) -> list[PositionEvent]:
        """Evaluate all open positions against current bar.

        Called at every bar close. Returns list of events fired this bar.
        Positions closed this bar are removed from _positions.
        """
        events: list[PositionEvent] = []
        to_close: list[tuple[str, PositionEventType, float, str]] = []

        for pos in list(self._positions.values()):
            pos.bars_held += 1
            pos.update_pnl(bar_close)

            # Maintain last-5 bar swing highs/lows for trailing
            pos.recent_highs.append(bar_high)
            pos.recent_lows.append(bar_low)
            if len(pos.recent_highs) > 5:
                pos.recent_highs.pop(0)
            if len(pos.recent_lows) > 5:
                pos.recent_lows.pop(0)

            # --- Scale-out partials + trail (new) ---
            if pos.r_distance > 0.0:
                favorable = (bar_close - pos.entry_price) * pos.direction
                r_mult = favorable / pos.r_distance

                # Partial 1: +1R -> take 1/3 off, move stop to BE - 1 tick
                if r_mult >= 1.0 and pos.breakeven_moved_at is None:
                    partial_qty = max(1, pos.initial_contracts // 3)
                    partial_qty = min(partial_qty, pos.remaining_contracts)
                    if partial_qty > 0 and pos.remaining_contracts > partial_qty:
                        exit_price = bar_close
                        partial_pnl = (
                            (exit_price - pos.entry_price)
                            * pos.direction
                            * NQ_DOLLARS_PER_POINT
                            * partial_qty
                        )
                        pos.remaining_contracts -= partial_qty
                        pos.partial_exits.append({
                            "bar": pos.bars_held,
                            "contracts": partial_qty,
                            "price": exit_price,
                            "reason": "+1R partial",
                        })
                        # BE - 1 tick (NQ tick = 0.25)
                        tick = 0.25
                        new_stop = pos.entry_price - (tick * pos.direction)
                        pos.stop_price = new_stop
                        pos.is_breakeven = True
                        pos.breakeven_moved_at = pos.bars_held
                        ev_p = PositionEvent(
                            event_type=PositionEventType.PARTIAL_EXIT,
                            position_id=pos.id,
                            side=pos.side,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            pnl=partial_pnl,
                            bars_held=pos.bars_held,
                            ts=time.time(),
                            signal_tier=pos.signal_tier,
                            signal_score=pos.signal_score,
                            reason=f"+1R partial: {partial_qty}c, stop->BE-1t",
                        )
                        self._on_event(ev_p)
                        events.append(ev_p)

                # Partial 2: +1.5R -> another 1/3 off
                elif r_mult >= 1.5 and len(pos.partial_exits) < 2 and pos.remaining_contracts > 1:
                    partial_qty = max(1, pos.initial_contracts // 3)
                    partial_qty = min(partial_qty, pos.remaining_contracts - 1)
                    if partial_qty > 0:
                        exit_price = bar_close
                        partial_pnl = (
                            (exit_price - pos.entry_price)
                            * pos.direction
                            * NQ_DOLLARS_PER_POINT
                            * partial_qty
                        )
                        pos.remaining_contracts -= partial_qty
                        pos.partial_exits.append({
                            "bar": pos.bars_held,
                            "contracts": partial_qty,
                            "price": exit_price,
                            "reason": "+1.5R partial",
                        })
                        ev_p = PositionEvent(
                            event_type=PositionEventType.PARTIAL_EXIT,
                            position_id=pos.id,
                            side=pos.side,
                            entry_price=pos.entry_price,
                            exit_price=exit_price,
                            pnl=partial_pnl,
                            bars_held=pos.bars_held,
                            ts=time.time(),
                            signal_tier=pos.signal_tier,
                            signal_score=pos.signal_score,
                            reason=f"+1.5R partial: {partial_qty}c",
                        )
                        self._on_event(ev_p)
                        events.append(ev_p)

                # Trailing: after 2 partials, trail the last 1/3 by max(ATR*0.75, 5-bar swing)
                if len(pos.partial_exits) >= 2 and pos.remaining_contracts > 0:
                    atr_trail = atr * 0.75
                    if pos.side == OrderSide.LONG:
                        swing = min(pos.recent_lows) if pos.recent_lows else bar_low
                        # Trail = max(close - atr*.75, swing_low_5bar)  -> higher is tighter
                        candidate = max(bar_close - atr_trail, swing)
                        if pos.trail_stop is None or candidate > pos.trail_stop:
                            old = pos.trail_stop
                            pos.trail_stop = candidate
                            if candidate > pos.stop_price:
                                pos.stop_price = candidate
                                ev_t = PositionEvent(
                                    event_type=PositionEventType.TRAIL_MOVE,
                                    position_id=pos.id,
                                    side=pos.side,
                                    entry_price=pos.entry_price,
                                    exit_price=0.0,
                                    pnl=pos.unrealized_pnl,
                                    bars_held=pos.bars_held,
                                    ts=time.time(),
                                    signal_tier=pos.signal_tier,
                                    signal_score=pos.signal_score,
                                    reason=f"Trail: {old} -> {candidate:.2f}",
                                )
                                self._on_event(ev_t)
                                events.append(ev_t)
                    else:  # SHORT
                        swing = max(pos.recent_highs) if pos.recent_highs else bar_high
                        candidate = min(bar_close + atr_trail, swing)
                        if pos.trail_stop is None or candidate < pos.trail_stop:
                            old = pos.trail_stop
                            pos.trail_stop = candidate
                            if candidate < pos.stop_price:
                                pos.stop_price = candidate
                                ev_t = PositionEvent(
                                    event_type=PositionEventType.TRAIL_MOVE,
                                    position_id=pos.id,
                                    side=pos.side,
                                    entry_price=pos.entry_price,
                                    exit_price=0.0,
                                    pnl=pos.unrealized_pnl,
                                    bars_held=pos.bars_held,
                                    ts=time.time(),
                                    signal_tier=pos.signal_tier,
                                    signal_score=pos.signal_score,
                                    reason=f"Trail: {old} -> {candidate:.2f}",
                                )
                                self._on_event(ev_t)
                                events.append(ev_t)

            # D-06: Move stop to breakeven after 3 bars of absorption confirmation
            if (
                not pos.is_breakeven
                and pos.bars_held >= 3
                and "absorption" in result.categories_firing
                and result.direction == pos.direction
            ):
                old_stop = pos.stop_price
                pos.stop_price = pos.entry_price
                pos.is_breakeven = True
                ev = PositionEvent(
                    event_type=PositionEventType.BREAKEVEN_MOVE,
                    position_id=pos.id,
                    side=pos.side,
                    entry_price=pos.entry_price,
                    exit_price=0.0,
                    pnl=pos.unrealized_pnl,
                    bars_held=pos.bars_held,
                    ts=time.time(),
                    signal_tier=pos.signal_tier,
                    reason=f"Breakeven: stop moved from {old_stop} to {pos.entry_price} — D-06",
                )
                self._on_event(ev)
                events.append(ev)
                log.info("position.breakeven", id=pos.id, new_stop=pos.stop_price)

            # Stop hit check
            stop_hit = (
                (pos.side == OrderSide.SHORT and bar_high >= pos.stop_price)
                or (pos.side == OrderSide.LONG and bar_low <= pos.stop_price)
            )
            if stop_hit:
                to_close.append((pos.id, PositionEventType.STOP_HIT, pos.stop_price, "Stop hit"))
                continue

            # Target hit check
            target_hit = (
                (pos.side == OrderSide.LONG and bar_high >= pos.target_price)
                or (pos.side == OrderSide.SHORT and bar_low <= pos.target_price)
            )
            if target_hit:
                to_close.append((pos.id, PositionEventType.TARGET_HIT, pos.target_price, "Target hit"))
                continue

            # D-09: Max hold timeout
            if pos.bars_held >= self.config.max_hold_bars:
                to_close.append(
                    (
                        pos.id,
                        PositionEventType.TIMEOUT_EXIT,
                        bar_close,
                        f"Timeout: {pos.bars_held} bars held — D-09",
                    )
                )

        for pos_id, event_type, exit_price, reason in to_close:
            ev = self._close(pos_id, exit_price, event_type, reason)
            if ev:
                events.append(ev)

        return events

    def close_position(
        self, position_id: str, exit_price: float, reason: str = "Manual exit"
    ) -> PositionEvent | None:
        """Manually close a position. Emits MANUAL_EXIT event."""
        return self._close(position_id, exit_price, PositionEventType.MANUAL_EXIT, reason)

    def _close(
        self,
        position_id: str,
        exit_price: float,
        event_type: PositionEventType,
        reason: str,
    ) -> PositionEvent | None:
        """Internal: close position, compute realized P&L, emit event, remove from dict."""
        pos = self._positions.pop(position_id, None)
        if pos is None:
            log.warning("position.close_not_found", id=position_id)
            return None

        closing_contracts = pos.remaining_contracts or pos.contracts
        realized_pnl = (
            (exit_price - pos.entry_price)
            * pos.direction
            * NQ_DOLLARS_PER_POINT
            * closing_contracts
        )
        # Add any previously-realized partial exit PnL
        for pe in pos.partial_exits:
            realized_pnl += (
                (pe["price"] - pos.entry_price)
                * pos.direction
                * NQ_DOLLARS_PER_POINT
                * pe["contracts"]
            )
        ev = PositionEvent(
            event_type=event_type,
            position_id=pos.id,
            side=pos.side,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            pnl=realized_pnl,
            bars_held=pos.bars_held,
            ts=time.time(),
            signal_tier=pos.signal_tier,
            signal_score=pos.signal_score,
            reason=reason,
        )
        self._on_event(ev)
        log.info(
            "position.closed",
            id=pos.id,
            type=event_type.value,
            pnl=realized_pnl,
            bars=pos.bars_held,
        )
        return ev
