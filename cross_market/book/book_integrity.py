"""Book integrity validator for MBO reconstruction hard gate."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from cross_market.book.mbo_order_book import MBOOrderBook


class AlertSeverity(str, Enum):
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(slots=True)
class IntegrityAlert:
    severity: AlertSeverity
    check_type: str
    detail: str
    sequence_id: Optional[int] = None


class BookIntegrityValidator:
    """Validates MBO book state on every event; critical alerts pause consumers."""

    STALE_THRESHOLD_MS = 30_000

    def __init__(self) -> None:
        self._last_sequence = -1
        self._last_update_time: dict[int, float] = {}
        self._consumers_paused = False

    def validate(
        self,
        book: MBOOrderBook,
        sequence_id: int,
        current_time_ms: float,
    ) -> list[IntegrityAlert]:
        alerts: list[IntegrityAlert] = []

        if self._last_sequence >= 0 and sequence_id != self._last_sequence + 1:
            alerts.append(
                IntegrityAlert(
                    severity=AlertSeverity.ERROR,
                    check_type="SEQUENCE_GAP",
                    detail=f"Expected {self._last_sequence + 1}, got {sequence_id}",
                    sequence_id=sequence_id,
                )
            )
        self._last_sequence = sequence_id

        best_bid = book.best_bid()
        best_ask = book.best_ask()
        if best_bid is not None and best_ask is not None and best_bid >= best_ask:
            alerts.append(
                IntegrityAlert(
                    severity=AlertSeverity.CRITICAL,
                    check_type="CROSSED_BOOK",
                    detail=f"best_bid={best_bid} >= best_ask={best_ask}",
                    sequence_id=sequence_id,
                )
            )

        for tick, level in book.bids.items():
            if level.total_size < 0:
                alerts.append(
                    IntegrityAlert(
                        severity=AlertSeverity.CRITICAL,
                        check_type="NEGATIVE_SIZE",
                        detail=f"bid at {tick * 0.25} size={level.total_size}",
                        sequence_id=sequence_id,
                    )
                )

        for tick, level in book.asks.items():
            if level.total_size < 0:
                alerts.append(
                    IntegrityAlert(
                        severity=AlertSeverity.CRITICAL,
                        check_type="NEGATIVE_SIZE",
                        detail=f"ask at {tick * 0.25} size={level.total_size}",
                        sequence_id=sequence_id,
                    )
                )

        for tick in [*book.bids.keys(), *book.asks.keys()]:
            last_update = self._last_update_time.get(tick, current_time_ms)
            if current_time_ms - last_update > self.STALE_THRESHOLD_MS:
                alerts.append(
                    IntegrityAlert(
                        severity=AlertSeverity.WARN,
                        check_type="STALE_LEVEL",
                        detail=(
                            f"Level {tick * 0.25} not updated in {self.STALE_THRESHOLD_MS}ms"
                        ),
                        sequence_id=sequence_id,
                    )
                )

        if best_bid is None and best_ask is None:
            alerts.append(
                IntegrityAlert(
                    severity=AlertSeverity.WARN,
                    check_type="EMPTY_BOOK",
                    detail="No bid or ask levels present",
                    sequence_id=sequence_id,
                )
            )

        if any(alert.severity == AlertSeverity.CRITICAL for alert in alerts):
            self._consumers_paused = True

        return alerts

    def record_update(self, price_tick: int, time_ms: float) -> None:
        self._last_update_time[price_tick] = time_ms

    def clear_pause(self) -> None:
        self._consumers_paused = False

    @property
    def consumers_paused(self) -> bool:
        return self._consumers_paused
