from __future__ import annotations

from collections import defaultdict, deque
from datetime import date, datetime
from typing import Callable

from deep6v2.clock import Clock, WallClock
from deep6v2.data.tick_classifier import AggressorSide, ClassifiedTick
from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.session import SessionContext


class BarBuilder:
    """Accumulate classified ticks into RTH footprint bars."""

    def __init__(
        self,
        clock: Clock | None = None,
        on_bar_close: Callable[[FootprintBar, SessionContext], None] | None = None,
    ) -> None:
        self._clock = clock or WallClock()
        self._on_bar_close = on_bar_close

        self._current_bar_minute: int | None = None
        self._current_bar_date: date | None = None
        self._bar_open: float | None = None
        self._bar_high: float = float("-inf")
        self._bar_low: float = float("inf")
        self._bar_last: float | None = None
        self._bid_volumes: dict[float, int] = defaultdict(int)
        self._ask_volumes: dict[float, int] = defaultdict(int)
        self._total_volume = 0
        self._bar_delta = 0

        self._session_cvd = 0.0
        self._session_open_bar_index = 0
        self._current_bar_index = 0
        self._session_type = SessionType.ETH
        self._active_session_date: date | None = None

        self._five_minute_bars: deque[FootprintBar] = deque(maxlen=50)

        self._ctx = SessionContext(
            atr=0.0,
            cvd=0.0,
            vah=0.0,
            val=0.0,
            poc=0.0,
            session_type=SessionType.ETH,
            session_open_bar_index=0,
        )

    def on_tick(self, tick: ClassifiedTick) -> None:
        now = self._clock.now()
        if not self._clock.is_rth(now):
            return

        bar_index = self._clock.session_bar_index(now)
        current_minute = self._minute_key(now)
        session_date = now.date()

        if self._should_reset_session(now, bar_index):
            self._reset_session(session_date, bar_index)

        if self._current_bar_minute is not None and (
            current_minute != self._current_bar_minute or session_date != self._current_bar_date
        ):
            bar = self._finalize_bar(now)
            if bar is not None:
                self._notify_bar_close(bar)
            self._start_new_bar(tick.price, bar_index, current_minute, session_date)
        elif self._current_bar_minute is None:
            self._start_new_bar(tick.price, bar_index, current_minute, session_date)

        self._current_bar_index = bar_index
        self._bar_high = max(self._bar_high, tick.price)
        self._bar_low = min(self._bar_low, tick.price)
        self._bar_last = tick.price
        self._total_volume += tick.size

        if tick.aggressor == AggressorSide.BUY:
            self._ask_volumes[tick.price] += tick.size
            self._bar_delta += tick.size
        elif tick.aggressor == AggressorSide.SELL:
            self._bid_volumes[tick.price] += tick.size
            self._bar_delta -= tick.size

    def _should_reset_session(self, now: datetime, bar_index: int) -> bool:
        if bar_index != 0:
            return False
        if self._session_type != SessionType.RTH:
            return True
        return self._active_session_date != now.date()

    def _start_new_bar(self, open_price: float, bar_index: int, minute_key: int, bar_date: date) -> None:
        self._bar_open = open_price
        self._bar_high = open_price
        self._bar_low = open_price
        self._bar_last = open_price
        self._bid_volumes = defaultdict(int)
        self._ask_volumes = defaultdict(int)
        self._total_volume = 0
        self._bar_delta = 0
        self._current_bar_minute = minute_key
        self._current_bar_date = bar_date
        self._current_bar_index = bar_index

    def _reset_session(self, session_date: date, bar_index: int) -> None:
        self._session_cvd = 0.0
        self._session_type = SessionType.RTH
        self._session_open_bar_index = bar_index
        self._active_session_date = session_date
        self._current_bar_minute = None
        self._current_bar_date = None
        self._bar_open = None
        self._bar_last = None
        self._bar_high = float("-inf")
        self._bar_low = float("inf")
        self._bid_volumes = defaultdict(int)
        self._ask_volumes = defaultdict(int)
        self._total_volume = 0
        self._bar_delta = 0
        self._five_minute_bars.clear()
        self._ctx = SessionContext(
            atr=0.0,
            cvd=0.0,
            vah=0.0,
            val=0.0,
            poc=0.0,
            session_type=SessionType.RTH,
            session_open_bar_index=bar_index,
        )

    def _finalize_bar(self, now: datetime) -> FootprintBar | None:
        if self._bar_open is None or self._bar_last is None or self._current_bar_minute is None:
            return None

        all_volumes: dict[float, int] = defaultdict(int)
        for price, volume in self._bid_volumes.items():
            all_volumes[price] += volume
        for price, volume in self._ask_volumes.items():
            all_volumes[price] += volume

        poc_price = max(all_volumes, key=all_volumes.get) if all_volumes else self._bar_last
        poc_volume = all_volumes.get(poc_price, 0)
        vah, val = self._calculate_value_area(dict(all_volumes), poc_price)

        self._session_cvd += self._bar_delta

        bar = FootprintBar(
            open=self._bar_open,
            high=self._bar_high,
            low=self._bar_low,
            close=self._bar_last,
            delta=self._bar_delta,
            total_volume=self._total_volume,
            bid_volumes=dict(self._bid_volumes),
            ask_volumes=dict(self._ask_volumes),
            poc_price=poc_price,
            poc_volume=poc_volume,
            vah=vah,
            val=val,
            cvd=self._session_cvd,
            bar_index=self._current_bar_index,
            timestamp=now,
            session_type=self._session_type,
        )

        self._ctx.bar_history.append(bar)
        self._ctx.price_history.append(bar.close)
        self._ctx.cvd_history.append(self._session_cvd)
        self._ctx.delta_history.append(bar.delta)
        self._ctx.poc_history.append(bar.poc_price)
        self._ctx.vol_history.append(bar.total_volume)
        self._ctx.cvd = self._session_cvd
        self._ctx.vah = bar.vah
        self._ctx.val = bar.val
        self._ctx.poc = bar.poc_price
        self._ctx.current_bar = bar

        self._update_five_minute_history()

        return bar

    def _update_five_minute_history(self) -> None:
        bars = self._ctx.bar_history
        if len(bars) >= 5 and bars[-1].bar_index % 5 == 4:
            self._five_minute_bars.append(bars[-1])

    def _calculate_value_area(self, all_volumes: dict[float, int], poc_price: float) -> tuple[float, float]:
        total_volume = sum(all_volumes.values())
        if total_volume == 0 or not all_volumes:
            return poc_price, poc_price

        sorted_prices = sorted(all_volumes)
        if poc_price not in all_volumes:
            return poc_price, poc_price

        target_volume = total_volume * 0.70
        poc_index = sorted_prices.index(poc_price)
        vah_index = poc_index
        val_index = poc_index
        accumulated_volume = all_volumes[poc_price]

        while accumulated_volume < target_volume:
            above_volume = 0
            below_volume = 0

            if vah_index + 1 < len(sorted_prices):
                above_volume = all_volumes[sorted_prices[vah_index + 1]]
            if val_index - 1 >= 0:
                below_volume = all_volumes[sorted_prices[val_index - 1]]

            if above_volume >= below_volume and vah_index + 1 < len(sorted_prices):
                vah_index += 1
                accumulated_volume += above_volume
            elif below_volume > 0 and val_index - 1 >= 0:
                val_index -= 1
                accumulated_volume += below_volume
            else:
                break

        return sorted_prices[vah_index], sorted_prices[val_index]

    def _notify_bar_close(self, bar: FootprintBar) -> None:
        if self._on_bar_close is not None:
            self._on_bar_close(bar, self._ctx)

    @staticmethod
    def _minute_key(dt: datetime) -> int:
        return ((dt.year * 1000 + dt.timetuple().tm_yday) * 1440) + (dt.hour * 60) + dt.minute


__all__ = ["BarBuilder"]
