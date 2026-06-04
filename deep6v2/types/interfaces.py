from __future__ import annotations

from typing import Protocol, runtime_checkable

from deep6v2.types.bar import FootprintBar
from deep6v2.types.dom import DOMSnapshot
from deep6v2.types.session import SessionContext
from deep6v2.types.signal import Direction, SignalResult


@runtime_checkable
class ISignalDetector(Protocol):
    def on_bar(self, bar: FootprintBar, ctx: SessionContext) -> list[SignalResult]: ...


@runtime_checkable
class IDepthConsumingDetector(Protocol):
    def on_depth(self, snapshot: DOMSnapshot) -> None: ...


@runtime_checkable
class IAbsorptionZoneReceiver(Protocol):
    def mark_absorption_zone(self, price: float, direction: Direction, strength: float) -> None: ...


__all__ = ["IAbsorptionZoneReceiver", "IDepthConsumingDetector", "ISignalDetector"]
