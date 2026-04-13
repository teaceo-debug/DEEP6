"""BarBuilder: asyncio coroutine that fires on_bar_close at bar boundaries.

Two instances run independently (1m and 5m) via asyncio.gather().
Both share the same SharedState and on_bar_close callback.

Per D-04: primary 1-min bars + secondary 5-min bars run independently.
Per D-05: each timeframe has its own FootprintBar instance.
Per D-06: RTH only — 9:30 AM to 4:00 PM Eastern.
Per D-08: ticks outside RTH are not accumulated (gate in on_trade).
Per D-17: FROZEN state — bar processing halted during disconnect.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from deep6.state.footprint import FootprintBar, BarHistory

EASTERN = ZoneInfo("America/New_York")


def next_boundary(period_seconds: int) -> datetime:
    """Compute the next UTC bar boundary (next multiple of period_seconds).

    Returns the smallest UTC datetime whose Unix timestamp is divisible
    by period_seconds and is strictly in the future.

    Example: period_seconds=60 at 14:30:37 UTC → 14:31:00 UTC
    """
    import time
    now_ts = time.time()
    next_ts = (now_ts // period_seconds + 1) * period_seconds
    return datetime.fromtimestamp(next_ts, tz=timezone.utc)


class BarBuilder:
    """Sleeps to bar boundary, closes bar, fires on_bar_close callback.

    on_trade() is called synchronously from tick_feed callback — must be O(1).
    run() is an asyncio coroutine — launched via asyncio.gather() in __main__.py.

    Thread safety: single asyncio event loop — no locks needed.
    """

    def __init__(self, period_seconds: int, label: str, state) -> None:
        """
        Args:
            period_seconds: Bar duration in seconds (60 for 1m, 300 for 5m).
            label:          Human label for logging ("1m" or "5m").
            state:          SharedState — provides freeze_guard, session, atr_trackers.
        """
        self.period = period_seconds
        self.label = label
        self.state = state
        self.current_bar = FootprintBar()
        self.history: "deque[FootprintBar]" = BarHistory()

    def _is_rth(self) -> bool:
        """True between 9:30 AM and 4:00 PM Eastern (D-06).

        Uses zoneinfo for correct DST handling — no manual UTC offset.
        Per T-02-04: checked synchronously on every on_trade() call.
        """
        now_et = datetime.now(EASTERN)
        rth_open  = now_et.replace(hour=9,  minute=30, second=0, microsecond=0)
        rth_close = now_et.replace(hour=16, minute=0,  second=0, microsecond=0)
        return rth_open <= now_et < rth_close

    def on_trade(self, price: float, size: int, aggressor: int) -> None:
        """Accumulate one trade tick into the current bar. Synchronous, O(1).

        D-08: gate — do not accumulate outside RTH.
        D-17: gate — do not accumulate when FROZEN (reconnect cycle in progress).
        """
        if not self._is_rth():
            return
        if self.state.freeze_guard.is_frozen:
            return
        self.current_bar.add_trade(price, size, aggressor)

    async def run(self) -> None:
        """Main bar loop: sleep to boundary, finalize bar, fire callbacks.

        Resets accumulator before any await so ticks arriving during on_bar_close
        processing are captured in the next bar (no missed ticks).
        """
        while True:
            target = next_boundary(self.period)
            now = datetime.now(timezone.utc)
            sleep_secs = (target - now).total_seconds()
            if sleep_secs > 0:
                await asyncio.sleep(sleep_secs)

            if not self._is_rth():
                # Outside RTH: discard accumulated ticks without firing (D-08)
                self.current_bar = FootprintBar()
                continue

            if self.state.freeze_guard.is_frozen:
                # FROZEN: discard bar and wait for reconnection (D-17)
                self.current_bar = FootprintBar()
                continue

            # --- Bar close sequence ---
            prior_cvd = self.state.session.cvd
            closed_bar = self.current_bar
            closed_bar.timestamp = target.timestamp()
            closed_bar.finalize(prior_cvd)

            # Reset accumulator BEFORE any awaits — no missed ticks window
            self.current_bar = FootprintBar()

            # Store in ring buffer (ARCH-04: feeds Phase 3 correlation matrix)
            self.history.appendleft(closed_bar)

            # Update session accumulators (CVD, VWAP)
            self.state.session.update(closed_bar)

            # Update ATR tracker for this timeframe
            if closed_bar.high > 0.0:
                self.state.atr_trackers[self.label].update(
                    closed_bar.high, closed_bar.low, closed_bar.close
                )

            # Fire on_bar_close for all signal engines (Phase 2+ hook)
            await self.state.on_bar_close(self.label, closed_bar)
