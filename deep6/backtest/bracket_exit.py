"""BracketExitTracker — resolve open trades against bracket stop/target.

Phase 13-03. ReplaySession emits a trade row on TYPE_A/TYPE_B bars with
``entry_price=bar.close`` but leaves exit columns NULL. This tracker
holds those open trades and walks each subsequent bar's (high, low) to
determine whether the stop or target was touched, then emits a
``ClosedTrade`` for ReplaySession to persist via
``DuckDBResultStore.update_trade_exit``.

Fill model: "first touch"
-------------------------
The simplest defensible bracket-exit model. A stop is filled the first
bar whose ``low <= stop_price`` (long) / ``high >= stop_price`` (short).
A target is filled the first bar whose ``high >= target_price`` (long) /
``low <= target_price`` (short). No intra-bar path reconstruction —
phase 14 may replace this with queue-position-aware fills.

Pessimistic tie-breaking
------------------------
If the **same bar** touches BOTH the stop and the target (i.e. bar range
straddles both levels), this tracker assumes the **STOP hit first**.

Rationale: we have no intrabar sequencing information in a bar-aggregated
feed. Assuming the stop fires first is the pessimistic choice — it
underestimates P&L, producing a conservative bias. A real system that
overestimates by assuming target-first would be intellectually dishonest,
because the market does not owe us the favorable path. Backtest honesty
> optimism.

Slippage
--------
  - STOP fills are market-order fills: add ``slippage_ticks`` adverse to
    the fill price (long stop: subtract ticks from stop; short stop: add).
  - TARGET fills are limit-order fills: no slippage (you filled *at* your
    limit price or not at all).

Commissions
-----------
Per round-trip: ``2 * commission_per_side``. Applied after tick→dollar
conversion so ``pnl`` is net.

Force-exit
----------
Trades that hit neither bracket within ``max_hold_bars`` are force-closed
at the next bar's close with ``exit_reason="HOLD_EXPIRY"``. This prevents
trades dangling open at stream end. ReplaySession additionally flushes
any still-open trades on ``__aexit__`` with ``exit_reason="TRUNCATED"``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from deep6.backtest.config import BacktestConfig
from deep6.state.footprint import FootprintBar


ExitReason = Literal["STOP", "TARGET", "HOLD_EXPIRY", "TRUNCATED"]


@dataclass
class ClosedTrade:
    """Result of resolving one open trade against a subsequent bar."""

    trade_id: str
    exit_ts: float            # POSIX seconds — matches EventClock.now() units
    exit_price: float
    pnl_ticks: float          # signed (positive = winner) before commission
    pnl_dollars: float        # signed, net of commissions
    exit_reason: ExitReason


@dataclass
class _OpenTrade:
    trade_id: str
    entry_price: float
    direction: int            # +1 long, -1 short
    entry_ts: float
    bars_held: int
    stop_price: float
    target_price: float


class BracketExitTracker:
    """Hold open trades, resolve them against subsequent bars.

    See module docstring for fill model, tie-breaking, slippage, and
    commissions. Stateful: one instance per replay session.
    """

    def __init__(self, config: BacktestConfig) -> None:
        self._config = config
        self._open: dict[str, _OpenTrade] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def open_trade(
        self,
        trade_id: str,
        entry_price: float,
        direction: int,
        entry_ts: float,
    ) -> None:
        """Register a new open trade.

        Args:
            trade_id: unique id — used as the key for later
                ``update_trade_exit`` in the result store.
            entry_price: fill price (typically ``bar.close`` at signal bar).
            direction: +1 for long, -1 for short.
            entry_ts: POSIX seconds of the signal bar close.
        """
        if direction not in (1, -1):
            raise ValueError(f"direction must be +1 or -1, got {direction}")
        cfg = self._config
        stop_pts = cfg.stop_ticks * cfg.tick_size
        tgt_pts = cfg.target_ticks * cfg.tick_size
        if direction == 1:
            stop_price = entry_price - stop_pts
            target_price = entry_price + tgt_pts
        else:
            stop_price = entry_price + stop_pts
            target_price = entry_price - tgt_pts
        self._open[trade_id] = _OpenTrade(
            trade_id=trade_id,
            entry_price=entry_price,
            direction=direction,
            entry_ts=entry_ts,
            bars_held=0,
            stop_price=stop_price,
            target_price=target_price,
        )

    def on_bar(self, bar: FootprintBar, ts: float) -> list[ClosedTrade]:
        """Walk every open trade against this bar's range.

        Emits a ClosedTrade for each trade whose bracket was touched (or
        whose hold expired). Closed trades are removed from the open set.

        Returns a (possibly empty) list of ClosedTrade results.
        """
        if not self._open:
            return []
        closed: list[ClosedTrade] = []
        high = bar.high
        low = bar.low
        for trade_id in list(self._open.keys()):
            ot = self._open[trade_id]
            ot.bars_held += 1

            stop_hit = self._stop_touched(ot, high, low)
            tgt_hit = self._target_touched(ot, high, low)

            if stop_hit and tgt_hit:
                # Pessimistic tie-break: assume STOP filled first.
                closed.append(self._close_stop(ot, ts))
                del self._open[trade_id]
            elif stop_hit:
                closed.append(self._close_stop(ot, ts))
                del self._open[trade_id]
            elif tgt_hit:
                closed.append(self._close_target(ot, ts))
                del self._open[trade_id]
            elif ot.bars_held >= self._config.max_hold_bars:
                # Force-exit at bar close — neither bracket hit within window.
                closed.append(self._close_at_price(
                    ot, ts, price=bar.close, reason="HOLD_EXPIRY",
                ))
                del self._open[trade_id]
        return closed

    def force_close_all(
        self, last_price: float, ts: float,
        reason: ExitReason = "TRUNCATED",
    ) -> list[ClosedTrade]:
        """Close any still-open trades at ``last_price``.

        Called by ReplaySession on ``__aexit__`` so no trade dangles open
        in the output. Default reason is ``TRUNCATED`` (stream ended
        before bracket resolution).
        """
        closed: list[ClosedTrade] = []
        for trade_id in list(self._open.keys()):
            ot = self._open[trade_id]
            closed.append(self._close_at_price(
                ot, ts, price=last_price, reason=reason,
            ))
            del self._open[trade_id]
        return closed

    @property
    def open_count(self) -> int:
        return len(self._open)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _stop_touched(ot: _OpenTrade, high: float, low: float) -> bool:
        if ot.direction == 1:
            return low <= ot.stop_price
        return high >= ot.stop_price

    @staticmethod
    def _target_touched(ot: _OpenTrade, high: float, low: float) -> bool:
        if ot.direction == 1:
            return high >= ot.target_price
        return low <= ot.target_price

    def _close_stop(self, ot: _OpenTrade, ts: float) -> ClosedTrade:
        # Market-order fill: apply adverse slippage.
        cfg = self._config
        slip = cfg.slippage_ticks * cfg.tick_size
        if ot.direction == 1:
            fill = ot.stop_price - slip   # long stop fills worse (lower)
        else:
            fill = ot.stop_price + slip   # short stop fills worse (higher)
        return self._build_closed(ot, ts, fill, "STOP")

    def _close_target(self, ot: _OpenTrade, ts: float) -> ClosedTrade:
        # Limit fill at the target — no slippage.
        return self._build_closed(ot, ts, ot.target_price, "TARGET")

    def _close_at_price(
        self, ot: _OpenTrade, ts: float, price: float, reason: ExitReason,
    ) -> ClosedTrade:
        return self._build_closed(ot, ts, price, reason)

    def _build_closed(
        self, ot: _OpenTrade, ts: float, fill_price: float,
        reason: ExitReason,
    ) -> ClosedTrade:
        cfg = self._config
        pnl_points = (fill_price - ot.entry_price) * ot.direction
        pnl_ticks = pnl_points / cfg.tick_size
        gross = pnl_ticks * cfg.tick_value
        commissions = 2.0 * cfg.commission_per_side
        pnl_dollars = gross - commissions
        return ClosedTrade(
            trade_id=ot.trade_id,
            exit_ts=ts,
            exit_price=fill_price,
            pnl_ticks=pnl_ticks,
            pnl_dollars=pnl_dollars,
            exit_reason=reason,
        )
