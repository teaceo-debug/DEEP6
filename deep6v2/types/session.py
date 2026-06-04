from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from deep6v2.types.bar import FootprintBar, SessionType
from deep6v2.types.signal import Direction


@dataclass
class SessionContext:
    atr: float
    cvd: float
    vah: float
    val: float
    poc: float
    session_type: SessionType
    session_open_bar_index: int
    current_bar: FootprintBar | None = None
    bar_history: deque[FootprintBar] = field(default_factory=lambda: deque(maxlen=50))
    price_history: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    cvd_history: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    delta_history: deque[int] = field(default_factory=lambda: deque(maxlen=50))
    poc_history: deque[float] = field(default_factory=lambda: deque(maxlen=50))
    vol_history: deque[int] = field(default_factory=lambda: deque(maxlen=50))
    imbalance_history: deque[dict[float, float]] = field(default_factory=lambda: deque(maxlen=50))
    e10_direction: Direction | None = None
    e10_strength: float = 0.0
    e10_stale: bool = True


__all__ = ["SessionContext"]
