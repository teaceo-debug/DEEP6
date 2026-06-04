from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from deep6v2.types.bar import FootprintBar
from deep6v2.types.signal import Direction


@dataclass(slots=True)
class OpenTrade:
    session_date: date
    side: str
    direction: Direction
    entry_price: float
    entry_time: datetime
    entry_bar_index: int
    stop_price: float
    target_price: float


@dataclass(slots=True)
class TradeRecord:
    date: date
    side: str
    entry: float
    exit: float
    pnl: float
    exit_reason: str
    bars_held: int
    entry_time: datetime
    exit_time: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "date": self.date,
            "side": self.side,
            "entry": self.entry,
            "exit": self.exit,
            "pnl": self.pnl,
            "exit_reason": self.exit_reason,
            "bars_held": self.bars_held,
            "entry_time": self.entry_time,
            "exit_time": self.exit_time,
        }


class TradeSimulator:
    def __init__(self, *, dollars_per_point: float = 20.0) -> None:
        self._dollars_per_point = dollars_per_point
        self._open_trade: OpenTrade | None = None

    @property
    def in_position(self) -> bool:
        return self._open_trade is not None

    def enter(
        self,
        *,
        session_date: date,
        entry_price: float,
        direction: Direction,
        entry_time: datetime,
        entry_bar_index: int,
        stop_price: float,
        target_price: float,
    ) -> None:
        if self._open_trade is not None:
            raise RuntimeError("trade already open")
        if direction not in (Direction.BULLISH, Direction.BEARISH):
            raise ValueError("direction must be bullish or bearish")

        self._open_trade = OpenTrade(
            session_date=session_date,
            side="LONG" if direction is Direction.BULLISH else "SHORT",
            direction=direction,
            entry_price=float(entry_price),
            entry_time=entry_time,
            entry_bar_index=entry_bar_index,
            stop_price=float(stop_price),
            target_price=float(target_price),
        )

    def on_bar(self, bar: FootprintBar) -> TradeRecord | None:
        trade = self._open_trade
        if trade is None:
            return None

        stop_hit = self._stop_hit(trade, bar)
        target_hit = self._target_hit(trade, bar)
        if stop_hit:
            return self._close_trade(bar, trade.stop_price, "stop")
        if target_hit:
            return self._close_trade(bar, trade.target_price, "target")
        return None

    def force_close(self, exit_price: float, exit_time: datetime, exit_bar_index: int) -> TradeRecord | None:
        trade = self._open_trade
        if trade is None:
            return None
        return self._finalize_trade(
            trade=trade,
            exit_price=float(exit_price),
            exit_reason="session_close",
            exit_time=exit_time,
            exit_bar_index=exit_bar_index,
        )

    @staticmethod
    def _stop_hit(trade: OpenTrade, bar: FootprintBar) -> bool:
        if trade.direction is Direction.BULLISH:
            return bar.low <= trade.stop_price
        return bar.high >= trade.stop_price

    @staticmethod
    def _target_hit(trade: OpenTrade, bar: FootprintBar) -> bool:
        if trade.direction is Direction.BULLISH:
            return bar.high >= trade.target_price
        return bar.low <= trade.target_price

    def _close_trade(self, bar: FootprintBar, exit_price: float, exit_reason: str) -> TradeRecord:
        trade = self._open_trade
        if trade is None:
            raise RuntimeError("no trade open")
        return self._finalize_trade(
            trade=trade,
            exit_price=exit_price,
            exit_reason=exit_reason,
            exit_time=bar.timestamp,
            exit_bar_index=bar.bar_index,
        )

    def _finalize_trade(
        self,
        *,
        trade: OpenTrade,
        exit_price: float,
        exit_reason: str,
        exit_time: datetime,
        exit_bar_index: int,
    ) -> TradeRecord:
        multiplier = 1.0 if trade.direction is Direction.BULLISH else -1.0
        pnl = (float(exit_price) - trade.entry_price) * multiplier * self._dollars_per_point
        record = TradeRecord(
            date=trade.session_date,
            side=trade.side,
            entry=trade.entry_price,
            exit=float(exit_price),
            pnl=pnl,
            exit_reason=exit_reason,
            bars_held=max(0, exit_bar_index - trade.entry_bar_index),
            entry_time=trade.entry_time,
            exit_time=exit_time,
        )
        self._open_trade = None
        return record


__all__ = ["OpenTrade", "TradeRecord", "TradeSimulator"]
