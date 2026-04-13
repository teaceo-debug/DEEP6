"""BarBuilder: asyncio coroutine that fires on_bar_close at bar boundaries.

Two instances run independently (1m and 5m) via asyncio.gather().
Both share the same on_bar_close callback from SharedState.

Per D-04, D-05: dual-timeframe 1m+5m BarBuilder instances, each with own FootprintBar.
Per D-06: RTH gate -- 9:30 AM to 4:00 PM Eastern.
Per D-08: DOM/tick data outside RTH is silently discarded -- no footprint accumulation.
Per D-13: on_trade() is synchronous O(1) -- called inline from asyncio tick callback.
Per D-17: freeze_guard.is_frozen check prevents accumulation during FROZEN state.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from deep6.state.footprint import FootprintBar, BarHistory

EASTERN = ZoneInfo("America/New_York")

# RTH session bounds (Eastern time)
RTH_OPEN_HOUR = 9
RTH_OPEN_MIN = 30
RTH_CLOSE_HOUR = 16
RTH_CLOSE_MIN = 0


def next_boundary(period_seconds: int) -> datetime:
    """Compute the next UTC bar boundary (next multiple of period_seconds).

    Returns a UTC-aware datetime whose timestamp is divisible by period_seconds.
    This aligns bars to clock boundaries (e.g., 60s -> on the minute).
    """
    import time
    now_ts = time.time()
    next_ts = (now_ts // period_seconds + 1) * period_seconds
    return datetime.fromtimestamp(next_ts, tz=timezone.utc)


class BarBuilder:
    """Sleeps to bar boundary, closes bar, fires on_bar_close callback.

    on_trade() is called synchronously from tick_feed callback -- must be O(1).
    run() is an asyncio coroutine -- launched via asyncio.gather() in main.

    Two instances (label="1m" and label="5m") run independently.
    Each instance has its own current_bar (FootprintBar) and history (deque).
    """

    def __init__(self, period_seconds: int, label: str, state) -> None:
        self.period = period_seconds
        self.label = label        # "1m" or "5m"
        self.state = state
        self.current_bar = FootprintBar()
        self.history = BarHistory()

    def _is_rth(self) -> bool:
        """True between 9:30 AM and 4:00 PM Eastern (D-06).

        Uses zoneinfo.ZoneInfo("America/New_York") for DST-correct handling.
        Per T-02-04: called synchronously on every on_trade() -- cannot be bypassed.
        """
        now_et = datetime.now(EASTERN)
        rth_open  = now_et.replace(hour=RTH_OPEN_HOUR,  minute=RTH_OPEN_MIN,  second=0, microsecond=0)
        rth_close = now_et.replace(hour=RTH_CLOSE_HOUR, minute=RTH_CLOSE_MIN, second=0, microsecond=0)
        return rth_open <= now_et < rth_close

    def on_trade(self, price: float, size: int, aggressor: int) -> None:
        """Synchronous -- called directly from tick callback. O(1).

        D-08: gate DOM/tick data outside RTH -- do not accumulate.
        D-17: do not accumulate during FROZEN state.
        """
        if not self._is_rth():
            return
        if self.state.freeze_guard.is_frozen:
            return
        self.current_bar.add_trade(price, size, aggressor)

    async def run(self) -> None:
        """Main coroutine: sleep to next bar boundary, finalize bar, fire callbacks.

        Runs forever -- cancelled by asyncio.gather() shutdown in main().
        Non-RTH bar boundaries result in a silent reset (D-08).
        FROZEN state results in a silent reset (D-17).
        """
        while True:
            target = next_boundary(self.period)
            now = datetime.now(timezone.utc)
            sleep_secs = (target - now).total_seconds()
            if sleep_secs > 0:
                await asyncio.sleep(sleep_secs)

            if not self._is_rth():
                # Outside RTH: reset without firing callbacks (D-08)
                self.current_bar = FootprintBar()
                continue

            if self.state.freeze_guard.is_frozen:
                # FROZEN state: discard bar, do not fire callbacks (D-17)
                self.current_bar = FootprintBar()
                continue

            # --- Bar close sequence ---
            prior_cvd = self.state.session.cvd
            closed_bar = self.current_bar
            closed_bar.timestamp = target.timestamp()
            closed_bar.finalize(prior_cvd)

            # Reset accumulator BEFORE any awaits -- ensures no ticks are missed
            # between finalize() and the next on_trade() call in the event loop.
            self.current_bar = FootprintBar()

            # Store in ring buffer (ARCH-04: feeds Phase 3 correlation matrix)
            # appendleft so history[0] is always the most recent bar
            self.history.appendleft(closed_bar)

            # Update session CVD and VWAP
            self.state.session.update(closed_bar)

            # Update ATR for this timeframe (ARCH-03)
            self.state.atr_trackers[self.label].update(
                closed_bar.high, closed_bar.low, closed_bar.close
            )

            # Fire on_bar_close for all signal engines (Phase 2+)
            await self.state.on_bar_close(self.label, closed_bar)
